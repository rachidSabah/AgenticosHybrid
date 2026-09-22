"""In-process asyncio Event Bus.

The default dev/test adapter. No external infrastructure. Uses AnyIO tasks to
fan out each published event to its topic subscribers. This is the reference
implementation of the :class:`EventBus` protocol.

Note: we deliberately avoid holding an AnyIO TaskGroup across async-context
boundaries (e.g. pytest fixture teardown) — tasks are tracked in a set and
cancelled on stop, which is safe across tasks/loops.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

from agentic_os.domain.events import EventEnvelope
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.event_bus import EventBus, Handler

log = get_logger("bus.local")


class LocalBus:
    def __init__(self, queue_capacity: int = 10_000, worker_count: int = 16) -> None:
        # topic -> {sub_id -> handler}
        self._topics: dict[str, dict[str, Handler]] = {}
        self._tasks: set[asyncio.Task] = set()
        self._lock = asyncio.Lock()
        self._started = False
        # Buffer events published before start() so subscribers don't miss them
        # and callers don't crash during subsystem initialization.
        self._pending: list[EventEnvelope] = []
        self._queue_capacity = queue_capacity
        self._worker_count = worker_count
        self._queue: asyncio.Queue[tuple[Handler, EventEnvelope] | None] | None = None
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
                asyncio.create_task(self._worker_loop(), name=f"localbus-worker-{i}")
                for i in range(self._worker_count)
            ]
            pending = list(self._pending)
            self._pending.clear()
        # Flush anything that was published before start().
        for event in pending:
            await self._dispatch(event)

    async def drain(self) -> None:
        """Await all in-flight event dispatches (test/inspection helper)."""
        if self._queue is not None:
            try:
                await asyncio.wait_for(self._queue.join(), timeout=1.0)
            except TimeoutError:
                pass
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

    async def stop(self) -> None:
        async with self._lock:
            if not self._started:
                return
            self._started = False
            self._pending.clear()

        # Let queue drain and stop workers with timeout protection
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

    async def publish(self, event: EventEnvelope) -> None:
        async with self._lock:
            if not self._started:
                # Queue for later — many kernel subsystems publish during their
                # initialize() which runs before bus.start().
                self._pending.append(event)
                return
        await self._dispatch(event)

    async def _dispatch(self, event: EventEnvelope) -> None:
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
                    log.warning("Event bus queue saturated, applying caller backpressure")
                    await self._queue.put((handler, event))
        else:
            for handler in handlers:
                task = asyncio.create_task(self._safe_dispatch(handler, event))
                self._tasks.add(task)
                task.add_done_callback(self._tasks.discard)

    async def _safe_dispatch(self, handler: Handler, event: EventEnvelope) -> None:
        try:
            await handler(event)
        except Exception:
            self._error_counts[event.topic] = self._error_counts.get(event.topic, 0) + 1
            log.exception("Dispatch failed for topic %s", event.topic)

    async def subscribe(self, topic: str, handler: Handler) -> str:
        # Use a UUID sub_id rather than id(handler): id() can be recycled by
        # the GC, and keying on it would let a new handler overwrite an
        # existing subscription silently.
        sub_id = f"{topic}:{uuid4().hex}"
        async with self._lock:
            self._topics.setdefault(topic, {})[sub_id] = handler
        return sub_id

    async def unsubscribe(self, subscription_id: str) -> None:
        topic = subscription_id.split(":", 1)[0]
        async with self._lock:
            self._topics.get(topic, {}).pop(subscription_id, None)


def create_local_bus() -> EventBus:
    return LocalBus()  # type: ignore[return-value]
