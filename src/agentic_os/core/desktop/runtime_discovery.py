"""Runtime Discovery Manager — auto-detects installed runtimes on the system."""

from __future__ import annotations

import shutil
from collections.abc import Sequence
from typing import Any

from agentic_os.domain.desktop import (
    RuntimeDiscoveryResult,
    RuntimeInfo,
    RuntimeType,
)
from agentic_os.infrastructure.logging import get_logger

log = get_logger("desktop.runtime_discovery")

_DISCOVERY_PROVIDERS: list[dict[str, Any]] = [
    {"type": RuntimeType.PYTHON, "names": ["python", "python3", "py"], "version_flag": "--version"},
    {"type": RuntimeType.GIT, "names": ["git"], "version_flag": "--version"},
    {"type": RuntimeType.DOCKER, "names": ["docker"], "version_flag": "--version"},
    {"type": RuntimeType.NODE, "names": ["node", "nodejs"], "version_flag": "--version"},
    {
        "type": RuntimeType.CLAUDE_CODE,
        "names": ["claude", "claude-code"],
        "version_flag": "--version",
    },
    {"type": RuntimeType.OPENCODE, "names": ["opencode"], "version_flag": "--version"},
    {"type": RuntimeType.GEMINI_CLI, "names": ["gemini"], "version_flag": "--version"},
    {"type": RuntimeType.CODEX_CLI, "names": ["codex"], "version_flag": "--version"},
    {"type": RuntimeType.OLLAMA, "names": ["ollama"], "version_flag": "--version"},
    {"type": RuntimeType.LM_STUDIO, "names": ["lm-studio"], "version_flag": "--version"},
    {"type": RuntimeType.SQLITE, "names": ["sqlite3", "sqlite"], "version_flag": "--version"},
]


class RuntimeDiscoveryManager:
    """Auto-detects installed runtimes and their capabilities."""

    def __init__(self) -> None:
        self._runtimes: dict[RuntimeType, RuntimeInfo] = {}

    async def discover_runtimes(self) -> RuntimeDiscoveryResult:
        import time

        start = time.monotonic()
        errors: list[str] = []

        for provider in _DISCOVERY_PROVIDERS:
            try:
                info = self._detect_one(provider)
                if info is not None:
                    self._runtimes[info.runtime_type] = info
            except Exception as exc:
                errors.append(f"{provider['type'].value}: {exc}")

        duration = time.monotonic() - start
        log.info(
            "Runtime discovery complete",
            count=len(self._runtimes),
            duration_seconds=round(duration, 2),
        )
        return RuntimeDiscoveryResult(
            total_discovered=len(self._runtimes),
            runtimes=list(self._runtimes.values()),
            duration_seconds=round(duration, 2),
            errors=errors,
        )

    def _detect_one(self, provider: dict[str, Any]) -> RuntimeInfo | None:
        for name in provider["names"]:
            path = shutil.which(name)
            if path:
                version = self._get_version(path, provider.get("version_flag", "--version"))
                capabilities = self._detect_capabilities(provider["type"])
                return RuntimeInfo(
                    runtime_type=provider["type"],
                    name=name,
                    version=version,
                    path=path,
                    executable=name,
                    capabilities=capabilities,
                    verified=True,
                )
        return None

    @staticmethod
    def _get_version(path: str, flag: str) -> str:
        import subprocess

        try:
            result = subprocess.run([path, flag], capture_output=True, text=True, timeout=10)
            output = result.stdout.strip() or result.stderr.strip()
            return output.split("\n")[0] if output else "unknown"
        except Exception:
            return "unknown"

    @staticmethod
    def _detect_capabilities(runtime_type: RuntimeType) -> list[str]:
        mapping: dict[RuntimeType, list[str]] = {
            RuntimeType.PYTHON: ["execution", "scripting", "package_management"],
            RuntimeType.GIT: ["version_control", "clone", "commit"],
            RuntimeType.DOCKER: ["containerization", "image_management"],
            RuntimeType.NODE: ["execution", "package_management"],
            RuntimeType.CLAUDE_CODE: ["ai_assistant", "code_generation"],
            RuntimeType.OPENCODE: ["ai_coding", "agentic"],
            RuntimeType.OLLAMA: ["local_llm", "model_serving"],
            RuntimeType.SQLITE: ["database", "sql"],
        }
        return mapping.get(runtime_type, [])

    async def get_discovered_runtimes(self) -> Sequence[RuntimeInfo]:
        return list(self._runtimes.values())

    async def get_runtime(self, runtime_type: RuntimeType) -> RuntimeInfo | None:
        return self._runtimes.get(runtime_type)

    async def verify_runtime(self, runtime_type: RuntimeType) -> bool:
        info = self._runtimes.get(runtime_type)
        if info is None:
            return False
        return shutil.which(info.executable) is not None

    async def refresh_runtime(self, runtime_type: RuntimeType) -> RuntimeInfo | None:
        for provider in _DISCOVERY_PROVIDERS:
            if provider["type"] == runtime_type:
                info = self._detect_one(provider)
                if info is not None:
                    self._runtimes[info.runtime_type] = info
                    return info
                return None
        return None

    async def get_discovery_count(self) -> int:
        return len(self._runtimes)
