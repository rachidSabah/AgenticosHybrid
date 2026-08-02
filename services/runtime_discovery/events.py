from __future__ import annotations

from uuid import UUID, uuid4

from core.contracts.event import Event, EventTopic
from core.event_bus.bus import EventBus
from core.logging import get_logger

_log = get_logger(__name__)

__all__ = [
    "RuntimeEventPublisher",
    "publish_discovery_scan_started",
    "publish_discovery_scan_completed",
    "publish_discovery_engine_found",
    "publish_discovery_engine_lost",
    "publish_binding_started",
    "publish_binding_completed",
    "publish_binding_failed",
    "publish_binding_unbound",
    "publish_validation_started",
    "publish_validation_passed",
    "publish_validation_failed",
    "publish_health_check_passed",
    "publish_health_check_failed",
    "publish_health_status_changed",
    "publish_health_degraded",
    "publish_health_recovered",
    "publish_profile_created",
    "publish_profile_updated",
    "publish_configuration_changed",
    "publish_telemetry_recorded",
    "publish_registry_registered",
    "publish_registry_unregistered",
]


class RuntimeEventPublisher:
    def __init__(self, bus: EventBus) -> None:
        self._bus = bus

    async def publish(
        self, topic: EventTopic | str, payload: dict, correlation_id: UUID | None = None
    ) -> None:
        from core.contracts.actor import ActorRef

        if isinstance(topic, str):
            topic = EventTopic(topic)
        event = Event(
            topic=topic.value,
            correlation_id=correlation_id or uuid4(),
            causation_id=None,
            actor=ActorRef(kind="system", id="runtime_discovery"),
            payload=payload,
        )
        await self._bus.publish(event)


async def _publish(bus: EventBus, topic: EventTopic, payload: dict) -> None:
    publisher = RuntimeEventPublisher(bus)
    await publisher.publish(topic, payload)


async def publish_discovery_scan_started(bus: EventBus, profile: str, provider_count: int) -> None:
    await _publish(
        bus,
        EventTopic.RUNTIME_DISCOVERY_SCAN_STARTED,
        {
            "profile": profile,
            "provider_count": provider_count,
        },
    )


async def publish_discovery_scan_completed(
    bus: EventBus, profile: str, engines_found: int, duration_ms: float
) -> None:
    await _publish(
        bus,
        EventTopic.RUNTIME_DISCOVERY_SCAN_COMPLETED,
        {
            "profile": profile,
            "engines_found": engines_found,
            "duration_ms": duration_ms,
        },
    )


async def publish_discovery_engine_found(
    bus: EventBus, engine_type: str, name: str, version: str | None = None, source: str = ""
) -> None:
    await _publish(
        bus,
        EventTopic.RUNTIME_DISCOVERY_ENGINE_FOUND,
        {
            "engine_type": engine_type,
            "name": name,
            "version": version,
            "source": source,
        },
    )


async def publish_discovery_engine_lost(bus: EventBus, engine_type: str, name: str) -> None:
    await _publish(
        bus,
        EventTopic.RUNTIME_DISCOVERY_ENGINE_LOST,
        {
            "engine_type": engine_type,
            "name": name,
        },
    )


async def publish_binding_started(bus: EventBus, runtime_id: str, engine_name: str) -> None:
    await _publish(
        bus,
        EventTopic.RUNTIME_BINDING_STARTED,
        {
            "runtime_id": runtime_id,
            "engine_name": engine_name,
        },
    )


async def publish_binding_completed(bus: EventBus, runtime_id: str, engine_name: str) -> None:
    await _publish(
        bus,
        EventTopic.RUNTIME_BINDING_COMPLETED,
        {
            "runtime_id": runtime_id,
            "engine_name": engine_name,
        },
    )


async def publish_binding_failed(
    bus: EventBus, runtime_id: str, engine_name: str, error: str
) -> None:
    await _publish(
        bus,
        EventTopic.RUNTIME_BINDING_FAILED,
        {
            "runtime_id": runtime_id,
            "engine_name": engine_name,
            "error": error,
        },
    )


async def publish_binding_unbound(bus: EventBus, runtime_id: str, engine_name: str) -> None:
    await _publish(
        bus,
        EventTopic.RUNTIME_BINDING_UNBOUND,
        {
            "runtime_id": runtime_id,
            "engine_name": engine_name,
        },
    )


