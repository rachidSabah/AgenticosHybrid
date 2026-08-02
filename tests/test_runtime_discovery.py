"""Tests for discovery engine."""

import pytest

from agentic_os.core.runtime.discovery import DiscoveryEngine, DiscoveryResult
from agentic_os.domain.execution import EngineCapability, EngineType
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


class TestDiscoveryEngine:
    @pytest.fixture
    def engine(self) -> DiscoveryEngine:
        return DiscoveryEngine()

    def test_add_provider(self, engine: DiscoveryEngine) -> None:
        provider = MockDiscoveryProvider("test", "path", [])
        engine.add_provider(provider)
        assert "test" in engine._providers

    def test_remove_provider(self, engine: DiscoveryEngine) -> None:
        provider = MockDiscoveryProvider("test", "path", [])
        engine.add_provider(provider)
        assert engine.remove_provider("test") is True
        assert engine.remove_provider("nonexistent") is False

    def test_list_providers(self, engine: DiscoveryEngine) -> None:
        provider = MockDiscoveryProvider("test", "path", [])
        engine.add_provider(provider)
        providers = engine.list_providers()
        assert len(providers) == 1
        assert providers[0]["name"] == "test"

    @pytest.mark.asyncio
    async def test_discover_all_empty(self, engine: DiscoveryEngine) -> None:
        results = await engine.discover_all()
        assert results == []

    @pytest.mark.asyncio
    async def test_discover_all(self, engine: DiscoveryEngine) -> None:
        reg = EngineRegistration(name="test", engine_type=EngineType.GENERIC)
        provider = MockDiscoveryProvider("test", "path", [reg])
        engine.add_provider(provider)
        results = await engine.discover_all()
        assert len(results) == 1
        assert results[0].registration.name == "test"
        assert results[0].provider_name == "test"

    @pytest.mark.asyncio
    async def test_discover_all_deduplicates(self, engine: DiscoveryEngine) -> None:
        reg = EngineRegistration(name="dupe", engine_type=EngineType.GENERIC)
        p1 = MockDiscoveryProvider("path", "path", [reg])
        p2 = MockDiscoveryProvider("wsl", "wsl", [reg])
        engine.add_provider(p1)
        engine.add_provider(p2)
        results = await engine.discover_all()
        # Dedup: same name, keep highest confidence (path=0.8 > wsl=0.5)
        assert len(results) == 1
        assert results[0].confidence == 0.8

    @pytest.mark.asyncio
    async def test_discover_by_type(self, engine: DiscoveryEngine) -> None:
        reg = EngineRegistration(name="test", engine_type=EngineType.GENERIC)
        p1 = MockDiscoveryProvider("path", "path", [reg])
        p2 = MockDiscoveryProvider("wsl", "wsl", [])
        engine.add_provider(p1)
        engine.add_provider(p2)
        results = await engine.discover_by_type("path")
        assert len(results) == 1
        assert results[0].provider_type == "path"

    @pytest.mark.asyncio
    async def test_discover_by_type_no_match(self, engine: DiscoveryEngine) -> None:
        reg = EngineRegistration(name="test", engine_type=EngineType.GENERIC)
        provider = MockDiscoveryProvider("path", "path", [reg])
        engine.add_provider(provider)
        results = await engine.discover_by_type("docker")
        assert results == []

    @pytest.mark.asyncio
    async def test_discover_all_handles_failure(self, engine: DiscoveryEngine) -> None:
        reg = EngineRegistration(name="good", engine_type=EngineType.GENERIC)
        good = MockDiscoveryProvider("good", "path", [reg])
        bad = FailingDiscoveryProvider()
        engine.add_provider(good)
        engine.add_provider(bad)
        results = await engine.discover_all()
        assert len(results) == 1
        assert results[0].registration.name == "good"

    def test_deduplicate(self, engine: DiscoveryEngine) -> None:
        reg = EngineRegistration(name="same", engine_type=EngineType.GENERIC)
        r1 = DiscoveryResult(
            registration=reg, provider_name="path", provider_type="path", confidence=0.8
        )
        r2 = DiscoveryResult(
            registration=reg, provider_name="wsl", provider_type="wsl", confidence=0.5
        )
        results = engine._deduplicate([r1, r2])
        assert len(results) == 1
        assert results[0].confidence == 0.8

    def test_get_provider_confidence(self, engine: DiscoveryEngine) -> None:
        assert engine._get_provider_confidence("configuration") == 1.0
        assert engine._get_provider_confidence("path") == 0.8
        assert engine._get_provider_confidence("docker") == 0.4
        assert engine._get_provider_confidence("unknown") == 0.5

    @pytest.mark.asyncio
    async def test_discover_all_merges_metadata(self, engine: DiscoveryEngine) -> None:
        reg1 = EngineRegistration(
            name="merge",
            engine_type=EngineType.GENERIC,
            capabilities=[EngineCapability.CODING],
        )
        reg2 = EngineRegistration(
            name="merge",
            engine_type=EngineType.GENERIC,
            capabilities=[EngineCapability.DOCKER],
        )
        p1 = MockDiscoveryProvider("path", "path", [reg1])
        p2 = MockDiscoveryProvider("wsl", "wsl", [reg2])
        engine.add_provider(p1)
        engine.add_provider(p2)
        results = await engine.discover_all()
        assert len(results) == 1
        # Highest confidence provider wins (path=0.8 > wsl=0.5)
        assert results[0].confidence == 0.8

    def test_discovery_result_to_dict(self) -> None:
        reg = EngineRegistration(name="test", engine_type=EngineType.GENERIC)
        result = DiscoveryResult(
            registration=reg, provider_name="p1", provider_type="path", confidence=0.9
        )
        d = result.to_dict()
        assert d["name"] == "test"
        assert d["provider_name"] == "p1"
        assert d["confidence"] == 0.9
