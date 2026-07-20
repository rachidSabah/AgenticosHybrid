"""Integration tests for services.runtime_discovery subsystems."""

from __future__ import annotations

import sys
from pathlib import Path

_services_path = str(Path(__file__).resolve().parent.parent / "services")
if _services_path not in sys.path:
    sys.path.insert(0, _services_path)

from unittest.mock import AsyncMock, MagicMock

import pytest
from services.runtime_discovery.binding import RuntimeBindingManager
from services.runtime_discovery.configuration import RuntimeConfigurationManager
from services.runtime_discovery.manager import RuntimeDiscoveryManager
from services.runtime_discovery.models import (
    BindingStatus,
    Runtime,
    RuntimeBindingConfig,
    RuntimeConfiguration,
    RuntimeTelemetry,
    RuntimeType,
)
from services.runtime_discovery.scheduler import RuntimeDiscoveryScheduler
from services.runtime_discovery.telemetry import RuntimeTelemetryCollector


class TestRuntimeBindingManager:
    @pytest.fixture
    def engine_manager(self) -> MagicMock:
        em = MagicMock()
        em.register_engine = AsyncMock()
        em.unregister_engine = AsyncMock()
        return em

    @pytest.fixture
    def binding_manager(self, engine_manager) -> RuntimeBindingManager:
        return RuntimeBindingManager(engine_manager)

    async def test_bind_default_config(
        self, binding_manager: RuntimeBindingManager, engine_manager
    ) -> None:
        runtime = Runtime(name="python3", runtime_type=RuntimeType.PYTHON)
        binding = await binding_manager.bind(runtime)
        assert binding.status == BindingStatus.BOUND
        assert binding.engine_name == "python3"
        engine_manager.register_engine.assert_awaited_once()

    async def test_bind_with_custom_config(
        self, binding_manager: RuntimeBindingManager, engine_manager
    ) -> None:
        runtime = Runtime(name="python3", runtime_type=RuntimeType.PYTHON)
        config = RuntimeBindingConfig(auto_register=True, auto_start=False)
        binding = await binding_manager.bind(runtime, config)
        assert binding.status == BindingStatus.BOUND
        engine_manager.register_engine.assert_awaited_once()

    async def test_bind_claude(
        self, binding_manager: RuntimeBindingManager, engine_manager
    ) -> None:
        runtime = Runtime(name="claude", runtime_type=RuntimeType.CLAUDE_CODE)
        binding = await binding_manager.bind(runtime)
        assert binding.status == BindingStatus.BOUND
        engine_manager.register_engine.assert_awaited_once()

    async def test_bind_failure(
        self, binding_manager: RuntimeBindingManager, engine_manager
    ) -> None:
        engine_manager.register_engine.side_effect = RuntimeError("registration failed")
        runtime = Runtime(name="python3", runtime_type=RuntimeType.PYTHON)
        binding = await binding_manager.bind(runtime)
        assert binding.status == BindingStatus.FAILED
        assert "registration failed" in (binding.error or "")

    async def test_unbind(self, binding_manager: RuntimeBindingManager, engine_manager) -> None:
        runtime = Runtime(name="python3", runtime_type=RuntimeType.PYTHON)
        await binding_manager.bind(runtime)
        result = await binding_manager.unbind(runtime.runtime_id)
        assert result is True
        engine_manager.unregister_engine.assert_awaited_once()

    async def test_unbind_nonexistent(self, binding_manager: RuntimeBindingManager) -> None:
        result = await binding_manager.unbind("nonexistent")
        assert result is False

    async def test_get_binding(self, binding_manager: RuntimeBindingManager) -> None:
        runtime = Runtime(name="test", runtime_type=RuntimeType.PYTHON)
        await binding_manager.bind(runtime)
        binding = binding_manager.get_binding(runtime.runtime_id)
        assert binding is not None
        assert binding.status == BindingStatus.BOUND

    async def test_get_binding_nonexistent(self, binding_manager: RuntimeBindingManager) -> None:
        assert binding_manager.get_binding("nonexistent") is None

    async def test_list_bindings(self, binding_manager: RuntimeBindingManager) -> None:
        await binding_manager.bind(Runtime(name="a", runtime_type=RuntimeType.PYTHON))
        await binding_manager.bind(Runtime(name="b", runtime_type=RuntimeType.GIT))
        assert len(binding_manager.list_bindings()) == 2

    async def test_list_bindings_by_status(
        self, binding_manager: RuntimeBindingManager, engine_manager
    ) -> None:
        engine_manager.register_engine.side_effect = RuntimeError("fail")
        await binding_manager.bind(Runtime(name="a", runtime_type=RuntimeType.PYTHON))
        engine_manager.register_engine.side_effect = None
        await binding_manager.bind(Runtime(name="b", runtime_type=RuntimeType.GIT))
        failed = binding_manager.list_bindings(status=BindingStatus.FAILED)
        assert len(failed) == 1


