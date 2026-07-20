from __future__ import annotations

import shutil

from core.logging import get_logger
from services.runtime_discovery.models import (
    DiscoveryProviderType,
    RuntimeDiscoveryResult,
    RuntimeType,
)

_log = get_logger(__name__)

_KNOWN_BINARIES: dict[str, RuntimeType] = {
    "claude": RuntimeType.CLAUDE_CODE,
    "gemini": RuntimeType.GEMINI_CLI,
    "codex": RuntimeType.CODEX_CLI,
    "hermes": RuntimeType.HERMES,
    "openhands": RuntimeType.OPENHANDS,
    "aider": RuntimeType.AIDER,
    "continue": RuntimeType.CONTINUE,
    "cline": RuntimeType.CLINE,
    "roo": RuntimeType.ROO_CODE,
    "ollama": RuntimeType.OLLAMA,
    "python": RuntimeType.PYTHON,
    "python3": RuntimeType.PYTHON,
    "node": RuntimeType.NODEJS,
    "nodejs": RuntimeType.NODEJS,
    "docker": RuntimeType.DOCKER,
    "git": RuntimeType.GIT,
    "gh": RuntimeType.GH_CLI,
}

_DISPLAY_NAMES: dict[RuntimeType, str] = {
    RuntimeType.CLAUDE_CODE: "Claude Code",
    RuntimeType.GEMINI_CLI: "Gemini CLI",
    RuntimeType.CODEX_CLI: "Codex CLI",
    RuntimeType.HERMES: "Hermes",
    RuntimeType.OPENHANDS: "OpenHands",
    RuntimeType.AIDER: "Aider",
    RuntimeType.CONTINUE: "Continue",
    RuntimeType.CLINE: "Cline",
    RuntimeType.ROO_CODE: "Roo Code",
    RuntimeType.OLLAMA: "Ollama",
    RuntimeType.PYTHON: "Python",
    RuntimeType.NODEJS: "Node.js",
    RuntimeType.DOCKER: "Docker",
    RuntimeType.GIT: "Git",
    RuntimeType.GH_CLI: "GitHub CLI",
}


class PathDiscoveryProvider:
    provider_type = DiscoveryProviderType.PATH

    async def discover(  # noqa: E501
        self, runtime_type: RuntimeType | None = None
    ) -> list[RuntimeDiscoveryResult]:
        results: list[RuntimeDiscoveryResult] = []
        binaries = {
            k: v for k, v in _KNOWN_BINARIES.items() if runtime_type is None or v == runtime_type
        }  # noqa: E501
        for binary_name, rt_type in binaries.items():
            path = shutil.which(binary_name)
            if path:
                version = await self._detect_version(path)
                results.append(
                    RuntimeDiscoveryResult(
                        runtime_type=rt_type,
                        name=binary_name,
                        display_name=_DISPLAY_NAMES.get(rt_type, binary_name),
                        version=version,
                        binary_path=path,
                        executable=path,
                        source=DiscoveryProviderType.PATH,
                        confidence=0.9,
                        found=True,
                    )
                )
        _log.info("PathDiscoveryProvider found %d runtimes", len(results))
        return results

    async def discover_all(self) -> list[RuntimeDiscoveryResult]:
        return await self.discover()

    async def get_provider_name(self) -> str:
        return "path"

    async def get_provider_type(self) -> DiscoveryProviderType:
        return DiscoveryProviderType.PATH

    async def _detect_version(self, path: str) -> str | None:
        import subprocess

        try:
            result = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=5)
            output = (result.stdout or result.stderr).strip().split("\n")[0]
            return output if output else None
        except Exception:
            return None
