from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from core.logging import get_logger

_log = get_logger(__name__)

__all__ = ["RuntimeDiscoveryScheduler"]


class RuntimeDiscoveryScheduler:
    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task] = {}
        self._running = False

    async def schedule(self, name: str, interval_s: int, coro_fn: Callable[[], Any]) -> None:
        if name in self._tasks:
            _log.warning("Scheduler task %s already running, skipping", name)
            return

        async def _loop():
            while self._running:
                try:
                    await coro_fn()
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    _log.warning("Scheduler task %s error: %s", name, e)
                await asyncio.sleep(interval_s)

        self._tasks[name] = asyncio.create_task(_loop())
        _log.info("Scheduled task", name=name, interval=interval_s)

    async def unschedule(self, name: str) -> None:
        task = self._tasks.pop(name, None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            _log.info("Unscheduled task", name=name)

    async def start_all(self) -> None:
        self._running = True

    async def stop_all(self) -> None:
        self._running = False
        for name in list(self._tasks.keys()):
            await self.unschedule(name)

    def is_scheduled(self, name: str) -> bool:
        return name in self._tasks

    def list_scheduled(self) -> list[str]:
        return list(self._tasks.keys())
