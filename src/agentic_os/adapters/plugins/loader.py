"""Plugin loader.

Discovers :class:`Plugin` implementations and calls ``load(ctx)``. Plugins may
register provider adapters, roles, or scheduled jobs without core changes. This
is what makes the OS "plugin-based" and every component "replaceable".
"""

from __future__ import annotations

import importlib

from agentic_os.core.registry import AgentRegistry, ProviderRegistry
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.plugin import Plugin, PluginContext

log = get_logger("plugins.loader")

_PLUGIN_PACKAGES = [
    "agentic_os.adapters.providers",
    "agentic_os.adapters.plugins.builtins",
]


def load_plugins(agents: AgentRegistry, providers: ProviderRegistry) -> list[Plugin]:
    ctx = PluginContext(agents, providers)
    loaded: list[Plugin] = []
    for pkg_name in _PLUGIN_PACKAGES:
        try:
            pkg = importlib.import_module(pkg_name)
        except ModuleNotFoundError:
            continue
        # Built-in plugin packages expose a module-level PLUGINS list of instances.
        for plugin in getattr(pkg, "PLUGINS", []):
            try:
                plugin.load(ctx)
                loaded.append(plugin)
                log.info("plugin.loaded", name=plugin.name)
            except Exception as exc:  # noqa: BLE001
                log.error("plugin.failed", name=getattr(plugin, "name", "?"), error=str(exc))
    return loaded
