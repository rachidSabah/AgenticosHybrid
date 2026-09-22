"""Agent Discovery & Binding Engine — SINGLE SOURCE OF TRUTH (spec §1).

Every UI surface reads from here. There is no per-component agent list.

    Agent Discovery Engine
            |
    AI Agent Binding / AI Brain / Agent Constellation / Prompt Center / ...

Guarantees:
* An agent appears only after real probes succeed (§5).
* git/node/python are classified as runtimes, exposed separately (§4).
* Removed executables disappear on rescan (§9).
* No fabricated health, version, throughput or heartbeat (§19, §20).
"""

from __future__ import annotations

import asyncio
import platform as _platform
from typing import Any

from agentic_os.core.brains.schema import (
    STATUS_UNAVAILABLE,
    DiscoveredAgent,
    DiscoverySnapshot,
)
from agentic_os.infrastructure.logging import get_logger

log = get_logger("brains.discovery_engine")

# Cap on concurrent probes so a huge PATH cannot stall startup.
# Measured on a large Windows PATH: 24 concurrent candidates oversubscribed
# the box and healthy CLIs (qwen, openai) began timing out (exit 124) —
# a false negative. 8 keeps probes reliable; scan completes in ~15s.
_MAX_CONCURRENT_PROBES = 8


def _build_adapter():
    system = _platform.system()
    if system == "Windows":
        from agentic_os.core.brains.windows_discovery import WindowsAgentDiscovery

        return WindowsAgentDiscovery()
    if system == "Linux":
        from agentic_os.core.brains.unix_discovery import LinuxAgentDiscovery

        return LinuxAgentDiscovery()
    if system == "Darwin":
        from agentic_os.core.brains.unix_discovery import MacOSAgentDiscovery

        return MacOSAgentDiscovery()
    from agentic_os.core.brains.unix_discovery import LinuxAgentDiscovery

    return LinuxAgentDiscovery()


