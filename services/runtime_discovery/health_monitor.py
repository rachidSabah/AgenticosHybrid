from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from typing import Any

from core.logging import get_logger
from services.runtime_discovery.models import (
    HealthStatus,
    Runtime,
    RuntimeHealth,
    RuntimeStatus,
)

_log = get_logger(__name__)

__all__ = ["RuntimeHealthMonitor"]


class RuntimeHealthMonitor:
    def __init__(self, check_interval_s: int = 60) -> None:
        self._health: dict[str, RuntimeHealth] = {}
        self._history: dict[str, list[RuntimeHealth]] = defaultdict(list)
        self._tasks: dict[str, asyncio.Task] = {}
        self._running = False
        self._check_interval_s = check_interval_s
        self._max_history = 100
        self._on_status_change: list[Any] = []

    def on_status_change(self, callback: Any) -> None:
        self._on_status_change.append(callback)

    async def check(self, runtime: Runtime) -> RuntimeHealth:
        import subprocess

        health = RuntimeHealth(runtime_id=runtime.runtime_id)
        binary = runtime.binary_path or runtime.name

        if not binary:
            health.record_failure("no binary path")
            return self._update(runtime, health)

        start = time.monotonic()
        try:
            result = subprocess.run(
                [binary, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            response_time = (time.monotonic() - start) * 1000
            if result.returncode == 0:
                health.record_success(response_time)
                health.version = (result.stdout or result.stderr).strip().split("\n")[0]
            else:
                health.record_failure(f"exit code {result.returncode}")
        except FileNotFoundError:
            health.record_failure("binary not found")
        except subprocess.TimeoutExpired:
            health.record_failure("health check timed out")
        except Exception as e:
            health.record_failure(str(e))

        return self._update(runtime, health)

    async def check_all(self, runtimes: list[Runtime]) -> list[RuntimeHealth]:
        results = await asyncio.gather(*[self.check(r) for r in runtimes], return_exceptions=True)
        healthy = []
        for r, result in zip(runtimes, results, strict=False):
            if isinstance(result, RuntimeHealth):
                healthy.append(result)
            else:
                health = RuntimeHealth(
                    runtime_id=r.runtime_id,
                    status=HealthStatus.UNHEALTHY,
                    healthy=False,
                    last_error=str(result),
                )
                healthy.append(self._update(r, health))
        return healthy

    def get_history(self, runtime_id: str, limit: int = 100) -> list[RuntimeHealth]:
        history = self._history.get(runtime_id, [])
        return history[-limit:]

    def get_health(self, runtime_id: str) -> RuntimeHealth | None:
        return self._health.get(runtime_id)

    def get_all_health(self) -> dict[str, RuntimeHealth]:
        return dict(self._health)

    async def start_periodic_check(self, runtime: Runtime) -> None:
        if runtime.runtime_id in self._tasks:
            return

        async def _check_loop():
            while self._running:
                await self.check(runtime)
                await asyncio.sleep(self._check_interval_s)

        self._tasks[runtime.runtime_id] = asyncio.create_task(_check_loop())
        _log.info(
            "Periodic health check started", runtime=runtime.name, interval=self._check_interval_s
        )

    async def stop_periodic_check(self, runtime_id: str) -> None:
        task = self._tasks.pop(runtime_id, None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def start_all(self, runtimes: list[Runtime]) -> None:
        self._running = True
        for runtime in runtimes:
            await self.start_periodic_check(runtime)

    async def stop_all(self) -> None:
        self._running = False
        for runtime_id in list(self._tasks.keys()):
            await self.stop_periodic_check(runtime_id)

    def _update(self, runtime: Runtime, health: RuntimeHealth) -> RuntimeHealth:
        prev = self._health.get(runtime.runtime_id)
        if prev and prev.status != health.status:
            for cb in self._on_status_change:
                try:
                    cb(runtime, prev.status, health.status)
                except Exception as e:
                    _log.warning("Status change callback error: %s", e)

        self._health[runtime.runtime_id] = health
        history = self._history[runtime.runtime_id]
        history.append(health)
        if len(history) > self._max_history:
            self._history[runtime.runtime_id] = history[-self._max_history :]

        runtime.health = health
        if not health.healthy:
            runtime.status = RuntimeStatus.UNHEALTHY
        elif runtime.status == RuntimeStatus.UNHEALTHY:
            runtime.status = RuntimeStatus.ACTIVE
        return health
