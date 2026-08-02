"""Tests for BrainLifecycleManager — state machine for BrainStatus transitions.

Covers valid/invalid transitions, history tracking, clear, last transition,
and rules introspection.
"""

from __future__ import annotations

import pytest

from agentic_os.core.brains.lifecycle import BrainLifecycleManager, StatusTransition
from agentic_os.domain.brains import BrainRecord, BrainRuntime, BrainStatus, BrainType, BrainVendor


@pytest.fixture
def lifecycle() -> BrainLifecycleManager:
    return BrainLifecycleManager()


@pytest.fixture
def sample_record() -> BrainRecord:
    return BrainRecord(
        id="test-1",
        display_name="Test Brain",
        brain_type=BrainType.LOCAL_CLI,
        vendor=BrainVendor.CUSTOM,
        runtime=BrainRuntime.UNKNOWN,
        version="1.0.0",
        status=BrainStatus.DISCOVERED,
    )


@pytest.fixture
def record_connected() -> BrainRecord:
    return BrainRecord(
        id="conn-1",
        display_name="Connected",
        brain_type=BrainType.CUSTOM,
        vendor=BrainVendor.CUSTOM,
        runtime=BrainRuntime.UNKNOWN,
        version="1",
        status=BrainStatus.CONNECTED,
    )


@pytest.fixture
def record_removed() -> BrainRecord:
    return BrainRecord(
        id="rm-1",
        display_name="Removed",
        brain_type=BrainType.CUSTOM,
        vendor=BrainVendor.CUSTOM,
        runtime=BrainRuntime.UNKNOWN,
        version="1",
        status=BrainStatus.REMOVED,
    )


# ═══════════════════════════════════════════════════════════════════════
# Valid transitions
# ═══════════════════════════════════════════════════════════════════════


class TestBrainLifecycleManagerValidTransitions:
    """Transition returns a new record with updated status."""

    async def test_discovered_to_registered(
        self,
        lifecycle: BrainLifecycleManager,
        sample_record: BrainRecord,
    ) -> None:
        result = await lifecycle.transition(sample_record, BrainStatus.REGISTERED)
        assert result is not None
        assert result.status == BrainStatus.REGISTERED
        assert result.id == sample_record.id

    async def test_connected_to_idle(
        self,
        lifecycle: BrainLifecycleManager,
        record_connected: BrainRecord,
    ) -> None:
        result = await lifecycle.transition(record_connected, BrainStatus.IDLE)
        assert result is not None
        assert result.status == BrainStatus.IDLE

    async def test_connected_to_busy(
        self,
        lifecycle: BrainLifecycleManager,
        record_connected: BrainRecord,
    ) -> None:
        result = await lifecycle.transition(record_connected, BrainStatus.BUSY)
        assert result is not None
        assert result.status == BrainStatus.BUSY

    async def test_failed_to_recovering(
        self,
        lifecycle: BrainLifecycleManager,
        sample_record: BrainRecord,
    ) -> None:
        failed = await lifecycle.transition(sample_record, BrainStatus.FAILED)
        assert failed is not None
        result = await lifecycle.transition(failed, BrainStatus.RECOVERING)
        assert result is not None
        assert result.status == BrainStatus.RECOVERING

    async def test_paused_to_idle(
        self,
        lifecycle: BrainLifecycleManager,
        sample_record: BrainRecord,
    ) -> None:
        await lifecycle.transition(sample_record, BrainStatus.REGISTERED)
        paused_rec = BrainRecord(
            id=sample_record.id,
            display_name=sample_record.display_name,
            brain_type=sample_record.brain_type,
            vendor=sample_record.vendor,
            runtime=sample_record.runtime,
            version=sample_record.version,
            status=BrainStatus.PAUSED,
        )
        result = await lifecycle.transition(paused_rec, BrainStatus.IDLE)
        assert result is not None
        assert result.status == BrainStatus.IDLE

    async def test_transition_with_reason(
        self,
        lifecycle: BrainLifecycleManager,
        sample_record: BrainRecord,
    ) -> None:
        result = await lifecycle.transition(
            sample_record,
            BrainStatus.REMOVED,
            reason="Manual cleanup",
        )
        assert result is not None
        assert result.status == BrainStatus.REMOVED

    async def test_transition_returns_new_object(
        self,
        lifecycle: BrainLifecycleManager,
        sample_record: BrainRecord,
    ) -> None:
        result = await lifecycle.transition(sample_record, BrainStatus.REGISTERED)
        assert result is not sample_record  # should be a new instance
        # Original should be unchanged
        assert sample_record.status == BrainStatus.DISCOVERED

    async def test_full_chain(
        self,
        lifecycle: BrainLifecycleManager,
        sample_record: BrainRecord,
    ) -> None:
        """DISCOVERED → REGISTERED → CONNECTED → IDLE → BUSY → IDLE."""
        r = sample_record
        r = await lifecycle.transition(r, BrainStatus.REGISTERED)
        assert r is not None and r.status == BrainStatus.REGISTERED
        r = await lifecycle.transition(r, BrainStatus.CONNECTED)
        assert r is not None and r.status == BrainStatus.CONNECTED
        r = await lifecycle.transition(r, BrainStatus.IDLE)
        assert r is not None and r.status == BrainStatus.IDLE
        r = await lifecycle.transition(r, BrainStatus.BUSY)
        assert r is not None and r.status == BrainStatus.BUSY
        r = await lifecycle.transition(r, BrainStatus.IDLE)
        assert r is not None and r.status == BrainStatus.IDLE


