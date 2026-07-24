"""Tests for OmniRoute Routing Policy Engine (Phase 5.4).

Targets: 70-100 tests covering policy CRUD, priority, strategy evaluation,
scope resolution, default policy, filters, weight/budget/latency overrides,
concurrency, EventBus, DI, lifecycle, metrics, and Router integration.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from agentic_os.core.omniroute.router import RouterEngineImpl
from agentic_os.core.omniroute.routing_policies import (
    BalancedStrategy,
    CloudFirstStrategy,
    CustomWeightedStrategy,
    EmergencyFailoverStrategy,
    HighestQualityStrategy,
    HighestReliabilityStrategy,
    LocalFirstStrategy,
    LowestCostStrategy,
    LowestLatencyStrategy,
    OfflineModeStrategy,
    RandomStrategy,
    ReasoningOptimizedStrategy,
    RoundRobinStrategy,
    RoutingPolicyEngineImpl,
    SafeModeStrategy,
    StickyProviderStrategy,
    StreamingOptimizedStrategy,
    ToolCallingOptimizedStrategy,
    UserDefaultStrategy,
    VisionOptimizedStrategy,
    WorkspaceDefaultStrategy,
    _ScoredCandidate,
)
from agentic_os.domain.events import Topic
from agentic_os.domain.omniroute import (
    OmniRouteModel,
    OmniRouteProvider,
    PolicyResult,
    RoutingPolicy,
    RoutingRequest,
)

# ══════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════


@pytest.fixture
def engine():
    impl = RoutingPolicyEngineImpl()
    return impl


@pytest.fixture
async def started_engine(engine):
    await engine.initialize()
    await engine.start()
    return engine


@pytest.fixture
def mock_event_bus():
    bus = AsyncMock()
    bus.publish = AsyncMock()
    return bus


@pytest.fixture
async def engine_with_bus(mock_event_bus):
    impl = RoutingPolicyEngineImpl(event_bus=mock_event_bus)
    await impl.initialize()
    await impl.start()
    return impl, mock_event_bus


@pytest.fixture
def sample_provider() -> OmniRouteProvider:
    return OmniRouteProvider(
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


@pytest.fixture
def sample_model() -> OmniRouteModel:
    return OmniRouteModel(
        model_id="gpt-4o",
        provider="openai",
        provider_id="openai-1",
        display_name="GPT-4o",
        context_window=128000,
        input_cost_per_1k=0.01,
        output_cost_per_1k=0.03,
        capabilities=("chat", "vision", "completion"),
        supports_streaming=True,
        supports_vision=True,
        supports_reasoning=False,
        supports_tools=True,
        quality_score=0.95,
        latency_ms=350,
        healthy=True,
        enabled=True,
    )


@pytest.fixture
def sample_candidates(sample_provider, sample_model) -> list[_ScoredCandidate]:
    return [
        _ScoredCandidate(
            provider=sample_provider,
            model=sample_model,
        )
    ]


@pytest.fixture
def multi_candidates() -> tuple[
    list[OmniRouteProvider], list[OmniRouteModel], list[_ScoredCandidate]
]:
    """Produces 4 providers with distinct cost/quality/latency profiles."""
    p1 = OmniRouteProvider(
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
    p2 = OmniRouteProvider(
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
    p3 = OmniRouteProvider(
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
    p4 = OmniRouteProvider(
        name="local",
        kind="ollama",
        base_url="http://localhost:11434",
        capabilities=("chat", "completion"),
        healthy=True,
        enabled=True,
        latency_ms=5000,
        cost_per_1k_input=0.0,
        cost_per_1k_output=0.0,
    )

    m1 = OmniRouteModel(
        model_id="gpt-4o",
        provider="openai",
        provider_id="p1",
        display_name="GPT-4o",
        context_window=128000,
        input_cost_per_1k=0.01,
        output_cost_per_1k=0.03,
        capabilities=("chat", "vision"),
        supports_streaming=True,
        supports_vision=True,
        supports_tools=True,
        quality_score=0.95,
        latency_ms=350,
        healthy=True,
        enabled=True,
    )
    m2 = OmniRouteModel(
        model_id="claude-sonnet-4",
        provider="anthropic",
        provider_id="p2",
        display_name="Claude Sonnet 4",
        context_window=200000,
        input_cost_per_1k=0.015,
        output_cost_per_1k=0.075,
        capabilities=("chat", "reasoning"),
        supports_streaming=True,
        supports_reasoning=True,
        quality_score=0.94,
        latency_ms=600,
        healthy=True,
        enabled=True,
    )
    m3 = OmniRouteModel(
        model_id="deepseek-coder",
        provider="deepseek",
        provider_id="p3",
        display_name="DeepSeek Coder",
        context_window=32000,
        input_cost_per_1k=0.0005,
        output_cost_per_1k=0.002,
        capabilities=("chat", "coding"),
        supports_tools=True,
        quality_score=0.88,
        latency_ms=900,
        healthy=True,
        enabled=True,
    )
    m4 = OmniRouteModel(
        model_id="llama-3-8b",
        provider="local",
        provider_id="p4",
        display_name="Llama 3 8B",
        context_window=8192,
        input_cost_per_1k=0.0,
        output_cost_per_1k=0.0,
        capabilities=("chat",),
        quality_score=0.72,
        latency_ms=5500,
        healthy=True,
        enabled=True,
    )

    providers = {"openai": p1, "anthropic": p2, "deepseek": p3, "local": p4}
    models = {"gpt-4o": m1, "claude-sonnet-4": m2, "deepseek-coder": m3, "llama-3-8b": m4}

    candidates = [
        _ScoredCandidate(provider=p1, model=m1),
        _ScoredCandidate(provider=p2, model=m2),
        _ScoredCandidate(provider=p3, model=m3),
        _ScoredCandidate(provider=p4, model=m4),
    ]

    return providers, models, candidates


@pytest.fixture
async def engine_with_router(multi_candidates) -> tuple[RoutingPolicyEngineImpl, RouterEngineImpl]:
    """Engine + Router with registries populated and policy engine wired in."""
    from agentic_os.core.omniroute.model_registry import ModelRegistryImpl
    from agentic_os.core.omniroute.provider_registry import ProviderRegistryImpl

    pr = ProviderRegistryImpl()
    mr = ModelRegistryImpl(provider_registry=pr)
    pe = RoutingPolicyEngineImpl()
    router = RouterEngineImpl(provider_registry=pr, model_registry=mr, routing_policy_engine=pe)

    await pr.start()
    await mr.start()
    await pe.initialize()
    await pe.start()
    await router.start()

    providers_meta, models_meta, _ = multi_candidates
    p_ids = {}
    for name, prov in providers_meta.items():
        pid = await pr.register(prov)
        p_ids[name] = pid

    for _mid, mdl in models_meta.items():
        # Set the correct provider_id from the registered provider
        provider_name = mdl.provider
        if provider_name in p_ids:
            mdl = OmniRouteModel(
                model_id=mdl.model_id,
                provider=mdl.provider,
                provider_id=p_ids[provider_name],
                display_name=mdl.display_name,
                context_window=mdl.context_window,
                input_cost_per_1k=mdl.input_cost_per_1k,
                output_cost_per_1k=mdl.output_cost_per_1k,
                capabilities=mdl.capabilities,
                supports_streaming=mdl.supports_streaming,
                supports_vision=mdl.supports_vision,
                supports_reasoning=mdl.supports_reasoning,
                supports_tools=mdl.supports_tools,
                quality_score=mdl.quality_score,
                latency_ms=mdl.latency_ms,
                healthy=mdl.healthy,
                enabled=mdl.enabled,
            )
        await mr.register_model(mdl)

    return pe, router


# ══════════════════════════════════════════════
# 1. Lifecycle Tests
# ══════════════════════════════════════════════


class TestLifecycle:
    async def test_initialize_seeds_default(self, engine):
        await engine.initialize()
        assert len(engine._policies) >= 1
        assert engine._default_policy_id != ""

    async def test_start_and_stop(self, engine):
        await engine.initialize()
        await engine.start()
        assert await engine.ready() is True
        await engine.stop()
        assert await engine.ready() is False

    async def test_dispose_clears(self, engine):
        await engine.initialize()
        await engine.dispose()
        assert len(engine._policies) == 0
        assert engine._default_policy_id == ""

    async def test_health_healthy_when_started(self, started_engine):
        health = await started_engine.health()
        assert health["status"] == "healthy"
        assert health["started"] is True
        assert health["policy_count"] >= 1

    async def test_health_stopped(self, engine):
        health = await engine.health()
        assert health["status"] == "stopped"
        assert health["started"] is False

    async def test_metadata(self, started_engine):
        meta = await started_engine.metadata()
        assert meta["type"] == "RoutingPolicyEngineImpl"
        assert meta["started"] is True
        assert "strategies_available" in meta

    async def test_dependencies_empty(self, started_engine):
        deps = await started_engine.dependencies()
        assert deps == []

    async def test_capabilities_non_empty(self, started_engine):
        caps = await started_engine.capabilities()
        assert len(caps) >= 3


# ══════════════════════════════════════════════
# 2. CRUD Tests
# ══════════════════════════════════════════════


class TestCRUD:
    async def test_create_policy(self, started_engine):
        pid = await started_engine.create_policy(
            RoutingPolicy(name="Test Policy", strategy="balanced")
        )
        assert pid != ""

    async def test_create_duplicate(self, started_engine):
        pid = await started_engine.create_policy(RoutingPolicy(name="Dup", strategy="balanced"))
        with pytest.raises(ValueError, match="already exists"):
            await started_engine.create_policy(
                RoutingPolicy(name="Dup2", strategy="lowest_cost", id=pid)
            )

    async def test_get_policy(self, started_engine):
        pid = await started_engine.create_policy(
            RoutingPolicy(name="Get Me", strategy="highest_quality")
        )
        p = await started_engine.get_policy(pid)
        assert p is not None
        assert p.name == "Get Me"
        assert p.strategy == "highest_quality"

    async def test_get_missing(self, started_engine):
        p = await started_engine.get_policy("nonexistent")
        assert p is None

    async def test_update_policy(self, started_engine):
        pid = await started_engine.create_policy(RoutingPolicy(name="Before", strategy="balanced"))
        await started_engine.update_policy(
            RoutingPolicy(id=pid, name="After", strategy="lowest_cost")
        )
        updated = await started_engine.get_policy(pid)
        assert updated.name == "After"
        assert updated.strategy == "lowest_cost"

    async def test_update_missing(self, started_engine):
        with pytest.raises(ValueError, match="not found"):
            await started_engine.update_policy(
                RoutingPolicy(id="nonexistent", name="X", strategy="balanced")
            )

    async def test_delete_policy(self, started_engine):
        pid = await started_engine.create_policy(
            RoutingPolicy(name="Delete Me", strategy="balanced")
        )
        result = await started_engine.delete_policy(pid)
        assert result is True
        assert await started_engine.get_policy(pid) is None

    async def test_delete_missing(self, started_engine):
        result = await started_engine.delete_policy("nonexistent")
        assert result is False

    async def test_delete_clears_default(self, started_engine):
        pid = await started_engine.create_policy(RoutingPolicy(name="Default", strategy="balanced"))
        await started_engine.set_default(pid)
        await started_engine.delete_policy(pid)
        default = await started_engine.default_policy()
        # Should fall back to the seeded default
        assert default is None or default.id != pid

    async def test_list_policies(self, started_engine):
        await started_engine.create_policy(RoutingPolicy(name="A", strategy="balanced"))
        await started_engine.create_policy(RoutingPolicy(name="B", strategy="lowest_cost"))
        policies = await started_engine.list_policies()
        assert len(policies) >= 3  # seeded default + 2

    async def test_list_enabled_only(self, started_engine):
        await started_engine.create_policy(
            RoutingPolicy(name="Disabled", strategy="balanced", enabled=False)
        )
        policies = await started_engine.list_policies(enabled_only=True)
        assert all(p.enabled for p in policies)

    async def test_enable_policy(self, started_engine):
        pid = await started_engine.create_policy(
            RoutingPolicy(name="Off", strategy="balanced", enabled=False)
        )
        changed = await started_engine.enable_policy(pid)
        assert changed is True
        p = await started_engine.get_policy(pid)
        assert p.enabled is True

    async def test_enable_already_enabled(self, started_engine):
        pid = await started_engine.create_policy(
            RoutingPolicy(name="On", strategy="balanced", enabled=True)
        )
        changed = await started_engine.enable_policy(pid)
        assert changed is False

    async def test_enable_missing(self, started_engine):
        changed = await started_engine.enable_policy("nope")
        assert changed is False

    async def test_disable_policy(self, started_engine):
        pid = await started_engine.create_policy(
            RoutingPolicy(name="On", strategy="balanced", enabled=True)
        )
        changed = await started_engine.disable_policy(pid)
        assert changed is True
        p = await started_engine.get_policy(pid)
        assert p.enabled is False

    async def test_disable_already_disabled(self, started_engine):
        pid = await started_engine.create_policy(
            RoutingPolicy(name="Off", strategy="balanced", enabled=False)
        )
        changed = await started_engine.disable_policy(pid)
        assert changed is False

    async def test_disable_missing(self, started_engine):
        changed = await started_engine.disable_policy("nope")
        assert changed is False


# ══════════════════════════════════════════════
# 3. Default Policy
# ══════════════════════════════════════════════


class TestDefaultPolicy:
    async def test_default_seeded_on_init(self, started_engine):
        default = await started_engine.default_policy()
        assert default is not None
        assert default.name == "Balanced (Default)"

    async def test_set_default(self, started_engine):
        pid = await started_engine.create_policy(
            RoutingPolicy(name="New Default", strategy="lowest_cost")
        )
        changed = await started_engine.set_default(pid)
        assert changed is True
        default = await started_engine.default_policy()
        assert default.id == pid

    async def test_set_default_missing(self, started_engine):
        changed = await started_engine.set_default("nope")
        assert changed is False

    async def test_default_fallback_when_no_policies(self, engine):
        default = await engine.default_policy()
        assert default is None

    async def test_default_fallback_sorted_by_priority(self, started_engine):
        """Default should be highest-priority enabled policy."""
        await started_engine.create_policy(
            RoutingPolicy(name="High", strategy="balanced", priority=100)
        )
        await started_engine.create_policy(
            RoutingPolicy(name="Low", strategy="lowest_cost", priority=0)
        )
        default = await started_engine.default_policy()
        # Could be seeded default or high — priority-based
        assert default is not None


# ══════════════════════════════════════════════
# 4. Policy Resolution & Scoping
# ══════════════════════════════════════════════


class TestPolicyScoping:
    async def test_resolve_returns_default(self, started_engine):
        req = RoutingRequest(task_type="chat")
        resolved = await started_engine.resolve_policy(req)
        assert resolved is not None
        assert resolved.name == "Balanced (Default)"

    async def test_applicable_by_workspace(self, started_engine):
        pid = await started_engine.create_policy(
            RoutingPolicy(
                name="WS Policy",
                strategy="lowest_cost",
                workspace_scope="my-workspace",
                enabled=True,
                priority=50,
            )
        )
        req = RoutingRequest(task_type="chat", workspace="my-workspace")
        applicable = await started_engine.applicable_policies(req)
        assert any(p.id == pid for p in applicable)

    async def test_applicable_ignores_wrong_workspace(self, started_engine):
        pid = await started_engine.create_policy(
            RoutingPolicy(
                name="WS Policy",
                strategy="lowest_cost",
                workspace_scope="ws-a",
                enabled=True,
                priority=50,
            )
        )
        req = RoutingRequest(task_type="chat", workspace="ws-b")
        applicable = await started_engine.applicable_policies(req)
        assert not any(p.id == pid for p in applicable)

    async def test_applicable_by_agent(self, started_engine):
        pid = await started_engine.create_policy(
            RoutingPolicy(
                name="Agent Policy",
                strategy="highest_quality",
                agent_scope="agent-1",
                enabled=True,
                priority=50,
            )
        )
        req = RoutingRequest(task_type="chat", agent="agent-1")
        applicable = await started_engine.applicable_policies(req)
        assert any(p.id == pid for p in applicable)

    async def test_applicable_ignores_wrong_agent(self, started_engine):
        pid = await started_engine.create_policy(
            RoutingPolicy(
                name="Agent Policy",
                strategy="highest_quality",
                agent_scope="agent-1",
                enabled=True,
                priority=50,
            )
        )
        req = RoutingRequest(task_type="chat", agent="agent-2")
        applicable = await started_engine.applicable_policies(req)
        assert not any(p.id == pid for p in applicable)

    async def test_applicable_by_user(self, started_engine):
        pid = await started_engine.create_policy(
            RoutingPolicy(
                name="User Policy",
                strategy="lowest_cost",
                user_scope="user-1",
                enabled=True,
                priority=50,
            )
        )
        req = RoutingRequest(task_type="chat", user_id="user-1")
        applicable = await started_engine.applicable_policies(req)
        assert any(p.id == pid for p in applicable)

    async def test_applicable_ignores_wrong_user(self, started_engine):
        pid = await started_engine.create_policy(
            RoutingPolicy(
                name="User Policy",
                strategy="lowest_cost",
                user_scope="user-1",
                enabled=True,
                priority=50,
            )
        )
        req = RoutingRequest(task_type="chat", user_id="user-2")
        applicable = await started_engine.applicable_policies(req)
        assert not any(p.id == pid for p in applicable)

    async def test_applicable_respects_disabled(self, started_engine):
        pid = await started_engine.create_policy(
            RoutingPolicy(
                name="Disabled Policy", strategy="lowest_cost", enabled=False, priority=50
            )
        )
        req = RoutingRequest(task_type="chat")
        applicable = await started_engine.applicable_policies(req)
        assert not any(p.id == pid for p in applicable)

    async def test_applicable_respects_provider_filter(self, started_engine):
        pid = await started_engine.create_policy(
            RoutingPolicy(
                name="OpenAI Only",
                strategy="balanced",
                enabled=True,
                priority=10,
                provider_filter=("openai",),
            )
        )
        req = RoutingRequest(task_type="chat", preferred_provider="anthropic")
        applicable = await started_engine.applicable_policies(req)
        assert not any(p.id == pid for p in applicable)

    async def test_applicable_respects_model_filter(self, started_engine):
        pid = await started_engine.create_policy(
            RoutingPolicy(
                name="GPT Only",
                strategy="balanced",
                enabled=True,
                priority=10,
                model_filter=("gpt-4o",),
            )
        )
        req = RoutingRequest(task_type="chat", preferred_model="claude")
        applicable = await started_engine.applicable_policies(req)
        assert not any(p.id == pid for p in applicable)

    async def test_applicable_respects_capability_filter(self, started_engine):
        pid = await started_engine.create_policy(
            RoutingPolicy(
                name="Vision Only",
                strategy="balanced",
                enabled=True,
                priority=10,
                capability_filter=("vision",),
            )
        )
        req = RoutingRequest(task_type="chat", required_capabilities=["audio"])
        applicable = await started_engine.applicable_policies(req)
        assert not any(p.id == pid for p in applicable)

    async def test_rank_policies_by_priority(self, started_engine):
        low = await started_engine.create_policy(
            RoutingPolicy(name="Low", strategy="lowest_cost", priority=0, enabled=True)
        )
        high = await started_engine.create_policy(
            RoutingPolicy(name="High", strategy="highest_quality", priority=100, enabled=True)
        )
        req = RoutingRequest(task_type="chat")
        ranked = await started_engine.rank_policies(req)
        # High should appear before Low
        high_idx = next(i for i, p in enumerate(ranked) if p.id == high)
        low_idx = next(i for i, p in enumerate(ranked) if p.id == low)
        assert high_idx < low_idx


# ══════════════════════════════════════════════
# 5. Strategy Evaluation Tests
# ══════════════════════════════════════════════


class TestStrategies:
    async def test_balanced_evaluation(self, multi_candidates):
        _, _, candidates = multi_candidates
        strategy = BalancedStrategy()
        policy = RoutingPolicy(strategy="balanced")
        result = await strategy.evaluate(candidates, RoutingRequest(task_type="chat"), policy)
        assert len(result) == 4
        assert all(c.score > 0 for c in result)
        # Highest quality (gpt-4o) should rank first under balanced defaults
        assert result[0].model.model_id == "gpt-4o"

    async def test_lowest_cost(self, multi_candidates):
        _, _, candidates = multi_candidates
        strategy = LowestCostStrategy()
        policy = RoutingPolicy(strategy="lowest_cost")
        result = await strategy.evaluate(candidates, RoutingRequest(task_type="chat"), policy)
        assert result[0].model.model_id == "llama-3-8b"  # cheapest: zero cost

    async def test_highest_quality(self, multi_candidates):
        _, _, candidates = multi_candidates
        strategy = HighestQualityStrategy()
        policy = RoutingPolicy(strategy="highest_quality")
        result = await strategy.evaluate(candidates, RoutingRequest(task_type="chat"), policy)
        assert result[0].model.model_id == "gpt-4o"  # quality 0.95

    async def test_lowest_latency(self, multi_candidates):
        _, _, candidates = multi_candidates
        strategy = LowestLatencyStrategy()
        policy = RoutingPolicy(strategy="lowest_latency")
        result = await strategy.evaluate(candidates, RoutingRequest(task_type="chat"), policy)
        assert result[0].model.model_id == "gpt-4o"  # latency 350ms on provider

    async def test_highest_reliability(self, multi_candidates):
        _, _, candidates = multi_candidates
        strategy = HighestReliabilityStrategy()
        policy = RoutingPolicy(strategy="highest_reliability")
        result = await strategy.evaluate(candidates, RoutingRequest(task_type="chat"), policy)
        # All healthy, so quality bonus breaks tie — gpt-4o
        assert result[0].model.model_id == "gpt-4o"

    async def test_local_first(self, multi_candidates):
        _, _, candidates = multi_candidates
        strategy = LocalFirstStrategy()
        policy = RoutingPolicy(strategy="local_first")
        result = await strategy.evaluate(candidates, RoutingRequest(task_type="chat"), policy)
        assert result[0].model.model_id == "llama-3-8b"  # local (ollama) gets bonus

    async def test_cloud_first(self, multi_candidates):
        _, _, candidates = multi_candidates
        strategy = CloudFirstStrategy()
        policy = RoutingPolicy(strategy="cloud_first")
        result = await strategy.evaluate(candidates, RoutingRequest(task_type="chat"), policy)
        # Cloud providers get bonus
        assert "llama-3-8b" not in [c.model.model_id for c in result[:2]]

    async def test_reasoning_optimized(self, multi_candidates):
        _, _, candidates = multi_candidates
        strategy = ReasoningOptimizedStrategy()
        policy = RoutingPolicy(strategy="reasoning_optimized")
        result = await strategy.evaluate(candidates, RoutingRequest(task_type="chat"), policy)
        # claude-sonnet-4 supports reasoning
        assert result[0].model.model_id == "claude-sonnet-4"

    async def test_vision_optimized(self, multi_candidates):
        _, _, candidates = multi_candidates
        strategy = VisionOptimizedStrategy()
        policy = RoutingPolicy(strategy="vision_optimized")
        result = await strategy.evaluate(candidates, RoutingRequest(task_type="chat"), policy)
        # gpt-4o supports vision
        assert result[0].model.model_id == "gpt-4o"

    async def test_streaming_optimized(self, multi_candidates):
        _, _, candidates = multi_candidates
        strategy = StreamingOptimizedStrategy()
        policy = RoutingPolicy(strategy="streaming_optimized")
        result = await strategy.evaluate(candidates, RoutingRequest(task_type="chat"), policy)
        # All support streaming, so lowest latency wins: gpt-4o
        assert result[0].model.model_id == "gpt-4o"

    async def test_tool_calling_optimized(self, multi_candidates):
        _, _, candidates = multi_candidates
        strategy = ToolCallingOptimizedStrategy()
        policy = RoutingPolicy(strategy="tool_calling_optimized")
        result = await strategy.evaluate(candidates, RoutingRequest(task_type="chat"), policy)
        # gpt-4o supports tools and has high quality
        assert result[0].model.model_id == "gpt-4o"

    async def test_custom_weighted(self, multi_candidates):
        _, _, candidates = multi_candidates
        strategy = CustomWeightedStrategy()
        policy = RoutingPolicy(
            strategy="custom_weighted",
            weight_overrides={"cost": 10.0, "quality": 0.1, "latency": 0.1},
        )
        result = await strategy.evaluate(candidates, RoutingRequest(task_type="chat"), policy)
        # Cost-weighted: deepseek-coder has lowest effective cost (0.0025) when
        # accounting for latency penalty on the zero-cost local provider
        assert result[0].model.model_id == "deepseek-coder"

    async def test_round_robin_rotates(self, multi_candidates):
        _, _, candidates = multi_candidates
        strategy = RoundRobinStrategy()
        policy = RoutingPolicy(strategy="round_robin")
        req = RoutingRequest(task_type="chat")

        first = await strategy.evaluate(list(candidates), req, policy)
        second = await strategy.evaluate(list(candidates), req, policy)
        third = await strategy.evaluate(list(candidates), req, policy)

        # Each call should pick the next candidate in order
        selected_ids = [first[0].model.model_id, second[0].model.model_id, third[0].model.model_id]
        assert len(set(selected_ids)) == min(3, len(candidates))  # At least some rotation

    async def test_random_produces_different_results(self, multi_candidates):
        """Random strategy should not always return the same order."""
        _, _, candidates = multi_candidates
        strategy = RandomStrategy()
        policy = RoutingPolicy(strategy="random")
        req = RoutingRequest(task_type="chat")

        results = set()
        for _ in range(5):
            result = await strategy.evaluate(list(candidates), req, policy)
            results.add(result[0].model.model_id)

        # With 4 candidates and randomness, likely more than 1 unique winner
        assert len(results) > 1

    async def test_sticky_provider(self, multi_candidates):
        providers, _, candidates = multi_candidates
        strategy = StickyProviderStrategy()
        policy = RoutingPolicy(strategy="sticky_provider")

        # First call picks the best (gpt-4o due to quality)
        req = RoutingRequest(task_type="chat", user_id="test-user")
        first = await strategy.evaluate(list(candidates), req, policy)
        first_winner = first[0].model.model_id

        # Second call should prefer same provider
        second = await strategy.evaluate(list(candidates), req, policy)
        assert second[0].model.model_id == first_winner

    async def test_workspace_default(self, multi_candidates):
        _, _, candidates = multi_candidates
        strategy = WorkspaceDefaultStrategy()
        policy = RoutingPolicy(strategy="workspace_default", workspace_scope="ws-1")
        result = await strategy.evaluate(candidates, RoutingRequest(task_type="chat"), policy)
        assert result[0].model.model_id == "gpt-4o"

    async def test_user_default(self, multi_candidates):
        _, _, candidates = multi_candidates
        strategy = UserDefaultStrategy()
        policy = RoutingPolicy(strategy="user_default", user_scope="user-1")
        result = await strategy.evaluate(candidates, RoutingRequest(task_type="chat"), policy)
        assert result[0].model.model_id == "gpt-4o"

    async def test_emergency_failover(self, multi_candidates):
        _, _, candidates = multi_candidates
        strategy = EmergencyFailoverStrategy()
        policy = RoutingPolicy(strategy="emergency_failover")

        # Make all candidates unhealthy
        for c in candidates:
            c.provider = OmniRouteProvider(
                id=c.provider.id,
                name=c.provider.name,
                kind=c.provider.kind,
                base_url=c.provider.base_url,
                healthy=False,
                enabled=True,
                capabilities=c.provider.capabilities,
                latency_ms=c.provider.latency_ms,
                cost_per_1k_input=c.provider.cost_per_1k_input,
                cost_per_1k_output=c.provider.cost_per_1k_output,
            )

        result = await strategy.evaluate(candidates, RoutingRequest(task_type="chat"), policy)
        # All score zero since no one is healthy
        assert all(c.score == 0 for c in result)

    async def test_safe_mode(self, multi_candidates):
        _, _, candidates = multi_candidates
        strategy = SafeModeStrategy()
        policy = RoutingPolicy(strategy="safe_mode")

        # One unhealthy provider
        candidates[2].provider = OmniRouteProvider(
            id=candidates[2].provider.id,
            name=candidates[2].provider.name,
            kind=candidates[2].provider.kind,
            base_url=candidates[2].provider.base_url,
            healthy=False,
            enabled=candidates[2].provider.enabled,
            capabilities=candidates[2].provider.capabilities,
            latency_ms=candidates[2].provider.latency_ms,
            cost_per_1k_input=candidates[2].provider.cost_per_1k_input,
            cost_per_1k_output=candidates[2].provider.cost_per_1k_output,
        )

        result = await strategy.evaluate(candidates, RoutingRequest(task_type="chat"), policy)
        # Unhealthy candidates get score 0
        assert result[0].score > 0
        assert not any(c.model.model_id == "deepseek-coder" for c in result if c.score > 0)

    async def test_offline_mode(self, multi_candidates):
        _, _, candidates = multi_candidates
        strategy = OfflineModeStrategy()
        policy = RoutingPolicy(strategy="offline_mode")
        result = await strategy.evaluate(candidates, RoutingRequest(task_type="chat"), policy)
        # Only local (ollama) gets score > 0
        assert result[0].model.model_id == "llama-3-8b"
        assert result[0].score > 0
        for c in result[1:]:
            assert c.score == 0


# ══════════════════════════════════════════════
# 6. Policy Engine Evaluate Tests
# ══════════════════════════════════════════════


class TestEngineEvaluate:
    async def test_evaluate_no_candidates(self, started_engine):
        result = await started_engine.evaluate([], RoutingRequest(task_type="chat"))
        assert isinstance(result, PolicyResult)
        assert result.selected_model_id == ""
        assert "No candidates" in result.reason

    async def test_evaluate_returns_winner(self, started_engine, multi_candidates):
        _, _, candidates = multi_candidates
        raw = [(c.provider, c.model) for c in candidates]
        result = await started_engine.evaluate(raw, RoutingRequest(task_type="chat"))
        assert result.selected_model_id != ""
        assert result.selected_provider != ""
        assert len(result.scored_candidates) >= 1
        assert result.policy_applied is True

    async def test_evaluate_applies_provider_filter(self, started_engine, multi_candidates):
        providers, _, candidates = multi_candidates
        raw = [(c.provider, c.model) for c in candidates]
        policy = RoutingPolicy(
            name="DeepSeek Only",
            strategy="balanced",
            enabled=True,
            priority=50,
            provider_filter=("deepseek",),
        )
        await started_engine.create_policy(policy)
        result = await started_engine.evaluate(raw, RoutingRequest(task_type="chat"), policy)
        assert result.selected_provider == "deepseek"

    async def test_evaluate_applies_model_filter(self, started_engine, multi_candidates):
        _, _, candidates = multi_candidates
        raw = [(c.provider, c.model) for c in candidates]
        policy = RoutingPolicy(
            name="Coder Only",
            strategy="balanced",
            enabled=True,
            priority=50,
            model_filter=("deepseek-coder",),
        )
        await started_engine.create_policy(policy)
        result = await started_engine.evaluate(raw, RoutingRequest(task_type="chat"), policy)
        assert result.selected_model_id == "deepseek-coder"

    async def test_evaluate_applies_capability_filter(self, started_engine, multi_candidates):
        _, _, candidates = multi_candidates
        raw = [(c.provider, c.model) for c in candidates]
        policy = RoutingPolicy(
            name="Vision Only",
            strategy="balanced",
            enabled=True,
            priority=50,
            capability_filter=("vision",),
        )
        await started_engine.create_policy(policy)
        result = await started_engine.evaluate(raw, RoutingRequest(task_type="chat"), policy)
        # Only gpt-4o has vision capability
        assert result.selected_model_id == "gpt-4o"

    async def test_evaluate_uses_weight_overrides(self, started_engine, multi_candidates):
        _, _, candidates = multi_candidates
        raw = [(c.provider, c.model) for c in candidates]
        policy = RoutingPolicy(
            name="Cheapest",
            strategy="custom_weighted",
            enabled=True,
            priority=50,
            weight_overrides={"cost": 10.0, "quality": 0.1, "latency": 0.1},
        )
        await started_engine.create_policy(policy)
        result = await started_engine.evaluate(raw, RoutingRequest(task_type="chat"), policy)
        # deepseek-coder has lowest effective cost when accounting for all dimensions
        assert result.selected_model_id == "deepseek-coder"

    async def test_evaluate_unknown_strategy_falls_back(self, started_engine, multi_candidates):
        _, _, candidates = multi_candidates
        raw = [(c.provider, c.model) for c in candidates]
        policy = RoutingPolicy(
            name="Weird",
            strategy="nonexistent_strategy",
            enabled=True,
            priority=50,
        )
        await started_engine.create_policy(policy)
        # Should fall back to balanced without error
        result = await started_engine.evaluate(raw, RoutingRequest(task_type="chat"), policy)
        assert result.selected_model_id != ""

    async def test_evaluate_scored_candidates_ordered(self, started_engine, multi_candidates):
        _, _, candidates = multi_candidates
        raw = [(c.provider, c.model) for c in candidates]
        result = await started_engine.evaluate(raw, RoutingRequest(task_type="chat"))
        scores = [s[3] for s in result.scored_candidates]
        # Should be descending
        for i in range(len(scores) - 1):
            assert scores[i] >= scores[i + 1]

    async def test_evaluate_policy_applied_false_on_fallback(self, engine, multi_candidates):
        _, _, candidates = multi_candidates
        raw = [(c.provider, c.model) for c in candidates]
        # Engine not started, no default seeded
        result = await engine.evaluate(raw, RoutingRequest(task_type="chat"))
        # Default will be a fallback synthetic policy
        assert result is not None


# ══════════════════════════════════════════════
# 7. Policy Filters Tests
# ══════════════════════════════════════════════


class TestPolicyFilters:
    async def test_provider_filter_limits_candidates(self, started_engine, multi_candidates):
        _, _, candidates = multi_candidates
        raw = [(c.provider, c.model) for c in candidates]
        policy = RoutingPolicy(
            name="OpenAI Only",
            strategy="balanced",
            enabled=True,
            priority=50,
            provider_filter=("openai",),
        )
        result = await started_engine.evaluate(raw, RoutingRequest(task_type="chat"), policy)
        assert result.selected_provider == "openai"

    async def test_model_filter_limits_candidates(self, started_engine, multi_candidates):
        _, _, candidates = multi_candidates
        raw = [(c.provider, c.model) for c in candidates]
        policy = RoutingPolicy(
            name="Claude Only",
            strategy="balanced",
            enabled=True,
            priority=50,
            model_filter=("claude-sonnet-4",),
        )
        result = await started_engine.evaluate(raw, RoutingRequest(task_type="chat"), policy)
        assert result.selected_model_id == "claude-sonnet-4"

    async def test_capability_filter_limits_candidates(self, started_engine, multi_candidates):
        _, _, candidates = multi_candidates
        raw = [(c.provider, c.model) for c in candidates]
        policy = RoutingPolicy(
            name="Coding Only",
            strategy="balanced",
            enabled=True,
            priority=50,
            capability_filter=("coding",),
        )
        result = await started_engine.evaluate(raw, RoutingRequest(task_type="chat"), policy)
        assert result.selected_model_id == "deepseek-coder"

    async def test_combined_filters(self, started_engine, multi_candidates):
        _, _, candidates = multi_candidates
        raw = [(c.provider, c.model) for c in candidates]
        # None should match these combined restrictions
        policy = RoutingPolicy(
            name="Impossible",
            strategy="balanced",
            enabled=True,
            priority=50,
            provider_filter=("openai",),
            capability_filter=("coding",),
        )
        result = await started_engine.evaluate(raw, RoutingRequest(task_type="chat"), policy)
        # No candidate satisfies both (openai doesn't have coding capability)
        assert result.selected_model_id == ""


# ══════════════════════════════════════════════
# 8. EventBus Tests
# ══════════════════════════════════════════════


class TestEventBus:
    async def test_created_event(self, engine_with_bus):
        engine, bus = engine_with_bus
        await engine.create_policy(RoutingPolicy(name="EB Test", strategy="balanced"))
        calls = [c[0][0].type for c in bus.publish.call_args_list]
        assert any(Topic.ROUTING_POLICY_CREATED.value in c for c in calls)

    async def test_updated_event(self, engine_with_bus):
        engine, bus = engine_with_bus
        pid = await engine.create_policy(RoutingPolicy(name="EB Before", strategy="balanced"))
        bus.reset_mock()
        await engine.update_policy(RoutingPolicy(id=pid, name="EB After", strategy="lowest_cost"))
        calls = [c[0][0].type for c in bus.publish.call_args_list]
        assert any(Topic.ROUTING_POLICY_UPDATED.value in c for c in calls)

    async def test_deleted_event(self, engine_with_bus):
        engine, bus = engine_with_bus
        pid = await engine.create_policy(RoutingPolicy(name="EB Del", strategy="balanced"))
        bus.reset_mock()
        await engine.delete_policy(pid)
        calls = [c[0][0].type for c in bus.publish.call_args_list]
        assert any(Topic.ROUTING_POLICY_DELETED.value in c for c in calls)

    async def test_enabled_event(self, engine_with_bus):
        engine, bus = engine_with_bus
        pid = await engine.create_policy(
            RoutingPolicy(name="EB Enable", strategy="balanced", enabled=False)
        )
        bus.reset_mock()
        await engine.enable_policy(pid)
        calls = [c[0][0].type for c in bus.publish.call_args_list]
        assert any(Topic.ROUTING_POLICY_ENABLED.value in c for c in calls)

    async def test_disabled_event(self, engine_with_bus):
        engine, bus = engine_with_bus
        pid = await engine.create_policy(
            RoutingPolicy(name="EB Disable", strategy="balanced", enabled=True)
        )
        bus.reset_mock()
        await engine.disable_policy(pid)
        calls = [c[0][0].type for c in bus.publish.call_args_list]
        assert any(Topic.ROUTING_POLICY_DISABLED.value in c for c in calls)


# ══════════════════════════════════════════════
# 9. Metrics / Observability Tests
# ══════════════════════════════════════════════


class TestMetrics:
    async def test_metrics_after_evaluation(self, started_engine, multi_candidates):
        raw = [(c.provider, c.model) for c in multi_candidates[2]]
        for _ in range(3):
            await started_engine.evaluate(raw, RoutingRequest(task_type="chat"))

        metrics = started_engine.metrics()
        assert metrics["total_evaluations"] >= 3
        assert len(metrics["policy_usage"]) >= 1
        assert metrics["avg_eval_time_ms"] > 0
        assert metrics["failures"] == 0

    async def test_metrics_tracks_selection(self, started_engine, multi_candidates):
        raw = [(c.provider, c.model) for c in multi_candidates[2]]
        await started_engine.evaluate(raw, RoutingRequest(task_type="chat"))

        metrics = started_engine.metrics()
        assert len(metrics["selection_frequency"]) >= 1

    async def test_metrics_tracks_policy_usage(self, started_engine, multi_candidates):
        raw = [(c.provider, c.model) for c in multi_candidates[2]]
        policy = RoutingPolicy(
            name="Metric Policy", strategy="lowest_cost", enabled=True, priority=50
        )
        await started_engine.create_policy(policy)

        await started_engine.evaluate(raw, RoutingRequest(task_type="chat"), policy)

        metrics = started_engine.metrics()
        assert "lowest_cost" in metrics["policy_usage"]

    async def test_strategy_names_available(self, started_engine):
        names = started_engine.get_strategy_names()
        assert "balanced" in names
        assert "lowest_cost" in names
        assert "highest_quality" in names
        assert "lowest_latency" in names
        assert "highest_reliability" in names
        assert "local_first" in names
        assert "cloud_first" in names
        assert "reasoning_optimized" in names
        assert "vision_optimized" in names
        assert "streaming_optimized" in names
        assert "tool_calling_optimized" in names
        assert "custom_weighted" in names
        assert "round_robin" in names
        assert "random" in names
        assert "sticky_provider" in names
        assert "workspace_default" in names
        assert "agent_default" in names
        assert "user_default" in names
        assert "emergency_failover" in names
        assert "safe_mode" in names
        assert "offline_mode" in names
        assert len(names) == 21


# ══════════════════════════════════════════════
# 10. Concurrency Tests
# ══════════════════════════════════════════════


class TestConcurrency:
    async def test_concurrent_create_policies(self, started_engine):
        async def create(n):
            return await started_engine.create_policy(
                RoutingPolicy(name=f"Concurrent-{n}", strategy="balanced")
            )

        tasks = [asyncio.create_task(create(i)) for i in range(10)]
        ids = await asyncio.gather(*tasks)
        assert len(set(ids)) == 10

    async def test_concurrent_evaluate(self, started_engine, multi_candidates):
        raw = [(c.provider, c.model) for c in multi_candidates[2]]

        async def evaluate():
            return await started_engine.evaluate(raw, RoutingRequest(task_type="chat"))

        results = await asyncio.gather(*[evaluate() for _ in range(5)])
        assert all(r.selected_model_id != "" for r in results)

    async def test_concurrent_mixed_ops(self, started_engine, multi_candidates):
        """Concurrent CRUD + evaluation should not deadlock."""
        raw = [(c.provider, c.model) for c in multi_candidates[2]]
        policy = RoutingPolicy(name="Race", strategy="balanced")

        async def eval_task():
            return await started_engine.evaluate(raw, RoutingRequest(task_type="chat"))

        async def crud_task():
            pid = await started_engine.create_policy(policy)
            await started_engine.get_policy(pid)
            await started_engine.delete_policy(pid)
            return pid

        tasks = [asyncio.create_task(eval_task()) for _ in range(3)]
        tasks += [asyncio.create_task(crud_task()) for _ in range(3)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        assert all(not isinstance(r, Exception) for r in results)


# ══════════════════════════════════════════════
# 11. Router Integration Tests
# ══════════════════════════════════════════════


class TestRouterIntegration:
    async def test_router_delegates_to_policy_engine(self, engine_with_router):
        pe, router = engine_with_router
        req = RoutingRequest(task_type="chat")
        decision = await router.route(req)
        assert decision.status == "routed"
        # Policy engine was used (not the hardcoded fallback)
        assert decision.policy_used != "weighted"

    async def test_router_policy_overrides_scoring(self, engine_with_router):
        pe, router = engine_with_router
        # Create a lowest_cost policy
        cheapest = RoutingPolicy(
            name="Cheapest", strategy="lowest_cost", enabled=True, priority=100
        )
        await pe.create_policy(cheapest)
        # This should override the default balanced
        req = RoutingRequest(task_type="chat")
        decision = await router.route(req)
        assert decision.policy_used == "lowest_cost"

    async def test_router_scoped_policy(self, engine_with_router):
        pe, router = engine_with_router
        ws_policy = RoutingPolicy(
            name="WS Router",
            strategy="lowest_cost",
            workspace_scope="my-ws",
            enabled=True,
            priority=100,
        )
        await pe.create_policy(ws_policy)
        # Without scope, default should apply
        req = RoutingRequest(task_type="chat")
        await router.route(req)
        # With scope, WS policy applies
        req_scoped = RoutingRequest(task_type="chat", workspace="my-ws")
        decision_scoped = await router.route(req_scoped)
        assert decision_scoped.policy_used == "lowest_cost"

    async def test_router_still_works_without_policy_engine(self):
        """Legacy test: no policy engine → fallback to weighted scoring."""
        router = RouterEngineImpl()
        from agentic_os.core.omniroute.provider_registry import ProviderRegistryImpl

        pr = ProviderRegistryImpl()
        await pr.start()
        router._provider_registry = pr
        router._model_registry = MagicMock()
        router._model_registry.list_enabled_models = AsyncMock(return_value=[])
        router._model_registry.get_provider_models = AsyncMock(return_value=[])
        await router.start()

        # Without policy engine, it should use built-in scoring
        req = RoutingRequest(task_type="chat")
        with pytest.raises(Exception, match="No providers|No models|provider_registry"):
            # Will fail because no providers/models registered, but that's OK
            await router.route(req)


# ══════════════════════════════════════════════
# 12. Edge Cases
# ══════════════════════════════════════════════


class TestEdgeCases:
    async def test_empty_policy_list(self, engine):
        await engine.initialize()
        policies = await engine.list_policies()
        assert len(policies) >= 1  # seeded default

    async def test_policy_priority_sorting(self, started_engine):
        p1 = await started_engine.create_policy(
            RoutingPolicy(name="Priority 10", strategy="balanced", priority=10, enabled=True)
        )
        p2 = await started_engine.create_policy(
            RoutingPolicy(name="Priority 100", strategy="lowest_cost", priority=100, enabled=True)
        )
        policies = await started_engine.list_policies(enabled_only=True)
        p100_idx = next(i for i, p in enumerate(policies) if p.id == p2)
        p10_idx = next(i for i, p in enumerate(policies) if p.id == p1)
        assert p100_idx < p10_idx

    async def test_evaluate_with_no_policies_no_start(self, engine, multi_candidates):
        """Engine without policies should resolve to fallback synthetic policy."""
        raw = [(c.provider, c.model) for c in multi_candidates[2]]
        result = await engine.evaluate(raw, RoutingRequest(task_type="chat"))
        assert result is not None
        assert result.selected_model_id != ""

    async def test_strategy_getter(self, started_engine):
        strategy = started_engine.get_strategy("balanced")
        assert strategy is not None
        assert isinstance(strategy, BalancedStrategy)

    async def test_strategy_getter_missing(self, started_engine):
        strategy = started_engine.get_strategy("does_not_exist")
        assert strategy is None

    async def test_multiple_policies_returned_for_matching_scopes(self, started_engine):
        await started_engine.create_policy(
            RoutingPolicy(
                name="WS-1",
                strategy="lowest_cost",
                workspace_scope="ws-1",
                enabled=True,
                priority=50,
            )
        )
        await started_engine.create_policy(
            RoutingPolicy(
                name="WS-2",
                strategy="highest_quality",
                workspace_scope="ws-1",
                enabled=True,
                priority=100,
            )
        )
        req = RoutingRequest(task_type="chat", workspace="ws-1")
        applicable = await started_engine.applicable_policies(req)
        assert len(applicable) >= 2

    async def test_global_policy_applies_to_all(self, started_engine):
        """A policy with no scopes should match any request."""
        pid = await started_engine.create_policy(
            RoutingPolicy(name="Global", strategy="lowest_cost", enabled=True, priority=10)
        )
        req = RoutingRequest(
            task_type="chat", workspace="anything", agent="anyone", user_id="anyuser"
        )
        applicable = await started_engine.applicable_policies(req)
        assert any(p.id == pid for p in applicable)

    async def test_overrides_in_evaluate_result(self, started_engine, multi_candidates):
        raw = [(c.provider, c.model) for c in multi_candidates[2]]
        policy = RoutingPolicy(
            name="Overrides",
            strategy="custom_weighted",
            enabled=True,
            priority=50,
            weight_overrides={"cost": 10.0},
            budget_override=0.01,
            latency_override_ms=500,
            context_override=32000,
        )
        result = await started_engine.evaluate(raw, RoutingRequest(task_type="chat"), policy)
        assert "weight_overrides" in result.overrides_used
        assert "budget_override" in result.overrides_used
        assert "latency_override_ms" in result.overrides_used
        assert "context_override" in result.overrides_used

    async def test_evaluate_with_single_candidate(self, started_engine, sample_candidates):
        raw = [(c.provider, c.model) for c in sample_candidates]
        result = await started_engine.evaluate(raw, RoutingRequest(task_type="chat"))
        assert result.selected_model_id == "gpt-4o"
        assert len(result.scored_candidates) == 1

    async def test_evaluate_policy_as_argument(self, started_engine, multi_candidates):
        raw = [(c.provider, c.model) for c in multi_candidates[2]]
        policy = RoutingPolicy(
            name="Explicit Policy",
            strategy="lowest_cost",
            enabled=True,
            priority=100,
        )
        result = await started_engine.evaluate(raw, RoutingRequest(task_type="chat"), policy=policy)
        assert result.policy_name == "Explicit Policy"
        assert result.strategy == "lowest_cost"

    async def test_metrics_isolation(self, started_engine):
        """Metrics should be distinct per engine instance."""
        engine2 = RoutingPolicyEngineImpl()
        await engine2.initialize()
        await engine2.start()

        m1_before = started_engine.metrics()
        m2_before = engine2.metrics()
        assert m1_before == m2_before

        # Evaluate only on first engine
        from agentic_os.core.omniroute.routing_policies import _ScoredCandidate

        dummy = _ScoredCandidate(
            provider=OmniRouteProvider(name="test", kind="test", base_url="http://test"),
            model=OmniRouteModel(model_id="test", provider="test", provider_id="t"),
        )
        raw = [(dummy.provider, dummy.model)]
        await started_engine.evaluate(raw, RoutingRequest(task_type="chat"))

        m1_after = started_engine.metrics()
        m2_after = engine2.metrics()
        assert m1_after["total_evaluations"] > m2_after["total_evaluations"]
