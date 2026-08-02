"""Tests for agentic_os.domain.observability."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from agentic_os.domain.observability import (
    CorrelationContext,
    HealthCheck,
    LogEntry,
    LogLevel,
    Metric,
    MetricType,
    Span,
    SpanContext,
    SpanEvent,
    SpanKind,
    SpanStatus,
    Trace,
)

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TestSpanKind:
    def test_members(self) -> None:
        assert SpanKind.INTERNAL.value == "internal"
        assert SpanKind.SERVER.value == "server"
        assert SpanKind.CLIENT.value == "client"
        assert SpanKind.PRODUCER.value == "producer"
        assert SpanKind.CONSUMER.value == "consumer"

    def test_all_members_defined(self) -> None:
        expected = {"INTERNAL", "SERVER", "CLIENT", "PRODUCER", "CONSUMER"}
        assert {m.name for m in SpanKind} == expected


class TestSpanStatus:
    def test_members(self) -> None:
        assert SpanStatus.OK.value == "ok"
        assert SpanStatus.ERROR.value == "error"
        assert SpanStatus.UNSET.value == "unset"

    def test_all_members_defined(self) -> None:
        expected = {"OK", "ERROR", "UNSET"}
        assert {m.name for m in SpanStatus} == expected


class TestMetricType:
    def test_members(self) -> None:
        assert MetricType.COUNTER.value == "counter"
        assert MetricType.GAUGE.value == "gauge"
        assert MetricType.HISTOGRAM.value == "histogram"
        assert MetricType.SUMMARY.value == "summary"

    def test_all_members_defined(self) -> None:
        expected = {"COUNTER", "GAUGE", "HISTOGRAM", "SUMMARY"}
        assert {m.name for m in MetricType} == expected


class TestLogLevel:
    def test_members(self) -> None:
        assert LogLevel.DEBUG.value == "debug"
        assert LogLevel.INFO.value == "info"
        assert LogLevel.WARNING.value == "warning"
        assert LogLevel.ERROR.value == "error"
        assert LogLevel.CRITICAL.value == "critical"

    def test_all_members_defined(self) -> None:
        expected = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        assert {m.name for m in LogLevel} == expected


# ---------------------------------------------------------------------------
# SpanContext
# ---------------------------------------------------------------------------


class TestSpanContext:
    def test_creation_defaults(self) -> None:
        ctx = SpanContext(trace_id="abc", span_id="def")
        assert ctx.trace_id == "abc"
        assert ctx.span_id == "def"
        assert ctx.trace_flags == 1
        assert ctx.trace_state is None

    def test_creation_with_all_fields(self) -> None:
        ctx = SpanContext(
            trace_id="abc",
            span_id="def",
            trace_flags=0,
            trace_state="foo=bar",
        )
        assert ctx.trace_flags == 0
        assert ctx.trace_state == "foo=bar"

    def test_to_dict(self) -> None:
        ctx = SpanContext(trace_id="abc", span_id="def", trace_flags=0, trace_state="k=v")
        d = ctx.to_dict()
        assert d == {
            "trace_id": "abc",
            "span_id": "def",
            "trace_flags": 0,
            "trace_state": "k=v",
        }

    def test_to_dict_default_trace_state_none(self) -> None:
        ctx = SpanContext(trace_id="abc", span_id="def")
        d = ctx.to_dict()
        assert d["trace_state"] is None

    def test_from_dict(self) -> None:
        ctx = SpanContext.from_dict(
            {"trace_id": "abc", "span_id": "def", "trace_flags": 0, "trace_state": "k=v"}
        )
        assert ctx.trace_id == "abc"
        assert ctx.span_id == "def"
        assert ctx.trace_flags == 0
        assert ctx.trace_state == "k=v"

    def test_from_dict_defaults(self) -> None:
        ctx = SpanContext.from_dict({"trace_id": "abc", "span_id": "def"})
        assert ctx.trace_flags == 1
        assert ctx.trace_state is None

    def test_from_dict_roundtrip(self) -> None:
        original = SpanContext(trace_id="abc", span_id="def", trace_flags=0, trace_state="x=y")
        restored = SpanContext.from_dict(original.to_dict())
        assert restored == original

    def test_generate_creates_different_values(self) -> None:
        ctx1 = SpanContext.generate()
        ctx2 = SpanContext.generate()
        assert ctx1.trace_id != ctx2.trace_id
        assert ctx1.span_id != ctx2.span_id

    def test_generate_has_valid_lengths(self) -> None:
        ctx = SpanContext.generate()
        assert len(ctx.trace_id) == 32  # uuid4 hex
        assert len(ctx.span_id) == 16  # uuid4 hex[:16]

    def test_immutable(self) -> None:
        ctx = SpanContext(trace_id="abc", span_id="def")
        with pytest.raises(AttributeError):
            ctx.trace_id = "xyz"  # type: ignore[misc]

    def test_slots(self) -> None:
        ctx = SpanContext(trace_id="abc", span_id="def")
        with pytest.raises((AttributeError, TypeError)):
            ctx.new_attr = "value"  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# CorrelationContext
# ---------------------------------------------------------------------------


class TestCorrelationContext:
    def test_creation_defaults(self) -> None:
        cc = CorrelationContext(trace_id="abc", span_id="def")
        assert cc.trace_id == "abc"
        assert cc.span_id == "def"
        assert cc.baggage == {}

    def test_creation_with_baggage(self) -> None:
        cc = CorrelationContext(
            trace_id="abc", span_id="def", baggage={"user": "alice", "env": "prod"}
        )
        assert cc.baggage == {"user": "alice", "env": "prod"}

    def test_to_dict(self) -> None:
        cc = CorrelationContext(trace_id="abc", span_id="def", baggage={"k": "v"})
        d = cc.to_dict()
        assert d == {"trace_id": "abc", "span_id": "def", "baggage": {"k": "v"}}

    def test_from_dict(self) -> None:
        cc = CorrelationContext.from_dict(
            {"trace_id": "abc", "span_id": "def", "baggage": {"k": "v"}}
        )
        assert cc.trace_id == "abc"
        assert cc.span_id == "def"
        assert cc.baggage == {"k": "v"}

    def test_from_dict_default_baggage(self) -> None:
        cc = CorrelationContext.from_dict({"trace_id": "abc", "span_id": "def"})
        assert cc.baggage == {}

    def test_from_dict_roundtrip(self) -> None:
        original = CorrelationContext(trace_id="abc", span_id="def", baggage={"env": "test"})
        restored = CorrelationContext.from_dict(original.to_dict())
        assert restored == original

    def test_generate_creates_different_values(self) -> None:
        cc1 = CorrelationContext.generate()
        cc2 = CorrelationContext.generate()
        assert cc1.trace_id != cc2.trace_id
        assert cc1.span_id != cc2.span_id

    def test_immutable(self) -> None:
        cc = CorrelationContext(trace_id="abc", span_id="def")
        with pytest.raises(AttributeError):
            cc.trace_id = "xyz"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# SpanEvent
# ---------------------------------------------------------------------------


class TestSpanEvent:
    def test_creation_defaults(self) -> None:
        event = SpanEvent(name="event1")
        assert event.name == "event1"
        assert event.attributes == {}
        assert isinstance(event.timestamp, datetime)

    def test_creation_with_attributes(self) -> None:
        now = datetime.now(UTC)
        event = SpanEvent(name="ev", attributes={"key": "val"}, timestamp=now)
        assert event.name == "ev"
        assert event.attributes == {"key": "val"}
        assert event.timestamp is now

    def test_to_dict(self) -> None:
        now = datetime.now(UTC)
        event = SpanEvent(name="ev", attributes={"k": "v"}, timestamp=now)
        d = event.to_dict()
        assert d["name"] == "ev"
        assert d["attributes"] == {"k": "v"}
        assert d["timestamp"] == now.isoformat()


# ---------------------------------------------------------------------------
# Span
# ---------------------------------------------------------------------------


class TestSpan:
    def test_creation_defaults(self) -> None:
        ctx = SpanContext(trace_id="t", span_id="s")
        span = Span(name="op", context=ctx)
        assert span.name == "op"
        assert span.context == ctx
        assert span.parent_context is None
        assert span.kind is SpanKind.INTERNAL
        assert span.attributes == {}
        assert span.events == ()
        assert span.status is SpanStatus.UNSET
        assert span.status_message is None
        assert isinstance(span.start_time, datetime)
        assert span.end_time is None

    def test_creation_with_parent(self) -> None:
        parent = SpanContext(trace_id="t", span_id="parent")
        ctx = SpanContext(trace_id="t", span_id="child")
        span = Span(name="child", context=ctx, parent_context=parent)
        assert span.parent_context == parent

    def test_to_dict(self) -> None:
        ctx = SpanContext(trace_id="t", span_id="s")
        span = Span(name="op", context=ctx)
        d = span.to_dict()
        assert d["name"] == "op"
        assert d["context"] == ctx.to_dict()
        assert d["parent_context"] is None
        assert d["kind"] == "internal"
        assert d["status"] == "unset"
        assert d["status_message"] is None
        assert d["events"] == []
        assert d["end_time"] is None
        assert d["start_time"] == span.start_time.isoformat()

    def test_to_dict_with_parent(self) -> None:
        parent = SpanContext(trace_id="t", span_id="p")
        ctx = SpanContext(trace_id="t", span_id="c")
        span = Span(name="op", context=ctx, parent_context=parent)
        d = span.to_dict()
        assert d["parent_context"] == parent.to_dict()

    def test_with_end_time_creates_finished_span(self) -> None:
        ctx = SpanContext(trace_id="t", span_id="s")
        span = Span(name="op", context=ctx)
        finished = span.with_end_time()
        assert finished.is_finished() is True
        assert finished.duration_ms() is not None
        assert finished.duration_ms() >= 0
        # original remains untouched
        assert span.is_finished() is False
        assert span.end_time is None

    def test_with_end_time_explicit_time(self) -> None:
        ctx = SpanContext(trace_id="t", span_id="s")
        span = Span(name="op", context=ctx)
        end = span.start_time + timedelta(seconds=2)
        finished = span.with_end_time(end_time=end)
        assert finished.end_time is end
        assert finished.duration_ms() == pytest.approx(2000.0)

    def test_with_status(self) -> None:
        ctx = SpanContext(trace_id="t", span_id="s")
        span = Span(name="op", context=ctx)
        updated = span.with_status(SpanStatus.ERROR, message="boom")
        assert updated.status is SpanStatus.ERROR
        assert updated.status_message == "boom"
        # original remains untouched
        assert span.status is SpanStatus.UNSET
        assert span.status_message is None

    def test_with_status_no_message(self) -> None:
        ctx = SpanContext(trace_id="t", span_id="s")
        span = Span(name="op", context=ctx)
        updated = span.with_status(SpanStatus.OK)
        assert updated.status is SpanStatus.OK
        assert updated.status_message is None

    def test_with_event_appends_event(self) -> None:
        ctx = SpanContext(trace_id="t", span_id="s")
        span = Span(name="op", context=ctx)
        event1 = SpanEvent(name="e1")
        event2 = SpanEvent(name="e2")
        span1 = span.with_event(event1)
        span2 = span1.with_event(event2)
        assert span.events == ()
        assert span1.events == (event1,)
        assert span2.events == (event1, event2)

    def test_duration_ms_returns_none_when_not_finished(self) -> None:
        ctx = SpanContext(trace_id="t", span_id="s")
        span = Span(name="op", context=ctx)
        assert span.duration_ms() is None

    def test_duration_ms_returns_value_when_finished(self) -> None:
        ctx = SpanContext(trace_id="t", span_id="s")
        span = Span(name="op", context=ctx)
        finished = span.with_end_time()
        assert finished.duration_ms() is not None
        assert isinstance(finished.duration_ms(), float)

    def test_is_finished_false_by_default(self) -> None:
        ctx = SpanContext(trace_id="t", span_id="s")
        span = Span(name="op", context=ctx)
        assert span.is_finished() is False

    def test_is_finished_true_after_with_end_time(self) -> None:
        ctx = SpanContext(trace_id="t", span_id="s")
        span = Span(name="op", context=ctx)
        assert span.with_end_time().is_finished() is True

    def test_immutable(self) -> None:
        ctx = SpanContext(trace_id="t", span_id="s")
        span = Span(name="op", context=ctx)
        with pytest.raises(AttributeError):
            span.name = "changed"  # type: ignore[misc]

    def test_slots(self) -> None:
        ctx = SpanContext(trace_id="t", span_id="s")
        span = Span(name="op", context=ctx)
        with pytest.raises((AttributeError, TypeError)):
            span.new_field = "x"  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Trace
# ---------------------------------------------------------------------------


class TestTrace:
    def test_creation(self) -> None:
        ctx1 = SpanContext(trace_id="t", span_id="s1")
        span1 = Span(name="root", context=ctx1)
        trace = Trace(spans=(span1,))
        assert trace.spans == (span1,)
        assert trace.root_span_id is None

    def test_to_dict(self) -> None:
        ctx1 = SpanContext(trace_id="t", span_id="s1")
        span1 = Span(name="root", context=ctx1)
        trace = Trace(spans=(span1,))
        d = trace.to_dict()
        assert d["spans"] == [span1.to_dict()]
        assert d["root_span_id"] is None

    def test_get_span_found(self) -> None:
        ctx1 = SpanContext(trace_id="t", span_id="s1")
        ctx2 = SpanContext(trace_id="t", span_id="s2")
        span1 = Span(name="a", context=ctx1)
        span2 = Span(name="b", context=ctx2)
        trace = Trace(spans=(span1, span2))
        assert trace.get_span("s1") is span1
        assert trace.get_span("s2") is span2

    def test_get_span_not_found(self) -> None:
        ctx = SpanContext(trace_id="t", span_id="s1")
        span = Span(name="a", context=ctx)
        trace = Trace(spans=(span,))
        assert trace.get_span("nonexistent") is None

    def test_get_root_span_with_explicit_root(self) -> None:
        ctx1 = SpanContext(trace_id="t", span_id="root")
        ctx2 = SpanContext(trace_id="t", span_id="child", trace_flags=1)
        span1 = Span(name="root", context=ctx1)
        span2 = Span(name="child", context=ctx2, parent_context=ctx1)
        trace = Trace(spans=(span1, span2), root_span_id="root")
        assert trace.get_root_span() is span1

    def test_get_root_span_auto_detect(self) -> None:
        """No explicit root_span_id, should auto-detect span with no parent."""
        ctx1 = SpanContext(trace_id="t", span_id="root")
        ctx2 = SpanContext(trace_id="t", span_id="child")
        span1 = Span(name="root", context=ctx1)
        span2 = Span(name="child", context=ctx2, parent_context=ctx1)
        trace = Trace(spans=(span1, span2))
        assert trace.get_root_span() is span1

    def test_get_root_span_auto_detect_first_if_all_have_parents_outside_trace(
        self,
    ) -> None:
        """All spans have parent_context whose span_id is outside the trace."""
        ctx1 = SpanContext(trace_id="t", span_id="s1")
        ctx2 = SpanContext(trace_id="t", span_id="s2")
        parent_outside = SpanContext(trace_id="t", span_id="outside")
        span1 = Span(name="a", context=ctx1, parent_context=parent_outside)
        span2 = Span(name="b", context=ctx2, parent_context=parent_outside)
        trace = Trace(spans=(span1, span2))
        # Both have parents outside, so we rely on parent_context.span_id not in span_ids
        # and pick the first match (span1)
        assert trace.get_root_span() is span1

    def test_get_root_span_empty_tuple(self) -> None:
        trace = Trace(spans=())
        assert trace.get_root_span() is None

    def test_get_root_span_fallback_to_first(self) -> None:
        """When no root_span_id and auto-detect fails, falls back to first span."""
        ctx1 = SpanContext(trace_id="t", span_id="s1")
        span1 = Span(name="a", context=ctx1)
        trace = Trace(spans=(span1,))
        assert trace.get_root_span() is span1


# ---------------------------------------------------------------------------
# Metric
# ---------------------------------------------------------------------------


class TestMetric:
    def test_creation_defaults(self) -> None:
        metric = Metric(name="cpu", type=MetricType.GAUGE, value=0.95)
        assert metric.name == "cpu"
        assert metric.type is MetricType.GAUGE
        assert metric.value == 0.95
        assert metric.labels == {}
        assert metric.unit is None
        assert metric.description is None
        assert isinstance(metric.timestamp, datetime)

    def test_creation_no_unit_no_description(self) -> None:
        metric = Metric(name="count", type=MetricType.COUNTER, value=42)
        assert metric.unit is None
        assert metric.description is None

    def test_creation_with_all_fields(self) -> None:
        now = datetime.now(UTC)
        metric = Metric(
            name="latency",
            type=MetricType.HISTOGRAM,
            value=123.0,
            labels={"method": "GET"},
            unit="ms",
            description="Request latency",
            timestamp=now,
        )
        assert metric.unit == "ms"
        assert metric.description == "Request latency"
        assert metric.labels == {"method": "GET"}
        assert metric.timestamp is now

    def test_metric_type_summary(self) -> None:
        metric = Metric(name="summary_metric", type=MetricType.SUMMARY, value=99.9)
        assert metric.type is MetricType.SUMMARY

    def test_to_dict(self) -> None:
        now = datetime.now(UTC)
        metric = Metric(
            name="mem",
            type=MetricType.GAUGE,
            value=0.5,
            labels={"host": "web01"},
            unit="percent",
            description="Memory usage",
            timestamp=now,
        )
        d = metric.to_dict()
        assert d["name"] == "mem"
        assert d["type"] == "gauge"
        assert d["value"] == 0.5
        assert d["labels"] == {"host": "web01"}
        assert d["unit"] == "percent"
        assert d["description"] == "Memory usage"
        assert d["timestamp"] == now.isoformat()

    def test_to_dict_no_unit_no_description(self) -> None:
        metric = Metric(name="hits", type=MetricType.COUNTER, value=10)
        d = metric.to_dict()
        assert d["unit"] is None
        assert d["description"] is None


# ---------------------------------------------------------------------------
# LogEntry
# ---------------------------------------------------------------------------


class TestLogEntry:
    def test_creation_defaults(self) -> None:
        entry = LogEntry(level="info", message="hello")
        assert entry.level == "info"
        assert entry.message == "hello"
        assert entry.attributes == {}
        assert isinstance(entry.timestamp, datetime)
        assert entry.correlation_context is None

    def test_creation_with_all_fields(self) -> None:
        now = datetime.now(UTC)
        cc = CorrelationContext(trace_id="t", span_id="s")
        entry = LogEntry(
            level="error",
            message="boom",
            attributes={"code": 500},
            timestamp=now,
            correlation_context=cc,
        )
        assert entry.level == "error"
        assert entry.attributes == {"code": 500}
        assert entry.timestamp is now
        assert entry.correlation_context is cc

    def test_to_dict(self) -> None:
        now = datetime.now(UTC)
        cc = CorrelationContext(trace_id="t", span_id="s", baggage={"k": "v"})
        entry = LogEntry(
            level="warn",
            message="slow",
            attributes={"latency": 200},
            timestamp=now,
            correlation_context=cc,
        )
        d = entry.to_dict()
        assert d["level"] == "warn"
        assert d["message"] == "slow"
        assert d["attributes"] == {"latency": 200}
        assert d["timestamp"] == now.isoformat()
        assert d["correlation_context"] == cc.to_dict()

    def test_to_dict_no_correlation_context(self) -> None:
        entry = LogEntry(level="info", message="test")
        d = entry.to_dict()
        assert d["correlation_context"] is None


# ---------------------------------------------------------------------------
# HealthCheck
# ---------------------------------------------------------------------------


class TestHealthCheck:
    def test_creation_defaults(self) -> None:
        hc = HealthCheck(component="db", healthy=True)
        assert hc.component == "db"
        assert hc.healthy is True
        assert hc.message is None
        assert hc.details == {}
        assert isinstance(hc.timestamp, datetime)

    def test_creation_with_all_fields(self) -> None:
        now = datetime.now(UTC)
        hc = HealthCheck(
            component="api",
            healthy=False,
            message="timeout",
            details={"status_code": 503},
            timestamp=now,
        )
        assert hc.component == "api"
        assert hc.healthy is False
        assert hc.message == "timeout"
        assert hc.details == {"status_code": 503}
        assert hc.timestamp is now

    def test_to_dict(self) -> None:
        now = datetime.now(UTC)
        hc = HealthCheck(
            component="cache",
            healthy=True,
            message="ok",
            details={"latency_ms": 2},
            timestamp=now,
        )
        d = hc.to_dict()
        assert d["component"] == "cache"
        assert d["healthy"] is True
        assert d["message"] == "ok"
        assert d["details"] == {"latency_ms": 2}
        assert d["timestamp"] == now.isoformat()

    def test_to_dict_no_message(self) -> None:
        hc = HealthCheck(component="disk", healthy=True)
        d = hc.to_dict()
        assert d["message"] is None


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_span_context_trace_flags_and_trace_state(self) -> None:
        """SpanContext with non-default trace_flags and trace_state."""
        ctx = SpanContext(
            trace_id="abc",
            span_id="def",
            trace_flags=0,
            trace_state="tenant=acme,congauth=conga0",
        )
        assert ctx.trace_flags == 0
        assert ctx.trace_state == "tenant=acme,congauth=conga0"

    def test_correlation_context_with_baggage(self) -> None:
        """CorrelationContext with baggage populated."""
        cc = CorrelationContext(
            trace_id="t",
            span_id="s",
            baggage={"user": "bob", "role": "admin", "region": "us-east"},
        )
        assert len(cc.baggage) == 3
        assert cc.baggage["user"] == "bob"

    def test_span_no_parent_context(self) -> None:
        """Span with parent_context=None explicitly."""
        ctx = SpanContext(trace_id="t", span_id="s")
        span = Span(name="op", context=ctx, parent_context=None)
        assert span.parent_context is None
        d = span.to_dict()
        assert d["parent_context"] is None

    def test_span_no_end_time_duration_ms_none_is_finished_false(self) -> None:
        """Span with no end_time: duration_ms returns None, is_finished False."""
        ctx = SpanContext(trace_id="t", span_id="s")
        span = Span(name="op", context=ctx)
        assert span.duration_ms() is None
        assert span.is_finished() is False

    def test_trace_no_root_span_id_auto_detect_root(self) -> None:
        """Trace with root_span_id=None auto-detects root span."""
        ctx_root = SpanContext(trace_id="t", span_id="r")
        ctx_child = SpanContext(trace_id="t", span_id="c")
        span_root = Span(name="root", context=ctx_root)
        span_child = Span(name="child", context=ctx_child, parent_context=ctx_root)
        trace = Trace(spans=(span_root, span_child), root_span_id=None)
        root = trace.get_root_span()
        assert root is span_root

    def test_trace_empty_spans_tuple(self) -> None:
        """Trace with empty spans tuple."""
        trace = Trace(spans=())
        assert trace.spans == ()
        assert trace.get_span("x") is None
        assert trace.get_root_span() is None
        d = trace.to_dict()
        assert d["spans"] == []
        assert d["root_span_id"] is None

    def test_span_empty_events_tuple(self) -> None:
        """Span with empty events tuple."""
        ctx = SpanContext(trace_id="t", span_id="s")
        span = Span(name="op", context=ctx)
        assert span.events == ()
        assert span.to_dict()["events"] == []

    def test_metric_no_unit_no_description(self) -> None:
        """Metric with unit=None and description=None."""
        metric = Metric(name="cpu", type=MetricType.GAUGE, value=0.5)
        assert metric.unit is None
        assert metric.description is None
        d = metric.to_dict()
        assert d["unit"] is None
        assert d["description"] is None

    def test_span_with_event_copies_context(self) -> None:
        """Verify with_event creates a new span with same context."""
        ctx = SpanContext(trace_id="t", span_id="s")
        span = Span(name="op", context=ctx)
        event = SpanEvent(name="ev")
        updated = span.with_event(event)
        assert updated.context is ctx  # shared reference
        assert updated.name == span.name
        assert updated.parent_context is span.parent_context

    def test_span_with_end_time_copies_context(self) -> None:
        ctx = SpanContext(trace_id="t", span_id="s")
        span = Span(name="op", context=ctx)
        finished = span.with_end_time()
        assert finished.context is ctx
        assert finished.name == span.name

    def test_span_with_status_copies_context(self) -> None:
        ctx = SpanContext(trace_id="t", span_id="s")
        span = Span(name="op", context=ctx)
        updated = span.with_status(SpanStatus.ERROR, "err")
        assert updated.context is ctx
        assert updated.name == span.name

    def test_trace_to_dict_with_root_span_id(self) -> None:
        ctx = SpanContext(trace_id="t", span_id="s")
        span = Span(name="op", context=ctx)
        trace = Trace(spans=(span,), root_span_id="s")
        d = trace.to_dict()
        assert d["root_span_id"] == "s"

    def test_log_entry_using_loglevel_enum(self) -> None:
        """LogEntry level can be a LogLevel enum member (string)."""
        entry = LogEntry(level=LogLevel.ERROR, message="fail")
        assert entry.level == "error"
        assert entry.level is LogLevel.ERROR
        d = entry.to_dict()
        assert d["level"] == "error"
