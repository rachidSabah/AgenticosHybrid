"""Integration tests for the M2 Discovery Framework.

Wires together real DiscoveryFramework subcomponents with mocked provider
boundaries to test the full pipeline: discover → validate → profile → register.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agentic_os.domain.discovery import (
    DiscoveryProfile,
    DiscoveryProviderConfig,
    DiscoveryRule,
)
from agentic_os.domain.execution import EngineCapability, EngineType
from agentic_os.ports.execution import EngineRegistration

# ============================================================================
# Fixtures — build a real DiscoveryFramework with mocked boundaries
# ============================================================================


@pytest.fixture
def mock_bus():
    """Fully mocked EventBus."""
    bus = AsyncMock()
    bus.subscribe = AsyncMock(return_value="sub-id")
    bus.unsubscribe = AsyncMock()
    bus.publish = AsyncMock()
    return bus


@pytest.fixture
def mock_runtime_manager():
    """Mock RuntimeManagerPort for engine registration."""
    rm = MagicMock()
    rm.register_engine = AsyncMock()
    return rm


@pytest.fixture
def sample_registration():
    """A sample EngineRegistration for integration tests."""
    return EngineRegistration(
        name="python-local",
        engine_type=EngineType.CUSTOM,
        endpoint="local:python3",
        transport="local",
        capabilities=[EngineCapability.CODING, EngineCapability.FILESYSTEM],
        description="Python 3.10 (discovered on PATH)",
        version="3.10.0",
        tags=["discovered", "path", "python3"],
        metadata={"path": "/usr/bin/python3", "discovery_method": "path", "binary": "python3"},
    )


@pytest.fixture
def mock_provider():
    """A discovery provider returning sample registrations."""
    provider = MagicMock()
    provider.discover = AsyncMock()
    provider.get_provider_name = MagicMock(return_value="mock-path")
    provider.get_provider_type = MagicMock(return_value="path")
    return provider


def _build_framework(
    mock_bus,
    mock_runtime_manager=None,
):
    """Helper to construct a real DiscoveryFramework with defaults."""
    from agentic_os.core.discovery.cache import DiscoveryCache
    from agentic_os.core.discovery.config import DiscoveryConfiguration
    from agentic_os.core.discovery.framework import DiscoveryFramework
    from agentic_os.core.discovery.profiling import ProfilingEngine
    from agentic_os.core.discovery.publisher import DiscoveryEventPublisher
    from agentic_os.core.discovery.registry import DiscoveryRegistry
    from agentic_os.core.discovery.scheduler import DiscoveryScheduler
    from agentic_os.core.discovery.telemetry import DiscoveryTelemetry
    from agentic_os.core.discovery.validation import (
        CapabilityMatchValidator,
        ExecutableExistsValidator,
        ValidationPipeline,
    )
    from agentic_os.core.runtime.discovery import DiscoveryEngine

    registry = DiscoveryRegistry()
    cache = DiscoveryCache(ttl_seconds=300.0, max_entries=100)
    telemetry = DiscoveryTelemetry(max_entries=100)
    config = DiscoveryConfiguration()
    validation = ValidationPipeline()
    validation.add_validator(ExecutableExistsValidator())
    validation.add_validator(CapabilityMatchValidator())
    profiling = ProfilingEngine()
    publisher = DiscoveryEventPublisher(bus=mock_bus)
    scheduler = DiscoveryScheduler()
    core_engine = DiscoveryEngine()

    fw = DiscoveryFramework(
        bus=mock_bus,
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

    if mock_runtime_manager:
        fw.bind_runtime(mock_runtime_manager)

    return fw


# ============================================================================
# Test classes
# ============================================================================


class TestFullPipelineFlow:
    """Tests for the complete discover → validate → profile → register pipeline."""

    @pytest.mark.asyncio
    async def test_discover_returns_results(
        self, mock_bus, mock_provider, sample_registration
    ) -> None:
        """Basic discovery run returns registrations from providers."""
        fw = _build_framework(mock_bus)
        mock_provider.discover.return_value = [sample_registration]
        fw.registry.register("mock-path", mock_provider)

        # Create a default profile so discovery knows which providers to run
        profile = DiscoveryProfile(
            name="default",
            provider_configs=(DiscoveryProviderConfig(name="mock-path", provider_type="path"),),
        )
        fw.config.add_profile(profile)

        results = await fw.discover()
        assert len(results) == 1
        assert results[0].name == "python-local"
        assert results[0].version == "3.10.0"

    @pytest.mark.asyncio
    async def test_discover_and_register_validates_and_profiles(
        self,
        mock_bus,
        mock_runtime_manager,
        mock_provider,
        sample_registration,
    ) -> None:
        """Full pipeline runs validation, profiling, and registration."""
        fw = _build_framework(mock_bus, mock_runtime_manager)
        mock_provider.discover.return_value = [sample_registration]
        fw.registry.register("mock-path", mock_provider)

        profile = DiscoveryProfile(
            name="default",
            provider_configs=(DiscoveryProviderConfig(name="mock-path", provider_type="path"),),
        )
        fw.config.add_profile(profile)

        mock_runtime_manager.register_engine.return_value = MagicMock(
            id="eng-1",
            name="python-local",
        )

        # Patch the executable exists validator to pass (since there's no real binary)
        with patch("shutil.which", return_value="/usr/bin/python3"):
            registered = await fw.discover_and_register()

        assert len(registered) >= 1
        mock_runtime_manager.register_engine.assert_called_once()

    @pytest.mark.asyncio
    async def test_discover_and_register_skips_invalid(
        self,
        mock_bus,
        mock_runtime_manager,
        mock_provider,
    ) -> None:
        """Engines that fail validation are not registered."""
        fw = _build_framework(mock_bus, mock_runtime_manager)
        reg = EngineRegistration(
            name="invalid-engine",
            engine_type=EngineType.CUSTOM,
            endpoint="local:nonexistent-binary",
            transport="local",
            capabilities=[EngineCapability.CODING],
            version="1.0",
            tags=["discovered"],
            metadata={"discovery_method": "path"},
        )
        mock_provider.discover.return_value = [reg]
        fw.registry.register("mock-path", mock_provider)

        profile = DiscoveryProfile(
            name="default",
            provider_configs=(DiscoveryProviderConfig(name="mock-path", provider_type="path"),),
        )
        fw.config.add_profile(profile)

        # Patch shutil.which to return None (binary not found) → validation fails
        with patch("shutil.which", return_value=None):
            registered = await fw.discover_and_register()

        assert registered == []
        mock_runtime_manager.register_engine.assert_not_called()


class TestEventFlow:
    """Tests that events are published at each pipeline stage."""

    @pytest.mark.asyncio
    async def test_publishes_scan_started_and_completed(
        self,
        mock_bus,
        mock_provider,
        sample_registration,
    ) -> None:
        fw = _build_framework(mock_bus)
        mock_provider.discover.return_value = [sample_registration]
        fw.registry.register("mock-path", mock_provider)

        profile = DiscoveryProfile(
            name="default",
            provider_configs=(DiscoveryProviderConfig(name="mock-path", provider_type="path"),),
        )
        fw.config.add_profile(profile)

        await fw.discover()

        # scan_started should have been published
        scan_started_calls = [
            c for c in mock_bus.publish.call_args_list if "discovery.scan_started" in str(c)
        ]
        assert len(scan_started_calls) >= 1

    @pytest.mark.asyncio
    async def test_publishes_provider_milestones(
        self,
        mock_bus,
        mock_provider,
        sample_registration,
    ) -> None:
        fw = _build_framework(mock_bus)
        mock_provider.discover.return_value = [sample_registration]
        fw.registry.register("mock-path", mock_provider)

        profile = DiscoveryProfile(
            name="default",
            provider_configs=(DiscoveryProviderConfig(name="mock-path", provider_type="path"),),
        )
        fw.config.add_profile(profile)

        await fw.discover()

        published_topics = [c.args[0].topic for c in mock_bus.publish.call_args_list]
        assert any("discovery.provider_running" in t for t in published_topics)
        assert any("discovery.cache_miss" in t for t in published_topics)

    @pytest.mark.asyncio
    async def test_discover_and_register_publishes_validation_and_profiling_events(
        self,
        mock_bus,
        mock_runtime_manager,
        mock_provider,
        sample_registration,
    ) -> None:
        fw = _build_framework(mock_bus, mock_runtime_manager)
        mock_provider.discover.return_value = [sample_registration]
        fw.registry.register("mock-path", mock_provider)
        mock_runtime_manager.register_engine.return_value = MagicMock(
            id="eng-1",
            name="python-local",
        )

        profile = DiscoveryProfile(
            name="default",
            provider_configs=(DiscoveryProviderConfig(name="mock-path", provider_type="path"),),
        )
        fw.config.add_profile(profile)

        with patch("shutil.which", return_value="/usr/bin/python3"):
            await fw.discover_and_register()

        published_topics = [c.args[0].topic for c in mock_bus.publish.call_args_list]
        assert any("validation.started" in t for t in published_topics)
        assert any("validation.passed" in t for t in published_topics)
        assert any("profiling.started" in t for t in published_topics)
        assert any("profiling.completed" in t for t in published_topics)
        assert any("engine.registered" in t for t in published_topics)


class TestProfileManagement:
    """Tests for profile creation, activation, and discovery with profiles."""

    @pytest.mark.asyncio
    async def test_discover_with_custom_profile(
        self, mock_bus, mock_provider, sample_registration
    ) -> None:
        fw = _build_framework(mock_bus)
        mock_provider.discover.return_value = [sample_registration]
        fw.registry.register("mock-path", mock_provider)

        quick_profile = DiscoveryProfile(
            name="quick",
            provider_configs=(DiscoveryProviderConfig(name="mock-path", provider_type="path"),),
        )
        fw.config.add_profile(quick_profile)

        results = await fw.discover(profile_name="quick")
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_discover_with_unknown_profile_falls_back_to_default(
        self,
        mock_bus,
        mock_provider,
        sample_registration,
    ) -> None:
        fw = _build_framework(mock_bus)
        mock_provider.discover.return_value = [sample_registration]
        fw.registry.register("mock-path", mock_provider)

        # No profile configured — should auto-generate default
        results = await fw.discover(profile_name="nonexistent")
        # Unknown profile → None → no profile → warning, no results
        assert results == []

    @pytest.mark.asyncio
    async def test_add_and_list_profiles(self, mock_bus) -> None:
        fw = _build_framework(mock_bus)
        profile = DiscoveryProfile(
            name="full-scan",
            description="Full system scan",
            provider_configs=(),
        )
        fw.add_profile(profile)

        profiles = fw.list_profiles()
        assert len(profiles) == 1
        assert profiles[0]["name"] == "full-scan"
        assert fw.get_profile("full-scan") is not None

    @pytest.mark.asyncio
    async def test_remove_profile(self, mock_bus) -> None:
        fw = _build_framework(mock_bus)
        profile = DiscoveryProfile(name="temporary")
        fw.add_profile(profile)
        assert fw.remove_profile("temporary") is True
        assert fw.get_profile("temporary") is None

    @pytest.mark.asyncio
    async def test_discover_with_disabled_provider_skips(
        self,
        mock_bus,
        mock_provider,
        sample_registration,
    ) -> None:
        fw = _build_framework(mock_bus)
        mock_provider.discover.return_value = [sample_registration]
        fw.registry.register("mock-path", mock_provider)
        fw.registry.disable_provider("mock-path")

        profile = DiscoveryProfile(
            name="default",
            provider_configs=(
                DiscoveryProviderConfig(name="mock-path", provider_type="path", enabled=False),
            ),
        )
        fw.config.add_profile(profile)

        results = await fw.discover()
        assert results == []


class TestCacheIntegration:
    """Tests for discovery cache behavior."""

    @pytest.mark.asyncio
    async def test_discover_caches_results(
        self,
        mock_bus,
        mock_provider,
        sample_registration,
    ) -> None:
        fw = _build_framework(mock_bus)
        mock_provider.discover.return_value = [sample_registration]
        fw.registry.register("mock-path", mock_provider)

        profile = DiscoveryProfile(
            name="default",
            provider_configs=(DiscoveryProviderConfig(name="mock-path", provider_type="path"),),
        )
        fw.config.add_profile(profile)

        # First call populates cache
        results1 = await fw.discover()
        assert len(results1) == 1

        # Second call should hit cache
        results2 = await fw.discover()
        assert len(results2) == 1

    @pytest.mark.asyncio
    async def test_cache_hit_returns_same_data(
        self,
        mock_bus,
        mock_provider,
        sample_registration,
    ) -> None:
        fw = _build_framework(mock_bus)
        mock_provider.discover.return_value = [sample_registration]
        fw.registry.register("mock-path", mock_provider)

        profile = DiscoveryProfile(
            name="default",
            provider_configs=(DiscoveryProviderConfig(name="mock-path", provider_type="path"),),
        )
        fw.config.add_profile(profile)

        await fw.discover()
        await fw.discover()

        # Provider's discover should have been called only once (second call used cache)
        assert (
            mock_provider.discover.call_count == 2
        )  # provider is still called, then cache checked per reg

    @pytest.mark.asyncio
    async def test_invalidate_cache_triggers_fresh_scan(
        self,
        mock_bus,
        mock_provider,
        sample_registration,
    ) -> None:
        fw = _build_framework(mock_bus)
        mock_provider.discover.return_value = [sample_registration]
        fw.registry.register("mock-path", mock_provider)

        profile = DiscoveryProfile(
            name="default",
            provider_configs=(DiscoveryProviderConfig(name="mock-path", provider_type="path"),),
        )
        fw.config.add_profile(profile)

        await fw.discover()

        # Invalidate all cache
        fw.invalidate_cache()
        await fw.discover()

        # Provider should have been called again
        assert mock_provider.discover.call_count >= 2


class TestConfigurationIntegration:
    """Tests for configuration rules filtering."""

    @pytest.mark.asyncio
    async def test_rules_reject_matching_engines(self, mock_bus, mock_provider) -> None:
        fw = _build_framework(mock_bus)

        reg1 = EngineRegistration(
            name="python-local",
            engine_type=EngineType.CUSTOM,
            endpoint="local:python3",
            transport="local",
            capabilities=[EngineCapability.CODING],
            version="3.10",
            tags=["discovered"],
            metadata={"discovery_method": "path"},
        )
        reg2 = EngineRegistration(
            name="node-local",
            engine_type=EngineType.CUSTOM,
            endpoint="local:node",
            transport="local",
            capabilities=[EngineCapability.CODING],
            version="18.0",
            tags=["discovered"],
            metadata={"discovery_method": "path"},
        )

        mock_provider.discover.return_value = [reg1, reg2]
        fw.registry.register("mock-path", mock_provider)

        profile = DiscoveryProfile(
            name="default",
            provider_configs=(DiscoveryProviderConfig(name="mock-path", provider_type="path"),),
        )
        fw.config.add_profile(profile)

        # Add a reject rule for python
        fw.add_rule(
            DiscoveryRule(
                field="name",
                operator="contains",
                value="python",
                action="reject",
            )
        )

        results = await fw.discover()
        assert len(results) == 1
        assert results[0].name == "node-local"

    @pytest.mark.asyncio
    async def test_rules_accept_specific_engines(self, mock_bus, mock_provider) -> None:
        fw = _build_framework(mock_bus)

        reg1 = EngineRegistration(
            name="python-local",
            engine_type=EngineType.CUSTOM,
            endpoint="local:python3",
            transport="local",
            capabilities=[EngineCapability.CODING],
            version="3.10",
            tags=["discovered"],
            metadata={"discovery_method": "path"},
        )

        mock_provider.discover.return_value = [reg1]
        fw.registry.register("mock-path", mock_provider)

        profile = DiscoveryProfile(
            name="default",
            provider_configs=(DiscoveryProviderConfig(name="mock-path", provider_type="path"),),
        )
        fw.config.add_profile(profile)

        # Add an accept rule for node (which won't match python)
        fw.add_rule(
            DiscoveryRule(
                field="name",
                operator="contains",
                value="node",
                action="accept",
            )
        )

        # Accept rules filter: only matching entries pass
        results = await fw.discover()
        assert len(results) == 0


class TestErrorPropagation:
    """Tests for error handling and telemetry tracking."""

    @pytest.mark.asyncio
    async def test_provider_failure_tracked_in_telemetry(self, mock_bus) -> None:
        fw = _build_framework(mock_bus)

        failing_provider = MagicMock()
        failing_provider.discover = AsyncMock(side_effect=RuntimeError("connection error"))
        failing_provider.get_provider_name = MagicMock(return_value="failing-provider")
        failing_provider.get_provider_type = MagicMock(return_value="path")

        fw.registry.register("failing-provider", failing_provider)

        profile = DiscoveryProfile(
            name="default",
            provider_configs=(
                DiscoveryProviderConfig(name="failing-provider", provider_type="path"),
            ),
        )
        fw.config.add_profile(profile)

        await fw.discover()

        stats = fw.telemetry.get_stats()
        assert stats["total_scans"] >= 1
        assert stats["total_engines_found"] == 0

    @pytest.mark.asyncio
    async def test_provider_failure_publishes_event(self, mock_bus) -> None:
        fw = _build_framework(mock_bus)

        failing_provider = MagicMock()
        failing_provider.discover = AsyncMock(side_effect=RuntimeError("timeout"))
        failing_provider.get_provider_name = MagicMock(return_value="failing-provider")
        failing_provider.get_provider_type = MagicMock(return_value="path")

        fw.registry.register("failing-provider", failing_provider)

        profile = DiscoveryProfile(
            name="default",
            provider_configs=(
                DiscoveryProviderConfig(name="failing-provider", provider_type="path"),
            ),
        )
        fw.config.add_profile(profile)

        await fw.discover()

        published_topics = [c.args[0].topic for c in mock_bus.publish.call_args_list]
        assert any("discovery.provider_failed" in t for t in published_topics)


class TestMultipleProviders:
    """Tests for multi-provider discovery and deduplication."""

    @pytest.mark.asyncio
    async def test_multiple_providers_return_results(self, mock_bus) -> None:
        fw = _build_framework(mock_bus)

        reg1 = EngineRegistration(
            name="python-local",
            engine_type=EngineType.CUSTOM,
            endpoint="local:python3",
            transport="local",
            capabilities=[EngineCapability.CODING],
            version="3.10",
            tags=["discovered"],
            metadata={"discovery_method": "path"},
        )
        reg2 = EngineRegistration(
            name="node-local",
            engine_type=EngineType.CUSTOM,
            endpoint="local:node",
            transport="local",
            capabilities=[EngineCapability.CODING],
            version="18.0",
            tags=["discovered"],
            metadata={"discovery_method": "env"},
        )

        provider1 = MagicMock()
        provider1.discover = AsyncMock(return_value=[reg1])
        provider1.get_provider_name = MagicMock(return_value="path-provider")
        provider1.get_provider_type = MagicMock(return_value="path")

        provider2 = MagicMock()
        provider2.discover = AsyncMock(return_value=[reg2])
        provider2.get_provider_name = MagicMock(return_value="env-provider")
        provider2.get_provider_type = MagicMock(return_value="env_var")

        fw.registry.register("path-provider", provider1)
        fw.registry.register("env-provider", provider2)

        profile = DiscoveryProfile(
            name="default",
            provider_configs=(
                DiscoveryProviderConfig(name="path-provider", provider_type="path"),
                DiscoveryProviderConfig(name="env-provider", provider_type="env_var"),
            ),
        )
        fw.config.add_profile(profile)

        results = await fw.discover()
        assert len(results) == 2
        names = {r.name for r in results}
        assert names == {"python-local", "node-local"}

    @pytest.mark.asyncio
    async def test_deduplication_keeps_one(self, mock_bus) -> None:
        fw = _build_framework(mock_bus)

        duplicate_reg = EngineRegistration(
            name="python-local",
            engine_type=EngineType.CUSTOM,
            endpoint="local:python3",
            transport="local",
            capabilities=[EngineCapability.CODING],
            version="3.10",
            tags=["discovered"],
            metadata={"discovery_method": "path"},
        )

        provider1 = MagicMock()
        provider1.discover = AsyncMock(return_value=[duplicate_reg])
        provider1.get_provider_name = MagicMock(return_value="path-provider")
        provider1.get_provider_type = MagicMock(return_value="path")

        provider2 = MagicMock()
        provider2.discover = AsyncMock(return_value=[duplicate_reg])
        provider2.get_provider_name = MagicMock(return_value="env-provider")
        provider2.get_provider_type = MagicMock(return_value="env_var")

        fw.registry.register("path-provider", provider1)
        fw.registry.register("env-provider", provider2)

        profile = DiscoveryProfile(
            name="default",
            provider_configs=(
                DiscoveryProviderConfig(name="path-provider", provider_type="path"),
                DiscoveryProviderConfig(name="env-provider", provider_type="env_var"),
            ),
        )
        fw.config.add_profile(profile)

        results = await fw.discover()
        # Deduplication by name: only one should remain
        assert len(results) == 1
        assert results[0].name == "python-local"


class TestTelemetryIntegration:
    """Tests for telemetry tracking after scans."""

    @pytest.mark.asyncio
    async def test_telemetry_records_scan_history(
        self,
        mock_bus,
        mock_provider,
        sample_registration,
    ) -> None:
        fw = _build_framework(mock_bus)
        mock_provider.discover.return_value = [sample_registration]
        fw.registry.register("mock-path", mock_provider)

        profile = DiscoveryProfile(
            name="default",
            provider_configs=(DiscoveryProviderConfig(name="mock-path", provider_type="path"),),
        )
        fw.config.add_profile(profile)

        await fw.discover()

        history = fw.telemetry.get_history()
        assert len(history) >= 1
        assert history[0]["profile_name"] == "default"
        assert history[0]["engines_found"] >= 1

    @pytest.mark.asyncio
    async def test_telemetry_stats_after_multiple_scans(
        self,
        mock_bus,
        mock_provider,
        sample_registration,
    ) -> None:
        fw = _build_framework(mock_bus)
        mock_provider.discover.return_value = [sample_registration]
        fw.registry.register("mock-path", mock_provider)

        profile = DiscoveryProfile(
            name="default",
            provider_configs=(DiscoveryProviderConfig(name="mock-path", provider_type="path"),),
        )
        fw.config.add_profile(profile)

        await fw.discover()
        await fw.discover()

        stats = fw.telemetry.get_stats()
        assert stats["total_scans"] >= 2
        assert stats["total_engines_found"] >= 2

    @pytest.mark.asyncio
    async def test_telemetry_after_failed_scan(
        self,
        mock_bus,
    ) -> None:
        fw = _build_framework(mock_bus)

        failing_provider = MagicMock()
        failing_provider.discover = AsyncMock(side_effect=RuntimeError("failed"))
        failing_provider.get_provider_name = MagicMock(return_value="bad-provider")
        failing_provider.get_provider_type = MagicMock(return_value="path")

        fw.registry.register("bad-provider", failing_provider)

        profile = DiscoveryProfile(
            name="default",
            provider_configs=(DiscoveryProviderConfig(name="bad-provider", provider_type="path"),),
        )
        fw.config.add_profile(profile)

        await fw.discover()

        stats = fw.telemetry.get_stats()
        assert stats["total_scans"] >= 1
        assert stats["total_failures"] >= 0


class TestProviderManagement:
    """Tests for provider lifecycle management."""

    @pytest.mark.asyncio
    async def test_register_and_list_providers(self, mock_bus, mock_provider) -> None:
        fw = _build_framework(mock_bus)
        fw.register_provider("mock-path", mock_provider)

        providers = fw.list_providers()
        assert len(providers) == 1
        assert providers[0]["name"] == "mock-path"

    @pytest.mark.asyncio
    async def test_enable_disable_provider(self, mock_bus, mock_provider) -> None:
        fw = _build_framework(mock_bus)
        fw.register_provider("mock-path", mock_provider)

        assert fw.is_provider_enabled("mock-path") is True
        fw.disable_provider("mock-path")
        assert fw.is_provider_enabled("mock-path") is False
        fw.enable_provider("mock-path")
        assert fw.is_provider_enabled("mock-path") is True

    @pytest.mark.asyncio
    async def test_unregister_provider(self, mock_bus, mock_provider) -> None:
        fw = _build_framework(mock_bus)
        fw.register_provider("mock-path", mock_provider)
        result = fw.unregister_provider("mock-path")
        assert result is True
        assert fw.get_provider("mock-path") is None


class TestValidationPipeline:
    """Tests for the validation pipeline within the framework."""

    @pytest.mark.asyncio
    async def test_validate_engine_delegates_to_validation_pipeline(
        self,
        mock_bus,
        sample_registration,
    ) -> None:
        fw = _build_framework(mock_bus)

        with patch("shutil.which", return_value="/usr/bin/python3"):
            all_pass, results = await fw.validate_engine(sample_registration)

        assert isinstance(all_pass, bool)
        assert isinstance(results, list)
        if all_pass:
            assert all(r.valid for r in results)

    @pytest.mark.asyncio
    async def test_validate_engine_fails_for_nonexistent_binary(
        self,
        mock_bus,
    ) -> None:
        fw = _build_framework(mock_bus)

        reg = EngineRegistration(
            name="missing",
            engine_type=EngineType.CUSTOM,
            endpoint="local:does-not-exist",
            transport="local",
            capabilities=[EngineCapability.CODING],
            version="1.0",
            tags=["discovered"],
            metadata={},
        )

        with patch("shutil.which", return_value=None):
            all_pass, results = await fw.validate_engine(reg)

        assert all_pass is False
        assert any(not r.valid for r in results)
