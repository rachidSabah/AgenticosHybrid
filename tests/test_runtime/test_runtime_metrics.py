"""Tests for MetricsCollector — sliding window, percentiles, counters, gauges."""

import pytest

from agentic_os.core.runtime.runtime_metrics import MetricsCollector


@pytest.fixture
async def collector() -> MetricsCollector:
    return MetricsCollector()


@pytest.mark.asyncio
class TestMetricsCollector:
    async def test_initial_snapshot(self, collector: MetricsCollector) -> None:
        snap = await collector.snapshot()
        assert snap.cpu_percent == 0.0
        assert snap.memory_mb == 0.0
        assert snap.threads == 0
        assert snap.tokens_used == 0
        assert snap.cost == 0.0
        assert snap.latency_ms == 0.0

    async def test_record_latency(self, collector: MetricsCollector) -> None:
        await collector.record_latency(100.0)
        await collector.record_latency(200.0)
        snap = await collector.snapshot()
        assert snap.latency_ms == 150.0  # average

    async def test_record_latency_single(self, collector: MetricsCollector) -> None:
        await collector.record_latency(42.0)
        snap = await collector.snapshot()
        assert snap.latency_ms == 42.0

    async def test_record_tokens(self, collector: MetricsCollector) -> None:
        await collector.record_tokens(500)
        await collector.record_tokens(300)
        snap = await collector.snapshot()
        assert snap.tokens_used == 800

    async def test_record_cost(self, collector: MetricsCollector) -> None:
        await collector.record_cost(0.05)
        await collector.record_cost(0.03)
        snap = await collector.snapshot()
        assert snap.cost == 0.08

    async def test_record_task_completed(self, collector: MetricsCollector) -> None:
        await collector.record_task_completed()
        await collector.record_task_completed()
        await collector.record_task_completed()
        snap = await collector.snapshot()
        assert snap.active_tasks == 3

    async def test_update_cpu(self, collector: MetricsCollector) -> None:
        await collector.update_cpu(75.5)
        snap = await collector.snapshot()
        assert snap.cpu_percent == 75.5

    async def test_update_memory(self, collector: MetricsCollector) -> None:
        await collector.update_memory(512.0)
        snap = await collector.snapshot()
        assert snap.memory_mb == 512.0

    async def test_update_threads(self, collector: MetricsCollector) -> None:
        await collector.update_threads(8)
        snap = await collector.snapshot()
        assert snap.threads == 8

    async def test_get_histogram_empty(self, collector: MetricsCollector) -> None:
        hist = await collector.get_histogram()
        assert hist == {"p50": 0.0, "p95": 0.0, "p99": 0.0}

    async def test_get_histogram_with_samples(self, collector: MetricsCollector) -> None:
        for ms in range(1, 101):
            await collector.record_latency(float(ms))
        hist = await collector.get_histogram()
        assert hist["p50"] >= 49.0  # approximate
        assert hist["p95"] >= 94.0
        assert hist["p99"] >= 98.0

    async def test_get_histogram_single_sample(self, collector: MetricsCollector) -> None:
        await collector.record_latency(55.0)
        hist = await collector.get_histogram()
        assert hist["p50"] == 55.0
        assert hist["p95"] == 55.0
        assert hist["p99"] == 55.0

    async def test_reset(self, collector: MetricsCollector) -> None:
        await collector.record_latency(100.0)
        await collector.record_tokens(500)
        await collector.update_cpu(80.0)
        await collector.reset()
        snap = await collector.snapshot()
        assert snap.latency_ms == 0.0
        assert snap.tokens_used == 0
        assert snap.cpu_percent == 0.0

    async def test_sliding_window_max_size(self, collector: MetricsCollector) -> None:
        # Add more than max samples (1000) and verify it doesn't blow up
        for i in range(1100):
            await collector.record_latency(float(i))
        snap = await collector.snapshot()
        assert snap.latency_ms > 0

    async def test_concurrent_recordings(self, collector: MetricsCollector) -> None:
        import asyncio

        async def record(i: int) -> None:
            await collector.record_latency(float(i))
            await collector.record_tokens(1)

        await asyncio.gather(*[record(i) for i in range(50)])
        snap = await collector.snapshot()
        assert snap.tokens_used == 50
        assert snap.latency_ms > 0

    async def test_counter_operations_independent(self, collector: MetricsCollector) -> None:
        await collector.record_tokens(100)
        await collector.record_cost(1.0)
        snap = await collector.snapshot()
        assert snap.tokens_used == 100
        assert snap.cost == 1.0
        assert snap.active_tasks == 0  # not touched

    async def test_gauge_overwrite(self, collector: MetricsCollector) -> None:
        await collector.update_cpu(50.0)
        await collector.update_cpu(80.0)
        snap = await collector.snapshot()
        assert snap.cpu_percent == 80.0  # last write wins