class TestRuntimeConfigurationManager:
    @pytest.fixture
    def config_manager(self, tmp_path) -> RuntimeConfigurationManager:
        return RuntimeConfigurationManager(config_dir=tmp_path)

    async def test_set_and_get_config(self, config_manager: RuntimeConfigurationManager) -> None:
        config = RuntimeConfiguration(runtime_id="test123", enabled=False)
        await config_manager.set_config("test123", config)
        retrieved = await config_manager.get_config("test123")
        assert retrieved is not None
        assert retrieved.enabled is False

    async def test_get_nonexistent(self, config_manager: RuntimeConfigurationManager) -> None:
        assert await config_manager.get_config("nonexistent") is None

    async def test_reset_config(self, config_manager: RuntimeConfigurationManager) -> None:
        config = RuntimeConfiguration(runtime_id="test123")
        await config_manager.set_config("test123", config)
        assert await config_manager.get_config("test123") is not None
        await config_manager.reset_config("test123")
        assert await config_manager.get_config("test123") is None

    async def test_list_configs(self, config_manager: RuntimeConfigurationManager) -> None:
        await config_manager.set_config("a", RuntimeConfiguration(runtime_id="a"))
        await config_manager.set_config("b", RuntimeConfiguration(runtime_id="b"))
        configs = await config_manager.list_configs()
        assert len(configs) == 2

    async def test_update_config(self, config_manager: RuntimeConfigurationManager) -> None:
        config = RuntimeConfiguration(runtime_id="test123")
        await config_manager.set_config("test123", config)
        updated = await config_manager.update_config(
            "test123", {"enabled": False, "timeout_s": 600.0}
        )
        assert updated is not None
        assert updated.enabled is False
        assert updated.timeout_s == 600.0

    async def test_update_config_creates_new(
        self, config_manager: RuntimeConfigurationManager
    ) -> None:
        updated = await config_manager.update_config("new_id", {"enabled": False})
        assert updated is not None
        assert updated.runtime_id == "new_id"

    async def test_persistence(self, config_manager: RuntimeConfigurationManager) -> None:
        config = RuntimeConfiguration(runtime_id="persist_test", enabled=False)
        await config_manager.set_config("persist_test", config)
        # Create a new manager with same dir to test file loading
        manager2 = RuntimeConfigurationManager(config_dir=config_manager._config_dir)
        retrieved = await manager2.get_config("persist_test")
        assert retrieved is not None
        assert retrieved.enabled is False


class TestRuntimeDiscoveryScheduler:
    @pytest.fixture
    def scheduler(self) -> RuntimeDiscoveryScheduler:
        return RuntimeDiscoveryScheduler()

    async def test_schedule_and_unschedule(self, scheduler: RuntimeDiscoveryScheduler) -> None:
        scheduler._running = True
        coro = MagicMock()
        coro.return_value = None
        await scheduler.schedule("test_task", 3600, coro)
        assert scheduler.is_scheduled("test_task") is True
        await scheduler.unschedule("test_task")
        assert scheduler.is_scheduled("test_task") is False

    async def test_schedule_duplicate(self, scheduler: RuntimeDiscoveryScheduler) -> None:
        scheduler._running = True
        coro = MagicMock()
        coro.return_value = None
        await scheduler.schedule("task", 3600, coro)
        await scheduler.schedule("task", 3600, coro)
        assert len(scheduler.list_scheduled()) == 1

    async def test_start_stop_all(self, scheduler: RuntimeDiscoveryScheduler) -> None:
        scheduler._running = True
        coro = MagicMock()
        coro.return_value = None
        await scheduler.schedule("task", 3600, coro)
        await scheduler.stop_all()
        assert scheduler._running is False
        assert len(scheduler.list_scheduled()) == 0

    async def test_schedule_not_running(self, scheduler: RuntimeDiscoveryScheduler) -> None:
        coro = MagicMock()
        coro.return_value = None
        await scheduler.schedule("task", 1, coro)
        # Should not crash - loop just won't run
        assert scheduler.is_scheduled("task") is True

    async def test_start_all(self, scheduler: RuntimeDiscoveryScheduler) -> None:
        await scheduler.start_all()
        assert scheduler._running is True

    async def test_list_scheduled_empty(self, scheduler: RuntimeDiscoveryScheduler) -> None:
        assert scheduler.list_scheduled() == []


