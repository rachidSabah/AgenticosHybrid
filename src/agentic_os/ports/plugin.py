"""Port: Plugin.

Plugins extend the OS without modifying core. A plugin may register provider
adapters, bus adapters, agents/roles, or scheduled jobs. The plugin loader
discovers subclasses of :class:`Plugin` and calls ``load(context)``.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from agentic_os.core.registry import AgentRegistry, ProviderRegistry


class PluginContext:
    """Handles a plugin receives so it can register capabilities."""

    def __init__(self, agents: AgentRegistry, providers: ProviderRegistry) -> None:
        self.agents = agents
        self.providers = providers


@runtime_checkable
class Plugin(Protocol):
    """A loadable extension."""

    name: str

    def load(self, ctx: PluginContext) -> None:
        """Register capabilities into the OS."""
        ...

    def unload(self) -> None:
        """Release resources (optional)."""
        ...
