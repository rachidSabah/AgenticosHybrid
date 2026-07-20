from __future__ import annotations

import subprocess
from collections.abc import AsyncIterator
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


class LocalEngineAdapter(BaseExecutionEngineAdapter):
    def __init__(self, config: EngineConfig | None = None) -> None:
        if config is None:
            config = EngineConfig(
                type=EngineType.LOCAL,
                name="local",
                version="1.0.0",
            )
        super().__init__(config)
        self._capabilities = EngineCapabilities(
            supports_streaming=False,
            supports_cancellation=False,
            supports_sessions=False,
            supports_tools=False,
            supports_vision=False,
            max_concurrent_tasks=5,
            task_timeout_s=30.0,
            features=["shell.execute", "fs.read", "fs.write"],
        )

    async def _on_execute(self, task: Any) -> Any:
        goal = task.goal if hasattr(task, "goal") else str(task)
        _log.info("Executing locally", goal=goal[:100])
        if isinstance(goal, str) and goal.startswith(("ls", "echo", "pwd", "whoami")):
            try:
                result = subprocess.run(
                    goal, shell=True, capture_output=True, text=True, timeout=30
                )
                return {
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "exit_code": result.returncode,
                    "mock": False,
                }
            except subprocess.TimeoutExpired:
                return {"error": "timeout", "mock": False}
        return {"goal": goal, "result": f"local_execution: {goal[:50]}", "mock": True}

    async def _on_stream(self, task: Any) -> AsyncIterator[Any]:
        result = await self._on_execute(task)
        yield result

    async def _on_discover_capabilities(self) -> EngineCapabilities:
        return EngineCapabilities(
            supports_streaming=False,
            supports_cancellation=False,
            supports_sessions=False,
            supports_tools=False,
            supports_vision=False,
            max_concurrent_tasks=5,
            task_timeout_s=30.0,
            features=["shell.execute", "fs.read", "fs.write"],
        )

    async def _on_estimate_cost(self, task: Any) -> EngineCostEstimate:
        return EngineCostEstimate(
            estimated_cost_usd=0.0,
            estimated_tokens_input=0,
            estimated_tokens_output=0,
            breakdown={"note": "local execution, no cost"},
        )

    async def _on_estimate_latency(self, task: Any) -> EngineLatencyEstimate:
        return EngineLatencyEstimate(
            estimated_duration_s=1.0,
            p50_latency_s=0.5,
            p95_latency_s=2.0,
            p99_latency_s=5.0,
            based_on_samples=1000,
        )
