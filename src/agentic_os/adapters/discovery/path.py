"""
Path Discovery Provider

Scans the system PATH for known AI coding assistant executables.
Returns EngineRegistration entries for each found executable.
"""

import locale
import os
import platform
import shlex
import subprocess
from dataclasses import dataclass, field
from typing import Any

from agentic_os.domain.execution import EngineCapability, EngineType
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.execution import DiscoveryProvider, EngineRegistration

log = get_logger("discovery.path")


@dataclass
class PathDiscovery(DiscoveryProvider):
    """
    Scans PATH for known AI execution tools.

    Checks common binary names, runs --version probes, and returns
    DiscoveryResult with confidence based on exit code and version parsing.
    """

    _known_executables: tuple[dict[str, Any], ...] = field(
        default_factory=lambda: (
            {
                "name": "claude",
                "binary": "claude",
                "type": EngineType.CLAUDE_CODE,
                "capabilities": [
                    EngineCapability.CODING,
                    EngineCapability.REASONING,
                    EngineCapability.TERMINAL,
                ],
            },
            {
                "name": "docker",
                "binary": "docker",
                "type": EngineType.DOCKER,
                "capabilities": [EngineCapability.DOCKER],
            },
            {
                "name": "wsl",
                "binary": "wsl.exe",
                "type": EngineType.WSL,
                "capabilities": [EngineCapability.TERMINAL],
                "platform": "Windows",
            },
            {
                "name": "node",
                "binary": "node",
                "type": EngineType.CUSTOM,
                "capabilities": [EngineCapability.CODING],
            },
            {
                "name": "python",
                "binary": "python3",
                "type": EngineType.CUSTOM,
                "capabilities": [EngineCapability.CODING, EngineCapability.FILESYSTEM],
            },
            {
                "name": "aider",
                "binary": "aider",
                "type": EngineType.AIDER,
                "capabilities": [EngineCapability.CODING, EngineCapability.PLANNING],
            },
            {
                "name": "code",
                "binary": "code",
                "type": EngineType.CUSTOM,
                "capabilities": [EngineCapability.CODING, EngineCapability.FILESYSTEM],
                "version_flag": "--version",
            },
        )
    )

    async def discover(self) -> list[EngineRegistration]:
        """Scan PATH for known executables and return registrations."""
        results: list[EngineRegistration] = []

        for entry in self._known_executables:
            # Skip platform-specific entries
            plat = entry.get("platform", "")
            if plat and platform.system() != plat:
                continue

            binary = entry["binary"]
            path = self._which(binary)
            if path is None:
                continue

            version = await self._get_version(path, entry.get("version_flag", "--version"))
            description = self._build_description(entry, version)

            results.append(
                EngineRegistration(
                    name=f"{entry['name']}-local",
                    engine_type=entry["type"],
                    endpoint=f"local:{binary}",
                    transport="local",
                    capabilities=entry["capabilities"],
                    description=description,
                    version=version or "unknown",
                    tags=["discovered", "path", binary],
                    metadata={
                        "path": path,
                        "discovery_method": "path",
                        "binary": binary,
                    },
                )
            )

        return results

    def get_provider_name(self) -> str:
        return "path-discovery"

    def get_provider_type(self) -> str:
        return "path"

    @staticmethod
    def _which(binary: str) -> str | None:
        """Check if a binary is available on PATH."""
        path = os.pathsep.join(
            [
                os.environ.get("PATH", ""),
                "/usr/local/bin",
                "/usr/bin",
                "/bin",
                "/opt/homebrew/bin",
            ]
        )
        for dirpath in path.split(os.pathsep):
            full = os.path.join(dirpath, binary)
            if os.path.isfile(full) and os.access(full, os.X_OK):
                return full
        return None

    @staticmethod
    async def _get_version(path: str, flag: str) -> str | None:
        """Try to get the version of an executable."""
        try:
            result = subprocess.run(
                [path, *shlex.split(flag)],
                capture_output=True,
                timeout=5.0,
            )
            if result.returncode == 0:
                raw = result.stdout
                if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
                    raw = raw.decode("utf-16", errors="replace")

                elif b"\x00" in raw:
                    raw = raw.decode("utf-16-le", errors="replace")

                else:
                    enc = locale.getpreferredencoding(False) or "utf-8"
                    raw = raw.decode(enc, errors="replace")

                first_line = raw.strip().split("\n")[0]
                return first_line[:100] if first_line else None
            return None
        except subprocess.TimeoutExpired, OSError, FileNotFoundError:
            return None

    @staticmethod
    def _build_description(entry: dict[str, Any], version: str | None) -> str:
        """Build a human-readable description."""
        base = entry.get("name", entry["binary"]).title()
        if version:
            return f"{base} v{version} (discovered on PATH)"
        return f"{base} (discovered on PATH)"
