"""NPM Global Package Discovery Provider.

Scans globally installed NPM packages for AI coding assistants.
"""

import json
import os
import subprocess
from dataclasses import dataclass, field
from typing import Any

from agentic_os.domain.execution import EngineCapability, EngineType
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.execution import DiscoveryProvider, EngineRegistration

log = get_logger("discovery.npm")


@dataclass
class NpmDiscovery(DiscoveryProvider):
    """Discovers AI coding assistants installed globally via npm."""

    _known_packages: tuple[dict[str, Any], ...] = field(
        default_factory=lambda: (
            {
                "name": "claude-code",
                "package": "@anthropic-ai/claude-code",
                "engine": EngineType.CLAUDE_CODE,
                "caps": [
                    EngineCapability.CODING,
                    EngineCapability.REASONING,
                    EngineCapability.TERMINAL,
                ],
            },
            {
                "name": "opencode",
                "package": "@sentry/opencode-cli",
                "engine": EngineType.OPENCODE,
                "caps": [
                    EngineCapability.CODING,
                    EngineCapability.REASONING,
                    EngineCapability.TERMINAL,
                ],
            },
            {
                "name": "codex",
                "package": "@openai/codex-cli",
                "engine": EngineType.CODEX,
                "caps": [EngineCapability.CODING, EngineCapability.REASONING],
            },
            {
                "name": "aider",
                "package": "aider",
                "engine": EngineType.AIDER,
                "caps": [EngineCapability.CODING, EngineCapability.PLANNING],
            },
            {
                "name": "hermes",
                "package": "@hermes-agents/hermes",
                "engine": EngineType.HERMES,
                "caps": [
                    EngineCapability.CODING,
                    EngineCapability.REASONING,
                    EngineCapability.PLANNING,
                    EngineCapability.TERMINAL,
                ],
            },
            {
                "name": "qwen",
                "package": "@alibaba/qwen-cli",
                "engine": EngineType.QWEN,
                "caps": [EngineCapability.CODING, EngineCapability.REASONING],
            },
        )
    )

    async def discover(self) -> list[EngineRegistration]:
        results: list[EngineRegistration] = []
        try:
            result = subprocess.run(
                ["npm", "list", "-g", "--json", "--depth=0"], capture_output=True, timeout=15.0
            )
            if result.returncode != 0:
                return results
            data = json.loads(result.stdout.decode("utf-8", errors="replace"))
            deps = data.get("dependencies", {})
            for entry in self._known_packages:
                pkg_name = entry["package"]
                if pkg_name in deps:
                    pkg_info = deps[pkg_name]
                    version = (pkg_info.get("version", "") or "").strip()
                    results.append(
                        EngineRegistration(
                            name=f"{entry['name']}-npm",
                            engine_type=entry["engine"],
                            endpoint=f"local:{entry['name']}",
                            transport="local",
                            capabilities=entry["caps"],
                            description=f"{entry['name'].title()} (npm global)"
                            + (f" v{version}" if version else ""),
                            version=version or "unknown",
                            tags=["discovered", "npm", entry["name"]],
                            metadata={"discovery_method": "npm", "package": pkg_name},
                        )
                    )
        except (subprocess.TimeoutExpired, OSError, FileNotFoundError, json.JSONDecodeError):
            pass
        return results

    def get_provider_name(self) -> str:
        return "npm-discovery"

    def get_provider_type(self) -> str:
        return "npm"
