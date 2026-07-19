"""Failure Recovery — recovers from failed tasks and agent failures.

Implements recovery planning, rollback to checkpoints, and agent reassignment
for resilient swarm execution.
"""

from typing import Any

from agentic_os.domain.events import EventEnvelope, Topic
from agentic_os.domain.orchestration import (
    AgentDescriptor,
    AgentTask,
    AgentTaskStatus,
    Checkpoint,
    OrchestrationPlan,
)
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.event_bus import EventBus
from agentic_os.ports.orchestration import RecoveryPort

log = get_logger("orchestration.recovery")


class FailureRecovery(RecoveryPort):
    """Recovers from task failures and agent unavailability.

    Attempts to re-execute failed tasks on available agents, rollback to
    checkpoints when needed, and recover entire plans from partial state.
    """

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus

    async def recover_task(
        self,
        task: AgentTask,
        available_agents: list[AgentDescriptor],
    ) -> AgentTask:
        """Recover a failed task by selecting a new agent."""
        await self._publish(
            Topic.ORCH_RECOVERY_STARTED,
            {
                "task_id": task.id,
                "available_agents": len(available_agents),
            },
        )

        if not available_agents:
            log.warning("No available agents for recovery", task_id=task.id)
            return task

        # Pick a different agent than the one that failed
        new_agent = None
        for agent in available_agents:
            if agent.agent_id != task.assigned_agent_id:
                new_agent = agent
                break

        if new_agent is None:
            new_agent = available_agents[0]

        recovered = AgentTask(
            id=task.id,
            goal_id=task.goal_id,
            title=task.title,
            description=task.description,
            status=AgentTaskStatus.ASSIGNED,
            assigned_agent_id=new_agent.agent_id,
            depends_on=task.depends_on,
            coordination_pattern=task.coordination_pattern,
            input_data=task.input_data,
            output_data={},
            error=None,
            priority=task.priority,
            timeout_seconds=task.timeout_seconds,
            created_at=task.created_at,
            started_at=None,
            completed_at=None,
        )

        await self._publish(
            Topic.ORCH_RECOVERY_COMPLETED,
            {
                "task_id": task.id,
                "new_agent_id": new_agent.agent_id,
            },
        )
        return recovered

    async def recover_plan(
        self,
        plan: OrchestrationPlan,
        checkpoint: Checkpoint | None = None,
    ) -> OrchestrationPlan:
        """Recover a plan from the last checkpoint."""
        if checkpoint:
            await self._publish(
                Topic.ORCH_RECOVERY_STARTED,
                {
                    "plan_id": plan.id,
                    "checkpoint_id": checkpoint.id,
                },
            )

            # Restore completed and failed states from checkpoint
            updated_tasks: list[AgentTask] = []
            for task in plan.subtasks:
                if task.id in checkpoint.completed_task_ids:
                    updated_tasks.append(
                        AgentTask(
                            id=task.id,
                            goal_id=task.goal_id,
                            title=task.title,
                            description=task.description,
                            status=AgentTaskStatus.COMPLETED,
                            assigned_agent_id=task.assigned_agent_id,
                            depends_on=task.depends_on,
                            coordination_pattern=task.coordination_pattern,
                            input_data=task.input_data,
                            output_data=checkpoint.partial_outputs.get(task.id, {}),
                            error=None,
                            priority=task.priority,
                            timeout_seconds=task.timeout_seconds,
                            created_at=task.created_at,
                            started_at=task.started_at,
                            completed_at=task.completed_at,
                        )
                    )
                elif task.id in checkpoint.failed_task_ids:
                    updated_tasks.append(
                        AgentTask(
                            id=task.id,
                            goal_id=task.goal_id,
                            title=task.title,
                            description=task.description,
                            status=AgentTaskStatus.PENDING,
                            assigned_agent_id=None,
                            depends_on=task.depends_on,
                            coordination_pattern=task.coordination_pattern,
                            input_data=task.input_data,
                            output_data={},
                            error=None,
                            priority=task.priority,
                            timeout_seconds=task.timeout_seconds,
                            created_at=task.created_at,
                            started_at=None,
                            completed_at=None,
                        )
                    )
                else:
                    updated_tasks.append(task)

            recovered_plan = OrchestrationPlan(
                id=plan.id,
                goal_id=plan.goal_id,
                subtasks=tuple(updated_tasks),
                status="recovering",
                metadata={**plan.metadata, "recovered_from": checkpoint.id},
                created_at=plan.created_at,
                completed_at=None,
            )

            await self._publish(
                Topic.ORCH_RECOVERY_COMPLETED,
                {
                    "plan_id": plan.id,
                    "recovered_tasks": len(updated_tasks),
                },
            )
            return recovered_plan

        # No checkpoint: reset all failed tasks to pending
        reset_tasks: list[AgentTask] = []
        for task in plan.subtasks:
            if task.status in (AgentTaskStatus.FAILED,):
                reset_tasks.append(
                    AgentTask(
                        id=task.id,
                        goal_id=task.goal_id,
                        title=task.title,
                        description=task.description,
                        status=AgentTaskStatus.PENDING,
                        assigned_agent_id=None,
                        depends_on=task.depends_on,
                        coordination_pattern=task.coordination_pattern,
                        input_data=task.input_data,
                        output_data={},
                        error=None,
                        priority=task.priority,
                        timeout_seconds=task.timeout_seconds,
                        created_at=task.created_at,
                        started_at=None,
                        completed_at=None,
                    )
                )
            else:
                reset_tasks.append(task)

        return OrchestrationPlan(
            id=plan.id,
            goal_id=plan.goal_id,
            subtasks=tuple(reset_tasks),
            status="pending",
            metadata=plan.metadata,
            created_at=plan.created_at,
            completed_at=None,
        )

    async def rollback_plan(
        self,
        plan: OrchestrationPlan,
        checkpoint: Checkpoint,
    ) -> OrchestrationPlan:
        """Rollback a plan to a specific checkpoint."""
        await self._publish(
            Topic.ORCH_RECOVERY_STARTED,
            {
                "plan_id": plan.id,
                "rollback_to": checkpoint.id,
            },
        )

        # Rollback all tasks to their state at checkpoint time
        rolled_back: list[AgentTask] = []
        for task in plan.subtasks:
            if task.id in checkpoint.completed_task_ids:
                rolled_back.append(task)
            elif task.id in checkpoint.failed_task_ids:
                rolled_back.append(
                    AgentTask(
                        id=task.id,
                        goal_id=task.goal_id,
                        title=task.title,
                        description=task.description,
                        status=AgentTaskStatus.PENDING,
                        assigned_agent_id=None,
                        depends_on=task.depends_on,
                        coordination_pattern=task.coordination_pattern,
                        input_data=task.input_data,
                        output_data={},
                        error=None,
                        priority=task.priority,
                        timeout_seconds=task.timeout_seconds,
                        created_at=task.created_at,
                        started_at=None,
                        completed_at=None,
                    )
                )
            else:
                # Reset all other tasks to pending
                rolled_back.append(
                    AgentTask(
                        id=task.id,
                        goal_id=task.goal_id,
                        title=task.title,
                        description=task.description,
                        status=AgentTaskStatus.PENDING,
                        assigned_agent_id=None,
                        depends_on=task.depends_on,
                        coordination_pattern=task.coordination_pattern,
                        input_data=task.input_data,
                        output_data={},
                        error=None,
                        priority=task.priority,
                        timeout_seconds=task.timeout_seconds,
                        created_at=task.created_at,
                        started_at=None,
                        completed_at=None,
                    )
                )

        return OrchestrationPlan(
            id=plan.id,
            goal_id=plan.goal_id,
            subtasks=tuple(rolled_back),
            status="pending",
            metadata={**plan.metadata, "rolled_back_to": checkpoint.id},
            created_at=plan.created_at,
            completed_at=None,
        )

    async def _publish(self, topic: Topic, payload: dict[str, Any]) -> None:
        try:
            await self._bus.publish(
                EventEnvelope(
                    type="event", source="failure-recovery", topic=topic.value, payload=payload
                )
            )
        except Exception as exc:
            log.warning("Publish failed", topic=topic.value, error=str(exc))
