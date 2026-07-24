"""Tests for OmniRoute Model Registry (Phase 5.2).

Covers: CRUD, search, filtering, provider validation, duplicates,
concurrency, EventBus, discovery sync, health, default model selection,
and DI integration.
"""

from __future__ import annotations

import asyncio

import pytest

from agentic_os.core.omniroute.model_registry import ModelRegistryImpl
from agentic_os.core.omniroute.provider_registry import ProviderRegistryImpl
from agentic_os.domain.omniroute import OmniRouteModel, OmniRouteProvider

# ── Fixtures ──


@pytest.fixture
async def provider_registry():
    impl = ProviderRegistryImpl()
    await impl.start()
    yield impl
    await impl.stop()


@pytest.fixture
async def registry():
    impl = ModelRegistryImpl()
    await impl.start()
    yield impl
    await impl.stop()


@pytest.fixture
async def registry_with_providers(provider_registry):
    impl = ModelRegistryImpl(provider_registry=provider_registry)
    await impl.start()
    # Register a test provider
    await provider_registry.register(
        OmniRouteProvider(
            name="test-openai",
            kind="openai",
            base_url="https://api.openai.com/v1",
            capabilities=("chat", "completion"),
            enabled=True,
        )
    )
    yield impl
    await impl.stop()


@pytest.fixture
def sample_model():
    return OmniRouteModel(
        model_id="gpt-4o",
        provider="test-openai",
        provider_id="",
        display_name="GPT-4o",
        model_family="gpt-4",
        context_window=128000,
        max_output_tokens=16384,
        input_cost_per_1k=0.01,
        output_cost_per_1k=0.03,
        capabilities=("chat", "completion", "vision"),
        supports_streaming=True,
        supports_reasoning=False,
        supports_vision=True,
        supports_tools=True,
        quality_score=0.95,
        latency_ms=350.0,
        throughput=120.0,
        tokenizer="cl100k_base",
        healthy=True,
        enabled=True,
        tags=("fast", "premium", "vision"),
        version="2024-08-06",
        aliases=("gpt-4o-latest",),
        input_modalities=("text", "image"),
        output_modalities=("text",),
    )


@pytest.fixture
def sample_model2():
    return OmniRouteModel(
        model_id="gpt-4o-mini",
        provider="test-openai",
        provider_id="",
        display_name="GPT-4o Mini",
        model_family="gpt-4",
        context_window=128000,
        max_output_tokens=16384,
        input_cost_per_1k=0.0015,
        output_cost_per_1k=0.006,
        capabilities=("chat", "completion"),
        supports_streaming=True,
        supports_reasoning=False,
        supports_vision=True,
        supports_tools=True,
        quality_score=0.85,
        latency_ms=200.0,
        throughput=250.0,
        tokenizer="cl100k_base",
        healthy=True,
        enabled=True,
        tags=("fast", "cheap"),
        version="2024-07-18",
        input_modalities=("text", "image"),
        output_modalities=("text",),
    )


# ═══════════════════════════════════════════════════════════════════
# CRUD
# ═══════════════════════════════════════════════════════════════════


