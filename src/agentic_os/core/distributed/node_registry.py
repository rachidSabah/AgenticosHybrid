"""Phase 17 — NodeRegistry + LeaderElection.

NodeRegistry: tracks cluster membership lifecycle (join/leave/timeout).
  Extends Phase 16's topology tracking with explicit membership state
  machine: PENDING → ACTIVE → LEAVING → LEFT.

LeaderElection: deterministic leader election with quorum + term tracking.
  Extends Phase 16's basic election with Raft-like terms and vote tracking.
  The election is deterministic (healthiest active node wins) so it works
  in single-node mode without any network calls.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from agentic_os.core.distributed.cluster_models import (
    LeaderElectionResult,
    LeaderElectionState,
    LeaderVote,
)
from agentic_os.infrastructure.logging import get_logger

if TYPE_CHECKING:
    from agentic_os.core.distributed.heartbeat_manager import HeartbeatManager
    from agentic_os.ports.event_bus import EventBus

log = get_logger("distributed.node_registry")


class NodeRegistry:
    """Tracks cluster node membership lifecycle."""

    def __init__(self, local_node_id: str = "") -> None:
        self._local_node_id = local_node_id
        self._nodes: dict[str, dict[str, Any]] = {}  # node_id → metadata
        self._stats: dict[str, int] = {
            "joined": 0,
            "left": 0,
            "timed_out": 0,
        }

    @property
    def local_node_id(self) -> str:
        return self._local_node_id

    @property
    def stats(self) -> dict[str, Any]:
        return {**self._stats, "active_nodes": len(self._nodes)}

    def register_join(
        self,
        node_id: str,
        host: str = "",
        port: int = 0,
        base_url: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Register a node joining the cluster."""
        entry = {
            "node_id": node_id,
            "host": host,
            "port": port,
            "base_url": base_url,
            "joined_at": datetime.now(UTC).isoformat(),
            "status": "active",
            "metadata": dict(metadata or {}),
        }
        self._nodes[node_id] = entry
        self._stats["joined"] += 1
        log.info("Node joined cluster", node=node_id, host=host)
        return entry

    def register_leave(self, node_id: str, reason: str = "") -> bool:
        """Register a node leaving the cluster."""
        if node_id not in self._nodes:
            return False
        self._nodes[node_id]["status"] = "left"
        self._nodes[node_id]["left_at"] = datetime.now(UTC).isoformat()
        self._nodes[node_id]["leave_reason"] = reason
        self._stats["left"] += 1
        log.info("Node left cluster", node=node_id, reason=reason)
        return True

    def register_timeout(self, node_id: str) -> bool:
        """Mark a node as timed out (missed too many heartbeats)."""
        if node_id not in self._nodes:
            return False
        self._nodes[node_id]["status"] = "timed_out"
        self._nodes[node_id]["timed_out_at"] = datetime.now(UTC).isoformat()
        self._stats["timed_out"] += 1
        log.warning("Node timed out", node=node_id)
        return True

    def remove(self, node_id: str) -> bool:
        """Fully remove a node from the registry."""
        if node_id not in self._nodes:
            return False
        del self._nodes[node_id]
        return True

    def list_nodes(self, status: str | None = None) -> list[dict[str, Any]]:
        if status is None:
            return list(self._nodes.values())
        return [n for n in self._nodes.values() if n.get("status") == status]

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        return self._nodes.get(node_id)

    def count(self, status: str | None = None) -> int:
        if status is None:
            return len(self._nodes)
        return sum(1 for n in self._nodes.values() if n.get("status") == status)


