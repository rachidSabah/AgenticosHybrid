"""Integration tests for the orchestrator vertical slice."""

from __future__ import annotations

import anyio

from agentic_os.adapters.providers.mock import MockProvider
from agentic_os.domain.agent import TaskStatus
from agentic_os.domain.events import EventEnvelope, Topic


async def test_full_slice_success(orchestrator, providers):
    providers.register(MockProvider())
    task = await orchestrator.create_task("Write a hello-world function", "coding")
    await anyio.sleep(0.5)
    stored = orchestrator.registry.get_task(task.id)
    assert stored.status == TaskStatus.COMPLETED
    assert stored.result
    assert any(a.status.value == "completed" for a in orchestrator.registry.agents())


async def test_failure_triggers_recovery_then_exhaust(kernel, providers, settings):
    settings.max_attempts = 2
    providers.register(MockProvider())
    task = await kernel.create_task("fail on purpose please", "coding")
    # allow retries + exhaustion
    await anyio.sleep(1.5)
    stored = kernel.registry.get_task(task.id)
    assert stored.status == TaskStatus.FAILED
    # attempts incremented on each re-dispatch
    assert stored.attempts >= 1


async def test_events_emitted_across_pipeline(orchestrator, providers, bus):
    providers.register(MockProvider())
    seen = []

    async def collect(e: EventEnvelope) -> None:
        seen.append(e.topic)

    for t in [Topic.TASK_CREATED, Topic.TASK_PLANNED, Topic.TASK_DISPATCHED, Topic.AGENT_COMPLETED]:
        await bus.subscribe(t.value, collect)
    await orchestrator.create_task("research the topic", "research")
    await anyio.sleep(0.5)
    assert Topic.TASK_CREATED.value in seen
    assert Topic.TASK_DISPATCHED.value in seen
    assert Topic.AGENT_COMPLETED.value in seen
