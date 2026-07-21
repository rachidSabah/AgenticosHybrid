"""Known Install Directory Discovery Provider.

Checks well-known installation directory paths for AI coding assistants
and developer tools. Captures engines installed by package managers that
place binaries in standard locations.
"""

import os
import platform as platform_mod
import subprocess
from dataclasses import dataclass, field
from typing import Any

from agentic_os.domain.execution import EngineCapability, EngineType
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.execution import DiscoveryProvider, EngineRegistration

log = get_logger("discovery.known_install_dirs")


@dataclass
class KnownInstallDirDiscovery(DiscoveryProvider):
    """Checks well-known installation directories for AI engines.

    Scans platform-specific standard install locations that aren't
    covered by PATH or registry scanning. Includes user home directories,
    common SDK directories, and package manager install roots.
    """

    _known_dirs: tuple[dict[str, Any], ...] = field(
        default_factory=lambda: (
            # Cross-platform home directory installs
            {
                "name": "claude",
                "dirs": [os.path.expanduser("~/.claude")],
                "binary": "claude",
                "type": EngineType.CLAUDE_CODE,
                "capabilities": [
                    EngineCapability.CODING,
                    EngineCapability.REASONING,
                    EngineCapability.TERMINAL,
                ],
            },
            {
                "name": "aider",
                "dirs": [os.path.expanduser("~/.local/bin")],
                "binary": "aider",
                "type": EngineType.AIDER,
                "capabilities": [EngineCapability.CODING, EngineCapability.PLANNING],
            },
            # Python virtual environments
            {
                "name": "python",
                "dirs": [os.path.expanduser("~/.local/bin"), "/usr/local/bin", "/opt/homebrew/bin"],
                "binary": "python3",
                "type": EngineType.CUSTOM,
                "capabilities": [EngineCapability.CODING, EngineCapability.FILESYSTEM],
            },
            # NPM global installs
            {
                "name": "node",
                "dirs": [
                    os.path.expanduser("~/.npm-global/bin"),
                    "/usr/local/share/npm/bin",
                    "/opt/homebrew/lib/node_modules/.bin",
                ],
                "binary": "node",
                "type": EngineType.CUSTOM,
                "capabilities": [EngineCapability.CODING],
            },
            # macOS Homebrew
            {
                "name": "claude",
                "dirs": ["/opt/homebrew/bin", "/usr/local/bin"],
                "binary": "claude",
                "type": EngineType.CLAUDE_CODE,
                "platform": "Darwin",
                "capabilities": [EngineCapability.CODING, EngineCapability.REASONING],
            },
            # Snap packages (Linux)
            {
                "name": "claude",
                "dirs": ["/snap/bin"],
                "binary": "claude",
                "type": EngineType.CLAUDE_CODE,
                "platform": "Linux",
                "capabilities": [EngineCapability.CODING, EngineCapability.REASONING],
            },
            # Cargo installs (Rust)
            {
                "name": "claude",
                "dirs": [os.path.expanduser("~/.cargo/bin")],
                "binary": "claude",
                "type": EngineType.CLAUDE_CODE,
                "capabilities": [EngineCapability.CODING, EngineCapability.REASONING],
            },
        )
    )

    async def discover(self) -> list[EngineRegistration]:
        """Scan known install directories for engine binaries."""
        results: list[EngineRegistration] = []
        system = platform_mod.system()

        for entry in self._known_dirs:
            platform_filter = entry.get("platform")
            if platform_filter and system != platform_filter:
                continue

            binary = entry["binary"]
            engine_type = entry["type"]
            capabilities = entry["capabilities"]

            for directory in entry["dirs"]:
                candidate = os.path.join(directory, binary)
                if not os.path.isfile(candidate) or not os.access(candidate, os.X_OK):
                    continue

                version = await self._get_version(candidate)
                description = self._build_description(entry, candidate, version)

                results.append(
                    EngineRegistration(
                        name=f"{entry['name']}-inst-{binary}",
                        engine_type=engine_type,
                        endpoint=f"local:{candidate}",
                        transport="local",
                        capabilities=capabilities,
                        description=description,
                        version=version or "unknown",
                        tags=["discovered", "known-install-dir", binary],
                        metadata={
                            "path": candidate,
                            "install_dir": directory,
                            "discovery_method": "known_install_dirs",
                            "binary": binary,
                        },
                    )
                )

        return results

    def get_provider_name(self) -> str:
        return "known-install-dirs"

    def get_provider_type(self) -> str:
        return "known_install_dirs"

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
        except (subprocess.TimeoutExpired, OSError, FileNotFoundError):
            return None

    @staticmethod
    def _build_description(entry: dict, match_path: str, version: str | None) -> str:
        """Build a human-readable description."""
        base = entry["name"].title()
        if version:
            return f"{base} v{version} (well-known install dir: {match_path})"
        return f"{base} (well-known install dir: {match_path})"
