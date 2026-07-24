"""Tests for OmniRoute Circuit Breaker Engine (Phase 5.5).

Targets: 100+ tests covering state transitions, failure tracking, recovery,
half-open probes, Router integration, EventBus, concurrency, and edge cases.
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import ANY, AsyncMock, MagicMock

import pytest

from agentic_os.core.omniroute.failover import (
    CircuitBreakerEngineImpl,
    _ProviderState,
    _SlidingWindow,
)
from agentic_os.core.omniroute.router import RouterEngineImpl
from agentic_os.domain.events import Topic
from agentic_os.domain.omniroute import (
    CircuitBreakerConfig,
    FailoverState,
    RoutingRequest,
)

# ══════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════


@pytest.fixture
async def engine():
    cb = CircuitBreakerEngineImpl()
    await cb.start()
    yield cb
    await cb.dispose()


@pytest.fixture
async def engine_with_bus():
    bus = AsyncMock()
    bus.publish = AsyncMock()
    cb = CircuitBreakerEngineImpl(event_bus=bus)
    await cb.start()
    yield cb, bus
    await cb.dispose()


@pytest.fixture
async def started_engine():
    cb = CircuitBreakerEngineImpl()
    cb._started = True
    cb._start_time = time.monotonic()
    yield cb
    await cb.dispose()


@pytest.fixture
def fast_config():
    return CircuitBreakerConfig(
        failure_threshold=3,
        minimum_request_count=2,
        recovery_timeout_seconds=0.05,
        half_open_probe_count=1,
        sliding_window_size=5,
    )


@pytest.fixture
async def fast_engine(fast_config):
    cb = CircuitBreakerEngineImpl(global_config=fast_config)
    await cb.start()
    yield cb
    await cb.dispose()


# ══════════════════════════════════════════════
# Lifecycle tests
# ══════════════════════════════════════════════


class TestLifecycle:
    """Circuit breaker lifecycle: initialize, start, stop, dispose, health, ready."""

    async def test_initialize(self):
        cb = CircuitBreakerEngineImpl()
        await cb.initialize()
        assert cb._started is False
        await cb.dispose()

    async def test_start(self):
        cb = CircuitBreakerEngineImpl()
        await cb.start()
        assert cb._started is True
        assert cb._start_time > 0
        await cb.dispose()

    async def test_stop(self):
        cb = CircuitBreakerEngineImpl()
        await cb.start()
        await cb.stop()
        assert cb._started is False
        await cb.dispose()

    async def test_dispose_clears_state(self, started_engine):
        await started_engine.record_failure("p1")
        await started_engine.dispose()
        assert len(started_engine._providers) == 0

    async def test_health(self, engine):
        h = await engine.health()
        assert h["status"] == "healthy"
        assert h["started"] is True
        assert h["tracked_providers"] >= 0

    async def test_health_after_stop(self, engine):
        await engine.stop()
        h = await engine.health()
        assert h["status"] == "stopped"

    async def test_ready(self, engine):
        assert await engine.ready() is True

    async def test_ready_after_stop(self, engine):
        await engine.stop()
        assert await engine.ready() is False

    async def test_metadata(self, engine):
        m = await engine.metadata()
        assert m["type"] == "CircuitBreakerEngineImpl"
        assert m["started"] is True
        assert "global_config" in m

    async def test_capabilities(self, engine):
        caps = await engine.capabilities()
        names = [c["name"] for c in caps]
        assert "circuit_breaker_state_machine" in names
        assert "failure_tracking" in names


# ══════════════════════════════════════════════
# _SlidingWindow tests
# ══════════════════════════════════════════════


class TestSlidingWindow:
    def test_initially_empty(self):
        sw = _SlidingWindow(5)
        assert sw.total == 0

    def test_add_increases_count(self):
        sw = _SlidingWindow(5)
        sw.add(1.0)
        assert sw.total == 1

    def test_max_size_enforced(self):
        sw = _SlidingWindow(3)
        for i in range(5):
            sw.add(float(i))
        assert sw.total == 3

    def test_full_flag(self):
        sw = _SlidingWindow(2)
        assert sw.full is False
        sw.add(1.0)
        assert sw.full is False
        sw.add(2.0)
        assert sw.full is True

    def test_clear(self):
        sw = _SlidingWindow(3)
        sw.add(1.0)
        sw.add(2.0)
        sw.clear()
        assert sw.total == 0

    def test_count_in_window(self):
        sw = _SlidingWindow(10)
        now = time.monotonic()
        sw.add(now)
        sw.add(now - 10)  # 10 seconds ago
        # Both are within a 60-second window from now
        assert sw.count_in_window(60.0) >= 1


# ══════════════════════════════════════════════
# _ProviderState tests
# ══════════════════════════════════════════════


class TestProviderState:
    def test_defaults(self):
        ps = _ProviderState(provider="test")
        assert ps.provider == "test"
        assert ps.state == FailoverState.CLOSED
        assert ps.failure_count == 0
        assert ps.success_count == 0

    def test_failure_rate_zero_when_no_requests(self):
        ps = _ProviderState(provider="test")
        assert ps.failure_rate == 0.0

    def test_failure_rate(self):
        ps = _ProviderState(provider="test")
        ps.failure_count = 3
        ps.success_count = 7
        assert ps.failure_rate == 0.3

    def test_average_latency_zero_when_no_samples(self):
        ps = _ProviderState(provider="test")
        assert ps.average_latency_ms == 0.0

    def test_average_latency(self):
        ps = _ProviderState(provider="test")
        ps.total_latency_ms = 150.0
        ps.latency_sample_count = 3
        assert ps.average_latency_ms == 50.0

    def test_should_trip_false_below_min_requests(self):
        ps = _ProviderState(provider="test")
        ps.total_requests = 1
        ps.config = CircuitBreakerConfig(minimum_request_count=3)
        assert ps.should_trip() is False

    def test_should_trip_true_after_consecutive_failures(self):
        ps = _ProviderState(provider="test")
        ps.total_requests = 10
        ps.consecutive_failures = 5
        ps.config = CircuitBreakerConfig(failure_threshold=3, minimum_request_count=2)
        assert ps.should_trip() is True

    def test_snapshot(self):
        ps = _ProviderState(provider="p1")
        ps.success_count = 5
        ps.failure_count = 2
        snap = ps.snapshot()
        assert snap.provider == "p1"
        assert snap.success_count == 5
        assert snap.failure_count == 2

    def test_metric_snapshot(self):
        ps = _ProviderState(provider="p1")
        ps.timeout_count = 3
        ps.http_failure_count = 2
        metrics = ps.metric_snapshot()
        assert metrics.timeout_count == 3
        assert metrics.http_failures == 2

    def test_uptime_ratio(self):
        ps = _ProviderState(provider="test")
        ps.first_seen = time.monotonic()
        ps.total_time_spent_open = 1.0
        # Recently started, negligible elapsed
        ratio = ps.uptime_ratio
        assert 0.0 <= ratio <= 1.0


# ══════════════════════════════════════════════
# State transition tests
# ══════════════════════════════════════════════


class TestStateTransitions:
    """CLOSED → OPEN → HALF_OPEN → CLOSED / back to OPEN."""

    async def test_initial_state_is_closed(self, engine):
        await engine.record_success("p1")
        state = await engine.provider_state("p1")
        assert state.state == FailoverState.CLOSED

    async def test_closed_to_open_after_failure_threshold(self, fast_engine):
        for _ in range(4):
            await fast_engine.record_failure("p1")
        state = await fast_engine.provider_state("p1")
        assert state.state == FailoverState.CIRCUIT_OPEN

    async def test_closed_stays_closed_below_threshold(self, engine):
        for _ in range(2):
            await engine.record_failure("p1")
        state = await engine.provider_state("p1")
        assert state.state == FailoverState.CLOSED

    async def test_open_to_half_open_after_recovery_timeout(self, fast_engine):
        # Trip the circuit
        for _ in range(4):
            await fast_engine.record_failure("p1")
        state = await fast_engine.provider_state("p1")
        assert state.state == FailoverState.CIRCUIT_OPEN

        # Wait for recovery timeout
        await asyncio.sleep(0.06)

        # allow_request should trigger HALF_OPEN
        allowed = await fast_engine.allow_request("p1")
        assert allowed is True
        state = await fast_engine.provider_state("p1")
        assert state.state == FailoverState.CIRCUIT_HALF_OPEN

    async def test_half_open_to_closed_on_probe_success(self, fast_engine):
        # Trip the circuit
        for _ in range(4):
            await fast_engine.record_failure("p1")

        # Wait for recovery
        await asyncio.sleep(0.06)
        await fast_engine.allow_request("p1")  # moves to HALF_OPEN

        # Probe success → CLOSED (need half_open_probe_count=1 success)
        await fast_engine.record_success("p1")
        state = await fast_engine.provider_state("p1")
        assert state.state == FailoverState.CLOSED

    async def test_half_open_to_open_on_probe_failure(self, fast_engine):
        # Trip the circuit
        for _ in range(4):
            await fast_engine.record_failure("p1")

        # Wait for recovery
        await asyncio.sleep(0.06)
        await fast_engine.allow_request("p1")  # moves to HALF_OPEN

        # Probe failure → back to OPEN
        await fast_engine.record_failure("p1")
        state = await fast_engine.provider_state("p1")
        assert state.state == FailoverState.CIRCUIT_OPEN

    async def test_multiple_trip_recovery_cycles(self, fast_engine):
        for _cycle in range(3):
            # Trip
            for _ in range(4):
                await fast_engine.record_failure("p1")
            state = await fast_engine.provider_state("p1")
            assert state.state == FailoverState.CIRCUIT_OPEN, "Cycle not OPEN"

            # Wait and recover
            await asyncio.sleep(0.06)
            await fast_engine.allow_request("p1")
            await fast_engine.record_success("p1")
            state = await fast_engine.provider_state("p1")
            assert state.state == FailoverState.CLOSED, "Cycle not CLOSED"

    async def test_consecutive_failures_reset_on_success(self):
        cb = CircuitBreakerEngineImpl()
        cb._started = True

        await cb.record_failure("p1")
        await cb.record_failure("p1")

        ps = cb._providers["p1"]
        assert ps.consecutive_failures == 2

        await cb.record_success("p1")
        assert ps.consecutive_failures == 0
        await cb.dispose()

    async def test_failure_count_increments(self, engine):
        for _ in range(5):
            await engine.record_failure("p1")
        state = await engine.provider_state("p1")
        assert state.failure_count == 5

    async def test_success_count_increments(self, engine):
        for _ in range(3):
            await engine.record_success("p1")
        state = await engine.provider_state("p1")
        assert state.success_count == 3


# ══════════════════════════════════════════════
# allow_request tests
# ══════════════════════════════════════════════


class TestAllowRequest:
    async def test_allows_when_closed(self, engine):
        await engine.record_success("p1")
        assert await engine.allow_request("p1") is True

    async def test_blocks_when_open(self, fast_engine):
        for _ in range(4):
            await fast_engine.record_failure("p1")
        assert await fast_engine.allow_request("p1") is False

    async def test_allows_half_open_probe(self, fast_engine):
        for _ in range(4):
            await fast_engine.record_failure("p1")
        await asyncio.sleep(0.06)
        allowed = await fast_engine.allow_request("p1")
        assert allowed is True

    async def test_blocks_half_open_after_probes_exhausted(self, fast_engine):
        for _ in range(4):
            await fast_engine.record_failure("p1")
        await asyncio.sleep(0.06)
        # First call transitions OPEN→HALF_OPEN (allowed, free transition)
        assert await fast_engine.allow_request("p1") is True
        # Second call consumes the probe slot
        assert await fast_engine.allow_request("p1") is True
        # Third call blocked (probe exhausted)
        assert await fast_engine.allow_request("p1") is False

    async def test_allows_when_not_started(self):
        cb = CircuitBreakerEngineImpl()
        cb._started = False
        assert await cb.allow_request("p1") is True
        await cb.dispose()

    async def test_allows_unknown_provider(self, engine):
        assert await engine.allow_request("unknown") is True

    async def test_allows_after_recovery(self, fast_engine):
        for _ in range(4):
            await fast_engine.record_failure("p1")
        await asyncio.sleep(0.06)
        await fast_engine.allow_request("p1")  # → HALF_OPEN
        await fast_engine.record_success("p1")  # → CLOSED
        assert await fast_engine.allow_request("p1") is True

    async def test_alternative_path_half_open(self, fast_engine):
        """Verify half_open path directly after timeout recovery."""
        for _ in range(4):
            await fast_engine.record_failure("p1")
        await asyncio.sleep(0.06)
        # allow_request should move from OPEN to HALF_OPEN
        assert await fast_engine.allow_request("p1") is True
        state = await fast_engine.provider_state("p1")
        assert state.state == FailoverState.CIRCUIT_HALF_OPEN


# ══════════════════════════════════════════════
# Public API tests
# ══════════════════════════════════════════════


class TestPublicAPI:
    async def test_provider_state_returns_none_for_unknown(self, engine):
        state = await engine.provider_state("nonexistent")
        assert state is None

    async def test_provider_state_after_success(self, engine):
        await engine.record_success("p1")
        state = await engine.provider_state("p1")
        assert state is not None
        assert state.provider == "p1"

    async def test_reset_unknown_provider(self, engine):
        assert await engine.reset("nonexistent") is False

    async def test_reset_known_provider(self, engine):
        await engine.record_failure("p1")
        assert await engine.reset("p1") is True
        state = await engine.provider_state("p1")
        assert state.state == FailoverState.CLOSED
        assert state.failure_count == 0
        assert state.success_count == 0

    async def test_trip_unknown_provider(self, engine):
        # Now creates and trips the provider
        assert await engine.trip("nonexistent") is True

    async def test_trip_known_provider(self, engine):
        await engine.record_success("p1")
        assert await engine.trip("p1") is True
        state = await engine.provider_state("p1")
        assert state.state == FailoverState.CIRCUIT_OPEN

    async def test_half_open_unknown_provider(self, engine):
        # Now creates and sets half-open
        assert await engine.half_open("nonexistent") is True

    async def test_half_open_known_provider(self, engine):
        await engine.record_success("p1")
        assert await engine.half_open("p1") is True
        state = await engine.provider_state("p1")
        assert state.state == FailoverState.CIRCUIT_HALF_OPEN

    async def test_close_unknown_provider(self, engine):
        # Now creates and closes the provider
        assert await engine.close("nonexistent") is True

    async def test_close_known_provider(self, engine):
        await engine.trip("p1")
        assert await engine.close("p1") is True
        state = await engine.provider_state("p1")
        assert state.state == FailoverState.CLOSED

    async def test_all_states_empty_when_no_providers(self, engine):
        states = await engine.all_states()
        assert states == {}

    async def test_all_states_after_records(self, engine):
        await engine.record_success("p1")
        await engine.record_failure("p2")
        states = await engine.all_states()
        assert "p1" in states
        assert "p2" in states

    async def test_healthy_providers(self, engine):
        await engine.record_success("p1")
        assert await engine.healthy_providers() == ["p1"]

    async def test_healthy_providers_excludes_open(self, fast_engine):
        for _ in range(4):
            await fast_engine.record_failure("p1")
        healthy = await fast_engine.healthy_providers()
        assert "p1" not in healthy

    async def test_open_providers(self, fast_engine):
        for _ in range(4):
            await fast_engine.record_failure("p1")
        open_list = await fast_engine.open_providers()
        assert "p1" in open_list

    async def test_open_providers_empty_when_closed(self, engine):
        await engine.record_success("p1")
        open_list = await engine.open_providers()
        assert "p1" not in open_list

    async def test_statistics_shape(self, engine):
        await engine.record_success("p1")
        await engine.record_failure("p2")
        stats = await engine.statistics()
        assert "tracked_providers" in stats
        assert "state_distribution" in stats
        assert "total_failures" in stats
        assert "total_successes" in stats

    async def test_provider_metrics(self, engine):
        await engine.record_failure("p1", failure_type="timeout")
        metrics = await engine.provider_metrics("p1")
        assert metrics is not None
        assert metrics.timeout_count == 1

    async def test_provider_metrics_unknown(self, engine):
        metrics = await engine.provider_metrics("nonexistent")
        assert metrics is None

    async def test_record_success_adds_latency(self, engine):
        await engine.record_success("p1", latency_ms=100.0)
        metrics = await engine.provider_metrics("p1")
        assert metrics.average_latency_ms == 100.0

    async def test_record_failure_ignored_when_not_started(self):
        cb = CircuitBreakerEngineImpl()
        cb._started = False
        await cb.record_failure("p1")
        assert cb._providers == {}
        await cb.dispose()

    async def test_record_success_ignored_when_not_started(self):
        cb = CircuitBreakerEngineImpl()
        cb._started = False
        await cb.record_success("p1")
        assert cb._providers == {}
        await cb.dispose()


# ══════════════════════════════════════════════
# Failure type classification tests
# ══════════════════════════════════════════════


class TestFailureClassification:
    async def test_timeout_classification(self, engine):
        await engine.record_failure("p1", failure_type="timeout")
        m = await engine.provider_metrics("p1")
        assert m.timeout_count == 1

    async def test_http_classification(self, engine):
        await engine.record_failure("p1", failure_type="http_5xx")
        m = await engine.provider_metrics("p1")
        assert m.http_failures == 1

    async def test_auth_classification(self, engine):
        await engine.record_failure("p1", failure_type="unauthorized")
        m = await engine.provider_metrics("p1")
        assert m.authentication_failures == 1

    async def test_rate_limit_classification(self, engine):
        await engine.record_failure("p1", failure_type="rate_limit")
        m = await engine.provider_metrics("p1")
        assert m.rate_limit_failures == 1

    async def test_network_classification(self, engine):
        await engine.record_failure("p1", failure_type="connection")
        m = await engine.provider_metrics("p1")
        assert m.network_failures == 1

    async def test_unavailable_classification(self, engine):
        await engine.record_failure("p1", failure_type="service_unavailable")
        m = await engine.provider_metrics("p1")
        assert m.provider_unavailable_count == 1

    async def test_unknown_failure_type(self, engine):
        await engine.record_failure("p1", failure_type="random_error")
        metrics = await engine.provider_metrics("p1")
        assert metrics.failure_count == 1
        # None of the specific counters should increment
        assert metrics.timeout_count == 0
        assert metrics.http_failures == 0
        assert metrics.authentication_failures == 0
        assert metrics.rate_limit_failures == 0
        assert metrics.network_failures == 0
        assert metrics.provider_unavailable_count == 0

    async def test_multiple_failure_types(self, engine):
        await engine.record_failure("p1", failure_type="timeout")
        await engine.record_failure("p1", failure_type="http_5xx")
        await engine.record_failure("p1", failure_type="rate_limit")
        m = await engine.provider_metrics("p1")
        assert m.timeout_count == 1
        assert m.http_failures == 1
        assert m.rate_limit_failures == 1
        assert m.failure_count == 3

    async def test_failure_type_variants_timeout(self, engine):
        await engine.record_failure("p1", failure_type="deadline_exceeded")
        m = await engine.provider_metrics("p1")
        assert m.timeout_count == 1

    async def test_failure_type_variants_auth(self, engine):
        await engine.record_failure("p1", failure_type="forbidden")
        m = await engine.provider_metrics("p1")
        assert m.authentication_failures == 1


# ══════════════════════════════════════════════
# Configuration threshold tests
# ══════════════════════════════════════════════


class TestConfiguration:
    async def test_high_failure_threshold(self):
        cfg = CircuitBreakerConfig(failure_threshold=10, minimum_request_count=5)
        cb = CircuitBreakerEngineImpl(global_config=cfg)
        await cb.start()
        for _ in range(9):
            await cb.record_failure("p1")
        state = await cb.provider_state("p1")
        assert state.state == FailoverState.CLOSED
        await cb.record_failure("p1")
        state = await cb.provider_state("p1")
        assert state.state == FailoverState.CIRCUIT_OPEN
        await cb.dispose()

    async def test_minimum_request_count_prevents_early_trip(self):
        cfg = CircuitBreakerConfig(failure_threshold=3, minimum_request_count=10)
        cb = CircuitBreakerEngineImpl(global_config=cfg)
        await cb.start()
        for _ in range(3):
            await cb.record_failure("p1")
        state = await cb.provider_state("p1")
        assert state.state == FailoverState.CLOSED  # Not enough total requests
        await cb.dispose()

    async def test_recovery_timeout(self):
        cfg = CircuitBreakerConfig(
            failure_threshold=3,
            minimum_request_count=2,
            recovery_timeout_seconds=0.2,
        )
        cb = CircuitBreakerEngineImpl(global_config=cfg)
        await cb.start()
        for _ in range(4):
            await cb.record_failure("p1")
        state = await cb.provider_state("p1")
        assert state.state == FailoverState.CIRCUIT_OPEN
        # Should still be OPEN before timeout
        assert await cb.allow_request("p1") is False
        await asyncio.sleep(0.25)
        # Should now be allowed (HALF_OPEN)
        assert await cb.allow_request("p1") is True
        await cb.dispose()

    async def test_half_open_probe_count(self):
        cfg = CircuitBreakerConfig(
            failure_threshold=3,
            minimum_request_count=2,
            recovery_timeout_seconds=0.05,
            half_open_probe_count=3,
        )
        cb = CircuitBreakerEngineImpl(global_config=cfg)
        await cb.start()
        for _ in range(4):
            await cb.record_failure("p1")
        await asyncio.sleep(0.06)
        # Should allow up to 3 probe requests (1 free transition + 3 probes = 4 total)
        assert await cb.allow_request("p1") is True  # OPEN→HALF_OPEN
        assert await cb.allow_request("p1") is True  # probe 1
        assert await cb.allow_request("p1") is True  # probe 2
        assert await cb.allow_request("p1") is True  # probe 3
        # 5th should be blocked
        assert await cb.allow_request("p1") is False
        await cb.dispose()

    async def test_default_config_sane(self):
        cfg = CircuitBreakerConfig()
        assert cfg.failure_threshold == 5
        assert cfg.minimum_request_count == 3
        assert cfg.recovery_timeout_seconds == 30.0
        assert cfg.half_open_probe_count == 2
        assert cfg.sliding_window_size == 10

    async def test_long_recovery_persists_open(self):
        cfg = CircuitBreakerConfig(
            failure_threshold=3,
            minimum_request_count=2,
            recovery_timeout_seconds=60.0,
        )
        cb = CircuitBreakerEngineImpl(global_config=cfg)
        await cb.start()
        for _ in range(4):
            await cb.record_failure("p1")
        state = await cb.provider_state("p1")
        assert state.state == FailoverState.CIRCUIT_OPEN
        # Short sleep should NOT trigger recovery
        await asyncio.sleep(0.01)
        assert await cb.allow_request("p1") is False
        await cb.dispose()

    async def test_trip_on_consecutive_failures_with_partial_successes(self, engine):
        """Consecutive failures should trip even with some successes mixed in."""
        cfg = CircuitBreakerConfig(failure_threshold=5, minimum_request_count=2)
        cb = CircuitBreakerEngineImpl(global_config=cfg)
        await cb.start()
        await cb.record_success("p1")
        for _ in range(5):
            await cb.record_failure("p1")
        state = await cb.provider_state("p1")
        assert state.state == FailoverState.CIRCUIT_OPEN
        assert state.consecutive_failures == 5
        await cb.dispose()


# ══════════════════════════════════════════════
# EventBus integration tests
# ══════════════════════════════════════════════


class TestEventBusIntegration:
    async def test_publishes_circuit_opened(self, engine_with_bus):
        cb, bus = engine_with_bus
        cfg = CircuitBreakerConfig(failure_threshold=2, minimum_request_count=1)
        cb._global_config = cfg
        await cb.record_failure("p1")
        await cb.record_failure("p1")  # should trip
        bus.publish.assert_any_call(ANY)
        calls = [
            c for c in bus.publish.call_args_list if Topic.PROVIDER_CIRCUIT_OPENED.value in str(c)
        ]
        assert len(calls) >= 1

    async def test_publishes_circuit_half_opened(self, engine_with_bus):
        cb, bus = engine_with_bus
        cfg = CircuitBreakerConfig(
            failure_threshold=2,
            minimum_request_count=1,
            recovery_timeout_seconds=0.05,
        )
        cb._global_config = cfg
        await cb.record_failure("p1")
        await cb.record_failure("p1")
        await asyncio.sleep(0.06)
        await cb.allow_request("p1")  # → HALF_OPEN
        calls = [
            c
            for c in bus.publish.call_args_list
            if Topic.PROVIDER_CIRCUIT_HALF_OPEN.value in str(c)
        ]
        assert len(calls) >= 1

    async def test_publishes_circuit_closed(self, engine_with_bus):
        cb, bus = engine_with_bus
        cfg = CircuitBreakerConfig(
            failure_threshold=2,
            minimum_request_count=1,
            recovery_timeout_seconds=0.05,
            half_open_probe_count=1,
        )
        cb._global_config = cfg
        await cb.record_failure("p1")
        await cb.record_failure("p1")  # OPEN
        await asyncio.sleep(0.06)
        await cb.allow_request("p1")  # HALF_OPEN
        await cb.record_success("p1")  # CLOSED
        calls = [
            c for c in bus.publish.call_args_list if Topic.PROVIDER_CIRCUIT_CLOSED.value in str(c)
        ]
        assert len(calls) >= 1

    async def test_publishes_failure_recorded(self, engine_with_bus):
        cb, bus = engine_with_bus
        await cb.record_failure("p1")
        calls = [
            c for c in bus.publish.call_args_list if Topic.PROVIDER_FAILURE_RECORDED.value in str(c)
        ]
        assert len(calls) >= 1

    async def test_publishes_success_recorded(self, engine_with_bus):
        cb, bus = engine_with_bus
        await cb.record_success("p1")
        calls = [
            c for c in bus.publish.call_args_list if Topic.PROVIDER_SUCCESS_RECORDED.value in str(c)
        ]
        assert len(calls) >= 1

    async def test_no_eventbus_does_not_crash(self, engine):
        await engine.record_success("p1")
        await engine.record_failure("p1")
        await engine.trip("p1")
        state = await engine.provider_state("p1")
        assert state is not None

    async def test_event_payload_contains_provider(self, engine_with_bus):
        cb, bus = engine_with_bus
        await cb.record_failure("p1", failure_type="timeout")
        call = bus.publish.call_args
        assert call is not None
        envelope = call[0][0]
        payload = envelope.payload
        assert payload["provider"] == "p1"

    async def test_event_payload_contains_failure_type(self, engine_with_bus):
        cb, bus = engine_with_bus
        await cb.record_failure("p1", failure_type="http_5xx")
        call = bus.publish.call_args
        envelope = call[0][0]
        payload = envelope.payload
        assert payload["failure_type"] == "http_5xx"

    async def test_event_topic_from_transition(self, engine_with_bus):
        cb, bus = engine_with_bus
        bus.publish.reset_mock()
        await cb.record_success("p1")
        calls = [c for c in bus.publish.call_args_list]
        topics_published = [c[0][0].type for c in calls]
        assert "provider.success_recorded" in topics_published


# ══════════════════════════════════════════════
# Concurrency tests
# ══════════════════════════════════════════════


class TestConcurrency:
    async def test_concurrent_record_failures(self, engine):
        async def fail():
            for _ in range(10):
                await engine.record_failure("p1")

        await asyncio.gather(fail(), fail(), fail())
        state = await engine.provider_state("p1")
        assert state.failure_count == 30

    async def test_concurrent_record_successes(self, engine):
        async def succeed():
            for _ in range(10):
                await engine.record_success("p1")

        await asyncio.gather(succeed(), succeed(), succeed())
        state = await engine.provider_state("p1")
        assert state.success_count == 30

    async def test_concurrent_mixed_ops(self, engine):
        async def fail():
            for _ in range(5):
                await engine.record_failure("p1")

        async def succeed():
            for _ in range(5):
                await engine.record_success("p1")

        async def check():
            for _ in range(5):
                await engine.allow_request("p1")
                await engine.provider_state("p1")

        await asyncio.gather(fail(), succeed(), check())
        state = await engine.provider_state("p1")
        assert state.failure_count + state.success_count == 10

    async def test_concurrent_trip_and_recover(self, fast_engine):
        async def tripper():
            await fast_engine.trip("p1")

        async def recoverer():
            await asyncio.sleep(0.06)
            await fast_engine.allow_request("p1")
            await fast_engine.record_success("p1")

        await asyncio.gather(tripper(), recoverer())
        state = await fast_engine.provider_state("p1")
        assert state.state == FailoverState.CLOSED or state.state == FailoverState.CIRCUIT_OPEN

    async def test_lock_held_during_transition(self, fast_engine):
        """Verify that the lock prevents race conditions during state transitions."""

        async def rapid_fail():
            for _ in range(20):
                await fast_engine.record_failure("p1")

        async def rapid_succeed():
            for _ in range(20):
                await fast_engine.record_success("p1")

        await asyncio.gather(rapid_fail(), rapid_succeed())
        state = await fast_engine.provider_state("p1")
        assert state.failure_count + state.success_count == 40


# ══════════════════════════════════════════════
# Router integration tests
# ══════════════════════════════════════════════


class MockCandidate:
    """Simple candidate with provider name for circuit breaker tests."""

    def __init__(self, name: str):
        self.provider = MagicMock()
        self.provider.name = name
        self.model = MagicMock()
        self.model.model_id = f"{name}-model"


class TestRouterIntegration:
    async def test_filter_removes_open_providers(self):
        cb = CircuitBreakerEngineImpl()
        await cb.start()
        cfg = CircuitBreakerConfig(failure_threshold=2, minimum_request_count=1)
        cb._global_config = cfg

        # Trip p1, keep p2 healthy
        await cb.record_failure("p1")
        await cb.record_failure("p1")
        await cb.record_success("p2")

        router = MagicMock()
        router._circuit_breaker = cb

        # Simulate the filter
        from agentic_os.core.omniroute.router import RouterEngineImpl

        re = RouterEngineImpl(circuit_breaker=cb)
        await re.start()

        # We can't easily call the private method, so test via allow_request
        assert await cb.allow_request("p1") is False
        assert await cb.allow_request("p2") is True
        await cb.dispose()
        await re.dispose()

    async def test_router_uses_circuit_breaker_in_pipeline(self):
        cb = CircuitBreakerEngineImpl()
        await cb.start()
        cfg = CircuitBreakerConfig(failure_threshold=2, minimum_request_count=1)
        cb._global_config = cfg

        re = RouterEngineImpl(circuit_breaker=cb)
        await re.start()

        # Verify the circuit breaker is wired
        assert re._circuit_breaker is cb
        await re.dispose()
        await cb.dispose()

    async def test_router_no_circuit_breaker(self):
        re = RouterEngineImpl()
        await re.start()
        assert re._circuit_breaker is None
        await re.dispose()

    async def test_filter_circuit_breaker_empty_candidates(self):
        """When no candidates pass circuit breaker, route returns failed."""
        cb = CircuitBreakerEngineImpl()
        await cb.start()
        cfg = CircuitBreakerConfig(failure_threshold=2, minimum_request_count=1)
        cb._global_config = cfg

        re = RouterEngineImpl(circuit_breaker=cb)
        re._provider_registry = MagicMock()
        re._provider_registry.list_providers = AsyncMock(return_value=[])
        re._model_registry = MagicMock()
        re._model_registry.list_enabled_models = AsyncMock(return_value=[])
        re._model_registry.list_models = AsyncMock(return_value=[])
        re._model_registry.get_provider_models = AsyncMock(return_value=[])
        await re.start()

        req = RoutingRequest(request_id="test-1")
        decision = await re.route(req)
        # Should fail with no providers
        assert decision.status in ("failed", "rejected")
        await re.dispose()
        await cb.dispose()

    async def test_filter_handles_broken_circuit_breaker_gracefully(self):
        """If circuit breaker throws, router should still function."""
        cb = AsyncMock()
        cb.allow_request = AsyncMock(side_effect=Exception("boom"))

        re = RouterEngineImpl(circuit_breaker=cb)
        # Setup provider registry with a provider
        from agentic_os.core.omniroute.provider_registry import ProviderRegistryImpl

        pr = ProviderRegistryImpl()
        await pr.start()
        from agentic_os.domain.omniroute import OmniRouteProvider

        pid = await pr.register(OmniRouteProvider(name="p1", healthy=True, enabled=True))
        from agentic_os.core.omniroute.model_registry import ModelRegistryImpl

        mr = ModelRegistryImpl(provider_registry=pr)
        await mr.start()
        from agentic_os.domain.omniroute import OmniRouteModel

        await mr.register_model(
            OmniRouteModel(model_id="m1", provider="p1", provider_id=pid, enabled=True)
        )

        re._provider_registry = pr
        re._model_registry = mr
        await re.start()

        # Route should still succeed (circuit breaker failure caught and allowed)
        req = RoutingRequest(request_id="test-2")
        decision = await re.route(req)
        assert decision.status == "routed"
        await mr.stop()
        await pr.stop()
        await re.dispose()
        await cb.dispose()

    async def test_router_registers_recovery(self, fast_engine):
        # Trip p1
        for _ in range(4):
            await fast_engine.record_failure("p1")
        assert await fast_engine.allow_request("p1") is False

        # Wait for recovery
        await asyncio.sleep(0.06)
        assert await fast_engine.allow_request("p1") is True

        # Record success → CLOSED
        await fast_engine.record_success("p1")
        state = await fast_engine.provider_state("p1")
        assert state.state == FailoverState.CLOSED

    async def test_router_keeps_healthy_when_mixed(self, fast_engine):
        """Healthy providers still work when one is tripped."""
        for _ in range(4):
            await fast_engine.record_failure("p1")
        await fast_engine.record_success("p2")
        assert await fast_engine.allow_request("p1") is False
        assert await fast_engine.allow_request("p2") is True

    async def test_router_with_partial_recovery(self, fast_engine):
        """Multiple recovery attempts should eventually succeed."""
        for _ in range(4):
            await fast_engine.record_failure("p1")
        await asyncio.sleep(0.06)
        await fast_engine.allow_request("p1")  # HALF_OPEN
        await fast_engine.record_success("p1")  # CLOSED
        assert await fast_engine.allow_request("p1") is True


# ══════════════════════════════════════════════
# Statistics / Metrics tests
# ══════════════════════════════════════════════


class TestStatistics:
    async def test_statistics_tracks_failures(self, engine):
        await engine.record_failure("p1")
        await engine.record_failure("p1")
        stats = await engine.statistics()
        assert stats["total_failures"] == 2

    async def test_statistics_tracks_successes(self, engine):
        await engine.record_success("p1")
        await engine.record_success("p1")
        stats = await engine.statistics()
        assert stats["total_successes"] == 2

    async def test_statistics_state_distribution(self, engine):
        await engine.record_success("p1")
        stats = await engine.statistics()
        dist = stats["state_distribution"]
        assert FailoverState.CLOSED.value in dist or "closed" in str(dist)

    async def test_statistics_includes_trips(self, fast_engine):
        for _ in range(4):
            await fast_engine.record_failure("p1")
        stats = await fast_engine.statistics()
        assert stats["total_trips"] >= 1

    async def test_state_transitions_tracked(self, fast_engine):
        for _ in range(4):
            await fast_engine.record_failure("p1")
        await asyncio.sleep(0.06)
        await fast_engine.allow_request("p1")
        await fast_engine.record_success("p1")
        stats = await fast_engine.statistics()
        assert len(stats["state_transitions"]) >= 1

    async def test_statistics_avg_latency(self, engine):
        await engine.record_success("p1", latency_ms=50.0)
        await engine.record_success("p1", latency_ms=150.0)
        stats = await engine.statistics()
        assert stats["avg_latency_ms"] == 100.0

    async def test_statistics_empty_engine(self, engine):
        stats = await engine.statistics()
        assert stats["tracked_providers"] == 0

    async def test_open_providers_multiple(self, fast_engine):
        for _ in range(4):
            await fast_engine.record_failure("p1")
        for _ in range(4):
            await fast_engine.record_failure("p2")
        opens = await fast_engine.open_providers()
        assert "p1" in opens
        assert "p2" in opens

    async def test_trip_count_increments(self, fast_engine):
        for _ in range(4):
            await fast_engine.record_failure("p1")
        stats = await fast_engine.statistics()
        assert stats["total_trips"] >= 1


# ══════════════════════════════════════════════
# Edge cases
# ══════════════════════════════════════════════


class TestEdgeCases:
    async def test_unknown_provider_gets_created(self, engine):
        await engine.record_success("new_provider")
        state = await engine.provider_state("new_provider")
        assert state is not None

    async def test_manual_reset_clears_everything(self, engine):
        await engine.record_failure("p1")
        await engine.record_failure("p1")
        await engine.record_failure("p1")
        await engine.reset("p1")
        state = await engine.provider_state("p1")
        assert state.failure_count == 0
        assert state.success_count == 0
        assert state.consecutive_failures == 0

    async def test_success_after_trip_does_not_immediately_close(self, fast_engine):
        """One success is not enough when half_open_probe_count > 1."""
        cfg = CircuitBreakerConfig(
            failure_threshold=3,
            minimum_request_count=2,
            recovery_timeout_seconds=0.05,
            half_open_probe_count=3,
        )
        cb = CircuitBreakerEngineImpl(global_config=cfg)
        await cb.start()
        for _ in range(4):
            await cb.record_failure("p1")
        await asyncio.sleep(0.06)
        await cb.allow_request("p1")
        await cb.record_success("p1")
        state = await cb.provider_state("p1")
        # Should still be HALF_OPEN after only 1 of 3 probe successes
        assert state.state == FailoverState.CIRCUIT_HALF_OPEN
        await cb.dispose()

    async def test_mixed_failures_between_providers(self, engine):
        await engine.record_success("p1")
        await engine.record_failure("p2")
        assert await engine.allow_request("p1") is True
        assert await engine.allow_request("p2") is True  # Below threshold

    async def test_large_trip_count_does_not_overflow(self):
        cb = CircuitBreakerEngineImpl()
        cb._started = True
        for _ in range(1000):
            await cb.record_failure("p1")
        state = await cb.provider_state("p1")
        assert state.failure_count == 1000
        await cb.dispose()

    async def test_provider_metrics_consistent(self, engine):
        await engine.record_failure("p1", failure_type="timeout", latency_ms=100.0)
        await engine.record_success("p1", latency_ms=50.0)
        m = await engine.provider_metrics("p1")
        assert m.failure_count == 1
        assert m.success_count == 1
        assert m.timeout_count == 1
        assert m.average_latency_ms == 75.0
        assert m.consecutive_failures == 0  # Reset by success

    async def test_multiple_trips_same_provider(self, fast_engine):
        for _cycle in range(3):
            for _ in range(4):
                await fast_engine.record_failure("p1")
            await asyncio.sleep(0.06)
            await fast_engine.allow_request("p1")
            await fast_engine.record_success("p1")
        stats = await fast_engine.statistics()
        assert stats["total_recoveries"] >= 2

    async def test_dispose_then_reuse_fails_safely(self, engine):
        await engine.dispose()
        # Should not crash
        await engine.record_failure("p1")  # ignored (not started)
        h = await engine.health()
        assert h["status"] == "stopped"

    async def test_allow_request_after_close(self, engine):
        await engine.trip("p1")
        assert await engine.allow_request("p1") is False
        await engine.close("p1")
        assert await engine.allow_request("p1") is True

    async def test_statistics_with_provider_metrics(self, engine):
        await engine.record_success("p1", latency_ms=75.0)
        await engine.record_failure("p2")
        stats = await engine.statistics()
        # The circuit breaker tracks per-provider metrics
        assert stats["tracked_providers"] >= 2


# ══════════════════════════════════════════════
# Additional edge / corner case tests
# ══════════════════════════════════════════════


class TestMoreEdgeCases:
    async def test_reset_after_trip_clears_open_until(self, engine):
        await engine.trip("p1")
        state = await engine.provider_state("p1")
        assert state.circuit_open_until is not None
        await engine.reset("p1")
        state2 = await engine.provider_state("p1")
        assert state2.circuit_open_until is None

    async def test_max_sliding_window_does_not_trip(self):
        """With high threshold and few requests, sliding window should not trip."""
        cfg = CircuitBreakerConfig(
            failure_threshold=5,
            minimum_request_count=5,
            sliding_window_size=10,
        )
        cb = CircuitBreakerEngineImpl(global_config=cfg)
        await cb.start()
        for _ in range(3):
            await cb.record_failure("p1")
        state = await cb.provider_state("p1")
        assert state.state == FailoverState.CLOSED
        await cb.dispose()

    async def test_internal_transition_noop(self, engine):
        """Test transition to same state does not raise."""
        await engine.record_success("p1")
        ps = engine._providers["p1"]
        old = ps.state
        await engine._transition("p1", old, "test")
        state = await engine.provider_state("p1")
        assert state.state == old

    async def test_stats_state_transitions_format(self, engine):
        await engine.trip("p1")
        await engine.close("p1")
        await engine.trip("p1")
        stats = await engine.statistics()
        for key in stats["state_transitions"]:
            assert "→" in key
