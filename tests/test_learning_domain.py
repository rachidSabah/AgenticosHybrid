"""Tests for agentic_os.domain.learning domain models."""

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
    OptimizationGoal,
    OptimizationPolicy,
    OptimizationRecommendation,
    PerformanceTrend,
    Prediction,
    PredictionStatus,
    Recommendation,
    RecommendationPriority,
    RecoveryPattern,
    RoutingDecision,
    SwarmPerformance,
    TrendDirection,
    WorkflowPerformance,
)


class TestExecutionOutcome:
    def test_values(self) -> None:
        assert ExecutionOutcome.SUCCESS == "success"
        assert ExecutionOutcome.FAILURE == "failure"
        assert ExecutionOutcome.TIMEOUT == "timeout"


class TestExecutionHistory:
    def test_defaults(self) -> None:
        entry = ExecutionHistory(
            id="ex-1", target_id="e1", target_type="engine", outcome=ExecutionOutcome.SUCCESS
        )
        assert entry.id == "ex-1"
        assert entry.target_id == "e1"
        assert entry.target_type == "engine"
        assert entry.duration_ms == 0.0
        assert entry.cpu_percent == 0.0
        assert entry.token_count == 0
        assert entry.metadata == {}
        assert entry.completed_at is None

    def test_to_dict(self) -> None:
        entry = ExecutionHistory(
            id="ex-1",
            target_id="e1",
            target_type="engine",
            outcome=ExecutionOutcome.SUCCESS,
            duration_ms=150.0,
        )
        d = entry.to_dict()
        assert d["id"] == "ex-1"
        assert d["outcome"] == "success"
        assert d["duration_ms"] == 150.0
        assert "started_at" in d

    def test_to_dict_roundtrip(self) -> None:
        entry = ExecutionHistory(
            id="ex-1",
            target_id="e1",
            target_type="engine",
            outcome=ExecutionOutcome.FAILURE,
            duration_ms=200.0,
            cost=0.05,
            error="timeout",
            metadata={"retry": True},
        )
        d = entry.to_dict()
        assert d["error"] == "timeout"
        assert d["cost"] == 0.05
        assert d["metadata"]["retry"] is True


class TestExecutionProfile:
    def test_defaults(self) -> None:
        profile = ExecutionProfile(target_id="e1", target_type="engine")
        assert profile.total_executions == 0
        assert profile.success_rate == 0.0

    def test_success_rate(self) -> None:
        profile = ExecutionProfile(
            target_id="e1",
            target_type="engine",
            total_executions=10,
            success_count=8,
            failure_count=2,
        )
        assert profile.success_rate == 0.8

    def test_success_rate_zero_division(self) -> None:
        profile = ExecutionProfile(target_id="e1", target_type="engine")
        assert profile.success_rate == 0.0

    def test_to_dict(self) -> None:
        profile = ExecutionProfile(target_id="e1", target_type="engine", total_executions=5)
        d = profile.to_dict()
        assert d["target_id"] == "e1"
        assert d["total_executions"] == 5


class TestBenchmarkRecord:
    def test_defaults(self) -> None:
        record = BenchmarkRecord(
            id="b1", target_id="e1", target_type="engine", benchmark_name="latency"
        )
        assert record.score == 0.0
        assert record.capability_coverage == 0.0

    def test_with_score(self) -> None:
        record = BenchmarkRecord(
            id="b1", target_id="e1", target_type="engine", benchmark_name="latency", score=0.5
        )
        updated = record.with_score(score=0.9)
        assert updated.score == 0.9
        assert updated.id == "b1"
        assert updated.latency_ms == 0.0  # unchanged defaults

    def test_to_dict(self) -> None:
        record = BenchmarkRecord(
            id="b1", target_id="e1", target_type="engine", benchmark_name="latency", score=0.85
        )
        d = record.to_dict()
        assert d["score"] == 0.85
        assert d["benchmark_name"] == "latency"


