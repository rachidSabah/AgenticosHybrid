"""Dashboard broadcaster.

Bridges the event bus to live WebSocket clients. Subscribes to all operational
topics and fans each event out to connected dashboards. This is the final hop of
the vertical slice: live updates in the browser.
"""

from __future__ import annotations

from typing import Any

import anyio
from anyio.streams.memory import MemoryObjectSendStream

from agentic_os.domain.events import EventEnvelope, Topic
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.event_bus import EventBus

log = get_logger("api.dashboard")

# Every operational topic is forwarded to live dashboards so Mission Control
# visualizes the real EventBus. Broadening this set is additive — existing
# subscribers still receive their events; no public interface changes.
_DASHBOARD_TOPICS = [
    # Task / agent lifecycle
    Topic.TASK_CREATED,
    Topic.TASK_PLANNED,
    Topic.TASK_DISPATCHED,
    Topic.TASK_ASSIGNED,
    Topic.AGENT_STARTED,
    Topic.AGENT_COMPLETED,
    Topic.AGENT_FAILED,
    Topic.AGENT_RECOVERED,
    # Supervision
    Topic.HEALTH_CHECK,
    Topic.HEALTH_DEGRADED,
    Topic.RECOVERY_TRIGGERED,
    # Provider management
    Topic.PROVIDER_HEALTH,
    Topic.PROVIDER_REGISTERED,
    Topic.PROVIDER_FAILED,
    Topic.PROVIDER_FAILOVER,
    Topic.COST_RECORDED,
    # Memory
    Topic.MEMORY_WRITTEN,
    Topic.MEMORY_EVICTED,
    # Capability
    Topic.AGENT_COMPOSED,
    # Security
    Topic.APPROVAL_REQUESTED,
    Topic.APPROVAL_DECIDED,
    Topic.AUDIT,
    Topic.TOOL_DENIED,
]


class DashboardBroadcaster:
    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        self._clients: set[MemoryObjectSendStream] = set()

    async def start(self) -> None:
        for topic in _DASHBOARD_TOPICS:
            await self._bus.subscribe(topic.value, self._on_event)

    async def stop(self) -> None:
        pass

    def add_client(self) -> tuple[Any, MemoryObjectSendStream]:
        send, recv = anyio.create_memory_object_stream(max_buffer_size=256)
        self._clients.add(send)
        return recv, send

    def remove_client(self, send: MemoryObjectSendStream) -> None:
        self._clients.discard(send)

    async def _on_event(self, event: EventEnvelope) -> None:
        snapshot = event.model_dump(mode="json")
        for client in list(self._clients):
            try:
                await client.send(snapshot)
            except anyio.BrokenResourceError:
                self._clients.discard(client)
