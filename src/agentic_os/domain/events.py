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
