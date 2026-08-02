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
    def __init__(self) -> None:
        # topic -> {sub_id -> handler}
        self._topics: dict[str, dict[str, Handler]] = {}
        self._tasks: set[asyncio.Task] = set()
        self._lock = asyncio.Lock()
        self._started = False
        # Buffer events published before start() so subscribers don't miss them
        # and callers don't crash during subsystem initialization.
        self._pending: list[EventEnvelope] = []

    async def start(self) -> None:
        async with self._lock:
            self._started = True
            pending = list(self._pending)
            self._pending.clear()
        # Flush anything that was published before start().
        for event in pending:
            await self._dispatch(event)

    async def drain(self) -> None:
        """Await all in-flight event dispatches (test/inspection helper)."""
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

    async def stop(self) -> None:
        # Let in-flight dispatches complete so subscribers observe pending events.
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        async with self._lock:
            self._started = False
            self._pending.clear()

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
        for handler in handlers:
            task = asyncio.create_task(self._safe_dispatch(handler, event))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    async def _safe_dispatch(self, handler: Handler, event: EventEnvelope) -> None:
        try:
            await handler(event)
        except Exception:
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
