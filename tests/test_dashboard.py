"""Tests for the live dashboard WebSocket broadcaster (Phase 3A)."""

from __future__ import annotations

import pytest

from agentic_os.adapters.bus.local import LocalBus
from agentic_os.api.dashboard import DashboardBroadcaster
from agentic_os.domain.events import EventEnvelope, Topic


@pytest.fixture
async def bus():
    b = LocalBus()
    await b.start()
    yield b
    await b.stop()


async def test_forwards_phase2_topics(bus):
    """The broadcaster must forward memory/provider/security/capability events
    (Phase 2 topics) to connected clients, not just task/agent/health."""
    bc = DashboardBroadcaster(bus)
    await bc.start()
    recv, send = bc.add_client()

    seen: list[str] = []

    async def pump():
        async for snap in recv:
            seen.append(snap["topic"])

    async with recv:
        import asyncio

        task = asyncio.create_task(pump())
        # Emit one event per Phase-2 category.
        for topic in (
            Topic.MEMORY_WRITTEN,
            Topic.PROVIDER_HEALTH,
            Topic.AGENT_COMPOSED,
            Topic.APPROVAL_REQUESTED,
            Topic.COST_RECORDED,
        ):
            await bus.publish(EventEnvelope(type="t", source="test", topic=topic.value, payload={}))
        await asyncio.sleep(0.1)
        task.cancel()

    assert Topic.MEMORY_WRITTEN.value in seen
    assert Topic.PROVIDER_HEALTH.value in seen
    assert Topic.AGENT_COMPOSED.value in seen
    assert Topic.APPROVAL_REQUESTED.value in seen
    assert Topic.COST_RECORDED.value in seen
    bc.remove_client(send)


async def test_legacy_task_topics_still_forwarded(bus):
    bc = DashboardBroadcaster(bus)
    await bc.start()
    recv, send = bc.add_client()
    seen: list[str] = []

    async def pump():
        async for snap in recv:
            seen.append(snap["topic"])

    async with recv:
        import asyncio

        task = asyncio.create_task(pump())
        await bus.publish(
            EventEnvelope(type="t", source="test", topic=Topic.TASK_CREATED.value, payload={})
        )
        await asyncio.sleep(0.1)
        task.cancel()

    assert Topic.TASK_CREATED.value in seen
    bc.remove_client(send)
