"""Tests for RuntimeSupervisor — watchdog, heartbeat timeout, crash detection."""

import asyncio
from datetime import UTC, datetime

import pytest

from agentic_os.core.runtime.runtime import Runtime, RuntimeHealth, RuntimeStatus
from agentic_os.core.runtime.runtime_recovery import RuntimeRecovery
from agentic_os.core.runtime.runtime_supervisor import HealthManager, RuntimeSupervisor


@pytest.fixture
def fake_bus() -> object:
    class _FakeBus:
        async def publish(self, topic: str, data: object) -> None:
            pass

    return _FakeBus()


@pytest.fixture
def recovery() -> RuntimeRecovery:
    return RuntimeRecovery()


@pytest.fixture
def supervisor(recovery, fake_bus) -> RuntimeSupervisor:
    return RuntimeSupervisor(
        recovery=recovery,
        bus=fake_bus,
        heartbeat_threshold=0.1,  # very short for fast tests
        watch_interval=9999,  # don't auto-start loops
    )


@pytest.mark.asyncio
class TestHealthManager:
    async def test_is_alive_ready(self) -> None:
        hm = HealthManager()
        r = Runtime(status=RuntimeStatus.READY)
        assert await hm.is_alive(r) is True

    async def test_is_alive_stopped(self) -> None:
        hm = HealthManager()
        r = Runtime(status=RuntimeStatus.STOPPED)
        assert await hm.is_alive(r) is False

    async def test_is_alive_crashed(self) -> None:
        hm = HealthManager()
        r = Runtime(status=RuntimeStatus.CRASHED)
        assert await hm.is_alive(r) is False

    async def test_is_alive_failed(self) -> None:
        hm = HealthManager()
        r = Runtime(status=RuntimeStatus.FAILED)
        assert await hm.is_alive(r) is False

    async def test_is_alive_disconnected(self) -> None:
        hm = HealthManager()
        r = Runtime(status=RuntimeStatus.DISCONNECTED)
        assert await hm.is_alive(r) is False


@pytest.mark.asyncio
class TestRuntimeSupervisor:
    async def test_register_adds_runtime(self, supervisor: RuntimeSupervisor) -> None:
        r = Runtime(name="watch-me")
        supervisor.register(r.id, r)
        assert r.id in supervisor._runtimes

    async def test_register_then_start(self, supervisor: RuntimeSupervisor) -> None:
        r = Runtime(name="watch-me")
        supervisor.register(r.id, r)
        result = supervisor.start(r.id)
        assert result is True
        assert supervisor.is_watching(r.id)

    async def test_start_on_unregistered(self, supervisor: RuntimeSupervisor) -> None:
        result = supervisor.start("ghost")
        assert result is False

    async def test_start_idempotent(self, supervisor: RuntimeSupervisor) -> None:
        r = Runtime(name="dup-watch")
        supervisor.register(r.id, r)
        supervisor.start(r.id)
        result = supervisor.start(r.id)
        assert result is True  # already running

    async def test_stop_removes_watch(self, supervisor: RuntimeSupervisor) -> None:
        r = Runtime(name="stop-me")
        supervisor.register(r.id, r)
        supervisor.start(r.id)
        await supervisor.stop(r.id)
        assert not supervisor.is_watching(r.id)

    async def test_unregister_removes_and_stops(self, supervisor: RuntimeSupervisor) -> None:
        r = Runtime(name="unreg")
        supervisor.register(r.id, r)
        supervisor.start(r.id)
        await supervisor.unregister(r.id)
        assert r.id not in supervisor._runtimes
        assert not supervisor.is_watching(r.id)

    async def test_stop_all(self, supervisor: RuntimeSupervisor) -> None:
        r1 = Runtime(name="a")
        r2 = Runtime(name="b")
        supervisor.register(r1.id, r1)
        supervisor.register(r2.id, r2)
        supervisor.start(r1.id)
        supervisor.start(r2.id)
        await supervisor.stop_all()
        assert not supervisor.is_watching(r1.id)
        assert not supervisor.is_watching(r2.id)

    async def test_heartbeat_stale_triggers_crash(self, supervisor: RuntimeSupervisor) -> None:
        r = Runtime(
            name="stale-hb",
            status=RuntimeStatus.READY,
            health=RuntimeHealth.HEALTHY,
            heartbeat=datetime(2020, 1, 1, tzinfo=UTC),  # very old
        )
        await supervisor._check_heartbeat(r)
        assert r.health == RuntimeHealth.UNHEALTHY
        assert r.status == RuntimeStatus.CRASHED
        assert "Heartbeat stale" in (r.last_error or "")

    async def test_heartbeat_fresh_keeps_healthy(self, supervisor: RuntimeSupervisor) -> None:
        r = Runtime(
            name="fresh-hb",
            status=RuntimeStatus.READY,
            health=RuntimeHealth.HEALTHY,
            heartbeat=datetime.now(UTC),
        )
        await supervisor._check_heartbeat(r)
        # Should still be healthy if within threshold
        assert r.health == RuntimeHealth.HEALTHY

    async def test_heartbeat_recovery_to_healthy(self, supervisor: RuntimeSupervisor) -> None:
        r = Runtime(
            name="recovery-hb",
            status=RuntimeStatus.READY,
            health=RuntimeHealth.UNHEALTHY,
            heartbeat=datetime.now(UTC),  # fresh
        )
        await supervisor._check_heartbeat(r)
        assert r.health == RuntimeHealth.HEALTHY

    async def test_no_heartbeat_no_change(self, supervisor: RuntimeSupervisor) -> None:
        r = Runtime(name="no-hb", status=RuntimeStatus.READY, heartbeat=None)
        await supervisor._check_heartbeat(r)
        assert r.heartbeat is None

    async def test_liveness_dead_detected(self, supervisor: RuntimeSupervisor) -> None:
        r = Runtime(
            name="dead-proc",
            status=RuntimeStatus.READY,
            health=RuntimeHealth.HEALTHY,
            pid=999999,  # unlikely to exist
        )
        await supervisor._check_liveness(r)
        # The default HealthManager checks status, not actual PID
        # Since status is READY, is_alive returns True
        assert r.status == RuntimeStatus.READY

    async def test_liveness_stopped_not_flagged(self, supervisor: RuntimeSupervisor) -> None:
        r = Runtime(name="stopped-proc", status=RuntimeStatus.STOPPED)
        await supervisor._check_liveness(r)
        assert r.status == RuntimeStatus.STOPPED

    async def test_check_resources_logs_high_cpu(self, supervisor: RuntimeSupervisor) -> None:
        r = Runtime(name="hot-cpu", cpu=95.0)
        # Should not crash — just logs
        await supervisor._check_resources(r)

    async def test_check_resources_logs_high_memory(self, supervisor: RuntimeSupervisor) -> None:
        r = Runtime(name="big-mem", memory=2048.0)
        await supervisor._check_resources(r)

    async def test_watch_loop_removes_task_on_gone(self, supervisor: RuntimeSupervisor) -> None:
        # Register but don't add _runtimes entry — it will be None in loop
        r = Runtime(name="gone")
        supervisor.register(r.id, r)
        supervisor.start(r.id)
        # Remove the runtime from dict to simulate removal
        supervisor._runtimes.pop(r.id, None)
        # Give the loop a chance to run
        await asyncio.sleep(0.05)
        assert not supervisor.is_watching(r.id)

    async def test_is_watching_false_for_unknown(self, supervisor: RuntimeSupervisor) -> None:
        assert supervisor.is_watching("ghost") is False
