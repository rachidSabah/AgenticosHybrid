"""Orchestration Telemetry — records orchestration history and metrics.

Provides an in-memory ring buffer for orchestration events, aggregators
for common queries, and per-agent/per-swarm statistics.
"""

from collections import deque
from typing import Any

from agentic_os.domain.orchestration import (
    AgentTask,
    ConsensusResult,
    OrchestrationGoal,
    OrchestrationTelemetryEntry,
)
from agentic_os.infrastructure.logging import get_logger

log = get_logger("orchestration.telemetry")


class OrchestrationTelemetry:
    """Records orchestration lifecycle events and provides aggregate metrics.

    Maintains an in-memory ring buffer of telemetry entries (oldest entries
    are dropped when the limit is reached).
    """

    def __init__(self, max_entries: int = 500) -> None:
        self._max_entries = max_entries
        self._entries: deque[OrchestrationTelemetryEntry] = deque(maxlen=max_entries)

    # ── Recording ──

    def record(
        self,
        event_type: str,
        swarm_id: str | None = None,
        goal_id: str | None = None,
        task_id: str | None = None,
        agent_id: str | None = None,
        duration_ms: float = 0.0,
        status: str = "",
        details: dict[str, Any] | None = None,
    ) -> OrchestrationTelemetryEntry:
        """Record a telemetry entry."""
        entry = OrchestrationTelemetryEntry(
            event_type=event_type,
            swarm_id=swarm_id,
            goal_id=goal_id,
            task_id=task_id,
            agent_id=agent_id,
            duration_ms=duration_ms,
            status=status,
            details=details or {},
        )
        self._entries.append(entry)
        return entry

    def record_task(self, task: AgentTask) -> OrchestrationTelemetryEntry:
        """Record a task lifecycle event."""
        return self.record(
            event_type=f"task.{task.status.value}",
            goal_id=task.goal_id,
            task_id=task.id,
            agent_id=task.assigned_agent_id,
            status=task.status.value,
            details={"title": task.title, "error": task.error}
            if task.error
            else {"title": task.title},
        )

    def record_goal(self, goal: OrchestrationGoal) -> OrchestrationTelemetryEntry:
        """Record a goal lifecycle event."""
        return self.record(
            event_type=f"goal.{goal.status}",
            goal_id=goal.id,
            swarm_id=goal.swarm_id,
            status=goal.status,
            details={"title": goal.title},
        )

    def record_consensus(self, result: ConsensusResult) -> OrchestrationTelemetryEntry:
        """Record a consensus lifecycle event."""
        return self.record(
            event_type=f"consensus.{result.status.value}",
            swarm_id=result.swarm_id,
            status=result.status.value,
            details={
                "topic": result.topic,
                "yea": result.yea_count,
                "nay": result.nay_count,
                "outcome": result.outcome,
            },
        )

    # ── Queries ──

    def get_entries(
        self,
        limit: int = 50,
        event_type: str | None = None,
        swarm_id: str | None = None,
        goal_id: str | None = None,
        agent_id: str | None = None,
    ) -> list[OrchestrationTelemetryEntry]:
        """Get recent telemetry entries, optionally filtered."""
        result: list[OrchestrationTelemetryEntry] = list(self._entries)

        if event_type:
            result = [e for e in result if e.event_type == event_type]
        if swarm_id:
            result = [e for e in result if e.swarm_id == swarm_id]
        if goal_id:
            result = [e for e in result if e.goal_id == goal_id]
        if agent_id:
            result = [e for e in result if e.agent_id == agent_id]

        result.reverse()
        return result[:limit]

    def get_stats(self) -> dict[str, Any]:
        """Get aggregated orchestration statistics."""
        total = len(self._entries)

        # Count by event type
        by_type: dict[str, int] = {}
        for e in self._entries:
            by_type[e.event_type] = by_type.get(e.event_type, 0) + 1

        # Count by status
        by_status: dict[str, int] = {}
        for e in self._entries:
            if e.status:
                by_status[e.status] = by_status.get(e.status, 0) + 1

        # Unique swarms, goals, agents
        swarm_ids: set[str] = set()
        goal_ids: set[str] = set()
        agent_ids: set[str] = set()
        for e in self._entries:
            if e.swarm_id:
                swarm_ids.add(e.swarm_id)
            if e.goal_id:
                goal_ids.add(e.goal_id)
            if e.agent_id:
                agent_ids.add(e.agent_id)

        total_duration = sum(e.duration_ms for e in self._entries)

        return {
            "total_entries": total,
            "by_event_type": dict(by_type),
            "by_status": dict(by_status),
            "unique_swarms": len(swarm_ids),
            "unique_goals": len(goal_ids),
            "unique_agents": len(agent_ids),
            "total_duration_ms": total_duration,
            "history_limit": self._max_entries,
            "entries_remaining": self._max_entries - total,
        }

    def clear(self) -> None:
        """Clear all telemetry entries."""
        self._entries.clear()

    @property
    def entry_count(self) -> int:
        """Current number of entries in the buffer."""
        return len(self._entries)
