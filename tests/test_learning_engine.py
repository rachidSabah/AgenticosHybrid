"""Tests for the Learning & Optimization Engine core subsystems.

Covers:
- KnowledgeBase
- AnalyticsEngine
- BenchmarkEngine
- PredictionEngine
- OptimizationEngine
- LearningManager (with mock event bus)
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from agentic_os.core.learning import (
    AnalyticsEngine,
    BenchmarkEngine,
    KnowledgeBase,
    LearningManager,
    OptimizationEngine,
    PredictionEngine,
)
from agentic_os.domain.learning import (
    BenchmarkRecord,
    EnginePerformance,
    ExecutionHistory,
    ExecutionOutcome,
    ExecutionProfile,
    ExperienceRecord,
    KnowledgePattern,
    LearningSnapshot,
    LearningStatistics,
    OptimizationGoal,
    OptimizationPolicy,
    PerformanceTrend,
    Prediction,
    Recommendation,
    RoutingDecision,
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _execution(
    exec_id: str,
    target_id: str = "engine-1",
    target_type: str = "engine",
    outcome: str = "success",
    duration_ms: float = 100.0,
    cost: float = 0.01,
    metadata: dict | None = None,
) -> ExecutionHistory:
    """Build an ExecutionHistory with sensible defaults."""
    return ExecutionHistory(
        id=exec_id,
        target_id=target_id,
        target_type=target_type,
        outcome=ExecutionOutcome(outcome),
        duration_ms=duration_ms,
        cost=cost,
        cpu_percent=50.0,
        memory_mb=256.0,
        token_count=1000,
        metadata=metadata or {},
    )


# =========================================================================
# KnowledgeBase
# =========================================================================


class TestKnowledgeBase:
    @pytest.fixture
    def kb(self) -> KnowledgeBase:
        return KnowledgeBase()

    @pytest.mark.asyncio
    async def test_store_and_get_pattern(self, kb: KnowledgeBase) -> None:
        p = KnowledgePattern(id="kp-1", pattern_type="optimization")
        stored = await kb.store_pattern(p)
        assert stored.id == "kp-1"
        retrieved = await kb.get_pattern("kp-1")
        assert retrieved is not None
        assert retrieved.id == "kp-1"

    @pytest.mark.asyncio
    async def test_get_pattern_unknown(self, kb: KnowledgeBase) -> None:
        assert await kb.get_pattern("nonexistent") is None

    @pytest.mark.asyncio
    async def test_query_patterns_by_type(self, kb: KnowledgeBase) -> None:
        await kb.store_pattern(KnowledgePattern(id="kp-1", pattern_type="optimization"))
        await kb.store_pattern(KnowledgePattern(id="kp-2", pattern_type="routing"))
        result = await kb.query_patterns({"pattern_type": "optimization"}, limit=10)
        assert len(result) == 1
        assert result[0].id == "kp-1"

    @pytest.mark.asyncio
    async def test_query_patterns_min_confidence(self, kb: KnowledgeBase) -> None:
        await kb.store_pattern(KnowledgePattern(id="kp-1", pattern_type="t", confidence=0.9))
        await kb.store_pattern(KnowledgePattern(id="kp-2", pattern_type="t", confidence=0.5))
        result = await kb.query_patterns({}, min_confidence=0.8, limit=10)
        assert len(result) == 1
        assert result[0].id == "kp-1"

    @pytest.mark.asyncio
    async def test_store_and_query_experience(self, kb: KnowledgeBase) -> None:
        exp = ExperienceRecord(id="exp-1", experience_type="execution", source="engine-1")
        await kb.store_experience(exp)
        results = await kb.query_experiences({"source": "engine-1"})
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_query_experiences_filter(self, kb: KnowledgeBase) -> None:
        await kb.store_experience(
            ExperienceRecord(id="e1", experience_type="execution", source="s1")
        )
        await kb.store_experience(
            ExperienceRecord(id="e2", experience_type="benchmark", source="s2")
        )
        results = await kb.query_experiences({"experience_type": "benchmark"})
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_statistics_empty(self, kb: KnowledgeBase) -> None:
        stats = await kb.get_statistics()
        assert stats.total_experiences == 0
        assert stats.total_patterns_detected == 0

    @pytest.mark.asyncio
    async def test_statistics_with_data(self, kb: KnowledgeBase) -> None:
        await kb.store_pattern(KnowledgePattern(id="kp-1", pattern_type="t", confidence=0.9))
        await kb.store_pattern(KnowledgePattern(id="kp-2", pattern_type="t", confidence=0.3))
        await kb.store_experience(ExperienceRecord(id="e1", experience_type="e", source="s"))
        stats = await kb.get_statistics()
        assert stats.total_patterns_detected == 2
        assert stats.total_experiences == 1

    @pytest.mark.asyncio
    async def test_prune_older_than(self, kb: KnowledgeBase) -> None:
        await kb.store_pattern(KnowledgePattern(id="kp-1", pattern_type="t", confidence=0.9))
        # Use min_confidence above the pattern's confidence to trigger removal
        removed = await kb.prune(older_than_days=0, min_confidence=0.95)
        assert removed == 1
        assert await kb.get_pattern("kp-1") is None

    @pytest.mark.asyncio
    async def test_prune_low_confidence(self, kb: KnowledgeBase) -> None:
        await kb.store_pattern(KnowledgePattern(id="kp-1", pattern_type="t", confidence=0.05))
        removed = await kb.prune(older_than_days=365, min_confidence=0.1)
        assert removed == 1

    @pytest.mark.asyncio
    async def test_prune_keeps_recent_high_confidence(self, kb: KnowledgeBase) -> None:
        await kb.store_pattern(KnowledgePattern(id="kp-1", pattern_type="t", confidence=0.9))
        removed = await kb.prune(older_than_days=365, min_confidence=0.1)
        assert removed == 0


# =========================================================================
# AnalyticsEngine
# =========================================================================


class TestAnalyticsEngine:
    @pytest.fixture
    def analytics(self) -> AnalyticsEngine:
        return AnalyticsEngine()

    def _feed(self, analytics: AnalyticsEngine, *executions: ExecutionHistory) -> None:
        for e in executions:
            analytics.record_execution(e)

    @pytest.mark.asyncio
    async def test_get_engine_performance_empty(self, analytics: AnalyticsEngine) -> None:
        assert await analytics.get_engine_performance("nonexistent") is None

    @pytest.mark.asyncio
    async def test_get_engine_performance_after_recording(self, analytics: AnalyticsEngine) -> None:
        self._feed(analytics, _execution("e1", target_id="engine-1"))
        perf = await analytics.get_engine_performance("engine-1")
        assert perf is not None
        assert perf.total_executions == 1
        assert perf.success_count == 1

    @pytest.mark.asyncio
    async def test_engine_performance_tracks_failures(self, analytics: AnalyticsEngine) -> None:
        self._feed(
            analytics,
            _execution("e1", target_id="e1", outcome="success"),
            _execution("e2", target_id="e1", outcome="failure"),
        )
        perf = await analytics.get_engine_performance("e1")
        assert perf is not None
        assert perf.total_executions == 2
        assert perf.success_count == 1
        assert perf.failure_count == 1

    @pytest.mark.asyncio
    async def test_list_engine_performance(self, analytics: AnalyticsEngine) -> None:
        self._feed(
            analytics,
            _execution("e1", target_id="fast"),
            _execution("e2", target_id="slow"),
            _execution("e3", target_id="medium"),
        )
        results = await analytics.list_engine_performance()
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_list_engine_performance_filtered_by_type(
        self, analytics: AnalyticsEngine
    ) -> None:
        self._feed(
            analytics,
            _execution("e1", target_id="e1", metadata={"engine_type": "openai"}),
            _execution("e2", target_id="e2", metadata={"engine_type": "openai"}),
            _execution("e3", target_id="e3", metadata={"engine_type": "anthropic"}),
        )
        results = await analytics.list_engine_performance(engine_type="openai")
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_get_performance_trend_no_data(self, analytics: AnalyticsEngine) -> None:
        assert await analytics.get_performance_trend("nonexistent", "latency") is None

    @pytest.mark.asyncio
    async def test_get_performance_trend_with_data(self, analytics: AnalyticsEngine) -> None:
        self._feed(analytics, _execution("e1", target_id="e1", duration_ms=200))
        trend = await analytics.get_performance_trend("e1", "latency")
        assert trend is not None
        assert trend.metric_name == "latency"
        assert trend.current_value > 0

    @pytest.mark.asyncio
    async def test_get_capability_scores_empty(self, analytics: AnalyticsEngine) -> None:
        assert await analytics.get_capability_scores("nonexistent") == []

    @pytest.mark.asyncio
    async def test_top_engines_empty(self, analytics: AnalyticsEngine) -> None:
        assert await analytics.get_top_engines("math") == []

    @pytest.mark.asyncio
    async def test_statistics_empty(self, analytics: AnalyticsEngine) -> None:
        stats = await analytics.compute_statistics()
        assert stats.total_experiences == 0

    @pytest.mark.asyncio
    async def test_statistics_with_data(self, analytics: AnalyticsEngine) -> None:
        self._feed(
            analytics,
            _execution("e1", target_id="e1", outcome="success"),
            _execution("e2", target_id="e2", outcome="failure"),
        )
        stats = await analytics.compute_statistics()
        assert stats.total_experiences == 2

    @pytest.mark.asyncio
    async def test_snapshot(self, analytics: AnalyticsEngine) -> None:
        snap = await analytics.take_snapshot()
        assert isinstance(snap, LearningSnapshot)
        assert snap.id.startswith("snap-")


# =========================================================================
# BenchmarkEngine
# =========================================================================


class TestBenchmarkEngine:
    @pytest.fixture
    def bm(self) -> BenchmarkEngine:
        return BenchmarkEngine()

    @pytest.mark.asyncio
    async def test_run_benchmark_returns_record(self, bm: BenchmarkEngine) -> None:
        record = await bm.run_benchmark("engine-1", "engine", "latency")
        assert isinstance(record, BenchmarkRecord)
        assert record.target_id == "engine-1"
        assert record.benchmark_name == "latency"
        assert record.score > 0

    @pytest.mark.asyncio
    async def test_get_benchmark(self, bm: BenchmarkEngine) -> None:
        created = await bm.run_benchmark("engine-1", "engine", "latency")
        retrieved = await bm.get_benchmark(created.id)
        assert retrieved is not None
        assert retrieved.id == created.id

    @pytest.mark.asyncio
    async def test_get_benchmark_unknown(self, bm: BenchmarkEngine) -> None:
        assert await bm.get_benchmark("nonexistent") is None

    @pytest.mark.asyncio
    async def test_list_benchmarks(self, bm: BenchmarkEngine) -> None:
        await bm.run_benchmark("e1", "engine", "latency")
        await bm.run_benchmark("e2", "engine", "latency")
        records = await bm.list_benchmarks()
        assert len(records) == 2

    @pytest.mark.asyncio
    async def test_list_benchmarks_filtered_by_target(self, bm: BenchmarkEngine) -> None:
        await bm.run_benchmark("e1", "engine", "latency")
        await bm.run_benchmark("e2", "engine", "latency")
        records = await bm.list_benchmarks(target_id="e1")
        assert len(records) == 1

    @pytest.mark.asyncio
    async def test_list_benchmarks_filtered_by_name(self, bm: BenchmarkEngine) -> None:
        await bm.run_benchmark("e1", "engine", "latency")
        await bm.run_benchmark("e1", "engine", "throughput")
        records = await bm.list_benchmarks(target_id="e1", benchmark_name="latency")
        assert len(records) == 1

    @pytest.mark.asyncio
    async def test_compare_engines(self, bm: BenchmarkEngine) -> None:
        await bm.run_benchmark("e1", "engine", "latency")
        await bm.run_benchmark("e2", "engine", "latency")
        result = await bm.compare_engines(["e1", "e2", "e3"], "latency")
        assert "e1" in result
        assert "e2" in result
        assert "e3" not in result

    @pytest.mark.asyncio
    async def test_benchmark_history(self, bm: BenchmarkEngine) -> None:
        for _ in range(5):
            await bm.run_benchmark("e1", "engine", "latency")
        history = await bm.get_benchmark_history("e1", "latency", limit=3)
        assert len(history) == 3

    @pytest.mark.asyncio
    async def test_top_scores(self, bm: BenchmarkEngine) -> None:
        for _ in range(5):
            await bm.run_benchmark("e1", "engine", "latency")
        top = await bm.get_top_scores("latency")
        assert len(top) <= 5
        if len(top) > 1:
            assert top[0].score >= top[-1].score


# =========================================================================
# PredictionEngine
# =========================================================================


class TestPredictionEngine:
    @pytest.fixture
    def pred(self) -> PredictionEngine:
        return PredictionEngine()

    def _feed(self, pred: PredictionEngine, count: int = 5, target_id: str = "e1") -> None:
        for i in range(count):
            pred.ingest_execution(_execution(f"ex-{i}", target_id=target_id))

    @pytest.mark.asyncio
    async def test_predict_duration_insufficient_data(self, pred: PredictionEngine) -> None:
        pred.ingest_execution(_execution("ex-1"))
        p = await pred.predict_duration("e1", "engine")
        assert p.prediction_status.value == "insufficient_data"

    @pytest.mark.asyncio
    async def test_predict_duration_with_enough_data(self, pred: PredictionEngine) -> None:
        self._feed(pred, count=10)
        p = await pred.predict_duration("e1", "engine")
        assert p.predicted_value > 0
        assert p.confidence > 0
        assert p.target_id == "e1"

    @pytest.mark.asyncio
    async def test_predict_cost(self, pred: PredictionEngine) -> None:
        self._feed(pred, count=10)
        p = await pred.predict_cost("e1", "engine")
        assert p.predicted_value >= 0
        assert p.prediction_type == "cost"

    @pytest.mark.asyncio
    async def test_predict_success_probability(self, pred: PredictionEngine) -> None:
        self._feed(pred, count=10)
        p = await pred.predict_success_probability("e1", "engine")
        assert 0 <= p.predicted_value <= 1

    @pytest.mark.asyncio
    async def test_predict_success_probability_no_data(self, pred: PredictionEngine) -> None:
        p = await pred.predict_success_probability("nonexistent", "engine")
        assert p.prediction_status.value == "insufficient_data"

    @pytest.mark.asyncio
    async def test_predict_resource_usage(self, pred: PredictionEngine) -> None:
        self._feed(pred, count=10)
        p = await pred.predict_resource_usage("e1", "engine")
        assert p.predicted_value > 0

    @pytest.mark.asyncio
    async def test_get_prediction(self, pred: PredictionEngine) -> None:
        self._feed(pred, count=10)
        p = await pred.predict_duration("e1", "engine")
        retrieved = await pred.get_prediction(p.id)
        assert retrieved is not None
        assert retrieved.id == p.id

    @pytest.mark.asyncio
    async def test_get_prediction_unknown(self, pred: PredictionEngine) -> None:
        assert await pred.get_prediction("nonexistent") is None

    @pytest.mark.asyncio
    async def test_list_predictions(self, pred: PredictionEngine) -> None:
        self._feed(pred, count=10)
        await pred.predict_duration("e1", "engine")
        await pred.predict_cost("e1", "engine")
        preds = await pred.list_predictions()
        assert len(preds) >= 2

    @pytest.mark.asyncio
    async def test_list_predictions_filtered(self, pred: PredictionEngine) -> None:
        self._feed(pred, count=10)
        await pred.predict_duration("e1", "engine")
        preds = await pred.list_predictions(prediction_type="duration")
        assert len(preds) >= 1

    @pytest.mark.asyncio
    async def test_batched_predict(self, pred: PredictionEngine) -> None:
        for target in ["e1", "e2", "e3"]:
            self._feed(pred, count=10, target_id=target)
        result = await pred.batched_predict(["e1", "e2", "e3"], "engine", "duration")
        assert len(result) == 3
        for tid in ["e1", "e2", "e3"]:
            assert tid in result


# =========================================================================
# OptimizationEngine
# =========================================================================


class TestOptimizationEngine:
    @pytest.fixture
    def opt(self) -> OptimizationEngine:
        return OptimizationEngine()

    @pytest.mark.asyncio
    async def test_analyze_performance_no_engine(self, opt: OptimizationEngine) -> None:
        recs = await opt.analyze_performance("nonexistent", "engine")
        assert recs == []

    @pytest.mark.asyncio
    async def test_analyze_performance_high_latency(self, opt: OptimizationEngine) -> None:
        opt.set_engine_performance(
            [
                EnginePerformance(
                    engine_id="e1", total_executions=10, avg_latency_ms=2000, avg_cost=0.01
                ),
            ]
        )
        recs = await opt.analyze_performance("e1", "engine")
        assert len(recs) >= 1

    @pytest.mark.asyncio
    async def test_analyze_performance_low_success_rate(self, opt: OptimizationEngine) -> None:
        opt.set_engine_performance(
            [
                EnginePerformance(
                    engine_id="e1",
                    total_executions=10,
                    success_count=5,
                    failure_count=5,
                    avg_latency_ms=100,
                    avg_cost=0.01,
                ),
            ]
        )
        recs = await opt.analyze_performance("e1", "engine")
        rec_titles = [r.title for r in recs]
        assert any("success" in t.lower() for t in rec_titles)

    @pytest.mark.asyncio
    async def test_optimize_routing_selects_lowest_latency(self, opt: OptimizationEngine) -> None:
        opt.set_engine_performance(
            [
                EnginePerformance(
                    engine_id="e1", total_executions=10, avg_latency_ms=500, avg_cost=0.01
                ),
                EnginePerformance(
                    engine_id="e2", total_executions=10, avg_latency_ms=100, avg_cost=0.01
                ),
                EnginePerformance(
                    engine_id="e3", total_executions=10, avg_latency_ms=1000, avg_cost=0.01
                ),
            ]
        )
        decision = await opt.optimize_routing("task-1", ["math"], ["e1", "e2", "e3"])
        assert decision.selected_engine_id == "e2"

    @pytest.mark.asyncio
    async def test_optimize_routing_fallback(self, opt: OptimizationEngine) -> None:
        decision = await opt.optimize_routing("task-1", ["math"], ["e1", "e2"])
        assert decision.selected_engine_id == "e1"
        assert "No performance data" in decision.routing_reason

    @pytest.mark.asyncio
    async def test_optimize_routing_no_engines(self, opt: OptimizationEngine) -> None:
        with pytest.raises(ValueError, match="No available engines"):
            await opt.optimize_routing("task-1", ["math"], [])

    @pytest.mark.asyncio
    async def test_generate_recommendations(self, opt: OptimizationEngine) -> None:
        opt.set_engine_performance(
            [
                EnginePerformance(
                    engine_id="e1",
                    total_executions=10,
                    avg_latency_ms=2000,
                    success_count=10,
                    avg_cost=0.1,
                ),
            ]
        )
        recs = await opt.generate_recommendations("e1", "engine")
        assert len(recs) >= 1
        assert all(isinstance(r, Recommendation) for r in recs)

    @pytest.mark.asyncio
    async def test_generate_recommendations_no_data(self, opt: OptimizationEngine) -> None:
        recs = await opt.generate_recommendations("nonexistent", "engine")
        assert recs == []

    @pytest.mark.asyncio
    async def test_apply_recommendation(self, opt: OptimizationEngine) -> None:
        opt.set_engine_performance(
            [
                EnginePerformance(
                    engine_id="e1", total_executions=10, avg_latency_ms=2000, avg_cost=0.01
                ),
            ]
        )
        recs = await opt.generate_recommendations("e1", "engine")
        assert len(recs) > 0
        applied = await opt.apply_recommendation(recs[0].id)
        assert applied.applied_at is not None

    @pytest.mark.asyncio
    async def test_apply_recommendation_not_found(self, opt: OptimizationEngine) -> None:
        with pytest.raises(ValueError):
            await opt.apply_recommendation("nonexistent")

    @pytest.mark.asyncio
    async def test_dismiss_recommendation(self, opt: OptimizationEngine) -> None:
        opt.set_engine_performance(
            [
                EnginePerformance(
                    engine_id="e1", total_executions=10, avg_latency_ms=2000, avg_cost=0.01
                ),
            ]
        )
        recs = await opt.generate_recommendations("e1", "engine")
        dismissed = await opt.dismiss_recommendation(recs[0].id)
        assert dismissed.dismissed_at is not None

    @pytest.mark.asyncio
    async def test_list_recommendations(self, opt: OptimizationEngine) -> None:
        opt.set_engine_performance(
            [
                EnginePerformance(
                    engine_id="e1",
                    total_executions=10,
                    avg_latency_ms=2000,
                    success_count=5,
                    avg_cost=0.01,
                ),
            ]
        )
        await opt.generate_recommendations("e1", "engine")
        all_recs = await opt.list_recommendations()
        assert len(all_recs) >= 1

    @pytest.mark.asyncio
    async def test_routing_history(self, opt: OptimizationEngine) -> None:
        await opt.optimize_routing("task-1", ["math"], ["e1"])
        await opt.optimize_routing("task-2", ["code"], ["e1"])
        history = await opt.get_routing_history()
        assert len(history) == 2

    @pytest.mark.asyncio
    async def test_routing_history_filtered(self, opt: OptimizationEngine) -> None:
        await opt.optimize_routing("task-1", ["math"], ["e1"])
        await opt.optimize_routing("task-2", ["code"], ["e1"])
        history = await opt.get_routing_history(task_id="task-1")
        assert len(history) == 1
        assert history[0].task_id == "task-1"

    @pytest.mark.asyncio
    async def test_policy_crud(self, opt: OptimizationEngine) -> None:
        policy = OptimizationPolicy(id="p1", name="test-policy", goal=OptimizationGoal.LATENCY)
        created = await opt.create_optimization_policy(policy)
        assert created.id == "p1"

        retrieved = await opt.get_optimization_policy("p1")
        assert retrieved is not None
        assert retrieved.name == "test-policy"

        policies = await opt.list_optimization_policies()
        assert len(policies) == 1

        updated = OptimizationPolicy(id="p1", name="updated", goal=OptimizationGoal.COST)
        await opt.update_optimization_policy("p1", updated)
        retrieved = await opt.get_optimization_policy("p1")
        assert retrieved is not None
        assert retrieved.name == "updated"

        deleted = await opt.delete_optimization_policy("p1")
        assert deleted is True
        assert await opt.get_optimization_policy("p1") is None

    @pytest.mark.asyncio
    async def test_policy_delete_not_found(self, opt: OptimizationEngine) -> None:
        assert await opt.delete_optimization_policy("nonexistent") is False


# =========================================================================
# LearningManager (integration with mock bus)
# =========================================================================


class _MockBus:
    """Minimal EventBus stub for testing the LearningManager."""

    def __init__(self) -> None:
        self.events: list[Any] = []

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def publish(self, event: Any) -> None:
        self.events.append(event)

    async def subscribe(self, topic: str, handler: Any) -> str:
        return "sub-1"

    async def unsubscribe(self, subscription_id: str) -> None:
        pass


class TestLearningManager:
    @pytest.fixture
    def bus(self) -> _MockBus:
        return _MockBus()

    @pytest.fixture
    async def manager(self, bus: _MockBus) -> LearningManager:
        m = LearningManager(bus=bus)
        await m.start()
        return m

    @pytest.mark.asyncio
    async def test_start_stop(self, bus: _MockBus) -> None:
        m = LearningManager(bus=bus)
        await m.start()
        assert m._running is True
        await m.stop()
        assert m._running is False

    @pytest.mark.asyncio
    async def test_start_already_running(self, bus: _MockBus) -> None:
        m = LearningManager(bus=bus)
        await m.start()
        await m.start()  # should not crash

    @pytest.mark.asyncio
    async def test_record_execution(self, manager: LearningManager) -> None:
        result = await manager.record_execution(_execution("ex-1"))
        assert result.id == "ex-1"

    @pytest.mark.asyncio
    async def test_record_execution_fires_event(
        self, manager: LearningManager, bus: _MockBus
    ) -> None:
        await manager.record_execution(_execution("ex-1"))
        assert any("execution_id" in str(e) for e in bus.events)

    @pytest.mark.asyncio
    async def test_get_execution(self, manager: LearningManager) -> None:
        await manager.record_execution(_execution("ex-1", target_id="engine-1"))
        result = await manager.get_execution("ex-1")
        assert result is not None
        assert result.id == "ex-1"

    @pytest.mark.asyncio
    async def test_get_execution_not_found(self, manager: LearningManager) -> None:
        assert await manager.get_execution("nonexistent") is None

    @pytest.mark.asyncio
    async def test_list_executions(self, manager: LearningManager) -> None:
        for i in range(5):
            await manager.record_execution(_execution(f"ex-{i}", target_id="engine-1"))
        results = await manager.list_executions(target_id="engine-1")
        assert len(results) == 5

    @pytest.mark.asyncio
    async def test_list_executions_filtered_by_outcome(self, manager: LearningManager) -> None:
        await manager.record_execution(_execution("ex-1", outcome="success"))
        await manager.record_execution(_execution("ex-2", outcome="failure"))
        results = await manager.list_executions(outcome="failure")
        assert len(results) == 1
        assert results[0].id == "ex-2"

    @pytest.mark.asyncio
    async def test_execution_profile(self, manager: LearningManager) -> None:
        await manager.record_execution(_execution("ex-1", target_id="engine-1", duration_ms=100))
        await manager.record_execution(_execution("ex-2", target_id="engine-1", duration_ms=200))
        profile = await manager.get_execution_profile("engine-1", "engine")
        assert isinstance(profile, ExecutionProfile)
        assert profile.total_executions == 2

    @pytest.mark.asyncio
    async def test_analyze_performance(self, manager: LearningManager) -> None:
        for i in range(10):
            await manager.record_execution(
                _execution(f"ex-{i}", target_id="engine-1", duration_ms=2000)
            )
        recs = await manager.analyze_performance("engine-1", "engine")
        assert len(recs) >= 1

    @pytest.mark.asyncio
    async def test_predict_duration(self, manager: LearningManager) -> None:
        for i in range(10):
            await manager.record_execution(
                _execution(f"ex-{i}", target_id="engine-1", duration_ms=100 * (i + 1))
            )
        pred = await manager.predict_duration("engine-1", "engine")
        assert isinstance(pred, Prediction)
        assert pred.predicted_value > 0

    @pytest.mark.asyncio
    async def test_predict_cost(self, manager: LearningManager) -> None:
        for i in range(10):
            await manager.record_execution(
                _execution(f"ex-{i}", target_id="engine-1", cost=0.01 * (i + 1))
            )
        pred = await manager.predict_cost("engine-1", "engine")
        assert isinstance(pred, Prediction)
        assert pred.predicted_value > 0

    @pytest.mark.asyncio
    async def test_predict_success(self, manager: LearningManager) -> None:
        for i in range(10):
            await manager.record_execution(
                _execution(f"ex-{i}", target_id="engine-1", outcome="success")
            )
        pred = await manager.predict_success_probability("engine-1", "engine")
        assert pred.predicted_value == 1.0

    @pytest.mark.asyncio
    async def test_generate_recommendations(self, manager: LearningManager) -> None:
        for i in range(10):
            await manager.record_execution(
                _execution(f"ex-{i}", target_id="engine-1", duration_ms=3000)
            )
        recs = await manager.generate_recommendations("engine-1", "engine")
        assert len(recs) >= 1

    @pytest.mark.asyncio
    async def test_recommendation_apply(self, manager: LearningManager) -> None:
        for i in range(10):
            await manager.record_execution(
                _execution(f"ex-{i}", target_id="engine-1", duration_ms=3000)
            )
        recs = await manager.generate_recommendations("engine-1", "engine")
        if recs:
            applied = await manager.apply_recommendation(recs[0].id)
            assert applied.applied_at is not None

    @pytest.mark.asyncio
    async def test_run_benchmark(self, manager: LearningManager) -> None:
        record = await manager.run_benchmark("engine-1", "engine", "latency")
        assert isinstance(record, BenchmarkRecord)
        assert record.target_id == "engine-1"

    @pytest.mark.asyncio
    async def test_list_benchmarks(self, manager: LearningManager) -> None:
        await manager.run_benchmark("e1", "engine", "latency")
        await manager.run_benchmark("e2", "engine", "latency")
        records = await manager.list_benchmarks()
        assert len(records) == 2

    @pytest.mark.asyncio
    async def test_optimize_routing(self, manager: LearningManager) -> None:
        decision = await manager.optimize_routing(
            task_id="task-1",
            required_capabilities=["math"],
            available_engines=["e1", "e2"],
        )
        assert isinstance(decision, RoutingDecision)
        assert decision.selected_engine_id in ["e1", "e2"]

    @pytest.mark.asyncio
    async def test_optimize_routing_fires_event(
        self, manager: LearningManager, bus: _MockBus
    ) -> None:
        await manager.optimize_routing("task-1", ["math"], ["e1"])
        assert any("routing" in str(e) for e in bus.events)

    @pytest.mark.asyncio
    async def test_statistics(self, manager: LearningManager) -> None:
        stats = await manager.compute_statistics()
        assert isinstance(stats, LearningStatistics)

    @pytest.mark.asyncio
    async def test_snapshot(self, manager: LearningManager) -> None:
        snap = await manager.take_snapshot()
        assert isinstance(snap, LearningSnapshot)

    @pytest.mark.asyncio
    async def test_get_engine_performance(self, manager: LearningManager) -> None:
        await manager.record_execution(_execution("ex-1", target_id="engine-1"))
        perf = await manager.get_engine_performance("engine-1")
        assert perf is not None
        assert perf.total_executions == 1

    @pytest.mark.asyncio
    async def test_get_engine_performance_not_found(self, manager: LearningManager) -> None:
        assert await manager.get_engine_performance("nonexistent") is None

    @pytest.mark.asyncio
    async def test_list_engine_performance(self, manager: LearningManager) -> None:
        await manager.record_execution(_execution("ex-1", target_id="e1"))
        await manager.record_execution(_execution("ex-2", target_id="e2"))
        results = await manager.list_engine_performance()
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_policy_crud_through_manager(self, manager: LearningManager) -> None:
        policy = OptimizationPolicy(id="p1", name="test")
        created = await manager.create_optimization_policy(policy)
        assert created.id == "p1"
        assert await manager.get_optimization_policy("p1") is not None

    @pytest.mark.asyncio
    async def test_get_performance_trend(self, manager: LearningManager) -> None:
        await manager.record_execution(_execution("ex-1", target_id="e1", duration_ms=100))
        trend = await manager.get_performance_trend("e1", "latency")
        assert trend is not None
        assert isinstance(trend, PerformanceTrend)

    @pytest.mark.asyncio
    async def test_list_knowledge_patterns_empty(self, manager: LearningManager) -> None:
        patterns = await manager.list_knowledge_patterns()
        assert patterns == []

    @pytest.mark.asyncio
    async def test_clear_history(self, manager: LearningManager) -> None:
        await manager.record_execution(_execution("ex-1"))
        count = await manager.clear_history(older_than_hours=0)
        assert count >= 0
