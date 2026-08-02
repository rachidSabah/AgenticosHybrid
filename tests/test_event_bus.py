"""Unit tests for the abstract Event Bus + Local adapter."""

from __future__ import annotations

from agentic_os.domain.events import EventEnvelope, Topic


async def test_publish_reaches_subscriber(bus):
    seen = []

    async def handler(e: EventEnvelope) -> None:
        seen.append(e)

    await bus.subscribe(Topic.TASK_CREATED.value, handler)
    await bus.publish(
        EventEnvelope(type="task.created", source="test", topic=Topic.TASK_CREATED.value)
    )
    await bus.publish(
        EventEnvelope(type="task.created", source="test", topic=Topic.TASK_CREATED.value)
    )
    # allow fan-out
    import anyio

    await anyio.sleep(0.05)
    assert len(seen) == 2


async def test_subscriber_isolation(bus):
    """A raising subscriber must not break other subscribers or the bus."""
    good = []

    async def bad(_: EventEnvelope) -> None:
        raise RuntimeError("boom")

    async def good_handler(e: EventEnvelope) -> None:
        good.append(e)

    await bus.subscribe(Topic.TASK_CREATED.value, bad)
    await bus.subscribe(Topic.TASK_CREATED.value, good_handler)
    await bus.publish(
        EventEnvelope(type="task.created", source="test", topic=Topic.TASK_CREATED.value)
    )
    import anyio

    await anyio.sleep(0.05)
    assert len(good) == 1


async def test_unsubscribe_stops_delivery(bus):
    seen = []

    async def handler(e: EventEnvelope) -> None:
        seen.append(e)

    sub_id = await bus.subscribe(Topic.TASK_CREATED.value, handler)
    await bus.unsubscribe(sub_id)
    await bus.publish(
        EventEnvelope(type="task.created", source="test", topic=Topic.TASK_CREATED.value)
    )
    import anyio

    await anyio.sleep(0.05)
    assert seen == []


async def test_publish_before_start_is_queued(bus):
    """Events published before start() are buffered and flushed once started.

    This prevents kernel subsystems that publish during their initialize()
    (which runs before bus.start()) from crashing on a RuntimeError.
    """
    fresh = __import__("agentic_os.adapters.bus.local", fromlist=["LocalBus"]).LocalBus()
    seen: list[EventEnvelope] = []

    async def handler(e: EventEnvelope) -> None:
        seen.append(e)

    # Subscribe + publish BEFORE start() — must NOT raise, must NOT lose events.
    await fresh.subscribe(Topic.TASK_CREATED.value, handler)
    await fresh.publish(EventEnvelope(type="x", source="t", topic=Topic.TASK_CREATED.value))

    # Subscriber must not have received it yet (bus not started).
    import anyio

    await anyio.sleep(0.05)
    assert seen == []

    # Start the bus — the queued event must now be delivered.
    await fresh.start()
    await anyio.sleep(0.05)
    assert len(seen) == 1
    await fresh.stop()
