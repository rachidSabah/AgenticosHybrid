from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from core.contracts.event import Event

Handler = Callable[[Event], Awaitable[None]]


class EventBus:
    def __init__(self, queue_capacity: int = 10_000, worker_count: int = 16) -> None:
        self._topics: dict[str, dict[str, Handler]] = {}
        self._tasks: set[asyncio.Task] = set()
        self._lock = asyncio.Lock()
        self._started = False
        self._queue_capacity = queue_capacity
        self._worker_count = worker_count
        self._queue: asyncio.Queue[tuple[Handler, Event] | None] | None = None
        self._workers: list[asyncio.Task] = []
        self._error_counts: dict[str, int] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    @property
    def error_counts(self) -> dict[str, int]:
        return dict(self._error_counts)

    async def _worker_loop(self) -> None:
        while True:
            if self._queue is None:
                break
            try:
                item = await self._queue.get()
            except asyncio.CancelledError:
                break
            if item is None:
                self._queue.task_done()
                break
            handler, event = item
            try:
                await self._safe_dispatch(handler, event)
            finally:
                self._queue.task_done()

    async def start(self) -> None:
        async with self._lock:
            if self._started:
                return
            self._started = True
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                self._loop = None
            if self._queue is None:
                self._queue = asyncio.Queue(maxsize=self._queue_capacity)
            self._workers = [
                asyncio.create_task(self._worker_loop(), name=f"corebus-worker-{i}")
                for i in range(self._worker_count)
            ]

    async def stop(self) -> None:
        async with self._lock:
            if not self._started:
                return
            self._started = False

        if self._queue is not None:
            try:
                await asyncio.wait_for(self._queue.join(), timeout=0.5)
            except TimeoutError:
                pass
            for _ in self._workers:
                try:
                    self._queue.put_nowait(None)
                except (asyncio.QueueFull, Exception):
                    pass
            for w in self._workers:
                w.cancel()
            await asyncio.gather(*self._workers, return_exceptions=True)
            self._workers.clear()
            self._queue = None
            self._loop = None

        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

    async def publish(self, event: Event) -> None:
        if not self._started:
            raise RuntimeError("EventBus.publish called before start()")
        handlers = list(self._topics.get(event.topic, {}).values())
        if not handlers:
            return
        try:
            cur_loop = asyncio.get_running_loop()
        except RuntimeError:
            cur_loop = None

        if (
            self._queue is not None
            and self._workers
            and (self._loop is None or cur_loop == self._loop)
        ):
            for handler in handlers:
                try:
                    self._queue.put_nowait((handler, event))
                except asyncio.QueueFull:
                    await self._queue.put((handler, event))
        else:
            for handler in handlers:
                task = asyncio.create_task(self._safe_dispatch(handler, event))
                self._tasks.add(task)
                task.add_done_callback(self._tasks.discard)

    async def _safe_dispatch(self, handler: Handler, event: Event) -> None:
        try:
            await handler(event)
        except Exception as exc:
            import logging

            topic = getattr(event, "topic", "unknown")
            self._error_counts[topic] = self._error_counts.get(topic, 0) + 1
            logging.getLogger("core.event_bus").warning(
                "Dispatch failed for topic %s: %s", topic, exc
            )

    async def subscribe(self, topic: str, handler: Handler) -> str:
        sub_id = f"{topic}:{id(handler)}"
        async with self._lock:
            self._topics.setdefault(topic, {})[sub_id] = handler
        return sub_id

    async def unsubscribe(self, subscription_id: str) -> None:
        topic = subscription_id.split(":", 1)[0]
        async with self._lock:
            self._topics.get(topic, {}).pop(subscription_id, None)

    async def drain(self) -> None:
        if self._queue is not None:
            await self._queue.join()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
