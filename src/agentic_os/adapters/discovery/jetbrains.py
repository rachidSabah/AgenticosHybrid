"""JetBrains Discovery Provider.

Detects JetBrains IDE installations and plugins that provide AI coding
assistant capabilities. Probes the JetBrains plugin directories for
known AI-enhancing plugins.
"""

import json
import os
import platform as platform_mod
import subprocess
from dataclasses import dataclass, field
from typing import Any

from agentic_os.domain.execution import EngineCapability, EngineType
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.execution import DiscoveryProvider, EngineRegistration

log = get_logger("discovery.jetbrains")


@dataclass
class JetBrainsDiscovery(DiscoveryProvider):
    """Probes JetBrains IDE installations and plugin directories.

    Detects JetBrains IDEs (IntelliJ IDEA, PyCharm, WebStorm, etc.),
    then scans their plugin directories for known AI-assistive plugins
    like AI Assistant, GitHub Copilot, and Codeium.
    Cross-platform: uses platform-specific plugin locations.
    """

    _ide_config_patterns: tuple[dict[str, Any], ...] = field(
        default_factory=lambda: (
            {
                "name": "IntelliJ IDEA",
                "config_dir": "JetBrains/IntelliJIdea*",
                "apps": ["idea", "idea.sh", "idea64.exe"],
                "cli_names": ["idea", "intellij"],
            },
            {
                "name": "PyCharm",
                "config_dir": "JetBrains/PyCharm*",
                "apps": ["pycharm", "pycharm.sh", "pycharm64.exe"],
                "cli_names": ["pycharm", "charm"],
            },
            {
                "name": "WebStorm",
                "config_dir": "JetBrains/WebStorm*",
                "apps": ["webstorm", "webstorm.sh", "webstorm64.exe"],
                "cli_names": ["webstorm"],
            },
            {
                "name": "GoLand",
                "config_dir": "JetBrains/GoLand*",
                "apps": ["goland", "goland.sh", "goland64.exe"],
                "cli_names": ["goland"],
            },
            {
                "name": "CLion",
                "config_dir": "JetBrains/CLion*",
                "apps": ["clion", "clion.sh", "clion64.exe"],
                "cli_names": ["clion"],
            },
            {
                "name": "RustRover",
                "config_dir": "JetBrains/RustRover*",
                "apps": ["rustrover", "rustrover.sh", "rustrover64.exe"],
                "cli_names": ["rustrover"],
            },
        )
    )

    _known_ai_plugins: tuple[dict[str, Any], ...] = field(
        default_factory=lambda: (
            {
                "name": "github-copilot",
                "dir_prefix": "github-copilot",
                "type": EngineType.CUSTOM,
                "capabilities": [EngineCapability.CODING, EngineCapability.REASONING],
            },
            {
                "name": "jetbrains-ai",
                "dir_prefix": "ai-assistant",
                "type": EngineType.CUSTOM,
                "capabilities": [EngineCapability.CODING, EngineCapability.REASONING],
            },
            {
                "name": "codeium",
                "dir_prefix": "codeium",
                "type": EngineType.CUSTOM,
                "capabilities": [EngineCapability.CODING],
            },
            {
                "name": "tabnine",
                "dir_prefix": "tabnine",
                "type": EngineType.CUSTOM,
                "capabilities": [EngineCapability.CODING],
            },
            {
                "name": "amazon-q",
                "dir_prefix": "amazon-q",
                "type": EngineType.CUSTOM,
                "capabilities": [EngineCapability.CODING, EngineCapability.PLANNING],
            },
            {
                "name": "continue",
                "dir_prefix": "continue",
                "type": EngineType.CUSTOM,
                "capabilities": [
                    EngineCapability.CODING,
                    EngineCapability.REASONING,
                    EngineCapability.FILESYSTEM,
                ],
            },
        )
    )

    async def discover(self) -> list[EngineRegistration]:
        """Probe JetBrains IDE installations and AI plugin directories."""
        results: list[EngineRegistration] = []
        system = platform_mod.system()

        plugin_roots = self._get_plugin_roots(system)
        if not plugin_roots:
            log.info("No JetBrains plugin roots found for platform", platform=system)
            return results

        for ide in self._ide_config_patterns:
            ide_name = ide["name"]

            # Find this IDE's CLI
            cli_paths = self._find_ide_cli(ide, system)
            for cli_path in cli_paths:
                ide_reg = await self._make_ide_registration(ide, cli_path)
                if ide_reg is not None:
                    results.append(ide_reg)

            # Scan for AI plugins
            plugin_dir = self._resolve_plugin_dir(plugin_roots, ide)
            if plugin_dir and os.path.isdir(plugin_dir):
                try:
                    plugin_results = await self._scan_plugins_dir(plugin_dir, ide_name)
                    results.extend(plugin_results)
                except (OSError, PermissionError) as exc:
                    log.warning("Cannot scan JetBrains plugin dir", path=plugin_dir, error=str(exc))

        return results

    def get_provider_name(self) -> str:
        return "jetbrains-discovery"

    def get_provider_type(self) -> str:
        return "jetbrains"

    # ── Internal ──

    @staticmethod
    def _get_plugin_roots(system: str) -> list[str]:
        """Get platform-specific JetBrains plugin root directories."""
        roots: list[str] = []

        if system == "Windows":
            local_app_data = os.environ.get("LOCALAPPDATA", "")
            app_data = os.environ.get("APPDATA", "")
            if local_app_data:
                roots.extend(
                    [
                        os.path.join(local_app_data, "JetBrains"),
                        os.path.join(local_app_data, "Programs", "JetBrains"),
                    ]
                )
            if app_data:
                roots.append(os.path.join(app_data, "JetBrains"))
            roots.append(os.path.expandvars(r"%USERPROFILE%\.cache\JetBrains"))

        elif system == "Darwin":
            roots.extend(
                [
                    os.path.expanduser("~/Library/Application Support/JetBrains"),
                    os.path.expanduser("~/Library/Caches/JetBrains"),
                    "/Applications/JetBrains Toolbox.app/Contents/app",
                ]
            )

        elif system == "Linux":
            roots.extend(
                [
                    os.path.expanduser("~/.local/share/JetBrains"),
                    os.path.expanduser("~/.cache/JetBrains"),
                    os.path.expanduser("~/.config/JetBrains"),
                    "/opt/JetBrains",
                    "/snap/jetbrains",
                ]
            )

        return roots

    @staticmethod
    def _resolve_plugin_dir(plugin_roots: list[str], ide: dict) -> str | None:
        """Resolve the plugin directory for a specific IDE."""
        config_pattern = ide["config_dir"]

        # Try the config pattern directly under each root
        for root in plugin_roots:
            import glob

            matches = glob.glob(os.path.join(root, config_pattern, "plugins"))
            if matches:
                return matches[0]

        # Fall back to glob without "plugins" subpath
        for root in plugin_roots:
            import glob

            matches = glob.glob(os.path.join(root, config_pattern))
            if matches:
                candidate = os.path.join(matches[0], "plugins")
                if os.path.isdir(candidate):
                    return candidate

        return None

    @staticmethod
    def _find_ide_cli(ide: dict, system: str) -> list[str]:
        """Find CLI launcher for a JetBrains IDE."""
        import shutil

        found: list[str] = []

        for cli_name in ide["cli_names"]:
            cli_path = shutil.which(cli_name)
            if cli_path:
                found.append(cli_path)

        if system == "Windows":
            for app_name in ide.get("apps", []):
                if "64.exe" in app_name:
                    paths = [
                        os.path.expandvars(rf"%LOCALAPPDATA%\Programs\JetBrains\bin\{app_name}"),
                        os.path.expandvars(rf"%ProgramFiles%\JetBrains\bin\{app_name}"),
                    ]
                    for path in paths:
                        if os.path.isfile(path):
                            found.append(path)

        elif system == "Darwin":
            for app_name in ide.get("apps", []):
                if app_name.startswith("idea"):
                    path = "/Applications/IntelliJ IDEA.app/Contents/MacOS/idea"
                    if os.path.isfile(path):
                        found.append(path)
                elif app_name.startswith("pycharm"):
                    path = "/Applications/PyCharm.app/Contents/MacOS/pycharm"
                    if os.path.isfile(path):
                        found.append(path)

        return found

    @staticmethod
    async def _find_ide_installations(system: str) -> list[dict]:
        """Use the JetBrains Toolbox to find installations (if available)."""
        import shutil

        toolbox = shutil.which("jetbrains-toolbox") or shutil.which("jetbrains-toolbox.exe")
        if toolbox is None:
            return []

        try:
            result = subprocess.run(
                [toolbox, "list", "--format", "json"],
                capture_output=True,
                text=True,
                timeout=15.0,
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                if isinstance(data, list):
                    return data
            return []
        except (subprocess.TimeoutExpired, OSError, json.JSONDecodeError) as exc:
            log.warning("JetBrains Toolbox listing failed", error=str(exc))
            return []

    async def _make_ide_registration(self, ide: dict, cli_path: str) -> EngineRegistration | None:
        """Create an EngineRegistration for a JetBrains IDE."""
        if not os.path.isfile(cli_path) or not os.access(cli_path, os.X_OK):
            return None

        version = await self._get_version(cli_path)

        return EngineRegistration(
            name=f"jetbrains-{ide['name'].lower().replace(' ', '-')}",
            engine_type=EngineType.CUSTOM,
            endpoint=f"local:{cli_path}",
            transport="local",
            capabilities=[EngineCapability.CODING, EngineCapability.FILESYSTEM],
            description=f"{ide['name']} v{version or '?'} (JetBrains IDE)",
            version=version or "unknown",
            tags=["discovered", "jetbrains", "ide", ide["name"].lower().replace(" ", "-")],
            metadata={
                "cli_path": cli_path,
                "ide_name": ide["name"],
                "discovery_method": "jetbrains",
            },
        )

    async def _scan_plugins_dir(self, plugin_dir: str, ide_name: str) -> list[EngineRegistration]:
        """Scan a JetBrains plugin directory for AI plugins."""
        results: list[EngineRegistration] = []

        try:
            entries = os.listdir(plugin_dir)
        except (OSError, PermissionError):
            return []

        for entry_name in entries:
            entry_path = os.path.join(plugin_dir, entry_name)
            if not os.path.isdir(entry_path):
                continue

            matched = self._match_plugin(entry_name)
            if matched is None:
                continue

            # Try to read plugin version from its properties
            version = await self._read_plugin_version(entry_path)

            results.append(
                EngineRegistration(
                    name=f"jetbrains-{matched['name']}-{ide_name.lower().replace(' ', '-')}",
                    engine_type=matched["type"],
                    endpoint=f"jetbrains:plugin:{matched['name']}",
                    transport="local",
                    capabilities=matched["capabilities"],
                    description=(
                        f"JetBrains AI plugin: {matched['name']} {version or ''} ({ide_name})"
                    ),
                    version=version or "unknown",
                    tags=["discovered", "jetbrains", "plugin", matched["name"]],
                    metadata={
                        "plugin_path": entry_path,
                        "plugin_dir": plugin_dir,
                        "ide_name": ide_name,
                        "discovery_method": "jetbrains",
                    },
                )
            )

        return results

    def _match_plugin(self, plugin_dir_name: str) -> dict | None:
        """Match a JetBrains plugin directory against known AI plugins."""
        name_lower = plugin_dir_name.lower()
        for known in self._known_ai_plugins:
            if known["dir_prefix"].lower() in name_lower:
                return known
        return None

    @staticmethod
    async def _read_plugin_version(plugin_path: str) -> str | None:
        """Read plugin version from plugin.xml or META-INF."""
        # Try plugin.xml
        meta_inf = os.path.join(plugin_path, "META-INF", "plugin.xml")
        if os.path.isfile(meta_inf):
            try:
                with open(meta_inf, encoding="utf-8") as f:
                    content = f.read(65536)
                import re

                match = re.search(r'version="([^"]+)"', content)
                if match:
                    return match.group(1)[:50]
            except (OSError, PermissionError):
                pass

        # Try package.json (for web-based plugins)
        pkg_path = os.path.join(plugin_path, "package.json")
        if os.path.isfile(pkg_path):
            try:
                with open(pkg_path, encoding="utf-8") as f:
                    pkg = json.loads(f.read(65536))
                return str(pkg.get("version", ""))[:50] or None
            except (json.JSONDecodeError, OSError):
                pass

        return None

    @staticmethod
    async def _get_version(executable: str) -> str | None:
        """Get the IDE version."""
        try:
            result = subprocess.run(
                [executable, "--version"],
                capture_output=True,
                text=True,
                timeout=5.0,
            )
            if result.returncode == 0:
                first_line = result.stdout.strip().split("\n")[0]
                return first_line[:100] if first_line else None
            return None
        except (subprocess.TimeoutExpired, OSError, FileNotFoundError):
            return None
