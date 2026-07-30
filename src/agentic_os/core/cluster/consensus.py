"""Phase 16 — ClusterConsensusManager.

Distributed voting across cluster nodes. Supports 5 consensus types:

  - MAJORITY   : >50% of votes must be "yes"
  - WEIGHTED   : sum(weight) of "yes" votes must exceed 50% of total weight
  - CONFIDENCE : weighted by vote.confidence, accept if avg confidence > 0.6
  - LEADER     : leader decides, others may dissent (recorded but not blocking)
  - QUORUM     : requires quorum_size voters AND majority of those

All votes are recorded with full history. The manager is stateless
between consensus rounds — each call to ``run_consensus()`` is independent.
"""

from __future__ import annotations

from typing import Any

from agentic_os.core.cluster.domain import (
    ConsensusResult,
    ConsensusType,
    ConsensusVote,
)
from agentic_os.infrastructure.logging import get_logger

log = get_logger("cluster.consensus")

# Thresholds
_CONFIDENCE_ACCEPT_THRESHOLD = 0.6


class ClusterConsensusManager:
    """Runs distributed consensus rounds.

    The manager does NOT perform network calls — it expects votes to
    be collected by the caller (e.g. via HTTP fan-out to peer nodes)
    and passed in. This keeps the manager pure and testable.
    """

    def __init__(self, quorum_size: int = 1, leader_id: str = "") -> None:
        self._quorum_size = max(1, quorum_size)
        self._leader_id = leader_id
        self._history: list[ConsensusResult] = []

    # ── Configuration ──────────────────────────────────────────────

    def set_quorum_size(self, size: int) -> None:
        self._quorum_size = max(1, size)

    def set_leader(self, leader_id: str) -> None:
        self._leader_id = leader_id

    @property
    def quorum_size(self) -> int:
        return self._quorum_size

    @property
    def leader_id(self) -> str:
        return self._leader_id

    # ── Consensus execution ────────────────────────────────────────

    def run_consensus(
        self,
        proposal: str,
        votes: list[ConsensusVote] | None = None,
        consensus_type: ConsensusType | str = ConsensusType.MAJORITY,
    ) -> ConsensusResult:
        """Run one consensus round. Returns the result (also stored in history)."""
        if isinstance(consensus_type, str):
            consensus_type = ConsensusType(consensus_type)
        votes = list(votes or [])

        result = ConsensusResult(
            proposal=proposal,
            consensus_type=consensus_type,
            votes=votes,
            leader_id=self._leader_id,
            quorum_size=self._quorum_size,
        )

        # Check quorum
        result.quorum_met = len(votes) >= self._quorum_size

        # Compute decision based on type
        if consensus_type == ConsensusType.LEADER:
            result.decision = self._decide_leader(votes)
        elif not result.quorum_met:
            result.decision = "no_quorum"
        elif consensus_type == ConsensusType.MAJORITY:
            result.decision = self._decide_majority(votes)
        elif consensus_type == ConsensusType.WEIGHTED:
            result.decision = self._decide_weighted(votes)
        elif consensus_type == ConsensusType.CONFIDENCE:
            result.decision = self._decide_confidence(votes)
        elif consensus_type == ConsensusType.QUORUM:
            result.decision = self._decide_quorum(votes)
        else:
            result.decision = "rejected"

        # Compute agreement + confidence
        yes_votes = [v for v in votes if v.vote == "yes"]
        result.agreement = len(yes_votes) / len(votes) if votes else 0.0
        if votes:
            result.confidence = sum(v.confidence for v in votes) / len(votes)
        else:
            result.confidence = 0.0

        self._history.append(result)
        # Cap history at 200 entries
        if len(self._history) > 200:
            self._history = self._history[-200:]

        log.info(
            "Consensus %s on '%s': %s (agreement=%.2f, quorum_met=%s)",
            consensus_type.value,
            proposal[:50],
            result.decision,
            result.agreement,
            result.quorum_met,
        )
        return result

    # ── Decision strategies ────────────────────────────────────────

    def _decide_majority(self, votes: list[ConsensusVote]) -> str:
        yes = sum(1 for v in votes if v.vote == "yes")
        no = sum(1 for v in votes if v.vote == "no")
        if yes > no:
            return "accepted"
        return "rejected"

    def _decide_weighted(self, votes: list[ConsensusVote]) -> str:
        total_weight = sum(v.weight for v in votes)
        if total_weight == 0:
            return "rejected"
        yes_weight = sum(v.weight for v in votes if v.vote == "yes")
        if yes_weight / total_weight > 0.5:
            return "accepted"
        return "rejected"

    def _decide_confidence(self, votes: list[ConsensusVote]) -> str:
        if not votes:
            return "rejected"
        yes_conf = [v.confidence for v in votes if v.vote == "yes"]
        if not yes_conf:
            return "rejected"
        avg_conf = sum(yes_conf) / len(yes_conf)
        if avg_conf >= _CONFIDENCE_ACCEPT_THRESHOLD:
            return "accepted"
        return "rejected"

    def _decide_leader(self, votes: list[ConsensusVote]) -> str:
        """Leader's vote decides. Dissent is recorded but doesn't block."""
        if not self._leader_id:
            return "rejected"
        for v in votes:
            if v.node_id == self._leader_id:
                return "accepted" if v.vote == "yes" else "rejected"
        return "rejected"

    def _decide_quorum(self, votes: list[ConsensusVote]) -> str:
        """Requires quorum AND majority of those voting."""
        if len(votes) < self._quorum_size:
            return "no_quorum"
        return self._decide_majority(votes)

    # ── Queries ────────────────────────────────────────────────────

    def list_history(self, limit: int = 50) -> list[ConsensusResult]:
        return list(self._history[-limit:])

    def get(self, consensus_id: str) -> ConsensusResult | None:
        for r in self._history:
            if r.id == consensus_id:
                return r
        return None

    def stats(self) -> dict[str, Any]:
        by_decision: dict[str, int] = {"accepted": 0, "rejected": 0, "no_quorum": 0}
        by_type: dict[str, int] = {t.value: 0 for t in ConsensusType}
        for r in self._history:
            by_decision[r.decision] = by_decision.get(r.decision, 0) + 1
            by_type[r.consensus_type.value] = by_type.get(r.consensus_type.value, 0) + 1
        return {
            "total_consensuses": len(self._history),
            "by_decision": by_decision,
            "by_type": by_type,
            "quorum_size": self._quorum_size,
            "leader_id": self._leader_id,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "history": [r.to_dict() for r in self._history[-50:]],
            "stats": self.stats(),
        }
