"""Tests for OrchestrationEventPublisher (Phase 4, M3)."""

import pytest

from agentic_os.core.orchestration.publisher import OrchestrationEventPublisher
from agentic_os.domain.events import Topic


class _MockBus:
    def __init__(self):
        self.events = []

    async def publish(self, envelope):
        self.events.append(envelope)


@pytest.fixture
def bus():
    return _MockBus()


@pytest.fixture
def publisher(bus):
    return OrchestrationEventPublisher(bus=bus)


class TestOrchestrationEventPublisher:
    async def test_swarm_created(self, publisher, bus) -> None:
        await publisher.swarm_created("s1", "test-swarm")
        assert bus.events[-1].topic == Topic.ORCH_SWARM_CREATED.value

    async def test_swarm_deleted(self, publisher, bus) -> None:
        await publisher.swarm_deleted("s1")
        assert bus.events[-1].topic == Topic.ORCH_SWARM_DELETED.value

    async def test_swarm_updated(self, publisher, bus) -> None:
        await publisher.swarm_updated("s1", "updated")
        assert bus.events[-1].topic == Topic.ORCH_SWARM_UPDATED.value

    async def test_swarm_activated(self, publisher, bus) -> None:
        await publisher.swarm_activated("s1")
        assert bus.events[-1].topic == Topic.ORCH_SWARM_ACTIVATED.value

    async def test_swarm_deactivated(self, publisher, bus) -> None:
        await publisher.swarm_deactivated("s1")
        assert bus.events[-1].topic == Topic.ORCH_SWARM_DEACTIVATED.value

    async def test_agent_joined(self, publisher, bus) -> None:
        await publisher.agent_joined("s1", "a1")
        assert bus.events[-1].topic == Topic.ORCH_AGENT_JOINED.value

    async def test_agent_left(self, publisher, bus) -> None:
        await publisher.agent_left("s1", "a1")
        assert bus.events[-1].topic == Topic.ORCH_AGENT_LEFT.value

    async def test_task_created(self, publisher, bus) -> None:
        await publisher.task_created("t1", "g1", "test")
        assert bus.events[-1].topic == Topic.ORCH_TASK_CREATED.value

    async def test_task_decomposed(self, publisher, bus) -> None:
        await publisher.task_decomposed("g1", 3)
        assert bus.events[-1].topic == Topic.ORCH_TASK_DECOMPOSED.value

    async def test_task_assigned(self, publisher, bus) -> None:
        await publisher.task_assigned("t1", "a1")
        assert bus.events[-1].topic == Topic.ORCH_TASK_ASSIGNED.value

    async def test_task_started(self, publisher, bus) -> None:
        await publisher.task_started("t1", "a1")
        assert bus.events[-1].topic == Topic.ORCH_TASK_STARTED.value

    async def test_task_completed(self, publisher, bus) -> None:
        await publisher.task_completed("t1", "a1")
        assert bus.events[-1].topic == Topic.ORCH_TASK_COMPLETED.value

    async def test_task_failed(self, publisher, bus) -> None:
        await publisher.task_failed("t1", "a1", "error")
        assert bus.events[-1].topic == Topic.ORCH_TASK_FAILED.value

    async def test_task_cancelled(self, publisher, bus) -> None:
        await publisher.task_cancelled("t1")
        assert bus.events[-1].topic == Topic.ORCH_TASK_CANCELLED.value

    async def test_plan_created(self, publisher, bus) -> None:
        await publisher.plan_created("p1", "g1", 5)
        assert bus.events[-1].topic == Topic.ORCH_PLAN_CREATED.value

    async def test_plan_completed(self, publisher, bus) -> None:
        await publisher.plan_completed("p1", "completed")
        assert bus.events[-1].topic == Topic.ORCH_PLAN_COMPLETED.value

    async def test_coord_sequential(self, publisher, bus) -> None:
        await publisher.coord_sequential_started("s1", 3)
        assert bus.events[-1].topic == Topic.ORCH_COORD_SEQUENTIAL_STARTED.value
        await publisher.coord_sequential_completed("s1", 3)
        assert bus.events[-1].topic == Topic.ORCH_COORD_SEQUENTIAL_COMPLETED.value

    async def test_coord_parallel(self, publisher, bus) -> None:
        await publisher.coord_parallel_started("s1", 5)
        assert bus.events[-1].topic == Topic.ORCH_COORD_PARALLEL_STARTED.value
        await publisher.coord_parallel_completed("s1", 5)
        assert bus.events[-1].topic == Topic.ORCH_COORD_PARALLEL_COMPLETED.value

    async def test_coord_fan_out(self, publisher, bus) -> None:
        await publisher.coord_fan_out_started("s1", 3)
        assert bus.events[-1].topic == Topic.ORCH_COORD_FAN_OUT_STARTED.value
        await publisher.coord_fan_out_completed("s1", 3)
        assert bus.events[-1].topic == Topic.ORCH_COORD_FAN_OUT_COMPLETED.value

    async def test_coord_fan_in(self, publisher, bus) -> None:
        await publisher.coord_fan_in_started("s1", 3)
        assert bus.events[-1].topic == Topic.ORCH_COORD_FAN_IN_STARTED.value
        await publisher.coord_fan_in_completed("s1", 3)
        assert bus.events[-1].topic == Topic.ORCH_COORD_FAN_IN_COMPLETED.value

    async def test_coord_hierarchical(self, publisher, bus) -> None:
        await publisher.coord_hierarchical_started("s1", 3)
        assert bus.events[-1].topic == Topic.ORCH_COORD_HIERARCHICAL_STARTED.value
        await publisher.coord_hierarchical_completed("s1", 3)
        assert bus.events[-1].topic == Topic.ORCH_COORD_HIERARCHICAL_COMPLETED.value

    async def test_coord_voting(self, publisher, bus) -> None:
        await publisher.coord_voting_started("s1", 5)
        assert bus.events[-1].topic == Topic.ORCH_COORD_VOTING_STARTED.value
        await publisher.coord_voting_completed("s1", True)
        assert bus.events[-1].topic == Topic.ORCH_COORD_VOTING_COMPLETED.value

    async def test_consensus_started(self, publisher, bus) -> None:
        await publisher.consensus_started("c1", "s1", "t1", 3)
        assert bus.events[-1].topic == Topic.ORCH_CONSENSUS_STARTED.value

    async def test_consensus_reached(self, publisher, bus) -> None:
        await publisher.consensus_reached("c1", True)
        assert bus.events[-1].topic == Topic.ORCH_CONSENSUS_REACHED.value

    async def test_consensus_failed(self, publisher, bus) -> None:
        await publisher.consensus_failed("c1")
        assert bus.events[-1].topic == Topic.ORCH_CONSENSUS_FAILED.value

    async def test_vote_cast(self, publisher, bus) -> None:
        await publisher.vote_cast("c1", "a1", "yes", 1.0)
        assert bus.events[-1].topic == Topic.ORCH_VOTE_CAST.value

    async def test_leader_election(self, publisher, bus) -> None:
        await publisher.leader_election_started("s1", 3)
        assert bus.events[-1].topic == Topic.ORCH_LEADER_ELECTION_STARTED.value
        await publisher.leader_elected("s1", "a1", 95.0)
        assert bus.events[-1].topic == Topic.ORCH_LEADER_ELECTED.value

    async def test_msg_sent(self, publisher, bus) -> None:
        await publisher.msg_sent("m1", "a1", "a2", "s1")
        assert bus.events[-1].topic == Topic.ORCH_MSG_SENT.value

    async def test_msg_received(self, publisher, bus) -> None:
        await publisher.msg_received("m1", "a2")
        assert bus.events[-1].topic == Topic.ORCH_MSG_RECEIVED.value

    async def test_msg_broadcast(self, publisher, bus) -> None:
        await publisher.msg_broadcast("m1", "a1", "s1")
        assert bus.events[-1].topic == Topic.ORCH_MSG_BROADCAST.value

    async def test_bus_error_does_not_raise(self, publisher) -> None:
        broken_bus = _BrokenBus()
        p = OrchestrationEventPublisher(bus=broken_bus)
        await p.swarm_created("s1", "test")  # should not raise

    async def test_all_swarm_lifecycle_events(self, publisher, bus) -> None:
        await publisher.swarm_created("s1", "s1")
        await publisher.swarm_updated("s1", "s1")
        await publisher.swarm_activated("s1")
        await publisher.swarm_deactivated("s1")
        await publisher.swarm_deleted("s1")
        topics = [e.topic for e in bus.events]
        assert Topic.ORCH_SWARM_CREATED.value in topics
        assert Topic.ORCH_SWARM_UPDATED.value in topics
        assert Topic.ORCH_SWARM_ACTIVATED.value in topics
        assert Topic.ORCH_SWARM_DEACTIVATED.value in topics
        assert Topic.ORCH_SWARM_DELETED.value in topics


class _BrokenBus:
    async def publish(self, envelope):
        raise RuntimeError("Bus unavailable")
