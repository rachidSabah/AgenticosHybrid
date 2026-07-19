"""Optimization engine — analyze performance, generate recommendations, route tasks."""

import random
from collections.abc import Sequence
from datetime import UTC, datetime

from agentic_os.domain.learning import (
    EnginePerformance,
    OptimizationPolicy,
    OptimizationRecommendation,
    Recommendation,
    RecommendationPriority,
    RoutingDecision,
)
from agentic_os.ports.learning import OptimizerPort


def _utcnow() -> datetime:
    return datetime.now(UTC)


class OptimizationEngine(OptimizerPort):
    """In-memory optimization engine using heuristic analysis.

    Analyzes performance data, generates recommendations, and optimizes
    routing decisions.  A production deployment would augment the
    heuristics with a learned cost model.
    """

    def __init__(self) -> None:
        self._recommendations: dict[str, Recommendation] = {}
        self._optimization_recommendations: dict[str, OptimizationRecommendation] = {}
        self._routing_decisions: dict[str, RoutingDecision] = {}
        self._policies: dict[str, OptimizationPolicy] = {}
        self._engine_performance: dict[str, EnginePerformance] = {}

    def set_engine_performance(self, performances: Sequence[EnginePerformance]) -> None:
        """Seed the optimizer with current engine performance data."""
        for perf in performances:
            self._engine_performance[perf.engine_id] = perf

    # ── Performance Analysis ──

    async def analyze_performance(
        self,
        target_id: str,
        target_type: str,
    ) -> Sequence[OptimizationRecommendation]:
        engine = self._engine_performance.get(target_id)
        if engine is None:
            return []

        recommendations: list[OptimizationRecommendation] = []

        # High latency heuristic
        if engine.avg_latency_ms > 1000 and engine.total_executions > 5:
            rec = OptimizationRecommendation(
                id=f"opt-{int(_utcnow().timestamp())}-{random.randint(1000, 9999)}",
                target_id=target_id,
                target_type=target_type,
                recommendation_type="engine",
                title="High latency detected — consider engine upgrade or routing change",
                description=(
                    f"Average latency {engine.avg_latency_ms:.0f}ms exceeds 1000ms threshold."
                ),
                expected_improvement=0.3,
                priority=RecommendationPriority.HIGH,
                confidence=0.7,
                parameters={
                    "current_latency_ms": engine.avg_latency_ms,
                    "target_latency_ms": 500.0,
                },
                rationale="Latency consistently above threshold across executions.",
            )
            self._optimization_recommendations[rec.id] = rec
            recommendations.append(rec)

        # Low success rate heuristic
        if engine.total_executions > 5 and engine.success_rate < 0.8:
            rec = OptimizationRecommendation(
                id=f"opt-{int(_utcnow().timestamp())}-{random.randint(1000, 9999)}",
                target_id=target_id,
                target_type=target_type,
                recommendation_type="engine",
                title="Low success rate — investigate failures or reduce load",
                description=(f"Success rate {engine.success_rate:.1%} is below 80% threshold."),
                expected_improvement=0.2,
                priority=RecommendationPriority.CRITICAL,
                confidence=0.8,
                parameters={
                    "current_success_rate": engine.success_rate,
                    "target_success_rate": 0.95,
                },
                rationale="Failure rate above acceptable threshold.",
            )
            self._optimization_recommendations[rec.id] = rec
            recommendations.append(rec)

        return recommendations

    # ── Routing ──

    async def optimize_routing(
        self,
        task_id: str,
        required_capabilities: Sequence[str],
        available_engines: Sequence[str],
    ) -> RoutingDecision:
        if not available_engines:
            raise ValueError("No available engines to route to")

        # Simple heuristic: pick engine with lowest average latency
        candidates = [(eid, self._engine_performance.get(eid)) for eid in available_engines]
        candidates_with_data = [(eid, p) for eid, p in candidates if p is not None]

        if candidates_with_data:
            best = min(candidates_with_data, key=lambda x: x[1].avg_latency_ms)
            selected = best[0]
            expected_latency = best[1].avg_latency_ms
            confidence = max(
                0.5, min(0.95, 1.0 - (best[1].failure_count / max(best[1].total_executions, 1)))
            )
            reason = f"Lowest avg latency ({best[1].avg_latency_ms:.0f}ms)"
        else:
            selected = available_engines[0]
            expected_latency = 500.0
            confidence = 0.5
            reason = "No performance data — default selection"

        decision = RoutingDecision(
            id=f"route-{int(_utcnow().timestamp())}-{random.randint(1000, 9999)}",
            task_id=task_id,
            selected_engine_id=selected,
            alternative_engine_ids=tuple(available_engines),
            routing_reason=reason,
            expected_latency_ms=expected_latency,
            expected_cost=0.01,
            confidence=confidence,
            metadata={"required_capabilities": list(required_capabilities)},
        )
        self._routing_decisions[decision.id] = decision
        return decision

    # ── Recommendations ──

    async def generate_recommendations(
        self,
        target_id: str,
        target_type: str,
        limit: int = 10,
    ) -> Sequence[Recommendation]:
        engine = self._engine_performance.get(target_id)
        if engine is None:
            return []

        recs: list[Recommendation] = []

        if engine.avg_latency_ms > 1000:
            recs.append(
                Recommendation(
                    id=f"rec-{int(_utcnow().timestamp())}-r1",
                    title="Reduce engine latency",
                    description=(
                        f"Average latency is {engine.avg_latency_ms:.0f}ms."
                        " Consider scaling or load balancing."
                    ),
                    recommendation_type="engine",
                    priority=RecommendationPriority.HIGH,
                    expected_benefit=f"Reduce latency from {engine.avg_latency_ms:.0f}ms to ~500ms",
                    effort="medium",
                    parameters={"current_latency_ms": engine.avg_latency_ms},
                )
            )

        if engine.success_rate < 0.9:
            recs.append(
                Recommendation(
                    id=f"rec-{int(_utcnow().timestamp())}-r2",
                    title="Improve execution reliability",
                    description=(
                        f"Success rate is {engine.success_rate:.1%}."
                        " Review error logs and retry policies."
                    ),
                    recommendation_type="engine",
                    priority=RecommendationPriority.CRITICAL,
                    expected_benefit=f"Improve success rate from {engine.success_rate:.1%} to >95%",
                    effort="high",
                    parameters={"current_success_rate": engine.success_rate},
                )
            )

        if engine.avg_cost > 0.05:
            recs.append(
                Recommendation(
                    id=f"rec-{int(_utcnow().timestamp())}-r3",
                    title="Optimize execution cost",
                    description=f"Average cost ${engine.avg_cost:.4f} per execution is high.",
                    recommendation_type="policy",
                    priority=RecommendationPriority.MEDIUM,
                    expected_benefit=f"Reduce cost from ${engine.avg_cost:.4f} to <$0.01",
                    effort="low",
                    parameters={"current_cost": engine.avg_cost},
                )
            )

        for rec in recs:
            self._recommendations[rec.id] = rec

        return recs[:limit]

    # ── Recommendation CRUD ──

    async def get_recommendation(self, recommendation_id: str) -> Recommendation | None:
        return self._recommendations.get(recommendation_id)

    async def list_recommendations(
        self,
        target_id: str | None = None,
        recommendation_type: str | None = None,
        priority: str | None = None,
        applied: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[Recommendation]:
        results = list(self._recommendations.values())
        # Note: Recommendation model doesn't have target_id — skip that filter
        if recommendation_type is not None:
            results = [r for r in results if r.recommendation_type == recommendation_type]
        if priority is not None:
            results = [r for r in results if r.priority.value == priority]
        if applied is not None:
            results = [r for r in results if (r.applied_at is not None) == applied]
        results.sort(key=lambda r: r.created_at, reverse=True)
        return results[offset : offset + limit]

    async def apply_recommendation(self, recommendation_id: str) -> Recommendation:
        rec = self._recommendations.get(recommendation_id)
        if rec is None:
            raise ValueError(f"Recommendation not found: {recommendation_id}")
        updated = rec.with_applied()
        self._recommendations[recommendation_id] = updated
        return updated

    async def dismiss_recommendation(self, recommendation_id: str) -> Recommendation:
        rec = self._recommendations.get(recommendation_id)
        if rec is None:
            raise ValueError(f"Recommendation not found: {recommendation_id}")
        updated = rec.with_dismissed()
        self._recommendations[recommendation_id] = updated
        return updated

    # ── Routing History ──

    async def get_routing_history(
        self,
        task_id: str | None = None,
        limit: int = 50,
    ) -> Sequence[RoutingDecision]:
        results = list(self._routing_decisions.values())
        if task_id is not None:
            results = [d for d in results if d.task_id == task_id]
        results.sort(key=lambda d: d.created_at, reverse=True)
        return results[:limit]

    # ── Policies ──

    async def get_optimization_policy(self, policy_id: str) -> OptimizationPolicy | None:
        return self._policies.get(policy_id)

    async def list_optimization_policies(self, limit: int = 50) -> Sequence[OptimizationPolicy]:
        results = sorted(
            self._policies.values(),
            key=lambda p: p.created_at,
            reverse=True,
        )
        return results[:limit]

    async def create_optimization_policy(self, policy: OptimizationPolicy) -> OptimizationPolicy:
        self._policies[policy.id] = policy
        return policy

    async def update_optimization_policy(
        self,
        policy_id: str,
        policy: OptimizationPolicy,
    ) -> OptimizationPolicy:
        existing = self._policies.get(policy_id)
        if existing is None:
            raise ValueError(f"Policy not found: {policy_id}")
        self._policies[policy_id] = policy
        return policy

    async def delete_optimization_policy(self, policy_id: str) -> bool:
        if policy_id in self._policies:
            del self._policies[policy_id]
            return True
        return False