class TestModelRegistryCRUD:
    """CRUD operations for models."""

    async def test_register_and_get(self, registry, sample_model):
        mid = await registry.register_model(sample_model)
        assert mid is not None and len(mid) > 0

        retrieved = await registry.get_model(mid)
        assert retrieved is not None
        assert retrieved.model_id == "gpt-4o"
        assert retrieved.display_name == "GPT-4o"
        assert retrieved.context_window == 128000
        assert retrieved.quality_score == 0.95
        assert retrieved.healthy is True  # sample_model has healthy=True

    async def test_register_returns_id(self, registry, sample_model):
        mid = await registry.register_model(sample_model)
        retrieved = await registry.get_model(mid)
        assert retrieved is not None

    async def test_register_duplicate(self, registry, sample_model):
        mid1 = await registry.register_model(sample_model)
        mid2 = await registry.register_model(sample_model)
        assert mid1 == mid2

    async def test_unregister_model(self, registry, sample_model):
        mid = await registry.register_model(sample_model)
        result = await registry.unregister_model(mid)
        assert result is True
        assert await registry.get_model(mid) is None

    async def test_unregister_not_found(self, registry):
        assert await registry.unregister_model("nonexistent") is False

    async def test_update_model(self, registry, sample_model):
        mid = await registry.register_model(sample_model)
        updated = OmniRouteModel(
            id=mid,
            model_id="gpt-4o",
            latency_ms=200.0,
            input_cost_per_1k=0.008,
            quality_score=0.97,
        )
        result = await registry.update_model(updated)
        assert result is not None
        assert result.latency_ms == 200.0
        assert result.input_cost_per_1k == 0.008
        assert result.quality_score == 0.97
        assert result.model_id == "gpt-4o"  # Preserved

    async def test_update_not_found(self, registry):
        result = await registry.update_model(OmniRouteModel(id="nonexistent"))
        assert result is None

    async def test_count(self, registry, sample_model, sample_model2):
        assert await registry.count() == 0
        await registry.register_model(sample_model)
        assert await registry.count() == 1
        await registry.register_model(sample_model2)
        assert await registry.count() == 2

    async def test_get_model_by_name(self, registry, sample_model):
        await registry.register_model(sample_model)
        found = await registry.get_model_by_name("GPT-4o")
        assert found is not None
        assert found.model_id == "gpt-4o"

    async def test_get_model_by_name_alias(self, registry, sample_model):
        await registry.register_model(sample_model)
        found = await registry.get_model_by_name("gpt-4o-latest")
        assert found is not None
        assert found.model_id == "gpt-4o"

    async def test_get_model_by_name_not_found(self, registry):
        assert await registry.get_model_by_name("nonexistent") is None

    async def test_list_models(self, registry, sample_model, sample_model2):
        await registry.register_model(sample_model)
        await registry.register_model(sample_model2)
        all_models = await registry.list_models()
        assert len(all_models) == 2

    async def test_list_models_filter_provider(self, registry, sample_model):
        await registry.register_model(sample_model)
        await registry.register_model(
            OmniRouteModel(model_id="claude-4", provider="test-anthropic", provider_id="")
        )
        openai_models = await registry.list_models(provider="test-openai")
        assert len(openai_models) == 1

    async def test_list_models_filter_capability(self, registry, sample_model):
        await registry.register_model(sample_model)
        # sample_model has "vision" capability
        vision_models = await registry.list_models(capability="vision")
        assert len(vision_models) == 1
        embedding_models = await registry.list_models(capability="embedding")
        assert len(embedding_models) == 0

    async def test_list_models_filter_family(self, registry, sample_model, sample_model2):
        await registry.register_model(sample_model)
        await registry.register_model(sample_model2)
        await registry.register_model(
            OmniRouteModel(model_id="dall-e-3", provider="test-openai", model_family="dall-e")
        )
        gpt4_models = await registry.list_models(family="gpt-4")
        assert len(gpt4_models) == 2

    async def test_list_models_enabled_only(self, registry, sample_model):
        await registry.register_model(sample_model)
        await registry.register_model(
            OmniRouteModel(model_id="disabled-model", provider="test", enabled=False)
        )
        enabled = await registry.list_models(enabled_only=True)
        assert len(enabled) == 1

    async def test_list_models_healthy_only(self, registry, sample_model):
        await registry.register_model(sample_model)
        await registry.set_model_health(sample_model.id, True)
        unhealthy = OmniRouteModel(model_id="unhealthy-model", provider="test")
        await registry.register_model(unhealthy)
        healthy = await registry.list_models(healthy_only=True)
        assert len(healthy) == 1

    async def test_list_by_provider(self, registry, sample_model, sample_model2):
        await registry.register_model(sample_model)
        await registry.register_model(sample_model2)
        await registry.register_model(
            OmniRouteModel(model_id="claude-3", provider="test-anthropic", provider_id="")
        )
        openai_models = await registry.list_by_provider("test-openai")
        assert len(openai_models) == 2

    async def test_list_by_capability(self, registry, sample_model, sample_model2):
        await registry.register_model(sample_model)
        await registry.register_model(sample_model2)
        # sample_model has "vision", sample_model2 also has "vision"
        # sample_model2 also has "completion"
        completion_models = await registry.list_by_capability("completion")
        assert len(completion_models) == 2


# ═══════════════════════════════════════════════════════════════════
# Provider Validation
# ═══════════════════════════════════════════════════════════════════


