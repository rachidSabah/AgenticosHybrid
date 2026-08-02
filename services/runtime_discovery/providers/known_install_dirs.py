from __future__ import annotations

from pathlib import Path

from core.logging import get_logger
from services.runtime_discovery.models import (
    DiscoveryProviderType,
    RuntimeDiscoveryResult,
    RuntimeType,
)

_log = get_logger(__name__)

_INSTALL_DIRS: dict[str, list[Path]] = {
    "ollama": [Path.home() / ".ollama"],
    "claude": [
        Path.home() / ".claude",
        Path.home() / "AppData" / "Local" / "Claude",
        Path("/usr/share/claude"),
    ],
    "codex": [Path.home() / ".codex"],
    "aider": [Path.home() / ".aider"],
    "continue": [Path.home() / ".continue"],
    "docker": [
        Path("/var/run/docker.sock"),
        Path("C:\\Program Files\\Docker"),
    ],
}

_DIR_TO_TYPE: dict[str, RuntimeType] = {
    "ollama": RuntimeType.OLLAMA,
    "claude": RuntimeType.CLAUDE_CODE,
    "codex": RuntimeType.CODEX_CLI,
    "aider": RuntimeType.AIDER,
    "continue": RuntimeType.CONTINUE,
    "docker": RuntimeType.DOCKER,
}

_DISPLAY_NAMES: dict[RuntimeType, str] = {
    RuntimeType.OLLAMA: "Ollama",
    RuntimeType.CLAUDE_CODE: "Claude Code",
    RuntimeType.CODEX_CLI: "Codex CLI",
    RuntimeType.AIDER: "Aider",
    RuntimeType.CONTINUE: "Continue",
    RuntimeType.DOCKER: "Docker",
}


class KnownInstallDirsProvider:
    provider_type = DiscoveryProviderType.KNOWN_INSTALL_DIRS

    async def discover(  # noqa: E501
        self, runtime_type: RuntimeType | None = None
    ) -> list[RuntimeDiscoveryResult]:
        results: list[RuntimeDiscoveryResult] = []
        for binary_name, dirs in _INSTALL_DIRS.items():
            rt_type = _DIR_TO_TYPE.get(binary_name)
            if rt_type is None or (runtime_type is not None and rt_type != runtime_type):
                continue
            for d in dirs:
                if d.exists():
                    results.append(
                        RuntimeDiscoveryResult(
                            runtime_type=rt_type,
                            name=binary_name,
                            display_name=_DISPLAY_NAMES.get(rt_type, binary_name),
                            binary_path=str(d),
                            executable=str(d),
                            source=DiscoveryProviderType.KNOWN_INSTALL_DIRS,
                            confidence=0.7,
                            found=True,
                            metadata={"install_dir": str(d)},
                        )
                    )
                    break
        _log.info("KnownInstallDirsProvider found %d runtimes", len(results))
        return results

    async def discover_all(self) -> list[RuntimeDiscoveryResult]:
        return await self.discover()

    async def get_provider_name(self) -> str:
        return "known_install_dirs"

    async def get_provider_type(self) -> DiscoveryProviderType:
        return DiscoveryProviderType.KNOWN_INSTALL_DIRS
