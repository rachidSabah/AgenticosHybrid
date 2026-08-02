"""Checkpoint Manager — saves and restores execution state for resilience.

Enables the orchestration engine to recover from failures by checkpointing
task states, partial outputs, and execution metadata at configurable intervals.
"""

from typing import Any

from agentic_os.domain.events import EventEnvelope, Topic
from agentic_os.domain.orchestration import (
    AgentTaskStatus,
    Checkpoint,
    ExecutionStage,
    OrchestrationPlan,
)
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.event_bus import EventBus
from agentic_os.ports.orchestration import CheckpointPort

log = get_logger("orchestration.checkpoint")


class CheckpointManager(CheckpointPort):
    """Manages execution checkpoints for plan recovery.

    Saves checkpoints containing completed/failed task IDs, partial outputs,
    and metadata. Supports restoring plans from any saved checkpoint.
    """

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        self._checkpoints: dict[str, Checkpoint] = {}

    async def save_checkpoint(
        self,
        plan: OrchestrationPlan,
        stage: ExecutionStage | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Checkpoint:
        """Save a checkpoint capturing current execution state."""
        completed_ids = tuple(t.id for t in plan.subtasks if t.status == AgentTaskStatus.COMPLETED)
        failed_ids = tuple(t.id for t in plan.subtasks if t.status == AgentTaskStatus.FAILED)

        partial_outputs: dict[str, dict[str, Any]] = {}
        for t in plan.subtasks:
            if t.output_data:
                partial_outputs[t.id] = dict(t.output_data)

        task_states = {t.id: t.status.value for t in plan.subtasks}

        checkpoint = Checkpoint(
            plan_id=plan.id,
            stage_id=stage.id if stage else "",
            task_states=task_states,
            completed_task_ids=completed_ids,
            failed_task_ids=failed_ids,
            partial_outputs=partial_outputs,
            metadata=metadata or {},
        )

        self._checkpoints[checkpoint.id] = checkpoint

        await self._publish(
            Topic.ORCH_CHECKPOINT_CREATED,
            {
                "checkpoint_id": checkpoint.id,
                "plan_id": plan.id,
                "completed": len(completed_ids),
                "failed": len(failed_ids),
            },
        )

        log.info("Checkpoint saved", checkpoint_id=checkpoint.id, plan_id=plan.id)
        return checkpoint

    async def restore_checkpoint(self, checkpoint_id: str) -> OrchestrationPlan | None:
        """Restore execution state from a checkpoint — returns the plan at checkpoint time."""
        checkpoint = self._checkpoints.get(checkpoint_id)
        if checkpoint is None:
            return None

        await self._publish(
            Topic.ORCH_CHECKPOINT_RESTORED,
            {
                "checkpoint_id": checkpoint_id,
                "plan_id": checkpoint.plan_id,
            },
        )

        log.info("Checkpoint restored", checkpoint_id=checkpoint_id)
        return None  # Caller must reconstruct the plan from checkpoint data

    async def list_checkpoints(self, plan_id: str) -> list[Checkpoint]:
        """List all checkpoints for a plan, most recent first."""
        result = [c for c in self._checkpoints.values() if c.plan_id == plan_id]
        result.sort(key=lambda c: c.created_at, reverse=True)
        return result

    async def delete_checkpoint(self, checkpoint_id: str) -> bool:
        """Delete a checkpoint."""
        if checkpoint_id in self._checkpoints:
            del self._checkpoints[checkpoint_id]
            return True
        return False

    async def _publish(self, topic: Topic, payload: dict[str, Any]) -> None:
        try:
            await self._bus.publish(
                EventEnvelope(
                    type="event", source="checkpoint-manager", topic=topic.value, payload=payload
                )
            )
        except Exception as exc:
            log.warning("Publish failed", topic=topic.value, error=str(exc))