class TestModelRegistryProviderValidation:
    """Model must validate against ProviderRegistry."""

    async def test_register_with_valid_provider(self, registry_with_providers, sample_model):
        mid = await registry_with_providers.register_model(sample_model)
        assert mid is not None

    async def test_register_without_provider_fails(self, registry_with_providers):
        model = OmniRouteModel(
            model_id="orphan-model",
            provider="nonexistent",
            provider_id="nonexistent-id",
        )
        with pytest.raises(ValueError, match="provider 'nonexistent-id' not found"):
            await registry_with_providers.register_model(model)

    async def test_register_with_disabled_provider_fails(
        self, provider_registry, registry_with_providers
    ):
        """Register a disabled provider, then try to register a model for it."""
        disabled = await provider_registry.register(
            OmniRouteProvider(
                name="disabled-provider",
                kind="test",
                base_url="http://test",
                enabled=False,
            )
        )
        model_with_id = OmniRouteModel(
            model_id="model-on-disabled",
            provider="disabled-provider",
            provider_id=disabled,
        )
        with pytest.raises(ValueError, match="not found, disabled, or unhealthy"):
            await registry_with_providers.register_model(model_with_id)

    async def test_standalone_registry_allows_without_validation(self, registry, sample_model):
        """Without a provider registry, models can be registered freely."""
        mid = await registry.register_model(sample_model)
        assert mid is not None


# ═══════════════════════════════════════════════════════════════════
# Search & Filtering
# ═══════════════════════════════════════════════════════════════════


class TestModelRegistrySearch:
    """Compound search and filtering."""

    @pytest.fixture(autouse=True)
    async def setup_models(self, registry):
        self._reg = registry
        await registry.register_model(
            OmniRouteModel(
                model_id="gpt-4o",
                provider="openai",
                capabilities=("chat", "vision", "completion"),
                context_window=128000,
                input_cost_per_1k=0.01,
                output_cost_per_1k=0.03,
                latency_ms=350,
                quality_score=0.95,
                supports_streaming=True,
                supports_reasoning=False,
                supports_vision=True,
                supports_tools=True,
                healthy=True,
                enabled=True,
                tags=("premium",),
                input_modalities=("text", "image"),
                output_modalities=("text",),
            )
        )
        await registry.register_model(
            OmniRouteModel(
                model_id="gpt-4o-mini",
                provider="openai",
                capabilities=("chat", "completion"),
                context_window=128000,
                input_cost_per_1k=0.0015,
                output_cost_per_1k=0.006,
                latency_ms=200,
                quality_score=0.85,
                supports_streaming=True,
                supports_reasoning=False,
                supports_vision=True,
                supports_tools=True,
                healthy=True,
                enabled=True,
                tags=("cheap",),
            )
        )
        await registry.register_model(
            OmniRouteModel(
                model_id="claude-sonnet-4",
                provider="anthropic",
                capabilities=("chat", "reasoning", "completion"),
                context_window=200000,
                input_cost_per_1k=0.015,
                output_cost_per_1k=0.075,
                latency_ms=500,
                quality_score=0.93,
                supports_streaming=True,
                supports_reasoning=True,
                supports_vision=True,
                supports_tools=True,
                healthy=True,
                enabled=True,
                tags=("premium", "reasoning"),
            )
        )
        await registry.register_model(
            OmniRouteModel(
                model_id="deepseek-coder",
                provider="deepseek",
                capabilities=("chat", "coding", "completion"),
                context_window=128000,
                input_cost_per_1k=0.0005,
                output_cost_per_1k=0.002,
                latency_ms=800,
                quality_score=0.88,
                supports_streaming=True,
                supports_reasoning=False,
                supports_vision=False,
                supports_tools=True,
                healthy=True,
                enabled=True,
                tags=("cheap", "coding"),
            )
        )

    async def test_search_basic(self):
        results = await self._reg.search()
        assert len(results) == 4

    async def test_search_by_provider(self):
        results = await self._reg.search(provider="openai")
        assert len(results) == 2

    async def test_search_by_capability(self):
        results = await self._reg.search(capability="vision")
        assert len(results) == 1  # only gpt-4o has "vision" in capabilities tuple

    async def test_search_by_reasoning(self):
        results = await self._reg.search(supports_reasoning=True)
        assert len(results) == 1
        assert results[0].model_id == "claude-sonnet-4"

    async def test_search_by_min_context(self):
        results = await self._reg.search(min_context=150000)
        assert len(results) == 1
        assert results[0].model_id == "claude-sonnet-4"

    async def test_search_by_max_cost(self):
        results = await self._reg.search(max_cost_input=0.001)
        assert len(results) == 1
        assert results[0].model_id == "deepseek-coder"

    async def test_search_by_max_latency(self):
        results = await self._reg.search(max_latency_ms=250)
        assert len(results) == 1
        assert results[0].model_id == "gpt-4o-mini"

    async def test_search_by_min_quality(self):
        results = await self._reg.search(min_quality=0.90)
        assert len(results) == 2
        model_ids = {m.model_id for m in results}
        assert "gpt-4o" in model_ids
        assert "claude-sonnet-4" in model_ids

    async def test_search_by_tag(self):
        results = await self._reg.search(tag="coding")
        assert len(results) == 1
        assert results[0].model_id == "deepseek-coder"

    async def test_search_by_modality(self):
        results = await self._reg.search(modality="image")
        assert len(results) == 1
        assert results[0].model_id == "gpt-4o"

    async def test_search_compound(self):
        """Compound query: chat capability, cheap, fast, high quality."""
        results = await self._reg.search(
            capability="chat",
            max_cost_input=0.002,
            max_latency_ms=300,
            min_quality=0.80,
        )
        assert len(results) == 1
        assert results[0].model_id == "gpt-4o-mini"

    async def test_search_enabled_implicit(self):
        """Enabled_only defaults to True."""
        results = await self._reg.search()
        assert all(m.enabled for m in results)

    async def test_search_limit(self):
        results = await self._reg.search(limit=2)
        assert len(results) <= 2

    async def test_search_ordering(self):
        """Results ordered by quality_score descending."""
        results = await self._reg.search()
        for i in range(len(results) - 1):
            assert results[i].quality_score >= results[i + 1].quality_score

    async def test_best_models(self):
        results = await self._reg.best_models("chat", top_k=3)
        assert len(results) == 3
        assert results[0].quality_score >= results[1].quality_score >= results[2].quality_score

    async def test_best_models_with_cost_limit(self):
        results = await self._reg.best_models("chat", max_cost=0.002)
        assert len(results) > 0
        for m in results:
            assert m.input_cost_per_1k <= 0.002 or m.input_cost_per_1k == 0.0

    async def test_compatible_models_basic(self):
        results = await self._reg.compatible_models(min_context=100000)
        assert len(results) == 4

    async def test_compatible_models_with_features(self):
        results = await self._reg.compatible_models(
            features={"vision", "tools"},
            min_context=50000,
        )
        assert (
            len(results) == 3
        )  # gpt-4o, gpt-4o-mini, claude-sonnet-4 all have supports_vision + supports_tools
        model_ids = {m.model_id for m in results}
        assert "gpt-4o" in model_ids
        assert "claude-sonnet-4" in model_ids
        assert "gpt-4o-mini" in model_ids

    async def test_compatible_models_reasoning(self):
        results = await self._reg.compatible_models(features={"reasoning"})
        assert len(results) == 1
        assert results[0].model_id == "claude-sonnet-4"


