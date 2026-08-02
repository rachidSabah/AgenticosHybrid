"""Routing optimizer — analyzes routing decisions and optimizes task routing."""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from agentic_os.domain.learning import (
    ExecutionHistory,
    OptimizationRecommendation,
    OptimizationTarget,
    RecommendationStatus,
    RoutingDecision,
)
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.learning import RoutingOptimizationPort

log = get_logger("learning.routing")


def _utcnow() -> datetime:
    return datetime.now(UTC)


class RoutingOptimizer(RoutingOptimizationPort):
    """In-memory routing optimizer implementing RoutingOptimizationPort.

    Analyzes historical routing decisions and execution data to identify
    improvement opportunities and generate optimized routing strategies.
    Stores routing decisions in memory for analysis.
    """

    def __init__(self) -> None:
        self._routing_decisions: dict[str, RoutingDecision] = {}
        self._execution_history: dict[str, ExecutionHistory] = {}
        self._optimization_recommendations: dict[str, OptimizationRecommendation] = {}

    # ── Data ingestion ──

    def record_routing_decision(self, decision: RoutingDecision) -> RoutingDecision:
        """Store a routing decision for historical analysis."""
        self._routing_decisions[decision.id] = decision
        log.debug("Recorded routing decision", decision_id=decision.id)
        return decision

    def record_execution(self, history: ExecutionHistory) -> ExecutionHistory:
        """Store an execution record for analysis."""
        self._execution_history[history.id] = history
        return history

    # ── Analysis ──

    async def analyze_routing(self) -> Sequence[OptimizationRecommendation]:
        recommendations: list[OptimizationRecommendation] = []
        decisions = list(self._routing_decisions.values())

        if not decisions:
            return recommendations

        # Group decisions by selected engine to find under/over-utilized engines
        engine_counts: dict[str, list[RoutingDecision]] = {}
        for d in decisions:
            engine_counts.setdefault(d.selected_engine, []).append(d)

        # Check for engines with low success rates
        for engine, engine_decisions in engine_counts.items():
            completed = [d for d in engine_decisions if d.success is not None]
            if not completed or len(completed) < 3:
                continue
            success_rate = sum(1 for d in completed if d.success) / len(completed)
            if success_rate < 0.7:
                rec = OptimizationRecommendation(
                    target=OptimizationTarget.ROUTING,
                    current_value=f"engine:{engine}",
                    recommended_value=f"reduced routing to {engine}",
                    confidence=round(success_rate, 2),
                    supporting_evidence=(
                        f"Engine {engine} has {success_rate:.0%} success rate "
                        f"across {len(completed)} routed executions."
                    ),
                    historical_data={
                        "engine": engine,
                        "success_rate": success_rate,
                        "total_routed": len(completed),
                        "success_count": sum(1 for d in completed if d.success),
                    },
                    alternatives=tuple(e for e in engine_counts if e != engine)
                    or ("fallback_engine",),
                    estimated_improvement=round((0.95 - success_rate) * 100, 1),
                    source="routing_optimizer",
                )
                self._optimization_recommendations[rec.id] = rec
                recommendations.append(rec)
                log.info(
                    "Routing improvement identified",
                    engine=engine,
                    success_rate=success_rate,
                    rec_id=rec.id,
                )

        # Check for engines with high latency variance
        for engine, engine_decisions in engine_counts.items():
            with_latency = [
                d
                for d in engine_decisions
                if d.actual_latency_ms is not None and d.expected_latency_ms > 0
            ]
            if len(with_latency) < 3:
                continue
            ratios = [
                d.actual_latency_ms / d.expected_latency_ms
                for d in with_latency
                if d.actual_latency_ms is not None
            ]
            avg_ratio = sum(ratios) / len(ratios)
            if avg_ratio > 1.5:
                rec = OptimizationRecommendation(
                    target=OptimizationTarget.ROUTING,
                    current_value=f"engine:{engine} (latency ratio {avg_ratio:.1f}x)",
                    recommended_value=f"apply latency优化 for {engine}",
                    confidence=0.6,
                    supporting_evidence=(
                        f"Engine {engine} averages {avg_ratio:.1f}x expected latency "
                        f"across {len(with_latency)} executions."
                    ),
                    historical_data={
                        "engine": engine,
                        "avg_latency_ratio": avg_ratio,
                        "sample_count": len(with_latency),
                    },
                    alternatives=(
                        "increase timeout",
                        "route to faster engine",
                        "adjust concurrency",
                    ),
                    estimated_improvement=round((avg_ratio - 1.0) * 50, 1),
                    source="routing_optimizer",
                )
                self._optimization_recommendations[rec.id] = rec
                recommendations.append(rec)
                log.info(
                    "Latency variance detected",
                    engine=engine,
                    avg_ratio=avg_ratio,
                    rec_id=rec.id,
                )

        return recommendations

    async def optimize_routing(self, recommendation_id: str) -> RoutingDecision:
        rec = self._optimization_recommendations.get(recommendation_id)
        if rec is None:
            raise ValueError(f"Optimization recommendation not found: {recommendation_id}")

        # Generate an optimized routing decision based on the recommendation
        selected = rec.recommended_value.replace("reduced routing to ", "").strip()
        if not selected:
            selected = rec.recommended_value

        alternatives_list = list(rec.alternatives) if rec.alternatives else []

        decision = RoutingDecision(
            execution_id=f"optimized-{rec.id}",
            selected_engine=selected,
            alternative_engines=tuple(alternatives_list),
            selection_reason=rec.supporting_evidence,
            confidence=rec.confidence,
            expected_latency_ms=0.0,
            expected_cost=0.0,
        )
        self._routing_decisions[decision.id] = decision

        # Mark recommendation as applied
        updated_rec = OptimizationRecommendation(
            id=rec.id,
            target=rec.target,
            current_value=rec.current_value,
            recommended_value=rec.recommended_value,
            confidence=rec.confidence,
            supporting_evidence=rec.supporting_evidence,
            historical_data=rec.historical_data,
            alternatives=rec.alternatives,
            estimated_improvement=rec.estimated_improvement,
            status=RecommendationStatus.APPLIED,
            source=rec.source,
            created_at=rec.created_at,
            applied_at=_utcnow(),
        )
        self._optimization_recommendations[rec.id] = updated_rec

        log.info(
            "Routing optimization applied",
            rec_id=recommendation_id,
            decision_id=decision.id,
            selected=selected,
        )
        return decision

    async def get_routing_history(self, limit: int = 100) -> Sequence[RoutingDecision]:
        results = sorted(
            self._routing_decisions.values(),
            key=lambda d: d.created_at,
            reverse=True,
        )
        return results[:limit]

    async def get_routing_stats(self) -> dict[str, Any]:
        decisions = list(self._routing_decisions.values())
        if not decisions:
            return {
                "total_decisions": 0,
                "engines_used": [],
                "avg_confidence": 0.0,
                "success_rate": 0.0,
                "avg_expected_latency_ms": 0.0,
            }

        completed = [d for d in decisions if d.success is not None]
        success_rate = sum(1 for d in completed if d.success) / len(completed) if completed else 0.0

        engine_set: set[str] = set()
        for d in decisions:
            engine_set.add(d.selected_engine)
            for alt in d.alternative_engines:
                engine_set.add(alt)

        avg_confidence = sum(d.confidence for d in decisions) / len(decisions)
        avg_latency = sum(d.expected_latency_ms for d in decisions) / len(decisions)

        return {
            "total_decisions": len(decisions),
            "engines_used": sorted(engine_set),
            "avg_confidence": round(avg_confidence, 3),
            "success_rate": round(success_rate, 3),
            "avg_expected_latency_ms": round(avg_latency, 1),
            "recommendations_active": sum(
                1
                for r in self._optimization_recommendations.values()
                if r.status == RecommendationStatus.ACTIVE
            ),
        }
