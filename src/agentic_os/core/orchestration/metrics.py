"""Metrics Engine, Cost Tracker, and Performance Analyzer.

Collects execution metrics, tracks costs per plan/agent/stage, records
timeline entries, and provides performance analysis and reporting.
"""

from collections import deque
from typing import Any

from agentic_os.domain.events import EventEnvelope, Topic
from agentic_os.domain.orchestration import (
    AgentTaskStatus,
    ExecutionCost,
    ExecutionMetrics,
    ExecutionTimeline,
    OrchestrationPlan,
)
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.event_bus import EventBus
from agentic_os.ports.orchestration import CostEstimatorPort, MetricsPort

log = get_logger("orchestration.metrics")


class MetricsEngine(MetricsPort):
    """Collects execution metrics and timeline entries for plans."""

    def __init__(self, bus: EventBus, max_timeline_entries: int = 1000) -> None:
        self._bus = bus
        self._max_timeline = max_timeline_entries
        self._timelines: dict[str, deque[ExecutionTimeline]] = {}
        self._metrics_cache: dict[str, ExecutionMetrics] = {}

    async def collect_metrics(self, plan: OrchestrationPlan) -> ExecutionMetrics:
        """Collect execution metrics for a plan."""
        tasks = plan.subtasks
        total = len(tasks)
        completed = sum(1 for t in tasks if t.status == AgentTaskStatus.COMPLETED)
        failed = sum(1 for t in tasks if t.status == AgentTaskStatus.FAILED)
        skipped = sum(1 for t in tasks if t.status == AgentTaskStatus.CANCELLED)

        # Calculate durations
        durations: list[float] = []
        for t in tasks:
            if t.started_at and t.completed_at:
                delta = (t.completed_at - t.started_at).total_seconds() * 1000
                durations.append(delta)

        metrics = ExecutionMetrics(
            plan_id=plan.id,
            total_tasks=total,
            completed_tasks=completed,
            failed_tasks=failed,
            skipped_tasks=skipped,
            total_duration_ms=sum(durations),
            avg_task_duration_ms=sum(durations) / len(durations) if durations else 0.0,
            max_task_duration_ms=max(durations) if durations else 0.0,
            min_task_duration_ms=min(durations) if durations else 0.0,
            task_durations=tuple(durations),
            retry_count=0,
            checkpoint_count=0,
        )

        self._metrics_cache[plan.id] = metrics

        await self._publish(Topic.ORCH_METRICS_COLLECTED, metrics.to_dict())
        return metrics

    async def record_timeline(self, entry: ExecutionTimeline) -> None:
        """Record a timeline entry."""
        if entry.plan_id not in self._timelines:
            self._timelines[entry.plan_id] = deque(maxlen=self._max_timeline)
        self._timelines[entry.plan_id].append(entry)

    async def get_timeline(self, plan_id: str, limit: int = 100) -> list[ExecutionTimeline]:
        """Get the execution timeline for a plan."""
        entries = list(self._timelines.get(plan_id, []))
        entries.reverse()
        return entries[:limit]

    def get_cached_metrics(self, plan_id: str) -> ExecutionMetrics | None:
        """Get cached metrics for a plan without async collection."""
        return self._metrics_cache.get(plan_id)

    async def _publish(self, topic: Topic, payload: dict[str, Any]) -> None:
        try:
            await self._bus.publish(
                EventEnvelope(
                    type="event", source="metrics-engine", topic=topic.value, payload=payload
                )
            )
        except Exception as exc:
            log.warning("Publish failed", topic=topic.value, error=str(exc))


class CostTracker(CostEstimatorPort):
    """Tracks execution costs per plan, agent, and stage."""

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        self._costs: dict[str, ExecutionCost] = {}

    async def estimate_cost(self, plan: OrchestrationPlan) -> ExecutionCost:
        """Estimate the cost of executing a plan based on task count and complexity."""
        base_cost = 0.01  # $0.01 per task baseline
        estimated = len(plan.subtasks) * base_cost
        cost = ExecutionCost(
            plan_id=plan.id,
            estimated_total=estimated,
            cost_by_agent={},
            cost_by_stage={},
        )
        self._costs[plan.id] = cost
        return cost

    async def track_cost(
        self,
        plan_id: str,
        agent_id: str,
        cost: float,
        stage_id: str | None = None,
    ) -> ExecutionCost:
        """Track actual cost incurred by an agent."""
        current = self._costs.get(plan_id, ExecutionCost(plan_id=plan_id))
        updated = current.with_cost(agent_id, cost)

        if stage_id:
            stage_costs = dict(updated.cost_by_stage)
            stage_costs[stage_id] = stage_costs.get(stage_id, 0.0) + cost
            updated = ExecutionCost(
                plan_id=updated.plan_id,
                total_cost=updated.total_cost,
                cost_by_agent=updated.cost_by_agent,
                cost_by_stage=stage_costs,
                estimated_total=updated.estimated_total,
                currency=updated.currency,
                metadata=updated.metadata,
            )

        self._costs[plan_id] = updated

        await self._publish(
            Topic.ORCH_COST_RECORDED,
            {
                "plan_id": plan_id,
                "agent_id": agent_id,
                "cost": cost,
                "total_cost": updated.total_cost,
            },
        )

        return updated

    async def get_costs(self, plan_id: str) -> ExecutionCost | None:
        """Get accumulated costs for a plan."""
        return self._costs.get(plan_id)

    async def _publish(self, topic: Topic, payload: dict[str, Any]) -> None:
        try:
            await self._bus.publish(
                EventEnvelope(
                    type="event", source="cost-tracker", topic=topic.value, payload=payload
                )
            )
        except Exception as exc:
            log.warning("Publish failed", topic=topic.value, error=str(exc))


class PerformanceAnalyzer:
    """Analyzes execution performance and generates reports."""

    def __init__(self, metrics_engine: MetricsEngine, cost_tracker: CostTracker) -> None:
        self._metrics = metrics_engine
        self._cost_tracker = cost_tracker

    async def analyze_plan(self, plan_id: str) -> dict[str, Any]:
        """Generate a performance analysis report for a plan."""
        metrics = self._metrics.get_cached_metrics(plan_id)
        costs = await self._cost_tracker.get_costs(plan_id)

        if not metrics:
            return {"plan_id": plan_id, "error": "No metrics available"}

        # Calculate success rate
        success_rate = metrics.completed_tasks / max(metrics.total_tasks, 1) * 100

        # Identify bottlenecks (slowest tasks)
        bottleneck_threshold = (
            metrics.avg_task_duration_ms * 2 if metrics.avg_task_duration_ms > 0 else 0
        )
        bottlenecks = []
        for duration in metrics.task_durations:
            if duration > bottleneck_threshold:
                bottlenecks.append(round(duration, 2))

        report: dict[str, Any] = {
            "plan_id": plan_id,
            "success_rate": round(success_rate, 1),
            "total_duration_seconds": round(metrics.total_duration_ms / 1000, 2),
            "avg_task_duration_seconds": round(metrics.avg_task_duration_ms / 1000, 2),
            "completed_ratio": f"{metrics.completed_tasks}/{metrics.total_tasks}",
            "failed_ratio": f"{metrics.failed_tasks}/{metrics.total_tasks}",
            "bottleneck_count": len(bottlenecks),
            "total_cost": costs.total_cost if costs else 0.0,
            "efficiency": round(success_rate / max(metrics.total_duration_ms, 1) * 1000, 4),
        }

        return report
