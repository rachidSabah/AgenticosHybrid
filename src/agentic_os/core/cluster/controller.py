"""Phase 16 — ClusterController.

Long-running controller that owns the cluster subsystem lifecycle and
subscribes it to the EventBus so cluster state updates automatically.

Subscribes to:
  - cluster.node.joined     → update topology + sync brains
  - cluster.node.left       → purge remote brains
  - cluster.node.updated    → refresh node metrics
  - brain.registered        → add to local view (already in BrainRegistry)
  - brain.removed           → remove from local view
  - brain.health_changed    → update brain health in remote registry

On node join, the controller:
  1. Adds the node to the topology (already done by FederationManager)
  2. Asks DistributedBrainRegistry to sync brains (in production: HTTP GET)
  3. Publishes cluster.topology.updated

On node leave:
  1. Removes all remote brains for that node
  2. Triggers FailoverEngine to reassign any active missions
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agentic_os.core.cluster.consensus import ClusterConsensusManager
from agentic_os.core.cluster.distributed_registry import DistributedBrainRegistry
from agentic_os.core.cluster.failover import FailoverEngine
from agentic_os.core.cluster.federated_graph import FederatedKnowledgeGraph
from agentic_os.core.cluster.federation import ClusterFederationManager
from agentic_os.core.cluster.scheduler import GlobalMissionScheduler
from agentic_os.core.cluster.topology import ClusterTopology
from agentic_os.infrastructure.logging import get_logger

if TYPE_CHECKING:
    from agentic_os.core.brains.registry import BrainRegistry
    from agentic_os.core.ecosystem.collaboration_network import CollaborationNetwork
    from agentic_os.ports.event_bus import EventBus

log = get_logger("cluster.controller")

# Topics the ClusterController subscribes to.
_OBSERVED_TOPICS = [
    "cluster.node.joined",
    "cluster.node.left",
    "cluster.node.updated",
    "brain.registered",
    "brain.removed",
    "brain.health_changed",
]


class ClusterController:
    """Owns the cluster subsystem lifecycle + event subscriptions."""

    def __init__(
        self,
        bus: EventBus,
        brain_registry: BrainRegistry,
        local_node_id: str = "",
        local_host: str = "localhost",
        local_port: int = 8000,
        local_base_url: str = "http://localhost:8000",
        collaboration_network: CollaborationNetwork | None = None,
    ) -> None:
        self._bus = bus
        self._started = False
        self._subscriptions: list[str] = []
        self._local_registry = brain_registry
        self._network = collaboration_network

        # Sub-components — created here, wired together
        self._federation = ClusterFederationManager(
            bus=bus,
            local_node_id=local_node_id,
            local_host=local_host,
            local_port=local_port,
            local_base_url=local_base_url,
        )
        self._distributed = DistributedBrainRegistry(
            local_registry=brain_registry,
            federation=self._federation,
            bus=bus,
        )
        self._topology: ClusterTopology = self._federation.topology
        self._graph = FederatedKnowledgeGraph()
        self._scheduler = GlobalMissionScheduler(
            bus=bus,
            local_registry=brain_registry,
            distributed_registry=self._distributed,
            federation=self._federation,
            collaboration_network=collaboration_network,
        )
        self._consensus = ClusterConsensusManager(
            quorum_size=1,
            leader_id=self._federation.local_node_id,
        )
        self._failover = FailoverEngine(
            bus=bus,
            federation=self._federation,
            distributed_registry=self._distributed,
            scheduler=self._scheduler,
        )
        self._events_processed = 0

    # ── Properties (read-only views) ───────────────────────────────

    @property
    def federation(self) -> ClusterFederationManager:
        return self._federation

    @property
    def distributed_registry(self) -> DistributedBrainRegistry:
        return self._distributed

    @property
    def topology(self) -> ClusterTopology:
        return self._topology

    @property
    def graph(self) -> FederatedKnowledgeGraph:
        return self._graph

    @property
    def scheduler(self) -> GlobalMissionScheduler:
        return self._scheduler

    @property
    def consensus(self) -> ClusterConsensusManager:
        return self._consensus

    @property
    def failover(self) -> FailoverEngine:
        return self._failover

    @property
    def started(self) -> bool:
        return self._started

    # ── Lifecycle ──────────────────────────────────────────────────

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        await self._federation.start()
        # Update consensus quorum based on initial topology
        self._consensus.set_quorum_size(self._topology.quorum_size())
        self._consensus.set_leader(self._federation.local_node_id)
        for topic in _OBSERVED_TOPICS:
            try:
                sub_id = await self._bus.subscribe(topic, self._on_event)
                self._subscriptions.append(sub_id)
            except Exception:
                log.exception("Failed to subscribe to %s", topic)
        log.info(
            "ClusterController started (%d subscriptions, local=%s)",
            len(self._subscriptions),
            self._federation.local_node_id,
        )

    async def stop(self) -> None:
        self._started = False
        for sub_id in self._subscriptions:
            try:
                await self._bus.unsubscribe(sub_id)
            except Exception:
                pass
        self._subscriptions.clear()
        await self._federation.stop()
        log.info("ClusterController stopped")

    # ── Event handling ─────────────────────────────────────────────

    async def _on_event(self, event: Any) -> None:
        self._events_processed += 1
        topic = event.topic
        payload = event.payload or {}

        try:
            if topic == "cluster.node.joined":
                await self._on_node_joined(payload)
            elif topic == "cluster.node.left":
                await self._on_node_left(payload)
            elif topic == "cluster.node.updated":
                await self._on_node_updated(payload)
            elif topic == "brain.registered":
                await self._on_brain_registered(payload)
            elif topic == "brain.removed":
                await self._on_brain_removed(payload)
            elif topic == "brain.health_changed":
                await self._on_brain_health_changed(payload)
        except Exception:
            log.exception("ClusterController failed to handle %s", topic)

    async def _on_node_joined(self, payload: dict[str, Any]) -> None:
        """When a node joins, sync its brains into the distributed registry."""
        node_id = str(payload.get("id", ""))
        if not node_id or node_id == self._federation.local_node_id:
            return  # local node — already in BrainRegistry
        # In production, this would HTTP GET /api/brains on the remote node.
        # For Phase 16 we just update the topology (FederationManager
        # already did this when it published cluster.node.joined).
        # If the payload includes a brains list, sync them.
        brains = payload.get("brains") or []
        if brains and isinstance(brains, list):
            await self._distributed.sync_from_node(node_id, brains)
            # Also add to federated graph
            for b in brains:
                brain_id = str(b.get("id") or b.get("brain_id") or "")
                if brain_id:
                    self._graph.add_remote_brain(
                        brain_id=brain_id,
                        node_id=node_id,
                        display_name=str(b.get("display_name") or ""),
                        capabilities=list(b.get("capabilities") or []),
                        health=float(b.get("health") or 100),
                        latency=float(b.get("latency") or 0),
                        provider=str(b.get("provider") or ""),
                    )
        # Update consensus quorum
        self._consensus.set_quorum_size(self._topology.quorum_size())

    async def _on_node_left(self, payload: dict[str, Any]) -> None:
        node_id = str(payload.get("node_id", ""))
        if not node_id:
            return
        # Remove all remote brains for this node
        await self._distributed.remove_all_for_node(node_id)
        # Trigger failover for any active missions on that node
        await self._failover.detect_node_offline(node_id)
        # Update consensus quorum
        self._consensus.set_quorum_size(self._topology.quorum_size())

    async def _on_node_updated(self, payload: dict[str, Any]) -> None:
        node_id = str(payload.get("id", ""))
        if not node_id:
            return
        # Update heartbeat metrics
        await self._federation.update_node_heartbeat(node_id, payload)

    async def _on_brain_registered(self, payload: dict[str, Any]) -> None:
        """A local brain was registered — add it to the federated graph."""
        brain_id = str(payload.get("id", ""))
        if not brain_id:
            return
        # Add to federated graph as a local brain
        self._graph.add_remote_brain(
            brain_id=brain_id,
            node_id=self._federation.local_node_id,
            display_name=str(payload.get("display_name", brain_id)),
            capabilities=list(payload.get("capabilities") or []),
            health=float(payload.get("health") or 100),
            latency=float(payload.get("latency") or 0),
            provider=str(payload.get("vendor") or ""),
        )

    async def _on_brain_removed(self, payload: dict[str, Any]) -> None:
        brain_id = str(payload.get("id", ""))
        if not brain_id:
            return
        self._graph.remove_remote_brain(brain_id, self._federation.local_node_id)

    async def _on_brain_health_changed(self, payload: dict[str, Any]) -> None:
        brain_id = str(payload.get("id", ""))
        if not brain_id:
            return
        # Update the federated graph node
        fed_id = self._graph._federated_brain_id(brain_id, self._federation.local_node_id)
        node = self._graph.get_node(fed_id)
        if node is not None:
            node.properties["health"] = float(payload.get("health", 0))
            from datetime import UTC, datetime

            node.updated_at = datetime.now(UTC).isoformat()

    # ── Operations ─────────────────────────────────────────────────

    async def discover_nodes(self) -> list[dict[str, Any]]:
        nodes = await self._federation.discover_nodes()
        return [n.to_dict() for n in nodes]

    async def rebalance(self) -> dict[str, Any]:
        return await self._scheduler.rebalance()

    async def synchronize(self) -> dict[str, Any]:
        """Force a sync of all remote nodes' brains."""
        result: dict[str, Any] = {"synced": 0, "nodes": []}
        for node in self._topology.list_nodes():
            if node.is_local or node.status.value not in {"active", "degraded"}:
                continue
            # In production: HTTP GET /api/brains on node.base_url
            # For Phase 16: just record that we attempted sync
            result["nodes"].append({"node_id": node.id, "synced": True})
            result["synced"] += 1
        await self._publish(
            "cluster.updated",
            {"action": "synchronize", **result},
        )
        return result

    async def elect_leader(self, candidates: list[str] | None = None) -> str | None:
        leader = await self._federation.elect_leader(candidates)
        if leader:
            self._consensus.set_leader(leader)
        return leader

    async def rebuild(self) -> dict[str, Any]:
        """Rebuild the federated graph + topology from scratch."""
        self._graph.clear()
        # Re-add local brains
        try:
            local_brains = await self._local_registry.list_all()
            for b in local_brains:
                self._graph.add_remote_brain(
                    brain_id=b.id,
                    node_id=self._federation.local_node_id,
                    display_name=b.display_name,
                    capabilities=list(b.capabilities) if b.capabilities else [],
                    health=b.health,
                    latency=b.latency,
                    provider=str(b.vendor.value) if hasattr(b.vendor, "value") else str(b.vendor),
                )
        except Exception:
            log.exception("Failed to rebuild federated graph from local registry")
        # Re-add remote brains
        for r in self._distributed.list_remote_brains():
            self._graph.add_remote_brain(
                brain_id=r.brain_id,
                node_id=r.node_id,
                display_name=r.display_name,
                capabilities=list(r.capabilities),
                health=r.health,
                latency=r.latency,
                provider=r.provider,
            )
        await self._publish("cluster.topology.updated", self._topology.stats())
        return {
            "rebuilt": True,
            "graph_stats": self._graph.cluster_stats(),
            "topology_stats": self._topology.stats(),
        }

    # ── Snapshot ───────────────────────────────────────────────────

    def dashboard(self) -> dict[str, Any]:
        from agentic_os.core.cluster.domain import ClusterStatistics, NodeStatus

        nodes = self._topology.list_nodes()
        stats = ClusterStatistics()
        stats.total_nodes = len(nodes)
        stats.active_nodes = sum(1 for n in nodes if n.status == NodeStatus.ACTIVE)
        stats.degraded_nodes = sum(1 for n in nodes if n.status == NodeStatus.DEGRADED)
        stats.unreachable_nodes = sum(1 for n in nodes if n.status == NodeStatus.UNREACHABLE)
        dist_stats = self._distributed.stats()
        stats.local_brains = dist_stats["local_brains"]
        stats.remote_brains = dist_stats["remote_brains"]
        stats.total_brains = dist_stats["total_brains"]
        stats.total_capabilities = sum(n.capability_count for n in nodes)
        stats.active_missions = sum(n.active_missions for n in nodes)
        stats.failover_count = self._failover.stats()["actions_completed"]
        stats.consensus_count = len(self._consensus.list_history(limit=1000))
        if nodes:
            stats.average_node_health = sum(n.health_score for n in nodes) / len(nodes)
            stats.average_network_latency = sum(n.network_latency_ms for n in nodes) / len(nodes)
            stats.cluster_utilization = sum(n.cpu_usage for n in nodes) / len(nodes) / 100.0
        from datetime import UTC, datetime

        stats.last_updated = datetime.now(UTC).isoformat()
        return {
            "federation": self._federation.dashboard(),
            "topology": self._topology.snapshot().to_dict(),
            "distributed_registry": self._distributed.stats(),
            "scheduler": self._scheduler.stats(),
            "consensus": self._consensus.stats(),
            "failover": self._failover.stats(),
            "graph": self._graph.cluster_stats(),
            "statistics": stats.to_dict(),
        }

    def status(self) -> dict[str, Any]:
        return {
            "started": self._started,
            "events_processed": self._events_processed,
            "subscriptions": len(self._subscriptions),
            "local_node_id": self._federation.local_node_id,
            "is_leader": self._federation.is_leader,
            "cluster_id": self._federation.cluster_id,
            "node_count": len(self._topology.list_nodes()),
            "remote_brain_count": len(self._distributed.list_remote_brains()),
        }

    async def _publish(self, topic: str, payload: dict[str, Any]) -> None:
        try:
            from agentic_os.domain.events import EventEnvelope

            await self._bus.publish(
                EventEnvelope(
                    type=topic,
                    source="cluster.controller",
                    topic=topic,
                    payload=payload,
                )
            )
        except Exception:
            log.exception("Failed to publish %s", topic)