class TestOptimizationRecommendation:
    def test_defaults(self) -> None:
        rec = OptimizationRecommendation(
            id="r1",
            target_id="e1",
            target_type="engine",
            recommendation_type="routing",
            title="Test rec",
        )
        assert rec.applied is False
        assert rec.priority == RecommendationPriority.MEDIUM
        assert rec.applied_at is None

    def test_with_applied(self) -> None:
        rec = OptimizationRecommendation(
            id="r1",
            target_id="e1",
            target_type="engine",
            recommendation_type="routing",
            title="Test rec",
        )
        applied = rec.with_applied()
        assert applied.applied is True
        assert applied.applied_at is not None

    def test_to_dict(self) -> None:
        rec = OptimizationRecommendation(
            id="r1",
            target_id="e1",
            target_type="engine",
            recommendation_type="routing",
            title="Test",
            priority=RecommendationPriority.HIGH,
        )
        d = rec.to_dict()
        assert d["priority"] == "high"


class TestRoutingDecision:
    def test_defaults(self) -> None:
        d = RoutingDecision(id="rd1", task_id="t1", selected_engine_id="e1")
        assert d.alternative_engine_ids == ()
        assert d.confidence == 0.0

    def test_to_dict(self) -> None:
        d = RoutingDecision(
            id="rd1",
            task_id="t1",
            selected_engine_id="e1",
            alternative_engine_ids=("e2", "e3"),
        )
        data = d.to_dict()
        assert data["alternative_engine_ids"] == ["e2", "e3"]


class TestCapabilityScore:
    def test_defaults(self) -> None:
        cs = CapabilityScore(engine_id="e1", capability="math")
        assert cs.score == 0.0
        assert cs.sample_count == 0

    def test_with_score(self) -> None:
        cs = CapabilityScore(engine_id="e1", capability="math")
        updated = cs.with_score(score=0.95, confidence=0.8, sample_count=10)
        assert updated.score == 0.95
        assert updated.sample_count == 10
        assert updated.last_evaluated is not None

    def test_to_dict(self) -> None:
        cs = CapabilityScore(engine_id="e1", capability="math", score=0.9)
        d = cs.to_dict()
        assert d["capability"] == "math"


class TestEnginePerformance:
    def test_defaults(self) -> None:
        perf = EnginePerformance(engine_id="e1")
        assert perf.total_executions == 0
        assert perf.success_rate == 0.0

    def test_success_rate(self) -> None:
        perf = EnginePerformance(engine_id="e1", total_executions=20, success_count=18)
        assert perf.success_rate == 0.9

    def test_to_dict(self) -> None:
        perf = EnginePerformance(engine_id="e1", engine_type="openai", total_executions=10)
        d = perf.to_dict()
        assert d["engine_type"] == "openai"
        assert d["capability_scores"] == []


class TestWorkflowPerformance:
    def test_success_rate(self) -> None:
        perf = WorkflowPerformance(workflow_type="test", total_executions=5, success_count=4)
        assert perf.success_rate == 0.8

    def test_to_dict(self) -> None:
        perf = WorkflowPerformance(workflow_type="test")
        d = perf.to_dict()
        assert d["avg_duration_ms"] == 0.0


class TestSwarmPerformance:
    def test_goal_success_rate(self) -> None:
        perf = SwarmPerformance(swarm_id="s1", total_goals=10, completed_goals=7)
        assert perf.goal_success_rate == 0.7

    def test_to_dict(self) -> None:
        perf = SwarmPerformance(swarm_id="s1")
        d = perf.to_dict()
        assert d["goal_success_rate"] == 0.0


class TestFailurePattern:
    def test_defaults(self) -> None:
        fp = FailurePattern(id="fp1", pattern_type="timeout", target_type="engine", signature="sig")
        assert fp.frequency == 0
        assert fp.common_errors == ()

    def test_to_dict(self) -> None:
        fp = FailurePattern(
            id="fp1",
            pattern_type="timeout",
            target_type="engine",
            signature="sig",
            frequency=5,
            common_errors=("err1", "err2"),
        )
        d = fp.to_dict()
        assert d["common_errors"] == ["err1", "err2"]


class TestRecoveryPattern:
    def test_defaults(self) -> None:
        rp = RecoveryPattern(id="rp1", failure_pattern_id="fp1", strategy="retry")
        assert rp.success_rate == 0.0

    def test_to_dict(self) -> None:
        rp = RecoveryPattern(id="rp1", failure_pattern_id="fp1", strategy="retry")
        d = rp.to_dict()
        assert d["strategy"] == "retry"


