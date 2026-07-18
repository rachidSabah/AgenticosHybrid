"""Port: Plugin Registry.

Plugins extend the OS without modifying core. A plugin may register provider
adapters, bus adapters, agents/roles, or scheduled jobs. The plugin registry
manages plugin lifecycle, dependencies, and capabilities.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from agentic_os.core.registry import AgentRegistry, ProviderRegistry
from agentic_os.domain.plugin import (
    PluginCapability,
    PluginCategory,
    PluginConfig,
    PluginInstance,
    PluginManifest,
    PluginRegistrySnapshot,
    PluginSearchQuery,
    PluginSearchResult,
    PluginStatus,
    PluginValidationResult,
)


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


@dataclass(frozen=True, slots=True)
class PluginInstallRequest:
    """Request to install a plugin."""

    reference: str  # plugin name, URL, or local path
    source: str = "registry"  # "registry", "url", "local"
    version: str | None = None
    config: dict | None = None
    force: bool = False
    skip_dependencies: bool = False
    verify_signature: bool = False


@dataclass(frozen=True, slots=True)
class PluginUpdateRequest:
    """Request to update a plugin."""

    version: str | None = None
    config: dict | None = None


@runtime_checkable
class PluginRegistryPort(Protocol):
    """Port for plugin registry operations."""

    # CRUD
    async def install_plugin(self, request: PluginInstallRequest) -> PluginInstance: ...
    async def uninstall_plugin(self, name: str, force: bool = False) -> bool: ...
    async def get_plugin(self, name: str) -> PluginInstance | None: ...
    async def list_plugins(
        self,
        category: PluginCategory | None = None,
        status: PluginStatus | None = None,
        enabled_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[PluginInstance]: ...
    async def update_plugin(self, name: str, request: PluginUpdateRequest) -> PluginInstance: ...

    # Lifecycle
    async def start_plugin(self, name: str) -> PluginInstance: ...
    async def stop_plugin(self, name: str) -> PluginInstance: ...
    async def restart_plugin(self, name: str) -> PluginInstance: ...

    # Validation & Dependencies
    async def validate_plugin(self, request: PluginInstallRequest) -> PluginValidationResult: ...
    async def check_dependencies(self, name: str) -> dict[str, bool]: ...
    async def resolve_dependencies(self, name: str) -> list[str]: ...

    # Configuration
    async def get_config(self, name: str) -> PluginConfig | None: ...
    async def set_config(self, name: str, config: PluginConfig) -> PluginConfig: ...

    # Search & Discovery
    async def search_plugins(self, query: PluginSearchQuery) -> PluginSearchResult: ...
    async def get_plugin_manifest(
        self, name: str, version: str | None = None
    ) -> PluginManifest | None: ...
    async def list_registry_categories(self) -> list[PluginCategory]: ...

    # Health & Monitoring
    async def check_health(self, name: str) -> tuple[str, dict]: ...
    async def get_health(self, name: str) -> tuple[str, dict] | None: ...

    # Capabilities
    async def get_capabilities(self, name: str) -> list[PluginCapability]: ...
    async def find_plugins_by_capability(self, capability: str) -> list[PluginInstance]: ...

    # Registry Snapshot
    async def get_registry(self) -> PluginRegistrySnapshot: ...

    # Signing & Verification
    async def verify_signature(self, manifest: PluginManifest) -> tuple[bool, str | None]: ...
    async def sign_plugin(self, manifest: PluginManifest, private_key: str) -> PluginManifest: ...

    # Lifecycle
    async def shutdown(self) -> None: ...
