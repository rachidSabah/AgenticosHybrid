"""Phase 15 — EvolutionEngine.

Analyzes historical data from the Executive and Cognitive layers and
produces concrete evolution recommendations:

  - recommended_capability     (which capability is missing / underprovisioned)
  - recommended_routing        (which runtime should handle which capability)
  - recommended_collaboration  (which runtimes should collaborate more)
  - recommended_optimization   (which runtime to demote / promote / replace)

The engine is a pure consumer of:
  - ExecutiveMemory (decisions, reflections, goal results)
  - CognitiveMemory (predictions, evaluations, experience)
  - BrainRegistry (live runtime health)
  - CapabilityGraph (capability coverage)
  - CollaborationNetwork (trust scores)
  - SwarmCoordinator (swarm history)

It does NOT modify those sources — it only reads them and emits
``EvolutionRecommendation`` objects. Recommendations flow back through
the EventBus via ``ecosystem.evolution.generated`` so the Executive
and Cognitive layers can react if they choose.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agentic_os.core.ecosystem.domain import (
    EvolutionRecommendation,
    RecommendationType,
)
from agentic_os.infrastructure.logging import get_logger

if TYPE_CHECKING:
    from agentic_os.core.brains.registry import BrainRegistry
    from agentic_os.core.cognitive.memory import CognitiveMemory
    from agentic_os.core.ecosystem.capability_graph import CapabilityGraph
    from agentic_os.core.ecosystem.collaboration_network import CollaborationNetwork
    from agentic_os.core.executive.memory import ExecutiveMemory

log = get_logger("ecosystem.evolution")


class EvolutionEngine:
    """Produces self-evolution recommendations from historical data.

    All analysis methods are public so they can be tested in isolation
    and so the EcosystemController can call them individually if needed.
    """

    def __init__(
        self,
        brain_registry: BrainRegistry | None = None,
        exec_memory: ExecutiveMemory | None = None,
        cognitive_memory: CognitiveMemory | None = None,
        capability_graph: CapabilityGraph | None = None,
        collaboration_network: CollaborationNetwork | None = None,
    ) -> None:
        self._registry = brain_registry
        self._exec_memory = exec_memory
        self._cog_memory = cognitive_memory
        self._graph = capability_graph
        self._network = collaboration_network
        self._recommendations: list[EvolutionRecommendation] = []
        self._analyses_run = 0

    # ── Public API ──────────────────────────────────────────────────

    def set_capability_graph(self, graph: CapabilityGraph) -> None:
        self._graph = graph

    def set_collaboration_network(self, network: CollaborationNetwork) -> None:
        self._network = network

    async def analyze_all(self) -> list[EvolutionRecommendation]:
        """Run every analyzer and append results to ``recommendations``."""
        recs: list[EvolutionRecommendation] = []
        recs.extend(await self.analyze_capability_gaps())
        recs.extend(await self.analyze_routing_optimizations())
        recs.extend(await self.analyze_collaboration_opportunities())
        recs.extend(await self.analyze_performance_optimizations())
        self._recommendations.extend(recs)
        # Cap stored recommendations at 200 (keep most recent)
        if len(self._recommendations) > 200:
            self._recommendations = self._recommendations[-200:]
        self._analyses_run += 1
        return recs

    def list_recommendations(
        self,
        rec_type: RecommendationType | str | None = None,
        limit: int = 50,
    ) -> list[EvolutionRecommendation]:
        if rec_type is None:
            return list(self._recommendations[-limit:])
        if isinstance(rec_type, str):
            rec_type = RecommendationType(rec_type)
        return [r for r in self._recommendations[-limit:] if r.type == rec_type]

    def clear_recommendations(self) -> None:
        self._recommendations.clear()

    def stats(self) -> dict[str, Any]:
        by_type: dict[str, int] = {t.value: 0 for t in RecommendationType}
        for r in self._recommendations:
            by_type[r.type.value] = by_type.get(r.type.value, 0) + 1
        return {
            "total_recommendations": len(self._recommendations),
            "analyses_run": self._analyses_run,
            "by_type": by_type,
        }

    # ── Analyzers ───────────────────────────────────────────────────

    async def analyze_capability_gaps(self) -> list[EvolutionRecommendation]:
        """Find capabilities required by past missions but rarely satisfied."""
        recs: list[EvolutionRecommendation] = []
        if self._exec_memory is None or self._graph is None:
            return recs

        # Pull capability demand from past goal results / reflections
        try:
            decisions = await self._safe_call(self._exec_memory.list_decisions, [])
            reflections = await self._safe_call(self._exec_memory.list_reflections, [])
        except Exception:
            log.exception("Failed to read executive memory for capability analysis")
            return recs

        # Tally required capabilities that were hard to satisfy.
        # Decisions store the required capability inside the ``factors`` dict
        # (see DecisionEngine.select) — fall back to top-level for safety.
        demand: dict[str, dict[str, int]] = {}
        for d in decisions:
            factors = d.get("factors") or {}
            cap = str(factors.get("required_capability") or d.get("required_capability") or "")
            if not cap:
                continue
            entry = demand.setdefault(cap, {"requested": 0, "satisfied": 0})
            entry["requested"] += 1
            if d.get("selected_runtime"):
                entry["satisfied"] += 1

        for cap, tally in demand.items():
            if tally["requested"] < 2:
                continue
            satisfaction = tally["satisfied"] / tally["requested"]
            if satisfaction >= 0.8:
                continue
            providers = self._graph.providers_of(cap)
            recs.append(
                EvolutionRecommendation(
                    type=RecommendationType.CAPABILITY,
                    title=f"Underprovisioned capability: {cap}",
                    rationale=(
                        f"Capability '{cap}' was requested {tally['requested']} times "
                        f"but only satisfied {tally['satisfied']} ({satisfaction:.0%}). "
                        f"Currently provided by {len(providers)} runtime(s)."
                    ),
                    target_id=cap,
                    target_type="capability",
                    priority=0.8 if satisfaction < 0.5 else 0.6,
                    confidence=min(1.0, tally["requested"] / 10.0),
                    expected_impact=(1.0 - satisfaction) * 0.5,
                    evidence={
                        "capability": cap,
                        "requested": tally["requested"],
                        "satisfied": tally["satisfied"],
                        "current_providers": providers,
                    },
                    action={
                        "discover_more": True,
                        "capability": cap,
                        "target_provider_count": max(len(providers) + 1, 3),
                    },
                )
            )

        # Detect capabilities referenced in reflections but not in the graph.
        # Reflection stores missing-capability info under ``capability_gaps``.
        for r in reflections:
            for cap in r.get("capability_gaps", []) or []:
                cap = str(cap)
                if not self._graph.providers_of(cap):
                    recs.append(
                        EvolutionRecommendation(
                            type=RecommendationType.CAPABILITY,
                            title=f"Missing capability: {cap}",
                            rationale=(
                                f"Reflection {r.get('id', '?')} identified '{cap}' "
                                "as a gap — no runtime currently provides it."
                            ),
                            target_id=cap,
                            target_type="capability",
                            priority=0.9,
                            confidence=0.7,
                            expected_impact=0.4,
                            evidence={"reflection_id": r.get("id", ""), "capability": cap},
                            action={"discover_more": True, "capability": cap},
                        )
                    )

        # Also surface capabilities that exist in the graph but have only one provider
        # (single point of failure)
        if self._graph is not None:
            for node in self._graph.list_nodes("capability"):
                providers = self._graph.providers_of(node.label)
                if len(providers) == 1:
                    recs.append(
                        EvolutionRecommendation(
                            type=RecommendationType.CAPABILITY,
                            title=f"Single-provider capability: {node.label}",
                            rationale=(
                                f"Capability '{node.label}' is provided by only one "
                                f"runtime ({providers[0]}). Recommend discovering "
                                "additional providers for redundancy."
                            ),
                            target_id=node.id,
                            target_type="capability",
                            priority=0.5,
                            confidence=0.6,
                            expected_impact=0.3,
                            evidence={"capability": node.label, "provider": providers[0]},
                            action={"discover_more": True, "capability": node.label},
                        )
                    )

        return recs

    async def analyze_routing_optimizations(self) -> list[EvolutionRecommendation]:
        """Recommend re-routing capabilities to better-performing runtimes."""
        recs: list[EvolutionRecommendation] = []
        if self._registry is None or self._graph is None:
            return recs

        try:
            brains = await self._registry.list_all()
        except Exception:
            log.exception("Failed to read BrainRegistry for routing analysis")
            return recs

        for brain in brains:
            # Find low-health or high-latency runtimes that should be demoted
            if brain.health < 50 or brain.latency > 2000:
                caps = list(brain.capabilities)
                # Find alternative providers for each capability
                for cap in caps:
                    alt_providers = [
                        b
                        for b in brains
                        if b.id != brain.id
                        and cap in b.capabilities
                        and b.health >= 70
                        and b.latency < brain.latency
                    ]
                    if alt_providers:
                        best_alt = min(alt_providers, key=lambda b: b.latency)
                        recs.append(
                            EvolutionRecommendation(
                                type=RecommendationType.ROUTING,
                                title=f"Re-route '{cap}' away from {brain.display_name}",
                                rationale=(
                                    f"{brain.display_name} has health={brain.health:.0f} "
                                    f"latency={brain.latency:.0f}ms. Alternative "
                                    f"{best_alt.display_name} (health={best_alt.health:.0f}, "
                                    f"latency={best_alt.latency:.0f}ms) is healthier/faster."
                                ),
                                target_id=brain.id,
                                target_type="brain",
                                priority=0.7,
                                confidence=0.8,
                                expected_impact=0.3,
                                evidence={
                                    "current_provider": brain.id,
                                    "current_health": brain.health,
                                    "current_latency": brain.latency,
                                    "alternative_provider": best_alt.id,
                                    "alternative_health": best_alt.health,
                                    "alternative_latency": best_alt.latency,
                                    "capability": cap,
                                },
                                action={
                                    "reroute": True,
                                    "capability": cap,
                                    "from": brain.id,
                                    "to": best_alt.id,
                                },
                            )
                        )
                        break  # one recommendation per brain is enough

        return recs

    async def analyze_collaboration_opportunities(self) -> list[EvolutionRecommendation]:
        """Recommend swarms of runtimes that haven't collaborated but should."""
        recs: list[EvolutionRecommendation] = []
        if self._registry is None or self._network is None:
            return recs

        try:
            brains = await self._registry.list_all()
        except Exception:
            log.exception("Failed to read BrainRegistry for collaboration analysis")
            return recs

        # Find complementary capability pairs that have never collaborated
        for i, a in enumerate(brains):
            a_caps = set(a.capabilities)
            for b in brains[i + 1 :]:
                b_caps = set(b.capabilities)
                # Complementary: capabilities that one has but the other doesn't
                complementary = (a_caps - b_caps) | (b_caps - a_caps)
                common = a_caps & b_caps
                # Score: more complementary + more common = better team
                if not complementary or len(common) < 1:
                    continue
                existing_link = self._network.get_link(a.id, b.id)
                if existing_link is not None and existing_link.total >= 1:
                    continue  # Already collaborated
                score = (len(complementary) * 0.5 + len(common) * 0.5) / max(
                    len(a_caps | b_caps), 1
                )
                recs.append(
                    EvolutionRecommendation(
                        type=RecommendationType.COLLABORATION,
                        title=f"Pair {a.display_name} with {b.display_name}",
                        rationale=(
                            f"{a.display_name} (caps: {sorted(a_caps)}) and "
                            f"{b.display_name} (caps: {sorted(b_caps)}) have "
                            f"{len(complementary)} complementary and "
                            f"{len(common)} common capabilities but have never "
                            "collaborated."
                        ),
                        target_id=f"{a.id}+{b.id}",
                        target_type="brain_pair",
                        priority=round(min(0.8, score), 3),
                        confidence=0.6,
                        expected_impact=0.2,
                        evidence={
                            "brain_a": a.id,
                            "brain_b": b.id,
                            "complementary": sorted(complementary),
                            "common": sorted(common),
                        },
                        action={
                            "form_swarm": True,
                            "members": [a.id, b.id],
                            "complementary": sorted(complementary),
                        },
                    )
                )
                if len(recs) >= 20:
                    return recs

        return recs

    async def analyze_performance_optimizations(self) -> list[EvolutionRecommendation]:
        """Recommend demoting consistently-failing runtimes."""
        recs: list[EvolutionRecommendation] = []
        if self._network is None or self._registry is None:
            return recs

        try:
            brains = await self._registry.list_all()
        except Exception:
            log.exception("Failed to read BrainRegistry for performance analysis")
            return recs

        for brain in brains:
            stats = self._network.runtime_stats(brain.id)
            if stats["total"] < 3:
                continue
            if stats["success_rate"] < 0.4:
                recs.append(
                    EvolutionRecommendation(
                        type=RecommendationType.OPTIMIZATION,
                        title=f"Demote {brain.display_name} (low success rate)",
                        rationale=(
                            f"{brain.display_name} has a collaboration success rate "
                            f"of {stats['success_rate']:.0%} over {stats['total']} "
                            "collaborations. Recommend deprioritizing in future "
                            "task assignment."
                        ),
                        target_id=brain.id,
                        target_type="brain",
                        priority=0.8,
                        confidence=min(1.0, stats["total"] / 10.0),
                        expected_impact=0.4,
                        evidence={
                            "runtime_id": brain.id,
                            "success_rate": stats["success_rate"],
                            "total_collaborations": stats["total"],
                            "average_trust": stats["average_trust"],
                        },
                        action={
                            "deprioritize": True,
                            "runtime_id": brain.id,
                            "new_priority": 0.3,
                        },
                    )
                )
            elif stats["success_rate"] >= 0.9 and stats["total"] >= 5:
                recs.append(
                    EvolutionRecommendation(
                        type=RecommendationType.OPTIMIZATION,
                        title=f"Promote {brain.display_name} (high success rate)",
                        rationale=(
                            f"{brain.display_name} has a collaboration success rate "
                            f"of {stats['success_rate']:.0%} over {stats['total']} "
                            "collaborations. Recommend prioritizing in future "
                            "task assignment and leadership roles."
                        ),
                        target_id=brain.id,
                        target_type="brain",
                        priority=0.6,
                        confidence=min(1.0, stats["total"] / 10.0),
                        expected_impact=0.3,
                        evidence={
                            "runtime_id": brain.id,
                            "success_rate": stats["success_rate"],
                            "total_collaborations": stats["total"],
                            "average_trust": stats["average_trust"],
                        },
                        action={
                            "prioritize": True,
                            "runtime_id": brain.id,
                            "new_priority": 0.9,
                        },
                    )
                )

        # Cognitive memory: prediction accuracy
        if self._cog_memory is not None:
            try:
                predictions = await self._safe_call(self._cog_memory.list_predictions, [])
                if predictions:
                    accurate = sum(
                        1
                        for p in predictions
                        if p.get("actual_outcome") is not None
                        and p.get("actual_outcome") == p.get("predicted_outcome")
                    )
                    total = sum(1 for p in predictions if p.get("actual_outcome") is not None)
                    if total >= 5:
                        accuracy = accurate / total
                        if accuracy < 0.5:
                            recs.append(
                                EvolutionRecommendation(
                                    type=RecommendationType.OPTIMIZATION,
                                    title="Retrain prediction engine (low accuracy)",
                                    rationale=(
                                        f"Prediction accuracy is {accuracy:.0%} over "
                                        f"{total} predictions. Recommend recalibrating "
                                        "the prediction model weights."
                                    ),
                                    target_id="prediction_engine",
                                    target_type="cognitive_engine",
                                    priority=0.6,
                                    confidence=0.7,
                                    expected_impact=0.2,
                                    evidence={
                                        "accurate_predictions": accurate,
                                        "total_predictions": total,
                                        "accuracy": accuracy,
                                    },
                                    action={"retrain": True, "engine": "prediction_engine"},
                                )
                            )
            except Exception:
                log.exception("Failed to read cognitive memory for prediction analysis")

        return recs

    # ── Helpers ─────────────────────────────────────────────────────

    async def _safe_call(self, func: Any, default: Any) -> Any:
        """Call a sync or async method safely. Returns ``default`` on failure."""
        try:
            result = func()
            if hasattr(result, "__await__"):
                return await result
            return result
        except Exception:
            log.exception("Evolution analysis helper failed")
            return default

    def to_dict(self) -> dict[str, Any]:
        return {
            "recommendations": [r.to_dict() for r in self._recommendations[-50:]],
            "stats": self.stats(),
        }
