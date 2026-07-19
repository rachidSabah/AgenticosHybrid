"""Analytics engine — aggregate performance views, trends, and capability scores."""

import math
from collections.abc import Sequence
from datetime import UTC, datetime

from agentic_os.domain.learning import (
    CapabilityScore,
    EnginePerformance,
    ExecutionHistory,
    LearningSnapshot,
    LearningStatistics,
    PerformanceTrend,
    SwarmPerformance,
    TrendDirection,
    WorkflowPerformance,
)
from agentic_os.ports.learning import AnalyticsPort


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _percentile(sorted_values: Sequence[float], pct: float) -> float:
    """Compute the pct-th percentile from a sorted list."""
    if not sorted_values:
        return 0.0
    k = (pct / 100.0) * (len(sorted_values) - 1)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_values[int(k)]
    return sorted_values[f] * (c - k) + sorted_values[c] * (k - f)


class AnalyticsEngine(AnalyticsPort):
    """Aggregates performance metrics, trends, and capability scores.

    Reads from in-memory stores populated by :class:`LearningManager`
    or directly via :meth:`record_execution`.
    """

    def __init__(self) -> None:
        self._engines: dict[str, EnginePerformance] = {}
        self._workflows: dict[str, WorkflowPerformance] = {}
        self._swarms: dict[str, SwarmPerformance] = {}
        self._executions: dict[str, ExecutionHistory] = {}

    def record_execution(self, execution: ExecutionHistory) -> None:
        """Ingest an execution record for aggregation (called by LearningManager)."""
        self._executions[execution.id] = execution
        self._update_engine_performance(execution)
        self._update_workflow_performance(execution)
        self._update_swarm_performance(execution)

    # ── Engine Performance ──

    async def get_engine_performance(self, engine_id: str) -> EnginePerformance | None:
        return self._engines.get(engine_id)

    async def list_engine_performance(
        self,
        engine_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[EnginePerformance]:
        results = sorted(self._engines.values(), key=lambda e: e.total_executions, reverse=True)
        if engine_type is not None:
            results = [e for e in results if e.engine_type == engine_type]
        return results[offset : offset + limit]

    # ── Workflow Performance ──

    async def get_workflow_performance(self, workflow_type: str) -> WorkflowPerformance | None:
        return self._workflows.get(workflow_type)

    async def list_workflow_performance(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[WorkflowPerformance]:
        results = sorted(self._workflows.values(), key=lambda w: w.total_executions, reverse=True)
        return results[offset : offset + limit]

    # ── Swarm Performance ──

    async def get_swarm_performance(self, swarm_id: str) -> SwarmPerformance | None:
        return self._swarms.get(swarm_id)

    async def list_swarm_performance(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[SwarmPerformance]:
        results = sorted(self._swarms.values(), key=lambda s: s.total_goals, reverse=True)
        return results[offset : offset + limit]

    # ── Trends ──

    async def get_performance_trend(
        self,
        target_id: str,
        metric_name: str,
        window_hours: int = 24,
    ) -> PerformanceTrend | None:
        relevant = [e for e in self._executions.values() if e.target_id == target_id]
        if not relevant:
            return None

        window_start = _utcnow().timestamp() - window_hours * 3600
        recent = [e for e in relevant if e.started_at.timestamp() >= window_start]
        older = [e for e in relevant if e.started_at.timestamp() < window_start]

        if not recent:
            return None

        current_value = self._metric_value(recent, metric_name)
        previous_value = self._metric_value(older, metric_name) if older else current_value
        direction = self._compute_direction(current_value, previous_value)

        return PerformanceTrend(
            target_id=target_id,
            metric_name=metric_name,
            direction=direction,
            current_value=current_value,
            previous_value=previous_value,
            change_percent=(((current_value - previous_value) / max(previous_value, 0.001)) * 100),
            samples_analyzed=len(recent),
            window_hours=window_hours,
        )

    async def list_performance_trends(
        self,
        target_id: str,
        window_hours: int = 24,
    ) -> Sequence[PerformanceTrend]:
        metrics = {"latency", "cost", "success_rate", "duration"}
        trends: list[PerformanceTrend] = []
        for metric in metrics:
            trend = await self.get_performance_trend(target_id, metric, window_hours)
            if trend is not None:
                trends.append(trend)
        return trends

    # ── Capability Scores ──

    async def get_capability_scores(self, engine_id: str) -> Sequence[CapabilityScore]:
        engine = self._engines.get(engine_id)
        if engine is None:
            return []
        return engine.capability_scores

    async def get_top_engines(
        self,
        capability: str,
        min_confidence: float = 0.0,
        limit: int = 10,
    ) -> Sequence[EnginePerformance]:
        scored: list[tuple[float, EnginePerformance]] = []
        for engine in self._engines.values():
            for cs in engine.capability_scores:
                if cs.capability == capability and cs.confidence >= min_confidence:
                    scored.append((cs.score, engine))
                    break
        scored.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in scored[:limit]]

    # ── Statistics / Snapshots ──

    async def compute_statistics(self) -> LearningStatistics:
        total_experiences = len(self._executions)
        total_success = sum(1 for e in self._executions.values() if e.outcome.value == "success")
        return LearningStatistics(
            total_experiences=total_experiences,
            total_patterns_detected=0,
            total_recommendations_generated=0,
            recommendations_applied=0,
            avg_improvement_per_recommendation=0.0,
            learning_accuracy=(total_success / total_experiences if total_experiences > 0 else 0.0),
            knowledge_base_size=len(self._engines) + len(self._workflows) + len(self._swarms),
        )

    async def take_snapshot(self) -> LearningSnapshot:
        return LearningSnapshot(
            id=f"snap-{int(_utcnow().timestamp())}",
            total_experiences=len(self._executions),
            total_patterns=0,
            total_benchmarks=0,
            total_recommendations=0,
            profile_count=0,
            knowledge_patterns=0,
            avg_learning_score=0.0,
        )

    # ── Internals ──

    def _update_engine_performance(self, execution: ExecutionHistory) -> None:
        if execution.target_type != "engine":
            return
        perf = self._engines.get(execution.target_id)
        if perf is None:
            perf = EnginePerformance(
                engine_id=execution.target_id,
                engine_type=execution.metadata.get("engine_type", ""),
            )

        updated = EnginePerformance(
            engine_id=perf.engine_id,
            engine_type=perf.engine_type,
            total_executions=perf.total_executions + 1,
            success_count=perf.success_count + (1 if execution.outcome.value == "success" else 0),
            failure_count=perf.failure_count + (1 if execution.outcome.value == "failure" else 0),
            avg_latency_ms=(
                ((perf.avg_latency_ms * perf.total_executions) + execution.duration_ms)
                / (perf.total_executions + 1)
            ),
            avg_cost=(
                ((perf.avg_cost * perf.total_executions) + execution.cost)
                / (perf.total_executions + 1)
            ),
            avg_cpu_percent=(
                ((perf.avg_cpu_percent * perf.total_executions) + execution.cpu_percent)
                / (perf.total_executions + 1)
            ),
            avg_memory_mb=(
                ((perf.avg_memory_mb * perf.total_executions) + execution.memory_mb)
                / (perf.total_executions + 1)
            ),
            capability_scores=perf.capability_scores,
            metadata=perf.metadata,
            updated_at=_utcnow(),
        )
        self._engines[execution.target_id] = updated

    def _update_workflow_performance(self, execution: ExecutionHistory) -> None:
        if execution.target_type != "workflow":
            return
        perf = self._workflows.get(execution.target_id)
        if perf is None:
            perf = WorkflowPerformance(workflow_type=execution.target_id)

        updated = WorkflowPerformance(
            workflow_type=perf.workflow_type,
            total_executions=perf.total_executions + 1,
            success_count=perf.success_count + (1 if execution.outcome.value == "success" else 0),
            avg_duration_ms=(
                ((perf.avg_duration_ms * perf.total_executions) + execution.duration_ms)
                / (perf.total_executions + 1)
            ),
            avg_cost=(
                ((perf.avg_cost * perf.total_executions) + execution.cost)
                / (perf.total_executions + 1)
            ),
            avg_stage_count=perf.avg_stage_count,
            metadata=perf.metadata,
            updated_at=_utcnow(),
        )
        self._workflows[execution.target_id] = updated

    def _update_swarm_performance(self, execution: ExecutionHistory) -> None:
        if execution.target_type != "swarm":
            return
        perf = self._swarms.get(execution.target_id)
        if perf is None:
            perf = SwarmPerformance(swarm_id=execution.target_id)

        updated = SwarmPerformance(
            swarm_id=perf.swarm_id,
            total_goals=perf.total_goals + 1,
            completed_goals=perf.completed_goals
            + (1 if execution.outcome.value == "success" else 0),
            failed_goals=perf.failed_goals + (1 if execution.outcome.value == "failure" else 0),
            total_tasks=perf.total_tasks,
            completed_tasks=perf.completed_tasks,
            failed_tasks=perf.failed_tasks,
            avg_goal_duration_ms=(
                ((perf.avg_goal_duration_ms * perf.total_goals) + execution.duration_ms)
                / (perf.total_goals + 1)
            ),
            avg_task_duration_ms=perf.avg_task_duration_ms,
            avg_agents_per_swarm=perf.avg_agents_per_swarm,
            metadata=perf.metadata,
            updated_at=_utcnow(),
        )
        self._swarms[execution.target_id] = updated

    @staticmethod
    def _metric_value(executions: list[ExecutionHistory], metric: str) -> float:
        if not executions:
            return 0.0
        if metric == "latency" or metric == "duration":
            return _mean([e.duration_ms for e in executions])
        if metric == "cost":
            return _mean([e.cost for e in executions])
        if metric == "success_rate":
            return sum(1 for e in executions if e.outcome.value == "success") / len(executions)
        return 0.0

    @staticmethod
    def _compute_direction(current: float, previous: float) -> TrendDirection:
        if previous == 0:
            return TrendDirection.UNKNOWN
        ratio = current / previous
        if ratio < 0.95:
            return TrendDirection.IMPROVING  # lower latency/cost = improving
        if ratio > 1.05:
            return TrendDirection.DEGRADING
        return TrendDirection.STABLE
