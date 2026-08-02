"""Tests for OrchestrationFramework (Phase 4, M3)."""

import pytest

from agentic_os.core.orchestration.config import OrchestrationConfiguration
from agentic_os.core.orchestration.framework import OrchestrationFramework


class _MockBus:
    def __init__(self):
        self.events = []

    async def start(self):
        pass

    async def stop(self):
        pass

    async def publish(self, envelope):
        self.events.append(envelope)


class _MockRuntime:
    async def list_engines(self, capability=None, status=None):
        return []

    async def get_engine(self, engine_id):
        return None

    async def execute(self, engine_id, request):
        from agentic_os.ports.execution import ExecutionResult

        return ExecutionResult(status="completed", output={"done": True})

    async def list_capabilities(self):
        return {}

    async def find_engines(self, capability, min_confidence=0.0):
        return []

    async def execute_on_best(self, request, required_capability):
        from agentic_os.ports.execution import ExecutionResult

        return ExecutionResult(status="completed", output={"done": True})

    async def initialize(self):
        pass

    async def shutdown(self):
        pass


@pytest.fixture
def bus():
    return _MockBus()


@pytest.fixture
def runtime():
    return _MockRuntime()


@pytest.fixture
def config():
    return OrchestrationConfiguration(
        enabled=True,
        agent_sync_interval_seconds=0.1,  # fast for tests
        telemetry_max_entries=100,
    )


@pytest.fixture
def framework(bus, runtime, config):
    return OrchestrationFramework(
        bus=bus,
        runtime=runtime,
        config=config,
    )


