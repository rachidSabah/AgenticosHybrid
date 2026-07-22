"""
Learning SDK — developer-facing client for the Learning & Optimization Engine.

Provides a high-level API for recording executions, generating recommendations,
running benchmarks, managing experiments, and querying optimization results.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from agentic_os.core.learning.manager import LearningManager
from agentic_os.domain.learning import (
    Benchmark,
    Evaluation,
    ExecutionHistory,
    Experiment,
    LearningMetrics,
    LearningProfile,
    OptimizationPolicy,
    OptimizationResult,
    OptimizationTarget,
    Recommendation,
    RecommendationStatus,
)
from agentic_os.infrastructure.logging import get_logger

log = get_logger("sdk.learning")


class LearningClient:
    """High-level client for the Learning & Optimization Engine."""

    def __init__(self, manager: LearningManager) -> None:
        self._manager = manager

    async def record_execution(
        self,
        execution_id: str,
        engine_type: str,
        engine_name: str,
        duration_ms: float,
        status: str,
        cost: float = 0.0,
        retry_count: int = 0,
        error_type: str | None = None,
        **metadata: Any,
    ) -> ExecutionHistory:
        history = ExecutionHistory(
            execution_id=execution_id,
            engine_type=engine_type,
            engine_name=engine_name,
            duration_ms=duration_ms,
            status=status,
            cost=cost,
            retry_count=retry_count,
            error_type=error_type,
            metadata=metadata,
        )
        return await self._manager.record_execution(history)

    async def get_recommendations(
        self, status: RecommendationStatus | None = None, limit: int = 50
    ) -> Sequence[Recommendation]:
        return await self._manager.list_recommendations(status, limit)

    async def generate_recommendation(self, category: str, **context: Any) -> Recommendation:
        return await self._manager.generate_recommendation(category, context)

    async def run_benchmark(
        self, name: str, targets: Sequence[str], iterations: int = 10
    ) -> Benchmark:
        benchmark = Benchmark(name=name, targets=tuple(targets), iterations=iterations)
        created = await self._manager.create_benchmark(benchmark)
        return await self._manager.run_benchmark(created.id)

    async def create_experiment(
        self,
        name: str,
        experiment_type: str,
        control_config: dict[str, Any],
        treatment_config: dict[str, Any],
    ) -> Experiment:
        exp = Experiment(
            name=name,
            experiment_type=experiment_type,  # type: ignore
            control_config=control_config,
            treatment_config=treatment_config,
        )
        return await self._manager.create_experiment(exp)

    async def start_experiment(self, experiment_id: str) -> Experiment:
        return await self._manager.start_experiment(experiment_id)

    async def get_learning_metrics(self) -> LearningMetrics:
        return await self._manager.compute_learning_metrics()

    async def create_profile(self, name: str, **kwargs: Any) -> LearningProfile:
        profile = LearningProfile(name=name, **kwargs)
        return await self._manager.create_profile(profile)

    async def optimize(self, target: str, **config: Any) -> OptimizationResult:
        return await self._manager.optimize(OptimizationTarget(target), config)

    async def evaluate(self, target_id: str, target_type: str, **metrics: float) -> Evaluation:
        return await self._manager.evaluate(target_id, target_type, metrics)

    async def create_policy(self, name: str, target: str, **kwargs: Any) -> OptimizationPolicy:
        policy = OptimizationPolicy(
            name=name, target=OptimizationTarget(target) if target else None, **kwargs
        )
        return await self._manager.create_policy(policy)


__all__ = ["LearningClient"]
