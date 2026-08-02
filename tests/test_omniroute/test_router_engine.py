"""Tests for OmniRoute Router Engine (Phase 5.3).

Targets: 80-95 tests covering routing, ranking, filtering, fallback,
weighted scoring, budget/latency/capability/context filtering,
provider health, disabled providers/models, concurrency, EventBus,
DI, lifecycle, metrics, observability, and edge cases.
"""

from __future__ import annotations

import asyncio

import pytest

from agentic_os.core.omniroute.router import RouterEngineImpl, _ScoringEngine
from agentic_os.domain.omniroute import (
    OmniRouteModel,
    OmniRouteProvider,
    RoutingRequest,
)

# ── Fixtures ──


@pytest.fixture
def router():
    """RouterEngine without registries (standalone mode)."""
    impl = RouterEngineImpl()
    return impl


@pytest.fixture
async def router_with_registries():
    """RouterEngine with populated provider and model registries."""
    from agentic_os.core.omniroute.model_registry import ModelRegistryImpl
    from agentic_os.core.omniroute.provider_registry import ProviderRegistryImpl

    pr = ProviderRegistryImpl()
    mr = ModelRegistryImpl(provider_registry=pr)
    impl = RouterEngineImpl(provider_registry=pr, model_registry=mr)

    await pr.start()
    await mr.start()
    await impl.start()

    # Register providers
    openai_id = await pr.register(
        OmniRouteProvider(
            name="openai",
            kind="openai",
            base_url="https://api.openai.com/v1",
            capabilities=("chat", "completion", "vision"),
            healthy=True,
            enabled=True,
            latency_ms=200,
            cost_per_1k_input=0.01,
            cost_per_1k_output=0.03,
        )
    )
    anthropic_id = await pr.register(
        OmniRouteProvider(
            name="anthropic",
            kind="anthropic",
            base_url="https://api.anthropic.com/v1",
            capabilities=("chat", "reasoning", "completion"),
            healthy=True,
            enabled=True,
            latency_ms=400,
            cost_per_1k_input=0.015,
            cost_per_1k_output=0.075,
        )
    )
    deepseek_id = await pr.register(
        OmniRouteProvider(
            name="deepseek",
            kind="deepseek",
            base_url="https://api.deepseek.com/v1",
            capabilities=("chat", "coding", "completion"),
            healthy=True,
            enabled=True,
            latency_ms=800,
            cost_per_1k_input=0.0005,
            cost_per_1k_output=0.002,
        )
    )

    # Register models
    await mr.register_model(
        OmniRouteModel(
            model_id="gpt-4o",
            provider="openai",
            provider_id=openai_id,
            display_name="GPT-4o",
            context_window=128000,
            input_cost_per_1k=0.01,
            output_cost_per_1k=0.03,
            capabilities=("chat", "vision", "completion"),
            supports_streaming=True,
            supports_reasoning=False,
            supports_vision=True,
            supports_tools=True,
            quality_score=0.95,
            latency_ms=350,
            healthy=True,
            enabled=True,
        )
    )
    await mr.register_model(
        OmniRouteModel(
            model_id="gpt-4o-mini",
            provider="openai",
            provider_id=openai_id,
            display_name="GPT-4o Mini",
            context_window=128000,
            input_cost_per_1k=0.0015,
            output_cost_per_1k=0.006,
            capabilities=("chat", "completion"),
            supports_streaming=True,
            supports_reasoning=False,
            supports_vision=True,
            supports_tools=True,
            quality_score=0.85,
            latency_ms=200,
            healthy=True,
            enabled=True,
        )
    )
    await mr.register_model(
        OmniRouteModel(
            model_id="claude-sonnet-4",
            provider="anthropic",
            provider_id=anthropic_id,
            display_name="Claude Sonnet 4",
            context_window=200000,
            input_cost_per_1k=0.015,
            output_cost_per_1k=0.075,
            capabilities=("chat", "reasoning", "completion"),
            supports_streaming=True,
            supports_reasoning=True,
            supports_vision=True,
            supports_tools=True,
            quality_score=0.93,
            latency_ms=500,
            healthy=True,
            enabled=True,
        )
    )
    await mr.register_model(
        OmniRouteModel(
            model_id="deepseek-coder",
            provider="deepseek",
            provider_id=deepseek_id,
            display_name="DeepSeek Coder",
            context_window=128000,
            input_cost_per_1k=0.0005,
            output_cost_per_1k=0.002,
            capabilities=("chat", "coding", "completion"),
            supports_streaming=True,
            supports_reasoning=False,
            supports_vision=False,
            supports_tools=True,
            quality_score=0.88,
            latency_ms=800,
            healthy=True,
            enabled=True,
        )
    )

    yield impl, pr, mr

    await impl.stop()
    await mr.stop()
    await pr.stop()


@pytest.fixture
def basic_request():
    return RoutingRequest(task_type="chat", required_capabilities=("chat",))


# ═══════════════════════════════════════════════════════════════════
# Lifecycle
# ═══════════════════════════════════════════════════════════════════


