"""Consensus strategies — voting and agreement protocols for swarms."""

from dataclasses import dataclass
from typing import Any

from agentic_os.domain.orchestration import (
    AgentDescriptor,
    ConsensusResult,
    ConsensusStatus,
)
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.event_bus import EventBus
from agentic_os.ports.orchestration import ConsensusStrategy

log = get_logger("orchestration.consensus")


@dataclass
class SimpleMajorityConsensus(ConsensusStrategy):
    """Simple majority voting — each agent gets weight 1.0, threshold 0.51.

    spec §18: no fabricated consensus votes. This strategy has no channel
    through which agents actually cast ballots, so no vote is ever
    synthesized from latency/capability-derived "confidence". With zero real
    votes collected the round honestly reports votes=[], vote_count=0 and
    consensus_reached=False (no consensus rounds recorded).
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
        """Run consensus with equal-weighted majority voting over real ballots.

        spec §18: agents cannot vote through this interface, so the vote set
        stays empty and consensus is not reached until real ballots are wired
        in. No VoteValue is derived from agent latency or capabilities.
        """
        log.info(
            "Consensus round completed with no votes recorded",
            swarm_id=swarm_id,
            topic=topic,
            yea=0,
            nay=0,
            outcome=False,
        )

        return ConsensusResult(
            swarm_id=swarm_id,
            topic=topic,
            status=ConsensusStatus.FAILED,
            votes=(),
            yea_count=0,
            nay_count=0,
            abstain_count=0,
            total_weight=0.0,
            yea_weight=0.0,
            threshold=self.threshold,
            outcome=False,
        )


@dataclass
class WeightedConsensus(ConsensusStrategy):
    """Weighted consensus — ballots are aggregated with per-vote weights.

    spec §18: no fabricated consensus votes. This strategy has no channel
    through which agents actually cast ballots, so no vote (and no weight) is
    ever synthesized from latency/status heuristics. With zero real votes
    collected the round honestly reports votes=[], vote_count=0,
    total_weight=0 and consensus_reached=False (no consensus rounds recorded).
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
        """Run consensus with weighted aggregation of real ballots.

        spec §18: agents cannot vote through this interface, so the vote set
        stays empty and consensus is not reached until real ballots are wired
        in. No VoteValue or weight is derived from agent latency or status.
        """
        log.info(
            "Weighted consensus round completed with no votes recorded",
            swarm_id=swarm_id,
            topic=topic,
            yea=0,
            nay=0,
            yea_weight=0.0,
            total_weight=0.0,
            outcome=False,
        )

        return ConsensusResult(
            swarm_id=swarm_id,
            topic=topic,
            status=ConsensusStatus.FAILED,
            votes=(),
            yea_count=0,
            nay_count=0,
            abstain_count=0,
            total_weight=0.0,
            yea_weight=0.0,
            threshold=self.threshold,
            outcome=False,
        )
