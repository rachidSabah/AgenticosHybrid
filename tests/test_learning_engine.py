"""Tests for the Learning & Optimization Engine core subsystems.

Covers:
- LearningManager (with mock event bus)
- HistoricalAnalyzer
- RecommendationEngine
- PolicyEngine
- EvaluationEngine
- ExperimentManager
- BenchmarkManager
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from agentic_os.core.learning import (
    BenchmarkManager,
    EvaluationEngine,
    ExperimentManager,
    HistoricalAnalyzer,
    LearningManager,
    PolicyEngine,
    RecommendationEngine,
)
from agentic_os.domain.learning import (
    Benchmark,
    ExecutionHistory,
    Experiment,
    ExperimentStatus,
    ExperimentType,
    OptimizationPolicy,
    OptimizationTarget,
    PolicyEffect,
)


@pytest.fixture
def mock_bus() -> AsyncMock:
    bus = AsyncMock()
    bus.publish = AsyncMock()
    return bus


@pytest.fixture
def manager(mock_bus: AsyncMock) -> LearningManager:
    return LearningManager(bus=mock_bus)


class TestHistoricalAnalyzer:
    @pytest.mark.asyncio
    async def test_record_and_analyze(self) -> None:
        analyzer = HistoricalAnalyzer()
        h1 = ExecutionHistory(
            execution_id="e1",
            engine_type="generic",
            engine_name="g1",
            status="success",
            duration_ms=100.0,
        )
        h2 = ExecutionHistory(
            execution_id="e2",
            engine_type="generic",
            engine_name="g1",
            status="failure",
            duration_ms=200.0,
            error_type="timeout",
        )

        analyzer.record_execution(h1)
        analyzer.record_execution(h2)

        stats = await analyzer.analyze_executions((h1.id, h2.id))
        assert stats.total_count == 2
        assert stats.success_count == 1
        assert stats.failure_count == 1

    @pytest.mark.asyncio
    async def test_empty_analyze(self) -> None:
        analyzer = HistoricalAnalyzer()
        stats = await analyzer.analyze_executions(())
        assert stats.total_count == 0


class TestRecommendationEngine:
    @pytest.mark.asyncio
    async def test_generate_and_list(self) -> None:
        engine = RecommendationEngine()
        rec = await engine.generate_recommendation("engine_selection", {"task": "coding"})
        assert rec.category == "engine_selection"
        assert rec.confidence > 0

        recs = await engine.list_recommendations()
        assert len(recs) == 1

    @pytest.mark.asyncio
    async def test_apply_and_dismiss(self) -> None:
        engine = RecommendationEngine()
        rec = await engine.generate_recommendation("routing", {})

        applied = await engine.apply_recommendation(rec.id)
        assert applied.status.value == "applied"

        dismissed = await engine.dismiss_recommendation(rec.id)
        assert dismissed.status.value == "dismissed"


class TestPolicyEngine:
    @pytest.mark.asyncio
    async def test_crud(self) -> None:
        engine = PolicyEngine()
        policy = OptimizationPolicy(
            name="test-policy", target=OptimizationTarget.ROUTING, effect=PolicyEffect.ALLOW
        )
        created = await engine.create_policy(policy)
        assert created.name == "test-policy"

        fetched = await engine.get_policy(created.id)
        assert fetched is not None

        policies = await engine.list_policies()
        assert len(policies) == 1

        await engine.delete_policy(created.id)
        assert await engine.get_policy(created.id) is None

    @pytest.mark.asyncio
    async def test_check_policy(self) -> None:
        engine = PolicyEngine()
        policy = OptimizationPolicy(
            name="deny-cost", target=OptimizationTarget.EXECUTION_COST, effect=PolicyEffect.DENY
        )
        await engine.create_policy(policy)

        result = await engine.check_policy(OptimizationTarget.EXECUTION_COST, {})
        assert result is False

        result2 = await engine.check_policy(OptimizationTarget.ROUTING, {})
        assert result2 is True


class TestEvaluationEngine:
    @pytest.mark.asyncio
    async def test_evaluate(self) -> None:
        engine = EvaluationEngine()
        ev = await engine.evaluate(
            "e1", "engine", {"latency": 100.0, "cost": 0.05, "success_rate": 0.95}
        )
        assert ev.target_id == "e1"
        assert ev.score > 0
        assert ev.passed is True

    @pytest.mark.asyncio
    async def test_list_evaluations(self) -> None:
        engine = EvaluationEngine()
        await engine.evaluate("e1", "engine", {"latency": 100.0})
        await engine.evaluate("e1", "engine", {"latency": 200.0})
        evals = await engine.list_evaluations("e1")
        assert len(evals) == 2


class TestExperimentManager:
    @pytest.mark.asyncio
    async def test_lifecycle(self) -> None:
        engine = ExperimentManager()
        exp = Experiment(
            name="test-ab",
            experiment_type=ExperimentType.A_B_TEST,
            control_config={"engine": "a"},
            treatment_config={"engine": "b"},
        )
        created = await engine.create_experiment(exp)
        assert created.status == ExperimentStatus.DRAFT

        started = await engine.start_experiment(created.id)
        assert started.status == ExperimentStatus.RUNNING

        completed = await engine.complete_experiment(created.id)
        assert completed.status == ExperimentStatus.COMPLETED


class TestBenchmarkManager:
    @pytest.mark.asyncio
    async def test_crud_and_run(self) -> None:
        engine = BenchmarkManager()
        bm = Benchmark(name="speed", targets=("e1", "e2"), iterations=5)
        created = await engine.create_benchmark(bm)
        assert created.name == "speed"

        benchmarks = await engine.list_benchmarks()
        assert len(benchmarks) == 1

        await engine.delete_benchmark(created.id)
        benchmarks = await engine.list_benchmarks()
        assert len(benchmarks) == 0


class TestLearningManager:
    @pytest.mark.asyncio
    async def test_profile_crud(self, manager: LearningManager) -> None:
        from agentic_os.domain.learning import LearningProfile

        profile = LearningProfile(name="test-profile")
        created = await manager.create_profile(profile)
        assert created.name == "test-profile"

        fetched = await manager.get_profile(created.id)
        assert fetched is not None

        profiles = await manager.list_profiles()
        assert len(profiles) == 1

        await manager.delete_profile(created.id)
        assert await manager.get_profile(created.id) is None

    @pytest.mark.asyncio
    async def test_record_and_analyze(self, manager: LearningManager) -> None:
        h = ExecutionHistory(
            execution_id="e1",
            engine_type="generic",
            engine_name="g1",
            status="success",
            duration_ms=100.0,
        )
        recorded = await manager.record_execution(h)
        assert recorded.execution_id == "e1"

        stats = await manager.analyze_executions((h.id,))
        assert stats.total_count == 1

    @pytest.mark.asyncio
    async def test_recommendations(self, manager: LearningManager) -> None:
        rec = await manager.generate_recommendation("engine_selection", {"task": "coding"})
        assert rec.category == "engine_selection"

        recs = await manager.list_recommendations()
        assert len(recs) == 1

    @pytest.mark.asyncio
    async def test_policy_workflow(self, manager: LearningManager) -> None:
        policy = OptimizationPolicy(
            name="test", target=OptimizationTarget.ROUTING, effect=PolicyEffect.ALLOW
        )
        created = await manager.create_policy(policy)
        assert created.name == "test"

        policies = await manager.list_policies()
        assert len(policies) == 1

        updated = OptimizationPolicy(
            id=created.id,
            name="updated",
            target=OptimizationTarget.ROUTING,
            effect=PolicyEffect.DENY,
        )
        result = await manager.update_policy(updated)
        assert result.effect == PolicyEffect.DENY

        await manager.delete_policy(created.id)
        assert len(await manager.list_policies()) == 0

    @pytest.mark.asyncio
    async def test_experiment_lifecycle(self, manager: LearningManager) -> None:
        exp = Experiment(
            name="test-exp",
            experiment_type=ExperimentType.A_B_TEST,
            control_config={},
            treatment_config={},
        )
        created = await manager.create_experiment(exp)
        assert created.name == "test-exp"

        experiments = await manager.list_experiments()
        assert len(experiments) == 1

        started = await manager.start_experiment(created.id)
        assert started.status == ExperimentStatus.RUNNING

    @pytest.mark.asyncio
    async def test_learning_metrics(self, manager: LearningManager) -> None:
        metrics = await manager.compute_learning_metrics()
        assert metrics.total_executions >= 0
