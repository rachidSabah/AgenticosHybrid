"""Self-Healing Engine — severity-classified automatic recovery.

Severity classification:
  CRITICAL (4): System-wide failure, data loss risk → requires user approval
  HIGH    (3): Subsystem failure, functional degradation → requires user approval
  MEDIUM  (2): Non-critical service degraded → auto-repair if confident
  LOW     (1): Minor glitch, transient error → auto-repair silently

Auto-repair actions (MEDIUM/LOW only):
  - WebSocket reconnect
  - Cache rebuild
  - Service restart (non-critical)
  - Configuration reload
  - Provider re-bind
  - Index rebuild

Architectural / destructive actions (CRITICAL/HIGH):
  - Full backend restart
  - Database repair
  - Plugin reload
  - Security policy reset
  → Queued for user approval

Integration:
  - Subscribes to EventBus for automatic detection (failures, degradation, heartbeat loss)
  - Exposes status via API for Mission Control display
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum
from typing import Callable, Optional

from agentic_os.config import Settings
from agentic_os.core.recovery import RecoveryManagerImpl
from agentic_os.domain.events import EventEnvelope, Topic
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.event_bus import EventBus

log = get_logger("core.self_healing")


class Severity(IntEnum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class HealingIssue:
    id: str
    subsystem: str
    description: str
    severity: Severity
    detected_at: float  # timestamp
    auto_repairable: bool
    auto_repair_action: Optional[str] = None
    requires_approval: bool = False
    approved: Optional[bool] = None  # None = pending, True = approved, False = rejected
    resolution: Optional[str] = None
    resolved_at: Optional[float] = None
    error: Optional[str] = None


@dataclass
class HealingAction:
    name: str
    description: str
    severity: Severity
    auto_repair: bool  # True = run automatically, False = require approval
    run: Callable[[], bool]  # Returns True on success


class SelfHealingEngine:
    """Monitors system health and performs automatic recovery.

    Subscribes to EventBus topics for failure detection and exposes
    a live issue list for Mission Control visualization.
    """

    def __init__(
        self,
        bus: EventBus,
        recovery: RecoveryManagerImpl,
        settings: Settings,
    ) -> None:
        self._bus = bus
        self._recovery = recovery
        self._settings = settings
        self._issues: list[HealingIssue] = []
        self._actions: list[HealingAction] = []
        self._running = False
        self._issue_counter = 0

        # Register built-in healing actions
        self._register_actions()

    def _register_actions(self) -> None:
        self._actions = [
            HealingAction(
                name="websocket_reconnect",
                description="Reconnect EventBus WebSocket connection",
                severity=Severity.MEDIUM,
                auto_repair=True,
                run=self._reconnect_websocket,
            ),
            HealingAction(
                name="rebuild_cache",
                description="Rebuild discovery cache from providers",
                severity=Severity.LOW,
                auto_repair=True,
                run=self._rebuild_cache,
            ),
            HealingAction(
                name="reload_config",
                description="Reload runtime configuration from disk",
                severity=Severity.MEDIUM,
                auto_repair=False,  # config reload needs awareness
                run=self._reload_config,
            ),
            HealingAction(
                name="restart_provider",
                description="Restart a failed AI provider connection",
                severity=Severity.MEDIUM,
                auto_repair=True,
                run=self._restart_provider,
            ),
            HealingAction(
                name="repair_bindings",
                description="Rebind agent providers after detection failure",
                severity=Severity.MEDIUM,
                auto_repair=True,
                run=self._repair_bindings,
            ),
            HealingAction(
                name="restart_backend",
                description="Full backend process restart (destructive)",
                severity=Severity.CRITICAL,
                auto_repair=False,
                run=self._restart_backend,
            ),
            HealingAction(
                name="rebuild_indexes",
                description="Rebuild search and memory indexes",
                severity=Severity.LOW,
                auto_repair=True,
                run=self._rebuild_indexes,
            ),
            HealingAction(
                name="resync_state",
                description="Resynchronize Mission Control state from EventBus history",
                severity=Severity.LOW,
                auto_repair=True,
                run=self._resync_state,
            ),
            HealingAction(
                name="restart_plugin",
                description="Reload a failed plugin module",
                severity=Severity.MEDIUM,
                auto_repair=True,
                run=self._restart_plugin,
            ),
            HealingAction(
                name="repair_runtime",
                description="Restart the runtime discovery subsystem",
                severity=Severity.MEDIUM,
                auto_repair=True,
                run=self._repair_runtime,
            ),
        ]

    async def start(self) -> None:
        """Subscribe to EventBus topics and begin monitoring."""
        self._running = True
        topics = [
            Topic.AGENT_FAILED,
            Topic.HEALTH_DEGRADED,
            Topic.PROVIDER_FAILED,
            Topic.CONNECTION_LOST,
        ]
        for topic in topics:
            await self._bus.subscribe(topic.value, self._on_event)
        log.info("self_healing.started")

    async def stop(self) -> None:
        self._running = False
        log.info("self_healing.stopped")

    # ── Event handlers ──

    async def _on_event(self, event: EventEnvelope) -> None:
        if not self._running:
            return

        payload = event.payload
        subsystem = payload.get("source", event.source)
        description = payload.get("reason", str(payload))
        severity = self._classify(event.topic, payload)

        issue = HealingIssue(
            id=f"heal-{self._issue_counter}",
            subsystem=subsystem,
            description=description,
            severity=severity,
            detected_at=time.time(),
            auto_repairable=severity <= Severity.MEDIUM,
            requires_approval=severity >= Severity.HIGH,
        )
        self._issue_counter += 1
        self._issues.append(issue)

        log.info("self_healing.detected", subsystem=subsystem, severity=severity.name)

        if issue.auto_repairable:
            await self._auto_repair(issue)
        elif issue.requires_approval:
            await self._request_approval(issue)

        # Publish healing event for Mission Control
        await self._bus.publish(
            EventEnvelope(
                type="self_healing.issue_detected",
                source="self_healing",
                topic=Topic.SELF_HEALING_ISSUE.value,
                payload={
                    "issue_id": issue.id,
                    "subsystem": issue.subsystem,
                    "severity": severity.name,
                    "description": issue.description,
                    "auto_repairable": issue.auto_repairable,
                    "requires_approval": issue.requires_approval,
                },
            )
        )

    def _classify(self, topic: str, payload: dict) -> Severity:
        """Map events to severity levels."""
        topic_str = topic if isinstance(topic, str) else topic.value if hasattr(topic, 'value') else str(topic)
        
        if topic_str in ("agent.failed", "health.critical"):
            return Severity.HIGH
        if topic_str in ("health.degraded", "connection.lost"):
            return Severity.MEDIUM
        if topic_str in ("provider.failed",):
            return Severity.MEDIUM
        # Transient / retryable
        if topic_str in ("agent.recovered",):
            return Severity.LOW
        
        # Payload-based heuristics
        if payload.get("critical", False):
            return Severity.CRITICAL
        if payload.get("retry_count", 0) >= (self._settings.max_attempts or 3):
            return Severity.HIGH
        return Severity.LOW

    # ── Auto-repair ──

    async def _auto_repair(self, issue: HealingIssue) -> None:
        """Find and execute the best auto-repair action."""
        action = self._best_action(issue)
        if action is None or not action.auto_repair:
            issue.resolution = "No auto-repair action available"
            issue.resolved_at = time.time()
            return

        log.info("self_healing.repairing", issue=issue.id, action=action.name)
        try:
            success = await asyncio.to_thread(action.run)
            if success:
                issue.resolution = f"Auto-repaired via {action.name}"
                issue.resolved_at = time.time()
                log.info("self_healing.repaired", issue=issue.id, action=action.name)
            else:
                issue.error = f"Auto-repair {action.name} failed"
                issue.resolution = "Auto-repair failed"
                issue.resolved_at = time.time()
                issue.requires_approval = True  # Escalate
                log.warning("self_healing.failed", issue=issue.id, action=action.name)
        except Exception as e:
            issue.error = str(e)
            issue.resolution = "Auto-repair raised exception"
            issue.resolved_at = time.time()
            issue.requires_approval = True
            log.error("self_healing.error", issue=issue.id, error=str(e))

    def _best_action(self, issue: HealingIssue) -> Optional[HealingAction]:
        """Select the most appropriate healing action."""
        subsystem = issue.subsystem.lower()
        
        for action in self._actions:
            if not action.auto_repair:
                continue
            if action.severity > issue.severity:
                continue
            # Match by subsystem keyword
            if "websocket" in subsystem and "websocket" in action.name:
                return action
            if "cache" in subsystem and "cache" in action.name:
                return action
            if "provider" in subsystem and "provider" in action.name:
                return action
            if "bind" in subsystem and "bind" in action.name:
                return action
            if "plugin" in subsystem and "plugin" in action.name:
                return action
            if "runtime" in subsystem and "runtime" in action.name:
                return action

        # Fallback: lowest severity generic action
        for action in sorted(self._actions, key=lambda a: a.severity):
            if action.auto_repair and action.severity <= issue.severity:
                return action
        return None

    async def _request_approval(self, issue: HealingIssue) -> None:
        """Queue a high/critical issue for user approval."""
        log.info("self_healing.approval_needed", issue=issue.id, severity=issue.severity.name)
        # Approval is managed externally via the API

    # ── Built-in healing actions ──

    async def _reconnect_websocket(self) -> bool:
        """Reconnect WebSocket connection to the EventBus."""
        try:
            await self._bus.stop()
            await asyncio.sleep(0.5)
            await self._bus.start()
            return True
        except Exception:
            return False

    async def _rebuild_cache(self) -> bool:
        """Clear and rebuild the discovery cache."""
        try:
            from agentic_os.services.runtime_discovery import cache
            await cache.clear()
            await cache.rebuild()
            return True
        except Exception:
            return False

    async def _reload_config(self) -> bool:
        """Reload configuration from disk."""
        try:
            self._settings.reload()
            return True
        except Exception:
            return False

    async def _restart_provider(self) -> bool:
        """Restart a failed AI provider connection."""
        try:
            from agentic_os.core.providers import vault
            await vault.restart_all()
            return True
        except Exception:
            return False

    async def _repair_bindings(self) -> bool:
        """Rebind agent providers."""
        try:
            from agentic_os.adapters.providers import auto_bind
            await auto_bind.rebind_all()
            return True
        except Exception:
            return False

    async def _restart_backend(self) -> bool:
        """Full backend restart."""
        # Requires user approval — this should be called via API
        return False

    async def _rebuild_indexes(self) -> bool:
        """Rebuild memory/search indexes."""
        try:
            from agentic_os.core.memory import manager
            await manager.reindex()
            return True
        except Exception:
            return False

    async def _resync_state(self) -> bool:
        """Resynchronize state from EventBus replay."""
        try:
            from agentic_os.domain.events import replay
            await replay.resync()
            return True
        except Exception:
            return False

    async def _restart_plugin(self) -> bool:
        """Reload a failed plugin module."""
        try:
            from agentic_os.core.plugins import loader
            await loader.restart_failed()
            return True
        except Exception:
            return False

    async def _repair_runtime(self) -> bool:
        """Restart the runtime discovery subsystem."""
        try:
            from agentic_os.services.runtime_discovery import manager
            await manager.restart()
            return True
        except Exception:
            return False

    # ── Public API for frontend ──

    def get_issues(
        self,
        severity: Optional[int] = None,
        unresolved_only: bool = True,
    ) -> list[HealingIssue]:
        result = list(self._issues)
        if unresolved_only:
            result = [i for i in result if i.resolved_at is None]
        if severity is not None:
            result = [i for i in result if i.severity >= severity]
        return sorted(result, key=lambda i: i.severity, reverse=True)

    def get_pending_approvals(self) -> list[HealingIssue]:
        return [
            i for i in self._issues
            if i.requires_approval and i.approved is None
        ]

    async def approve_action(self, issue_id: str) -> bool:
        for issue in self._issues:
            if issue.id == issue_id and issue.approved is None:
                issue.approved = True
                # Execute the action
                action = self._best_action(issue)
                if action:
                    success = await asyncio.to_thread(action.run)
                    if success:
                        issue.resolution = f"Approved: {action.name}"
                    else:
                        issue.error = f"Approved action {action.name} failed"
                    issue.resolved_at = time.time()
                else:
                    issue.resolution = "No action available"
                    issue.resolved_at = time.time()
                return True
        return False

    async def reject_action(self, issue_id: str, reason: str = "") -> bool:
        for issue in self._issues:
            if issue.id == issue_id and issue.approved is None:
                issue.approved = False
                issue.resolution = f"Rejected: {reason}" if reason else "Rejected by user"
                issue.resolved_at = time.time()
                return True
        return False

    def get_summary(self) -> dict:
        unresolved = [i for i in self._issues if i.resolved_at is None]
        return {
            "total_issues": len(self._issues),
            "unresolved": len(unresolved),
            "critical": len([i for i in unresolved if i.severity == Severity.CRITICAL]),
            "high": len([i for i in unresolved if i.severity == Severity.HIGH]),
            "medium": len([i for i in unresolved if i.severity == Severity.MEDIUM]),
            "low": len([i for i in unresolved if i.severity == Severity.LOW]),
            "pending_approvals": len(self.get_pending_approvals()),
            "auto_repaired": len([i for i in self._issues if i.resolved_at and i.auto_repairable and not i.error]),
        }
