"""Tests for SwarmManager (Phase 4, M3)."""

import pytest

from agentic_os.core.orchestration.swarm import SwarmManager
from agentic_os.domain.events import Topic
from agentic_os.domain.orchestration import (
    AgentDescriptor,
    SwarmSpec,
    SwarmTopology,
)


class _MockBus:
    """Minimal EventBus mock for testing."""

    def __init__(self):
        self.events = []

    async def publish(self, envelope):
        self.events.append(envelope)


class _MockAgentRegistry:
    """Mock agent registry for swarming tests."""

    def __init__(self):
        self._agents = {
            "a1": AgentDescriptor(
                agent_id="a1",
                name="Agent-1",
                engine_type="generic",
                capabilities=("code",),
                latency_ms=10.0,
                health_status="healthy",
            ),
            "a2": AgentDescriptor(
                agent_id="a2",
                name="Agent-2",
                engine_type="generic",
                capabilities=("research",),
                latency_ms=20.0,
                health_status="healthy",
            ),
            "a3": AgentDescriptor(
                agent_id="a3",
                name="Agent-3",
                engine_type="generic",
                capabilities=("code", "research"),
                latency_ms=5.0,
                health_status="healthy",
            ),
        }

    async def get_agent(self, agent_id):
        return self._agents.get(agent_id)

    async def list_agents(self):
        return list(self._agents.values())


class _MockIntelligence:
    """Mock intelligence engine."""

    async def elect_leader(self, swarm_id, agents):
        if not agents:
            from agentic_os.domain.orchestration import LeaderElectionResult

            return LeaderElectionResult(swarm_id=swarm_id)
        winner = max(agents, key=lambda a: (len(a.capabilities), -a.latency_ms))
        from agentic_os.domain.orchestration import LeaderElectionResult

        return LeaderElectionResult(
            swarm_id=swarm_id,
            elected_leader_id=winner.agent_id,
            candidates=tuple(a.agent_id for a in agents),
            vote_counts={a.agent_id: len(a.capabilities) for a in agents},
            total_votes=sum(len(a.capabilities) for a in agents),
        )


@pytest.fixture
def bus():
    return _MockBus()


@pytest.fixture
def agent_registry():
    return _MockAgentRegistry()


@pytest.fixture
def intelligence():
    return _MockIntelligence()


@pytest.fixture
def manager(bus, agent_registry, intelligence):
    return SwarmManager(
        bus=bus,
        agent_registry=agent_registry,
        intelligence=intelligence,
    )


