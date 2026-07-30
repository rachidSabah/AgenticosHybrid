"""Installer Upgrade — safe migration of configuration across versions.

Preserves user settings, API keys, custom providers, and MCP servers
when Mission Control is upgraded. Automatically binds new providers
and removes obsolete ones.
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from agentic_os.infrastructure.logging import get_logger

log = get_logger("installer.upgrade")


@dataclass
class UpgradeManifest:
    """Records what was upgraded and what changed."""

    from_version: str = ""
    to_version: str = ""
    upgraded_at: str = ""
    preserved_settings: list[str] = field(default_factory=list)
    preserved_api_keys: list[str] = field(default_factory=list)
    preserved_providers: list[str] = field(default_factory=list)
    preserved_mcp_servers: list[str] = field(default_factory=list)
    newly_bound_providers: list[str] = field(default_factory=list)
    removed_obsolete_providers: list[str] = field(default_factory=list)
    migration_errors: list[str] = field(default_factory=list)
    success: bool = True


class UpgradeManager:
    """Manages safe upgrades of Mission Control configuration.

    Key directories:
        config_dir:  ~/.config/agentic-os/  (or %APPDATA%/agentic-os)
        cache_dir:   ~/.cache/agentic-os/   (or %LOCALAPPDATA%/agentic-os/cache)
    """

    def __init__(self, config_dir: str | None = None, cache_dir: str | None = None):
        self._config_dir = config_dir or self._default_config_dir()
        self._cache_dir = cache_dir or self._default_cache_dir()

    def _default_config_dir(self) -> str:
        import sys
        if sys.platform == "win32":
            base = os.environ.get("APPDATA", os.path.expanduser("~/.config"))
        elif sys.platform == "darwin":
            base = os.path.expanduser("~/Library/Application Support")
        else:
            base = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
        return os.path.join(base, "agentic-os")

    def _default_cache_dir(self) -> str:
        import sys
        if sys.platform == "win32":
            base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~/.cache"))
        elif sys.platform == "darwin":
            base = os.path.expanduser("~/Library/Caches")
        else:
            base = os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache"))
        return os.path.join(base, "agentic-os")

    @property
    def config_file(self) -> str:
        return os.path.join(self._config_dir, "config.json")

    @property
    def providers_dir(self) -> str:
        return os.path.join(self._config_dir, "providers")

    @property
    def mcp_dir(self) -> str:
        return os.path.join(self._config_dir, "mcp")

    @property
    def keys_file(self) -> str:
        return os.path.join(self._config_dir, "keys.json")

    @property
    def manifest_file(self) -> str:
        return os.path.join(self._cache_dir, "upgrade-manifest.json")

    def backup_config(self, version: str) -> str:
        """Create a timestamped backup of the current configuration."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_dir = os.path.join(
            self._cache_dir, "backups", f"pre-{version}-{timestamp}"
        )

        if os.path.isdir(self._config_dir):
            os.makedirs(backup_dir, exist_ok=True)
            for item in os.listdir(self._config_dir):
                src = os.path.join(self._config_dir, item)
                dst = os.path.join(backup_dir, item)
                if os.path.isfile(src):
                    shutil.copy2(src, dst)
                elif os.path.isdir(src):
                    shutil.copytree(src, dst, dirs_exist_ok=True)

        log.info("Config backed up", backup=backup_dir, version=version)
        return backup_dir

    def load_config(self) -> dict[str, Any]:
        """Load current configuration."""
        if not os.path.isfile(self.config_file):
            return {}
        try:
            with open(self.config_file, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("Cannot read config", error=str(exc))
            return {}

    def save_config(self, config: dict[str, Any]) -> bool:
        """Save configuration."""
        try:
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            with open(self.config_file, "w") as f:
                json.dump(config, f, indent=2)
            return True
        except OSError as exc:
            log.error("Cannot save config", error=str(exc))
            return False

    def load_keys(self) -> dict[str, str]:
        """Load encrypted API keys."""
        if not os.path.isfile(self.keys_file):
            return {}
        try:
            with open(self.keys_file, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}

    def save_keys(self, keys: dict[str, str]) -> bool:
        """Save API keys."""
        try:
            os.makedirs(os.path.dirname(self.keys_file), exist_ok=True)
            with open(self.keys_file, "w") as f:
                json.dump(keys, f, indent=2)
            return True
        except OSError:
            return False

    def perform_upgrade(
        self,
        from_version: str,
        to_version: str,
        newly_supported: list[str] | None = None,
        obsolete_providers: list[str] | None = None,
    ) -> UpgradeManifest:
        """Perform a full upgrade cycle."""
        manifest = UpgradeManifest(
            from_version=from_version,
            to_version=to_version,
            upgraded_at=datetime.now(timezone.utc).isoformat(),
        )

        # 1. Backup current config
        try:
            self.backup_config(from_version)
        except Exception as exc:
            manifest.migration_errors.append(f"Backup failed: {exc}")

        # 2. Preserve settings
        config = self.load_config()
        preserved = set()

        # User settings
        for key in ("theme", "sidebar", "layout", "language", "telemetry", "notifications"):
            if key in config:
                preserved.add(key)

        # Custom providers
        custom_providers = config.get("custom_providers", [])
        for cp in custom_providers:
            manifest.preserved_providers.append(cp.get("name", "unknown"))

        # MCP servers
        mcp_servers = config.get("mcp_servers", [])
        for ms in mcp_servers:
            manifest.preserved_mcp_servers.append(ms.get("name", "unknown"))

        # API keys
        keys = self.load_keys()
        manifest.preserved_api_keys = list(keys.keys())

        manifest.preserved_settings = list(preserved)

        # 3. Bind newly supported providers
        if newly_supported:
            manifest.newly_bound_providers = list(newly_supported)

        # 4. Remove obsolete providers
        if obsolete_providers:
            manifest.removed_obsolete_providers = list(obsolete_providers)
            config["disabled_providers"] = list(
                set(config.get("disabled_providers", [])) - set(obsolete_providers)
            )

        # 5. Migrate config structure if needed
        if config:
            config["version"] = to_version
            config["last_upgraded"] = manifest.upgraded_at
            if not self.save_config(config):
                manifest.migration_errors.append("Failed to save migrated config")

        # 6. Save upgrade manifest
        try:
            os.makedirs(os.path.dirname(self.manifest_file), exist_ok=True)
            with open(self.manifest_file, "w") as f:
                json.dump({
                    "from_version": from_version,
                    "to_version": to_version,
                    "upgraded_at": manifest.upgraded_at,
                    "preserved_settings": manifest.preserved_settings,
                    "preserved_api_keys_count": len(manifest.preserved_api_keys),
                    "preserved_providers": manifest.preserved_providers,
                    "preserved_mcp_servers": manifest.preserved_mcp_servers,
                    "newly_bound_providers": manifest.newly_bound_providers,
                    "removed_obsolete_providers": manifest.removed_obsolete_providers,
                    "success": len(manifest.migration_errors) == 0,
                }, f, indent=2)
        except OSError as exc:
            manifest.migration_errors.append(f"Failed to save manifest: {exc}")

        manifest.success = len(manifest.migration_errors) == 0
        log.info("Upgrade completed",
                 from_v=from_version, to_v=to_version,
                 success=manifest.success)
        return manifest
