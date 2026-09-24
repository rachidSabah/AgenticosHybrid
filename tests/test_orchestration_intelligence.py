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
        # spec §18: agents have not cast real votes — no synthesized votes.
        assert len(result.votes) == 0

    async def test_consensus_no_synthesized_votes(self, engine, bus) -> None:
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
        # spec §18: even high-capability agents cast no vote until they really
        # vote — the round honestly reports votes=[] and outcome=False.
        assert len(result.votes) == 0
        assert result.outcome is False

    async def test_consensus_no_vote_without_real_ballot(self, engine, bus) -> None:
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
        # spec §18: no synthesized ABSTAIN either — a non-voting agent simply
        # produces no vote.
        assert len(result.votes) == 0

    async def test_consensus_mixed(self, engine, bus, agents) -> None:
        # Override agents to cover varied capability/latency profiles
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
        # spec §18: capability/latency heuristics must NOT produce votes —
        # no agent has cast a real ballot, so the vote set stays empty.
        assert len(result.votes) == 0
        assert result.outcome is False

    async def test_consensus_emits_events(self, engine, bus, agents) -> None:
        await engine.start_consensus(
            swarm_id="s1",
            topic="t1",
            proposals=[],
            agents=agents[:2],
        )
        topics = [e.topic for e in bus.events]
        assert "orchestration.consensus_started" in topics
        # spec §18: no synthesized votes → no vote_cast events are emitted.
        assert "orchestration.vote_cast" not in topics

    async def test_cast_vote_existing_consensus(self, engine, bus, agents) -> None:
        # No agent casts a synthesized vote at start → round stays IN_PROGRESS
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
        # a1 casts no vote → consensus still IN_PROGRESS with empty votes
        assert result.status == ConsensusStatus.IN_PROGRESS
        assert len(result.votes) == 0
        bus.events.clear()
        updated = await engine.cast_vote(result.id, "a2", VoteValue.YES, "I agree")
        assert updated is not None
        # Only the real vote cast via cast_vote is recorded.
        assert len(updated.votes) == 1

    async def test_cast_vote_nonexistent(self, engine, bus) -> None:
        result = await engine.cast_vote("nonexistent", "a1", VoteValue.YES)
        assert result is None

    async def test_cast_vote_after_reached(self, engine, bus, agents) -> None:
        # spec §18: start_consensus records no synthesized votes; consensus is
        # reached only after real votes arrive via cast_vote.
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
        # No votes collected at start — round stays IN_PROGRESS, not reached.
        assert result.status == ConsensusStatus.IN_PROGRESS
        assert len(result.votes) == 0
        first = await engine.cast_vote(result.id, "a1", VoteValue.YES, "agree")
        assert first is not None
        assert first.status == ConsensusStatus.REACHED
        # Round already closed — a further cast returns the reached result.
        second = await engine.cast_vote(result.id, "a2", VoteValue.YES, "agree")
        assert second is not None
        assert second.status == ConsensusStatus.REACHED
        assert len(second.votes) == 1

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
        # spec §18: no real ballots were cast — vote_counts stays empty and
        # total_votes is 0 (previously fabricated from capability counts).
        assert result.total_votes == 0
        assert result.vote_counts == {}

    async def test_collect_vote_no_vote_no_capabilities(self, engine) -> None:
        agent = AgentDescriptor(
            agent_id="a1",
            name="A1",
            engine_type="generic",
            capabilities=(),
            latency_ms=100.0,
            health_status="healthy",
        )
        # spec §18: no vote is synthesized (previously an ABSTAIN).
        vote = await engine._collect_vote(agent, "test", [])
        assert vote is None

    async def test_collect_vote_no_synthesized_yes(self, engine) -> None:
        agent = AgentDescriptor(
            agent_id="a1",
            name="A1",
            engine_type="generic",
            capabilities=("code", "research", "analyze", "deploy"),
            latency_ms=10.0,
            health_status="healthy",
        )
        # spec §18: high capability must NOT produce a synthesized YES vote.
        vote = await engine._collect_vote(agent, "test", [])
        assert vote is None

    async def test_collect_vote_no_synthesized_no(self, engine) -> None:
        agent = AgentDescriptor(
            agent_id="a1",
            name="A1",
            engine_type="generic",
            capabilities=("code",),
            latency_ms=500.0,
            health_status="healthy",
        )
        # spec §18: high latency must NOT produce a synthesized NO vote.
        vote = await engine._collect_vote(agent, "test", [])
        assert vote is None
