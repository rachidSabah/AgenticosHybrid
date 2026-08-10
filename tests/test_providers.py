"""Tests for provider adapters and plugin loading."""

from __future__ import annotations

import shutil

import pytest

from agentic_os.adapters.plugins.builtins import PLUGINS
from agentic_os.adapters.providers import hermes as hermes_module
from agentic_os.adapters.providers.claude_code import ClaudeCodeProvider
from agentic_os.adapters.providers.hermes import HermesProvider
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
    # The mock provider must NOT be auto-registered in production — it is a
    # test-only utility registered explicitly by tests or ProviderFactory.
    assert "mock" not in names
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


async def test_hermes_provider_passes_prompt_as_argv(monkeypatch):
    """Regression: the hermes prompt must be the ``-z`` argument value.

    A previous change piped the prompt via stdin with ``-z -``. The real
    hermes oneshot mode (``-z PROMPT``) reads no stdin, so every agent
    received the literal prompt ``-`` and replied "You sent just '-'".
    Guard against the exact argv-vs-stdin regression recurring.
    """
    # Don't depend on hermes being on $PATH in CI — stub the binary check.
    monkeypatch.setattr(
        hermes_module.shutil, "which", lambda name: name if name == "hermes" else None
    )

    captured: dict[str, object] = {}

    async def fake_run_cli(args, *, input_data=None, env=None, cwd=None, timeout=120.0, on_output=None):
        captured["args"] = list(args)
        captured["input_data"] = input_data
        return 0, "All files written", ""

    monkeypatch.setattr(hermes_module, "run_cli", fake_run_cli)

    p = HermesProvider(bin_path="hermes")
    agent = Agent(id="a1", role="coding", provider="hermes")
    task = Task(
        title="Write hello",
        role="coding",
        description="in Python",
        user_prompt="Write hello world in Python",
    )
    result = await p.execute(agent, task)

    assert result == "All files written"
    args = captured["args"]
    assert args[0] == "hermes"
    assert args[1] == "-z"
    assert "Write hello world in Python" in args[2]  # prompt is the -z value
    assert args[3] == "--yolo"
    assert captured["input_data"] is None  # never piped via stdin