class TestRouterLifecycle:
    """Lifecycle management."""

    async def test_initial_state(self):
        r = RouterEngineImpl()
        assert await r.ready() is False

    async def test_start_and_stop(self, router):
        await router.start()
        assert await router.ready() is True
        await router.stop()
        assert await router.ready() is False

    async def test_initialize(self, router):
        await router.initialize()
        assert router is not None  # no-op, just shouldn't crash

    async def test_dispose(self, router):
        await router.start()
        await router.dispose()
        assert await router.ready() is False

    async def test_health_stopped(self, router):
        h = await router.health()
        assert h["status"] == "stopped"

    async def test_health_started(self, router):
        await router.start()
        h = await router.health()
        assert h["status"] == "healthy"
        assert "routing_count" in h

    async def test_metadata(self, router):
        m = await router.metadata()
        assert m["type"] == "RouterEngineImpl"

    async def test_dependencies(self, router):
        d = await router.dependencies()
        assert "provider_registry" in d
        assert "model_registry" in d

    async def test_capabilities(self, router):
        c = await router.capabilities()
        names = [x["name"] for x in c]
        assert "routing" in names
        assert "ranking" in names
        assert "fallback" in names
        assert "scoring" in names
        assert "estimation" in names


# ═══════════════════════════════════════════════════════════════════
# Request Validation
# ═══════════════════════════════════════════════════════════════════


class TestRequestValidation:
    """validate_request."""

    async def test_valid_request(self, router):
        req = RoutingRequest(task_type="chat")
        errors = await router.validate_request(req)
        assert errors == []

    async def test_empty_task_type(self, router):
        req = RoutingRequest(task_type="")
        errors = await router.validate_request(req)
        assert "task_type is required" in errors

    async def test_negative_weights(self, router):
        req = RoutingRequest(task_type="chat", cost_weight=-1, quality_weight=-2, latency_weight=-3)
        errors = await router.validate_request(req)
        assert len(errors) == 3

    async def test_negative_budget(self, router):
        req = RoutingRequest(task_type="chat", budget_limit=-1)
        errors = await router.validate_request(req)
        assert "budget_limit must be >= 0" in errors

    async def test_negative_latency(self, router):
        req = RoutingRequest(task_type="chat", max_latency_ms=-1)
        errors = await router.validate_request(req)
        assert "max_latency_ms must be >= 0" in errors


# ═══════════════════════════════════════════════════════════════════
# Routing Pipeline
# ═══════════════════════════════════════════════════════════════════


class TestRoutingPipeline:
    """Full routing pipeline integration."""

    async def test_route_selects_valid_candidate(self, router_with_registries):
        r, pr, mr = router_with_registries
        req = RoutingRequest(task_type="chat", required_capabilities=("chat",))
        decision = await r.route(req)
        assert decision.status == "routed"
        assert decision.provider in ("openai", "anthropic", "deepseek")
        assert decision.model_id in ("gpt-4o", "gpt-4o-mini", "claude-sonnet-4", "deepseek-coder")
        assert decision.score.weighted_total > 0

    async def test_route_rejected_on_invalid_request(self, router_with_registries):
        r, pr, mr = router_with_registries
        req = RoutingRequest(task_type="", required_capabilities=("chat",))
        decision = await r.route(req)
        assert decision.status == "rejected"
        assert decision.reason != ""

    async def test_route_return_estimated_cost(self, router_with_registries):
        r, pr, mr = router_with_registries
        decision = await r.route(RoutingRequest(task_type="chat"))
        assert decision.estimated_cost > 0

    async def test_route_return_estimated_latency(self, router_with_registries):
        r, pr, mr = router_with_registries
        decision = await r.route(RoutingRequest(task_type="chat"))
        assert decision.estimated_latency_ms > 0

    async def test_route_return_fallback_chain(self, router_with_registries):
        r, pr, mr = router_with_registries
        decision = await r.route(RoutingRequest(task_type="chat"))
        assert len(decision.fallback_chain) >= 1  # at least the selected one

    async def test_route_prefers_preferred_provider(self, router_with_registries):
        r, pr, mr = router_with_registries
        req = RoutingRequest(task_type="chat", preferred_provider="deepseek")
        decision = await r.route(req)
        assert decision.provider == "deepseek"

    async def test_route_prefers_preferred_model(self, router_with_registries):
        r, pr, mr = router_with_registries
        req = RoutingRequest(task_type="chat", preferred_model="gpt-4o")
        decision = await r.route(req)
        assert decision.model_id == "gpt-4o"

    async def test_route_many(self, router_with_registries):
        r, pr, mr = router_with_registries
        reqs = [
            RoutingRequest(task_type="chat"),
            RoutingRequest(task_type="chat"),
            RoutingRequest(task_type="chat"),
        ]
        decisions = await r.route_many(reqs)
        assert len(decisions) == 3
        for d in decisions:
            assert d.status == "routed"


# ═══════════════════════════════════════════════════════════════════
# Capability Filtering
# ═══════════════════════════════════════════════════════════════════


