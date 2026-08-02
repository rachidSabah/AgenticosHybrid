"""Swarm Supervisor — execution monitoring, failure detection, and recovery.

Monitors active executions, detects task failures and dependency deadlocks,
restarts or reassigns failed tasks, and tracks overall execution progress.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any

from agentic_os.core.orchestration.registry import OrchestrationAgentRegistry
from agentic_os.core.runtime.manager import RuntimeManager
from agentic_os.domain.events import EventEnvelope, Topic
from agentic_os.domain.orchestration import (
    AgentDescriptor,
    AgentTask,
    AgentTaskStatus,
    OrchestrationPlan,
)
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.event_bus import EventBus
from agentic_os.ports.execution import ExecutionRequest
from agentic_os.ports.orchestration import SupervisorPort

log = get_logger("orchestration.supervisor")


@dataclass
class SwarmSupervisor(SupervisorPort):
    """Supervises swarm execution — monitors, detects failures, and recovers.

    Tracks task execution state, detects failures and deadlocks, and
    automatically restarts or reassigns failed tasks using retry policies.
    """

    bus: EventBus
    agent_registry: OrchestrationAgentRegistry
    runtime: RuntimeManager

    max_retries: int = 3
    monitor_interval_seconds: float = 5.0
    deadlock_timeout_seconds: float = 120.0

    _active_monitors: dict[str, asyncio.Task] = field(default_factory=dict, repr=False)

    async def monitor_execution(self, plan: OrchestrationPlan) -> OrchestrationPlan:
        """Monitor ongoing execution and detect failures or deadlocks."""
        await self._publish(
            Topic.ORCH_SUPERVISOR_MONITORING,
            {
                "plan_id": plan.id,
                "task_count": len(plan.subtasks),
            },
        )

        failed = [t for t in plan.subtasks if t.status == AgentTaskStatus.FAILED]
        hung = await self._detect_hung_tasks(plan)
        deadlocked = await self.detect_deadlocks(plan)

        if failed:
            log.warning("Failed tasks detected", plan_id=plan.id, count=len(failed))
            await self._publish(
                Topic.ORCH_SUPERVISOR_FAILURE_DETECTED,
                {
                    "plan_id": plan.id,
                    "task_ids": [t.id for t in failed],
                },
            )

        if deadlocked:
            log.warning("Deadlocked tasks detected", plan_id=plan.id, count=len(deadlocked))
            await self._publish(
                Topic.ORCH_SUPERVISOR_DEADLOCK_DETECTED,
                {
                    "plan_id": plan.id,
                    "task_ids": deadlocked,
                },
            )

        updated = list(plan.subtasks)
        for task in failed + hung:
            if task.id in [t.id for t in plan.subtasks if t.status == AgentTaskStatus.FAILED]:
                continue
            idx = next((i for i, t in enumerate(updated) if t.id == task.id), None)
            if idx is not None:
                updated[idx] = task

        return OrchestrationPlan(
            id=plan.id,
            goal_id=plan.goal_id,
            subtasks=tuple(updated),
            status=plan.status,
            metadata=plan.metadata,
            created_at=plan.created_at,
            completed_at=plan.completed_at,
        )

    async def detect_failures(self, plan: OrchestrationPlan) -> list[AgentTask]:
        """Detect failed tasks in a plan."""
        return [t for t in plan.subtasks if t.status == AgentTaskStatus.FAILED]

    async def detect_deadlocks(self, plan: OrchestrationPlan) -> list[str]:
        """Detect deadlocked dependency chains."""
        task_map = {t.id: t for t in plan.subtasks}
        completed = {t.id for t in plan.subtasks if t.status == AgentTaskStatus.COMPLETED}

        visited: set[str] = set()
        in_progress: set[str] = set()
        deadlocked: list[str] = []

        def _visit(task_id: str) -> bool:
            if task_id in in_progress:
                return True
            if task_id in visited:
                return False
            task = task_map.get(task_id)
            if task is None or not task.depends_on:
                visited.add(task_id)
                return False
            in_progress.add(task_id)
            for dep in task.depends_on:
                if dep not in completed and _visit(dep):
                    deadlocked.append(task_id)
                    return True
            in_progress.discard(task_id)
            visited.add(task_id)
            return False

        for t in plan.subtasks:
            _visit(t.id)

        return list(set(deadlocked))

    async def restart_task(
        self,
        task: AgentTask,
        agent: AgentDescriptor | None = None,
    ) -> AgentTask:
        """Restart a failed task on an agent."""
        agent_id = agent.agent_id if agent else task.assigned_agent_id
        if not agent_id:
            return task.with_error("No agent for restart")

        await self._publish(
            Topic.ORCH_SUPERVISOR_RESTARTED,
            {
                "task_id": task.id,
                "agent_id": agent_id,
            },
        )

        request = ExecutionRequest(
            action=task.title,
            payload=task.input_data,
            timeout_seconds=task.timeout_seconds,
        )
        try:
            result = await asyncio.wait_for(
                self.runtime.execute(agent_id, request),
                timeout=task.timeout_seconds,
            )
        except Exception as exc:
            return task.with_error(f"Restart failed: {exc}")

        if result and hasattr(result, "status") and result.status.value == "completed":
            output = dict(result.output) if hasattr(result, "output") else {}
            return AgentTask(
                id=task.id,
                goal_id=task.goal_id,
                title=task.title,
                description=task.description,
                status=AgentTaskStatus.COMPLETED,
                assigned_agent_id=agent_id,
                depends_on=task.depends_on,
                coordination_pattern=task.coordination_pattern,
                input_data=task.input_data,
                output_data=output,
                error=None,
                priority=task.priority,
                timeout_seconds=task.timeout_seconds,
                created_at=task.created_at,
                started_at=None,
                completed_at=None,
            )
        return task.with_error("Restart execution failed")

    async def reassign_task(self, task: AgentTask, new_agent_id: str) -> AgentTask:
        """Reassign a task to a different agent."""
        await self._publish(
            Topic.ORCH_SUPERVISOR_REASSIGNED,
            {
                "task_id": task.id,
                "new_agent_id": new_agent_id,
            },
        )
        return task.with_assigned(new_agent_id)

    async def _detect_hung_tasks(self, plan: OrchestrationPlan) -> list[AgentTask]:
        """Detect tasks that have been running longer than their timeout."""
        from datetime import UTC, datetime

        now = datetime.now(UTC)
        hung: list[AgentTask] = []
        for task in plan.subtasks:
            if task.status == AgentTaskStatus.RUNNING and task.started_at:
                elapsed = (now - task.started_at).total_seconds()
                if elapsed > task.timeout_seconds:
                    hung.append(task.with_error(f"Hung: exceeded {task.timeout_seconds}s timeout"))
        return hung

    async def _publish(self, topic: Topic, payload: dict[str, Any]) -> None:
        try:
            await self.bus.publish(
                EventEnvelope(type="event", source="supervisor", topic=topic.value, payload=payload)
            )
        except Exception as exc:
            log.warning("Supervisor publish failed", topic=topic.value, error=str(exc))
