"""Chocolatey Discovery Provider.

Scans Chocolatey-installed packages for AI coding assistants.
"""

import asyncio
import locale
import os
import shlex
import subprocess
from dataclasses import dataclass, field
from typing import Any

from agentic_os.domain.execution import EngineCapability, EngineType
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.execution import DiscoveryProvider, EngineRegistration

log = get_logger("discovery.choco")


@dataclass
class ChocolateyDiscovery(DiscoveryProvider):
    """Discovers AI coding assistants installed via Chocolatey."""

    _known_packages: tuple[dict[str, Any], ...] = field(
        default_factory=lambda: (
            {
                "name": "claude-code",
                "package": "claude-code",
                "engine": EngineType.CLAUDE_CODE,
                "caps": [EngineCapability.CODING, EngineCapability.REASONING],
            },
            {
                "name": "aider",
                "package": "aider",
                "engine": EngineType.AIDER,
                "caps": [EngineCapability.CODING, EngineCapability.PLANNING],
            },
            {
                "name": "ollama",
                "package": "ollama",
                "engine": EngineType.CUSTOM,
                "caps": [EngineCapability.REASONING, EngineCapability.OFFLINE],
            },
        )
    )

    async def discover(self) -> list[EngineRegistration]:
        results: list[EngineRegistration] = []
        choco_dir = os.path.join(
            os.environ.get("ChocolateyInstall", "C:\\ProgramData\\chocolatey"), "bin"
        )
        if not os.path.isdir(choco_dir):
            return results

        for entry in self._known_packages:
            binary = entry["package"]
            path = os.path.join(choco_dir, f"{binary}.exe")
            if not os.path.isfile(path):
                path = os.path.join(choco_dir, binary)
                if not os.path.isfile(path):
                    continue
            version = await self._get_version(path)
            results.append(
                EngineRegistration(
                    name=f"{entry['name']}-choco",
                    engine_type=entry["engine"],
                    endpoint=f"local:{binary}",
                    transport="local",
                    capabilities=entry["caps"],
                    description=f"{entry['name'].title()} (Chocolatey)"
                    + (f" v{version}" if version else ""),
                    version=version or "unknown",
                    tags=["discovered", "chocolatey", binary],
                    metadata={"path": path, "discovery_method": "chocolatey", "binary": binary},
                )
            )
        return results

    def get_provider_name(self) -> str:
        return "chocolatey-discovery"

    def get_provider_type(self) -> str:
        return "chocolatey"

    @staticmethod
    async def _get_version(path: str) -> str | None:
        try:
            result = subprocess.run([path, "--version"], capture_output=True, timeout=5.0)
            return (
                result.stdout.decode("utf-8", errors="replace").strip().split("\n")[0][:100]
                if result.returncode == 0
                else None
            )
        except (subprocess.TimeoutExpired, OSError, FileNotFoundError):
            return None