class TestSwarmManager:
    async def test_create_swarm_basic(self, manager, bus) -> None:
        spec = SwarmSpec(name="test-swarm")
        result = await manager.create_swarm(spec)
        assert result.name == "test-swarm"
        assert result.topology == SwarmTopology.MESH
        assert result.id is not None

    async def test_create_swarm_with_agents(self, manager) -> None:
        spec = SwarmSpec(name="s1", agent_ids=("a1", "a2"))
        result = await manager.create_swarm(spec)
        assert result.agent_ids == ("a1", "a2")

    async def test_create_swarm_invalid_agent(self, manager) -> None:
        spec = SwarmSpec(name="s1", agent_ids=("nonexistent",))
        with pytest.raises(ValueError, match="not found"):
            await manager.create_swarm(spec)

    async def test_create_swarm_star_too_few(self, manager) -> None:
        spec = SwarmSpec(name="s1", topology=SwarmTopology.STAR, agent_ids=("a1",))
        with pytest.raises(ValueError, match="at least 3"):
            await manager.create_swarm(spec)

    async def test_create_swarm_ring_too_few(self, manager) -> None:
        spec = SwarmSpec(name="s1", topology=SwarmTopology.RING, agent_ids=("a1",))
        with pytest.raises(ValueError, match="at least 2"):
            await manager.create_swarm(spec)

    async def test_get_swarm(self, manager) -> None:
        spec = SwarmSpec(name="s1")
        await manager.create_swarm(spec)
        result = await manager.get_swarm(spec.id)
        assert result is not None
        assert result.name == "s1"

    async def test_get_swarm_not_found(self, manager) -> None:
        result = await manager.get_swarm("nonexistent")
        assert result is None

    async def test_list_swarms_empty(self, manager) -> None:
        swarms = await manager.list_swarms()
        assert swarms == []

    async def test_list_swarms_populated(self, manager) -> None:
        await manager.create_swarm(SwarmSpec(name="s1"))
        await manager.create_swarm(SwarmSpec(name="s2"))
        swarms = await manager.list_swarms()
        assert len(swarms) == 2

    async def test_update_swarm(self, manager) -> None:
        spec = SwarmSpec(name="s1")
        await manager.create_swarm(spec)
        updated = SwarmSpec(id=spec.id, name="s1-updated")
        result = await manager.update_swarm(spec.id, updated)
        assert result is not None
        assert result.name == "s1-updated"

    async def test_update_swarm_not_found(self, manager) -> None:
        result = await manager.update_swarm("nonexistent", SwarmSpec(name="x"))
        assert result is None

    async def test_delete_swarm(self, manager) -> None:
        spec = SwarmSpec(name="s1")
        await manager.create_swarm(spec)
        result = await manager.delete_swarm(spec.id)
        assert result
        assert await manager.get_swarm(spec.id) is None

    async def test_delete_swarm_not_found(self, manager) -> None:
        result = await manager.delete_swarm("nonexistent")
        assert not result

    async def test_add_agent_to_swarm(self, manager) -> None:
        spec = SwarmSpec(name="s1")
        await manager.create_swarm(spec)
        result = await manager.add_agent_to_swarm(spec.id, "a1")
        assert result is not None
        assert "a1" in result.agent_ids

    async def test_add_agent_to_swarm_not_found(self, manager) -> None:
        result = await manager.add_agent_to_swarm("nonexistent", "a1")
        assert result is None

    async def test_add_agent_to_swarm_invalid_agent(self, manager) -> None:
        spec = SwarmSpec(name="s1")
        await manager.create_swarm(spec)
        with pytest.raises(ValueError, match="not found"):
            await manager.add_agent_to_swarm(spec.id, "nonexistent")

    async def test_remove_agent_from_swarm(self, manager) -> None:
        spec = SwarmSpec(name="s1", agent_ids=("a1", "a2"))
        await manager.create_swarm(spec)
        result = await manager.remove_agent_from_swarm(spec.id, "a1")
        assert result is not None
        assert "a1" not in result.agent_ids

    async def test_remove_agent_not_in_swarm(self, manager) -> None:
        spec = SwarmSpec(name="s1")
        await manager.create_swarm(spec)
        result = await manager.remove_agent_from_swarm(spec.id, "nonexistent")
        assert result is not None  # no-op, still returns spec

    async def test_get_agents_in_swarm(self, manager, agent_registry) -> None:
        spec = SwarmSpec(name="s1", agent_ids=("a1", "a2"))
        await manager.create_swarm(spec)
        agents = await manager.get_agents_in_swarm(spec.id)
        assert len(agents) == 2

    async def test_get_agents_in_swarm_empty(self, manager) -> None:
        spec = SwarmSpec(name="s1")
        await manager.create_swarm(spec)
        agents = await manager.get_agents_in_swarm(spec.id)
        assert agents == []

    async def test_get_agents_in_swarm_not_found(self, manager) -> None:
        agents = await manager.get_agents_in_swarm("nonexistent")
        assert agents == []

    async def test_activate_swarm(self, manager) -> None:
        spec = SwarmSpec(name="s1")
        await manager.create_swarm(spec)
        result = await manager.activate_swarm(spec.id)
        assert result
        state = await manager.get_swarm_state(spec.id)
        assert state is not None
        assert state.active

    async def test_activate_swarm_not_found(self, manager) -> None:
        result = await manager.activate_swarm("nonexistent")
        assert not result

    async def test_deactivate_swarm(self, manager) -> None:
        spec = SwarmSpec(name="s1")
        await manager.create_swarm(spec)
        await manager.activate_swarm(spec.id)
        result = await manager.deactivate_swarm(spec.id)
        assert result
        state = await manager.get_swarm_state(spec.id)
        assert not state.active

    async def test_deactivate_swarm_not_found(self, manager) -> None:
        result = await manager.deactivate_swarm("nonexistent")
        assert not result

    async def test_get_swarm_state_not_found(self, manager) -> None:
        state = await manager.get_swarm_state("nonexistent")
        assert state is None

    async def test_elect_leader(self, manager) -> None:
        spec = SwarmSpec(name="s1", agent_ids=("a1", "a2", "a3"))
        await manager.create_swarm(spec)
        result = await manager.elect_leader(spec.id)
        assert result is not None
        assert result.elected_leader_id == "a3"  # most capabilities

    async def test_elect_leader_no_agents(self, manager) -> None:
        spec = SwarmSpec(name="s1")
        await manager.create_swarm(spec)
        result = await manager.elect_leader(spec.id)
        assert result is None

    async def test_elect_leader_not_found(self, manager) -> None:
        result = await manager.elect_leader("nonexistent")
        assert result is None

    async def test_get_leader(self, manager) -> None:
        spec = SwarmSpec(name="s1", agent_ids=("a1", "a2", "a3"))
        await manager.create_swarm(spec)
        await manager.elect_leader(spec.id)
        leader = await manager.get_leader(spec.id)
        assert leader is not None
        assert leader.agent_id == "a3"

    async def test_get_leader_no_leader(self, manager) -> None:
        spec = SwarmSpec(name="s1")
        await manager.create_swarm(spec)
        leader = await manager.get_leader(spec.id)
        assert leader is None

    async def test_create_swarm_emits_event(self, manager, bus) -> None:
        spec = SwarmSpec(name="s1")
        await manager.create_swarm(spec)
        topics = [e.topic for e in bus.events]
        assert Topic.ORCH_SWARM_CREATED.value in topics

    async def test_delete_swarm_emits_event(self, manager, bus) -> None:
        spec = SwarmSpec(name="s1")
        await manager.create_swarm(spec)
        bus.events.clear()
        await manager.delete_swarm(spec.id)
        topics = [e.topic for e in bus.events]
        assert Topic.ORCH_SWARM_DELETED.value in topics

    async def test_add_agent_emits_event(self, manager, bus) -> None:
        spec = SwarmSpec(name="s1")
        await manager.create_swarm(spec)
        bus.events.clear()
        await manager.add_agent_to_swarm(spec.id, "a1")
        topics = [e.topic for e in bus.events]
        assert Topic.ORCH_AGENT_JOINED.value in topics
