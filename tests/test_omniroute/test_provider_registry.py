"""Tests for OmniRoute Provider Registry (Phase 5.1)."""

from __future__ import annotations

import pytest

from agentic_os.core.omniroute.provider_registry import ProviderRegistryImpl
from agentic_os.domain.omniroute import OmniRouteProvider, ProviderDiscoveryStatus


@pytest.fixture
async def registry():
    impl = ProviderRegistryImpl()
    await impl.start()
    yield impl
    await impl.stop()


@pytest.fixture
def sample_provider():
    return OmniRouteProvider(
        name="test-openai",
        kind="openai",
        base_url="https://api.openai.com/v1",
        api_key_ref="vault://openai/api_key",
        capabilities=("chat", "completion", "embedding"),
        models=("gpt-4o", "gpt-4o-mini"),
        latency_ms=350.0,
        cost_per_1k_input=0.01,
        cost_per_1k_output=0.03,
        context_window=128000,
        supports_streaming=True,
        supports_reasoning=False,
        supports_vision=True,
        supports_tools=True,
        rate_limit=10000,
        version="1.0.0",
        priority=10,
    )


class TestProviderRegistryCRUD:
    """CRUD operations for providers."""

    async def test_register_and_get(self, registry, sample_provider):
        pid = await registry.register(sample_provider)
        assert pid is not None and len(pid) > 0

        retrieved = await registry.get(pid)
        assert retrieved is not None
        assert retrieved.name == "test-openai"
        assert retrieved.kind == "openai"
        assert retrieved.status == ProviderDiscoveryStatus.REGISTERED
        assert retrieved.healthy is False  # Not yet health-checked

    async def test_register_duplicate(self, registry, sample_provider):
        pid = await registry.register(sample_provider)
        pid2 = await registry.register(sample_provider)
        # Should return the same id and not raise
        assert pid == pid2

    async def test_get_by_name(self, registry, sample_provider):
        await registry.register(sample_provider)
        found = await registry.get_by_name("test-openai")
        assert found is not None
        assert found.kind == "openai"

    async def test_get_by_name_not_found(self, registry):
        assert await registry.get_by_name("nonexistent") is None

    async def test_update(self, registry, sample_provider):
        pid = await registry.register(sample_provider)
        updated = OmniRouteProvider(
            id=pid,
            name="test-openai",
            latency_ms=200.0,
            cost_per_1k_input=0.005,
        )
        result = await registry.update(updated)
        assert result is not None
        assert result.latency_ms == 200.0
        assert result.cost_per_1k_input == 0.005
        assert result.name == "test-openai"  # Preserved

    async def test_update_not_found(self, registry):
        result = await registry.update(OmniRouteProvider(id="nonexistent"))
        assert result is None

    async def test_delete(self, registry, sample_provider):
        pid = await registry.register(sample_provider)
        deleted = await registry.delete(pid)
        assert deleted is True
        assert await registry.get(pid) is None

    async def test_delete_not_found(self, registry):
        assert await registry.delete("nonexistent") is False

    async def test_count(self, registry, sample_provider):
        assert await registry.count() == 0
        await registry.register(sample_provider)
        assert await registry.count() == 1

    async def test_list_all(self, registry, sample_provider):
        await registry.register(sample_provider)
        await registry.register(
            OmniRouteProvider(
                name="test-anthropic", kind="anthropic", base_url="https://api.anthropic.com"
            )
        )
        all_providers = await registry.list_providers()
        assert len(all_providers) == 2

    async def test_list_filter_kind(self, registry, sample_provider):
        await registry.register(sample_provider)
        await registry.register(
            OmniRouteProvider(name="test-local", kind="ollama", base_url="http://localhost:11434")
        )
        openai_providers = await registry.list_providers(kind="openai")
        assert len(openai_providers) == 1
        assert openai_providers[0].kind == "openai"

    async def test_list_filter_capability(self, registry, sample_provider):
        await registry.register(sample_provider)
        chat_providers = await registry.list_providers(capability="chat")
        assert len(chat_providers) == 1
        embedding_providers = await registry.list_providers(capability="embedding")
        assert len(embedding_providers) == 1
        vision_providers = await registry.list_providers(capability="vision")
        assert len(vision_providers) == 0  # Not in capabilities

    async def test_list_enabled_only(self, registry, sample_provider):
        await registry.register(sample_provider)
        await registry.register(
            OmniRouteProvider(
                name="disabled-provider", kind="test", base_url="http://test", enabled=False
            )
        )
        enabled = await registry.list_providers(enabled_only=True)
        assert len(enabled) == 1
        assert enabled[0].enabled is True

    async def test_list_healthy_only(self, registry, sample_provider):
        pid = await registry.register(sample_provider)
        await registry.set_health(pid, True)
        await registry.register(
            OmniRouteProvider(name="unhealthy-provider", kind="test", base_url="http://test")
        )
        healthy = await registry.list_providers(healthy_only=True)
        assert len(healthy) == 1
        assert healthy[0].healthy is True


class TestProviderRegistryHealth:
    """Health tracking for providers."""

    async def test_set_healthy(self, registry, sample_provider):
        pid = await registry.register(sample_provider)
        result = await registry.set_health(pid, True)
        assert result is True
        assert await registry.is_healthy(pid) is True

    async def test_set_unhealthy(self, registry, sample_provider):
        pid = await registry.register(sample_provider)
        await registry.set_health(pid, True)
        await registry.set_health(pid, False, error="timeout")
        assert await registry.is_healthy(pid) is False
        provider = await registry.get(pid)
        assert provider is not None
        assert provider.error_message == "timeout"
        assert provider.status == ProviderDiscoveryStatus.FAILED

    async def test_set_health_not_found(self, registry):
        assert await registry.set_health("nonexistent", True) is False

    async def test_is_healthy_not_found(self, registry):
        assert await registry.is_healthy("nonexistent") is False

    async def test_list_unhealthy(self, registry, sample_provider):
        pid1 = await registry.register(sample_provider)
        await registry.register(
            OmniRouteProvider(name="healthy-one", kind="test", base_url="http://test")
        )
        await registry.set_health(pid1, True)
        # pid2 starts unhealthy (default)
        unhealthy = await registry.list_unhealthy()
        assert len(unhealthy) == 1
        assert unhealthy[0].name == "healthy-one"