class TestOrchestrationFramework:
    async def test_start_builds_subsystems(self, framework) -> None:
        assert framework.agent_registry is None
        assert framework.swarm_manager is None
        await framework.start()
        assert framework.agent_registry is not None
        assert framework.swarm_manager is not None
        assert framework.coordination_engine is not None
        assert framework.intelligence_engine is not None
        assert framework.communication_bus is not None
        assert framework.task_orchestrator is not None
        assert framework.publisher is not None
        assert framework.telemetry is not None
        await framework.stop()

    async def test_start_idempotent(self, framework) -> None:
        await framework.start()
        await framework.start()  # second start should be no-op
        await framework.stop()

    async def test_stop_cleans_up(self, framework) -> None:
        await framework.start()
        assert framework._running
        await framework.stop()
        assert not framework._running

    async def test_discover_agents_empty(self, framework) -> None:
        await framework.start()
        agents = await framework.discover_agents()
        assert agents == []
        await framework.stop()

    async def test_list_agents(self, framework) -> None:
        await framework.start()
        agents = await framework.list_agents()
        assert isinstance(agents, list)
        await framework.stop()

    async def test_get_agent_not_found(self, framework) -> None:
        await framework.start()
        agent = await framework.get_agent("nonexistent")
        assert agent is None
        await framework.stop()

    async def test_find_agents_by_capability(self, framework) -> None:
        await framework.start()
        agents = await framework.find_agents_by_capability("coding")
        assert agents == []
        await framework.stop()

    async def test_create_swarm(self, framework) -> None:
        await framework.start()
        spec = await framework.create_swarm(
            name="test-swarm",
            description="A test swarm",
            topology="mesh",
        )
        assert spec.name == "test-swarm"
        assert spec.id is not None
        await framework.stop()

    async def test_get_swarm(self, framework) -> None:
        await framework.start()
        spec = await framework.create_swarm(name="s1")
        result = await framework.get_swarm(spec.id)
        assert result is not None
        await framework.stop()

    async def test_get_swarm_not_found(self, framework) -> None:
        await framework.start()
        result = await framework.get_swarm("nonexistent")
        assert result is None
        await framework.stop()

    async def test_list_swarms(self, framework) -> None:
        await framework.start()
        await framework.create_swarm(name="s1")
        await framework.create_swarm(name="s2")
        swarms = await framework.list_swarms()
        assert len(swarms) == 2
        await framework.stop()

    async def test_delete_swarm(self, framework) -> None:
        await framework.start()
        spec = await framework.create_swarm(name="s1")
        result = await framework.delete_swarm(spec.id)
        assert result
        await framework.stop()

    async def test_delete_swarm_not_found(self, framework) -> None:
        await framework.start()
        result = await framework.delete_swarm("nonexistent")
        assert not result
        await framework.stop()

    async def test_add_agent_to_swarm(self, framework) -> None:
        await framework.start()
        spec = await framework.create_swarm(name="s1")
        result = await framework.add_agent_to_swarm(spec.id, "nonexistent")
        assert result is None  # agent doesn't exist
        await framework.stop()

    async def test_create_goal(self, framework) -> None:
        await framework.start()
        goal = await framework.create_goal(
            title="test-goal",
            description="do something",
            context={"key": "value"},
        )
        assert goal.title == "test-goal"
        assert goal.status == "pending"
        await framework.stop()

    async def test_get_goal(self, framework) -> None:
        await framework.start()
        goal = await framework.create_goal(title="g1")
        result = await framework.get_goal(goal.id)
        assert result is not None
        await framework.stop()

    async def test_list_goals(self, framework) -> None:
        await framework.start()
        await framework.create_goal(title="g1")
        await framework.create_goal(title="g2")
        goals = await framework.list_goals()
        assert len(goals) == 2
        await framework.stop()

    async def test_cancel_goal(self, framework) -> None:
        await framework.start()
        goal = await framework.create_goal(title="g1")
        result = await framework.cancel_goal(goal.id)
        assert result is not None
        await framework.stop()

    async def test_reach_consensus_empty_swarm(self, framework) -> None:
        await framework.start()
        result = await framework.reach_consensus(
            swarm_id="nonexistent",
            topic="test",
        )
        assert result is None
        await framework.stop()

    async def test_reach_consensus_no_quorum(self, framework) -> None:
        await framework.start()
        spec = await framework.create_swarm(name="s1")
        result = await framework.reach_consensus(
            swarm_id=spec.id,
            topic="test",
        )
        assert result is None  # no agents in swarm
        await framework.stop()

    async def test_cast_vote(self, framework) -> None:
        await framework.start()
        result = await framework.cast_vote(
            consensus_id="nonexistent",
            voter_id="a1",
            value="yes",
        )
        assert result is None  # consensus doesn't exist
        await framework.stop()

    async def test_cast_vote_invalid_value(self, framework) -> None:
        await framework.start()
        result = await framework.cast_vote(
            consensus_id="c1",
            voter_id="a1",
            value="invalid",
        )
        assert result is None
        await framework.stop()

    async def test_send_message(self, framework) -> None:
        await framework.start()
        result = await framework.send_message(
            source_agent_id="a1",
            target_agent_id="a2",
            swarm_id="s1",
            payload={"hello": "world"},
        )
        assert result is not None
        await framework.stop()

    async def test_broadcast_message(self, framework) -> None:
        await framework.start()
        result = await framework.broadcast_message(
            source_agent_id="a1",
            swarm_id="s1",
            payload={"alert": "test"},
        )
        assert result is not None
        await framework.stop()

    async def test_get_message_history(self, framework) -> None:
        await framework.start()
        history = await framework.get_message_history()
        assert history == []
        await framework.stop()

    async def test_get_stats(self, framework) -> None:
        await framework.start()
        stats = framework.get_stats()
        assert "total_entries" in stats
        await framework.stop()

    async def test_get_telemetry_entries(self, framework) -> None:
        await framework.start()
        entries = framework.get_telemetry_entries()
        assert entries == []
        await framework.stop()

    async def test_orchestrate_full_pipeline(self, framework) -> None:
        await framework.start()
        goal = await framework.create_goal(title="orchestrate-test")
        spec = await framework.create_swarm(name="orchestrate-swarm")
        plan = await framework.orchestrate(goal, spec.id)
        # Plan may complete with no agents in swarm — that's fine, no crash
        if plan is not None:
            assert plan.goal_id == goal.id
        await framework.stop()

    async def test_get_swarm_state_not_found(self, framework) -> None:
        await framework.start()
        state = await framework.get_swarm_state("nonexistent")
        assert state is None
        await framework.stop()

    async def test_elect_leader_not_found(self, framework) -> None:
        await framework.start()
        result = await framework.elect_leader("nonexistent")
        assert result is None
        await framework.stop()

    async def test_get_swarm_leader_not_found(self, framework) -> None:
        await framework.start()
        leader = await framework.get_swarm_leader("nonexistent")
        assert leader is None
        await framework.stop()

    async def test_get_plan_not_found(self, framework) -> None:
        await framework.start()
        plan = await framework.get_plan("nonexistent")
        assert plan is None
        await framework.stop()

    async def test_get_task_not_found(self, framework) -> None:
        await framework.start()
        task = await framework.get_task("nonexistent")
        assert task is None
        await framework.stop()
