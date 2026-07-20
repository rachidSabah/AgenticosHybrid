from __future__ import annotations

from uuid import UUID, uuid4

from core.contracts.event import Event, EventTopic
from core.event_bus.bus import EventBus
from core.logging import get_logger

_log = get_logger(__name__)

__all__ = [
    "ExecutionEventPublisher",
    "publish_engine_discovered",
    "publish_engine_registered",
    "publish_engine_unregistered",
    "publish_engine_health_changed",
    "publish_engine_enabled",
    "publish_engine_disabled",
    "publish_task_created",
    "publish_task_queued",
    "publish_task_dispatched",
    "publish_task_started",
    "publish_task_progress",
    "publish_task_completed",
    "publish_task_failed",
    "publish_task_cancelled",
    "publish_task_timeout",
    "publish_session_created",
    "publish_session_active",
    "publish_session_closed",
    "publish_session_error",
    "publish_route_selected",
    "publish_route_failover",
    "publish_benchmark_started",
    "publish_benchmark_completed",
]


class ExecutionEventPublisher:
    def __init__(self, bus: EventBus) -> None:
        self._bus = bus

    async def publish(
        self,
        topic: EventTopic | str,
        payload: dict,
        correlation_id: UUID | None = None,
        causation_id: UUID | None = None,
    ) -> None:
        from core.contracts.actor import ActorRef

        if isinstance(topic, str):
            topic = EventTopic(topic)
        event = Event(
            topic=topic.value,
            correlation_id=correlation_id or uuid4(),
            causation_id=causation_id,
            actor=ActorRef(kind="system", id="execution_engine"),
            payload=payload,
        )
        await self._bus.publish(event)


async def _publish(
    bus: EventBus,
    topic: EventTopic,
    payload: dict,
    correlation_id: UUID | None = None,
    causation_id: UUID | None = None,
) -> None:
    publisher = ExecutionEventPublisher(bus)
    await publisher.publish(topic, payload, correlation_id, causation_id)


async def publish_engine_discovered(
    bus: EventBus,
    engine_type: str,
    name: str,
    version: str | None = None,
    binary_path: str | None = None,
) -> None:
    await _publish(
        bus,
        EventTopic.EXECUTION_ENGINE_DISCOVERED,
        {
            "engine_type": engine_type,
            "name": name,
            "version": version,
            "binary_path": binary_path,
        },
    )


async def publish_engine_registered(
    bus: EventBus, engine_type: str, name: str, version: str | None = None
) -> None:
    await _publish(
        bus,
        EventTopic.EXECUTION_ENGINE_REGISTERED,
        {
            "engine_type": engine_type,
            "name": name,
            "version": version,
        },
    )


async def publish_engine_unregistered(bus: EventBus, engine_type: str, name: str) -> None:
    await _publish(
        bus,
        EventTopic.EXECUTION_ENGINE_UNREGISTERED,
        {
            "engine_type": engine_type,
            "name": name,
        },
    )


async def publish_engine_health_changed(
    bus: EventBus, engine_type: str, name: str, healthy: bool, error: str | None = None
) -> None:
    await _publish(
        bus,
        EventTopic.EXECUTION_ENGINE_HEALTH_CHANGED,
        {
            "engine_type": engine_type,
            "name": name,
            "healthy": healthy,
            "error": error,
        },
    )


async def publish_engine_enabled(bus: EventBus, engine_type: str, name: str) -> None:
    await _publish(
        bus,
        EventTopic.EXECUTION_ENGINE_ENABLED,
        {
            "engine_type": engine_type,
            "name": name,
        },
    )


async def publish_engine_disabled(bus: EventBus, engine_type: str, name: str) -> None:
    await _publish(
        bus,
        EventTopic.EXECUTION_ENGINE_DISABLED,
        {
            "engine_type": engine_type,
            "name": name,
        },
    )


async def publish_task_created(bus: EventBus, task_id: str, engine_type: str, goal: str) -> None:
    await _publish(
        bus,
        EventTopic.EXECUTION_TASK_CREATED,
        {
            "task_id": task_id,
            "engine_type": engine_type,
            "goal": goal,
        },
    )


async def publish_task_queued(bus: EventBus, task_id: str, engine_type: str) -> None:
    await _publish(
        bus,
        EventTopic.EXECUTION_TASK_QUEUED,
        {
            "task_id": task_id,
            "engine_type": engine_type,
        },
    )