class TestLearningSnapshot:
    def test_defaults(self) -> None:
        snap = LearningSnapshot(id="snap-1")
        assert snap.total_experiences == 0

    def test_to_dict(self) -> None:
        snap = LearningSnapshot(id="snap-1", total_experiences=42, total_patterns=7)
        d = snap.to_dict()
        assert d["total_experiences"] == 42


class TestLearningStatistics:
    def test_defaults(self) -> None:
        stats = LearningStatistics()
        assert stats.total_experiences == 0

    def test_to_dict(self) -> None:
        stats = LearningStatistics(
            total_experiences=100,
            total_patterns_detected=10,
            learning_accuracy=0.85,
        )
        d = stats.to_dict()
        assert d["learning_accuracy"] == 0.85


class TestOptimizationPolicy:
    def test_defaults(self) -> None:
        policy = OptimizationPolicy(id="p1", name="default")
        assert policy.goal == OptimizationGoal.BALANCED
        assert policy.enabled is True

    def test_with_updated(self) -> None:
        policy = OptimizationPolicy(id="p1", name="default")
        updated = policy.with_updated(enabled=False, learning_rate=0.2)
        assert updated.enabled is False
        assert updated.learning_rate == 0.2
        assert updated.name == "default"

    def test_to_dict(self) -> None:
        policy = OptimizationPolicy(id="p1", name="default", goal=OptimizationGoal.LATENCY)
        d = policy.to_dict()
        assert d["goal"] == "latency"


class TestPrediction:
    def test_defaults(self) -> None:
        pred = Prediction(
            id="pred-1", target_id="e1", target_type="engine", prediction_type="duration"
        )
        assert pred.confidence == 0.0
        assert pred.prediction_status == PredictionStatus.INSUFFICIENT_DATA
        assert pred.features == {}

    def test_to_dict(self) -> None:
        pred = Prediction(
            id="pred-1",
            target_id="e1",
            target_type="engine",
            prediction_type="duration",
            predicted_value=500.0,
            confidence=0.85,
            prediction_status=PredictionStatus.HIGH_CONFIDENCE,
        )
        d = pred.to_dict()
        assert d["prediction_status"] == "high_confidence"
        assert d["predicted_value"] == 500.0


class TestRecommendation:
    def test_defaults(self) -> None:
        rec = Recommendation(id="rec-1", title="Test")
        assert rec.priority == RecommendationPriority.INFO
        assert rec.applied_at is None

    def test_with_applied(self) -> None:
        rec = Recommendation(id="rec-1", title="Test")
        applied = rec.with_applied()
        assert applied.applied_at is not None

    def test_with_dismissed(self) -> None:
        rec = Recommendation(id="rec-1", title="Test")
        dismissed = rec.with_dismissed()
        assert dismissed.dismissed_at is not None

    def test_to_dict(self) -> None:
        rec = Recommendation(
            id="rec-1",
            title="Optimize",
            priority=RecommendationPriority.HIGH,
        )
        d = rec.to_dict()
        assert d["priority"] == "high"


class TestExperienceRecord:
    def test_defaults(self) -> None:
        exp = ExperienceRecord(id="exp-1", experience_type="execution", source="engine")
        assert exp.reward == 0.0

    def test_to_dict(self) -> None:
        exp = ExperienceRecord(
            id="exp-1",
            experience_type="execution",
            source="engine",
            reward=1.0,
            observation={"duration_ms": 100},
        )
        d = exp.to_dict()
        assert d["reward"] == 1.0


class TestKnowledgePattern:
    def test_defaults(self) -> None:
        kp = KnowledgePattern(id="kp-1", pattern_type="optimization")
        assert kp.confidence == 0.0

    def test_to_dict(self) -> None:
        kp = KnowledgePattern(id="kp-1", pattern_type="optimization", confidence=0.9)
        d = kp.to_dict()
        assert d["confidence"] == 0.9


class TestPerformanceTrend:
    def test_defaults(self) -> None:
        pt = PerformanceTrend(target_id="e1", metric_name="latency")
        assert pt.direction == TrendDirection.UNKNOWN

    def test_to_dict(self) -> None:
        pt = PerformanceTrend(
            target_id="e1",
            metric_name="latency",
            direction=TrendDirection.IMPROVING,
            change_percent=-15.0,
        )
        d = pt.to_dict()
        assert d["direction"] == "improving"
