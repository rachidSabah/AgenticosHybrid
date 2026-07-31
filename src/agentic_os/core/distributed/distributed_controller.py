"""Phase 17 — Replication + ClusterHealth + DistributedController.

Replication: replicates state entries (brain registry, mission state,
  evolution proposals) across the cluster via the transport layer.

ClusterHealth: aggregates per-node health snapshots into a cluster-wide
  health view. Extends Phase 16's basic health with heartbeat-driven
  liveness data.

DistributedController: top-level controller that owns the lifecycle of
  all distributed/ components and wires them into the kernel.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from agentic_os.core.distributed.cluster_models import (
    ClusterHealthSnapshot,
    DistributedStatistics,
    DistributedTask,
    DistributedTaskStatus,
    NodeHealthSnapshot,
    ReplicationEntry,
    ReplicationEntryType,
)
from agentic_os.core.distributed.distributed_executor import (
    ClusterScheduler,
    DistributedEventBus,
    DistributedExecutor,
)
from agentic_os.core.distributed.heartbeat_manager import HeartbeatManager
from agentic_os.core.distributed.node_registry import LeaderElection, NodeRegistry
from agentic_os.core.distributed.transport import NodeTransport
from agentic_os.infrastructure.logging import get_logger

if TYPE_CHECKING:
    from agentic_os.core.cluster.federation import ClusterFederationManager
    from agentic_os.ports.event_bus import EventBus

log = get_logger("distributed.controller")


class Replication:
    """Replicates state entries across the cluster."""

    def __init__(
        self,
        transport: NodeTransport,
        local_node_id: str = "",
    ) -> None:
        self._transport = transport
        self._local_node_id = local_node_id
        self._entries: dict[str, ReplicationEntry] = {}  # key → entry
        self._received: dict[str, ReplicationEntry] = {}  # key → received entry
        self._stats: dict[str, int] = {
            "entries_created": 0,
            "entries_replicated": 0,
            "entries_received": 0,
            "replication_failures": 0,
        }

    @property
    def stats(self) -> dict[str, Any]:
        return dict(self._stats)

    def list_entries(self, limit: int = 50) -> list[ReplicationEntry]:
        return list(self._entries.values())[-limit:]

    async def replicate(
        self,
        key: str,
        value: dict[str, Any],
        entry_type: ReplicationEntryType = ReplicationEntryType.BRAIN_REGISTRY,
    ) -> int:
        """Create a replication entry and propagate to peers. Returns count of peers reached."""
        existing = self._entries.get(key)
        version = (existing.version + 1) if existing else 0

        entry = ReplicationEntry(
            entry_type=entry_type,
            source_node_id=self._local_node_id,
            key=key,
            value=value,
            version=version,
        )
        self._entries[key] = entry
        self._stats["entries_created"] += 1

        peers = self._transport.list_peers()
        if not peers:
            return 0

        results = await asyncio.gather(
            *[self._transport.replicate_state(pid, entry.to_dict()) for pid in peers],
            return_exceptions=True,
        )
        delivered = sum(1 for r in results if r is True)
        entry.replicated_to = [pid for pid, r in zip(peers, results, strict=False) if r is True]
        self._stats["entries_replicated"] += delivered
        if delivered < len(peers):
            self._stats["replication_failures"] += len(peers) - delivered
        return delivered

    def receive_replication(self, entry_data: dict[str, Any]) -> bool:
        """Receive a replicated state entry from a peer."""
        try:
            entry_type_str = str(entry_data.get("entry_type", "brain_registry"))
            entry_type = ReplicationEntryType(entry_type_str)
        except ValueError:
            entry_type = ReplicationEntryType.BRAIN_REGISTRY

        entry = ReplicationEntry(
            entry_type=entry_type,
            source_node_id=str(entry_data.get("source_node_id", "")),
            key=str(entry_data.get("key", "")),
            value=dict(entry_data.get("value", {})),
            version=int(entry_data.get("version", 0)),
            timestamp=str(entry_data.get("timestamp", "")),
        )

        existing = self._received.get(entry.key)
        if existing and existing.version >= entry.version:
            return False  # stale

        self._received[entry.key] = entry
        self._stats["entries_received"] += 1
        return True


class ClusterHealth:
    """Aggregates per-node health into a cluster-wide snapshot."""

    def __init__(self, heartbeat_manager: HeartbeatManager | None = None) -> None:
        self._heartbeat = heartbeat_manager
        self._node_metrics: dict[str, NodeHealthSnapshot] = {}
        self._last_snapshot: ClusterHealthSnapshot | None = None

    def update_node_metrics(self, node_id: str, metrics: dict[str, Any]) -> None:
        """Update metrics for a single node."""
        snapshot = self._node_metrics.get(node_id)
        if snapshot is None:
            snapshot = NodeHealthSnapshot(node_id=node_id)
            self._node_metrics[node_id] = snapshot
        snapshot.health_score = float(metrics.get("health_score", snapshot.health_score))
        snapshot.cpu_usage = float(metrics.get("cpu_usage", snapshot.cpu_usage))
        snapshot.memory_usage = float(metrics.get("memory_usage", snapshot.memory_usage))
        snapshot.brain_count = int(metrics.get("brain_count", snapshot.brain_count))
        snapshot.active_tasks = int(metrics.get("active_tasks", snapshot.active_tasks))
        snapshot.latency_ms = float(metrics.get("latency_ms", snapshot.latency_ms))
        snapshot.is_alive = bool(metrics.get("is_alive", snapshot.is_alive))

    def compute_snapshot(self, leader_id: str = "") -> ClusterHealthSnapshot:
        """Compute the cluster-wide health snapshot."""
        # Sync with heartbeat statuses
        if self._heartbeat is not None:
            for status in self._heartbeat.list_statuses():
                node_id = status.node_id
                if node_id not in self._node_metrics:
                    self._node_metrics[node_id] = NodeHealthSnapshot(node_id=node_id)
                self._node_metrics[node_id].is_alive = status.is_alive

        nodes = list(self._node_metrics.values())
        alive = [n for n in nodes if n.is_alive]
        dead = [n for n in nodes if not n.is_alive]

        snapshot = ClusterHealthSnapshot(
            total_nodes=len(nodes),
            alive_nodes=len(alive),
            dead_nodes=len(dead),
            avg_health=sum(n.health_score for n in nodes) / len(nodes) if nodes else 0,
            avg_cpu=sum(n.cpu_usage for n in nodes) / len(nodes) if nodes else 0,
            avg_memory=sum(n.memory_usage for n in nodes) / len(nodes) if nodes else 0,
            total_brains=sum(n.brain_count for n in nodes),
            total_active_tasks=sum(n.active_tasks for n in nodes),
            leader_id=leader_id,
            quorum_intact=len(alive) >= max(1, (len(nodes) // 2) + 1),
            node_health=dict(self._node_metrics),
            last_updated=datetime.now(UTC).isoformat(),
        )
        self._last_snapshot = snapshot
        return snapshot

    @property
    def last_snapshot(self) -> ClusterHealthSnapshot | None:
        return self._last_snapshot


class DistributedController:
    """Top-level controller for the distributed execution fabric.

    Owns the lifecycle of all distributed/ components and wires them
    into the kernel. Does NOT replace the existing ClusterController
    from Phase 16 — it extends it with transport + execution + propagation.
    """

    def __init__(
        self,
        bus: EventBus,
        local_node_id: str = "",
        local_base_url: str = "",
        federation: ClusterFederationManager | None = None,
    ) -> None:
        self._bus = bus
        self._local_node_id = local_node_id or "local"
        self._local_base_url = local_base_url
        self._federation = federation
        self._started = False
        self._subscriptions: list[str] = []

        # Components
        self._transport = NodeTransport(
            local_node_id=self._local_node_id,
            local_base_url=self._local_base_url,
        )
        self._heartbeat = HeartbeatManager(
            bus=bus,
            transport=self._transport,
            local_node_id=self._local_node_id,
        )
        self._node_registry = NodeRegistry(local_node_id=self._local_node_id)
        self._leader_election = LeaderElection(
            bus=bus,
            local_node_id=self._local_node_id,
            heartbeat_manager=self._heartbeat,
        )
        self._event_bus = DistributedEventBus(
            bus=bus,
            transport=self._transport,
            local_node_id=self._local_node_id,
        )
        self._executor = DistributedExecutor(
            bus=bus,
            transport=self._transport,
            local_node_id=self._local_node_id,
        )
        self._scheduler = ClusterScheduler(bus=bus, executor=self._executor)
        self._replication = Replication(
            transport=self._transport,
            local_node_id=self._local_node_id,
        )
        self._health = ClusterHealth(heartbeat_manager=self._heartbeat)
        self._statistics = DistributedStatistics()
        self._events_processed = 0

    # ── Properties ─────────────────────────────────────────────────

    @property
    def transport(self) -> NodeTransport:
        return self._transport

    @property
    def heartbeat(self) -> HeartbeatManager:
        return self._heartbeat

    @property
    def node_registry(self) -> NodeRegistry:
        return self._node_registry

    @property
    def leader_election(self) -> LeaderElection:
        return self._leader_election

    @property
    def event_bus(self) -> DistributedEventBus:
        return self._event_bus

    @property
    def executor(self) -> DistributedExecutor:
        return self._executor

    @property
    def scheduler(self) -> ClusterScheduler:
        return self._scheduler

    @property
    def replication(self) -> Replication:
        return self._replication

    @property
    def health(self) -> ClusterHealth:
        return self._health

    @property
    def started(self) -> bool:
        return self._started

    # ── Lifecycle ──────────────────────────────────────────────────

    async def start(self) -> None:
        if self._started:
            return
        self._started = True

        # Register self in node registry
        self._node_registry.register_join(
            node_id=self._local_node_id,
            base_url=self._local_base_url,
        )

        # Register default propagation topics
        for prefix in [
            "brain.",
            "mission.",
            "executive.",
            "cognitive.",
            "swarm.",
            "ecosystem.",
            "cluster.",
        ]:
            self._event_bus.register_propagation_prefix(prefix)

        # Start heartbeat manager
        await self._heartbeat.start()

        # Run initial leader election (single-node: self wins)
        result = self._leader_election.run_election()
        if result.winner_id:
            await self._publish(
                "node.leader.elected",
                result.to_dict(),
            )

        await self._publish(
            "distributed.started",
            {"node_id": self._local_node_id, "base_url": self._local_base_url},
        )

        log.info(
            "DistributedController started (node=%s, leader=%s)",
            self._local_node_id,
            self._leader_election.current_leader,
        )

    async def stop(self) -> None:
        self._started = False
        await self._heartbeat.stop()
        await self._transport.close()
        await self._publish(
            "distributed.stopped",
            {"node_id": self._local_node_id},
        )
        log.info("DistributedController stopped")

    # ── Operations ─────────────────────────────────────────────────

    async def join_cluster(self, peer_url: str, peer_node_id: str = "") -> dict[str, Any]:
        """Join a cluster by connecting to a peer node."""
        if not peer_node_id:
            peer_node_id = f"peer-{peer_url}"
        self._transport.register_peer(peer_node_id, peer_url)
        self._node_registry.register_join(
            node_id=peer_node_id,
            base_url=peer_url,
        )
        await self._publish(
            "node.joined",
            {"node_id": peer_node_id, "base_url": peer_url},
        )
        return {"joined": True, "peer_node_id": peer_node_id}

    async def leave_cluster(self, node_id: str, reason: str = "") -> dict[str, Any]:
        """Remove a node from the cluster."""
        self._transport.unregister_peer(node_id)
        self._node_registry.register_leave(node_id, reason)
        await self._publish(
            "node.left",
            {"node_id": node_id, "reason": reason},
        )
        return {"left": True, "node_id": node_id}

    async def dispatch_task(self, task: DistributedTask) -> bool:
        """Dispatch a distributed task."""
        return await self._scheduler.schedule_and_dispatch(task)

    async def elect_leader(self) -> dict[str, Any]:
        """Run leader election."""
        result = self._leader_election.run_election()
        await self._publish("node.leader.elected", result.to_dict())
        return result.to_dict()

    def get_cluster_health(self) -> dict[str, Any]:
        """Get cluster health snapshot."""
        snapshot = self._health.compute_snapshot(leader_id=self._leader_election.current_leader)
        return snapshot.to_dict()

    def dashboard(self) -> dict[str, Any]:
        """Combined dashboard for /api/distributed/dashboard."""
        health = self._health.compute_snapshot(leader_id=self._leader_election.current_leader)
        return {
            "local_node_id": self._local_node_id,
            "started": self._started,
            "leader_id": self._leader_election.current_leader,
            "leader_term": self._leader_election.current_term,
            "leader_state": self._leader_election.state.value,
            "transport": self._transport.stats,
            "heartbeat": self._heartbeat.stats,
            "node_registry": self._node_registry.stats,
            "leader_election": self._leader_election.stats,
            "event_bus": self._event_bus.stats,
            "executor": self._executor.stats,
            "scheduler": self._scheduler.stats,
            "replication": self._replication.stats,
            "health": health.to_dict(),
            "nodes": self._node_registry.list_nodes(),
            "peers": self._transport.list_peers(),
            "tasks": [t.to_dict() for t in self._executor.list_tasks()],
        }

    def status(self) -> dict[str, Any]:
        return {
            "started": self._started,
            "local_node_id": self._local_node_id,
            "leader_id": self._leader_election.current_leader,
            "leader_state": self._leader_election.state.value,
            "peer_count": len(self._transport.list_peers()),
            "active_tasks": len(self._executor.list_tasks(DistributedTaskStatus.EXECUTING)),
            "events_processed": self._events_processed,
        }

    # ── Internal ───────────────────────────────────────────────────

    async def _publish(self, topic: str, payload: dict[str, Any]) -> None:
        try:
            from agentic_os.domain.events import EventEnvelope

            await self._bus.publish(
                EventEnvelope(
                    type=topic,
                    source="distributed.controller",
                    topic=topic,
                    payload=payload,
                )
            )
        except Exception:
            log.exception("Failed to publish %s", topic)
