"""NATS JetStream Event Bus adapter (supported alternative).

Topics become JetStream subjects. Durable consumers provide replay and
at-least-once delivery. The JSON payload is the envelope.
"""

from __future__ import annotations

import nats
from nats.js.client import JetStreamContext

from agentic_os.domain.events import EventEnvelope
from agentic_os.ports.event_bus import EventBus, Handler

_STREAM = "AGENTIC_OS"
_DURABLE = "kernel"


class NatsJetStreamBus:
    def __init__(self, url: str) -> None:
        self._url = url
        self._nc = None
        self._js: JetStreamContext | None = None
        self._handlers: dict[str, Handler] = {}
        self._subs: list = []

    async def start(self) -> None:
        self._nc = await nats.connect(self._url)
        self._js = self._nc.jetstream()
        await self._js.add_stream(name=_STREAM, subjects=["*"])
        for topic in self._handlers:
            await self._consume(topic)

    async def stop(self) -> None:
        for sub in self._subs:
            await sub.unsubscribe()
        if self._nc is not None:
            await self._nc.drain()

    async def publish(self, event: EventEnvelope) -> None:
        if self._js is None:
            raise RuntimeError("NATS JetStream not started")
        await self._js.publish(event.topic, event.model_dump_json().encode())

    async def subscribe(self, topic: str, handler: Handler) -> str:
        sub_id = f"{topic}:{id(handler)}"
        self._handlers[topic] = handler
        if self._js is not None:
            await self._consume(topic)
        return sub_id

    async def _consume(self, topic: str) -> None:
        if self._js is None:
            raise RuntimeError("NATS JetStream not started")
        handler = self._handlers[topic]
        sub = await self._js.subscribe(topic, durable=_DURABLE, manual_ack=True)

        async def _loop() -> None:
            async for msg in sub.messages:
                try:
                    event = EventEnvelope.model_validate_json(msg.data)
                    await handler(event)
                    await msg.ack()
                except Exception:
                    await msg.nak()

        import anyio

        self._subs.append(sub)
        self._subs.append(anyio.create_task(_loop()))

    async def unsubscribe(self, subscription_id: str) -> None:
        topic = subscription_id.split(":", 1)[0]
        self._handlers.pop(topic, None)


def create_nats_bus(url: str) -> EventBus:
    return NatsJetStreamBus(url)  # type: ignore[return-value]
