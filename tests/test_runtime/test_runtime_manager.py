"""Tests for RuntimeManager — facade, lifecycle orchestration, discovery bridge."""

import pytest

from agentic_os.core.runtime.runtime import Runtime, RuntimeHealth, RuntimeStatus, RuntimeType
from agentic_os.core.runtime.runtime_manager import RuntimeManager


@pytest.fixture
def mock_bus() -> object:
    """A minimal bus that swallows events."""

    class _FakeBus:
        async def publish(self, topic: str, data: object) -> None:
            pass

    return _FakeBus()


@pytest.fixture
async def manager(mock_bus, tmp_path, monkeypatch) -> RuntimeManager:
    m = RuntimeManager(bus=mock_bus, data_dir=str(tmp_path))

    # Mock bridge to prevent auto-discovery
    async def _noop_sync() -> list:
        return []

    monkeypatch.setattr(m.bridge, "sync_discovered", _noop_sync)
    await m.start()
    return m


@pytest.mark.asyncio
class TestRuntimeManager:
    async def test_start_sets_running(self, manager: RuntimeManager) -> None:
        assert manager._running is True

    async def test_start_idempotent(self, manager: RuntimeManager) -> None:
        await manager.start()  # second start should be no-op
        assert manager._running is True

    async def test_stop_sets_not_running(self, manager: RuntimeManager) -> None:
        await manager.stop()
        assert manager._running is False

    async def test_stop_on_unstarted(self) -> None:
        m = RuntimeManager()
        await m.stop()  # should not raise
        assert m._running is False

    async def test_discover_returns_list(self, manager: RuntimeManager) -> None:
        result = await manager.discover()
        assert isinstance(result, list)

    async def test_register_and_get(self, manager: RuntimeManager) -> None:
        r = Runtime(name="test-me", type=RuntimeType.NODE)
        rid = await manager.registry.register(r)
        fetched = await manager.get(rid)
        assert fetched is not None
        assert fetched.name == "test-me"

    async def test_get_not_found(self, manager: RuntimeManager) -> None:
        assert await manager.get("unknown") is None

    async def test_list_all_empty(self, manager: RuntimeManager) -> None:
        runtimes = await manager.list_all()
        assert runtimes == []

    async def test_list_all_with_runtimes(self, manager: RuntimeManager) -> None:
        await manager.registry.register(Runtime(name="a"))
        await manager.registry.register(Runtime(name="b"))
        runtimes = await manager.list_all()
        assert len(runtimes) == 2

    async def test_list_all_filter_by_type(self, manager: RuntimeManager) -> None:
        await manager.registry.register(Runtime(name="py", type=RuntimeType.PYTHON))
        await manager.registry.register(Runtime(name="js", type=RuntimeType.NODE))
        pythons = await manager.list_all(runtime_type=RuntimeType.PYTHON)
        assert len(pythons) == 1
        assert pythons[0].name == "py"

    async def test_list_all_filter_by_status(self, manager: RuntimeManager) -> None:
        r1 = Runtime(name="ready", status=RuntimeStatus.READY)
        r2 = Runtime(name="stopped", status=RuntimeStatus.STOPPED)
        await manager.registry.register(r1)
        await manager.registry.register(r2)
        ready = await manager.list_all(status=RuntimeStatus.READY)
        assert len(ready) == 1
        assert ready[0].name == "ready"

    async def test_list_all_filter_both(self, manager: RuntimeManager) -> None:
        r = Runtime(name="filter-me", type=RuntimeType.PYTHON, status=RuntimeStatus.READY)
        await manager.registry.register(r)
        result = await manager.list_all(runtime_type=RuntimeType.PYTHON, status=RuntimeStatus.READY)
        assert len(result) == 1

    async def test_launch_nonexistent(self, manager: RuntimeManager) -> None:
        with pytest.raises(ValueError, match="not found"):
            await manager.launch("missing")

    async def test_kill_nonexistent(self, manager: RuntimeManager) -> None:
        with pytest.raises(ValueError, match="not found"):
            await manager.kill("missing")

    async def test_launch_registered(self, manager: RuntimeManager) -> None:
        r = Runtime(name="launchable", status=RuntimeStatus.REGISTERED)
        rid = await manager.registry.register(r)
        result = await manager.launch(rid)
        assert result.status in (RuntimeStatus.READY, RuntimeStatus.FAILED)

    async def test_execute_command_nonexistent(self, manager: RuntimeManager) -> None:
        with pytest.raises(ValueError, match="not found"):
            await manager.execute_command("missing", "echo hi")

    async def test_attach_terminal_nonexistent(self, manager: RuntimeManager) -> None:
        with pytest.raises(ValueError, match="not found"):
            await manager.attach_terminal("missing")

    async def test_get_logs_not_found(self, manager: RuntimeManager) -> None:
        with pytest.raises(ValueError, match="not found"):
            await manager.get_logs("missing")

    async def test_get_logs_empty(self, manager: RuntimeManager) -> None:
        r = Runtime(name="logger")
        rid = await manager.registry.register(r)
        logs = await manager.get_logs(rid)
        assert logs == []

    async def test_get_logs_with_filters(self, manager: RuntimeManager) -> None:
        from agentic_os.core.runtime.runtime import RuntimeLog

        r = Runtime(name="filter-logs")
        rid = await manager.registry.register(r)
        raw = await manager.registry.get_raw(rid)
        assert raw is not None
        raw.logs.append(RuntimeLog(stream="stdout", text="hello", level="info"))
        raw.logs.append(RuntimeLog(stream="stderr", text="error", level="error"))
        await manager.registry.update(raw)

        stdout_logs = await manager.get_logs(rid, stream="stdout")
        assert len(stdout_logs) == 1
        error_logs = await manager.get_logs(rid, level="error")
        assert len(error_logs) == 1

    async def test_get_metrics_not_found(self, manager: RuntimeManager) -> None:
        assert await manager.get_metrics("missing") is None

    async def test_get_metrics_returns_metrics(self, manager: RuntimeManager) -> None:
        from agentic_os.core.runtime.runtime import RuntimeMetrics

        r = Runtime(name="metric-man", metrics=RuntimeMetrics(cpu_percent=50.0))
        rid = await manager.registry.register(r)
        metrics = await manager.get_metrics(rid)
        assert metrics is not None
        assert metrics.cpu_percent == 50.0

    async def test_get_health_not_found(self, manager: RuntimeManager) -> None:
        assert await manager.get_health("missing") is None

    async def test_get_health_returns_health(self, manager: RuntimeManager) -> None:
        r = Runtime(name="healthy-one", health=RuntimeHealth.HEALTHY)
        rid = await manager.registry.register(r)
        health = await manager.get_health(rid)
        assert health == RuntimeHealth.HEALTHY
