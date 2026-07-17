"""Port: Event Bus.

The single most important interface in the system. Everything communicates
through it. Three adapters implement this protocol:

* ``LocalBus``        — in-process asyncio (dev/tests/zero-infra)
* ``RedisStreamsBus`` — Redis Streams (default production)
* ``NatsJetStreamBus``— NATS JetStream (supported alternative)

A ``Handler`` is any async callable receiving an :class:`EventEnvelope`.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol, runtime_checkable

from agentic_os.domain.events import EventEnvelope

Handler = Callable[[EventEnvelope], Awaitable[None]]


@runtime_checkable
class EventBus(Protocol):
    """Abstract event bus contract."""

    async def start(self) -> None:
        """Connect/initialize the underlying transport."""
        ...

    async def stop(self) -> None:
        """Flush and tear down the underlying transport."""
        ...

    async def publish(self, event: EventEnvelope) -> None:
        """Publish an envelope to its ``topic``."""
        ...

    async def subscribe(self, topic: str, handler: Handler) -> str:
        """Subscribe ``handler`` to ``topic``. Returns a subscription id."""
        ...

    async def unsubscribe(self, subscription_id: str) -> None:
        """Cancel a subscription by id."""
        ...
