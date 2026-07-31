"""Phase 17 — Distributed Execution Fabric & Cluster Orchestration.

Builds on the existing Phase 16 cluster/ package with:
  - Transport layer for inter-node HTTP communication
  - Distributed event propagation (cross-node EventBus)
  - Remote task execution (DistributedExecutor)
  - Heartbeat-based failure detection
  - Raft-like leader election with term tracking
  - State replication across nodes
  - Cluster-wide health aggregation

All additive — reuses Phase 16's ClusterFederationManager,
DistributedBrainRegistry, GlobalMissionScheduler, and
ClusterConsensusManager. Does NOT replace any existing implementation.
"""

from agentic_os.core.distributed.cluster_models import (
    ClusterHealthSnapshot,
    DistributedEvent,
    DistributedStatistics,
    DistributedTask,
    DistributedTaskStatus,
    HeartbeatPacket,
    HeartbeatStatus,
    LeaderElectionResult,
    LeaderElectionState,
    LeaderVote,
    NodeHealthSnapshot,
    ReplicationEntry,
    ReplicationEntryType,
    TaskAcknowledgement,
)
from agentic_os.core.distributed.distributed_controller import (
    ClusterHealth,
    DistributedController,
    Replication,
)
from agentic_os.core.distributed.distributed_executor import (
    ClusterScheduler,
    DistributedEventBus,
    DistributedExecutor,
)
from agentic_os.core.distributed.heartbeat_manager import HeartbeatManager
from agentic_os.core.distributed.node_registry import (
    LeaderElection,
    NodeRegistry,
)
from agentic_os.core.distributed.transport import NodeTransport

__all__ = [
    "ClusterHealth",
    "ClusterHealthSnapshot",
    "ClusterScheduler",
    "DistributedController",
    "DistributedEvent",
    "DistributedEventBus",
    "DistributedExecutor",
    "DistributedStatistics",
    "DistributedTask",
    "DistributedTaskStatus",
    "HeartbeatManager",
    "HeartbeatPacket",
    "HeartbeatStatus",
    "LeaderElection",
    "LeaderElectionResult",
    "LeaderElectionState",
    "LeaderVote",
    "NodeHealthSnapshot",
    "NodeRegistry",
    "NodeTransport",
    "Replication",
    "ReplicationEntry",
    "ReplicationEntryType",
    "TaskAcknowledgement",
]
