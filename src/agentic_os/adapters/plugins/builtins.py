"""Built-in plugins.

These register provider adapters into the OS at boot and auto-detect AI
agents installed on the local machine. Add new providers here (or as separate
plugin packages) without touching core. Each plugin conforms to the :class:`Plugin`
port (``name``, ``load(ctx)``, ``unload()``).

Auto-binding plugins probe PATH for known CLI agents (Claude Code, Hermes,
Codex, Aider, Ollama, etc.) and register them as live providers so Mission
Control can use them immediately — no manual config required.
"""

from __future__ import annotations

import shutil

from agentic_os.adapters.providers.auto_bind import auto_discover_and_bind
from agentic_os.adapters.providers.mock import MockProvider
from agentic_os.adapters.providers.strategies import ProviderFactory
from agentic_os.config import settings
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.plugin import Plugin, PluginContext

log = get_logger("plugins.builtins")


class MockProviderPlugin:
    """Always available — zero-infrastructure fallback provider."""

    name = "mock-provider"

    def load(self, ctx: PluginContext) -> None:
        ctx.providers.register(MockProvider())
        log.info("plugin.loaded", name=self.name)

    def unload(self) -> None:
        pass


class ClaudeCodeProviderPlugin:
    """Auto-detect Claude Code CLI on PATH and register if found.

    Uses ProviderFactory to create the adapter with the correct
    ClaudeExecutionStrategy (claude -p "{prompt}" --output-format text).
    """

    name = "claude-code-provider"

    def load(self, ctx: PluginContext) -> None:
        bin_path = settings.claude_code_bin or "claude"
        if not shutil.which(bin_path):
            log.info("plugin.skipping", name=self.name, reason="claude binary not on PATH")
            return

        api_key = settings.anthropic_api_key or ""
        adapter = ProviderFactory.create(
            kind="claude_code",
            bin_path=bin_path,
            name="claude_code",
            display_name="Claude Code",
            capabilities=["coding", "reasoning", "terminal"],
            api_key=api_key,
        )
        ctx.providers.register(adapter)
        if api_key:
            log.info("plugin.loaded", name=self.name, bin_path=bin_path)
        else:
            log.warning("plugin.loaded.degraded", name=self.name, bin_path=bin_path)

    def unload(self) -> None:
        pass


class HermesProviderPlugin:
    """Auto-detect Hermes CLI on PATH and register if found.

    Uses ProviderFactory to create the adapter with the correct
    HermesExecutionStrategy (hermes -p "{prompt}" --output-format text).
    """

    name = "hermes-provider"

    def load(self, ctx: PluginContext) -> None:
        bin_path = "hermes"
        if not shutil.which(bin_path):
            log.info("plugin.skipping", name=self.name, reason="hermes binary not on PATH")
            return

        api_key = settings.hermes_config or ""
        adapter = ProviderFactory.create(
            kind="hermes",
            bin_path=bin_path,
            name="hermes",
            display_name="Hermes Agent",
            capabilities=["coding", "reasoning", "research", "planning"],
            api_key=api_key,
        )
        ctx.providers.register(adapter)
        if api_key:
            log.info("plugin.loaded", name=self.name, bin_path=bin_path)
        else:
            log.warning("plugin.loaded.degraded", name=self.name, bin_path=bin_path)

    def unload(self) -> None:
        pass


class AutoBindPlugin:
    """Scans PATH for any other known AI agents and registers them dynamically.

    This catches agents not covered by dedicated plugins — Codex, Aider, Ollama,
    LM Studio, Open Interpreter, etc. Each found agent gets a generic adapter so
    it at least appears in Mission Control's provider list.
    """

    name = "auto-bind-providers"

    def load(self, ctx: PluginContext) -> None:
        provider_count_before = len(ctx.providers.list_providers())
        bound = auto_discover_and_bind(ctx.providers)
        if bound:
            log.info(
                "plugin.auto_bound",
                count=len(bound),
                total=len(ctx.providers.list_providers()),
            )
        else:
            log.info(
                "plugin.auto_bound.complete",
                skipped=provider_count_before,
                total=len(ctx.providers.list_providers()),
            )

    def unload(self) -> None:
        pass


# Order matters: mock first (always available), then named plugins, then auto-bind.
PLUGINS: list[Plugin] = [
    MockProviderPlugin(),
    ClaudeCodeProviderPlugin(),
    HermesProviderPlugin(),
    AutoBindPlugin(),
]
