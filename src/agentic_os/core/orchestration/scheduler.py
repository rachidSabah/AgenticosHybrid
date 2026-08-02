"""Swarm Scheduler — task prioritization, sequencing, and dispatching.

Responsible for scheduling tasks across available agents, respecting
dependencies, priorities, and retry policies. Dispatches tasks to agents
via the Execution Engine Framework.
"""

import asyncio

from agentic_os.core.orchestration.registry import OrchestrationAgentRegistry
from agentic_os.core.runtime.manager import RuntimeManager
from agentic_os.domain.events import EventEnvelope, Topic
from agentic_os.domain.orchestration import (
    AgentDescriptor,
    AgentTask,
    AgentTaskStatus,
    OrchestrationPlan,
    RetryPolicy,
)
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.event_bus import EventBus
from agentic_os.ports.execution import ExecutionRequest
from agentic_os.ports.orchestration import SchedulerPort

log = get_logger("orchestration.scheduler")


class SwarmScheduler(SchedulerPort):
    """Schedules and dispatches tasks across swarm agents.

    Maintains a priority queue of ready tasks, dispatches to agents via the
    RuntimeManager, and handles task sequencing based on dependencies.
    Supports optional retry policies for failed tasks.
    """

    def __init__(
        self,
        bus: EventBus,
        agent_registry: OrchestrationAgentRegistry,
        runtime: RuntimeManager,
        default_policy: RetryPolicy | None = None,
    ) -> None:
        self._bus = bus
        self._agent_registry = agent_registry
        self._runtime = runtime
        self._default_policy = default_policy or RetryPolicy(
            max_retries=3,
            base_delay_seconds=1.0,
            max_delay_seconds=60.0,
            backoff_multiplier=2.0,
        )
        self._schedules: dict[str, list[AgentTask]] = {}

    async def schedule_tasks(
        self,
        plan: OrchestrationPlan,
        agents: list[AgentDescriptor],
        policy: RetryPolicy | None = None,
    ) -> OrchestrationPlan:
        """Schedule all tasks in a plan, resolving topologically."""
        policy = policy or self._default_policy

        # Topological sort: tasks with no deps first
        tasks = list(plan.subtasks)
        task_map = {t.id: t for t in tasks}
        completed: set[str] = set()
        ordered: list[AgentTask] = []
        remaining = set(t.id for t in tasks)

        while remaining:
            ready = [
                task_map[tid]
                for tid in remaining
                if all(dep in completed for dep in task_map[tid].depends_on)
            ]
            if not ready:
                log.warning("Deadlock detected in schedule", plan_id=plan.id)
                break
            # Sort by priority (higher first)
            ready.sort(key=lambda t: t.priority, reverse=True)
            for task in ready:
                ordered.append(task)
                completed.add(task.id)
                remaining.remove(task.id)

        self._schedules[plan.id] = ordered

        await self._bus.publish(
            EventEnvelope(
                type="event",
                source="scheduler",
                topic=Topic.ORCH_SCHEDULER_TASK_SCHEDULED.value,
                payload={
                    "plan_id": plan.id,
                    "task_count": len(ordered),
                    "policy": policy.to_dict(),
                },
            )
        )
        log.info("Tasks scheduled", plan_id=plan.id, count=len(ordered))
        return plan

    async def dispatch_task(
        self,
        task: AgentTask,
        agent: AgentDescriptor | None = None,
    ) -> AgentTask:
        """Dispatch a single task to an agent via the RuntimeManager."""
        agent_id = agent.agent_id if agent else task.assigned_agent_id
        if not agent_id:
            return task.with_error("No agent assigned for dispatch")

        await self._bus.publish(
            EventEnvelope(
                type="event",
                source="scheduler",
                topic=Topic.ORCH_SCHEDULER_TASK_DISPATCHED.value,
                payload={"task_id": task.id, "agent_id": agent_id},
            )
        )

        request = ExecutionRequest(
            action=task.title,
            payload=task.input_data,
            timeout_seconds=task.timeout_seconds,
        )

        try:
            result = await asyncio.wait_for(
                self._runtime.execute(agent_id, request),
                timeout=task.timeout_seconds,
            )
        except TimeoutError:
            log.warning("Task timed out", task_id=task.id, agent_id=agent_id)
            return task.with_error(f"Timed out after {task.timeout_seconds}s")
        except Exception as exc:
            log.warning("Task dispatch failed", task_id=task.id, error=str(exc))
            return task.with_error(str(exc))

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
                error=task.error,
                priority=task.priority,
                timeout_seconds=task.timeout_seconds,
                created_at=task.created_at,
                started_at=result.started_at if hasattr(result, "started_at") else None,
                completed_at=None,
            )
        else:
            error = getattr(result, "error", "Execution failed") if result else "No result"
            return task.with_error(str(error))

    async def get_schedule(self, plan_id: str) -> list[AgentTask]:
        """Get the current schedule for a plan."""
        return self._schedules.get(plan_id, [])