class TestProviderRegistryCapabilities:
    """Capability-based queries."""

    async def test_providers_for_capability(self, registry, sample_provider):
        pid = await registry.register(sample_provider)
        await registry.set_health(pid, True)
        providers = await registry.providers_for_capability("chat")
        assert len(providers) == 1

    async def test_providers_for_capability_case_insensitive(self, registry, sample_provider):
        await registry.register(sample_provider)
        providers = await registry.providers_for_capability("CHAT")
        assert len(providers) == 1

    async def test_providers_for_capability_only_enabled(self, registry, sample_provider):
        await registry.register(sample_provider)
        await registry.register(
            OmniRouteProvider(
                name="disabled",
                kind="test",
                base_url="http://test",
                enabled=False,
                capabilities=("chat",),
            )
        )
        providers = await registry.providers_for_capability("chat")
        assert len(providers) == 1  # Only enabled

    async def test_set_capabilities(self, registry, sample_provider):
        pid = await registry.register(sample_provider)
        result = await registry.set_capabilities(pid, ["vision", "image_generation"])
        assert result is True
        provider = await registry.get(pid)
        assert provider is not None
        assert "vision" in provider.capabilities
        assert "image_generation" in provider.capabilities
        assert "chat" not in provider.capabilities

    async def test_set_capabilities_not_found(self, registry):
        assert await registry.set_capabilities("nonexistent", ["chat"]) is False


class TestProviderRegistryCostAndRate:
    """Cost metadata and rate limit tracking."""

    async def test_set_cost_metadata(self, registry, sample_provider):
        pid = await registry.register(sample_provider)
        result = await registry.set_cost_metadata(
            pid, cost_per_1k_input=0.02, cost_per_1k_output=0.06
        )
        assert result is True
        provider = await registry.get(pid)
        assert provider is not None
        assert provider.cost_per_1k_input == 0.02
        assert provider.cost_per_1k_output == 0.06

    async def test_set_cost_not_found(self, registry):
        assert await registry.set_cost_metadata("nonexistent", cost_per_1k_input=0.01) is False

    async def test_set_rate_limit(self, registry, sample_provider):
        pid = await registry.register(sample_provider)
        result = await registry.set_rate_limit(pid, 5000)
        assert result is True
        assert await registry.rate_limit_remaining(pid) == 5000

    async def test_consume_rate(self, registry, sample_provider):
        pid = await registry.register(sample_provider)
        await registry.set_rate_limit(pid, 5)
        for _ in range(5):
            assert await registry.consume_rate(pid) is True
        assert await registry.consume_rate(pid) is False  # Exceeded

    async def test_consume_rate_no_limit(self, registry):
        pid = await registry.register(
            OmniRouteProvider(name="no-limit-provider", kind="test", base_url="http://test")
        )
        # No rate limit configured
        assert await registry.consume_rate(pid) is True
        assert await registry.rate_limit_remaining(pid) == -1

    async def test_rate_limit_remaining(self, registry, sample_provider):
        pid = await registry.register(sample_provider)
        await registry.set_rate_limit(pid, 100)
        await registry.consume_rate(pid, 3)
        remaining = await registry.rate_limit_remaining(pid)
        assert remaining <= 97  # Window-based, so approximate


class TestProviderRegistryLifecycle:
    """Lifecycle and health check."""

    async def test_start_stop(self):
        impl = ProviderRegistryImpl()
        assert (await impl.health_check())["status"] == "stopped"
        await impl.start()
        assert (await impl.health_check())["status"] == "healthy"
        assert (await impl.health_check())["provider_count"] == 0
        await impl.stop()
        assert (await impl.health_check())["status"] == "stopped"

    async def test_discovery_sync(self, registry):
        discovered = [
            {
                "name": "discovered-openai",
                "kind": "openai",
                "base_url": "https://openai.com",
                "capabilities": ["chat"],
            },
            {
                "name": "discovered-ollama",
                "kind": "ollama",
                "base_url": "http://localhost:11434",
                "capabilities": ["chat"],
            },
        ]
        registered, updated = await registry.sync_from_discovery(discovered)
        assert registered == 2
        assert updated == 0
        assert await registry.count() == 2

        # Re-sync should update, not re-register
        discovered[0]["latency_ms"] = 150.0
        registered, updated = await registry.sync_from_discovery(discovered)
        assert registered == 0
        assert updated == 2

    async def test_event_bus_publishing(self):
        """Verify events are published to EventBus."""

        published_events = []

        class FakeBus:
            async def publish(self, event):
                published_events.append(event)

            async def start(self):
                pass

            async def stop(self):
                pass

            async def subscribe(self, topic, handler):
                return ""

            async def unsubscribe(self, sid):
                pass

        bus = FakeBus()
        impl = ProviderRegistryImpl(event_bus=bus)
        await impl.start()

        pid = await impl.register(
            OmniRouteProvider(name="test", kind="test", base_url="http://test")
        )
        await impl.set_health(pid, True)
        await impl.set_health(pid, False, error="timeout")
        await impl.delete(pid)

        topics = [e.topic for e in published_events]
        assert "provider.registered" in topics
        assert "provider.health" in topics
        assert "provider.failed" in topics

        await impl.stop()
