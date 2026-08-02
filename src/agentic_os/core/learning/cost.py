"""Cost optimizer — analyzes execution costs and recommends savings."""

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from agentic_os.domain.learning import (
    CostMetrics,
    ExecutionHistory,
    OptimizationTarget,
    RecommendationStatus,
)
from agentic_os.infrastructure.logging import get_logger

log = get_logger("learning.cost")


def _utcnow() -> datetime:
    return datetime.now(UTC)


_SAVINGS_RECOMMENDATIONS: dict[str, dict[str, Any]] = {
    "engine_switch": {
        "title": "Switch to Lower-Cost Engine",
        "description": (
            "Engine '{engine}' has an average cost of ${avg_cost:.4f} per execution, "
            "which is {pct:.0f}% higher than the alternative '{alternative}'. "
            "Switching could save approximately ${savings:.2f} over the next {period}."
        ),
    },
    "batching": {
        "title": "Enable Execution Batching",
        "description": (
            "Executions for {task_type} tasks are predominantly small and frequent. "
            "Batching {count} executions per batch could reduce per-execution overhead "
            "by an estimated {pct:.0f}%."
        ),
    },
    "retry_policy": {
        "title": "Reduce Expensive Retries",
        "description": (
            "Engine '{engine}' has a {retry_count}-execution retry rate of {retry_rate:.0f}%, "
            "costing an estimated ${retry_cost:.2f}. Tighter retry limits or "
            "circuit-breaker could reduce this."
        ),
    },
}


