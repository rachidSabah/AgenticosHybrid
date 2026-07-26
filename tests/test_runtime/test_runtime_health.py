"""Tests for HealthManager — health check, heartbeat, monitoring lifecycle."""

from datetime import UTC, datetime

import pytest

from agentic_os.core.runtime.runtime import Runtime, RuntimeHealth
from agentic_os.core.runtime.runtime_health import HealthCheckResult, HealthManager


@pytest.fixture
def health_mgr() -> HealthManager:
    return HealthManager()


@pytest.mark.asyncio
class TestHealthManager:
    async def test_check_healthy(self, health_mgr: HealthManager) -> None:
        r = Runtime(
            name="healthy-rt",
            pid=999999,  # non-existent, will show as not alive
            started_at=datetime.now(UTC),
        )
        result = await health_mgr.check(r)
        assert isinstance(result, HealthCheckResult)
        assert result.runtime_id == r.id
        assert not result.pid_alive  # PID doesn't exist
        assert result.healthy is False  # no pid = unhealthy

    async def test_check_no_pid(self, health_mgr: HealthManager) -> None:
        r = Runtime(name="no-pid", pid=None)
        result = await health_mgr.check(r)
        assert not result.pid_alive
        assert "no pid set" in result.errors

    async def test_check_with_heartbeat(self, health_mgr: HealthManager) -> None:
        r = Runtime(
            name="hb-check",
            pid=None,
            heartbeat=datetime.now(UTC),
        )
        result = await health_mgr.check(r)
        assert result.heartbeat_recency is not None

    async def test_check_with_stale_heartbeat(self, health_mgr: HealthManager) -> None:
        r = Runtime(
            name="stale-hb",
            pid=None,
            heartbeat=datetime(2020, 1, 1, tzinfo=UTC),
        )
        result = await health_mgr.check(r)
        # Without pid, stale heartbeat makes it degraded/unhealthy
        assert not result.healthy

    async def test_determine_health_no_pid(self, health_mgr: HealthManager) -> None:
        health = health_mgr._determine_health(False, None, ["no pid set"])
        assert health == RuntimeHealth.UNHEALTHY

    async def test_determine_health_alive_no_errors(self, health_mgr: HealthManager) -> None:
        health = health_mgr._determine_health(True, None, [])
        assert health == RuntimeHealth.HEALTHY

    async def test_determine_health_alive_with_errors(self, health_mgr: HealthManager) -> None:
        health = health_mgr._determine_health(True, None, ["some error"])
        assert health == RuntimeHealth.DEGRADED

    async def test_determine_health_stale_heartbeat(self, health_mgr: HealthManager) -> None:
        health = health_mgr._determine_health(True, 999.0, [])
        assert health == RuntimeHealth.DEGRADED

    async def test_set_callback(self, health_mgr: HealthManager) -> None:
        calls = []

        async def cb(rid: str, old: RuntimeHealth, new: RuntimeHealth, details: dict) -> None:
            calls.append((rid, old, new))

        health_mgr.set_callback("rt-1", cb)
        assert "rt-1" in health_mgr._callbacks

        health_mgr.set_callback("rt-1", None)
        assert "rt-1" not in health_mgr._callbacks

    async def test_start_monitoring(self, health_mgr: HealthManager) -> None:
        r = Runtime(name="monitored", pid=None)

        def getter() -> Runtime:
            return r

        result = await health_mgr.start_monitoring("rt-1", getter, interval=9999)
        assert result is True
        assert await health_mgr.is_monitoring("rt-1") is True

    async def test_start_monitoring_idempotent(self, health_mgr: HealthManager) -> None:
        r = Runtime(name="dup-mon")

        def getter() -> Runtime:
            return r

        await health_mgr.start_monitoring("rt-1", getter, interval=9999)
        result = await health_mgr.start_monitoring("rt-1", getter, interval=9999)
        assert result is True

    async def test_stop_monitoring(self, health_mgr: HealthManager) -> None:
        r = Runtime(name="stop-mon")

        def getter() -> Runtime:
            return r

        await health_mgr.start_monitoring("rt-1", getter, interval=9999)
        result = await health_mgr.stop_monitoring("rt-1")
        assert result is True
        assert await health_mgr.is_monitoring("rt-1") is False

    async def test_stop_monitoring_not_running(self, health_mgr: HealthManager) -> None:
        result = await health_mgr.stop_monitoring("ghost")
        assert result is False

    async def test_list_monitored(self, health_mgr: HealthManager) -> None:
        r = Runtime(name="list-mon")

        def getter() -> Runtime:
            return r

        await health_mgr.start_monitoring("rt-1", getter, interval=9999)
        monitored = await health_mgr.list_monitored()
        assert "rt-1" in monitored

    async def test_stop_all(self, health_mgr: HealthManager) -> None:
        r1 = Runtime(name="a")
        r2 = Runtime(name="b")

        def make_getter(rt: Runtime):
            return lambda: rt

        await health_mgr.start_monitoring("rt-a", make_getter(r1), interval=9999)
        await health_mgr.start_monitoring("rt-b", make_getter(r2), interval=9999)
        count = await health_mgr.stop_all()
        assert count == 2

    async def test_get_last_health(self, health_mgr: HealthManager) -> None:
        assert await health_mgr.get_last_health("ghost") is None

    async def test_health_check_result_properties(self) -> None:
        result = HealthCheckResult(
            runtime_id="rt-1",
            runtime_name="test",
            health=RuntimeHealth.HEALTHY,
            pid_alive=True,
            uptime_seconds=100.0,
        )
        assert result.healthy is True
        d = result.to_dict()
        assert d["runtime_id"] == "rt-1"
        assert d["health"] == "healthy"

    async def test_health_check_result_to_metrics(self) -> None:
        result = HealthCheckResult(
            runtime_id="rt-1",
            runtime_name="test",
            health=RuntimeHealth.HEALTHY,
            pid_alive=True,
            uptime_seconds=50.0,
            cpu_percent=30.0,
            memory_mb=128.0,
        )
        metrics = result.to_metrics()
        assert metrics.cpu_percent == 30.0
        assert metrics.memory_mb == 128.0
        assert metrics.uptime_seconds == 50.0
