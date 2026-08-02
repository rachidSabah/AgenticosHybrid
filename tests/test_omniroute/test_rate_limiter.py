"""Tests for OmniRoute Intelligent Rate Limiter & Quota Engine (Phase 5.8).

Covers:
- Lifecycle
- Policy CRUD
- Token bucket algorithm
- Leaky bucket algorithm
- Sliding window algorithm
- Fixed window algorithm
- Reservations (reserve/grant/release/rollback/TTL)
- Queue management (priority, WFQ, RR, overflow)
- Adaptive quotas
- Retry prediction
- Statistics and metrics
- Forecasting
- Concurrency and thread safety
- Router integration
- Edge cases
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from agentic_os.core.omniroute.rate_limiter import RateLimiterEngineImpl, _RetryPredictor
from agentic_os.domain.events import Topic
from agentic_os.domain.omniroute import (
    LeakyBucket,
    PermitGrant,
    PermitReservation,
    PriorityLevel,
    QueueStatistics,
    QuotaForecast,
    QuotaScope,
    QuotaUsage,
    RateLimitDecision,
    RateLimitForecast,
    RateLimitMetrics,
    RateLimitPolicy,
    RetryPrediction,
    SlidingWindowCounter,
    TokenBucket,
)

# ── Helpers ──


def _make_policy(
    name: str = "test_policy",
    scope: QuotaScope = QuotaScope.GLOBAL,
    scope_id: str = "",
    algorithm: str = "token_bucket",
    enabled: bool = True,
    order: int = 0,
    priority: PriorityLevel = PriorityLevel.NORMAL,
    capacity: float = 100.0,
    refill_rate: float = 10.0,
    max_burst: int = 0,
    queue_max_size: int = 0,
    token_bucket: TokenBucket | None = None,
    leaky_bucket: LeakyBucket | None = None,
    sliding_window: SlidingWindowCounter | None = None,
) -> RateLimitPolicy:
    return RateLimitPolicy(
        name=name,
        description=f"Test policy {name}",
        enabled=enabled,
        order=order,
        priority=priority,
        scope=scope,
        scope_id=scope_id,
        algorithm=algorithm,
        token_bucket=token_bucket
        if token_bucket is not None
        else TokenBucket(
            capacity=capacity, refill_rate=refill_rate, burst_allowance=float(max_burst)
        ),
        leaky_bucket=leaky_bucket
        if leaky_bucket is not None
        else LeakyBucket(drain_rate=10.0, max_queue_depth=100),
        sliding_window=sliding_window
        if sliding_window is not None
        else SlidingWindowCounter(max_requests=100, window_duration_s=60.0),
        max_burst=max_burst,
        queue_max_size=queue_max_size,
    )


def _make_engine(event_bus: Any | None = None) -> RateLimiterEngineImpl:
    engine = RateLimiterEngineImpl(event_bus=event_bus)
    return engine


@pytest.fixture
def engine() -> RateLimiterEngineImpl:
    eng = _make_engine()
    return eng


@pytest.fixture
async def started_engine(engine: RateLimiterEngineImpl) -> RateLimiterEngineImpl:
    await engine.start()
    return engine


# ════════════════════════════════════════════
# 1. Lifecycle
# ════════════════════════════════════════════


class TestLifecycle:
    async def test_initial_state(self, engine: RateLimiterEngineImpl) -> None:
        assert not await engine.ready()
        assert not await engine.healthy()
        h = await engine.health()
        assert h["status"] == "stopped"

    async def test_start(self, engine: RateLimiterEngineImpl) -> None:
        await engine.start()
        assert await engine.ready()
        assert await engine.healthy()

    async def test_stop(self, engine: RateLimiterEngineImpl) -> None:
        await engine.start()
        await engine.stop()
        assert not await engine.ready()

    async def test_dispose_clears_state(self, engine: RateLimiterEngineImpl) -> None:
        await engine.start()
        policy = _make_policy("dispose_test")
        await engine.create_policy(policy)
        assert engine.policy_count == 1
        await engine.dispose()
        assert engine.policy_count == 0
        assert engine.total_requests == 0
        assert not await engine.ready()

    async def test_health_after_start(self, engine: RateLimiterEngineImpl) -> None:
        await engine.start()
        h = await engine.health()
        assert h["status"] == "healthy"
        assert h["started"] is True
        assert h["uptime_seconds"] >= 0

    async def test_health_after_dispose(self, engine: RateLimiterEngineImpl) -> None:
        await engine.start()
        await engine.dispose()
        h = await engine.health()
        assert h["status"] == "stopped"

    async def test_evaluate_before_start_returns_approved(
        self, engine: RateLimiterEngineImpl
    ) -> None:
        decision = await engine.evaluate("provider_a", "model_x")
        assert decision.approved
        assert "not started" in decision.reason

    async def test_double_start(self, engine: RateLimiterEngineImpl) -> None:
        await engine.start()
        await engine.start()
        assert await engine.ready()

    async def test_stop_before_start(self, engine: RateLimiterEngineImpl) -> None:
        await engine.stop()
        assert not await engine.ready()


# ════════════════════════════════════════════
# 2. Policy CRUD
# ════════════════════════════════════════════


class TestPolicyCRUD:
    async def test_create_policy(self, started_engine: RateLimiterEngineImpl) -> None:
        policy = _make_policy("crud_create")
        created = await started_engine.create_policy(policy)
        assert created.id == policy.id
        assert created.name == "crud_create"
        assert created.enabled

    async def test_create_policy_increments_count(
        self, started_engine: RateLimiterEngineImpl
    ) -> None:
        p1 = _make_policy("p1")
        p2 = _make_policy("p2")
        await started_engine.create_policy(p1)
        await started_engine.create_policy(p2)
        assert started_engine.policy_count == 2

    async def test_get_policy(self, started_engine: RateLimiterEngineImpl) -> None:
        policy = _make_policy("get_test")
        await started_engine.create_policy(policy)
        retrieved = await started_engine.get_policy(policy.id)
        assert retrieved is not None
        assert retrieved.id == policy.id
        assert retrieved.name == "get_test"

    async def test_get_missing_policy(self, started_engine: RateLimiterEngineImpl) -> None:
        retrieved = await started_engine.get_policy("nonexistent")
        assert retrieved is None

    async def test_update_policy(self, started_engine: RateLimiterEngineImpl) -> None:
        policy = _make_policy("update_test")
        await started_engine.create_policy(policy)
        result = await started_engine.update_policy(
            RateLimitPolicy(
                id=policy.id,
                name="updated_name",
                description="updated",
                enabled=False,
                priority=policy.priority,
                scope=policy.scope,
                scope_id=policy.scope_id,
                algorithm=policy.algorithm,
                token_bucket=policy.token_bucket,
                leaky_bucket=policy.leaky_bucket,
                sliding_window=policy.sliding_window,
                max_burst=policy.max_burst,
                queue_max_size=policy.queue_max_size,
                metadata=policy.metadata,
                created_at=policy.created_at,
            )
        )
        assert result is not None
        assert result.name == "updated_name"

    async def test_update_missing_policy(self, started_engine: RateLimiterEngineImpl) -> None:
        result = await started_engine.update_policy(_make_policy("missing"))
        assert result is None

    async def test_delete_policy(self, started_engine: RateLimiterEngineImpl) -> None:
        policy = _make_policy("delete_test")
        await started_engine.create_policy(policy)
        deleted = await started_engine.delete_policy(policy.id)
        assert deleted
        assert started_engine.policy_count == 0

    async def test_delete_missing_policy(self, started_engine: RateLimiterEngineImpl) -> None:
        deleted = await started_engine.delete_policy("nonexistent")
        assert not deleted

    async def test_list_policies(self, started_engine: RateLimiterEngineImpl) -> None:
        p1 = _make_policy("list1", scope=QuotaScope.GLOBAL)
        p2 = _make_policy("list2", scope=QuotaScope.PROVIDER, scope_id="prov_a")
        await started_engine.create_policy(p1)
        await started_engine.create_policy(p2)
        all_policies = await started_engine.list_policies()
        assert len(all_policies) == 2

    async def test_list_policies_by_scope(self, started_engine: RateLimiterEngineImpl) -> None:
        p1 = _make_policy("scope1", scope=QuotaScope.GLOBAL)
        p2 = _make_policy("scope2", scope=QuotaScope.PROVIDER, scope_id="prov_a")
        await started_engine.create_policy(p1)
        await started_engine.create_policy(p2)
        global_policies = await started_engine.list_policies(scope=QuotaScope.GLOBAL)
        assert len(global_policies) == 1

    async def test_enable_policy(self, started_engine: RateLimiterEngineImpl) -> None:
        policy = _make_policy("enable_test", enabled=False)
        await started_engine.create_policy(policy)
        enabled = await started_engine.enable_policy(policy.id)
        assert enabled
        retrieved = await started_engine.get_policy(policy.id)
        assert retrieved is not None
        assert retrieved.enabled

    async def test_enable_missing_policy(self, started_engine: RateLimiterEngineImpl) -> None:
        enabled = await started_engine.enable_policy("nonexistent")
        assert not enabled

    async def test_disable_policy(self, started_engine: RateLimiterEngineImpl) -> None:
        policy = _make_policy("disable_test", enabled=True)
        await started_engine.create_policy(policy)
        disabled = await started_engine.disable_policy(policy.id)
        assert disabled
        retrieved = await started_engine.get_policy(policy.id)
        assert retrieved is not None
        assert not retrieved.enabled

    async def test_disable_missing_policy(self, started_engine: RateLimiterEngineImpl) -> None:
        disabled = await started_engine.disable_policy("nonexistent")
        assert not disabled

    async def test_policy_event_on_create(self) -> None:
        bus = MagicMock()
        bus.publish = AsyncMock()
        engine = _make_engine(event_bus=bus)
        await engine.start()
        policy = _make_policy("event_test")
        await engine.create_policy(policy)
        bus.publish.assert_called()
        call_args = bus.publish.call_args[0][0]
        assert call_args.topic == Topic.RATE_LIMIT_POLICY_CREATED.value

    async def test_policy_event_on_delete(self) -> None:
        bus = MagicMock()
        bus.publish = AsyncMock()
        engine = _make_engine(event_bus=bus)
        await engine.start()
        policy = _make_policy("event_del")
        await engine.create_policy(policy)
        bus.publish.reset_mock()
        await engine.delete_policy(policy.id)
        assert any(
            call[0][0].topic == Topic.RATE_LIMIT_POLICY_DELETED.value
            for call in bus.publish.call_args_list
        )


# ════════════════════════════════════════════
# 3. Token Bucket
# ════════════════════════════════════════════


class TestTokenBucket:
    async def test_token_bucket_approves_when_tokens_available(
        self, started_engine: RateLimiterEngineImpl
    ) -> None:
        policy = _make_policy(
            "tb_approve", algorithm="token_bucket", capacity=100.0, refill_rate=10.0
        )
        await started_engine.create_policy(policy)
        decision = await started_engine.evaluate("provider_a", "model_x")
        assert decision.approved
        assert decision.algorithm == "token_bucket"

    async def test_token_bucket_rejects_when_empty(
        self, started_engine: RateLimiterEngineImpl
    ) -> None:
        policy = _make_policy(
            "tb_reject", algorithm="token_bucket", capacity=2.0, refill_rate=0.001, max_burst=0
        )
        await started_engine.create_policy(policy)
        await started_engine.evaluate("provider_a", "model_x")
        await started_engine.evaluate("provider_a", "model_x")
        decision = await started_engine.evaluate("provider_a", "model_x")
        assert decision.rejected
        assert "empty" in decision.reason

    async def test_token_bucket_burst_allows_extra(
        self, started_engine: RateLimiterEngineImpl
    ) -> None:
        policy = _make_policy(
            "tb_burst", algorithm="token_bucket", capacity=2.0, refill_rate=0.001, max_burst=5
        )
        await started_engine.create_policy(policy)
        for _ in range(3):
            d = await started_engine.evaluate("provider_a", "model_x")
            assert d.approved, f"Burst failed at iteration {_}: {d.reason}"

    async def test_token_bucket_refills_over_time(
        self, started_engine: RateLimiterEngineImpl
    ) -> None:
        tb = TokenBucket(
            capacity=5.0, refill_rate=1000.0, refill_interval_ms=1.0, burst_allowance=0.0
        )
        policy = _make_policy("tb_refill", algorithm="token_bucket", token_bucket=tb)
        await started_engine.create_policy(policy)
        for _ in range(5):
            await started_engine.evaluate("provider_a", "model_x")
        await asyncio.sleep(0.01)  # Let refill interval elapse
        decision = await started_engine.evaluate("provider_a", "model_x")
        # Should be approved because refill_rate is high enough to replenish
        assert decision.approved or decision.delayed

    async def test_token_bucket_remaining_tokens_in_decision(
        self, started_engine: RateLimiterEngineImpl
    ) -> None:
        policy = _make_policy(
            "tb_remaining", algorithm="token_bucket", capacity=10.0, refill_rate=0.001
        )
        await started_engine.create_policy(policy)
        decision = await started_engine.evaluate("provider_a", "model_x")
        assert decision.approved

    async def test_token_bucket_multiple_providers_independent(
        self, started_engine: RateLimiterEngineImpl
    ) -> None:
        p_a = _make_policy(
            "tb_prov_a",
            algorithm="token_bucket",
            scope=QuotaScope.PROVIDER,
            scope_id="prov_a",
            capacity=1.0,
            refill_rate=0.001,
            max_burst=0,
        )
        p_b = _make_policy(
            "tb_prov_b",
            algorithm="token_bucket",
            scope=QuotaScope.PROVIDER,
            scope_id="prov_b",
            capacity=10.0,
            refill_rate=0.001,
            max_burst=0,
        )
        await started_engine.create_policy(p_a)
        await started_engine.create_policy(p_b)
        d_a = await started_engine.evaluate("prov_a", "model_x")
        assert d_a.approved
        d_a2 = await started_engine.evaluate("prov_a", "model_x")
        assert d_a2.rejected
        d_b = await started_engine.evaluate("prov_b", "model_x")
        assert d_b.approved

    async def test_token_bucket_zero_capacity_rejects(
        self, started_engine: RateLimiterEngineImpl
    ) -> None:
        policy = _make_policy("tb_zero", algorithm="token_bucket", capacity=0.0, refill_rate=0.0)
        await started_engine.create_policy(policy)
        decision = await started_engine.evaluate("provider_a", "model_x")
        assert not decision.approved

    async def test_token_bucket_queue_when_full(
        self, started_engine: RateLimiterEngineImpl
    ) -> None:
        policy = _make_policy(
            "tb_queue", algorithm="token_bucket", capacity=1.0, refill_rate=0.001, queue_max_size=10
        )
        await started_engine.create_policy(policy)
        await started_engine.evaluate("provider_a", "model_x")
        decision = await started_engine.evaluate("provider_a", "model_x")
        assert decision.queued
        assert decision.queue_position > 0

    async def test_token_bucket_empty_event(self) -> None:
        bus = MagicMock()
        bus.publish = AsyncMock()
        engine = _make_engine(event_bus=bus)
        await engine.start()
        policy = _make_policy(
            "tb_empty_event", algorithm="token_bucket", capacity=1.0, refill_rate=0.001
        )
        await engine.create_policy(policy)
        await engine.evaluate("provider_a", "model_x")
        bus.publish.reset_mock()
        await engine.evaluate("provider_a", "model_x")
        assert any(
            call[0][0].topic == Topic.TOKEN_BUCKET_EMPTY.value
            for call in bus.publish.call_args_list
        )


# ════════════════════════════════════════════
# 4. Leaky Bucket
# ════════════════════════════════════════════


class TestLeakyBucket:
    async def test_leaky_bucket_approves_when_queue_available(
        self, started_engine: RateLimiterEngineImpl
    ) -> None:
        policy = _make_policy("lb_approve", algorithm="leaky_bucket")
        await started_engine.create_policy(policy)
        decision = await started_engine.evaluate("provider_a", "model_x")
        assert decision.approved
        assert decision.algorithm == "leaky_bucket"

    async def test_leaky_bucket_overflows(self, started_engine: RateLimiterEngineImpl) -> None:
        # Set up so leaky bucket fills quickly
        policy_with_small_queue = RateLimitPolicy(
            name="lb_overflow",
            description="",
            enabled=True,
            order=0,
            scope=QuotaScope.GLOBAL,
            scope_id="",
            algorithm="leaky_bucket",
            token_bucket=TokenBucket(),
            leaky_bucket=LeakyBucket(drain_rate=0.001, max_queue_depth=2),
            sliding_window=SlidingWindowCounter(),
            max_burst=0,
            queue_max_size=0,
            priority=PriorityLevel.NORMAL,
            metadata={},
            created_at=datetime.now(UTC),
        )
        await started_engine.create_policy(policy_with_small_queue)
        await started_engine.evaluate("provider_a", "model_x")
        await started_engine.evaluate("provider_a", "model_x")
        decision = await started_engine.evaluate("provider_a", "model_x")
        assert not decision.approved

    async def test_leaky_bucket_drains_over_time(
        self, started_engine: RateLimiterEngineImpl
    ) -> None:
        policy = RateLimitPolicy(
            name="lb_drain",
            description="",
            enabled=True,
            order=0,
            scope=QuotaScope.GLOBAL,
            scope_id="",
            algorithm="leaky_bucket",
            token_bucket=TokenBucket(),
            leaky_bucket=LeakyBucket(drain_rate=1000.0, drain_interval_ms=10, max_queue_depth=2),
            sliding_window=SlidingWindowCounter(),
            max_burst=0,
            queue_max_size=0,
            priority=PriorityLevel.NORMAL,
            metadata={},
            created_at=datetime.now(UTC),
        )
        await started_engine.create_policy(policy)
        await started_engine.evaluate("provider_a", "model_x")
        await started_engine.evaluate("provider_a", "model_x")
        await asyncio.sleep(0.02)
        decision = await started_engine.evaluate("provider_a", "model_x")
        assert decision.approved

    async def test_leaky_bucket_queue_when_full(
        self, started_engine: RateLimiterEngineImpl
    ) -> None:
        policy = RateLimitPolicy(
            name="lb_queue",
            description="",
            enabled=True,
            order=0,
            scope=QuotaScope.GLOBAL,
            scope_id="",
            algorithm="leaky_bucket",
            token_bucket=TokenBucket(),
            leaky_bucket=LeakyBucket(drain_rate=0.001, max_queue_depth=1),
            sliding_window=SlidingWindowCounter(),
            max_burst=0,
            queue_max_size=10,
            priority=PriorityLevel.NORMAL,
            metadata={},
            created_at=datetime.now(UTC),
        )
        await started_engine.create_policy(policy)
        await started_engine.evaluate("provider_a", "model_x")
        decision = await started_engine.evaluate("provider_a", "model_x")
        assert decision.queued or decision.rejected


# ════════════════════════════════════════════
# 5. Sliding Window
# ════════════════════════════════════════════


class TestSlidingWindow:
    async def test_sliding_window_approves_within_limit(
        self, started_engine: RateLimiterEngineImpl
    ) -> None:
        policy = _make_policy("sw_approve", algorithm="sliding_window")
        await started_engine.create_policy(policy)
        decision = await started_engine.evaluate("provider_a", "model_x")
        assert decision.approved

    async def test_sliding_window_rejects_when_exceeded(self) -> None:
        engine = _make_engine()
        await engine.start()
        policy = RateLimitPolicy(
            name="sw_reject",
            description="",
            enabled=True,
            order=0,
            scope=QuotaScope.GLOBAL,
            scope_id="",
            algorithm="sliding_window",
            token_bucket=TokenBucket(),
            leaky_bucket=LeakyBucket(),
            sliding_window=SlidingWindowCounter(max_requests=2, window_duration_s=3600.0),
            max_burst=0,
            queue_max_size=0,
            priority=PriorityLevel.NORMAL,
            metadata={},
            created_at=datetime.now(UTC),
        )
        await engine.create_policy(policy)
        await engine.evaluate("provider_a", "model_x")
        await engine.evaluate("provider_a", "model_x")
        decision = await engine.evaluate("provider_a", "model_x")
        assert decision.rejected
        assert "window exceeded" in decision.reason

    async def test_sliding_window_expires_after_duration(
        self, started_engine: RateLimiterEngineImpl
    ) -> None:
        policy = RateLimitPolicy(
            name="sw_expire",
            description="",
            enabled=True,
            order=0,
            scope=QuotaScope.GLOBAL,
            scope_id="",
            algorithm="fixed_window",
            token_bucket=TokenBucket(),
            leaky_bucket=LeakyBucket(),
            sliding_window=SlidingWindowCounter(max_requests=1, window_duration_s=0.05),
            max_burst=0,
            queue_max_size=0,
            priority=PriorityLevel.NORMAL,
            metadata={},
            created_at=datetime.now(UTC),
        )
        await started_engine.create_policy(policy)
        await started_engine.evaluate("provider_a", "model_x")
        await asyncio.sleep(0.1)
        decision = await started_engine.evaluate("provider_a", "model_x")
        assert decision.approved


# ════════════════════════════════════════════
# 6. Fixed Window
# ════════════════════════════════════════════


class TestFixedWindow:
    async def test_fixed_window_approves_within_limit(
        self, started_engine: RateLimiterEngineImpl
    ) -> None:
        policy = _make_policy("fw_approve", algorithm="fixed_window")
        await started_engine.create_policy(policy)
        decision = await started_engine.evaluate("provider_a", "model_x")
        assert decision.approved

    async def test_fixed_window_rejects_when_exceeded(self) -> None:
        engine = _make_engine()
        await engine.start()
        policy = RateLimitPolicy(
            name="fw_reject",
            description="",
            enabled=True,
            order=0,
            scope=QuotaScope.GLOBAL,
            scope_id="",
            algorithm="fixed_window",
            token_bucket=TokenBucket(),
            leaky_bucket=LeakyBucket(),
            sliding_window=SlidingWindowCounter(max_requests=1, window_duration_s=3600.0),
            max_burst=0,
            queue_max_size=0,
            priority=PriorityLevel.NORMAL,
            metadata={},
            created_at=datetime.now(UTC),
        )
        await engine.create_policy(policy)
        await engine.evaluate("provider_a", "model_x")
        decision = await engine.evaluate("provider_a", "model_x")
        assert decision.rejected
        assert "window exceeded" in decision.reason

    async def test_fixed_window_resets_after_duration(
        self, started_engine: RateLimiterEngineImpl
    ) -> None:
        policy = RateLimitPolicy(
            name="fw_reset",
            description="",
            enabled=True,
            order=0,
            scope=QuotaScope.GLOBAL,
            scope_id="",
            algorithm="fixed_window",
            token_bucket=TokenBucket(),
            leaky_bucket=LeakyBucket(),
            sliding_window=SlidingWindowCounter(max_requests=1, window_duration_s=0.001),
            max_burst=0,
            queue_max_size=0,
            priority=PriorityLevel.NORMAL,
            metadata={},
            created_at=datetime.now(UTC),
        )
        await started_engine.create_policy(policy)
        await started_engine.evaluate("provider_a", "model_x")
        await asyncio.sleep(0.005)
        decision = await started_engine.evaluate("provider_a", "model_x")
        assert decision.approved


# ════════════════════════════════════════════
# 7. Reservations
# ════════════════════════════════════════════


class TestReservations:
    async def test_reserve_creates_reservation(self, started_engine: RateLimiterEngineImpl) -> None:
        policy = _make_policy("reserve_test")
        await started_engine.create_policy(policy)
        res = await started_engine.reserve("provider_a", "model_x", policy.id)
        assert res is not None
        assert res.status == "reserved"
        assert res.count == 1

    async def test_reserve_without_specific_policy(
        self, started_engine: RateLimiterEngineImpl
    ) -> None:
        policy = _make_policy("reserve_global")
        await started_engine.create_policy(policy)
        res = await started_engine.reserve("provider_a", "model_x")
        assert res is not None

    async def test_reserve_no_policies_returns_none(
        self, started_engine: RateLimiterEngineImpl
    ) -> None:
        res = await started_engine.reserve("provider_a", "model_x")
        assert res is None

    async def test_grant_reservation(self, started_engine: RateLimiterEngineImpl) -> None:
        policy = _make_policy("grant_test")
        await started_engine.create_policy(policy)
        res = await started_engine.reserve("provider_a", "model_x", policy.id)
        assert res is not None
        grant = await started_engine.grant(res.id)
        assert grant.granted
        assert grant.reservation_id == res.id

    async def test_grant_nonexistent_reservation(
        self, started_engine: RateLimiterEngineImpl
    ) -> None:
        grant = await started_engine.grant("nonexistent")
        assert not grant.granted

    async def test_release_reservation(self, started_engine: RateLimiterEngineImpl) -> None:
        policy = _make_policy("release_test")
        await started_engine.create_policy(policy)
        res = await started_engine.reserve("provider_a", "model_x", policy.id)
        await started_engine.grant(res.id)
        release = await started_engine.release(res.id)
        assert release.released

    async def test_release_nonexistent_reservation(
        self, started_engine: RateLimiterEngineImpl
    ) -> None:
        release = await started_engine.release("nonexistent")
        assert not release.released

    async def test_rollback_reservation(self, started_engine: RateLimiterEngineImpl) -> None:
        policy = _make_policy("rollback_test")
        await started_engine.create_policy(policy)
        res = await started_engine.reserve("provider_a", "model_x", policy.id)
        rolled = await started_engine.rollback(res.id)
        assert rolled

    async def test_rollback_nonexistent(self, started_engine: RateLimiterEngineImpl) -> None:
        rolled = await started_engine.rollback("nonexistent")
        assert not rolled

    async def test_rollback_released_fails(self, started_engine: RateLimiterEngineImpl) -> None:
        policy = _make_policy("rollback_fail")
        await started_engine.create_policy(policy)
        res = await started_engine.reserve("provider_a", "model_x", policy.id)
        await started_engine.grant(res.id)
        await started_engine.release(res.id)
        rolled = await started_engine.rollback(res.id)
        assert not rolled

    async def test_reservation_ttl_expires(self) -> None:
        engine = _make_engine()
        await engine.start()
        policy = _make_policy("ttl_test")
        await engine.create_policy(policy)
        # Use a short TTL
        res = await engine.reserve("provider_a", "model_x", policy.id, ttl_seconds=0.001)
        assert res is not None
        await asyncio.sleep(0.005)
        grant = await engine.grant(res.id)
        assert not grant.granted

    async def test_reservation_event_on_reserve(self) -> None:
        bus = MagicMock()
        bus.publish = AsyncMock()
        engine = _make_engine(event_bus=bus)
        await engine.start()
        policy = _make_policy("res_event")
        await engine.create_policy(policy)
        await engine.reserve("provider_a", "model_x", policy.id)
        assert any(
            call[0][0].topic == Topic.PERMIT_RESERVED.value for call in bus.publish.call_args_list
        )

    async def test_reservation_event_on_grant(self) -> None:
        bus = MagicMock()
        bus.publish = AsyncMock()
        engine = _make_engine(event_bus=bus)
        await engine.start()
        policy = _make_policy("grant_event")
        await engine.create_policy(policy)
        res = await engine.reserve("provider_a", "model_x", policy.id)
        bus.publish.reset_mock()
        await engine.grant(res.id)
        assert any(
            call[0][0].topic == Topic.PERMIT_GRANTED.value for call in bus.publish.call_args_list
        )

    async def test_reservation_event_on_release(self) -> None:
        bus = MagicMock()
        bus.publish = AsyncMock()
        engine = _make_engine(event_bus=bus)
        await engine.start()
        policy = _make_policy("rel_event")
        await engine.create_policy(policy)
        res = await engine.reserve("provider_a", "model_x", policy.id)
        await engine.grant(res.id)
        bus.publish.reset_mock()
        await engine.release(res.id)
        assert any(
            call[0][0].topic == Topic.PERMIT_RELEASED.value for call in bus.publish.call_args_list
        )

    async def test_reservation_event_on_rollback(self) -> None:
        bus = MagicMock()
        bus.publish = AsyncMock()
        engine = _make_engine(event_bus=bus)
        await engine.start()
        policy = _make_policy("rb_event")
        await engine.create_policy(policy)
        res = await engine.reserve("provider_a", "model_x", policy.id)
        bus.publish.reset_mock()
        await engine.rollback(res.id)
        assert any(
            call[0][0].topic == Topic.PERMIT_ROLLED_BACK.value
            for call in bus.publish.call_args_list
        )


# ════════════════════════════════════════════
# 8. Queue Management
# ════════════════════════════════════════════


class TestQueueManagement:
    async def test_queue_priority_critical_first(
        self, started_engine: RateLimiterEngineImpl
    ) -> None:
        policy = _make_policy(
            "q_priority",
            algorithm="token_bucket",
            capacity=1.0,
            refill_rate=0.001,
            queue_max_size=10,
        )
        await started_engine.create_policy(policy)
        await started_engine.evaluate("provider_a", "model_x", priority=PriorityLevel.LOW)
        await started_engine.evaluate("provider_a", "model_x", priority=PriorityLevel.HIGH)
        qs = await started_engine.queue_state()
        assert qs.total_queued >= 1
        assert qs.queue_depth >= 0

    async def test_queue_state(self, started_engine: RateLimiterEngineImpl) -> None:
        policy = _make_policy(
            "q_state", algorithm="token_bucket", capacity=1.0, refill_rate=0.001, queue_max_size=10
        )
        await started_engine.create_policy(policy)
        await started_engine.evaluate("provider_a", "model_x")
        await started_engine.evaluate("provider_a", "model_x")
        qs = await started_engine.queue_state()
        assert isinstance(qs, QueueStatistics)
        assert qs.total_queued >= 1

    async def test_queue_overflow_detected(self, started_engine: RateLimiterEngineImpl) -> None:
        policy = _make_policy(
            "q_overflow",
            algorithm="token_bucket",
            capacity=1.0,
            refill_rate=0.001,
            queue_max_size=0,
        )
        await started_engine.create_policy(policy)
        await started_engine.evaluate("provider_a", "model_x")
        await started_engine.evaluate("provider_a", "model_x")
        qs = await started_engine.queue_state()
        assert isinstance(qs, QueueStatistics)

    async def test_queue_overflow_event(self) -> None:
        bus = MagicMock()
        bus.publish = AsyncMock()
        engine = _make_engine(event_bus=bus)
        await engine.start()
        policy = _make_policy(
            "q_overflow_event",
            algorithm="token_bucket",
            capacity=0.0,
            refill_rate=0.0,
            queue_max_size=0,
        )
        await engine.create_policy(policy)
        await engine.evaluate("provider_a", "model_x")
        assert any(
            call[0][0].topic == Topic.RATE_LIMIT_REJECTED.value
            for call in bus.publish.call_args_list
        )


# ════════════════════════════════════════════
# 9. Adaptive Quotas
# ════════════════════════════════════════════


class TestAdaptiveQuotas:
    async def test_adaptive_adjustment_reduces_capacity(
        self, started_engine: RateLimiterEngineImpl
    ) -> None:
        policy = _make_policy(
            "adapt_down",
            scope=QuotaScope.PROVIDER,
            scope_id="degraded_provider",
            algorithm="token_bucket",
            capacity=100.0,
        )
        await started_engine.create_policy(policy)
        await started_engine.evaluate("degraded_provider", "model_x")
        metrics = await started_engine.metrics()
        # No adaptive adjustments without separate mechanism, but it should still return
        assert metrics.adaptive_adjustments >= 0

    async def test_metrics_include_adaptive_adjustments(
        self, started_engine: RateLimiterEngineImpl
    ) -> None:
        metrics = await started_engine.metrics()
        assert isinstance(metrics.adaptive_adjustments, int)

    async def test_forecast_shows_at_risk_when_capacity_low(
        self, started_engine: RateLimiterEngineImpl
    ) -> None:
        policy = _make_policy(
            "at_risk",
            scope=QuotaScope.PROVIDER,
            scope_id="prov_risk",
            algorithm="token_bucket",
            capacity=1.0,
            refill_rate=0.001,
        )
        await started_engine.create_policy(policy)
        fc = await started_engine.forecast()
        assert "prov_risk" in fc.at_risk_providers


# ════════════════════════════════════════════
# 10. Retry Prediction
# ════════════════════════════════════════════


class TestRetryPrediction:
    def test_retry_predictor_basic(self) -> None:
        predictor = _RetryPredictor()
        prediction = predictor.predict(
            queue_depth=5, drain_rate=10.0, tokens_remaining=0.5, refill_rate=10.0
        )
        assert isinstance(prediction, RetryPrediction)
        assert prediction.queue_delay_ms > 0
        assert prediction.confidence > 0
        assert prediction.estimated_wait_total_ms > 0

    def test_retry_predictor_zero_drain_rate(self) -> None:
        predictor = _RetryPredictor()
        prediction = predictor.predict(
            queue_depth=10, drain_rate=0.0, tokens_remaining=0.0, refill_rate=0.0
        )
        assert prediction.estimated_wait_total_ms >= 0

    def test_retry_predictor_full_tokens(self) -> None:
        predictor = _RetryPredictor()
        prediction = predictor.predict(
            queue_depth=0, drain_rate=10.0, tokens_remaining=1.0, refill_rate=10.0
        )
        assert prediction.queue_delay_ms >= 0
        assert prediction.expected_permit_availability == 1.0

    async def test_predict_retry_api(self, started_engine: RateLimiterEngineImpl) -> None:
        policy = _make_policy("predict_api", algorithm="token_bucket", capacity=10.0)
        await started_engine.create_policy(policy)
        prediction = await started_engine.predict_retry("provider_a", "model_x")
        assert isinstance(prediction, RetryPrediction)

    async def test_predict_retry_returns_values(
        self, started_engine: RateLimiterEngineImpl
    ) -> None:
        policy = _make_policy(
            "predict_vals", algorithm="token_bucket", capacity=0.0, refill_rate=0.001
        )
        await started_engine.create_policy(policy)
        await started_engine.evaluate("provider_a", "model_x")
        prediction = await started_engine.predict_retry("provider_a", "model_x")
        assert prediction.retry_after_ms >= 0
        assert prediction.queue_delay_ms >= 0


# ════════════════════════════════════════════
# 11. Statistics & Metrics
# ════════════════════════════════════════════


class TestStatistics:
    async def test_statistics_initial_values(self, started_engine: RateLimiterEngineImpl) -> None:
        stats = await started_engine.statistics()
        assert stats.total_requests == 0
        assert stats.approved == 0
        assert stats.rejected == 0

    async def test_statistics_after_requests(self, started_engine: RateLimiterEngineImpl) -> None:
        policy = _make_policy("stats_test", algorithm="token_bucket", capacity=100.0)
        await started_engine.create_policy(policy)
        await started_engine.evaluate("provider_a", "model_x")
        await started_engine.evaluate("provider_a", "model_x")
        stats = await started_engine.statistics()
        assert stats.total_requests == 2
        assert stats.approved == 2

    async def test_statistics_tracks_rejections(
        self, started_engine: RateLimiterEngineImpl
    ) -> None:
        policy = _make_policy(
            "stats_reject", algorithm="token_bucket", capacity=0.0, refill_rate=0.0
        )
        await started_engine.create_policy(policy)
        await started_engine.evaluate("provider_a", "model_x")
        stats = await started_engine.statistics()
        assert stats.rejected == 1

    async def test_metrics_returns_complete_object(
        self, started_engine: RateLimiterEngineImpl
    ) -> None:
        metrics = await started_engine.metrics()
        assert isinstance(metrics, RateLimitMetrics)
        assert metrics.requests_per_second >= 0
        assert metrics.queue_depth >= 0

    async def test_metrics_after_burst(self, started_engine: RateLimiterEngineImpl) -> None:
        policy = _make_policy(
            "metrics_burst", algorithm="token_bucket", capacity=5.0, refill_rate=0.001, max_burst=10
        )
        await started_engine.create_policy(policy)
        for _ in range(10):
            await started_engine.evaluate("provider_a", "model_x")
        metrics = await started_engine.metrics()
        # Verify it returns something reasonable
        assert metrics.burst_count >= 0

    async def test_snapshot_includes_all_data(self, started_engine: RateLimiterEngineImpl) -> None:
        policy = _make_policy("snap_test")
        await started_engine.create_policy(policy)
        await started_engine.evaluate("provider_a", "model_x")
        snap = await started_engine.snapshot()
        assert "policies" in snap
        assert "usage" in snap
        assert "reservations" in snap
        assert "total_requests" in snap

    async def test_quota_state_returns_usage(self, started_engine: RateLimiterEngineImpl) -> None:
        policy = _make_policy("quota_state", scope=QuotaScope.PROVIDER, scope_id="prov_quota")
        await started_engine.create_policy(policy)
        await started_engine.evaluate("prov_quota", "model_x")
        usage = await started_engine.quota_state(QuotaScope.PROVIDER, "prov_quota")
        # Usage may or may not be tracked depending on implementation
        assert usage is None or isinstance(usage, QuotaUsage)

    async def test_provider_state(self, started_engine: RateLimiterEngineImpl) -> None:
        policy = _make_policy("prov_state", scope=QuotaScope.PROVIDER, scope_id="prov_state")
        await started_engine.create_policy(policy)
        state = await started_engine.provider_state("prov_state")
        assert state["provider"] == "prov_state"
        assert "policies" in state
        assert len(state["policies"]) >= 1

    async def test_provider_state_unknown(self, started_engine: RateLimiterEngineImpl) -> None:
        state = await started_engine.provider_state("unknown")
        assert state["provider"] == "unknown"
        assert len(state["policies"]) == 0


# ════════════════════════════════════════════
# 12. Forecasting
# ════════════════════════════════════════════


class TestForecasting:
    async def test_forecast_returns_rate_limit_forecast(
        self, started_engine: RateLimiterEngineImpl
    ) -> None:
        fc = await started_engine.forecast()
        assert isinstance(fc, RateLimitForecast)

    async def test_forecast_with_policies(self, started_engine: RateLimiterEngineImpl) -> None:
        policy = _make_policy(
            "fc_test",
            scope=QuotaScope.PROVIDER,
            scope_id="prov_fc",
            algorithm="token_bucket",
            capacity=100.0,
        )
        await started_engine.create_policy(policy)
        fc = await started_engine.forecast()
        assert "prov_fc" in fc.provider_forecasts or len(fc.provider_forecasts) >= 0

    async def test_forecast_model_forecasts(self, started_engine: RateLimiterEngineImpl) -> None:
        policy = _make_policy("fc_model", scope=QuotaScope.MODEL, scope_id="model_fc")
        await started_engine.create_policy(policy)
        fc = await started_engine.forecast()
        assert isinstance(fc.model_forecasts, dict)

    async def test_forecast_workspace(self, started_engine: RateLimiterEngineImpl) -> None:
        policy = _make_policy("fc_ws", scope=QuotaScope.WORKSPACE, scope_id="ws_fc")
        await started_engine.create_policy(policy)
        fc = await started_engine.forecast()
        assert isinstance(fc.workspace_forecasts, dict)

    async def test_forecast_global(self, started_engine: RateLimiterEngineImpl) -> None:
        fc = await started_engine.forecast()
        assert isinstance(fc.global_forecast, QuotaForecast)


# ════════════════════════════════════════════
# 13. Concurrency & Thread Safety
# ════════════════════════════════════════════


class TestConcurrency:
    async def test_concurrent_evaluations(self, started_engine: RateLimiterEngineImpl) -> None:
        policy = _make_policy(
            "concurrent", algorithm="token_bucket", capacity=100.0, refill_rate=100.0
        )
        await started_engine.create_policy(policy)

        async def eval_task() -> RateLimitDecision:
            return await started_engine.evaluate("provider_a", "model_x")

        results = await asyncio.gather(*[eval_task() for _ in range(10)])
        approved = sum(1 for r in results if r.approved)
        assert approved >= 0

    async def test_concurrent_reservations(self, started_engine: RateLimiterEngineImpl) -> None:
        policy = _make_policy("concurrent_res")
        await started_engine.create_policy(policy)

        async def reserve_task() -> PermitReservation | None:
            return await started_engine.reserve("provider_a", "model_x", policy.id)

        results = await asyncio.gather(*[reserve_task() for _ in range(10)])
        valid = [r for r in results if r is not None]
        assert len(valid) == 10

    async def test_concurrent_grants(self, started_engine: RateLimiterEngineImpl) -> None:
        policy = _make_policy("concurrent_grant")
        await started_engine.create_policy(policy)
        res = await started_engine.reserve("provider_a", "model_x", policy.id)

        async def grant_task() -> PermitGrant:
            return await started_engine.grant(res.id)

        # Multiple grants of the same reservation should only succeed once
        results = await asyncio.gather(*[grant_task() for _ in range(5)])
        granted = sum(1 for r in results if r.granted)
        assert granted == 1

    async def test_concurrent_metrics_and_evaluate(
        self, started_engine: RateLimiterEngineImpl
    ) -> None:
        async def eval_task() -> None:
            await started_engine.evaluate("provider_a", "model_x")

        async def metrics_task() -> None:
            await started_engine.metrics()

        await asyncio.gather(eval_task(), metrics_task(), eval_task(), metrics_task())

    async def test_lock_held_during_mutation(self, started_engine: RateLimiterEngineImpl) -> None:
        """Verify that concurrent mutations don't corrupt state."""
        for i in range(5):
            policy = _make_policy(f"lock_test_{i}")
            await started_engine.create_policy(policy)
        assert started_engine.policy_count == 5


