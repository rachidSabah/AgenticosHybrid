"""WSL Discovery Provider.

Probes Windows Subsystem for Linux for available AI coding assistant
executables. Runs ``wsl.exe --list --verbose`` to find distros, then
probes each for known binaries.
"""

import platform
import re
import subprocess
from dataclasses import dataclass, field
from typing import Any

from agentic_os.domain.execution import EngineCapability, EngineType
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.execution import DiscoveryProvider, EngineRegistration

log = get_logger("discovery.wsl")


@dataclass
class WslDiscovery(DiscoveryProvider):
    """Probes WSL for AI coding assistant executables.

    Runs ``wsl.exe --list --verbose`` to detect installed distros, then
    runs ``which <binary>`` inside each distro to find known tools.
    On non-Windows platforms this provider returns empty results.
    """

    _known_binaries: tuple[dict[str, Any], ...] = field(
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
                "name": "node",
                "binary": "node",
                "type": EngineType.CUSTOM,
                "capabilities": [EngineCapability.CODING],
            },
            {
                "name": "python3",
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
            },
        )
    )

    async def discover(self) -> list[EngineRegistration]:
        """Probe WSL distros for known AI executables."""
        results: list[EngineRegistration] = []

        if platform.system() != "Windows":
            log.info("WSL discovery skipped — not on Windows")
            return results

        distros = self._list_distros()
        if not distros:
            log.info("No WSL distros found")
            return results

        for distro in distros:
            distro_results = await self._scan_distro(distro)
            results.extend(distro_results)

        return results

    def get_provider_name(self) -> str:
        return "wsl-discovery"

    def get_provider_type(self) -> str:
        return "wsl"

    # ── Internal ──

    @staticmethod
    def _list_distros() -> list[str]:
        """Run ``wsl.exe --list --verbose`` and parse distro names."""
        try:
            result = subprocess.run(
                ["wsl.exe", "--list", "--verbose"],
                capture_output=True,
                text=True,
                timeout=30.0,
            )
            if result.returncode != 0:
                return []

            distros: list[str] = []
            lines = result.stdout.strip().split("\n")
            # Skip header line
            for line in lines[1:]:
                line = line.strip()
                if not line:
                    continue
                parts = re.split(r"\s+", line, maxsplit=3)
                if len(parts) >= 2:
                    distro_name = parts[1] if parts[0].isdigit() else parts[0]
                    distros.append(distro_name)

            return distros
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
            log.warning("Failed to list WSL distros", error=str(exc))
            return []

    async def _scan_distro(self, distro: str) -> list[EngineRegistration]:
        """Scan a single WSL distro for known binaries."""
        results: list[EngineRegistration] = []

        for entry in self._known_binaries:
            binary = entry["binary"]
            wsl_path = self._which_in_wsl(distro, binary)
            if wsl_path is None:
                continue

            version = self._get_version_in_wsl(distro, wsl_path)
            description = self._build_description(entry, distro, wsl_path, version)

            results.append(
                EngineRegistration(
                    name=f"{entry['name']}-wsl-{distro.lower().replace(' ', '-')}",
                    engine_type=entry["type"],
                    endpoint=f"wsl:{distro}:{wsl_path}",
                    transport="wsl",
                    capabilities=entry["capabilities"],
                    description=description,
                    version=version or "unknown",
                    tags=["discovered", "wsl", distro.lower(), binary],
                    metadata={
                        "wsl_distro": distro,
                        "wsl_path": wsl_path,
                        "discovery_method": "wsl",
                        "binary": binary,
                    },
                )
            )

        return results

    @staticmethod
    def _which_in_wsl(distro: str, binary: str) -> str | None:
        """Run ``which <binary>`` inside a WSL distro."""
        try:
            result = subprocess.run(
                ["wsl.exe", "-d", distro, "--", "which", binary],
                capture_output=True,
                text=True,
                timeout=15.0,
            )
            if result.returncode == 0:
                path = result.stdout.strip()
                return path if path else None
            return None
        except subprocess.TimeoutExpired, OSError:
            return None

    @staticmethod
    def _get_version_in_wsl(distro: str, binary_path: str) -> str | None:
        """Get the version of a binary inside a WSL distro."""
        try:
            result = subprocess.run(
                ["wsl.exe", "-d", distro, "--", binary_path, "--version"],
                capture_output=True,
                text=True,
                timeout=15.0,
            )
            if result.returncode == 0:
                first_line = result.stdout.strip().split("\n")[0]
                return first_line[:100] if first_line else None
            return None
        except subprocess.TimeoutExpired, OSError:
            return None

    @staticmethod
    def _build_description(entry: dict, distro: str, wsl_path: str, version: str | None) -> str:
        """Build a human-readable description."""
        base = entry["name"].title()
        if version:
            return f"{base} v{version} (WSL {distro}: {wsl_path})"
        return f"{base} (WSL {distro}: {wsl_path})"
