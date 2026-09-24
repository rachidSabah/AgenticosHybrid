"""Tests for multi-proxy failover selection.

These tests never touch the network: ``probe`` is monkeypatched to simulate
reachable / unreachable proxies.
"""

from __future__ import annotations

import pytest

from agentic_os.adapters.providers.proxy_failover import (
    describe_unreachable,
    probe,
    select_healthy_proxy,
)
from agentic_os.domain.proxy_profile import ProxyChain, ProxyProfile

PROXIES = [
    ProxyProfile(name="local-proxy", base_url="http://127.0.0.1:4000/v1"),
    ProxyProfile(
        name="openrouter",
        base_url="https://openrouter.ai/api/v1",
        api_key_env="OPENROUTER_API_KEY",
    ),
]


def _patch_probe(monkeypatch, fn):
    monkeypatch.setattr("agentic_os.adapters.providers.proxy_failover.probe", fn)


@pytest.mark.asyncio
async def test_skips_unreachable_and_returns_first_healthy(monkeypatch):
    async def fake(p: ProxyProfile, timeout: float = 5.0) -> bool:
        return p.name == "openrouter"  # local-proxy is down

    _patch_probe(monkeypatch, fake)
    chosen = await select_healthy_proxy(PROXIES)
    assert chosen is not None
    assert chosen.name == "openrouter"


@pytest.mark.asyncio
async def test_returns_none_when_all_down(monkeypatch):
    async def fake(p: ProxyProfile, timeout: float = 5.0) -> bool:
        return False

    _patch_probe(monkeypatch, fake)
    assert await select_healthy_proxy(PROXIES) is None


@pytest.mark.asyncio
async def test_prefers_earlier_proxy_when_both_healthy(monkeypatch):
    async def fake(p: ProxyProfile, timeout: float = 5.0) -> bool:
        return True

    _patch_probe(monkeypatch, fake)
    chosen = await select_healthy_proxy(PROXIES)
    assert chosen.name == "local-proxy"


@pytest.mark.asyncio
async def test_empty_list_returns_none(monkeypatch):
    _patch_probe(monkeypatch, lambda p, timeout=5.0: True)
    assert await select_healthy_proxy([]) is None


@pytest.mark.asyncio
async def test_chain_input_accepted(monkeypatch):
    async def fake(p: ProxyProfile, timeout: float = 5.0) -> bool:
        return p.name == "openrouter"

    _patch_probe(monkeypatch, fake)
    chosen = await select_healthy_proxy(ProxyChain(profiles=PROXIES))
    assert chosen.name == "openrouter"


@pytest.mark.asyncio
async def test_probe_returns_false_on_network_error(monkeypatch):
    """A proxy that raises must be treated as down, never raise out."""
    unreachable = ProxyProfile(name="dead", base_url="http://127.0.0.1:59999/v1")
    result = await probe(unreachable, timeout=1.0)
    assert result is False


def test_describe_unreachable_names_all_proxies():
    msg = describe_unreachable(PROXIES)
    assert "local-proxy" in msg and "openrouter" in msg
