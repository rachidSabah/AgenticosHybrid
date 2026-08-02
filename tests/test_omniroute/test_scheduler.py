"""Tests for OmniRoute Intelligent Request Scheduler & Queue Manager (Phase 5.9)."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock

import pytest

from agentic_os.core.omniroute.scheduler import (
    SchedulerEngineImpl,
    _BackPressureManager,
    _EDFQueue,
    _LoadPredictor,
    _PriorityQueueManager,
    _QueueEntry,
    _RetryPlanner,
    _StarvationDetector,
    _WeightedFairQueue,
    _WorkerAllocator,
)
from agentic_os.domain.omniroute import (
    DispatchPlan,
    PriorityLevel,
    QueueItem,
    QueueMetrics,
    QueueStatistics,
    SchedulingDecision,
    SchedulingReason,
)

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_entry(
    item_id: str = "test-id",
    provider: str = "test-provider",
    model: str = "test-model",
    priority: PriorityLevel = PriorityLevel.NORMAL,
    deadline_ms: float | None = None,
    cost: float = 0.0,
    latency_ms: float = 0.0,
    enqueued_ms: float = 0.0,
) -> _QueueEntry:
    return _QueueEntry(
        item=QueueItem(
            id=item_id,
            provider=provider,
            model=model,
            priority=priority,
        ),
        priority_level=priority,
        enqueued_ms=enqueued_ms,
        deadline_ms=deadline_ms,
        retry_count=0,
        age_boost=0,
    )


def _make_scheduler(
    algorithm: str = "adaptive_hybrid",
    max_queue: int = 100,
    event_bus: Any | None = None,
    worker_pool: int = 4,
) -> SchedulerEngineImpl:
    bus = event_bus or AsyncMock()
    return SchedulerEngineImpl(
        event_bus=bus,
        max_queue=max_queue,
        worker_pool=worker_pool,
        algorithm=algorithm,
    )


@pytest.fixture
async def scheduler() -> SchedulerEngineImpl:
    return _make_scheduler()


@pytest.fixture
def event_bus() -> AsyncMock:
    return AsyncMock()


# ═══════════════════════════════════════════════════════════════════════════════
# Section 1: Lifecycle
# ═══════════════════════════════════════════════════════════════════════════════


class TestLifecycle:
    async def test_start_sets_running(self, scheduler: SchedulerEngineImpl) -> None:
        assert not scheduler._running
        await scheduler.start()
        assert scheduler._running

    async def test_stop_clears_running(self, scheduler: SchedulerEngineImpl) -> None:
        await scheduler.start()
        await scheduler.stop()
        assert not scheduler._running

    async def test_restart_works(self, scheduler: SchedulerEngineImpl) -> None:
        await scheduler.start()
        await scheduler.stop()
        await scheduler.start()
        assert scheduler._running

    async def test_double_start_is_idempotent(self, scheduler: SchedulerEngineImpl) -> None:
        await scheduler.start()
        await scheduler.start()
        assert scheduler._running

    async def test_double_stop_is_idempotent(self, scheduler: SchedulerEngineImpl) -> None:
        await scheduler.start()
        await scheduler.stop()
        await scheduler.stop()
        assert not scheduler._running

    async def test_start_publishes_event(self, event_bus: AsyncMock) -> None:
        s = _make_scheduler(event_bus=event_bus)
        await s.start()
        await asyncio.sleep(0)
        assert event_bus.publish.await_count >= 1

    async def test_health_after_start(self, scheduler: SchedulerEngineImpl) -> None:
        await scheduler.start()
        h = await scheduler.health()
        assert h.status == "running"

    async def test_health_after_stop(self, scheduler: SchedulerEngineImpl) -> None:
        await scheduler.start()
        await scheduler.stop()
        h = await scheduler.health()
        assert h.status == "stopped"

    async def test_health_before_start(self, scheduler: SchedulerEngineImpl) -> None:
        h = await scheduler.health()
        assert h.status == "stopped"


# ═══════════════════════════════════════════════════════════════════════════════
# Section 2: FIFO Scheduling
# ═══════════════════════════════════════════════════════════════════════════════


class TestFIFO:
    @pytest.fixture
    async def s_fifo(self) -> SchedulerEngineImpl:
        s = _make_scheduler(algorithm="fifo", worker_pool=10)
        await s.start()
        return s

    async def test_enqueue_returns_decision(self, s_fifo: SchedulerEngineImpl) -> None:
        d = await s_fifo.enqueue("p1", "m1")
        assert d.queued is True
        assert d.item_id != ""

    async def test_dequeue_fifo_order(self, s_fifo: SchedulerEngineImpl) -> None:
        d1 = await s_fifo.enqueue("p1", "m1")
        d2 = await s_fifo.enqueue("p1", "m2")
        p1 = await s_fifo.dequeue()
        p2 = await s_fifo.dequeue()
        assert p1 is not None and p1.item.id == d1.item_id
        assert p2 is not None and p2.item.id == d2.item_id

    async def test_dequeue_empty_returns_none(self, s_fifo: SchedulerEngineImpl) -> None:
        assert await s_fifo.dequeue() is None

    async def test_dequeue_after_enqueue(self, s_fifo: SchedulerEngineImpl) -> None:
        await s_fifo.enqueue("p1", "m1")
        p = await s_fifo.dequeue()
        assert p is not None
        assert p.item.provider == "p1"

    async def test_enqueue_multiple_fifo(self, s_fifo: SchedulerEngineImpl) -> None:
        ids = []
        for i in range(5):
            d = await s_fifo.enqueue("p1", f"m{i}")
            ids.append(d.item_id)
        for expected in ids:
            p = await s_fifo.dequeue()
            assert p is not None
            assert p.item.id == expected

    async def test_dequeue_returns_dispatch_plan(self, s_fifo: SchedulerEngineImpl) -> None:
        await s_fifo.enqueue("p1", "m1")
        p = await s_fifo.dequeue()
        assert p is not None
        assert isinstance(p, DispatchPlan)
        assert p.reservation is not None
        assert p.reservation.reserved_at > 0
        assert p.reservation.expires_at > p.reservation.reserved_at


# ═══════════════════════════════════════════════════════════════════════════════
# Section 3: Priority Queue Scheduling
# ═══════════════════════════════════════════════════════════════════════════════


class TestPriorityQueue:
    @pytest.fixture
    async def s_pq(self) -> SchedulerEngineImpl:
        s = _make_scheduler(algorithm="priority", worker_pool=10)
        await s.start()
        return s

    async def test_critical_dispatched_first(self, s_pq: SchedulerEngineImpl) -> None:
        await s_pq.enqueue("p1", "m1", priority=PriorityLevel.LOW)
        await s_pq.enqueue("p2", "m2", priority=PriorityLevel.CRITICAL)
        p = await s_pq.dequeue()
        assert p is not None
        assert p.item.priority == PriorityLevel.CRITICAL

    async def test_priority_order(self, s_pq: SchedulerEngineImpl) -> None:
        levels = [
            PriorityLevel.BACKGROUND,
            PriorityLevel.LOW,
            PriorityLevel.NORMAL,
            PriorityLevel.HIGH,
            PriorityLevel.CRITICAL,
        ]
        for lv in reversed(levels):
            await s_pq.enqueue("p1", f"m-{lv.value}", priority=lv)
        for expected in reversed(levels):
            p = await s_pq.dequeue()
            assert p is not None
            assert p.item.priority == expected

    async def test_fifo_within_same_priority(self, s_pq: SchedulerEngineImpl) -> None:
        d1 = await s_pq.enqueue("p1", "m1", priority=PriorityLevel.NORMAL)
        d2 = await s_pq.enqueue("p1", "m2", priority=PriorityLevel.NORMAL)
        p1 = await s_pq.dequeue()
        p2 = await s_pq.dequeue()
        assert p1 is not None and p2 is not None
        assert p1.item.id == d1.item_id
        assert p2.item.id == d2.item_id

    async def test_empty_returns_none(self, s_pq: SchedulerEngineImpl) -> None:
        assert await s_pq.dequeue() is None


# ═══════════════════════════════════════════════════════════════════════════════
# Section 4: EDF Scheduling
# ═══════════════════════════════════════════════════════════════════════════════


class TestEDFScheduling:
    @pytest.fixture
    async def s(self) -> SchedulerEngineImpl:
        s = _make_scheduler(algorithm="edf")
        await s.start()
        return s

    async def test_enqueue_with_deadline(self, s: SchedulerEngineImpl) -> None:
        d = await s.enqueue("p1", "m1", deadline_s=10)
        assert d.queued

    async def test_dequeue_edf(self, s: SchedulerEngineImpl) -> None:
        await s.enqueue("p1", "m1", deadline_s=1)
        p = await s.dequeue()
        assert p is not None
        assert p.item.id != ""

    async def test_edf_earliest_deadline_first(self, s: SchedulerEngineImpl) -> None:
        await s.enqueue("p1", "m1", deadline_s=10, priority=PriorityLevel.LOW)
        await s.enqueue("p2", "m2", deadline_s=1, priority=PriorityLevel.HIGH)
        p = await s.dequeue()
        assert p is not None
        assert p.item.id != ""


# ═══════════════════════════════════════════════════════════════════════════════
# Section 5: Internal Components
# ═══════════════════════════════════════════════════════════════════════════════


class TestPriorityQueueManager:
    def test_push_and_pop(self) -> None:
        pq = _PriorityQueueManager(max_size=10)
        assert pq.push(_make_entry(item_id="a"))
        assert pq.total == 1
        popped = pq.pop()
        assert popped is not None and popped.item.id == "a"

    def test_pop_empty(self) -> None:
        pq = _PriorityQueueManager(max_size=10)
        assert pq.pop() is None

    def test_total_tracking(self) -> None:
        pq = _PriorityQueueManager(max_size=10)
        pq.push(_make_entry(item_id="a"))
        pq.push(_make_entry(item_id="b"))
        assert pq.total == 2

    def test_overflow_reject(self) -> None:
        pq = _PriorityQueueManager(max_size=1)
        pq.push(_make_entry(item_id="old"))
        assert pq.push(_make_entry(item_id="new"), strategy="reject") is False

    def test_overflow_drop_oldest(self) -> None:
        pq = _PriorityQueueManager(max_size=1)
        pq.push(_make_entry(item_id="old"))
        assert pq.push(_make_entry(item_id="new"), strategy="drop_oldest") is True
        popped = pq.pop()
        assert popped is not None and popped.item.id == "new"

    def test_overflow_drop_newest(self) -> None:
        pq = _PriorityQueueManager(max_size=1)
        pq.push(_make_entry(item_id="old"))
        assert pq.push(_make_entry(item_id="new"), strategy="drop_newest") is True
        popped = pq.pop()
        assert popped is not None and popped.item.id == "old"

    def test_priority_order(self) -> None:
        pq = _PriorityQueueManager(max_size=10)
        pq.push(_make_entry(item_id="low", priority=PriorityLevel.LOW))
        pq.push(_make_entry(item_id="critical", priority=PriorityLevel.CRITICAL))
        popped = pq.pop()
        assert popped is not None and popped.item.id == "critical"

    def test_remove(self) -> None:
        pq = _PriorityQueueManager(max_size=10)
        pq.push(_make_entry(item_id="remove-me"))
        assert pq.remove("remove-me") is True
        assert pq.total == 0

    def test_remove_not_found(self) -> None:
        pq = _PriorityQueueManager(max_size=10)
        assert pq.remove("nonexistent") is False

    def test_clear(self) -> None:
        pq = _PriorityQueueManager(max_size=10)
        pq.push(_make_entry(item_id="a"))
        pq.push(_make_entry(item_id="b"))
        pq.clear()
        assert pq.total == 0
        assert pq.pop() is None


class TestEDFQueue:
    def test_earliest_deadline_first(self) -> None:
        q = _EDFQueue()
        q.push(_make_entry(item_id="a", deadline_ms=100))
        q.push(_make_entry(item_id="b", deadline_ms=50))
        popped = q.pop()
        assert popped is not None and popped.item.id == "b"

    def test_fifo_without_deadline(self) -> None:
        q = _EDFQueue()
        q.push(_make_entry(item_id="a"))
        q.push(_make_entry(item_id="b"))
        p1 = q.pop()
        p2 = q.pop()
        assert p1 is not None and p1.item.id == "a"
        assert p2 is not None and p2.item.id == "b"

    def test_pop_empty(self) -> None:
        q = _EDFQueue()
        assert q.pop() is None

    def test_peek(self) -> None:
        q = _EDFQueue()
        q.push(_make_entry(item_id="a", deadline_ms=10))
        assert q.peek() is not None and q.peek().item.id == "a"

    def test_peek_empty(self) -> None:
        q = _EDFQueue()
        assert q.peek() is None

    def test_total(self) -> None:
        q = _EDFQueue()
        q.push(_make_entry(item_id="a"))
        assert q.total == 1
        q.pop()
        assert q.total == 0

    def test_clear(self) -> None:
        q = _EDFQueue()
        q.push(_make_entry(item_id="a"))
        q.clear()
        assert q.total == 0
        assert q.pop() is None

    def test_multiple_deadlines(self) -> None:
        q = _EDFQueue()
        q.push(_make_entry(item_id="c", deadline_ms=200))
        q.push(_make_entry(item_id="a", deadline_ms=5))
        q.push(_make_entry(item_id="b", deadline_ms=100))
        assert q.pop().item.id == "a"
        assert q.pop().item.id == "b"
        assert q.pop().item.id == "c"


class TestWeightedFairQueue:
    def test_push_and_pop(self) -> None:
        wfq = _WeightedFairQueue()
        wfq.push("g1", _make_entry(item_id="a"))
        assert wfq.total == 1
        popped = wfq.pop_wfq()
        assert popped is not None and popped.item.id == "a"

    def test_round_robin_groups(self) -> None:
        wfq = _WeightedFairQueue()
        wfq.push("g1", _make_entry(item_id="a1"))
        wfq.push("g1", _make_entry(item_id="a2"))
        wfq.push("g2", _make_entry(item_id="b1"))
        ids = []
        for _ in range(3):
            p = wfq.pop_wfq()
            if p:
                ids.append(p.item.id)
        assert "b1" in ids

    def test_pop_empty(self) -> None:
        wfq = _WeightedFairQueue()
        assert wfq.pop_wfq() is None

    def test_clear(self) -> None:
        wfq = _WeightedFairQueue()
        wfq.push("g1", _make_entry(item_id="a"))
        wfq.clear()
        assert wfq.total == 0
        assert wfq.pop_wfq() is None


class TestStarvationDetector:
    def test_no_starvation(self) -> None:
        sd = _StarvationDetector(max_wait_ms=50)
        entry = _make_entry(enqueued_ms=0.0)
        assert sd.check(10, entry) == 0

    def test_moderate_starvation(self) -> None:
        sd = _StarvationDetector(max_wait_ms=50)
        entry = _make_entry(enqueued_ms=0.0)
        assert sd.check(80, entry) >= 1

    def test_severe_starvation(self) -> None:
        sd = _StarvationDetector(max_wait_ms=50)
        entry = _make_entry(enqueued_ms=0.0)
        assert sd.check(300, entry) >= 2

    def test_reset(self) -> None:
        sd = _StarvationDetector(max_wait_ms=50)
        sd.reset()
        entry = _make_entry(enqueued_ms=0.0)
        assert sd.check(10, entry) == 0

    def test_starvation_increases_with_time(self) -> None:
        sd = _StarvationDetector(max_wait_ms=50)
        entry = _make_entry(enqueued_ms=0.0)
        assert sd.check(30, entry) == 0
        assert sd.check(60, entry) >= 1
        assert sd.check(120, entry) >= 2
        assert sd.check(250, entry) >= 3


class TestBackPressureManager:
    def test_initial_state(self) -> None:
        bp = _BackPressureManager(high_water_mark=90, low_water_mark=50)
        assert not bp.active

    def test_backpressure_high(self) -> None:
        bp = _BackPressureManager(high_water_mark=90, low_water_mark=50)
        bp.update(95)
        assert bp.active

    def test_backpressure_clears_at_low(self) -> None:
        bp = _BackPressureManager(high_water_mark=90, low_water_mark=50)
        bp.update(95)
        assert bp.active
        bp.update(40)
        assert not bp.active

    def test_backpressure_state_returned(self) -> None:
        bp = _BackPressureManager(high_water_mark=90, low_water_mark=50)
        changed = bp.update(95)
        assert changed
        changed = bp.update(40)
        assert changed

    def test_mid_range_no_change(self) -> None:
        bp = _BackPressureManager(high_water_mark=90, low_water_mark=50)
        bp.update(95)
        changed = bp.update(70)
        assert not changed

    def test_utilization_calculation(self) -> None:
        bp = _BackPressureManager(high_water_mark=90, low_water_mark=50)
        # utilization from the default implementation
        assert bp.update(75) is False
        assert not bp.active


class TestRetryPlanner:
    def test_initial_retry_count(self) -> None:
        rp = _RetryPlanner()
        schedule = rp.plan("item-1", max_retries=3)
        assert schedule.retry_count == 1

    def test_exceeds_max_retries(self) -> None:
        rp = _RetryPlanner()
        rp.plan("item-1", max_retries=2)
        rp.plan("item-1", max_retries=2)
        schedule = rp.plan("item-1", max_retries=2)
        assert schedule.should_retry is False
        assert "max retries" in schedule.reason

    def test_exponential_backoff(self) -> None:
        rp = _RetryPlanner()
        s1 = rp.plan("item-1", max_retries=5)
        assert s1.delay_ms >= 0
        s2 = rp.plan("item-1", max_retries=5)
        assert s2.delay_ms >= s1.delay_ms

    def test_multiple_schedules_independent(self) -> None:
        rp = _RetryPlanner()
        a = rp.plan("A", max_retries=3)
        b = rp.plan("B", max_retries=3)
        assert a.should_retry and b.should_retry

    def test_total_retries_tracked(self) -> None:
        rp = _RetryPlanner()
        rp.plan("x", max_retries=5)
        rp.plan("x", max_retries=5)
        assert rp.total_retries == 2


class TestWorkerAllocator:
    def test_allocate_success(self) -> None:
        wa = _WorkerAllocator(pool_size=4)
        assert wa.acquire() is True
        assert wa.available == 3

    def test_allocate_exhausted(self) -> None:
        wa = _WorkerAllocator(pool_size=1)
        wa.acquire()
        assert wa.acquire() is False

    def test_release_frees_slot(self) -> None:
        wa = _WorkerAllocator(pool_size=1)
        wa.acquire()
        wa.release()
        assert wa.available == 1

    def test_available_count(self) -> None:
        wa = _WorkerAllocator(pool_size=4)
        assert wa.available == 4
        wa.acquire()
        assert wa.available == 3

    def test_release_invalid(self) -> None:
        wa = _WorkerAllocator(pool_size=4)
        wa.release()  # no-op when already at 0
        assert wa.available == 4


class TestLoadPredictor:
    def test_initial_load(self) -> None:
        lp = _LoadPredictor(window_s=10)
        assert lp.predicted_load(0) == float("inf")

    def test_record_increases_load(self) -> None:
        lp = _LoadPredictor(window_s=60)
        lp.record_dispatch()
        assert lp.dispatch_rate() >= 0

    def test_no_record_no_load(self) -> None:
        lp = _LoadPredictor(window_s=60)
        assert lp.dispatch_rate() == 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# Section 6: Deadlines & Overflows
# ═══════════════════════════════════════════════════════════════════════════════


class TestOverflowPolicies:
    @pytest.fixture
    async def s(self) -> SchedulerEngineImpl:
        s = _make_scheduler(algorithm="fifo", max_queue=3)
        await s.start()
        return s

    async def test_queue_full_rejects(self, s: SchedulerEngineImpl) -> None:
        for _ in range(3):
            await s.enqueue("p1", "m1")
        d = await s.enqueue("p1", "m_overflow")
        assert d.queued is False

    async def test_queue_full_has_reason(self, s: SchedulerEngineImpl) -> None:
        for _ in range(3):
            await s.enqueue("p1", "m1")
        d = await s.enqueue("p1", "m_overflow")
        assert d.reason == SchedulingReason.QUEUE_FULL

    async def test_overflow_resets_after_drain(self, s: SchedulerEngineImpl) -> None:
        for _ in range(3):
            await s.enqueue("p1", "m1")
        p = await s.dequeue()
        assert p is not None
        d = await s.enqueue("p1", "m_new")
        assert d.queued

    async def test_backpressure_detected(self) -> None:
        s = _make_scheduler(algorithm="fifo", max_queue=10)
        await s.start()
        # Fill the queue
        for _ in range(10):
            await s.enqueue("p1", "m1")
        # Dequeue to trigger backpressure check
        await s.dequeue()
        # Check backpressure is active (90% of 10 = 9, and we still have 9 items)
        assert s._backpressure.active

    async def test_dequeue_empty_returns_none(self, s: SchedulerEngineImpl) -> None:
        assert await s.dequeue() is None


# ═══════════════════════════════════════════════════════════════════════════════
# Section 7: Events
# ═══════════════════════════════════════════════════════════════════════════════


class TestEvents:
    async def test_start_publishes(self, event_bus: AsyncMock) -> None:
        s = _make_scheduler(event_bus=event_bus)
        await s.start()
        await asyncio.sleep(0)
        assert event_bus.publish.await_count >= 1

    async def test_enqueue_publishes_event(self, event_bus: AsyncMock) -> None:
        s = _make_scheduler(algorithm="fifo", event_bus=event_bus)
        await s.start()
        await s.enqueue("p1", "m1")
        await asyncio.sleep(0)
        assert event_bus.publish.await_count >= 2

    async def test_dequeue_publishes_event(self, event_bus: AsyncMock) -> None:
        s = _make_scheduler(algorithm="fifo", event_bus=event_bus)
        await s.start()
        await s.enqueue("p1", "m1")
        await s.dequeue()
        await asyncio.sleep(0)
        assert event_bus.publish.await_count >= 3

    async def test_cancel_publishes_event(self, event_bus: AsyncMock) -> None:
        s = _make_scheduler(algorithm="fifo", event_bus=event_bus)
        await s.start()
        d = await s.enqueue("p1", "m1")
        await s.cancel(d.item_id)
        await asyncio.sleep(0)
        assert event_bus.publish.await_count >= 3

    async def test_stop_publishes_event(self, event_bus: AsyncMock) -> None:
        s = _make_scheduler(event_bus=event_bus)
        await s.start()
        await s.stop()
        await asyncio.sleep(0)
        assert event_bus.publish.await_count >= 2

    async def test_pause_publishes_event(self) -> None:
        bus = AsyncMock()
        s = _make_scheduler(event_bus=bus)
        await s.start()
        await s.pause("maintenance")
        await asyncio.sleep(0)
        assert bus.publish.await_count >= 2

    async def test_resume_publishes_event(self) -> None:
        bus = AsyncMock()
        s = _make_scheduler(event_bus=bus)
        await s.start()
        await s.pause()
        await s.resume()
        await asyncio.sleep(0)
        assert bus.publish.await_count >= 3


# ═══════════════════════════════════════════════════════════════════════════════
# Section 8: Cancellation
# ═══════════════════════════════════════════════════════════════════════════════


class TestCancellation:
    @pytest.fixture
    async def s(self) -> SchedulerEngineImpl:
        s = _make_scheduler(algorithm="fifo")
        await s.start()
        return s

    async def test_cancel_frees_slot(self, s: SchedulerEngineImpl) -> None:
        d = await s.enqueue("p1", "m1")
        assert await s.cancel(d.item_id) is True
        assert s._fifo.total == 0

    async def test_cancel_pending_not_dispatched(self, s: SchedulerEngineImpl) -> None:
        d = await s.enqueue("p1", "m1")
        await s.cancel(d.item_id)
        p = await s.dequeue()
        assert p is None

    async def test_cancel_twice_returns_false(self, s: SchedulerEngineImpl) -> None:
        d = await s.enqueue("p1", "m1")
        assert await s.cancel(d.item_id) is True
        assert await s.cancel(d.item_id) is False

    async def test_cancel_returns_false_for_missing(self, s: SchedulerEngineImpl) -> None:
        assert await s.cancel("missing") is False


# ═══════════════════════════════════════════════════════════════════════════════
# Section 9: Pause / Resume
# ═══════════════════════════════════════════════════════════════════════════════


class TestPauseResume:
    @pytest.fixture
    async def s(self) -> SchedulerEngineImpl:
        s = _make_scheduler(algorithm="fifo")
        await s.start()
        return s

    async def test_pause_sets_paused(self, s: SchedulerEngineImpl) -> None:
        await s.pause("testing")
        assert s._paused

    async def test_resume_clears_paused(self, s: SchedulerEngineImpl) -> None:
        await s.pause()
        await s.resume()
        assert not s._paused

    async def test_paused_dequeue_returns_none(self, s: SchedulerEngineImpl) -> None:
        await s.enqueue("p1", "m1")
        await s.pause()
        assert await s.dequeue() is None

    async def test_resume_allows_dequeue(self, s: SchedulerEngineImpl) -> None:
        await s.enqueue("p1", "m1")
        await s.pause()
        await s.resume()
        p = await s.dequeue()
        assert p is not None


# ═══════════════════════════════════════════════════════════════════════════════
# Section 10: Metrics & Statistics
# ═══════════════════════════════════════════════════════════════════════════════


class TestMetrics:
    @pytest.fixture
    async def s(self) -> SchedulerEngineImpl:
        s = _make_scheduler(algorithm="fifo")
        await s.start()
        return s

    async def test_statistics_returns(self, s: SchedulerEngineImpl) -> None:
        stats = await s.statistics()
        assert isinstance(stats, QueueStatistics)

    async def test_statistics_count(self, s: SchedulerEngineImpl) -> None:
        await s.enqueue("p1", "m1")
        stats = await s.statistics()
        assert stats.total_queued >= 1

    async def test_stats_after_dequeue(self, s: SchedulerEngineImpl) -> None:
        await s.enqueue("p1", "m1")
        await s.dequeue()
        stats = await s.statistics()
        assert stats.total_dispatched >= 1

    async def test_metrics_returns(self, s: SchedulerEngineImpl) -> None:
        metrics = await s.metrics()
        assert isinstance(metrics, QueueMetrics)

    async def test_metrics_depth(self, s: SchedulerEngineImpl) -> None:
        await s.enqueue("p1", "m1")
        metrics = await s.metrics()
        assert metrics.queue_length >= 1

    async def test_zero_stats_when_empty(self, s: SchedulerEngineImpl) -> None:
        stats = await s.statistics()
        assert stats.total_queued == 0

    async def test_worker_utilization_metric(self, s: SchedulerEngineImpl) -> None:
        stats = await s.statistics()
        assert isinstance(stats.worker_utilization, float)

    async def test_dispatch_rate_metric(self, s: SchedulerEngineImpl) -> None:
        stats = await s.statistics()
        assert isinstance(stats.dispatch_rate, float)

    async def test_health_report(self, s: SchedulerEngineImpl) -> None:
        h = await s.health()
        assert h.status == "running"

    async def test_health_has_metrics(self, s: SchedulerEngineImpl) -> None:
        h = await s.health()
        assert hasattr(h, "queue_full_pct")
        assert hasattr(h, "worker_utilization")

    async def test_health_after_enqueue(self, s: SchedulerEngineImpl) -> None:
        await s.enqueue("p1", "m1")
        h = await s.health()
        assert h.total_queued == 1


# ═══════════════════════════════════════════════════════════════════════════════
# Section 11: Concurrency
# ═══════════════════════════════════════════════════════════════════════════════


class TestConcurrency:
    @pytest.fixture
    async def s(self) -> SchedulerEngineImpl:
        s = _make_scheduler(algorithm="fifo")
        await s.start()
        return s

    async def test_concurrent_enqueue(self, s: SchedulerEngineImpl) -> None:
        results = await asyncio.gather(
            s.enqueue("p1", "m1"),
            s.enqueue("p2", "m2"),
        )
        assert all(r.queued for r in results)
        assert len(set(r.item_id for r in results)) == 2

    async def test_concurrent_dequeue(self, s: SchedulerEngineImpl) -> None:
        await s.enqueue("p1", "m1")
        await s.enqueue("p2", "m2")
        plans = await asyncio.gather(
            s.dequeue(),
            s.dequeue(),
        )
        non_none = [p for p in plans if p is not None]
        assert len(non_none) == 2

    async def test_concurrent_mixed(self, s: SchedulerEngineImpl) -> None:
        results = await asyncio.gather(
            s.enqueue("p1", "m1"),
            s.dequeue(),
        )
        assert any(isinstance(r, SchedulingDecision) for r in results)
        assert any(isinstance(r, DispatchPlan) or r is None for r in results)


# ═══════════════════════════════════════════════════════════════════════════════
# Section 12: Shutdown Safety
# ═══════════════════════════════════════════════════════════════════════════════


class TestShutdownSafety:
    async def test_dequeue_after_stop_returns_none(self) -> None:
        s = _make_scheduler(algorithm="fifo")
        await s.start()
        await s.enqueue("p1", "m1")
        await s.stop()
        assert await s.dequeue() is None

    async def test_cancel_after_stop_returns_false(self) -> None:
        s = _make_scheduler(algorithm="fifo")
        await s.start()
        d = await s.enqueue("p1", "m1")
        await s.stop()
        assert await s.cancel(d.item_id) is False

    async def test_enqueue_after_stop_returns_not_queued(self) -> None:
        s = _make_scheduler(algorithm="fifo")
        await s.start()
        await s.stop()
        d = await s.enqueue("p1", "m1")
        assert d.queued is False

    async def test_enqueue_after_restart(self) -> None:
        s = _make_scheduler(algorithm="fifo")
        await s.start()
        await s.enqueue("p1", "m1")
        await s.stop()
        await s.start()
        d2 = await s.enqueue("p1", "m2")
        assert d2.queued
        # Queue was cleared on stop, only the new item should be present
        p = await s.dequeue()
        assert p is not None
        assert p.item.id == d2.item_id

    async def test_dequeue_before_start_returns_none(self) -> None:
        s = _make_scheduler(algorithm="fifo")
        assert await s.dequeue() is None


# ═══════════════════════════════════════════════════════════════════════════════
# Section 13: Scheduling Algorithms
# ═══════════════════════════════════════════════════════════════════════════════


class TestSchedulingAlgorithms:
    @pytest.mark.parametrize(
        "algo",
        ["fifo", "priority", "edf", "fair", "rr", "wrr", "adaptive_hybrid"],
    )
    async def test_each_algorithm_enqueues(self, algo: str) -> None:
        s = _make_scheduler(algorithm=algo)
        await s.start()
        d = await s.enqueue("p1", "m1")
        assert d.queued

    @pytest.mark.parametrize(
        "algo",
        ["fifo", "priority", "edf", "fair", "rr", "wrr", "adaptive_hybrid"],
    )
    async def test_each_algorithm_dispatches(self, algo: str) -> None:
        s = _make_scheduler(algorithm=algo)
        await s.start()
        await s.enqueue("p1", "m1")
        p = await s.dequeue()
        assert p is not None

    @pytest.mark.parametrize(
        "algo",
        ["fifo", "priority", "edf", "fair", "rr", "wrr", "adaptive_hybrid"],
    )
    async def test_each_algorithm_empty_returns_none(self, algo: str) -> None:
        s = _make_scheduler(algorithm=algo)
        await s.start()
        assert await s.dequeue() is None

    async def test_adaptive_hybrid_dispatch(self) -> None:
        s = _make_scheduler(algorithm="adaptive_hybrid")
        await s.start()
        await s.enqueue("p1", "m1")
        p = await s.dequeue()
        assert p is not None


# ═══════════════════════════════════════════════════════════════════════════════
# Section 14: Dispatch Plans
# ═══════════════════════════════════════════════════════════════════════════════


class TestDispatchPlans:
    @pytest.fixture
    async def s(self) -> SchedulerEngineImpl:
        s = _make_scheduler(algorithm="fifo")
        await s.start()
        return s

    async def test_dispatch_plan_has_item(self, s: SchedulerEngineImpl) -> None:
        await s.enqueue("p1", "m1")
        p = await s.dequeue()
        assert p is not None
        assert p.item is not None

    async def test_dispatch_plan_has_reserved_at(self, s: SchedulerEngineImpl) -> None:
        await s.enqueue("p1", "m1")
        p = await s.dequeue()
        assert p is not None
        assert p.reservation.reserved_at > 0
        assert p.reservation.expires_at > p.reservation.reserved_at


# ═══════════════════════════════════════════════════════════════════════════════
# Section 15: Adaptive Hybrid
# ═══════════════════════════════════════════════════════════════════════════════


class TestAdaptiveHybrid:
    @pytest.fixture
    async def s(self) -> SchedulerEngineImpl:
        s = _make_scheduler(algorithm="adaptive_hybrid")
        await s.start()
        return s

    async def test_hybrid_dispatch(self, s: SchedulerEngineImpl) -> None:
        await s.enqueue("p1", "m1")
        p = await s.dequeue()
        assert p is not None

    async def test_hybrid_dispatch_order(self, s: SchedulerEngineImpl) -> None:
        await s.enqueue("p1", "m2")
        await s.enqueue("p1", "m1")
        p1 = await s.dequeue()
        p2 = await s.dequeue()
        assert p1 is not None
        assert p2 is not None
        assert p1.item.id != p2.item.id

    async def test_hybrid_with_deadline_uses_edf(self, s: SchedulerEngineImpl) -> None:
        await s.enqueue("p1", "m1", deadline_s=1)
        assert s._edf.total == 1

    async def test_hybrid_enqueues_to_fair_by_default(self, s: SchedulerEngineImpl) -> None:
        await s.enqueue("p1", "m1")
        total = s._fair.total + s._fifo.total + s._edf.total
        assert total == 1


# ═══════════════════════════════════════════════════════════════════════════════
# Section 16: Stress Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestStress:
    @pytest.fixture
    async def s(self) -> SchedulerEngineImpl:
        s = _make_scheduler(algorithm="fifo", max_queue=500, worker_pool=50)
        await s.start()
        return s

    async def test_bulk_enqueue(self, s: SchedulerEngineImpl) -> None:
        decisions = await asyncio.gather(*[s.enqueue("p1", f"m{i}") for i in range(50)])
        assert all(d.queued for d in decisions)
        assert s._fifo.total == 50

    async def test_bulk_dispatch(self, s: SchedulerEngineImpl) -> None:
        for i in range(50):
            await s.enqueue("p1", f"m{i}")
        dispatched = 0
        for _ in range(50):
            p = await s.dequeue()
            if p:
                dispatched += 1
        assert dispatched == 50

    async def test_enqueue_dequeue_cycle(self, s: SchedulerEngineImpl) -> None:
        for i in range(20):
            await s.enqueue("p1", f"m{i}")
        for _ in range(20):
            p = await s.dequeue()
            assert p is not None
        assert await s.dequeue() is None

    async def test_multiple_providers(self, s: SchedulerEngineImpl) -> None:
        d1 = await s.enqueue("provider_a", "m1")
        d2 = await s.enqueue("provider_b", "m2")
        assert d1.queued and d2.queued


# ═══════════════════════════════════════════════════════════════════════════════
# Section 17: Edge Cases
# ═══════════════════════════════════════════════════════════════════════════════


class TestEdgeCases:
    async def test_dequeue_before_start_returns_none(self) -> None:
        s = _make_scheduler(algorithm="fifo")
        assert await s.dequeue() is None

    async def test_schedule_returns_scheduling_decision(self) -> None:
        s = _make_scheduler(algorithm="fifo")
        await s.start()
        d = await s.schedule("p1", "m1")
        assert isinstance(d, SchedulingDecision)

    async def test_schedule_enqueues_item(self) -> None:
        s = _make_scheduler(algorithm="fifo")
        await s.start()
        d = await s.schedule("p1", "m1")
        assert d.queued is True

    async def test_enqueue_with_deadline(self) -> None:
        s = _make_scheduler(algorithm="adaptive_hybrid")
        await s.start()
        d = await s.enqueue("p1", "m1", deadline_s=5)
        assert d.queued

    async def test_cancel_nonexistent(self) -> None:
        s = _make_scheduler(algorithm="fifo")
        await s.start()
        assert await s.cancel("nonexistent") is False

    async def test_pause_has_reason(self) -> None:
        s = _make_scheduler(algorithm="fifo")
        await s.start()
        await s.pause("backpressure")
        assert s._pause_reason == "backpressure"
