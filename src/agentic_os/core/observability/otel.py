"""OpenTelemetry Observability Integration

Production-grade observability using OpenTelemetry SDK.
"""

from __future__ import annotations

import contextvars
from typing import Any

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.metrics import Counter, Histogram, Meter, UpDownCounter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import Span as OtelSpan
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.trace import SpanContext as OtelSpanContext
from opentelemetry.trace import SpanKind as OtelSpanKind
from opentelemetry.trace import Status as OtelStatus
from opentelemetry.trace import StatusCode as OtelStatusCode
from opentelemetry.trace import Tracer
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

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

log = get_logger("observability.otel")


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
        self._tracer: Tracer
        self._propagator = TraceContextTextMapPropagator()
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

    def start_span(
        self,
        name: str,
        kind: str = "internal",
        parent: SpanContext | None = None,
        attributes: dict[str, Any] | None = None,
        links: list[tuple[SpanContext, dict[str, Any]]] | None = None,
    ) -> Span:
        # Create parent context for OTel
        otel_parent = None
        if parent:
            otel_ctx = OtelSpanContext(
                trace_id=int(parent.trace_id, 16),
                span_id=int(parent.span_id, 16),
                is_remote=False,
            )
            otel_parent = trace.set_span_in_context(
                trace.NonRecordingSpan(otel_ctx)
            )

        # Start OTel span
        otel_span = self._tracer.start_span(
            name,
            kind=self._map_kind(kind),
            context=otel_parent,
            attributes=attributes,
        )

        # Create domain span
        sc = otel_span.get_span_context()
        trace_id = format(sc.trace_id, "032x")
        span_id = format(sc.span_id, "016x")

        context = SpanContext(trace_id=trace_id, span_id=span_id)
        parent_context = parent

        domain_span = Span(
            name=name,
            context=context,
            parent_context=parent_context,
            kind=SpanKind(kind) if kind in SpanKind._value2member_map_ else SpanKind.INTERNAL,
            attributes=attributes or {},
        )

        # Store OTel span reference
        domain_span._otel_span = otel_span  # type: ignore

        # Set as current span
        self._current_span.set(domain_span)

        return domain_span

    def end_span(self, span: Span, status: str = "ok", message: str | None = None) -> None:
        otel_span = getattr(span, "_otel_span", None)
        if otel_span and isinstance(otel_span, OtelSpan):
            otel_span.set_status(OtelStatus(self._map_status(SpanStatus(status)), message))
            otel_span.end()

        # Clear current span if it matches
        if self._current_span.get() is span:
            self._current_span.set(None)

    def get_current_span(self) -> Span | None:
        return self._current_span.get()

    def set_current_span(self, span: Span | None) -> None:
        self._current_span.set(span)

    def get_trace(self, trace_id: str) -> Trace | None:
        # OTel doesn't provide trace storage by default
        return None

    def inject_context(self, context: SpanContext, carrier: dict[str, str]) -> None:
        otel_ctx = OtelSpanContext(
            trace_id=int(context.trace_id, 16),
            span_id=int(context.span_id, 16),
            is_remote=False,
        )
        otel_span = trace.NonRecordingSpan(otel_ctx)
        ctx = trace.set_span_in_context(otel_span)
        self._propagator.inject(carrier, context=ctx)

    def extract_context(self, carrier: dict[str, str]) -> SpanContext | None:
        ctx = self._propagator.extract(carrier)
        span = trace.get_current_span(ctx)
        if span and span.get_span_context().is_valid:
            sc = span.get_span_context()
            return SpanContext(
                trace_id=format(sc.trace_id, "032x"),
                span_id=format(sc.span_id, "016x"),
                trace_flags=sc.trace_flags,
            )
        return None

    def shutdown(self) -> None:
        if self._tracer_provider and hasattr(self._tracer_provider, "shutdown"):
            self._tracer_provider.shutdown()


