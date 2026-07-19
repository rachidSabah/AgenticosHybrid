"""Retry Manager — handles task retry with configurable backoff policies.

Implements exponential backoff with jitter, configurable max retries,
and retry-on-error / retry-on-timeout policies.
"""

import asyncio
import random
from typing import Any

from agentic_os.domain.events import EventEnvelope, Topic
from agentic_os.domain.orchestration import (
    AgentTask,
    AgentTaskStatus,
    RetryPolicy,
)
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.event_bus import EventBus

log = get_logger("orchestration.retry")


class RetryManager:
    """Manages task retries with exponential backoff and configurable policies.

    Tracks retry counts per task, computes backoff delays with jitter, and
    determines when retries are exhausted.
    """

    def __init__(self, bus: EventBus, default_policy: RetryPolicy | None = None) -> None:
        self._bus = bus
        self._default_policy = default_policy or RetryPolicy()
        self._retry_counts: dict[str, int] = {}
        self._task_history: dict[str, list[AgentTaskStatus]] = {}

    async def should_retry(self, task: AgentTask, policy: RetryPolicy | None = None) -> bool:
        """Determine if a task should be retried based on its failure mode."""
        policy = policy or self._default_policy
        current_count = self._retry_counts.get(task.id, 0)

        if current_count >= policy.max_retries:
            await self._publish(
                Topic.ORCH_RETRY_EXHAUSTED,
                {
                    "task_id": task.id,
                    "retries": current_count,
                },
            )
            return False

        if task.error and "timeout" in task.error.lower():
            if not policy.retry_on_timeout:
                return False
        elif task.error:
            if not policy.retry_on_error:
                return False

        return True

    async def execute_with_retry(
        self,
        task: AgentTask,
        execute_fn: Any,
        policy: RetryPolicy | None = None,
    ) -> AgentTask:
        """Execute a task with retry logic."""
        policy = policy or self._default_policy
        current_count = self._retry_counts.get(task.id, 0)

        self._retry_counts[task.id] = current_count + 1

        # Compute backoff
        delay = min(
            policy.base_delay_seconds * (policy.backoff_multiplier**current_count),
            policy.max_delay_seconds,
        )
        if policy.jitter:
            delay += random.uniform(0, delay * 0.1)

        await self._publish(
            Topic.ORCH_RETRY_SCHEDULED,
            {
                "task_id": task.id,
                "retry_count": current_count + 1,
                "delay_seconds": round(delay, 2),
            },
        )

        await asyncio.sleep(delay)

        await self._publish(
            Topic.ORCH_RETRY_EXECUTING,
            {
                "task_id": task.id,
                "retry_count": current_count + 1,
            },
        )

        result = await execute_fn(task)
        return result

    def get_retry_count(self, task_id: str) -> int:
        """Get the current retry count for a task."""
        return self._retry_counts.get(task_id, 0)

    def reset_retry_count(self, task_id: str) -> None:
        """Reset retry count for a task (e.g., after successful execution)."""
        self._retry_counts.pop(task_id, None)

    async def _publish(self, topic: Topic, payload: dict[str, Any]) -> None:
        try:
            await self._bus.publish(
                EventEnvelope(
                    type="event", source="retry-manager", topic=topic.value, payload=payload
                )
            )
        except Exception as exc:
            log.warning("Publish failed", topic=topic.value, error=str(exc))
