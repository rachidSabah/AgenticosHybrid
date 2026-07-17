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

from agentic_os.domain.events import EventEnvelope
from agentic_os.ports.event_bus import EventBus, Handler


class LocalBus:
    def __init__(self) -> None:
        self._topics: dict[str, dict[str, Handler]] = {}
        self._tasks: set[asyncio.Task] = set()
        self._lock = asyncio.Lock()
        self._started = False

    async def start(self) -> None:
        self._started = True

    async def drain(self) -> None:
        """Await all in-flight event dispatches (test/inspection helper)."""
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

    async def stop(self) -> None:
        # Let in-flight dispatches complete so subscribers observe pending events.
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        self._started = False

    async def publish(self, event: EventEnvelope) -> None:
        if not self._started:
            raise RuntimeError("LocalBus.publish called before start()")
        handlers = list(self._topics.get(event.topic, {}).values())
        for handler in handlers:
            task = asyncio.create_task(self._safe_dispatch(handler, event))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    async def _safe_dispatch(self, handler: Handler, event: EventEnvelope) -> None:
        try:
            await handler(event)
        except Exception:
            # Isolation: one bad subscriber must not kill the fan-out.
            pass

    async def subscribe(self, topic: str, handler: Handler) -> str:
        sub_id = f"{topic}:{id(handler)}"
        async with self._lock:
            self._topics.setdefault(topic, {})[sub_id] = handler
        return sub_id

    async def unsubscribe(self, subscription_id: str) -> None:
        topic = subscription_id.split(":", 1)[0]
        async with self._lock:
            self._topics.get(topic, {}).pop(subscription_id, None)


def create_local_bus() -> EventBus:
    return LocalBus()  # type: ignore[return-value]