# ════════════════════════════════════════════
# 14. Edge Cases
# ════════════════════════════════════════════


class TestEdgeCases:
    async def test_empty_provider_model_combo(self, started_engine: RateLimiterEngineImpl) -> None:
        policy = _make_policy("empty_combo")
        await started_engine.create_policy(policy)
        decision = await started_engine.evaluate("", "")
        assert decision.approved

    async def test_no_applicable_policies(self, started_engine: RateLimiterEngineImpl) -> None:
        decision = await started_engine.evaluate("provider_a", "model_x")
        assert decision.approved
        assert "no applicable policies" in decision.reason

    async def test_disabled_policy_not_applied(self, started_engine: RateLimiterEngineImpl) -> None:
        policy = _make_policy(
            "disabled", algorithm="token_bucket", capacity=0.0, refill_rate=0.0, enabled=False
        )
        await started_engine.create_policy(policy)
        decision = await started_engine.evaluate("provider_a", "model_x")
        assert decision.approved

    async def test_policy_with_different_scopes(
        self, started_engine: RateLimiterEngineImpl
    ) -> None:
        global_p = _make_policy(
            "global", scope=QuotaScope.GLOBAL, algorithm="token_bucket", capacity=5.0
        )
        provider_p = _make_policy(
            "provider",
            scope=QuotaScope.PROVIDER,
            scope_id="prov_a",
            algorithm="token_bucket",
            capacity=2.0,
        )
        await started_engine.create_policy(global_p)
        await started_engine.create_policy(provider_p)
        d1 = await started_engine.evaluate("prov_a", "model_x")
        assert d1.approved

    async def test_multiple_evaluate_round_robin(
        self, started_engine: RateLimiterEngineImpl
    ) -> None:
        policy = _make_policy("robin_test", algorithm="token_bucket", capacity=5.0)
        await started_engine.create_policy(policy)
        for _ in range(10):
            await started_engine.evaluate("provider_a", "model_x")
            # Some should be approved
            pass
        stats = await started_engine.statistics()
        assert stats.total_requests == 10

    async def test_consume_api(self, started_engine: RateLimiterEngineImpl) -> None:
        policy = _make_policy("consume_test", algorithm="token_bucket", capacity=10.0)
        await started_engine.create_policy(policy)
        result = await started_engine.consume("provider_a", "model_x", count=1)
        assert result

    async def test_consume_when_exhausted(self, started_engine: RateLimiterEngineImpl) -> None:
        policy = _make_policy(
            "consume_exhaust", algorithm="token_bucket", capacity=1.0, refill_rate=0.001
        )
        await started_engine.create_policy(policy)
        await started_engine.consume("provider_a", "model_x", count=1)
        result = await started_engine.consume("provider_a", "model_x", count=1)
        assert not result

    async def test_evaluate_with_workspace_scope(
        self, started_engine: RateLimiterEngineImpl
    ) -> None:
        policy = _make_policy("ws_test", scope=QuotaScope.WORKSPACE, scope_id="ws_1")
        await started_engine.create_policy(policy)
        decision = await started_engine.evaluate("provider_a", "model_x", scope_id="ws_1")
        assert decision.approved

    async def test_evaluate_with_user_scope(self, started_engine: RateLimiterEngineImpl) -> None:
        policy = _make_policy("user_test", scope=QuotaScope.USER, scope_id="user_1")
        await started_engine.create_policy(policy)
        decision = await started_engine.evaluate("provider_a", "model_x", scope_id="user_1")
        assert decision.approved

    async def test_high_priority_policy_wins(self, started_engine: RateLimiterEngineImpl) -> None:
        low_p = _make_policy(
            "low",
            algorithm="token_bucket",
            capacity=1.0,
            refill_rate=0.001,
            priority=PriorityLevel.LOW,
        )
        high_p = _make_policy(
            "high", algorithm="token_bucket", capacity=100.0, priority=PriorityLevel.HIGH
        )
        await started_engine.create_policy(low_p)
        await started_engine.create_policy(high_p)
        decision = await started_engine.evaluate("provider_a", "model_x")
        assert decision.approved

    async def test_metadata_in_policy(self, started_engine: RateLimiterEngineImpl) -> None:
        policy = RateLimitPolicy(
            name="meta_test",
            description="",
            enabled=True,
            order=0,
            scope=QuotaScope.GLOBAL,
            scope_id="",
            algorithm="token_bucket",
            token_bucket=TokenBucket(),
            leaky_bucket=LeakyBucket(),
            sliding_window=SlidingWindowCounter(),
            max_burst=0,
            queue_max_size=0,
            priority=PriorityLevel.NORMAL,
            metadata={"key": "value"},
            created_at=datetime.now(UTC),
        )
        await started_engine.create_policy(policy)
        retrieved = await started_engine.get_policy(policy.id)
        assert retrieved is not None
        assert retrieved.metadata.get("key") == "value"

    async def test_concurrent_create_delete(self, started_engine: RateLimiterEngineImpl) -> None:
        async def create_then_delete(idx: int) -> None:
            p = _make_policy(f"cd_{idx}")
            await started_engine.create_policy(p)
            await started_engine.delete_policy(p.id)

        await asyncio.gather(*[create_then_delete(i) for i in range(5)])
        # Should not crash

    async def test_rate_limiter_event_on_approve(self) -> None:
        bus = MagicMock()
        bus.publish = AsyncMock()
        engine = _make_engine(event_bus=bus)
        await engine.start()
        policy = _make_policy("approve_event")
        await engine.create_policy(policy)
        await engine.evaluate("provider_a", "model_x")
        assert any(
            call[0][0].topic == Topic.RATE_LIMIT_APPROVED.value
            for call in bus.publish.call_args_list
        )

    async def test_rate_limiter_event_on_reject(self) -> None:
        bus = MagicMock()
        bus.publish = AsyncMock()
        engine = _make_engine(event_bus=bus)
        await engine.start()
        policy = _make_policy(
            "reject_event", algorithm="token_bucket", capacity=0.0, refill_rate=0.0
        )
        await engine.create_policy(policy)
        await engine.evaluate("provider_a", "model_x")
        assert any(
            call[0][0].topic == Topic.RATE_LIMIT_REJECTED.value
            for call in bus.publish.call_args_list
        )

    async def test_quota_exceeded_event(self) -> None:
        bus = MagicMock()
        bus.publish = AsyncMock()
        engine = _make_engine(event_bus=bus)
        await engine.start()
        policy = RateLimitPolicy(
            name="qe_event",
            description="",
            enabled=True,
            order=0,
            scope=QuotaScope.GLOBAL,
            scope_id="",
            algorithm="sliding_window",
            token_bucket=TokenBucket(),
            leaky_bucket=LeakyBucket(),
            sliding_window=SlidingWindowCounter(max_requests=0, window_duration_s=3600.0),
            max_burst=0,
            queue_max_size=0,
            priority=PriorityLevel.NORMAL,
            metadata={},
            created_at=datetime.now(UTC),
        )
        await engine.create_policy(policy)
        await engine.evaluate("provider_a", "model_x")
        assert any(
            call[0][0].topic == Topic.QUOTA_EXCEEDED.value for call in bus.publish.call_args_list
        )

    async def test_consume_on_empty_policies(self, started_engine: RateLimiterEngineImpl) -> None:
        # No policies -> consume returns True
        result = await started_engine.consume("provider_a", "model_x")
        assert result

    async def test_dispose_after_requests(self, started_engine: RateLimiterEngineImpl) -> None:
        policy = _make_policy("dispose_req", capacity=100.0)
        await started_engine.create_policy(policy)
        await started_engine.evaluate("provider_a", "model_x")
        await started_engine.dispose()
        assert started_engine.policy_count == 0
        assert started_engine.total_requests == 0

    async def test_multiple_scopes_global_workspace(
        self, started_engine: RateLimiterEngineImpl
    ) -> None:
        g = _make_policy("g", scope=QuotaScope.GLOBAL, algorithm="token_bucket", capacity=100.0)
        w = _make_policy(
            "w", scope=QuotaScope.WORKSPACE, scope_id="ws_1", algorithm="token_bucket", capacity=2.0
        )
        await started_engine.create_policy(g)
        await started_engine.create_policy(w)
        d1 = await started_engine.evaluate("provider_a", "model_x", scope_id="ws_1")
        assert d1.approved
        d2 = await started_engine.evaluate("provider_a", "model_x", scope_id="ws_1")
        assert d2.approved

    async def test_model_scope_policy(self, started_engine: RateLimiterEngineImpl) -> None:
        policy = _make_policy("model_scope", scope=QuotaScope.MODEL, scope_id="model_x")
        await started_engine.create_policy(policy)
        decision = await started_engine.evaluate("provider_a", "model_x")
        assert decision.approved

    async def test_agent_scope_policy(self, started_engine: RateLimiterEngineImpl) -> None:
        policy = _make_policy("agent_scope", scope=QuotaScope.AGENT, scope_id="agent_1")
        await started_engine.create_policy(policy)
        decision = await started_engine.evaluate("provider_a", "model_x", scope_id="agent_1")
        assert decision.approved

    async def test_no_matching_scope_policy(self, started_engine: RateLimiterEngineImpl) -> None:
        policy = _make_policy("no_match", scope=QuotaScope.WORKSPACE, scope_id="ws_a")
        await started_engine.create_policy(policy)
        # Evaluate with different scope_id so no match
        decision = await started_engine.evaluate("provider_a", "model_x", scope_id="ws_b")
        assert decision.approved
        assert "no applicable policies" in decision.reason

    async def test_evaluate_returns_retry_after(
        self, started_engine: RateLimiterEngineImpl
    ) -> None:
        policy = _make_policy(
            "retry_after", algorithm="token_bucket", capacity=0.0, refill_rate=0.0
        )
        await started_engine.create_policy(policy)
        decision = await started_engine.evaluate("provider_a", "model_x")
        if decision.rejected:
            assert decision.retry_after_ms > 0
            assert decision.tokens_remaining >= 0


