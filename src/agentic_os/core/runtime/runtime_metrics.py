"""Metrics collection for runtimes — O(1) sliding-window histograms, counters, gauges."""

from __future__ import annotations

import asyncio
import math
from collections import deque

from agentic_os.core.runtime.runtime import RuntimeMetrics
from agentic_os.infrastructure.logging import get_logger

__all__ = [
    "MetricsCollector",
]

log = get_logger("runtime.metrics")

MAX_LATENCY_SAMPLES = 1000

PERCENTILES: dict[str, float] = {
    "p50": 0.50,
    "p95": 0.95,
    "p99": 0.99,
}


class MetricsCollector:
    """O(1) metrics collector with sliding-window latency histograms.

    Records counters (tokens, cost, tasks), gauges (cpu, memory, threads),
    and latency samples for percentile calculation.
    Thread-safe via asyncio.Lock.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        # latency sliding window
        self._latency_samples: deque[float] = deque(maxlen=MAX_LATENCY_SAMPLES)
        # counters
        self._tokens_used: int = 0
        self._cost: float = 0.0
        self._tasks_completed: int = 0
        # gauges (latest value)
        self._cpu_percent: float = 0.0
        self._memory_mb: float = 0.0
        self._threads: int = 0

    # ── Record methods ──────────────────────────────────────────────────────

    async def record_latency(self, ms: float) -> None:
        """Record a latency sample in milliseconds."""
        async with self._lock:
            self._latency_samples.append(ms)

    async def record_tokens(self, count: int) -> None:
        """Record token usage (increments counter)."""
        async with self._lock:
            self._tokens_used += count

    async def record_cost(self, amount: float) -> None:
        """Record cost (increments counter)."""
        async with self._lock:
            self._cost += amount

    async def record_task_completed(self) -> None:
        """Increment task-completed counter."""
        async with self._lock:
            self._tasks_completed += 1

    async def update_cpu(self, percent: float) -> None:
        """Set the current CPU usage gauge."""
        async with self._lock:
            self._cpu_percent = percent

    async def update_memory(self, mb: float) -> None:
        """Set the current memory usage gauge."""
        async with self._lock:
            self._memory_mb = mb

    async def update_threads(self, count: int) -> None:
        """Set the current thread count gauge."""
        async with self._lock:
            self._threads = count

    # ── Snapshot / histogram ────────────────────────────────────────────────

    async def snapshot(self) -> RuntimeMetrics:
        """Return a point-in-time :class:`RuntimeMetrics` snapshot.

        Latency is reported as the arithmetic mean of the sliding window.
        Use :meth:`get_histogram` for percentile distributions.
        """
        async with self._lock:
            samples = list(self._latency_samples)
            n = len(samples)
            avg_latency = sum(samples) / n if n > 0 else 0.0
            return RuntimeMetrics(
                cpu_percent=self._cpu_percent,
                memory_mb=self._memory_mb,
                threads=self._threads,
                tokens_used=self._tokens_used,
                cost=self._cost,
                latency_ms=avg_latency,
                active_tasks=self._tasks_completed,
            )

    async def get_histogram(self) -> dict[str, float]:
        """Return percentile latencies as ``{"p50": …, "p95": …, "p99": …}``.

        Returns 0.0 for all percentiles when no samples have been collected.
        """
        async with self._lock:
            samples = sorted(self._latency_samples)
            n = len(samples)

        if n == 0:
            return {label: 0.0 for label in PERCENTILES}

        result: dict[str, float] = {}
        for label, q in PERCENTILES.items():
            idx = max(0, min(n - 1, int(math.ceil(q * n) - 1)))
            result[label] = samples[idx]
        return result

    async def reset(self) -> None:
        """Reset all counters, gauges, and latency samples."""
        async with self._lock:
            self._latency_samples.clear()
            self._tokens_used = 0
            self._cost = 0.0
            self._tasks_completed = 0
            self._cpu_percent = 0.0
            self._memory_mb = 0.0
            self._threads = 0