class CostOptimizer:
    """In-memory cost optimizer that analyzes execution cost data.

    Identifies expensive engines and providers, generates cost-saving
    recommendations, and tracks cost metrics over time.
    """

    def __init__(self) -> None:
        self._execution_history: dict[str, ExecutionHistory] = {}
        self._cost_metrics_history: list[CostMetrics] = []
        self._savings_recommendations: dict[str, dict[str, Any]] = {}

    def record_execution(self, history: ExecutionHistory) -> ExecutionHistory:
        """Feed an execution record for cost analysis."""
        self._execution_history[history.id] = history
        return history

    async def track_cost(
        self, execution_id: str, cost: float, engine: str, provider: str = ""
    ) -> None:
        """Record a discrete cost data point for an execution."""
        existing = self._execution_history.get(execution_id)
        if existing is not None:
            updated = replace(existing, cost=cost, engine_name=engine)
            self._execution_history[execution_id] = updated
        log.debug("Tracked cost", execution_id=execution_id, cost=cost, engine=engine)

    async def analyze_costs(self) -> CostMetrics:
        """Analyze execution history and produce current cost metrics."""
        executions = list(self._execution_history.values())
        if not executions:
            metrics = CostMetrics(
                period_start=_utcnow(),
                period_end=_utcnow(),
            )
            self._cost_metrics_history.append(metrics)
            return metrics

        total_cost = sum(e.cost for e in executions)
        avg_cost = total_cost / len(executions) if executions else 0.0

        cost_by_engine: dict[str, float] = {}
        cost_by_provider: dict[str, float] = {}
        for e in executions:
            engine_key = e.engine_name or e.engine_type or "unknown"
            cost_by_engine[engine_key] = cost_by_engine.get(engine_key, 0.0) + e.cost
            provider_key = e.metadata.get("provider", "unknown") if e.metadata else "unknown"
            if isinstance(provider_key, str):
                cost_by_provider[provider_key] = cost_by_provider.get(provider_key, 0.0) + e.cost

        metrics = CostMetrics(
            total_cost=round(total_cost, 4),
            avg_cost_per_execution=round(avg_cost, 4),
            cost_by_engine=cost_by_engine,
            cost_by_provider=cost_by_provider,
            period_start=_utcnow(),
            period_end=_utcnow(),
        )
        self._cost_metrics_history.append(metrics)
        log.info("Cost analysis complete", total_cost=total_cost, avg_cost=avg_cost)
        return metrics

    async def recommend_cost_savings(self) -> Sequence[dict[str, Any]]:
        """Generate cost-saving recommendations based on execution data."""
        executions = list(self._execution_history.values())
        recommendations: list[dict[str, Any]] = []

        if len(executions) < 3:
            return recommendations

        # Find expensive engines and suggest cheaper alternatives
        engine_costs: dict[str, list[float]] = {}
        for e in executions:
            engine_key = e.engine_name or e.engine_type or "unknown"
            engine_costs.setdefault(engine_key, []).append(e.cost)

        if len(engine_costs) >= 2:
            avg_costs = {eng: sum(costs) / len(costs) for eng, costs in engine_costs.items()}
            sorted_engines = sorted(avg_costs, key=lambda k: avg_costs[k])
            if len(sorted_engines) >= 2:
                expensive = sorted_engines[-1]
                cheap = sorted_engines[0]
                expensive_avg = avg_costs[expensive]
                cheap_avg = avg_costs[cheap]

                if expensive_avg > cheap_avg * 1.2 and expensive_avg > 0.0:
                    pct = ((expensive_avg - cheap_avg) / expensive_avg) * 100
                    savings = (expensive_avg - cheap_avg) * len(engine_costs[expensive])
                    rec = {
                        "id": f"cost-save-{int(_utcnow().timestamp())}",
                        "target": OptimizationTarget.EXECUTION_COST.value,
                        "type": "engine_switch",
                        "title": _SAVINGS_RECOMMENDATIONS["engine_switch"]["title"],
                        "description": _SAVINGS_RECOMMENDATIONS["engine_switch"][
                            "description"
                        ].format(
                            engine=expensive,
                            avg_cost=expensive_avg,
                            pct=pct,
                            alternative=cheap,
                            savings=savings,
                            period="next 100 executions",
                        ),
                        "estimated_savings": round(savings, 2),
                        "confidence": min(0.9, 0.5 + pct / 200),
                        "current_engine": expensive,
                        "recommended_engine": cheap,
                        "status": RecommendationStatus.ACTIVE.value,
                    }
                    recommendations.append(rec)
                    self._savings_recommendations[rec["id"]] = rec
                    log.info(
                        "Cost savings opportunity identified",
                        expensive=expensive,
                        cheap=cheap,
                        savings=savings,
                    )

        # Check for high retry costs
        retry_engine_costs: dict[str, dict[str, Any]] = {}
        for e in executions:
            if e.retry_count > 0:
                engine_key = e.engine_name or e.engine_type or "unknown"
                entry = retry_engine_costs.setdefault(
                    engine_key, {"retries": 0, "cost": 0.0, "count": 0}
                )
                entry["retries"] += e.retry_count
                entry["cost"] += e.cost
                entry["count"] += 1

        for engine, data in retry_engine_costs.items():
            if data["retries"] > 5 and data["cost"] > 0.01:
                retry_rate = (data["retries"] / data["count"]) * 100
                rec = {
                    "id": f"cost-retry-{int(_utcnow().timestamp())}",
                    "target": OptimizationTarget.EXECUTION_COST.value,
                    "type": "retry_policy",
                    "title": _SAVINGS_RECOMMENDATIONS["retry_policy"]["title"],
                    "description": _SAVINGS_RECOMMENDATIONS["retry_policy"]["description"].format(
                        engine=engine,
                        retry_count=data["count"],
                        retry_rate=retry_rate,
                        retry_cost=round(data["cost"], 2),
                    ),
                    "estimated_savings": round(data["cost"] * 0.3, 2),
                    "confidence": 0.7,
                    "engine": engine,
                    "retry_rate": round(retry_rate, 1),
                    "status": RecommendationStatus.ACTIVE.value,
                }
                recommendations.append(rec)
                self._savings_recommendations[rec["id"]] = rec
                log.info("Retry cost savings identified", engine=engine, retry_rate=retry_rate)

        return recommendations

    async def get_cost_metrics(
        self, period_start: str | None = None, period_end: str | None = None
    ) -> CostMetrics:
        if not self._cost_metrics_history:
            return CostMetrics(
                period_start=_utcnow(),
                period_end=_utcnow(),
            )
        latest = self._cost_metrics_history[-1]
        return latest

    async def estimate_savings(
        self,
        current_engine: str,
        target_engine: str,
        estimated_executions: int = 1000,
    ) -> dict[str, Any]:
        """Estimate potential savings from switching engines."""
        executions = list(self._execution_history.values())
        current_costs = [
            e.cost for e in executions if (e.engine_name or e.engine_type) == current_engine
        ]
        target_costs = [
            e.cost for e in executions if (e.engine_name or e.engine_type) == target_engine
        ]

        if not current_costs or not target_costs:
            return {
                "estimated_savings": 0.0,
                "confidence": 0.0,
                "reason": "Insufficient data for estimation",
            }

        current_avg = sum(current_costs) / len(current_costs)
        target_avg = sum(target_costs) / len(target_costs)
        per_execution_savings = current_avg - target_avg

        if per_execution_savings <= 0:
            return {
                "estimated_savings": 0.0,
                "confidence": 0.0,
                "reason": "Target engine is not cheaper than current engine",
            }

        total_savings = per_execution_savings * estimated_executions
        confidence = min(
            0.95,
            0.5 + (len(current_costs) + len(target_costs)) / 200,
        )

        return {
            "estimated_savings": round(total_savings, 2),
            "per_execution_savings": round(per_execution_savings, 4),
            "confidence": round(confidence, 3),
            "current_avg_cost": round(current_avg, 4),
            "target_avg_cost": round(target_avg, 4),
            "sample_size_current": len(current_costs),
            "sample_size_target": len(target_costs),
            "estimated_executions": estimated_executions,
        }
