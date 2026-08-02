"""Environment Variable Discovery Provider.

Checks specific environment variables for AI coding assistant
executables, SDK paths, and API endpoints.
"""

import os
import subprocess
from dataclasses import dataclass, field
from typing import Any

from agentic_os.domain.execution import EngineCapability, EngineType
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.execution import DiscoveryProvider, EngineRegistration

log = get_logger("discovery.env_var")


@dataclass
class EnvVarDiscovery(DiscoveryProvider):
    """Checks environment variables for engine executables and endpoints.

    Probes well-known environment variables used by AI coding assistants
    and development tools to locate installed engines.
    Cross-platform: works on all operating systems via ``os.environ``.
    """

    _env_var_configs: tuple[dict[str, Any], ...] = field(
        default_factory=lambda: (
            # Claude Code
            {
                "name": "claude-code",
                "vars": ["CLAUDE_PATH", "CLAUDE_BINARY"],
                "type": EngineType.CLAUDE_CODE,
                "endpoint_prefix": "local:",
                "capabilities": [
                    EngineCapability.CODING,
                    EngineCapability.REASONING,
                    EngineCapability.TERMINAL,
                ],
            },
            # Anthropic API key indirect
            {
                "name": "claude-code-env",
                "vars": ["ANTHROPIC_API_KEY"],
                "type": EngineType.CLAUDE_CODE,
                "endpoint_prefix": "env:",
                "capabilities": [EngineCapability.CODING, EngineCapability.REASONING],
            },
            # Docker
            {
                "name": "docker",
                "vars": ["DOCKER_HOST", "DOCKER_BINARY"],
                "type": EngineType.DOCKER,
                "endpoint_prefix": "",
                "capabilities": [EngineCapability.DOCKER],
            },
            # Node.js
            {
                "name": "node",
                "vars": ["NODE_PATH", "NODE_BINARY"],
                "type": EngineType.CUSTOM,
                "endpoint_prefix": "",
                "capabilities": [EngineCapability.CODING],
            },
            # Python
            {
                "name": "python",
                "vars": ["PYTHON_BINARY", "PYTHON_PATH"],
                "type": EngineType.CUSTOM,
                "endpoint_prefix": "",
                "capabilities": [EngineCapability.CODING, EngineCapability.FILESYSTEM],
            },
            # Aider
            {
                "name": "aider",
                "vars": ["AIDER_PATH", "AIDER_BINARY"],
                "type": EngineType.AIDER,
                "endpoint_prefix": "local:",
                "capabilities": [EngineCapability.CODING, EngineCapability.PLANNING],
            },
            # Generic AI tools
            {
                "name": "openai",
                "vars": ["OPENAI_API_KEY", "OPENAI_BASE_URL"],
                "type": EngineType.CUSTOM,
                "endpoint_prefix": "env:",
                "capabilities": [EngineCapability.CODING, EngineCapability.REASONING],
            },
            # OpenHands
            {
                "name": "openhands",
                "vars": ["OPENHANDS_PATH", "OPENHANDS_BINARY"],
                "type": EngineType.OPENHANDS,
                "endpoint_prefix": "local:",
                "capabilities": [
                    EngineCapability.CODING,
                    EngineCapability.PLANNING,
                    EngineCapability.FILESYSTEM,
                ],
            },
        )
    )

    async def discover(self) -> list[EngineRegistration]:
        """Probe environment variables for engine executables."""
        results: list[EngineRegistration] = []
        seen_vars: set[str] = set()

        for entry in self._env_var_configs:
            endpoint_prefix = entry["endpoint_prefix"]

            for var_name in entry["vars"]:
                if var_name in seen_vars:
                    continue
                seen_vars.add(var_name)

                value = os.environ.get(var_name)
                if not value or not value.strip():
                    continue

                value = value.strip()
                registration = await self._build_registration(
                    entry,
                    var_name,
                    value,
                    endpoint_prefix,
                )
                if registration is not None:
                    results.append(registration)

        return results

    def get_provider_name(self) -> str:
        return "env-var-discovery"

    def get_provider_type(self) -> str:
        return "env_var"

    # ── Internal ──

    async def _build_registration(
        self,
        entry: dict,
        var_name: str,
        var_value: str,
        endpoint_prefix: str,
    ) -> EngineRegistration | None:
        """Build an EngineRegistration from an environment variable."""
        # Determine if the value points to an executable
        is_executable = False
        if endpoint_prefix == "local:":
            if os.path.isfile(var_value) and os.access(var_value, os.X_OK):
                is_executable = True
        elif endpoint_prefix == "":
            # Could be a path or API endpoint
            if os.path.isfile(var_value) and os.access(var_value, os.X_OK):
                is_executable = True

        endpoint = var_value
        transport = "env"
        metadata_value = var_value

        if is_executable:
            endpoint = f"local:{var_value}"
            transport = "local"
        elif endpoint_prefix == "env:":
            endpoint = f"env:{var_value}"

        # Try to determine version if executable
        version = None
        if is_executable:
            version = await self._get_version(var_value)

        description = self._build_description(entry, var_name, var_value, version, is_executable)

        return EngineRegistration(
            name=f"{entry['name']}-env-{var_name.lower()}",
            engine_type=entry["type"],
            endpoint=endpoint,
            transport=transport,
            capabilities=entry["capabilities"],
            description=description,
            version=version or "unknown",
            tags=["discovered", "env-var", entry["name"], var_name.lower()],
            metadata={
                "env_var": var_name,
                "value": metadata_value,
                "is_executable": is_executable,
                "discovery_method": "env_var",
            },
        )

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
    def _build_description(
        entry: dict,
        var_name: str,
        var_value: str,
        version: str | None,
        is_executable: bool,
    ) -> str:
        """Build a human-readable description."""
        base = entry["name"].title()
        location = f"path: {var_value}" if is_executable else f"value: {var_value[:50]}"

        if version:
            return f"{base} v{version} (env {var_name} → {location})"
        return f"{base} (env {var_name} → {location})"
