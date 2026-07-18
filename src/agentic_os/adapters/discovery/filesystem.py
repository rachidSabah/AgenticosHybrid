"""Filesystem Discovery Provider.

Scans well-known directories for AI coding assistant executables using
glob patterns. Catches engines installed in non-PATH locations.
"""

import glob
import os
import platform as platform_mod
import subprocess
from dataclasses import dataclass, field
from typing import Any

from agentic_os.domain.execution import EngineCapability, EngineType
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.execution import DiscoveryProvider, EngineRegistration

log = get_logger("discovery.filesystem")


@dataclass
class FilesystemDiscovery(DiscoveryProvider):
    """Scans filesystem directories for AI coding assistant executables.

    Uses glob patterns against well-known install directories to find
    executables. Useful for finding engines installed via package managers,
    SDKs, or manual installation that aren't on the system PATH.
    """

    _scan_patterns: tuple[dict[str, Any], ...] = field(
        default_factory=lambda: (
            # Linux/macOS common install paths
            {
                "name": "claude-code",
                "patterns": [
                    "/usr/local/bin/claude",
                    "/opt/claude/claude",
                    "/home/*/.local/bin/claude",
                    "/snap/bin/claude",
                ],
                "type": EngineType.CLAUDE_CODE,
                "platform": ["Linux", "Darwin"],
                "capabilities": [
                    EngineCapability.CODING,
                    EngineCapability.REASONING,
                    EngineCapability.TERMINAL,
                ],
            },
            {
                "name": "docker",
                "patterns": ["/usr/local/bin/docker", "/usr/bin/docker", "/snap/bin/docker"],
                "type": EngineType.DOCKER,
                "platform": ["Linux", "Darwin"],
                "capabilities": [EngineCapability.DOCKER],
            },
            {
                "name": "node",
                "patterns": [
                    "/usr/local/bin/node",
                    "/usr/bin/node",
                    "/opt/homebrew/bin/node",
                    "/snap/bin/node",
                    "/home/*/.nvm/versions/node/*/bin/node",
                ],
                "type": EngineType.CUSTOM,
                "platform": ["Linux", "Darwin"],
                "capabilities": [EngineCapability.CODING],
            },
            {
                "name": "aider",
                "patterns": [
                    "/usr/local/bin/aider",
                    "/home/*/.local/bin/aider",
                    "/opt/homebrew/bin/aider",
                ],
                "type": EngineType.AIDER,
                "platform": ["Linux", "Darwin"],
                "capabilities": [EngineCapability.CODING, EngineCapability.PLANNING],
            },
            # Windows common install paths
            {
                "name": "claude-code",
                "patterns": [
                    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Claude\claude.exe"),
                    os.path.expandvars(r"%APPDATA%\Claude\claude.exe"),
                ],
                "type": EngineType.CLAUDE_CODE,
                "platform": ["Windows"],
                "capabilities": [
                    EngineCapability.CODING,
                    EngineCapability.REASONING,
                    EngineCapability.TERMINAL,
                ],
            },
            {
                "name": "docker",
                "patterns": [
                    os.path.expandvars(r"%ProgramFiles%\Docker\Docker\resources\bin\docker.exe"),
                    r"C:\Program Files\Docker\Docker\resources\bin\docker.exe",
                ],
                "type": EngineType.DOCKER,
                "platform": ["Windows"],
                "capabilities": [EngineCapability.DOCKER],
            },
        )
    )

    async def discover(self) -> list[EngineRegistration]:
        """Scan filesystem for known engine executables."""
        results: list[EngineRegistration] = []
        system = platform_mod.system()

        for entry in self._scan_patterns:
            platform_list = entry.get("platform", [])
            if platform_list and system not in platform_list:
                continue

            engine_type = entry["type"]
            capabilities = entry["capabilities"]

            for pattern in entry["patterns"]:
                matches = glob.glob(pattern)
                for match in matches:
                    if not os.path.isfile(match) or not os.access(match, os.X_OK):
                        continue

                    version = await self._get_version(match)
                    description = self._build_description(entry, match, version)

                    results.append(
                        EngineRegistration(
                            name=f"{entry['name']}-fs-{os.path.basename(match).replace('.', '-')}",
                            engine_type=engine_type,
                            endpoint=f"local:{match}",
                            transport="local",
                            capabilities=capabilities,
                            description=description,
                            version=version or "unknown",
                            tags=["discovered", "filesystem", entry["name"]],
                            metadata={
                                "path": match,
                                "discovery_method": "filesystem",
                                "pattern": pattern,
                            },
                        )
                    )

        return results

    def get_provider_name(self) -> str:
        return "filesystem-discovery"

    def get_provider_type(self) -> str:
        return "filesystem"

    # ── Internal ──

    @staticmethod
    async def _get_version(executable: str) -> str | None:
        """Try to get the version of an executable."""
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
        except subprocess.TimeoutExpired, OSError, FileNotFoundError:
            return None

    @staticmethod
    def _build_description(entry: dict, match_path: str, version: str | None) -> str:
        """Build a human-readable description."""
        base = entry["name"].title()
        if version:
            return f"{base} v{version} (discovered at {match_path})"
        return f"{base} (discovered at {match_path})"
