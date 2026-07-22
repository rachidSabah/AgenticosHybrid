"""Scheduler skeleton.

Minimal periodic task runner used by the Health Monitor. The full Temporal-backed
workflow engine is a later phase; this skeleton provides the same ``every``
interface so callers don't change when we upgrade (ADR-0006).

Implemented with plain asyncio tasks + a stop event so it is safe to start and
stop across async-context boundaries (e.g. pytest fixture teardown).
"""

from __future__ import annotations

import asyncio

from agentic_os.infrastructure.logging import get_logger

log = get_logger("core.scheduler")


class Scheduler:
    def __init__(self) -> None:
        self._tasks: list[asyncio.Task] = []
        self._stop = asyncio.Event()

    async def start(self) -> None:
        self._stop.clear()

    async def stop(self) -> None:
        self._stop.set()
        for t in self._tasks:
            t.cancel()
        for t in self._tasks:
            try:
                await t
            except asyncio.CancelledError, Exception:
                pass
        self._tasks.clear()

    def every(self, seconds: float, coro_fn) -> None:
        """Schedule ``coro_fn`` to run repeatedly every ``seconds``."""

        async def _loop() -> None:
            while not self._stop.is_set():
                try:
                    await asyncio.sleep(seconds)
                    if self._stop.is_set():
                        break
                    await coro_fn()
                except asyncio.CancelledError:
                    break
                except Exception:
                    log.exception("Scheduled task failed")

        self._tasks.append(asyncio.create_task(_loop()))
