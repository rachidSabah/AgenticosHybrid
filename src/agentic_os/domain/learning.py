"""Domain models for the Learning & Optimization Engine (Phase 5, v0.9.0).

All models are frozen dataclasses following the same pattern as
:mod:`agentic_os.domain.orchestration` — immutable, with ``to_dict()``
and ``with_*()`` builder methods for state transitions.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


def _utcnow() -> datetime:
    return datetime.now(UTC)


# ── Enums ──


class ExecutionOutcome(StrEnum):
    """Result of an execution attempt."""

    SUCCESS = "success"
    FAILURE = "failure"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    PARTIAL = "partial"


class OptimizationGoal(StrEnum):
    """Target dimension for optimization."""

    LATENCY = "latency"
    COST = "cost"
    QUALITY = "quality"
    RELIABILITY = "reliability"
    EFFICIENCY = "efficiency"
    BALANCED = "balanced"


class RecommendationPriority(StrEnum):
    """Urgency level of a recommendation."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class PredictionStatus(StrEnum):
    """Confidence in a prediction."""

    HIGH_CONFIDENCE = "high_confidence"
    MEDIUM_CONFIDENCE = "medium_confidence"
    LOW_CONFIDENCE = "low_confidence"
    INSUFFICIENT_DATA = "insufficient_data"


class TrendDirection(StrEnum):
    """Direction of a performance trend."""

    IMPROVING = "improving"
    DEGRADING = "degrading"
    STABLE = "stable"
    VOLATILE = "volatile"
    UNKNOWN = "unknown"


# ── Core Models ──


@dataclass(frozen=True)
class ExecutionHistory:
    """Record of a single execution with full metrics."""

    id: str
    target_id: str
    target_type: str  # "engine", "workflow", "swarm", "task"
    outcome: ExecutionOutcome
    duration_ms: float = 0.0
    cpu_percent: float = 0.0
    memory_mb: float = 0.0
    token_count: int = 0
    cost: float = 0.0
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    started_at: datetime = field(default_factory=_utcnow)
    completed_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "target_id": self.target_id,
            "target_type": self.target_type,
            "outcome": self.outcome.value,
            "duration_ms": self.duration_ms,
            "cpu_percent": self.cpu_percent,
            "memory_mb": self.memory_mb,
            "token_count": self.token_count,
            "cost": self.cost,
            "error": self.error,
            "metadata": self.metadata,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


@dataclass(frozen=True)
class ExecutionProfile:
    """Aggregated profile of execution patterns over a window."""

    target_id: str
    target_type: str
    window_hours: int = 24
    total_executions: int = 0
    success_count: int = 0
    failure_count: int = 0
    avg_duration_ms: float = 0.0
    avg_cpu_percent: float = 0.0
    avg_memory_mb: float = 0.0
    avg_token_count: float = 0.0
    avg_cost: float = 0.0
    p50_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    computed_at: datetime = field(default_factory=_utcnow)

    @property
    def success_rate(self) -> float:
        if self.total_executions == 0:
            return 0.0
        return self.success_count / self.total_executions

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_id": self.target_id,
            "target_type": self.target_type,
            "window_hours": self.window_hours,
            "total_executions": self.total_executions,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "success_rate": self.success_rate,
            "avg_duration_ms": self.avg_duration_ms,
            "avg_cpu_percent": self.avg_cpu_percent,
            "avg_memory_mb": self.avg_memory_mb,
            "avg_token_count": self.avg_token_count,
            "avg_cost": self.avg_cost,
            "p50_latency_ms": self.p50_latency_ms,
            "p95_latency_ms": self.p95_latency_ms,
            "p99_latency_ms": self.p99_latency_ms,
            "metadata": self.metadata,
            "computed_at": self.computed_at.isoformat(),
        }


