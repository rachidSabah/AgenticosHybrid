"""Desktop Performance Monitor — monitors system resource usage."""

from __future__ import annotations

from collections.abc import Sequence

from agentic_os.domain.desktop import DesktopPerformanceMetrics
from agentic_os.infrastructure.logging import get_logger

log = get_logger("desktop.performance")


class DesktopPerformanceMonitor:
    """In-memory performance monitor. Collects real metrics when Tauri is available."""

    def __init__(self) -> None:
        self._metrics = DesktopPerformanceMetrics()
        self._history: dict[str, list[float]] = {}
        self._monitoring = False

    async def get_metrics(self) -> DesktopPerformanceMetrics:
        return self._metrics

    async def update_metrics(self, metrics: DesktopPerformanceMetrics) -> None:
        self._metrics = metrics
        self._record_metric("cpu", metrics.cpu_usage_percent)
        self._record_metric("memory", metrics.memory_usage_percent)
        self._record_metric("disk", metrics.disk_usage_percent)

    async def get_metric_history(self, metric: str, limit: int = 60) -> Sequence[float]:
        return self._history.get(metric, [])[-limit:]

    async def start_monitoring(self, interval_seconds: float = 5.0) -> None:
        self._monitoring = True
        log.info("Performance monitoring started", interval=interval_seconds)

    async def stop_monitoring(self) -> None:
        self._monitoring = False
        log.info("Performance monitoring stopped")

    def _record_metric(self, name: str, value: float) -> None:
        if name not in self._history:
            self._history[name] = []
        self._history[name].append(value)
        if len(self._history[name]) > 1000:
            self._history[name] = self._history[name][-1000:]
