"""Phase 16 — ClusterTopology.

Live graph of hosts/nodes/connections. Maintains:

  - NodeInfo per AgenticOS instance (local + remote)
  - NodeConnection between every pair (latency, bandwidth, healthy)
  - Leader/quorum tracking
  - Aggregate cluster health

Pure in-memory. Does NOT publish discovery events and is NOT a second
source of truth for runtime data (BrainRegistry remains canonical).

The topology is updated by:
  - ClusterFederationManager (node join/leave/heartbeat)
  - FailoverEngine (node marked unreachable)
  - Leader election (role changes)
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from agentic_os.core.cluster.domain import (
    ClusterTopologySnapshot,
    NodeConnection,
    NodeInfo,
    NodeRole,
    NodeStatus,
)
from agentic_os.infrastructure.logging import get_logger

log = get_logger("cluster.topology")


class ClusterTopology:
    """In-memory cluster topology graph."""

    def __init__(self, cluster_id: str = "default") -> None:
        self._cluster_id = cluster_id
        self._nodes: dict[str, NodeInfo] = {}
        self._connections: dict[str, NodeConnection] = {}
        self._leader_id: str = ""
        self._updates_count = 0

    # ── Node CRUD ──────────────────────────────────────────────────

    def add_node(self, node: NodeInfo) -> NodeInfo:
        """Add or update a node. Existing nodes are merged."""
        existing = self._nodes.get(node.id)
        if existing is not None:
            # Preserve role/leader status across updates
            node.role = existing.role
            if existing.is_local:
                node.is_local = True
            node.started_at = existing.started_at
        self._nodes[node.id] = node
        # Auto-create connections to every other node
        for other_id in self._nodes:
            if other_id == node.id:
                continue
            self._ensure_connection(node.id, other_id)
            self._ensure_connection(other_id, node.id)
        self._updates_count += 1
        return node

    def remove_node(self, node_id: str) -> bool:
        if node_id not in self._nodes:
            return False
        del self._nodes[node_id]
        # Cascade-remove connections touching this node
        for key in list(self._connections.keys()):
            conn = self._connections[key]
            if conn.source == node_id or conn.target == node_id:
                del self._connections[key]
        if self._leader_id == node_id:
            self._leader_id = ""
        self._updates_count += 1
        return True

    def get_node(self, node_id: str) -> NodeInfo | None:
        return self._nodes.get(node_id)

    def list_nodes(self, status: NodeStatus | str | None = None) -> list[NodeInfo]:
        if status is None:
            return list(self._nodes.values())
        if isinstance(status, str):
            status = NodeStatus(status)
        return [n for n in self._nodes.values() if n.status == status]

    # ── Connection CRUD ────────────────────────────────────────────

    def _ensure_connection(self, source: str, target: str) -> NodeConnection:
        key = f"{source}->{target}"
        if key not in self._connections:
            self._connections[key] = NodeConnection(source=source, target=target)
        return self._connections[key]

    def update_connection(
        self,
        source: str,
        target: str,
        latency_ms: float | None = None,
        bandwidth_mbps: float | None = None,
        healthy: bool | None = None,
    ) -> NodeConnection | None:
        conn = self._ensure_connection(source, target)
        if latency_ms is not None:
            conn.latency_ms = latency_ms
        if bandwidth_mbps is not None:
            conn.bandwidth_mbps = bandwidth_mbps
        if healthy is not None:
            conn.healthy = healthy
        from datetime import UTC, datetime

        conn.last_checked = datetime.now(UTC).isoformat()
        self._updates_count += 1
        return conn

    def list_connections(self) -> list[NodeConnection]:
        return list(self._connections.values())

    # ── Leader / Quorum ────────────────────────────────────────────

    @property
    def leader_id(self) -> str:
        return self._leader_id

    def set_leader(self, node_id: str) -> bool:
        if node_id not in self._nodes:
            return False
        # Demote previous leader
        for n in self._nodes.values():
            if n.role == NodeRole.LEADER:
                n.role = NodeRole.FOLLOWER
        self._nodes[node_id].role = NodeRole.LEADER
        self._leader_id = node_id
        self._updates_count += 1
        return True

    def quorum_size(self) -> int:
        """Quorum = majority of active+degraded nodes."""
        eligible = [
            n for n in self._nodes.values() if n.status in {NodeStatus.ACTIVE, NodeStatus.DEGRADED}
        ]
        return (len(eligible) // 2) + 1

    def has_quorum(self, voter_count: int) -> bool:
        return voter_count >= self.quorum_size()

    # ── Mark node status ───────────────────────────────────────────

    def mark_node_status(self, node_id: str, status: NodeStatus) -> bool:
        node = self._nodes.get(node_id)
        if node is None:
            return False
        node.status = status
        self._updates_count += 1
        return True

    def update_heartbeat(
        self,
        node_id: str,
        *,
        brain_count: int | None = None,
        capability_count: int | None = None,
        active_missions: int | None = None,
        cpu_usage: float | None = None,
        memory_usage: float | None = None,
        disk_usage: float | None = None,
        network_latency_ms: float | None = None,
        bandwidth_mbps: float | None = None,
        health_score: float | None = None,
        issues: list[str] | None = None,
    ) -> bool:
        node = self._nodes.get(node_id)
        if node is None:
            return False
        from datetime import UTC, datetime

        node.last_heartbeat = datetime.now(UTC).isoformat()
        if brain_count is not None:
            node.brain_count = brain_count
        if capability_count is not None:
            node.capability_count = capability_count
        if active_missions is not None:
            node.active_missions = active_missions
        if cpu_usage is not None:
            node.cpu_usage = cpu_usage
        if memory_usage is not None:
            node.memory_usage = memory_usage
        if disk_usage is not None:
            node.disk_usage = disk_usage
        if network_latency_ms is not None:
            node.network_latency_ms = network_latency_ms
        if bandwidth_mbps is not None:
            node.bandwidth_mbps = bandwidth_mbps
        if health_score is not None:
            node.health_score = health_score
        if issues is not None:
            node.issues = list(issues)
        # Auto-promote/demote based on health
        if node.status == NodeStatus.JOINING and node.health_score >= 50:
            node.status = NodeStatus.ACTIVE
        elif node.status == NodeStatus.ACTIVE and node.health_score < 50:
            node.status = NodeStatus.DEGRADED
        self._updates_count += 1
        return True

    # ── Snapshot ───────────────────────────────────────────────────

    def snapshot(self) -> ClusterTopologySnapshot:
        nodes = list(self._nodes.values())
        total_brains = sum(n.brain_count for n in nodes)
        total_caps = sum(n.capability_count for n in nodes)
        total_missions = sum(n.active_missions for n in nodes)
        if nodes:
            avg_health = sum(n.health_score for n in nodes) / len(nodes)
        else:
            avg_health = 0.0
        return ClusterTopologySnapshot(
            cluster_id=self._cluster_id,
            nodes=nodes,
            connections=list(self._connections.values()),
            leader_id=self._leader_id,
            quorum_size=self.quorum_size(),
            total_brains=total_brains,
            total_capabilities=total_caps,
            total_active_missions=total_missions,
            cluster_health=avg_health / 100.0,
            last_updated=datetime.now(UTC).isoformat(),
        )

    def stats(self) -> dict[str, Any]:
        nodes = list(self._nodes.values())
        return {
            "total_nodes": len(nodes),
            "active": sum(1 for n in nodes if n.status == NodeStatus.ACTIVE),
            "degraded": sum(1 for n in nodes if n.status == NodeStatus.DEGRADED),
            "unreachable": sum(1 for n in nodes if n.status == NodeStatus.UNREACHABLE),
            "connections": len(self._connections),
            "leader_id": self._leader_id,
            "quorum_size": self.quorum_size(),
            "updates_count": self._updates_count,
        }

    def to_dict(self) -> dict[str, Any]:
        snap = self.snapshot()
        return {**snap.to_dict(), "stats": self.stats()}

    def clear(self) -> None:
        self._nodes.clear()
        self._connections.clear()
        self._leader_id = ""
        self._updates_count += 1
