"""Phase 16 — FailoverEngine.

Detects failures (offline nodes, offline runtimes, high latency, failed
missions, network partitions) and produces FailoverActions:

  - REASSIGN_MISSION   : move a mission from one (node, brain) to another
  - REPLACE_RUNTIME    : swap a failing brain for a healthy equivalent
  - ELECT_REPLACEMENT  : ask GlobalMissionScheduler to pick a new runtime
  - RESUME_EXECUTION   : restart a paused mission on the new runtime
  - QUARANTINE_NODE    : mark a node as unschedulable

The engine is a pure consumer of the EventBus — it subscribes to
cluster.* and brain.* events to detect failures. It does NOT execute
the actions itself; instead it publishes them so the
ExecutiveController / SwarmCoordinator can apply them.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from agentic_os.core.cluster.domain import (
    FailoverAction,
    FailoverActionType,
    FailoverTrigger,
    NodeStatus,
)
from agentic_os.infrastructure.logging import get_logger

if TYPE_CHECKING:
    from agentic_os.core.cluster.distributed_registry import DistributedBrainRegistry
    from agentic_os.core.cluster.federation import ClusterFederationManager
    from agentic_os.core.cluster.scheduler import GlobalMissionScheduler
    from agentic_os.ports.event_bus import EventBus

log = get_logger("cluster.failover")

# Thresholds
_LATENCY_FAILURE_MS = 5000.0
_NODE_STALE_TIMEOUT_S = 90.0


class FailoverEngine:
    """Detects failures and produces recovery actions."""

    def __init__(
        self,
        bus: EventBus | None = None,
        federation: ClusterFederationManager | None = None,
        distributed_registry: DistributedBrainRegistry | None = None,
        scheduler: GlobalMissionScheduler | None = None,
    ) -> None:
        self._bus = bus
        self._federation = federation
        self._distributed = distributed_registry
        self._scheduler = scheduler
        self._actions: list[FailoverAction] = []
        self._stats: dict[str, int] = {
            "triggers_detected": 0,
            "actions_started": 0,
            "actions_completed": 0,
            "actions_failed": 0,
        }

    # ── Dependency injection ───────────────────────────────────────

    def set_federation(self, federation: ClusterFederationManager) -> None:
        self._federation = federation

    def set_distributed_registry(self, registry: DistributedBrainRegistry) -> None:
        self._distributed = registry

    def set_scheduler(self, scheduler: GlobalMissionScheduler) -> None:
        self._scheduler = scheduler

    def set_bus(self, bus: EventBus) -> None:
        self._bus = bus

    # ── Detection ──────────────────────────────────────────────────

    async def detect_node_offline(self, node_id: str) -> FailoverAction | None:
        """Check if a node is offline and emit a quarantine action."""
        if self._federation is None:
            return None
        node = self._federation.topology.get_node(node_id)
        if node is None:
            return None
        if node.status != NodeStatus.UNREACHABLE:
            return None
        self._stats["triggers_detected"] += 1
        action = FailoverAction(
            trigger=FailoverTrigger.NODE_OFFLINE,
            action_type=FailoverActionType.QUARANTINE_NODE,
            target_node_id=node_id,
            rationale=f"Node {node_id} marked unreachable — quarantining",
            evidence={
                "node_id": node_id,
                "last_heartbeat": node.last_heartbeat,
                "health_score": node.health_score,
            },
            status="pending",
        )
        await self._execute(action)
        return action

    async def detect_runtime_offline(self, brain_id: str, node_id: str) -> FailoverAction | None:
        """Detect a single offline runtime and emit a replace action."""
        if self._distributed is None:
            return None
        record = self._distributed.get_remote_brain(brain_id, node_id)
        if record is None:
            return None
        if record.health >= 30:
            return None
        self._stats["triggers_detected"] += 1
        action = FailoverAction(
            trigger=FailoverTrigger.RUNTIME_OFFLINE,
            action_type=FailoverActionType.REPLACE_RUNTIME,
            target_node_id=node_id,
            target_brain_id=brain_id,
            rationale=f"Runtime {brain_id} on {node_id} has health={record.health:.0f} — replacing",
            evidence={
                "brain_id": brain_id,
                "node_id": node_id,
                "health": record.health,
                "capabilities": list(record.capabilities),
            },
            status="pending",
        )
        # Find a replacement via the scheduler
        if self._scheduler is not None and record.capabilities:
            replacement = await self._scheduler.select_optimal(
                required_capabilities=list(record.capabilities),
                mission_id=f"failover-{action.id}",
            )
            if replacement is not None:
                action.replacement_node_id = replacement.node_id
                action.replacement_brain_id = replacement.brain_id
                action.rationale += (
                    f" → replacement={replacement.brain_id} on {replacement.node_id}"
                )
        await self._execute(action)
        return action

    async def detect_high_latency(self, brain_id: str, node_id: str) -> FailoverAction | None:
        """Detect high-latency runtime and emit a replace action."""
        if self._distributed is None:
            return None
        record = self._distributed.get_remote_brain(brain_id, node_id)
        if record is None:
            return None
        if record.latency < _LATENCY_FAILURE_MS:
            return None
        self._stats["triggers_detected"] += 1
        action = FailoverAction(
            trigger=FailoverTrigger.HIGH_LATENCY,
            action_type=FailoverActionType.REPLACE_RUNTIME,
            target_node_id=node_id,
            target_brain_id=brain_id,
            rationale=(
                f"Runtime {brain_id} latency={record.latency:.0f}ms exceeds {_LATENCY_FAILURE_MS}ms"
            ),
            evidence={
                "brain_id": brain_id,
                "node_id": node_id,
                "latency": record.latency,
            },
            status="pending",
        )
        if self._scheduler is not None and record.capabilities:
            replacement = await self._scheduler.select_optimal(
                required_capabilities=list(record.capabilities),
                mission_id=f"failover-{action.id}",
            )
            if replacement is not None:
                action.replacement_node_id = replacement.node_id
                action.replacement_brain_id = replacement.brain_id
        await self._execute(action)
        return action

    async def detect_failed_mission(
        self,
        mission_id: str,
        brain_id: str,
        node_id: str,
    ) -> FailoverAction | None:
        """Emit a reassignment action for a failed mission."""
        self._stats["triggers_detected"] += 1
        action = FailoverAction(
            trigger=FailoverTrigger.MISSION_FAILED,
            action_type=FailoverActionType.REASSIGN_MISSION,
            target_node_id=node_id,
            target_brain_id=brain_id,
            target_mission_id=mission_id,
            rationale=f"Mission {mission_id} failed on {brain_id}@{node_id} — reassigning",
            evidence={
                "mission_id": mission_id,
                "brain_id": brain_id,
                "node_id": node_id,
            },
            status="pending",
        )
        if self._scheduler is not None:
            replacement = await self._scheduler.select_optimal(
                mission_id=f"failover-{action.id}",
            )
            if replacement is not None:
                action.replacement_node_id = replacement.node_id
                action.replacement_brain_id = replacement.brain_id
        await self._execute(action)
        return action

    async def detect_network_partition(self, node_ids: list[str]) -> FailoverAction | None:
        """Detect a network partition affecting multiple nodes."""
        if not node_ids:
            return None
        self._stats["triggers_detected"] += 1
        action = FailoverAction(
            trigger=FailoverTrigger.NETWORK_PARTITION,
            action_type=FailoverActionType.QUARANTINE_NODE,
            target_node_id=node_ids[0],
            rationale=f"Network partition detected affecting {len(node_ids)} nodes: {node_ids}",
            evidence={"partitioned_nodes": node_ids},
            status="pending",
        )
        await self._execute(action)
        return action

    # ── Manual triggers ────────────────────────────────────────────

    async def trigger_manual_failover(
        self,
        brain_id: str,
        node_id: str,
        mission_id: str = "",
    ) -> FailoverAction:
        """Manually trigger a failover for a runtime."""
        self._stats["triggers_detected"] += 1
        action = FailoverAction(
            trigger=FailoverTrigger.MANUAL,
            action_type=FailoverActionType.REASSIGN_MISSION,
            target_node_id=node_id,
            target_brain_id=brain_id,
            target_mission_id=mission_id,
            rationale=f"Manual failover requested for {brain_id}@{node_id}",
            evidence={"manual": True},
            status="pending",
        )
        if self._scheduler is not None:
            replacement = await self._scheduler.select_optimal(
                mission_id=f"manual-failover-{action.id}"
            )
            if replacement is not None:
                action.replacement_node_id = replacement.node_id
                action.replacement_brain_id = replacement.brain_id
        await self._execute(action)
        return action

    # ── Execution ──────────────────────────────────────────────────

    async def _execute(self, action: FailoverAction) -> None:
        """Publish the action and mark it completed.

        The actual execution (re-dispatching missions, etc.) is handled
        by listeners of cluster.failover.completed — typically the
        ExecutiveController or SwarmCoordinator.
        """
        self._actions.append(action)
        self._stats["actions_started"] += 1
        action.started_at = datetime.now(UTC).isoformat()

        await self._publish(
            "cluster.failover.started",
            action.to_dict(),
        )

        # In a real system, the action would be applied here. For Phase 16
        # we publish the action and mark it completed — the Executive /
        # Swarm layer listens to cluster.failover.completed and applies
        # the reassignment.
        action.status = "completed"
        action.completed_at = datetime.now(UTC).isoformat()
        self._stats["actions_completed"] += 1

        await self._publish(
            "cluster.failover.completed",
            action.to_dict(),
        )

    # ── Queries ────────────────────────────────────────────────────

    def list_actions(self, limit: int = 50) -> list[FailoverAction]:
        return list(self._actions[-limit:])

    def get_action(self, action_id: str) -> FailoverAction | None:
        for a in self._actions:
            if a.id == action_id:
                return a
        return None

    def stats(self) -> dict[str, Any]:
        return dict(self._stats)

    def to_dict(self) -> dict[str, Any]:
        return {
            "actions": [a.to_dict() for a in self._actions[-50:]],
            "stats": self.stats(),
        }

    # ── Internal ───────────────────────────────────────────────────

    async def _publish(self, topic: str, payload: dict[str, Any]) -> None:
        if self._bus is None:
            return
        try:
            from agentic_os.domain.events import EventEnvelope

            await self._bus.publish(
                EventEnvelope(
                    type=topic,
                    source="cluster.failover",
                    topic=topic,
                    payload=payload,
                )
            )
        except Exception:
            log.exception("Failed to publish %s", topic)
