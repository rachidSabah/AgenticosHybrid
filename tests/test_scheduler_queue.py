"""Tests for DurableTaskQueue and scheduler_queue leased task lifecycle."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from agentic_os.core.persistent.domain import QueueTaskStatus
from agentic_os.core.persistent.scheduler_queue import DurableTaskQueue


@pytest.fixture
def mock_bus():
    bus = AsyncMock()
    bus.publish = AsyncMock()
    return bus


@pytest.fixture
def mock_persistence():
    persistence = AsyncMock()
    persistence.save_queue_task = AsyncMock()
    return persistence


@pytest.fixture
def queue(mock_bus, mock_persistence):
    return DurableTaskQueue(bus=mock_bus, persistence=mock_persistence)


@pytest.mark.asyncio
async def test_enqueue_and_lease(queue):
    task = await queue.enqueue({"data": 123}, queue="test", priority=1)
    assert task.status == QueueTaskStatus.QUEUED
    assert queue.stats["enqueued"] == 1

    leased = await queue.lease(queue="test", worker_id="worker-1", lease_s=10.0)
    assert leased is not None
    assert leased.id == task.id
    assert leased.status == QueueTaskStatus.LEASED
    assert leased.lease_owner == "worker-1"
    assert leased.attempts == 1
    assert queue.stats["leased_count"] == 1
    assert len(queue.list_tasks("test")) == 0


@pytest.mark.asyncio
async def test_ack_leased_task(queue):
    _task = await queue.enqueue({"payload": "foo"}, queue="test")
    leased = await queue.lease(queue="test", worker_id="worker-2")
    assert leased is not None

    ok = await queue.ack(leased.id, worker_id="worker-2", result={"res": "ok"})
    assert ok is True
    assert leased.status == QueueTaskStatus.COMPLETED
    assert leased.result == {"res": "ok"}
    assert queue.stats["completed"] == 1
    assert queue.stats["leased_count"] == 0


@pytest.mark.asyncio
async def test_nack_requeues_when_attempts_remain(queue):
    _task = await queue.enqueue({"payload": "bar"}, queue="test", max_attempts=2)
    leased = await queue.lease(queue="test", worker_id="worker-3")
    assert leased is not None

    ok = await queue.nack(leased.id, worker_id="worker-3", error="Temporary failure")
    assert ok is True
    assert leased.status == QueueTaskStatus.QUEUED
    assert leased.lease_owner == ""
    assert queue.stats["leased_count"] == 0
    assert len(queue.list_tasks("test")) == 1


@pytest.mark.asyncio
async def test_nack_dead_letters_after_max_attempts(queue):
    _task = await queue.enqueue({"payload": "baz"}, queue="test", max_attempts=1)
    leased = await queue.lease(queue="test", worker_id="worker-4")
    assert leased is not None

    ok = await queue.nack(leased.id, worker_id="worker-4", error="Fatal failure")
    assert ok is True
    assert leased.status == QueueTaskStatus.DEAD_LETTER
    assert queue.stats["dead_lettered"] == 1
    assert queue.stats["leased_count"] == 0
    assert len(queue.list_dead_letter()) == 1


@pytest.mark.asyncio
async def test_check_timeouts(queue):
    _task = await queue.enqueue({"payload": "timeout_test"}, queue="test")
    leased = await queue.lease(queue="test", worker_id="worker-5", lease_s=1.0)
    assert leased is not None

    # Manually expire the lease
    leased.lease_expires = (datetime.now(UTC) - timedelta(seconds=5)).isoformat()

    timed_out = await queue.check_timeouts()
    assert timed_out == 1
    assert leased.status == QueueTaskStatus.TIMED_OUT
    assert leased.lease_owner == ""
    assert queue.stats["timed_out"] == 1
    assert queue.stats["leased_count"] == 0
    assert len(queue.list_tasks("test")) == 1
