from __future__ import annotations

import platform
import shutil
import subprocess
import time
from datetime import UTC, datetime
from typing import Any

from core.logging import get_logger
from services.runtime_discovery.models import (
    Runtime,
    RuntimeProfile,
    RuntimeType,
    RuntimeValidationResult,
)

_log = get_logger(__name__)

__all__ = ["ProfilingEngine"]

_RESOURCE_FOOTPRINT_MB: dict[RuntimeType, float] = {
    RuntimeType.CLAUDE_CODE: 512.0,
    RuntimeType.GEMINI_CLI: 256.0,
    RuntimeType.CODEX_CLI: 384.0,
    RuntimeType.HERMES: 1024.0,
    RuntimeType.OPENHANDS: 768.0,
    RuntimeType.AIDER: 256.0,
    RuntimeType.CONTINUE: 512.0,
    RuntimeType.CLINE: 384.0,
    RuntimeType.ROO_CODE: 256.0,
    RuntimeType.OLLAMA: 2048.0,
    RuntimeType.PYTHON: 64.0,
    RuntimeType.NODEJS: 128.0,
    RuntimeType.DOCKER: 256.0,
    RuntimeType.GIT: 32.0,
    RuntimeType.GH_CLI: 64.0,
    RuntimeType.MCP_SERVER: 128.0,
}

_LATENCY_ESTIMATE_MS: dict[RuntimeType, float] = {
    RuntimeType.CLAUDE_CODE: 15000.0,
    RuntimeType.GEMINI_CLI: 10000.0,
    RuntimeType.CODEX_CLI: 20000.0,
    RuntimeType.HERMES: 2000.0,
    RuntimeType.OPENHANDS: 25000.0,
    RuntimeType.AIDER: 12000.0,
    RuntimeType.CONTINUE: 18000.0,
    RuntimeType.CLINE: 14000.0,
    RuntimeType.ROO_CODE: 16000.0,
    RuntimeType.OLLAMA: 5000.0,
    RuntimeType.PYTHON: 500.0,
    RuntimeType.NODEJS: 500.0,
    RuntimeType.DOCKER: 2000.0,
    RuntimeType.GIT: 300.0,
    RuntimeType.GH_CLI: 1000.0,
    RuntimeType.MCP_SERVER: 500.0,
}

_COST_ESTIMATE_USD: dict[RuntimeType, float] = {
    RuntimeType.CLAUDE_CODE: 0.015,
    RuntimeType.GEMINI_CLI: 0.005,
    RuntimeType.CODEX_CLI: 0.010,
    RuntimeType.HERMES: 0.0,
    RuntimeType.OPENHANDS: 0.008,
    RuntimeType.AIDER: 0.006,
    RuntimeType.CONTINUE: 0.012,
    RuntimeType.CLINE: 0.014,
    RuntimeType.ROO_CODE: 0.007,
    RuntimeType.OLLAMA: 0.0,
    RuntimeType.PYTHON: 0.0,
    RuntimeType.NODEJS: 0.0,
    RuntimeType.DOCKER: 0.0,
    RuntimeType.GIT: 0.0,
    RuntimeType.GH_CLI: 0.0,
    RuntimeType.MCP_SERVER: 0.0,
}

_SUPPORTS_STREAMING: dict[RuntimeType, bool] = {
    RuntimeType.CLAUDE_CODE: True,
    RuntimeType.GEMINI_CLI: True,
    RuntimeType.CODEX_CLI: True,
    RuntimeType.AIDER: True,
    RuntimeType.CONTINUE: True,
    RuntimeType.CLINE: True,
    RuntimeType.ROO_CODE: True,
    RuntimeType.OLLAMA: True,
}

_MAX_CONCURRENCY: dict[RuntimeType, int] = {
    RuntimeType.CLAUDE_CODE: 1,
    RuntimeType.GEMINI_CLI: 1,
    RuntimeType.CODEX_CLI: 1,
    RuntimeType.HERMES: 1,
    RuntimeType.PYTHON: 4,
    RuntimeType.NODEJS: 4,
    RuntimeType.GIT: 1,
    RuntimeType.DOCKER: 2,
}

_CONFIG_DEFAULTS: dict[RuntimeType, dict[str, Any]] = {
    RuntimeType.CLAUDE_CODE: {"timeout_s": 600, "model": "claude-sonnet-4"},
    RuntimeType.GEMINI_CLI: {"timeout_s": 600, "model": "gemini-2.0-flash"},
    RuntimeType.CODEX_CLI: {"timeout_s": 600, "model": "gpt-4o"},
    RuntimeType.HERMES: {"timeout_s": 120},
    RuntimeType.PYTHON: {"timeout_s": 30},
    RuntimeType.NODEJS: {"timeout_s": 30},
    RuntimeType.GIT: {"timeout_s": 60},
    RuntimeType.DOCKER: {"timeout_s": 120},
}


class ProfilingEngine:
    async def profile(self, runtime: Runtime) -> RuntimeProfile:
        executable_path = runtime.binary_path or ""
        start = time.monotonic()
        if executable_path:
            try:
                subprocess.run([executable_path, "--version"], capture_output=True, timeout=5)
            except Exception:
                pass
        measured_latency = (time.monotonic() - start) * 1000

        return RuntimeProfile(
            runtime_id=runtime.runtime_id,
            runtime_type=runtime.runtime_type,
            version=runtime.version or "unknown",
            executable_path=executable_path,
            platform=platform.system().lower(),
            capabilities=[c.namespace for c in runtime.capabilities],
            supports_streaming=_SUPPORTS_STREAMING.get(runtime.runtime_type, False),
            supports_mcp=self._estimate_mcp_support(runtime),
            supports_tools=True,
            supports_vision=runtime.runtime_type
            in (
                RuntimeType.CLAUDE_CODE,
                RuntimeType.GEMINI_CLI,
                RuntimeType.CODEX_CLI,
                RuntimeType.HERMES,
            ),
            latency_estimate_ms=measured_latency
            or _LATENCY_ESTIMATE_MS.get(runtime.runtime_type, 5000),
            cost_estimate=_COST_ESTIMATE_USD.get(runtime.runtime_type, 0.0),
            resource_footprint_mb=_RESOURCE_FOOTPRINT_MB.get(runtime.runtime_type, 128),
            max_concurrency=_MAX_CONCURRENCY.get(runtime.runtime_type, 1),
            config_defaults=_CONFIG_DEFAULTS.get(runtime.runtime_type, {}),
            created_at=datetime.now(UTC),
        )

    async def to_execution_profile(self, profile: RuntimeProfile) -> dict[str, Any]:
        return {
            "name": profile.runtime_id,
            "engine_type": profile.runtime_type.value,
            "version": profile.version,
            "executable_path": profile.executable_path,
            "platform": profile.platform,
            "capabilities": list(profile.capabilities),
            "supports_streaming": profile.supports_streaming,
            "supports_mcp": profile.supports_mcp,
            "latency_estimate_ms": profile.latency_estimate_ms,
            "cost_estimate": profile.cost_estimate,
            "resource_footprint_mb": profile.resource_footprint_mb,
            "max_concurrency": profile.max_concurrency,
            "config_defaults": dict(profile.config_defaults),
        }

    @staticmethod
    def _estimate_mcp_support(runtime: Runtime) -> bool:
        return runtime.runtime_type in (
            RuntimeType.CLAUDE_CODE,
            RuntimeType.CODEX_CLI,
            RuntimeType.CONTINUE,
            RuntimeType.CLINE,
        )
