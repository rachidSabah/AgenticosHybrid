"""Runtime EventBus integration — all runtime events as typed dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


def _utcnow() -> datetime:
    return datetime.now(UTC)


# ── Event Names ─────────────────────────────────────────────────────────────

RUNTIME_EVENTS = {
    "RUNTIME_DISCOVERED": "runtime.discovered",
    "RUNTIME_REGISTERED": "runtime.registered",
    "RUNTIME_STARTED": "runtime.started",
    "RUNTIME_READY": "runtime.ready",
    "RUNTIME_BUSY": "runtime.busy",
    "RUNTIME_IDLE": "runtime.idle",
    "RUNTIME_STREAM_STARTED": "runtime.stream.started",
    "RUNTIME_STREAM_ENDED": "runtime.stream.ended",
    "RUNTIME_COMMAND_STARTED": "runtime.command.started",
    "RUNTIME_COMMAND_COMPLETED": "runtime.command.completed",
    "RUNTIME_COMMAND_FAILED": "runtime.command.failed",
    "RUNTIME_LOG": "runtime.log",
    "RUNTIME_HEARTBEAT": "runtime.heartbeat",
    "RUNTIME_STOPPED": "runtime.stopped",
    "RUNTIME_CRASHED": "runtime.crashed",
    "RUNTIME_RESTARTED": "runtime.restarted",
    "RUNTIME_RECOVERED": "runtime.recovered",
    "RUNTIME_HEALTH_CHANGED": "runtime.health.changed",
    "RUNTIME_SESSION_CREATED": "runtime.session.created",
    "RUNTIME_SESSION_CLOSED": "runtime.session.closed",
    "RUNTIME_REMOVED": "runtime.removed",
    "RUNTIME_METRICS": "runtime.metrics",
    "RUNTIME_UPDATED": "runtime.updated",
}

# Build reverse lookup
EVENT_NAMES = {v: k for k, v in RUNTIME_EVENTS.items()}


# ── Event Payloads ──────────────────────────────────────────────────────────


@dataclass
class RuntimeEvent:
    """Base runtime event with common fields."""

    topic: str
    runtime_id: str
    runtime_name: str
    timestamp: datetime = field(default_factory=_utcnow)
    payload: dict[str, Any] = field(default_factory=dict)
    session_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "runtime_id": self.runtime_id,
            "runtime_name": self.runtime_name,
            "timestamp": self.timestamp.isoformat(),
            "payload": self.payload,
            "session_id": self.session_id,
        }


def make_runtime_event(
    topic: str,
    runtime_id: str,
    runtime_name: str,
    **extra: Any,
) -> RuntimeEvent:
    """Factory helper to create a RuntimeEvent."""
    return RuntimeEvent(
        topic=topic,
        runtime_id=runtime_id,
        runtime_name=runtime_name,
        payload=extra,
    )


# ── Publish helpers ─────────────────────────────────────────────────────────


async def publish_runtime_event(
    bus: Any,
    topic: str,
    runtime_id: str,
    runtime_name: str,
    **extra: Any,
) -> None:
    """Publish a runtime event to the EventBus."""
    if bus is None:
        return
    event = make_runtime_event(topic, runtime_id, runtime_name, **extra)
    await bus.publish(topic, event.to_dict())


async def publish_runtime_discovered(bus: Any, rid: str, name: str, **kw: Any) -> None:
    await publish_runtime_event(bus, RUNTIME_EVENTS["RUNTIME_DISCOVERED"], rid, name, **kw)


async def publish_runtime_registered(bus: Any, rid: str, name: str, **kw: Any) -> None:
    await publish_runtime_event(bus, RUNTIME_EVENTS["RUNTIME_REGISTERED"], rid, name, **kw)


async def publish_runtime_started(
    bus: Any, rid: str, name: str, pid: int | None = None, **kw: Any
) -> None:
    await publish_runtime_event(bus, RUNTIME_EVENTS["RUNTIME_STARTED"], rid, name, pid=pid, **kw)


async def publish_runtime_ready(bus: Any, rid: str, name: str, **kw: Any) -> None:
    await publish_runtime_event(bus, RUNTIME_EVENTS["RUNTIME_READY"], rid, name, **kw)


async def publish_runtime_stopped(
    bus: Any, rid: str, name: str, exit_code: int | None = None, **kw: Any
) -> None:
    await publish_runtime_event(
        bus, RUNTIME_EVENTS["RUNTIME_STOPPED"], rid, name, exit_code=exit_code, **kw
    )


async def publish_runtime_crashed(bus: Any, rid: str, name: str, error: str, **kw: Any) -> None:
    await publish_runtime_event(
        bus, RUNTIME_EVENTS["RUNTIME_CRASHED"], rid, name, error=error, **kw
    )


async def publish_runtime_restarted(bus: Any, rid: str, name: str, **kw: Any) -> None:
    await publish_runtime_event(bus, RUNTIME_EVENTS["RUNTIME_RESTARTED"], rid, name, **kw)


async def publish_runtime_recovered(bus: Any, rid: str, name: str, **kw: Any) -> None:
    await publish_runtime_event(bus, RUNTIME_EVENTS["RUNTIME_RECOVERED"], rid, name, **kw)


async def publish_runtime_health_changed(
    bus: Any, rid: str, name: str, old_health: str, new_health: str, **kw: Any
) -> None:
    await publish_runtime_event(
        bus,
        RUNTIME_EVENTS["RUNTIME_HEALTH_CHANGED"],
        rid,
        name,
        old_health=old_health,
        new_health=new_health,
        **kw,
    )


async def publish_runtime_session_created(
    bus: Any, rid: str, name: str, session_id: str, **kw: Any
) -> None:
    await publish_runtime_event(
        bus, RUNTIME_EVENTS["RUNTIME_SESSION_CREATED"], rid, name, session_id=session_id, **kw
    )


async def publish_runtime_session_closed(
    bus: Any, rid: str, name: str, session_id: str, **kw: Any
) -> None:
    await publish_runtime_event(
        bus, RUNTIME_EVENTS["RUNTIME_SESSION_CLOSED"], rid, name, session_id=session_id, **kw
    )


async def publish_runtime_heartbeat(bus: Any, rid: str, name: str, **kw: Any) -> None:
    await publish_runtime_event(bus, RUNTIME_EVENTS["RUNTIME_HEARTBEAT"], rid, name, **kw)


async def publish_runtime_command(
    bus: Any, rid: str, name: str, command: str, status: str = "started", **kw: Any
) -> None:
    topic = (
        RUNTIME_EVENTS["RUNTIME_COMMAND_STARTED"]
        if status == "started"
        else RUNTIME_EVENTS["RUNTIME_COMMAND_COMPLETED"]
    )
    await publish_runtime_event(bus, topic, rid, name, command=command, status=status, **kw)


async def publish_runtime_command_failed(
    bus: Any, rid: str, name: str, command: str, error: str, **kw: Any
) -> None:
    await publish_runtime_event(
        bus, RUNTIME_EVENTS["RUNTIME_COMMAND_FAILED"], rid, name, command=command, error=error, **kw
    )


async def publish_runtime_removed(bus: Any, rid: str, name: str, **kw: Any) -> None:
    await publish_runtime_event(bus, RUNTIME_EVENTS["RUNTIME_REMOVED"], rid, name, **kw)