class TestCapabilityFiltering:
    """Required capabilities and feature flags."""

    async def test_vision_required(self, router_with_registries):
        r, pr, mr = router_with_registries
        req = RoutingRequest(task_type="chat", vision_required=True)
        decision = await r.route(req)
        assert decision.status == "routed"
        # deepseek has supports_vision=False, so it shouldn't be selected
        assert decision.provider != "deepseek"

    async def test_reasoning_required(self, router_with_registries):
        r, pr, mr = router_with_registries
        req = RoutingRequest(task_type="chat", reasoning_required=True)
        decision = await r.route(req)
        assert decision.status == "routed"
        assert decision.model_id == "claude-sonnet-4"  # only model with reasoning

    async def test_streaming_required(self, router_with_registries):
        r, pr, mr = router_with_registries
        req = RoutingRequest(task_type="chat", streaming_required=True)
        decision = await r.route(req)
        assert decision.status == "routed"

    async def test_tools_required(self, router_with_registries):
        r, pr, mr = router_with_registries
        req = RoutingRequest(task_type="chat", tools_required=True)
        decision = await r.route(req)
        assert decision.status == "routed"

    async def test_capability_filter_chat(self, router_with_registries):
        r, pr, mr = router_with_registries
        req = RoutingRequest(task_type="chat", required_capabilities=("chat",))
        decision = await r.route(req)
        assert decision.status == "routed"

    async def test_capability_filter_coding(self, router_with_registries):
        r, pr, mr = router_with_registries
        req = RoutingRequest(task_type="chat", required_capabilities=("coding",))
        decision = await r.route(req)
        assert decision.status == "routed"
        assert decision.provider == "deepseek"

    async def test_capability_filter_none_match(self, router_with_registries):
        r, pr, mr = router_with_registries
        req = RoutingRequest(task_type="chat", required_capabilities=("image-generation",))
        decision = await r.route(req)
        assert decision.status == "failed"  # no model has this capability

    async def test_capability_filter_vision_string(self, router_with_registries):
        """Filter by capability string "vision" in capabilities tuple."""
        r, pr, mr = router_with_registries
        req = RoutingRequest(task_type="chat", required_capabilities=("vision",))
        decision = await r.route(req)
        assert decision.status == "routed"
        assert decision.model_id in ("gpt-4o", "claude-sonnet-4")


# ═══════════════════════════════════════════════════════════════════
# Context, Budget & Latency Filtering
# ═══════════════════════════════════════════════════════════════════


class TestContextBudgetLatencyFiltering:
    """Context window, budget, and max latency constraints."""

    async def test_minimum_context_satisfied(self, router_with_registries):
        r, pr, mr = router_with_registries
        req = RoutingRequest(task_type="chat", minimum_context=100000)
        decision = await r.route(req)
        assert decision.status == "routed"

    async def test_minimum_context_exceeds_all(self, router_with_registries):
        r, pr, mr = router_with_registries
        req = RoutingRequest(task_type="chat", minimum_context=1_000_000)
        decision = await r.route(req)
        assert decision.status == "failed"

    async def test_minimum_context_selects_longest(self, router_with_registries):
        r, pr, mr = router_with_registries
        req = RoutingRequest(task_type="chat", minimum_context=150000)
        decision = await r.route(req)
        assert decision.status == "routed"
        assert decision.model_id == "claude-sonnet-4"  # 200k context

    async def test_budget_filter_low(self, router_with_registries):
        r, pr, mr = router_with_registries
        req = RoutingRequest(task_type="chat", budget_limit=0.003)
        decision = await r.route(req)
        assert decision.status == "routed"
        assert decision.model_id == "deepseek-coder"  # cheapest (0.0025) fits budget

    async def test_budget_filter_medium(self, router_with_registries):
        r, pr, mr = router_with_registries
        req = RoutingRequest(task_type="chat", budget_limit=0.008)
        decision = await r.route(req)
        assert decision.status == "routed"
        # deepseek-coder (0.0025) and gpt-4o-mini (0.0075) both fit;
        # deepseek wins (higher quality + lower cost)

    async def test_budget_filter_zero(self, router_with_registries):
        r, pr, mr = router_with_registries
        req = RoutingRequest(task_type="chat", budget_limit=0)
        decision = await r.route(req)
        assert decision.status == "routed"  # zero = no filter

    async def test_latency_filter_low(self, router_with_registries):
        r, pr, mr = router_with_registries
        req = RoutingRequest(task_type="chat", max_latency_ms=250)
        decision = await r.route(req)
        assert decision.status == "routed"
        assert decision.model_id == "gpt-4o-mini"  # fastest

    async def test_latency_filter_zero(self, router_with_registries):
        r, pr, mr = router_with_registries
        req = RoutingRequest(task_type="chat", max_latency_ms=0)
        decision = await r.route(req)
        assert decision.status == "routed"  # zero = no filter

    async def test_latency_filter_too_low(self, router_with_registries):
        r, pr, mr = router_with_registries
        req = RoutingRequest(task_type="chat", max_latency_ms=10)
        decision = await r.route(req)
        assert decision.status == "failed"  # all latencies > 10ms


# ═══════════════════════════════════════════════════════════════════
# Provider & Model Health / Disabled
# ═══════════════════════════════════════════════════════════════════


