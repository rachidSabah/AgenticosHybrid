"""Plugin discovery — detects plugins on the local system.

Discovers plugins from:
- Plugin directories (`.agentic_os/plugins/`, `~/.config/agentic_os/plugins/`)
- Plugin manifest files (`plugin.json`, `manifest.json`)
- Package manager plugin registries (pip, npm, cargo)
- AgenticOS standard plugin paths

Each discovered plugin is returned with its metadata, capabilities,
and version information.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.logging import get_logger

_log = get_logger(__name__)

__all__ = [
    "PluginDiscovery",
    "DiscoveredPlugin",
    "PluginType",
]

from enum import StrEnum


class PluginType(StrEnum):
    """Supported plugin types."""

    CORE = "core"
    PROVIDER = "provider"
    TOOL = "tool"
    MCP = "mcp"
    ADAPTER = "adapter"
    HOOK = "hook"
    UI = "ui"
    CUSTOM = "custom"


@dataclass
class DiscoveredPlugin:
    """A discovered plugin on the local system."""

    name: str
    path: str
    plugin_type: PluginType = PluginType.CUSTOM
    version: str | None = None
    description: str = ""
    author: str = ""
    entry_point: str | None = None
    capabilities: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    discovered_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "plugin_type": self.plugin_type.value,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "entry_point": self.entry_point,
            "capabilities": list(self.capabilities),
            "dependencies": list(self.dependencies),
            "metadata": dict(self.metadata),
            "discovered_at": self.discovered_at.isoformat(),
        }


# Standard plugin directory names to search
_PLUGIN_DIR_NAMES = [
    "plugins",
    "extensions",
    "addons",
]

# Plugin manifest file names
_PLUGIN_MANIFEST_NAMES = [
    "plugin.json",
    "manifest.json",
    "plugin.yaml",
    "plugin.yml",
]

# Plugin entry points to detect
_PLUGIN_ENTRY_POINTS = [
    "main.py",
    "index.js",
    "index.ts",
    "main.go",
    "plugin.py",
    "run.py",
    "start.py",
]


class PluginDiscovery:
    """Discovers plugins installed on the local system.

    Scans standard plugin directories, package manager sites,
    and manifest files to find and describe installed plugins.
    """

    def __init__(self) -> None:
        self._discovered: dict[str, DiscoveredPlugin] = {}

    async def discover_all(self) -> list[DiscoveredPlugin]:
        """Discover all plugins from all sources."""
        plugins: list[DiscoveredPlugin] = []

        # 1. Standard plugin directories
        plugins.extend(await self._discover_from_standard_dirs())

        # 2. Python package plugins (pip-installed agentic packages)
        plugins.extend(await self._discover_from_python_packages())

        # 3. User-configured plugin paths
        plugins.extend(await self._discover_from_env_paths())

        # Deduplicate by name
        merged = self._deduplicate(plugins)

        for plugin in merged:
            self._discovered[plugin.name] = plugin

        _log.info("Plugin discovery found %d plugins", len(merged))
        return merged

    async def discover_by_type(self, plugin_type: PluginType) -> list[DiscoveredPlugin]:
        """Discover plugins matching a specific plugin type."""
        all_plugins = await self.discover_all()
        return [p for p in all_plugins if p.plugin_type == plugin_type]

    async def discover_by_name(self, name: str) -> DiscoveredPlugin | None:
        """Discover a single plugin by name."""
        all_plugins = await self.discover_all()
        return next((p for p in all_plugins if p.name == name), None)

    def get_discovered(self, name: str) -> DiscoveredPlugin | None:
        """Get a previously discovered plugin by name."""
        return self._discovered.get(name)

    def get_all_discovered(self) -> list[DiscoveredPlugin]:
        """Return all previously discovered plugins."""
        return list(self._discovered.values())

    # ── Standard directories ──

    async def _discover_from_standard_dirs(self) -> list[DiscoveredPlugin]:
        """Discover plugins from standard AgenticOS plugin directories."""
        plugins: list[DiscoveredPlugin] = []
        search_dirs = self._get_plugin_search_dirs()

        for search_dir in search_dirs:
            if not search_dir.is_dir():
                continue

            try:
                for entry in search_dir.iterdir():
                    if not entry.is_dir():
                        continue

                    plugin = await self._scan_plugin_dir(entry)
                    if plugin:
                        plugins.append(plugin)
            except PermissionError:
                _log.debug("Permission denied scanning %s", search_dir)
                continue

        return plugins

    async def _scan_plugin_dir(self, plugin_dir: Path) -> DiscoveredPlugin | None:
        """Scan a single directory for plugin information."""
        name = plugin_dir.name

        # Look for manifest files
        for manifest_name in _PLUGIN_MANIFEST_NAMES:
            manifest_path = plugin_dir / manifest_name
            if manifest_path.exists():
                plugin = await self._parse_manifest(manifest_path)
                if plugin:
                    return plugin

        # No manifest - infer from directory structure
        return self._infer_from_directory(plugin_dir)

    async def _parse_manifest(self, manifest_path: Path) -> DiscoveredPlugin | None:
        """Parse a plugin manifest file."""
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

        plugin_dir = manifest_path.parent

        # Find entry point
        entry_point = data.get("entry_point") or data.get("main")
        if not entry_point:
            entry_point = self._find_entry_point(plugin_dir)

        # Determine plugin type
        type_str = data.get("type", "custom")
        try:
            plugin_type = PluginType(type_str)
        except ValueError:
            plugin_type = PluginType.CUSTOM

        return DiscoveredPlugin(
            name=data.get("name", plugin_dir.name),
            path=str(plugin_dir),
            plugin_type=plugin_type,
            version=data.get("version"),
            description=data.get("description", ""),
            author=data.get("author", ""),
            entry_point=entry_point,
            capabilities=data.get("capabilities", []),
            dependencies=data.get("dependencies", []),
            metadata={"source": "manifest", "manifest_path": str(manifest_path)},
        )

    def _infer_from_directory(self, plugin_dir: Path) -> DiscoveredPlugin | None:
        """Infer plugin metadata from directory structure."""
        name = plugin_dir.name
        entry_point = self._find_entry_point(plugin_dir)

        if entry_point is None:
            return None

        # Try to determine type from name or location
        plugin_type = PluginType.CUSTOM
        name_lower = name.lower()
        if "provider" in name_lower:
            plugin_type = PluginType.PROVIDER
        elif "tool" in name_lower:
            plugin_type = PluginType.TOOL
        elif "mcp" in name_lower or "server" in name_lower:
            plugin_type = PluginType.MCP
        elif "hook" in name_lower:
            plugin_type = PluginType.HOOK
        elif "adapter" in name_lower:
            plugin_type = PluginType.ADAPTER
        elif "ui" in name_lower or "panel" in name_lower or "view" in name_lower:
            plugin_type = PluginType.UI

        return DiscoveredPlugin(
            name=name,
            path=str(plugin_dir),
            plugin_type=plugin_type,
            entry_point=entry_point,
            metadata={"source": "directory_inference"},
        )

    # ── Python package discovery ──

    async def _discover_from_python_packages(self) -> list[DiscoveredPlugin]:
        """Discover plugins installed as Python packages."""
        plugins: list[DiscoveredPlugin] = []

        # Check for agentic_os plugins installed via pip
        try:
            import importlib.metadata as importlib_metadata

            for dist in importlib_metadata.distributions():
                name = dist.metadata.get("Name", "")
                if not name:
                    continue

                # Filter to likely plugin packages
                if not any(
                    marker in name.lower()
                    for marker in ("agentic", "plugin", "provider", "mcp", "tool")
                ):
                    continue

                # Skip core packages
                if name in ("agentic-os",):
                    continue

                entry_points = dist.entry_points
                capabilities = [ep.name for ep in entry_points if ep.group == "agentic_os.capabilities"]

                plugins.append(
                    DiscoveredPlugin(
                        name=name,
                        path=dist.locate_file("") if hasattr(dist, "locate_file") else "",
                        plugin_type=PluginType.PROVIDER if "provider" in name.lower() else PluginType.CUSTOM,
                        version=dist.version,
                        description=dist.metadata.get("Summary", ""),
                        author=dist.metadata.get("Author", ""),
                        capabilities=capabilities,
                        dependencies=[req.name for req in dist.requires if req] if dist.requires else [],
                        metadata={"source": "python_package"},
                    )
                )
        except Exception as exc:
            _log.debug("Python package discovery error: %s", exc)

        return plugins

    # ── Environment path discovery ──

    async def _discover_from_env_paths(self) -> list[DiscoveredPlugin]:
        """Discover plugins from environment-configured paths."""
        plugins: list[DiscoveredPlugin] = []
        env_paths = os.environ.get("AGENTIC_OS_PLUGIN_PATH", "")
        if not env_paths:
            return plugins

        for path_str in env_paths.split(os.pathsep):
            path = Path(path_str)
            if not path.is_dir():
                continue

            try:
                for entry in path.iterdir():
                    if entry.is_dir():
                        plugin = await self._scan_plugin_dir(entry)
                        if plugin:
                            plugins.append(plugin)
            except PermissionError:
                continue

        return plugins

    # ── Helpers ──

    @staticmethod
    def _get_plugin_search_dirs() -> list[Path]:
        """Return directories to search for plugins."""
        home = Path.home()
        config_home = Path(os.environ.get("XDG_CONFIG_HOME", home / ".config"))
        data_home = Path(os.environ.get("XDG_DATA_HOME", home / ".local" / "share"))

        dirs: list[Path] = [
            home / ".agentic_os" / "plugins",
            config_home / "agentic_os" / "plugins",
            data_home / "agentic_os" / "plugins",
            home / ".config" / "agentic_os" / "plugins",
            Path.cwd() / "plugins",
            Path.cwd() / "extensions",
        ]

        # Also check the installed package's plugin directory
        package_dir = Path(__file__).resolve().parent.parent.parent / "plugins"
        if package_dir.is_dir():
            dirs.append(package_dir)

        return dirs

    @staticmethod
    def _find_entry_point(plugin_dir: Path) -> str | None:
        """Find the entry point file in a plugin directory."""
        for entry_point in _PLUGIN_ENTRY_POINTS:
            candidate = plugin_dir / entry_point
            if candidate.exists():
                return str(candidate)

        # Also look for any .py or .js file at the root
        try:
            for f in plugin_dir.iterdir():
                if f.is_file() and f.suffix in (".py", ".js", ".ts", ".go", ".sh"):
                    return str(f)
        except PermissionError:
            pass

        return None

    @staticmethod
    def _deduplicate(plugins: list[DiscoveredPlugin]) -> list[DiscoveredPlugin]:
        """Deduplicate plugins by name, keeping the one with more information."""
        best: dict[str, DiscoveredPlugin] = {}
        for plugin in plugins:
            existing = best.get(plugin.name)
            if existing is None:
                best[plugin.name] = plugin
            else:
                # Prefer the one with version info
                if plugin.version and not existing.version:
                    best[plugin.name] = plugin
                elif plugin.description and not existing.description:
                    existing.description = plugin.description
                if plugin.capabilities:
                    existing.capabilities = list(set(existing.capabilities + plugin.capabilities))
                if plugin.dependencies:
                    existing.dependencies = list(set(existing.dependencies + plugin.dependencies))
        return list(best.values())
