"""Config File Discovery Provider.

Reads engine configuration from well-known config files (YAML, JSON, TOML)
that specify AI coding assistant endpoints, SDKs, or tool configurations.
"""

import json
import os
from dataclasses import dataclass, field
from typing import Any

from agentic_os.domain.execution import EngineCapability, EngineType
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.execution import DiscoveryProvider, EngineRegistration

log = get_logger("discovery.config_file")


@dataclass
class ConfigFileDiscovery(DiscoveryProvider):
    """Reads well-known config files for engine endpoint definitions.

    Scans standard configuration file locations for references to AI
    coding assistants. Supports JSON, YAML, and TOML config files.
    Cross-platform: reads from home directory and common app config dirs.
    """

    _config_paths: tuple[dict[str, Any], ...] = field(
        default_factory=lambda: (
            # Claude Code config
            {
                "name": "claude-code",
                "paths": [
                    os.path.expanduser("~/.claude/config.json"),
                    os.path.expanduser("~/.claude/config.yaml"),
                    os.path.expanduser("~/.claude/config.yml"),
                ],
                "files": ["config.json", "config.yaml", "config.yml"],
                "engine_type": EngineType.CLAUDE_CODE,
                "config_dir": os.path.expanduser("~/.claude"),
                "capabilities": [
                    EngineCapability.CODING,
                    EngineCapability.REASONING,
                    EngineCapability.TERMINAL,
                ],
            },
            # Aider config
            {
                "name": "aider",
                "paths": [
                    os.path.expanduser("~/.aider.conf.yml"),
                    os.path.expanduser("~/.aider/aider.conf.yml"),
                ],
                "files": [".aider.conf.yml", "aider.conf.yml"],
                "engine_type": EngineType.AIDER,
                "config_dir": os.path.expanduser("~/.aider"),
                "capabilities": [EngineCapability.CODING, EngineCapability.PLANNING],
            },
            # Docker config
            {
                "name": "docker",
                "paths": [
                    os.path.expanduser("~/.docker/config.json"),
                ],
                "files": ["config.json"],
                "engine_type": EngineType.DOCKER,
                "config_dir": os.path.expanduser("~/.docker"),
                "capabilities": [EngineCapability.DOCKER],
            },
            # pipx installed tools
            {
                "name": "pipx",
                "paths": [
                    os.path.expanduser("~/.local/pipx/venvs"),
                ],
                "files": [],
                "engine_type": EngineType.CUSTOM,
                "config_dir": os.path.expanduser("~/.local/pipx"),
                "capabilities": [EngineCapability.CODING],
            },
            # npm global config
            {
                "name": "npm-global",
                "paths": [
                    os.path.expanduser("~/.npmrc"),
                ],
                "files": [],
                "engine_type": EngineType.CUSTOM,
                "config_dir": "",
                "capabilities": [EngineCapability.CODING],
            },
        )
    )

    _config_readers: tuple[str, ...] = field(
        default_factory=lambda: (
            "json",
            "yaml",
            "toml",
        )
    )

    async def discover(self) -> list[EngineRegistration]:
        """Read config files and extract engine registrations."""
        results: list[EngineRegistration] = []

        for entry in self._config_paths:
            # Check explicit paths first
            found = False
            for config_path in entry["paths"]:
                if os.path.isfile(config_path):
                    registration = await self._parse_config_file(entry, config_path)
                    if registration is not None:
                        results.append(registration)
                        found = True

            # If no specific config file found, check config directory for known files
            if not found and entry.get("config_dir") and os.path.isdir(entry["config_dir"]):
                for file_name in entry.get("files", []):
                    config_path = os.path.join(entry["config_dir"], file_name)
                    if os.path.isfile(config_path):
                        registration = await self._parse_config_file(entry, config_path)
                        if registration is not None:
                            results.append(registration)
                            break

        return results

    def get_provider_name(self) -> str:
        return "config-file-discovery"

    def get_provider_type(self) -> str:
        return "config_file"

    # ── Internal ──

    async def _parse_config_file(self, entry: dict, config_path: str) -> EngineRegistration | None:
        """Parse a config file and extract engine information."""
        try:
            with open(config_path, encoding="utf-8") as f:
                content = f.read(65536)  # 64 KiB max
        except (OSError, PermissionError) as exc:
            log.warning("Cannot read config file", path=config_path, error=str(exc))
            return None

        ext = os.path.splitext(config_path)[1].lower()
        config_data: dict | None = None

        try:
            if ext == ".json":
                config_data = json.loads(content)
            elif ext in (".yaml", ".yml"):
                config_data = self._parse_yaml_simple(content)
            elif ext == ".toml":
                config_data = self._parse_toml_simple(content)
            else:
                # Try each reader in order
                if isinstance(content, str):
                    config_data = json.loads(content)
        except (json.JSONDecodeError, ValueError):
            pass

        if config_data is None or not isinstance(config_data, dict):
            return None

        return self._build_registration(entry, config_data, config_path)

    def _build_registration(
        self,
        entry: dict,
        config_data: dict,
        config_path: str,
    ) -> EngineRegistration | None:
        """Build an EngineRegistration from parsed config data."""
        # Look for executable references in common config keys
        executable = self._extract_executable(config_data)
        if executable is None or not executable.strip():
            # Config exists but no executable reference — that's expected
            # Register based on config existence alone (lower confidence)
            return EngineRegistration(
                name=f"{entry['name']}-config",
                engine_type=entry["engine_type"],
                endpoint="config:discovered",
                transport="local",
                capabilities=entry["capabilities"],
                description=f"{entry['name'].title()} config found at {config_path}",
                version="",
                tags=["discovered", "config-file", entry["name"]],
                metadata={
                    "config_path": config_path,
                    "discovery_method": "config_file",
                },
            )

        version = self._extract_version(config_data, entry)
        description = f"{entry['name'].title()} (config file: {config_path})"
        if version:
            description = f"{entry['name'].title()} v{version} (config file: {config_path})"

        return EngineRegistration(
            name=f"{entry['name']}-config",
            engine_type=entry["engine_type"],
            endpoint=f"local:{executable}",
            transport="local",
            capabilities=entry["capabilities"],
            description=description,
            version=version or "",
            tags=["discovered", "config-file", entry["name"]],
            metadata={
                "config_path": config_path,
                "executable": executable,
                "discovery_method": "config_file",
            },
        )

    @staticmethod
    def _extract_executable(config_data: dict) -> str | None:
        """Extract executable path from config data."""
        for key in ("executable", "exe", "binary", "path", "bin", "command"):
            if key in config_data and isinstance(config_data[key], str):
                return config_data[key]
        return None

    @staticmethod
    def _extract_version(config_data: dict, entry: dict) -> str | None:
        """Extract version string from config data."""
        for key in ("version", "release", "tag"):
            if key in config_data and isinstance(config_data[key], str):
                return config_data[key]
        return None

    @staticmethod
    def _parse_yaml_simple(content: str) -> dict | None:
        """A basic YAML parser for simple key-value configs.

        Full YAML parsing would require the ``yaml`` package; this handles
        the common subset found in tool config files.
        """
        try:
            result: dict = {}
            for line in content.split("\n"):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if ":" in line:
                    key, _, value = line.partition(":")
                    key = key.strip()
                    value = value.strip().strip("'\"").strip()
                    if key:
                        result[key] = value
            return result if result else None
        except (ValueError, OSError):
            return None

    @staticmethod
    def _parse_toml_simple(content: str) -> dict | None:
        """A basic TOML parser for simple key-value configs.

        Full TOML parsing would require the ``toml`` package; this handles
        the common subset found in tool config files.
        """
        try:
            result: dict = {}
            current_section: dict | None = None
            for line in content.split("\n"):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("[") and line.endswith("]"):
                    current_section = None
                    continue
                if "=" in line:
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip().strip("'\"").strip()
                    if current_section is not None:
                        current_section[key] = value
                    elif key:
                        result[key] = value
            return result if result else None
        except (ValueError, OSError):
            return None