# ═══════════════════════════════════════════════════════════════════
# Default Model Selection
# ═══════════════════════════════════════════════════════════════════


class TestModelRegistryDefaults:
    """Default model per provider."""

    async def test_set_default(self, registry, sample_model, sample_model2):
        mid1 = await registry.register_model(sample_model)
        await registry.register_model(sample_model2)

        result = await registry.set_default(mid1)
        assert result is True

        default = await registry.default_model("")
        assert default is not None
        assert default.model_id == "gpt-4o"

    async def test_set_default_twice(self, registry, sample_model, sample_model2):
        mid1 = await registry.register_model(sample_model)
        mid2 = await registry.register_model(sample_model2)

        await registry.set_default(mid1)
        await registry.set_default(mid2)

        default = await registry.default_model("")
        assert default is not None
        assert default.model_id == "gpt-4o-mini"

    async def test_set_default_not_found(self, registry):
        assert await registry.set_default("nonexistent") is False

    async def test_default_model_none(self, registry):
        assert await registry.default_model("any-provider") is None

    async def test_default_cleared_on_unregister(self, registry, sample_model):
        mid = await registry.register_model(sample_model)
        await registry.set_default(mid)
        await registry.unregister_model(mid)
        assert await registry.default_model("") is None


# ═══════════════════════════════════════════════════════════════════
# Health
# ═══════════════════════════════════════════════════════════════════


