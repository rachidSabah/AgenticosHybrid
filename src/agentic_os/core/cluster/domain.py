"""Phase 16 — Cluster federation domain models.

Pure data structures for the distributed multi-host AgenticOS:

  - NodeInfo / NodeStatus / NodeHealth — remote AgenticOS instances
  - ClusterTopology — hosts/nodes/connections graph
  - RemoteBrainRecord — a BrainRecord tagged with its origin host
  - ClusterScore — multi-factor score for global scheduling
  - ConsensusVote / ConsensusResult — distributed voting
  - FailoverAction — recovery actions

All additive — does not modify BrainRecord or any existing domain.
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


# ── Node Identity & Health ────────────────────────────────────────────


class NodeStatus(StrEnum):
    """Lifecycle state of a cluster node (remote AgenticOS instance)."""

    JOINING = "joining"  # discovered, awaiting handshake
    ACTIVE = "active"  # healthy and accepting work
    DEGRADED = "degraded"  # slow but reachable
    UNREACHABLE = "unreachable"  # missed N heartbeats
    LEAVING = "leaving"  # graceful shutdown in progress
    LEFT = "left"  # removed from cluster


class NodeRole(StrEnum):
    """Cluster role for a node."""

    FOLLOWER = "follower"
    CANDIDATE = "candidate"
    LEADER = "leader"
    OBSERVER = "observer"  # read-only member (no scheduling)


@dataclass
class NodeInfo:
    """A remote AgenticOS node in the federation.

    A node is one running AgenticOS instance (kernel + API + runtimes).
    The local node is always present in the topology with ``is_local=True``.
    """

    id: str
    host: str = "localhost"
    port: int = 8000
    base_url: str = "http://localhost:8000"
    display_name: str = ""
    status: NodeStatus = NodeStatus.JOINING
    role: NodeRole = NodeRole.FOLLOWER
    is_local: bool = False
    version: str = "1.0.0"
    cluster_id: str = "default"
    started_at: str = field(default_factory=_now_iso)
    last_heartbeat: str = field(default_factory=_now_iso)
    heartbeat_interval_s: float = 30.0
    # Live metrics (reported by the node, refreshed by heartbeat)
    brain_count: int = 0
    capability_count: int = 0
    active_missions: int = 0
    cpu_usage: float = 0.0
    memory_usage: float = 0.0
    disk_usage: float = 0.0
    network_latency_ms: float = 0.0
    bandwidth_mbps: float = 0.0
    # Health snapshot
    health_score: float = 100.0
    issues: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "host": self.host,
            "port": self.port,
            "base_url": self.base_url,
            "display_name": self.display_name or f"{self.host}:{self.port}",
            "status": self.status.value,
            "role": self.role.value,
            "is_local": self.is_local,
            "version": self.version,
            "cluster_id": self.cluster_id,
            "started_at": self.started_at,
            "last_heartbeat": self.last_heartbeat,
            "heartbeat_interval_s": self.heartbeat_interval_s,
            "brain_count": self.brain_count,
            "capability_count": self.capability_count,
            "active_missions": self.active_missions,
            "cpu_usage": round(self.cpu_usage, 2),
            "memory_usage": round(self.memory_usage, 2),
            "disk_usage": round(self.disk_usage, 2),
            "network_latency_ms": round(self.network_latency_ms, 2),
            "bandwidth_mbps": round(self.bandwidth_mbps, 2),
            "health_score": round(self.health_score, 2),
            "issues": list(self.issues),
            "metadata": dict(self.metadata),
        }


@dataclass
class NodeConnection:
    """A network link between two nodes in the topology."""

    source: str
    target: str
    latency_ms: float = 0.0
    bandwidth_mbps: float = 0.0
    healthy: bool = True
    last_checked: str = field(default_factory=_now_iso)

    @property
    def edge_id(self) -> str:
        return f"{self.source}->{self.target}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "latency_ms": round(self.latency_ms, 2),
            "bandwidth_mbps": round(self.bandwidth_mbps, 2),
            "healthy": self.healthy,
            "last_checked": self.last_checked,
        }


# ── Cluster Topology ──────────────────────────────────────────────────


@dataclass
class ClusterTopologySnapshot:
    """Live snapshot of the cluster topology."""

    cluster_id: str = "default"
    nodes: list[NodeInfo] = field(default_factory=list)
    connections: list[NodeConnection] = field(default_factory=list)
    leader_id: str = ""
    quorum_size: int = 1
    total_brains: int = 0
    total_capabilities: int = 0
    total_active_missions: int = 0
    cluster_health: float = 0.0
    last_updated: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cluster_id": self.cluster_id,
            "nodes": [n.to_dict() for n in self.nodes],
            "connections": [c.to_dict() for c in self.connections],
            "leader_id": self.leader_id,
            "quorum_size": self.quorum_size,
            "total_brains": self.total_brains,
            "total_capabilities": self.total_capabilities,
            "total_active_missions": self.total_active_missions,
            "cluster_health": round(self.cluster_health, 3),
            "last_updated": self.last_updated,
        }


# ── Remote Brain Record ───────────────────────────────────────────────


@dataclass
class RemoteBrainRecord:
    """A brain that lives on a remote node.

    Stored in DistributedBrainRegistry alongside local BrainRecords.
    The local BrainRegistry remains canonical for local brains —
    this wrapper adds remote-only brains + cluster metadata.
    """

    brain_id: str
    node_id: str
    display_name: str = ""
    provider: str = ""
    host: str = ""
    capabilities: tuple[str, ...] = field(default_factory=tuple)
    health: float = 100.0
    latency: float = 0.0
    availability: float = 1.0
    version: str = "1.0.0"
    last_synced: str = field(default_factory=_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "brain_id": self.brain_id,
            "node_id": self.node_id,
            "display_name": self.display_name,
            "provider": self.provider,
            "host": self.host,
            "capabilities": list(self.capabilities),
            "health": round(self.health, 2),
            "latency": round(self.latency, 2),
            "availability": round(self.availability, 3),
            "version": self.version,
            "last_synced": self.last_synced,
            "metadata": dict(self.metadata),
        }


# ── Cluster Score (for global scheduling) ─────────────────────────────


@dataclass
class ClusterScore:
    """Multi-factor score for a (node, brain) candidate.

    Used by GlobalMissionScheduler.select_optimal(). Every factor is
    normalized to [0, 1] and weighted — selection is deterministic.
    """

    node_id: str
    brain_id: str = ""
    brain_name: str = ""
    health_score: float = 0.0  # brain.health / 100
    latency_score: float = 0.0  # 1 - (latency / 5000)
    availability_score: float = 0.0  # 1 if available else 0
    historical_success: float = 0.0  # from CollaborationNetwork
    cluster_load_score: float = 0.0  # 1 - (cpu_usage / 100)
    memory_score: float = 0.0  # 1 - (memory_usage / 100)
    provider_score: float = 0.0  # 1 if provider matches
    confidence_score: float = 0.0  # from CollaborationNetwork.trust
    capability_match: float = 0.0  # matching / required
    total_score: float = 0.0
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "brain_id": self.brain_id,
            "brain_name": self.brain_name,
            "health_score": round(self.health_score, 3),
            "latency_score": round(self.latency_score, 3),
            "availability_score": round(self.availability_score, 3),
            "historical_success": round(self.historical_success, 3),
            "cluster_load_score": round(self.cluster_load_score, 3),
            "memory_score": round(self.memory_score, 3),
            "provider_score": round(self.provider_score, 3),
            "confidence_score": round(self.confidence_score, 3),
            "capability_match": round(self.capability_match, 3),
            "total_score": round(self.total_score, 4),
            "rationale": self.rationale,
        }


# ── Consensus ─────────────────────────────────────────────────────────


class ConsensusType(StrEnum):
    MAJORITY = "majority"
    WEIGHTED = "weighted"
    CONFIDENCE = "confidence"
    LEADER = "leader"
    QUORUM = "quorum"


@dataclass
class ConsensusVote:
    """A single vote from one node."""

    node_id: str
    vote: str  # "yes" / "no" / "abstain"
    weight: float = 1.0
    confidence: float = 1.0
    rationale: str = ""
    timestamp: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "vote": self.vote,
            "weight": round(self.weight, 3),
            "confidence": round(self.confidence, 3),
            "rationale": self.rationale,
            "timestamp": self.timestamp,
        }


@dataclass
class ConsensusResult:
    """Outcome of a consensus round."""

    id: str = field(default_factory=lambda: _new_id("consensus-"))
    proposal: str = ""
    consensus_type: ConsensusType = ConsensusType.MAJORITY
    votes: list[ConsensusVote] = field(default_factory=list)
    decision: str = ""  # "accepted" / "rejected" / "no_quorum"
    confidence: float = 0.0
    agreement: float = 0.0  # fraction of yes votes
    leader_id: str = ""
    quorum_size: int = 1
    quorum_met: bool = False
    created_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "proposal": self.proposal,
            "consensus_type": self.consensus_type.value,
            "votes": [v.to_dict() for v in self.votes],
            "decision": self.decision,
            "confidence": round(self.confidence, 3),
            "agreement": round(self.agreement, 3),
            "leader_id": self.leader_id,
            "quorum_size": self.quorum_size,
            "quorum_met": self.quorum_met,
            "created_at": self.created_at,
        }


# ── Failover ──────────────────────────────────────────────────────────


class FailoverTrigger(StrEnum):
    NODE_OFFLINE = "node_offline"
    RUNTIME_OFFLINE = "runtime_offline"
    HIGH_LATENCY = "high_latency"
    MISSION_FAILED = "mission_failed"
    NETWORK_PARTITION = "network_partition"
    MANUAL = "manual"


class FailoverActionType(StrEnum):
    REASSIGN_MISSION = "reassign_mission"
    REPLACE_RUNTIME = "replace_runtime"
    ELECT_REPLACEMENT = "elect_replacement"
    RESUME_EXECUTION = "resume_execution"
    QUARANTINE_NODE = "quarantine_node"


@dataclass
class FailoverAction:
    """A recovery action produced by FailoverEngine."""

    id: str = field(default_factory=lambda: _new_id("failover-"))
    trigger: FailoverTrigger = FailoverTrigger.MANUAL
    action_type: FailoverActionType = FailoverActionType.REASSIGN_MISSION
    target_node_id: str = ""
    target_brain_id: str = ""
    target_mission_id: str = ""
    replacement_node_id: str = ""
    replacement_brain_id: str = ""
    rationale: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)
    status: str = "pending"  # pending / in_progress / completed / failed
    started_at: str = ""
    completed_at: str = ""
    created_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "trigger": self.trigger.value,
            "action_type": self.action_type.value,
            "target_node_id": self.target_node_id,
            "target_brain_id": self.target_brain_id,
            "target_mission_id": self.target_mission_id,
            "replacement_node_id": self.replacement_node_id,
            "replacement_brain_id": self.replacement_brain_id,
            "rationale": self.rationale,
            "evidence": dict(self.evidence),
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "created_at": self.created_at,
        }


# ── Cluster Statistics ────────────────────────────────────────────────


@dataclass
class ClusterStatistics:
    """Aggregate cluster statistics."""

    total_nodes: int = 0
    active_nodes: int = 0
    degraded_nodes: int = 0
    unreachable_nodes: int = 0
    total_brains: int = 0
    local_brains: int = 0
    remote_brains: int = 0
    total_capabilities: int = 0
    unique_capabilities: int = 0
    active_missions: int = 0
    completed_missions: int = 0
    failed_missions: int = 0
    failover_count: int = 0
    consensus_count: int = 0
    average_node_health: float = 0.0
    average_network_latency: float = 0.0
    cluster_utilization: float = 0.0
    last_updated: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_nodes": self.total_nodes,
            "active_nodes": self.active_nodes,
            "degraded_nodes": self.degraded_nodes,
            "unreachable_nodes": self.unreachable_nodes,
            "total_brains": self.total_brains,
            "local_brains": self.local_brains,
            "remote_brains": self.remote_brains,
            "total_capabilities": self.total_capabilities,
            "unique_capabilities": self.unique_capabilities,
            "active_missions": self.active_missions,
            "completed_missions": self.completed_missions,
            "failed_missions": self.failed_missions,
            "failover_count": self.failover_count,
            "consensus_count": self.consensus_count,
            "average_node_health": round(self.average_node_health, 2),
            "average_network_latency": round(self.average_network_latency, 2),
            "cluster_utilization": round(self.cluster_utilization, 3),
            "last_updated": self.last_updated,
        }