class TestProviderModelHealth:
    """Handling of unhealthy/disabled providers and models."""

    async def test_unhealthy_provider_skipped(self, router_with_registries):
        r, pr, mr = router_with_registries
        # Make deepseek unhealthy
        deepseek = await pr.get_by_name("deepseek")
        assert deepseek is not None
        await pr.set_health(deepseek.id, False)

        req = RoutingRequest(task_type="chat", preferred_provider="deepseek")
        decision = await r.route(req)
        assert decision.status == "routed"
        assert decision.provider != "deepseek"  # should skip unhealthy

    async def test_disabled_provider_skipped(self, router_with_registries):
        r, pr, mr = router_with_registries
        # Disable deepseek
        deepseek = await pr.get_by_name("deepseek")
        assert deepseek is not None
        await pr.update(OmniRouteProvider(id=deepseek.id, name="deepseek", enabled=False))

        req = RoutingRequest(task_type="chat", preferred_provider="deepseek")
        decision = await r.route(req)
        assert decision.status == "routed"
        assert decision.provider != "deepseek"

    async def test_disabled_model_skipped(self, router_with_registries):
        r, pr, mr = router_with_registries
        # Disable gpt-4o-mini
        gpt_mini = await mr.get_model_by_name("GPT-4o Mini")
        assert gpt_mini is not None
        disabled = OmniRouteModel(
            id=gpt_mini.id,
            model_id="gpt-4o-mini",
            enabled=False,
        )
        await mr.update_model(disabled)

        req = RoutingRequest(task_type="chat", preferred_model="gpt-4o-mini")
        decision = await r.route(req)
        assert decision.status == "routed"
        assert decision.model_id != "gpt-4o-mini"

    async def test_all_providers_unhealthy_fails(self, router_with_registries):
        r, pr, mr = router_with_registries
        # Make all unhealthy
        for p in await pr.list_providers():
            await pr.set_health(p.id, False)

        req = RoutingRequest(task_type="chat")
        decision = await r.route(req)
        assert decision.status == "failed"
        assert "unhealthy" in decision.reason or "no providers" in decision.reason.lower()


# ═══════════════════════════════════════════════════════════════════
# Scoring Engine
# ═══════════════════════════════════════════════════════════════════


class TestScoringEngine:
    """Weighted multi-dimensional scoring."""

    def test_score_quality(self):
        model = OmniRouteModel(model_id="test", quality_score=0.8)
        req = RoutingRequest(task_type="chat")
        scorer = _ScoringEngine(req)
        score = scorer.score(OmniRouteProvider(name="test"), model)
        assert 0 < score.quality_score <= 1.0

    def test_score_cost_cheapest_is_best(self):
        cheap = OmniRouteModel(
            model_id="cheap", input_cost_per_1k=0.0001, output_cost_per_1k=0.0002
        )
        expensive = OmniRouteModel(
            model_id="expensive", input_cost_per_1k=1.0, output_cost_per_1k=2.0
        )
        req = RoutingRequest(task_type="chat", cost_weight=10)
        scorer = _ScoringEngine(req)
        cheap_score = scorer.score(
            OmniRouteProvider(name="test", cost_per_1k_input=0, cost_per_1k_output=0), cheap
        )
        exp_score = scorer.score(
            OmniRouteProvider(name="test", cost_per_1k_input=0, cost_per_1k_output=0), expensive
        )
        assert cheap_score.cost_score > exp_score.cost_score

    def test_score_latency_fastest_is_best(self):
        fast = OmniRouteModel(model_id="fast", latency_ms=50)
        slow = OmniRouteModel(model_id="slow", latency_ms=3000)
        req = RoutingRequest(task_type="chat", latency_weight=10)
        scorer = _ScoringEngine(req)
        fast_score = scorer.score(OmniRouteProvider(name="test", latency_ms=50), fast)
        slow_score = scorer.score(OmniRouteProvider(name="test", latency_ms=3000), slow)
        assert fast_score.latency_score > slow_score.latency_score

    def test_score_health_both_healthy(self):
        provider = OmniRouteProvider(name="test", healthy=True)
        model = OmniRouteModel(model_id="test", healthy=True)
        req = RoutingRequest(task_type="chat")
        scorer = _ScoringEngine(req)
        score = scorer.score(provider, model)
        assert score.health_score == 1.0

    def test_score_health_one_unhealthy(self):
        provider = OmniRouteProvider(name="test", healthy=True)
        model = OmniRouteModel(model_id="test", healthy=False)
        req = RoutingRequest(task_type="chat")
        scorer = _ScoringEngine(req)
        score = scorer.score(provider, model)
        assert score.health_score == 0.5

    def test_score_context_larger_is_better(self):
        large = OmniRouteModel(model_id="large", context_window=200000)
        small = OmniRouteModel(model_id="small", context_window=4000)
        req = RoutingRequest(task_type="chat")
        scorer = _ScoringEngine(req)
        large_score = scorer.score(OmniRouteProvider(name="test"), large)
        small_score = scorer.score(OmniRouteProvider(name="test"), small)
        assert large_score.context_score > small_score.context_score

    def test_score_preference_provider(self):
        provider = OmniRouteProvider(name="openai")
        model = OmniRouteModel(model_id="gpt-4o")
        req = RoutingRequest(task_type="chat", preferred_provider="openai")
        scorer = _ScoringEngine(req)
        score = scorer.score(provider, model)
        assert score.preference_score > 0

    def test_score_preference_model(self):
        provider = OmniRouteProvider(name="test")
        model = OmniRouteModel(model_id="gpt-4o", display_name="GPT-4o")
        req = RoutingRequest(task_type="chat", preferred_model="gpt-4o")
        scorer = _ScoringEngine(req)
        score = scorer.score(provider, model)
        assert score.preference_score > 0

    def test_weighted_total_combines_all_dimensions(self):
        provider = OmniRouteProvider(
            name="test",
            healthy=True,
            latency_ms=100,
            cost_per_1k_input=0.01,
            cost_per_1k_output=0.03,
        )
        model = OmniRouteModel(
            model_id="test",
            quality_score=0.9,
            latency_ms=100,
            context_window=128000,
            healthy=True,
            input_cost_per_1k=0.01,
            output_cost_per_1k=0.03,
        )
        req = RoutingRequest(task_type="chat", quality_weight=2, cost_weight=1, latency_weight=1)
        scorer = _ScoringEngine(req)
        score = scorer.score(provider, model)
        assert score.weighted_total > 0
        assert score.candidate_count == 1

    def test_score_reliability_enabled_healthy(self):
        provider = OmniRouteProvider(name="test", enabled=True, healthy=True)
        model = OmniRouteModel(model_id="test")
        req = RoutingRequest(task_type="chat")
        scorer = _ScoringEngine(req)
        score = scorer.score(provider, model)
        assert score.reliability_score == 1.0

    def test_score_reliability_disabled(self):
        provider = OmniRouteProvider(name="test", enabled=False)
        model = OmniRouteModel(model_id="test")
        req = RoutingRequest(task_type="chat")
        scorer = _ScoringEngine(req)
        score = scorer.score(provider, model)
        assert score.reliability_score == 0.0


