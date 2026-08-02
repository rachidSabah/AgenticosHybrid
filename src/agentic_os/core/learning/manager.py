"""
LearningManager — composition root for the Learning & Optimization Engine.

Orchestrates all learning subsystems: data collection, analysis, optimization,
recommendations, benchmarks, experiments, policies, evaluation, and telemetry.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from agentic_os.core.learning.benchmark import BenchmarkManager
from agentic_os.core.learning.cost import CostOptimizer
from agentic_os.core.learning.evaluation import EvaluationEngine
from agentic_os.core.learning.experiment import ExperimentManager
from agentic_os.core.learning.history import HistoricalAnalyzer
from agentic_os.core.learning.model_selection import ModelSelectionEngine
from agentic_os.core.learning.optimization import OptimizationManager
from agentic_os.core.learning.performance import PerformanceOptimizer
from agentic_os.core.learning.policy import PolicyEngine
from agentic_os.core.learning.prompt import PromptOptimizationManager
from agentic_os.core.learning.publisher import LearningEventPublisher
from agentic_os.core.learning.quality import QualityOptimizer
from agentic_os.core.learning.recommendation import RecommendationEngine
from agentic_os.core.learning.routing import RoutingOptimizer
from agentic_os.core.learning.strategy import StrategyManager
from agentic_os.core.learning.swarm import SwarmOptimizer
from agentic_os.core.learning.telemetry import LearningTelemetry
from agentic_os.domain.learning import (
    Benchmark,
    Evaluation,
    ExecutionHistory,
    Experiment,
    LearningMetrics,
    LearningProfile,
    OptimizationPolicy,
    OptimizationRecommendation,
    OptimizationResult,
    OptimizationTarget,
    PerformanceProfile,
    Recommendation,
    RecommendationStatus,
    RoutingDecision,
)
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.event_bus import EventBus as EventBusProtocol

log = get_logger("core.learning.manager")


class LearningManager:
    """Composition root — wires and exposes the full Learning & Optimization Engine."""

    def __init__(
        self,
        bus: EventBusProtocol,
        history: HistoricalAnalyzer | None = None,
        telemetry: LearningTelemetry | None = None,
        optimization: OptimizationManager | None = None,
        benchmark: BenchmarkManager | None = None,
        evaluation: EvaluationEngine | None = None,
        recommendation: RecommendationEngine | None = None,
        experiment: ExperimentManager | None = None,
        routing: RoutingOptimizer | None = None,
        cost: CostOptimizer | None = None,
        performance: PerformanceOptimizer | None = None,
        quality: QualityOptimizer | None = None,
        swarm: SwarmOptimizer | None = None,
        prompt: PromptOptimizationManager | None = None,
        policy: PolicyEngine | None = None,
        strategy: StrategyManager | None = None,
        model_selection: ModelSelectionEngine | None = None,
        publisher: LearningEventPublisher | None = None,
    ) -> None:
        self._bus = bus
        self._history = history or HistoricalAnalyzer()
        self._telemetry = telemetry or LearningTelemetry()
        self._optimization = optimization or OptimizationManager()
        self._benchmark = benchmark or BenchmarkManager()
        self._evaluation = evaluation or EvaluationEngine()
        self._recommendation = recommendation or RecommendationEngine()
        self._experiment = experiment or ExperimentManager()
        self._routing = routing or RoutingOptimizer()
        self._cost = cost or CostOptimizer()
        self._performance = performance or PerformanceOptimizer()
        self._quality = quality or QualityOptimizer()
        self._swarm = swarm or SwarmOptimizer()
        self._prompt = prompt or PromptOptimizationManager()
        self._policy = policy or PolicyEngine()
        self._strategy = strategy or StrategyManager()
        self._model_selection = model_selection or ModelSelectionEngine()
        self._publisher = publisher or LearningEventPublisher(bus)
        self._profiles: dict[str, LearningProfile] = {}
        self._initialized = False

    @property
    def publisher(self) -> LearningEventPublisher:
        return self._publisher

    @property
    def history(self) -> HistoricalAnalyzer:
        return self._history

    @property
    def telemetry(self) -> LearningTelemetry:
        return self._telemetry

    @property
    def optimization(self) -> OptimizationManager:
        return self._optimization

    @property
    def benchmark(self) -> BenchmarkManager:
        return self._benchmark

    @property
    def evaluation(self) -> EvaluationEngine:
        return self._evaluation

    @property
    def recommendation(self) -> RecommendationEngine:
        return self._recommendation

    @property
    def experiment(self) -> ExperimentManager:
        return self._experiment

    @property
    def routing(self) -> RoutingOptimizer:
        return self._routing

    @property
    def cost(self) -> CostOptimizer:
        return self._cost

    @property
    def performance(self) -> PerformanceOptimizer:
        return self._performance

    @property
    def quality(self) -> QualityOptimizer:
        return self._quality

    @property
    def swarm(self) -> SwarmOptimizer:
        return self._swarm

    @property
    def prompt(self) -> PromptOptimizationManager:
        return self._prompt

    @property
    def policy(self) -> PolicyEngine:
        return self._policy

    @property
    def strategy(self) -> StrategyManager:
        return self._strategy

    @property
    def model_selection(self) -> ModelSelectionEngine:
        return self._model_selection

    async def start(self) -> None:
        self._initialized = True
        log.info("Learning & Optimization Engine started")

    async def stop(self) -> None:
        self._initialized = False
        log.info("Learning & Optimization Engine stopped")

    # ── Profile management ──

    async def create_profile(self, profile: LearningProfile) -> LearningProfile:
        self._profiles[profile.id] = profile
        await self._publisher.publish_learning_started(profile.id)
        log.info("Created learning profile", profile_id=profile.id)
        return profile

    async def get_profile(self, profile_id: str) -> LearningProfile | None:
        return self._profiles.get(profile_id)

    async def list_profiles(self) -> Sequence[LearningProfile]:
        return list(self._profiles.values())

    async def update_profile(self, profile: LearningProfile) -> LearningProfile:
        self._profiles[profile.id] = profile
        await self._publisher.publish_learning_completed(profile.id)
        return profile

    async def delete_profile(self, profile_id: str) -> None:
        self._profiles.pop(profile_id, None)

    # ── Execution recording ──

    async def record_execution(self, history: ExecutionHistory) -> ExecutionHistory:
        self._history.record_execution(history)
        await self._telemetry.ingest_execution_metrics(
            {
                "execution_id": history.execution_id,
                "duration_ms": history.duration_ms,
                "status": history.status,
                "cost": history.cost,
                "retry_count": history.retry_count,
                "error_type": history.error_type,
            }
        )
        return history

    async def analyze_executions(self, history_ids: tuple[str, ...]) -> Any:
        return await self._history.analyze_executions(history_ids)

    async def compute_learning_metrics(
        self, period_start: str | None = None, period_end: str | None = None
    ) -> LearningMetrics:
        stats = await self._history.compute_trends()
        stats_dict = stats if isinstance(stats, dict) else {}
        total = stats_dict.get("total_count", 0)
        success = stats_dict.get("success_count", 0)
        return LearningMetrics(
            total_executions=total,
            total_optimizations=len(self._optimization._results),
            total_recommendations=len(self._recommendation._recommendations),
            success_rate=success / max(total, 1),
        )

    # ── Optimization ──

    async def optimize(
        self, target: OptimizationTarget, config: dict[str, Any]
    ) -> OptimizationResult:
        result = await self._optimization.optimize(target, config)
        await self._publisher.publish_optimization(result.id, target.value, result.status.value)
        return result

    async def get_optimization_result(self, result_id: str) -> OptimizationResult | None:
        return await self._optimization.get_result(result_id)

    async def list_optimization_results(
        self, limit: int = 50, **filters: Any
    ) -> Sequence[OptimizationResult]:
        return await self._optimization.list_results(limit, **filters)

    async def rollback_optimization(self, result_id: str) -> OptimizationResult:
        return await self._optimization.rollback(result_id)

    # ── Benchmarks ──

    async def create_benchmark(self, benchmark: Benchmark) -> Benchmark:
        created = await self._benchmark.create_benchmark(benchmark)
        await self._publisher.publish_benchmark(created.id, "created")
        return created

    async def run_benchmark(self, benchmark_id: str) -> Benchmark:
        result = await self._benchmark.run_benchmark(benchmark_id)
        await self._publisher.publish_benchmark(benchmark_id, "completed")
        return result

    async def compare_benchmark(self, benchmark_id: str) -> Benchmark:
        return await self._benchmark.compare(benchmark_id)

    async def list_benchmarks(self) -> Sequence[Benchmark]:
        return await self._benchmark.list_benchmarks()

    async def get_benchmark(self, benchmark_id: str) -> Benchmark | None:
        return await self._benchmark.get_benchmark(benchmark_id)

    async def delete_benchmark(self, benchmark_id: str) -> None:
        await self._benchmark.delete_benchmark(benchmark_id)

    # ── Evaluations ──

    async def evaluate(
        self, target_id: str, target_type: str, metrics: dict[str, float]
    ) -> Evaluation:
        result = await self._evaluation.evaluate(target_id, target_type, metrics)
        await self._publisher.publish_evaluation(result.id, target_type, result.score)
        return result

    async def list_evaluations(self, target_id: str) -> Sequence[Evaluation]:
        return await self._evaluation.list_evaluations(target_id)

    # ── Recommendations ──

    async def generate_recommendation(
        self, category: str, context: dict[str, Any]
    ) -> Recommendation:
        rec = await self._recommendation.generate_recommendation(category, context)
        await self._publisher.publish_recommendation(rec.id, category, rec.confidence)
        return rec

    async def list_recommendations(
        self, status: RecommendationStatus | None = None, limit: int = 50
    ) -> Sequence[Recommendation]:
        return await self._recommendation.list_recommendations(status, limit)

    async def apply_recommendation(self, recommendation_id: str) -> Recommendation:
        return await self._recommendation.apply_recommendation(recommendation_id)

    async def dismiss_recommendation(self, recommendation_id: str) -> Recommendation:
        return await self._recommendation.dismiss_recommendation(recommendation_id)

    # ── Experiments ──

    async def create_experiment(self, experiment: Experiment) -> Experiment:
        created = await self._experiment.create_experiment(experiment)
        await self._publisher.publish_experiment(created.id, "created")
        return created

    async def start_experiment(self, experiment_id: str) -> Experiment:
        return await self._experiment.start_experiment(experiment_id)

    async def complete_experiment(self, experiment_id: str) -> Experiment:
        result = await self._experiment.complete_experiment(experiment_id)
        await self._publisher.publish_experiment(experiment_id, "completed")
        return result

    async def list_experiments(self) -> Sequence[Experiment]:
        return await self._experiment.list_experiments()

    async def get_experiment(self, experiment_id: str) -> Experiment | None:
        return await self._experiment.get_experiment(experiment_id)

    # ── Routing ──

    async def analyze_routing(self) -> Sequence[OptimizationRecommendation]:
        return await self._routing.analyze_routing()

    async def optimize_routing(self, recommendation_id: str) -> RoutingDecision:
        return await self._routing.optimize_routing(recommendation_id)

    async def get_routing_stats(self) -> dict[str, Any]:
        return await self._routing.get_routing_stats()

    # ── Performance ──

    async def profile_performance(self, target_id: str, target_type: str) -> PerformanceProfile:
        return await self._performance.profile_performance(target_id, target_type)

    async def get_performance_trends(self) -> dict[str, Any]:
        return await self._performance.get_performance_trends()

    # ── Cost ──

    async def get_cost_metrics(
        self, period_start: str | None = None, period_end: str | None = None
    ) -> Any:
        return await self._telemetry.get_cost_metrics(period_start, period_end)

    # ── Quality ──

    async def get_quality_metrics(
        self, period_start: str | None = None, period_end: str | None = None
    ) -> Any:
        return await self._telemetry.get_quality_metrics(period_start, period_end)

    # ── Failure ──

    async def get_failure_analysis(
        self, period_start: str | None = None, period_end: str | None = None
    ) -> Any:
        return await self._telemetry.get_failure_analysis(period_start, period_end)

    # ── Policies ──

    async def create_policy(self, policy: OptimizationPolicy) -> OptimizationPolicy:
        created = await self._policy.create_policy(policy)
        await self._publisher.publish_policy(created.id, "created")
        return created

    async def list_policies(self) -> Sequence[OptimizationPolicy]:
        return await self._policy.list_policies()

    async def update_policy(self, policy: OptimizationPolicy) -> OptimizationPolicy:
        return await self._policy.update_policy(policy)

    async def delete_policy(self, policy_id: str) -> None:
        await self._policy.delete_policy(policy_id)

    async def check_policy(self, target: OptimizationTarget, context: dict[str, Any]) -> bool:
        return await self._policy.check_policy(target, context)


__all__ = ["LearningManager"]
