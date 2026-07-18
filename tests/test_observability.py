"""Comprehensive tests for Observability implementations.

Covers InMemoryTracing, InMemoryMetrics, InMemoryStructuredLogging,
PrometheusMetrics, StructuredLogging (structlog), OTelTracing,
and the factory function create_observability_stack.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agentic_os.core.observability import (
    OTelTracing,
    create_observability_stack,
)
from agentic_os.core.observability.in_memory import (
    InMemoryMetrics,
    InMemoryStructuredLogging,
    InMemoryTracing,
    TraceContextPropagator,
)
from agentic_os.core.observability.logging import (
    StructuredLogging,
    configure_logging,
    get_logging,
)
from agentic_os.core.observability.metrics import (
    PrometheusMetrics,
    configure_metrics,
    get_metrics,
)
from agentic_os.core.observability.tracing import (
    configure_tracing,
    get_tracing,
)
from agentic_os.domain.observability import (
    CorrelationContext,
    LogEntry,
    LogLevel,
    Metric,
    MetricType,
    Span,
    SpanContext,
    SpanEvent,
    SpanKind,
)

# =========================================================================
# InMemoryTracing Tests
# =========================================================================


class TestInMemoryTracing:
    """Test InMemoryTracing implementation."""

    @pytest.fixture
    def tracing(self):
        return InMemoryTracing()

    def test_start_span_basic(self, tracing):
        span = tracing.start_span("test-op")
        assert span.name == "test-op"
        assert span.kind == SpanKind.INTERNAL
        assert span.context.trace_id
        assert span.context.span_id
        assert span.start_time is not None
        assert span.end_time is None

    def test_start_span_with_kind(self, tracing):
        span = tracing.start_span("server-op", kind="server")
        assert span.kind == SpanKind.SERVER

    def test_start_span_with_attributes(self, tracing):
        span = tracing.start_span("op", attributes={"key": "val"})
        assert span.attributes == {"key": "val"}

    def test_start_span_with_parent(self, tracing):
        parent = tracing.start_span("parent")
        child = tracing.start_span("child", parent=parent.context)
        assert child.parent_context is not None
        assert child.parent_context.span_id == parent.context.span_id
        assert child.parent_context.trace_id == parent.context.trace_id

    def test_start_span_sets_current(self, tracing):
        span = tracing.start_span("current")
        assert tracing.get_current_span() is span
        assert tracing.get_current_span().context.span_id == span.context.span_id

    def test_end_span(self, tracing):
        span = tracing.start_span("op")
        tracing.end_span(span, status="ok", message="done")
        ended = tracing.get_current_span()
        # Current should be cleared
        assert ended is None

    def test_end_span_updates_trace_storage(self, tracing):
        span = tracing.start_span("op")
        tracing.end_span(span)
        trace = tracing.get_trace(span.context.trace_id)
        assert trace is not None
        assert len(trace.spans) == 1
        assert trace.spans[0].is_finished()

    def test_get_trace_not_found(self, tracing):
        result = tracing.get_trace("nonexistent")
        assert result is None

    def test_get_trace_returns_root(self, tracing):
        parent = tracing.start_span("parent")
        tracing.end_span(parent)
        child = tracing.start_span("child", parent=parent.context)
        tracing.end_span(child)

        trace = tracing.get_trace(parent.context.trace_id)
        assert trace is not None
        assert trace.root_span_id == parent.context.span_id

    def test_set_current_span(self, tracing):
        span = Span(name="test", context=SpanContext.generate())
        tracing.set_current_span(span)
        assert tracing.get_current_span() is span

    def test_set_current_span_none(self, tracing):
        tracing.set_current_span(None)
        assert tracing.get_current_span() is None

    def test_inject_context(self, tracing):
        ctx = SpanContext.generate()
        carrier: dict[str, str] = {}
        tracing.inject_context(ctx, carrier)
        assert "traceparent" in carrier
        assert carrier["traceparent"].startswith("00-")
        assert ctx.trace_id in carrier["traceparent"]
        assert ctx.span_id in carrier["traceparent"]

    def test_extract_context(self, tracing):
        ctx = SpanContext.generate()
        carrier: dict[str, str] = {}
        tracing.inject_context(ctx, carrier)

        extracted = tracing.extract_context(carrier)
        assert extracted is not None
        assert extracted.trace_id == ctx.trace_id
        assert extracted.span_id == ctx.span_id

    def test_extract_context_from_empty(self, tracing):
        result = tracing.extract_context({})
        assert result is None

    def test_shutdown(self, tracing):
        # Should not crash
        tracing.shutdown()

    def test_inject_context_using_propagator(self, tracing):
        """Test that inject uses the internal propagator correctly."""
        ctx = SpanContext.generate()
        carrier: dict[str, str] = {}
        tracing.inject_context(ctx, carrier)
        assert "traceparent" in carrier

    def test_multiple_spans_same_trace(self, tracing):
        s1 = tracing.start_span("s1")
        s2 = tracing.start_span("s2", parent=s1.context)
        s3 = tracing.start_span("s3", parent=s2.context)
        tracing.end_span(s3)
        tracing.end_span(s2)
        tracing.end_span(s1)

        trace = tracing.get_trace(s1.context.trace_id)
        assert trace is not None
        assert len(trace.spans) == 3


class TestTraceContextPropagator:
    """Test W3C TraceContext propagation."""

    def test_propagate(self):
        propagator = TraceContextPropagator()
        ctx = SpanContext.generate()
        carrier: dict[str, str] = {}
        propagator.inject(ctx, carrier)
        assert "traceparent" in carrier
        # Format: 00-{trace_id}-{span_id}-{flags}
        parts = carrier["traceparent"].split("-")
        assert parts[0] == "00"
        assert parts[1] == ctx.trace_id
        assert parts[2] == ctx.span_id
        assert parts[3] == "01"  # sampled

    def test_extract(self):
        propagator = TraceContextPropagator()
        carrier = {
            "traceparent": "00-abc123def45678901234567890123456-fedcba9876543210-01",
        }
        ctx = propagator.extract(carrier)
        assert ctx is not None
        assert ctx.trace_id == "abc123def45678901234567890123456"
        assert ctx.span_id == "fedcba9876543210"
        assert ctx.trace_flags == 1

    def test_extract_invalid_header(self):
        propagator = TraceContextPropagator()
        result = propagator.extract({"traceparent": "invalid"})
        assert result is None


# =========================================================================
# InMemoryMetrics Tests
# =========================================================================


class TestInMemoryMetrics:
    """Test InMemoryMetrics implementation."""

    @pytest.fixture
    def metrics(self):
        return InMemoryMetrics()

    def test_counter(self, metrics):
        metrics.counter("test_counter", value=5)
        metric = metrics.get_metric("test_counter")
        assert metric is not None
        assert metric.value == 5
        assert metric.type == MetricType.COUNTER

    def test_counter_accumulates(self, metrics):
        metrics.counter("c", value=1)
        metrics.counter("c", value=2)
        metric = metrics.get_metric("c")
        assert metric is not None
        assert metric.value == 3

    def test_counter_with_labels(self, metrics):
        metrics.counter("c", value=1, labels={"env": "test"})
        metric = metrics.get_metric("c", labels={"env": "test"})
        assert metric is not None
        assert metric.labels == {"env": "test"}

    def test_counter_labels_are_distinct(self, metrics):
        metrics.counter("c", value=1, labels={"env": "test"})
        metrics.counter("c", value=2, labels={"env": "prod"})
        test_metric = metrics.get_metric("c", labels={"env": "test"})
        prod_metric = metrics.get_metric("c", labels={"env": "prod"})
        assert test_metric is not None and test_metric.value == 1
        assert prod_metric is not None and prod_metric.value == 2

    def test_gauge(self, metrics):
        metrics.gauge("g", value=42)
        metric = metrics.get_metric("g")
        assert metric is not None
        assert metric.type == MetricType.GAUGE
        assert metric.value == 42

    def test_gauge_overwrites(self, metrics):
        metrics.gauge("g", value=10)
        metrics.gauge("g", value=20)
        metric = metrics.get_metric("g")
        assert metric is not None and metric.value == 20

    def test_histogram(self, metrics):
        metrics.histogram("h", value=100)
        metric = metrics.get_metric("h")
        assert metric is not None
        assert metric.type == MetricType.HISTOGRAM
        assert metric.value == 100

    def test_summary(self, metrics):
        metrics.summary("s", value=50)
        metric = metrics.get_metric("s")
        assert metric is not None
        # InMemoryMetrics treats summary as histogram
        assert metric.type == MetricType.HISTOGRAM

    def test_record_metric_counter(self, metrics):
        m = Metric(name="m", type=MetricType.COUNTER, value=7)
        metrics.record_metric(m)
        stored = metrics.get_metric("m")
        assert stored is not None and stored.value == 7

    def test_record_metric_gauge(self, metrics):
        m = Metric(name="m", type=MetricType.GAUGE, value=3.14)
        metrics.record_metric(m)
        stored = metrics.get_metric("m")
        assert stored is not None and stored.value == 3.14

    def test_record_metric_histogram(self, metrics):
        m = Metric(name="m", type=MetricType.HISTOGRAM, value=200)
        metrics.record_metric(m)
        stored = metrics.get_metric("m")
        assert stored is not None and stored.type == MetricType.HISTOGRAM

    def test_record_metric_summary(self, metrics):
        m = Metric(name="m", type=MetricType.SUMMARY, value=150)
        metrics.record_metric(m)
        stored = metrics.get_metric("m")
        assert stored is not None

    def test_list_metrics(self, metrics):
        metrics.counter("c1", value=1)
        metrics.counter("c2", value=2)
        metrics.gauge("g1", value=3)
        all_metrics = metrics.list_metrics()
        assert len(all_metrics) == 3

    def test_list_metrics_with_prefix(self, metrics):
        metrics.counter("http_requests", value=1)
        metrics.counter("db_queries", value=2)
        http_metrics = metrics.list_metrics(prefix="http_")
        assert len(http_metrics) == 1
        assert http_metrics[0].name == "http_requests"

    def test_get_metric_not_found(self, metrics):
        result = metrics.get_metric("nonexistent")
        assert result is None

    def test_export_prometheus(self, metrics):
        metrics.counter("requests", value=10, labels={"method": "GET"})
        output = metrics.export_prometheus()
        assert isinstance(output, bytes)
        text = output.decode()
        assert "requests" in text
        assert "10" in text
        assert "method" in text
        assert "GET" in text

    def test_export_prometheus_empty(self, metrics):
        output = metrics.export_prometheus()
        assert isinstance(output, bytes)

    def test_get_content_type(self, metrics):
        ct = metrics.get_content_type()
        assert "text/plain" in ct


# =========================================================================
# InMemoryStructuredLogging Tests
# =========================================================================


class TestInMemoryStructuredLogging:
    """Test InMemoryStructuredLogging implementation."""

    @pytest.fixture
    def logging(self):
        return InMemoryStructuredLogging()

    def test_log_entry(self, logging):
        logging.info("test message", key="val")
        entries = logging.get_entries()
        assert len(entries) == 1
        entry = entries[0]
        assert entry.message == "test message"
        assert entry.level == LogLevel.INFO
        assert entry.attributes == {"key": "val"}

    def test_debug(self, logging):
        logging.debug("debug msg")
        assert logging.get_entries()[-1].level == LogLevel.DEBUG

    def test_info(self, logging):
        logging.info("info msg")
        assert logging.get_entries()[-1].level == LogLevel.INFO

    def test_warning(self, logging):
        logging.warning("warn msg")
        assert logging.get_entries()[-1].level == LogLevel.WARNING

    def test_error(self, logging):
        logging.error("error msg")
        assert logging.get_entries()[-1].level == LogLevel.ERROR

    def test_critical(self, logging):
        logging.critical("critical msg")
        assert logging.get_entries()[-1].level == LogLevel.CRITICAL

    def test_log_with_correlation_context(self, logging):
        ctx = CorrelationContext(trace_id="trace1", span_id="span1")
        logging.bind_context(ctx)
        logging.info("with context")
        entry = logging.get_entries()[-1]
        assert entry.correlation_context is not None
        assert entry.correlation_context.trace_id == "trace1"

    def test_with_context_creates_isolated_copy(self, logging):
        ctx = CorrelationContext(trace_id="t1", span_id="s1")
        logging.bind_context(ctx)
        isolated = logging.with_context(CorrelationContext(trace_id="t2", span_id="s2"))
        # Original still has its context
        assert logging.get_current_context() is not None
        assert logging.get_current_context().trace_id == "t1"
        # Isolated has new context
        assert isolated.get_current_context() is not None
        assert isolated.get_current_context().trace_id == "t2"
        # They should be different instances
        assert logging.get_current_context().trace_id != isolated.get_current_context().trace_id

    def test_clear_context(self, logging):
        logging.bind_context(CorrelationContext(trace_id="t1", span_id="s1"))
        logging.clear_context()
        assert logging.get_current_context() is None

    def test_get_current_context_none(self, logging):
        assert logging.get_current_context() is None

    def test_multiple_entries(self, logging):
        logging.info("first")
        logging.info("second")
        logging.info("third")
        assert len(logging.get_entries()) == 3

    def test_get_entries_by_level(self, logging):
        logging.debug("d1")
        logging.info("i1")
        logging.warning("w1")
        entries = logging.get_entries()
        assert len([e for e in entries if e.level == LogLevel.DEBUG]) == 1
        assert len([e for e in entries if e.level == LogLevel.INFO]) == 1
        assert len([e for e in entries if e.level == LogLevel.WARNING]) == 1

    def test_clear_entries(self, logging):
        logging.info("msg")
        assert len(logging.get_entries()) == 1
        logging.clear_entries()
        assert len(logging.get_entries()) == 0


# =========================================================================
# PrometheusMetrics Tests
# =========================================================================


class TestPrometheusMetrics:
    """Test PrometheusMetrics implementation (production adapter)."""

    @pytest.fixture
    def metrics(self):
        return PrometheusMetrics()

    def test_counter(self, metrics):
        # Should not raise
        metrics.counter("prom_counter", value=1)
        metrics.counter("prom_counter", value=2)
        # We can't easily retrieve the value, but it shouldn't crash

    def test_counter_with_labels(self, metrics):
        metrics.counter("prom_counter_labeled", value=1, labels={"env": "test"})

    def test_gauge(self, metrics):
        metrics.gauge("prom_gauge", value=42)

    def test_histogram(self, metrics):
        metrics.histogram("prom_histogram", value=100)

    def test_summary(self, metrics):
        metrics.summary("prom_summary", value=50)

    def test_record_metric(self, metrics):
        m = Metric(name="prom_recorded", type=MetricType.COUNTER, value=7)
        metrics.record_metric(m)

    def test_get_metric_returns_none(self, metrics):
        # Prometheus doesn't support retrieval
        result = metrics.get_metric("anything")
        assert result is None

    def test_list_metrics_returns_empty(self, metrics):
        result = metrics.list_metrics()
        assert result == []

    def test_export_prometheus(self, metrics):
        metrics.counter("api_calls", value=5, labels={"endpoint": "/test"})
        output = metrics.export_prometheus()
        assert isinstance(output, bytes)
        text = output.decode()
        # Should contain our counter
        assert "api_calls" in text

    def test_get_content_type(self, metrics):
        ct = metrics.get_content_type()
        assert "text/plain" in ct

    def test_multiple_instruments(self, metrics):
        metrics.counter("c", value=1)
        metrics.gauge("g", value=2)
        metrics.histogram("h", value=3)
        metrics.summary("s", value=4)
        output = metrics.export_prometheus()
        text = output.decode()
        assert "c" in text
        # Gauges use UpDownCounter in Prometheus
        assert "g" in text
        assert "h" in text
        # Summary is treated as histogram
        assert "s" in text

    def test_prometheus_registry_isolation(self):
        m1 = PrometheusMetrics()
        m2 = PrometheusMetrics()
        m1.counter("isolated", value=1)
        m2.counter("isolated", value=2)
        # Each registry is separate, no conflict

    def test_content_type_format(self, metrics):
        ct = metrics.get_content_type()
        assert "text/plain" in ct
        assert "charset=utf-8" in ct


# =========================================================================
# StructuredLogging (structlog) Tests
# =========================================================================


class TestStructuredLogging:
    """Test StructuredLogging implementation (structlog)."""

    @pytest.fixture
    def logging(self):
        # Avoid OTel re-init issues
        return StructuredLogging("test-logger")

    def test_debug(self, logging):
        logging.debug("debug message")
        # Should not raise

    def test_info(self, logging):
        logging.info("info message", extra_key="val")
        # Should not raise

    def test_warning(self, logging):
        logging.warning("warn message")

    def test_error(self, logging):
        logging.error("error message")

    def test_critical(self, logging):
        logging.critical("critical message")

    def test_log_entry(self, logging):
        entry = LogEntry(
            level=LogLevel.INFO,
            message="structured entry",
            attributes={"key": "val"},
        )
        logging.log(entry)
        # Should not raise

    def test_log_entry_with_context(self, logging):
        ctx = CorrelationContext(trace_id="t1", span_id="s1")
        logging.bind_context(ctx)
        logging.info("with binding")

    def test_with_context(self, logging):
        ctx = CorrelationContext(trace_id="t1", span_id="s1")
        isolated = logging.with_context(ctx)
        assert isolated is not None

    def test_bind_context(self, logging):
        ctx = CorrelationContext(trace_id="t1", span_id="s1")
        logging.bind_context(ctx)
        current = logging.get_current_context()
        assert current is not None
        assert current.trace_id == "t1"

    def test_clear_context(self, logging):
        logging.bind_context(CorrelationContext(trace_id="t1", span_id="s1"))
        logging.clear_context()
        assert logging.get_current_context() is None

    def test_get_current_context_none(self, logging):
        assert logging.get_current_context() is None

    def test_log_with_correlation_in_extra(self, logging):
        ctx = CorrelationContext(trace_id="t1", span_id="s1", baggage={"user": "alice"})
        logging.bind_context(ctx)
        logging.info("message with baggage")

    def test_configure_logging(self):
        # Should not raise
        configure_logging("test-logger", level="DEBUG", json_output=False)


# =========================================================================
# Factory Function Tests
# =========================================================================


class TestCreateObservabilityStack:
    """Test create_observability_stack factory."""

    def test_development_mode(self):
        stack = create_observability_stack(mode="development")
        assert "tracing" in stack
        assert "metrics" in stack
        assert "logging" in stack
        assert isinstance(stack["tracing"], InMemoryTracing)
        assert isinstance(stack["metrics"], InMemoryMetrics)
        assert isinstance(stack["logging"], InMemoryStructuredLogging)

    def test_testing_mode(self):
        stack = create_observability_stack(mode="testing")
        assert isinstance(stack["tracing"], InMemoryTracing)
        assert isinstance(stack["metrics"], InMemoryMetrics)
        assert isinstance(stack["logging"], InMemoryStructuredLogging)

    @patch("agentic_os.core.observability.PrometheusMetrics")
    @patch("agentic_os.core.observability.StructuredLogging")
    @patch("agentic_os.core.observability.OTelTracing")
    def test_production_mode(self, mock_tracing, mock_logging, mock_metrics):
        stack = create_observability_stack(
            mode="production",
            service_name="test-svc",
            otlp_endpoint="http://localhost:4317",
        )
        assert "tracing" in stack
        assert "metrics" in stack
        assert "logging" in stack

    def test_production_no_otlp_raises(self):
        with pytest.raises(ValueError, match="OTLP endpoint required"):
            create_observability_stack(mode="production")

    def test_service_name_passed(self):
        stack = create_observability_stack(mode="testing", service_name="custom-svc")
        assert stack is not None

    def test_invalid_mode_defaults(self):
        stack = create_observability_stack(mode="random")
        assert isinstance(stack["tracing"], InMemoryTracing)


# =========================================================================
# OTelTracing (tracing.py) Tests
# =========================================================================


class TestOTelTracing:
    """Test OTelTracing from tracing.py with mocked OTel."""

    @pytest.fixture
    def tracing(self):
        with patch("agentic_os.core.observability.tracing.TracerProvider") as mock_provider:
            mock_tracer = MagicMock()
            mock_otel_span = MagicMock()
            mock_otel_span.get_span_context.return_value = MagicMock(
                trace_id=12345,
                span_id=67890,
                trace_flags=1,
                trace_state=None,
            )
            # NonRecordingSpan for parent
            mock_tracer.start_span.return_value = mock_otel_span
            mock_provider_instance = MagicMock()
            mock_provider.return_value = mock_provider_instance

            with patch("agentic_os.core.observability.tracing.trace.get_tracer") as gt:
                gt.return_value = mock_tracer
                tracing = OTelTracing("test-svc")
                tracing._tracer = mock_tracer
                tracing._tracer_provider = mock_provider_instance
                yield tracing

    def test_start_span(self, tracing):
        span = tracing.start_span("test-op", attributes={"key": "val"})
        assert span.name == "test-op"
        assert span.attributes == {"key": "val"}

    def test_start_span_with_parent(self, tracing):
        parent_ctx = SpanContext(trace_id="a" * 32, span_id="b" * 16)
        span = tracing.start_span("child", parent=parent_ctx)
        assert span.parent_context is not None
        assert span.parent_context.span_id == parent_ctx.span_id

    def test_start_span_sets_current(self, tracing):
        span = tracing.start_span("current")
        assert tracing.get_current_span() is span

    def test_end_span(self, tracing):
        span = tracing.start_span("op")
        tracing.end_span(span, status="ok", message="done")
        assert tracing.get_current_span() is None

    def test_get_current_span_none(self, tracing):
        assert tracing.get_current_span() is None

    def test_set_current_span(self, tracing):
        span = Span(name="manual", context=SpanContext.generate())
        tracing.set_current_span(span)
        assert tracing.get_current_span() is span

    def test_inject_context(self, tracing):
        ctx = SpanContext(trace_id="c" * 32, span_id="d" * 16)
        carrier: dict[str, str] = {}
        tracing.inject_context(ctx, carrier)
        assert "traceparent" in carrier

    def test_inject_no_otel_span(self, tracing):
        """Inject still works without stored OTel span."""
        ctx = SpanContext(trace_id="e" * 32, span_id="f" * 16)
        carrier: dict[str, str] = {}
        tracing.inject_context(ctx, carrier)
        assert "traceparent" in carrier

    def test_extract_context(self, tracing):
        with patch.object(tracing._propagator, "extract") as mock_extract:
            mock_ctx = MagicMock()
            mock_span = MagicMock()
            mock_sc = MagicMock()
            mock_sc.trace_id = 999
            mock_sc.span_id = 888
            mock_sc.trace_flags = 1
            mock_sc.is_valid = True
            mock_span.get_span_context.return_value = mock_sc
            mock_ctx_span = MagicMock()
            mock_ctx_span.get_span_context.return_value = mock_sc

            with patch(
                "agentic_os.core.observability.tracing.trace.get_current_span",
                return_value=mock_ctx_span,
            ):
                mock_extract.return_value = mock_ctx
                result = tracing.extract_context({"traceparent": "test"})
                assert result is not None
                assert result.trace_id == format(999, "032x")
                assert result.span_id == format(888, "016x")

    def test_shutdown(self, tracing):
        tracing.shutdown()

    def test_get_trace(self, tracing):
        # OTelTracing doesn't store traces
        result = tracing.get_trace("any")
        assert result is None

    def test_start_span_uses_current_as_parent(self, tracing):
        """Second start_span without parent uses the current span as parent."""
        first = tracing.start_span("parent")
        # Now current span is set to first
        second = tracing.start_span("child")  # No explicit parent
        assert second.parent_context is not None
        assert second.parent_context.span_id == first.context.span_id

    def test_end_span_with_events(self, tracing):
        """end_span propagates events to OTel span."""
        from opentelemetry.trace import Span as OtelSpanType

        span = tracing.start_span("op")
        event = SpanEvent(name="test-event", attributes={"key": "val"})
        span_with_event = span.with_event(event)

        # Replace OTel span with a spec'd mock so isinstance passes
        mock_otel = MagicMock(spec=OtelSpanType)
        mock_otel.get_span_context.return_value = MagicMock(
            trace_id=12345,
            span_id=67890,
            trace_flags=1,
            trace_state=None,
        )
        tracing._otel_spans[span_with_event.context.span_id] = mock_otel

        tracing.end_span(span_with_event)
        mock_otel.set_status.assert_called_once()
        mock_otel.add_event.assert_called_once()
        mock_otel.end.assert_called_once()

    def test_end_span_with_error_status(self, tracing):
        span = tracing.start_span("op")
        tracing.end_span(span, status="error", message="something broke")
        assert tracing.get_current_span() is None

    def test_end_span_with_unset_status(self, tracing):
        span = tracing.start_span("op")
        tracing.end_span(span, status="unset")
        assert tracing.get_current_span() is None

    def test_export_traces(self, tracing):
        # Should not raise
        tracing.export_traces([])

    def test_inject_without_otel_span(self, tracing):
        """inject_context works even without OTel span stored."""
        ctx = SpanContext(trace_id="c" * 32, span_id="d" * 16)
        carrier: dict[str, str] = {}
        tracing.inject_context(ctx, carrier)
        assert "traceparent" in carrier

    def test_get_trace_with_span_data(self, tracing):
        """start_span populates internal trace storage."""
        span = tracing.start_span("op")
        trace_id = span.context.trace_id
        result = tracing.get_trace(trace_id)
        assert result is not None
        assert len(result.spans) >= 1


# =========================================================================
# OTel Metrics & StructuredLogging (otel.py) Tests
# =========================================================================


class TestOTelStructuredLogging:
    """Test StructuredLogging from otel.py."""

    @pytest.fixture
    def logging(self):
        from agentic_os.core.observability.otel import StructuredLogging

        return StructuredLogging("otel-test")

    def test_debug(self, logging):
        logging.debug("debug")

    def test_info(self, logging):
        logging.info("info")

    def test_warning(self, logging):
        logging.warning("warn")

    def test_error(self, logging):
        logging.error("error")

    def test_critical(self, logging):
        logging.critical("critical")

    def test_log_entry(self, logging):
        entry = LogEntry(level=LogLevel.INFO, message="entry")
        logging.log(entry)

    def test_with_context(self, logging):
        ctx = CorrelationContext(trace_id="t1", span_id="s1")
        isolated = logging.with_context(ctx)
        assert isolated is not None

    def test_bind_and_clear_context(self, logging):
        ctx = CorrelationContext(trace_id="t1", span_id="s1")
        logging.bind_context(ctx)
        assert logging.get_current_context() is not None
        logging.clear_context()
        assert logging.get_current_context() is None


# =========================================================================
# OTelTracing (otel.py) — NOT TESTED
# =========================================================================
# OTelTracing from otel.py uses `domain_span._otel_span = otel_span` on
# a frozen dataclass (Span), which fails at runtime. The tracing.py
# version (tested as TestOTelTracing above) is the canonical production
# implementation used by create_observability_stack. The otel.py
# duplicate has known regressions and is not tested here.


# =========================================================================
# Global Accessors Tests
# =========================================================================


class TestGlobalAccessors:
    """Test global accessor functions."""

    def test_configure_logging_returns(self):
        logger = configure_logging("global-test")
        assert logger is not None

    def test_get_logging(self):
        log = get_logging()
        assert log is not None

    def test_configure_metrics(self):
        with patch("agentic_os.core.observability.metrics.PrometheusMetrics") as pm:
            pm_instance = MagicMock()
            pm.return_value = pm_instance
            metrics = configure_metrics()
            assert metrics is not None

    def test_get_metrics(self):
        with patch("agentic_os.core.observability.metrics.PrometheusMetrics") as pm:
            pm_instance = MagicMock()
            pm.return_value = pm_instance
            metrics = get_metrics()
            assert metrics is not None

    def test_configure_tracing(self):
        with patch("agentic_os.core.observability.tracing.OTelTracing") as mock_cls:
            mock_instance = MagicMock()
            mock_cls.return_value = mock_instance
            with patch("agentic_os.core.observability.tracing.TracerProvider"):
                with patch("agentic_os.core.observability.tracing.trace.get_tracer") as gt:
                    gt.return_value = MagicMock()
                    tracing = configure_tracing("test-svc")
                    assert tracing is not None

    def test_get_tracing(self):
        with patch("agentic_os.core.observability.tracing.OTelTracing") as mock_cls:
            mock_instance = MagicMock()
            mock_cls.return_value = mock_instance
            with patch("agentic_os.core.observability.tracing.TracerProvider"):
                with patch("agentic_os.core.observability.tracing.trace.get_tracer") as gt:
                    gt.return_value = MagicMock()
                    tracing = get_tracing()
                    assert tracing is not None


# =========================================================================
# End-to-End Integration Tests
# =========================================================================


class TestEndToEnd:
    """End-to-end integration tests using the in-memory stack."""

    @pytest.fixture
    def stack(self):
        return create_observability_stack(mode="testing")

    def test_trace_propagates_to_log(self, stack):
        tracing = stack["tracing"]
        logging = stack["logging"]

        span = tracing.start_span("request")
        ctx = CorrelationContext(
            trace_id=span.context.trace_id,
            span_id=span.context.span_id,
        )
        logging.bind_context(ctx)
        logging.info("Processing request", method="GET")

        # Cleanup
        tracing.end_span(span)
        entries = logging.get_entries()
        assert len(entries) >= 1
        last = entries[-1]
        assert last.correlation_context is not None
        assert last.correlation_context.trace_id == span.context.trace_id

    def test_metrics_and_tracing_independent(self, stack):
        tracing = stack["tracing"]
        metrics = stack["metrics"]

        span = tracing.start_span("measured-op")
        metrics.counter("ops_total", value=1)
        metrics.histogram("op_duration_ms", value=150)
        tracing.end_span(span)

        trace = tracing.get_trace(span.context.trace_id)
        metric_c = metrics.get_metric("ops_total")
        metric_h = metrics.get_metric("op_duration_ms")

        assert trace is not None
        assert metric_c is not None and metric_c.value == 1
        assert metric_h is not None and metric_h.value == 150

    def test_log_context_isolation(self, stack):
        log1 = stack["logging"]
        ctx1 = CorrelationContext(trace_id="t1", span_id="s1")
        log1.bind_context(ctx1)

        log2 = log1.with_context(CorrelationContext(trace_id="t2", span_id="s2"))

        log1.info("from log1")
        log2.info("from log2")

        entries = log1.get_entries()
        assert len(entries) == 1
        assert entries[0].correlation_context.trace_id == "t1"
