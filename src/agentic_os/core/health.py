"""Health Monitor — periodic liveness checks + degradation events.

Emits ``HEALTH_CHECK`` on each pass and ``HEALTH_DEGRADED`` / ``AGENT_FAILED``
when an agent misses its heartbeat window. The Supervisor consumes these to
trigger recovery.
"""

from __future__ import annotations

from datetime import UTC, datetime

from agentic_os.config import Settings
from agentic_os.core.scheduler import Scheduler
from agentic_os.domain.agent import Agent, AgentStatus, TaskStatus
from agentic_os.domain.events import EventEnvelope, Topic
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.event_bus import EventBus

log = get_logger("core.health")


class HealthMonitorImpl:
    def __init__(self, bus: EventBus, registry, scheduler: Scheduler, settings: Settings) -> None:
        self._bus = bus
        self._registry = registry
        self._scheduler = scheduler
        self._settings = settings

    async def start(self) -> None:
        self._scheduler.every(self._settings.health_interval_seconds, self._tick)

    async def stop(self) -> None:
        pass

    async def register(self, agent: Agent) -> None:
        agent.heartbeat()

    async def check(self, agent: Agent) -> bool:
        # A completed agent is healthy by definition.
        if agent.status in (AgentStatus.COMPLETED,):
            return True
        # An agent that is NOT running (idle / failed / recovering) is not
        # "unhealthy" — it simply has nothing to heartbeat for. Reporting
        # healthy:false for idle agents flooded the EventBus with false
        # health.check failures for agents whose tasks finished long ago.
        if agent.status != AgentStatus.RUNNING:
            return True
        task = self._registry.get_task(agent.current_task_id) if agent.current_task_id else None
        if task is not None and task.status == TaskStatus.IN_PROGRESS:
            return True
        if agent.last_heartbeat is None:
            return False
        age = (datetime.now(UTC) - agent.last_heartbeat).total_seconds()
        return age <= self._settings.heartbeat_timeout_seconds

    async def _tick(self) -> None:
        for agent in self._registry.agents():
            # Only agents with a live heartbeat contract emit health events.
            # Long-idle agents (finished/never-started work) produce endless
            # healthy:false noise that Mission Control surfaces as ghost
            # failures — skip them entirely instead of reporting false.
            if agent.last_heartbeat is None:
                continue
            if agent.status != AgentStatus.RUNNING:
                continue
            healthy = await self.check(agent)
            await self._bus.publish(
                EventEnvelope(
                    type="health.check",
                    source="health-monitor",
                    topic=Topic.HEALTH_CHECK.value,
                    payload={"agent_id": agent.id, "healthy": healthy},
                )
            )
            if not healthy:
                # Do not false-degrade an agent whose task is actively executing:
                # long-running real-provider tasks outlive the heartbeat window,
                # and recovery would re-dispatch a healthy execution.
                task = (
                    self._registry.get_task(agent.current_task_id)
                    if agent.current_task_id
                    else None
                )
                if task is not None and task.status == TaskStatus.IN_PROGRESS:
                    continue
                log.warning("health.degraded", agent=agent.id)
                await self._bus.publish(
                    EventEnvelope(
                        type="health.degraded",
                        source="health-monitor",
                        topic=Topic.HEALTH_DEGRADED.value,
                        payload={"agent_id": agent.id, "task_id": agent.current_task_id},
                    )
                )