@dataclass(frozen=True)
class BenchmarkRecord:
    """Result of a single benchmark measurement."""

    id: str
    target_id: str
    target_type: str
    benchmark_name: str
    score: float = 0.0
    latency_ms: float = 0.0
    cost: float = 0.0
    reliability: float = 0.0
    memory_mb: float = 0.0
    cpu_percent: float = 0.0
    capability_coverage: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "target_id": self.target_id,
            "target_type": self.target_type,
            "benchmark_name": self.benchmark_name,
            "score": self.score,
            "latency_ms": self.latency_ms,
            "cost": self.cost,
            "reliability": self.reliability,
            "memory_mb": self.memory_mb,
            "cpu_percent": self.cpu_percent,
            "capability_coverage": self.capability_coverage,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }

    def with_score(self, **kwargs: Any) -> BenchmarkRecord:
        return BenchmarkRecord(
            id=self.id,
            target_id=self.target_id,
            target_type=self.target_type,
            benchmark_name=self.benchmark_name,
            score=kwargs.get("score", self.score),
            latency_ms=kwargs.get("latency_ms", self.latency_ms),
            cost=kwargs.get("cost", self.cost),
            reliability=kwargs.get("reliability", self.reliability),
            memory_mb=kwargs.get("memory_mb", self.memory_mb),
            cpu_percent=kwargs.get("cpu_percent", self.cpu_percent),
            capability_coverage=kwargs.get("capability_coverage", self.capability_coverage),
            metadata=kwargs.get("metadata", self.metadata),
            created_at=self.created_at,
        )


@dataclass(frozen=True)
class OptimizationRecommendation:
    """Recommendation for optimizing a specific target."""

    id: str
    target_id: str
    target_type: str
    recommendation_type: str  # "routing", "engine", "swarm", "workflow", "policy"
    title: str
    description: str = ""
    expected_improvement: float = 0.0
    priority: RecommendationPriority = RecommendationPriority.MEDIUM
    confidence: float = 0.0
    parameters: dict[str, Any] = field(default_factory=dict)
    rationale: str = ""
    created_at: datetime = field(default_factory=_utcnow)
    applied_at: datetime | None = None
    applied: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "target_id": self.target_id,
            "target_type": self.target_type,
            "recommendation_type": self.recommendation_type,
            "title": self.title,
            "description": self.description,
            "expected_improvement": self.expected_improvement,
            "priority": self.priority.value,
            "confidence": self.confidence,
            "parameters": self.parameters,
            "rationale": self.rationale,
            "created_at": self.created_at.isoformat(),
            "applied_at": self.applied_at.isoformat() if self.applied_at else None,
            "applied": self.applied,
        }

    def with_applied(self, applied: bool = True) -> OptimizationRecommendation:
        return OptimizationRecommendation(
            id=self.id,
            target_id=self.target_id,
            target_type=self.target_type,
            recommendation_type=self.recommendation_type,
            title=self.title,
            description=self.description,
            expected_improvement=self.expected_improvement,
            priority=self.priority,
            confidence=self.confidence,
            parameters=self.parameters,
            rationale=self.rationale,
            created_at=self.created_at,
            applied_at=_utcnow() if applied else self.applied_at,
            applied=applied,
        )


@dataclass(frozen=True)
class RoutingDecision:
    """Record of a routing decision made by the optimizer."""

    id: str
    task_id: str
    selected_engine_id: str
    alternative_engine_ids: tuple[str, ...] = field(default_factory=tuple)
    routing_reason: str = ""
    expected_latency_ms: float = 0.0
    expected_cost: float = 0.0
    confidence: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "task_id": self.task_id,
            "selected_engine_id": self.selected_engine_id,
            "alternative_engine_ids": list(self.alternative_engine_ids),
            "routing_reason": self.routing_reason,
            "expected_latency_ms": self.expected_latency_ms,
            "expected_cost": self.expected_cost,
            "confidence": self.confidence,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }


@dataclass(frozen=True)
class CapabilityScore:
    """Score for an engine's capability in a specific area."""

    engine_id: str
    capability: str
    score: float = 0.0
    confidence: float = 0.0
    sample_count: int = 0
    last_evaluated: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "engine_id": self.engine_id,
            "capability": self.capability,
            "score": self.score,
            "confidence": self.confidence,
            "sample_count": self.sample_count,
            "last_evaluated": self.last_evaluated.isoformat(),
        }

    def with_score(self, score: float, confidence: float, sample_count: int) -> CapabilityScore:
        return CapabilityScore(
            engine_id=self.engine_id,
            capability=self.capability,
            score=score,
            confidence=confidence,
            sample_count=sample_count,
            last_evaluated=_utcnow(),
        )


