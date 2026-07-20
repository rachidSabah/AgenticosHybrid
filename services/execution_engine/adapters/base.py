from __future__ import annotations

import asyncio
import os
import statistics
import time
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.contracts.execution_engine import (
    EngineCapabilities,
    EngineConfig,
    EngineCostEstimate,
    EngineHealthState,
    EngineLatencyEstimate,
    EngineTelemetry,
    EngineType,
    ExecutionEngineError,
    ExecutionEnginePort,
)
from core.logging import get_logger

_log = get_logger(__name__)


class BaseExecutionEngineAdapter(ABC):
    def __init__(self, config: EngineConfig) -> None:
        self._config = config
        self._health = EngineHealthState(
            engine=config.name,
            engine_type=config.type,
            initialized=False,
        )
        self._telemetry = EngineTelemetry(
            engine=config.name,
            engine_type=config.type,
        )
        self._capabilities = EngineCapabilities()
        self._initialized = False
        self._latencies: list[float] = []

    @property
    def name(self) -> str:
        return self._config.name

    @property
    def engine_type(self) -> EngineType:
        return self._config.type

    @property
    def configuration(self) -> EngineConfig:
        return self._config

    async def initialize(self, config: EngineConfig | None = None) -> None:
        if config is not None:
            self._config = config
        try:
            await self._on_initialize()
            self._initialized = True
            self._health.initialized = True
            self._health.healthy = True
            _log.info("Engine initialized", engine=self.name)
        except Exception as e:
            self._health.healthy = False
            self._health.last_error = str(e)
            raise ExecutionEngineError(self.name, f"Initialization failed: {e}") from e

    async def shutdown(self) -> None:
        try:
            await self._on_shutdown()
        except Exception as e:
            _log.warning("Engine shutdown error: %s", e)
        finally:
            self._initialized = False
            self._health.initialized = False

    async def health_check(self) -> EngineHealthState:
        try:
            healthy = await self._on_health_check()
            self._health.healthy = healthy
            if healthy:
                self._health.consecutive_failures = 0
        except Exception as e:
            self._health.healthy = False
            self._health.consecutive_failures += 1
            self._health.last_error = str(e)
        self._health.last_health_check = datetime.now(UTC)
        return EngineHealthState(
            engine=self._health.engine,
            engine_type=self._health.engine_type,
            healthy=self._health.healthy,
            initialized=self._health.initialized,
            consecutive_failures=self._health.consecutive_failures,
            total_tasks=self._health.total_tasks,
            total_failures=self._health.total_failures,
            last_error=self._health.last_error,
            last_health_check=self._health.last_health_check,
        )

    async def execute(self, task: Any) -> Any:
        if not self._initialized:
            raise ExecutionEngineError(self.name, "Engine not initialized")
        start = time.monotonic()
        try:
            result = await self._on_execute(task)
            elapsed = time.monotonic() - start
            self._latencies.append(elapsed)
            self._telemetry.tasks_completed += 1
            self._telemetry.total_duration_s += elapsed
            self._telemetry.avg_duration_s = self._telemetry.total_duration_s / max(
                1, self._telemetry.tasks_completed + self._telemetry.tasks_failed
            )
            self._health.record_success()
            return result
        except Exception as e:
            elapsed = time.monotonic() - start
            self._telemetry.tasks_failed += 1
            self._telemetry.total_duration_s += elapsed
            self._health.record_failure(str(e))
            raise ExecutionEngineError(self.name, f"Execution failed: {e}", retryable=True) from e

    async def cancel(self, task_id: str) -> bool:
        try:
            return await self._on_cancel(task_id)
        except Exception as e:
            _log.warning("Cancel failed for task %s: %s", task_id, e)
            return False

    def stream(self, task: Any) -> AsyncIterator[Any]:
        return self._on_stream(task)

    async def benchmark(self) -> dict[str, Any]:
        return await self._on_benchmark()

    async def version(self) -> str:
        return self._config.version or "unknown"

    async def telemetry(self) -> EngineTelemetry:
        return self._telemetry

    async def discover_capabilities(self) -> EngineCapabilities:
        return await self._on_discover_capabilities()

    def supports(self, capability: str) -> bool:
        return capability in self._capabilities.features

    async def estimate_cost(self, task: Any) -> EngineCostEstimate:
        return await self._on_estimate_cost(task)

    async def estimate_latency(self, task: Any) -> EngineLatencyEstimate:
        return await self._on_estimate_latency(task)

    async def _on_initialize(self) -> None:
        pass

    async def _on_shutdown(self) -> None:
        pass

    async def _on_health_check(self) -> bool:
        return True

    @abstractmethod
    async def _on_execute(self, task: Any) -> Any:
        ...

    async def _on_cancel(self, task_id: str) -> bool:
        return False

    async def _on_stream(self, task: Any) -> AsyncIterator[Any]:
        yield await self._on_execute(task)

    async def _on_benchmark(self) -> dict[str, Any]:
        return {"engine": self.name, "status": "not_implemented"}

    async def _on_discover_capabilities(self) -> EngineCapabilities:
        return self._capabilities

    async def _on_estimate_cost(self, task: Any) -> EngineCostEstimate:
        return EngineCostEstimate()

    async def _on_estimate_latency(self, task: Any) -> EngineLatencyEstimate:
        avg = statistics.mean(self._latencies) if len(self._latencies) > 0 else 0.0
        return EngineLatencyEstimate(
            estimated_duration_s=avg,
            p50_latency_s=avg,
            p95_latency_s=avg,
            p99_latency_s=avg,
            based_on_samples=len(self._latencies),
        )