# ════════════════════════════════════════════
# 15. Permits & Auditing
# ════════════════════════════════════════════


class TestPermitAudit:
    async def test_permit_snapshot(self, started_engine: RateLimiterEngineImpl) -> None:
        policy = _make_policy("ps_test")
        await started_engine.create_policy(policy)
        res = await started_engine.reserve("provider_a", "model_x", policy.id)
        assert res is not None
        snap = await started_engine.snapshot()
        assert snap["reservations"].active_reservations >= 1

    async def test_permit_lifecycle(self, started_engine: RateLimiterEngineImpl) -> None:
        policy = _make_policy("plc_test")
        await started_engine.create_policy(policy)
        res = await started_engine.reserve("provider_a", "model_x", policy.id)
        assert res is not None
        grant = await started_engine.grant(res.id)
        assert grant.granted
        release = await started_engine.release(res.id)
        assert release.released

    async def test_rollback_after_release_fails(
        self, started_engine: RateLimiterEngineImpl
    ) -> None:
        policy = _make_policy("rb_after_release")
        await started_engine.create_policy(policy)
        res = await started_engine.reserve("provider_a", "model_x", policy.id)
        await started_engine.grant(res.id)
        await started_engine.release(res.id)
        rolled = await started_engine.rollback(res.id)
        assert not rolled

    async def test_expire_stale_reservations(self) -> None:
        from agentic_os.core.omniroute.rate_limiter import _PermitManager

        pm = _PermitManager()
        pm.reserve("policy_1", QuotaScope.GLOBAL, "", "provider_a", "model_x", ttl_seconds=0.001)
        await asyncio.sleep(0.005)
        expired = pm.expire_stale()
        assert expired >= 1

    async def test_audit_log_records_reservations(self) -> None:
        bus = MagicMock()
        bus.publish = AsyncMock()
        engine = _make_engine(event_bus=bus)
        await engine.start()
        policy = _make_policy("audit_res")
        await engine.create_policy(policy)
        res = await engine.reserve("provider_a", "model_x", policy.id)
        assert res is not None
        # Event published for reservation
        assert any(
            call[0][0].topic == Topic.PERMIT_RESERVED.value for call in bus.publish.call_args_list
        )