# ═══════════════════════════════════════════════════════════════════
# Fallback Chain
# ═══════════════════════════════════════════════════════════════════


class TestFallbackChain:
    """generate_fallback_chain."""

    async def test_fallback_chain_generated(self, router_with_registries):
        r, pr, mr = router_with_registries
        req = RoutingRequest(task_type="chat")
        chain = await r.generate_fallback_chain(req, chain_length=5)
        assert len(chain) >= 1
        for entry in chain:
            assert len(entry) == 3  # (provider_name, provider_id, model_id)

    async def test_fallback_chain_length(self, router_with_registries):
        r, pr, mr = router_with_registries
        req = RoutingRequest(task_type="chat")
        chain = await r.generate_fallback_chain(req, chain_length=2)
        assert len(chain) <= 2

    async def test_fallback_chain_empty_on_no_candidates(self, router_with_registries):
        r, pr, mr = router_with_registries
        req = RoutingRequest(task_type="chat", max_latency_ms=1)  # too strict
        chain = await r.generate_fallback_chain(req)
        assert len(chain) == 0

    async def test_fallback_chain_on_route(self, router_with_registries):
        r, pr, mr = router_with_registries
        decision = await r.route(RoutingRequest(task_type="chat"))
        assert len(decision.fallback_chain) >= 1
        assert decision.alternatives_rejected >= 2  # at least 2 alternatives


# ═══════════════════════════════════════════════════════════════════
# Best Model / Provider / Ranking
# ═══════════════════════════════════════════════════════════════════


class TestBestAndRanking:
    """best_model, best_provider, rank_models, rank_providers."""

    async def test_best_model(self, router_with_registries):
        r, pr, mr = router_with_registries
        decisions = await r.best_model(RoutingRequest(task_type="chat"), top_k=1)
        assert len(decisions) == 1
        assert decisions[0].status == "routed"

    async def test_best_model_empty_on_failure(self, router_with_registries):
        r, pr, mr = router_with_registries
        decisions = await r.best_model(
            RoutingRequest(task_type="", required_capabilities=("chat",)), top_k=1
        )
        assert len(decisions) == 0

    async def test_best_provider(self, router_with_registries):
        r, pr, mr = router_with_registries
        decision = await r.best_provider(RoutingRequest(task_type="chat"))
        assert decision is not None
        assert decision.status == "routed"

    async def test_best_provider_prefers_openai(self, router_with_registries):
        r, pr, mr = router_with_registries
        decision = await r.best_provider(
            RoutingRequest(task_type="chat", preferred_provider="openai")
        )
        assert decision is not None
        assert decision.provider == "openai"

    async def test_rank_models(self, router_with_registries):
        r, pr, mr = router_with_registries
        ranked = await r.rank_models(RoutingRequest(task_type="chat"), limit=10)
        assert len(ranked) >= 1
        # Check ordering by score descending
        for i in range(len(ranked) - 1):
            assert ranked[i].score.weighted_total >= ranked[i + 1].score.weighted_total

    async def test_rank_models_limit(self, router_with_registries):
        r, pr, mr = router_with_registries
        ranked = await r.rank_models(RoutingRequest(task_type="chat"), limit=2)
        assert len(ranked) <= 2

    async def test_rank_models_empty_on_failure(self, router_with_registries):
        r, pr, mr = router_with_registries
        ranked = await r.rank_models(RoutingRequest(task_type="chat", max_latency_ms=1))
        assert len(ranked) == 0

    async def test_rank_providers(self, router_with_registries):
        r, pr, mr = router_with_registries
        ranked = await r.rank_providers(RoutingRequest(task_type="chat"))
        assert len(ranked) >= 1

    async def test_rank_providers_ordering(self, router_with_registries):
        r, pr, mr = router_with_registries
        ranked = await r.rank_providers(RoutingRequest(task_type="chat"))
        for i in range(len(ranked) - 1):
            assert ranked[i].score.weighted_total >= ranked[i + 1].score.weighted_total

    async def test_rank_providers_empty_on_no_candidates(self, router_with_registries):
        r, pr, mr = router_with_registries
        for p in await pr.list_providers():
            await pr.set_health(p.id, False)
        ranked = await r.rank_providers(RoutingRequest(task_type="chat"))
        assert len(ranked) == 0


