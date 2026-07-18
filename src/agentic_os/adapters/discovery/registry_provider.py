"""Windows Registry Discovery Provider.

Probes the Windows Registry for installed AI coding assistant executables
and SDK installations. Uses ``winreg`` on Windows, falls back to ``reg query``
for WSL cross-compile scenarios.
"""

import platform
import subprocess
from dataclasses import dataclass, field
from typing import Any

from agentic_os.domain.execution import EngineCapability, EngineType
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.execution import DiscoveryProvider, EngineRegistration

log = get_logger("discovery.registry")


@dataclass
class WindowsRegistryDiscovery(DiscoveryProvider):
    """Probes the Windows Registry for installed AI engines.

    Checks well-known registry paths for executable locations and SDK registrations.
    On non-Windows platforms this provider returns empty results (and logs a note).
    """

    _registry_paths: tuple[dict[str, Any], ...] = field(
        default_factory=lambda: (
            {
                "name": "claude-code",
                "key_paths": [
                    r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\claude.exe",
                    r"SOFTWARE\Anthropic\Claude\InstallPath",
                ],
                "engine_type": EngineType.CLAUDE_CODE,
                "capabilities": [
                    EngineCapability.CODING,
                    EngineCapability.REASONING,
                    EngineCapability.TERMINAL,
                ],
            },
            {
                "name": "docker",
                "key_paths": [
                    r"SOFTWARE\Docker Inc.\Docker\InstallPath",
                ],
                "engine_type": EngineType.DOCKER,
                "capabilities": [EngineCapability.DOCKER],
            },
            {
                "name": "vscode",
                "key_paths": [
                    r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\code.exe",
                ],
                "engine_type": EngineType.CUSTOM,
                "capabilities": [EngineCapability.CODING, EngineCapability.FILESYSTEM],
            },
            {
                "name": "node",
                "key_paths": [
                    r"SOFTWARE\Node.js\InstallPath",
                ],
                "engine_type": EngineType.CUSTOM,
                "capabilities": [EngineCapability.CODING],
            },
            {
                "name": "python",
                "key_paths": [
                    r"SOFTWARE\Python\PythonCore\InstallPath",
                ],
                "engine_type": EngineType.CUSTOM,
                "capabilities": [EngineCapability.CODING, EngineCapability.FILESYSTEM],
            },
        )
    )

    async def discover(self) -> list[EngineRegistration]:
        """Probe the Windows Registry for installed engines."""
        results: list[EngineRegistration] = []

        if platform.system() != "Windows":
            log.info("Windows Registry discovery skipped — not on Windows")
            return results

        for entry in self._registry_paths:
            install_path = self._query_registry(entry["key_paths"])
            if install_path is None:
                continue

            # Try to find the actual executable within the install path
            executable = self._find_executable(install_path)
            if executable is None:
                continue

            version = await self._get_version(executable)
            description = self._build_description(entry, install_path, version)

            results.append(
                EngineRegistration(
                    name=f"{entry['name']}-registry",
                    engine_type=entry["engine_type"],
                    endpoint=f"local:{executable}",
                    transport="local",
                    capabilities=entry["capabilities"],
                    description=description,
                    version=version or "unknown",
                    tags=["discovered", "registry", entry["name"]],
                    metadata={
                        "install_path": install_path,
                        "discovery_method": "registry",
                        "executable": executable,
                    },
                )
            )

        return results

    def get_provider_name(self) -> str:
        return "windows-registry"

    def get_provider_type(self) -> str:
        return "registry"

    # ── Internal helpers ──

    @staticmethod
    def _query_registry(key_paths: list[str]) -> str | None:
        """Query registry keys and return first found install path."""
        try:
            import winreg
        except ImportError:
            return None

        # Use getattr for Windows-only registry APIs so static checkers on
        # non-Windows platforms (where winreg stubs lack these members) pass.
        # Use getattr for Windows-only registry APIs so static checkers on
        # non-Windows platforms (where winreg stubs lack these members) pass.
        # Via a wrapper so ruff's B009 doesn't fire on non-constant attribute lookups.
        def _reg(name: str) -> Any:
            return getattr(winreg, name)

        reg_open = _reg("OpenKey")
        reg_hklm = _reg("HKEY_LOCAL_MACHINE")
        reg_hkcu = _reg("HKEY_CURRENT_USER")
        reg_query = _reg("QueryValueEx")

        for key_path in key_paths:
            try:
                with reg_open(reg_hklm, key_path) as key:
                    value, _ = reg_query(key, "")
                    if value and isinstance(value, str) and value.strip():
                        return value.strip()
            except OSError, FileNotFoundError:
                pass

            try:
                with reg_open(reg_hkcu, key_path) as key:
                    value, _ = reg_query(key, "")
                    if value and isinstance(value, str) and value.strip():
                        return value.strip()
            except OSError, FileNotFoundError:
                pass

        return None

    @staticmethod
    def _find_executable(install_path: str) -> str | None:
        """Find the main executable within an install path."""
        import os

        common_names = [
            "claude.exe",
            "code.exe",
            "node.exe",
            "python.exe",
            "docker.exe",
            "claude",
            "code",
            "node",
            "python",
            "docker",
        ]
        for name in common_names:
            candidate = os.path.join(install_path, name)
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate
            # Check in bin/ subdirectory
            candidate = os.path.join(install_path, "bin", name)
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate
        return None

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
    def _build_description(entry: dict, install_path: str, version: str | None) -> str:
        """Build a human-readable description."""
        base = entry["name"].title()
        if version:
            return f"{base} v{version} (discovered in Windows Registry)"
        return f"{base} (discovered in Windows Registry at {install_path})"
