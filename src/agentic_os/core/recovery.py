"""Recovery Manager — automatic failure recovery.

On ``AGENT_FAILED`` (or degraded→failed), this re-dispatches the agent's task,
up to ``max_attempts``. After exhaustion it marks the task FAILED and stops.
This proves the "recover failed agents" goal end-to-end.
"""

from __future__ import annotations

from agentic_os.config import Settings
from agentic_os.core.orchestrator import Orchestrator
from agentic_os.domain.agent import Agent, AgentStatus
from agentic_os.domain.events import EventEnvelope, Topic
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.event_bus import EventBus

log = get_logger("core.recovery")


class RecoveryManagerImpl:
    def __init__(self, bus: EventBus, orchestrator: Orchestrator, settings: Settings) -> None:
        self._bus = bus
        self._orchestrator = orchestrator
        self._settings = settings

    async def start(self) -> None:
        await self._bus.subscribe(Topic.AGENT_FAILED.value, self._on_failed)
        await self._bus.subscribe(Topic.HEALTH_DEGRADED.value, self._on_degraded)

    async def stop(self) -> None:
        pass

    async def handle_failure(self, agent: Agent, reason: str) -> bool:
        task = (
            self._orchestrator.registry.get_task(agent.current_task_id)
            if agent.current_task_id
            else None
        )
        if task is None:
            return False
        if task.attempts >= self._settings.max_attempts:
            from agentic_os.domain.agent import TaskStatus

            log.error("recovery.exhausted", agent=agent.id, task=task.id, attempts=task.attempts)
            task.status = TaskStatus.FAILED
            task.error = reason
            task.touch()
            agent.mark_failed()
            return False
        log.info("recovery.retry", agent=agent.id, attempt=task.attempts)
        agent.mark_recovering()
        await self._orchestrator.dispatch_task(task)
        return True

    async def _on_failed(self, event: EventEnvelope) -> None:
        agent_id = event.payload.get("agent_id")
        if not agent_id:
            return
        agent = self._orchestrator.registry.get_agent(agent_id)
        if agent:
            await self.handle_failure(agent, event.payload.get("reason", "failed"))

    async def _on_degraded(self, event: EventEnvelope) -> None:
        # Treat sustained degradation as failure after the heartbeat window.
        agent_id = event.payload.get("agent_id")
        if not agent_id:
            return
        agent = self._orchestrator.registry.get_agent(agent_id)
        if agent and agent.status == AgentStatus.RUNNING:
            agent.mark_failed()
            await self._bus.publish(
                EventEnvelope(
                    type="agent.failed",
                    source="recovery",
                    topic=Topic.AGENT_FAILED.value,
                    payload={
                        "agent_id": agent.id,
                        "task_id": agent.current_task_id,
                        "reason": "health degraded",
                    },
                )
            )
