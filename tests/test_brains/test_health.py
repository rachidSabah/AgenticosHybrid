"""Tests for BrainHealthMonitor — periodic heartbeat checks and stale detection."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock

import pytest

from agentic_os.core.brains.health import BrainHealthMonitor, _BrainHeartbeat
from agentic_os.domain.brains import BrainRecord, BrainRuntime, BrainStatus, BrainType, BrainVendor
from agentic_os.domain.events import EventEnvelope, Topic

# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def sample_brain() -> BrainRecord:
    return BrainRecord(
        id="brain-1",
        display_name="Test Brain",
        brain_type=BrainType.LOCAL_CLI,
        vendor=BrainVendor.CUSTOM,
        runtime=BrainRuntime.UNKNOWN,
        version="1.0.0",
        status=BrainStatus.CONNECTED,
        health=90.0,
    )


@pytest.fixture
def get_brains_fn(sample_brain: BrainRecord) -> AsyncMock:
    return AsyncMock(return_value=[sample_brain])


@pytest.fixture
def event_bus() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def monitor() -> BrainHealthMonitor:
    return BrainHealthMonitor(interval_seconds=1.0, stale_timeout_seconds=5.0)


# ═══════════════════════════════════════════════════════════════════════════════
# Initialization
# ═══════════════════════════════════════════════════════════════════════════════


class TestBrainHealthMonitorInit:
    def test_default_values(self) -> None:
        m = BrainHealthMonitor()
        assert m._interval == 30.0
        assert m._stale_timeout == 120.0
        assert m._task is None
        assert m._event_bus is None
        assert m._started is False
        assert m._brains == {}

    def test_custom_values(self) -> None:
        m = BrainHealthMonitor(interval_seconds=10.0, stale_timeout_seconds=60.0)
        assert m._interval == 10.0
        assert m._stale_timeout == 60.0

    def test_lock_is_initialized(self, monitor: BrainHealthMonitor) -> None:
        assert monitor._lock is not None


# ═══════════════════════════════════════════════════════════════════════════════
# Lifecycle — start / stop
# ═══════════════════════════════════════════════════════════════════════════════


class TestBrainHealthMonitorStart:
    async def test_start_sets_fields_and_seeds_brains(
        self, monitor: BrainHealthMonitor, get_brains_fn: AsyncMock, event_bus: AsyncMock
    ) -> None:
        await monitor.start(get_brains=get_brains_fn, update_brain=None, event_bus=event_bus)
        assert monitor._started is True
        assert monitor._get_brains_fn is get_brains_fn
        assert monitor._event_bus is event_bus
        assert monitor._task is not None
        # Brain should be seeded
        async with monitor._lock:
            assert "brain-1" in monitor._brains
        # Cleanup
        await monitor.stop()

    async def test_start_handles_get_brains_error(
        self, monitor: BrainHealthMonitor, event_bus: AsyncMock
    ) -> None:
        failing_fn = AsyncMock(side_effect=RuntimeError("fail"))
        await monitor.start(get_brains=failing_fn, event_bus=event_bus)
        assert monitor._started is True
        assert monitor._task is not None
        await monitor.stop()

    async def test_start_without_event_bus(
        self, monitor: BrainHealthMonitor, get_brains_fn: AsyncMock
    ) -> None:
        await monitor.start(get_brains=get_brains_fn)
        assert monitor._event_bus is None
        await monitor.stop()


class TestBrainHealthMonitorStop:
    async def test_stop_cancels_task_and_clears_brains(
        self, monitor: BrainHealthMonitor, get_brains_fn: AsyncMock, event_bus: AsyncMock
    ) -> None:
        await monitor.start(get_brains=get_brains_fn, event_bus=event_bus)
        await monitor.stop()
        assert monitor._started is False
        assert monitor._task is None
        async with monitor._lock:
            assert monitor._brains == {}

    async def test_stop_when_not_started_is_safe(self, monitor: BrainHealthMonitor) -> None:
        await monitor.stop()  # should not raise

    async def test_stop_twice_is_safe(
        self, monitor: BrainHealthMonitor, get_brains_fn: AsyncMock, event_bus: AsyncMock
    ) -> None:
        await monitor.start(get_brains=get_brains_fn, event_bus=event_bus)
        await monitor.stop()
        await monitor.stop()  # second stop should be safe


# ═══════════════════════════════════════════════════════════════════════════════
# Heartbeat recording
# ═══════════════════════════════════════════════════════════════════════════════


class TestBrainHealthMonitorHeartbeat:
    async def test_record_heartbeat_adds_new_brain(self, monitor: BrainHealthMonitor) -> None:
        await monitor.record_heartbeat("brain-new")
        ts = await monitor.last_heartbeat("brain-new")
        assert ts is not None
        assert ts > 0

    async def test_record_heartbeat_updates_existing(self, monitor: BrainHealthMonitor) -> None:
        await monitor.record_heartbeat("brain-1")
        ts1 = await monitor.last_heartbeat("brain-1")
        time.sleep(0.01)
        await monitor.record_heartbeat("brain-1")
        ts2 = await monitor.last_heartbeat("brain-1")
        assert ts2 > ts1

    async def test_remove_brain_removes_tracking(self, monitor: BrainHealthMonitor) -> None:
        await monitor.record_heartbeat("brain-1")
        await monitor.remove_brain("brain-1")
        ts = await monitor.last_heartbeat("brain-1")
        assert ts is None

    async def test_remove_brain_unknown_id_is_safe(self, monitor: BrainHealthMonitor) -> None:
        await monitor.remove_brain("nonexistent")  # should not raise


# ═══════════════════════════════════════════════════════════════════════════════
# Status queries
# ═══════════════════════════════════════════════════════════════════════════════


class TestBrainHealthMonitorStatus:
    async def test_last_heartbeat_returns_timestamp(self, monitor: BrainHealthMonitor) -> None:
        await monitor.record_heartbeat("brain-1")
        ts = await monitor.last_heartbeat("brain-1")
        assert isinstance(ts, float)
        assert ts > 0

    async def test_last_heartbeat_none_for_unknown(self, monitor: BrainHealthMonitor) -> None:
        ts = await monitor.last_heartbeat("unknown")
        assert ts is None

    async def test_is_stale_returns_true_for_unknown(self, monitor: BrainHealthMonitor) -> None:
        stale = await monitor.is_stale("unknown")
        assert stale is True

    async def test_is_stale_returns_true_for_stale_brain(self, monitor: BrainHealthMonitor) -> None:
        # Stale timeout is 5s, so a freshly-recorded brain should not be stale
        monitor._stale_timeout = -1.0  # force stale
        await monitor.record_heartbeat("brain-1")
        stale = await monitor.is_stale("brain-1")
        assert stale is True

    async def test_is_stale_false_for_fresh_brain(self, monitor: BrainHealthMonitor) -> None:
        await monitor.record_heartbeat("brain-1")
        stale = await monitor.is_stale("brain-1")
        assert stale is False

    async def test_tracking_summary_returns_dict(self, monitor: BrainHealthMonitor) -> None:
        await monitor.record_heartbeat("brain-1")
        summary = await monitor.tracking_summary()
        assert isinstance(summary, dict)
        assert "brain-1" in summary
        assert "last_heartbeat" in summary["brain-1"]
        assert "age_seconds" in summary["brain-1"]
        assert "stale" in summary["brain-1"]


# ═══════════════════════════════════════════════════════════════════════════════
# Internal: _check_all / _mark_unhealthy / _publish
# ═══════════════════════════════════════════════════════════════════════════════


class TestBrainHealthMonitorCheckAll:
    async def test_check_all_marks_stale_brain_unhealthy(
        self, monitor: BrainHealthMonitor, event_bus: AsyncMock
    ) -> None:
        brain = BrainRecord(
            id="brain-stale",
            display_name="Stale Brain",
            brain_type=BrainType.LOCAL_CLI,
            vendor=BrainVendor.CUSTOM,
            runtime=BrainRuntime.UNKNOWN,
            version="1.0",
            status=BrainStatus.CONNECTED,
            health=50.0,
        )
        get_brains_fn = AsyncMock(return_value=[brain])
        await monitor.start(get_brains=get_brains_fn, update_brain=None, event_bus=event_bus)

        # Manually set an old heartbeat
        old_ts = time.time() - 100.0
        async with monitor._lock:
            monitor._brains["brain-stale"] = _BrainHeartbeat(
                brain_id="brain-stale", last_heartbeat=old_ts
            )

        # Run check
        await monitor._check_all()

        # Should have published BRAIN_HEALTH_CHANGED
        assert event_bus.publish.called
        call_args = event_bus.publish.call_args
        envelope = call_args[0][0]
        assert envelope.topic == Topic.BRAIN_HEALTH_CHANGED.value
        assert envelope.payload["status"] == "unhealthy"
        await monitor.stop()

    async def test_check_all_adds_new_brains_without_heartbeat(
        self, monitor: BrainHealthMonitor, event_bus: AsyncMock
    ) -> None:
        brain = BrainRecord(
            id="brain-new",
            display_name="New Brain",
            brain_type=BrainType.LOCAL_CLI,
            vendor=BrainVendor.CUSTOM,
            runtime=BrainRuntime.UNKNOWN,
            version="1.0",
            status=BrainStatus.CONNECTED,
            health=100.0,
        )
        get_brains_fn = AsyncMock(return_value=[brain])
        await monitor.start(get_brains=get_brains_fn, event_bus=event_bus)

        # Remove the seeded heartbeat
        async with monitor._lock:
            monitor._brains.clear()

        await monitor._check_all()

        # Should have added the brain
        async with monitor._lock:
            assert "brain-new" in monitor._brains
        await monitor.stop()

    async def test_check_all_handles_get_brains_error(
        self, monitor: BrainHealthMonitor, event_bus: AsyncMock
    ) -> None:
        failing_fn = AsyncMock(side_effect=RuntimeError("fetch fail"))
        await monitor.start(get_brains=failing_fn, event_bus=event_bus)

        # This should log a warning but not raise
        await monitor._check_all()  # should not raise
        await monitor.stop()

    async def test_check_all_does_not_mark_already_unhealthy(
        self, monitor: BrainHealthMonitor, event_bus: AsyncMock
    ) -> None:
        brain = BrainRecord(
            id="brain-unhealthy",
            display_name="Unhealthy Brain",
            brain_type=BrainType.LOCAL_CLI,
            vendor=BrainVendor.CUSTOM,
            runtime=BrainRuntime.UNKNOWN,
            version="1.0",
            status=BrainStatus.UNHEALTHY,
            health=10.0,
        )
        get_brains_fn = AsyncMock(return_value=[brain])
        await monitor.start(get_brains=get_brains_fn, event_bus=event_bus)

        old_ts = time.time() - 100.0
        async with monitor._lock:
            monitor._brains["brain-unhealthy"] = _BrainHeartbeat(
                brain_id="brain-unhealthy", last_heartbeat=old_ts
            )

        # Reset publish mock
        event_bus.publish.reset_mock()
        await monitor._check_all()

        # Should NOT publish because already UNHEALTHY
        assert not event_bus.publish.called
        await monitor.stop()


class TestBrainHealthMonitorMarkUnhealthy:
    async def test_mark_unhealthy_publishes_event(
        self, monitor: BrainHealthMonitor, sample_brain: BrainRecord, event_bus: AsyncMock
    ) -> None:
        monitor._event_bus = event_bus
        await monitor._mark_unhealthy(sample_brain)

        assert event_bus.publish.called
        envelope = event_bus.publish.call_args[0][0]
        assert envelope.topic == Topic.BRAIN_HEALTH_CHANGED.value
        assert envelope.payload["status"] == "unhealthy"
        assert envelope.payload["health"] == 70.0  # 90 - 20

    async def test_mark_unhealthy_calls_update_fn(
        self, monitor: BrainHealthMonitor, sample_brain: BrainRecord
    ) -> None:
        update_fn = AsyncMock()
        monitor._update_fn = update_fn
        await monitor._mark_unhealthy(sample_brain)

        update_fn.assert_called_once_with(
            sample_brain.id,
            status=BrainStatus.UNHEALTHY,
            health=70.0,
        )

    async def test_mark_unhealthy_handles_update_fn_error(
        self, monitor: BrainHealthMonitor, sample_brain: BrainRecord, event_bus: AsyncMock
    ) -> None:
        failing_update = AsyncMock(side_effect=RuntimeError("update fail"))
        monitor._update_fn = failing_update
        monitor._event_bus = event_bus

        # Should not raise, should still publish event
        await monitor._mark_unhealthy(sample_brain)

        assert event_bus.publish.called

    async def test_mark_unhealthy_no_update_fn(
        self, monitor: BrainHealthMonitor, sample_brain: BrainRecord, event_bus: AsyncMock
    ) -> None:
        monitor._event_bus = event_bus
        await monitor._mark_unhealthy(sample_brain)
        # Should have published even without update_fn
        assert event_bus.publish.called


class TestBrainHealthMonitorPublish:
    async def test_publish_sends_event_via_bus(
        self, monitor: BrainHealthMonitor, sample_brain: BrainRecord, event_bus: AsyncMock
    ) -> None:
        monitor._event_bus = event_bus
        await monitor._publish(Topic.BRAIN_HEALTH_CHANGED, sample_brain)

        event_bus.publish.assert_called_once()
        envelope = event_bus.publish.call_args[0][0]
        assert isinstance(envelope, EventEnvelope)
        assert envelope.type == Topic.BRAIN_HEALTH_CHANGED.value
        assert envelope.source == "brain_health_monitor"
        assert envelope.topic == Topic.BRAIN_HEALTH_CHANGED.value
        assert envelope.payload["id"] == "brain-1"

    async def test_publish_is_noop_when_bus_is_none(
        self, monitor: BrainHealthMonitor, sample_brain: BrainRecord
    ) -> None:
        monitor._event_bus = None
        # Should not raise
        await monitor._publish(Topic.BRAIN_HEALTH_CHANGED, sample_brain)

    async def test_publish_handles_bus_error(
        self, monitor: BrainHealthMonitor, sample_brain: BrainRecord
    ) -> None:
        failing_bus = AsyncMock()
        failing_bus.publish.side_effect = RuntimeError("bus error")
        monitor._event_bus = failing_bus
        # Should not raise
        await monitor._publish(Topic.BRAIN_HEALTH_CHANGED, sample_brain)


# ═══════════════════════════════════════════════════════════════════════════════
# Background loop
# ═══════════════════════════════════════════════════════════════════════════════


class TestBrainHealthMonitorLoop:
    async def test_loop_handles_cancelled_error(
        self, monitor: BrainHealthMonitor, get_brains_fn: AsyncMock
    ) -> None:
        # Start with fast interval, then stop (which cancels the task)
        monitor._interval = 0.01
        await monitor.start(get_brains=get_brains_fn)
        assert monitor._started is True
        assert monitor._task is not None

        await monitor.stop()
        assert monitor._started is False
        assert monitor._task is None

    async def test_loop_handles_unexpected_error(self, monitor: BrainHealthMonitor) -> None:
        failing_fn = AsyncMock(side_effect=RuntimeError("loop error"))
        monitor._interval = 0.01
        await monitor.start(get_brains=failing_fn)

        # After one interval the loop runs and catches the error
        await asyncio.sleep(0.05)

        await monitor.stop()
        assert monitor._started is False
