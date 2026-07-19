"""Learning Manager — main Phase 5 composition root.

Wires together all learning & optimization subsystems:

- **KnowledgeBase** — store and query learned patterns and experiences
- **AnalyticsEngine** — aggregate performance views, trends, capability scores
- **BenchmarkEngine** — run benchmarks, measure scores, compare engines
- **PredictionEngine** — predict execution outcomes from historical data
- **OptimizationEngine** — analyze performance, generate recommendations
- **LearningEventPublisher** — bridge learning events onto the EventBus

The manager is the entry point for the API layer and kernel integration.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from agentic_os.core.learning.analytics import AnalyticsEngine
from agentic_os.core.learning.benchmark import BenchmarkEngine
from agentic_os.core.learning.knowledge import KnowledgeBase
from agentic_os.core.learning.optimizer import OptimizationEngine
from agentic_os.core.learning.predictor import PredictionEngine
from agentic_os.core.learning.publisher import LearningEventPublisher
from agentic_os.domain.learning import (
    BenchmarkRecord,
    CapabilityScore,
    EnginePerformance,
    ExecutionHistory,
    ExecutionOutcome,
    ExecutionProfile,
    ExperienceRecord,
    FailurePattern,
    KnowledgePattern,
    LearningSnapshot,
    LearningStatistics,
    OptimizationPolicy,
    OptimizationRecommendation,
    PerformanceTrend,
    Prediction,
    Recommendation,
    RecoveryPattern,
    RoutingDecision,
    SwarmPerformance,
    WorkflowPerformance,
)
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.event_bus import EventBus

log = get_logger("learning.manager")


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _maybe_parse_dt(value: Any) -> datetime | None:
    """Parse an ISO datetime string (or return a datetime unchanged)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    return _utcnow()


