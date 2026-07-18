"""Observability Domain Models

Domain layer for observability - pure Python, no external dependencies.
Follows hexagonal architecture: domain depends on nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4


def _utcnow() -> datetime:
    return datetime.now(UTC)


class SpanKind(StrEnum):
    """Span kinds following OpenTelemetry specification."""

    INTERNAL = "internal"
    SERVER = "server"
    CLIENT = "client"
    PRODUCER = "producer"
    CONSUMER = "consumer"


class SpanStatus(StrEnum):
    """Span status codes."""

    OK = "ok"
    ERROR = "error"
    UNSET = "unset"


class MetricType(StrEnum):
    """Metric types."""

    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"


class LogLevel(StrEnum):
    """Log levels."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class SpanContext:
    """Span context for trace propagation."""

    trace_id: str
    span_id: str
    trace_flags: int = 1  # sampled by default
    trace_state: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "trace_flags": self.trace_flags,
            "trace_state": self.trace_state,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SpanContext:
        return cls(
            trace_id=data["trace_id"],
            span_id=data["span_id"],
            trace_flags=data.get("trace_flags", 1),
            trace_state=data.get("trace_state"),
        )

    @classmethod
    def generate(cls) -> SpanContext:
        """Generate a new span context."""
        return cls(
            trace_id=uuid4().hex,
            span_id=uuid4().hex[:16],
        )


@dataclass(frozen=True, slots=True)
class CorrelationContext:
    """Correlation context for distributed tracing."""

    trace_id: str
    span_id: str
    baggage: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "baggage": self.baggage,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CorrelationContext:
        return cls(
            trace_id=data["trace_id"],
            span_id=data["span_id"],
            baggage=data.get("baggage", {}),
        )

    @classmethod
    def generate(cls) -> CorrelationContext:
        """Generate a new correlation context."""
        return cls(
            trace_id=uuid4().hex,
            span_id=uuid4().hex[:16],
        )


@dataclass(frozen=True, slots=True)
class SpanEvent:
    """Event within a span."""

    name: str
    attributes: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "attributes": self.attributes,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class Span:
    """Distributed trace span."""

    name: str
    context: SpanContext
    parent_context: SpanContext | None = None
    kind: SpanKind = SpanKind.INTERNAL
    attributes: dict[str, Any] = field(default_factory=dict)
    events: tuple[SpanEvent, ...] = field(default_factory=tuple)
    status: SpanStatus = SpanStatus.UNSET
    status_message: str | None = None
    start_time: datetime = field(default_factory=_utcnow)
    end_time: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "context": self.context.to_dict(),
            "parent_context": self.parent_context.to_dict() if self.parent_context else None,
            "kind": self.kind.value,
            "attributes": self.attributes,
            "events": [e.to_dict() for e in self.events],
            "status": self.status.value,
            "status_message": self.status_message,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
        }

    def with_end_time(self, end_time: datetime | None = None) -> Span:
        """Return a new span with end time set."""
        return Span(
            name=self.name,
            context=self.context,
            parent_context=self.parent_context,
            kind=self.kind,
            attributes=self.attributes,
            events=self.events,
            status=self.status,
            status_message=self.status_message,
            start_time=self.start_time,
            end_time=end_time or _utcnow(),
        )

    def with_status(
        self, status: SpanStatus, message: str | None = None
    ) -> Span:
        """Return a new span with status set."""
        return Span(
            name=self.name,
            context=self.context,
            parent_context=self.parent_context,
            kind=self.kind,
            attributes=self.attributes,
            events=self.events,
            status=status,
            status_message=message,
            start_time=self.start_time,
            end_time=self.end_time,
        )

    def with_event(self, event: SpanEvent) -> Span:
        """Return a new span with an event added."""
        return Span(
            name=self.name,
            context=self.context,
            parent_context=self.parent_context,
            kind=self.kind,
            attributes=self.attributes,
            events=self.events + (event,),
            status=self.status,
            status_message=self.status_message,
            start_time=self.start_time,
            end_time=self.end_time,
        )

    def duration_ms(self) -> float | None:
        """Calculate span duration in milliseconds."""
        if self.end_time:
            return (self.end_time - self.start_time).total_seconds() * 1000
        return None

    def is_finished(self) -> bool:
        """Check if span is finished."""
        return self.end_time is not None


@dataclass(frozen=True, slots=True)
class Trace:
    """Complete trace consisting of spans."""

    spans: tuple[Span, ...]
    root_span_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "spans": [s.to_dict() for s in self.spans],
            "root_span_id": self.root_span_id,
        }

    def get_span(self, span_id: str) -> Span | None:
        """Get a span by ID."""
        for span in self.spans:
            if span.context.span_id == span_id:
                return span
        return None

    def get_root_span(self) -> Span | None:
        """Get the root span."""
        if self.root_span_id:
            return self.get_span(self.root_span_id)
        # Fallback: find span with no parent in trace
        span_ids = {s.context.span_id for s in self.spans}
        for span in self.spans:
            if not span.parent_context or span.parent_context.span_id not in span_ids:
                return span
        return self.spans[0] if self.spans else None


@dataclass(frozen=True, slots=True)
class Metric:
    """A metric data point."""

    name: str
    type: MetricType
    value: float
    labels: dict[str, str] = field(default_factory=dict)
    unit: str | None = None
    description: str | None = None
    timestamp: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type.value,
            "value": self.value,
            "labels": self.labels,
            "unit": self.unit,
            "description": self.description,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class LogEntry:
    """Structured log entry."""

    level: str
    message: str
    attributes: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=_utcnow)
    correlation_context: CorrelationContext | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "message": self.message,
            "attributes": self.attributes,
            "timestamp": self.timestamp.isoformat(),
            "correlation_context": (
                self.correlation_context.to_dict() if self.correlation_context else None
            ),
        }


@dataclass(frozen=True, slots=True)
class HealthCheck:
    """Health check result."""

    component: str
    healthy: bool
    message: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "component": self.component,
            "healthy": self.healthy,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
        }


__all__ = [
    "SpanKind",
    "SpanStatus",
    "MetricType",
    "LogLevel",
    "SpanContext",
    "CorrelationContext",
    "SpanEvent",
    "Span",
    "Trace",
    "Metric",
    "LogEntry",
    "HealthCheck",
]