@dataclass(frozen=True)
class EnginePerformance:
    """Aggregated performance metrics for a single execution engine."""

    engine_id: str
    engine_type: str = ""
    total_executions: int = 0
    success_count: int = 0
    failure_count: int = 0
    avg_latency_ms: float = 0.0
    avg_cost: float = 0.0
    avg_cpu_percent: float = 0.0
    avg_memory_mb: float = 0.0
    capability_scores: tuple[CapabilityScore, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)
    updated_at: datetime = field(default_factory=_utcnow)

    @property
    def success_rate(self) -> float:
        if self.total_executions == 0:
            return 0.0
        return self.success_count / self.total_executions

    def to_dict(self) -> dict[str, Any]:
        return {
            "engine_id": self.engine_id,
            "engine_type": self.engine_type,
            "total_executions": self.total_executions,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "success_rate": self.success_rate,
            "avg_latency_ms": self.avg_latency_ms,
            "avg_cost": self.avg_cost,
            "avg_cpu_percent": self.avg_cpu_percent,
            "avg_memory_mb": self.avg_memory_mb,
            "capability_scores": [s.to_dict() for s in self.capability_scores],
            "metadata": self.metadata,
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass(frozen=True)
class WorkflowPerformance:
    """Performance metrics for a workflow type."""

    workflow_type: str
    total_executions: int = 0
    success_count: int = 0
    avg_duration_ms: float = 0.0
    avg_cost: float = 0.0
    avg_stage_count: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    updated_at: datetime = field(default_factory=_utcnow)

    @property
    def success_rate(self) -> float:
        if self.total_executions == 0:
            return 0.0
        return self.success_count / self.total_executions

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow_type": self.workflow_type,
            "total_executions": self.total_executions,
            "success_count": self.success_count,
            "success_rate": self.success_rate,
            "avg_duration_ms": self.avg_duration_ms,
            "avg_cost": self.avg_cost,
            "avg_stage_count": self.avg_stage_count,
            "metadata": self.metadata,
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass(frozen=True)
class SwarmPerformance:
    """Performance metrics for swarm orchestration."""

    swarm_id: str
    total_goals: int = 0
    completed_goals: int = 0
    failed_goals: int = 0
    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    avg_goal_duration_ms: float = 0.0
    avg_task_duration_ms: float = 0.0
    avg_agents_per_swarm: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    updated_at: datetime = field(default_factory=_utcnow)

    @property
    def goal_success_rate(self) -> float:
        if self.total_goals == 0:
            return 0.0
        return self.completed_goals / self.total_goals

    def to_dict(self) -> dict[str, Any]:
        return {
            "swarm_id": self.swarm_id,
            "total_goals": self.total_goals,
            "completed_goals": self.completed_goals,
            "failed_goals": self.failed_goals,
            "total_tasks": self.total_tasks,
            "completed_tasks": self.completed_tasks,
            "failed_tasks": self.failed_tasks,
            "goal_success_rate": self.goal_success_rate,
            "avg_goal_duration_ms": self.avg_goal_duration_ms,
            "avg_task_duration_ms": self.avg_task_duration_ms,
            "avg_agents_per_swarm": self.avg_agents_per_swarm,
            "metadata": self.metadata,
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass(frozen=True)
class FailurePattern:
    """Identified pattern in execution failures."""

    id: str
    pattern_type: str  # "timeout", "crash", "resource_exhaustion", "network", "unknown"
    target_type: str  # "engine", "workflow", "swarm", "task"
    signature: str  # Hash/description of the failure signature
    frequency: int = 0
    avg_recovery_time_ms: float = 0.0
    severity: float = 0.0  # 0.0 (low) to 1.0 (critical)
    common_errors: tuple[str, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)
    first_seen: datetime = field(default_factory=_utcnow)
    last_seen: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "pattern_type": self.pattern_type,
            "target_type": self.target_type,
            "signature": self.signature,
            "frequency": self.frequency,
            "avg_recovery_time_ms": self.avg_recovery_time_ms,
            "severity": self.severity,
            "common_errors": list(self.common_errors),
            "metadata": self.metadata,
            "first_seen": self.first_seen.isoformat(),
            "last_seen": self.last_seen.isoformat(),
        }


@dataclass(frozen=True)
class RecoveryPattern:
    """Identified pattern in successful recoveries."""

    id: str
    failure_pattern_id: str
    strategy: str  # "retry", "failover", "reassign", "checkpoint_restore", "reroute"
    success_rate: float = 0.0
    avg_recovery_time_ms: float = 0.0
    application_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "failure_pattern_id": self.failure_pattern_id,
            "strategy": self.strategy,
            "success_rate": self.success_rate,
            "avg_recovery_time_ms": self.avg_recovery_time_ms,
            "application_count": self.application_count,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }


