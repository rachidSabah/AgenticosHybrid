"""Intelligent Request Scheduler & Queue Manager (Phase 5.9).

Sits between the Rate Limiter and the Circuit Breaker in the routing
pipeline.  Responsible for request prioritisation, queue management,
deadline-aware scheduling, fairness, starvation prevention, provider-aware
dispatch ordering, retry scheduling, back-pressure handling, adaptive
queue balancing, and scheduling metrics.

Port protocol
-------------
:class:`SchedulerEnginePort` — implement this or depend on it.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from heapq import heappop, heappush
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4

from agentic_os.domain.events import EventEnvelope, Topic
from agentic_os.domain.omniroute import (
    DispatchPlan,
    DispatchReservation,
    PriorityLevel,
    QueueItem,
    QueueMetrics,
    QueueOverflowStrategy,
    QueueSnapshot,
    QueueStatistics,
    RetrySchedule,
    SchedulerHealth,
    SchedulingDecision,
    SchedulingPolicy,
    SchedulingReason,
)
from agentic_os.infrastructure.logging import get_logger

log = get_logger("omniroute.scheduler")

# ── Constants ──

_DEFAULT_AGE_SECS: float = 30.0
_DEFAULT_MAX_QUEUE: int = 500
_DEFAULT_WORKER_POOL: int = 32
_DEFAULT_OVERFLOW: str = "reject"


# ── Port Protocol ──


@runtime_checkable
class SchedulerEnginePort(Protocol):
    """Intelligent request scheduler & queue manager."""

    async def schedule(
        self,
        provider: str,
        model: str,
        priority: PriorityLevel = PriorityLevel.NORMAL,
        deadline_s: float | None = None,
        provider_cost: float = 0.0,
        estimated_latency_ms: float = 0.0,
        queue_affinity: str | None = None,
    ) -> SchedulingDecision: ...

    async def enqueue(
        self,
        provider: str,
        model: str,
        priority: PriorityLevel = PriorityLevel.NORMAL,
        deadline_s: float | None = None,
        provider_cost: float = 0.0,
        estimated_latency_ms: float = 0.0,
        queue_affinity: str | None = None,
    ) -> str: ...

    async def dequeue(self) -> DispatchPlan | None: ...

    async def cancel(self, item_id: str) -> bool: ...

    async def pause(self, reason: str = "") -> None: ...

    async def resume(self) -> None: ...

    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def health(self) -> SchedulerHealth: ...

    async def metrics(self) -> QueueMetrics: ...

    async def statistics(self) -> QueueStatistics: ...

    async def snapshot(self) -> QueueSnapshot: ...


# ═══════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════


def _new_id() -> str:
    return uuid4().hex[:12]


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _now_ms() -> float:
    return time.monotonic() * 1000


# ═══════════════════════════════════════════════════════════════
# Internal state classes
# ═══════════════════════════════════════════════════════════════


@dataclass
class _QueueEntry:
    """Internal queue item with heap metadata."""

    item: QueueItem
    priority_level: PriorityLevel
    enqueued_ms: float
    deadline_ms: float | None = None
    retry_count: int = 0
    age_boost: int = 0  # priority boost for starvation prevention


@dataclass
class _FairnessTracker:
    """Per-group fairness tracking."""

    dispatched: int = 0
    last_dispatch_ms: float = 0.0
    deficit: float = 0.0


# ═══════════════════════════════════════════════════════════════
# Internal Components
# ═══════════════════════════════════════════════════════════════


class _PriorityQueueManager:
    """Multi-level priority queue with FIFO ordering within each level."""

    def __init__(self, max_size: int = _DEFAULT_MAX_QUEUE) -> None:
        self._max_size = max_size
        self._queues: dict[PriorityLevel, deque[_QueueEntry]] = {
            level: deque() for level in PriorityLevel
        }
        self._total = 0
        self._overflow_count = 0

    @property
    def total(self) -> int:
        return self._total

    @property
    def overflow_count(self) -> int:
        return self._overflow_count

    def push(self, entry: _QueueEntry, strategy: str = _DEFAULT_OVERFLOW) -> bool:
        """Push an entry, returning True on success.  Applies overflow strategy."""
        if self._total >= self._max_size:
            self._overflow_count += 1
            if strategy == "drop_oldest":
                oldest_time = float("inf")
                oldest_level = PriorityLevel.BACKGROUND
                for level in PriorityLevel:
                    q = self._queues[level]
                    if q and q[0].enqueued_ms < oldest_time:
                        oldest_time = q[0].enqueued_ms
                        oldest_level = level
                if self._queues[oldest_level]:
                    self._queues[oldest_level].popleft()
                    self._total -= 1
                    return self.push(entry, strategy)
            elif strategy == "drop_newest":
                return True  # drop new item, queue unchanged — success
            elif strategy == "priority_eviction":
                # Evict from lowest priority if at capacity
                for level in reversed(list(PriorityLevel)):
                    if self._queues[level]:
                        self._queues[level].pop()
                        self._total -= 1
                        return self.push(entry, strategy)
                return False
            else:
                return False  # reject
        self._queues[entry.priority_level].append(entry)
        self._total += 1
        return True

    def pop(self, strategy: str = _DEFAULT_OVERFLOW) -> _QueueEntry | None:
        """Pop the highest-priority item (FIFO within priority)."""
        for level in PriorityLevel:
            q = self._queues[level]
            if q:
                self._total -= 1
                return q.popleft()
        return None

    def peek(self) -> _QueueEntry | None:
        for level in PriorityLevel:
            q = self._queues[level]
            if q:
                return q[0]
        return None

    def remove(self, item_id: str) -> bool:
        for level in PriorityLevel:
            q = self._queues[level]
            for i, entry in enumerate(q):
                if entry.item.id == item_id:
                    del q[i]
                    self._total -= 1
                    return True
        return False

    def clear(self) -> None:
        self._overflow_count = 0
        self._total = 0
        for level in PriorityLevel:
            self._queues[level].clear()

    def depth_by_priority(self, level: PriorityLevel) -> int:
        return len(self._queues[level])


class _EDFQueue:
    """Earliest Deadline First queue — min-heap of deadline items."""

    def __init__(self) -> None:
        self._heap: list[tuple[float, int, _QueueEntry]] = []
        self._counter = 0

    @property
    def total(self) -> int:
        return len(self._heap)

    def push(self, entry: _QueueEntry) -> None:
        deadline = entry.deadline_ms if entry.deadline_ms is not None else float("inf")
        self._counter += 1
        heappush(self._heap, (deadline, self._counter, entry))

    def pop(self) -> _QueueEntry | None:
        if not self._heap:
            return None
        _, _, entry = heappop(self._heap)
        return entry

    def peek(self) -> _QueueEntry | None:
        if not self._heap:
            return None
        return self._heap[0][2]

    def remove(self, item_id: str) -> bool:
        new_heap = []
        found = False
        for deadline, ctr, entry in self._heap:
            if entry.item.id == item_id:
                found = True
                continue
            new_heap.append((deadline, ctr, entry))
        self._heap = new_heap
        return found

    def clear(self) -> None:
        self._heap.clear()
        self._counter = 0

    def expired(self, now_ms: float) -> list[_QueueEntry]:
        """Return all expired entries."""
        expired: list[_QueueEntry] = []
        while self._heap and self._heap[0][0] <= now_ms:
            _, _, entry = heappop(self._heap)
            expired.append(entry)
        return expired


class _WeightedFairQueue:
    """Weighted Fair Queue with per-group deficits."""

    def __init__(self) -> None:
        self._queues: dict[str, deque[_QueueEntry]] = defaultdict(deque)
        self._fairness: dict[str, _FairnessTracker] = {}
        self._weights: dict[str, float] = {}
        self._round_robin: list[str] = []
        self._rr_index = 0
        self._total = 0

    @property
    def total(self) -> int:
        return self._total

    def set_weight(self, group: str, weight: float) -> None:
        self._weights[group] = max(0.1, weight)
        if group not in self._fairness:
            self._fairness[group] = _FairnessTracker()
            self._round_robin.append(group)

    def push(self, group: str, entry: _QueueEntry) -> None:
        if group not in self._fairness:
            self.set_weight(group, 1.0)
        self._queues[group].append(entry)
        self._total += 1

    def pop_wfq(self) -> _QueueEntry | None:
        """WFQ: select group with lowest deficit / weight."""
        candidates: list[tuple[float, str]] = []
        for group, q in self._queues.items():
            if q:
                weight = self._weights.get(group, 1.0)
                deficit = self._fairness[group].deficit
                candidates.append((deficit / weight, group))
        if not candidates:
            return None
        candidates.sort(key=lambda x: x[0])
        chosen = candidates[0][1]
        entry = self._queues[chosen].popleft()
        self._total -= 1
        self._fairness[chosen].deficit += 1.0
        self._fairness[chosen].last_dispatch_ms = _now_ms()
        self._fairness[chosen].dispatched += 1
        return entry

    def pop_rr(self) -> _QueueEntry | None:
        """Round-robin across groups."""
        if not self._round_robin:
            return None
        for _ in range(len(self._round_robin)):
            group = self._round_robin[self._rr_index]
            self._rr_index = (self._rr_index + 1) % len(self._round_robin)
            if self._queues[group]:
                self._total -= 1
                entry = self._queues[group].popleft()
                return entry
        return None

    def pop_wrr(self) -> _QueueEntry | None:
        """Weighted Round Robin according to weights."""
        if not self._round_robin:
            return None
        total_weight = sum(self._weights.get(g, 1.0) for g in self._round_robin)
        if total_weight == 0:
            return self.pop_rr()
        for _ in range(len(self._round_robin) * 3):
            group = self._round_robin[self._rr_index]
            w = self._weights.get(group, 1.0)
            if self._queues[group] and (w / total_weight) >= 0.1:
                self._rr_index = (self._rr_index + 1) % len(self._round_robin)
                self._total -= 1
                return self._queues[group].popleft()
            self._rr_index = (self._rr_index + 1) % len(self._round_robin)
        return self.pop_rr()

    def clear(self) -> None:
        self._queues.clear()
        self._fairness.clear()
        self._total = 0
        self._rr_index = 0


class _StarvationDetector:
    """Detects and ages requests that have waited too long."""

    def __init__(self, max_wait_ms: float = 5000.0) -> None:
        self._max_wait_ms = max_wait_ms
        self._starvation_count = 0

    @property
    def starvation_count(self) -> int:
        return self._starvation_count

    def check(self, now_ms: float, entry: _QueueEntry) -> int:
        """Return the age boost (how many priority levels to raise)."""
        elapsed = now_ms - entry.enqueued_ms
        if elapsed > self._max_wait_ms * 4:
            self._starvation_count += 1
            return 3
        elif elapsed > self._max_wait_ms * 2:
            self._starvation_count += 1
            return 2
        elif elapsed > self._max_wait_ms:
            self._starvation_count += 1
            return 1
        return 0

    def reset(self) -> None:
        self._starvation_count = 0


class _BackPressureManager:
    """Monitors queue depth and triggers back-pressure."""

    def __init__(
        self,
        high_water_mark: int = 100,
        low_water_mark: int = 30,
    ) -> None:
        self._high = high_water_mark
        self._low = low_water_mark
        self._backpressure = False
        self._events = 0

    @property
    def active(self) -> bool:
        return self._backpressure

    @property
    def events(self) -> int:
        return self._events

    def update(self, depth: int) -> bool:
        """Return True if backpressure state changed."""
        if depth >= self._high and not self._backpressure:
            self._backpressure = True
            self._events += 1
            return True
        elif depth <= self._low and self._backpressure:
            self._backpressure = False
            self._events += 1
            return True
        return False

    def reset(self) -> None:
        self._backpressure = False
        self._events = 0


class _WorkerAllocator:
    """Manages a pool of virtual workers for dispatch."""

    def __init__(self, pool_size: int = _DEFAULT_WORKER_POOL) -> None:
        self._pool_size = pool_size
        self._acquired: int = 0

    @property
    def available(self) -> int:
        return self._pool_size - self._acquired

    @property
    def utilization(self) -> float:
        return self._acquired / max(self._pool_size, 1)

    def acquire(self, count: int = 1) -> bool:
        if self._acquired + count <= self._pool_size:
            self._acquired += count
            return True
        return False

    def release(self, count: int = 1) -> None:
        self._acquired = max(0, self._acquired - count)

    def reset(self) -> None:
        self._acquired = 0


class _RetryPlanner:
    """Plans retry schedules for failed requests."""

    def __init__(self) -> None:
        self._retry_counts: dict[str, int] = {}
        self._total_retries = 0

    @property
    def total_retries(self) -> int:
        return self._total_retries

    @property
    def retry_rate(self) -> float:
        return self._total_retries / max(sum(self._retry_counts.values()), 1)

    def plan(self, item_id: str, max_retries: int = 3) -> RetrySchedule:
        count = self._retry_counts.get(item_id, 0)
        if count >= max_retries:
            return RetrySchedule(
                should_retry=False,
                retry_count=count,
                delay_ms=0,
                reason="max retries exceeded",
            )
        delay = 100 * (2**count) + 50  # exponential backoff with jitter
        self._retry_counts[item_id] = count + 1
        self._total_retries += 1
        return RetrySchedule(
            should_retry=True,
            retry_count=count + 1,
            delay_ms=delay,
            reason=f"retry #{count + 1}",
        )

    def reset(self, item_id: str | None = None) -> None:
        if item_id:
            self._retry_counts.pop(item_id, None)
        else:
            self._retry_counts.clear()


class _LoadPredictor:
    """Predicts queue load based on recent dispatch rate."""

    def __init__(self, window_s: float = 60.0) -> None:
        self._timestamps: deque[float] = deque(maxlen=1000)
        self._window_s = window_s

    def record_dispatch(self) -> None:
        self._timestamps.append(time.monotonic())

    def dispatch_rate(self, now: float | None = None) -> float:
        now = now or time.monotonic()
        cutoff = now - self._window_s
        recent = [t for t in self._timestamps if t > cutoff]
        return len(recent) / self._window_s if recent else 0.0

    def predicted_load(self, queue_depth: int, now: float | None = None) -> float:
        rate = self.dispatch_rate(now)
        if rate == 0:
            return float("inf")
        return queue_depth / rate

    def reset(self) -> None:
        self._timestamps.clear()


class _SchedulerMetrics:
    """Collects and exposes scheduler metrics."""

    def __init__(self) -> None:
        self.queue_length = 0
        self.average_wait_time = 0.0
        self.dispatch_count = 0
        self.expired_count = 0
        self.retry_count = 0
        self.dispatch_rate = 0.0
        self.backpressure_events = 0
        self.starvation_count = 0
        self.deadline_misses = 0
        self.worker_utilization = 0.0
        self.dispatch_latency = 0.0
        self.fairness_index = 1.0
        self.health_status = "healthy"

    def snapshot(self) -> QueueMetrics:
        return QueueMetrics(
            queue_length=self.queue_length,
            average_wait_time=self.average_wait_time,
            dispatch_rate=self.dispatch_rate,
            expired_requests=self.expired_count,
            retry_rate=self.retry_count / max(self.dispatch_count, 1),
            queue_utilization=self.queue_length / max(_DEFAULT_MAX_QUEUE, 1),
            starvation_count=self.starvation_count,
            deadline_misses=self.deadline_misses,
            backpressure_events=self.backpressure_events,
            worker_utilization=self.worker_utilization,
            dispatch_latency=self.dispatch_latency,
            fairness_index=self.fairness_index,
            scheduler_health=self.health_status,
        )


# ═══════════════════════════════════════════════════════════════
# Engine Implementation
# ═══════════════════════════════════════════════════════════════


class _QueueBalancer:
    """Adaptively balances requests across provider-affinity queues."""

    def __init__(self, imbalance_threshold: float = 0.3) -> None:
        self._imbalance_threshold = imbalance_threshold
        self._provider_loads: dict[str, int] = {}
        self._total_load = 0

    def record_push(self, provider: str) -> None:
        self._provider_loads[provider] = self._provider_loads.get(provider, 0) + 1
        self._total_load += 1

    def record_dispatch(self, provider: str) -> None:
        current = self._provider_loads.get(provider, 0)
        self._provider_loads[provider] = max(0, current - 1)
        self._total_load = max(0, self._total_load - 1)

    def imbalance(self) -> float:
        if not self._provider_loads or self._total_load == 0:
            return 0.0
        loads = list(self._provider_loads.values())
        return (max(loads) - min(loads)) / self._total_load

    def should_rebalance(self) -> bool:
        return self.imbalance() > self._imbalance_threshold

    def reset(self) -> None:
        self._provider_loads.clear()
        self._total_load = 0


class SchedulerEngineImpl:
    """Intelligent Request Scheduler — production queue & dispatch engine."""

    def __init__(
        self,
        event_bus: Any | None = None,
        max_queue: int = _DEFAULT_MAX_QUEUE,
        worker_pool: int = _DEFAULT_WORKER_POOL,
        fair: bool = True,
        algorithm: str = "adaptive_hybrid",
        soft_deadline_s: float = 30.0,
        hard_deadline_s: float = 60.0,
        backpressure_high: float = 0.9,
        backpressure_low: float = 0.5,
        max_retries: int = 3,
    ) -> None:
        self._event_bus = event_bus
        self._running = False
        self._paused = False
        self._pause_reason: str = ""
        self._lock = asyncio.Lock()
        self._scheduler_policy = SchedulingPolicy(
            algorithm=algorithm,
            max_queue_depth=max_queue,
            worker_pool_size=worker_pool,
            enable_fairness=fair,
            enable_starvation_detection=True,
            enable_backpressure=True,
            enable_deadlines=True,
            default_priority=PriorityLevel.NORMAL,
            overflow_strategy=QueueOverflowStrategy.REJECT,
            aging_threshold_ms=_DEFAULT_AGE_SECS * 1000,
        )
        self._started_at: float = 0.0
        self._dispatched: int = 0
        self._canceled: int = 0
        self._expired: int = 0
        self._total_wait: float = 0.0
        self._total_latency: float = 0.0
        self._last_dispatch_rate_update: float = 0.0
        self._dispatch_times: deque[float] = deque(maxlen=100)

        # Internal components
        self._fifo = _PriorityQueueManager(max_queue)
        self._edf = _EDFQueue()
        self._fair = _WeightedFairQueue()
        self._starvation = _StarvationDetector()
        self._backpressure = _BackPressureManager(
            high_water_mark=int(backpressure_high * max_queue),
            low_water_mark=int(backpressure_low * max_queue),
        )
        self._workers = _WorkerAllocator(worker_pool)
        self._retry = _RetryPlanner()
        self._predictor = _LoadPredictor()
        self._metrics_collector = _SchedulerMetrics()
        self._balancer = _QueueBalancer()

        # Active reservations
        self._reservations: dict[str, DispatchReservation] = {}

        # Health tracking
        self._health: SchedulerHealth = SchedulerHealth(
            status="stopped",
            uptime_s=0.0,
            total_queued=0,
            total_dispatched=0,
            total_expired=0,
            total_canceled=0,
            total_retries=0,
            backpressure_active=False,
            queue_full_pct=0.0,
            worker_utilization=0.0,
            error_count=0,
            last_error="",
        )

        # Policy for rebalancing
        self._last_rebalance: float = 0.0

    # ── Public API ──

    async def start(self) -> None:
        async with self._lock:
            if self._running:
                return
            self._running = True
            self._paused = False
            self._pause_reason = ""
            self._started_at = time.monotonic()
            self._health = replace(self._health, status="running")
            self._publish(Topic.SCHEDULER_STARTED)
        log.info(
            "SchedulerEngine started",
            extra={"max_queue": self._scheduler_policy.max_queue_depth},
        )

    async def stop(self) -> None:
        async with self._lock:
            if not self._running:
                return
            self._running = False
            self._paused = False
            self._health = replace(self._health, status="stopped")
            self._fifo.clear()
            self._edf.clear()
            self._fair.clear()
            self._update_health()
            self._publish(Topic.SCHEDULER_STOPPED)
        log.info("SchedulerEngine stopped")

    async def health(self) -> SchedulerHealth:
        async with self._lock:
            self._update_health()
            return self._health

    async def metrics(self) -> QueueMetrics:
        async with self._lock:
            self._metrics_collector.queue_length = (
                self._fifo.total + self._edf.total + self._fair.total
            )
            return self._metrics_collector.snapshot()

    async def statistics(self) -> QueueStatistics:
        async with self._lock:
            return QueueStatistics(
                total_queued=self._fifo.total + self._edf.total + self._fair.total,
                total_dispatched=self._dispatched,
                total_expired=self._expired,
                total_canceled=self._canceled,
                total_retries=self._retry.total_retries,
                average_wait_ms=self._average_wait(),
                dispatch_rate=self._predictor.dispatch_rate(),
                backpressure_events=self._backpressure.events,
                starvation_count=self._starvation.starvation_count,
                overflow_count=self._fifo.overflow_count,
                worker_utilization=self._workers.utilization,
            )

    async def snapshot(self) -> QueueSnapshot:
        async with self._lock:
            now_ms = _now_ms()
            wait_times: list[float] = []
            depths: dict[str, int] = {}
            for level in PriorityLevel:
                d = self._fifo.depth_by_priority(level)
                if d > 0:
                    depths[level.value] = d
            # Sample wait times
            for level in PriorityLevel:
                for entry in list(self._fifo._queues[level])[:10]:
                    wait_times.append(now_ms - entry.enqueued_ms)
            return QueueSnapshot(
                timestamp=_utcnow(),
                total_queued=self._fifo.total + self._edf.total + self._fair.total,
                depth_by_priority=depths,
                edf_depth=self._edf.total,
                fair_depth=self._fair.total,
                backpressure_active=self._backpressure.active,
                worker_utilization=self._workers.utilization,
                average_wait_ms=sum(wait_times) / max(len(wait_times), 1),
                max_wait_ms=max(wait_times) if wait_times else 0.0,
                overflow_count=self._fifo.overflow_count,
                stale_count=0,
            )

    async def schedule(
        self,
        provider: str,
        model: str,
        priority: PriorityLevel = PriorityLevel.NORMAL,
        deadline_s: float | None = None,
        provider_cost: float = 0.0,
        estimated_latency_ms: float = 0.0,
        queue_affinity: str | None = None,
    ) -> SchedulingDecision:
        return await self.enqueue(
            provider,
            model,
            priority,
            deadline_s,
            provider_cost,
            estimated_latency_ms,
            queue_affinity,
        )

    async def enqueue(
        self,
        provider: str,
        model: str,
        priority: PriorityLevel = PriorityLevel.NORMAL,
        deadline_s: float | None = None,
        provider_cost: float = 0.0,
        estimated_latency_ms: float = 0.0,
        queue_affinity: str | None = None,
    ) -> SchedulingDecision:
        async with self._lock:
            if not self._running:
                return SchedulingDecision(
                    queued=False,
                    reason=SchedulingReason.SCHEDULER_NOT_RUNNING,
                )

            if self._paused:
                return SchedulingDecision(
                    queued=False,
                    reason=SchedulingReason.QUEUE_PAUSED,
                )

            now_ms = _now_ms()
            item_id = _new_id()
            now_dt = _utcnow()
            deadline_dt = None
            if deadline_s is not None:
                deadline_dt = now_dt + timedelta(seconds=deadline_s)

            item = QueueItem(
                id=item_id,
                provider=provider,
                model=model,
                priority=priority,
                created_at=now_dt,
                deadline=deadline_dt,
                cost=provider_cost,
                estimated_latency_ms=estimated_latency_ms,
                queue_affinity=queue_affinity or "",
            )

            entry = _QueueEntry(
                item=item,
                priority_level=priority,
                enqueued_ms=now_ms,
                deadline_ms=(now_ms + deadline_s * 1000) if deadline_s else None,
            )

            # Apply backpressure check
            total_depth = self._fifo.total + self._edf.total + self._fair.total
            self._backpressure.update(total_depth)
            algo = self._scheduler_policy.algorithm
            max_q = self._scheduler_policy.max_queue_depth
            if total_depth >= max_q and algo in ("fifo", "priority"):
                overflow = self._scheduler_policy.overflow_strategy
                if overflow == QueueOverflowStrategy.REJECT:
                    self._publish(
                        Topic.SCHEDULER_QUEUE_OVERFLOW,
                        {"item_id": item_id, "reason": "max queue depth"},
                    )
                    return SchedulingDecision(
                        queued=False,
                        reason=SchedulingReason.QUEUE_FULL,
                        retry_after_ms=_DEFAULT_AGE_SECS * 1000,
                    )

            # Enqueue according to algorithm
            queued = False

            if algo == "edf":
                self._edf.push(entry)
                queued = True
            elif algo == "fair":
                self._fair.push(queue_affinity or provider, entry)
                queued = True
            elif algo in ("fifo", "priority"):
                queued = self._fifo.push(entry, "reject")
            else:  # adaptive_hybrid
                if deadline_s is not None:
                    self._edf.push(entry)
                    queued = True
                elif queue_affinity or provider:
                    self._fair.push(queue_affinity or provider, entry)
                    queued = True
                else:
                    queued = self._fifo.push(entry, "reject")

            if not queued and not (algo in ("edf", "fair") and deadline_s or queue_affinity):
                self._publish(
                    Topic.SCHEDULER_QUEUE_OVERFLOW,
                    {"item_id": item_id, "reason": "queue full"},
                )
                return SchedulingDecision(
                    queued=False,
                    reason=SchedulingReason.QUEUE_FULL,
                    retry_after_ms=_DEFAULT_AGE_SECS * 1000,
                )

            self._balancer.record_push(provider)
            self._publish(Topic.REQUEST_ENQUEUED, {"item_id": item_id, "provider": provider})
            return SchedulingDecision(
                queued=True,
                item_id=item_id,
                position=total_depth + 1,
                reason=SchedulingReason.QUEUED,
            )

    async def dequeue(self) -> DispatchPlan | None:
        async with self._lock:
            if not self._running or self._paused:
                return None

            now_ms = _now_ms()
            algo = self._scheduler_policy.algorithm
            entry: _QueueEntry | None = None

            # Priorities: EDF expiry → starvation aging → dispatch

            # 1. Check EDF for expired items
            for expired in self._edf.expired(now_ms):
                self._expired += 1
                self._metrics_collector.expired_count += 1
                self._metrics_collector.deadline_misses += 1
                self._publish(Topic.REQUEST_EXPIRED, {"item_id": expired.item.id})

            # 2. Check worker availability
            if not self._workers.acquire():
                return None

            # 3. Dequeue by algorithm
            if algo == "edf":
                entry = self._edf.pop()
            elif algo == "fifo":
                entry = self._fifo.pop()
            elif algo == "fair":
                entry = self._fair.pop_wfq()
            elif algo == "wrr":
                entry = self._fair.pop_wrr()
            elif algo == "rr":
                entry = self._fair.pop_rr()
            else:  # adaptive_hybrid
                # Try EDF first, then fair, then FIFO
                entry = self._edf.pop()
                if entry is None:
                    entry = self._fair.pop_wfq()
                if entry is None:
                    entry = self._fifo.pop()

            if entry is None:
                self._workers.release()
                return None

            # Starvation detection
            boost = self._starvation.check(now_ms, entry)
            if boost > 0:
                self._metrics_collector.starvation_count += 1

            # Plan if retried
            retry = self._retry.plan(entry.item.id, 3)

            # Track wait time
            wait_ms = now_ms - entry.enqueued_ms
            self._total_wait += wait_ms

            self._dispatched += 1
            self._predictor.record_dispatch()

            # Update backpressure after dequeue
            self._backpressure.update(self._fifo.total + self._edf.total + self._fair.total)

            # Create reservation
            reservation = DispatchReservation(
                item_id=entry.item.id,
                provider=entry.item.provider,
                model=entry.item.model,
                reserved_at=now_ms,
                expires_at=now_ms + 30000,
            )
            self._reservations[entry.item.id] = reservation

            # Publish event
            self._publish(
                Topic.REQUEST_DEQUEUED,
                {
                    "item_id": entry.item.id,
                    "wait_ms": wait_ms,
                    "boost": boost,
                },
            )

            plan = DispatchPlan(
                item=entry.item,
                priority=entry.priority_level,
                wait_time_ms=wait_ms,
                retry=retry,
                deadline_ms=entry.deadline_ms,
                reservation=reservation,
                algorithm=algo,
            )
            return plan

    async def cancel(self, item_id: str) -> bool:
        async with self._lock:
            found = self._fifo.remove(item_id) or self._edf.remove(item_id)
            if not found:
                # Check fair queue entries
                for group in list(self._fair._queues):
                    q = self._fair._queues[group]
                    for i, entry in enumerate(q):
                        if entry.item.id == item_id:
                            del q[i]
                            self._fair._total -= 1
                            found = True
                            break
                    if found:
                        break
            if found:
                self._canceled += 1
                self._publish(Topic.REQUEST_CANCELLED, {"item_id": item_id})
            return found

    async def pause(self, reason: str = "") -> None:
        async with self._lock:
            self._paused = True
            self._pause_reason = reason
            self._health = replace(self._health, status="paused")
            self._publish(Topic.BACKPRESSURE_ENABLED, {"reason": reason})
        log.info("SchedulerEngine paused", extra={"reason": reason})

    async def resume(self) -> None:
        async with self._lock:
            self._paused = False
            self._pause_reason = ""
            self._health = replace(self._health, status="running")
            self._publish(Topic.BACKPRESSURE_DISABLED)
        log.info("SchedulerEngine resumed")

    # ── Internal ──

    def _update_health(self) -> None:
        total = self._fifo.total + self._edf.total + self._fair.total
        self._health = SchedulerHealth(
            status=self._health.status,
            uptime_s=time.monotonic() - self._started_at if self._started_at > 0 else 0.0,
            total_queued=total,
            total_dispatched=self._dispatched,
            total_expired=self._expired,
            total_canceled=self._canceled,
            total_retries=self._retry.total_retries,
            backpressure_active=self._backpressure.active,
            queue_full_pct=total / max(self._scheduler_policy.max_queue_depth, 1),
            worker_utilization=self._workers.utilization,
            error_count=0,
            last_error="",
        )

    def _average_wait(self) -> float:
        if self._dispatched == 0:
            return 0.0
        return self._total_wait / self._dispatched

    def _publish(self, topic: Topic, payload: dict | None = None) -> None:
        if self._event_bus is None:
            return
        try:
            envelope = EventEnvelope(
                type=topic.value,
                source="omniroute.scheduler",
                topic=topic.value,
                payload=payload or {},
            )
            asyncio.ensure_future(self._event_bus.publish(envelope))
        except Exception:
            log.warning("Failed to publish scheduler event", extra={"topic": topic.value})
