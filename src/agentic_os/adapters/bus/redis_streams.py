"""Redis Streams Event Bus adapter (default production).

Each topic maps to a Redis Stream. Consumers read via consumer groups so that
multiple supervisors can share load and survive restarts with ``>`` reads.
Payloads are JSON-encoded envelopes.
"""

from __future__ import annotations

import asyncio

import redis.asyncio as redis

from agentic_os.domain.events import EventEnvelope
from agentic_os.ports.event_bus import EventBus, Handler

CONSUMER_GROUP = "agentic-os"
_CONSUMER_NAME = "kernel"


class RedisStreamsBus:
    def __init__(self, url: str) -> None:
        self._url = url
        self._client: redis.Redis | None = None
        self._handlers: dict[str, Handler] = {}
        self._tasks: list = []

    async def start(self) -> None:  # noqa: C901
        self._client = redis.Redis.from_url(self._url, decode_responses=True)
        # Ensure a consumer group exists per subscribed topic (lazy on subscribe).
        for topic in self._handlers:
            await self._ensure_group(topic)

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        if self._client is not None:
            await self._client.aclose()

    async def _ensure_group(self, topic: str) -> None:
        assert self._client is not None
        try:
            await self._client.xgroup_create(topic, CONSUMER_GROUP, id="0", mkstream=True)
        except redis.ResponseError as exc:  # group may already exist
            if "BUSYGROUP" not in str(exc):
                raise

    async def publish(self, event: EventEnvelope) -> None:
        assert self._client is not None
        await self._client.xadd(event.topic, {"payload": event.model_dump_json()})

    async def subscribe(self, topic: str, handler: Handler) -> str:
        sub_id = f"{topic}:{id(handler)}"
        self._handlers[topic] = handler
        if self._client is not None:
            await self._ensure_group(topic)
            import anyio

            self._tasks.append(anyio.create_task(self._read_loop(topic)))
        return sub_id

    async def unsubscribe(self, subscription_id: str) -> None:
        topic = subscription_id.split(":", 1)[0]
        self._handlers.pop(topic, None)

    async def _read_loop(self, topic: str) -> None:
        from typing import Any

        assert self._client is not None
        handler = self._handlers[topic]
        while True:
            try:
                resp: Any = await self._client.xreadgroup(
                    CONSUMER_GROUP, _CONSUMER_NAME, {topic: ">"}, count=10, block=1000
                )
            except Exception:
                await asyncio.sleep(1)
                continue
            entries: list = list(resp) if resp else []
            for _stream, messages in entries:
                for msg_id, fields in messages:
                    try:
                        payload = fields.get("payload") if isinstance(fields, dict) else fields
                        event = EventEnvelope.model_validate_json(payload)
                        await handler(event)
                    finally:
                        await self._client.xack(topic, CONSUMER_GROUP, msg_id)


def create_redis_bus(url: str) -> EventBus:
    return RedisStreamsBus(url)  # type: ignore[return-value]
