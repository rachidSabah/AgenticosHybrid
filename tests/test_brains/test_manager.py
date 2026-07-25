"""Tests for BrainManager — lifecycle controls for registered brains.

Covers pause, resume, restart, shutdown, recover, callback wiring, event
publishing, and error cases.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

from agentic_os.core.brains.manager import BrainManager
from agentic_os.domain.brains import (
    BrainRecord,
    BrainRuntime,
    BrainStatus,
    BrainType,
    BrainVendor,
)
from agentic_os.domain.events import Topic

# ═══════════════════════════════════════════════════════════════════════
# Construction
# ═══════════════════════════════════════════════════════════════════════


class TestBrainManagerConstruction:
    """Default callbacks and wiring."""

    async def test_default_callbacks(self) -> None:
        manager = BrainManager()
        assert manager._get is not None
        assert manager._update is not None
        result = await manager._get("any")
        assert result is None
        result2 = await manager._update("any")
        assert result2 is None

    async def test_with_custom_callbacks(self) -> None:
        async def get_brain(bid: str) -> BrainRecord | None:
            return None

        async def update_brain(bid: str, **kwargs) -> BrainRecord | None:
            return None

        manager = BrainManager(get_brain=get_brain, update_brain=update_brain)
        assert manager._get is get_brain
        assert manager._update is update_brain

    async def test_with_event_bus(self, mock_event_bus: AsyncMock) -> None:
        manager = BrainManager(event_bus=mock_event_bus)
        assert manager._event_bus is mock_event_bus


# ═══════════════════════════════════════════════════════════════════════
# Pause
# ═══════════════════════════════════════════════════════════════════════


class TestBrainManagerPause:
    """pause() — transition to PAUSED from active states."""

    async def test_pause_connected_brain(self, mock_event_bus: AsyncMock) -> None:
        record = BrainRecord(
            id="b1",
            display_name="B1",
            brain_type=BrainType.CUSTOM,
            vendor=BrainVendor.CUSTOM,
            runtime=BrainRuntime.UNKNOWN,
            version="1",
            status=BrainStatus.CONNECTED,
        )

        async def get_brain(bid: str) -> BrainRecord | None:
            return record if bid == "b1" else None

        async def update_brain(bid: str, **kwargs) -> BrainRecord | None:
            return record

        manager = BrainManager(
            get_brain=get_brain,
            update_brain=update_brain,
            event_bus=mock_event_bus,
        )
        result = await manager.pause("b1")
        assert result is not None

    async def test_pause_idle_brain(self) -> None:
        record = BrainRecord(
            id="b1",
            display_name="B1",
            brain_type=BrainType.CUSTOM,
            vendor=BrainVendor.CUSTOM,
            runtime=BrainRuntime.UNKNOWN,
            version="1",
            status=BrainStatus.IDLE,
        )

        async def get_brain(bid: str) -> BrainRecord | None:
            return record if bid == "b1" else None

        async def update_brain(bid: str, **kwargs) -> BrainRecord | None:
            return record

        manager = BrainManager(get_brain=get_brain, update_brain=update_brain)
        result = await manager.pause("b1")
        assert result is not None

    async def test_pause_not_found(self) -> None:
        async def get_brain(bid: str) -> BrainRecord | None:
            return None

        manager = BrainManager(get_brain=get_brain)
        result = await manager.pause("unknown")
        assert result is None

    async def test_pause_wrong_status(self) -> None:
        record = BrainRecord(
            id="b1",
            display_name="B1",
            brain_type=BrainType.CUSTOM,
            vendor=BrainVendor.CUSTOM,
            runtime=BrainRuntime.UNKNOWN,
            version="1",
            status=BrainStatus.FAILED,
        )

        async def get_brain(bid: str) -> BrainRecord | None:
            return record if bid == "b1" else None

        manager = BrainManager(get_brain=get_brain)
        result = await manager.pause("b1")
        assert result is None

    async def test_pause_publishes_disconnected_event(
        self,
        mock_event_bus: AsyncMock,
    ) -> None:
        record = BrainRecord(
            id="b1",
            display_name="B1",
            brain_type=BrainType.CUSTOM,
            vendor=BrainVendor.CUSTOM,
            runtime=BrainRuntime.UNKNOWN,
            version="1",
            status=BrainStatus.IDLE,
        )

        async def get_brain(bid: str) -> BrainRecord | None:
            return record if bid == "b1" else None

        async def update_brain(bid: str, **kwargs) -> BrainRecord | None:
            return record

        manager = BrainManager(
            get_brain=get_brain,
            update_brain=update_brain,
            event_bus=mock_event_bus,
        )
        await manager.pause("b1")
        mock_event_bus.publish.assert_called_once()
        assert mock_event_bus.publish.call_args[0][0].topic == Topic.BRAIN_DISCONNECTED.value


# ═══════════════════════════════════════════════════════════════════════
# Resume
# ═══════════════════════════════════════════════════════════════════════


class TestBrainManagerResume:
    """resume() — transition from PAUSED to IDLE."""

    async def test_resume_paused_brain(self) -> None:
        record = BrainRecord(
            id="b1",
            display_name="B1",
            brain_type=BrainType.CUSTOM,
            vendor=BrainVendor.CUSTOM,
            runtime=BrainRuntime.UNKNOWN,
            version="1",
            status=BrainStatus.PAUSED,
        )

        async def get_brain(bid: str) -> BrainRecord | None:
            return record if bid == "b1" else None

        async def update_brain(bid: str, **kwargs) -> BrainRecord | None:
            return record

        manager = BrainManager(get_brain=get_brain, update_brain=update_brain)
        result = await manager.resume("b1")
        assert result is not None

    async def test_resume_not_found(self) -> None:
        async def get_brain(bid: str) -> BrainRecord | None:
            return None

        manager = BrainManager(get_brain=get_brain)
        result = await manager.resume("unknown")
        assert result is None

    async def test_resume_not_paused(self) -> None:
        record = BrainRecord(
            id="b1",
            display_name="B1",
            brain_type=BrainType.CUSTOM,
            vendor=BrainVendor.CUSTOM,
            runtime=BrainRuntime.UNKNOWN,
            version="1",
            status=BrainStatus.CONNECTED,
        )

        async def get_brain(bid: str) -> BrainRecord | None:
            return record if bid == "b1" else None

        manager = BrainManager(get_brain=get_brain)
        result = await manager.resume("b1")
        assert result is None

    async def test_resume_publishes_connected_event(
        self,
        mock_event_bus: AsyncMock,
    ) -> None:
        record = BrainRecord(
            id="b1",
            display_name="B1",
            brain_type=BrainType.CUSTOM,
            vendor=BrainVendor.CUSTOM,
            runtime=BrainRuntime.UNKNOWN,
            version="1",
            status=BrainStatus.PAUSED,
        )

        async def get_brain(bid: str) -> BrainRecord | None:
            return record if bid == "b1" else None

        async def update_brain(bid: str, **kwargs) -> BrainRecord | None:
            return record

        manager = BrainManager(
            get_brain=get_brain,
            update_brain=update_brain,
            event_bus=mock_event_bus,
        )
        await manager.resume("b1")
        mock_event_bus.publish.assert_called_once()
        assert mock_event_bus.publish.call_args[0][0].topic == Topic.BRAIN_CONNECTED.value

    async def test_resume_no_publish_if_update_fails(
        self,
        mock_event_bus: AsyncMock,
    ) -> None:
        record = BrainRecord(
            id="b1",
            display_name="B1",
            brain_type=BrainType.CUSTOM,
            vendor=BrainVendor.CUSTOM,
            runtime=BrainRuntime.UNKNOWN,
            version="1",
            status=BrainStatus.PAUSED,
        )

        async def get_brain(bid: str) -> BrainRecord | None:
            return record if bid == "b1" else None

        async def update_brain(bid: str, **kwargs) -> BrainRecord | None:
            return None  # update returns None — simulates failure

        manager = BrainManager(
            get_brain=get_brain,
            update_brain=update_brain,
            event_bus=mock_event_bus,
        )
        result = await manager.resume("b1")
        assert result is None
        mock_event_bus.publish.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════
# Restart
# ═══════════════════════════════════════════════════════════════════════


class TestBrainManagerRestart:
    """restart() — transition via RESTARTING → IDLE."""

    async def test_restart_brain(self) -> None:
        record = BrainRecord(
            id="b1",
            display_name="B1",
            brain_type=BrainType.CUSTOM,
            vendor=BrainVendor.CUSTOM,
            runtime=BrainRuntime.UNKNOWN,
            version="1",
            status=BrainStatus.IDLE,
        )

        async def get_brain(bid: str) -> BrainRecord | None:
            return record if bid == "b1" else None

        async def update_brain(bid: str, **kwargs) -> BrainRecord | None:
            return record

        manager = BrainManager(get_brain=get_brain, update_brain=update_brain)
        result = await manager.restart("b1")
        assert result is not None

    async def test_restart_not_found(self) -> None:
        async def get_brain(bid: str) -> BrainRecord | None:
            return None

        manager = BrainManager(get_brain=get_brain)
        result = await manager.restart("unknown")
        assert result is None

    async def test_restart_publishes_two_events(
        self,
        mock_event_bus: AsyncMock,
    ) -> None:
        record = BrainRecord(
            id="b1",
            display_name="B1",
            brain_type=BrainType.CUSTOM,
            vendor=BrainVendor.CUSTOM,
            runtime=BrainRuntime.UNKNOWN,
            version="1",
            status=BrainStatus.IDLE,
        )

        async def get_brain(bid: str) -> BrainRecord | None:
            return record if bid == "b1" else None

        async def update_brain(bid: str, **kwargs) -> BrainRecord | None:
            return record

        manager = BrainManager(
            get_brain=get_brain,
            update_brain=update_brain,
            event_bus=mock_event_bus,
        )
        await manager.restart("b1")
        assert mock_event_bus.publish.call_count == 2
        topics = [call[0][0].topic for call in mock_event_bus.publish.call_args_list]
        assert Topic.BRAIN_UPDATED.value in topics
        assert Topic.BRAIN_CONNECTED.value in topics


# ═══════════════════════════════════════════════════════════════════════
# Shutdown
# ═══════════════════════════════════════════════════════════════════════


class TestBrainManagerShutdown:
    """shutdown() — transition to SHUTDOWN."""

    async def test_shutdown_brain(self) -> None:
        record = BrainRecord(
            id="b1",
            display_name="B1",
            brain_type=BrainType.CUSTOM,
            vendor=BrainVendor.CUSTOM,
            runtime=BrainRuntime.UNKNOWN,
            version="1",
            status=BrainStatus.CONNECTED,
        )

        async def get_brain(bid: str) -> BrainRecord | None:
            return record if bid == "b1" else None

        async def update_brain(bid: str, **kwargs) -> BrainRecord | None:
            return record

        manager = BrainManager(get_brain=get_brain, update_brain=update_brain)
        result = await manager.shutdown("b1")
        assert result is not None

    async def test_shutdown_not_found(self) -> None:
        async def get_brain(bid: str) -> BrainRecord | None:
            return None

        manager = BrainManager(get_brain=get_brain)
        result = await manager.shutdown("unknown")
        assert result is None

    async def test_shutdown_publishes_disconnected_event(
        self,
        mock_event_bus: AsyncMock,
    ) -> None:
        record = BrainRecord(
            id="b1",
            display_name="B1",
            brain_type=BrainType.CUSTOM,
            vendor=BrainVendor.CUSTOM,
            runtime=BrainRuntime.UNKNOWN,
            version="1",
            status=BrainStatus.CONNECTED,
        )

        async def get_brain(bid: str) -> BrainRecord | None:
            return record if bid == "b1" else None

        async def update_brain(bid: str, **kwargs) -> BrainRecord | None:
            return record

        manager = BrainManager(
            get_brain=get_brain,
            update_brain=update_brain,
            event_bus=mock_event_bus,
        )
        await manager.shutdown("b1")
        mock_event_bus.publish.assert_called_once()
        assert mock_event_bus.publish.call_args[0][0].topic == Topic.BRAIN_DISCONNECTED.value


# ═══════════════════════════════════════════════════════════════════════
# Recover
# ═══════════════════════════════════════════════════════════════════════


class TestBrainManagerRecover:
    """recover() — transition from FAILED/UNHEALTHY/DEGRADED/DISCONNECTED to IDLE."""

    async def test_recover_failed_brain(self, sample_record_failed: BrainRecord) -> None:
        async def get_brain(bid: str) -> BrainRecord | None:
            return sample_record_failed if bid == sample_record_failed.id else None

        async def update_brain(bid: str, **kwargs) -> BrainRecord | None:
            return sample_record_failed

        manager = BrainManager(get_brain=get_brain, update_brain=update_brain)
        result = await manager.recover(sample_record_failed.id)
        assert result is not None

    async def test_recover_unhealthy_brain(self, sample_record_unhealthy: BrainRecord) -> None:
        async def get_brain(bid: str) -> BrainRecord | None:
            return sample_record_unhealthy if bid == sample_record_unhealthy.id else None

        async def update_brain(bid: str, **kwargs) -> BrainRecord | None:
            return sample_record_unhealthy

        manager = BrainManager(get_brain=get_brain, update_brain=update_brain)
        result = await manager.recover(sample_record_unhealthy.id)
        assert result is not None

    async def test_recover_disconnected_brain(
        self, sample_record_disconnected: BrainRecord
    ) -> None:
        async def get_brain(bid: str) -> BrainRecord | None:
            return sample_record_disconnected if bid == sample_record_disconnected.id else None

        async def update_brain(bid: str, **kwargs) -> BrainRecord | None:
            return sample_record_disconnected

        manager = BrainManager(get_brain=get_brain, update_brain=update_brain)
        result = await manager.recover(sample_record_disconnected.id)
        assert result is not None

    async def test_recover_not_found(self) -> None:
        async def get_brain(bid: str) -> BrainRecord | None:
            return None

        manager = BrainManager(get_brain=get_brain)
        result = await manager.recover("unknown")
        assert result is None

    async def test_recover_not_recoverable(self) -> None:
        record = BrainRecord(
            id="b1",
            display_name="B1",
            brain_type=BrainType.CUSTOM,
            vendor=BrainVendor.CUSTOM,
            runtime=BrainRuntime.UNKNOWN,
            version="1",
            status=BrainStatus.CONNECTED,
        )

        async def get_brain(bid: str) -> BrainRecord | None:
            return record if bid == "b1" else None

        manager = BrainManager(get_brain=get_brain)
        result = await manager.recover("b1")
        assert result is None

    async def test_recover_publishes_two_events(
        self, mock_event_bus: AsyncMock, sample_record_failed: BrainRecord
    ) -> None:
        async def get_brain(bid: str) -> BrainRecord | None:
            return sample_record_failed if bid == sample_record_failed.id else None

        async def update_brain(bid: str, **kwargs) -> BrainRecord | None:
            return sample_record_failed

        manager = BrainManager(
            get_brain=get_brain,
            update_brain=update_brain,
            event_bus=mock_event_bus,
        )
        await manager.recover(sample_record_failed.id)
        assert mock_event_bus.publish.call_count == 2
        topics = [call[0][0].topic for call in mock_event_bus.publish.call_args_list]
        assert Topic.AGENT_RECOVERED.value in topics
        assert Topic.BRAIN_CONNECTED.value in topics


# ═══════════════════════════════════════════════════════════════════════
# Event bus edge cases
# ═══════════════════════════════════════════════════════════════════════


class TestBrainManagerEventBusEdgeCases:
    """Event bus is None or throws."""

    async def test_no_event_bus_does_not_raise(self) -> None:
        record = BrainRecord(
            id="b1",
            display_name="B1",
            brain_type=BrainType.CUSTOM,
            vendor=BrainVendor.CUSTOM,
            runtime=BrainRuntime.UNKNOWN,
            version="1",
            status=BrainStatus.IDLE,
        )

        async def get_brain(bid: str) -> BrainRecord | None:
            return record if bid == "b1" else None

        async def update_brain(bid: str, **kwargs) -> BrainRecord | None:
            return record

        manager = BrainManager(get_brain=get_brain, update_brain=update_brain)
        result = await manager.pause("b1")
        assert result is not None

    async def test_event_bus_exception_caught(
        self,
        mock_event_bus: AsyncMock,
    ) -> None:
        """Publish failures are logged, not propagated."""
        mock_event_bus.publish.side_effect = RuntimeError("bus error")
        record = BrainRecord(
            id="b1",
            display_name="B1",
            brain_type=BrainType.CUSTOM,
            vendor=BrainVendor.CUSTOM,
            runtime=BrainRuntime.UNKNOWN,
            version="1",
            status=BrainStatus.IDLE,
        )

        async def get_brain(bid: str) -> BrainRecord | None:
            return record if bid == "b1" else None

        async def update_brain(bid: str, **kwargs) -> BrainRecord | None:
            return record

        manager = BrainManager(
            get_brain=get_brain,
            update_brain=update_brain,
            event_bus=mock_event_bus,
        )
        result = await manager.pause("b1")  # should not raise
        assert result is not None


# ═══════════════════════════════════════════════════════════════════════
# Can pause helper
# ═══════════════════════════════════════════════════════════════════════


class TestBrainManagerCanPause:
    """_can_pause static helper."""

    def test_can_pause_connected(self) -> None:
        record = BrainRecord(
            id="b",
            display_name="b",
            brain_type=BrainType.CUSTOM,
            vendor=BrainVendor.CUSTOM,
            runtime=BrainRuntime.UNKNOWN,
            version="1",
            status=BrainStatus.CONNECTED,
        )
        assert BrainManager._can_pause(record) is True

    def test_can_pause_idle(self) -> None:
        record = BrainRecord(
            id="b",
            display_name="b",
            brain_type=BrainType.CUSTOM,
            vendor=BrainVendor.CUSTOM,
            runtime=BrainRuntime.UNKNOWN,
            version="1",
            status=BrainStatus.IDLE,
        )
        assert BrainManager._can_pause(record) is True

    def test_can_pause_false_for_failed(self) -> None:
        record = BrainRecord(
            id="b",
            display_name="b",
            brain_type=BrainType.CUSTOM,
            vendor=BrainVendor.CUSTOM,
            runtime=BrainRuntime.UNKNOWN,
            version="1",
            status=BrainStatus.FAILED,
        )
        assert BrainManager._can_pause(record) is False

    def test_can_pause_false_for_paused(self) -> None:
        record = BrainRecord(
            id="b",
            display_name="b",
            brain_type=BrainType.CUSTOM,
            vendor=BrainVendor.CUSTOM,
            runtime=BrainRuntime.UNKNOWN,
            version="1",
            status=BrainStatus.PAUSED,
        )
        assert BrainManager._can_pause(record) is False