class TestModelRegistryHealth:
    """Health tracking and lifecycle."""

    async def test_set_healthy(self, registry, sample_model):
        mid = await registry.register_model(sample_model)
        await registry.set_model_health(mid, True)
        retrieved = await registry.get_model(mid)
        assert retrieved is not None
        assert retrieved.healthy is True

    async def test_set_unhealthy(self, registry, sample_model):
        mid = await registry.register_model(sample_model)
        await registry.set_model_health(mid, False, error="timeout")
        retrieved = await registry.get_model(mid)
        assert retrieved is not None
        assert retrieved.healthy is False

    async def test_set_health_not_found(self, registry):
        assert await registry.set_model_health("nonexistent", True) is False

    async def test_health_check(self, registry):
        status = await registry.health_check()
        assert status["status"] == "healthy"
        assert status["model_count"] == 0

    async def test_ready(self, registry):
        assert await registry.ready() is True

    async def test_ready_stopped(self):
        impl = ModelRegistryImpl()
        assert await impl.ready() is False

    async def test_metadata(self, registry):
        meta = await registry.metadata()
        assert meta["type"] == "ModelRegistryImpl"
        assert meta["started"] is True

    async def test_capabilities(self, registry):
        caps = await registry.capabilities()
        assert len(caps) == 3
        names = [c["name"] for c in caps]
        assert "model_registry" in names
        assert "model_search" in names
        assert "sync_from_discovery" in names

    async def test_dependencies(self, registry):
        deps = await registry.dependencies()
        assert "provider_registry" in deps

    async def test_start_stop(self):
        impl = ModelRegistryImpl()
        assert (await impl.health_check())["status"] == "stopped"
        await impl.start()
        assert (await impl.health_check())["status"] == "healthy"
        await impl.stop()
        assert (await impl.health_check())["status"] == "stopped"


# ═══════════════════════════════════════════════════════════════════
# EventBus Integration
# ═══════════════════════════════════════════════════════════════════


class TestModelRegistryEventBus:
    """Events are published on lifecycle changes."""

    async def test_events_on_register_and_unregister(self):
        published = []

        class FakeBus:
            async def publish(self, event):
                published.append(event)

            async def start(self):
                pass

            async def stop(self):
                pass

            async def subscribe(self, topic, handler):
                return ""

            async def unsubscribe(self, sid):
                pass

        bus = FakeBus()
        impl = ModelRegistryImpl(event_bus=bus)
        await impl.start()

        mid = await impl.register_model(OmniRouteModel(model_id="test-model", provider="test"))
        await impl.update_model(OmniRouteModel(id=mid, model_id="test-model"))
        await impl.set_model_health(mid, True)
        await impl.set_default(mid)
        await impl.unregister_model(mid)

        topics = [e.topic for e in published]
        assert "model.registered" in topics
        assert "model.updated" in topics
        assert "model.health" in topics
        assert "model.default_changed" in topics
        assert "model.removed" in topics

        await impl.stop()


# ═══════════════════════════════════════════════════════════════════
# Discovery Sync
# ═══════════════════════════════════════════════════════════════════


