"""Tests for the switchable proxy profile."""

from __future__ import annotations

import json
import os

import pytest

from agentic_os.domain.proxy_profile import (
    ProxyChain,
    ProxyProfile,
    get_active_profile,
    get_proxy_chain,
    set_proxy_chain,
)


@pytest.fixture
def isolated_proxy_file(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTICOS_PROXY_FILE", str(tmp_path / "proxy.json"))
    yield tmp_path / "proxy.json"


def test_default_chain_is_empty_full_isolation(isolated_proxy_file):
    """No proxy ships preconfigured — the default chain is EMPTY (isolation)."""
    chain = get_proxy_chain()
    assert chain.is_empty()
    assert chain.profiles == []


def test_roundtrip_persists_order(isolated_proxy_file):
    chain = ProxyChain(
        profiles=[
            ProxyProfile(name="local-proxy", base_url="http://127.0.0.1:4000/v1"),
            ProxyProfile(
                name="openrouter",
                base_url="https://openrouter.ai/api/v1",
                api_key_env="OPENROUTER_API_KEY",
            ),
        ]
    )
    set_proxy_chain(chain)
    loaded = get_proxy_chain()
    assert [p.name for p in loaded.profiles] == ["local-proxy", "openrouter"]
    assert loaded.profiles[1].api_key_env == "OPENROUTER_API_KEY"


def test_api_key_reads_env_when_declared(monkeypatch):
    monkeypatch.setenv("MY_TEST_KEY", "abc123")
    p = ProxyProfile(name="openrouter", base_url="https://x/v1", api_key_env="MY_TEST_KEY")
    assert p.api_key() == "abc123"


def test_api_key_without_env_is_empty_no_fabricated_bearer():
    """No env var declared → empty key. Never invent a bearer from the name."""
    p = ProxyProfile(name="any-endpoint", base_url="http://127.0.0.1:4000/v1")
    assert p.api_key() == ""


def test_api_key_missing_env_returns_empty(monkeypatch):
    monkeypatch.delenv("NOPE_MISSING", raising=False)
    p = ProxyProfile(name="x", base_url="https://x/v1", api_key_env="NOPE_MISSING")
    assert p.api_key() == ""


def test_corrupt_file_yields_empty_chain(isolated_proxy_file):
    """A malformed file must not resurrect an assumed endpoint — chain stays empty."""
    isolated_proxy_file.write_text("{not json", encoding="utf-8")
    chain = get_proxy_chain()
    assert chain.is_empty()


def test_entries_without_base_url_are_dropped(isolated_proxy_file):
    isolated_proxy_file.write_text(
        json.dumps({"profiles": [{"name": "bad"}, {"name": "ok", "base_url": "https://x/v1"}]}),
        encoding="utf-8",
    )
    chain = get_proxy_chain()
    assert [p.name for p in chain.profiles] == ["ok"]


def test_get_active_profile_returns_first(isolated_proxy_file):
    set_proxy_chain(
        ProxyChain(
            profiles=[
                ProxyProfile(name="first", base_url="https://first/v1"),
                ProxyProfile(name="second", base_url="https://second/v1"),
            ]
        )
    )
    assert get_active_profile().name == "first"


def test_isolated_file_env_respected(isolated_proxy_file):
    set_proxy_chain(ProxyChain(profiles=[ProxyProfile(name="z", base_url="https://z/v1")]))
    assert isolated_proxy_file.exists()
    assert os.environ["AGENTICOS_PROXY_FILE"] == str(isolated_proxy_file)
