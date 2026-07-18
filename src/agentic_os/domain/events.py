"""Domain event envelope and topic taxonomy.

Every message on the Event Bus is wrapped in an :class:`EventEnvelope` so that
consumers get a uniform shape (id, type, source, timestamp, payload). The bus
itself is payload-agnostic; topics are plain strings defined here as constants
to avoid drift across producers/consumers.
"""

from __future__ import annotations

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
    # Plugin (Phase 3B)
    PLUGIN_INSTALLED = "plugin.installed"
    PLUGIN_UNINSTALLED = "plugin.uninstalled"
    PLUGIN_UPDATED = "plugin.updated"
    PLUGIN_STARTED = "plugin.started"
    PLUGIN_STOPPED = "plugin.stopped"
    PLUGIN_FAILED = "plugin.failed"
    PLUGIN_HEALTH_CHANGED = "plugin.health_changed"
    PLUGIN_CAPABILITY_REGISTERED = "plugin.capability_registered"


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
