"""Tests for RuntimeController — start/stop/restart lifecycle with mock launcher."""

import pytest

from agentic_os.core.runtime.runtime import Runtime, RuntimeHealth, RuntimeStatus, RuntimeType
from agentic_os.core.runtime.runtime_controller import RuntimeController
from agentic_os.core.runtime.runtime_registry import RuntimeRegistry


@pytest.fixture
async def registry() -> RuntimeRegistry:
    return RuntimeRegistry()


@pytest.fixture
def fake_bus() -> object:
    class _FakeBus:
        async def publish(self, topic: str, data: object) -> None:
            pass

    return _FakeBus()


@pytest.fixture
def mock_launcher() -> object:
    class _MockLauncher:
        async def launch(self, runtime: Runtime) -> dict:
            return {"pid": 99999}

        async def stop(self, runtime: Runtime) -> int:
            return 0

        async def kill(self, runtime: Runtime) -> int:
            return 0

    return _MockLauncher()


@pytest.fixture
async def controller(registry, fake_bus, mock_launcher) -> RuntimeController:
    return RuntimeController(
        registry=registry,
        launcher=mock_launcher,
        bus=fake_bus,
    )


def _make_runtime(**kw: object) -> Runtime:
    defaults = dict(name="test-rt", type=RuntimeType.PYTHON)
    defaults.update(kw)
    return Runtime(**defaults)  # type: ignore[arg-type]


@pytest.mark.asyncio
class TestRuntimeController:
    async def test_start_transitions_to_ready(
        self, controller: RuntimeController, registry: RuntimeRegistry
    ) -> None:
        r = _make_runtime(status=RuntimeStatus.DISCOVERED)
        rid = await registry.register(r)
        result = await controller.start(rid)
        assert result.status == RuntimeStatus.READY
        assert result.health == RuntimeHealth.HEALTHY
        assert result.pid == 99999

    async def test_start_from_registered(
        self, controller: RuntimeController, registry: RuntimeRegistry
    ) -> None:
        r = _make_runtime(status=RuntimeStatus.REGISTERED)
        rid = await registry.register(r)
        result = await controller.start(rid)
        assert result.status == RuntimeStatus.READY

    async def test_start_from_stopped(
        self, controller: RuntimeController, registry: RuntimeRegistry
    ) -> None:
        r = _make_runtime(status=RuntimeStatus.STOPPED)
        rid = await registry.register(r)
        result = await controller.start(rid)
        assert result.status == RuntimeStatus.READY

    async def test_start_from_crashed(
        self, controller: RuntimeController, registry: RuntimeRegistry
    ) -> None:
        r = _make_runtime(status=RuntimeStatus.CRASHED)
        rid = await registry.register(r)
        result = await controller.start(rid)
        assert result.status == RuntimeStatus.READY

    async def test_start_from_failed(
        self, controller: RuntimeController, registry: RuntimeRegistry
    ) -> None:
        r = _make_runtime(status=RuntimeStatus.FAILED)
        rid = await registry.register(r)
        result = await controller.start(rid)
        assert result.status == RuntimeStatus.READY

    async def test_start_invalid_state_raises(
        self, controller: RuntimeController, registry: RuntimeRegistry
    ) -> None:
        r = _make_runtime(status=RuntimeStatus.STARTING)
        rid = await registry.register(r)
        with pytest.raises(RuntimeError, match="Cannot start runtime"):
            await controller.start(rid)

    async def test_start_not_found_raises(self, controller: RuntimeController) -> None:
        with pytest.raises(ValueError, match="not found"):
            await controller.start("missing")

    async def test_stop_graceful(
        self, controller: RuntimeController, registry: RuntimeRegistry
    ) -> None:
        r = _make_runtime(status=RuntimeStatus.READY, pid=12345)
        rid = await registry.register(r)
        result = await controller.stop(rid, force=False)
        assert result.status == RuntimeStatus.STOPPED
        assert result.health == RuntimeHealth.STOPPED

    async def test_stop_force(
        self, controller: RuntimeController, registry: RuntimeRegistry
    ) -> None:
        r = _make_runtime(status=RuntimeStatus.READY, pid=12345)
        rid = await registry.register(r)
        result = await controller.stop(rid, force=True)
        assert result.status == RuntimeStatus.STOPPED

    async def test_stop_already_stopped(
        self, controller: RuntimeController, registry: RuntimeRegistry
    ) -> None:
        r = _make_runtime(status=RuntimeStatus.STOPPED)
        rid = await registry.register(r)
        result = await controller.stop(rid)
        assert result.status == RuntimeStatus.STOPPED

    async def test_stop_no_pid(
        self, controller: RuntimeController, registry: RuntimeRegistry
    ) -> None:
        r = _make_runtime(status=RuntimeStatus.READY, pid=None)
        rid = await registry.register(r)
        result = await controller.stop(rid)
        assert result.status == RuntimeStatus.STOPPED

    async def test_stop_not_found_raises(self, controller: RuntimeController) -> None:
        with pytest.raises(ValueError, match="not found"):
            await controller.stop("missing")

    async def test_restart(self, controller: RuntimeController, registry: RuntimeRegistry) -> None:
        r = _make_runtime(status=RuntimeStatus.READY, pid=12345)
        rid = await registry.register(r)
        result = await controller.restart(rid)
        assert result.status == RuntimeStatus.READY
        assert result.restart_count >= 1

    async def test_restart_already_stopped(
        self, controller: RuntimeController, registry: RuntimeRegistry
    ) -> None:
        r = _make_runtime(status=RuntimeStatus.STOPPED)
        rid = await registry.register(r)
        result = await controller.restart(rid)
        assert result.status == RuntimeStatus.READY

    async def test_restart_not_found_raises(self, controller: RuntimeController) -> None:
        with pytest.raises(ValueError, match="not found"):
            await controller.restart("missing")

    async def test_kill(self, controller: RuntimeController, registry: RuntimeRegistry) -> None:
        r = _make_runtime(status=RuntimeStatus.READY, pid=12345)
        rid = await registry.register(r)
        result = await controller.kill(rid)
        assert result.status == RuntimeStatus.STOPPED
        assert result.health == RuntimeHealth.STOPPED

    async def test_kill_no_pid(
        self, controller: RuntimeController, registry: RuntimeRegistry
    ) -> None:
        r = _make_runtime(status=RuntimeStatus.READY, pid=None)
        rid = await registry.register(r)
        result = await controller.kill(rid)
        assert result.status == RuntimeStatus.STOPPED

    async def test_kill_not_found_raises(self, controller: RuntimeController) -> None:
        with pytest.raises(ValueError, match="not found"):
            await controller.kill("missing")

    async def test_launcher_failure_sets_failed(
        self, controller: RuntimeController, registry: RuntimeRegistry
    ) -> None:
        class _FailingLauncher:
            async def launch(self, runtime: Runtime) -> dict:
                raise RuntimeError("Launch failed")

        ctrl = RuntimeController(
            registry=registry,
            launcher=_FailingLauncher(),
        )
        r = _make_runtime(status=RuntimeStatus.DISCOVERED)
        rid = await registry.register(r)
        with pytest.raises(RuntimeError, match="Launch failed"):
            await ctrl.start(rid)
        fetched = await registry.get(rid)
        assert fetched is not None
        assert fetched.status == RuntimeStatus.FAILED
        assert fetched.health == RuntimeHealth.UNHEALTHY
        assert "Launch failed" in (fetched.last_error or "")
