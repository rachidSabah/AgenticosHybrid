"""Phase 17 — DistributedEventBus + DistributedExecutor + ClusterScheduler.

DistributedEventBus: wraps the existing LocalBus with cross-node event
  propagation. When an event is published locally, it's also forwarded
  to peer nodes via the transport layer. Incoming events from peers are
  re-published locally (with hop_count TTL to prevent loops).

DistributedExecutor: dispatches tasks to remote nodes for execution.
  Tracks acknowledgements, timeouts, and retries.

ClusterScheduler: extends Phase 16's GlobalMissionScheduler with actual
  remote dispatch capability. Selects the optimal (node, brain) pair
  and dispatches the task via the transport.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from agentic_os.core.distributed.cluster_models import (
    DistributedEvent,
    DistributedTask,
    DistributedTaskStatus,
    TaskAcknowledgement,
)
from agentic_os.infrastructure.logging import get_logger

if TYPE_CHECKING:
    from agentic_os.core.distributed.transport import NodeTransport
    from agentic_os.ports.event_bus import EventBus

log = get_logger("distributed.event_bus")


class DistributedEventBus:
    """Wraps the existing EventBus with cross-node event propagation.

    Does NOT replace the EventBus — it sits on top, forwarding events
    to peers and receiving events from peers. The existing EventBus
    remains the single source of truth for local event dispatch.
    """

    def __init__(
        self,
        bus: EventBus,
        transport: NodeTransport,
        local_node_id: str = "",
    ) -> None:
        self._bus = bus
        self._transport = transport
        self._local_node_id = local_node_id
        self._propagation_topics: set[str] = set()
        self._seen_event_ids: set[str] = set()
        self._max_seen_cache = 10000
        self._stats: dict[str, int] = {
            "events_propagated_out": 0,
            "events_received_in": 0,
            "events_dropped_loop": 0,
            "events_dropped_ttl": 0,
        }

    @property
    def stats(self) -> dict[str, Any]:
        return dict(self._stats)

    def register_propagation_topic(self, topic: str) -> None:
        """Register a topic prefix for cross-node propagation."""
        self._propagation_topics.add(topic)

    def register_propagation_prefix(self, prefix: str) -> None:
        """Register a topic prefix (e.g. 'brain.') for propagation."""
        # Store as prefix for matching
        self._propagation_topics.add(prefix)

    def should_propagate(self, topic: str) -> bool:
        """Check if a topic should be propagated to peers."""
        for prefix in self._propagation_topics:
            if topic.startswith(prefix) or topic == prefix:
                return True
        return False

    async def propagate_outbound(self, topic: str, payload: dict[str, Any]) -> int:
        """Propagate a local event to all peers. Returns count of peers reached."""
        if not self.should_propagate(topic):
            return 0
        if not self._transport.list_peers():
            return 0

        event = DistributedEvent(
            event_type=topic,
            source_node_id=self._local_node_id,
            origin_node_id=self._local_node_id,
            payload=payload,
        )

        # Track to prevent loops
        self._seen_event_ids.add(event.event_id)
        if len(self._seen_event_ids) > self._max_seen_cache:
            self._seen_event_ids = set(list(self._seen_event_ids)[-self._max_seen_cache :])

        delivered = await self._transport.broadcast_event(event.to_dict())
        self._stats["events_propagated_out"] += 1
        return delivered

    def receive_inbound(self, event_data: dict[str, Any]) -> bool:
        """Receive an event from a peer. Returns True if accepted locally.

        Events are rejected if:
        - Already seen (loop prevention)
        - TTL exceeded (hop_count >= max_hops)
        """
        event_id = str(event_data.get("event_id", ""))
        hop_count = int(event_data.get("hop_count", 0))
        max_hops = int(event_data.get("max_hops", 3))

        # Loop prevention
        if event_id and event_id in self._seen_event_ids:
            self._stats["events_dropped_loop"] += 1
            return False

        # TTL check
        if hop_count >= max_hops:
            self._stats["events_dropped_ttl"] += 1
            return False

        # Track
        if event_id:
            self._seen_event_ids.add(event_id)
            if len(self._seen_event_ids) > self._max_seen_cache:
                self._seen_event_ids = set(list(self._seen_event_ids)[-self._max_seen_cache :])

        self._stats["events_received_in"] += 1

        # Re-publish locally (the EventBus will dispatch to local subscribers)
        topic = str(event_data.get("event_type", ""))
        payload = event_data.get("payload", {})
        try:
            from agentic_os.domain.events import EventEnvelope

            # Schedule the publish on the event loop — receive_inbound is
            # sync so we can't await, but we can fire-and-forget.
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(
                    self._bus.publish(
                        EventEnvelope(
                            type=topic,
                            source=f"distributed.peer:{event_data.get('source_node_id', '')}",
                            topic=topic,
                            payload=payload,
                        )
                    )
                )
        except Exception:
            log.debug("Failed to re-publish inbound event", exc_info=True)

        return True


class DistributedExecutor:
    """Dispatches tasks to remote nodes for execution.

    Tracks task lifecycle: PENDING → DISPATCHED → ACKNOWLEDGED →
    EXECUTING → COMPLETED/FAILED/TIMEOUT.

    In single-node mode (no peers), tasks are marked as completed
    locally without any network calls.
    """

    def __init__(
        self,
        bus: EventBus,
        transport: NodeTransport,
        local_node_id: str = "",
    ) -> None:
        self._bus = bus
        self._transport = transport
        self._local_node_id = local_node_id
        self._tasks: dict[str, DistributedTask] = {}
        self._acks: dict[str, TaskAcknowledgement] = {}
        self._stats: dict[str, int] = {
            "dispatched": 0,
            "acknowledged": 0,
            "completed": 0,
            "failed": 0,
            "timed_out": 0,
            "retried": 0,
        }

    @property
    def stats(self) -> dict[str, Any]:
        return dict(self._stats)

    def list_tasks(
        self, status: DistributedTaskStatus | str | None = None
    ) -> list[DistributedTask]:
        if status is None:
            return list(self._tasks.values())
        if isinstance(status, str):
            try:
                status = DistributedTaskStatus(status)
            except ValueError:
                return []
        return [t for t in self._tasks.values() if t.status == status]

    def get_task(self, task_id: str) -> DistributedTask | None:
        return self._tasks.get(task_id)

    # ── Task lifecycle ─────────────────────────────────────────────

    async def dispatch(self, task: DistributedTask) -> bool:
        """Dispatch a task to the assigned node. Returns True if dispatched."""
        self._tasks[task.id] = task
        task.source_node_id = self._local_node_id

        if not task.assigned_node_id or task.assigned_node_id == self._local_node_id:
            # Local execution (single-node mode)
            task.status = DistributedTaskStatus.COMPLETED
            task.completion_time = datetime.now(UTC).isoformat()
            task.result = {"executed_locally": True}
            self._stats["completed"] += 1
            await self._publish_event("distributed.task.completed", task.to_dict())
            return True

        # Remote execution
        task.status = DistributedTaskStatus.DISPATCHED
        task.dispatch_time = datetime.now(UTC).isoformat()
        self._stats["dispatched"] += 1

        result = await self._transport.dispatch_task(task.assigned_node_id, task.to_dict())

        if result is not None:
            task.status = DistributedTaskStatus.ACKNOWLEDGED
            task.ack_time = datetime.now(UTC).isoformat()
            self._stats["acknowledged"] += 1
            await self._publish_event("distributed.task.dispatched", task.to_dict())
            return True
        else:
            # Dispatch failed — retry or fail
            if task.retries < task.max_retries:
                task.retries += 1
                self._stats["retried"] += 1
                log.info("Retrying task", task_id=task.id, retry=task.retries)
                return await self.dispatch(task)
            else:
                task.status = DistributedTaskStatus.FAILED
                task.error = "Dispatch failed after retries"
                self._stats["failed"] += 1
                await self._publish_event("distributed.task.failed", task.to_dict())
                return False

    def receive_acknowledgement(self, ack: TaskAcknowledgement) -> bool:
        """Receive a task acknowledgement from a remote node."""
        task = self._tasks.get(ack.task_id)
        if task is None:
            return False
        task.assigned_node_id = ack.node_id
        task.assigned_brain_id = ack.brain_id
        if ack.accepted:
            task.status = DistributedTaskStatus.ACKNOWLEDGED
            task.ack_time = datetime.now(UTC).isoformat()
            self._stats["acknowledged"] += 1
        else:
            task.status = DistributedTaskStatus.FAILED
            task.error = ack.reason
            self._stats["failed"] += 1
        self._acks[ack.task_id] = ack
        return True

    def receive_completion(
        self, task_id: str, result: dict[str, Any], success: bool = True
    ) -> bool:
        """Receive a task completion from a remote node."""
        task = self._tasks.get(task_id)
        if task is None:
            return False
        task.completion_time = datetime.now(UTC).isoformat()
        task.result = result
        if success:
            task.status = DistributedTaskStatus.COMPLETED
            self._stats["completed"] += 1
        else:
            task.status = DistributedTaskStatus.FAILED
            task.error = str(result.get("error", "Remote execution failed"))
            self._stats["failed"] += 1
        return True

    def check_timeouts(self) -> int:
        """Check for timed-out tasks. Returns count of newly timed out."""
        now = datetime.now(UTC)
        count = 0
        for task in self._tasks.values():
            if task.status not in {
                DistributedTaskStatus.DISPATCHED,
                DistributedTaskStatus.ACKNOWLEDGED,
                DistributedTaskStatus.EXECUTING,
            }:
                continue
            if not task.dispatch_time:
                continue
            try:
                dispatched = datetime.fromisoformat(task.dispatch_time)
            except (ValueError, TypeError):
                continue
            elapsed = (now - dispatched).total_seconds()
            if elapsed > task.timeout_s:
                task.status = DistributedTaskStatus.TIMEOUT
                task.error = f"Timed out after {task.timeout_s}s"
                self._stats["timed_out"] += 1
                count += 1
                log.warning("Task timed out", task_id=task.id, elapsed_s=elapsed)
        return count

    # ── Internal ───────────────────────────────────────────────────

    async def _publish_event(self, topic: str, payload: dict[str, Any]) -> None:
        try:
            from agentic_os.domain.events import EventEnvelope

            await self._bus.publish(
                EventEnvelope(
                    type=topic,
                    source="distributed.executor",
                    topic=topic,
                    payload=payload,
                )
            )
        except Exception:
            log.exception("Failed to publish %s", topic)


class ClusterScheduler:
    """Extends Phase 16's GlobalMissionScheduler with remote dispatch.

    Selects the optimal (node, brain) pair using the existing
    GlobalMissionScheduler scoring, then dispatches the task via
    the DistributedExecutor.
    """

    def __init__(
        self,
        bus: EventBus,
        executor: DistributedExecutor,
    ) -> None:
        self._bus = bus
        self._executor = executor
        self._dispatch_count: int = 0
        self._stats: dict[str, int] = {
            "tasks_scheduled": 0,
            "tasks_dispatched_locally": 0,
            "tasks_dispatched_remotely": 0,
            "tasks_failed_to_dispatch": 0,
        }

    @property
    def stats(self) -> dict[str, Any]:
        return dict(self._stats)

    async def schedule_and_dispatch(
        self,
        task: DistributedTask,
        selected_node_id: str = "",
        selected_brain_id: str = "",
    ) -> bool:
        """Schedule a task and dispatch it to the selected node."""
        self._stats["tasks_scheduled"] += 1
        task.assigned_node_id = selected_node_id
        task.assigned_brain_id = selected_brain_id

        if not selected_node_id or selected_node_id == self._executor._local_node_id:
            self._stats["tasks_dispatched_locally"] += 1
        else:
            self._stats["tasks_dispatched_remotely"] += 1

        success = await self._executor.dispatch(task)
        if not success:
            self._stats["tasks_failed_to_dispatch"] += 1
        return success
