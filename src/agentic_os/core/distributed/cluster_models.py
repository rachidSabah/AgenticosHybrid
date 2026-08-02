"""Phase 17 — Distributed execution fabric domain models.

Pure data structures for multi-node distributed execution:
  - DistributedTask / TaskAcknowledgement / TaskResult
  - HeartbeatPacket / HeartbeatStatus
  - LeaderElectionState / Vote
  - ReplicationEntry
  - NodeHealthSnapshot
  - DistributedEvent (envelope for cross-node propagation)

All additive — does not modify any existing domain model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _new_id(prefix: str = "") -> str:
    return f"{prefix}{uuid4().hex[:12]}" if prefix else uuid4().hex[:12]


# ── Distributed Task ───────────────────────────────────────────────────


class DistributedTaskStatus(StrEnum):
    PENDING = "pending"
    DISPATCHED = "dispatched"
    ACKNOWLEDGED = "acknowledged"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


@dataclass
class DistributedTask:
    """A task dispatched for remote execution on a cluster node."""

    id: str = field(default_factory=lambda: _new_id("dtask-"))
    mission_id: str = ""
    title: str = ""
    description: str = ""
    required_capabilities: list[str] = field(default_factory=list)
    payload: dict[str, Any] = field(default_factory=dict)
    target_node_id: str = ""  # empty = any node
    source_node_id: str = ""
    priority: float = 0.5
    status: DistributedTaskStatus = DistributedTaskStatus.PENDING
    assigned_node_id: str = ""
    assigned_brain_id: str = ""
    dispatch_time: str = ""
    ack_time: str = ""
    completion_time: str = ""
    result: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    timeout_s: float = 60.0
    retries: int = 0
    max_retries: int = 2
    created_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "mission_id": self.mission_id,
            "title": self.title,
            "description": self.description,
            "required_capabilities": list(self.required_capabilities),
            "payload": dict(self.payload),
            "target_node_id": self.target_node_id,
            "source_node_id": self.source_node_id,
            "priority": round(self.priority, 3),
            "status": self.status.value,
            "assigned_node_id": self.assigned_node_id,
            "assigned_brain_id": self.assigned_brain_id,
            "dispatch_time": self.dispatch_time,
            "ack_time": self.ack_time,
            "completion_time": self.completion_time,
            "result": dict(self.result),
            "error": self.error,
            "timeout_s": self.timeout_s,
            "retries": self.retries,
            "max_retries": self.max_retries,
            "created_at": self.created_at,
        }


@dataclass
class TaskAcknowledgement:
    """Acknowledgement from a remote node that it received a task."""

    task_id: str
    node_id: str
    brain_id: str = ""
    accepted: bool = True
    reason: str = ""
    timestamp: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "node_id": self.node_id,
            "brain_id": self.brain_id,
            "accepted": self.accepted,
            "reason": self.reason,
            "timestamp": self.timestamp,
        }


# ── Heartbeat ──────────────────────────────────────────────────────────


@dataclass
class HeartbeatPacket:
    """A heartbeat packet sent between nodes."""

    node_id: str
    timestamp: str = field(default_factory=_now_iso)
    sequence: int = 0
    status: str = "active"  # active | degraded | leaving
    brain_count: int = 0
    active_tasks: int = 0
    cpu_usage: float = 0.0
    memory_usage: float = 0.0
    health_score: float = 100.0
    leader_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "timestamp": self.timestamp,
            "sequence": self.sequence,
            "status": self.status,
            "brain_count": self.brain_count,
            "active_tasks": self.active_tasks,
            "cpu_usage": round(self.cpu_usage, 2),
            "memory_usage": round(self.memory_usage, 2),
            "health_score": round(self.health_score, 2),
            "leader_id": self.leader_id,
        }


@dataclass
class HeartbeatStatus:
    """Tracked heartbeat status for a single node."""

    node_id: str
    last_heartbeat: str = ""
    last_sequence: int = 0
    missed_count: int = 0
    is_alive: bool = True
    consecutive_failures: int = 0
    packets_received: int = 0
    packets_missed: int = 0
    avg_latency_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "last_heartbeat": self.last_heartbeat,
            "last_sequence": self.last_sequence,
            "missed_count": self.missed_count,
            "is_alive": self.is_alive,
            "consecutive_failures": self.consecutive_failures,
            "packets_received": self.packets_received,
            "packets_missed": self.packets_missed,
            "avg_latency_ms": round(self.avg_latency_ms, 2),
        }


# ── Leader Election ────────────────────────────────────────────────────


class LeaderElectionState(StrEnum):
    FOLLOWER = "follower"
    CANDIDATE = "candidate"
    LEADER = "leader"
    OBSERVER = "observer"


@dataclass
class LeaderVote:
    """A vote in a leader election round."""

    voter_id: str
    candidate_id: str
    term: int = 0
    timestamp: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "voter_id": self.voter_id,
            "candidate_id": self.candidate_id,
            "term": self.term,
            "timestamp": self.timestamp,
        }


@dataclass
class LeaderElectionResult:
    """Result of a leader election round."""

    term: int = 0
    winner_id: str = ""
    total_votes: int = 0
    votes_for_winner: int = 0
    quorum_met: bool = False
    participants: list[str] = field(default_factory=list)
    votes: list[LeaderVote] = field(default_factory=list)
    timestamp: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "term": self.term,
            "winner_id": self.winner_id,
            "total_votes": self.total_votes,
            "votes_for_winner": self.votes_for_winner,
            "quorum_met": self.quorum_met,
            "participants": list(self.participants),
            "votes": [v.to_dict() for v in self.votes],
            "timestamp": self.timestamp,
        }


# ── Replication ────────────────────────────────────────────────────────


class ReplicationEntryType(StrEnum):
    BRAIN_REGISTRY = "brain_registry"
    MISSION_STATE = "mission_state"
    GOAL_STATE = "goal_state"
    EVOLUTION_PROPOSAL = "evolution_proposal"
    CAPABILITY_GRAPH = "capability_graph"


@dataclass
class ReplicationEntry:
    """A state entry to be replicated across the cluster."""

    id: str = field(default_factory=lambda: _new_id("repl-"))
    entry_type: ReplicationEntryType = ReplicationEntryType.BRAIN_REGISTRY
    source_node_id: str = ""
    key: str = ""
    value: dict[str, Any] = field(default_factory=dict)
    version: int = 0
    timestamp: str = field(default_factory=_now_iso)
    replicated_to: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "entry_type": self.entry_type.value,
            "source_node_id": self.source_node_id,
            "key": self.key,
            "value": dict(self.value),
            "version": self.version,
            "timestamp": self.timestamp,
            "replicated_to": list(self.replicated_to),
        }


# ── Cluster Health ─────────────────────────────────────────────────────


@dataclass
class NodeHealthSnapshot:
    """Health snapshot for a single node."""

    node_id: str
    is_alive: bool = True
    health_score: float = 100.0
    cpu_usage: float = 0.0
    memory_usage: float = 0.0
    brain_count: int = 0
    active_tasks: int = 0
    latency_ms: float = 0.0
    uptime_s: float = 0.0
    issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "is_alive": self.is_alive,
            "health_score": round(self.health_score, 2),
            "cpu_usage": round(self.cpu_usage, 2),
            "memory_usage": round(self.memory_usage, 2),
            "brain_count": self.brain_count,
            "active_tasks": self.active_tasks,
            "latency_ms": round(self.latency_ms, 2),
            "uptime_s": round(self.uptime_s, 1),
            "issues": list(self.issues),
        }


@dataclass
class ClusterHealthSnapshot:
    """Aggregate cluster health."""

    total_nodes: int = 0
    alive_nodes: int = 0
    dead_nodes: int = 0
    avg_health: float = 0.0
    avg_cpu: float = 0.0
    avg_memory: float = 0.0
    total_brains: int = 0
    total_active_tasks: int = 0
    leader_id: str = ""
    quorum_intact: bool = True
    node_health: dict[str, NodeHealthSnapshot] = field(default_factory=dict)
    last_updated: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_nodes": self.total_nodes,
            "alive_nodes": self.alive_nodes,
            "dead_nodes": self.dead_nodes,
            "avg_health": round(self.avg_health, 2),
            "avg_cpu": round(self.avg_cpu, 2),
            "avg_memory": round(self.avg_memory, 2),
            "total_brains": self.total_brains,
            "total_active_tasks": self.total_active_tasks,
            "leader_id": self.leader_id,
            "quorum_intact": self.quorum_intact,
            "node_health": {k: v.to_dict() for k, v in self.node_health.items()},
            "last_updated": self.last_updated,
        }


# ── Distributed Event ──────────────────────────────────────────────────


@dataclass
class DistributedEvent:
    """An event envelope for cross-node propagation.

    Wraps a standard EventEnvelope with source/origin tracking so the
    receiving node knows where the event came from and can avoid
    re-broadcasting it (prevents loops).
    """

    event_type: str = ""
    source_node_id: str = ""
    origin_node_id: str = ""  # original creator (may differ from source)
    payload: dict[str, Any] = field(default_factory=dict)
    hop_count: int = 0
    max_hops: int = 3  # TTL for propagation
    timestamp: str = field(default_factory=_now_iso)
    event_id: str = field(default_factory=lambda: _new_id("devt-"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "source_node_id": self.source_node_id,
            "origin_node_id": self.origin_node_id,
            "payload": dict(self.payload),
            "hop_count": self.hop_count,
            "max_hops": self.max_hops,
            "timestamp": self.timestamp,
            "event_id": self.event_id,
        }


# ── Distributed Statistics ─────────────────────────────────────────────


@dataclass
class DistributedStatistics:
    """Aggregate statistics for the distributed execution fabric."""

    total_tasks_dispatched: int = 0
    total_tasks_completed: int = 0
    total_tasks_failed: int = 0
    total_tasks_timed_out: int = 0
    total_events_propagated: int = 0
    total_heartbeats_sent: int = 0
    total_heartbeats_received: int = 0
    total_replications: int = 0
    leader_elections: int = 0
    avg_task_latency_ms: float = 0.0
    avg_event_propagation_ms: float = 0.0
    last_updated: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_tasks_dispatched": self.total_tasks_dispatched,
            "total_tasks_completed": self.total_tasks_completed,
            "total_tasks_failed": self.total_tasks_failed,
            "total_tasks_timed_out": self.total_tasks_timed_out,
            "total_events_propagated": self.total_events_propagated,
            "total_heartbeats_sent": self.total_heartbeats_sent,
            "total_heartbeats_received": self.total_heartbeats_received,
            "total_replications": self.total_replications,
            "leader_elections": self.leader_elections,
            "avg_task_latency_ms": round(self.avg_task_latency_ms, 2),
            "avg_event_propagation_ms": round(self.avg_event_propagation_ms, 2),
            "last_updated": self.last_updated,
        }
