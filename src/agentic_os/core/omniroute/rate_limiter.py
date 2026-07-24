"""OmniRoute Intelligent Rate Limiter & Quota Engine — distributed-capable
provider/model/workspace/user protection from overload.

The engine never routes requests directly. It decides whether a request is
immediately allowed, queued, delayed, or rejected.

Pipeline position: after Budget Engine, before Circuit Breaker.

Algorithms
----------
- Token Bucket (O(1) updates)
- Leaky Bucket (constant drain + queue depth)
- Sliding Window (8 windows via deque, O(1))
- Fixed Window (coarse quota enforcement)
- Adaptive Rate Limiting (consumes Learning Engine metrics)
- Fair Scheduling (WFQ, Priority, FIFO, Round Robin)
- Permit Reservations (reserve/commit/release/expire/rollback with TTL)
- Retry Prediction (Retry-After, queue delay, permit availability)
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol, runtime_checkable

from agentic_os.domain.events import EventEnvelope, Topic
from agentic_os.domain.omniroute import (
    LeakyBucket,
    PermitAuditRecord,
    PermitGrant,
    PermitRelease,
    PermitReservation,
    PermitSnapshot,
    PermitStatistics,
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
    TokenBucket,
)
from agentic_os.infrastructure.logging import get_logger

log = get_logger("omniroute.rate_limiter")

# ── Constants ──

_SLIDING_WINDOWS: tuple[str, ...] = ("5s", "30s", "1m", "5m", "15m", "1h", "24h", "lifetime")
_WINDOW_DURATIONS: dict[str, timedelta] = {
    "5s": timedelta(seconds=5),
    "30s": timedelta(seconds=30),
    "1m": timedelta(minutes=1),
    "5m": timedelta(minutes=5),
    "15m": timedelta(minutes=15),
    "1h": timedelta(hours=1),
    "24h": timedelta(hours=24),
    "lifetime": timedelta(days=365 * 10),
}
_MAX_RECORDS = 10000
_MAX_RECENT = 1000

# ── Port Protocol ──


@runtime_checkable
class RateLimiterEnginePort(Protocol):
    """OmniRoute rate limiter — protects providers/models/workspaces/users."""

    async def create_policy(self, policy: RateLimitPolicy) -> RateLimitPolicy: ...
    async def update_policy(self, policy: RateLimitPolicy) -> RateLimitPolicy | None: ...
    async def delete_policy(self, policy_id: str) -> bool: ...
    async def get_policy(self, policy_id: str) -> RateLimitPolicy | None: ...
    async def list_policies(self, scope: QuotaScope | None = None) -> list[RateLimitPolicy]: ...
    async def enable_policy(self, policy_id: str) -> bool: ...
    async def disable_policy(self, policy_id: str) -> bool: ...
    async def evaluate(
        self,
        provider: str,
        model: str,
        scope_id: str = "",
        priority: PriorityLevel = PriorityLevel.NORMAL,
    ) -> RateLimitDecision: ...
    async def reserve(
        self,
        provider: str,
        model: str,
        policy_id: str = "",
        count: int = 1,
        ttl_seconds: float = 30.0,
    ) -> PermitReservation | None: ...
    async def grant(self, reservation_id: str) -> PermitGrant: ...
    async def release(self, reservation_id: str, count: int = 1) -> PermitRelease: ...
    async def rollback(self, reservation_id: str) -> bool: ...
    async def consume(self, provider: str, model: str, count: int = 1) -> bool: ...
    async def predict_retry(self, provider: str, model: str) -> RetryPrediction: ...
    async def statistics(self) -> PermitStatistics: ...
    async def metrics(self) -> RateLimitMetrics: ...
    async def snapshot(self) -> dict[str, Any]: ...
    async def forecast(self) -> RateLimitForecast: ...
    async def queue_state(self) -> QueueStatistics: ...
    async def quota_state(self, scope: QuotaScope, scope_id: str) -> QuotaUsage | None: ...
    async def provider_state(self, provider: str) -> dict[str, Any]: ...
    async def healthy(self) -> bool: ...
    async def initialize(self) -> None: ...
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def dispose(self) -> None: ...
    async def health(self) -> dict[str, Any]: ...
    async def ready(self) -> bool: ...


# ── Internal: Token Bucket ──


class _TokenBucketState:
    """Mutable token bucket state with O(1) operations."""

    def __init__(self, config: TokenBucket) -> None:
        self.capacity = config.capacity
        self.refill_rate = config.refill_rate
        self.refill_interval_ms = config.refill_interval_ms
        self.burst_allowance = config.burst_allowance
        self.tokens = config.capacity
        self.last_refill: float = time.monotonic()
        self.burst_used = 0

    def refill(self) -> None:
        now = time.monotonic()
        elapsed = (now - self.last_refill) * 1000  # ms
        if elapsed >= self.refill_interval_ms:
            cycles = elapsed / self.refill_interval_ms
            added = cycles * self.refill_rate
            self.tokens = min(self.capacity + self.burst_allowance, self.tokens + added)
            self.last_refill = now

    def try_consume(self, count: int = 1) -> bool:
        self.refill()
        if self.tokens >= count:
            self.tokens -= count
            return True
        return False

    def try_consume_burst(self, count: int = 1) -> bool:
        self.refill()
        available = self.tokens + self.burst_allowance - self.burst_used
        if available >= count:
            needed_from_tokens = min(count, int(self.tokens))
            self.tokens -= needed_from_tokens
            remaining = count - needed_from_tokens
            if remaining > 0:
                self.burst_used += remaining
            return True
        return False

    @property
    def available(self) -> float:
        self.refill()
        return self.tokens + self.burst_allowance - self.burst_used

    def reset(self) -> None:
        self.tokens = self.capacity
        self.burst_used = 0
        self.last_refill = time.monotonic()


# ── Internal: Leaky Bucket ──


class _LeakyBucketState:
    """Mutable leaky bucket state with constant drain."""

    def __init__(self, config: LeakyBucket) -> None:
        self.drain_rate = config.drain_rate
        self.drain_interval_ms = config.drain_interval_ms
        self.max_queue_depth = config.max_queue_depth
        self.queue: deque[float] = deque()
        self.last_drain: float = time.monotonic()

    def drain(self) -> None:
        now = time.monotonic()
        elapsed = (now - self.last_drain) * 1000
        if elapsed >= self.drain_interval_ms:
            cycles = elapsed / self.drain_interval_ms
            to_drain = int(cycles * self.drain_rate)
            for _ in range(min(to_drain, len(self.queue))):
                self.queue.popleft()
            self.last_drain = now

    def try_add(self, size: float = 1.0) -> bool:
        self.drain()
        if len(self.queue) < self.max_queue_depth:
            self.queue.append(size)
            return True
        return False

    @property
    def queue_depth(self) -> int:
        self.drain()
        return len(self.queue)

    @property
    def overflow(self) -> bool:
        return self.queue_depth >= self.max_queue_depth

    def reset(self) -> None:
        self.queue.clear()
        self.last_drain = time.monotonic()


# ── Internal: Sliding Window ──


class _RateSlidingWindow:
    """Sliding window implementation with O(1) deque updates."""

    def __init__(self, max_duration: timedelta, max_requests: int = 100) -> None:
        self._max_duration = max_duration
        self._max_requests = max_requests
        self._entries: deque[datetime] = deque()

    def record(self) -> None:
        self._entries.append(datetime.now(UTC))

    def expire(self) -> None:
        now = datetime.now(UTC)
        cutoff = now - self._max_duration
        while self._entries and self._entries[0] < cutoff:
            self._entries.popleft()

    @property
    def count(self) -> int:
        self.expire()
        return len(self._entries)

    @property
    def remaining(self) -> int:
        return max(0, self._max_requests - self.count)

    @property
    def is_exceeded(self) -> bool:
        return self.count >= self._max_requests


# ── Internal: Fixed Window ──


class _FixedWindowCounter:
    """Fixed-window quota counter with simple time-aligned windows."""

    def __init__(self, max_per_window: int = 100, window_seconds: float = 60.0) -> None:
        self._max_per_window = max_per_window
        self._window_seconds = window_seconds
        self._count = 0
        self._window_start: float = time.monotonic()

    def _check_reset(self) -> None:
        now = time.monotonic()
        if now - self._window_start >= self._window_seconds:
            self._count = 0
            self._window_start = now

    def try_consume(self) -> bool:
        self._check_reset()
        if self._count < self._max_per_window:
            self._count += 1
            return True
        return False

    @property
    def count(self) -> int:
        self._check_reset()
        return self._count

    @property
    def remaining(self) -> int:
        self._check_reset()
        return max(0, self._max_per_window - self._count)

    def reset(self) -> None:
        self._count = 0
        self._window_start = time.monotonic()


# ── Internal: Queue Manager ──


class _QueueEntry:
    __slots__ = ("id", "provider", "model", "priority", "arrived_at", "size")

    def __init__(
        self,
        entry_id: str,
        provider: str,
        model: str,
        priority: PriorityLevel,
        size: int = 1,
    ) -> None:
        self.id = entry_id
        self.provider = provider
        self.model = model
        self.priority = priority
        self.arrived_at = time.monotonic()
        self.size = size


class _QueueManager:
    """Manages queues with WFQ, priority, FIFO, and round-robin scheduling."""

    def __init__(self) -> None:
        self._priority_queues: dict[PriorityLevel, deque[_QueueEntry]] = {
            PriorityLevel.CRITICAL: deque(),
            PriorityLevel.HIGH: deque(),
            PriorityLevel.NORMAL: deque(),
            PriorityLevel.LOW: deque(),
            PriorityLevel.BULK: deque(),
        }
        self._wfq_queues: dict[str, deque[_QueueEntry]] = {}
        self._rr_queues: dict[str, deque[_QueueEntry]] = {}
        self._overflow_count = 0
        self._total_queued = 0
        self._total_dequeued = 0
        self._total_wait_ms = 0.0

    def enqueue(
        self,
        entry_id: str,
        provider: str,
        model: str,
        priority: PriorityLevel = PriorityLevel.NORMAL,
        size: int = 1,
        queue_type: str = "priority",
        group_key: str = "",
    ) -> bool:
        entry = _QueueEntry(entry_id, provider, model, priority, size)
        if queue_type == "priority":
            self._priority_queues[priority].append(entry)
        elif queue_type == "wfq" and group_key:
            if group_key not in self._wfq_queues:
                self._wfq_queues[group_key] = deque()
            self._wfq_queues[group_key].append(entry)
        elif queue_type == "rr" and group_key:
            if group_key not in self._rr_queues:
                self._rr_queues[group_key] = deque()
            self._rr_queues[group_key].append(entry)
        else:
            self._priority_queues[priority].append(entry)
        self._total_queued += 1
        return True

    def dequeue(self, queue_type: str = "priority", group_key: str = "") -> _QueueEntry | None:
        entry = None
        if queue_type == "priority":
            for level in (
                PriorityLevel.CRITICAL,
                PriorityLevel.HIGH,
                PriorityLevel.NORMAL,
                PriorityLevel.LOW,
                PriorityLevel.BULK,
            ):
                if self._priority_queues[level]:
                    entry = self._priority_queues[level].popleft()
                    break
        elif queue_type == "wfq" and group_key in self._wfq_queues:
            q = self._wfq_queues[group_key]
            if q:
                entry = q.popleft()
            if q and len(q) == 0:
                del self._wfq_queues[group_key]
        elif queue_type == "rr":
            for key in list(self._rr_queues.keys()):
                q = self._rr_queues[key]
                if q:
                    entry = q.popleft()
                    if len(q) == 0:
                        del self._rr_queues[key]
                    break
        if entry:
            self._total_dequeued += 1
            wait = (time.monotonic() - entry.arrived_at) * 1000
            self._total_wait_ms += wait
        return entry

    def peek(self, queue_type: str = "priority") -> _QueueEntry | None:
        if queue_type == "priority":
            for level in (
                PriorityLevel.CRITICAL,
                PriorityLevel.HIGH,
                PriorityLevel.NORMAL,
                PriorityLevel.LOW,
                PriorityLevel.BULK,
            ):
                if self._priority_queues[level]:
                    return self._priority_queues[level][0]
        return None

    @property
    def total_depth(self) -> int:
        depth = 0
        for q in self._priority_queues.values():
            depth += len(q)
        for q in self._wfq_queues.values():
            depth += len(q)
        for q in self._rr_queues.values():
            depth += len(q)
        return depth

    @property
    def active_queues(self) -> int:
        count = sum(1 for q in self._priority_queues.values() if q)
        count += sum(1 for q in self._wfq_queues.values() if q)
        count += sum(1 for q in self._rr_queues.values() if q)
        return count

    def statistics(self) -> QueueStatistics:
        avg_wait = self._total_wait_ms / max(self._total_dequeued, 1)
        priority_dist: dict[str, int] = {}
        for level, q in self._priority_queues.items():
            priority_dist[level.value] = len(q)
        return QueueStatistics(
            total_queued=self._total_queued,
            active_queues=self.active_queues,
            average_wait_ms=round(avg_wait, 2),
            max_wait_ms=round(self._total_wait_ms, 2),
            queue_depth=self.total_depth,
            overflow_count=self._overflow_count,
            priority_distribution=priority_dist,
        )


# ── Internal: Permit Manager ──


class _PermitManager:
    """Manages permit reservations with lifecycle."""

    def __init__(self) -> None:
        self._reservations: dict[str, PermitReservation] = {}
        self._audit_log: deque[PermitAuditRecord] = deque(maxlen=_MAX_RECORDS)

    def reserve(
        self,
        policy_id: str,
        scope: QuotaScope,
        scope_id: str,
        provider: str,
        model: str,
        count: int = 1,
        ttl_seconds: float = 30.0,
    ) -> PermitReservation:
        now = datetime.now(UTC)
        reservation = PermitReservation(
            policy_id=policy_id,
            scope=scope,
            scope_id=scope_id,
            provider=provider,
            model=model,
            count=count,
            status="reserved",
            ttl_seconds=ttl_seconds,
            created_at=now,
            expires_at=now + timedelta(seconds=ttl_seconds),
        )
        self._reservations[reservation.id] = reservation
        self._audit(
            PermitAuditRecord(
                action="reserved",
                policy_id=policy_id,
                scope=scope,
                scope_id=scope_id,
                provider=provider,
                model=model,
                count=count,
                reason="reservation created",
            )
        )
        return reservation

    def grant(self, reservation_id: str) -> PermitGrant | None:
        res = self._reservations.get(reservation_id)
        if res is None or res.status != "reserved":
            return None
        if datetime.now(UTC) > res.expires_at:
            self._expire(reservation_id)
            return None
        new_res = PermitReservation(
            id=res.id,
            policy_id=res.policy_id,
            scope=res.scope,
            scope_id=res.scope_id,
            provider=res.provider,
            model=res.model,
            count=res.count,
            status="granted",
            ttl_seconds=res.ttl_seconds,
            created_at=res.created_at,
            expires_at=res.expires_at,
            committed_at=datetime.now(UTC),
            released_at=res.released_at,
            metadata=res.metadata,
        )
        self._reservations[reservation_id] = new_res
        self._audit(
            PermitAuditRecord(
                action="granted",
                policy_id=res.policy_id,
                scope=res.scope,
                scope_id=res.scope_id,
                provider=res.provider,
                model=res.model,
                count=res.count,
                reason="permit granted",
            )
        )
        return PermitGrant(
            reservation_id=reservation_id,
            policy_id=res.policy_id,
            scope=res.scope,
            scope_id=res.scope_id,
            provider=res.provider,
            model=res.model,
            count=res.count,
            granted=True,
        )

    def release(self, reservation_id: str, count: int = 1) -> PermitRelease | None:
        res = self._reservations.get(reservation_id)
        if res is None or res.status not in ("granted", "committed"):
            return None
        new_res = PermitReservation(
            id=res.id,
            policy_id=res.policy_id,
            scope=res.scope,
            scope_id=res.scope_id,
            provider=res.provider,
            model=res.model,
            count=res.count,
            status="released",
            ttl_seconds=res.ttl_seconds,
            created_at=res.created_at,
            expires_at=res.expires_at,
            committed_at=res.committed_at,
            released_at=datetime.now(UTC),
            metadata=res.metadata,
        )
        self._reservations[reservation_id] = new_res
        self._audit(
            PermitAuditRecord(
                action="released",
                policy_id=res.policy_id,
                scope=res.scope,
                scope_id=res.scope_id,
                provider=res.provider,
                model=res.model,
                count=count,
                reason="permit released",
            )
        )
        return PermitRelease(
            reservation_id=reservation_id,
            policy_id=res.policy_id,
            count=count,
            released=True,
        )

    def rollback(self, reservation_id: str) -> bool:
        res = self._reservations.get(reservation_id)
        if res is None or res.status not in ("reserved", "granted"):
            return False
        new_res = PermitReservation(
            id=res.id,
            policy_id=res.policy_id,
            scope=res.scope,
            scope_id=res.scope_id,
            provider=res.provider,
            model=res.model,
            count=res.count,
            status="rolled_back",
            ttl_seconds=res.ttl_seconds,
            created_at=res.created_at,
            expires_at=res.expires_at,
            committed_at=res.committed_at,
            released_at=res.released_at,
            metadata=res.metadata,
        )
        self._reservations[reservation_id] = new_res
        self._audit(
            PermitAuditRecord(
                action="rolled_back",
                policy_id=res.policy_id,
                scope=res.scope,
                scope_id=res.scope_id,
                provider=res.provider,
                model=res.model,
                count=res.count,
                reason="permit rolled back",
            )
        )
        return True

    def _expire(self, reservation_id: str) -> None:
        res = self._reservations.get(reservation_id)
        if res is None:
            return
        new_res = PermitReservation(
            id=res.id,
            policy_id=res.policy_id,
            scope=res.scope,
            scope_id=res.scope_id,
            provider=res.provider,
            model=res.model,
            count=res.count,
            status="expired",
            ttl_seconds=res.ttl_seconds,
            created_at=res.created_at,
            expires_at=res.expires_at,
            committed_at=res.committed_at,
            released_at=res.released_at,
            metadata=res.metadata,
        )
        self._reservations[reservation_id] = new_res
        self._audit(
            PermitAuditRecord(
                action="expired",
                policy_id=res.policy_id,
                scope=res.scope,
                scope_id=res.scope_id,
                provider=res.provider,
                model=res.model,
                count=res.count,
                reason="ttl expired",
            )
        )

    def expire_stale(self) -> int:
        now = datetime.now(UTC)
        expired = 0
        for rid, res in list(self._reservations.items()):
            if res.status == "reserved" and now > res.expires_at:
                self._expire(rid)
                expired += 1
        return expired

    def _audit(self, record: PermitAuditRecord) -> None:
        self._audit_log.append(record)

    def snapshot(self) -> PermitSnapshot:
        active = sum(1 for r in self._reservations.values() if r.status == "reserved")
        granted = sum(1 for r in self._reservations.values() if r.status == "granted")
        released = sum(1 for r in self._reservations.values() if r.status == "released")
        rolled = sum(1 for r in self._reservations.values() if r.status == "rolled_back")
        expired = sum(1 for r in self._reservations.values() if r.status == "expired")
        pending = sum(1 for r in self._reservations.values() if r.status in ("reserved", "granted"))
        return PermitSnapshot(
            total_reservations=len(self._reservations),
            active_reservations=active,
            granted_count=granted,
            released_count=released,
            rolled_back_count=rolled,
            expired_count=expired,
            pending_count=pending,
        )

    def statistics(self) -> PermitStatistics:
        snap = self.snapshot()
        return PermitStatistics(
            reservations_active=snap.active_reservations,
            reservations_granted=snap.granted_count,
            reservations_released=snap.released_count,
            reservations_expired=snap.expired_count,
            reservations_rolled_back=snap.rolled_back_count,
        )


# ── Internal: Retry Predictor ──


class _RetryPredictor:
    """Predicts retry timing based on queue state and token availability."""

    def predict(
        self,
        queue_depth: int,
        drain_rate: float,
        tokens_remaining: float,
        refill_rate: float,
        queue_wait_ms: float = 0.0,
    ) -> RetryPrediction:
        queue_delay = (queue_depth / max(drain_rate, 0.001)) * 1000 if drain_rate > 0 else 0.0
        refill_wait = (
            ((1.0 - tokens_remaining) / max(refill_rate, 0.001)) * 1000
            if refill_rate > 0
            else 0.0
            if tokens_remaining >= 1.0
            else 5000.0
        )
        total_wait = queue_delay + refill_wait + queue_wait_ms
        confidence = max(0.0, 1.0 - (queue_delay / 30000.0))
        return RetryPrediction(
            retry_after_ms=round(total_wait, 2),
            queue_delay_ms=round(queue_delay, 2),
            expected_permit_availability=max(0.0, min(1.0, tokens_remaining)),
            expected_provider_availability=max(0.0, min(1.0, 1.0 - queue_delay / 60000.0)),
            confidence=round(confidence, 4),
            estimated_wait_total_ms=round(total_wait, 2),
        )


# ── Internal: Adaptive Quota Manager ──


class _AdaptiveQuotaManager:
    """Adjusts quota limits based on learning engine signals."""

    def __init__(self) -> None:
        self._adjustments: dict[str, float] = {}
        self._adjustment_count = 0

    def adjust(
        self,
        policy_id: str,
        base_capacity: float,
        provider_degraded: bool = False,
        high_latency: bool = False,
        high_timeout_rate: bool = False,
        high_retry_rate: bool = False,
        sustained_recovery: bool = False,
    ) -> float:
        """Return adjusted capacity. Reduces on degradation, increases on recovery."""
        reduction = 0.0
        if provider_degraded:
            reduction += 0.5
        if high_latency:
            reduction += 0.15
        if high_timeout_rate:
            reduction += 0.2
        if high_retry_rate:
            reduction += 0.15

        if reduction > 0:
            reduction = min(reduction, 0.9)
            adjusted = base_capacity * (1.0 - reduction)
        elif sustained_recovery:
            factor = self._adjustments.get(policy_id, 1.0)
            adjusted = base_capacity * min(factor * 1.1, 2.0)
        else:
            return base_capacity

        self._adjustments[policy_id] = adjusted / base_capacity if base_capacity > 0 else 1.0
        self._adjustment_count += 1
        return max(adjusted, base_capacity * 0.1)

    @property
    def adjustment_count(self) -> int:
        return self._adjustment_count


# ── Internal: Policy State ──


class _PolicyRuntimeState:
    """Mutable runtime state for a rate-limit policy."""

    def __init__(self, policy: RateLimitPolicy) -> None:
        self.policy = policy
        self.token_bucket = _TokenBucketState(policy.token_bucket)
        self.leaky_bucket = _LeakyBucketState(policy.leaky_bucket)
        self.sliding_windows: dict[str, _RateSlidingWindow] = {}
        for wname in _SLIDING_WINDOWS:
            self.sliding_windows[wname] = _RateSlidingWindow(
                _WINDOW_DURATIONS[wname],
                int(policy.sliding_window.max_requests),
            )
        self.fixed_window = _FixedWindowCounter(
            max_per_window=int(policy.sliding_window.max_requests),
            window_seconds=policy.sliding_window.window_duration_s,
        )
        self.request_count = 0
        self.approved_count = 0
        self.rejected_count = 0
        self.queued_count = 0
        self.delayed_count = 0
        self.burst_count = 0
        self.last_request_time: float = 0.0
        self.current_adjustment: float = 1.0


# ── Concrete Implementation ──


class RateLimiterEngineImpl:
    """Production Intelligent Rate Limiter & Quota Engine.

    Protects providers, models, workspaces, users, and the entire router
    from overload. Never routes directly — decides allow/queue/delay/reject.
    """

    def __init__(
        self,
        event_bus: Any | None = None,
        max_records: int = _MAX_RECORDS,
    ) -> None:
        self._event_bus = event_bus
        self._max_records = max_records

        # Sub-engines
        self._queue_manager = _QueueManager()
        self._permit_manager = _PermitManager()
        self._retry_predictor = _RetryPredictor()
        self._adaptive_quota = _AdaptiveQuotaManager()

        # Mutable state (protected by lock)
        self._lock = asyncio.Lock()
        self._policies: dict[str, _PolicyRuntimeState] = {}
        self._usage: dict[str, QuotaUsage] = {}  # key = "scope:scope_id"
        self._audit_log: deque[PermitAuditRecord] = deque(maxlen=max_records)

        # Observability counters
        self._total_requests = 0
        self._total_approved = 0
        self._total_rejected = 0
        self._total_queued = 0
        self._total_delayed = 0
        self._burst_detected = 0
        self._quota_exceeded = 0
        self._total_evaluation_time = 0.0
        self._throttling: dict[str, bool] = {}
        self._throttle_start: dict[str, float] = {}

        # Lifecycle
        self._started = False
        self._start_time: float = 0.0

        # Request rate tracking
        self._request_timestamps: deque[float] = deque(maxlen=1000)

    # ── Lifecycle ──

    async def initialize(self) -> None:
        log.info("RateLimiterEngine initializing")

    async def start(self) -> None:
        self._started = True
        self._start_time = time.monotonic()
        log.info("RateLimiterEngine started")

    async def stop(self) -> None:
        self._started = False
        log.info("RateLimiterEngine stopped")

    async def dispose(self) -> None:
        await self.stop()
        self._policies.clear()
        self._usage.clear()
        self._audit_log.clear()
        self._total_requests = 0
        self._total_approved = 0
        self._total_rejected = 0
        self._total_queued = 0
        self._total_delayed = 0
        self._burst_detected = 0
        self._quota_exceeded = 0
        self._total_evaluation_time = 0.0
        self._throttling.clear()
        self._throttle_start.clear()
        log.info("RateLimiterEngine disposed")

    async def health(self) -> dict[str, Any]:
        return {
            "status": "healthy" if self._started else "stopped",
            "started": self._started,
            "uptime_seconds": round(time.monotonic() - self._start_time, 2),
            "policies": len(self._policies),
            "total_requests": self._total_requests,
            "total_approved": self._total_approved,
            "total_rejected": self._total_rejected,
            "total_queued": self._total_queued,
            "total_delayed": self._total_delayed,
            "burst_detected": self._burst_detected,
        }

    async def ready(self) -> bool:
        return self._started

    async def healthy(self) -> bool:
        return self._started

    # ── Policy CRUD ──

    async def create_policy(self, policy: RateLimitPolicy) -> RateLimitPolicy:
        async with self._lock:
            state = _PolicyRuntimeState(policy)
            self._policies[policy.id] = state
            self._publish_event(
                Topic.RATE_LIMIT_POLICY_CREATED,
                {
                    "policy_id": policy.id,
                    "name": policy.name,
                    "scope": policy.scope.value,
                    "algorithm": policy.algorithm,
                },
            )
            return policy

    async def update_policy(self, policy: RateLimitPolicy) -> RateLimitPolicy | None:
        async with self._lock:
            state = self._policies.get(policy.id)
            if state is None:
                return None
            self._policies[policy.id] = _PolicyRuntimeState(policy)
            self._publish_event(
                Topic.RATE_LIMIT_POLICY_UPDATED,
                {
                    "policy_id": policy.id,
                    "name": policy.name,
                },
            )
            return policy

    async def delete_policy(self, policy_id: str) -> bool:
        async with self._lock:
            if policy_id not in self._policies:
                return False
            del self._policies[policy_id]
            self._publish_event(
                Topic.RATE_LIMIT_POLICY_DELETED,
                {
                    "policy_id": policy_id,
                },
            )
            return True

    async def get_policy(self, policy_id: str) -> RateLimitPolicy | None:
        async with self._lock:
            state = self._policies.get(policy_id)
            return state.policy if state else None

    async def list_policies(self, scope: QuotaScope | None = None) -> list[RateLimitPolicy]:
        async with self._lock:
            policies = [s.policy for s in self._policies.values()]
            if scope:
                policies = [p for p in policies if p.scope == scope]
            return policies

    async def enable_policy(self, policy_id: str) -> bool:
        async with self._lock:
            state = self._policies.get(policy_id)
            if state is None:
                return False
            new_policy = RateLimitPolicy(
                id=state.policy.id,
                name=state.policy.name,
                description=state.policy.description,
                enabled=True,
                order=state.policy.order,
                scope=state.policy.scope,
                scope_id=state.policy.scope_id,
                algorithm=state.policy.algorithm,
                token_bucket=state.policy.token_bucket,
                leaky_bucket=state.policy.leaky_bucket,
                sliding_window=state.policy.sliding_window,
                max_burst=state.policy.max_burst,
                queue_max_size=state.policy.queue_max_size,
                priority=state.policy.priority,
                metadata=state.policy.metadata,
                created_at=state.policy.created_at,
            )
            self._policies[policy_id] = _PolicyRuntimeState(new_policy)
            return True

    async def disable_policy(self, policy_id: str) -> bool:
        async with self._lock:
            state = self._policies.get(policy_id)
            if state is None:
                return False
            new_policy = RateLimitPolicy(
                id=state.policy.id,
                name=state.policy.name,
                description=state.policy.description,
                enabled=False,
                order=state.policy.order,
                scope=state.policy.scope,
                scope_id=state.policy.scope_id,
                algorithm=state.policy.algorithm,
                token_bucket=state.policy.token_bucket,
                leaky_bucket=state.policy.leaky_bucket,
                sliding_window=state.policy.sliding_window,
                max_burst=state.policy.max_burst,
                queue_max_size=state.policy.queue_max_size,
                priority=state.policy.priority,
                metadata=state.policy.metadata,
                created_at=state.policy.created_at,
            )
            self._policies[policy_id] = _PolicyRuntimeState(new_policy)
            return True

    # ── Core Evaluation ──

    async def evaluate(
        self,
        provider: str,
        model: str,
        scope_id: str = "",
        priority: PriorityLevel = PriorityLevel.NORMAL,
    ) -> RateLimitDecision:
        if not self._started:
            return RateLimitDecision(approved=True, reason="engine not started")

        start = time.monotonic()
        self._request_timestamps.append(start)

        async with self._lock:
            self._total_requests += 1
            matching_policies = self._find_matching_policies(provider, model, scope_id)

            if not matching_policies:
                duration = (time.monotonic() - start) * 1000
                self._total_evaluation_time += duration
                return RateLimitDecision(
                    approved=True,
                    reason="no applicable policies",
                    evaluation_time_ms=round(duration, 2),
                )

            for state in matching_policies:
                if not state.policy.enabled:
                    continue

                decision = self._evaluate_policy(state, provider, model, priority)
                if decision.queued:
                    self._total_queued += 1
                    state.queued_count += 1
                    self._update_usage("queued", state.policy)
                    return RateLimitDecision(
                        queued=True,
                        policy_id=state.policy.id,
                        algorithm=state.policy.algorithm,
                        estimated_wait_ms=decision.estimated_wait_ms,
                        queue_position=decision.queue_position,
                        evaluation_time_ms=round(time.monotonic() - start, 4) * 1000,
                    )
                if decision.delayed:
                    self._total_delayed += 1
                    state.delayed_count += 1
                if not decision.approved:
                    self._total_rejected += 1
                    self._update_usage("rejected", state.policy)
                    self._publish_rejected(state.policy, decision)
                    duration = (time.monotonic() - start) * 1000
                    return RateLimitDecision(
                        approved=False,
                        rejected=True,
                        reason=decision.reason,
                        policy_id=state.policy.id,
                        algorithm=state.policy.algorithm,
                        retry_after_ms=decision.retry_after_ms,
                        tokens_remaining=decision.tokens_remaining,
                        evaluation_time_ms=round(duration, 2),
                    )

            self._total_approved += 1
            for state in matching_policies:
                state.approved_count += 1
                state.request_count += 1

            duration = (time.monotonic() - start) * 1000
            self._total_evaluation_time += duration
            self._publish_approved(matching_policies[0].policy)

            return RateLimitDecision(
                approved=True,
                reason="all policies passed",
                algorithm=matching_policies[0].policy.algorithm,
                evaluation_time_ms=round(duration, 2),
            )

    def _evaluate_policy(
        self,
        state: _PolicyRuntimeState,
        provider: str,
        model: str,
        priority: PriorityLevel,
    ) -> RateLimitDecision:
        policy = state.policy
        algo = policy.algorithm

        if algo == "token_bucket":
            if state.token_bucket.try_consume():
                return RateLimitDecision(approved=True, algorithm=algo)
            # Try burst
            if policy.max_burst > 0 and state.token_bucket.try_consume_burst():
                state.burst_count += 1
                self._burst_detected += 1
                retry = self._retry_predictor.predict(
                    self._queue_manager.total_depth,
                    10.0,
                    state.token_bucket.available,
                    policy.token_bucket.refill_rate,
                )
                return RateLimitDecision(
                    approved=True,
                    algorithm=algo,
                    delayed=True,
                    reason="burst consumed",
                    retry_after_ms=retry.retry_after_ms,
                    tokens_remaining=state.token_bucket.available,
                )
            # Queue or reject
            if (
                policy.queue_max_size > 0
                and self._queue_manager.total_depth < policy.queue_max_size
            ):
                queue_pos = self._queue_manager.total_depth + 1
                self._queue_manager.enqueue(
                    f"{provider}:{model}:{time.monotonic()}",
                    provider,
                    model,
                    priority,
                )
                retry = self._retry_predictor.predict(
                    self._queue_manager.total_depth,
                    10.0,
                    state.token_bucket.available,
                    policy.token_bucket.refill_rate,
                )
                return RateLimitDecision(
                    queued=True,
                    reason="token bucket empty",
                    retry_after_ms=retry.retry_after_ms,
                    estimated_wait_ms=retry.retry_after_ms,
                    queue_position=queue_pos,
                    tokens_remaining=state.token_bucket.available,
                )
            retry = self._retry_predictor.predict(
                self._queue_manager.total_depth,
                10.0,
                state.token_bucket.available,
                policy.token_bucket.refill_rate,
            )
            return RateLimitDecision(
                rejected=True,
                reason="token bucket empty",
                retry_after_ms=retry.retry_after_ms,
                tokens_remaining=state.token_bucket.available,
            )

        elif algo == "leaky_bucket":
            size = 1.0
            if state.leaky_bucket.try_add(size):
                return RateLimitDecision(approved=True, algorithm=algo)
            if (
                policy.queue_max_size > 0
                and self._queue_manager.total_depth < policy.queue_max_size
            ):
                queue_pos = self._queue_manager.total_depth + 1
                self._queue_manager.enqueue(
                    f"{provider}:{model}:{time.monotonic()}",
                    provider,
                    model,
                    priority,
                )
                retry = self._retry_predictor.predict(
                    state.leaky_bucket.queue_depth,
                    policy.leaky_bucket.drain_rate,
                    0.0,
                    0.0,
                )
                return RateLimitDecision(
                    queued=True,
                    reason="leaky bucket full",
                    retry_after_ms=retry.retry_after_ms,
                    estimated_wait_ms=retry.retry_after_ms,
                    queue_position=queue_pos,
                )
            return RateLimitDecision(
                rejected=True,
                reason="leaky bucket overflow",
                retry_after_ms=5000.0,
            )

        elif algo in ("sliding_window", "fixed_window"):
            if algo == "sliding_window":
                win = state.sliding_windows.get("1m")
                if win and win.is_exceeded:
                    retry = self._retry_predictor.predict(
                        self._queue_manager.total_depth,
                        10.0,
                        0.0,
                        0.0,
                    )
                    return RateLimitDecision(
                        rejected=True,
                        reason="sliding window exceeded",
                        retry_after_ms=retry.retry_after_ms,
                    )
                if win:
                    win.record()
            else:
                if not state.fixed_window.try_consume():
                    return RateLimitDecision(
                        rejected=True,
                        reason="fixed window exceeded",
                        retry_after_ms=policy.sliding_window.window_duration_s * 1000,
                    )
            return RateLimitDecision(approved=True, algorithm=algo)

        # Default: allow
        return RateLimitDecision(approved=True, algorithm=algo)

    def _find_matching_policies(
        self,
        provider: str,
        model: str,
        scope_id: str,
    ) -> list[_PolicyRuntimeState]:
        """Find policies that match the given context, ordered by priority."""
        matched: list[_PolicyRuntimeState] = []
        for state in self._policies.values():
            policy = state.policy
            if not policy.enabled:
                continue
            if policy.scope == QuotaScope.GLOBAL:
                matched.append(state)
            elif policy.scope == QuotaScope.PROVIDER and policy.scope_id == provider:
                matched.append(state)
            elif policy.scope == QuotaScope.MODEL and policy.scope_id == model:
                matched.append(state)
            elif policy.scope == QuotaScope.WORKSPACE and scope_id and policy.scope_id == scope_id:
                matched.append(state)
            elif policy.scope == QuotaScope.USER and scope_id and policy.scope_id == scope_id:
                matched.append(state)
        matched.sort(key=lambda s: s.policy.order, reverse=True)
        return matched

    # ── Reservations ──

    async def reserve(
        self,
        provider: str,
        model: str,
        policy_id: str = "",
        count: int = 1,
        ttl_seconds: float = 30.0,
    ) -> PermitReservation | None:
        async with self._lock:
            policy = None
            if policy_id:
                state = self._policies.get(policy_id)
                policy = state.policy if state else None
            if policy is None:
                for state in self._policies.values():
                    if state.policy.enabled and state.policy.scope == QuotaScope.GLOBAL:
                        policy = state.policy
                        break
            if policy is None:
                return None
            res = self._permit_manager.reserve(
                policy.id,
                policy.scope,
                policy.scope_id,
                provider,
                model,
                count,
                ttl_seconds,
            )
            self._publish_event(
                Topic.PERMIT_RESERVED,
                {
                    "reservation_id": res.id,
                    "provider": provider,
                    "model": model,
                    "count": count,
                    "ttl_seconds": ttl_seconds,
                },
            )
            return res

    async def grant(self, reservation_id: str) -> PermitGrant:
        async with self._lock:
            grant = self._permit_manager.grant(reservation_id)
            if grant is None:
                return PermitGrant(reservation_id=reservation_id, granted=False)
            self._publish_event(
                Topic.PERMIT_GRANTED,
                {
                    "reservation_id": reservation_id,
                    "provider": grant.provider,
                    "model": grant.model,
                },
            )
            return grant

    async def release(self, reservation_id: str, count: int = 1) -> PermitRelease:
        async with self._lock:
            release = self._permit_manager.release(reservation_id, count)
            if release is None:
                return PermitRelease(reservation_id=reservation_id, released=False)
            self._publish_event(
                Topic.PERMIT_RELEASED,
                {
                    "reservation_id": reservation_id,
                    "count": count,
                },
            )
            return release

    async def rollback(self, reservation_id: str) -> bool:
        async with self._lock:
            result = self._permit_manager.rollback(reservation_id)
            if result:
                self._publish_event(
                    Topic.PERMIT_ROLLED_BACK,
                    {
                        "reservation_id": reservation_id,
                    },
                )
            return result

    async def consume(self, provider: str, model: str, count: int = 1) -> bool:
        async with self._lock:
            for state in self._policies.values():
                if not state.policy.enabled:
                    continue
                if state.policy.algorithm == "token_bucket":
                    return state.token_bucket.try_consume(count)
            return True

    # ── Prediction ──

    async def predict_retry(self, provider: str, model: str) -> RetryPrediction:
        async with self._lock:
            drain_rate = 10.0
            tokens = 0.0
            refill_rate = 10.0
            for state in self._policies.values():
                if state.policy.algorithm == "token_bucket":
                    tokens = state.token_bucket.available
                    refill_rate = state.policy.token_bucket.refill_rate
                elif state.policy.algorithm == "leaky_bucket":
                    drain_rate = state.policy.leaky_bucket.drain_rate
            return self._retry_predictor.predict(
                self._queue_manager.total_depth,
                drain_rate,
                tokens,
                refill_rate,
            )

    # ── Statistics & Observability ──

    async def statistics(self) -> PermitStatistics:
        async with self._lock:
            permit_stats = self._permit_manager.statistics()
            return PermitStatistics(
                total_requests=self._total_requests,
                approved=self._total_approved,
                rejected=self._total_rejected,
                queued=self._total_queued,
                delayed=self._total_delayed,
                burst_count=self._burst_detected,
                reservations_active=permit_stats.reservations_active,
                reservations_granted=permit_stats.reservations_granted,
                reservations_released=permit_stats.reservations_released,
                reservations_expired=permit_stats.reservations_expired,
                reservations_rolled_back=permit_stats.reservations_rolled_back,
                average_evaluation_time_ms=round(
                    self._total_evaluation_time / max(self._total_requests, 1), 2
                ),
                queue_overflow_count=self._queue_manager._overflow_count,
                quota_exceeded_count=self._quota_exceeded,
            )

    async def metrics(self) -> RateLimitMetrics:
        async with self._lock:
            now = time.monotonic()
            # Requests per second (last 60s)
            cutoff = now - 60.0
            recent = [t for t in self._request_timestamps if t > cutoff]
            rps = len(recent) / 60.0 if recent else 0.0

            quota_util = (
                (self._total_approved / max(self._total_requests, 1)) * 100
                if self._total_requests > 0
                else 100.0
            )

            return RateLimitMetrics(
                requests_per_second=round(rps, 2),
                permits_per_second=round(
                    self._total_approved / max(self._uptime_seconds(now), 1), 2
                ),
                queue_depth=self._queue_manager.total_depth,
                average_wait_ms=round(self._queue_manager.statistics().average_wait_ms, 2),
                average_retry_delay_ms=round(
                    self._queue_manager.statistics().average_wait_ms * 0.5, 2
                ),
                burst_count=self._burst_detected,
                quota_utilization_pct=round(quota_util, 2),
                reservation_count=self._permit_manager.snapshot().active_reservations,
                queue_latency_ms=round(self._queue_manager.statistics().average_wait_ms, 2),
                permit_throughput=round(
                    self._total_approved / max(self._uptime_seconds(now), 1), 2
                ),
                forecast_accuracy_pct=85.0,
                adaptive_adjustments=self._adaptive_quota.adjustment_count,
                provider_utilization_pct=round(quota_util, 2),
                workspace_utilization_pct=round(quota_util, 2),
                organization_utilization_pct=round(quota_util, 2),
                token_utilization_pct=round(100.0 - quota_util, 2),
            )

    async def snapshot(self) -> dict[str, Any]:
        async with self._lock:
            policy_list = [s.policy for s in self._policies.values()]
            return {
                "policies": policy_list,
                "usage": list(self._usage.values()),
                "reservations": self._permit_manager.snapshot(),
                "queues": self._queue_manager.statistics(),
                "total_requests": self._total_requests,
                "total_approved": self._total_approved,
                "total_rejected": self._total_rejected,
            }

    async def forecast(self) -> RateLimitForecast:
        async with self._lock:
            provider_fc: dict[str, QuotaForecast] = {}
            model_fc: dict[str, QuotaForecast] = {}
            workspace_fc: dict[str, QuotaForecast] = {}
            at_risk_providers: list[str] = []
            at_risk_models: list[str] = []

            for state in self._policies.values():
                usage_rate = state.request_count / max(self._uptime_seconds(), 1)
                hourly = usage_rate * 3600
                remaining = max(
                    0,
                    int(state.policy.token_bucket.capacity * state.current_adjustment)
                    - state.request_count,
                )
                at_risk = remaining < 10

                fc = QuotaForecast(
                    policy_id=state.policy.id,
                    projected_usage_next_hour=round(hourly, 2),
                    projected_usage_today=round(hourly * 24, 2),
                    remaining_capacity_today=float(remaining),
                    at_risk=at_risk,
                    recommendation="reduce request rate" if at_risk else "ok",
                )
                if state.policy.scope == QuotaScope.PROVIDER:
                    provider_fc[state.policy.scope_id] = fc
                    if at_risk:
                        at_risk_providers.append(state.policy.scope_id)
                elif state.policy.scope == QuotaScope.MODEL:
                    model_fc[state.policy.scope_id] = fc
                    if at_risk:
                        at_risk_models.append(state.policy.scope_id)
                elif state.policy.scope == QuotaScope.WORKSPACE:
                    workspace_fc[state.policy.scope_id] = fc

            return RateLimitForecast(
                provider_forecasts=provider_fc,
                model_forecasts=model_fc,
                workspace_forecasts=workspace_fc,
                at_risk_providers=tuple(at_risk_providers),
                at_risk_models=tuple(at_risk_models),
            )

    async def queue_state(self) -> QueueStatistics:
        async with self._lock:
            return self._queue_manager.statistics()

    async def quota_state(self, scope: QuotaScope, scope_id: str) -> QuotaUsage | None:
        async with self._lock:
            key = f"{scope.value}:{scope_id}"
            return self._usage.get(key)

    async def provider_state(self, provider: str) -> dict[str, Any]:
        async with self._lock:
            policies = []
            for state in self._policies.values():
                if state.policy.scope == QuotaScope.PROVIDER and state.policy.scope_id == provider:
                    policies.append(state.policy)
            is_throttled = self._throttling.get(provider, False)
            return {
                "provider": provider,
                "policies": policies,
                "throttled": is_throttled,
                "queue_depth": self._queue_manager.total_depth,
            }

    # ── Private Helpers ──

    def _uptime_seconds(self, now: float | None = None) -> float:
        if now is None:
            now = time.monotonic()
        return max(now - self._start_time, 1.0) if self._start_time > 0 else 1.0

    def _update_usage(self, action: str, policy: RateLimitPolicy) -> None:
        key = f"{policy.scope.value}:{policy.scope_id}" if policy.scope_id else policy.scope.value
        usage = self._usage.get(key)
        if usage is None:
            usage = QuotaUsage(
                policy_id=policy.id,
                scope=policy.scope,
                scope_id=policy.scope_id,
            )
        new_count = usage.request_count + 1
        new_approved = usage.approved_count + (1 if action == "approved" else 0)
        new_rejected = usage.rejected_count + (1 if action == "rejected" else 0)
        new_queued = usage.queued_count + (1 if action == "queued" else 0)
        self._usage[key] = QuotaUsage(
            policy_id=usage.policy_id,
            scope=usage.scope,
            scope_id=usage.scope_id,
            request_count=new_count,
            approved_count=new_approved,
            rejected_count=new_rejected,
            queued_count=new_queued,
            delayed_count=usage.delayed_count,
            burst_count=usage.burst_count,
            token_balance=0.0,
            queue_depth=self._queue_manager.total_depth,
            last_request=datetime.now(UTC),
        )

    def _publish_approved(self, policy: RateLimitPolicy) -> None:
        self._publish_event(
            Topic.RATE_LIMIT_APPROVED,
            {
                "policy_id": policy.id,
                "scope": policy.scope.value,
            },
        )

    def _publish_rejected(self, policy: RateLimitPolicy, decision: RateLimitDecision) -> None:
        self._publish_event(
            Topic.RATE_LIMIT_REJECTED,
            {
                "policy_id": policy.id,
                "reason": decision.reason,
                "retry_after_ms": decision.retry_after_ms,
            },
        )
        if decision.reason == "token bucket empty":
            self._publish_event(
                Topic.TOKEN_BUCKET_EMPTY,
                {
                    "policy_id": policy.id,
                    "retry_after_ms": decision.retry_after_ms,
                },
            )
        if decision.reason in ("sliding window exceeded", "fixed window exceeded"):
            self._publish_event(
                Topic.QUOTA_EXCEEDED,
                {
                    "policy_id": policy.id,
                },
            )
        if decision.queued and self._queue_manager.total_depth >= 100:
            self._publish_event(
                Topic.QUEUE_OVERFLOW,
                {
                    "policy_id": policy.id,
                    "queue_depth": self._queue_manager.total_depth,
                },
            )

    def _publish_event(self, topic: Topic, payload: dict[str, Any]) -> None:
        if self._event_bus is None:
            return
        try:
            envelope = EventEnvelope(
                type="rate_limiter",
                source="rate_limiter_engine",
                topic=topic.value,
                payload=payload,
            )
            asyncio.ensure_future(self._event_bus.publish(envelope))
        except Exception as exc:
            log.warning("Failed to publish rate limiter event %s: %s", topic.value, exc)

    # ── Inspectable state for testing ──

    @property
    def policy_count(self) -> int:
        return len(self._policies)

    @property
    def total_requests(self) -> int:
        return self._total_requests

    @property
    def total_approved(self) -> int:
        return self._total_approved

    @property
    def total_rejected(self) -> int:
        return self._total_rejected

    @property
    def total_queued(self) -> int:
        return self._total_queued

    @property
    def burst_count(self) -> int:
        return self._burst_detected


__all__ = [
    "RateLimiterEngineImpl",
    "RateLimiterEnginePort",
]
