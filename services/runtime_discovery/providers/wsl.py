from __future__ import annotations

import platform
import subprocess

from core.logging import get_logger
from services.runtime_discovery.models import (
    DiscoveryProviderType,
    RuntimeDiscoveryResult,
    RuntimeType,
)

_log = get_logger(__name__)

_WSL_BINARIES: dict[str, RuntimeType] = {
    "claude": RuntimeType.CLAUDE_CODE,
    "gemini": RuntimeType.GEMINI_CLI,
    "codex": RuntimeType.CODEX_CLI,
    "python3": RuntimeType.PYTHON,
    "node": RuntimeType.NODEJS,
    "docker": RuntimeType.DOCKER,
    "git": RuntimeType.GIT,
    "ollama": RuntimeType.OLLAMA,
}

_WSL_DISPLAY_NAMES: dict[RuntimeType, str] = {
    RuntimeType.CLAUDE_CODE: "Claude Code (WSL)",
    RuntimeType.GEMINI_CLI: "Gemini CLI (WSL)",
    RuntimeType.CODEX_CLI: "Codex CLI (WSL)",
    RuntimeType.PYTHON: "Python (WSL)",
    RuntimeType.NODEJS: "Node.js (WSL)",
    RuntimeType.DOCKER: "Docker (WSL)",
    RuntimeType.GIT: "Git (WSL)",
    RuntimeType.OLLAMA: "Ollama (WSL)",
}


class WSLDiscoveryProvider:
    provider_type = DiscoveryProviderType.WSL

    async def discover(
        self, runtime_type: RuntimeType | None = None
    ) -> list[RuntimeDiscoveryResult]:
        results: list[RuntimeDiscoveryResult] = []
        if platform.system() != "Windows":
            return results
        try:
            result = subprocess.run(
                ["wsl.exe", "--list", "--quiet"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                return results
            distros = [d.strip() for d in result.stdout.splitlines() if d.strip()]
            for distro in distros:
                binaries = {
                    k: v
                    for k, v in _WSL_BINARIES.items()
                    if runtime_type is None or v == runtime_type
                }
                for binary_name, rt_type in binaries.items():
                    try:
                        check = subprocess.run(
                            ["wsl.exe", "-d", distro, "which", binary_name],
                            capture_output=True,
                            text=True,
                            timeout=5,
                        )
                        if check.returncode == 0:
                            wsl_path = check.stdout.strip()
                            results.append(
                                RuntimeDiscoveryResult(
                                    runtime_type=rt_type,
                                    name=binary_name,
                                    display_name=_WSL_DISPLAY_NAMES.get(
                                        rt_type, f"{binary_name} (WSL)"
                                    ),
                                    binary_path=wsl_path,
                                    executable=wsl_path,
                                    source=DiscoveryProviderType.WSL,
                                    confidence=0.6,
                                    found=True,
                                    metadata={"wsl_distro": distro},
                                )
                            )
                    except Exception:
                        continue
        except Exception as e:
            _log.info("WSL discovery error: %s", e)
        _log.info("WSLDiscoveryProvider found %d runtimes", len(results))
        return results

    async def discover_all(self) -> list[RuntimeDiscoveryResult]:
        return await self.discover()

    async def get_provider_name(self) -> str:
        return "wsl"

    async def get_provider_type(self) -> DiscoveryProviderType:
        return DiscoveryProviderType.WSL
