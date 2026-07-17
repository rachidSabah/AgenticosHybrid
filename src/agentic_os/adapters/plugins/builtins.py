"""Built-in plugins.

These register provider adapters into the OS at boot. Add new providers here
(or as separate plugin packages) without touching core. Each plugin conforms to
the :class:`Plugin` port (``name``, ``load(ctx)``, ``unload()``).
"""

from __future__ import annotations

from agentic_os.adapters.providers.claude_code import ClaudeCodeProvider
from agentic_os.adapters.providers.mock import MockProvider
from agentic_os.config import settings
from agentic_os.ports.plugin import Plugin, PluginContext


class MockProviderPlugin:
    name = "mock-provider"

    def load(self, ctx: PluginContext) -> None:
        ctx.providers.register(MockProvider())

    def unload(self) -> None:
        pass


class ClaudeCodeProviderPlugin:
    name = "claude-code-provider"

    def load(self, ctx: PluginContext) -> None:
        ctx.providers.register(
            ClaudeCodeProvider(
                bin_path=settings.claude_code_bin, api_key=settings.anthropic_api_key
            )
        )

    def unload(self) -> None:
        pass


PLUGINS: list[Plugin] = [MockProviderPlugin(), ClaudeCodeProviderPlugin()]