class LeaderElection:
    """Deterministic leader election with quorum + term tracking."""

    def __init__(
        self,
        bus: EventBus,
        local_node_id: str = "",
        heartbeat_manager: HeartbeatManager | None = None,
    ) -> None:
        self._bus = bus
        self._local_node_id = local_node_id
        self._heartbeat = heartbeat_manager
        self._state: LeaderElectionState = LeaderElectionState.FOLLOWER
        self._current_term: int = 0
        self._current_leader: str = ""
        self._votes: list[LeaderVote] = []
        self._election_history: list[LeaderElectionResult] = []
        self._stats: dict[str, int] = {
            "elections_run": 0,
            "elected_leader": 0,
            "elections_failed": 0,
        }

    @property
    def state(self) -> LeaderElectionState:
        return self._state

    @property
    def current_leader(self) -> str:
        return self._current_leader

    @property
    def current_term(self) -> int:
        return self._current_term

    @property
    def stats(self) -> dict[str, Any]:
        return {**self._stats, "state": self._state.value, "leader": self._current_leader}

    def list_history(self, limit: int = 50) -> list[LeaderElectionResult]:
        return list(self._election_history[-limit:])

    # ── Election ───────────────────────────────────────────────────

    def run_election(
        self,
        candidates: list[dict[str, Any]] | None = None,
        votes: list[LeaderVote] | None = None,
    ) -> LeaderElectionResult:
        """Run a leader election round.

        Strategy: deterministic — pick the active node with the highest
        health_score, then highest brain_count, then lowest node_id.
        This works in single-node mode (auto-elect self) and multi-node
        mode (all nodes compute the same winner).

        If explicit votes are provided, use majority voting instead.
        """
        self._current_term += 1
        self._stats["elections_run"] += 1
        self._state = LeaderElectionState.CANDIDATE

        result = LeaderElectionResult(term=self._current_term)

        if votes:
            # Use provided votes (from peers)
            result.votes = list(votes)
            result.total_votes = len(votes)
            vote_counts: dict[str, int] = {}
            for v in votes:
                vote_counts[v.candidate_id] = vote_counts.get(v.candidate_id, 0) + 1
            if vote_counts:
                winner = max(vote_counts, key=lambda k: vote_counts.get(k, 0))
                result.winner_id = winner
                result.votes_for_winner = vote_counts[winner]
        else:
            # Deterministic election based on node health
            eligible = self._get_eligible_nodes(candidates)
            result.participants = [n["node_id"] for n in eligible]
            result.total_votes = len(eligible)

            if eligible:
                # Sort by (health_score desc, brain_count desc, node_id asc)
                eligible.sort(
                    key=lambda n: (
                        -float(n.get("health_score", 0)),
                        -int(n.get("brain_count", 0)),
                        str(n.get("node_id", "")),
                    )
                )
                winner = eligible[0]
                result.winner_id = winner["node_id"]
                result.votes_for_winner = 1  # self-vote in deterministic mode

        # Check quorum (majority of total participants)
        quorum_size = max(1, (result.total_votes // 2) + 1)
        result.quorum_met = result.votes_for_winner >= quorum_size

        if result.quorum_met and result.winner_id:
            self._current_leader = result.winner_id
            self._state = (
                LeaderElectionState.LEADER
                if result.winner_id == self._local_node_id
                else LeaderElectionState.FOLLOWER
            )
            self._stats["elected_leader"] += 1
            log.info(
                "Leader elected",
                leader=result.winner_id,
                term=result.term,
                votes=result.votes_for_winner,
            )
        else:
            self._state = LeaderElectionState.FOLLOWER
            self._stats["elections_failed"] += 1
            log.warning("Leader election failed — no quorum")

        self._election_history.append(result)
        if len(self._election_history) > 100:
            self._election_history = self._election_history[-100:]

        return result

    def _get_eligible_nodes(self, candidates: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        """Get eligible nodes for election."""
        if candidates:
            return [c for c in candidates if c.get("status", "active") == "active"]

        # Use heartbeat statuses if available
        if self._heartbeat is not None:
            eligible: list[dict[str, Any]] = []
            for status in self._heartbeat.list_statuses():
                if status.is_alive:
                    eligible.append(
                        {
                            "node_id": status.node_id,
                            "health_score": 100.0 - status.consecutive_failures * 20,
                            "brain_count": 0,
                        }
                    )
            # Always include self
            if not any(n["node_id"] == self._local_node_id for n in eligible):
                eligible.append(
                    {
                        "node_id": self._local_node_id,
                        "health_score": 100.0,
                        "brain_count": 0,
                    }
                )
            return eligible

        # Fallback: just self
        return [
            {
                "node_id": self._local_node_id,
                "health_score": 100.0,
                "brain_count": 0,
            }
        ]

    def receive_vote(self, vote: LeaderVote) -> bool:
        """Receive a vote from a peer. Returns True if vote accepted."""
        if vote.term < self._current_term:
            return False
        self._votes.append(vote)
        return True

    def step_down(self) -> None:
        """Step down from leader/candidate to follower."""
        self._state = LeaderElectionState.FOLLOWER
