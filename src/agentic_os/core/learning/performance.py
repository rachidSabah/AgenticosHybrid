"""Performance optimizer — profiles, analyzes, and optimizes execution performance."""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from agentic_os.domain.learning import (
    ExecutionHistory,
    OptimizationRecommendation,
    OptimizationResult,
    OptimizationStatus,
    OptimizationTarget,
    PerformanceProfile,
    RecommendationStatus,
)
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.learning import PerformanceOptimizationPort

log = get_logger("learning.performance")


def _utcnow() -> datetime:
    return datetime.now(UTC)


class PerformanceOptimizer(PerformanceOptimizationPort):
    """In-memory performance optimizer implementing PerformanceOptimizationPort.

    Profiles execution targets, analyzes performance data to identify
    bottlenecks, applies optimizations, and tracks performance trends.
    """

    def __init__(self) -> None:
        self._execution_history: dict[str, ExecutionHistory] = {}
        self._performance_profiles: dict[str, PerformanceProfile] = {}
        self._optimization_recommendations: dict[str, OptimizationRecommendation] = {}
        self._optimization_results: dict[str, OptimizationResult] = {}
        self._trend_data: dict[str, list[dict[str, Any]]] = {}

    def record_execution(self, history: ExecutionHistory) -> ExecutionHistory:
        """Feed an execution record for performance analysis."""
        self._execution_history[history.id] = history
        # Record trend data point
        key = f"{history.engine_type}:{history.task_type}"
        self._trend_data.setdefault(key, []).append(
            {
                "timestamp": history.executed_at.isoformat(),
                "duration_ms": history.duration_ms,
                "cost": history.cost,
                "status": history.status,
                "execution_id": history.execution_id,
            }
        )
        return history

    async def profile_performance(self, target_id: str, target_type: str) -> PerformanceProfile:
        executions = [
            e
            for e in self._execution_history.values()
            if (
                target_type == "engine"
                and (e.engine_name == target_id or e.engine_type == target_id)
            )
            or (target_type == "execution" and e.execution_id == target_id)
            or (target_type == "task" and e.task_type == target_id)
        ]

        if not executions:
            profile = PerformanceProfile(
                target_id=target_id,
                target_type=target_type,
            )
            self._performance_profiles[profile.id] = profile
            return profile

        latencies = [e.duration_ms for e in executions if e.duration_ms > 0]
        costs = [e.cost for e in executions]
        successes = [1 for e in executions if e.status == "completed"]
        total_count = len(executions)

        if latencies:
            sorted_latencies = sorted(latencies)
            avg_latency = sum(latencies) / len(latencies)
            p50 = _percentile(sorted_latencies, 50)
            p95 = _percentile(sorted_latencies, 95)
            p99 = _percentile(sorted_latencies, 99)
        else:
            avg_latency = 0.0
            p50 = 0.0
            p95 = 0.0
            p99 = 0.0

        avg_cost = sum(costs) / len(costs) if costs else 0.0
        success_rate = len(successes) / total_count if total_count > 0 else 0.0

        profile = PerformanceProfile(
            target_id=target_id,
            target_type=target_type,
            avg_latency_ms=round(avg_latency, 1),
            p50_latency_ms=round(p50, 1),
            p95_latency_ms=round(p95, 1),
            p99_latency_ms=round(p99, 1),
            avg_cost=round(avg_cost, 4),
            success_rate=round(success_rate, 3),
            throughput=round(total_count / 3600, 2) if total_count > 0 else 0.0,
            sample_count=total_count,
        )
        self._performance_profiles[profile.id] = profile
        log.info(
            "Profiled performance",
            target_id=target_id,
            target_type=target_type,
            avg_latency=avg_latency,
            sample_count=total_count,
        )
        return profile

    async def analyze_performance(self) -> Sequence[OptimizationRecommendation]:
        recommendations: list[OptimizationRecommendation] = []

        for profile in self._performance_profiles.values():
            if profile.sample_count < 3:
                continue

            # High latency bottleneck
            if profile.avg_latency_ms > 2000:
                rec = OptimizationRecommendation(
                    target=OptimizationTarget.PARALLELISM,
                    current_value=f"avg_latency={profile.avg_latency_ms:.0f}ms",
                    recommended_value="increase parallelism or upgrade engine",
                    confidence=0.7,
                    supporting_evidence=(
                        f"Target {profile.target_id} ({profile.target_type}) has "
                        f"average latency {profile.avg_latency_ms:.0f}ms "
                        f"(p95: {profile.p95_latency_ms:.0f}ms, "
                        f"p99: {profile.p99_latency_ms:.0f}ms). "
                        f"Sample size: {profile.sample_count}."
                    ),
                    historical_data={
                        "target_id": profile.target_id,
                        "target_type": profile.target_type,
                        "avg_latency_ms": profile.avg_latency_ms,
                        "p95_latency_ms": profile.p95_latency_ms,
                        "p99_latency_ms": profile.p99_latency_ms,
                    },
                    alternatives=(
                        "scale horizontally",
                        "optimize engine configuration",
                        "reduce task complexity",
                    ),
                    estimated_improvement=min(
                        80.0, (profile.avg_latency_ms - 500.0) / profile.avg_latency_ms * 100
                    ),
                    source="performance_optimizer",
                )
                self._optimization_recommendations[rec.id] = rec
                recommendations.append(rec)
                log.info(
                    "High latency detected",
                    target_id=profile.target_id,
                    avg_latency=profile.avg_latency_ms,
                    rec_id=rec.id,
                )

            # Low success rate
            if profile.success_rate < 0.8:
                rec = OptimizationRecommendation(
                    target=OptimizationTarget.RESPONSE_QUALITY,
                    current_value=f"success_rate={profile.success_rate:.1%}",
                    recommended_value=f"improve reliability for {profile.target_id}",
                    confidence=0.75,
                    supporting_evidence=(
                        f"Target {profile.target_id} has success rate {profile.success_rate:.1%} "
                        f"({profile.sample_count} samples). Below 80% threshold."
                    ),
                    historical_data={
                        "target_id": profile.target_id,
                        "target_type": profile.target_type,
                        "success_rate": profile.success_rate,
                        "sample_count": profile.sample_count,
                    },
                    alternatives=(
                        "implement retry logic",
                        "increase timeout",
                        "switch to more reliable engine",
                    ),
                    estimated_improvement=round((0.95 - profile.success_rate) * 100, 1),
                    source="performance_optimizer",
                )
                self._optimization_recommendations[rec.id] = rec
                recommendations.append(rec)
                log.info(
                    "Low success rate detected",
                    target_id=profile.target_id,
                    success_rate=profile.success_rate,
                    rec_id=rec.id,
                )

        return recommendations

    async def optimize_performance(self, recommendation_id: str) -> OptimizationResult:
        rec = self._optimization_recommendations.get(recommendation_id)
        if rec is None:
            raise ValueError(f"Optimization recommendation not found: {recommendation_id}")

        # Create an optimization result from the recommendation
        result = OptimizationResult(
            recommendation_id=rec.id,
            target=rec.target,
            previous_value=rec.current_value,
            new_value=rec.recommended_value,
            status=OptimizationStatus.APPLIED,
            improvement_pct=rec.estimated_improvement,
            metrics_before=dict(rec.historical_data),
            metrics_after={},
            applied_at=_utcnow(),
            reason=rec.supporting_evidence,
        )
        self._optimization_results[result.id] = result

        # Mark recommendation applied
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
            "Performance optimization applied",
            rec_id=recommendation_id,
            result_id=result.id,
            target=rec.target.value if rec.target else None,
        )
        return result

    async def get_performance_trends(self) -> dict[str, Any]:
        trends: dict[str, Any] = {}
        for key, points in self._trend_data.items():
            sorted_points = sorted(points, key=lambda p: p["timestamp"])
            durations = [p["duration_ms"] for p in sorted_points if p["duration_ms"] > 0]
            trends[key] = {
                "data_points": len(sorted_points),
                "avg_latency_ms": round(sum(durations) / len(durations), 1) if durations else 0.0,
                "min_latency_ms": round(min(durations), 1) if durations else 0.0,
                "max_latency_ms": round(max(durations), 1) if durations else 0.0,
                "recent_trend": sorted_points[-10:] if len(sorted_points) >= 10 else sorted_points,
            }
        return {
            "trends": trends,
            "total_profiles": len(self._performance_profiles),
            "total_recommendations": len(self._optimization_recommendations),
            "total_optimizations": len(self._optimization_results),
        }


def _percentile(sorted_data: list[float], percentile: int) -> float:
    """Compute the Nth percentile from a sorted list of values."""
    if not sorted_data:
        return 0.0
    k = (len(sorted_data) - 1) * percentile / 100.0
    f = int(k)
    c = f + 1
    if c >= len(sorted_data):
        return sorted_data[-1]
    return sorted_data[f] + (k - f) * (sorted_data[c] - sorted_data[f])
