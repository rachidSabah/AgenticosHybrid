"""uv Environment Discovery Provider.

Scans uv-managed Python environments for AI coding assistants.
"""

import json
import os
import subprocess
from dataclasses import dataclass, field
from typing import Any

from agentic_os.domain.execution import EngineCapability, EngineType
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.execution import DiscoveryProvider, EngineRegistration

log = get_logger("discovery.uv")


@dataclass
class UvDiscovery(DiscoveryProvider):
    """Discovers AI coding assistants installed via uv (astral.sh)."""

    _known_tools: tuple[dict[str, Any], ...] = field(
        default_factory=lambda: (
            {
                "name": "hermes",
                "tool": "hermes-agent",
                "engine": EngineType.HERMES,
                "caps": [
                    EngineCapability.CODING,
                    EngineCapability.REASONING,
                    EngineCapability.PLANNING,
                    EngineCapability.TERMINAL,
                ],
            },
            {
                "name": "opencode",
                "tool": "sentry-opencode-cli",
                "engine": EngineType.OPENCODE,
                "caps": [EngineCapability.CODING, EngineCapability.REASONING],
            },
            {
                "name": "aider",
                "tool": "aider-chat",
                "engine": EngineType.AIDER,
                "caps": [EngineCapability.CODING, EngineCapability.PLANNING],
            },
            {
                "name": "open-interpreter",
                "tool": "open-interpreter",
                "engine": EngineType.OPEN_INTERPRETER,
                "caps": [EngineCapability.CODING, EngineCapability.TERMINAL],
            },
        )
    )

    async def discover(self) -> list[EngineRegistration]:
        results: list[EngineRegistration] = []
        try:
            result = subprocess.run(["uv", "tool", "list"], capture_output=True, timeout=15.0)
            if result.returncode != 0:
                return results
            text = result.stdout.decode("utf-8", errors="replace")
            for entry in self._known_tools:
                if entry["tool"] in text:
                    results.append(
                        EngineRegistration(
                            name=f"{entry['name']}-uv",
                            engine_type=entry["engine"],
                            endpoint=f"local:{entry['tool']}",
                            transport="local",
                            capabilities=entry["caps"],
                            description=f"{entry['name'].title()} (uv tool)",
                            version="unknown",
                            tags=["discovered", "uv", entry["tool"]],
                            metadata={"discovery_method": "uv", "tool": entry["tool"]},
                        )
                    )
        except (subprocess.TimeoutExpired, OSError, FileNotFoundError):
            pass
        return results

    def get_provider_name(self) -> str:
        return "uv-discovery"

    def get_provider_type(self) -> str:
        return "uv"
