"""Phase 15 — EcosystemManager.

Top-level coordinator for the autonomous agent ecosystem. Maintains:

  - CapabilityGraph      (what provides what)
  - CollaborationNetwork (who trusts whom)
  - EvolutionEngine      (what should change)
  - TaskMarketplace      (who should do what)
  - EcosystemStats       (live snapshot)
  - EcosystemHealth      (live health)

The manager is a pure consumer of:
  - BrainRegistry (canonical runtime data)
  - ExecutiveMemory (decisions, reflections)
  - CognitiveMemory (predictions, evaluations)
  - EventBus (subscribes to brain.* + mission.* + swarm.* events)
  - SwarmCoordinator (active swarms)

It does NOT duplicate any of those sources — it derives its state from
them on every event and on every ``refresh()`` call.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agentic_os.core.ecosystem.capability_graph import CapabilityGraph
from agentic_os.core.ecosystem.collaboration_network import CollaborationNetwork
from agentic_os.core.ecosystem.domain import (
    EcosystemHealth,
    EcosystemHealthLevel,
    EcosystemStats,
)
from agentic_os.core.ecosystem.evolution_engine import EvolutionEngine
from agentic_os.core.ecosystem.task_marketplace import TaskMarketplace
from agentic_os.infrastructure.logging import get_logger

if TYPE_CHECKING:
    from agentic_os.core.brains.registry import BrainRegistry
    from agentic_os.core.cognitive.memory import CognitiveMemory
    from agentic_os.core.executive.memory import ExecutiveMemory
    from agentic_os.core.orchestration.swarm_coordinator import SwarmCoordinator
    from agentic_os.ports.event_bus import EventBus

log = get_logger("ecosystem.manager")


class EcosystemManager:
    """Top-level coordinator. Owns the ecosystem's live state.

    The manager exposes its sub-components as read-only properties so
    the API layer can query them directly without going through the
    manager for every read.
    """

    def __init__(
        self,
        bus: EventBus,
        brain_registry: BrainRegistry | None = None,
        exec_memory: ExecutiveMemory | None = None,
        cognitive_memory: CognitiveMemory | None = None,
        swarm_coordinator: SwarmCoordinator | None = None,
    ) -> None:
        self._bus = bus
        self._registry = brain_registry
        self._exec_memory = exec_memory
        self._cog_memory = cognitive_memory
        self._swarm = swarm_coordinator
        self._started = False

        # Sub-components
        self._graph = CapabilityGraph()
        self._network = CollaborationNetwork()
        self._evolution = EvolutionEngine(
            brain_registry=brain_registry,
            exec_memory=exec_memory,
            cognitive_memory=cognitive_memory,
            capability_graph=self._graph,
            collaboration_network=self._network,
        )
        self._marketplace = TaskMarketplace(
            brain_registry=brain_registry,
            collaboration_network=self._network,
            bus=bus,
        )

        # Live stats / health
        self._stats = EcosystemStats()
        self._health = EcosystemHealth()
        self._refresh_count = 0

    # ── Properties (read-only views) ────────────────────────────────

    @property
    def capability_graph(self) -> CapabilityGraph:
        return self._graph

    @property
    def collaboration_network(self) -> CollaborationNetwork:
        return self._network

    @property
    def evolution_engine(self) -> EvolutionEngine:
        return self._evolution

    @property
    def marketplace(self) -> TaskMarketplace:
        return self._marketplace

    @property
    def brain_registry(self) -> BrainRegistry | None:
        return self._registry

    @property
    def stats(self) -> EcosystemStats:
        return self._stats

    @property
    def health(self) -> EcosystemHealth:
        return self._health

    @property
    def started(self) -> bool:
        return self._started

    # ── Dependency injection (late binding from kernel) ─────────────

    def set_brain_registry(self, registry: BrainRegistry) -> None:
        self._registry = registry
        self._evolution = EvolutionEngine(
            brain_registry=registry,
            exec_memory=self._exec_memory,
            cognitive_memory=self._cog_memory,
            capability_graph=self._graph,
            collaboration_network=self._network,
        )
        self._marketplace.set_brain_registry(registry)

    def set_exec_memory(self, memory: ExecutiveMemory) -> None:
        self._exec_memory = memory
        self._evolution = EvolutionEngine(
            brain_registry=self._registry,
            exec_memory=memory,
            cognitive_memory=self._cog_memory,
            capability_graph=self._graph,
            collaboration_network=self._network,
        )

    def set_cognitive_memory(self, memory: CognitiveMemory) -> None:
        self._cog_memory = memory
        self._evolution = EvolutionEngine(
            brain_registry=self._registry,
            exec_memory=self._exec_memory,
            cognitive_memory=memory,
            capability_graph=self._graph,
            collaboration_network=self._network,
        )

    def set_swarm_coordinator(self, swarm: SwarmCoordinator) -> None:
        self._swarm = swarm

    # ── Lifecycle ───────────────────────────────────────────────────

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        # Initial population of the capability graph from BrainRegistry
        await self._populate_graph_from_registry()
        await self.refresh()
        log.info("EcosystemManager started")

    async def stop(self) -> None:
        self._started = False
        log.info("EcosystemManager stopped")

    # ── Public operations ───────────────────────────────────────────

    async def refresh(self) -> None:
        """Recompute ecosystem stats + health from live BrainRegistry.

        Idempotent — safe to call on every event or on a timer.
        """
        await self._compute_stats()
        self._compute_health()
        self._refresh_count += 1
        await self._publish("ecosystem.updated", self._stats.to_dict())
        await self._publish("ecosystem.statistics.updated", self._stats.to_dict())
        await self._publish("ecosystem.health.updated", self._health.to_dict())

    async def analyze(self) -> dict[str, Any]:
        """Run the EvolutionEngine and emit recommendations."""
        recs = await self._evolution.analyze_all()
        await self._publish(
            "ecosystem.evolution.generated",
            {
                "recommendations": [r.to_dict() for r in recs],
                "count": len(recs),
            },
        )
        await self._publish(
            "ecosystem.analysis.completed",
            {
                "recommendations_generated": len(recs),
                "stats": self._evolution.stats(),
            },
        )
        # Refresh stats so the new recommendation count is visible
        self._stats.evolution_recommendations = len(self._evolution.list_recommendations())
        return {
            "recommendations": [r.to_dict() for r in recs],
            "count": len(recs),
            "stats": self._evolution.stats(),
        }

    async def optimize(self) -> dict[str, Any]:
        """Trigger continuous self-optimization.

        Runs analysis → publishes optimization.started → emits
        recommendations → publishes optimization.completed. The actual
        application of recommendations is delegated to the Executive /
        Cognitive layers (which listen to ecosystem.evolution.generated).
        """
        await self._publish(
            "ecosystem.optimization.started",
            {"timestamp": self._now_iso()},
        )
        result = await self.analyze()
        await self._publish(
            "ecosystem.optimization.completed",
            {
                "recommendations_count": result["count"],
                "stats": result["stats"],
                "timestamp": self._now_iso(),
            },
        )
        return {
            "optimization_run": True,
            **result,
        }

    async def evolve(self) -> dict[str, Any]:
        """Force one evolution cycle (alias for ``optimize``)."""
        return await self.optimize()

    async def rebuild(self) -> dict[str, Any]:
        """Rebuild the capability graph + collaboration network from scratch.

        Wipes local state and re-derives it from BrainRegistry. Useful
        when the manager has been running for a long time and accumulated
        drift, or after a major discovery event.
        """
        self._graph.clear()
        self._network.clear()
        await self._populate_graph_from_registry()
        await self.refresh()
        await self._publish(
            "ecosystem.capability.updated",
            self._graph.stats(),
        )
        await self._publish(
            "ecosystem.collaboration.updated",
            self._network.stats(),
        )
        return {
            "rebuilt": True,
            "graph_stats": self._graph.stats(),
            "network_stats": self._network.stats(),
        }

    # ── Event-driven updaters (called by EcosystemController) ───────

    async def on_brain_registered(self, payload: dict[str, Any]) -> None:
        self._graph.apply_brain_registered(payload)
        await self.refresh()
        await self._publish("ecosystem.capability.updated", self._graph.stats())

    async def on_brain_updated(self, payload: dict[str, Any]) -> None:
        self._graph.apply_brain_updated(payload)
        await self.refresh()

    async def on_brain_removed(self, payload: dict[str, Any]) -> None:
        self._graph.apply_brain_removed(payload)
        await self.refresh()
        await self._publish("ecosystem.capability.updated", self._graph.stats())

    async def on_mission_completed(self, payload: dict[str, Any]) -> None:
        self._graph.apply_mission_completed(payload)
        # Record collaborations among mission members
        members = payload.get("members") or payload.get("agents") or []
        success = bool(payload.get("success", True))
        for i, a in enumerate(members):
            aid = str(a if isinstance(a, str) else (a.get("id") or ""))
            for b in members[i + 1 :]:
                bid = str(b if isinstance(b, str) else (b.get("id") or ""))
                if aid and bid:
                    self._network.record_collaboration(
                        source=aid,
                        target=bid,
                        success=success,
                        metadata={"mission_id": payload.get("mission_id") or payload.get("id")},
                    )
        await self.refresh()
        await self._publish("ecosystem.collaboration.updated", self._network.stats())

    async def on_swarm_completed(self, payload: dict[str, Any]) -> None:
        self._graph.apply_swarm_completed(payload)
        members = payload.get("members") or []
        success = bool(payload.get("success", True))
        for i, a in enumerate(members):
            aid = str(a if isinstance(a, str) else (a.get("id") or ""))
            for b in members[i + 1 :]:
                bid = str(b if isinstance(b, str) else (b.get("id") or ""))
                if aid and bid:
                    self._network.record_collaboration(
                        source=aid,
                        target=bid,
                        success=success,
                        metadata={"swarm_id": payload.get("swarm_id")},
                    )
        await self.refresh()
        await self._publish("ecosystem.collaboration.updated", self._network.stats())

    # ── Snapshot / dashboard ────────────────────────────────────────

    def dashboard(self) -> dict[str, Any]:
        """Combined snapshot for the ``/api/ecosystem/dashboard`` endpoint."""
        return {
            "stats": self._stats.to_dict(),
            "health": self._health.to_dict(),
            "graph_stats": self._graph.stats(),
            "network_stats": self._network.stats(),
            "marketplace_stats": self._marketplace.stats(),
            "evolution_stats": self._evolution.stats(),
            "refresh_count": self._refresh_count,
        }

    # ── Internals ───────────────────────────────────────────────────

    async def _populate_graph_from_registry(self) -> None:
        if self._registry is None:
            return
        try:
            brains = await self._registry.list_all()
        except Exception:
            log.exception("Failed to populate graph from registry")
            return
        for brain in brains:
            self._graph.apply_brain_registered(
                {
                    "id": brain.id,
                    "display_name": brain.display_name,
                    "capabilities": list(brain.capabilities) if brain.capabilities else [],
                    "vendor": getattr(brain, "vendor", "unknown"),
                    "health": brain.health,
                    "latency": brain.latency,
                }
            )

    async def _compute_stats(self) -> None:
        stats = EcosystemStats()
        if self._registry is not None:
            try:
                brains = await self._registry.list_all()
                stats.total_runtimes = len(brains)
                health_sum = 0.0
                latency_sum = 0.0
                cap_set: set[str] = set()
                cap_total = 0
                for b in brains:
                    if b.health >= 80:
                        stats.healthy_runtimes += 1
                    elif b.health >= 50:
                        stats.degraded_runtimes += 1
                    else:
                        stats.unhealthy_runtimes += 1
                    health_sum += b.health
                    latency_sum += b.latency
                    caps = list(b.capabilities) if b.capabilities else []
                    cap_total += len(caps)
                    cap_set.update(caps)
                if brains:
                    stats.average_health = health_sum / len(brains)
                    stats.average_latency = latency_sum / len(brains)
                stats.total_capabilities = cap_total
                stats.unique_capabilities = len(cap_set)
            except Exception:
                log.exception("Failed to compute ecosystem stats")

        # Pull mission/swarm counts from the appropriate sources
        if self._swarm is not None:
            try:
                swarms = self._swarm.list_swarms()
                stats.active_swarms = sum(
                    1 for s in swarms if s.get("phase") in {"active", "executing", "forming"}
                )
            except Exception:
                log.exception("Failed to read swarm stats")

        # Mission counts from exec memory
        if self._exec_memory is not None:
            try:
                goal_results = await self._safe_await(
                    self._exec_memory.list_goal_results(limit=200)
                )
                stats.completed_missions = sum(1 for r in goal_results if r.get("achieved") is True)
                stats.failed_missions = sum(1 for r in goal_results if r.get("achieved") is False)
            except Exception:
                log.exception("Failed to read goal results for stats")

        # Collaboration counts
        net_stats = self._network.stats()
        stats.total_collaborations = net_stats["total_collaborations"]
        stats.successful_collaborations = net_stats["successful_collaborations"]
        stats.failed_collaborations = net_stats["failed_collaborations"]
        stats.average_confidence = net_stats["average_trust"]

        # Evolution recommendations
        stats.evolution_recommendations = len(self._evolution.list_recommendations())

        from datetime import UTC, datetime

        stats.last_updated = datetime.now(UTC).isoformat()
        self._stats = stats

    def _compute_health(self) -> None:
        """Derive ecosystem health from stats + network trust."""
        stats = self._stats
        health = EcosystemHealth()

        # Availability score = healthy runtimes / total
        if stats.total_runtimes > 0:
            health.availability_score = stats.healthy_runtimes / stats.total_runtimes
        else:
            health.availability_score = 0.0

        # Performance score = inverse of average latency (normalized)
        if stats.average_latency > 0:
            health.performance_score = max(0.0, 1.0 - (stats.average_latency / 5000.0))
        else:
            health.performance_score = 1.0

        # Collaboration score = success rate
        if stats.total_collaborations > 0:
            health.collaboration_score = (
                stats.successful_collaborations / stats.total_collaborations
            )
        else:
            health.collaboration_score = 0.5

        # Evolution score = average confidence (trust)
        health.evolution_score = stats.average_confidence

        # Overall health score = weighted average
        health.health_score = (
            0.35 * health.availability_score
            + 0.25 * health.performance_score
            + 0.20 * health.collaboration_score
            + 0.20 * health.evolution_score
        )

        # Determine level
        if stats.total_runtimes == 0:
            health.level = EcosystemHealthLevel.OFFLINE
            health.issues.append("No runtimes discovered")
        elif health.health_score >= 0.85:
            health.level = EcosystemHealthLevel.OPTIMAL
        elif health.health_score >= 0.70:
            health.level = EcosystemHealthLevel.HEALTHY
        elif health.health_score >= 0.50:
            health.level = EcosystemHealthLevel.DEGRADED
            if stats.unhealthy_runtimes > 0:
                health.issues.append(f"{stats.unhealthy_runtimes} runtime(s) unhealthy")
            if stats.average_latency > 2000:
                health.issues.append(f"High average latency: {stats.average_latency:.0f}ms")
        else:
            health.level = EcosystemHealthLevel.CRITICAL
            if stats.unhealthy_runtimes > 0:
                health.issues.append(f"{stats.unhealthy_runtimes} runtime(s) unhealthy")
            if stats.average_latency > 3000:
                health.issues.append(f"Critical latency: {stats.average_latency:.0f}ms")
            if stats.total_collaborations > 0 and health.collaboration_score < 0.5:
                health.issues.append(
                    f"Low collaboration success rate: {health.collaboration_score:.0%}"
                )

        # Recommendations (actionable)
        if health.availability_score < 0.5 and stats.total_runtimes > 0:
            health.recommendations.append("Discover or restart runtimes to improve availability")
        if health.performance_score < 0.5:
            health.recommendations.append(
                "Investigate high-latency runtimes for routing optimization"
            )
        if stats.total_collaborations > 5 and health.collaboration_score < 0.6:
            health.recommendations.append(
                "Review failing collaborations and demote low-trust runtimes"
            )

        from datetime import UTC, datetime

        health.last_updated = datetime.now(UTC).isoformat()
        self._health = health

    async def _safe_await(self, coro: Any) -> Any:
        try:
            return await coro
        except Exception:
            log.exception("Ecosystem manager helper failed")
            return []

    async def _publish(self, topic: str, payload: dict[str, Any]) -> None:
        try:
            from agentic_os.domain.events import EventEnvelope

            await self._bus.publish(
                EventEnvelope(
                    type=topic,
                    source="ecosystem.manager",
                    topic=topic,
                    payload=payload,
                )
            )
        except Exception:
            log.exception("Failed to publish %s", topic)

    @staticmethod
    def _now_iso() -> str:
        from datetime import UTC, datetime

        return datetime.now(UTC).isoformat()
