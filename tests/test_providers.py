"""Tests for provider adapters and plugin loading."""

from __future__ import annotations

import shutil

import pytest

from agentic_os.adapters.plugins.builtins import PLUGINS
from agentic_os.adapters.providers.claude_code import ClaudeCodeProvider
from agentic_os.adapters.providers.mock import MockProvider
from agentic_os.core.registry import AgentRegistry, ProviderRegistry
from agentic_os.domain.agent import Agent, Task
from agentic_os.ports.plugin import PluginContext


async def test_mock_provider_success():
    p = MockProvider()
    agent = Agent(id="a1", role="coding", provider="mock")
    task = Task(title="do a thing", role="coding")
    result = await p.execute(agent, task)
    assert "completed" in result


async def test_mock_provider_forced_failure():
    p = MockProvider()
    agent = Agent(id="a1", role="coding", provider="mock")
    task = Task(title="please fail now", role="coding")
    with pytest.raises(RuntimeError):
        await p.execute(agent, task)


def test_builtin_plugins_register_providers():
    agents = AgentRegistry()
    providers = ProviderRegistry()
    ctx = PluginContext(agents, providers)
    for plugin in PLUGINS:
        plugin.load(ctx)
    names = {p.name for p in providers.list_providers()}
    assert "mock" in names
    # claude_code and hermes are optional — only registered if the binary
    # is on $PATH, which varies by CI environment.
    if shutil.which("claude"):
        assert "claude_code" in names
    if shutil.which("hermes"):
        assert "hermes" in names


def test_claude_code_provider_reports_info():
    p = ClaudeCodeProvider(bin_path="claude")
    assert p.info.name == "claude_code"
    assert p.info.supports_tools is True
