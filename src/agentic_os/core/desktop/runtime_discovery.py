"""Runtime Discovery Manager — auto-detects installed runtimes on the system."""

from __future__ import annotations

import shutil
from collections.abc import Sequence
from typing import Any

from services.runtime_discovery.manager import RuntimeDiscoveryManager as CoreDiscoveryManager

from agentic_os.domain.desktop import (
    RuntimeDiscoveryResult,
    RuntimeInfo,
    RuntimeType,
)
from agentic_os.infrastructure.logging import get_logger

log = get_logger("desktop.runtime_discovery")


class RuntimeDiscoveryManager:
    """Auto-detects installed runtimes using the authoritative unified Runtime Discovery Engine."""

    def __init__(self) -> None:
        self._core_manager = CoreDiscoveryManager()
        self._runtimes: dict[RuntimeType, RuntimeInfo] = {}

    async def discover_runtimes(self) -> RuntimeDiscoveryResult:
        import time

        start = time.monotonic()
        errors: list[str] = []

        try:
            discovered = await self._core_manager.discover_all()
            for item in discovered:
                # Map Core RuntimeType to desktop RuntimeType
                try:
                    desktop_type = RuntimeType(item.runtime_type.value)
                except ValueError:
                    desktop_type = RuntimeType.CUSTOM

                info = RuntimeInfo(
                    runtime_type=desktop_type,
                    name=item.name,
                    version=item.version or "unknown",
                    path=item.binary_path or "",
                    executable=item.executable or item.name,
                    capabilities=[
                        c.value if hasattr(c, "value") else str(c) for c in item.capabilities  # ty:ignore[unresolved-attribute]
                    ],
                    verified=item.found,
                )
                self._runtimes[desktop_type] = info
        except Exception as exc:
            errors.append(f"Unified Discovery error: {exc}")

        duration = time.monotonic() - start
        log.info(
            "Runtime discovery complete via unified engine",
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
        # Delegate to the unified core discovery engine
        try:
            discovered = await self._core_manager.discover_all()
            for item in discovered:
                try:
                    if RuntimeType(item.runtime_type.value) == runtime_type:
                        info = RuntimeInfo(
                            runtime_type=runtime_type,
                            name=item.name,
                            version=item.version or "unknown",
                            path=item.binary_path or "",
                            executable=item.executable or item.name,
                            capabilities=[],
                            verified=item.found,
                        )
                        self._runtimes[runtime_type] = info
                        return info
                except ValueError:
                    continue
            # Runtime not found — ensure it's removed from cache
            self._runtimes.pop(runtime_type, None)
        except Exception:
            self._runtimes.pop(runtime_type, None)
        return None

    async def get_discovery_count(self) -> int:
        return len(self._runtimes)
