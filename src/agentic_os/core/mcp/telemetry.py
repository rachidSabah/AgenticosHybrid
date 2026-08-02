"""
MCP Telemetry

Collects and reports telemetry data for MCP servers including:
- Request/response metrics
- Latency distributions
- Error rates
- Resource usage
- Capability usage
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from agentic_os.domain.events import EventEnvelope, Topic
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.event_bus import EventBus

log = get_logger("mcp.telemetry")


def _utcnow() -> datetime:
    return datetime.now(UTC)


class MetricType(StrEnum):
    """Types of telemetry metrics."""

    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    TIMER = "timer"


@dataclass
class TelemetryMetric:
    """A single telemetry metric."""

    name: str
    value: float
    metric_type: MetricType
    labels: dict[str, str]
    timestamp: datetime


@dataclass
class RequestMetric:
    """Metrics for an MCP request."""

    request_id: str
    server_id: str
    method: str
    started_at: datetime
    completed_at: datetime | None = None
    success: bool = True
    error: str | None = None
    latency_ms: float | None = None
    response_size_bytes: int | None = None
    tool_name: str | None = None
    resource_uri: str | None = None


@dataclass
class ServerMetrics:
    """Aggregated metrics for an MCP server."""

    server_id: str
    server_name: str
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_latency_ms: float = 0.0
    min_latency_ms: float | None = None
    max_latency_ms: float | None = None
    avg_latency_ms: float = 0.0
    tool_invocations: dict[str, int] = field(default_factory=dict)
    resource_reads: int = 0
    prompt_calls: int = 0
    errors_by_type: dict[str, int] = field(default_factory=dict)
    last_request_at: datetime | None = None


@dataclass
class TelemetrySnapshot:
    """A point-in-time snapshot of all telemetry data."""

    timestamp: datetime
    total_requests: int
    successful_requests: int
    failed_requests: int
    total_latency_ms: float
    avg_latency_ms: float
    active_servers: int
    server_metrics: dict[str, ServerMetrics]
    recent_errors: list[dict[str, Any]]


class MCPTelemetry:
    """
    MCP Telemetry collector and reporter.

    Features:
    - Request/response tracking
    - Latency measurement
    - Error tracking
    - Server-level aggregations
    - Historical data retention
    - Event-based collection
    """

    def __init__(
        self,
        bus: EventBus,
        max_recent_errors: int = 100,
        retention_seconds: int = 3600,
    ) -> None:
        self._bus = bus
        self._max_recent_errors = max_recent_errors
        self._retention_seconds = retention_seconds

        self._metrics: dict[str, list[TelemetryMetric]] = {}
        self._server_metrics: dict[str, ServerMetrics] = {}
        self._recent_requests: list[RequestMetric] = []
        self._recent_errors: list[dict[str, Any]] = []
        self._pending_requests: dict[str, RequestMetric] = {}

        # Aggregated stats
        self._total_requests: int = 0
        self._successful_requests: int = 0
        self._failed_requests: int = 0
        self._total_latency_ms: float = 0.0
        self._latency_samples: list[float] = []

    async def _emit(self, topic: Topic, payload: dict[str, Any]) -> None:
        """Emit an event to the event bus."""
        await self._bus.publish(
            EventEnvelope(
                type="event",
                source="mcp-telemetry",
                topic=topic.value,
                payload=payload,
            )
        )

    # ── Request Tracking ─────────────────────────────────────────────────

    def start_request(
        self,
        server_id: str,
        server_name: str,
        method: str,
        tool_name: str | None = None,
        resource_uri: str | None = None,
    ) -> str:
        """Start tracking a request. Returns a request ID."""
        request_id = uuid4().hex

        metric = RequestMetric(
            request_id=request_id,
            server_id=server_id,
            method=method,
            started_at=_utcnow(),
            tool_name=tool_name,
            resource_uri=resource_uri,
        )

        self._pending_requests[request_id] = metric
        self._total_requests += 1

        # Initialize server metrics if needed
        if server_id not in self._server_metrics:
            self._server_metrics[server_id] = ServerMetrics(
                server_id=server_id,
                server_name=server_name,
            )

        return request_id

    def complete_request(
        self,
        request_id: str,
        success: bool = True,
        error: str | None = None,
        response_size_bytes: int | None = None,
    ) -> RequestMetric | None:
        """Complete a tracked request."""
        metric = self._pending_requests.pop(request_id, None)
        if not metric:
            log.warning(f"Request {request_id} not found for completion")
            return None

        metric.completed_at = _utcnow()
        metric.success = success
        metric.error = error
        metric.response_size_bytes = response_size_bytes

        latency_ms = (metric.completed_at - metric.started_at).total_seconds() * 1000
        metric.latency_ms = latency_ms

        self._update_server_metrics(metric)
        self._record_latency(latency_ms)

        if success:
            self._successful_requests += 1
        else:
            self._failed_requests += 1
            self._record_error(metric)

        self._recent_requests.append(metric)
        if len(self._recent_requests) > 1000:
            self._recent_requests = self._recent_requests[-1000:]

        return metric

    def _update_server_metrics(self, metric: RequestMetric) -> None:
        """Update server-level metrics."""
        sm = self._server_metrics.get(metric.server_id)
        if not sm:
            return

        sm.total_requests += 1
        if metric.success:
            sm.successful_requests += 1
        else:
            sm.failed_requests += 1

        if metric.latency_ms is not None:
            sm.total_latency_ms += metric.latency_ms
            sm.avg_latency_ms = sm.total_latency_ms / sm.total_requests

            if sm.min_latency_ms is None or metric.latency_ms < sm.min_latency_ms:
                sm.min_latency_ms = metric.latency_ms
            if sm.max_latency_ms is None or metric.latency_ms > sm.max_latency_ms:
                sm.max_latency_ms = metric.latency_ms

        if metric.tool_name:
            sm.tool_invocations[metric.tool_name] = sm.tool_invocations.get(metric.tool_name, 0) + 1

        if metric.method == "resources/read":
            sm.resource_reads += 1

        if metric.method == "prompts/get":
            sm.prompt_calls += 1

        if metric.error:
            err = metric.error
            error_type = type(err).__name__ if isinstance(err, Exception) else "Unknown"
            sm.errors_by_type[error_type] = sm.errors_by_type.get(error_type, 0) + 1

        sm.last_request_at = _utcnow()

    def _record_latency(self, latency_ms: float) -> None:
        """Record a latency sample."""
        self._total_latency_ms += latency_ms
        self._latency_samples.append(latency_ms)
        if len(self._latency_samples) > 1000:
            self._latency_samples = self._latency_samples[-1000:]

    def _record_error(self, metric: RequestMetric) -> None:
        """Record an error."""
        error_entry = {
            "timestamp": metric.completed_at.isoformat()
            if metric.completed_at
            else _utcnow().isoformat(),
            "request_id": metric.request_id,
            "server_id": metric.server_id,
            "method": metric.method,
            "error": str(metric.error) if metric.error else "Unknown",
            "latency_ms": metric.latency_ms,
        }
        self._recent_errors.append(error_entry)
        if len(self._recent_errors) > self._max_recent_errors:
            self._recent_errors = self._recent_errors[-self._max_recent_errors :]

    # ── Metric Recording ────────────────────────────────────────────────

    def record_metric(
        self,
        name: str,
        value: float,
        metric_type: MetricType = MetricType.GAUGE,
        labels: dict[str, str] | None = None,
    ) -> None:
        """Record a custom metric."""
        metric = TelemetryMetric(
            name=name,
            value=value,
            metric_type=metric_type,
            labels=labels or {},
            timestamp=_utcnow(),
        )

        if name not in self._metrics:
            self._metrics[name] = []
        self._metrics[name].append(metric)

    def increment_counter(self, name: str, labels: dict[str, str] | None = None) -> None:
        """Increment a counter metric."""
        self.record_metric(name, 1.0, MetricType.COUNTER, labels)

    def set_gauge(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        """Set a gauge metric."""
        self.record_metric(name, value, MetricType.GAUGE, labels)

    def record_histogram(
        self, name: str, value: float, labels: dict[str, str] | None = None
    ) -> None:
        """Record a histogram value."""
        self.record_metric(name, value, MetricType.HISTOGRAM, labels)

    # ── Aggregation ─────────────────────────────────────────────────────

    def get_snapshot(self) -> TelemetrySnapshot:
        """Get a point-in-time snapshot of all telemetry."""
        total = self._total_requests
        avg_latency = self._total_latency_ms / total if total > 0 else 0.0

        return TelemetrySnapshot(
            timestamp=_utcnow(),
            total_requests=self._total_requests,
            successful_requests=self._successful_requests,
            failed_requests=self._failed_requests,
            total_latency_ms=self._total_latency_ms,
            avg_latency_ms=avg_latency,
            active_servers=len(self._server_metrics),
            server_metrics=self._server_metrics.copy(),
            recent_errors=self._recent_errors.copy(),
        )

    def get_server_metrics(self, server_id: str) -> ServerMetrics | None:
        """Get metrics for a specific server."""
        return self._server_metrics.get(server_id)

    def get_all_server_metrics(self) -> dict[str, ServerMetrics]:
        """Get metrics for all servers."""
        return self._server_metrics.copy()

    def get_latency_distribution(self) -> dict[str, float]:
        """Get latency distribution percentiles."""
        if not self._latency_samples:
            return {"p50": 0.0, "p90": 0.0, "p95": 0.0, "p99": 0.0}

        sorted_samples = sorted(self._latency_samples)
        n = len(sorted_samples)

        return {
            "p50": sorted_samples[int(n * 0.5)],
            "p90": sorted_samples[int(n * 0.9)],
            "p95": sorted_samples[int(n * 0.95)],
            "p99": sorted_samples[int(n * 0.99)] if n >= 100 else sorted_samples[-1],
            "min": sorted_samples[0],
            "max": sorted_samples[-1],
            "count": n,
        }

    def get_error_rate(self) -> float:
        """Get the current error rate."""
        if self._total_requests == 0:
            return 0.0
        return self._failed_requests / self._total_requests

    def get_recent_errors(self, limit: int = 20) -> list[dict[str, Any]]:
        """Get the most recent errors."""
        return self._recent_errors[-limit:]

    def get_summary(self) -> dict[str, Any]:
        """Get a summary of all telemetry."""
        return {
            "total_requests": self._total_requests,
            "successful_requests": self._successful_requests,
            "failed_requests": self._failed_requests,
            "error_rate": self.get_error_rate(),
            "avg_latency_ms": self._total_latency_ms / self._total_requests
            if self._total_requests > 0
            else 0.0,
            "active_servers": len(self._server_metrics),
            "latency_distribution": self.get_latency_distribution(),
        }

    # ── Cleanup ─────────────────────────────────────────────────────────

    async def cleanup_old_data(self) -> dict[str, int]:
        """Remove old telemetry data."""
        cutoff = _utcnow().timestamp() - self._retention_seconds
        stats = {"metrics_removed": 0, "requests_removed": 0}

        for name in list(self._metrics.keys()):
            self._metrics[name] = [
                m for m in self._metrics[name] if m.timestamp.timestamp() > cutoff
            ]
            stats["metrics_removed"] += len(self._metrics[name])

        old_count = len(self._recent_requests)
        self._recent_requests = [
            r
            for r in self._recent_requests
            if r.completed_at is not None and r.completed_at.timestamp() > cutoff
        ]
        stats["requests_removed"] = old_count - len(self._recent_requests)

        return stats


__all__ = [
    "MCPTelemetry",
    "TelemetryMetric",
    "RequestMetric",
    "ServerMetrics",
    "TelemetrySnapshot",
    "MetricType",
]
