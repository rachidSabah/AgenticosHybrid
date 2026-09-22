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