class AgentDiscoveryEngine:
    """Owns discovery state and publishes it to every consumer."""

    def __init__(self) -> None:
        self._adapter = _build_adapter()
        self._snapshot = DiscoverySnapshot(platform=self._adapter.platform_name)
        self._lock = asyncio.Lock()
        self._history: dict[str, DiscoveredAgent] = {}
        self._rescan_task: asyncio.Task | None = None
        self._rescan_interval: float = 300.0

    # ── Public API ──────────────────────────────────────────────────────────

    @property
    def snapshot(self) -> DiscoverySnapshot:
        return self._snapshot

    def get_bound_agents(self) -> list[DiscoveredAgent]:
        """Active AI agents only — excludes runtimes and unavailable ones."""
        return self._snapshot.active_agents()

    def get_runtimes(self) -> list[DiscoveredAgent]:
        return self._snapshot.runtimes()

    def get_all(self) -> list[DiscoveredAgent]:
        return list(self._snapshot.agents)

    def get_history(self) -> list[DiscoveredAgent]:
        """Historical records — never rendered as active (§9)."""
        return list(self._history.values())

    async def scan(self) -> DiscoverySnapshot:
        """Full discovery pass: discover -> validate -> classify."""
        async with self._lock:
            candidates = await self._adapter.discover()
            sem = asyncio.Semaphore(_MAX_CONCURRENT_PROBES)

            async def _validate(name: str) -> DiscoveredAgent:
                async with sem:
                    try:
                        return await self._adapter.validate(name)
                    except Exception as exc:  # noqa: BLE001
                        agent = DiscoveredAgent(id=f"agent:{name}", name=name)
                        agent.status = STATUS_UNAVAILABLE
                        agent.error = str(exc)
                        return agent

            results = await asyncio.gather(*(_validate(c) for c in candidates))

            # Dedup by resolved executable path / command (§9).
            deduped: dict[str, DiscoveredAgent] = {}
            for agent in results:
                key = (agent.executable_path or agent.command).lower()
                existing = deduped.get(key)
                if existing is None or self._score(agent) > self._score(existing):
                    deduped[key] = agent

            snapshot = DiscoverySnapshot(
                platform=self._adapter.platform_name,
                agents=sorted(deduped.values(), key=lambda a: a.name.lower()),
                candidates_seen=len(candidates),
            )
            self._snapshot = snapshot

            for agent in snapshot.agents:
                self._history[agent.id] = agent

            log.info(
                "discovery.scan_complete",
                platform=snapshot.platform,
                candidates=snapshot.candidates_seen,
                discovered=len(snapshot.agents),
                active=len(snapshot.active_agents()),
                runtimes=len(snapshot.runtimes()),
            )
            return snapshot

    async def unbind(self, agent_id: str) -> bool:
        """Actually remove the binding, not just hide it (§14)."""
        async with self._lock:
            before = len(self._snapshot.agents)
            self._snapshot.agents = [
                a for a in self._snapshot.agents if a.id != agent_id
            ]
            removed = len(self._snapshot.agents) < before
            if removed:
                log.info("discovery.unbound", agent_id=agent_id)
            return removed

    # ── Auto rescan (§13) ───────────────────────────────────────────────────

    def start_auto_rescan(self, interval_seconds: float = 300.0) -> None:
        """Begin periodic rescanning so newly installed CLIs appear on their own.

        Safe to call more than once; only one loop is ever started.
        """
        if self._rescan_task is not None and not self._rescan_task.done():
            return
        self._rescan_interval = interval_seconds
        self._rescan_task = asyncio.create_task(self._rescan_loop())
        log.info("discovery.auto_rescan_started", interval=interval_seconds)

    def stop_auto_rescan(self) -> None:
        if self._rescan_task and not self._rescan_task.done():
            self._rescan_task.cancel()
            log.info("discovery.auto_rescan_stopped")

    async def _rescan_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(self._rescan_interval)
            except asyncio.CancelledError:
                raise
            try:
                await self.scan()
            except Exception as exc:  # noqa: BLE001
                log.warning("discovery.auto_rescan_failed", error=str(exc))

    # ── Validate All / Repair All (§15, §16) ───────────────────────────────

    async def validate_all(self) -> dict[str, dict[str, Any]]:
        """Run the real probe sequence against every bound agent (§15).

        Returns honest per-agent results. No results are generated — an agent
        that fails validation is reported as failed.
        """
        results: dict[str, dict[str, Any]] = {}
        for agent in list(self._snapshot.agents):
            try:
                fresh = await self._adapter.validate(agent.command)
            except Exception as exc:  # noqa: BLE001
                results[agent.id] = {
                    "name": agent.name,
                    "passed": False,
                    "status": "failed",
                    "detail": str(exc),
                }
                continue
            results[agent.id] = {
                "name": fresh.name,
                "passed": fresh.status in ("healthy", "degraded"),
                "status": fresh.status,
                "version": fresh.version,
                "health_score": fresh.health_score,
                "detail": fresh.error or "",
            }
        log.info("discovery.validate_all", agents=len(results))
        return results

    async def repair_all(self) -> dict[str, dict[str, Any]]:
        """Attempt real remediation for each agent (§16).

        Remediation is limited to what can actually be done: re-resolve the
        executable and re-probe. If that fails, the result is
        "repair_unavailable" — never "repair successful".
        """
        results: dict[str, dict[str, Any]] = {}
        for agent in list(self._snapshot.agents):
            try:
                path = await self._adapter.resolve(agent.command)
            except Exception:  # noqa: BLE001
                path = None
            if not path:
                results[agent.id] = {
                    "name": agent.name,
                    "repaired": False,
                    "outcome": "repair_unavailable",
                    "detail": "executable could not be re-resolved",
                }
                continue
            fresh = await self._adapter.validate(agent.command)
            if fresh.status in ("healthy", "degraded"):
                results[agent.id] = {
                    "name": agent.name,
                    "repaired": True,
                    "outcome": "rebound",
                    "status": fresh.status,
                    "version": fresh.version,
                }
            else:
                results[agent.id] = {
                    "name": agent.name,
                    "repaired": False,
                    "outcome": "repair_unavailable",
                    "status": fresh.status,
                    "detail": fresh.error or "validation still failing",
                }
        log.info("discovery.repair_all", agents=len(results))
        return results

    # ── Helpers ─────────────────────────────────────────────────────────────

    @staticmethod
    def _score(agent: DiscoveredAgent) -> int:
        """Prefer the most-evidenced record when de-duplicating."""
        score = 0
        if agent.version:
            score += 2
        if agent.health_score is not None:
            score += 2
        score += len(agent.capabilities)
        score += sum(1 for p in agent.probes if p.ok)
        return score

    def to_dict(self) -> dict[str, Any]:
        return self._snapshot.to_dict()


# Process-wide singleton — the one place UI surfaces read from.
agent_discovery_engine = AgentDiscoveryEngine()
