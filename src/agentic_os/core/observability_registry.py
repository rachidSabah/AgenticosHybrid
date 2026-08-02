"""Observability Registry — Metrics, timings, snapshots, and dependency graph data.

The Kernel's observability hub. Every service can record metrics and snapshots
through this registry, which aggregates them into a holistic view of Kernel health,
startup performance, and runtime behavior.

Usage:
    obs = ObservabilityRegistry(lifecycle, container, health_registry)
    obs.record_metric("requests_per_second", 42.0, tags={"service": "api"})
    report = obs.generate_health_report()
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from agentic_os.core.container import Container
from agentic_os.core.health_registry import HealthRegistry
from agentic_os.core.lifecycle import LifecycleManager, Phase, PhaseResult

log = logging.getLogger("agentic_os.observability")


@dataclass
class MetricPoint:
    """A single metric data point with optional tags."""

    name: str
    value: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    tags: dict[str, str] = field(default_factory=dict)
    unit: str = "count"


@dataclass
class PhaseTiming:
    """Timing data for a single startup phase."""

    phase: Phase
    success: bool
    services_count: int
    services_started: int
    services_failed: int
    duration_ms: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class KernelSnapshot:
    """Complete snapshot of Kernel state at a point in time."""

    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    container_registration_count: int = 0
    container_singleton_count: int = 0
    lifecycle_state: str = ""
    current_phase: str | None = None
    service_count: int = 0
    healthy_services: int = 0
    degraded_services: int = 0
    failed_services: int = 0
    background_services: int = 0
    uptime_seconds: float = 0.0
    total_errors: int = 0
    phases: dict[str, dict[str, Any]] = field(default_factory=dict)
    metrics_summary: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "container": {
                "registrations": self.container_registration_count,
                "singletons": self.container_singleton_count,
            },
            "lifecycle": {
                "state": self.lifecycle_state,
                "current_phase": self.current_phase,
            },
            "services": {
                "total": self.service_count,
                "healthy": self.healthy_services,
                "degraded": self.degraded_services,
                "failed": self.failed_services,
                "background": self.background_services,
            },
            "uptime_seconds": self.uptime_seconds,
            "total_errors": self.total_errors,
            "phases": self.phases,
            "metrics": self.metrics_summary,
        }


class ObservabilityRegistry:
    """Kernel observability hub.

    Collects metrics, startup timings, and service snapshots, and provides
    a holistic health report.
    """

    def __init__(
        self,
        lifecycle: LifecycleManager,
        container: Container,
        health_registry: HealthRegistry | None = None,
    ) -> None:
        self._lifecycle = lifecycle
        self._container = container
        self._health_registry = health_registry

        self._metrics: list[MetricPoint] = []
        self._metric_aggregates: dict[str, list[float]] = defaultdict(list)
        self._max_metric_points = 10_000

        self._phase_timings: dict[Phase, PhaseTiming] = {}

        self._snapshots: list[KernelSnapshot] = []
        self._max_snapshots = 1000

        self._error_count = 0
        self._last_errors: list[str] = []

        self._started_at: datetime | None = None

    # ── Startup Tracking ──

    def mark_started(self) -> None:
        self._started_at = datetime.now(UTC)

    def record_phase_timing(self, result: PhaseResult) -> None:
        timing = PhaseTiming(
            phase=result.phase,
            success=result.success,
            services_count=(len(result.started_services) + len(result.failed_services)),
            services_started=len(result.started_services),
            services_failed=len(result.failed_services),
            duration_ms=result.duration_ms,
        )
        self._phase_timings[result.phase] = timing

    def get_phase_timings(self) -> list[PhaseTiming]:
        ordered = []
        for phase in list(Phase):
            if phase in self._phase_timings:
                ordered.append(self._phase_timings[phase])
        return ordered

    def total_startup_duration_ms(self) -> float:
        return sum(t.duration_ms for t in self._phase_timings.values())

    # ── Metric Recording ──

    def record_metric(
        self,
        name: str,
        value: float,
        tags: dict[str, str] | None = None,
        unit: str = "count",
    ) -> None:
        point = MetricPoint(name=name, value=value, tags=tags or {}, unit=unit)
        self._metrics.append(point)
        self._metric_aggregates[name].append(value)
        self._trim_metrics()

    def get_metric(self, name: str) -> list[MetricPoint]:
        return [m for m in self._metrics if m.name == name]

    def get_metric_aggregate(self, name: str) -> dict[str, float]:
        values = self._metric_aggregates.get(name, [])
        if not values:
            return {"count": 0, "sum": 0.0, "avg": 0.0, "min": 0.0, "max": 0.0, "latest": 0.0}
        return {
            "count": len(values),
            "sum": sum(values),
            "avg": sum(values) / len(values),
            "min": min(values),
            "max": max(values),
            "latest": values[-1],
        }

    def get_all_metric_summaries(self) -> dict[str, dict[str, float]]:
        return {name: self.get_metric_aggregate(name) for name in self._metric_aggregates}

    # ── Error Tracking ──

    def record_error(self, error: str) -> None:
        self._error_count += 1
        self._last_errors.append(error)
        if len(self._last_errors) > 100:
            self._last_errors = self._last_errors[-100:]

    @property
    def error_count(self) -> int:
        return self._error_count

    def recent_errors(self, limit: int = 10) -> list[str]:
        return self._last_errors[-limit:]

    # ── Snapshots ──

    async def snapshot(self) -> KernelSnapshot:
        lifecycle_health = await self._lifecycle.health()
        state_summary = self._lifecycle.state_summary()
        healthy = len(state_summary.get("healthy", [])) + len(state_summary.get("ready", []))
        degraded = len(state_summary.get("degraded", []))
        failed = len(state_summary.get("failed", []))

        phase_data: dict[str, dict[str, Any]] = {}
        for phase in list(Phase):
            phase_result = self._lifecycle.get_phase_result(phase)
            if phase_result:
                phase_data[phase.value] = {
                    "success": phase_result.success,
                    "started": len(phase_result.started_services),
                    "failed": len(phase_result.failed_services),
                    "duration_ms": phase_result.duration_ms,
                }

        uptime = 0.0
        if self._started_at:
            uptime = (datetime.now(UTC) - self._started_at).total_seconds()

        snapshot = KernelSnapshot(
            container_registration_count=self._container.registration_count,
            container_singleton_count=self._container.singleton_count,
            lifecycle_state=lifecycle_health.get("current_state", "unknown"),
            current_phase=lifecycle_health.get("current_phase"),
            service_count=lifecycle_health.get("total_services", 0),
            healthy_services=healthy,
            degraded_services=degraded,
            failed_services=failed,
            uptime_seconds=uptime,
            total_errors=self._error_count,
            phases=phase_data,
            metrics_summary=self._get_metrics_summary(),
        )
        self._snapshots.append(snapshot)
        self._trim_snapshots()
        return snapshot

    def get_snapshots(self, limit: int = 10, since: datetime | None = None) -> list[KernelSnapshot]:
        snaps = self._snapshots
        if since:
            snaps = [s for s in snaps if s.timestamp >= since]
        return snaps[-limit:]

    # ── Reports ──

    async def generate_health_report(self) -> dict[str, Any]:
        lifecycle_health = await self._lifecycle.health()
        phase_timings = [
            {
                "phase": t.phase.value,
                "success": t.success,
                "services_count": t.services_count,
                "services_started": t.services_started,
                "services_failed": t.services_failed,
                "duration_ms": t.duration_ms,
            }
            for t in self.get_phase_timings()
        ]
        return {
            "kernel": {
                "state": lifecycle_health.get("current_state"),
                "current_phase": lifecycle_health.get("current_phase"),
                "uptime_seconds": (
                    (datetime.now(UTC) - self._started_at).total_seconds()
                    if self._started_at
                    else 0.0
                ),
                "startup_duration_ms": self.total_startup_duration_ms(),
                "errors_total": self._error_count,
            },
            "services": {
                "total": lifecycle_health.get("total_services", 0),
                "by_state": self._lifecycle.state_summary(),
            },
            "phases": phase_timings,
            "metrics": self._get_metrics_summary(),
            "container": {
                "registrations": self._container.registration_count,
                "singletons": self._container.singleton_count,
            },
        }

    def generate_dependency_report(self) -> dict[str, Any]:
        graph = self._container.dependency_graph()
        return {
            "nodes": list(graph.keys()),
            "edges": [
                {"from": source, "to": target}
                for source, targets in graph.items()
                for target in targets
            ],
            "node_count": len(graph),
            "edge_count": sum(len(t) for t in graph.values()),
        }

    # ── Internal ──

    def _get_metrics_summary(self) -> dict[str, float]:
        summary: dict[str, float] = {}
        for name in self._metric_aggregates:
            values = self._metric_aggregates[name]
            if values:
                summary[name] = values[-1]
        return summary

    def _trim_metrics(self) -> None:
        if len(self._metrics) > self._max_metric_points:
            self._metrics = self._metrics[-self._max_metric_points :]
            self._metric_aggregates.clear()
            for m in self._metrics:
                self._metric_aggregates[m.name].append(m.value)

    def _trim_snapshots(self) -> None:
        if len(self._snapshots) > self._max_snapshots:
            self._snapshots = self._snapshots[-self._max_snapshots :]
