"""Discovery WebSocket broadcaster.

Subscribes to discovery lifecycle topics and fans events out to connected
Mission Control clients that care about runtime discovery, validation,
profiling, and engine state changes.
"""

from __future__ import annotations

from typing import Any

import anyio
from anyio.streams.memory import MemoryObjectSendStream

from agentic_os.domain.events import EventEnvelope, Topic
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.event_bus import EventBus

log = get_logger("api.discovery_ws")

# All discovery-specific topics streamed to /ws/discovery clients.
_DISCOVERY_TOPICS = [
    # Discovery lifecycle
    Topic.DISCOVERY_SCAN_STARTED,
    Topic.DISCOVERY_SCAN_COMPLETED,
    Topic.DISCOVERY_PROVIDER_RUNNING,
    Topic.DISCOVERY_PROVIDER_FAILED,
    Topic.DISCOVERY_ENGINE_FOUND,
    Topic.DISCOVERY_ENGINE_LOST,
    Topic.DISCOVERY_ENGINE_REJECTED,
    Topic.DISCOVERY_CACHE_HIT,
    Topic.DISCOVERY_CACHE_MISS,
    Topic.DISCOVERY_PROFILE_ACTIVATED,
    Topic.DISCOVERY_PROFILE_DEACTIVATED,
    # Engine lifecycle
    Topic.ENGINE_DISCOVERED,
    Topic.ENGINE_LOST,
    Topic.ENGINE_REGISTERED,
    Topic.ENGINE_UNREGISTERED,
    Topic.ENGINE_UPDATED,
    Topic.ENGINE_ONLINE,
    Topic.ENGINE_OFFLINE,
    Topic.ENGINE_ERROR,
    Topic.ENGINE_CAPABILITIES_CHANGED,
    # Validation
    Topic.VALIDATION_STARTED,
    Topic.VALIDATION_PASSED,
    Topic.VALIDATION_FAILED,
    Topic.VALIDATION_SKIPPED,
    # Profiling
    Topic.PROFILING_STARTED,
    Topic.PROFILING_COMPLETED,
    # Plugins (discoverable artifacts)
    Topic.PLUGIN_INSTALLED,
    Topic.PLUGIN_UNINSTALLED,
    Topic.PLUGIN_UPDATED,
    Topic.PLUGIN_STARTED,
    Topic.PLUGIN_STOPPED,
    Topic.PLUGIN_FAILED,
    # Phase 6.1 — Local Agent Discovery
    Topic.AGENT_DISCOVERED,
    Topic.AGENT_REGISTERED,
    Topic.AGENT_UPDATED,
    Topic.AGENT_STARTED_STATUS,
    Topic.AGENT_STOPPED_STATUS,
    Topic.AGENT_CRASHED,
    Topic.AGENT_HEALTH_CHANGED,
    Topic.AGENT_VERSION_CHANGED,
    Topic.AGENT_REMOVED,
    Topic.DISCOVERY_STARTED,
    Topic.DISCOVERY_COMPLETED,
    Topic.DISCOVERY_FAILED,
]


class DiscoveryBroadcaster:
    """Fans discovery lifecycle events to connected WebSocket clients."""

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        self._clients: set[MemoryObjectSendStream] = set()
        self._subscriptions: list[str] = []

    async def start(self) -> None:
        self._subscriptions = []
        for topic in _DISCOVERY_TOPICS:
            sub_id = await self._bus.subscribe(topic.value, self._on_event)
            self._subscriptions.append(sub_id)
        log.info("discovery_ws.started", topics=len(_DISCOVERY_TOPICS))

    async def stop(self) -> None:
        for sub_id in self._subscriptions:
            try:
                await self._bus.unsubscribe(sub_id)
            except Exception:
                log.warning("Failed to unsubscribe %s", sub_id, exc_info=True)
        self._subscriptions.clear()
        for client in list(self._clients):
            try:
                client.close()
            except Exception:
                pass
        self._clients.clear()

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
            except anyio.ClosedResourceError:
                self._clients.discard(client)
            except Exception:
                log.debug("Failed to deliver discovery event to a client", exc_info=True)
                self._clients.discard(client)


__all__ = ["DiscoveryBroadcaster"]
