"""Tests for agentic_os.domain.learning domain models."""

from agentic_os.domain.learning import (
    Benchmark,
    BenchmarkStatus,
    CostMetrics,
    Evaluation,
    ExecutionHistory,
    Experiment,
    ExperimentStatus,
    ExperimentType,
    FailureAnalysis,
    LatencyMetrics,
    LearningMetrics,
    LearningPhase,
    LearningProfile,
    OptimizationPolicy,
    OptimizationRecommendation,
    OptimizationResult,
    OptimizationStatus,
    OptimizationTarget,
    PerformanceProfile,
    PolicyEffect,
    QualityMetrics,
    Recommendation,
    RecommendationStatus,
    RoutingDecision,
    TelemetryGranularity,
)


class TestLearningPhase:
    def test_values(self) -> None:
        assert LearningPhase.DATA_COLLECTION == "data_collection"
        assert LearningPhase.TRAINING == "training"
        assert LearningPhase.EVALUATION == "evaluation"
        assert LearningPhase.DEPLOYMENT == "deployment"
        assert LearningPhase.MONITORING == "monitoring"


class TestOptimizationTarget:
    def test_values(self) -> None:
        assert OptimizationTarget.ROUTING == "routing"
        assert OptimizationTarget.ENGINE_SELECTION == "engine_selection"
        assert OptimizationTarget.EXECUTION_COST == "execution_cost"


class TestRecommendation:
    def test_defaults(self) -> None:
        rec = Recommendation(category="engine_selection", title="Switch to engine-b", confidence=0.8)
        assert rec.status == RecommendationStatus.ACTIVE

    def test_to_dict(self) -> None:
        rec = Recommendation(category="routing", title="Use engine-b", confidence=0.85, evidence="Faster latency")
        d = rec.to_dict()
        assert d["category"] == "routing"
        assert d["confidence"] == 0.85


class TestRoutingDecision:
    def test_defaults(self) -> None:
        rd = RoutingDecision(execution_id="ex-1", selected_engine="engine-b", selection_reason="latency", confidence=0.9)
        assert rd.confidence == 0.9

    def test_to_dict(self) -> None:
        rd = RoutingDecision(execution_id="ex-1", selected_engine="engine-b", selection_reason="faster", confidence=0.9)
        d = rd.to_dict()
        assert d["selected_engine"] == "engine-b"


class TestPerformanceProfile:
    def test_defaults(self) -> None:
        pp = PerformanceProfile(target_id="e1", target_type="engine")
        assert pp.avg_latency_ms == 0.0
        assert pp.sample_count == 0

    def test_to_dict(self) -> None:
        pp = PerformanceProfile(target_id="e1", target_type="engine", avg_latency_ms=150.0, p95_latency_ms=300.0, success_rate=0.95)
        d = pp.to_dict()
        assert d["avg_latency_ms"] == 150.0
        assert d["success_rate"] == 0.95


class TestLearningMetrics:
    def test_to_dict(self) -> None:
        lm = LearningMetrics(total_executions=100, total_optimizations=5, success_rate=0.9)
        d = lm.to_dict()
        assert d["total_executions"] == 100
        assert d["success_rate"] == 0.9
        assert d["optimization_effectiveness"] == 0.0


class TestCostMetrics:
    def test_to_dict(self) -> None:
        cm = CostMetrics(total_cost=50.0, avg_cost_per_execution=0.05, estimated_savings=10.0)
        d = cm.to_dict()
        assert d["total_cost"] == 50.0


class TestLatencyMetrics:
    def test_to_dict(self) -> None:
        lm = LatencyMetrics(avg_latency_ms=200.0, p95_latency_ms=500.0, improvement_pct=15.0)
        d = lm.to_dict()
        assert d["avg_latency_ms"] == 200.0


class TestQualityMetrics:
    def test_to_dict(self) -> None:
        qm = QualityMetrics(avg_quality_score=0.85, improvement_pct=5.0)
        d = qm.to_dict()
        assert d["avg_quality_score"] == 0.85


class TestFailureAnalysis:
    def test_to_dict(self) -> None:
        fa = FailureAnalysis(total_failures=10, failure_rate=0.1)
        d = fa.to_dict()
        assert d["total_failures"] == 10
        assert d["failure_rate"] == 0.1


