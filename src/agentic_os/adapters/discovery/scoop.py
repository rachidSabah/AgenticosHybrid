"""Scoop Package Manager Discovery Provider.

Scans scoop-installed packages for AI coding assistants.
"""
import os
import subprocess
from dataclasses import dataclass, field
from typing import Any

from agentic_os.domain.execution import EngineCapability, EngineType
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.execution import DiscoveryProvider, EngineRegistration

log = get_logger("discovery.scoop")


@dataclass
class ScoopDiscovery(DiscoveryProvider):
    """Discovers AI coding assistants installed via Scoop."""

    _known_apps: tuple[dict[str, Any], ...] = field(
        default_factory=lambda: (
            {"name": "claude-code", "app": "claude-code", "engine": EngineType.CLAUDE_CODE,
             "caps": [EngineCapability.CODING, EngineCapability.REASONING, EngineCapability.TERMINAL]},
            {"name": "aider", "app": "aider", "engine": EngineType.AIDER,
             "caps": [EngineCapability.CODING, EngineCapability.PLANNING]},
            {"name": "goose", "app": "goose", "engine": EngineType.GOOSE,
             "caps": [EngineCapability.CODING, EngineCapability.PLANNING, EngineCapability.TERMINAL]},
            {"name": "git", "app": "git", "engine": EngineType.CUSTOM,
             "caps": [EngineCapability.GIT]},
        )
    )

    async def discover(self) -> list[EngineRegistration]:
        results: list[EngineRegistration] = []
        scoop_dir = os.path.join(os.path.expanduser("~"), "scoop", "apps")
        if not os.path.isdir(scoop_dir):
            return results

        for entry in self._known_apps:
            app_dir = os.path.join(scoop_dir, entry["app"], "current")
            if not os.path.isdir(app_dir):
                continue
            bin_path = None
            for ext in ("", ".exe", ".cmd", ".bat"):
                candidate = os.path.join(app_dir, entry["app"] + ext)
                if os.path.isfile(candidate):
                    bin_path = candidate
                    break
            if not bin_path:
                continue
            version = await self._get_version(bin_path)
            results.append(EngineRegistration(
                name=f"{entry['name']}-scoop",
                engine_type=entry["engine"],
                endpoint=f"local:{entry['app']}",
                transport="local",
                capabilities=entry["caps"],
                description=f"{entry['name'].title()} (Scoop)" + (f" v{version}" if version else ""),
                version=version or "unknown",
                tags=["discovered", "scoop", entry["app"]],
                metadata={"path": bin_path, "discovery_method": "scoop", "app": entry["app"]},
            ))
        return results

    def get_provider_name(self) -> str: return "scoop-discovery"
    def get_provider_type(self) -> str: return "scoop"

    @staticmethod
    async def _get_version(path: str) -> str | None:
        try:
            result = subprocess.run([path, "--version"], capture_output=True, timeout=5.0)
            return result.stdout.decode("utf-8", errors="replace").strip().split("\n")[0][:100] if result.returncode == 0 else None
        except (subprocess.TimeoutExpired, OSError, FileNotFoundError):
            return None
