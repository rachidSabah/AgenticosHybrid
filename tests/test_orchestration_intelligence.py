"""Tests for SwarmIntelligenceEngine (Phase 4, M3)."""

import pytest

from agentic_os.core.orchestration.intelligence import SwarmIntelligenceEngine
from agentic_os.domain.orchestration import (
    AgentDescriptor,
    ConsensusResult,
    ConsensusStatus,
    VoteValue,
)


class _MockBus:
    def __init__(self):
        self.events = []

    async def publish(self, envelope):
        self.events.append(envelope)


@pytest.fixture
def bus():
    return _MockBus()


@pytest.fixture
def engine(bus):
    return SwarmIntelligenceEngine(bus=bus)


@pytest.fixture
def agents():
    return [
        AgentDescriptor(
            agent_id="a1",
            name="Agent-1",
            engine_type="generic",
            capabilities=("code", "research"),
            latency_ms=10.0,
            health_status="healthy",
        ),
        AgentDescriptor(
            agent_id="a2",
            name="Agent-2",
            engine_type="generic",
            capabilities=("code",),
            latency_ms=200.0,
            health_status="healthy",
        ),
        AgentDescriptor(
            agent_id="a3",
            name="Agent-3",
            engine_type="generic",
            capabilities=("research",),
            latency_ms=5.0,
            health_status="healthy",
        ),
    ]


