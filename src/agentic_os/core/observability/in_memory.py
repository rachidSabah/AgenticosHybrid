"""In-Memory Observability Implementations

Lightweight in-memory implementations for development and testing.
"""

from __future__ import annotations

import contextvars
from collections import defaultdict
from typing import Any

from agentic_os.domain.observability import (
    CorrelationContext,
    LogEntry,
    LogLevel,
    Metric,
    MetricType,
    Span,
    SpanContext,
    SpanKind,
    SpanStatus,
    Trace,
)
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.observability import (
    LoggingPort,
    MetricsPort,
    TracingPort,
)

log = get_logger("observability.in_memory")


class InMemoryTracing(TracingPort):
    """In-memory tracing implementation for development/testing."""

    def __init__(self):
        self._current_span: contextvars.ContextVar[Span | None] = contextvars.ContextVar(
            "current_span", default=None
        )
        self._traces: dict[str, list[Span]] = defaultdict(list)
        self._propagator = TraceContextPropagator()

    def start_span(
        self,
        name: str,
        kind: str = "internal",
        parent: SpanContext | None = None,
        attributes: dict[str, Any] | None = None,
        links: list[tuple[SpanContext, dict[str, Any]]] | None = None,
    ) -> Span:
        """Start a new span."""
        # Create span context
        if parent:
            trace_id = parent.trace_id
        else:
            current = self._current_span.get()
            if current:
                trace_id = current.context.trace_id
            else:
                trace_id = SpanContext.generate().trace_id

        span_context = SpanContext(
            trace_id=trace_id,
            span_id=SpanContext.generate().span_id,
        )

        parent_context = parent
        if not parent_context:
            current = self._current_span.get()
            if current:
                parent_context = current.context

        span = Span(
            name=name,
            context=span_context,
            parent_context=parent_context,
            kind=SpanKind(kind) if kind in SpanKind.__members__.values() else SpanKind.INTERNAL,
            attributes=attributes or {},
        )

        # Track in traces
        self._traces[trace_id].append(span)
        self._current_span.set(span)

        log.debug("span_started", name=name, trace_id=trace_id, span_id=span_context.span_id)
        return span

    def end_span(
        self, span: Span, status: str = "ok", message: str | None = None
    ) -> None:
        """End a span."""
        ended_span = span.with_end_time().with_status(
            SpanStatus(status) if status in SpanStatus.__members__.values() else SpanStatus.OK,
            message,
        )

        # Update in traces
        trace_id = span.context.trace_id
        if trace_id in self._traces:
            self._traces[trace_id] = [
                ended_span if s.context.span_id == span.context.span_id else s
                for s in self._traces[trace_id]
            ]

        # Clear current span if it matches
        if self._current_span.get() is span:
            self._current_span.set(None)

        log.debug(
            "span_ended",
            name=span.name,
            trace_id=trace_id,
            span_id=span.context.span_id,
            duration_ms=ended_span.duration_ms(),
        )

    def get_current_span(self) -> Span | None:
        return self._current_span.get()

    def set_current_span(self, span: Span | None) -> None:
        self._current_span.set(span)

    def get_trace(self, trace_id: str) -> Trace | None:
        spans = self._traces.get(trace_id)
        if not spans:
            return None

        # Find root span
        span_ids = {s.context.span_id for s in spans}
        root_span_id = None
        for span in spans:
            if not span.parent_context or span.parent_context.span_id not in span_ids:
                root_span_id = span.context.span_id
                break

        return Trace(spans=tuple(spans), root_span_id=root_span_id)

    def inject_context(self, context: SpanContext, carrier: dict[str, str]) -> None:
        self._propagator.inject(context, carrier)

    def extract_context(self, carrier: dict[str, str]) -> SpanContext | None:
        return self._propagator.extract(carrier)

    def shutdown(self) -> None:
        pass


class TraceContextPropagator:
    """W3C TraceContext propagator for in-memory tracing."""

    def inject(self, context: SpanContext, carrier: dict[str, str]) -> None:
        carrier["traceparent"] = (
            f"00-{context.trace_id}-{context.span_id}-{context.trace_flags:02x}"
        )
        if context.trace_state:
            carrier["tracestate"] = context.trace_state

    def extract(self, carrier: dict[str, str]) -> SpanContext | None:
        traceparent = carrier.get("traceparent") or carrier.get("Traceparent")
        if not traceparent:
            return None

        parts = traceparent.split("-")
        if len(parts) != 4:
            return None

        _, trace_id, span_id, flags = parts
        return SpanContext(
            trace_id=trace_id,
            span_id=span_id,
            trace_flags=int(flags, 16),
        )


