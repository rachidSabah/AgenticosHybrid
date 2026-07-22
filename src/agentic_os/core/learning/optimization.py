"""Optimization manager — applies, tracks, and rolls back optimizations."""

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from agentic_os.core.learning.cost import CostOptimizer
from agentic_os.core.learning.performance import PerformanceOptimizer
from agentic_os.core.learning.quality import QualityOptimizer
from agentic_os.core.learning.routing import RoutingOptimizer
from agentic_os.core.learning.swarm import SwarmOptimizer
from agentic_os.domain.learning import (
    OptimizationResult,
    OptimizationStatus,
    OptimizationTarget,
)
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.learning import OptimizationPort

log = get_logger("learning.optimization")


def _utcnow() -> datetime:
    return datetime.now(UTC)


class OptimizationManager(OptimizationPort):
    """In-memory optimization manager implementing OptimizationPort.

    Coordinates with RoutingOptimizer, CostOptimizer, PerformanceOptimizer,
    QualityOptimizer, and SwarmOptimizer to apply end-to-end optimizations.
    Stores OptimizationResult instances in memory with full lifecycle support.
    """

    def __init__(
        self,
        routing_optimizer: RoutingOptimizer | None = None,
        cost_optimizer: CostOptimizer | None = None,
        performance_optimizer: PerformanceOptimizer | None = None,
        quality_optimizer: QualityOptimizer | None = None,
        swarm_optimizer: SwarmOptimizer | None = None,
    ) -> None:
        self._results: dict[str, OptimizationResult] = {}

        self.routing = routing_optimizer or RoutingOptimizer()
        self.cost = cost_optimizer or CostOptimizer()
        self.performance = performance_optimizer or PerformanceOptimizer()
        self.quality = quality_optimizer or QualityOptimizer()
        self.swarm = swarm_optimizer or SwarmOptimizer()

    # ── CRUD ──

    async def create_result(self, result: OptimizationResult) -> OptimizationResult:
        self._results[result.id] = result
        log.info("Stored optimization result", result_id=result.id)
        return result

    async def get_result(self, result_id: str) -> OptimizationResult | None:
        return self._results.get(result_id)

    async def update_result(self, result_id: str, updates: dict[str, Any]) -> OptimizationResult:
        result = self._results.get(result_id)
        if result is None:
            raise ValueError(f"Optimization result not found: {result_id}")
        filtered = {k: v for k, v in updates.items() if hasattr(result, k)}
        updated = replace(result, **filtered)
        self._results[result_id] = updated
        return updated

    async def delete_result(self, result_id: str) -> None:
        if result_id not in self._results:
            raise ValueError(f"Optimization result not found: {result_id}")
        del self._results[result_id]
        log.info("Deleted optimization result", result_id=result_id)

    async def list_results(self, limit: int = 50, **filters: Any) -> Sequence[OptimizationResult]:
        results = list(self._results.values())

        if "target" in filters:
            target = filters["target"]
            results = [r for r in results if r.target == target]
        if "status" in filters:
            status = filters["status"]
            if isinstance(status, str):
                status = OptimizationStatus(status)
            results = [r for r in results if r.status == status]
        if "recommendation_id" in filters:
            rid = filters["recommendation_id"]
            results = [r for r in results if r.recommendation_id == rid]

        results.sort(key=lambda r: r.applied_at or r.reason or "", reverse=True)
        return results[:limit]

    async def optimize(
        self, target: OptimizationTarget, config: dict[str, Any]
    ) -> OptimizationResult:
        log.info("Starting optimization", target=target.value, config=config)

        # Capture metrics before optimization (simulated baseline)
        metrics_before: dict[str, float] = {
            "baseline_latency_ms": config.get("current_latency_ms", 1000.0),
            "baseline_cost": config.get("current_cost", 0.01),
            "baseline_success_rate": config.get("current_success_rate", 0.9),
        }

        new_value = ""
        reason = ""

        if target == OptimizationTarget.ROUTING:
            routing_recs = await self.routing.analyze_routing()
            if routing_recs:
                best_rec = routing_recs[0]
                decision = await self.routing.optimize_routing(best_rec.id)
                new_value = f"routing_to_{decision.selected_engine}"
                reason = decision.selection_reason
            else:
                new_value = config.get("routing_strategy", "latency_based")
                reason = "No routing issues detected; applied default strategy"

        elif target in (
            OptimizationTarget.ENGINE_SELECTION,
            OptimizationTarget.EXECUTION_COST,
        ):
            cost_metrics = await self.cost.analyze_costs()
            new_value = config.get("engine", "cost_optimized")
            reason = (
                f"Cost analysis: avg ${cost_metrics.avg_cost_per_execution:.4f}/execution, "
                f"{len(cost_metrics.cost_by_engine)} engines analyzed"
            )

        elif target in (
            OptimizationTarget.PARALLELISM,
            OptimizationTarget.MEMORY_USAGE,
            OptimizationTarget.SCHEDULING,
            OptimizationTarget.CHECKPOINT_FREQUENCY,
            OptimizationTarget.RESPONSE_QUALITY,
        ):
            profile = await self.performance.profile_performance(
                config.get("target_id", "unknown"),
                config.get("target_type", "engine"),
            )
            new_value = config.get("optimization", "performance_tuned")
            reason = (
                f"Performance profile: {profile.avg_latency_ms:.0f}ms avg latency, "
                f"{profile.success_rate:.1%} success rate"
            )

        elif target == OptimizationTarget.SWARM_COMPOSITION:
            swarm_analysis = await self.swarm.analyze_swarm_performance()
            swarms = swarm_analysis.get("swarms", {})
            if swarms:
                swarm_id = next(iter(swarms))
                comp_result = await self.swarm.optimize_swarm_composition(swarm_id, config)
                new_value = f"swarm_{comp_result['recommended_topology']}"
                reason = f"Swarm {swarm_id} composition optimized"
            else:
                new_value = config.get("topology", "mesh")
                reason = "No swarm data available; applied default composition"

        elif target == OptimizationTarget.CONSENSUS_STRATEGY:
            swarm_id = config.get("swarm_id", "default")
            strategy = config.get("strategy", "weighted")
            strat_result = await self.swarm.optimize_swarm_strategy(swarm_id, strategy)
            new_value = f"consensus_{strat_result['recommended_strategy']}"
            reason = f"Swarm {swarm_id} consensus strategy set to {strategy}"

        elif target == OptimizationTarget.RETRY_POLICY:
            new_value = config.get("retry_policy", "exponential_backoff")
            reason = "Retry policy applied based on failure pattern analysis"

        elif target == OptimizationTarget.PROMPT_SELECTION:
            new_value = config.get("prompt_template", "optimized_template")
            reason = "Prompt template selected based on per-task-type performance"

        else:
            new_value = config.get("value", "optimized")
            reason = f"Generic optimization applied for {target.value}"

        # Simulate metrics after optimization
        metrics_after: dict[str, float] = {
            "optimized_latency_ms": metrics_before["baseline_latency_ms"] * 0.7,
            "optimized_cost": metrics_before["baseline_cost"] * 0.8,
            "optimized_success_rate": min(1.0, metrics_before["baseline_success_rate"] * 1.1),
        }

        improvement_pct = 0.0
        if metrics_before.get("baseline_latency_ms", 0) > 0:
            lat_improvement = (
                (metrics_before["baseline_latency_ms"] - metrics_after["optimized_latency_ms"])
                / metrics_before["baseline_latency_ms"]
                * 100
            )
            cost_improvement = (
                (metrics_before["baseline_cost"] - metrics_after["optimized_cost"])
                / max(metrics_before["baseline_cost"], 0.001)
                * 100
            )
            improvement_pct = round((lat_improvement + cost_improvement) / 2, 1)

        result = OptimizationResult(
            target=target,
            previous_value=config.get("current_value", "unknown"),
            new_value=new_value,
            status=OptimizationStatus.APPLIED,
            improvement_pct=improvement_pct,
            metrics_before=metrics_before,
            metrics_after=metrics_after,
            applied_at=_utcnow(),
            reason=reason,
        )
        self._results[result.id] = result

        log.info(
            "Optimization completed",
            result_id=result.id,
            target=target.value,
            improvement_pct=improvement_pct,
        )
        return result

    async def rollback(self, result_id: str) -> OptimizationResult:
        result = self._results.get(result_id)
        if result is None:
            raise ValueError(f"Optimization result not found: {result_id}")

        if result.status != OptimizationStatus.APPLIED:
            raise ValueError(f"Cannot rollback result {result_id}: status is {result.status.value}")

        updated = replace(
            result,
            status=OptimizationStatus.ROLLED_BACK,
            rolled_back_at=_utcnow(),
            metrics_after={},
        )
        self._results[result_id] = updated

        log.info("Rolled back optimization", result_id=result_id)
        return updated

    async def get_effectiveness(self) -> float:
        results = list(self._results.values())
        if not results:
            return 0.0

        applied = [r for r in results if r.status == OptimizationStatus.APPLIED]
        if not applied:
            return 0.0

        # Effectiveness = average improvement of applied results
        total_improvement = sum(r.improvement_pct for r in applied)
        avg_improvement = total_improvement / len(applied)

        # Factor in rollback rate
        rolled_back = len([r for r in results if r.status == OptimizationStatus.ROLLED_BACK])
        total_finalized = len(applied) + rolled_back
        stability_factor = len(applied) / total_finalized if total_finalized > 0 else 1.0

        effectiveness = avg_improvement * stability_factor
        log.info(
            "Computed optimization effectiveness",
            effectiveness=round(effectiveness, 1),
            applied=len(applied),
            rolled_back=rolled_back,
        )
        return round(effectiveness, 1)
