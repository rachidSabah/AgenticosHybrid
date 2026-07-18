"""Consensus strategies — voting and agreement protocols for swarms."""

from dataclasses import dataclass
from typing import Any

from agentic_os.domain.orchestration import (
    AgentDescriptor,
    ConsensusResult,
    ConsensusStatus,
    Vote,
    VoteValue,
)
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.event_bus import EventBus
from agentic_os.ports.orchestration import ConsensusStrategy

log = get_logger("orchestration.consensus")


@dataclass
class SimpleMajorityConsensus(ConsensusStrategy):
    """Simple majority voting — each agent gets weight 1.0, threshold 0.51.

    The simplest consensus strategy: each agent has equal weight and a
    simple majority (>50%) is required to reach consensus.
    """

    threshold: float = 0.51

    async def reach_consensus(
        self,
        swarm_id: str,
        topic: str,
        proposals: list[dict[str, Any]],
        agents: list[AgentDescriptor],
        bus: EventBus,
    ) -> ConsensusResult:
        """Run consensus with equal-weighted majority voting."""
        if not agents:
            return ConsensusResult(
                swarm_id=swarm_id,
                topic=topic,
                status=ConsensusStatus.FAILED,
                outcome=False,
            )

        # Each agent votes on the proposal
        votes: list[Vote] = []
        yea = 0
        nay = 0
        abstain = 0

        for agent in agents:
            # For simplicity, agents vote based on capability confidence
            confidence = agent.latency_ms / 100.0
            threshold_adjusted = self.threshold - (confidence * 0.1)
            threshold_adjusted = max(0.1, min(0.9, threshold_adjusted))

            vote_value = VoteValue.YES if threshold_adjusted <= 0.5 else VoteValue.NO

            vote = Vote(
                voter_id=agent.agent_id,
                value=vote_value,
                rationale=f"Confidence-adjusted threshold: {threshold_adjusted:.2f}",
                weight=1.0,
            )
            votes.append(vote)

            if vote_value == VoteValue.YES:
                yea += 1
            elif vote_value == VoteValue.NO:
                nay += 1
            else:
                abstain += 1

        total = len(agents)
        outcome = yea / total >= self.threshold if total > 0 else False

        log.info(
            "Consensus round completed",
            swarm_id=swarm_id,
            topic=topic,
            yea=yea,
            nay=nay,
            outcome=outcome,
        )

        return ConsensusResult(
            swarm_id=swarm_id,
            topic=topic,
            status=ConsensusStatus.REACHED if outcome else ConsensusStatus.FAILED,
            votes=tuple(votes),
            yea_count=yea,
            nay_count=nay,
            abstain_count=abstain,
            total_weight=float(total),
            yea_weight=float(yea),
            threshold=self.threshold,
            outcome=outcome,
        )


@dataclass
class WeightedConsensus(ConsensusStrategy):
    """Weighted consensus — agents have weights based on capability confidence.

    Agents with higher capability confidence or lower latency get higher
    voting weight. This allows more reliable agents to have greater influence.
    """

    threshold: float = 0.51

    async def reach_consensus(
        self,
        swarm_id: str,
        topic: str,
        proposals: list[dict[str, Any]],
        agents: list[AgentDescriptor],
        bus: EventBus,
    ) -> ConsensusResult:
        """Run consensus with capability-weighted voting."""
        if not agents:
            return ConsensusResult(
                swarm_id=swarm_id,
                topic=topic,
                status=ConsensusStatus.FAILED,
                outcome=False,
            )

        votes: list[Vote] = []
        total_weight = 0.0
        yea_weight = 0.0
        yea = 0
        nay = 0
        abstain = 0

        for agent in agents:
            # Weight based on latency (inverse — lower latency = higher weight)
            # and status (online = higher weight)
            latency_weight = max(0.1, 1.0 - (agent.latency_ms / 500.0))
            status_weight = 1.0 if agent.status in ("idle", "running") else 0.5
            weight = latency_weight * status_weight
            total_weight += weight

            # Vote decision uses the same confidence-adjusted logic
            vote_value = VoteValue.YES if agent.latency_ms < 200 else VoteValue.NO

            rationale = (
                f"Weight: {weight:.2f} (latency={agent.latency_ms}ms, status={agent.status})"
            )
            vote = Vote(
                voter_id=agent.agent_id,
                value=vote_value,
                rationale=rationale,
                weight=round(weight, 2),
            )
            votes.append(vote)

            if vote_value == VoteValue.YES:
                yea += 1
                yea_weight += weight
            elif vote_value == VoteValue.NO:
                nay += 1
            else:
                abstain += 1

        outcome = yea_weight / total_weight >= self.threshold if total_weight > 0 else False

        log.info(
            "Weighted consensus round completed",
            swarm_id=swarm_id,
            topic=topic,
            yea=yea,
            nay=nay,
            yea_weight=round(yea_weight, 2),
            total_weight=round(total_weight, 2),
            outcome=outcome,
        )

        return ConsensusResult(
            swarm_id=swarm_id,
            topic=topic,
            status=ConsensusStatus.REACHED if outcome else ConsensusStatus.FAILED,
            votes=tuple(votes),
            yea_count=yea,
            nay_count=nay,
            abstain_count=abstain,
            total_weight=round(total_weight, 2),
            yea_weight=round(yea_weight, 2),
            threshold=self.threshold,
            outcome=outcome,
        )