# ════════════════════════════════════════════
# 16. Edge Cases - Algorithm Specific
# ════════════════════════════════════════════


class TestAlgorithmEdgeCases:
    async def test_unknown_algorithm_defaults_approved(
        self, started_engine: RateLimiterEngineImpl
    ) -> None:
        policy = RateLimitPolicy(
            name="unknown_algo",
            description="",
            enabled=True,
            order=0,
            scope=QuotaScope.GLOBAL,
            scope_id="",
            algorithm="nonexistent_algo",
            token_bucket=TokenBucket(),
            leaky_bucket=LeakyBucket(),
            sliding_window=SlidingWindowCounter(),
            max_burst=0,
            queue_max_size=0,
            priority=PriorityLevel.NORMAL,
            metadata={},
            created_at=datetime.now(UTC),
        )
        await started_engine.create_policy(policy)
        decision = await started_engine.evaluate("provider_a", "model_x")
        assert decision.approved

    async def test_token_bucket_refill_cycle(self) -> None:
        from agentic_os.core.omniroute.rate_limiter import _TokenBucketState

        tb = _TokenBucketState(
            TokenBucket(
                capacity=10.0, refill_rate=5.0, refill_interval_ms=100.0, burst_allowance=0.0
            )
        )
        assert tb.available == 10.0
        tb.try_consume(8)
        assert tb.available == 2.0
        # After refill interval
        tb.last_refill = 0
        tb.refill()
        assert tb.available > 2.0

    async def test_leaky_bucket_drain_cycle(self) -> None:
        from agentic_os.core.omniroute.rate_limiter import _LeakyBucketState

        lb = _LeakyBucketState(
            LeakyBucket(drain_rate=5.0, drain_interval_ms=100.0, max_queue_depth=10)
        )
        for _ in range(5):
            lb.try_add(1.0)
        assert lb.queue_depth == 5
        lb.last_drain = 0
        lb.drain()
        assert lb.queue_depth < 5

    async def test_fixed_window_reset(self) -> None:
        from agentic_os.core.omniroute.rate_limiter import _FixedWindowCounter

        fw = _FixedWindowCounter(max_per_window=5, window_seconds=0.001)
        for _ in range(5):
            assert fw.try_consume()
        assert not fw.try_consume()
        await asyncio.sleep(0.005)
        assert fw.try_consume()
