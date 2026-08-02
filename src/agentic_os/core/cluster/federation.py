"""Phase 16 — ClusterFederationManager.

Discovers remote AgenticOS nodes, maintains cluster membership, runs
heartbeats, and synchronizes node metadata.

The federation manager is purely additive — it does NOT replace
LocalDiscoveryService (which discovers local runtimes) or BrainRegistry
(which remains canonical for local brains). Instead, it:

  1. Maintains a list of known remote nodes (NodeInfo)
  2. Periodically checks node health (heartbeat)
  3. Publishes cluster.* events on the existing EventBus
  4. Coordinates with DistributedBrainRegistry to sync remote brains

In a single-node deployment, the federation manager still runs but
only contains the local node — fully backward compatible.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from agentic_os.core.cluster.domain import (
    NodeInfo,
    NodeRole,
    NodeStatus,
)
from agentic_os.core.cluster.topology import ClusterTopology
from agentic_os.infrastructure.logging import get_logger

if TYPE_CHECKING:
    from agentic_os.ports.event_bus import EventBus

log = get_logger("cluster.federation")

# Default heartbeat interval. In production this would be configurable
# via Settings; for now we hard-code a sensible default.
_DEFAULT_HEARTBEAT_INTERVAL = 30.0
_DEFAULT_STALE_TIMEOUT = 90.0  # 3 missed heartbeats
_DEFAULT_DISCOVERY_INTERVAL = 60.0


class ClusterFederationManager:
    """Top-level cluster coordinator.

    Owns the ClusterTopology + heartbeat loop + discovery loop.
    Pure consumer of EventBus — publishes cluster.* events but does
    not subscribe to brain.* or mission.* (that's the controller's job).
    """

    def __init__(
        self,
        bus: EventBus,
        cluster_id: str = "default",
        local_node_id: str = "",
        local_host: str = "localhost",
        local_port: int = 8000,
        local_base_url: str = "http://localhost:8000",
        version: str = "1.0.0",
    ) -> None:
        self._bus = bus
        self._cluster_id = cluster_id
        self._local_node_id = local_node_id or f"node-{local_host}-{local_port}"
        self._version = version
        self._topology = ClusterTopology(cluster_id=cluster_id)
        self._started = False
        self._heartbeat_task: asyncio.Task | None = None
        self._discovery_task: asyncio.Task | None = None
        self._known_remote_urls: set[str] = set()
        self._stats: dict[str, int] = {
            "nodes_joined": 0,
            "nodes_left": 0,
            "heartbeats_sent": 0,
            "heartbeats_received": 0,
            "discoveries_run": 0,
        }

        # Auto-register the local node
        local_node = NodeInfo(
            id=self._local_node_id,
            host=local_host,
            port=local_port,
            base_url=local_base_url,
            display_name=f"local ({local_host}:{local_port})",
            status=NodeStatus.ACTIVE,
            role=NodeRole.LEADER,  # local node is leader in single-node mode
            is_local=True,
            version=version,
            cluster_id=cluster_id,
        )
        self._topology.add_node(local_node)
        self._topology.set_leader(self._local_node_id)

    # ── Properties ─────────────────────────────────────────────────

    @property
    def topology(self) -> ClusterTopology:
        return self._topology

    @property
    def local_node_id(self) -> str:
        return self._local_node_id

    @property
    def cluster_id(self) -> str:
        return self._cluster_id

    @property
    def is_leader(self) -> bool:
        return self._topology.leader_id == self._local_node_id

    @property
    def stats(self) -> dict[str, int]:
        return dict(self._stats)

    # ── Lifecycle ──────────────────────────────────────────────────

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        # Start background heartbeat + discovery loops
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        self._discovery_task = asyncio.create_task(self._discovery_loop())
        await self._publish("cluster.started", self._topology.snapshot().to_dict())
        await self._publish("cluster.topology.updated", self._topology.stats())
        log.info(
            "ClusterFederationManager started (cluster=%s, local=%s)",
            self._cluster_id,
            self._local_node_id,
        )

    async def stop(self) -> None:
        self._started = False
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except (asyncio.CancelledError, Exception):
                pass
            self._heartbeat_task = None
        if self._discovery_task is not None:
            self._discovery_task.cancel()
            try:
                await self._discovery_task
            except (asyncio.CancelledError, Exception):
                pass
            self._discovery_task = None
        log.info("ClusterFederationManager stopped")

    # ── Node Membership ────────────────────────────────────────────

    async def add_remote_node(
        self,
        node_id: str,
        host: str,
        port: int,
        base_url: str = "",
        display_name: str = "",
        version: str = "1.0.0",
        metadata: dict[str, Any] | None = None,
    ) -> NodeInfo:
        """Register a remote node. Triggers cluster.node.joined event."""
        if not base_url:
            base_url = f"http://{host}:{port}"
        if not display_name:
            display_name = f"{host}:{port}"
        node = NodeInfo(
            id=node_id,
            host=host,
            port=port,
            base_url=base_url,
            display_name=display_name,
            status=NodeStatus.JOINING,
            role=NodeRole.FOLLOWER,
            is_local=False,
            version=version,
            cluster_id=self._cluster_id,
            metadata=dict(metadata or {}),
        )
        self._topology.add_node(node)
        self._stats["nodes_joined"] += 1
        await self._publish(
            "cluster.node.joined",
            node.to_dict(),
        )
        await self._publish("cluster.topology.updated", self._topology.stats())
        log.info("Remote node joined: %s (%s:%s)", node_id, host, port)
        return node

    async def remove_node(self, node_id: str, reason: str = "") -> bool:
        """Remove a node. Triggers cluster.node.left event."""
        node = self._topology.get_node(node_id)
        if node is None:
            return False
        self._topology.mark_node_status(node_id, NodeStatus.LEFT)
        await self._publish(
            "cluster.node.left",
            {"node_id": node_id, "reason": reason, "node": node.to_dict()},
        )
        self._topology.remove_node(node_id)
        self._stats["nodes_left"] += 1
        await self._publish("cluster.topology.updated", self._topology.stats())
        log.info("Node left: %s (reason: %s)", node_id, reason)
        return True

    async def update_node_heartbeat(
        self,
        node_id: str,
        metrics: dict[str, Any],
    ) -> bool:
        """Process a heartbeat from a remote node."""
        success = self._topology.update_heartbeat(
            node_id,
            brain_count=metrics.get("brain_count"),
            capability_count=metrics.get("capability_count"),
            active_missions=metrics.get("active_missions"),
            cpu_usage=metrics.get("cpu_usage"),
            memory_usage=metrics.get("memory_usage"),
            disk_usage=metrics.get("disk_usage"),
            network_latency_ms=metrics.get("network_latency_ms"),
            bandwidth_mbps=metrics.get("bandwidth_mbps"),
            health_score=metrics.get("health_score"),
            issues=metrics.get("issues"),
        )
        if success:
            self._stats["heartbeats_received"] += 1
            node = self._topology.get_node(node_id)
            if node is not None:
                await self._publish("cluster.node.updated", node.to_dict())
                await self._publish("cluster.topology.updated", self._topology.stats())
        return success

    # ── Discovery ──────────────────────────────────────────────────

    def register_remote_url(self, url: str) -> None:
        """Register a remote AgenticOS URL for discovery.

        The discovery loop will periodically attempt to contact these
        URLs and add them as nodes if reachable.
        """
        self._known_remote_urls.add(url.rstrip("/"))

    async def discover_nodes(self) -> list[NodeInfo]:
        """Manually trigger node discovery.

        In a real deployment this would do HTTP probes against
        ``self._known_remote_urls``. For Phase 16 we keep it pure:
        discovery is driven by explicit ``add_remote_node()`` calls
        from the API or other controllers. This method returns the
        current node list so callers can verify membership.
        """
        self._stats["discoveries_run"] += 1
        nodes = self._topology.list_nodes()
        await self._publish(
            "cluster.updated",
            {"node_count": len(nodes), "discoveries_run": self._stats["discoveries_run"]},
        )
        return nodes

    # ── Leader Election ────────────────────────────────────────────

    async def elect_leader(self, candidates: list[str] | None = None) -> str | None:
        """Elect a new leader.

        Strategy: pick the active node with the highest health_score.
        If ``candidates`` is provided, only consider those node IDs.
        Ties are broken by node_id (deterministic).
        """
        all_nodes = self._topology.list_nodes(status=NodeStatus.ACTIVE)
        if candidates:
            candidate_set = set(candidates)
            all_nodes = [n for n in all_nodes if n.id in candidate_set]
        if not all_nodes:
            return None
        # Sort by (health_score desc, brain_count desc, node_id asc) — deterministic
        all_nodes.sort(key=lambda n: (-n.health_score, -n.brain_count, n.id))
        new_leader = all_nodes[0]
        if self._topology.set_leader(new_leader.id):
            await self._publish(
                "cluster.node.updated",
                new_leader.to_dict(),
            )
            await self._publish("cluster.topology.updated", self._topology.stats())
            log.info("Elected leader: %s", new_leader.id)
            return new_leader.id
        return None

    # ── Background Loops ───────────────────────────────────────────

    async def _heartbeat_loop(self) -> None:
        """Periodically send heartbeats + check for stale nodes."""
        while self._started:
            try:
                await asyncio.sleep(_DEFAULT_HEARTBEAT_INTERVAL)
                if not self._started:
                    break
                await self._send_heartbeats()
                await self._check_stale_nodes()
            except asyncio.CancelledError:
                break
            except Exception:
                log.exception("Heartbeat loop error")

    async def _discovery_loop(self) -> None:
        """Periodically re-discover nodes."""
        while self._started:
            try:
                await asyncio.sleep(_DEFAULT_DISCOVERY_INTERVAL)
                if not self._started:
                    break
                await self.discover_nodes()
            except asyncio.CancelledError:
                break
            except Exception:
                log.exception("Discovery loop error")

    async def _send_heartbeats(self) -> None:
        """Emit a heartbeat event for the local node.

        In a real federation this would POST to each remote node's
        /api/cluster/heartbeat endpoint. Here we just publish the
        event so other components (and tests) can observe it.
        """
        self._stats["heartbeats_sent"] += 1
        local = self._topology.get_node(self._local_node_id)
        if local is None:
            return
        await self._publish(
            "cluster.updated",
            {
                "heartbeat_from": self._local_node_id,
                "timestamp": local.last_heartbeat,
            },
        )

    async def _check_stale_nodes(self) -> None:
        """Mark nodes with stale heartbeats as unreachable."""
        from datetime import UTC, datetime, timedelta

        cutoff = datetime.now(UTC) - timedelta(seconds=_DEFAULT_STALE_TIMEOUT)
        for node in self._topology.list_nodes():
            if node.is_local:
                continue
            try:
                last = datetime.fromisoformat(node.last_heartbeat)
            except (ValueError, TypeError):
                continue
            if last < cutoff and node.status != NodeStatus.UNREACHABLE:
                self._topology.mark_node_status(node.id, NodeStatus.UNREACHABLE)
                await self._publish(
                    "cluster.node.updated",
                    node.to_dict(),
                )
                log.warning("Node %s marked unreachable (stale heartbeat)", node.id)

    # ── Queries ────────────────────────────────────────────────────

    def list_nodes(self) -> list[NodeInfo]:
        return self._topology.list_nodes()

    def get_node(self, node_id: str) -> NodeInfo | None:
        return self._topology.get_node(node_id)

    def dashboard(self) -> dict[str, Any]:
        snap = self._topology.snapshot()
        return {
            "cluster_id": self._cluster_id,
            "local_node_id": self._local_node_id,
            "is_leader": self.is_leader,
            "topology": snap.to_dict(),
            "stats": dict(self._stats),
        }

    # ── Internal ───────────────────────────────────────────────────

    async def _publish(self, topic: str, payload: dict[str, Any]) -> None:
        try:
            from agentic_os.domain.events import EventEnvelope

            await self._bus.publish(
                EventEnvelope(
                    type=topic,
                    source="cluster.federation",
                    topic=topic,
                    payload=payload,
                )
            )
        except Exception:
            log.exception("Failed to publish %s", topic)
