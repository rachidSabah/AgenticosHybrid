"""Tests for DiscoveryRegistry — provider lifecycle, config, and bulk discovery."""

import pytest

from agentic_os.core.discovery.registry import DiscoveryRegistry, DiscoveryRegistryError
from agentic_os.domain.discovery import DiscoveryProfile, DiscoveryProviderConfig
from agentic_os.domain.execution import EngineType
from agentic_os.ports.execution import EngineRegistration


class MockDiscoveryProvider:
    """A mock provider that returns predefined registrations."""

    def __init__(self, name: str, type_: str, registrations: list[EngineRegistration]) -> None:
        self._name = name
        self._type = type_
        self._registrations = registrations

    async def discover(self) -> list[EngineRegistration]:
        return self._registrations

    def get_provider_name(self) -> str:
        return self._name

    def get_provider_type(self) -> str:
        return self._type


class FailingDiscoveryProvider:
    """A mock provider that raises during discovery."""

    async def discover(self) -> list[EngineRegistration]:
        msg = "Discovery failed"
        raise RuntimeError(msg)

    def get_provider_name(self) -> str:
        return "failing"

    def get_provider_type(self) -> str:
        return "manual"


class TestDiscoveryRegistry:
    @pytest.fixture
    def registry(self) -> DiscoveryRegistry:
        return DiscoveryRegistry()

    # ── Register / Unregister ──

    def test_register_provider(self, registry: DiscoveryRegistry) -> None:
        provider = MockDiscoveryProvider("test", "path", [])
        registry.register("test", provider)
        assert registry.get_provider("test") is provider
        assert registry.count() == 1

    def test_register_provider_with_config(self, registry: DiscoveryRegistry) -> None:
        provider = MockDiscoveryProvider("test", "path", [])
        config = DiscoveryProviderConfig(name="test", provider_type="path", enabled=False)
        registry.register("test", provider, config=config)
        assert registry.get_config("test") is config
        assert registry.is_enabled("test") is False

    def test_register_duplicate_raises(self, registry: DiscoveryRegistry) -> None:
        provider = MockDiscoveryProvider("test", "path", [])
        registry.register("test", provider)
        with pytest.raises(DiscoveryRegistryError, match="already registered"):
            registry.register("test", provider)

    def test_unregister_existing(self, registry: DiscoveryRegistry) -> None:
        provider = MockDiscoveryProvider("test", "path", [])
        registry.register("test", provider)
        assert registry.unregister("test") is True
        assert registry.get_provider("test") is None
        assert registry.count() == 0

    def test_unregister_nonexistent(self, registry: DiscoveryRegistry) -> None:
        assert registry.unregister("nonexistent") is False

    def test_unregister_removes_config(self, registry: DiscoveryRegistry) -> None:
        provider = MockDiscoveryProvider("test", "path", [])
        registry.register("test", provider)
        assert registry.get_config("test") is not None
        registry.unregister("test")
        assert registry.get_config("test") is None

    # ── List providers ──

    def test_list_providers_empty(self, registry: DiscoveryRegistry) -> None:
        assert registry.list_providers() == []

    def test_list_providers_format(self, registry: DiscoveryRegistry) -> None:
        provider = MockDiscoveryProvider("test", "path", [])
        registry.register("test", provider)
        providers = registry.list_providers()
        assert len(providers) == 1
        entry = providers[0]
        assert entry["name"] == "test"
        assert entry["provider_type"] == "path"
        assert entry["enabled"] is True
        assert entry["interval_seconds"] == 60.0
        assert entry["timeout_seconds"] == 10.0
        assert entry["confidence_override"] is None

    def test_list_providers_multiple(self, registry: DiscoveryRegistry) -> None:
        p1 = MockDiscoveryProvider("a", "path", [])
        p2 = MockDiscoveryProvider("b", "wsl", [])
        registry.register("a", p1)
        registry.register("b", p2)
        assert len(registry.list_providers()) == 2

    # ── Enable / Disable ──

    def test_enable_provider(self, registry: DiscoveryRegistry) -> None:
        provider = MockDiscoveryProvider("test", "path", [])
        config = DiscoveryProviderConfig(name="test", provider_type="path", enabled=False)
        registry.register("test", provider, config=config)
        assert registry.is_enabled("test") is False
        assert registry.enable_provider("test") is True
        assert registry.is_enabled("test") is True

    def test_enable_already_enabled_returns_false(self, registry: DiscoveryRegistry) -> None:
        provider = MockDiscoveryProvider("test", "path", [])
        registry.register("test", provider)
        assert registry.is_enabled("test") is True
        assert registry.enable_provider("test") is False

    def test_enable_nonexistent_returns_false(self, registry: DiscoveryRegistry) -> None:
        assert registry.enable_provider("nonexistent") is False

    def test_disable_provider(self, registry: DiscoveryRegistry) -> None:
        provider = MockDiscoveryProvider("test", "path", [])
        registry.register("test", provider)
        assert registry.is_enabled("test") is True
        assert registry.disable_provider("test") is True
        assert registry.is_enabled("test") is False

    def test_disable_already_disabled_returns_false(self, registry: DiscoveryRegistry) -> None:
        provider = MockDiscoveryProvider("test", "path", [])
        config = DiscoveryProviderConfig(name="test", provider_type="path", enabled=False)
        registry.register("test", provider, config=config)
        assert registry.disable_provider("test") is False

    def test_disable_nonexistent_returns_false(self, registry: DiscoveryRegistry) -> None:
        assert registry.disable_provider("nonexistent") is False

    def test_is_enabled_no_config_returns_true(self, registry: DiscoveryRegistry) -> None:
        provider = MockDiscoveryProvider("test", "path", [])
        registry.register("test", provider)
        # Remove config to test fallback
        registry._configs.pop("test", None)
        assert registry.is_enabled("test") is True

    def test_is_enabled_not_registered_returns_false(self, registry: DiscoveryRegistry) -> None:
        assert registry.is_enabled("nonexistent") is False

    # ── discover_by_provider ──

    @pytest.mark.asyncio
    async def test_discover_by_provider_returns_registrations(
        self, registry: DiscoveryRegistry
    ) -> None:
        reg = EngineRegistration(name="engine1", engine_type=EngineType.GENERIC)
        provider = MockDiscoveryProvider("test", "path", [reg])
        registry.register("test", provider)
        results = await registry.discover_by_provider("test")
        assert len(results) == 1
        assert results[0].name == "engine1"

    @pytest.mark.asyncio
    async def test_discover_by_provider_disabled_returns_empty(
        self, registry: DiscoveryRegistry
    ) -> None:
        reg = EngineRegistration(name="engine1", engine_type=EngineType.GENERIC)
        provider = MockDiscoveryProvider("test", "path", [reg])
        config = DiscoveryProviderConfig(name="test", provider_type="path", enabled=False)
        registry.register("test", provider, config=config)
        results = await registry.discover_by_provider("test")
        assert results == []

    @pytest.mark.asyncio
    async def test_discover_by_provider_unknown_raises(self, registry: DiscoveryRegistry) -> None:
        with pytest.raises(DiscoveryRegistryError, match="Unknown provider"):
            await registry.discover_by_provider("nonexistent")

    # ── discover_all ──

    @pytest.mark.asyncio
    async def test_discover_all_empty(self, registry: DiscoveryRegistry) -> None:
        results = await registry.discover_all()
        assert results == {}

    @pytest.mark.asyncio
    async def test_discover_all_returns_dict(self, registry: DiscoveryRegistry) -> None:
        reg = EngineRegistration(name="engine1", engine_type=EngineType.GENERIC)
        provider = MockDiscoveryProvider("test", "path", [reg])
        registry.register("test", provider)
        results = await registry.discover_all()
        assert isinstance(results, dict)
        assert "test" in results
        assert len(results["test"]) == 1
        assert results["test"][0].name == "engine1"

    @pytest.mark.asyncio
    async def test_discover_all_skips_disabled(self, registry: DiscoveryRegistry) -> None:
        reg = EngineRegistration(name="engine1", engine_type=EngineType.GENERIC)
        provider = MockDiscoveryProvider("test", "path", [reg])
        config = DiscoveryProviderConfig(name="test", provider_type="path", enabled=False)
        registry.register("test", provider, config=config)
        results = await registry.discover_all()
        assert results == {}

    @pytest.mark.asyncio
    async def test_discover_all_handles_failure(self, registry: DiscoveryRegistry) -> None:
        reg = EngineRegistration(name="good", engine_type=EngineType.GENERIC)
        good = MockDiscoveryProvider("good", "path", [reg])
        bad = FailingDiscoveryProvider()
        registry.register("good", good)
        registry.register(
            "bad", bad, config=DiscoveryProviderConfig(name="bad", provider_type="manual")
        )
        results = await registry.discover_all()
        assert "good" in results
        assert "bad" in results
        assert len(results["good"]) == 1
        assert len(results["bad"]) == 0

    # ── count ──

    def test_count_multiple_providers(self, registry: DiscoveryRegistry) -> None:
        assert registry.count() == 0
        registry.register("a", MockDiscoveryProvider("a", "path", []))
        registry.register("b", MockDiscoveryProvider("b", "wsl", []))
        assert registry.count() == 2

    # ── get_enabled_for_profile ──

    def test_get_enabled_for_profile(self, registry: DiscoveryRegistry) -> None:
        registry.register("p1", MockDiscoveryProvider("p1", "path", []))
        registry.register("p2", MockDiscoveryProvider("p2", "wsl", []))
        profile = DiscoveryProfile(
            name="test",
            provider_configs=(DiscoveryProviderConfig(name="p1", provider_type="path"),),
        )
        enabled = registry.get_enabled_for_profile(profile)
        assert enabled == ["p1"]

    def test_get_enabled_for_profile_disabled_in_profile(self, registry: DiscoveryRegistry) -> None:
        registry.register("p1", MockDiscoveryProvider("p1", "path", []))
        profile = DiscoveryProfile(
            name="test",
            provider_configs=(
                DiscoveryProviderConfig(name="p1", provider_type="path", enabled=False),
            ),
        )
        enabled = registry.get_enabled_for_profile(profile)
        assert enabled == []

    # ── list_enabled / list_by_type ──

    def test_list_enabled(self, registry: DiscoveryRegistry) -> None:
        registry.register("p1", MockDiscoveryProvider("p1", "path", []))
        config = DiscoveryProviderConfig(name="p2", provider_type="wsl", enabled=False)
        registry.register("p2", MockDiscoveryProvider("p2", "wsl", []), config=config)
        enabled = registry.list_enabled()
        assert "p1" in enabled
        assert "p2" not in enabled

    def test_list_by_type(self, registry: DiscoveryRegistry) -> None:
        registry.register("p1", MockDiscoveryProvider("p1", "path", []))
        registry.register("p2", MockDiscoveryProvider("p2", "wsl", []))
        registry.register("p3", MockDiscoveryProvider("p3", "path", []))
        assert set(registry.list_by_type("path")) == {"p1", "p3"}
        assert registry.list_by_type("wsl") == ["p2"]
        assert registry.list_by_type("docker") == []

    # ── configure ──

    def test_configure_existing(self, registry: DiscoveryRegistry) -> None:
        registry.register("test", MockDiscoveryProvider("test", "path", []))
        new_config = DiscoveryProviderConfig(name="test", provider_type="path", enabled=False)
        assert registry.configure("test", new_config) is True
        assert registry.get_config("test") is new_config

    def test_configure_nonexistent(self, registry: DiscoveryRegistry) -> None:
        config = DiscoveryProviderConfig(name="test", provider_type="path")
        assert registry.configure("test", config) is False
