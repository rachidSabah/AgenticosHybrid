from __future__ import annotations

import asyncio
import json
import os
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


class CustomEngineAdapter(BaseExecutionEngineAdapter):
    def __init__(self, config: EngineConfig) -> None:
        super().__init__(config)
        self._process: asyncio.subprocess.Process | None = None
        self._binary_path = config.binary_path or self._find_binary()

    @staticmethod
    def _find_binary() -> str | None:
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
        _log.info("Executing with custom engine %s", self._config.name, goal=goal[:100])
        command = self._config.extra.get("command_template", "{goal}").format(goal=goal)
        if self._process and self._process.returncode is None:
            request = json.dumps({"method": "execute", "params": {"command": command}}) + "\n"
            assert self._process.stdin is not None
            self._process.stdin.write(request.encode())
            await self._process.stdin.drain()
            assert self._process.stdout is not None
            response = await asyncio.wait_for(self._process.stdout.readline(), timeout=self._config.extra.get("timeout_s", 300))
            return json.loads(response.decode()) if response else {"result": "empty"}
        return {"goal": goal, "result": f"custom_execution: {command[:50]}", "mock": True}

    async def _on_cancel(self, task_id: str) -> bool:
        if not self._process:
            return False
        cancel_request = json.dumps({"method": "cancel", "params": {"task_id": task_id}}) + "\n"
        assert self._process.stdin is not None
        self._process.stdin.write(cancel_request.encode())
        await self._process.stdin.drain()
        return True

    async def _on_discover_capabilities(self) -> EngineCapabilities:
        return EngineCapabilities(
            supports_streaming=self._config.extra.get("supports_streaming", True),
            supports_cancellation=self._config.extra.get("supports_cancellation", True),
            supports_sessions=self._config.extra.get("supports_sessions", False),
            supports_tools=self._config.extra.get("supports_tools", True),
            supports_vision=self._config.extra.get("supports_vision", False),
            max_concurrent_tasks=self._config.extra.get("max_concurrent_tasks", 1),
            task_timeout_s=self._config.extra.get("task_timeout_s", 600.0),
            features=self._config.extra.get("features", ["custom.execute"]),
        )

    async def _on_estimate_cost(self, task: Any) -> EngineCostEstimate:
        custom_cost = self._config.extra.get("estimated_cost_usd", 0.01)
        return EngineCostEstimate(
            estimated_cost_usd=custom_cost,
            estimated_tokens_input=self._config.extra.get("estimated_tokens_input", 1000),
            estimated_tokens_output=self._config.extra.get("estimated_tokens_output", 500),
            breakdown={"custom_estimate": custom_cost},
        )

    async def _on_estimate_latency(self, task: Any) -> EngineLatencyEstimate:
        return EngineLatencyEstimate(
            estimated_duration_s=self._config.extra.get("estimated_latency_s", 10.0),
            p50_latency_s=self._config.extra.get("p50_latency_s", 8.0),
            p95_latency_s=self._config.extra.get("p95_latency_s", 20.0),
            p99_latency_s=self._config.extra.get("p99_latency_s", 40.0),
            based_on_samples=self._config.extra.get("latency_samples", 50),
        )