class InMemoryMetrics(MetricsPort):
    """In-memory metrics implementation for development/testing."""

    def __init__(self):
        self._metrics: dict[str, Metric] = {}
        self._counters: dict[str, float] = defaultdict(float)
        self._gauges: dict[str, float] = {}
        self._histograms: dict[str, list[float]] = defaultdict(list)

    def _make_key(self, name: str, labels: dict[str, str] | None) -> str:
        if not labels:
            return name
        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"

    def counter(
        self,
        name: str,
        value: float = 1.0,
        labels: dict[str, str] | None = None,
        unit: str | None = None,
        description: str | None = None,
    ) -> None:
        key = self._make_key(name, labels)
        self._counters[key] += value
        self._metrics[key] = Metric(
            name=name,
            type=MetricType.COUNTER,
            value=self._counters[key],
            labels=labels or {},
            unit=unit,
            description=description,
        )

    def gauge(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None,
        unit: str | None = None,
        description: str | None = None,
    ) -> None:
        key = self._make_key(name, labels)
        self._gauges[key] = value
        self._metrics[key] = Metric(
            name=name,
            type=MetricType.GAUGE,
            value=value,
            labels=labels or {},
            unit=unit,
            description=description,
        )

    def histogram(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None,
        unit: str | None = None,
        description: str | None = None,
    ) -> None:
        key = self._make_key(name, labels)
        self._histograms[key].append(value)
        # Store latest value
        self._metrics[key] = Metric(
            name=name,
            type=MetricType.HISTOGRAM,
            value=value,
            labels=labels or {},
            unit=unit,
            description=description,
        )

    def summary(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None,
        unit: str | None = None,
        description: str | None = None,
    ) -> None:
        self.histogram(name, value, labels, unit, description)

    def record_metric(self, metric: Metric) -> None:
        key = self._make_key(metric.name, metric.labels)
        self._metrics[key] = metric

    def get_metric(self, name: str, labels: dict[str, str] | None = None) -> Metric | None:
        key = self._make_key(name, labels)
        return self._metrics.get(key)

    def list_metrics(self, prefix: str = "") -> list[Metric]:
        return [m for k, m in self._metrics.items() if k.startswith(prefix)]

    def export_prometheus(self) -> bytes:
        lines = []
        for _key, metric in self._metrics.items():
            labels_str = ""
            if metric.labels:
                labels_str = "{" + ",".join(f'{k}="{v}"' for k, v in metric.labels.items()) + "}"
            lines.append(f"# TYPE {metric.name} {metric.type.value}")
            lines.append(f"{metric.name}{labels_str} {metric.value}")
        return "\n".join(lines).encode()

    def get_content_type(self) -> str:
        return "text/plain; version=0.0.4"


class InMemoryStructuredLogging(LoggingPort):
    """In-memory structured logging for development/testing."""

    def __init__(self):
        self._entries: list[LogEntry] = []
        self._correlation_context: contextvars.ContextVar[CorrelationContext | None] = (
            contextvars.ContextVar("correlation_context", default=None)
        )

    def log(self, entry: LogEntry) -> None:
        context = entry.correlation_context or self.get_current_context()
        if context and not entry.correlation_context:
            entry = LogEntry(
                level=entry.level,
                message=entry.message,
                attributes=entry.attributes,
                timestamp=entry.timestamp,
                correlation_context=context,
            )
        self._entries.append(entry)

    def debug(self, message: str, **attributes: Any) -> None:
        self.log(
            LogEntry(
                level=LogLevel.DEBUG,
                message=message,
                attributes=attributes,
                correlation_context=self.get_current_context(),
            )
        )

    def info(self, message: str, **attributes: Any) -> None:
        self.log(
            LogEntry(
                level=LogLevel.INFO,
                message=message,
                attributes=attributes,
                correlation_context=self.get_current_context(),
            )
        )

    def warning(self, message: str, **attributes: Any) -> None:
        self.log(
            LogEntry(
                level=LogLevel.WARNING,
                message=message,
                attributes=attributes,
                correlation_context=self.get_current_context(),
            )
        )

    def error(self, message: str, **attributes: Any) -> None:
        self.log(
            LogEntry(
                level=LogLevel.ERROR,
                message=message,
                attributes=attributes,
                correlation_context=self.get_current_context(),
            )
        )

    def critical(self, message: str, **attributes: Any) -> None:
        self.log(
            LogEntry(
                level=LogLevel.CRITICAL,
                message=message,
                attributes=attributes,
                correlation_context=self.get_current_context(),
            )
        )

    def with_context(self, context: CorrelationContext) -> LoggingPort:
        new_logger = InMemoryStructuredLogging()
        new_logger._correlation_context.set(context)
        return new_logger

    def bind_context(self, context: CorrelationContext) -> None:
        self._correlation_context.set(context)

    def clear_context(self) -> None:
        self._correlation_context.set(None)

    def get_current_context(self) -> CorrelationContext | None:
        return self._correlation_context.get()

    def get_entries(self) -> list[LogEntry]:
        return self._entries.copy()

    def clear_entries(self) -> None:
        self._entries.clear()