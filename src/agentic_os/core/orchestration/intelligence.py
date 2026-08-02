"""Swarm Intelligence Engine — consensus, voting, and leader election.

Provides mechanisms for agent groups to make collective decisions:
- Consensus: agents vote on a proposal with configurable thresholds
- Voting: structured polls with various strategies
- Leader election: select a swarm leader based on capabilities
"""

from typing import Any

from agentic_os.domain.events import EventEnvelope, Topic
from agentic_os.domain.orchestration import (
    AgentDescriptor,
    ConsensusResult,
    ConsensusStatus,
    LeaderElectionResult,
    Vote,
    VoteValue,
)
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.event_bus import EventBus

log = get_logger("orchestration.intelligence")


class SwarmIntelligenceEngine:
    """Handles consensus, voting, and leader election for swarms."""

    def __init__(
        self,
        bus: EventBus,
        default_quorum: float = 0.51,
    ) -> None:
        self._bus = bus
        self._default_quorum = default_quorum
        self._consensus_rounds: dict[str, ConsensusResult] = {}

    # ── Consensus ──

    async def start_consensus(
        self,
        swarm_id: str,
        topic: str,
        proposals: list[dict[str, Any]],
        agents: list[AgentDescriptor],
        quorum: float | None = None,
    ) -> ConsensusResult:
        """Start a consensus round and collect initial votes."""
        # Create the consensus result
        result = ConsensusResult(
            swarm_id=swarm_id,
            topic=topic,
            status=ConsensusStatus.IN_PROGRESS,
            threshold=quorum or self._default_quorum,
        )

        self._consensus_rounds[result.id] = result

        await self._publish_intelligence_event(
            Topic.ORCH_CONSENSUS_STARTED,
            {
                "consensus_id": result.id,
                "swarm_id": swarm_id,
                "topic": topic,
                "agent_count": len(agents),
            },
        )

        # Collect votes from each agent
        for agent in agents:
            vote = await self._collect_vote(agent, topic, proposals)
            result = result.with_vote(vote)
            self._consensus_rounds[result.id] = result

            await self._publish_intelligence_event(
                Topic.ORCH_VOTE_CAST,
                {
                    "consensus_id": result.id,
                    "voter_id": agent.agent_id,
                    "vote_value": vote.value.value,
                    "weight": vote.weight,
                },
            )

        # Check if consensus was reached
        if result.status == ConsensusStatus.REACHED:
            await self._publish_intelligence_event(
                Topic.ORCH_CONSENSUS_REACHED,
                {
                    "consensus_id": result.id,
                    "outcome": result.outcome,
                    "yea_weight": result.yea_weight,
                    "total_weight": result.total_weight,
                },
            )
        else:
            await self._publish_intelligence_event(
                Topic.ORCH_CONSENSUS_FAILED,
                {
                    "consensus_id": result.id,
                    "yea_weight": result.yea_weight,
                    "total_weight": result.total_weight,
                    "threshold": result.threshold,
                },
            )

        return result

    async def cast_vote(
        self,
        consensus_id: str,
        voter_id: str,
        value: VoteValue,
        rationale: str = "",
        weight: float = 1.0,
    ) -> ConsensusResult | None:
        """Cast a vote in an existing consensus round."""
        consensus = self._consensus_rounds.get(consensus_id)
        if consensus is None:
            return None

        if consensus.status != ConsensusStatus.IN_PROGRESS:
            return consensus

        vote = Vote(
            voter_id=voter_id,
            value=value,
            rationale=rationale,
            weight=weight,
        )

        result = consensus.with_vote(vote)
        self._consensus_rounds[consensus_id] = result

        await self._publish_intelligence_event(
            Topic.ORCH_VOTE_CAST,
            {
                "consensus_id": consensus_id,
                "voter_id": voter_id,
                "vote_value": value.value,
                "weight": weight,
            },
        )

        if result.status == ConsensusStatus.REACHED:
            await self._publish_intelligence_event(
                Topic.ORCH_CONSENSUS_REACHED,
                {
                    "consensus_id": consensus_id,
                    "outcome": result.outcome,
                    "yea_weight": result.yea_weight,
                    "total_weight": result.total_weight,
                },
            )
        elif result.status == ConsensusStatus.FAILED:
            await self._publish_intelligence_event(
                Topic.ORCH_CONSENSUS_FAILED,
                {
                    "consensus_id": consensus_id,
                    "yea_weight": result.yea_weight,
                    "total_weight": result.total_weight,
                    "threshold": result.threshold,
                },
            )

        return result

    async def get_consensus(self, consensus_id: str) -> ConsensusResult | None:
        """Get the current state of a consensus round."""
        return self._consensus_rounds.get(consensus_id)

    # ── Leader Election ──

    async def elect_leader(
        self,
        swarm_id: str,
        agents: list[AgentDescriptor],
    ) -> LeaderElectionResult:
        """Elect a leader from a list of agents using capability-based selection."""
        await self._publish_intelligence_event(
            Topic.ORCH_LEADER_ELECTION_STARTED,
            {"swarm_id": swarm_id, "candidate_count": len(agents)},
        )

        if not agents:
            result = LeaderElectionResult(
                swarm_id=swarm_id,
                elected_leader_id="",
                candidates=(),
            )
            return result

        # Score each agent: more capabilities + lower latency = better leader
        scored = []
        for agent in agents:
            score = len(agent.capabilities) * 10.0
            score += max(0, 100.0 - agent.latency_ms) / 10.0
            if agent.health_status == "healthy":
                score += 5.0
            scored.append((score, agent))

        scored.sort(key=lambda x: x[0], reverse=True)
        winner = scored[0][1]

        vote_counts: dict[str, int] = {}
        for _, agent in scored:
            vote_counts[agent.agent_id] = max(1, int(len(agent.capabilities)))

        result = LeaderElectionResult(
            swarm_id=swarm_id,
            elected_leader_id=winner.agent_id,
            candidates=tuple(a.agent_id for _, a in scored),
            vote_counts=vote_counts,
            total_votes=sum(vote_counts.values()),
        )

        await self._publish_intelligence_event(
            Topic.ORCH_LEADER_ELECTED,
            {
                "swarm_id": swarm_id,
                "leader_id": winner.agent_id,
                "leader_name": winner.name,
                "score": scored[0][0],
            },
        )

        log.info(
            "Leader elected",
            swarm_id=swarm_id,
            leader=winner.name,
            score=scored[0][0],
        )

        return result

    # ── Internal ──

    async def _collect_vote(
        self,
        agent: AgentDescriptor,
        topic: str,
        proposals: list[dict[str, Any]],
    ) -> Vote:
        """Collect a vote from a single agent based on its capabilities.

        The vote decision uses a simple heuristic:
        - Agents with more capabilities tend to vote YES
        - Agents with higher latency tend to vote NO (conservative)
        - Agents with no capabilities ABSTAIN
        """
        if not agent.capabilities:
            return Vote(
                voter_id=agent.agent_id,
                value=VoteValue.ABSTAIN,
                rationale="No capabilities to evaluate proposal",
            )

        # Heuristic: capability_count * 10 > latency_ms means likely YES
        capability_score = len(agent.capabilities) * 10.0
        latency_penalty = agent.latency_ms / 20.0
        net_score = capability_score - latency_penalty

        if net_score > 5.0:
            rationale = (
                f"Capability score {capability_score:.0f} exceeds "
                f"latency penalty {latency_penalty:.0f}"
            )
            return Vote(
                voter_id=agent.agent_id,
                value=VoteValue.YES,
                rationale=rationale,
            )
        elif net_score < -5.0:
            rationale = (
                f"Latency penalty {latency_penalty:.0f} exceeds "
                f"capability score {capability_score:.0f}"
            )
            return Vote(
                voter_id=agent.agent_id,
                value=VoteValue.NO,
                rationale=rationale,
            )
        else:
            return Vote(
                voter_id=agent.agent_id,
                value=VoteValue.ABSTAIN,
                rationale="Net score too close to call",
            )

    async def _publish_intelligence_event(
        self,
        topic: Topic,
        payload: dict[str, Any],
    ) -> None:
        """Publish a swarm intelligence lifecycle event."""
        try:
            await self._bus.publish(
                EventEnvelope(
                    type="event",
                    source="swarm-intelligence",
                    topic=topic.value,
                    payload=payload,
                )
            )
        except Exception as exc:
            log.warning("Failed to publish intelligence event", topic=topic.value, error=str(exc))
