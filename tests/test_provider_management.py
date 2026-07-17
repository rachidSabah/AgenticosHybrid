"""Tests for the Provider Management System (Subsystem 1)."""

from __future__ import annotations

import pytest

from agentic_os.adapters.providers.mock import MockProvider
from agentic_os.adapters.providers.openai_compatible import OpenAICompatibleProvider
from agentic_os.adapters.security.encrypted_store import EncryptedSecretStore
from agentic_os.core.providers.health import FailoverPolicyImpl, ProviderHealthMonitorImpl
from agentic_os.core.providers.manager import ModelManagerImpl, ProviderManagerImpl
from agentic_os.core.providers.router import ProviderRouter
from agentic_os.core.providers.routing import (
    CostRoutingPolicy,
    CostTrackerImpl,
    RateLimitMonitorImpl,
    RoundRobinRoutingPolicy,
)
from agentic_os.core.providers.vault import ApiKeyVaultImpl
from agentic_os.domain.provider_mgmt import ProviderConfig
from agentic_os.ports.provider_management import ModelInfo


@pytest.fixture
def manager():
    m = ProviderManagerImpl()
    m.register(MockProvider())
    m.register_model(
        ModelInfo(id="mock-fast", provider="mock", capabilities=["coding", "reasoning"])
    )
    m.register_model(
        ModelInfo(
            id="gpt",
            provider="openai",
            input_cost_per_1k=0.01,
            output_cost_per_1k=0.02,
            capabilities=["coding"],
        )
    )
    return m


async def test_provider_manager_register_and_models(manager):
    assert manager.get("mock") is not None
    assert len(manager.list_models("mock")) == 1
    assert manager.get_model("mock", "mock-fast") is not None


async def test_model_manager_cheapest(manager):
    mm = ModelManagerImpl(manager)
    cheapest = mm.cheapest("coding")
    assert cheapest is not None
    assert cheapest.provider == "mock"  # free vs openai


async def test_vault_store_and_revoke():
    store = EncryptedSecretStore(path=None)  # in-memory
    vault = ApiKeyVaultImpl(store)
    await vault.store_key("openai", "sk-test")
    assert await vault.get_key("openai") == "sk-test"
    await vault.revoke("openai")
    assert await vault.get_key("openai") is None


async def test_encrypted_store_roundtrip(tmp_path):
    store = EncryptedSecretStore(path=tmp_path / "vault.json")
    await store.put("k", "v")
    reloaded = EncryptedSecretStore(path=tmp_path / "vault.json")
    assert await reloaded.get("k") == "v"


async def test_rate_limit_monitor():
    rl = RateLimitMonitorImpl()
    rl.set_limit("p", 2)
    assert rl.consume("p") is True
    assert rl.consume("p") is True
    assert rl.consume("p") is False
    assert rl.remaining("p") == 0


async def test_cost_tracker_records_and_totals(manager):
    ct = CostTrackerImpl()
    ct.bind_models(ModelManagerImpl(manager))
    cost = await ct.record("openai", "gpt", "t1", 1000, 1000)
    assert cost == 0.03
    assert ct.total_cost() == 0.03
    assert ct.total_cost("openai") == 0.03
    assert ct.total_cost("mock") == 0.0


async def test_routing_policies(manager):
    mm = ModelManagerImpl(manager)
    rr = RoundRobinRoutingPolicy()
    cands = [("mock", "mock-fast"), ("openai", "gpt")]
    a = await rr.select("coding", cands)
    b = await rr.select("coding", cands)
    assert a != b  # alternates
    cost_policy = CostRoutingPolicy(mm)
    pick = await cost_policy.select("coding", cands)
    assert pick is not None
    assert pick[0] == "mock"


async def test_failover_skips_failed():
    fo = FailoverPolicyImpl()
    nxt = await fo.next_provider("openai", "coding", ["openai", "mock", "groq"])
    assert nxt == "mock"


async def test_health_monitor_probes_provider(manager):
    from agentic_os.adapters.bus.local import LocalBus
    from agentic_os.core.scheduler import Scheduler

    bus = LocalBus()
    await bus.start()
    sched = Scheduler()
    hm = ProviderHealthMonitorImpl(bus, manager, sched)
    ok = await hm.check_now("mock")
    assert ok is True
    assert hm.status("mock") == "healthy"
    await bus.stop()


async def test_router_select_and_failover(manager):
    from agentic_os.adapters.bus.local import LocalBus
    from agentic_os.core.scheduler import Scheduler

    bus = LocalBus()
    await bus.start()
    sched = Scheduler()
    hm = ProviderHealthMonitorImpl(bus, manager, sched)
    rate = RateLimitMonitorImpl()
    router = ProviderRouter(bus, manager, ModelManagerImpl(manager), hm, rate, policy="cost")
    pick = await router.select("coding")
    assert pick is not None
    fo = await router.failover(pick[0], "coding")
    assert fo is None or fo[0] != pick[0]
    await bus.stop()


async def test_openai_compatible_adapter_health_unreachable():
    p = OpenAICompatibleProvider("local", "http://127.0.0.1:9", "m")
    assert await p.healthcheck() is False


async def test_provider_config_validation():
    cfg = ProviderConfig(
        name="my-llm",
        kind="openai_compatible",
        base_url="http://x",
        default_model="m",
        rate_limit=100,
    )
    assert cfg.enabled is True
    assert cfg.rate_limit == 100