@dataclass(frozen=True)
class LearningSnapshot:
    """Point-in-time snapshot of the learning engine's state."""

    id: str
    total_experiences: int = 0
    total_patterns: int = 0
    total_recommendations: int = 0
    total_benchmarks: int = 0
    profile_count: int = 0
    knowledge_patterns: int = 0
    avg_learning_score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "total_experiences": self.total_experiences,
            "total_patterns": self.total_patterns,
            "total_recommendations": self.total_recommendations,
            "total_benchmarks": self.total_benchmarks,
            "profile_count": self.profile_count,
            "knowledge_patterns": self.knowledge_patterns,
            "avg_learning_score": self.avg_learning_score,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }


@dataclass(frozen=True)
class LearningStatistics:
    """Aggregated statistics about the learning process."""

    total_experiences: int = 0
    total_patterns_detected: int = 0
    total_recommendations_generated: int = 0
    recommendations_applied: int = 0
    avg_improvement_per_recommendation: float = 0.0
    learning_accuracy: float = 0.0
    knowledge_base_size: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    computed_at: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_experiences": self.total_experiences,
            "total_patterns_detected": self.total_patterns_detected,
            "total_recommendations_generated": self.total_recommendations_generated,
            "recommendations_applied": self.recommendations_applied,
            "avg_improvement_per_recommendation": self.avg_improvement_per_recommendation,
            "learning_accuracy": self.learning_accuracy,
            "knowledge_base_size": self.knowledge_base_size,
            "metadata": self.metadata,
            "computed_at": self.computed_at.isoformat(),
        }


@dataclass(frozen=True)
class OptimizationPolicy:
    """Policy configuration that guides optimization behavior."""

    id: str
    name: str
    goal: OptimizationGoal = OptimizationGoal.BALANCED
    enabled: bool = True
    max_execution_cost: float = 0.0  # 0 = unlimited
    max_execution_latency_ms: float = 0.0  # 0 = unlimited
    min_reliability: float = 0.0
    prefer_low_cost: bool = False
    prefer_low_latency: bool = False
    auto_apply_recommendations: bool = False
    learning_rate: float = 0.1
    exploration_rate: float = 0.1
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "goal": self.goal.value,
            "enabled": self.enabled,
            "max_execution_cost": self.max_execution_cost,
            "max_execution_latency_ms": self.max_execution_latency_ms,
            "min_reliability": self.min_reliability,
            "prefer_low_cost": self.prefer_low_cost,
            "prefer_low_latency": self.prefer_low_latency,
            "auto_apply_recommendations": self.auto_apply_recommendations,
            "learning_rate": self.learning_rate,
            "exploration_rate": self.exploration_rate,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    def with_updated(self, **kwargs: Any) -> OptimizationPolicy:
        return OptimizationPolicy(
            id=self.id,
            name=kwargs.get("name", self.name),
            goal=kwargs.get("goal", self.goal),
            enabled=kwargs.get("enabled", self.enabled),
            max_execution_cost=kwargs.get("max_execution_cost", self.max_execution_cost),
            max_execution_latency_ms=kwargs.get(
                "max_execution_latency_ms", self.max_execution_latency_ms
            ),
            min_reliability=kwargs.get("min_reliability", self.min_reliability),
            prefer_low_cost=kwargs.get("prefer_low_cost", self.prefer_low_cost),
            prefer_low_latency=kwargs.get("prefer_low_latency", self.prefer_low_latency),
            auto_apply_recommendations=kwargs.get(
                "auto_apply_recommendations", self.auto_apply_recommendations
            ),
            learning_rate=kwargs.get("learning_rate", self.learning_rate),
            exploration_rate=kwargs.get("exploration_rate", self.exploration_rate),
            metadata=kwargs.get("metadata", self.metadata),
            created_at=self.created_at,
            updated_at=_utcnow(),
        )


@dataclass(frozen=True)
class Prediction:
    """A prediction about future execution characteristics."""

    id: str
    target_id: str
    target_type: str
    prediction_type: (
        str  # "duration", "cost", "success_probability", "failure_probability", "resource_usage"
    )
    predicted_value: float = 0.0
    confidence: float = 0.0
    lower_bound: float = 0.0
    upper_bound: float = 0.0
    prediction_status: PredictionStatus = PredictionStatus.INSUFFICIENT_DATA
    features: dict[str, Any] = field(default_factory=dict)
    model_version: str = ""
    created_at: datetime = field(default_factory=_utcnow)
    valid_until: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "target_id": self.target_id,
            "target_type": self.target_type,
            "prediction_type": self.prediction_type,
            "predicted_value": self.predicted_value,
            "confidence": self.confidence,
            "lower_bound": self.lower_bound,
            "upper_bound": self.upper_bound,
            "prediction_status": self.prediction_status.value,
            "features": self.features,
            "model_version": self.model_version,
            "created_at": self.created_at.isoformat(),
            "valid_until": self.valid_until.isoformat() if self.valid_until else None,
        }


