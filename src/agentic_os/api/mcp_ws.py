"""MCP WebSocket broadcaster.

Subscribes exclusively to MCP runtime topics and fans events out to connected
Mission Control clients that care only about MCP server state, tools, resources,
prompts, sessions, and health.
"""

from typing import Any

import anyio
from anyio.streams.memory import MemoryObjectSendStream

from agentic_os.domain.events import EventEnvelope, Topic
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.event_bus import EventBus

log = get_logger("api.mcp_ws")

# All MCP-specific topics streamed to /ws/mcp clients.
_MCP_TOPICS = [
    Topic.MCP_SERVER_REGISTERED,
    Topic.MCP_SERVER_UPDATED,
    Topic.MCP_SERVER_UNREGISTERED,
    Topic.MCP_SERVER_STARTED,
    Topic.MCP_SERVER_STOPPED,
    Topic.MCP_SERVER_FAILED,
    Topic.MCP_HEALTH_CHANGED,
    Topic.MCP_TOOL_INVOKED,
    Topic.MCP_TOOL_DISCOVERED,
    Topic.MCP_TOOL_ERROR,
    Topic.MCP_PERMISSIONS_CHANGED,
    Topic.MCP_SESSION_CREATED,
    Topic.MCP_SESSION_DESTROYED,
    Topic.MCP_SESSION_EXPIRED,
    Topic.MCP_RESOURCE_CHANGED,
    Topic.MCP_RESOURCE_UPDATED,
    Topic.MCP_TRANSPORT_CONNECTED,
    Topic.MCP_TRANSPORT_DISCONNECTED,
    Topic.MCP_TRANSPORT_ERROR,
    Topic.MCP_CAPABILITY_NEGOTIATED,
]


class MCPBroadcaster:
    """Fans MCP runtime events to connected WebSocket clients."""

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        self._clients: set[MemoryObjectSendStream] = set()
        self._subscriptions: list[str] = []

    async def start(self) -> None:
        self._subscriptions = []
        for topic in _MCP_TOPICS:
            sub_id = await self._bus.subscribe(topic.value, self._on_event)
            self._subscriptions.append(sub_id)
        log.info("mcp_ws.started", topics=len(_MCP_TOPICS))

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
                log.debug("Failed to deliver MCP event to a client", exc_info=True)
                self._clients.discard(client)
