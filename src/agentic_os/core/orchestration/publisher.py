"""Orchestration event publisher — emits orchestration lifecycle events through EventBus.

Follows the same pattern as ``DiscoveryEventPublisher``: each event has a
dedicated method that constructs an ``EventEnvelope`` and publishes it
through the injected ``EventBus``.
"""

from dataclasses import dataclass
from typing import Any

from agentic_os.domain.events import EventEnvelope, Topic
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.event_bus import EventBus

log = get_logger("orchestration.publisher")


@dataclass
class OrchestrationEventPublisher:
    """Publishes orchestration lifecycle events through the injected EventBus.

    Each method emits an indexed envelope with structured payload so consumers
    (Mission Control, telemetry, logging) can react to orchestration state
    changes.
    """

    bus: EventBus

    # ── Swarm Lifecycle ──

    async def swarm_created(self, swarm_id: str, name: str) -> None:
        await self._publish(
            Topic.ORCH_SWARM_CREATED,
            {"swarm_id": swarm_id, "name": name},
        )

    async def swarm_deleted(self, swarm_id: str) -> None:
        await self._publish(
            Topic.ORCH_SWARM_DELETED,
            {"swarm_id": swarm_id},
        )

    async def swarm_updated(self, swarm_id: str, name: str) -> None:
        await self._publish(
            Topic.ORCH_SWARM_UPDATED,
            {"swarm_id": swarm_id, "name": name},
        )

    async def swarm_activated(self, swarm_id: str) -> None:
        await self._publish(
            Topic.ORCH_SWARM_ACTIVATED,
            {"swarm_id": swarm_id},
        )

    async def swarm_deactivated(self, swarm_id: str) -> None:
        await self._publish(
            Topic.ORCH_SWARM_DEACTIVATED,
            {"swarm_id": swarm_id},
        )

    async def agent_joined(self, swarm_id: str, agent_id: str) -> None:
        await self._publish(
            Topic.ORCH_AGENT_JOINED,
            {"swarm_id": swarm_id, "agent_id": agent_id},
        )

    async def agent_left(self, swarm_id: str, agent_id: str) -> None:
        await self._publish(
            Topic.ORCH_AGENT_LEFT,
            {"swarm_id": swarm_id, "agent_id": agent_id},
        )

    # ── Task Orchestration ──

    async def task_created(self, task_id: str, goal_id: str, title: str) -> None:
        await self._publish(
            Topic.ORCH_TASK_CREATED,
            {"task_id": task_id, "goal_id": goal_id, "title": title},
        )

    async def task_decomposed(self, goal_id: str, subtask_count: int) -> None:
        await self._publish(
            Topic.ORCH_TASK_DECOMPOSED,
            {"goal_id": goal_id, "subtask_count": subtask_count},
        )

    async def task_assigned(self, task_id: str, agent_id: str) -> None:
        await self._publish(
            Topic.ORCH_TASK_ASSIGNED,
            {"task_id": task_id, "agent_id": agent_id},
        )

    async def task_started(self, task_id: str, agent_id: str) -> None:
        await self._publish(
            Topic.ORCH_TASK_STARTED,
            {"task_id": task_id, "agent_id": agent_id},
        )

    async def task_completed(self, task_id: str, agent_id: str) -> None:
        await self._publish(
            Topic.ORCH_TASK_COMPLETED,
            {"task_id": task_id, "agent_id": agent_id},
        )

    async def task_failed(self, task_id: str, agent_id: str, error: str) -> None:
        await self._publish(
            Topic.ORCH_TASK_FAILED,
            {"task_id": task_id, "agent_id": agent_id, "error": error},
        )

    async def task_cancelled(self, task_id: str) -> None:
        await self._publish(
            Topic.ORCH_TASK_CANCELLED,
            {"task_id": task_id},
        )

    async def plan_created(self, plan_id: str, goal_id: str, subtask_count: int) -> None:
        await self._publish(
            Topic.ORCH_PLAN_CREATED,
            {"plan_id": plan_id, "goal_id": goal_id, "subtask_count": subtask_count},
        )

    async def plan_completed(self, plan_id: str, status: str) -> None:
        await self._publish(
            Topic.ORCH_PLAN_COMPLETED,
            {"plan_id": plan_id, "status": status},
        )

    # ── Coordination Patterns ──

    async def coord_sequential_started(self, swarm_id: str, task_count: int) -> None:
        await self._publish(
            Topic.ORCH_COORD_SEQUENTIAL_STARTED,
            {"swarm_id": swarm_id, "task_count": task_count},
        )

    async def coord_sequential_completed(self, swarm_id: str, completed: int) -> None:
        await self._publish(
            Topic.ORCH_COORD_SEQUENTIAL_COMPLETED,
            {"swarm_id": swarm_id, "completed": completed},
        )

    async def coord_parallel_started(self, swarm_id: str, task_count: int) -> None:
        await self._publish(
            Topic.ORCH_COORD_PARALLEL_STARTED,
            {"swarm_id": swarm_id, "task_count": task_count},
        )

    async def coord_parallel_completed(self, swarm_id: str, completed: int) -> None:
        await self._publish(
            Topic.ORCH_COORD_PARALLEL_COMPLETED,
            {"swarm_id": swarm_id, "completed": completed},
        )

    async def coord_fan_out_started(self, swarm_id: str, agent_count: int) -> None:
        await self._publish(
            Topic.ORCH_COORD_FAN_OUT_STARTED,
            {"swarm_id": swarm_id, "agent_count": agent_count},
        )

    async def coord_fan_out_completed(self, swarm_id: str, agent_count: int) -> None:
        await self._publish(
            Topic.ORCH_COORD_FAN_OUT_COMPLETED,
            {"swarm_id": swarm_id, "agent_count": agent_count},
        )

    async def coord_fan_in_started(self, swarm_id: str, agent_count: int) -> None:
        await self._publish(
            Topic.ORCH_COORD_FAN_IN_STARTED,
            {"swarm_id": swarm_id, "agent_count": agent_count},
        )

    async def coord_fan_in_completed(self, swarm_id: str, agent_count: int) -> None:
        await self._publish(
            Topic.ORCH_COORD_FAN_IN_COMPLETED,
            {"swarm_id": swarm_id, "agent_count": agent_count},
        )

    async def coord_hierarchical_started(self, swarm_id: str, task_count: int) -> None:
        await self._publish(
            Topic.ORCH_COORD_HIERARCHICAL_STARTED,
            {"swarm_id": swarm_id, "task_count": task_count},
        )

    async def coord_hierarchical_completed(self, swarm_id: str, completed: int) -> None:
        await self._publish(
            Topic.ORCH_COORD_HIERARCHICAL_COMPLETED,
            {"swarm_id": swarm_id, "completed": completed},
        )

    async def coord_voting_started(self, swarm_id: str, voter_count: int) -> None:
        await self._publish(
            Topic.ORCH_COORD_VOTING_STARTED,
            {"swarm_id": swarm_id, "voter_count": voter_count},
        )

    async def coord_voting_completed(self, swarm_id: str, outcome: bool) -> None:
        await self._publish(
            Topic.ORCH_COORD_VOTING_COMPLETED,
            {"swarm_id": swarm_id, "outcome": outcome},
        )

    # ── Swarm Intelligence ──

    async def consensus_started(
        self, consensus_id: str, swarm_id: str, topic: str, agent_count: int
    ) -> None:
        await self._publish(
            Topic.ORCH_CONSENSUS_STARTED,
            {
                "consensus_id": consensus_id,
                "swarm_id": swarm_id,
                "topic": topic,
                "agent_count": agent_count,
            },
        )

    async def consensus_reached(self, consensus_id: str, outcome: bool) -> None:
        await self._publish(
            Topic.ORCH_CONSENSUS_REACHED,
            {"consensus_id": consensus_id, "outcome": outcome},
        )

    async def consensus_failed(self, consensus_id: str) -> None:
        await self._publish(
            Topic.ORCH_CONSENSUS_FAILED,
            {"consensus_id": consensus_id},
        )

    async def vote_cast(
        self, consensus_id: str, voter_id: str, vote_value: str, weight: float
    ) -> None:
        await self._publish(
            Topic.ORCH_VOTE_CAST,
            {
                "consensus_id": consensus_id,
                "voter_id": voter_id,
                "vote_value": vote_value,
                "weight": weight,
            },
        )

    async def leader_election_started(self, swarm_id: str, candidate_count: int) -> None:
        await self._publish(
            Topic.ORCH_LEADER_ELECTION_STARTED,
            {"swarm_id": swarm_id, "candidate_count": candidate_count},
        )

    async def leader_elected(self, swarm_id: str, leader_id: str, score: float) -> None:
        await self._publish(
            Topic.ORCH_LEADER_ELECTED,
            {"swarm_id": swarm_id, "leader_id": leader_id, "score": score},
        )

    # ── Communication ──

    async def msg_sent(
        self, message_id: str, source: str, target: str | None, swarm_id: str
    ) -> None:
        await self._publish(
            Topic.ORCH_MSG_SENT,
            {
                "message_id": message_id,
                "source_agent_id": source,
                "target_agent_id": target,
                "swarm_id": swarm_id,
            },
        )

    async def msg_received(self, message_id: str, target: str) -> None:
        await self._publish(
            Topic.ORCH_MSG_RECEIVED,
            {"message_id": message_id, "target_agent_id": target},
        )

    async def msg_broadcast(self, message_id: str, source: str, swarm_id: str) -> None:
        await self._publish(
            Topic.ORCH_MSG_BROADCAST,
            {
                "message_id": message_id,
                "source_agent_id": source,
                "swarm_id": swarm_id,
            },
        )

    # ── Internal ──

    async def _publish(self, topic: Topic, payload: dict[str, Any]) -> None:
        """Low-level publish helper with error handling."""
        try:
            await self.bus.publish(
                EventEnvelope(
                    type="event",
                    source="orchestration-publisher",
                    topic=topic.value,
                    payload=payload,
                )
            )
        except Exception as exc:
            log.warning(
                "Failed to publish orchestration event",
                topic=topic.value,
                error=str(exc),
            )
