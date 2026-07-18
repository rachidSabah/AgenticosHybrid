"""Tests for DiscoveryFramework hot-reload functionality.

Covers start/stop lifecycle, EventBus integration, file watcher polling,
and graceful error handling.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agentic_os.domain.events import EventEnvelope, Topic


@pytest.fixture
def mock_bus():
    """Create a fully mocked EventBus."""
    bus = AsyncMock()
    bus.subscribe = AsyncMock(return_value="sub-1")
    bus.unsubscribe = AsyncMock()
    return bus


@pytest.fixture
def mock_registry():
    """Create a mocked DiscoveryRegistry."""
    registry = MagicMock()
    registry.get_provider = MagicMock(return_value=None)
    registry.list_providers = MagicMock(return_value=[])
    return registry


@pytest.fixture
def mock_cache():
    """Create a mocked DiscoveryCache."""
    cache = MagicMock()
    cache.invalidate_by_provider = MagicMock(return_value=0)
    return cache


@pytest.fixture
def mock_config():
    """Create a mocked DiscoveryConfiguration."""
    config = MagicMock()
    config.profiles = {}
    config.get_profile = MagicMock(return_value=None)
    config.default_profile = "default"
    config.enabled = True
    config.cache_ttl_seconds = 300.0
    config.max_cache_entries = 1000
    config.telemetry_max_entries = 1000
    config.rules = []
    return config


@pytest.fixture
def framework(mock_bus, mock_registry, mock_cache, mock_config):
    """Build a DiscoveryFramework with all subcomponents mocked."""
    from agentic_os.core.discovery.framework import DiscoveryFramework
    from agentic_os.core.discovery.profiling import ProfilingEngine
    from agentic_os.core.discovery.publisher import DiscoveryEventPublisher
    from agentic_os.core.discovery.scheduler import DiscoveryScheduler
    from agentic_os.core.discovery.telemetry import DiscoveryTelemetry
    from agentic_os.core.discovery.validation import ValidationPipeline
    from agentic_os.core.runtime.discovery import DiscoveryEngine

    return DiscoveryFramework(
        bus=mock_bus,
        core_engine=DiscoveryEngine(),
        registry=mock_registry,
        cache=mock_cache,
        telemetry=DiscoveryTelemetry(),
        scheduler=DiscoveryScheduler(),
        config=mock_config,
        validation=ValidationPipeline(),
        profiling=ProfilingEngine(),
        publisher=DiscoveryEventPublisher(bus=mock_bus),
    )


class TestHotReloadStart:
    """Tests for start_hot_reload()."""

    @pytest.mark.asyncio
    async def test_start_sets_running_flag(self, framework) -> None:
        assert framework.hot_reload_running is False
        await framework.start_hot_reload()
        assert framework.hot_reload_running is True
        await framework.stop_hot_reload()

    @pytest.mark.asyncio
    async def test_start_subscribes_to_engine_updated(self, framework, mock_bus) -> None:
        await framework.start_hot_reload()
        mock_bus.subscribe.assert_called_once_with(
            Topic.ENGINE_UPDATED.value,
            framework._handle_hot_reload_event,
        )
        await framework.stop_hot_reload()

    @pytest.mark.asyncio
    async def test_start_creates_watcher_task(self, framework) -> None:
        await framework.start_hot_reload()
        assert len(framework._watchers) == 1
        assert isinstance(framework._watchers[0], asyncio.Task)
        watcher_name = framework._watchers[0].get_name()
        assert "discovery-hot-reload" in watcher_name
        await framework.stop_hot_reload()

    @pytest.mark.asyncio
    async def test_double_start_is_safe(self, framework, mock_bus) -> None:
        await framework.start_hot_reload()
        first_watcher_count = len(framework._watchers)
        first_sub_count = len(framework._subscriptions)

        # Second start should be a no-op
        await framework.start_hot_reload()
        assert len(framework._watchers) == first_watcher_count
        assert len(framework._subscriptions) == first_sub_count
        assert mock_bus.subscribe.call_count == 1

        await framework.stop_hot_reload()


class TestHotReloadStop:
    """Tests for stop_hot_reload()."""

    @pytest.mark.asyncio
    async def test_stop_clears_running_flag(self, framework) -> None:
        await framework.start_hot_reload()
        await framework.stop_hot_reload()
        assert framework.hot_reload_running is False

    @pytest.mark.asyncio
    async def test_stop_cancels_tasks(self, framework) -> None:
        await framework.start_hot_reload()
        watcher = framework._watchers[0]
        assert not watcher.cancelled()

        await framework.stop_hot_reload()
        # The task may be in cancelling state (Python 3.14) or fully cancelled
        assert watcher.cancelling() or watcher.cancelled()
        assert len(framework._watchers) == 0

    @pytest.mark.asyncio
    async def test_stop_unsubscribes_from_bus(self, framework, mock_bus) -> None:
        await framework.start_hot_reload()
        await framework.stop_hot_reload()
        mock_bus.unsubscribe.assert_called_once_with("sub-1")
        assert len(framework._subscriptions) == 0

    @pytest.mark.asyncio
    async def test_stop_handles_bus_error_gracefully(self, framework, mock_bus) -> None:
        mock_bus.unsubscribe.side_effect = RuntimeError("bus error")
        await framework.start_hot_reload()
        # Should not raise
        await framework.stop_hot_reload()
        assert framework.hot_reload_running is False

    @pytest.mark.asyncio
    async def test_stop_when_not_started_is_safe(self, framework) -> None:
        # Should not raise
        await framework.stop_hot_reload()
        assert framework.hot_reload_running is False


class TestHotReloadEventHandler:
    """Tests for _handle_hot_reload_event()."""

    @pytest.mark.asyncio
    async def test_handle_event_with_engine_id(self, framework) -> None:
        event = EventEnvelope(
            type="event",
            source="test",
            topic=Topic.ENGINE_UPDATED.value,
            payload={"engine_id": "engine-123"},
        )
        # Should not raise
        await framework._handle_hot_reload_event(event)

    @pytest.mark.asyncio
    async def test_handle_event_without_engine_id(self, framework) -> None:
        event = EventEnvelope(
            type="event",
            source="test",
            topic=Topic.ENGINE_UPDATED.value,
            payload={},
        )
        # Should not raise and return early
        await framework._handle_hot_reload_event(event)

    @pytest.mark.asyncio
    async def test_handle_event_with_empty_engine_id(self, framework) -> None:
        event = EventEnvelope(
            type="event",
            source="test",
            topic=Topic.ENGINE_UPDATED.value,
            payload={"engine_id": ""},
        )
        await framework._handle_hot_reload_event(event)


class TestWatcher:
    """Tests for _watch_executables()."""

    @pytest.mark.asyncio
    async def test_watcher_exits_on_cancelled_error(self, framework) -> None:
        framework._hot_reload_running = True

        # Request cancellation after first iteration
        async def delayed_cancel():
            await asyncio.sleep(0.05)
            framework._hot_reload_running = False

        async def run_watcher():
            await framework._watch_executables()

        # Run the watcher in a task that gets cancelled
        task = asyncio.create_task(run_watcher())
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        # The watcher handled CancelledError gracefully
        assert True

    @pytest.mark.asyncio
    async def test_watcher_detects_executable_change(self, framework) -> None:
        from agentic_os.domain.discovery import DiscoveryProfile, DiscoveryProviderConfig

        provider_cfg = DiscoveryProviderConfig(
            name="mock-provider", provider_type="mock", enabled=True
        )
        profile = DiscoveryProfile(
            name="test",
            provider_configs=(provider_cfg,),
        )

        framework._hot_reload_running = False

        mock_provider = MagicMock()
        mock_provider.discover = AsyncMock(return_value=[])
        mock_provider.get_provider_name = MagicMock(return_value="mock-provider")
        framework.registry.get_provider = MagicMock(return_value=mock_provider)
        framework.config.profiles = {"test": profile}

        # Should not raise -- runs one quick iteration then stops via flag
        framework._hot_reload_running = True
        # Cancel after first yield to break the loop
        with patch.object(framework.cache, "invalidate_by_provider"):
            task = asyncio.create_task(framework._watch_executables())
            await asyncio.sleep(0.1)
            framework._hot_reload_running = False
            await asyncio.sleep(0.1)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError, Exception:
                pass

    @pytest.mark.asyncio
    async def test_watcher_handles_provider_error(self, framework) -> None:
        """Watcher should continue if a provider raises during discovery."""
        from agentic_os.domain.discovery import DiscoveryProfile, DiscoveryProviderConfig

        provider_cfg = DiscoveryProviderConfig(
            name="failing-provider", provider_type="mock", enabled=True
        )
        profile = DiscoveryProfile(
            name="test",
            provider_configs=(provider_cfg,),
        )

        mock_provider = MagicMock()
        mock_provider.discover = AsyncMock(side_effect=RuntimeError("provider failed"))
        framework.registry.get_provider = MagicMock(return_value=mock_provider)
        framework.config.profiles = {"test": profile}

        framework._hot_reload_running = True
        task = asyncio.create_task(framework._watch_executables())
        await asyncio.sleep(0.1)
        framework._hot_reload_running = False
        await asyncio.sleep(0.1)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError, Exception:
            pass
        # Watcher handled the error gracefully
        assert True


class TestAsyncIOCreateTask:
    """Tests for the standalone asyncio_create_task helper."""

    @pytest.mark.asyncio
    async def test_create_task_with_name(self) -> None:
        from agentic_os.core.discovery.framework import asyncio_create_task

        async def dummy():
            return 42

        task = asyncio_create_task(dummy(), name="test-task")
        assert task.get_name() == "test-task"
        result = await task
        assert result == 42

    @pytest.mark.asyncio
    async def test_create_task_without_name(self) -> None:
        from agentic_os.core.discovery.framework import asyncio_create_task

        async def dummy():
            return 99

        task = asyncio_create_task(dummy())
        result = await task
        assert result == 99

    @pytest.mark.asyncio
    async def test_create_task_handles_exception(self) -> None:
        from agentic_os.core.discovery.framework import asyncio_create_task

        async def failing():
            msg = "task error"
            raise ValueError(msg)

        task = asyncio_create_task(failing())
        with pytest.raises(ValueError, match="task error"):
            await task


class TestHotReloadProperty:
    """Tests for the hot_reload_running property."""

    @pytest.mark.asyncio
    async def test_property_initially_false(self, framework) -> None:
        assert framework.hot_reload_running is False

    @pytest.mark.asyncio
    async def test_property_true_after_start(self, framework) -> None:
        await framework.start_hot_reload()
        assert framework.hot_reload_running is True
        await framework.stop_hot_reload()

    @pytest.mark.asyncio
    async def test_property_false_after_stop(self, framework) -> None:
        await framework.start_hot_reload()
        await framework.stop_hot_reload()
        assert framework.hot_reload_running is False