# ═══════════════════════════════════════════════════════════════════════
# Invalid transitions
# ═══════════════════════════════════════════════════════════════════════


class TestBrainLifecycleManagerInvalidTransitions:
    """Transition returns None for disallowed transitions."""

    async def test_discovered_to_idle_invalid(
        self,
        lifecycle: BrainLifecycleManager,
        sample_record: BrainRecord,
    ) -> None:
        result = await lifecycle.transition(sample_record, BrainStatus.IDLE)
        assert result is None

    async def test_removed_is_terminal(
        self,
        lifecycle: BrainLifecycleManager,
        record_removed: BrainRecord,
    ) -> None:
        """No transition out of REMOVED."""
        result = await lifecycle.transition(record_removed, BrainStatus.CONNECTED)
        assert result is None

    async def test_idle_to_executing_invalid(
        self,
        lifecycle: BrainLifecycleManager,
        sample_record: BrainRecord,
    ) -> None:
        """IDLE -> EXECUTING is not in the transition map."""
        idle = await lifecycle.transition(sample_record, BrainStatus.REGISTERED)
        assert idle is not None
        idle2 = await lifecycle.transition(idle, BrainStatus.CONNECTED)
        assert idle2 is not None
        idle3 = await lifecycle.transition(idle2, BrainStatus.IDLE)
        assert idle3 is not None
        result = await lifecycle.transition(idle3, BrainStatus.EXECUTING)
        assert result is None

    async def test_paused_to_busy_invalid(
        self,
        lifecycle: BrainLifecycleManager,
    ) -> None:
        paused = BrainRecord(
            id="p1",
            display_name="P",
            brain_type=BrainType.CUSTOM,
            vendor=BrainVendor.CUSTOM,
            runtime=BrainRuntime.UNKNOWN,
            version="1",
            status=BrainStatus.PAUSED,
        )
        result = await lifecycle.transition(paused, BrainStatus.BUSY)
        assert result is None


# ═══════════════════════════════════════════════════════════════════════
# Same-status transition (ValueError)
# ═══════════════════════════════════════════════════════════════════════


