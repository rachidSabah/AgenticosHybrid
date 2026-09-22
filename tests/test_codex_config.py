"""Tests for rendering ~/.codex/config.toml from an AgenticOS proxy profile."""

from __future__ import annotations

import pytest

from agentic_os.adapters.providers.codex_config import (
    render_codex_config,
    write_codex_config,
)
from agentic_os.domain.proxy_profile import ProxyProfile


def test_renders_nexus_profile():
    out = render_codex_config(
        ProxyProfile(name="nexus", base_url="http://127.0.0.1:8787/v1", model="gpt-5.6-terra")
    )
    assert 'base_url = "http://127.0.0.1:8787/v1"' in out
    assert 'model = "gpt-5.6-terra"' in out
    assert 'model_provider = "nexus"' in out


def test_renders_env_key_when_declared():
    out = render_codex_config(
        ProxyProfile(
            name="openrouter",
            base_url="https://openrouter.ai/api/v1",
            api_key_env="OPENROUTER_API_KEY",
            model="m",
        )
    )
    assert 'env_key = "OPENROUTER_API_KEY"' in out


def test_omits_env_key_for_keyless_proxy():
    out = render_codex_config(ProxyProfile(name="nexus", base_url="http://x/v1", model="m"))
    assert 'env_key = "USERPROFILE"' in out


def test_preserves_existing_trust_blocks(tmp_path):
    target = tmp_path / "config.toml"
    target.write_text(
        '[projects.\'f:\\\\aioverdesktop\']\ntrust_level = "trusted"\n\n[windows]\nsandbox = "elevated"\n',
        encoding="utf-8",
    )
    write_codex_config(
        ProxyProfile(name="nexus", base_url="http://x/v1", model="m"), path=str(target)
    )
    out = target.read_text(encoding="utf-8")
    assert "aioverdesktop" in out
    assert 'trust_level = "trusted"' in out
    assert "[windows]" in out


def test_result_is_parseable_toml(tmp_path):
    tomllib = pytest.importorskip("tomllib")
    out = render_codex_config(
        ProxyProfile(name="nexus", base_url="http://127.0.0.1:8787/v1", model="gpt-5.6-terra")
    )
    parsed = tomllib.loads(out)
    assert parsed["model"] == "gpt-5.6-terra"
    assert parsed["model_providers"]["nexus"]["base_url"] == "http://127.0.0.1:8787/v1"


def test_write_returns_path(tmp_path):
    target = tmp_path / "config.toml"
    result = write_codex_config(
        ProxyProfile(name="nexus", base_url="http://x/v1", model="m"), path=str(target)
    )
    assert result == target
    assert target.exists()