class TestRuntimeTelemetryCollector:
    @pytest.fixture
    def collector(self) -> RuntimeTelemetryCollector:
        return RuntimeTelemetryCollector(max_history=10)

    async def test_record_and_get(self, collector: RuntimeTelemetryCollector) -> None:
        telemetry = RuntimeTelemetry(
            runtime_id="test123",
            runtime_type=RuntimeType.PYTHON,
            name="python3",
        )
        await collector.record("test123", telemetry)
        retrieved = await collector.get("test123")
        assert retrieved is not None
        assert retrieved.name == "python3"

    async def test_get_nonexistent(self, collector: RuntimeTelemetryCollector) -> None:
        assert await collector.get("ghost") is None

    async def test_get_all(self, collector: RuntimeTelemetryCollector) -> None:
        await collector.record("a", RuntimeTelemetry(runtime_id="a"))
        await collector.record("b", RuntimeTelemetry(runtime_id="b"))
        all_telemetry = await collector.get_all()
        assert len(all_telemetry) == 2

    async def test_flush(self, collector: RuntimeTelemetryCollector) -> None:
        await collector.record("a", RuntimeTelemetry(runtime_id="a"))
        assert len(await collector.get_all()) == 1
        await collector.flush()
        assert len(await collector.get_all()) == 0

    async def test_get_history(self, collector: RuntimeTelemetryCollector) -> None:
        t = RuntimeTelemetry(runtime_id="test123")
        await collector.record("test123", t)
        history = collector.get_history("test123")
        assert len(history) == 1

    async def test_history_limit(self, collector: RuntimeTelemetryCollector) -> None:
        for _ in range(20):
            await collector.record("test123", RuntimeTelemetry(runtime_id="test123"))
        history = collector.get_history("test123")
        assert len(history) <= 10

    async def test_get_stats(self, collector: RuntimeTelemetryCollector) -> None:
        t1 = RuntimeTelemetry(runtime_id="a", name="tool_a")
        t1.record_execution(1.0, success=True)
        t2 = RuntimeTelemetry(runtime_id="b", name="tool_b")
        t2.record_execution(2.0, success=False)
        await collector.record("a", t1)
        await collector.record("b", t2)
        stats = collector.get_stats()
        assert stats["total_runtimes"] == 2
        assert stats["total_tasks_completed"] == 1
        assert stats["total_tasks_failed"] == 1