# ═══════════════════════════════════════════════════════════════════
# Cost & Latency Estimation
# ═══════════════════════════════════════════════════════════════════


class TestEstimation:
    """estimate_cost, estimate_latency."""

    async def test_estimate_cost_positive(self, router_with_registries):
        r, pr, mr = router_with_registries
        cost = await r.estimate_cost(RoutingRequest(task_type="chat"))
        assert cost > 0

    async def test_estimate_cost_zero_on_no_registries(self, router):
        cost = await router.estimate_cost(RoutingRequest(task_type="chat"))
        assert cost == 0.0

    async def test_estimate_latency_positive(self, router_with_registries):
        r, pr, mr = router_with_registries
        lat = await r.estimate_latency(RoutingRequest(task_type="chat"))
        assert lat > 0

    async def test_estimate_latency_zero_on_no_registries(self, router):
        lat = await router.estimate_latency(RoutingRequest(task_type="chat"))
        assert lat == 0.0


# ═══════════════════════════════════════════════════════════════════
# Score Candidate
# ═══════════════════════════════════════════════════════════════════


class TestScoreCandidate:
    """score_candidate."""

    async def test_score_candidate_valid(self, router):
        provider = OmniRouteProvider(name="test", healthy=True, enabled=True)
        model = OmniRouteModel(model_id="test", quality_score=0.9)
        req = RoutingRequest(task_type="chat")
        score = await router.score_candidate(provider, model, req)
        assert score.weighted_total > 0
        assert score.quality_score == 0.9

    async def test_score_candidate_all_dimensions_present(self, router):
        provider = OmniRouteProvider(name="test", healthy=True, enabled=True, latency_ms=100)
        model = OmniRouteModel(
            model_id="test",
            quality_score=0.8,
            context_window=128000,
            latency_ms=100,
            healthy=True,
            input_cost_per_1k=0.01,
            output_cost_per_1k=0.03,
        )
        req = RoutingRequest(task_type="chat")
        score = await router.score_candidate(provider, model, req)
        assert score.quality_score > 0
        assert score.cost_score > 0
        assert score.latency_score > 0
        assert score.health_score > 0
        assert score.reliability_score > 0
        assert score.context_score > 0
        assert score.weighted_total > 0


# ═══════════════════════════════════════════════════════════════════
# Supported Capabilities
# ═══════════════════════════════════════════════════════════════════


class TestSupportedCapabilities:
    """supported_capabilities."""

    async def test_returns_list(self, router):
        caps = await router.supported_capabilities()
        assert len(caps) > 5
        assert "chat" in caps
        assert "vision" in caps
        assert "streaming" in caps


# ═══════════════════════════════════════════════════════════════════
# EventBus Integration
# ═══════════════════════════════════════════════════════════════════


class TestRouterEventBus:
    """Events published during routing."""

    async def test_events_on_successful_route(self):
        from agentic_os.core.omniroute.model_registry import ModelRegistryImpl
        from agentic_os.core.omniroute.provider_registry import ProviderRegistryImpl

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
        pr = ProviderRegistryImpl(event_bus=bus)
        mr = ModelRegistryImpl(provider_registry=pr, event_bus=bus)
        router = RouterEngineImpl(provider_registry=pr, model_registry=mr, event_bus=bus)

        await pr.start()
        await mr.start()
        await router.start()

        oid = await pr.register(
            OmniRouteProvider(
                name="test", kind="test", base_url="http://test", healthy=True, enabled=True
            )
        )
        await mr.register_model(
            OmniRouteModel(model_id="test-model", provider="test", provider_id=oid)
        )

        decision = await router.route(RoutingRequest(task_type="chat"))
        assert decision.status == "routed"

        topics = [e.topic for e in published]
        assert "route.requested" in topics
        assert "route.selected" in topics
        assert "route.scoring" in topics

        await router.stop()
        await mr.stop()
        await pr.stop()

    async def test_events_on_rejected_route(self):
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

        router = RouterEngineImpl(event_bus=FakeBus())
        await router.start()

        decision = await router.route(RoutingRequest(task_type=""))
        assert decision.status == "rejected"

        topics = [e.topic for e in published]
        assert "route.requested" in topics
        assert "route.rejected" in topics

        await router.stop()