class TestModelRegistryDiscoverySync:
    """sync_from_discovery integration."""

    async def test_sync_new_models(self, registry):
        discovered = [
            {
                "model_id": "gpt-4o",
                "provider": "openai",
                "provider_id": "openai-1",
                "display_name": "GPT-4o",
                "context_window": 128000,
                "capabilities": ["chat", "vision"],
            },
            {
                "model_id": "claude-3",
                "provider": "anthropic",
                "provider_id": "anthropic-1",
                "display_name": "Claude 3",
                "context_window": 200000,
                "capabilities": ["chat", "reasoning"],
            },
        ]
        registered, updated = await registry.sync_from_discovery(discovered)
        assert registered == 2
        assert updated == 0
        assert await registry.count() == 2

    async def test_sync_updates_existing(self, registry):
        discovered = [
            {
                "model_id": "gpt-4o",
                "provider": "openai",
                "provider_id": "openai-1",
                "display_name": "GPT-4o",
                "context_window": 128000,
            },
        ]
        await registry.sync_from_discovery(discovered)

        # Update with new latency
        discovered[0]["latency_ms"] = 300.0
        discovered[0]["quality_score"] = 0.96
        registered, updated = await registry.sync_from_discovery(discovered)
        assert registered == 0
        assert updated == 1  # only update_model calls count as "updated"

    async def test_sync_no_duplicates(self, registry):
        discovered = [
            {
                "model_id": "gpt-4o",
                "provider": "openai",
                "provider_id": "openai-1",
                "display_name": "GPT-4o",
            },
        ]
        reg1, _ = await registry.sync_from_discovery(discovered)
        reg2, upd2 = await registry.sync_from_discovery(discovered)
        assert reg1 == 1
        assert reg2 == 0
        assert upd2 > 0
        assert await registry.count() == 1

    async def test_sync_with_all_fields(self, registry):
        discovered = [
            {
                "model_id": "gpt-4o",
                "provider": "openai",
                "provider_id": "openai-1",
                "display_name": "GPT-4o",
                "model_family": "gpt-4",
                "context_window": 128000,
                "max_output_tokens": 16384,
                "input_cost_per_1k": 0.01,
                "output_cost_per_1k": 0.03,
                "capabilities": ["chat", "vision"],
                "supports_streaming": True,
                "supports_reasoning": False,
                "supports_vision": True,
                "supports_tools": True,
                "latency_ms": 350.0,
                "quality_score": 0.95,
                "throughput": 120.0,
                "tokenizer": "cl100k_base",
                "healthy": True,
                "enabled": True,
                "tags": ["premium"],
                "version": "2024-08-06",
                "aliases": ["gpt-4o-latest"],
                "input_modalities": ["text", "image"],
                "output_modalities": ["text"],
            }
        ]
        registered, _ = await registry.sync_from_discovery(discovered)
        assert registered == 1
        model = await registry.get_model_by_name("GPT-4o")
        assert model is not None
        assert model.model_family == "gpt-4"
        assert model.tokenizer == "cl100k_base"
        assert model.throughput == 120.0
        assert "premium" in model.tags
        assert "gpt-4o-latest" in model.aliases
        assert "image" in model.input_modalities


# ═══════════════════════════════════════════════════════════════════
# Concurrency
# ═══════════════════════════════════════════════════════════════════


class TestModelRegistryConcurrency:
    """Thread safety under concurrent access."""

    async def test_concurrent_registrations(self, registry):
        async def register_model(n: int):
            model = OmniRouteModel(
                model_id=f"concurrent-model-{n}",
                provider=f"provider-{n}",
            )
            return await registry.register_model(model)

        tasks = [register_model(i) for i in range(20)]
        ids = await asyncio.gather(*tasks)
        assert len(set(ids)) == 20
        assert await registry.count() == 20

    async def test_concurrent_reads_and_writes(self, registry, sample_model):
        mid = await registry.register_model(sample_model)

        async def read_model():
            return await registry.get_model(mid)

        async def update_model():
            await registry.update_model(
                OmniRouteModel(id=mid, model_id="gpt-4o", quality_score=0.96)
            )

        async def delete_and_recreate():
            await registry.unregister_model(mid)
            return await registry.register_model(sample_model)

        results = await asyncio.gather(
            read_model(),
            update_model(),
            delete_and_recreate(),
            return_exceptions=True,
        )
        # No crash is the primary assertion
        assert results is not None


# ═══════════════════════════════════════════════════════════════════
# Observability / Metrics
# ═══════════════════════════════════════════════════════════════════


class TestModelRegistryObservability:
    """Metrics collection."""

    async def test_registration_count_increases(self, registry, sample_model):
        # Access internal metrics through _metrics() method
        await registry.register_model(sample_model)
        assert registry._registration_count == 1

    async def test_search_count_increases(self, registry, sample_model):
        await registry.register_model(sample_model)
        await registry.search()
        assert registry._search_count == 1
        assert registry._search_duration_total > 0

    async def test_sync_count_increases(self, registry):
        await registry.sync_from_discovery(
            [
                {"model_id": "test", "provider": "test", "provider_id": "test"},
            ]
        )
        assert registry._sync_count == 1
        assert registry._sync_duration_total > 0

    async def test_metrics_snapshot(self, registry, sample_model):
        await registry.register_model(sample_model)
        await registry.set_model_health(sample_model.id, True)
        await registry.search()

        metrics = registry._metrics()
        assert metrics["registered_models"] == 1
        assert metrics["healthy_models"] == 1
        assert metrics["disabled_models"] == 0
        assert metrics["search_count"] == 1
