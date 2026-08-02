"""Tests for HealthMonitor (Phase 6.1)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from agentic_os.core.discovery.local.health_monitor import HealthMonitor
from agentic_os.domain.discovery import AgentHealthRecord, AgentStatus
from agentic_os.domain.events import Topic


class TestHealthMonitorLifecycle:
    @pytest.fixture
    def monitor(self) -> HealthMonitor:
        return HealthMonitor(interval_seconds=0.1)

    async def test_start_sets_running(self, monitor: HealthMonitor) -> None:
        await monitor.start()
        assert monitor.is_running is True
        await monitor.stop()

    async def test_stop_clears_running(self, monitor: HealthMonitor) -> None:
        await monitor.start()
        await monitor.stop()
        assert monitor.is_running is False

    async def test_start_twice_is_idempotent(self, monitor: HealthMonitor) -> None:
        await monitor.start()
        await monitor.start()  # second start should be no-op
        assert monitor.is_running is True
        await monitor.stop()

    async def test_stop_when_not_started_is_safe(self, monitor: HealthMonitor) -> None:
        await monitor.stop()  # should not raise
        assert monitor.is_running is False


class TestHealthMonitorTracking:
    @pytest.fixture
    def monitor(self) -> HealthMonitor:
        return HealthMonitor(interval_seconds=1.0)

    async def test_track_agent_adds_to_last_statuses(self, monitor: HealthMonitor) -> None:
        await monitor.track_agent("agent-1", pid=1001)
        async with monitor._lock:
            assert "agent-1" in monitor._last_statuses
            assert monitor._restart_counts.get("agent-1") == 0

    async def test_track_agent_idempotent(self, monitor: HealthMonitor) -> None:
        await monitor.track_agent("agent-1")
        await monitor.track_agent("agent-1")  # second should be no-op
        async with monitor._lock:
            assert monitor._last_statuses["agent-1"] == AgentStatus.UNKNOWN

    async def test_untrack_agent_removes_entry(self, monitor: HealthMonitor) -> None:
        await monitor.track_agent("agent-1")
        await monitor.untrack_agent("agent-1")
        async with monitor._lock:
            assert "agent-1" not in monitor._last_statuses

    async def test_untrack_nonexistent_agent_is_safe(self, monitor: HealthMonitor) -> None:
        await monitor.untrack_agent("nonexistent")  # should not raise


class TestHealthMonitorCheck:
    @pytest.fixture
    def monitor(self) -> HealthMonitor:
        return HealthMonitor(interval_seconds=1.0)

    async def test_health_check_alive_pid(self, monitor: HealthMonitor) -> None:
        with (
            patch.object(monitor, "_is_pid_alive", AsyncMock(return_value=True)),
            patch("asyncio.sleep"),  # prevent actual sleep
        ):
            rec = await monitor._check_agent("agent-1", 1001)
            assert rec.status == AgentStatus.RUNNING
            assert rec.health_score == 1.0
            assert rec.pid == 1001
            assert rec.error == ""

    async def test_health_check_dead_pid(self, monitor: HealthMonitor) -> None:
        with (
            patch.object(monitor, "_is_pid_alive", AsyncMock(return_value=False)),
            patch("asyncio.sleep"),
        ):
            rec = await monitor._check_agent("agent-1", 1001)
            assert rec.status == AgentStatus.CRASHED
            assert rec.health_score == 0.0
            assert "no longer running" in rec.error

    async def test_health_check_none_pid(self, monitor: HealthMonitor) -> None:
        rec = await monitor._check_agent("agent-1", None)
        assert rec.status == AgentStatus.IDLE
        assert rec.health_score == 0.5

    async def test_health_check_zero_pid(self, monitor: HealthMonitor) -> None:
        rec = await monitor._check_agent("agent-1", 0)
        assert rec.status == AgentStatus.IDLE
        assert rec.health_score == 0.5


class TestHealthMonitorEventPublishing:
    async def test_publishes_on_status_change(self) -> None:
        event_bus = AsyncMock()
        monitor = HealthMonitor(interval_seconds=1.0, event_bus=event_bus)

        with patch.object(monitor, "_is_pid_alive", AsyncMock(return_value=True)):
            rec = AgentHealthRecord(
                agent_id="agent-1",
                status=AgentStatus.RUNNING,
                health_score=1.0,
                latency_ms=0.0,
                memory_mb=0.0,
                cpu_percent=0.0,
                threads=0,
                pid=1001,
            )
            await monitor._publish_health_changed(rec, AgentStatus.UNKNOWN)
            event_bus.publish.assert_called_once()

    async def test_does_not_publish_on_same_status(self) -> None:
        event_bus = AsyncMock()
        monitor = HealthMonitor(interval_seconds=1.0, event_bus=event_bus)

        rec = AgentHealthRecord(
            agent_id="agent-1",
            status=AgentStatus.RUNNING,
            health_score=1.0,
            latency_ms=0.0,
            memory_mb=0.0,
            cpu_percent=0.0,
            threads=0,
            pid=1001,
        )
        await monitor._publish_health_changed(rec, AgentStatus.RUNNING)
        event_bus.publish.assert_called_once()

    async def test_no_event_bus_does_not_publish(self) -> None:
        monitor = HealthMonitor(interval_seconds=1.0, event_bus=None)
        rec = AgentHealthRecord(
            agent_id="agent-1",
            status=AgentStatus.RUNNING,
            health_score=1.0,
            latency_ms=0.0,
            memory_mb=0.0,
            cpu_percent=0.0,
            threads=0,
            pid=1001,
        )
        # Should not raise
        await monitor._publish_health_changed(rec, AgentStatus.UNKNOWN)

    async def test_publish_uses_correct_topic(self) -> None:
        event_bus = AsyncMock()
        monitor = HealthMonitor(interval_seconds=1.0, event_bus=event_bus)
        rec = AgentHealthRecord(
            agent_id="agent-1",
            status=AgentStatus.RUNNING,
            health_score=1.0,
            latency_ms=5.0,
            memory_mb=64.0,
            cpu_percent=2.0,
            threads=4,
            pid=1001,
        )
        await monitor._publish_health_changed(rec, AgentStatus.UNKNOWN)
        # publish() now takes a single EventEnvelope argument; the topic lives
        # on the envelope, not in kwargs.
        args, _ = event_bus.publish.call_args
        envelope = args[0]
        assert envelope.topic == Topic.AGENT_HEALTH_CHANGED.value


class TestHealthMonitorPIDCheck:
    @pytest.fixture
    def monitor_linux(self) -> HealthMonitor:
        m = HealthMonitor(interval_seconds=1.0)
        m._system = "linux"
        return m

    @pytest.fixture
    def monitor_windows(self) -> HealthMonitor:
        m = HealthMonitor(interval_seconds=1.0)
        m._system = "windows"
        return m

    async def test_is_pid_alive_windows_found(self, monitor_windows: HealthMonitor) -> None:
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            proc = AsyncMock()
            proc.communicate = AsyncMock(return_value=(b"1234", b""))
            proc.returncode = 0
            mock_exec.return_value = proc
            alive = await monitor_windows._is_pid_alive(1234)
            assert alive is True

    async def test_is_pid_alive_windows_not_found(self, monitor_windows: HealthMonitor) -> None:
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            proc = AsyncMock()
            proc.communicate = AsyncMock(return_value=(b"5678", b""))
            proc.returncode = 0
            mock_exec.return_value = proc
            alive = await monitor_windows._is_pid_alive(1234)
            assert alive is False

    async def test_is_pid_alive_linux_found(self, monitor_linux: HealthMonitor) -> None:
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            proc = AsyncMock()
            proc.wait = AsyncMock(return_value=0)
            proc.returncode = 0
            mock_exec.return_value = proc
            alive = await monitor_linux._is_pid_alive(1001)
            assert alive is True

    async def test_is_pid_alive_linux_not_found(self, monitor_linux: HealthMonitor) -> None:
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            proc = AsyncMock()
            proc.wait = AsyncMock(return_value=1)
            mock_exec.return_value = proc
            alive = await monitor_linux._is_pid_alive(99999)
            assert alive is False

    async def test_is_pid_alive_file_not_found(self, monitor_linux: HealthMonitor) -> None:
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_exec.side_effect = FileNotFoundError("kill not found")
            alive = await monitor_linux._is_pid_alive(1001)
            assert alive is False


class TestHealthMonitorRestartCounting:
    async def test_dead_pid_increments_restart_count(self) -> None:
        monitor = HealthMonitor(interval_seconds=1.0)
        await monitor.track_agent("agent-1", pid=1001)
        with (
            patch.object(monitor, "_is_pid_alive", AsyncMock(return_value=False)),
            patch("asyncio.sleep"),
        ):
            await monitor._check_agent("agent-1", 1001)
            async with monitor._lock:
                assert monitor._restart_counts.get("agent-1") == 1

    async def test_alive_pid_does_not_increment_restart(self) -> None:
        monitor = HealthMonitor(interval_seconds=1.0)
        await monitor.track_agent("agent-1", pid=1001)
        with (
            patch.object(monitor, "_is_pid_alive", AsyncMock(return_value=True)),
            patch("asyncio.sleep"),
        ):
            await monitor._check_agent("agent-1", 1001)
            async with monitor._lock:
                assert monitor._restart_counts.get("agent-1") == 0


class TestHealthMonitorCancellation:
    async def test_graceful_cancellation(self) -> None:
        monitor = HealthMonitor(interval_seconds=0.05)
        await monitor.start()
        assert monitor.is_running
        await monitor.stop()
        assert not monitor.is_running

    async def test_stop_awaits_task(self) -> None:
        monitor = HealthMonitor(interval_seconds=0.05)
        await monitor.start()
        await monitor.stop()
        # Should complete quickly without error
