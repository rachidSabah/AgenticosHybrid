"""CLI tool discovery — detects command-line development tools.

Discovers CLI tools installed on the system by scanning PATH, standard
install directories, and known package manager locations. Each discovered
tool includes version information and detected capabilities.

Integrates with the core ``Scanner`` utility for filesystem scanning and
returns standardized results compatible with the Runtime Discovery framework.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from core.logging import get_logger

from services.runtime_discovery.scanner import Scanner

_log = get_logger(__name__)

__all__ = [
    "CLIDiscovery",
    "DiscoveredCLI",
]

# Known CLI tools to discover, mapped to their type category
_KNOWN_CLIS: dict[str, str] = {
    # AI Coding CLIs
    "claude": "ai_coding",
    "gemini": "ai_coding",
    "gemini-cli": "ai_coding",
    "codex": "ai_coding",
    "opencode": "ai_coding",
    "aider": "ai_coding",
    "continue": "ai_coding",
    "cline": "ai_coding",
    "roo": "ai_coding",
    "roo-cli": "ai_coding",
    "agy": "ai_coding",
    # Local LLM
    "ollama": "local_llm",
    "llama-cli": "local_llm",
    "llama-server": "local_llm",
    # Package managers
    "npm": "package_manager",
    "pip": "package_manager",
    "pip3": "package_manager",
    "uv": "package_manager",
    "cargo": "package_manager",
    "go": "package_manager",
    "gem": "package_manager",
    "brew": "package_manager",
    "choco": "package_manager",
    "winget": "package_manager",
    "scoop": "package_manager",
    # Version control
    "git": "version_control",
    "svn": "version_control",
    "hg": "version_control",
    # Containers
    "docker": "container",
    "podman": "container",
    "nerdctl": "container",
    "kubectl": "container",
    "helm": "container",
    "minikube": "container",
    # Cloud CLIs
    "aws": "cloud",
    "gcloud": "cloud",
    "az": "cloud",
    "doctl": "cloud",
    "gh": "cloud",
    "glab": "cloud",
    # Databases
    "psql": "database",
    "mysql": "database",
    "sqlite3": "database",
    "redis-cli": "database",
    "mongosh": "database",
    # Development
    "make": "development",
    "cmake": "development",
    "gcc": "development",
    "clang": "development",
    "rustc": "development",
    "go": "development",
    "node": "development",
    "python": "development",
    "python3": "development",
    "java": "development",
    "mvn": "development",
    "gradle": "development",
    # Shell
    "bash": "shell",
    "zsh": "shell",
    "fish": "shell",
    "pwsh": "shell",
    "powershell": "shell",
    # Editors
    "code": "editor",
    "cursor": "editor",
    "vim": "editor",
    "nvim": "editor",
    "nano": "editor",
    "emacs": "editor",
}


@dataclass
class DiscoveredCLI:
    """A discovered CLI tool on the local system."""

    name: str
    binary_path: str
    category: str = "unknown"
    version: str | None = None
    source: str = "path"
    metadata: dict[str, Any] = field(default_factory=dict)
    discovered_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "binary_path": self.binary_path,
            "category": self.category,
            "version": self.version,
            "source": self.source,
            "metadata": dict(self.metadata),
            "discovered_at": self.discovered_at.isoformat(),
        }


class CLIDiscovery:
    """Discovers CLI development tools installed on the local system.

    Uses the ``Scanner`` utility to find binaries on PATH and in standard
    install directories, then maps them to known tool categories.
    """

    def __init__(self) -> None:
        self._scanner = Scanner()
        self._discovered: dict[str, DiscoveredCLI] = {}

    @property
    def known_clis(self) -> dict[str, str]:
        """Return the mapping of known CLI names to categories."""
        return dict(_KNOWN_CLIS)

    async def discover_all(self) -> list[DiscoveredCLI]:
        """Discover all known CLI tools on the system."""
        binary_names = list(_KNOWN_CLIS.keys())

        # Use the Scanner to find all binaries
        scan_result = self._scanner.scan_all(binary_names)

        clis: list[DiscoveredCLI] = []
        seen: set[str] = set()

        for scanned in scan_result.binaries:
            name = scanned.name
            if name in seen:
                continue
            seen.add(name)

            cli = DiscoveredCLI(
                name=name,
                binary_path=scanned.binary_path,
                category=_KNOWN_CLIS.get(name, "unknown"),
                version=scanned.version,
                source=scanned.source,
                metadata={"detected_by": "cli_discovery"},
            )
            clis.append(cli)
            self._discovered[name] = cli

        _log.info("CLI discovery found %d tools", len(clis))
        return clis

    async def discover_by_category(self, category: str) -> list[DiscoveredCLI]:
        """Discover CLI tools matching a specific category."""
        names = [name for name, cat in _KNOWN_CLIS.items() if cat == category]
        if not names:
            return []

        scan_result = self._scanner.scan_all(names)

        clis: list[DiscoveredCLI] = []
        for scanned in scan_result.binaries:
            cli = DiscoveredCLI(
                name=scanned.name,
                binary_path=scanned.binary_path,
                category=category,
                version=scanned.version,
                source=scanned.source,
                metadata={"detected_by": "cli_discovery"},
            )
            clis.append(cli)

        return clis

    async def discover_single(self, name: str) -> DiscoveredCLI | None:
        """Discover a single CLI tool by name."""
        category = _KNOWN_CLIS.get(name, "unknown")
        binary_path = self._scanner.which(name)
        if binary_path is None:
            return None

        version = self._scanner.detect_version(binary_path)
        cli = DiscoveredCLI(
            name=name,
            binary_path=binary_path,
            category=category,
            version=version,
            source="path",
            metadata={"detected_by": "cli_discovery"},
        )
        self._discovered[name] = cli
        return cli

    def get_discovered(self, name: str) -> DiscoveredCLI | None:
        """Get a previously discovered CLI tool by name."""
        return self._discovered.get(name)

    def get_all_discovered(self) -> list[DiscoveredCLI]:
        """Return all previously discovered CLI tools."""
        return list(self._discovered.values())

    @staticmethod
    def get_tool_categories() -> dict[str, list[str]]:
        """Return the mapping of categories to tool names."""
        categories: dict[str, list[str]] = {}
        for name, category in _KNOWN_CLIS.items():
            categories.setdefault(category, []).append(name)
        return categories