async def publish_task_dispatched(
    bus: EventBus, task_id: str, engine_type: str, engine_name: str
) -> None:
    await _publish(
        bus,
        EventTopic.EXECUTION_TASK_DISPATCHED,
        {
            "task_id": task_id,
            "engine_type": engine_type,
            "engine_name": engine_name,
        },
    )


async def publish_task_started(bus: EventBus, task_id: str, engine_type: str) -> None:
    await _publish(
        bus,
        EventTopic.EXECUTION_TASK_STARTED,
        {
            "task_id": task_id,
            "engine_type": engine_type,
        },
    )


async def publish_task_progress(
    bus: EventBus, task_id: str, progress: float, message: str = ""
) -> None:
    await _publish(
        bus,
        EventTopic.EXECUTION_TASK_PROGRESS,
        {
            "task_id": task_id,
            "progress": progress,
            "message": message,
        },
    )


async def publish_task_completed(
    bus: EventBus, task_id: str, engine_type: str, duration_s: float
) -> None:
    await _publish(
        bus,
        EventTopic.EXECUTION_TASK_COMPLETED,
        {
            "task_id": task_id,
            "engine_type": engine_type,
            "duration_s": duration_s,
        },
    )


async def publish_task_failed(bus: EventBus, task_id: str, engine_type: str, error: str) -> None:
    await _publish(
        bus,
        EventTopic.EXECUTION_TASK_FAILED,
        {
            "task_id": task_id,
            "engine_type": engine_type,
            "error": error,
        },
    )


async def publish_task_cancelled(bus: EventBus, task_id: str, engine_type: str) -> None:
    await _publish(
        bus,
        EventTopic.EXECUTION_TASK_CANCELLED,
        {
            "task_id": task_id,
            "engine_type": engine_type,
        },
    )


async def publish_task_timeout(bus: EventBus, task_id: str, engine_type: str) -> None:
    await _publish(
        bus,
        EventTopic.EXECUTION_TASK_TIMEOUT,
        {
            "task_id": task_id,
            "engine_type": engine_type,
        },
    )


async def publish_session_created(bus: EventBus, session_id: str, engine_type: str) -> None:
    await _publish(
        bus,
        EventTopic.EXECUTION_SESSION_CREATED,
        {
            "session_id": session_id,
            "engine_type": engine_type,
        },
    )


async def publish_session_active(bus: EventBus, session_id: str, engine_type: str) -> None:
    await _publish(
        bus,
        EventTopic.EXECUTION_SESSION_ACTIVE,
        {
            "session_id": session_id,
            "engine_type": engine_type,
        },
    )


async def publish_session_closed(
    bus: EventBus, session_id: str, engine_type: str, task_count: int
) -> None:
    await _publish(
        bus,
        EventTopic.EXECUTION_SESSION_CLOSED,
        {
            "session_id": session_id,
            "engine_type": engine_type,
            "task_count": task_count,
        },
    )


async def publish_session_error(
    bus: EventBus, session_id: str, engine_type: str, error: str
) -> None:
    await _publish(
        bus,
        EventTopic.EXECUTION_SESSION_ERROR,
        {
            "session_id": session_id,
            "engine_type": engine_type,
            "error": error,
        },
    )


async def publish_route_selected(
    bus: EventBus, strategy: str, selected: str, alternatives: list[str]
) -> None:
    await _publish(
        bus,
        EventTopic.EXECUTION_ROUTE_SELECTED,
        {
            "strategy": strategy,
            "selected": selected,
            "alternatives": alternatives,
        },
    )


async def publish_route_failover(
    bus: EventBus, from_engine: str, to_engine: str, reason: str
) -> None:
    await _publish(
        bus,
        EventTopic.EXECUTION_ROUTE_FAILOVER,
        {
            "from_engine": from_engine,
            "to_engine": to_engine,
            "reason": reason,
        },
    )


async def publish_benchmark_started(bus: EventBus, engine_type: str, task_count: int) -> None:
    await _publish(
        bus,
        EventTopic.EXECUTION_BENCHMARK_STARTED,
        {
            "engine_type": engine_type,
            "task_count": task_count,
        },
    )


async def publish_benchmark_completed(
    bus: EventBus, engine_type: str, avg_duration_s: float, error_rate: float
) -> None:
    await _publish(
        bus,
        EventTopic.EXECUTION_BENCHMARK_COMPLETED,
        {
            "engine_type": engine_type,
            "avg_duration_s": avg_duration_s,
            "error_rate": error_rate,
        },
    )
