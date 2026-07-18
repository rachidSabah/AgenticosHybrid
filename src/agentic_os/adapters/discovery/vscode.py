"""VS Code Discovery Provider.

Detects VS Code installations and extensions that provide AI coding
assistant capabilities. Probes the VS Code extensions directory for
known AI-enhancing extensions.
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

log = get_logger("discovery.vscode")


@dataclass
class VSCodeDiscovery(DiscoveryProvider):
    """Probes VS Code installations and extensions for AI coding tools.

    Detects VS Code itself (``code`` CLI), then scans the extensions
    directory for known AI-enhancing extensions like Claude Dev,
    GitHub Copilot, Continue.dev, and Cline.
    Cross-platform: uses platform-specific extension directories.
    """

    _extensions_dir_patterns: tuple[str, ...] = field(
        default_factory=lambda: (
            # Windows
            os.path.expandvars(r"%APPDATA%\Code\User\extensions"),
            os.path.expandvars(r"%USERPROFILE%\.vscode\extensions"),
            # Linux / macOS
            os.path.expanduser("~/.vscode/extensions"),
            os.path.expanduser("~/.vscode-oss/extensions"),
            os.path.expanduser("~/.vscode-server/extensions"),
            # Flatpak / Snap
            os.path.expanduser("~/.var/app/com.visualstudio.code/config/Code/extensions"),
        )
    )

    _known_ai_extensions: tuple[dict[str, Any], ...] = field(
        default_factory=lambda: (
            {
                "name": "github-copilot",
                "id_prefix": "github.copilot",
                "type": EngineType.CUSTOM,
                "capabilities": [EngineCapability.CODING, EngineCapability.REASONING],
            },
            {
                "name": "claude-dev",
                "id_prefix": "saoudrizwan.claude-dev",
                "type": EngineType.CLAUDE_CODE,
                "capabilities": [
                    EngineCapability.CODING,
                    EngineCapability.REASONING,
                    EngineCapability.TERMINAL,
                ],
            },
            {
                "name": "continue",
                "id_prefix": "continue.continue",
                "type": EngineType.CUSTOM,
                "capabilities": [
                    EngineCapability.CODING,
                    EngineCapability.REASONING,
                    EngineCapability.FILESYSTEM,
                ],
            },
            {
                "name": "cline",
                "id_prefix": "claude.c-line",
                "type": EngineType.CLAUDE_CODE,
                "capabilities": [
                    EngineCapability.CODING,
                    EngineCapability.REASONING,
                    EngineCapability.TERMINAL,
                ],
            },
            {
                "name": "tabnine",
                "id_prefix": "tabnine.tabnine-vscode",
                "type": EngineType.CUSTOM,
                "capabilities": [EngineCapability.CODING],
            },
            {
                "name": "amazon-q",
                "id_prefix": "amazon.q",
                "type": EngineType.CUSTOM,
                "capabilities": [EngineCapability.CODING, EngineCapability.PLANNING],
            },
            {
                "name": "codeium",
                "id_prefix": "codeium.codeium",
                "type": EngineType.CUSTOM,
                "capabilities": [EngineCapability.CODING],
            },
            {
                "name": "cursor",
                "id_prefix": "cursor.cursor",
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
        """Scan VS Code extensions for AI coding assistants."""
        results: list[EngineRegistration] = []

        # Find VS Code / Cursor / VSCodium installations
        code_cli = self._find_vscode_cli()
        if code_cli:
            code_version = await self._get_version(code_cli)
            results.append(
                EngineRegistration(
                    name="vscode",
                    engine_type=EngineType.CUSTOM,
                    endpoint=f"local:{code_cli}",
                    transport="local",
                    capabilities=[EngineCapability.CODING, EngineCapability.FILESYSTEM],
                    description=f"VS Code v{code_version or '?'} (discovered)",
                    version=code_version or "",
                    tags=["discovered", "vscode", "ide"],
                    metadata={
                        "cli_path": code_cli,
                        "discovery_method": "vscode",
                    },
                )
            )

        # Scan extensions directories for AI tools
        scanned_dirs: set[str] = set()
        for ext_dir in self._extensions_dir_patterns:
            real_dir = os.path.realpath(ext_dir) if os.path.exists(ext_dir) else ext_dir
            if not os.path.isdir(real_dir) or real_dir in scanned_dirs:
                continue
            scanned_dirs.add(real_dir)

            try:
                ext_results = await self._scan_extensions_dir(real_dir)
                results.extend(ext_results)
            except (OSError, PermissionError) as exc:
                log.warning("Cannot scan VS Code extensions dir", path=real_dir, error=str(exc))

        return results

    def get_provider_name(self) -> str:
        return "vscode-discovery"

    def get_provider_type(self) -> str:
        return "vscode"

    # ── Internal ──

    @staticmethod
    def _find_vscode_cli() -> str | None:
        """Find the VS Code CLI (``code``) in PATH or well-known locations."""
        import shutil

        candidates = ["code", "code-insiders", "code-oss", "codium", "cursor"]
        system = platform_mod.system()

        for name in candidates:
            cli_path = shutil.which(name)
            if cli_path:
                return cli_path

        if system == "Windows":
            extra_paths = [
                os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\bin\code"),
                os.path.expandvars(
                    r"%LOCALAPPDATA%\Programs\Microsoft VS Code Insiders\bin\code-insiders"
                ),
            ]
            for path in extra_paths:
                if os.path.isfile(path):
                    return path

        elif system == "Darwin":
            mac_paths = [
                "/usr/local/bin/code",
                "/opt/homebrew/bin/code",
                "/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code",
            ]
            for path in mac_paths:
                if os.path.isfile(path):
                    return path

        return None

    async def _scan_extensions_dir(self, ext_dir: str) -> list[EngineRegistration]:
        """Scan a VS Code extensions directory for AI extensions."""
        results: list[EngineRegistration] = []

        try:
            entries = os.listdir(ext_dir)
        except OSError, PermissionError:
            return []

        for ext_name in entries:
            ext_path = os.path.join(ext_dir, ext_name)
            if not os.path.isdir(ext_path):
                continue

            # Check if this extension matches a known AI extension
            matched = self._match_extension(ext_name)
            if matched is None:
                continue

            # Read package.json for version info
            version = await self._read_extension_version(ext_path)

            results.append(
                EngineRegistration(
                    name=f"vscode-{matched['name']}",
                    engine_type=matched["type"],
                    endpoint=f"vscode:ext:{ext_name}",
                    transport="local",
                    capabilities=matched["capabilities"],
                    description=(
                        f"VS Code extension: {matched['name']} {version or ''} ({ext_path})"
                    ),
                    version=version or "unknown",
                    tags=["discovered", "vscode", "extension", matched["name"]],
                    metadata={
                        "extension_path": ext_path,
                        "extension_name": ext_name,
                        "discovery_method": "vscode",
                        "extension_type": matched["name"],
                    },
                )
            )

        return results

    def _match_extension(self, ext_name: str) -> dict | None:
        """Match a VS Code extension directory name against known AI extensions."""
        ext_name_lower = ext_name.lower()
        for known in self._known_ai_extensions:
            if ext_name_lower.startswith(known["id_prefix"].lower()):
                return known
        return None

    @staticmethod
    async def _read_extension_version(ext_path: str) -> str | None:
        """Read the version from an extension's ``package.json``."""
        pkg_path = os.path.join(ext_path, "package.json")
        if not os.path.isfile(pkg_path):
            return None

        try:
            with open(pkg_path, encoding="utf-8") as f:
                pkg = json.loads(f.read(65536))
            return str(pkg.get("version", ""))[:50] or None
        except json.JSONDecodeError, OSError, PermissionError:
            return None

    @staticmethod
    async def _get_version(executable: str) -> str | None:
        """Get the VS Code version."""
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
