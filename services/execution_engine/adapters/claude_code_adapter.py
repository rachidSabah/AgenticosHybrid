from __future__ import annotations

import asyncio
import json
import os
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from core.contracts.execution_engine import (
    EngineCapabilities,
    EngineConfig,
    EngineCostEstimate,
    EngineLatencyEstimate,
    EngineType,
)
from core.logging import get_logger
from services.execution_engine.adapters.base import BaseExecutionEngineAdapter

_log = get_logger(__name__)


class ClaudeCodeAdapter(BaseExecutionEngineAdapter):
    def __init__(self, config: EngineConfig | None = None) -> None:
        if config is None:
            config = EngineConfig(
                type=EngineType.CLAUDE_CODE,
                name="claude_code",
                version=self._detect_version(),
            )
        super().__init__(config)
        self._process: asyncio.subprocess.Process | None = None
        self._binary_path = self._find_binary()

    @staticmethod
    def _detect_version() -> str:
        try:
            import subprocess
            result = subprocess.run(["claude", "--version"], capture_output=True, text=True, timeout=10)
            return result.stdout.strip() or result.stderr.strip() or "unknown"
        except Exception:
            return "unknown"

    @staticmethod
    def _find_binary() -> str | None:
        for name in ("claude",):
            path_env = os.environ.get("PATH", "")
            for directory in path_env.split(os.pathsep):
                full = Path(directory) / name
                if full.is_file():
                    return str(full)
                if os.name == "nt":
                    for ext in (".exe", ".cmd", ".bat"):
                        full_ext = Path(directory) / f"{name}{ext}"
                        if full_ext.is_file():
                            return str(full_ext)
        return None

    async def _on_initialize(self) -> None:
        if self._binary_path:
            self._process = await asyncio.create_subprocess_exec(
                self._binary_path,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

    async def _on_shutdown(self) -> None:
        if self._process and self._process.returncode is None:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self._process.kill()

    async def _on_health_check(self) -> bool:
        return self._process is not None and self._process.returncode is None

    async def _on_execute(self, task: Any) -> Any:
        goal = task.goal if hasattr(task, "goal") else str(task)
        _log.info("Executing with Claude Code", goal=goal[:100])
        if not self._process:
            return {"goal": goal, "result": "mock_claude_execution", "mock": True}
        request = json.dumps({"method": "execute_task", "params": {"goal": goal}}) + "\n"
        assert self._process.stdin is not None
        self._process.stdin.write(request.encode())
        await self._process.stdin.drain()
        assert self._process.stdout is not None
        response = await asyncio.wait_for(self._process.stdout.readline(), timeout=self._config.extra.get("timeout_s", 300))
        return json.loads(response.decode()) if response else {"result": "empty"}

    async def _on_cancel(self, task_id: str) -> bool:
        if not self._process:
            return False
        cancel_request = json.dumps({"method": "cancel_task", "params": {"task_id": task_id}}) + "\n"
        assert self._process.stdin is not None
        self._process.stdin.write(cancel_request.encode())
        await self._process.stdin.drain()
        return True

    async def _on_stream(self, task: Any) -> AsyncIterator[Any]:
        goal = task.goal if hasattr(task, "goal") else str(task)
        if not self._process:
            yield {"goal": goal, "result": "mock_stream", "mock": True}
            return
        request = json.dumps({"method": "stream_task", "params": {"goal": goal}}) + "\n"
        assert self._process.stdin is not None
        self._process.stdin.write(request.encode())
        await self._process.stdin.drain()
        assert self._process.stdout is not None
        while True:
            line = await self._process.stdout.readline()
            if not line:
                break
            yield json.loads(line.decode())

    async def _on_discover_capabilities(self) -> EngineCapabilities:
        return EngineCapabilities(
            supports_streaming=True,
            supports_cancellation=True,
            supports_sessions=False,
            supports_tools=True,
            supports_vision=True,
            max_concurrent_tasks=1,
            task_timeout_s=600.0,
            features=["code.read", "code.write", "code.refactor", "code.review", "test.run", "shell.execute"],
        )

    async def _on_estimate_cost(self, task: Any) -> EngineCostEstimate:
        return EngineCostEstimate(
            estimated_cost_usd=0.015,
            estimated_tokens_input=1000,
            estimated_tokens_output=500,
            breakdown={"per_token": 0.000015, "estimated_tokens": 1500},
        )

    async def _on_estimate_latency(self, task: Any) -> EngineLatencyEstimate:
        return EngineLatencyEstimate(
            estimated_duration_s=15.0,
            p50_latency_s=12.0,
            p95_latency_s=30.0,
            p99_latency_s=60.0,
            based_on_samples=100,
        )
