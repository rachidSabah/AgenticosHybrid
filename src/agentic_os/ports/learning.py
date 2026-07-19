"""
Learning & Optimization Engine Port Interfaces

Defines protocol contracts for the Phase 5 learning, prediction, optimization,
recommendation, benchmark, and analytics subsystems.  Domain logic depends on
these interfaces, never on implementations.

Six protocols follow the same pattern as ``ports/orchestration.py``:

- **LearningEnginePort** — record experiences, detect failure/recovery patterns,
  manage the knowledge base
- **OptimizerPort** — analyze performance, generate and apply recommendations,
  manage routing decisions
- **PredictorPort** — predict execution outcomes (duration, cost, success
  probability) from historical data
- **AnalyticsPort** — aggregate performance views, trends, statistics,
  capability scores
- **BenchmarkPort** — run benchmarks, measure scores, compare engines
- **KnowledgeBasePort** — store and query learned patterns and experiences
"""

from collections.abc import Sequence
from typing import Any, Protocol, runtime_checkable

from agentic_os.domain.learning import (
    BenchmarkRecord,
    CapabilityScore,
    EnginePerformance,
    ExecutionHistory,
    ExecutionProfile,
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
from agentic_os.ports.event_bus import EventBus

# ── Analytics Port ──


@runtime_checkable
class AnalyticsPort(Protocol):
    """Aggregate performance views, trends, statistics, and capability scores."""

    async def get_engine_performance(self, engine_id: str) -> EnginePerformance | None:
        """Get aggregated performance metrics for a single engine."""
        ...

    async def list_engine_performance(
        self,
        engine_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[EnginePerformance]:
        """List engine performance records, optionally filtered by type."""
        ...

    async def get_workflow_performance(self, workflow_type: str) -> WorkflowPerformance | None:
        """Get aggregated performance metrics for a workflow type."""
        ...

    async def list_workflow_performance(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[WorkflowPerformance]:
        """List workflow performance records."""
        ...

    async def get_swarm_performance(self, swarm_id: str) -> SwarmPerformance | None:
        """Get aggregated performance metrics for a swarm."""
        ...

    async def list_swarm_performance(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[SwarmPerformance]:
        """List swarm performance records."""
        ...

    async def get_performance_trend(
        self,
        target_id: str,
        metric_name: str,
        window_hours: int = 24,
    ) -> PerformanceTrend | None:
        """Get trend information for a specific metric over time."""
        ...

    async def list_performance_trends(
        self,
        target_id: str,
        window_hours: int = 24,
    ) -> Sequence[PerformanceTrend]:
        """List all available trends for a target."""
        ...

    async def get_capability_scores(self, engine_id: str) -> Sequence[CapabilityScore]:
        """Get capability scores for an engine."""
        ...

    async def get_top_engines(
        self,
        capability: str,
        min_confidence: float = 0.0,
        limit: int = 10,
    ) -> Sequence[EnginePerformance]:
        """Get top-performing engines for a capability."""
        ...

    async def compute_statistics(self) -> LearningStatistics:
        """Compute aggregate learning statistics across all data."""
        ...

    async def take_snapshot(self) -> LearningSnapshot:
        """Take a point-in-time snapshot of the learning state."""
        ...


# ── Benchmark Port ──


@runtime_checkable
class BenchmarkPort(Protocol):
    """Run benchmarks, measure scores, compare engines."""

    async def run_benchmark(
        self,
        target_id: str,
        target_type: str,
        benchmark_name: str,
        bus: EventBus | None = None,
    ) -> BenchmarkRecord:
        """Run a benchmark against a target and return measurements."""
        ...

    async def get_benchmark(self, benchmark_id: str) -> BenchmarkRecord | None:
        """Get a benchmark record by ID."""
        ...

    async def list_benchmarks(
        self,
        target_id: str | None = None,
        benchmark_name: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[BenchmarkRecord]:
        """List benchmark records, optionally filtered."""
        ...

    async def compare_engines(
        self,
        engine_ids: Sequence[str],
        benchmark_name: str,
    ) -> dict[str, BenchmarkRecord]:
        """Compare multiple engines on the same benchmark."""
        ...

    async def get_benchmark_history(
        self,
        target_id: str,
        benchmark_name: str,
        limit: int = 20,
    ) -> Sequence[BenchmarkRecord]:
        """Get historical benchmark results for a target."""
        ...

    async def get_top_scores(
        self,
        benchmark_name: str,
        limit: int = 10,
    ) -> Sequence[BenchmarkRecord]:
        """Get top scores for a benchmark across all targets."""
        ...


# ── Prediction Port ──


@runtime_checkable
class PredictorPort(Protocol):
    """Predict execution outcomes from historical data."""

    async def predict_execution(
        self,
        target_id: str,
        target_type: str,
        features: dict[str, Any] | None = None,
    ) -> Prediction:
        """Predict execution characteristics (duration, cost, success)."""
        ...

    async def predict_duration(
        self,
        target_id: str,
        target_type: str,
        features: dict[str, Any] | None = None,
    ) -> Prediction:
        """Predict execution duration for a target."""
        ...

    async def predict_cost(
        self,
        target_id: str,
        target_type: str,
        features: dict[str, Any] | None = None,
    ) -> Prediction:
        """Predict execution cost for a target."""
        ...

    async def predict_success_probability(
        self,
        target_id: str,
        target_type: str,
        features: dict[str, Any] | None = None,
    ) -> Prediction:
        """Predict the probability of successful execution."""
        ...

    async def predict_resource_usage(
        self,
        target_id: str,
        target_type: str,
        features: dict[str, Any] | None = None,
    ) -> Prediction:
        """Predict resource usage (CPU, memory) for an execution."""
        ...

    async def get_prediction(self, prediction_id: str) -> Prediction | None:
        """Get a prediction by ID."""
        ...

    async def list_predictions(
        self,
        target_id: str | None = None,
        prediction_type: str | None = None,
        limit: int = 50,
    ) -> Sequence[Prediction]:
        """List predictions, optionally filtered."""
        ...

    async def batched_predict(
        self,
        target_ids: Sequence[str],
        target_type: str,
        prediction_type: str = "duration",
        features: dict[str, Any] | None = None,
    ) -> dict[str, Prediction]:
        """Predict for multiple targets at once."""
        ...


# ── Optimizer Port ──


@runtime_checkable
class OptimizerPort(Protocol):
    """Analyze performance, generate and apply recommendations, manage routing."""

    async def analyze_performance(
        self, target_id: str, target_type: str
    ) -> Sequence[OptimizationRecommendation]:
        """Analyze performance of a target and generate recommendations."""
        ...

    async def optimize_routing(
        self,
        task_id: str,
        required_capabilities: Sequence[str],
        available_engines: Sequence[str],
    ) -> RoutingDecision:
        """Optimize routing decision for a task across available engines."""
        ...

    async def generate_recommendations(
        self,
        target_id: str,
        target_type: str,
        limit: int = 10,
    ) -> Sequence[Recommendation]:
        """Generate actionable recommendations for a target."""
        ...

    async def get_recommendation(self, recommendation_id: str) -> Recommendation | None:
        """Get a recommendation by ID."""
        ...

    async def list_recommendations(
        self,
        target_id: str | None = None,
        recommendation_type: str | None = None,
        priority: str | None = None,
        applied: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[Recommendation]:
        """List recommendations with optional filters."""
        ...

    async def apply_recommendation(self, recommendation_id: str) -> Recommendation:
        """Apply a recommendation (mark as applied)."""
        ...

    async def dismiss_recommendation(self, recommendation_id: str) -> Recommendation:
        """Dismiss a recommendation without applying."""
        ...

    async def get_routing_history(
        self,
        task_id: str | None = None,
        limit: int = 50,
    ) -> Sequence[RoutingDecision]:
        """Get routing decision history."""
        ...

    async def get_optimization_policy(self, policy_id: str) -> OptimizationPolicy | None:
        """Get an optimization policy by ID."""
        ...

    async def list_optimization_policies(self, limit: int = 50) -> Sequence[OptimizationPolicy]:
        """List all optimization policies."""
        ...

    async def create_optimization_policy(self, policy: OptimizationPolicy) -> OptimizationPolicy:
        """Create a new optimization policy."""
        ...

    async def update_optimization_policy(
        self, policy_id: str, policy: OptimizationPolicy
    ) -> OptimizationPolicy:
        """Update an existing optimization policy."""
        ...

    async def delete_optimization_policy(self, policy_id: str) -> bool:
        """Delete an optimization policy."""
        ...


# ── Learning Engine Port ──


@runtime_checkable
class LearningEnginePort(Protocol):
    """Core learning: record experiences, detect patterns, manage knowledge."""

    async def record_execution(self, execution: ExecutionHistory) -> ExecutionHistory:
        """Record an execution in the learning history."""
        ...

    async def get_execution(self, execution_id: str) -> ExecutionHistory | None:
        """Get an execution record by ID."""
        ...

    async def list_executions(
        self,
        target_id: str | None = None,
        target_type: str | None = None,
        outcome: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[ExecutionHistory]:
        """List execution records with optional filters."""
        ...

    async def get_execution_profile(
        self,
        target_id: str,
        target_type: str,
        window_hours: int = 24,
    ) -> ExecutionProfile:
        """Get or compute an execution profile for a target."""
        ...

    async def detect_failure_patterns(
        self,
        target_id: str | None = None,
        min_frequency: int = 2,
    ) -> Sequence[FailurePattern]:
        """Detect failure patterns from execution history."""
        ...

    async def get_failure_pattern(self, pattern_id: str) -> FailurePattern | None:
        """Get a failure pattern by ID."""
        ...

    async def list_failure_patterns(
        self,
        target_type: str | None = None,
        pattern_type: str | None = None,
        limit: int = 50,
    ) -> Sequence[FailurePattern]:
        """List failure patterns with optional filters."""
        ...

    async def detect_recovery_patterns(
        self,
        failure_pattern_id: str | None = None,
    ) -> Sequence[RecoveryPattern]:
        """Detect recovery patterns from execution history."""
        ...

    async def get_recovery_pattern(self, pattern_id: str) -> RecoveryPattern | None:
        """Get a recovery pattern by ID."""
        ...

    async def list_recovery_patterns(
        self,
        strategy: str | None = None,
        limit: int = 50,
    ) -> Sequence[RecoveryPattern]:
        """List recovery patterns with optional filters."""
        ...

    async def record_experience(self, experience: Any) -> Any:
        """Record a raw learning experience for analysis."""
        ...

    async def extract_knowledge(
        self,
        pattern_type: str | None = None,
        min_confidence: float = 0.5,
    ) -> Sequence[KnowledgePattern]:
        """Extract knowledge patterns from recorded experiences."""
        ...

    async def get_knowledge_pattern(self, pattern_id: str) -> KnowledgePattern | None:
        """Get a knowledge pattern by ID."""
        ...

    async def list_knowledge_patterns(
        self,
        pattern_type: str | None = None,
        min_confidence: float = 0.0,
        limit: int = 50,
    ) -> Sequence[KnowledgePattern]:
        """List knowledge patterns with optional filters."""
        ...

    async def clear_history(self, older_than_hours: int = 0) -> int:
        """Clear execution history, optionally older than N hours. Returns count."""
        ...


# ── Knowledge Base Port ──


@runtime_checkable
class KnowledgeBasePort(Protocol):
    """Store and query learned patterns and experiences."""

    async def store_pattern(self, pattern: KnowledgePattern) -> KnowledgePattern:
        """Store a knowledge pattern."""
        ...

    async def get_pattern(self, pattern_id: str) -> KnowledgePattern | None:
        """Get a knowledge pattern by ID."""
        ...

    async def query_patterns(
        self,
        query: dict[str, Any],
        min_confidence: float = 0.0,
        limit: int = 20,
    ) -> Sequence[KnowledgePattern]:
        """Query patterns by conditions or metadata."""
        ...

    async def store_experience(self, experience: Any) -> Any:
        """Store a raw experience record."""
        ...

    async def query_experiences(
        self,
        query: dict[str, Any],
        limit: int = 50,
    ) -> Sequence[Any]:
        """Query experiences by conditions or metadata."""
        ...

    async def get_statistics(self) -> LearningStatistics:
        """Get aggregate statistics about the knowledge base."""
        ...

    async def prune(self, older_than_days: int = 90, min_confidence: float = 0.1) -> int:
        """Remove old or low-confidence patterns. Returns count removed."""
        ...
