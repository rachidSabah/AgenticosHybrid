"""Prometheus Metrics Implementation

Core implementation of MetricsPort using Prometheus client.
"""

from __future__ import annotations

from collections import defaultdict

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    Summary,
    generate_latest,
)

from agentic_os.domain.observability import Metric, MetricType
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.observability import MetricsPort

log = get_logger("observability.metrics")


class PrometheusMetrics(MetricsPort):
    """Prometheus-based metrics implementation."""

    def __init__(self, registry: CollectorRegistry | None = None):
        self._registry = registry or CollectorRegistry()
        self._counters: dict[str, Counter] = {}
        self._gauges: dict[str, Gauge] = {}
        self._histograms: dict[str, Histogram] = {}
        self._summaries: dict[str, Summary] = {}
        self._metrics_cache: dict[str, Metric] = {}
        self._lock = defaultdict(lambda: defaultdict(float))

    def _get_labels_key(self, labels: dict[str, str] | None) -> str:
        """Generate a cache key for labels."""
        if not labels:
            return ""
        return ",".join(f"{k}={v}" for k, v in sorted(labels.items()))

    def _get_or_create_counter(
        self, name: str, labels: dict[str, str] | None, unit: str | None, description: str | None
    ) -> Counter:
        key = f"{name}:{self._get_labels_key(labels)}"
        if key not in self._counters:
            label_names = list(labels.keys()) if labels else []
            self._counters[key] = Counter(
                name, description or "", labelnames=label_names, registry=self._registry
            )
        return self._counters[key]

    def _get_or_create_gauge(
        self, name: str, labels: dict[str, str] | None, unit: str | None, description: str | None
    ) -> Gauge:
        key = f"{name}:{self._get_labels_key(labels)}"
        if key not in self._gauges:
            label_names = list(labels.keys()) if labels else []
            self._gauges[key] = Gauge(
                name, description or "", labelnames=label_names, registry=self._registry
            )
        return self._gauges[key]

    def _get_or_create_histogram(
        self, name: str, labels: dict[str, str] | None, unit: str | None, description: str | None
    ) -> Histogram:
        key = f"{name}:{self._get_labels_key(labels)}"
        if key not in self._histograms:
            label_names = list(labels.keys()) if labels else []
            self._histograms[key] = Histogram(
                name, description or "", labelnames=label_names, registry=self._registry
            )
        return self._histograms[key]

    def _get_or_create_summary(
        self, name: str, labels: dict[str, str] | None, unit: str | None, description: str | None
    ) -> Summary:
        key = f"{name}:{self._get_labels_key(labels)}"
        if key not in self._summaries:
            label_names = list(labels.keys()) if labels else []
            self._summaries[key] = Summary(
                name, description or "", labelnames=label_names, registry=self._registry
            )
        return self._summaries[key]

    def counter(
        self,
        name: str,
        value: float = 1.0,
        labels: dict[str, str] | None = None,
        unit: str | None = None,
        description: str | None = None,
    ) -> None:
        """Record a counter metric."""
        counter = self._get_or_create_counter(name, labels, unit, description)
        if labels:
            counter.labels(**labels).inc(value)
        else:
            counter.inc(value)

        # Update cache
        metric_key = f"{name}:{self._get_labels_key(labels)}"
        self._metrics_cache[metric_key] = Metric(
            name=name,
            type=MetricType.COUNTER,
            value=value,
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
        """Record a gauge metric."""
        gauge = self._get_or_create_gauge(name, labels, unit, description)
        if labels:
            gauge.labels(**labels).set(value)
        else:
            gauge.set(value)

        # Update cache
        metric_key = f"{name}:{self._get_labels_key(labels)}"
        self._metrics_cache[metric_key] = Metric(
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
        """Record a histogram metric."""
        histogram = self._get_or_create_histogram(name, labels, unit, description)
        if labels:
            histogram.labels(**labels).observe(value)
        else:
            histogram.observe(value)

        # Update cache
        metric_key = f"{name}:{self._get_labels_key(labels)}"
        self._metrics_cache[metric_key] = Metric(
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
        """Record a summary metric."""
        summary = self._get_or_create_summary(name, labels, unit, description)
        if labels:
            summary.labels(**labels).observe(value)
        else:
            summary.observe(value)

        # Update cache
        metric_key = f"{name}:{self._get_labels_key(labels)}"
        self._metrics_cache[metric_key] = Metric(
            name=name,
            type=MetricType.SUMMARY,
            value=value,
            labels=labels or {},
            unit=unit,
            description=description,
        )

    def record_metric(self, metric: Metric) -> None:
        """Record a metric directly."""
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
        """Get a metric value."""
        key = f"{name}:{self._get_labels_key(labels)}"
        return self._metrics_cache.get(key)

    def list_metrics(self, prefix: str = "") -> list[Metric]:
        """List all metrics matching prefix."""
        return [m for k, m in self._metrics_cache.items() if k.startswith(prefix)]

    def export_prometheus(self) -> bytes:
        """Export metrics in Prometheus format."""
        return generate_latest(self._registry)

    def get_content_type(self) -> str:
        """Get Prometheus content type."""
        return CONTENT_TYPE_LATEST


# Global metrics instance
_metrics_instance: PrometheusMetrics | None = None


def get_metrics() -> PrometheusMetrics:
    """Get or create the global metrics instance."""
    global _metrics_instance
    if _metrics_instance is None:
        _metrics_instance = PrometheusMetrics()
    return _metrics_instance


def configure_metrics(registry: CollectorRegistry | None = None) -> PrometheusMetrics:
    """Configure and return the global metrics instance."""
    global _metrics_instance
    _metrics_instance = PrometheusMetrics(registry)
    return _metrics_instance
