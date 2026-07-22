"""Winget (Windows Package Manager) Discovery Provider.

Scans winget-installed packages for AI coding assistants.
"""

import json
import subprocess
from dataclasses import dataclass, field
from typing import Any

from agentic_os.domain.execution import EngineCapability, EngineType
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.execution import DiscoveryProvider, EngineRegistration

log = get_logger("discovery.winget")


@dataclass
class WingetDiscovery(DiscoveryProvider):
    """Discovers AI coding assistants installed via Windows Package Manager."""

    _known_packages: tuple[dict[str, Any], ...] = field(
        default_factory=lambda: (
            {
                "name": "claude-code",
                "pid": "Anthropic.ClaudeCode",
                "engine": EngineType.CLAUDE_CODE,
                "caps": [
                    EngineCapability.CODING,
                    EngineCapability.REASONING,
                    EngineCapability.TERMINAL,
                ],
            },
            {
                "name": "opencode",
                "pid": "Sentry.OpenCodeCLI",
                "engine": EngineType.OPENCODE,
                "caps": [EngineCapability.CODING, EngineCapability.REASONING],
            },
            {
                "name": "ollama",
                "pid": "Ollama.Ollama",
                "engine": EngineType.CUSTOM,
                "caps": [EngineCapability.REASONING, EngineCapability.OFFLINE],
            },
            {
                "name": "git",
                "pid": "Git.Git",
                "engine": EngineType.CUSTOM,
                "caps": [EngineCapability.GIT],
            },
            {
                "name": "openinterpreter",
                "pid": "OpenInterpreter.OpenInterpreter",
                "engine": EngineType.OPEN_INTERPRETER,
                "caps": [EngineCapability.CODING, EngineCapability.TERMINAL],
            },
        )
    )

    async def discover(self) -> list[EngineRegistration]:
        results: list[EngineRegistration] = []
        try:
            result = subprocess.run(
                ["winget", "list", "--accept-source-agreements"],
                capture_output=True,
                timeout=30.0,
                text=True,
            )
            if result.returncode not in (0, 1):
                return results
            text = result.stdout
            for entry in self._known_packages:
                if entry["pid"] in text:
                    results.append(
                        EngineRegistration(
                            name=f"{entry['name']}-winget",
                            engine_type=entry["engine"],
                            endpoint=f"local:{entry['name']}",
                            transport="local",
                            capabilities=entry["caps"],
                            description=f"{entry['name'].title()} (WinGet)",
                            version="unknown",
                            tags=["discovered", "winget", entry["name"]],
                            metadata={"discovery_method": "winget", "package": entry["pid"]},
                        )
                    )
        except (subprocess.TimeoutExpired, OSError, FileNotFoundError):
            pass
        return results

    def get_provider_name(self) -> str:
        return "winget-discovery"

    def get_provider_type(self) -> str:
        return "winget"
