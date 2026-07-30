"""Phase 16 — GlobalMissionScheduler.

Evaluates every available runtime across the cluster, scores each
candidate with a deterministic multi-factor formula, and selects the
optimal (node, brain) pair for mission dispatch.

Selection factors (each normalized to [0, 1]):
  - health_score      (brain.health / 100)              weight: 0.18
  - latency_score     (1 - latency/5000)                weight: 0.12
  - availability      (1 if available else 0)           weight: 0.12
  - historical_success (from CollaborationNetwork)       weight: 0.10
  - cluster_load      (1 - cpu_usage/100)               weight: 0.15
  - memory_score      (1 - memory_usage/100)            weight: 0.10
  - provider_score    (1 if provider matches)           weight: 0.05
  - confidence_score  (trust from CollaborationNetwork) weight: 0.08
  - capability_match  (matching/required)               weight: 0.10

Total weights sum to 1.0. Selection is deterministic: identical inputs
always produce identical scores and the same winner (ties broken by
node_id, then brain_id).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from agentic_os.core.cluster.domain import ClusterScore
from agentic_os.infrastructure.logging import get_logger

if TYPE_CHECKING:
    from agentic_os.core.brains.registry import BrainRegistry
    from agentic_os.core.cluster.distributed_registry import DistributedBrainRegistry
    from agentic_os.core.cluster.federation import ClusterFederationManager
    from agentic_os.core.ecosystem.collaboration_network import CollaborationNetwork
    from agentic_os.ports.event_bus import EventBus

log = get_logger("cluster.scheduler")

# Weights — sum to 1.0
_WEIGHTS: dict[str, float] = {
    "health_score": 0.18,
    "latency_score": 0.12,
    "availability_score": 0.12,
    "historical_success": 0.10,
    "cluster_load_score": 0.15,
    "memory_score": 0.10,
    "provider_score": 0.05,
    "confidence_score": 0.08,
    "capability_match": 0.10,
}


class GlobalMissionScheduler:
    """Deterministic cluster-wide runtime selection."""

    def __init__(
        self,
        bus: EventBus | None = None,
        local_registry: BrainRegistry | None = None,
        distributed_registry: DistributedBrainRegistry | None = None,
        federation: ClusterFederationManager | None = None,
        collaboration_network: CollaborationNetwork | None = None,
    ) -> None:
        self._bus = bus
        self._local = local_registry
        self._distributed = distributed_registry
        self._federation = federation
        self._network = collaboration_network
        self._decisions: list[dict[str, Any]] = []
        self._stats: dict[str, int] = {
            "selections_made": 0,
            "candidates_evaluated": 0,
            "rebalances_run": 0,
        }

    # ── Dependency injection ───────────────────────────────────────

    def set_local_registry(self, registry: BrainRegistry) -> None:
        self._local = registry

    def set_distributed_registry(self, registry: DistributedBrainRegistry) -> None:
        self._distributed = registry

    def set_federation(self, federation: ClusterFederationManager) -> None:
        self._federation = federation

    def set_collaboration_network(self, network: CollaborationNetwork) -> None:
        self._network = network

    def set_bus(self, bus: EventBus) -> None:
        self._bus = bus

    # ── Public API ─────────────────────────────────────────────────

    async def select_optimal(
        self,
        required_capabilities: list[str] | None = None,
        preferred_provider: str = "",
        mission_id: str = "",
    ) -> ClusterScore | None:
        """Select the optimal (node, brain) for a mission.

        Returns the winning ClusterScore, or None if no candidates.
        """
        await self._publish(
            "cluster.scheduler.started",
            {
                "mission_id": mission_id,
                "required_capabilities": required_capabilities or [],
                "preferred_provider": preferred_provider,
            },
        )

        candidates = await self._gather_candidates(required_capabilities or [])
        self._stats["candidates_evaluated"] += len(candidates)

        if not candidates:
            await self._publish(
                "cluster.scheduler.completed",
                {"mission_id": mission_id, "result": "no_candidates"},
            )
            return None

        scored = [
            self._score(c, required_capabilities or [], preferred_provider) for c in candidates
        ]
        # Deterministic sort: total_score desc, then node_id asc, then brain_id asc
        scored.sort(key=lambda s: (-s.total_score, s.node_id, s.brain_id))
        winner = scored[0]

        self._decisions.append(
            {
                "mission_id": mission_id,
                "winner": winner.to_dict(),
                "candidates_evaluated": len(candidates),
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )
        self._stats["selections_made"] += 1

        await self._publish(
            "cluster.scheduler.completed",
            {
                "mission_id": mission_id,
                "winner": winner.to_dict(),
                "candidates_evaluated": len(candidates),
            },
        )
        return winner

    async def rebalance(self) -> dict[str, Any]:
        """Re-evaluate active missions and suggest rebalancing.

        For Phase 16 this is a stub that publishes the event — the
        actual mission migration would be handled by FailoverEngine.
        """
        self._stats["rebalances_run"] += 1
        await self._publish(
            "cluster.scheduler.started",
            {"action": "rebalance", "timestamp": datetime.now(UTC).isoformat()},
        )
        result = {
            "rebalanced": True,
            "rebalances_run": self._stats["rebalances_run"],
            "timestamp": datetime.now(UTC).isoformat(),
        }
        await self._publish("cluster.scheduler.completed", result)
        return result

    def list_decisions(self, limit: int = 50) -> list[dict[str, Any]]:
        return list(self._decisions[-limit:])

    def stats(self) -> dict[str, Any]:
        return {**self._stats, "weights": dict(_WEIGHTS)}

    # ── Candidate gathering ────────────────────────────────────────

    async def _gather_candidates(self, required_capabilities: list[str]) -> list[dict[str, Any]]:
        """Gather all candidate (node, brain) pairs across the cluster.

        Each candidate dict has:
          - node_id, brain_id, brain_name
          - health, latency, availability
          - cpu_usage, memory_usage (from node)
          - capabilities, provider
        """
        candidates: list[dict[str, Any]] = []

        # Local brains
        if self._local is not None and self._federation is not None:
            try:
                local_brains = await self._local.list_all()
                local_node = self._federation.topology.get_node(self._federation.local_node_id)
                for b in local_brains:
                    caps = list(b.capabilities) if b.capabilities else []
                    if required_capabilities and not any(c in caps for c in required_capabilities):
                        continue
                    candidates.append(
                        {
                            "node_id": self._federation.local_node_id,
                            "brain_id": b.id,
                            "brain_name": b.display_name,
                            "health": b.health,
                            "latency": b.latency,
                            "availability": 1.0 if b.health >= 50 else 0.0,
                            "cpu_usage": local_node.cpu_usage if local_node else 0,
                            "memory_usage": local_node.memory_usage if local_node else 0,
                            "capabilities": caps,
                            "provider": str(b.vendor.value)
                            if hasattr(b.vendor, "value")
                            else str(b.vendor),
                            "scope": "local",
                        }
                    )
            except Exception:
                log.exception("Failed to gather local candidates")

        # Remote brains
        if self._distributed is not None:
            try:
                remote_brains = self._distributed.list_remote_brains()
                for r in remote_brains:
                    caps = list(r.capabilities)
                    if required_capabilities and not any(c in caps for c in required_capabilities):
                        continue
                    node = (
                        self._federation.topology.get_node(r.node_id) if self._federation else None
                    )
                    candidates.append(
                        {
                            "node_id": r.node_id,
                            "brain_id": r.brain_id,
                            "brain_name": r.display_name,
                            "health": r.health,
                            "latency": r.latency,
                            "availability": r.availability,
                            "cpu_usage": node.cpu_usage if node else 0,
                            "memory_usage": node.memory_usage if node else 0,
                            "capabilities": caps,
                            "provider": r.provider,
                            "scope": "remote",
                        }
                    )
            except Exception:
                log.exception("Failed to gather remote candidates")

        return candidates

    # ── Scoring ────────────────────────────────────────────────────

    def _score(
        self,
        candidate: dict[str, Any],
        required_capabilities: list[str],
        preferred_provider: str,
    ) -> ClusterScore:
        """Compute a deterministic ClusterScore for one candidate."""
        node_id = str(candidate.get("node_id", ""))
        brain_id = str(candidate.get("brain_id", ""))
        brain_name = str(candidate.get("brain_name", ""))
        health = float(candidate.get("health", 0))
        latency = float(candidate.get("latency", 0))
        availability = float(candidate.get("availability", 0))
        cpu_usage = float(candidate.get("cpu_usage", 0))
        memory_usage = float(candidate.get("memory_usage", 0))
        caps = list(candidate.get("capabilities") or [])
        provider = str(candidate.get("provider", ""))

        # Normalized factors
        health_score = max(0.0, min(1.0, health / 100.0))
        latency_score = max(0.0, 1.0 - (latency / 5000.0)) if latency > 0 else 0.5
        availability_score = max(0.0, min(1.0, availability))
        cluster_load_score = max(0.0, 1.0 - (cpu_usage / 100.0))
        memory_score = max(0.0, 1.0 - (memory_usage / 100.0))
        provider_score = 1.0 if preferred_provider and provider == preferred_provider else 0.5
        if required_capabilities:
            matching = sum(1 for c in required_capabilities if c in caps)
            capability_match = matching / len(required_capabilities)
        else:
            capability_match = 1.0

        # Historical success + confidence from CollaborationNetwork
        historical_success = 0.5
        confidence_score = 0.5
        if self._network is not None:
            try:
                stats = self._network.runtime_stats(brain_id)
                if stats["total"] > 0:
                    historical_success = stats["success_rate"]
                confidence_score = stats["average_trust"]
            except Exception:
                pass

        total = (
            _WEIGHTS["health_score"] * health_score
            + _WEIGHTS["latency_score"] * latency_score
            + _WEIGHTS["availability_score"] * availability_score
            + _WEIGHTS["historical_success"] * historical_success
            + _WEIGHTS["cluster_load_score"] * cluster_load_score
            + _WEIGHTS["memory_score"] * memory_score
            + _WEIGHTS["provider_score"] * provider_score
            + _WEIGHTS["confidence_score"] * confidence_score
            + _WEIGHTS["capability_match"] * capability_match
        )

        rationale_parts: list[str] = []
        rationale_parts.append(f"health={health_score:.2f}")
        rationale_parts.append(f"latency={latency_score:.2f}")
        rationale_parts.append(f"avail={availability_score:.2f}")
        rationale_parts.append(f"load={cluster_load_score:.2f}")
        rationale_parts.append(f"cap_match={capability_match:.2f}")
        rationale_parts.append(f"hist_success={historical_success:.2f}")
        rationale_parts.append(f"trust={confidence_score:.2f}")

        return ClusterScore(
            node_id=node_id,
            brain_id=brain_id,
            brain_name=brain_name,
            health_score=health_score,
            latency_score=latency_score,
            availability_score=availability_score,
            historical_success=historical_success,
            cluster_load_score=cluster_load_score,
            memory_score=memory_score,
            provider_score=provider_score,
            confidence_score=confidence_score,
            capability_match=capability_match,
            total_score=round(total, 4),
            rationale=f"Selected via weighted score ({', '.join(rationale_parts)})",
        )

    # ── Internal ───────────────────────────────────────────────────

    async def _publish(self, topic: str, payload: dict[str, Any]) -> None:
        if self._bus is None:
            return
        try:
            from agentic_os.domain.events import EventEnvelope

            await self._bus.publish(
                EventEnvelope(
                    type=topic,
                    source="cluster.scheduler",
                    topic=topic,
                    payload=payload,
                )
            )
        except Exception:
            log.exception("Failed to publish %s", topic)