@dataclass
class LearningManager:
    """Main learning & optimization composition root.

    Usage::

        manager = LearningManager(bus=event_bus)
        await manager.start()

        execution = ExecutionHistory(id="ex-1", target_id="engine-1", ...)
        await manager.record_execution(execution)

        pred = await manager.predict_duration("engine-1", "engine")
        recs = await manager.analyze_performance("engine-1", "engine")

        await manager.stop()
    """

    bus: EventBus

    # Subsystems (built by ``start()`` unless injected)
    knowledge_base: KnowledgeBase | None = None
    analytics_engine: AnalyticsEngine | None = None
    benchmark_engine: BenchmarkEngine | None = None
    prediction_engine: PredictionEngine | None = None
    optimization_engine: OptimizationEngine | None = None
    publisher: LearningEventPublisher | None = None

    # Internal state
    _running: bool = field(default=False, repr=False)
    _started_at: datetime | None = field(default=None, repr=False)

    # ── Lifecycle ──

    async def start(self) -> None:
        """Start the learning engine and build all subsystems."""
        if self._running:
            log.warning("LearningManager already running")
            return

        self._build_subsystems()
        self._started_at = _utcnow()
        self._running = True

        log.info(
            "Learning & Optimization Engine started",
            subsystems=[
                "knowledge_base",
                "analytics_engine",
                "benchmark_engine",
                "prediction_engine",
                "optimization_engine",
            ],
        )

    async def stop(self) -> None:
        """Stop the learning engine."""
        self._running = False
        duration = (_utcnow() - self._started_at).total_seconds() if self._started_at else 0.0
        log.info("Learning & Optimization Engine stopped", uptime_seconds=duration)

    def _build_subsystems(self) -> None:
        """Build default subsystems if not already injected."""
        if self.knowledge_base is None:
            self.knowledge_base = KnowledgeBase()
        if self.analytics_engine is None:
            self.analytics_engine = AnalyticsEngine()
        if self.benchmark_engine is None:
            self.benchmark_engine = BenchmarkEngine()
        if self.prediction_engine is None:
            self.prediction_engine = PredictionEngine()
        if self.optimization_engine is None:
            self.optimization_engine = OptimizationEngine()
        if self.publisher is None:
            self.publisher = LearningEventPublisher(self.bus)

    # ── Convenience property access ──

    @property
    def kb(self) -> KnowledgeBase:
        assert self.knowledge_base is not None
        return self.knowledge_base

    @property
    def analytics(self) -> AnalyticsEngine:
        assert self.analytics_engine is not None
        return self.analytics_engine

    @property
    def benchmark(self) -> BenchmarkEngine:
        assert self.benchmark_engine is not None
        return self.benchmark_engine

    @property
    def predictor(self) -> PredictionEngine:
        assert self.prediction_engine is not None
        return self.prediction_engine

    @property
    def optimizer(self) -> OptimizationEngine:
        assert self.optimization_engine is not None
        return self.optimization_engine

    # ======================================================================
    # LearningEnginePort — record_execution, detect_patterns, manage knowledge
    # ======================================================================

    async def record_execution(self, execution: ExecutionHistory) -> ExecutionHistory:
        """Record an execution and propagate to all subsystems."""
        assert self.knowledge_base is not None
        assert self.analytics_engine is not None
        assert self.prediction_engine is not None
        assert self.publisher is not None

        # Store in knowledge base as an experience record
        experience = ExperienceRecord(
            id=execution.id,
            experience_type="execution",
            source=execution.target_type,
            observation=execution.to_dict(),
            outcome=execution.outcome.value,
            reward=1.0 if execution.outcome.value == "success" else -1.0,
            metadata=execution.metadata,
        )
        await self.knowledge_base.store_experience(experience)

        # Update analytics
        self.analytics_engine.record_execution(execution)
        self.predictor.ingest_execution(execution)

        # Publish event
        await self.publisher.publish_execution_recorded(
            execution_id=execution.id,
            target_id=execution.target_id,
            target_type=execution.target_type,
            outcome=execution.outcome.value,
            duration_ms=execution.duration_ms,
        )

        return execution

    async def get_execution(self, execution_id: str) -> ExecutionHistory | None:
        assert self.knowledge_base is not None
        exps = await self.knowledge_base.query_experiences({"id": execution_id}, limit=1)
        if not exps:
            return None
        return ExecutionHistory(
            id=exps[0].id,
            target_id=exps[0].observation.get("target_id", ""),
            target_type=exps[0].observation.get("target_type", ""),
            outcome=ExecutionOutcome(exps[0].outcome),
            duration_ms=exps[0].observation.get("duration_ms", 0.0),
            cpu_percent=exps[0].observation.get("cpu_percent", 0.0),
            memory_mb=exps[0].observation.get("memory_mb", 0.0),
            token_count=exps[0].observation.get("token_count", 0),
            cost=exps[0].observation.get("cost", 0.0),
            error=exps[0].observation.get("error"),
            metadata=exps[0].observation.get("metadata", {}),
            started_at=_maybe_parse_dt(exps[0].observation.get("started_at")) or _utcnow(),
            completed_at=_maybe_parse_dt(exps[0].observation.get("completed_at")),
        )

    async def list_executions(
        self,
        target_id: str | None = None,
        target_type: str | None = None,
        outcome: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[ExecutionHistory]:
        assert self.knowledge_base is not None
        # Fetch all experiences; target_id lives in observation, not on the model
        exps = await self.knowledge_base.query_experiences({}, limit=limit + offset)
        results: list[ExecutionHistory] = []
        for exp in exps[offset:]:
            obs = exp.observation
            if target_id is not None and obs.get("target_id") != target_id:
                continue
            if target_type is not None and obs.get("target_type") != target_type:
                continue
            if outcome is not None and exp.outcome != outcome:
                continue
            results.append(
                ExecutionHistory(
                    id=exp.id,
                    target_id=obs.get("target_id", ""),
                    target_type=obs.get("target_type", ""),
                    outcome=ExecutionOutcome(exp.outcome),
                    duration_ms=obs.get("duration_ms", 0.0),
                    cpu_percent=obs.get("cpu_percent", 0.0),
                    memory_mb=obs.get("memory_mb", 0.0),
                    token_count=obs.get("token_count", 0),
                    cost=obs.get("cost", 0.0),
                    error=obs.get("error"),
                    metadata=obs.get("metadata", {}),
                    started_at=_maybe_parse_dt(obs.get("started_at")) or _utcnow(),
                    completed_at=_maybe_parse_dt(obs.get("completed_at")),
                )
            )
            if len(results) >= limit:
                break
        return results

    async def get_execution_profile(
        self,
        target_id: str,
        target_type: str,
        window_hours: int = 24,
    ) -> ExecutionProfile:
        assert self.analytics_engine is not None
        # Compute from stored executions
        engine_perf = await self.analytics_engine.get_engine_performance(target_id)
        if engine_perf is None:
            return ExecutionProfile(
                target_id=target_id,
                target_type=target_type,
                window_hours=window_hours,
            )
        return ExecutionProfile(
            target_id=target_id,
            target_type=target_type,
            window_hours=window_hours,
            total_executions=engine_perf.total_executions,
            success_count=engine_perf.success_count,
            failure_count=engine_perf.failure_count,
            avg_duration_ms=engine_perf.avg_latency_ms,
            avg_cpu_percent=engine_perf.avg_cpu_percent,
            avg_memory_mb=engine_perf.avg_memory_mb,
            avg_cost=engine_perf.avg_cost,
        )

    async def detect_failure_patterns(
        self,
        target_id: str | None = None,
        min_frequency: int = 2,
    ) -> Sequence[FailurePattern]:
        return []  # Placeholder — will be implemented with real pattern detection

    async def get_failure_pattern(self, pattern_id: str) -> FailurePattern | None:
        return None

    async def list_failure_patterns(
        self,
        target_type: str | None = None,
        pattern_type: str | None = None,
        limit: int = 50,
    ) -> Sequence[FailurePattern]:
        return []

    async def detect_recovery_patterns(
        self,
        failure_pattern_id: str | None = None,
    ) -> Sequence[RecoveryPattern]:
        return []

    async def get_recovery_pattern(self, pattern_id: str) -> RecoveryPattern | None:
        return None

    async def list_recovery_patterns(
        self,
        strategy: str | None = None,
        limit: int = 50,
    ) -> Sequence[RecoveryPattern]:
        return []

    async def record_experience(self, experience: Any) -> Any:
        assert self.knowledge_base is not None
        return await self.knowledge_base.store_experience(experience)

    async def extract_knowledge(
        self,
        pattern_type: str | None = None,
        min_confidence: float = 0.5,
    ) -> Sequence[KnowledgePattern]:
        assert self.knowledge_base is not None
        return await self.knowledge_base.query_patterns(
            {"pattern_type": pattern_type} if pattern_type else {},
            min_confidence=min_confidence,
        )

    async def get_knowledge_pattern(self, pattern_id: str) -> KnowledgePattern | None:
        assert self.knowledge_base is not None
        return await self.knowledge_base.get_pattern(pattern_id)

    async def list_knowledge_patterns(
        self,
        pattern_type: str | None = None,
        min_confidence: float = 0.0,
        limit: int = 50,
    ) -> Sequence[KnowledgePattern]:
        assert self.knowledge_base is not None
        return await self.knowledge_base.query_patterns(
            {"pattern_type": pattern_type} if pattern_type else {},
            min_confidence=min_confidence,
            limit=limit,
        )

    async def clear_history(self, older_than_hours: int = 0) -> int:
        assert self.knowledge_base is not None
        return await self.knowledge_base.prune(
            older_than_days=max(1, older_than_hours // 24),
        )

    # ======================================================================
    # OptimizerPort — analyze performance, generate recommendations, route
    # ======================================================================

    async def analyze_performance(
        self,
        target_id: str,
        target_type: str,
    ) -> Sequence[OptimizationRecommendation]:
        assert self.optimization_engine is not None
        assert self.analytics_engine is not None

        # Feed current engine data
        perf = await self.analytics_engine.get_engine_performance(target_id)
        if perf is not None:
            self.optimization_engine.set_engine_performance([perf])

        recs = await self.optimization_engine.analyze_performance(target_id, target_type)
        assert self.publisher is not None
        for rec in recs:
            await self.publisher.publish_recommendation_generated(
                recommendation_id=rec.id,
                target_id=target_id,
                recommendation_type=rec.recommendation_type,
                priority=rec.priority.value,
                title=rec.title,
            )
        return recs

    async def optimize_routing(
        self,
        task_id: str,
        required_capabilities: Sequence[str],
        available_engines: Sequence[str],
    ) -> RoutingDecision:
        assert self.optimization_engine is not None
        decision = await self.optimization_engine.optimize_routing(
            task_id,
            required_capabilities,
            available_engines,
        )
        assert self.publisher is not None
        await self.publisher.publish_routing_decision(
            decision_id=decision.id,
            task_id=task_id,
            selected_engine_id=decision.selected_engine_id,
            confidence=decision.confidence,
        )
        return decision

    async def generate_recommendations(
        self,
        target_id: str,
        target_type: str,
        limit: int = 10,
    ) -> Sequence[Recommendation]:
        assert self.optimization_engine is not None
        assert self.analytics_engine is not None

        # Feed current engine data (same pattern as analyze_performance)
        perf = await self.analytics_engine.get_engine_performance(target_id)
        if perf is not None:
            self.optimization_engine.set_engine_performance([perf])

        return await self.optimization_engine.generate_recommendations(
            target_id,
            target_type,
            limit,
        )

    async def get_recommendation(self, recommendation_id: str) -> Recommendation | None:
        assert self.optimization_engine is not None
        return await self.optimization_engine.get_recommendation(recommendation_id)

    async def list_recommendations(
        self,
        target_id: str | None = None,
        recommendation_type: str | None = None,
        priority: str | None = None,
        applied: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[Recommendation]:
        assert self.optimization_engine is not None
        return await self.optimization_engine.list_recommendations(
            target_id=target_id,
            recommendation_type=recommendation_type,
            priority=priority,
            applied=applied,
            limit=limit,
            offset=offset,
        )

    async def apply_recommendation(self, recommendation_id: str) -> Recommendation:
        assert self.optimization_engine is not None
        rec = await self.optimization_engine.apply_recommendation(recommendation_id)
        assert self.publisher is not None
        await self.publisher.publish_recommendation_applied(
            recommendation_id=rec.id,
            target_id=rec.metadata.get("target_id", "unknown"),
        )
        return rec

    async def dismiss_recommendation(self, recommendation_id: str) -> Recommendation:
        assert self.optimization_engine is not None
        return await self.optimization_engine.dismiss_recommendation(recommendation_id)

    async def get_routing_history(
        self,
        task_id: str | None = None,
        limit: int = 50,
    ) -> Sequence[RoutingDecision]:
        assert self.optimization_engine is not None
        return await self.optimization_engine.get_routing_history(task_id, limit)

    async def get_optimization_policy(self, policy_id: str) -> OptimizationPolicy | None:
        assert self.optimization_engine is not None
        return await self.optimization_engine.get_optimization_policy(policy_id)

    async def list_optimization_policies(
        self,
        limit: int = 50,
    ) -> Sequence[OptimizationPolicy]:
        assert self.optimization_engine is not None
        return await self.optimization_engine.list_optimization_policies(limit)

    async def create_optimization_policy(self, policy: OptimizationPolicy) -> OptimizationPolicy:
        assert self.optimization_engine is not None
        return await self.optimization_engine.create_optimization_policy(policy)

    async def update_optimization_policy(
        self,
        policy_id: str,
        policy: OptimizationPolicy,
    ) -> OptimizationPolicy:
        assert self.optimization_engine is not None
        return await self.optimization_engine.update_optimization_policy(policy_id, policy)

    async def delete_optimization_policy(self, policy_id: str) -> bool:
        assert self.optimization_engine is not None
        return await self.optimization_engine.delete_optimization_policy(policy_id)

    # ======================================================================
    # PredictorPort — predict execution outcomes
    # ======================================================================

    async def predict_execution(
        self,
        target_id: str,
        target_type: str,
        features: dict[str, Any] | None = None,
    ) -> Prediction:
        assert self.prediction_engine is not None
        pred = await self.prediction_engine.predict_execution(target_id, target_type, features)
        assert self.publisher is not None
        await self.publisher.publish_prediction_made(
            prediction_id=pred.id,
            target_id=target_id,
            prediction_type=pred.prediction_type,
            predicted_value=pred.predicted_value,
            confidence=pred.confidence,
        )
        return pred

    async def predict_duration(
        self,
        target_id: str,
        target_type: str,
        features: dict[str, Any] | None = None,
    ) -> Prediction:
        assert self.prediction_engine is not None
        return await self.prediction_engine.predict_duration(target_id, target_type, features)

    async def predict_cost(
        self,
        target_id: str,
        target_type: str,
        features: dict[str, Any] | None = None,
    ) -> Prediction:
        assert self.prediction_engine is not None
        return await self.prediction_engine.predict_cost(target_id, target_type, features)

    async def predict_success_probability(
        self,
        target_id: str,
        target_type: str,
        features: dict[str, Any] | None = None,
    ) -> Prediction:
        assert self.prediction_engine is not None
        return await self.prediction_engine.predict_success_probability(
            target_id,
            target_type,
            features,
        )

    async def predict_resource_usage(
        self,
        target_id: str,
        target_type: str,
        features: dict[str, Any] | None = None,
    ) -> Prediction:
        assert self.prediction_engine is not None
        return await self.prediction_engine.predict_resource_usage(
            target_id,
            target_type,
            features,
        )

    async def get_prediction(self, prediction_id: str) -> Prediction | None:
        assert self.prediction_engine is not None
        return await self.prediction_engine.get_prediction(prediction_id)

    async def list_predictions(
        self,
        target_id: str | None = None,
        prediction_type: str | None = None,
        limit: int = 50,
    ) -> Sequence[Prediction]:
        assert self.prediction_engine is not None
        return await self.prediction_engine.list_predictions(
            target_id=target_id,
            prediction_type=prediction_type,
            limit=limit,
        )

    async def batched_predict(
        self,
        target_ids: Sequence[str],
        target_type: str,
        prediction_type: str = "duration",
        features: dict[str, Any] | None = None,
    ) -> dict[str, Prediction]:
        assert self.prediction_engine is not None
        return await self.prediction_engine.batched_predict(
            target_ids,
            target_type,
            prediction_type,
            features,
        )

    # ======================================================================
    # AnalyticsPort — aggregate performance views
    # ======================================================================

    async def get_engine_performance(self, engine_id: str) -> EnginePerformance | None:
        assert self.analytics_engine is not None
        return await self.analytics_engine.get_engine_performance(engine_id)

    async def list_engine_performance(
        self,
        engine_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[EnginePerformance]:
        assert self.analytics_engine is not None
        return await self.analytics_engine.list_engine_performance(engine_type, limit, offset)

    async def get_workflow_performance(self, workflow_type: str) -> WorkflowPerformance | None:
        assert self.analytics_engine is not None
        return await self.analytics_engine.get_workflow_performance(workflow_type)

    async def list_workflow_performance(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[WorkflowPerformance]:
        assert self.analytics_engine is not None
        return await self.analytics_engine.list_workflow_performance(limit, offset)

    async def get_swarm_performance(self, swarm_id: str) -> SwarmPerformance | None:
        assert self.analytics_engine is not None
        return await self.analytics_engine.get_swarm_performance(swarm_id)

    async def list_swarm_performance(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[SwarmPerformance]:
        assert self.analytics_engine is not None
        return await self.analytics_engine.list_swarm_performance(limit, offset)

    async def get_performance_trend(
        self,
        target_id: str,
        metric_name: str,
        window_hours: int = 24,
    ) -> PerformanceTrend | None:
        assert self.analytics_engine is not None
        return await self.analytics_engine.get_performance_trend(
            target_id, metric_name, window_hours
        )

    async def list_performance_trends(
        self,
        target_id: str,
        window_hours: int = 24,
    ) -> Sequence[PerformanceTrend]:
        assert self.analytics_engine is not None
        return await self.analytics_engine.list_performance_trends(target_id, window_hours)

    async def get_capability_scores(self, engine_id: str) -> Sequence[CapabilityScore]:
        assert self.analytics_engine is not None
        return await self.analytics_engine.get_capability_scores(engine_id)

    async def get_top_engines(
        self,
        capability: str,
        min_confidence: float = 0.0,
        limit: int = 10,
    ) -> Sequence[EnginePerformance]:
        assert self.analytics_engine is not None
        return await self.analytics_engine.get_top_engines(capability, min_confidence, limit)

    async def compute_statistics(self) -> LearningStatistics:
        assert self.analytics_engine is not None
        return await self.analytics_engine.compute_statistics()

    async def take_snapshot(self) -> LearningSnapshot:
        assert self.analytics_engine is not None
        return await self.analytics_engine.take_snapshot()

    # ======================================================================
    # BenchmarkPort — run benchmarks
    # ======================================================================

    async def run_benchmark(
        self,
        target_id: str,
        target_type: str,
        benchmark_name: str,
        bus: EventBus | None = None,
    ) -> BenchmarkRecord:
        assert self.benchmark_engine is not None
        record = await self.benchmark_engine.run_benchmark(
            target_id=target_id,
            target_type=target_type,
            benchmark_name=benchmark_name,
            bus=self.bus if bus is None else bus,
        )
        assert self.publisher is not None
        await self.publisher.publish_benchmark_completed(
            benchmark_id=record.id,
            target_id=target_id,
            benchmark_name=benchmark_name,
            score=record.score,
        )
        return record

    async def get_benchmark(self, benchmark_id: str) -> BenchmarkRecord | None:
        assert self.benchmark_engine is not None
        return await self.benchmark_engine.get_benchmark(benchmark_id)

    async def list_benchmarks(
        self,
        target_id: str | None = None,
        benchmark_name: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[BenchmarkRecord]:
        assert self.benchmark_engine is not None
        return await self.benchmark_engine.list_benchmarks(
            target_id=target_id,
            benchmark_name=benchmark_name,
            limit=limit,
            offset=offset,
        )

    async def compare_engines(
        self,
        engine_ids: Sequence[str],
        benchmark_name: str,
    ) -> dict[str, BenchmarkRecord]:
        assert self.benchmark_engine is not None
        return await self.benchmark_engine.compare_engines(engine_ids, benchmark_name)

    async def get_benchmark_history(
        self,
        target_id: str,
        benchmark_name: str,
        limit: int = 20,
    ) -> Sequence[BenchmarkRecord]:
        assert self.benchmark_engine is not None
        return await self.benchmark_engine.get_benchmark_history(
            target_id,
            benchmark_name,
            limit,
        )

    async def get_top_scores(
        self,
        benchmark_name: str,
        limit: int = 10,
    ) -> Sequence[BenchmarkRecord]:
        assert self.benchmark_engine is not None
        return await self.benchmark_engine.get_top_scores(benchmark_name, limit)
