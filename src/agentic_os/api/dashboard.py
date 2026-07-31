"""Dashboard broadcaster.

Bridges the event bus to live WebSocket clients. Subscribes to all operational
topics and fans each event out to connected dashboards. This is the final hop of
the vertical slice: live updates in the browser.

Maintains an in-memory ring buffer of the last 256 events so newly-connected
clients can replay recent history via REST.
"""

from collections import deque
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
    # Phase 6.2: AI Brain Registry — runtime discovery events
    Topic.BRAIN_DISCOVERED,
    Topic.BRAIN_REGISTERED,
    Topic.BRAIN_UPDATED,
    Topic.BRAIN_CONNECTED,
    Topic.BRAIN_DISCONNECTED,
    Topic.BRAIN_HEALTH_CHANGED,
    Topic.BRAIN_BUSY,
    Topic.BRAIN_IDLE,
    Topic.BRAIN_EXECUTING,
    Topic.BRAIN_COMPLETED,
    Topic.BRAIN_FAILED,
    Topic.BRAIN_REMOVED,
    Topic.BRAIN_GRAPH_UPDATED,
    Topic.BRAIN_RELATIONSHIP_CHANGED,
    # Phase 15: Autonomous Agent Ecosystem — ecosystem lifecycle, evolution,
    # optimization, capability/collaboration graph updates. These are string
    # topics (not in the Topic enum) emitted by EcosystemManager — we
    # subscribe to them directly so Mission Control receives live updates.
    "ecosystem.started",
    "ecosystem.updated",
    "ecosystem.health.updated",
    "ecosystem.evolution.generated",
    "ecosystem.optimization.started",
    "ecosystem.optimization.completed",
    "ecosystem.capability.updated",
    "ecosystem.collaboration.updated",
    "ecosystem.analysis.completed",
    "ecosystem.statistics.updated",
    "ecosystem.task.published",
    "ecosystem.task.bids_collected",
    "ecosystem.task.awarded",
    "ecosystem.task.completed",
    "ecosystem.task.failed",
    "ecosystem.task.cancelled",
    # Also forward swarm/executive/cognitive string topics so Mission Control
    # can render Phase 11-14 activity in real time. These were previously
    # published on the bus but not forwarded to WebSocket clients.
    "swarm.created",
    "swarm.execution.started",
    "swarm.execution.completed",
    "swarm.consensus.started",
    "swarm.consensus.completed",
    "swarm.rebalanced",
    "swarm.disbanded",
    "swarm.member.joined",
    "swarm.member.left",
    "executive.started",
    "executive.stopped",
    "executive.mission.created",
    "executive.mission.dispatched",
    "executive.mission.completed",
    "executive.mission.failed",
    "executive.resource.allocated",
    "executive.supervision.recorded",
    "executive.policy.applied",
    "executive.policy.violated",
    "executive.decision",
    "executive.reflection",
    "executive.priority.recomputed",
    "cognitive.world.updated",
    "cognitive.strategy.generated",
    "cognitive.prediction.made",
    "cognitive.evaluation.completed",
    "cognitive.improvement.generated",
    "cognitive.experience.recorded",
    "cognitive.objective.activated",
    # Phase 16: Distributed Runtime Federation — cluster lifecycle, node
    # membership, scheduler, failover, consensus, topology events.
    "cluster.started",
    "cluster.updated",
    "cluster.node.joined",
    "cluster.node.left",
    "cluster.node.updated",
    "cluster.brain.discovered",
    "cluster.brain.removed",
    "cluster.scheduler.started",
    "cluster.scheduler.completed",
    "cluster.failover.started",
    "cluster.failover.completed",
    "cluster.consensus.completed",
    "cluster.topology.updated",
    "cluster.statistics.updated",
    # Phase 17: Autonomous Agent Evolution — improvement lifecycle, safety
    # validation, scheduling, generation, knowledge synthesis events.
    "evolution.started",
    "evolution.stopped",
    "evolution.analysis.completed",
    "evolution.improvement.scheduled",
    "evolution.improvement.applied",
    "evolution.improvement.rolled_back",
    "evolution.knowledge.synthesized",
    "evolution.readiness.updated",
    "evolution.statistics.updated",
    # Phase 17: Distributed Execution Fabric — node lifecycle, leader
    # election, task dispatch, heartbeat, replication events.
    "distributed.started",
    "distributed.stopped",
    "distributed.task.dispatched",
    "distributed.task.completed",
    "distributed.task.failed",
    "node.joined",
    "node.left",
    "node.leader.elected",
    "node.heartbeat.received",
    "node.health.updated",
]

# Normalize the topic list to plain strings. The list above mixes
# ``Topic`` enum instances (with ``.value``) and plain strings (for
# topics not in the enum, e.g. ``ecosystem.*``). Pre-converting avoids
# per-subscription branching in ``start()`` and keeps the type checker
# happy.
_DASHBOARD_TOPIC_STRINGS: list[str] = []
for _t in _DASHBOARD_TOPICS:
    _topic_value: object = getattr(_t, "value", _t)
    _DASHBOARD_TOPIC_STRINGS.append(str(_topic_value))

_MAX_HISTORY = 256


class DashboardBroadcaster:
    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        self._clients: set[MemoryObjectSendStream] = set()
        self._history: deque[dict[str, Any]] = deque(maxlen=_MAX_HISTORY)
        self._subscriptions: list[str] = []

    async def start(self) -> None:
        # Track subscription IDs so stop() can cleanly unsubscribe and avoid
        # leaking subscriptions across kernel restarts / hot reloads.
        self._subscriptions = []
        for topic_str in _DASHBOARD_TOPIC_STRINGS:
            sub_id = await self._bus.subscribe(topic_str, self._on_event)
            self._subscriptions.append(sub_id)

    async def stop(self) -> None:
        for sub_id in self._subscriptions:
            try:
                await self._bus.unsubscribe(sub_id)
            except Exception:
                log.warning("Failed to unsubscribe %s", sub_id, exc_info=True)
        self._subscriptions.clear()
        # Close any remaining client streams so their WS handlers exit promptly.
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

    def get_recent_events(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return the most recent events from the ring buffer (REST replay)."""
        events = list(self._history)
        return events[-limit:]

    async def _on_event(self, event: EventEnvelope) -> None:
        snapshot = event.model_dump(mode="json")
        self._history.append(snapshot)
        # Snapshot the client set so removals during iteration don't skip clients.
        for client in list(self._clients):
            try:
                await client.send(snapshot)
            except anyio.BrokenResourceError:
                self._clients.discard(client)
            except anyio.ClosedResourceError:
                self._clients.discard(client)
            except Exception:
                # Don't let one bad client abort delivery to the rest.
                log.debug("Failed to deliver event to a client", exc_info=True)
                self._clients.discard(client)
