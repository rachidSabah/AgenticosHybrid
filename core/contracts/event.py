"""Event contracts — the typed envelope that flows on the Event Bus.

Events are the only mechanism by which components communicate state changes.
Every event has:
  - A unique id (UUID).
  - A monotonic sequence number per stream.
  - A timestamp (UTC).
  - A correlation_id (the task that caused this event).
  - A causation_id (the event that triggered this event, if any).
  - A topic (string, dot-separated, e.g. ``agent.dispatched``).
  - A payload (Pydantic-validated against the topic's schema).
  - An actor (who emitted this event).

INV-04: every event is persisted to the event store BEFORE any subscriber is
allowed to observe a side effect.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from core.contracts.actor import ActorRef
from core.contracts.timestamp import utc_now


class EventTopic(StrEnum):
    """Reserved event topics.

    Custom topics are allowed (plugins, agents) but must use a namespace
    that doesn't collide with these (e.g. ``plugin.slack.message_sent``).
    """

    # --- Task lifecycle ---
    TASK_CREATED = "task.created"
    TASK_QUEUED = "task.queued"
    TASK_STARTED = "task.started"
    TASK_PAUSED = "task.paused"
    TASK_RESUMED = "task.resumed"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    TASK_CANCELLED = "task.cancelled"

    # --- Step lifecycle ---
    STEP_DISPATCHED = "step.dispatched"
    STEP_STARTED = "step.started"
    STEP_PROGRESS = "step.progress"
    STEP_COMPLETED = "step.completed"
    STEP_FAILED = "step.failed"
    STEP_RETIRED = "step.retired"
    STEP_COMMITTED = "step.committed"

    # --- Agent lifecycle ---
    AGENT_REGISTERED = "agent.registered"
    AGENT_UNREGISTERED = "agent.unregistered"
    AGENT_HEALTH_CHANGED = "agent.health_changed"
    AGENT_DISPATCHED = "agent.dispatched"
    AGENT_ACTION = "agent.action"

    # --- Approval gates ---
    APPROVAL_REQUESTED = "approval.requested"
    APPROVAL_RESPONDED = "approval.responded"

    # --- Plugin lifecycle ---
    PLUGIN_INSTALLED = "plugin.installed"
    PLUGIN_ENABLED = "plugin.enabled"
    PLUGIN_DISABLED = "plugin.disabled"
    PLUGIN_UNINSTALLED = "plugin.uninstalled"
    PLUGIN_RELOADED = "plugin.reloaded"

    # --- Execution engine lifecycle ---
    EXECUTION_ENGINE_DISCOVERED = "execution.engine.discovered"
    EXECUTION_ENGINE_REGISTERED = "execution.engine.registered"
    EXECUTION_ENGINE_UNREGISTERED = "execution.engine.unregistered"
    EXECUTION_ENGINE_HEALTH_CHANGED = "execution.engine.health_changed"
    EXECUTION_ENGINE_ENABLED = "execution.engine.enabled"
    EXECUTION_ENGINE_DISABLED = "execution.engine.disabled"

    # --- Execution task lifecycle ---
    EXECUTION_TASK_CREATED = "execution.task.created"
    EXECUTION_TASK_QUEUED = "execution.task.queued"
    EXECUTION_TASK_DISPATCHED = "execution.task.dispatched"
    EXECUTION_TASK_STARTED = "execution.task.started"
    EXECUTION_TASK_PROGRESS = "execution.task.progress"
    EXECUTION_TASK_COMPLETED = "execution.task.completed"
    EXECUTION_TASK_FAILED = "execution.task.failed"
    EXECUTION_TASK_CANCELLED = "execution.task.cancelled"
    EXECUTION_TASK_TIMEOUT = "execution.task.timeout"

    # --- Execution session lifecycle ---
    EXECUTION_SESSION_CREATED = "execution.session.created"
    EXECUTION_SESSION_ACTIVE = "execution.session.active"
    EXECUTION_SESSION_CLOSED = "execution.session.closed"
    EXECUTION_SESSION_ERROR = "execution.session.error"

    # --- Execution routing ---
    EXECUTION_ROUTE_SELECTED = "execution.route.selected"
    EXECUTION_ROUTE_FAILOVER = "execution.route.failover"
    EXECUTION_ROUTE_FALLBACK = "execution.route.fallback"

    # --- Execution benchmark ---
    EXECUTION_BENCHMARK_STARTED = "execution.benchmark.started"
    EXECUTION_BENCHMARK_COMPLETED = "execution.benchmark.completed"
    EXECUTION_BENCHMARK_FAILED = "execution.benchmark.failed"

    # --- Runtime discovery ---
    RUNTIME_DISCOVERY_SCAN_STARTED = "runtime.discovery.scan_started"
    RUNTIME_DISCOVERY_SCAN_COMPLETED = "runtime.discovery.scan_completed"
    RUNTIME_DISCOVERY_PROVIDER_RUNNING = "runtime.discovery.provider_running"
    RUNTIME_DISCOVERY_PROVIDER_FAILED = "runtime.discovery.provider_failed"
    RUNTIME_DISCOVERY_ENGINE_FOUND = "runtime.discovery.engine_found"
    RUNTIME_DISCOVERY_ENGINE_LOST = "runtime.discovery.engine_lost"
    RUNTIME_DISCOVERY_CACHE_HIT = "runtime.discovery.cache_hit"
    RUNTIME_DISCOVERY_CACHE_MISS = "runtime.discovery.cache_miss"
    RUNTIME_DISCOVERY_PROFILE_ACTIVATED = "runtime.discovery.profile_activated"
    RUNTIME_DISCOVERY_PROFILE_DEACTIVATED = "runtime.discovery.profile_deactivated"

    # --- Runtime binding ---
    RUNTIME_BINDING_STARTED = "runtime.binding.started"
    RUNTIME_BINDING_COMPLETED = "runtime.binding.completed"
    RUNTIME_BINDING_FAILED = "runtime.binding.failed"
    RUNTIME_BINDING_UNBOUND = "runtime.binding.unbound"

    # --- Runtime validation ---
    RUNTIME_VALIDATION_STARTED = "runtime.validation.started"
    RUNTIME_VALIDATION_PASSED = "runtime.validation.passed"
    RUNTIME_VALIDATION_FAILED = "runtime.validation.failed"
    RUNTIME_VALIDATION_SKIPPED = "runtime.validation.skipped"

    # --- Runtime health ---
    RUNTIME_HEALTH_CHECK_PASSED = "runtime.health.check_passed"
    RUNTIME_HEALTH_CHECK_FAILED = "runtime.health.check_failed"
    RUNTIME_HEALTH_STATUS_CHANGED = "runtime.health.status_changed"
    RUNTIME_HEALTH_DEGRADED = "runtime.health.degraded"
    RUNTIME_HEALTH_RECOVERED = "runtime.health.recovered"

    # --- Runtime profile ---
    RUNTIME_PROFILE_CREATED = "runtime.profile.created"
    RUNTIME_PROFILE_UPDATED = "runtime.profile.updated"
    RUNTIME_PROFILE_DELETED = "runtime.profile.deleted"

    # --- Runtime configuration ---
    RUNTIME_CONFIGURATION_CHANGED = "runtime.configuration.changed"
    RUNTIME_CONFIGURATION_RESET = "runtime.configuration.reset"

    # --- Runtime telemetry ---
    RUNTIME_TELEMETRY_RECORDED = "runtime.telemetry.recorded"
    RUNTIME_TELEMETRY_FLUSHED = "runtime.telemetry.flushed"

    # --- Runtime registry ---
    RUNTIME_REGISTRY_REGISTERED = "runtime.registry.registered"
    RUNTIME_REGISTRY_UNREGISTERED = "runtime.registry.unregistered"
    RUNTIME_REGISTRY_UPDATED = "runtime.registry.updated"

    # --- Config / system ---
    CONFIG_CHANGED = "config.changed"
    SYSTEM_BOOTING = "system.booting"
    SYSTEM_READY = "system.ready"
    SYSTEM_SHUTTING_DOWN = "system.shutting_down"


class Event(BaseModel):
    """A single typed event on the Event Bus.

    The payload is a free-form dict at this level; subscribers are responsible
    for validating it against the topic-specific schema at consumption time.
    This keeps the kernel decoupled from every possible payload type.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID = Field(default_factory=uuid4, description="Globally unique event ID.")
    sequence: int = Field(
        default=0,
        ge=0,
        description="Monotonic per-stream sequence number. Set by the bus on publish.",
    )
    timestamp: datetime = Field(default_factory=utc_now, description="UTC emit time.")
    topic: str = Field(description="Dot-separated topic, e.g. ``agent.dispatched``.")
    correlation_id: UUID = Field(
        description="The task (or other root operation) that caused this event.",
    )
    causation_id: UUID | None = Field(
        default=None,
        description="The event that triggered this event, if any.",
    )
    actor: ActorRef = Field(description="Who emitted this event.")
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Typed payload; subscribers validate against the topic schema.",
    )

    def derived(
        self,
        *,
        topic: str,
        payload: dict[str, Any] | None = None,
        actor: ActorRef | None = None,
    ) -> Event:
        """Return a new event caused by this one (causation_id = self.id).

        The correlation_id is preserved. The new event gets a fresh id and
        timestamp; the bus assigns the sequence number on publish.
        """
        return Event(
            topic=topic,
            correlation_id=self.correlation_id,
            causation_id=self.id,
            actor=actor or self.actor,
            payload=payload or {},
        )


class EventEnvelope(BaseModel):
    """A wire-format envelope for cross-process event delivery (Redis adapter, OTLP).

    The envelope wraps an Event with delivery metadata (delivery attempts,
        last-delivered-at, redelivery-after).
    """

    event: Event
    delivery_attempts: int = 0
    last_delivered_at: datetime | None = None
    redeliver_after: datetime | None = None
