"""Dashboard broadcaster.

Bridges the event bus to live WebSocket clients. Subscribes to all operational
topics and fans each event out to connected dashboards. This is the final hop of
the vertical slice: live updates in the browser.
"""

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
    # MCP Runtime (Phase 4, M3) — server lifecycle
    Topic.MCP_SERVER_REGISTERED,
    Topic.MCP_SERVER_UPDATED,
    Topic.MCP_SERVER_UNREGISTERED,
    Topic.MCP_SERVER_STARTED,
    Topic.MCP_SERVER_STOPPED,
    Topic.MCP_SERVER_FAILED,
    # MCP — health, tools, permissions
    Topic.MCP_HEALTH_CHANGED,
    Topic.MCP_TOOL_INVOKED,
    Topic.MCP_PERMISSIONS_CHANGED,
    Topic.MCP_TOOL_DISCOVERED,
    Topic.MCP_TOOL_ERROR,
    # MCP — sessions
    Topic.MCP_SESSION_CREATED,
    Topic.MCP_SESSION_DESTROYED,
    Topic.MCP_SESSION_EXPIRED,
    # MCP — resources & prompts
    Topic.MCP_RESOURCE_CHANGED,
    Topic.MCP_RESOURCE_UPDATED,
    # MCP — transport
    Topic.MCP_TRANSPORT_CONNECTED,
    Topic.MCP_TRANSPORT_DISCONNECTED,
    Topic.MCP_TRANSPORT_ERROR,
    # MCP — capability negotiation
    Topic.MCP_CAPABILITY_NEGOTIATED,
    # Phase 5: Learning & Optimization Engine — execution, predictions, recommendations
    Topic.LEARN_EXECUTION_RECORDED,
    Topic.LEARN_PROFILE_UPDATED,
    Topic.LEARN_RECOMMENDATION_GENERATED,
    Topic.LEARN_RECOMMENDATION_APPLIED,
    Topic.LEARN_BENCHMARK_COMPLETED,
    Topic.LEARN_PREDICTION_MADE,
    Topic.LEARN_PATTERN_DETECTED,
    Topic.LEARN_KNOWLEDGE_EXTRACTED,
    Topic.LEARN_ROUTING_DECISION,
    Topic.LEARN_OPTIMIZATION_APPLIED,
    Topic.LEARN_ANOMALY_DETECTED,
    Topic.LEARN_TREND_CHANGED,
    Topic.LEARN_EXPERIENCE_RECORDED,
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