@dataclass(frozen=True)
class Recommendation:
    """Actionable recommendation for the user or system."""

    id: str
    title: str
    description: str = ""
    recommendation_type: str = (
        ""  # "routing", "engine", "swarm", "workflow", "policy", "security", "infrastructure"
    )
    priority: RecommendationPriority = RecommendationPriority.INFO
    expected_benefit: str = ""
    effort: str = ""  # "low", "medium", "high"
    parameters: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utcnow)
    applied_at: datetime | None = None
    dismissed_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "recommendation_type": self.recommendation_type,
            "priority": self.priority.value,
            "expected_benefit": self.expected_benefit,
            "effort": self.effort,
            "parameters": self.parameters,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "applied_at": self.applied_at.isoformat() if self.applied_at else None,
            "dismissed_at": self.dismissed_at.isoformat() if self.dismissed_at else None,
        }

    def with_applied(self) -> Recommendation:
        return Recommendation(
            id=self.id,
            title=self.title,
            description=self.description,
            recommendation_type=self.recommendation_type,
            priority=self.priority,
            expected_benefit=self.expected_benefit,
            effort=self.effort,
            parameters=self.parameters,
            metadata=self.metadata,
            created_at=self.created_at,
            applied_at=_utcnow(),
        )

    def with_dismissed(self) -> Recommendation:
        return Recommendation(
            id=self.id,
            title=self.title,
            description=self.description,
            recommendation_type=self.recommendation_type,
            priority=self.priority,
            expected_benefit=self.expected_benefit,
            effort=self.effort,
            parameters=self.parameters,
            metadata=self.metadata,
            created_at=self.created_at,
            dismissed_at=_utcnow(),
        )


@dataclass(frozen=True)
class ExperienceRecord:
    """Record of a single learning experience."""

    id: str
    experience_type: str  # "execution", "failure", "recovery", "benchmark", "feedback"
    source: str  # Origin of the experience (engine, workflow, swarm)
    observation: dict[str, Any] = field(default_factory=dict)
    outcome: str = ""
    reward: float = 0.0  # Reinforcement learning reward signal
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "experience_type": self.experience_type,
            "source": self.source,
            "observation": self.observation,
            "outcome": self.outcome,
            "reward": self.reward,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }


@dataclass(frozen=True)
class KnowledgePattern:
    """Extracted knowledge pattern from experience analysis."""

    id: str
    pattern_type: str
    description: str = ""
    confidence: float = 0.0
    support_count: int = 0  # Number of experiences supporting this pattern
    conditions: dict[str, Any] = field(default_factory=dict)
    actions: dict[str, Any] = field(default_factory=dict)
    expected_outcome: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utcnow)
    last_verified: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "pattern_type": self.pattern_type,
            "description": self.description,
            "confidence": self.confidence,
            "support_count": self.support_count,
            "conditions": self.conditions,
            "actions": self.actions,
            "expected_outcome": self.expected_outcome,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "last_verified": self.last_verified.isoformat(),
        }


@dataclass(frozen=True)
class PerformanceTrend:
    """Trend information for a performance metric over time."""

    target_id: str
    metric_name: str  # "latency", "cost", "success_rate", "resource_usage"
    direction: TrendDirection = TrendDirection.UNKNOWN
    current_value: float = 0.0
    previous_value: float = 0.0
    change_percent: float = 0.0
    samples_analyzed: int = 0
    window_hours: int = 24
    metadata: dict[str, Any] = field(default_factory=dict)
    computed_at: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_id": self.target_id,
            "metric_name": self.metric_name,
            "direction": self.direction.value,
            "current_value": self.current_value,
            "previous_value": self.previous_value,
            "change_percent": self.change_percent,
            "samples_analyzed": self.samples_analyzed,
            "window_hours": self.window_hours,
            "metadata": self.metadata,
            "computed_at": self.computed_at.isoformat(),
        }
