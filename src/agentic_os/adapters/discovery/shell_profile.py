"""Shell Profile Discovery Provider.

Inspects shell configuration files (.bashrc, .zshrc, .profile, .bash_profile,
.fish) for configured AI coding assistants with aliases or path modifications.
Also checks common shell completion directories.
"""
import os
import re
from dataclasses import dataclass, field
from typing import Any

from agentic_os.domain.execution import EngineCapability, EngineType
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.execution import DiscoveryProvider, EngineRegistration

log = get_logger("discovery.shell")


@dataclass
class ShellProfileDiscovery(DiscoveryProvider):
    """Discovers AI coding assistants configured in shell profiles."""

    _known_tools: tuple[dict[str, Any], ...] = field(
        default_factory=lambda: (
            {"name": "claude", "pattern": r"claude", "engine": EngineType.CLAUDE_CODE,
             "caps": [EngineCapability.CODING, EngineCapability.REASONING]},
            {"name": "opencode", "pattern": r"opencode", "engine": EngineType.OPENCODE,
             "caps": [EngineCapability.CODING, EngineCapability.REASONING]},
            {"name": "hermes", "pattern": r"hermes", "engine": EngineType.HERMES,
             "caps": [EngineCapability.CODING, EngineCapability.REASONING]},
            {"name": "codex", "pattern": r"codex", "engine": EngineType.CODEX,
             "caps": [EngineCapability.CODING, EngineCapability.REASONING]},
            {"name": "gemini", "pattern": r"gemini", "engine": EngineType.GEMINI_CLI,
             "caps": [EngineCapability.CODING, EngineCapability.REASONING]},
            {"name": "aider", "pattern": r"aider", "engine": EngineType.AIDER,
             "caps": [EngineCapability.CODING, EngineCapability.PLANNING]},
            {"name": "goose", "pattern": r"goose", "engine": EngineType.GOOSE,
             "caps": [EngineCapability.CODING, EngineCapability.PLANNING]},
            {"name": "deepseek", "pattern": r"deepseek", "engine": EngineType.DEEPSEEK,
             "caps": [EngineCapability.CODING, EngineCapability.REASONING]},
        )
    )

    _shell_rc_files: tuple[str, ...] = field(
        default_factory=lambda: (
            ".bashrc", ".zshrc", ".bash_profile", ".profile", ".config/fish/config.fish",
        )
    )

    async def discover(self) -> list[EngineRegistration]:
        results: list[EngineRegistration] = []
        home = os.path.expanduser("~")
        content_map: dict[str, str] = {}

        for rc in self._shell_rc_files:
            path = os.path.join(home, rc)
            if os.path.isfile(path):
                try:
                    with open(path, "r", encoding="utf-8", errors="replace") as f:
                        content_map[rc] = f.read()
                except (OSError, PermissionError):
                    pass

        if not content_map:
            return results

        for entry in self._known_tools:
            pattern = entry["pattern"]
            found_in: list[str] = []
            for rc_name, content in content_map.items():
                if re.search(pattern, content, re.IGNORECASE):
                    found_in.append(rc_name)
            if found_in:
                files_found = ", ".join(found_in)
                results.append(EngineRegistration(
                    name=f"{entry['name']}-shell",
                    engine_type=entry["engine"],
                    endpoint=f"local:{entry['name']}",
                    transport="local",
                    capabilities=entry["caps"],
                    description=f"{entry['name'].title()} (referenced in shell profile: {files_found})",
                    version="unknown",
                    tags=["discovered", "shell", entry["name"]] + found_in,
                    metadata={"discovery_method": "shell_profile", "files": found_in, "pattern": entry["name"]},
                ))
        return results

    def get_provider_name(self) -> str: return "shell-profile-discovery"
    def get_provider_type(self) -> str: return "shell_profile"