class TestSwarmIntelligenceEngine:
    async def test_start_consensus(self, engine, bus, agents) -> None:
        result = await engine.start_consensus(
            swarm_id="s1",
            topic="should-deploy",
            proposals=[{"action": "deploy"}],
            agents=agents[:2],
        )
        assert isinstance(result, ConsensusResult)
        assert result.swarm_id == "s1"
        assert result.topic == "should-deploy"
        assert len(result.votes) == 2

    async def test_consensus_reached(self, engine, bus) -> None:
        agents = [
            AgentDescriptor(
                agent_id="a1",
                name="A1",
                engine_type="generic",
                capabilities=("code", "research", "analyze"),
                latency_ms=10.0,
                health_status="healthy",
            ),
            AgentDescriptor(
                agent_id="a2",
                name="A2",
                engine_type="generic",
                capabilities=("code", "research"),
                latency_ms=20.0,
                health_status="healthy",
            ),
        ]
        result = await engine.start_consensus(
            swarm_id="s1",
            topic="approve",
            proposals=[],
            agents=agents,
        )
        # Both have high capability scores, both likely vote YES
        assert result.status != ConsensusStatus.FAILED

    async def test_consensus_all_abstain(self, engine, bus) -> None:
        agents = [
            AgentDescriptor(
                agent_id="a1",
                name="A1",
                engine_type="generic",
                capabilities=(),
                latency_ms=100.0,
                health_status="healthy",
            ),
        ]
        result = await engine.start_consensus(
            swarm_id="s1",
            topic="vote",
            proposals=[],
            agents=agents,
        )
        assert len(result.votes) == 1
        assert result.votes[0].value == VoteValue.ABSTAIN

    async def test_consensus_mixed(self, engine, bus, agents) -> None:
        # Override agents to ensure a2 votes NO (high latency)
        mixed_agents = [
            AgentDescriptor(
                agent_id="a1",
                name="A1",
                engine_type="generic",
                capabilities=("code", "research"),
                latency_ms=10.0,
                health_status="healthy",
            ),
            AgentDescriptor(
                agent_id="a2",
                name="A2",
                engine_type="generic",
                capabilities=("code",),
                latency_ms=500.0,
                health_status="healthy",
            ),
            AgentDescriptor(
                agent_id="a3",
                name="A3",
                engine_type="generic",
                capabilities=("research",),
                latency_ms=5.0,
                health_status="healthy",
            ),
        ]
        result = await engine.start_consensus(
            swarm_id="s1",
            topic="mixed",
            proposals=[],
            agents=mixed_agents,
        )
        # a1 (high cap, low latency) → YES
        # a2 (low cap, high latency) → NO
        # a3 (mid cap, low latency) → YES
        assert len(result.votes) == 3
        vote_values = [v.value for v in result.votes]
        assert VoteValue.YES in vote_values
        assert VoteValue.NO in vote_values

    async def test_consensus_emits_events(self, engine, bus, agents) -> None:
        await engine.start_consensus(
            swarm_id="s1",
            topic="t1",
            proposals=[],
            agents=agents[:2],
        )
        topics = [e.topic for e in bus.events]
        assert "orchestration.consensus_started" in topics
        assert "orchestration.vote_cast" in topics

    async def test_cast_vote_existing_consensus(self, engine, bus, agents) -> None:
        # Use an agent with no capabilities so it abstains → consensus stays IN_PROGRESS
        agents = [
            AgentDescriptor(
                agent_id="a1",
                name="A1",
                engine_type="generic",
                capabilities=(),
                latency_ms=100.0,
                health_status="healthy",
            ),
            AgentDescriptor(
                agent_id="a2",
                name="A2",
                engine_type="generic",
                capabilities=("code",),
                latency_ms=10.0,
                health_status="healthy",
            ),
        ]
        result = await engine.start_consensus(
            swarm_id="s1",
            topic="t1",
            proposals=[],
            agents=agents[:1],
        )
        # a1 abstains → consensus still IN_PROGRESS
        assert result.status == ConsensusStatus.IN_PROGRESS
        bus.events.clear()
        updated = await engine.cast_vote(result.id, "a2", VoteValue.YES, "I agree")
        assert updated is not None
        assert len(updated.votes) == 2

    async def test_cast_vote_nonexistent(self, engine, bus) -> None:
        result = await engine.cast_vote("nonexistent", "a1", VoteValue.YES)
        assert result is None

    async def test_cast_vote_after_reached(self, engine, bus, agents) -> None:
        # Two agents both vote YES -> consensus reached
        agents = [
            AgentDescriptor(
                agent_id="a1",
                name="A1",
                engine_type="generic",
                capabilities=("code", "research"),
                latency_ms=10.0,
                health_status="healthy",
            ),
            AgentDescriptor(
                agent_id="a2",
                name="A2",
                engine_type="generic",
                capabilities=("code", "research"),
                latency_ms=20.0,
                health_status="healthy",
            ),
        ]
        result = await engine.start_consensus(
            swarm_id="s1",
            topic="t1",
            proposals=[],
            agents=agents,
        )
        # Already reached after start_consensus
        assert result.status == ConsensusStatus.REACHED

    async def test_get_consensus(self, engine, bus, agents) -> None:
        result = await engine.start_consensus(
            swarm_id="s1",
            topic="t1",
            proposals=[],
            agents=agents[:1],
        )
        fetched = await engine.get_consensus(result.id)
        assert fetched is not None
        assert fetched.id == result.id

    async def test_get_consensus_not_found(self, engine) -> None:
        result = await engine.get_consensus("nonexistent")
        assert result is None

    async def test_elect_leader(self, engine, bus, agents) -> None:
        result = await engine.elect_leader("s1", agents)
        # a1 has most capabilities (2) and low latency (10ms) → highest score
        assert result.elected_leader_id == "a1"
        assert len(result.candidates) == 3

    async def test_elect_leader_empty(self, engine, bus) -> None:
        result = await engine.elect_leader("s1", [])
        assert result.elected_leader_id == ""

    async def test_elect_leader_emits_events(self, engine, bus, agents) -> None:
        await engine.elect_leader("s1", agents)
        topics = [e.topic for e in bus.events]
        assert "orchestration.leader_election_started" in topics
        assert "orchestration.leader_elected" in topics

    async def test_elect_leader_single_agent(self, engine, bus) -> None:
        agents = [
            AgentDescriptor(
                agent_id="a1",
                name="A1",
                engine_type="generic",
                capabilities=("code",),
                latency_ms=50.0,
                health_status="healthy",
            ),
        ]
        result = await engine.elect_leader("s1", agents)
        assert result.elected_leader_id == "a1"
        assert result.total_votes >= 1

    async def test_collect_vote_abstain_no_capabilities(self, engine) -> None:
        agent = AgentDescriptor(
            agent_id="a1",
            name="A1",
            engine_type="generic",
            capabilities=(),
            latency_ms=100.0,
            health_status="healthy",
        )
        vote = await engine._collect_vote(agent, "test", [])
        assert vote.value == VoteValue.ABSTAIN

    async def test_collect_vote_yes_high_capability(self, engine) -> None:
        agent = AgentDescriptor(
            agent_id="a1",
            name="A1",
            engine_type="generic",
            capabilities=("code", "research", "analyze", "deploy"),
            latency_ms=10.0,
            health_status="healthy",
        )
        vote = await engine._collect_vote(agent, "test", [])
        assert vote.value == VoteValue.YES

    async def test_collect_vote_no_high_latency(self, engine) -> None:
        agent = AgentDescriptor(
            agent_id="a1",
            name="A1",
            engine_type="generic",
            capabilities=("code",),
            latency_ms=500.0,
            health_status="healthy",
        )
        vote = await engine._collect_vote(agent, "test", [])
        assert vote.value == VoteValue.NO