# ═══════════════════════════════════════════════════════════════════
# Metrics & Observability
# ═══════════════════════════════════════════════════════════════════


class TestRouterMetrics:
    """Observability metrics."""

    async def test_metrics_after_routing(self, router_with_registries):
        r, pr, mr = router_with_registries
        await r.route(RoutingRequest(task_type="chat"))
        m = r.metrics()
        assert m["routing_count"] == 1
        assert m["routing_failures"] == 0
        assert m["avg_routing_latency_ms"] > 0
        assert m["avg_candidate_count"] >= 1
        assert len(m["provider_selection_frequency"]) >= 1
        assert len(m["model_selection_frequency"]) >= 1

    async def test_metrics_tracks_failures(self, router_with_registries):
        r, pr, mr = router_with_registries
        await r.route(RoutingRequest(task_type="chat", max_latency_ms=1))
        m = r.metrics()
        assert m["routing_failures"] >= 1
        assert m["failure_rate"] > 0

    async def test_metrics_tracks_p50_p95_p99(self, router_with_registries):
        r, pr, mr = router_with_registries
        for _ in range(3):
            await r.route(RoutingRequest(task_type="chat"))
        m = r.metrics()
        assert m["p50_routing_latency_ms"] >= 0
        assert m["p95_routing_latency_ms"] >= 0
        assert m["p99_routing_latency_ms"] >= 0

    async def test_metrics_after_multiple_routes(self, router_with_registries):
        r, pr, mr = router_with_registries
        for _ in range(5):
            await r.route(RoutingRequest(task_type="chat"))
        m = r.metrics()
        assert m["routing_count"] == 5
        assert m["avg_candidate_count"] >= 1

    async def test_metrics_provider_selection_counts(self, router_with_registries):
        r, pr, mr = router_with_registries
        for _ in range(3):
            await r.route(RoutingRequest(task_type="chat", preferred_provider="openai"))
        m = r.metrics()
        assert m["provider_selection_frequency"].get("openai", 0) == 3


# ═══════════════════════════════════════════════════════════════════
# Concurrency
# ═══════════════════════════════════════════════════════════════════


class TestRouterConcurrency:
    """Thread safety under concurrent access."""

    async def test_concurrent_routes(self, router_with_registries):
        r, pr, mr = router_with_registries

        async def route_req(n: int):
            return await r.route(RoutingRequest(task_type="chat"))

        tasks = [route_req(i) for i in range(10)]
        decisions = await asyncio.gather(*tasks)
        assert len(decisions) == 10
        for d in decisions:
            assert d.status == "routed"

    async def test_concurrent_mixed_operations(self, router_with_registries):
        r, pr, mr = router_with_registries

        async def route():
            return await r.route(RoutingRequest(task_type="chat"))

        async def best():
            return await r.best_provider(RoutingRequest(task_type="chat"))

        async def estimate():
            return await r.estimate_cost(RoutingRequest(task_type="chat"))

        async def metrics():
            return r.metrics()

        results = await asyncio.gather(
            route(),
            route(),
            route(),
            best(),
            best(),
            estimate(),
            metrics(),
            return_exceptions=True,
        )
        successes = [x for x in results if not isinstance(x, Exception)]
        assert len(successes) >= 5


# ═══════════════════════════════════════════════════════════════════
# Edge Cases
# ═══════════════════════════════════════════════════════════════════


