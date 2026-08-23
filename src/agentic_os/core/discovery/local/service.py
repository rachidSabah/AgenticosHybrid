"""LocalDiscoveryService — main orchestrator for Phase 6.1 local agent discovery.

Wires together all scanners (:class:`AgentScanner`, sub-scanners) and the
:class:`HealthMonitor` into a single lifecycle-managed service.

The service runs an initial discovery on :meth:`start`, then periodically
health-checks registered agents.  Discovered agents can be auto-registered
with the event bus.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from agentic_os.core.discovery.local.capability_detector import CapabilityDetector
from agentic_os.core.discovery.local.health_monitor import HealthMonitor
from agentic_os.core.discovery.local.scanner import AgentScanner
from agentic_os.domain.discovery import (
    AgentDiscoveryConfig,
    AgentStatus,
    DiscoveryResult,
    LocalAgent,
)
from agentic_os.domain.events import EventEnvelope, Topic

log = logging.getLogger("agentic_os.local_discovery.service")


class LocalDiscoveryService:
    """Orchestrates local agent discovery, registration, and health monitoring.

    Lifecycle
    ---------
    ::

        service = LocalDiscoveryService(config)
        await service.start(event_bus=bus)
        # ... system runs ...
        await service.stop()

    Thread-safety
    -------------
    Internal state (``_agents`` dict) is guarded by an ``asyncio.Lock``.
    All public methods that read or mutate ``_agents`` acquire this lock.
    """

    def __init__(
        self,
        config: AgentDiscoveryConfig | None = None,
        scanner: AgentScanner | None = None,
        capability_detector: CapabilityDetector | None = None,
    ) -> None:
        self._config = config or AgentDiscoveryConfig()
        self._scanner = scanner or AgentScanner()
        self._capability_detector = capability_detector or CapabilityDetector()

        # Internal state
        self._lock = asyncio.Lock()
        self._agents: dict[str, LocalAgent] = {}  # agent_id → LocalAgent
        self._agent_keys: dict[tuple[str, str], str] = {}  # (tool_type, exe_path) → agent_id
        self._health_monitor: HealthMonitor | None = None
        self._started = False
        self._event_bus: Any = None
        self._discovery_count = 0

    # ── Lifecycle ───────────────────────────────────────────────────────────

    async def start(self, event_bus: Any | None = None) -> None:
        """Initialise scanners, start health monitor, and run initial discovery.

        Args:
            event_bus: Optional event bus instance.  When provided, health
                changes and agent lifecycle events are published automatically.
        """
        if self._started:
            log.debug("LocalDiscoveryService already started")
            return

        self._event_bus = event_bus

        # Health monitor
        self._health_monitor = HealthMonitor(
            interval_seconds=self._config.health_check_interval_seconds,
            event_bus=event_bus,
        )

        # Run initial discovery
        discovery_result = await self.run_discovery()
        log.info(
            "Initial discovery complete: %d agents found, %d new, %d updated, %d errors",
            discovery_result.agents_found,
            discovery_result.agents_new,
            discovery_result.agents_updated,
            len(discovery_result.errors),
        )

        # Start health monitor
        if self._health_monitor:
            await self._health_monitor.start()

        # Auto-register if configured
        if self._config.auto_register and event_bus is not None:
            await self.auto_register()

        self._started = True
        log.info("LocalDiscoveryService started")

    async def stop(self) -> None:
        """Stop health monitor and clean up."""
        if not self._started:
            return

        # Stop health monitor
        if self._health_monitor is not None:
            await self._health_monitor.stop()

        async with self._lock:
            self._agents.clear()
            self._agent_keys.clear()
            self._started = False

        log.info("LocalDiscoveryService stopped")

    @property
    def is_started(self) -> bool:
        """Return ``True`` if the service has been started (and not stopped)."""
        return self._started

    # ── Discovery ───────────────────────────────────────────────────────────

    async def run_discovery(self) -> DiscoveryResult:
        """Run all scanners, combine results, create/update :class:`LocalAgent` objects.

        *Deduplication:* if the same ``(tool_type, executable_path)``
        pair already exists, the existing agent's ``last_seen`` and
        ``version`` are updated instead of creating a duplicate.

        Returns:
            A :class:`DiscoveryResult` summarising what happened.

        Complexity: O(*S* + *n*) where *S* = scanner complexity and
        *n* = number of discovered agents.
        """
        start_time = time.time()
        errors: list[str] = []
        agents_found = 0
        agents_new = 0
        agents_updated = 0

        # ── Run main scan ──
        try:
            scan_results = await self._scanner.scan(enabled_tools=self._config.enabled_tools)
        except Exception as exc:
            log.exception("Scanner scan failed")
            errors.append(f"Scan failed: {exc}")
            scan_results = []

        # ── Run process scanner for status ──
        process_map: dict[str, dict[str, Any]] = {}
        if self._config.scan_processes:
            try:
                from agentic_os.core.discovery.local.process_scanner import (
                    ProcessScanner,
                )

                proc_results = await ProcessScanner().scan()
                for item in proc_results:
                    tt = item["tool_type"]
                    if tt not in process_map:
                        process_map[tt] = item
            except Exception as exc:
                log.warning("Process scanner failed: %s", exc)
                errors.append(f"Process scan failed: {exc}")

        # ── Process results ──
        async with self._lock:
            for tool_type, exe_path, version in scan_results:
                agents_found += 1
                key = (tool_type, exe_path)
                existing_id = self._agent_keys.get(key)

                if existing_id and existing_id in self._agents:
                    # Update existing agent
                    existing = self._agents[existing_id]
                    updated = self._merge_agent(existing, version, process_map)
                    self._agents[existing_id] = updated
                    agents_updated += 1
                else:
                    # Create new agent
                    agent = self._create_agent(tool_type, exe_path, version, process_map)
                    self._agents[agent.id] = agent
                    self._agent_keys[key] = agent.id
                    agents_new += 1

            # Register PID info for health tracking
            if self._health_monitor is not None:
                for agent in self._agents.values():
                    await self._health_monitor.track_agent(agent.id, agent.pid)

        duration_ms = (time.time() - start_time) * 1000.0
        tools_detected = tuple(sorted(set(tt for tt, _, _ in scan_results)))

        result = DiscoveryResult(
            agents_found=agents_found,
            agents_new=agents_new,
            agents_updated=agents_updated,
            errors=tuple(errors),
            duration_ms=round(duration_ms, 1),
            tools_detected=tools_detected,
        )

        log.info(
            "Discovery result: %d found, %d new, %d updated (%.1fms)",
            agents_found,
            agents_new,
            agents_updated,
            duration_ms,
        )
        return result

    # ── Agent access ────────────────────────────────────────────────────────

    async def get_agents(self) -> list[LocalAgent]:
        """Return the current list of all discovered :class:`LocalAgent` objects.

        Complexity: O(*n*) — returns a copy of the internal list.
        """
        async with self._lock:
            return list(self._agents.values())

    async def get_agent(self, agent_id: str) -> LocalAgent | None:
        """Return a single agent by ID, or ``None`` if not found.

        Complexity: O(1) dict lookup.
        """
        async with self._lock:
            return self._agents.get(agent_id)

    async def update_agent(self, agent_id: str, **updates: Any) -> LocalAgent | None:
        """Update an agent's fields in-place and publish ``AGENT_UPDATED``.

        Only the fields passed as keyword arguments are updated; the
        rest remain unchanged.

        Returns:
            The updated :class:`LocalAgent`, or ``None`` if *agent_id*
            is unknown.

        Complexity: O(1).
        """
        async with self._lock:
            existing = self._agents.get(agent_id)
            if existing is None:
                log.warning("update_agent: unknown agent_id '%s'", agent_id)
                return None

            # Build a new LocalAgent with updated fields.
            kwargs: dict[str, Any] = {
                "id": existing.id,
                "name": updates.get("name", existing.name),
                "tool_type": updates.get("tool_type", existing.tool_type),
                "version": updates.get("version", existing.version),
                "status": updates.get("status", existing.status),
                "executable_path": updates.get("executable_path", existing.executable_path),
                "working_directory": updates.get("working_directory", existing.working_directory),
                "pid": updates.get("pid", existing.pid),
                "capabilities": updates.get("capabilities", existing.capabilities),
                "supported_models": updates.get("supported_models", existing.supported_models),
                "supported_providers": updates.get(
                    "supported_providers", existing.supported_providers
                ),
                "health_score": updates.get("health_score", existing.health_score),
                "last_seen": updates.get("last_seen", existing.last_seen),
                "discovered_at": existing.discovered_at,
                "latency_ms": updates.get("latency_ms", existing.latency_ms),
                "memory_mb": updates.get("memory_mb", existing.memory_mb),
                "cpu_percent": updates.get("cpu_percent", existing.cpu_percent),
                "threads": updates.get("threads", existing.threads),
                "uptime_seconds": updates.get("uptime_seconds", existing.uptime_seconds),
                "restart_count": updates.get("restart_count", existing.restart_count),
                "configuration": updates.get("configuration", existing.configuration),
                "tags": updates.get("tags", existing.tags),
                "error": updates.get("error", existing.error),
            }
            updated = LocalAgent(**kwargs)
            self._agents[agent_id] = updated

            # Update key mapping if executable_path changed
            old_key = (existing.tool_type, existing.executable_path)
            new_key = (updated.tool_type, updated.executable_path)
            if old_key != new_key:
                self._agent_keys.pop(old_key, None)
                self._agent_keys[new_key] = agent_id

        # Publish event outside the lock
        await self._publish_agent_event(Topic.AGENT_UPDATED, updated)
        return updated

    async def remove_agent(self, agent_id: str) -> bool:
        """Remove an agent from the registry and publish ``AGENT_REMOVED``.

        Returns:
            ``True`` if the agent was removed, ``False`` if not found.

        Complexity: O(1).
        """
        async with self._lock:
            existing = self._agents.pop(agent_id, None)
            if existing is None:
                return False
            key = (existing.tool_type, existing.executable_path)
            self._agent_keys.pop(key, None)

            if self._health_monitor is not None:
                await self._health_monitor.untrack_agent(agent_id)

        await self._publish_agent_event(Topic.AGENT_REMOVED, existing)
        log.info("Removed agent %s (%s)", agent_id, existing.name)
        return True

    # ── Auto-registration ───────────────────────────────────────────────────

    async def auto_register(self, event_bus: Any | None = None) -> list[LocalAgent]:
        """Publish ``AGENT_DISCOVERED`` / ``AGENT_REGISTERED`` for all agents.

        Args:
            event_bus: Optional event bus.  Falls back to the one passed
                to :meth:`start`.

        Returns:
            The current list of registered agents.

        Complexity: O(*n*) where *n* = agent count.
        """
        bus = event_bus or self._event_bus
        if bus is None:
            log.warning("auto_register: no event bus available")
            return []

        async with self._lock:
            agents = list(self._agents.values())

        for agent in agents:
            await self._publish_agent_event(Topic.AGENT_DISCOVERED, agent, bus)
            await self._publish_agent_event(Topic.AGENT_REGISTERED, agent, bus)

        log.info("Auto-registered %d agents", len(agents))
        return agents

    # ── Internals ───────────────────────────────────────────────────────────

    def _create_agent(
        self,
        tool_type: str,
        exe_path: str,
        version: str,
        process_map: dict[str, dict[str, Any]],
    ) -> LocalAgent:
        """Construct a :class:`LocalAgent` from scan results."""
        from uuid import uuid4

        proc_info = process_map.get(tool_type, {})
        status = self._map_status(proc_info)
        capabilities = self._capability_detector.detect(tool_type, version)

        return LocalAgent(
            id=uuid4().hex[:12],
            name=tool_type.replace("-", " ").title(),
            tool_type=tool_type,
            version=version,
            status=status,
            executable_path=exe_path,
            pid=proc_info.get("pid") if proc_info else None,
            capabilities=capabilities,
            memory_mb=proc_info.get("memory_mb", 0.0) if proc_info else 0.0,
            cpu_percent=proc_info.get("cpu_percent", 0.0) if proc_info else 0.0,
            health_score=1.0 if status in (AgentStatus.RUNNING, AgentStatus.IDLE) else 0.0,
        )

    def _merge_agent(
        self,
        existing: LocalAgent,
        version: str,
        process_map: dict[str, dict[str, Any]],
    ) -> LocalAgent:
        """Merge new scan data into an existing :class:`LocalAgent`.

        Because ``LocalAgent`` is frozen, this builds a new instance.
        """
        from datetime import UTC, datetime

        proc_info = process_map.get(existing.tool_type, {})

        updates: dict[str, Any] = {
            "version": version or existing.version,
            "last_seen": datetime.now(UTC),
        }
        if proc_info:
            updates["pid"] = proc_info.get("pid", existing.pid)
            updates["memory_mb"] = proc_info.get("memory_mb", existing.memory_mb)
            updates["cpu_percent"] = proc_info.get("cpu_percent", existing.cpu_percent)
            updates["status"] = self._map_status(proc_info)

        return LocalAgent(
            id=existing.id,
            name=updates.get("name", existing.name),
            tool_type=updates.get("tool_type", existing.tool_type),
            version=updates["version"],
            status=updates.get("status", existing.status),
            executable_path=updates.get("executable_path", existing.executable_path),
            working_directory=updates.get("working_directory", existing.working_directory),
            pid=updates["pid"] if "pid" in updates else existing.pid,
            capabilities=updates.get("capabilities", existing.capabilities),
            supported_models=updates.get("supported_models", existing.supported_models),
            supported_providers=updates.get("supported_providers", existing.supported_providers),
            health_score=updates.get("health_score", existing.health_score),
            last_seen=updates["last_seen"],
            discovered_at=existing.discovered_at,
            latency_ms=updates.get("latency_ms", existing.latency_ms),
            memory_mb=updates.get("memory_mb", existing.memory_mb),
            cpu_percent=updates.get("cpu_percent", existing.cpu_percent),
            threads=updates.get("threads", existing.threads),
            uptime_seconds=updates.get("uptime_seconds", existing.uptime_seconds),
            restart_count=updates.get("restart_count", existing.restart_count),
            configuration=updates.get("configuration", existing.configuration),
            tags=updates.get("tags", existing.tags),
            error=updates.get("error", existing.error),
        )

    @staticmethod
    def _map_status(proc_info: dict[str, Any]) -> AgentStatus:
        """Map process info to an :class:`AgentStatus`.

        A CLI/agent binary that was *discovered on disk* is available even
        when no live session process exists (these tools are invoked
        on-demand, not as daemons). The health monitor uses the same
        convention — a tracked agent with no PID is reported ``IDLE``
        (health_monitor.py:191), which the dashboard treats as healthy.

        Return ``UNKNOWN`` only when discovery produced no information at
        all; otherwise prefer ``IDLE`` so installed tools are not falsely
        flagged ``degraded``.
        """
        if not proc_info:
            return AgentStatus.IDLE
        pid = proc_info.get("pid")
        if pid and pid > 0:
            return AgentStatus.RUNNING
        return AgentStatus.STOPPED

    async def _publish_agent_event(
        self,
        topic: Topic,
        agent: LocalAgent,
        event_bus: Any | None = None,
    ) -> None:
        """Publish an agent lifecycle event."""
        bus = event_bus or self._event_bus
        if bus is None:
            return

        payload = agent.to_dict()
        try:
            await bus.publish(
                EventEnvelope(
                    type=topic.value,
                    source="local_discovery",
                    topic=topic.value,
                    payload=payload,
                )
            )
            log.debug("Published %s for agent %s", topic.value, agent.id)
        except Exception:
            log.exception("Failed to publish %s for agent %s", topic.value, agent.id)
