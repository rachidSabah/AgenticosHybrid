from __future__ import annotations

import os

from core.logging import get_logger
from services.runtime_discovery.models import (
    DiscoveryProviderType,
    RuntimeDiscoveryResult,
    RuntimeType,
)

_log = get_logger(__name__)

_ENV_VAR_MAP: dict[str, tuple[str, RuntimeType]] = {
    "PYTHON_HOME": ("python", RuntimeType.PYTHON),
    "NODE_HOME": ("node", RuntimeType.NODEJS),
    "DOCKER_HOST": ("docker", RuntimeType.DOCKER),
    "GIT_HOME": ("git", RuntimeType.GIT),
    "OLLAMA_HOST": ("ollama", RuntimeType.OLLAMA),
    "ANTHROPIC_API_KEY": ("claude", RuntimeType.CLAUDE_CODE),
    "GEMINI_API_KEY": ("gemini", RuntimeType.GEMINI_CLI),
    "OPENAI_API_KEY": ("codex", RuntimeType.CODEX_CLI),
}

_DISPLAY_NAMES: dict[RuntimeType, str] = {
    RuntimeType.PYTHON: "Python",
    RuntimeType.NODEJS: "Node.js",
    RuntimeType.DOCKER: "Docker",
    RuntimeType.GIT: "Git",
    RuntimeType.OLLAMA: "Ollama",
    RuntimeType.CLAUDE_CODE: "Claude Code",
    RuntimeType.GEMINI_CLI: "Gemini CLI",
    RuntimeType.CODEX_CLI: "Codex CLI",
}


class EnvVarDiscoveryProvider:
    provider_type = DiscoveryProviderType.ENV_VAR

    async def discover(  # noqa: E501
        self, runtime_type: RuntimeType | None = None
    ) -> list[RuntimeDiscoveryResult]:
        results: list[RuntimeDiscoveryResult] = []
        for var_name, (binary_name, rt_type) in _ENV_VAR_MAP.items():
            if runtime_type is not None and rt_type != runtime_type:
                continue
            value = os.environ.get(var_name)
            if value:
                results.append(
                    RuntimeDiscoveryResult(
                        runtime_type=rt_type,
                        name=binary_name,
                        display_name=_DISPLAY_NAMES.get(rt_type, binary_name),
                        version=None,
                        binary_path=value,
                        executable=value,
                        source=DiscoveryProviderType.ENV_VAR,
                        confidence=0.5,
                        found=True,
                        metadata={"env_var": var_name, "env_value": value},
                    )
                )
        _log.info("EnvVarDiscoveryProvider found %d runtimes", len(results))
        return results

    async def discover_all(self) -> list[RuntimeDiscoveryResult]:
        return await self.discover()

    async def get_provider_name(self) -> str:
        return "env_var"

    async def get_provider_type(self) -> DiscoveryProviderType:
        return DiscoveryProviderType.ENV_VAR
