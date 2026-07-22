"""
Learning & Optimization Domain Models

Domain layer for Phase 4 Milestone 5 — Learning & Optimization Engine.
Pure Python, no external dependencies.

Every learning, optimization, benchmark, experiment, recommendation, and evaluation
model lives here. The engine learns from historical executions and optimizes
routing, engine selection, swarm strategies, costs, and quality.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4


def _utcnow() -> datetime:
    return datetime.now(UTC)


# ── Enums ──


class LearningPhase(StrEnum):
    DATA_COLLECTION = "data_collection"
    TRAINING = "training"
    EVALUATION = "evaluation"
    DEPLOYMENT = "deployment"
    MONITORING = "monitoring"


class OptimizationTarget(StrEnum):
    ROUTING = "routing"
    ENGINE_SELECTION = "engine_selection"
    SWARM_COMPOSITION = "swarm_composition"
    PLANNER_SELECTION = "planner_selection"
    VALIDATOR_SELECTION = "validator_selection"
    CONSENSUS_STRATEGY = "consensus_strategy"
    RETRY_POLICY = "retry_policy"
    PARALLELISM = "parallelism"
    SCHEDULING = "scheduling"
    CHECKPOINT_FREQUENCY = "checkpoint_frequency"
    MEMORY_USAGE = "memory_usage"
    PROMPT_SELECTION = "prompt_selection"
    EXECUTION_COST = "execution_cost"
    RESPONSE_QUALITY = "response_quality"


class OptimizationStatus(StrEnum):
    PENDING = "pending"
    APPLIED = "applied"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"
    REVERTED = "reverted"


class RecommendationStatus(StrEnum):
    ACTIVE = "active"
    APPLIED = "applied"
    DISMISSED = "dismissed"
    SUPERSEDED = "superseded"


class BenchmarkStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ExperimentStatus(StrEnum):
    DRAFT = "draft"
    RUNNING = "running"
    COMPLETED = "completed"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


class ExperimentType(StrEnum):
    A_B_TEST = "a_b_test"
    CANARY = "canary"
    CONTROLLED_ROLLOUT = "controlled_rollout"
    PERFORMANCE = "performance"
    ROUTING = "routing"
    PROMPT = "prompt"
    BENCHMARK = "benchmark"


class PolicyEffect(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"
    LOG_ONLY = "log_only"


class LearningMetric(StrEnum):
    EXECUTION_LATENCY = "execution_latency"
    FAILURE_RATE = "failure_rate"
    RESOURCE_USAGE = "resource_usage"
    TASK_SUCCESS_RATE = "task_success_rate"
    RETRY_COUNT = "retry_count"
    CAPABILITY_UTILIZATION = "capability_utilization"
    COST_PER_EXECUTION = "cost_per_execution"
    RESPONSE_QUALITY = "response_quality"
    USER_SATISFACTION = "user_satisfaction"


class TelemetryGranularity(StrEnum):
    PER_EXECUTION = "per_execution"
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"


# ── Domain Models ──


@dataclass(frozen=True)
class LearningProfile:
    """Configuration profile for a learning session."""

    id: str = field(default_factory=lambda: uuid4().hex)
    name: str = ""
    description: str = ""
    targets: tuple[OptimizationTarget, ...] = field(default_factory=tuple)
    metrics: tuple[LearningMetric, ...] = field(default_factory=tuple)
    enabled: bool = True
    telemetry_granularity: TelemetryGranularity = TelemetryGranularity.HOURLY
    max_history_size: int = 10000
    min_confidence: float = 0.6
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "targets": [t.value for t in self.targets],
            "metrics": [m.value for m in self.metrics],
            "enabled": self.enabled,
            "telemetry_granularity": self.telemetry_granularity.value,
            "max_history_size": self.max_history_size,
            "min_confidence": self.min_confidence,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass(frozen=True)
class ExecutionHistory:
    """Record of a single historical execution for analysis."""

    id: str = field(default_factory=lambda: uuid4().hex)
    execution_id: str = ""
    engine_type: str = ""
    engine_name: str = ""
    task_type: str = ""
    status: str = ""
    duration_ms: float = 0.0
    cost: float = 0.0
    retry_count: int = 0
    resource_usage: dict[str, float] = field(default_factory=dict)
    error_type: str | None = None
    swarm_id: str | None = None
    plan_id: str | None = None
    model_used: str | None = None
    prompt_template: str | None = None
    user_id: str | None = None
    workspace_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    executed_at: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "execution_id": self.execution_id,
            "engine_type": self.engine_type,
            "engine_name": self.engine_name,
            "task_type": self.task_type,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "cost": self.cost,
            "retry_count": self.retry_count,
            "resource_usage": dict(self.resource_usage),
            "error_type": self.error_type,
            "swarm_id": self.swarm_id,
            "plan_id": self.plan_id,
            "model_used": self.model_used,
            "prompt_template": self.prompt_template,
            "user_id": self.user_id,
            "workspace_id": self.workspace_id,
            "metadata": dict(self.metadata),
            "executed_at": self.executed_at.isoformat(),
        }


@dataclass(frozen=True)
class OptimizationPolicy:
    """Policy that governs what optimizations are allowed."""

    id: str = field(default_factory=lambda: uuid4().hex)
    name: str = ""
    description: str = ""
    target: OptimizationTarget | None = None
    effect: PolicyEffect = PolicyEffect.ALLOW
    conditions: dict[str, Any] = field(default_factory=dict)
    priority: int = 0
    enabled: bool = True
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "target": self.target.value if self.target else None,
            "effect": self.effect.value,
            "conditions": dict(self.conditions),
            "priority": self.priority,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass(frozen=True)
class OptimizationRecommendation:
    """A recommendation produced by the optimization engine."""

    id: str = field(default_factory=lambda: uuid4().hex)
    target: OptimizationTarget | None = None
    current_value: str = ""
    recommended_value: str = ""
    confidence: float = 0.0
    supporting_evidence: str = ""
    historical_data: dict[str, Any] = field(default_factory=dict)
    alternatives: tuple[str, ...] = field(default_factory=tuple)
    estimated_improvement: float = 0.0
    status: RecommendationStatus = RecommendationStatus.ACTIVE
    source: str = ""
    created_at: datetime = field(default_factory=_utcnow)
    applied_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "target": self.target.value if self.target else None,
            "current_value": self.current_value,
            "recommended_value": self.recommended_value,
            "confidence": self.confidence,
            "supporting_evidence": self.supporting_evidence,
            "historical_data": dict(self.historical_data),
            "alternatives": list(self.alternatives),
            "estimated_improvement": self.estimated_improvement,
            "status": self.status.value,
            "source": self.source,
            "created_at": self.created_at.isoformat(),
            "applied_at": self.applied_at.isoformat() if self.applied_at else None,
        }


@dataclass(frozen=True)
class RoutingDecision:
    """Record of a routing decision made by the optimizer."""

    id: str = field(default_factory=lambda: uuid4().hex)
    execution_id: str = ""
    selected_engine: str = ""
    alternative_engines: tuple[str, ...] = field(default_factory=tuple)
    selection_reason: str = ""
    confidence: float = 0.0
    expected_latency_ms: float = 0.0
    expected_cost: float = 0.0
    actual_latency_ms: float | None = None
    actual_cost: float | None = None
    success: bool | None = None
    created_at: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "execution_id": self.execution_id,
            "selected_engine": self.selected_engine,
            "alternative_engines": list(self.alternative_engines),
            "selection_reason": self.selection_reason,
            "confidence": self.confidence,
            "expected_latency_ms": self.expected_latency_ms,
            "expected_cost": self.expected_cost,
            "actual_latency_ms": self.actual_latency_ms,
            "actual_cost": self.actual_cost,
            "success": self.success,
            "created_at": self.created_at.isoformat(),
        }


@dataclass(frozen=True)
class Benchmark:
    """A benchmark run comparing engines, strategies, or configurations."""

    id: str = field(default_factory=lambda: uuid4().hex)
    name: str = ""
    description: str = ""
    targets: tuple[str, ...] = field(default_factory=tuple)
    metrics: tuple[LearningMetric, ...] = field(default_factory=tuple)
    iterations: int = 10
    status: BenchmarkStatus = BenchmarkStatus.PENDING
    results: dict[str, dict[str, float]] = field(default_factory=dict)
    winner: str | None = None
    report: str = ""
    created_at: datetime = field(default_factory=_utcnow)
    completed_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "targets": list(self.targets),
            "metrics": [m.value for m in self.metrics],
            "iterations": self.iterations,
            "status": self.status.value,
            "results": {k: dict(v) for k, v in self.results.items()},
            "winner": self.winner,
            "report": self.report,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


@dataclass(frozen=True)
class Evaluation:
    """Evaluation of an engine, strategy, or optimization result."""

    id: str = field(default_factory=lambda: uuid4().hex)
    target_id: str = ""
    target_type: str = ""
    score: float = 0.0
    metrics: dict[str, float] = field(default_factory=dict)
    passed: bool = False
    details: str = ""
    evaluated_at: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "target_id": self.target_id,
            "target_type": self.target_type,
            "score": self.score,
            "metrics": dict(self.metrics),
            "passed": self.passed,
            "details": self.details,
            "evaluated_at": self.evaluated_at.isoformat(),
        }


@dataclass(frozen=True)
class Experiment:
    """A controlled experiment comparing two or more configurations."""

    id: str = field(default_factory=lambda: uuid4().hex)
    name: str = ""
    description: str = ""
    experiment_type: ExperimentType = ExperimentType.A_B_TEST
    control_config: dict[str, Any] = field(default_factory=dict)
    treatment_config: dict[str, Any] = field(default_factory=dict)
    status: ExperimentStatus = ExperimentStatus.DRAFT
    winner: str | None = None
    metrics: dict[str, dict[str, float]] = field(default_factory=dict)
    confidence: float = 0.0
    rollback_on_regression: bool = True
    created_at: datetime = field(default_factory=_utcnow)
    completed_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "experiment_type": self.experiment_type.value,
            "control_config": dict(self.control_config),
            "treatment_config": dict(self.treatment_config),
            "status": self.status.value,
            "winner": self.winner,
            "metrics": {k: dict(v) for k, v in self.metrics.items()},
            "confidence": self.confidence,
            "rollback_on_regression": self.rollback_on_regression,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


@dataclass(frozen=True)
class PerformanceProfile:
    """Performance characteristics of an engine, provider, or strategy."""

    id: str = field(default_factory=lambda: uuid4().hex)
    target_id: str = ""
    target_type: str = ""
    avg_latency_ms: float = 0.0
    p50_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    avg_cost: float = 0.0
    success_rate: float = 0.0
    throughput: float = 0.0
    sample_count: int = 0
    profiled_at: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "target_id": self.target_id,
            "target_type": self.target_type,
            "avg_latency_ms": self.avg_latency_ms,
            "p50_latency_ms": self.p50_latency_ms,
            "p95_latency_ms": self.p95_latency_ms,
            "p99_latency_ms": self.p99_latency_ms,
            "avg_cost": self.avg_cost,
            "success_rate": self.success_rate,
            "throughput": self.throughput,
            "sample_count": self.sample_count,
            "profiled_at": self.profiled_at.isoformat(),
        }


@dataclass(frozen=True)
class LearningMetrics:
    """Aggregated learning metrics snapshot."""

    id: str = field(default_factory=lambda: uuid4().hex)
    total_executions: int = 0
    total_optimizations: int = 0
    total_recommendations: int = 0
    average_improvement: float = 0.0
    success_rate: float = 0.0
    optimization_effectiveness: float = 0.0
    recommendation_accuracy: float = 0.0
    period_start: datetime | None = None
    period_end: datetime | None = None
    created_at: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "total_executions": self.total_executions,
            "total_optimizations": self.total_optimizations,
            "total_recommendations": self.total_recommendations,
            "average_improvement": self.average_improvement,
            "success_rate": self.success_rate,
            "optimization_effectiveness": self.optimization_effectiveness,
            "recommendation_accuracy": self.recommendation_accuracy,
            "period_start": self.period_start.isoformat() if self.period_start else None,
            "period_end": self.period_end.isoformat() if self.period_end else None,
            "created_at": self.created_at.isoformat(),
        }


@dataclass(frozen=True)
class ExecutionStatistics:
    """Statistical breakdown of execution performance."""

    id: str = field(default_factory=lambda: uuid4().hex)
    total_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    avg_duration_ms: float = 0.0
    min_duration_ms: float = 0.0
    max_duration_ms: float = 0.0
    total_retries: int = 0
    by_engine: dict[str, int] = field(default_factory=dict)
    by_status: dict[str, int] = field(default_factory=dict)
    by_error_type: dict[str, int] = field(default_factory=dict)
    period_start: datetime | None = None
    period_end: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "total_count": self.total_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "avg_duration_ms": self.avg_duration_ms,
            "min_duration_ms": self.min_duration_ms,
            "max_duration_ms": self.max_duration_ms,
            "total_retries": self.total_retries,
            "by_engine": dict(self.by_engine),
            "by_status": dict(self.by_status),
            "by_error_type": dict(self.by_error_type),
            "period_start": self.period_start.isoformat() if self.period_start else None,
            "period_end": self.period_end.isoformat() if self.period_end else None,
        }


@dataclass(frozen=True)
class CostMetrics:
    """Cost tracking and optimization metrics."""

    id: str = field(default_factory=lambda: uuid4().hex)
    total_cost: float = 0.0
    avg_cost_per_execution: float = 0.0
    cost_by_engine: dict[str, float] = field(default_factory=dict)
    cost_by_provider: dict[str, float] = field(default_factory=dict)
    estimated_savings: float = 0.0
    period_start: datetime | None = None
    period_end: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "total_cost": self.total_cost,
            "avg_cost_per_execution": self.avg_cost_per_execution,
            "cost_by_engine": dict(self.cost_by_engine),
            "cost_by_provider": dict(self.cost_by_provider),
            "estimated_savings": self.estimated_savings,
            "period_start": self.period_start.isoformat() if self.period_start else None,
            "period_end": self.period_end.isoformat() if self.period_end else None,
        }


@dataclass(frozen=True)
class LatencyMetrics:
    """Latency tracking and optimization metrics."""

    id: str = field(default_factory=lambda: uuid4().hex)
    avg_latency_ms: float = 0.0
    p50_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    latency_by_engine: dict[str, float] = field(default_factory=dict)
    latency_by_provider: dict[str, float] = field(default_factory=dict)
    improvement_pct: float = 0.0
    period_start: datetime | None = None
    period_end: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "avg_latency_ms": self.avg_latency_ms,
            "p50_latency_ms": self.p50_latency_ms,
            "p95_latency_ms": self.p95_latency_ms,
            "p99_latency_ms": self.p99_latency_ms,
            "latency_by_engine": dict(self.latency_by_engine),
            "latency_by_provider": dict(self.latency_by_provider),
            "improvement_pct": self.improvement_pct,
            "period_start": self.period_start.isoformat() if self.period_start else None,
            "period_end": self.period_end.isoformat() if self.period_end else None,
        }


@dataclass(frozen=True)
class QualityMetrics:
    """Quality assessment metrics."""

    id: str = field(default_factory=lambda: uuid4().hex)
    avg_quality_score: float = 0.0
    min_quality_score: float = 0.0
    max_quality_score: float = 0.0
    quality_by_engine: dict[str, float] = field(default_factory=dict)
    quality_by_provider: dict[str, float] = field(default_factory=dict)
    improvement_pct: float = 0.0
    period_start: datetime | None = None
    period_end: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "avg_quality_score": self.avg_quality_score,
            "min_quality_score": self.min_quality_score,
            "max_quality_score": self.max_quality_score,
            "quality_by_engine": dict(self.quality_by_engine),
            "quality_by_provider": dict(self.quality_by_provider),
            "improvement_pct": self.improvement_pct,
            "period_start": self.period_start.isoformat() if self.period_start else None,
            "period_end": self.period_end.isoformat() if self.period_end else None,
        }


@dataclass(frozen=True)
class FailureAnalysis:
    """Analysis of execution failures and their root causes."""

    id: str = field(default_factory=lambda: uuid4().hex)
    total_failures: int = 0
    failure_rate: float = 0.0
    top_error_types: dict[str, int] = field(default_factory=dict)
    top_failing_engines: dict[str, int] = field(default_factory=dict)
    recovery_success_rate: float = 0.0
    common_patterns: tuple[str, ...] = field(default_factory=tuple)
    recommendations: tuple[str, ...] = field(default_factory=tuple)
    period_start: datetime | None = None
    period_end: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "total_failures": self.total_failures,
            "failure_rate": self.failure_rate,
            "top_error_types": dict(self.top_error_types),
            "top_failing_engines": dict(self.top_failing_engines),
            "recovery_success_rate": self.recovery_success_rate,
            "common_patterns": list(self.common_patterns),
            "recommendations": list(self.recommendations),
            "period_start": self.period_start.isoformat() if self.period_start else None,
            "period_end": self.period_end.isoformat() if self.period_end else None,
        }


@dataclass(frozen=True)
class OptimizationResult:
    """Result of applying an optimization."""

    id: str = field(default_factory=lambda: uuid4().hex)
    recommendation_id: str = ""
    target: OptimizationTarget | None = None
    previous_value: str = ""
    new_value: str = ""
    status: OptimizationStatus = OptimizationStatus.PENDING
    improvement_pct: float = 0.0
    metrics_before: dict[str, float] = field(default_factory=dict)
    metrics_after: dict[str, float] = field(default_factory=dict)
    applied_at: datetime | None = None
    rolled_back_at: datetime | None = None
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "recommendation_id": self.recommendation_id,
            "target": self.target.value if self.target else None,
            "previous_value": self.previous_value,
            "new_value": self.new_value,
            "status": self.status.value,
            "improvement_pct": self.improvement_pct,
            "metrics_before": dict(self.metrics_before),
            "metrics_after": dict(self.metrics_after),
            "applied_at": self.applied_at.isoformat() if self.applied_at else None,
            "rolled_back_at": self.rolled_back_at.isoformat() if self.rolled_back_at else None,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class Recommendation:
    """A general recommendation from the recommendation engine."""

    id: str = field(default_factory=lambda: uuid4().hex)
    category: str = ""
    title: str = ""
    description: str = ""
    confidence: float = 0.0
    evidence: str = ""
    alternatives: tuple[str, ...] = field(default_factory=tuple)
    status: RecommendationStatus = RecommendationStatus.ACTIVE
    source: str = ""
    created_at: datetime = field(default_factory=_utcnow)
    applied_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category,
            "title": self.title,
            "description": self.description,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "alternatives": list(self.alternatives),
            "status": self.status.value,
            "source": self.source,
            "created_at": self.created_at.isoformat(),
            "applied_at": self.applied_at.isoformat() if self.applied_at else None,
        }


__all__ = [
    "LearningPhase",
    "OptimizationTarget",
    "OptimizationStatus",
    "RecommendationStatus",
    "BenchmarkStatus",
    "ExperimentStatus",
    "ExperimentType",
    "PolicyEffect",
    "LearningMetric",
    "TelemetryGranularity",
    "LearningProfile",
    "ExecutionHistory",
    "OptimizationPolicy",
    "OptimizationRecommendation",
    "RoutingDecision",
    "Benchmark",
    "Evaluation",
    "Experiment",
    "PerformanceProfile",
    "LearningMetrics",
    "ExecutionStatistics",
    "CostMetrics",
    "LatencyMetrics",
    "QualityMetrics",
    "FailureAnalysis",
    "OptimizationResult",
    "Recommendation",
]