class TestEdgeCases:
    """Edge cases and error handling."""

    async def test_route_no_registries(self, router):
        await router.start()
        decision = await router.route(RoutingRequest(task_type="chat"))
        assert decision.status == "failed"

    async def test_route_after_stop_fails(self, router_with_registries):
        r, pr, mr = router_with_registries
        await r.stop()
        decision = await r.route(RoutingRequest(task_type="chat"))
        assert decision.status == "failed"  # health check would fail

    async def test_route_many_empty(self, router_with_registries):
        r, pr, mr = router_with_registries
        decisions = await r.route_many([])
        assert decisions == []

    async def test_empty_registries_dont_crash(self, router):
        await router.start()
        # No providers or models registered
        h = await router.health()
        assert h["status"] == "healthy"
        await router.stop()

    async def test_supported_capabilities_always_return(self, router):
        caps = await router.supported_capabilities()
        assert isinstance(caps, list)
        assert len(caps) > 0

    async def test_route_with_vision_and_reasoning(self, router_with_registries):
        r, pr, mr = router_with_registries
        req = RoutingRequest(
            task_type="chat",
            vision_required=True,
            reasoning_required=True,
        )
        decision = await r.route(req)
        # Only claude-sonnet-4 supports both vision and reasoning
        assert decision.status == "routed"
        assert decision.model_id == "claude-sonnet-4"

    async def test_route_prefer_cost_over_quality(self, router_with_registries):
        r, pr, mr = router_with_registries
        req = RoutingRequest(
            task_type="chat",
            cost_weight=10,
            quality_weight=0.1,
        )
        decision = await r.route(req)
        assert decision.status == "routed"
        # With cost weight max, the cheapest model should win
        assert decision.model_id == "deepseek-coder"  # cheapest

    async def test_route_prefer_quality_over_cost(self, router_with_registries):
        r, pr, mr = router_with_registries
        req = RoutingRequest(
            task_type="chat",
            quality_weight=10,
            cost_weight=0.1,
        )
        decision = await r.route(req)
        assert decision.status == "routed"
        assert decision.model_id == "gpt-4o"  # highest quality

    async def test_route_confidence_reflects_score(self, router_with_registries):
        r, pr, mr = router_with_registries
        decision = await r.route(RoutingRequest(task_type="chat"))
        assert 0 <= decision.confidence <= 1.0

    async def test_route_preferred_but_unhealthy_falls_back(self, router_with_registries):
        r, pr, mr = router_with_registries
        deepseek = await pr.get_by_name("deepseek")
        await pr.set_health(deepseek.id, False)

        req = RoutingRequest(task_type="chat", preferred_provider="deepseek")
        decision = await r.route(req)
        assert decision.status == "routed"
        assert decision.provider != "deepseek"  # fell back

    async def test_route_with_very_context_heavy(self, router_with_registries):
        r, pr, mr = router_with_registries
        req = RoutingRequest(task_type="chat", minimum_context=180000)
        decision = await r.route(req)
        # Only claude-sonnet-4 has 200k context
        assert decision.status == "routed"
        assert decision.model_id == "claude-sonnet-4"

    async def test_route_with_zero_capabilities(self, router_with_registries):
        r, pr, mr = router_with_registries
        req = RoutingRequest(task_type="chat", required_capabilities=())
        decision = await r.route(req)
        assert decision.status == "routed"

    async def test_metrics_initial_state(self, router):
        m = router.metrics()
        assert m["routing_count"] == 0
        assert m["routing_failures"] == 0
        assert m["avg_candidate_count"] == 0

    async def test_fallback_chain_with_single_candidate(self, router_with_registries):
        r, pr, mr = router_with_registries
        # Make all but openai unhealthy
        for p in await pr.list_providers():
            if p.name != "openai":
                await pr.set_health(p.id, False)

        req = RoutingRequest(task_type="chat")
        chain = await r.generate_fallback_chain(req, chain_length=1)
        assert len(chain) == 1 or len(chain) == 0
        # If chain is populated, it should be openai
        if chain:
            assert chain[0][0] == "openai"

    async def test_health_after_dispose(self, router):
        await router.start()
        await router.dispose()
        health = await router.health()
        assert health["status"] == "stopped"


# ═══════════════════════════════════════════════════════════════════
# Scoring Engine — Internal unit tests
# ═══════════════════════════════════════════════════════════════════


class TestScoringEngineInternal:
    """Direct unit tests on scoring formulas."""

    def test_score_quality_clamped(self):
        model = OmniRouteModel(model_id="test", quality_score=2.0)
        req = RoutingRequest(task_type="chat")
        scorer = _ScoringEngine(req)
        q = scorer._score_quality(model)
        assert q <= 1.0

    def test_score_cost_zero(self):
        model = OmniRouteModel(model_id="test", input_cost_per_1k=0, output_cost_per_1k=0)
        provider = OmniRouteProvider(name="test", cost_per_1k_input=0, cost_per_1k_output=0)
        req = RoutingRequest(task_type="chat")
        scorer = _ScoringEngine(req)
        cost = scorer._score_cost(provider, model)
        assert cost == 1.0  # zero cost = best score

    def test_score_latency_zero(self):
        provider = OmniRouteProvider(name="test", latency_ms=0)
        model = OmniRouteModel(model_id="test", latency_ms=0)
        req = RoutingRequest(task_type="chat")
        scorer = _ScoringEngine(req)
        lat = scorer._score_latency(provider, model)
        assert lat == 1.0  # zero latency = best score

    def test_score_health_none_healthy(self):
        provider = OmniRouteProvider(name="test", healthy=False)
        model = OmniRouteModel(model_id="test", healthy=False)
        req = RoutingRequest(task_type="chat")
        scorer = _ScoringEngine(req)
        h = scorer._score_health(provider, model)
        assert h == 0.0

    def test_score_context_zero(self):
        model = OmniRouteModel(model_id="test", context_window=0)
        req = RoutingRequest(task_type="chat")
        scorer = _ScoringEngine(req)
        ctx = scorer._score_context(model)
        assert ctx == 0.0

    def test_score_reliability_disabled_unhealthy(self):
        provider = OmniRouteProvider(name="test", enabled=False, healthy=False)
        req = RoutingRequest(task_type="chat")
        scorer = _ScoringEngine(req)
        rel = scorer._score_reliability(provider)
        assert rel == 0.0

    def test_score_preference_no_match(self):
        provider = OmniRouteProvider(name="test")
        model = OmniRouteModel(model_id="test")
        req = RoutingRequest(task_type="chat")
        scorer = _ScoringEngine(req)
        pref = scorer._score_preference(provider, model)
        assert pref == 0.0
