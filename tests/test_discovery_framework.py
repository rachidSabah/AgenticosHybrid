"""Tests for the M2 DiscoveryFramework orchestrator."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agentic_os.core.discovery.cache import DiscoveryCache
from agentic_os.core.discovery.config import DiscoveryConfiguration
from agentic_os.core.discovery.framework import DiscoveryFramework
from agentic_os.core.discovery.profiling import ProfilingEngine
from agentic_os.core.discovery.publisher import DiscoveryEventPublisher
from agentic_os.core.discovery.registry import DiscoveryRegistry
from agentic_os.core.discovery.scheduler import DiscoveryScheduler
from agentic_os.core.discovery.telemetry import DiscoveryTelemetry
from agentic_os.core.discovery.validation import ValidationPipeline
from agentic_os.core.runtime.discovery import DiscoveryEngine
from agentic_os.domain.discovery import (
    DiscoveryCacheEntry,
    DiscoveryProfile,
    DiscoveryProviderConfig,
    DiscoveryRule,
    ProfileResult,
    ValidationResult,
)
from agentic_os.domain.events import Topic
from agentic_os.domain.execution import EngineCapability, EngineType
from agentic_os.ports.execution import DiscoveryProvider, EngineRegistration, RuntimeManagerPort


def _make_reg(
    name: str = "test-engine",
    engine_type: EngineType = EngineType.GENERIC,
    endpoint: str | None = "local:python",
    capabilities: list | None = None,
    version: str = "1.0.0",
    transport: str = "local",
    description: str = "",
    tags: list[str] | None = None,
    metadata: dict | None = None,
) -> EngineRegistration:
    return EngineRegistration(
        name=name,
        engine_type=engine_type,
        endpoint=endpoint,
        capabilities=capabilities or [],
        version=version,
        transport=transport,
        description=description,
        tags=tags or [],
        metadata=metadata or {},
    )


def _make_default_profile() -> DiscoveryProfile:
    return DiscoveryProfile(
        name="default",
        description="Default scan profile",
        provider_configs=(
            DiscoveryProviderConfig(name="path", provider_type="path", enabled=True),
        ),
    )


# ── Fixtures ──


class TestDiscoveryFrameworkSetup:
    @pytest.fixture
    def framework(self) -> DiscoveryFramework:
        bus = MagicMock(spec_set=["publish", "subscribe", "unsubscribe", "start", "stop"])
        bus.subscribe = AsyncMock(return_value="sub-1")
        bus.unsubscribe = AsyncMock()
        bus.publish = AsyncMock()

        core_engine = MagicMock(spec=DiscoveryEngine)
        core_engine.add_provider = MagicMock()
        core_engine.remove_provider = MagicMock(return_value=True)
        core_engine._providers = {}
        core_engine._get_provider_confidence = MagicMock(return_value=0.8)

        registry = MagicMock(spec_set=DiscoveryRegistry)
        registry.get_provider = MagicMock(return_value=None)
        registry.list_providers = MagicMock(return_value=[])
        registry.register = MagicMock()
        registry.unregister = MagicMock(return_value=True)
        registry.discover_by_provider = AsyncMock(return_value=[])
        registry.enable_provider = MagicMock(return_value=True)
        registry.disable_provider = MagicMock(return_value=True)
        registry.is_enabled = MagicMock(return_value=True)
        registry.count = MagicMock(return_value=0)

        cache = MagicMock(spec_set=DiscoveryCache)
        cache.make_key = MagicMock(return_value="cache-key-123")
        cache.get = MagicMock(return_value=None)
        cache.create_entry = MagicMock()
        cache.invalidate = MagicMock()
        cache.invalidate_all = MagicMock(return_value=2)
        cache.invalidate_by_provider = MagicMock(return_value=1)
        cache.list_entries = MagicMock(return_value=[])

        telemetry = MagicMock(spec_set=DiscoveryTelemetry)
        telemetry.start_scan = MagicMock(return_value="scan-1")
        telemetry.complete_scan = MagicMock()
        telemetry.get_history = MagicMock(return_value=[])

        scheduler = MagicMock(spec_set=DiscoveryScheduler)
        scheduler.start = AsyncMock()
        scheduler.stop = AsyncMock()

        config = MagicMock(spec_set=DiscoveryConfiguration)
        config.default_profile = "default"
        config.get_profile = MagicMock(return_value=None)
        config.add_profile = MagicMock()
        config.remove_profile = MagicMock(return_value=True)
        config.list_profiles = MagicMock(return_value=[])
        config.get_rules = MagicMock(return_value=[])
        config.add_rule = MagicMock()

        validation = MagicMock(spec_set=ValidationPipeline)
        validation.validate = AsyncMock(return_value=[])
        validation.validate_and_report = AsyncMock(return_value=(True, []))

        profiling = MagicMock(spec_set=ProfilingEngine)
        profiling.profile = AsyncMock(return_value=MagicMock(spec=ProfileResult))

        publisher = MagicMock(spec_set=DiscoveryEventPublisher)
        publisher.scan_started = AsyncMock()
        publisher.provider_running = AsyncMock()
        publisher.provider_failed = AsyncMock()
        publisher.cache_hit = AsyncMock()
        publisher.cache_miss = AsyncMock()
        publisher.engine_discovered = AsyncMock()
        publisher.engine_lost = AsyncMock()
        publisher.engine_registered = AsyncMock()
        publisher.engine_rejected = AsyncMock()
        publisher.validation_started = AsyncMock()
        publisher.validation_passed = AsyncMock()
        publisher.validation_failed = AsyncMock()
        publisher.profiling_started = AsyncMock()
        publisher.profiling_completed = AsyncMock()

        return DiscoveryFramework(
            bus=bus,
            core_engine=core_engine,
            registry=registry,
            cache=cache,
            telemetry=telemetry,
            scheduler=scheduler,
            config=config,
            validation=validation,
            profiling=profiling,
            publisher=publisher,
        )


# ── Core Discovery ──


class TestDiscover(TestDiscoveryFrameworkSetup):
    @pytest.mark.asyncio
    async def test_discover_returns_empty_when_no_profile(
        self, framework: DiscoveryFramework
    ) -> None:
        framework.config.get_profile.return_value = None
        framework.registry.count.return_value = 0

        result = await framework.discover()

        assert result == []
        framework.telemetry.start_scan.assert_not_called()

    @pytest.mark.asyncio
    async def test_discover_creates_default_profile_when_enabled_providers_exist(
        self, framework: DiscoveryFramework
    ) -> None:
        framework.config.get_profile.side_effect = lambda name: None  # no profiles exist
        framework.registry.count.return_value = 1
        framework.registry.list_providers.return_value = [
            {
                "name": "path",
                "provider_type": "path",
                "enabled": True,
                "interval_seconds": 60.0,
                "timeout_seconds": 10.0,
                "confidence_override": None,
            }
        ]

        result = await framework.discover()

        assert result == []
        framework.config.add_profile.assert_called_once()
        framework.publisher.scan_started.assert_called_once_with("default")

    @pytest.mark.asyncio
    async def test_discover_with_profile_runs_providers(
        self, framework: DiscoveryFramework
    ) -> None:
        profile = _make_default_profile()
        framework.config.get_profile.return_value = profile

        reg = _make_reg(name="engine-1")
        mock_provider = MagicMock(spec=DiscoveryProvider)
        mock_provider.get_provider_type.return_value = "path"
        framework.registry.get_provider.return_value = mock_provider
        framework.registry.discover_by_provider.return_value = [reg]

        result = await framework.discover()

        assert len(result) == 1
        assert result[0].name == "engine-1"
        framework.publisher.scan_started.assert_called_once_with("default")
        framework.telemetry.complete_scan.assert_called_once()

    @pytest.mark.asyncio
    async def test_discover_skips_disabled_providers(self, framework: DiscoveryFramework) -> None:
        profile = DiscoveryProfile(
            name="test",
            provider_configs=(
                DiscoveryProviderConfig(
                    name="disabled-provider", provider_type="path", enabled=False
                ),
            ),
        )
        framework.config.get_profile.return_value = profile

        result = await framework.discover()

        assert result == []
        framework.registry.discover_by_provider.assert_not_called()

    @pytest.mark.asyncio
    async def test_discover_skips_unregistered_provider(
        self, framework: DiscoveryFramework
    ) -> None:
        profile = _make_default_profile()
        framework.config.get_profile.return_value = profile
        framework.registry.get_provider.return_value = None  # provider not in registry

        result = await framework.discover()

        assert result == []
        framework.registry.discover_by_provider.assert_not_called()

    @pytest.mark.asyncio
    async def test_discover_uses_cache_hit(self, framework: DiscoveryFramework) -> None:
        profile = _make_default_profile()
        framework.config.get_profile.return_value = profile

        mock_provider = MagicMock(spec=DiscoveryProvider)
        mock_provider.get_provider_type.return_value = "path"
        framework.registry.get_provider.return_value = mock_provider
        framework.registry.discover_by_provider.return_value = [_make_reg(name="cached-engine")]

        cached_reg_json = json.dumps(
            {
                "name": "cached-engine",
                "engine_type": "generic",
                "endpoint": None,
                "transport": "local",
                "capabilities": [],
                "description": "",
                "version": "1.0.0",
                "tags": [],
                "metadata": {},
            }
        )
        cache_entry = MagicMock(spec=DiscoveryCacheEntry)
        cache_entry.registration_json = cached_reg_json
        framework.cache.get.return_value = cache_entry

        result = await framework.discover()

        assert len(result) == 1
        assert result[0].name == "cached-engine"
        framework.publisher.cache_hit.assert_called_once()
        framework.cache.create_entry.assert_not_called()

    @pytest.mark.asyncio
    async def test_discover_caches_on_miss(self, framework: DiscoveryFramework) -> None:
        profile = _make_default_profile()
        framework.config.get_profile.return_value = profile

        reg = _make_reg(
            name="new-engine",
            engine_type=EngineType.GENERIC,
            capabilities=[EngineCapability.CODING],
        )
        mock_provider = MagicMock(spec=DiscoveryProvider)
        mock_provider.get_provider_type.return_value = "path"
        framework.registry.get_provider.return_value = mock_provider
        framework.registry.discover_by_provider.return_value = [reg]
        framework.cache.get.return_value = None  # cache miss

        result = await framework.discover()

        assert len(result) == 1
        assert result[0].name == "new-engine"
        framework.publisher.cache_miss.assert_called_once()
        framework.cache.create_entry.assert_called_once()

    @pytest.mark.asyncio
    async def test_discover_applies_reject_rules(self, framework: DiscoveryFramework) -> None:
        profile = _make_default_profile()
        framework.config.get_profile.return_value = profile

        rule = DiscoveryRule(field="name", operator="contains", value="reject-me", action="reject")
        framework.config.get_rules.return_value = [rule]

        mock_provider = MagicMock(spec=DiscoveryProvider)
        mock_provider.get_provider_type.return_value = "path"
        framework.registry.get_provider.return_value = mock_provider
        framework.registry.discover_by_provider.return_value = [
            _make_reg(name="keep-me"),
            _make_reg(name="reject-me-please"),
        ]

        result = await framework.discover()

        assert len(result) == 1
        assert result[0].name == "keep-me"

    @pytest.mark.asyncio
    async def test_discover_deduplicates_by_name(self, framework: DiscoveryFramework) -> None:
        profile = DiscoveryProfile(
            name="multi",
            provider_configs=(
                DiscoveryProviderConfig(name="path", provider_type="path", enabled=True),
                DiscoveryProviderConfig(name="env", provider_type="env", enabled=True),
            ),
        )
        framework.config.get_profile.return_value = profile

        duplicate_reg = _make_reg(name="duplicate")

        mock_path = MagicMock(spec=DiscoveryProvider)
        mock_path.get_provider_type.return_value = "path"
        mock_env = MagicMock(spec=DiscoveryProvider)
        mock_env.get_provider_type.return_value = "env"

        def get_provider_side_effect(name: str):
            return {"path": mock_path, "env": mock_env}.get(name)

        framework.registry.get_provider.side_effect = get_provider_side_effect

        def discover_by_provider_side_effect(name: str):
            return {"path": [duplicate_reg], "env": [duplicate_reg]}.get(name, [])

        framework.registry.discover_by_provider.side_effect = discover_by_provider_side_effect

        result = await framework.discover()

        assert len(result) == 1
        assert result[0].name == "duplicate"

    @pytest.mark.asyncio
    async def test_discover_handles_provider_failure(self, framework: DiscoveryFramework) -> None:
        profile = _make_default_profile()
        framework.config.get_profile.return_value = profile

        mock_provider = MagicMock(spec=DiscoveryProvider)
        mock_provider.get_provider_type.return_value = "path"
        framework.registry.get_provider.return_value = mock_provider
        framework.registry.discover_by_provider.side_effect = RuntimeError("Connection refused")

        result = await framework.discover()

        assert result == []
        framework.publisher.provider_failed.assert_called_once()
        framework.telemetry.complete_scan.assert_called_once()

    @pytest.mark.asyncio
    async def test_discover_injects_provider_confidence_override(
        self, framework: DiscoveryFramework
    ) -> None:
        profile = DiscoveryProfile(
            name="test",
            provider_configs=(
                DiscoveryProviderConfig(
                    name="path", provider_type="path", enabled=True, confidence_override=1.0
                ),
            ),
        )
        framework.config.get_profile.return_value = profile
        framework.registry.get_provider.return_value = MagicMock(spec=DiscoveryProvider)

        reg = _make_reg(name="engine-1")
        framework.registry.discover_by_provider.return_value = [reg]
        framework.cache.get.return_value = None

        await framework.discover()

        # Should create cache entry with confidence 1.0 (override)
        call_kwargs = framework.cache.create_entry.call_args[1]
        assert call_kwargs["confidence"] == 1.0


class TestDiscoverAndRegister(TestDiscoveryFrameworkSetup):
    @pytest.mark.asyncio
    async def test_full_flow_registers_engines(self, framework: DiscoveryFramework) -> None:
        reg = _make_reg(name="engine-1")
        framework.config.get_profile.return_value = _make_default_profile()
        framework.registry.get_provider.return_value = MagicMock(spec=DiscoveryProvider)
        framework.registry.discover_by_provider.return_value = [reg]
        framework.cache.get.return_value = None

        validation_result = ValidationResult.passed(
            engine_id="engine-1", engine_name="engine-1", executable_exists=True
        )
        framework.validation.validate_and_report.return_value = (True, [validation_result])

        profile_result = MagicMock(spec=ProfileResult)
        profile_result.engine_id = "engine-1"
        profile_result.engine_name = "engine-1"
        framework.profiling.profile.return_value = profile_result

        registered_engine = MagicMock()
        registered_engine.id = "eng-uuid"
        registered_engine.name = "engine-1"
        runtime_manager = MagicMock(spec=RuntimeManagerPort)
        runtime_manager.register_engine = AsyncMock(return_value=registered_engine)
        framework._runtime_manager = runtime_manager

        result = await framework.discover_and_register()

        assert len(result) == 1
        assert result[0].id == "eng-uuid"
        framework.publisher.validation_started.assert_called_once_with("engine-1")
        framework.publisher.validation_passed.assert_called_once()
        framework.publisher.profiling_started.assert_called_once_with("engine-1")
        framework.publisher.profiling_completed.assert_called_once()
        runtime_manager.register_engine.assert_called_once_with(reg)

    @pytest.mark.asyncio
    async def test_skips_validation_when_profile_disables_it(
        self, framework: DiscoveryFramework
    ) -> None:
        reg = _make_reg(name="engine-1")
        profile = DiscoveryProfile(
            name="no-validate",
            provider_configs=(DiscoveryProviderConfig(name="path", provider_type="path"),),
            validate_after_discovery=False,
        )
        framework.config.get_profile.return_value = profile
        framework.registry.get_provider.return_value = MagicMock(spec=DiscoveryProvider)
        framework.registry.discover_by_provider.return_value = [reg]
        framework.cache.get.return_value = None

        runtime_manager = MagicMock(spec=RuntimeManagerPort)
        runtime_manager.register_engine = AsyncMock(return_value=MagicMock())
        framework._runtime_manager = runtime_manager

        result = await framework.discover_and_register()

        assert len(result) == 1
        framework.validation.validate_and_report.assert_not_called()
        framework.publisher.validation_started.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_registration_on_validation_failure(
        self, framework: DiscoveryFramework
    ) -> None:
        reg = _make_reg(name="bad-engine")
        framework.config.get_profile.return_value = _make_default_profile()
        framework.registry.get_provider.return_value = MagicMock(spec=DiscoveryProvider)
        framework.registry.discover_by_provider.return_value = [reg]
        framework.cache.get.return_value = None

        validation_result = ValidationResult.failed(
            "bad-engine",
            "bad-engine",
            "executable not found",
        )
        framework.validation.validate_and_report.return_value = (False, [validation_result])

        result = await framework.discover_and_register()

        assert result == []
        framework.publisher.validation_failed.assert_called_once()
        framework.publisher.engine_rejected.assert_called_once()
        framework.publisher.profiling_started.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_already_registered_engine(self, framework: DiscoveryFramework) -> None:
        reg = _make_reg(name="dupe")
        framework.config.get_profile.return_value = _make_default_profile()
        framework.registry.get_provider.return_value = MagicMock(spec=DiscoveryProvider)
        framework.registry.discover_by_provider.return_value = [reg]
        framework.cache.get.return_value = None

        validation_result = ValidationResult.passed(engine_id="dupe", engine_name="dupe")
        framework.validation.validate_and_report.return_value = (True, [validation_result])

        runtime_manager = MagicMock(spec=RuntimeManagerPort)
        runtime_manager.register_engine = AsyncMock(side_effect=ValueError("Already registered"))
        framework._runtime_manager = runtime_manager

        result = await framework.discover_and_register()

        # Already registered is handled gracefully
        assert result == []
        runtime_manager.register_engine.assert_called_once_with(reg)

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_registrations(self, framework: DiscoveryFramework) -> None:
        framework.config.get_profile.return_value = _make_default_profile()
        framework.registry.get_provider.return_value = MagicMock(spec=DiscoveryProvider)
        framework.registry.discover_by_provider.return_value = []

        result = await framework.discover_and_register()

        assert result == []


# ── Auto Discovery ──


class TestAutoDiscovery(TestDiscoveryFrameworkSetup):
    @pytest.mark.asyncio
    async def test_start_auto_discovery_delegates_to_scheduler(
        self, framework: DiscoveryFramework
    ) -> None:
        await framework.start_auto_discovery()
        framework.scheduler.start.assert_called_once_with(framework)

    @pytest.mark.asyncio
    async def test_stop_auto_discovery_delegates_to_scheduler(
        self, framework: DiscoveryFramework
    ) -> None:
        await framework.stop_auto_discovery()
        framework.scheduler.stop.assert_called_once()


# ── Hot Reload ──


class TestHotReload(TestDiscoveryFrameworkSetup):
    @staticmethod
    def _mock_create_task(coro, name=None):
        """Close the coroutine to avoid RuntimeWarning and return a mock Task."""
        coro.close()
        return MagicMock(spec=asyncio.Task)

    @pytest.mark.asyncio
    async def test_start_hot_reload_subscribes_and_starts_watcher(
        self, framework: DiscoveryFramework
    ) -> None:
        with patch(
            "agentic_os.core.discovery.framework.asyncio_create_task",
            side_effect=self._mock_create_task,
        ) as mock_task:
            await framework.start_hot_reload()

        assert framework.hot_reload_running
        framework.bus.subscribe.assert_called_once_with(
            Topic.ENGINE_UPDATED.value,
            framework._handle_hot_reload_event,
        )
        mock_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_hot_reload_is_idempotent(self, framework: DiscoveryFramework) -> None:
        with patch(
            "agentic_os.core.discovery.framework.asyncio_create_task",
            side_effect=self._mock_create_task,
        ) as mock_task:
            await framework.start_hot_reload()
            await framework.start_hot_reload()

        # Only subscribed once, only one task created
        framework.bus.subscribe.assert_called_once()
        mock_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_hot_reload_cancels_watchers_and_unsubscribes(
        self, framework: DiscoveryFramework
    ) -> None:
        mock_watcher = MagicMock(spec=asyncio.Task)
        with patch(
            "agentic_os.core.discovery.framework.asyncio_create_task",
            side_effect=lambda coro, name=None: (coro.close(), mock_watcher)[1],
        ) as _:
            await framework.start_hot_reload()

        await framework.stop_hot_reload()

        assert not framework.hot_reload_running
        mock_watcher.cancel.assert_called_once()
        framework.bus.unsubscribe.assert_called_once_with("sub-1")

    @pytest.mark.asyncio
    async def test_hot_reload_running_property(self, framework: DiscoveryFramework) -> None:
        assert not framework.hot_reload_running
        with patch(
            "agentic_os.core.discovery.framework.asyncio_create_task",
            side_effect=self._mock_create_task,
        ):
            await framework.start_hot_reload()
        assert framework.hot_reload_running


# ── Delegate Methods ──


class TestProviderManagement(TestDiscoveryFrameworkSetup):
    def test_list_providers_delegates_to_registry(self, framework: DiscoveryFramework) -> None:
        framework.registry.list_providers.return_value = [{"name": "path", "enabled": True}]
        result = framework.list_providers()
        assert result == [{"name": "path", "enabled": True}]
        framework.registry.list_providers.assert_called_once()

    def test_get_provider_delegates_to_registry(self, framework: DiscoveryFramework) -> None:
        framework.registry.get_provider.return_value = MagicMock(spec=DiscoveryProvider)
        result = framework.get_provider("path")
        assert result is not None
        framework.registry.get_provider.assert_called_once_with("path")

    def test_enable_provider_delegates_to_registry(self, framework: DiscoveryFramework) -> None:
        framework.registry.enable_provider.return_value = True
        result = framework.enable_provider("path")
        assert result is True
        framework.registry.enable_provider.assert_called_once_with("path")

    def test_disable_provider_delegates_to_registry(self, framework: DiscoveryFramework) -> None:
        framework.registry.disable_provider.return_value = True
        result = framework.disable_provider("path")
        assert result is True
        framework.registry.disable_provider.assert_called_once_with("path")

    def test_is_provider_enabled_delegates_to_registry(self, framework: DiscoveryFramework) -> None:
        framework.registry.is_enabled.return_value = True
        result = framework.is_provider_enabled("path")
        assert result is True
        framework.registry.is_enabled.assert_called_once_with("path")


class TestCacheManagement(TestDiscoveryFrameworkSetup):
    def test_get_cache_entries_delegates_to_cache(self, framework: DiscoveryFramework) -> None:
        entry = MagicMock()
        entry.to_dict.return_value = {"key": "k1", "provider_name": "path"}
        framework.cache.list_entries.return_value = [entry]

        result = framework.get_cache_entries()
        assert result == [{"key": "k1", "provider_name": "path"}]
        framework.cache.list_entries.assert_called_once()

    def test_invalidate_cache_with_key(self, framework: DiscoveryFramework) -> None:
        result = framework.invalidate_cache("some-key")
        assert result == 1
        framework.cache.invalidate.assert_called_once_with("some-key")

    def test_invalidate_cache_all_when_key_none(self, framework: DiscoveryFramework) -> None:
        result = framework.invalidate_cache()
        assert result == 2
        framework.cache.invalidate_all.assert_called_once()


class TestProfileManagement(TestDiscoveryFrameworkSetup):
    def test_add_profile_delegates_to_config(self, framework: DiscoveryFramework) -> None:
        profile = _make_default_profile()
        framework.add_profile(profile)
        framework.config.add_profile.assert_called_once_with(profile)

    def test_remove_profile_delegates_to_config(self, framework: DiscoveryFramework) -> None:
        framework.config.remove_profile.return_value = True
        result = framework.remove_profile("test")
        assert result is True
        framework.config.remove_profile.assert_called_once_with("test")

    def test_get_profile_delegates_to_config(self, framework: DiscoveryFramework) -> None:
        profile = _make_default_profile()
        framework.config.get_profile.return_value = profile
        result = framework.get_profile("default")
        assert result is profile
        framework.config.get_profile.assert_called_once_with("default")

    def test_list_profiles_delegates_to_config(self, framework: DiscoveryFramework) -> None:
        framework.config.list_profiles.return_value = [{"name": "default"}]
        result = framework.list_profiles()
        assert result == [{"name": "default"}]
        framework.config.list_profiles.assert_called_once()


class TestRegistration(TestDiscoveryFrameworkSetup):
    @pytest.mark.asyncio
    async def test_register_provider_adds_to_registry_and_core(
        self, framework: DiscoveryFramework
    ) -> None:
        provider = MagicMock(spec=DiscoveryProvider)
        config = DiscoveryProviderConfig(name="nim", provider_type="nim")

        framework.register_provider("nim", provider, config)

        framework.registry.register.assert_called_once_with("nim", provider, config)
        framework.core_engine.add_provider.assert_called_once_with(provider)

    @pytest.mark.asyncio
    async def test_register_provider_without_config(self, framework: DiscoveryFramework) -> None:
        provider = MagicMock(spec=DiscoveryProvider)

        framework.register_provider("nim", provider)

        framework.registry.register.assert_called_once_with("nim", provider, None)

    @pytest.mark.asyncio
    async def test_unregister_provider_removes_from_both(
        self, framework: DiscoveryFramework
    ) -> None:
        framework.core_engine.remove_provider.return_value = True
        framework.registry.unregister.return_value = True

        result = framework.unregister_provider("nim")

        assert result is True
        framework.core_engine.remove_provider.assert_called_once_with("nim")
        framework.registry.unregister.assert_called_once_with("nim")

    @pytest.mark.asyncio
    async def test_register_provider_skips_core_if_already_exists(
        self, framework: DiscoveryFramework
    ) -> None:
        provider = MagicMock(spec=DiscoveryProvider)
        framework.core_engine._providers = {"nim": provider}

        framework.register_provider("nim", provider)

        framework.core_engine.add_provider.assert_not_called()


class TestValidateAndProfile(TestDiscoveryFrameworkSetup):
    @pytest.mark.asyncio
    async def test_validate_engine_delegates_to_pipeline(
        self, framework: DiscoveryFramework
    ) -> None:
        reg = _make_reg()
        framework.validation.validate_and_report.return_value = (True, [MagicMock()])

        all_pass, results = await framework.validate_engine(reg)

        assert all_pass
        framework.validation.validate_and_report.assert_called_once_with(reg, None, None)

    @pytest.mark.asyncio
    async def test_profile_engine_delegates_to_profiling(
        self, framework: DiscoveryFramework
    ) -> None:
        reg = _make_reg()
        expected_profile = MagicMock(spec=ProfileResult)
        framework.profiling.profile.return_value = expected_profile

        result = await framework.profile_engine(reg)

        assert result is expected_profile
        framework.profiling.profile.assert_called_once_with(reg)


class TestBindRuntime(TestDiscoveryFrameworkSetup):
    @pytest.mark.asyncio
    async def test_bind_runtime_sets_runtime_manager(self, framework: DiscoveryFramework) -> None:
        runtime_manager = MagicMock(spec=RuntimeManagerPort)
        framework.bind_runtime(runtime_manager)
        assert framework._runtime_manager is runtime_manager


class TestInternalHelpers(TestDiscoveryFrameworkSetup):
    def test_registration_matches_rule(self, framework: DiscoveryFramework) -> None:
        reg = _make_reg(name="my-engine", engine_type=EngineType.GENERIC)
        rule = DiscoveryRule(field="name", operator="eq", value="my-engine", action="accept")
        assert framework._registration_matches_rule(reg, rule)

    def test_apply_rules_with_no_rules(self, framework: DiscoveryFramework) -> None:
        framework.config.get_rules.return_value = []
        regs = [_make_reg(name="a"), _make_reg(name="b")]
        result = framework._apply_rules(regs)
        assert len(result) == 2

    def test_apply_rules_reject(self, framework: DiscoveryFramework) -> None:
        framework.config.get_rules.return_value = [
            DiscoveryRule(field="name", operator="eq", value="reject-me", action="reject")
        ]
        regs = [_make_reg(name="keep"), _make_reg(name="reject-me")]
        result = framework._apply_rules(regs)
        assert len(result) == 1
        assert result[0].name == "keep"

    def test_apply_rules_accept(self, framework: DiscoveryFramework) -> None:
        framework.config.get_rules.return_value = [
            DiscoveryRule(field="engine_type", operator="eq", value="generic", action="accept")
        ]
        regs = [
            _make_reg(name="a", engine_type=EngineType.GENERIC),
            _make_reg(name="b", engine_type=EngineType.DOCKER),
        ]
        result = framework._apply_rules(regs)
        assert len(result) == 1
        assert result[0].name == "a"

    def test_deduplicate_registrations(self, framework: DiscoveryFramework) -> None:
        regs = [
            _make_reg(name="a"),
            _make_reg(name="b"),
            _make_reg(name="a"),
            _make_reg(name="c"),
            _make_reg(name="b"),
        ]
        result = framework._deduplicate_registrations(regs)
        assert len(result) == 3
        assert [r.name for r in result] == ["a", "b", "c"]

    def test_deduplicate_empty(self, framework: DiscoveryFramework) -> None:
        result = framework._deduplicate_registrations([])
        assert result == []

    def test_get_effective_confidence_override(self, framework: DiscoveryFramework) -> None:
        config = DiscoveryProviderConfig(
            name="test", provider_type="path", confidence_override=0.95
        )
        provider = MagicMock(spec=DiscoveryProvider)
        confidence = framework._get_effective_confidence(config, provider)
        assert confidence == 0.95
        framework.core_engine._get_provider_confidence.assert_not_called()

    def test_get_effective_confidence_default(self, framework: DiscoveryFramework) -> None:
        config = DiscoveryProviderConfig(name="test", provider_type="path")
        provider = MagicMock(spec=DiscoveryProvider)
        framework.core_engine._get_provider_confidence.return_value = 0.8

        confidence = framework._get_effective_confidence(config, provider)

        assert confidence == 0.8
        framework.core_engine._get_provider_confidence.assert_called_once_with(
            provider.get_provider_type()
        )


class TestResolveProfile(TestDiscoveryFrameworkSetup):
    def test_resolve_profile_by_name_found(self, framework: DiscoveryFramework) -> None:
        profile = _make_default_profile()
        framework.config.get_profile.return_value = profile
        result = framework._resolve_profile("default")
        assert result is profile
        framework.config.get_profile.assert_called_once_with("default")

    def test_resolve_profile_by_name_not_found(self, framework: DiscoveryFramework) -> None:
        framework.config.get_profile.return_value = None
        result = framework._resolve_profile("nonexistent")
        assert result is None

    def test_resolve_profile_default_creates_on_the_fly(
        self, framework: DiscoveryFramework
    ) -> None:
        framework.config.get_profile.side_effect = lambda n: None  # no profiles
        framework.registry.count.return_value = 1
        framework.registry.list_providers.return_value = [
            {
                "name": "path",
                "provider_type": "path",
                "enabled": True,
                "interval_seconds": 60.0,
                "timeout_seconds": 10.0,
                "confidence_override": None,
            }
        ]

        result = framework._resolve_profile(None)

        assert result is not None
        assert result.name == "default"
        assert result.description == "Auto-generated default profile"
        framework.config.add_profile.assert_called_once()

    def test_resolve_profile_returns_none_when_no_providers(
        self, framework: DiscoveryFramework
    ) -> None:
        framework.config.get_profile.side_effect = lambda n: None
        framework.registry.count.return_value = 0

        result = framework._resolve_profile(None)

        assert result is None