class TestRuntimeEventPublisher:
    @pytest.fixture
    def bus(self) -> AsyncMock:
        bus = AsyncMock()
        bus.publish = AsyncMock()
        return bus

    async def test_publish_event(self, bus) -> None:
        from services.runtime_discovery.events import RuntimeEventPublisher

        publisher = RuntimeEventPublisher(bus)
        from core.contracts.event import EventTopic

        await publisher.publish(EventTopic.RUNTIME_DISCOVERY_SCAN_STARTED, {"profile": "default"})
        bus.publish.assert_awaited_once()

    async def test_publish_discovery_events(self, bus) -> None:
        from services.runtime_discovery.events import (
            publish_discovery_engine_found,
            publish_discovery_scan_completed,
            publish_discovery_scan_started,
        )

        await publish_discovery_scan_started(bus, "default", 10)
        bus.publish.assert_called()
        bus.publish.reset_mock()

        await publish_discovery_scan_completed(bus, "default", 5, 100.0)
        bus.publish.assert_called()
        bus.publish.reset_mock()

        await publish_discovery_engine_found(bus, "python", "python3", "3.14.0", "path")
        assert bus.publish.await_count >= 1

    async def test_publish_binding_events(self, bus) -> None:
        from services.runtime_discovery.events import (
            publish_binding_completed,
            publish_binding_failed,
            publish_binding_started,
            publish_binding_unbound,
        )

        await publish_binding_started(bus, "id1", "engine1")
        await publish_binding_completed(bus, "id1", "engine1")
        await publish_binding_failed(bus, "id1", "engine1", "error")
        await publish_binding_unbound(bus, "id1", "engine1")
        assert bus.publish.await_count == 4

    async def test_publish_validation_events(self, bus) -> None:
        from services.runtime_discovery.events import (
            publish_validation_failed,
            publish_validation_passed,
            publish_validation_started,
        )

        await publish_validation_started(bus, "id1", "test")
        await publish_validation_passed(bus, "id1", "test")
        await publish_validation_failed(bus, "id1", "test", ["err1"])
        assert bus.publish.await_count == 3

    async def test_publish_health_events(self, bus) -> None:
        from services.runtime_discovery.events import (
            publish_health_check_failed,
            publish_health_check_passed,
            publish_health_degraded,
            publish_health_recovered,
            publish_health_status_changed,
        )

        await publish_health_check_passed(bus, "id1", "test", 50.0)
        await publish_health_check_failed(bus, "id1", "test", "timeout")
        await publish_health_status_changed(bus, "id1", "test", "unhealthy")
        await publish_health_degraded(bus, "id1", "test", "high latency")
        await publish_health_recovered(bus, "id1", "test")
        assert bus.publish.await_count == 5

    async def test_publish_profile_events(self, bus) -> None:
        from services.runtime_discovery.events import (
            publish_profile_created,
            publish_profile_updated,
        )

        await publish_profile_created(bus, "id1", "1.0")
        await publish_profile_updated(bus, "id1", "1.1")
        assert bus.publish.await_count == 2

    async def test_publish_config_events(self, bus) -> None:
        from services.runtime_discovery.events import publish_configuration_changed

        await publish_configuration_changed(bus, "id1", "timeout")
        assert bus.publish.await_count == 1

    async def test_publish_telemetry_events(self, bus) -> None:
        from services.runtime_discovery.events import publish_telemetry_recorded

        await publish_telemetry_recorded(bus, "id1", 42)
        assert bus.publish.await_count == 1

    async def test_publish_registry_events(self, bus) -> None:
        from services.runtime_discovery.events import (
            publish_registry_registered,
            publish_registry_unregistered,
        )

        await publish_registry_registered(bus, "id1", "test", "python")
        await publish_registry_unregistered(bus, "id1", "test")
        assert bus.publish.await_count == 2


class TestRuntimeDiscoveryManager:
    @pytest.fixture
    def bus(self) -> AsyncMock:
        return AsyncMock()

    @pytest.fixture
    def engine_manager(self) -> MagicMock:
        em = MagicMock()
        em.initialize = AsyncMock()
        em.shutdown = AsyncMock()
        em.register_engine = AsyncMock()
        em.unregister_engine = AsyncMock()
        type(em).get_registry_snapshot = AsyncMock(return_value={"total": 0})
        return em

    @pytest.fixture
    async def manager(self, bus, engine_manager) -> RuntimeDiscoveryManager:
        m = RuntimeDiscoveryManager(bus=bus, engine_manager=engine_manager)
        return m

    async def test_initialization(self, manager, engine_manager) -> None:
        assert manager._initialized is False
        await manager.initialize()
        engine_manager.initialize.assert_awaited_once()
        assert manager._initialized is True

    async def test_shutdown(self, manager) -> None:
        await manager.initialize()
        await manager.shutdown()
        assert manager._initialized is False

    async def test_discover_and_bind_not_found(self, manager) -> None:
        from services.runtime_discovery.models import RuntimeDiscoveryResult

        result = RuntimeDiscoveryResult(found=False)
        runtime = await manager.discover_and_bind(result)
        assert runtime is None

    async def test_list_runtimes_empty(self, manager) -> None:
        await manager.initialize()
        runtimes = await manager.list_runtimes()
        assert isinstance(runtimes, list)

    async def test_get_runtime_async_nonexistent(self, manager) -> None:
        assert await manager.get_runtime_async("ghost") is None

    async def test_get_registry_snapshot(self, manager) -> None:
        await manager.initialize()
        snapshot = await manager.get_registry_snapshot()
        assert "total_runtimes" in snapshot

    async def test_get_cache_stats(self, manager) -> None:
        await manager.initialize()
        stats = manager.get_cache_stats()
        assert "total_entries" in stats

    async def test_auto_discovery_start_stop(self, manager) -> None:
        await manager.initialize()
        await manager.start_auto_discovery(interval_s=3600)
        await manager.stop_auto_discovery()

    async def test_health_monitoring_start_stop(self, manager) -> None:
        await manager.initialize()
        await manager.start_health_monitoring()
        await manager.stop_health_monitoring()

    def test_properties(self, manager) -> None:
        assert manager.engine_manager is not None
        assert manager.registry is not None
        assert manager.health_monitor is not None
        assert manager.binding_manager is not None
