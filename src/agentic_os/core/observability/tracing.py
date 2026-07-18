"""OpenTelemetry Tracing Implementation

Core implementation of TracingPort using OpenTelemetry SDK.
"""

from __future__ import annotations

import contextvars
from typing import Any

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.trace import Span as OtelSpan
from opentelemetry.trace import SpanContext as OtelSpanContext
from opentelemetry.trace import SpanKind as OtelSpanKind
from opentelemetry.trace import Status as OtelStatus
from opentelemetry.trace import StatusCode as OtelStatusCode
from opentelemetry.trace import TraceFlags, Tracer
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from agentic_os.domain.observability import (
    Span,
    SpanContext,
    SpanKind,
    SpanStatus,
    Trace,
)
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.observability import TracingPort

log = get_logger("observability.tracing")


class OTelTracing(TracingPort):
    """OpenTelemetry-based tracing implementation."""

    def __init__(
        self,
        service_name: str = "agentic-os",
        otlp_endpoint: str | None = None,
        console_export: bool = False,
    ):
        self.service_name = service_name
        self._current_span: contextvars.ContextVar[Span | None] = contextvars.ContextVar(
            "current_span", default=None
        )
        self._traces: dict[str, list[Span]] = {}
        self._otel_spans: dict[str, OtelSpan] = {}
        self._propagator = TraceContextTextMapPropagator()
        self._tracer: Tracer
        self._tracer_provider: TracerProvider | None = None
        self._initialize(otlp_endpoint, console_export)

    def _initialize(self, otlp_endpoint: str | None, console_export: bool) -> None:
        """Initialize OpenTelemetry tracer provider."""
        resource = Resource.create({"service.name": self.service_name})
        provider = TracerProvider(resource=resource)

        # Add OTLP exporter if endpoint provided
        if otlp_endpoint:
            try:
                otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
                provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
                log.info(f"OTLP trace exporter configured: {otlp_endpoint}")
            except Exception as e:
                log.warning(f"Failed to configure OTLP exporter: {e}")

        # Add console exporter for development
        if console_export:
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
            log.info("Console trace exporter enabled")

        trace.set_tracer_provider(provider)
        self._tracer = trace.get_tracer(self.service_name)
        self._tracer_provider = provider

    def _map_kind(self, kind: str) -> OtelSpanKind:
        """Map domain span kind to OpenTelemetry span kind."""
        mapping = {
            "internal": OtelSpanKind.INTERNAL,
            "server": OtelSpanKind.SERVER,
            "client": OtelSpanKind.CLIENT,
            "producer": OtelSpanKind.PRODUCER,
            "consumer": OtelSpanKind.CONSUMER,
        }
        return mapping.get(kind, OtelSpanKind.INTERNAL)

    def _map_status(self, status: SpanStatus) -> OtelStatusCode:
        """Map domain span status to OpenTelemetry status code."""
        mapping = {
            "ok": OtelStatusCode.OK,
            "error": OtelStatusCode.ERROR,
            "unset": OtelStatusCode.UNSET,
        }
        return mapping.get(status, OtelStatusCode.UNSET)

    def _to_domain_context(self, otel_context: OtelSpanContext) -> SpanContext:
        """Convert OTel span context to domain span context."""
        return SpanContext(
            trace_id=format(otel_context.trace_id, "032x"),
            span_id=format(otel_context.span_id, "016x"),
            trace_flags=otel_context.trace_flags,
            trace_state=(
                str(otel_context.trace_state) if otel_context.trace_state else None
            ),
        )

    def _to_otel_context(self, context: SpanContext) -> OtelSpanContext:
        """Convert domain span context to OTel span context."""
        return OtelSpanContext(
            trace_id=int(context.trace_id, 16),
            span_id=int(context.span_id, 16),
            trace_flags=TraceFlags(context.trace_flags),
            trace_state=None,  # Would need parsing
            is_remote=False,
        )

    def start_span(
        self,
        name: str,
        kind: str = "internal",
        parent: SpanContext | None = None,
        attributes: dict[str, Any] | None = None,
        links: list[tuple[SpanContext, dict[str, Any]]] | None = None,
    ) -> Span:
        """Start a new span."""
        if not self._tracer:
            raise RuntimeError("Tracer not initialized")

        # Determine parent context
        otel_parent = None
        if parent:
            otel_parent = trace.set_span_in_context(
                trace.NonRecordingSpan(self._to_otel_context(parent))
            )
        else:
            # Check for current span in context
            current = self._current_span.get()
            if current:
                otel_parent = trace.set_span_in_context(
                    trace.NonRecordingSpan(self._to_otel_context(current.context))
                )

        # Create OTel span
        otel_span = self._tracer.start_span(
            name=name,
            kind=self._map_kind(kind),
            context=otel_parent,
            attributes=attributes or {},
            links=[
                trace.Link(self._to_otel_context(ctx), attrs)
                for ctx, attrs in (links or [])
            ],
        )

        # Create domain span
        domain_context = self._to_domain_context(otel_span.get_span_context())
        parent_context = (
            self._to_domain_context(
                trace.get_current_span(otel_parent).get_span_context()
            )
            if otel_parent
            else None
        )

        span = Span(
            name=name,
            context=domain_context,
            parent_context=parent_context,
            kind=SpanKind(kind),
            attributes=attributes or {},
        )

        # Store OTel span reference
        self._otel_spans[domain_context.span_id] = otel_span

        # Set as current span
        self._current_span.set(span)

        # Track in traces
        trace_id = domain_context.trace_id
        if trace_id not in self._traces:
            self._traces[trace_id] = []
        self._traces[trace_id].append(span)

        log.debug(
            "span_started",
            name=name,
            trace_id=trace_id,
            span_id=domain_context.span_id,
        )
        return span

    def end_span(
        self, span: Span, status: str = "ok", message: str | None = None
    ) -> None:
        """End a span."""
        otel_span = self._otel_spans.pop(span.context.span_id, None)
        if otel_span and isinstance(otel_span, OtelSpan):
            otel_status = OtelStatus(self._map_status(SpanStatus(status)), message)
            otel_span.set_status(otel_status)
            # Add events
            for event in span.events:
                otel_span.add_event(
                    event.name,
                    event.attributes,
                    int(event.timestamp.timestamp() * 1_000_000_000),
                )
            otel_span.end()

        # Update trace storage
        trace_id = span.context.trace_id
        ended_span = span.with_end_time()
        if trace_id in self._traces:
            self._traces[trace_id] = [
                ended_span if s.context.span_id == span.context.span_id else s
                for s in self._traces[trace_id]
            ]

        # Clear current span if it matches
        current = self._current_span.get()
        if current and current.context.span_id == span.context.span_id:
            self._current_span.set(None)

        log.debug(
            "span_ended",
            name=span.name,
            trace_id=trace_id,
            span_id=span.context.span_id,
            duration_ms=ended_span.duration_ms(),
        )

    def get_current_span(self) -> Span | None:
        """Get the currently active span."""
        return self._current_span.get()

    def set_current_span(self, span: Span | None) -> None:
        """Set the currently active span."""
        self._current_span.set(span)

    def get_trace(self, trace_id: str) -> Trace | None:
        """Get a complete trace by ID."""
        spans = self._traces.get(trace_id)
        if not spans:
            return None

        # Find root span (no parent or parent not in trace)
        root_span_id = None
        span_ids = {s.context.span_id for s in spans}
        for span in spans:
            if not span.parent_context or span.parent_context.span_id not in span_ids:
                root_span_id = span.context.span_id
                break

        return Trace(spans=tuple(spans), root_span_id=root_span_id)

    def export_traces(self, traces: list[Trace]) -> None:
        """Export traces to backend - handled by OTel processors."""
        # OTel handles export via span processors
        log.debug(f"Exporting {len(traces)} traces")

    def inject_context(self, context: SpanContext, carrier: dict[str, str]) -> None:
        """Inject context into carrier (e.g., HTTP headers)."""
        otel_context = trace.set_span_in_context(
            trace.NonRecordingSpan(self._to_otel_context(context))
        )
        self._propagator.inject(carrier, context=otel_context)

    def extract_context(self, carrier: dict[str, str]) -> SpanContext | None:
        """Extract context from carrier."""
        otel_context = self._propagator.extract(carrier)
        span_context = trace.get_current_span(otel_context).get_span_context()
        if span_context and span_context.is_valid:
            return self._to_domain_context(span_context)
        return None

    def shutdown(self) -> None:
        """Shutdown tracer provider."""
        if self._tracer_provider and hasattr(self._tracer_provider, "shutdown"):
            self._tracer_provider.shutdown()
        log.info("Tracing shutdown complete")


# Global tracing instance
_tracing_instance: OTelTracing | None = None


def get_tracing() -> OTelTracing:
    """Get or create the global tracing instance."""
    global _tracing_instance
    if _tracing_instance is None:
        _tracing_instance = OTelTracing()
    return _tracing_instance


def configure_tracing(
    service_name: str = "agentic-os",
    otlp_endpoint: str | None = None,
    console_export: bool = False,
) -> OTelTracing:
    """Configure and return the global tracing instance."""
    global _tracing_instance
    _tracing_instance = OTelTracing(service_name, otlp_endpoint, console_export)
    return _tracing_instance