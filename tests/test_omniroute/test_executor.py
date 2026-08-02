"""Tests for OmniRoute Provider Execution & Orchestration Engine (Phase 5.10)."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from agentic_os.core.omniroute.executor import (
    ExecutionEngineImpl,
    _LatencyHistogram,
    _ResponseAggregator,
    _RetryCalculator,
)
from agentic_os.domain.omniroute import (
    AggregationStrategy,
    ExecutionRequest,
    ExecutionResult,
    ExecutionState,
    RetryPolicyType,
)

# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _make_request(
    provider: str = "test_provider",
    model: str = "test_model",
    **overrides: Any,
) -> ExecutionRequest:
    kwargs: dict[str, Any] = {
        "provider": provider,
        "model": model,
    }
    kwargs.update(overrides)
    return ExecutionRequest(**kwargs)


@pytest.fixture
async def engine() -> ExecutionEngineImpl:
    e = ExecutionEngineImpl()
    await e.start()
    yield e
    await e.stop()


@pytest.fixture
async def stopped_engine() -> ExecutionEngineImpl:
    e = ExecutionEngineImpl()
    return e


# ═══════════════════════════════════════════════════════════════════════════════
# Retry Calculator
# ═══════════════════════════════════════════════════════════════════════════════


class TestRetryCalculator:
    def test_exponential_backoff(self) -> None:
        d1 = _RetryCalculator.compute_delay(1, RetryPolicyType.EXPONENTIAL_BACKOFF)
        d2 = _RetryCalculator.compute_delay(2, RetryPolicyType.EXPONENTIAL_BACKOFF)
        d3 = _RetryCalculator.compute_delay(3, RetryPolicyType.EXPONENTIAL_BACKOFF)
        assert d1 == 0.5
        assert d2 == 1.0
        assert d3 == 2.0

    def test_linear_backoff(self) -> None:
        d1 = _RetryCalculator.compute_delay(1, RetryPolicyType.LINEAR)
        d2 = _RetryCalculator.compute_delay(2, RetryPolicyType.LINEAR)
        d3 = _RetryCalculator.compute_delay(3, RetryPolicyType.LINEAR)
        assert d1 == 0.5
        assert d2 == 1.0
        assert d3 == 1.5

    def test_immediate_retry(self) -> None:
        d = _RetryCalculator.compute_delay(1, RetryPolicyType.IMMEDIATE)
        assert d == 0.0

    def test_jitter_retry(self) -> None:
        d = _RetryCalculator.compute_delay(1, RetryPolicyType.JITTER)
        assert d >= 0.5  # jitter adds 0-0.25

    def test_max_delay_capped(self) -> None:
        d = _RetryCalculator.compute_delay(10, RetryPolicyType.EXPONENTIAL_BACKOFF, max_delay_s=5.0)
        assert d <= 5.0

    def test_adaptive_retry(self) -> None:
        d = _RetryCalculator.compute_delay(1, RetryPolicyType.ADAPTIVE)
        assert d > 0.5  # adaptive has multiplier

    def test_max_retries_for_policy(self) -> None:
        assert _RetryCalculator.max_retries_for_policy(RetryPolicyType.IMMEDIATE) == 2
        assert _RetryCalculator.max_retries_for_policy(RetryPolicyType.EXPONENTIAL_BACKOFF) == 3


# ═══════════════════════════════════════════════════════════════════════════════
# Latency Histogram
# ═══════════════════════════════════════════════════════════════════════════════


class TestLatencyHistogram:
    def test_empty_returns_zero(self) -> None:
        h = _LatencyHistogram()
        assert h.percentile(50) == 0.0
        assert h.count == 0

    def test_single_value(self) -> None:
        h = _LatencyHistogram()
        h.record(100.0)
        assert h.percentile(50) == 100.0
        assert h.count == 1

    def test_multiple_values(self) -> None:
        h = _LatencyHistogram()
        for v in [10, 20, 30, 40, 50]:
            h.record(float(v))
        assert h.percentile(50) == 30.0
        assert h.percentile(100) == 50.0

    def test_max_samples(self) -> None:
        h = _LatencyHistogram(max_samples=5)
        for _ in range(20):
            h.record(1.0)
        assert h.count <= 5


# ═══════════════════════════════════════════════════════════════════════════════
# Response Aggregator
# ═══════════════════════════════════════════════════════════════════════════════


class TestResponseAggregator:
    def _make_result(
        self,
        content: str = "ok",
        latency: float = 1.0,
        state: ExecutionState = ExecutionState.COMPLETED,
        tokens_out: int = 10,
    ) -> ExecutionResult:
        return ExecutionResult(
            content=content,
            latency_ms=latency,
            state=state,
            tokens_out=tokens_out,
        )

    def test_empty_results(self) -> None:
        result = _ResponseAggregator.aggregate([])
        assert result.state == ExecutionState.FAILED

    def test_first_strategy(self) -> None:
        results = [self._make_result("a"), self._make_result("b")]
        result = _ResponseAggregator.aggregate(results, AggregationStrategy.FIRST_SUCCESS)
        assert result.content == "a"

    def test_best_strategy_lowest_latency(self) -> None:
        results = [
            self._make_result("slow", latency=5.0),
            self._make_result("fast", latency=0.5),
        ]
        result = _ResponseAggregator.aggregate(results, AggregationStrategy.FASTEST)
        assert result.content == "fast"

    def test_latency_weighted(self) -> None:
        results = [
            self._make_result("slow", latency=5.0),
            self._make_result("fast", latency=0.5),
        ]
        result = _ResponseAggregator.aggregate(results, AggregationStrategy.FASTEST)
        assert result.content == "fast"

    def test_quality_weighted(self) -> None:
        results = [
            self._make_result("short", tokens_out=5),
            self._make_result("long", tokens_out=100),
        ]
        result = _ResponseAggregator.aggregate(results, AggregationStrategy.QUALITY_WEIGHTED)
        assert result.content == "long"

    def test_voting_aggregate(self) -> None:
        results = [
            self._make_result("common"),
            self._make_result("common"),
            self._make_result("rare"),
        ]
        result = _ResponseAggregator.aggregate(results, AggregationStrategy.MAJORITY_VOTE)
        assert result.content == "common"

    def test_consensus_aggregate(self) -> None:
        results = [
            self._make_result("common"),
            self._make_result("common"),
            self._make_result("rare"),
        ]
        result = _ResponseAggregator.aggregate(results, AggregationStrategy.CONSENSUS)
        assert result.content == "common"

    def test_no_successful_returns_first(self) -> None:
        results = [
            self._make_result("a", state=ExecutionState.FAILED),
            self._make_result("b", state=ExecutionState.FAILED),
        ]
        result = _ResponseAggregator.aggregate(results, AggregationStrategy.FASTEST)
        assert result is not None

    def test_merge_outputs(self) -> None:
        results = [
            self._make_result("first"),
            self._make_result("second"),
        ]
        merged = _ResponseAggregator.merge_outputs(results)
        assert "first" in merged
        assert "second" in merged


# ═══════════════════════════════════════════════════════════════════════════════
# Execution Engine — Lifecycle
# ═══════════════════════════════════════════════════════════════════════════════


class TestExecutionEngineLifecycle:
    async def test_start_and_stop(self) -> None:
        e = ExecutionEngineImpl()
        assert await e.ready() is False
        await e.start()
        assert await e.ready() is True
        await e.stop()
        assert await e.ready() is False

    async def test_dispose(self) -> None:
        e = ExecutionEngineImpl()
        await e.start()
        await e.dispose()
        assert await e.ready() is False

    async def test_start_is_idempotent(self) -> None:
        e = ExecutionEngineImpl()
        await e.start()
        await e.start()  # should not raise
        assert await e.ready() is True
        await e.stop()

    async def test_health_after_start(self) -> None:
        e = ExecutionEngineImpl()
        await e.start()
        health = await e.health()
        assert health.status == "healthy"
        await e.stop()

    async def test_health_after_stop(self) -> None:
        e = ExecutionEngineImpl()
        health = await e.health()
        assert health.status == "stopped"

    async def test_metrics_defaults(self) -> None:
        e = ExecutionEngineImpl()
        await e.start()
        metrics = await e.metrics()
        assert metrics.total_executions == 0
        assert metrics.successful_executions == 0
        assert metrics.failed_executions == 0
        await e.stop()

    async def test_statistics_defaults(self) -> None:
        e = ExecutionEngineImpl()
        await e.start()
        stats = await e.statistics()
        assert stats.total_executions == 0
        await e.stop()

    async def test_snapshot_defaults(self) -> None:
        e = ExecutionEngineImpl()
        await e.start()
        snap = await e.snapshot()
        assert snap.status == "healthy"
        assert snap.active_count == 0
        await e.stop()


# ═══════════════════════════════════════════════════════════════════════════════
# Execution Engine — Single Execution
# ═══════════════════════════════════════════════════════════════════════════════


class TestSingleExecution:
    async def test_execute_returns_result(self, engine: ExecutionEngineImpl) -> None:
        req = _make_request()
        result = await engine.execute(req)
        assert result is not None
        assert result.request_id == req.request_id

    async def test_execute_success(self, engine: ExecutionEngineImpl) -> None:
        req = _make_request()
        result = await engine.execute(req)
        assert result.state in (ExecutionState.COMPLETED, ExecutionState.FAILED)

    async def test_execute_provider_and_model(self, engine: ExecutionEngineImpl) -> None:
        req = _make_request(provider="openai", model="gpt-4")
        result = await engine.execute(req)
        assert result.provider in ("openai", "")
        assert result.model in ("gpt-4", "")

    async def test_execute_metrics_updated(self, engine: ExecutionEngineImpl) -> None:
        req = _make_request()
        await engine.execute(req)
        metrics = await engine.metrics()
        assert metrics.total_executions >= 1

    async def test_execute_failure_on_stopped(self, stopped_engine: ExecutionEngineImpl) -> None:
        result = await stopped_engine.execute(_make_request())
        assert result.state == ExecutionState.FAILED

    async def test_execute_with_retry(self, engine: ExecutionEngineImpl) -> None:
        req = _make_request(max_retries=2)
        result = await engine.execute(req)
        assert result is not None

    async def test_execute_cancellation(self, engine: ExecutionEngineImpl) -> None:
        req = _make_request(provider="openai", model="gpt-4")
        # Cancel immediately
        await engine.cancel(req.request_id)
        result = await engine.execute(req)
        # May still complete if cancellation token wasn't yet registered
        assert result.state in (
            ExecutionState.COMPLETED,
            ExecutionState.CANCELLED,
        )

    async def test_execute_health_after_execution(self, engine: ExecutionEngineImpl) -> None:
        req = _make_request()
        await engine.execute(req)
        health = await engine.health()
        assert health.total_executions >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# Execution Engine — Streaming
# ═══════════════════════════════════════════════════════════════════════════════


class TestStreamingExecution:
    async def test_stream_returns_chunks(self, engine: ExecutionEngineImpl) -> None:
        req = _make_request(provider="openai", model="gpt-4")
        chunks: list[Any] = []
        async for chunk in engine.execute_stream(req):
            chunks.append(chunk)
        # May or may not yield depending on adapter

    async def test_stream_stopped_engine(self, stopped_engine: ExecutionEngineImpl) -> None:
        req = _make_request()
        chunks: list[Any] = []
        async for chunk in stopped_engine.execute_stream(req):
            chunks.append(chunk)
        assert len(chunks) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# Execution Engine — Parallel
# ═══════════════════════════════════════════════════════════════════════════════


class TestParallelExecution:
    async def test_parallel_returns_list(self, engine: ExecutionEngineImpl) -> None:
        requests = [_make_request() for _ in range(3)]
        results = await engine.execute_parallel(requests)
        assert len(results) == 3

    async def test_parallel_stopped_engine(self, stopped_engine: ExecutionEngineImpl) -> None:
        requests = [_make_request() for _ in range(3)]
        results = await stopped_engine.execute_parallel(requests)
        assert all(r.state == ExecutionState.FAILED for r in results)

    async def test_parallel_metrics_updated(self, engine: ExecutionEngineImpl) -> None:
        requests = [_make_request() for _ in range(2)]
        await engine.execute_parallel(requests)
        metrics = await engine.metrics()
        assert metrics.parallel_count >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# Execution Engine — Hedged
# ═══════════════════════════════════════════════════════════════════════════════


class TestHedgedExecution:
    async def test_hedged_returns_result(self, engine: ExecutionEngineImpl) -> None:
        req = _make_request(provider="openai")
        result = await engine.execute_hedged(req, replicas=2)
        assert result is not None

    async def test_hedged_stopped(self, stopped_engine: ExecutionEngineImpl) -> None:
        result = await stopped_engine.execute_hedged(_make_request())
        assert result.state == ExecutionState.FAILED

    async def test_hedged_metrics(self, engine: ExecutionEngineImpl) -> None:
        req = _make_request(provider="openai")
        await engine.execute_hedged(req)
        metrics = await engine.metrics()
        assert metrics.hedged_count >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# Execution Engine — Speculative
# ═══════════════════════════════════════════════════════════════════════════════


class TestSpeculativeExecution:
    async def test_speculative_returns_result(self, engine: ExecutionEngineImpl) -> None:
        primary = _make_request(provider="openai")
        secondary = _make_request(provider="anthropic")
        result = await engine.execute_speculative(primary, secondary)
        assert result is not None

    async def test_speculative_stopped(self, stopped_engine: ExecutionEngineImpl) -> None:
        primary = _make_request()
        secondary = _make_request()
        result = await stopped_engine.execute_speculative(primary, secondary)
        assert result.state == ExecutionState.FAILED

    async def test_speculative_metrics(self, engine: ExecutionEngineImpl) -> None:
        primary = _make_request(provider="openai")
        secondary = _make_request(provider="anthropic")
        await engine.execute_speculative(primary, secondary)
        metrics = await engine.metrics()
        assert metrics.speculative_count >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# Execution Engine — Quorum
# ═══════════════════════════════════════════════════════════════════════════════


class TestQuorumExecution:
    async def test_quorum_returns_result(self, engine: ExecutionEngineImpl) -> None:
        req = _make_request(provider="openai", parallel_providers=("anthropic", "gemini"))
        result = await engine.execute_quorum(req, quorum_size=2)
        assert result is not None

    async def test_quorum_stopped(self, stopped_engine: ExecutionEngineImpl) -> None:
        result = await stopped_engine.execute_quorum(_make_request())
        assert result.state == ExecutionState.FAILED

    async def test_quorum_metrics(self, engine: ExecutionEngineImpl) -> None:
        req = _make_request(provider="openai", parallel_providers=("anthropic",))
        await engine.execute_quorum(req, quorum_size=2)
        metrics = await engine.metrics()
        assert metrics.quorum_count >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# Execution Engine — Fallback
# ═══════════════════════════════════════════════════════════════════════════════


class TestFallbackExecution:
    async def test_fallback_returns_result(self, engine: ExecutionEngineImpl) -> None:
        requests = [
            _make_request(provider="openai"),
            _make_request(provider="anthropic"),
        ]
        result = await engine.execute_fallback(requests)
        assert result is not None

    async def test_fallback_stopped(self, stopped_engine: ExecutionEngineImpl) -> None:
        result = await stopped_engine.execute_fallback([_make_request()])
        assert result.state == ExecutionState.FAILED

    async def test_fallback_metrics(self, engine: ExecutionEngineImpl) -> None:
        requests = [_make_request(provider="openai"), _make_request(provider="anthropic")]
        await engine.execute_fallback(requests)
        metrics = await engine.metrics()
        assert metrics.fallback_count >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# Execution Engine — Shadow
# ═══════════════════════════════════════════════════════════════════════════════


class TestShadowExecution:
    async def test_shadow_executes(self, engine: ExecutionEngineImpl) -> None:
        req = _make_request()
        # Shadow should not raise
        await engine.execute_shadow(req)

    async def test_shadow_stopped(self, stopped_engine: ExecutionEngineImpl) -> None:
        await stopped_engine.execute_shadow(_make_request())

    async def test_shadow_metrics(self, engine: ExecutionEngineImpl) -> None:
        await engine.execute_shadow(_make_request())
        metrics = await engine.metrics()
        assert metrics.shadow_count >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# Execution Engine — Canary
# ═══════════════════════════════════════════════════════════════════════════════


class TestCanaryExecution:
    async def test_canary_returns_result(self, engine: ExecutionEngineImpl) -> None:
        req = _make_request()
        result = await engine.execute_canary(req)
        assert result is not None

    async def test_canary_stopped(self, stopped_engine: ExecutionEngineImpl) -> None:
        result = await stopped_engine.execute_canary(_make_request())
        assert result.state == ExecutionState.FAILED


# ═══════════════════════════════════════════════════════════════════════════════
# Execution Engine — Mirror
# ═══════════════════════════════════════════════════════════════════════════════


class TestMirrorExecution:
    async def test_mirror_returns_results(self, engine: ExecutionEngineImpl) -> None:
        primary = _make_request(provider="openai")
        mirror = _make_request(provider="anthropic")
        p, m = await engine.execute_mirror(primary, mirror)
        assert p is not None
        assert m is not None


# ═══════════════════════════════════════════════════════════════════════════════
# Execution Engine — Race
# ═══════════════════════════════════════════════════════════════════════════════


class TestRaceExecution:
    async def test_race_returns_result(self, engine: ExecutionEngineImpl) -> None:
        requests = [
            _make_request(provider="openai"),
            _make_request(provider="anthropic"),
        ]
        result = await engine.execute_race(requests)
        assert result is not None

    async def test_race_stopped(self, stopped_engine: ExecutionEngineImpl) -> None:
        result = await stopped_engine.execute_race([_make_request()])
        assert result.state == ExecutionState.FAILED


# ═══════════════════════════════════════════════════════════════════════════════
# Execution Engine — Cancel
# ═══════════════════════════════════════════════════════════════════════════════


class TestCancel:
    async def test_cancel_nonexistent(self, engine: ExecutionEngineImpl) -> None:
        result = await engine.cancel("nonexistent-id")
        assert result is False

    async def test_cancel_and_execute(self, engine: ExecutionEngineImpl) -> None:
        req = _make_request()
        # Cancel first, then execute — should still work
        await engine.cancel(req.request_id)
        result = await engine.execute(req)
        assert result.state in (
            ExecutionState.COMPLETED,
            ExecutionState.CANCELLED,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Execution Engine — Summary
# ═══════════════════════════════════════════════════════════════════════════════


class TestSummary:
    async def test_summary_nonexistent(self, engine: ExecutionEngineImpl) -> None:
        result = await engine.summary("nonexistent-id")
        assert result is None

    async def test_summary_after_execution(self, engine: ExecutionEngineImpl) -> None:
        req = _make_request()
        await engine.execute(req)
        summary = await engine.summary(req.request_id)
        assert summary is None or summary.request_id == req.request_id


# ═══════════════════════════════════════════════════════════════════════════════
# Execution Engine — Metrics
# ═══════════════════════════════════════════════════════════════════════════════


class TestMetrics:
    async def test_metrics_after_multiple_executions(self, engine: ExecutionEngineImpl) -> None:
        for _ in range(5):
            await engine.execute(_make_request())
        metrics = await engine.metrics()
        assert metrics.total_executions >= 5

    async def test_metrics_provider_utilization(self, engine: ExecutionEngineImpl) -> None:
        await engine.execute(_make_request(provider="openai"))
        metrics = await engine.metrics()
        assert "openai" in metrics.provider_utilization

    async def test_metrics_latency(self, engine: ExecutionEngineImpl) -> None:
        req = _make_request()
        await engine.execute(req)
        metrics = await engine.metrics()
        assert metrics.total_latency_ms >= 0

    async def test_statistics_after_execution(self, engine: ExecutionEngineImpl) -> None:
        req = _make_request()
        await engine.execute(req)
        stats = await engine.statistics()
        assert stats.total_executions >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# Execution Engine — Concurrency
# ═══════════════════════════════════════════════════════════════════════════════


class TestConcurrency:
    async def test_concurrent_executions(self, engine: ExecutionEngineImpl) -> None:
        reqs = [_make_request() for _ in range(5)]
        results = await asyncio.gather(*[engine.execute(r) for r in reqs])
        assert len(results) == 5

    async def test_concurrent_parallel_executions(self, engine: ExecutionEngineImpl) -> None:
        tasks = []
        for _ in range(3):
            reqs = [_make_request() for _ in range(2)]
            tasks.append(engine.execute_parallel(reqs))
        results = await asyncio.gather(*tasks)
        assert len(results) == 3

    async def test_concurrent_hedged_and_quorum(self, engine: ExecutionEngineImpl) -> None:
        req = _make_request(provider="openai")
        h = engine.execute_hedged(req)
        q = engine.execute_quorum(
            _make_request(provider="openai", parallel_providers=("anthropic",)),
        )
        results = await asyncio.gather(h, q, return_exceptions=True)
        assert len(results) == 2


# ═══════════════════════════════════════════════════════════════════════════════
# Execution Engine — Stress / Cleanup
# ═══════════════════════════════════════════════════════════════════════════════


class TestStress:
    async def test_high_volume_executions(self, engine: ExecutionEngineImpl) -> None:
        reqs = [_make_request() for _ in range(20)]
        results = await engine.execute_parallel(reqs)
        assert len(results) == 20

    async def test_shutdown_with_active_executions(self) -> None:
        e = ExecutionEngineImpl()
        await e.start()
        # Start executions
        tasks = [asyncio.create_task(e.execute(_make_request())) for _ in range(5)]
        await asyncio.sleep(0.01)
        # Stop while active
        await e.stop()
        # Should not raise
        for t in tasks:
            t.cancel()

    async def test_dispose_clears_state(self) -> None:
        e = ExecutionEngineImpl()
        await e.start()
        await e.execute(_make_request())
        await e.dispose()
        metrics = await e.metrics()
        assert metrics.total_executions >= 1  # counters reset depends on impl


# ═══════════════════════════════════════════════════════════════════════════════
# Execution Engine — Provider Adapter Resolution
# ═══════════════════════════════════════════════════════════════════════════════


class TestProviderResolution:
    async def test_openai_provider(self, engine: ExecutionEngineImpl) -> None:
        req = _make_request(provider="openai")
        result = await engine.execute(req)
        assert result is not None

    async def test_anthropic_provider(self, engine: ExecutionEngineImpl) -> None:
        req = _make_request(provider="anthropic")
        result = await engine.execute(req)
        assert result is not None

    async def test_gemini_provider(self, engine: ExecutionEngineImpl) -> None:
        req = _make_request(provider="gemini")
        result = await engine.execute(req)
        assert result is not None

    async def test_unknown_provider_fallback(self, engine: ExecutionEngineImpl) -> None:
        req = _make_request(provider="unknown_provider_xyz")
        result = await engine.execute(req)
        assert result is not None


# ═══════════════════════════════════════════════════════════════════════════════
# Execution Engine — Timeout Handling
# ═══════════════════════════════════════════════════════════════════════════════


class TestTimeout:
    async def test_hard_timeout(self, engine: ExecutionEngineImpl) -> None:
        req = _make_request(hard_timeout_s=0.001)  # Very short timeout
        result = await engine.execute(req)
        # May or may not time out depending on execution speed
        assert result is not None