async def publish_validation_started(bus: EventBus, runtime_id: str, name: str) -> None:
    await _publish(
        bus,
        EventTopic.RUNTIME_VALIDATION_STARTED,
        {
            "runtime_id": runtime_id,
            "name": name,
        },
    )


async def publish_validation_passed(bus: EventBus, runtime_id: str, name: str) -> None:
    await _publish(
        bus,
        EventTopic.RUNTIME_VALIDATION_PASSED,
        {
            "runtime_id": runtime_id,
            "name": name,
        },
    )


async def publish_validation_failed(
    bus: EventBus, runtime_id: str, name: str, errors: list[str]
) -> None:
    await _publish(
        bus,
        EventTopic.RUNTIME_VALIDATION_FAILED,
        {
            "runtime_id": runtime_id,
            "name": name,
            "errors": errors,
        },
    )


async def publish_health_check_passed(
    bus: EventBus, runtime_id: str, name: str, response_time_ms: float
) -> None:
    await _publish(
        bus,
        EventTopic.RUNTIME_HEALTH_CHECK_PASSED,
        {
            "runtime_id": runtime_id,
            "name": name,
            "response_time_ms": response_time_ms,
        },
    )


async def publish_health_check_failed(
    bus: EventBus, runtime_id: str, name: str, error: str
) -> None:
    await _publish(
        bus,
        EventTopic.RUNTIME_HEALTH_CHECK_FAILED,
        {
            "runtime_id": runtime_id,
            "name": name,
            "error": error,
        },
    )


async def publish_health_status_changed(
    bus: EventBus, runtime_id: str, name: str, status: str
) -> None:
    await _publish(
        bus,
        EventTopic.RUNTIME_HEALTH_STATUS_CHANGED,
        {
            "runtime_id": runtime_id,
            "name": name,
            "status": status,
        },
    )


async def publish_health_degraded(bus: EventBus, runtime_id: str, name: str, error: str) -> None:
    await _publish(
        bus,
        EventTopic.RUNTIME_HEALTH_DEGRADED,
        {
            "runtime_id": runtime_id,
            "name": name,
            "error": error,
        },
    )


async def publish_health_recovered(bus: EventBus, runtime_id: str, name: str) -> None:
    await _publish(
        bus,
        EventTopic.RUNTIME_HEALTH_RECOVERED,
        {
            "runtime_id": runtime_id,
            "name": name,
        },
    )


async def publish_profile_created(bus: EventBus, runtime_id: str, version: str) -> None:
    await _publish(
        bus,
        EventTopic.RUNTIME_PROFILE_CREATED,
        {
            "runtime_id": runtime_id,
            "version": version,
        },
    )


async def publish_profile_updated(bus: EventBus, runtime_id: str, version: str) -> None:
    await _publish(
        bus,
        EventTopic.RUNTIME_PROFILE_UPDATED,
        {
            "runtime_id": runtime_id,
            "version": version,
        },
    )


async def publish_configuration_changed(bus: EventBus, runtime_id: str, key: str = "") -> None:
    await _publish(
        bus,
        EventTopic.RUNTIME_CONFIGURATION_CHANGED,
        {
            "runtime_id": runtime_id,
            "key": key,
        },
    )


async def publish_telemetry_recorded(bus: EventBus, runtime_id: str, tasks_completed: int) -> None:
    await _publish(
        bus,
        EventTopic.RUNTIME_TELEMETRY_RECORDED,
        {
            "runtime_id": runtime_id,
            "tasks_completed": tasks_completed,
        },
    )


async def publish_registry_registered(
    bus: EventBus, runtime_id: str, name: str, runtime_type: str
) -> None:
    await _publish(
        bus,
        EventTopic.RUNTIME_REGISTRY_REGISTERED,
        {
            "runtime_id": runtime_id,
            "name": name,
            "runtime_type": runtime_type,
        },
    )


async def publish_registry_unregistered(bus: EventBus, runtime_id: str, name: str) -> None:
    await _publish(
        bus,
        EventTopic.RUNTIME_REGISTRY_UNREGISTERED,
        {
            "runtime_id": runtime_id,
            "name": name,
        },
    )