class TestOptimizationResult:
    def test_defaults(self) -> None:
        res = OptimizationResult(recommendation_id="rec-1", target=OptimizationTarget.ROUTING, previous_value="a", new_value="b")
        assert res.status == OptimizationStatus.PENDING

    def test_to_dict(self) -> None:
        res = OptimizationResult(
            recommendation_id="rec-1", target=OptimizationTarget.ROUTING,
            previous_value="a", new_value="b", improvement_pct=25.0,
            status=OptimizationStatus.APPLIED,
        )
        d = res.to_dict()
        assert d["status"] == "applied"
        assert d["improvement_pct"] == 25.0


class TestExecutionHistory:
    def test_defaults(self) -> None:
        entry = ExecutionHistory(execution_id="ex-1", engine_type="generic", engine_name="test")
        assert entry.id
        assert entry.execution_id == "ex-1"
        assert entry.engine_type == "generic"
        assert entry.duration_ms == 0.0
        assert entry.cost == 0.0
        assert entry.status == ""
        assert entry.metadata == {}

    def test_to_dict(self) -> None:
        entry = ExecutionHistory(
            execution_id="ex-1",
            engine_type="generic",
            engine_name="test-engine",
            status="success",
            duration_ms=150.0,
            cost=0.05,
        )
        d = entry.to_dict()
        assert d["execution_id"] == "ex-1"
        assert d["engine_type"] == "generic"
        assert d["status"] == "success"
        assert d["duration_ms"] == 150.0


class TestLearningProfile:
    def test_defaults(self) -> None:
        profile = LearningProfile(name="test-profile")
        assert profile.name == "test-profile"
        assert profile.enabled is True
        assert profile.min_confidence == 0.6
        assert profile.telemetry_granularity == TelemetryGranularity.HOURLY

    def test_to_dict(self) -> None:
        profile = LearningProfile(name="perf", targets=(OptimizationTarget.ROUTING,))
        d = profile.to_dict()
        assert d["name"] == "perf"
        assert "routing" in d["targets"]


class TestOptimizationPolicy:
    def test_defaults(self) -> None:
        policy = OptimizationPolicy(name="test-policy")
        assert policy.name == "test-policy"
        assert policy.effect == PolicyEffect.ALLOW
        assert policy.enabled is True

    def test_to_dict(self) -> None:
        policy = OptimizationPolicy(name="cost-saver", target=OptimizationTarget.EXECUTION_COST, effect=PolicyEffect.ALLOW)
        d = policy.to_dict()
        assert d["name"] == "cost-saver"
        assert d["target"] == "execution_cost"


class TestExperiment:
    def test_defaults(self) -> None:
        exp = Experiment(name="a-b-test", experiment_type=ExperimentType.A_B_TEST)
        assert exp.status == ExperimentStatus.DRAFT
        assert exp.rollback_on_regression is True

    def test_to_dict(self) -> None:
        exp = Experiment(name="canary-test", experiment_type=ExperimentType.CANARY, control_config={}, treatment_config={})
        d = exp.to_dict()
        assert d["name"] == "canary-test"
        assert d["experiment_type"] == "canary"
        assert d["status"] == "draft"


class TestBenchmark:
    def test_defaults(self) -> None:
        bm = Benchmark(name="speed-test", targets=("engine-a", "engine-b"))
        assert bm.status == BenchmarkStatus.PENDING
        assert bm.iterations == 10

    def test_to_dict(self) -> None:
        bm = Benchmark(name="latency", targets=("e1",), iterations=5)
        d = bm.to_dict()
        assert d["name"] == "latency"
        assert d["iterations"] == 5


class TestEvaluation:
    def test_defaults(self) -> None:
        ev = Evaluation(target_id="e1", target_type="engine", score=0.85, passed=True)
        assert ev.score == 0.85
        assert ev.passed is True

    def test_to_dict(self) -> None:
        ev = Evaluation(target_id="e1", target_type="engine", score=0.92, passed=True)
        d = ev.to_dict()
        assert d["score"] == 0.92
        assert d["passed"] is True


class TestOptimizationRecommendation:
    def test_defaults(self) -> None:
        rec = OptimizationRecommendation(
            target=OptimizationTarget.ROUTING,
            current_value="engine-a",
            recommended_value="engine-b",
            confidence=0.85,
        )
        assert rec.status == RecommendationStatus.ACTIVE

    def test_to_dict(self) -> None:
        rec = OptimizationRecommendation(
            target=OptimizationTarget.EXECUTION_COST,
            current_value="$0.05",
            recommended_value="$0.02",
            confidence=0.9,
        )
        d = rec.to_dict()
        assert d["current_value"] == "$0.05"
        assert d["confidence"] == 0.9