class OTelMetrics(MetricsPort):
    """OpenTelemetry-based metrics implementation with Prometheus export."""

    def __init__(
        self,
        service_name: str = "agentic-os",
        otlp_endpoint: str | None = None,
        prometheus_port: int | None = None,
    ):
        self.service_name = service_name
        self._meter: Meter
        self._counters: dict[str, Counter] = {}
        self._up_down_counters: dict[str, UpDownCounter] = {}
        self._histograms: dict[str, Histogram] = {}
        self._prometheus_reader = None
        self._initialize(otlp_endpoint, prometheus_port)

    def _initialize(self, otlp_endpoint: str | None, prometheus_port: int | None) -> None:
        """Initialize OpenTelemetry meter provider."""
        resource = Resource.create({"service.name": self.service_name})
        readers = []

        # Prometheus reader for /metrics endpoint
        if prometheus_port:
            from opentelemetry.exporter.prometheus import PrometheusMetricReader
            self._prometheus_reader = PrometheusMetricReader()
            readers.append(self._prometheus_reader)
            log.info("Prometheus metric reader configured")

        # OTLP reader for remote metrics
        if otlp_endpoint:
            try:
                otlp_reader = PeriodicExportingMetricReader(
                    OTLPMetricExporter(endpoint=otlp_endpoint, insecure=True)
                )
                readers.append(otlp_reader)
                log.info(f"OTLP metric exporter configured: {otlp_endpoint}")
            except Exception as e:
                log.warning(f"Failed to configure OTLP metric exporter: {e}")

        provider = MeterProvider(resource=resource, metric_readers=readers)
        from opentelemetry.metrics import set_meter_provider
        set_meter_provider(provider)
        meter = provider.get_meter(self.service_name)
        self._meter = meter

    def _get_counter(self, name: str, unit: str | None, description: str | None) -> Counter:
        key = name
        if key not in self._counters:
            self._counters[key] = self._meter.create_counter(
                name, unit=unit or "", description=description or ""
            )
        return self._counters[key]

    def _get_up_down_counter(
        self, name: str, unit: str | None, description: str | None
    ) -> UpDownCounter:
        key = name
        if key not in self._up_down_counters:
            self._up_down_counters[key] = self._meter.create_up_down_counter(
                name, unit=unit or "", description=description or ""
            )
        return self._up_down_counters[key]

    def _get_histogram(self, name: str, unit: str | None, description: str | None) -> Histogram:
        key = name
        if key not in self._histograms:
            self._histograms[key] = self._meter.create_histogram(
                name, unit=unit or "", description=description or ""
            )
        return self._histograms[key]

    def counter(
        self,
        name: str,
        value: float = 1.0,
        labels: dict[str, str] | None = None,
        unit: str | None = None,
        description: str | None = None,
    ) -> None:
        counter = self._get_counter(name, unit, description)
        counter.add(value, labels or {})

    def gauge(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None,
        unit: str | None = None,
        description: str | None = None,
    ) -> None:
        # OTel doesn't have traditional gauges, use UpDownCounter
        up_down = self._get_up_down_counter(name, unit, description)
        up_down.add(value, labels or {})

    def histogram(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None,
        unit: str | None = None,
        description: str | None = None,
    ) -> None:
        histogram = self._get_histogram(name, unit, description)
        histogram.record(value, labels or {})

    def summary(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None,
        unit: str | None = None,
        description: str | None = None,
    ) -> None:
        # OTel doesn't have summary, use histogram
        self.histogram(name, value, labels, unit, description)

    def record_metric(self, metric: Metric) -> None:
        if metric.type == MetricType.COUNTER:
            self.counter(metric.name, metric.value, metric.labels, metric.unit, metric.description)
        elif metric.type == MetricType.GAUGE:
            self.gauge(metric.name, metric.value, metric.labels, metric.unit, metric.description)
        elif metric.type == MetricType.HISTOGRAM:
            self.histogram(
                metric.name, metric.value, metric.labels, metric.unit, metric.description
            )
        elif metric.type == MetricType.SUMMARY:
            self.summary(metric.name, metric.value, metric.labels, metric.unit, metric.description)

    def get_metric(self, name: str, labels: dict[str, str] | None = None) -> Metric | None:
        # OTel doesn't provide metric retrieval
        return None

    def list_metrics(self, prefix: str = "") -> list[Metric]:
        # OTel doesn't provide metric listing
        return []

    def export_prometheus(self) -> bytes:
        if self._prometheus_reader:
            # This is a simplified version - real impl would use the reader's collector
            return b"# Prometheus metrics not directly available from OTel\n"
        return b""

    def get_content_type(self) -> str:
        return "text/plain; version=0.0.4; charset=utf-8"


class StructuredLogging(LoggingPort):
    """Structured logging with correlation context support."""

    def __init__(self, logger_name: str = "agentic-os"):
        self.logger_name = logger_name
        self._correlation_context: contextvars.ContextVar[CorrelationContext | None] = (
            contextvars.ContextVar("correlation_context", default=None)
        )
        from agentic_os.infrastructure.logging import get_logger
        self._logger = get_logger(logger_name)

    def log(self, entry: LogEntry) -> None:
        log_method = getattr(self._logger, entry.level.lower(), self._logger.info)
        context = entry.correlation_context or self.get_current_context()

        extra = {}
        if context:
            extra["trace_id"] = context.trace_id
            extra["span_id"] = context.span_id
            extra.update(context.baggage)

        log_method(entry.message, **entry.attributes, **extra)

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
        new_logger = StructuredLogging(self.logger_name)
        new_logger._correlation_context.set(context)
        return new_logger

    def bind_context(self, context: CorrelationContext) -> None:
        self._correlation_context.set(context)

    def clear_context(self) -> None:
        self._correlation_context.set(None)

    def get_current_context(self) -> CorrelationContext | None:
        return self._correlation_context.get()


__all__ = [
    "OTelTracing",
    "OTelMetrics",
    "StructuredLogging",
]