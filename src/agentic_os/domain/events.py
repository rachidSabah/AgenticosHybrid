"""Domain event envelope and topic taxonomy.

Every message on the Event Bus is wrapped in an :class:`EventEnvelope` so that
consumers get a uniform shape (id, type, source, timestamp, payload). The bus
itself is payload-agnostic; topics are plain strings defined here as constants
to avoid drift across producers/consumers.
"""

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Topic(StrEnum):
    """Canonical event topics. Consumers subscribe to one or more of these."""

    TASK_CREATED = "task.created"
    TASK_PLANNED = "task.planned"
    TASK_DISPATCHED = "task.dispatched"
    TASK_ASSIGNED = "task.assigned"
    AGENT_STARTED = "agent.started"
    AGENT_HEARTBEAT = "agent.heartbeat"
    AGENT_COMPLETED = "agent.completed"
    AGENT_FAILED = "agent.failed"
    AGENT_RECOVERED = "agent.recovered"
    HEALTH_CHECK = "health.check"
    HEALTH_DEGRADED = "health.degraded"
    RECOVERY_TRIGGERED = "recovery.triggered"
    DASHBOARD = "dashboard.event"
    # Provider management
    PROVIDER_HEALTH = "provider.health"
    PROVIDER_REGISTERED = "provider.registered"
    PROVIDER_FAILED = "provider.failed"
    PROVIDER_FAILOVER = "provider.failover"
    COST_RECORDED = "cost.recorded"
    # Memory
    MEMORY_WRITTEN = "memory.written"
    MEMORY_EVICTED = "memory.evicted"
    # Capability
    AGENT_COMPOSED = "agent.composed"
    # Security
    APPROVAL_REQUESTED = "approval.requested"
    APPROVAL_DECIDED = "approval.decided"
    AUDIT = "audit.event"
    TOOL_DENIED = "tool.denied"
    # Workflow (Phase 3B)
    WORKFLOW_CREATED = "workflow.created"
    WORKFLOW_UPDATED = "workflow.updated"
    WORKFLOW_DELETED = "workflow.deleted"
    WORKFLOW_STARTED = "workflow.started"
    WORKFLOW_NODE_STARTED = "workflow.node_started"
    WORKFLOW_NODE_COMPLETED = "workflow.node_completed"
    WORKFLOW_NODE_FAILED = "workflow.node_failed"
    WORKFLOW_COMPLETED = "workflow.completed"
    WORKFLOW_FAILED = "workflow.failed"
    WORKFLOW_CANCELLED = "workflow.cancelled"
    WORKFLOW_PAUSED = "workflow.paused"
    WORKFLOW_RESUMED = "workflow.resumed"
    WORKFLOW_APPROVAL_REQUESTED = "workflow.approval_requested"
    WORKFLOW_APPROVAL_DECIDED = "workflow.approval_decided"
    WORKFLOW_REPLAYED = "workflow.replayed"
    # Pipeline (Phase 3B)
    PIPELINE_CREATED = "pipeline.created"
    PIPELINE_UPDATED = "pipeline.updated"
    PIPELINE_DELETED = "pipeline.deleted"
    PIPELINE_STARTED = "pipeline.started"
    PIPELINE_STAGE_STARTED = "pipeline.stage_started"
    PIPELINE_STAGE_COMPLETED = "pipeline.stage_completed"
    PIPELINE_STAGE_FAILED = "pipeline.stage_failed"
    PIPELINE_COMPLETED = "pipeline.completed"
    PIPELINE_FAILED = "pipeline.failed"
    PIPELINE_CANCELLED = "pipeline.cancelled"
    PIPELINE_PAUSED = "pipeline.paused"
    PIPELINE_RESUMED = "pipeline.resumed"
    PIPELINE_SCHEDULED = "pipeline.scheduled"
    PIPELINE_UNSCHEDULED = "pipeline.unscheduled"
    PIPELINE_ROLLED_BACK = "pipeline.rolled_back"
    # MCP (Phase 3B)
    MCP_SERVER_REGISTERED = "mcp.server_registered"
    MCP_SERVER_UPDATED = "mcp.server_updated"
    MCP_SERVER_UNREGISTERED = "mcp.server_unregistered"
    MCP_SERVER_STARTED = "mcp.server_started"
    MCP_SERVER_STOPPED = "mcp.server_stopped"
    MCP_SERVER_FAILED = "mcp.server_failed"
    MCP_HEALTH_CHANGED = "mcp.health_changed"
    MCP_TOOL_INVOKED = "mcp.tool_invoked"
    MCP_PERMISSIONS_CHANGED = "mcp.permissions_changed"
    # MCP Session (Phase 4, M3)
    MCP_SESSION_CREATED = "mcp.session_created"
    MCP_SESSION_DESTROYED = "mcp.session_destroyed"
    MCP_SESSION_EXPIRED = "mcp.session_expired"
    # MCP Resources (Phase 4, M3)
    MCP_RESOURCE_CHANGED = "mcp.resource_changed"
    MCP_RESOURCE_UPDATED = "mcp.resource_updated"
    # MCP Transport (Phase 4, M3)
    MCP_TRANSPORT_CONNECTED = "mcp.transport_connected"
    MCP_TRANSPORT_DISCONNECTED = "mcp.transport_disconnected"
    MCP_TRANSPORT_ERROR = "mcp.transport_error"
    # MCP Capability Negotiation (Phase 4, M3)
    MCP_CAPABILITY_NEGOTIATED = "mcp.capability_negotiated"
    # MCP Tool Discovery (Phase 4, M3)
    MCP_TOOL_DISCOVERED = "mcp.tool_discovered"
    MCP_TOOL_ERROR = "mcp.tool_error"
    # Plugin (Phase 3B)
    PLUGIN_INSTALLED = "plugin.installed"
    PLUGIN_UNINSTALLED = "plugin.uninstalled"
    PLUGIN_UPDATED = "plugin.updated"
    PLUGIN_STARTED = "plugin.started"
    PLUGIN_STOPPED = "plugin.stopped"
    PLUGIN_FAILED = "plugin.failed"
    PLUGIN_HEALTH_CHANGED = "plugin.health_changed"
    PLUGIN_CAPABILITY_REGISTERED = "plugin.capability_registered"
    # Execution Engine (Phase 4)
    ENGINE_REGISTERED = "engine.registered"
    ENGINE_UNREGISTERED = "engine.unregistered"
    ENGINE_UPDATED = "engine.updated"
    ENGINE_ONLINE = "engine.online"
    ENGINE_OFFLINE = "engine.offline"
    ENGINE_ERROR = "engine.error"
    ENGINE_DISCOVERED = "engine.discovered"
    ENGINE_LOST = "engine.lost"
    ENGINE_CAPABILITIES_CHANGED = "engine.capabilities_changed"
    ENGINE_EXECUTION_STARTED = "engine.execution_started"
    ENGINE_EXECUTION_COMPLETED = "engine.execution_completed"
    ENGINE_EXECUTION_FAILED = "engine.execution_failed"
    ENGINE_HEALTH_CHANGED = "engine.health_changed"
    ENGINE_BENCHMARK_COMPLETED = "engine.benchmark_completed"
    # Discovery & Profiling (Phase 4, M2)
    DISCOVERY_SCAN_STARTED = "discovery.scan_started"
    DISCOVERY_SCAN_COMPLETED = "discovery.scan_completed"
    DISCOVERY_PROVIDER_RUNNING = "discovery.provider_running"
    DISCOVERY_PROVIDER_FAILED = "discovery.provider_failed"
    DISCOVERY_ENGINE_FOUND = "discovery.engine_found"
    DISCOVERY_ENGINE_LOST = "discovery.engine_lost"
    DISCOVERY_ENGINE_REJECTED = "discovery.engine_rejected"
    DISCOVERY_CACHE_HIT = "discovery.cache_hit"
    DISCOVERY_CACHE_MISS = "discovery.cache_miss"
    DISCOVERY_PROFILE_ACTIVATED = "discovery.profile_activated"
    DISCOVERY_PROFILE_DEACTIVATED = "discovery.profile_deactivated"
    VALIDATION_STARTED = "validation.started"
    VALIDATION_PASSED = "validation.passed"
    VALIDATION_FAILED = "validation.failed"
    VALIDATION_SKIPPED = "validation.skipped"
    PROFILING_STARTED = "profiling.started"
    PROFILING_COMPLETED = "profiling.completed"

    # Orchestration & Swarm Intelligence (Phase 4, M3)
    # Swarm lifecycle (7)
    ORCH_SWARM_CREATED = "orchestration.swarm_created"
    ORCH_SWARM_DELETED = "orchestration.swarm_deleted"
    ORCH_SWARM_UPDATED = "orchestration.swarm_updated"
    ORCH_SWARM_ACTIVATED = "orchestration.swarm_activated"
    ORCH_SWARM_DEACTIVATED = "orchestration.swarm_deactivated"
    ORCH_AGENT_JOINED = "orchestration.agent_joined"
    ORCH_AGENT_LEFT = "orchestration.agent_left"
    # Task orchestration (9)
    ORCH_TASK_CREATED = "orchestration.task_created"
    ORCH_TASK_DECOMPOSED = "orchestration.task_decomposed"
    ORCH_TASK_ASSIGNED = "orchestration.task_assigned"
    ORCH_TASK_STARTED = "orchestration.task_started"
    ORCH_TASK_COMPLETED = "orchestration.task_completed"
    ORCH_TASK_FAILED = "orchestration.task_failed"
    ORCH_TASK_CANCELLED = "orchestration.task_cancelled"
    ORCH_PLAN_CREATED = "orchestration.plan_created"
    ORCH_PLAN_COMPLETED = "orchestration.plan_completed"
    # Coordination patterns (12)
    ORCH_COORD_SEQUENTIAL_STARTED = "orchestration.coord_sequential_started"
    ORCH_COORD_SEQUENTIAL_COMPLETED = "orchestration.coord_sequential_completed"
    ORCH_COORD_PARALLEL_STARTED = "orchestration.coord_parallel_started"
    ORCH_COORD_PARALLEL_COMPLETED = "orchestration.coord_parallel_completed"
    ORCH_COORD_FAN_OUT_STARTED = "orchestration.coord_fan_out_started"
    ORCH_COORD_FAN_OUT_COMPLETED = "orchestration.coord_fan_out_completed"
    ORCH_COORD_FAN_IN_STARTED = "orchestration.coord_fan_in_started"
    ORCH_COORD_FAN_IN_COMPLETED = "orchestration.coord_fan_in_completed"
    ORCH_COORD_HIERARCHICAL_STARTED = "orchestration.coord_hierarchical_started"
    ORCH_COORD_HIERARCHICAL_COMPLETED = "orchestration.coord_hierarchical_completed"
    ORCH_COORD_VOTING_STARTED = "orchestration.coord_voting_started"
    ORCH_COORD_VOTING_COMPLETED = "orchestration.coord_voting_completed"
    # Swarm intelligence (6)
    ORCH_CONSENSUS_STARTED = "orchestration.consensus_started"
    ORCH_CONSENSUS_REACHED = "orchestration.consensus_reached"
    ORCH_CONSENSUS_FAILED = "orchestration.consensus_failed"
    ORCH_VOTE_CAST = "orchestration.vote_cast"
    ORCH_LEADER_ELECTION_STARTED = "orchestration.leader_election_started"
    ORCH_LEADER_ELECTED = "orchestration.leader_elected"
    # Communication (3)
    ORCH_MSG_SENT = "orchestration.msg_sent"
    ORCH_MSG_RECEIVED = "orchestration.msg_received"
    ORCH_MSG_BROADCAST = "orchestration.msg_broadcast"


class EventEnvelope(BaseModel):
    """Wire format for everything published to the bus."""

    id: str = Field(default_factory=lambda: uuid4().hex)
    type: str
    source: str
    topic: str
    timestamp: datetime = Field(default_factory=_utcnow)
    payload: dict = Field(default_factory=dict)

    def route_to(self, topic: Topic) -> EventEnvelope:
        """Return a copy of this envelope re-targeted at a new topic."""
        return self.model_copy(update={"topic": topic.value, "id": uuid4().hex})