class TestBrainLifecycleManagerSameStatus:
    """Transition to the same status raises ValueError."""

    async def test_same_status_raises_value_error(
        self,
        lifecycle: BrainLifecycleManager,
        sample_record: BrainRecord,
    ) -> None:
        with pytest.raises(ValueError, match="already in status"):
            await lifecycle.transition(sample_record, BrainStatus.DISCOVERED)

    async def test_same_status_after_transition(
        self,
        lifecycle: BrainLifecycleManager,
        sample_record: BrainRecord,
    ) -> None:
        reg = await lifecycle.transition(sample_record, BrainStatus.REGISTERED)
        assert reg is not None
        with pytest.raises(ValueError, match="already in status"):
            await lifecycle.transition(reg, BrainStatus.REGISTERED)


# ═══════════════════════════════════════════════════════════════════════
# History tracking
# ═══════════════════════════════════════════════════════════════════════


class TestBrainLifecycleManagerHistory:
    """get_history() — recording and retrieval."""

    async def test_history_empty(
        self,
        lifecycle: BrainLifecycleManager,
    ) -> None:
        history = await lifecycle.get_history()
        assert history == []

    async def test_history_records_transition(
        self,
        lifecycle: BrainLifecycleManager,
        sample_record: BrainRecord,
    ) -> None:
        await lifecycle.transition(sample_record, BrainStatus.REGISTERED)
        history = await lifecycle.get_history()
        assert len(history) == 1
        entry = history[0]
        assert isinstance(entry, StatusTransition)
        assert entry.brain_id == sample_record.id
        assert entry.from_status == BrainStatus.DISCOVERED
        assert entry.to_status == BrainStatus.REGISTERED

    async def test_history_chronological(
        self,
        lifecycle: BrainLifecycleManager,
        sample_record: BrainRecord,
    ) -> None:
        r = sample_record
        r = await lifecycle.transition(r, BrainStatus.REGISTERED)
        assert r is not None
        r = await lifecycle.transition(r, BrainStatus.CONNECTED)
        assert r is not None
        r = await lifecycle.transition(r, BrainStatus.IDLE)
        assert r is not None
        history = await lifecycle.get_history()
        assert len(history) == 3
        assert history[0].to_status == BrainStatus.REGISTERED
        assert history[1].to_status == BrainStatus.CONNECTED
        assert history[2].to_status == BrainStatus.IDLE

    async def test_history_filtered_by_brain_id(
        self,
        lifecycle: BrainLifecycleManager,
        sample_record: BrainRecord,
        record_connected: BrainRecord,
    ) -> None:
        r1 = await lifecycle.transition(sample_record, BrainStatus.REGISTERED)
        assert r1 is not None
        r2 = await lifecycle.transition(r1, BrainStatus.CONNECTED)
        assert r2 is not None
        # Create several transitions for r2 (CONNECTED) cycling between valid statuses
        r = r2
        for _ in range(5):
            r = await lifecycle.transition(r, BrainStatus.IDLE)
            assert r is not None
            r = await lifecycle.transition(r, BrainStatus.BUSY)
            assert r is not None
            r = await lifecycle.transition(r, BrainStatus.IDLE)
            assert r is not None
            r = await lifecycle.transition(r, BrainStatus.CONNECTED)
            assert r is not None
        hist = await lifecycle.get_history(brain_id=r1.id)
        assert len(hist) > 1  # at least the original 2 transitions
        for entry in hist:
            assert entry.brain_id == r1.id

    async def test_history_limit(
        self,
        lifecycle: BrainLifecycleManager,
        sample_record: BrainRecord,
    ) -> None:
        r = sample_record
        r = await lifecycle.transition(r, BrainStatus.REGISTERED)
        assert r is not None
        for _ in range(10):
            r = await lifecycle.transition(r, BrainStatus.CONNECTED)
            assert r is not None
            r = await lifecycle.transition(r, BrainStatus.IDLE)
            assert r is not None

        # Get last 3
        history = await lifecycle.get_history(limit=3)
        assert len(history) == 3

    async def test_last_transition(
        self,
        lifecycle: BrainLifecycleManager,
        sample_record: BrainRecord,
    ) -> None:
        r1 = await lifecycle.transition(sample_record, BrainStatus.REGISTERED)
        assert r1 is not None
        r2 = await lifecycle.transition(r1, BrainStatus.CONNECTED)
        assert r2 is not None
        last = await lifecycle.last_transition(sample_record.id)
        assert last is not None
        assert last.to_status == BrainStatus.CONNECTED
        assert last.from_status == BrainStatus.REGISTERED

    async def test_last_transition_none(
        self,
        lifecycle: BrainLifecycleManager,
    ) -> None:
        last = await lifecycle.last_transition("unknown")
        assert last is None


