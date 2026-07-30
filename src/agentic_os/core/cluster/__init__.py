"""Phase 16 — Autonomous Distributed Runtime Federation & Multi-Host Intelligence.

Builds on the existing Phase 1-15 architecture:
  Discovery → EventBus → BrainRegistry → Executive/Cognitive/Swarm/Ecosystem
  → ClusterController (this layer) → DashboardBroadcaster → Store → UI

Components:
  - ClusterController: long-running controller (subscriptions + lifecycle)
  - ClusterFederationManager: remote node discovery, topology, heartbeat
  - DistributedBrainRegistry: extends BrainRegistry with remote brains
  - GlobalMissionScheduler: deterministic cluster-wide runtime selection
  - ClusterConsensusManager: majority/weighted/confidence/leader/quorum
  - FailoverEngine: detect failures + produce recovery actions
  - ClusterTopology: hosts/nodes/connections graph
  - FederatedKnowledgeGraph: extends CapabilityGraph with cross-host edges

All additive — reuses EventBus, BrainRegistry, CapabilityGraph, and
CollaborationNetwork as canonical sources. Single-node deployments
remain fully backward compatible (the local node is always present
and is the leader by default).
"""

from agentic_os.core.cluster.consensus import ClusterConsensusManager
from agentic_os.core.cluster.controller import ClusterController
from agentic_os.core.cluster.distributed_registry import DistributedBrainRegistry
from agentic_os.core.cluster.domain import (
    ClusterScore,
    ClusterStatistics,
    ClusterTopologySnapshot,
    ConsensusResult,
    ConsensusType,
    ConsensusVote,
    FailoverAction,
    FailoverActionType,
    FailoverTrigger,
    NodeConnection,
    NodeInfo,
    NodeRole,
    NodeStatus,
    RemoteBrainRecord,
)
from agentic_os.core.cluster.failover import FailoverEngine
from agentic_os.core.cluster.federated_graph import FederatedKnowledgeGraph
from agentic_os.core.cluster.federation import ClusterFederationManager
from agentic_os.core.cluster.scheduler import GlobalMissionScheduler
from agentic_os.core.cluster.topology import ClusterTopology

__all__ = [
    "ClusterConsensusManager",
    "ClusterController",
    "ClusterFederationManager",
    "ClusterScore",
    "ClusterStatistics",
    "ClusterTopology",
    "ClusterTopologySnapshot",
    "ConsensusResult",
    "ConsensusType",
    "ConsensusVote",
    "DistributedBrainRegistry",
    "FailoverAction",
    "FailoverActionType",
    "FailoverEngine",
    "FailoverTrigger",
    "FederatedKnowledgeGraph",
    "GlobalMissionScheduler",
    "NodeConnection",
    "NodeInfo",
    "NodeRole",
    "NodeStatus",
    "RemoteBrainRecord",
]