# ═══════════════════════════════════════════════════════════════════════
# Clear history
# ═══════════════════════════════════════════════════════════════════════


class TestBrainLifecycleManagerClearHistory:
    """clear_history() — remove entries."""

    async def test_clear_all(
        self,
        lifecycle: BrainLifecycleManager,
        sample_record: BrainRecord,
    ) -> None:
        r1 = await lifecycle.transition(sample_record, BrainStatus.REGISTERED)
        assert r1 is not None
        r2 = await lifecycle.transition(r1, BrainStatus.CONNECTED)
        assert r2 is not None
        count = await lifecycle.clear_history()
        assert count == 2
        assert await lifecycle.get_history() == []

    async def test_clear_by_brain_id(
        self,
        lifecycle: BrainLifecycleManager,
        sample_record: BrainRecord,
        record_connected: BrainRecord,
    ) -> None:
        r1 = await lifecycle.transition(sample_record, BrainStatus.REGISTERED)
        assert r1 is not None
        await lifecycle.transition(record_connected, BrainStatus.IDLE)
        count = await lifecycle.clear_history(brain_id=sample_record.id)
        assert count == 1
        remaining = await lifecycle.get_history()
        assert len(remaining) == 1
        assert remaining[0].brain_id == record_connected.id

    async def test_clear_empty(
        self,
        lifecycle: BrainLifecycleManager,
    ) -> None:
        count = await lifecycle.clear_history()
        assert count == 0


# ═══════════════════════════════════════════════════════════════════════
# Rules introspection
# ═══════════════════════════════════════════════════════════════════════


class TestBrainLifecycleManagerRules:
    """allowed_transitions(), is_terminal(), terminal_statuses."""

    def test_allowed_transitions_for_status(
        self,
        lifecycle: BrainLifecycleManager,
    ) -> None:
        result = lifecycle.allowed_transitions(BrainStatus.DISCOVERED)
        assert BrainStatus.DISCOVERED.value in result
        allowed = result[BrainStatus.DISCOVERED.value]
        assert "registered" in allowed
        assert "removed" in allowed
        assert "failed" in allowed

    def test_allowed_transitions_full(
        self,
        lifecycle: BrainLifecycleManager,
    ) -> None:
        result = lifecycle.allowed_transitions()
        assert BrainStatus.DISCOVERED.value in result
        assert BrainStatus.REMOVED.value in result
        assert result[BrainStatus.REMOVED.value] == []  # terminal

    def test_is_terminal_true(
        self,
        lifecycle: BrainLifecycleManager,
    ) -> None:
        assert lifecycle.is_terminal(BrainStatus.REMOVED) is True

    def test_is_terminal_false(
        self,
        lifecycle: BrainLifecycleManager,
    ) -> None:
        assert lifecycle.is_terminal(BrainStatus.CONNECTED) is False

    def test_terminal_statuses(
        self,
        lifecycle: BrainLifecycleManager,
    ) -> None:
        terminals = lifecycle.terminal_statuses
        assert "removed" in terminals
        # Only REMOVED has an empty allowed set
        assert len(terminals) == 1  # only REMOVED
