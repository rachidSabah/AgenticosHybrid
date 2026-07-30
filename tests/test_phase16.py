"""Tests for Phase 16 — Autonomous Distributed Runtime Federation & Multi-Host Intelligence.

Covers:
  - ClusterTopology node/connection CRUD + leader/quorum
  - ClusterFederationManager node join/leave/heartbeat/election
  - DistributedBrainRegistry remote brain CRUD + sync + unified view
  - GlobalMissionScheduler deterministic scoring + selection
  - ClusterConsensusManager all 5 consensus types
  - FailoverEngine detection + action production
  - FederatedKnowledgeGraph cross-host edges + impact analysis
  - ClusterController event subscriptions + node join/leave handling
  - REST API endpoints under /api/cluster/*
  - WebSocket propagation via DashboardBroadcaster
  - Mission reassignment + leader election + recovery workflow
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agentic_os.adapters.bus.local import LocalBus
from agentic_os.core.brains.registry import BrainRegistry
from agentic_os.core.cluster import (
    ClusterConsensusManager,
    ClusterController,
    ClusterFederationManager,
    ClusterTopology,
    ConsensusType,
    DistributedBrainRegistry,
    FailoverActionType,
    FailoverEngine,
    FailoverTrigger,
    FederatedKnowledgeGraph,
    GlobalMissionScheduler,
    NodeInfo,
    NodeRole,
    NodeStatus,
)
from agentic_os.core.ecosystem.collaboration_network import CollaborationNetwork
from agentic_os.domain.brains import (
    BrainRecord,
    BrainRuntime,
    BrainStatus,
    BrainType,
    BrainVendor,
)

# ── Fixtures ───────────────────────────────────────────────────────────


def make_brain(
    brain_id: str = "b1",
    name: str = "TestBrain",
    capabilities: tuple[str, ...] = ("chat",),
    health: float = 90.0,
    latency: float = 100.0,
) -> BrainRecord:
    return BrainRecord(
        id=brain_id,
        display_name=name,
        brain_type=BrainType.LOCAL_CLI,
        vendor=BrainVendor.OLLAMA,
        runtime=BrainRuntime.PYTHON,
        version="1.0.0",
        status=BrainStatus.CONNECTED,
        health=health,
        capabilities=capabilities,
        latency=latency,
    )


@pytest.fixture
async def bus():
    b = LocalBus()
    await b.start()
    yield b
    await b.stop()


@pytest.fixture
async def registry(bus):
    r = BrainRegistry()
    await r.start(event_bus=bus)
    yield r
    await r.stop()


@pytest.fixture
async def populated_registry(registry):
    await registry.register(make_brain("b1", "Alpha", ("chat", "code"), health=95, latency=50))
    await registry.register(make_brain("b2", "Beta", ("chat", "vision"), health=70, latency=200))
    await registry.register(make_brain("b3", "Gamma", ("code",), health=30, latency=2500))
    return registry


@pytest.fixture
def collaboration_network():
    return CollaborationNetwork()


@pytest.fixture
async def controller(bus, populated_registry, collaboration_network):
    cc = ClusterController(
        bus=bus,
        brain_registry=populated_registry,
        local_host="localhost",
        local_port=8000,
        collaboration_network=collaboration_network,
    )
    await cc.start()
    yield cc
    await cc.stop()


# ── ClusterTopology ────────────────────────────────────────────────────


class TestClusterTopology:
    def test_add_local_node(self):
        t = ClusterTopology()
        node = NodeInfo(id="n1", host="localhost", port=8000, is_local=True)
        t.add_node(node)
        assert t.get_node("n1") is not None
        assert len(t.list_nodes()) == 1

    def test_add_multiple_nodes_creates_connections(self):
        t = ClusterTopology()
        t.add_node(NodeInfo(id="n1", host="h1", port=8000))
        t.add_node(NodeInfo(id="n2", host="h2", port=8000))
        t.add_node(NodeInfo(id="n3", host="h3", port=8000))
        # 3 nodes × 2 directions = 6 connections
        assert len(t.list_connections()) == 6

    def test_remove_node_cascades_connections(self):
        t = ClusterTopology()
        t.add_node(NodeInfo(id="n1", host="h1", port=8000))
        t.add_node(NodeInfo(id="n2", host="h2", port=8000))
        assert len(t.list_connections()) == 2
        assert t.remove_node("n1") is True
        assert t.get_node("n1") is None
        assert len(t.list_connections()) == 0

    def test_set_leader_demotes_previous(self):
        t = ClusterTopology()
        t.add_node(NodeInfo(id="n1", host="h1", port=8000))
        t.add_node(NodeInfo(id="n2", host="h2", port=8000))
        assert t.set_leader("n1") is True
        assert t.leader_id == "n1"
        assert t.get_node("n1").role == NodeRole.LEADER
        # Promote n2 — n1 should be demoted
        assert t.set_leader("n2") is True
        assert t.get_node("n1").role == NodeRole.FOLLOWER
        assert t.get_node("n2").role == NodeRole.LEADER

    def test_quorum_size(self):
        t = ClusterTopology()
        t.add_node(NodeInfo(id="n1", host="h1", port=8000, status=NodeStatus.ACTIVE))
        assert t.quorum_size() == 1  # 1 // 2 + 1 = 1
        t.add_node(NodeInfo(id="n2", host="h2", port=8000, status=NodeStatus.ACTIVE))
        assert t.quorum_size() == 2  # 2 // 2 + 1 = 2
        t.add_node(NodeInfo(id="n3", host="h3", port=8000, status=NodeStatus.ACTIVE))
        assert t.quorum_size() == 2  # 3 // 2 + 1 = 2

    def test_has_quorum(self):
        t = ClusterTopology()
        t.add_node(NodeInfo(id="n1", host="h1", port=8000, status=NodeStatus.ACTIVE))
        t.add_node(NodeInfo(id="n2", host="h2", port=8000, status=NodeStatus.ACTIVE))
        t.add_node(NodeInfo(id="n3", host="h3", port=8000, status=NodeStatus.ACTIVE))
        assert t.quorum_size() == 2
        assert t.has_quorum(2) is True
        assert t.has_quorum(1) is False

    def test_update_heartbeat_promotes_joining_to_active(self):
        t = ClusterTopology()
        t.add_node(
            NodeInfo(id="n1", host="h1", port=8000, status=NodeStatus.JOINING, health_score=0)
        )
        assert t.update_heartbeat("n1", health_score=80) is True
        assert t.get_node("n1").status == NodeStatus.ACTIVE

    def test_update_heartbeat_demotes_active_to_degraded(self):
        t = ClusterTopology()
        t.add_node(
            NodeInfo(id="n1", host="h1", port=8000, status=NodeStatus.ACTIVE, health_score=80)
        )
        t.update_heartbeat("n1", health_score=30)
        assert t.get_node("n1").status == NodeStatus.DEGRADED

    def test_snapshot_aggregates_metrics(self):
        t = ClusterTopology()
        t.add_node(
            NodeInfo(
                id="n1", host="h1", port=8000, brain_count=3, capability_count=5, health_score=80
            )
        )
        t.add_node(
            NodeInfo(
                id="n2", host="h2", port=8000, brain_count=2, capability_count=3, health_score=60
            )
        )
        snap = t.snapshot()
        assert snap.total_brains == 5
        assert snap.total_capabilities == 8
        assert snap.cluster_health == 0.7  # (80+60)/2 / 100


# ── ClusterFederationManager ───────────────────────────────────────────


class TestClusterFederationManager:
    @pytest.mark.asyncio
    async def test_starts_with_local_node_as_leader(self, bus):
        fm = ClusterFederationManager(bus=bus, local_host="localhost", local_port=8000)
        await fm.start()
        try:
            assert fm.is_leader is True
            assert len(fm.list_nodes()) == 1
            assert fm.topology.leader_id == fm.local_node_id
        finally:
            await fm.stop()

    @pytest.mark.asyncio
    async def test_add_remote_node_publishes_event(self, bus):
        events: list[Any] = []

        async def capture(e):
            events.append(e)

        sub_id = await bus.subscribe("cluster.node.joined", capture)
        try:
            fm = ClusterFederationManager(bus=bus, local_host="localhost", local_port=8000)
            await fm.start()
            try:
                await fm.add_remote_node("remote-1", "10.0.0.2", 8000)
                await asyncio.sleep(0.05)
                assert any(e.topic == "cluster.node.joined" for e in events)
                assert fm.topology.get_node("remote-1") is not None
            finally:
                await fm.stop()
        finally:
            await bus.unsubscribe(sub_id)

    @pytest.mark.asyncio
    async def test_remove_node_publishes_event(self, bus):
        events: list[Any] = []

        async def capture(e):
            events.append(e)

        sub_id = await bus.subscribe("cluster.node.left", capture)
        try:
            fm = ClusterFederationManager(bus=bus, local_host="localhost", local_port=8000)
            await fm.start()
            try:
                await fm.add_remote_node("remote-1", "10.0.0.2", 8000)
                await fm.remove_node("remote-1", reason="test")
                await asyncio.sleep(0.05)
                assert any(e.topic == "cluster.node.left" for e in events)
                assert fm.topology.get_node("remote-1") is None
            finally:
                await fm.stop()
        finally:
            await bus.unsubscribe(sub_id)

    @pytest.mark.asyncio
    async def test_update_heartbeat_updates_node_metrics(self, bus):
        fm = ClusterFederationManager(bus=bus, local_host="localhost", local_port=8000)
        await fm.start()
        try:
            await fm.add_remote_node("remote-1", "10.0.0.2", 8000)
            await fm.update_node_heartbeat(
                "remote-1",
                {"brain_count": 5, "cpu_usage": 45.0, "health_score": 80},
            )
            node = fm.topology.get_node("remote-1")
            assert node.brain_count == 5
            assert node.cpu_usage == 45.0
            assert node.health_score == 80
        finally:
            await fm.stop()

    @pytest.mark.asyncio
    async def test_elect_leader_picks_healthiest_active(self, bus):
        fm = ClusterFederationManager(bus=bus, local_host="localhost", local_port=8000)
        await fm.start()
        try:
            await fm.add_remote_node("r1", "h1", 8000)
            await fm.add_remote_node("r2", "h2", 8000)
            # Mark local node with low health so remote wins
            fm.topology.update_heartbeat(fm.local_node_id, health_score=50)
            # Mark r1 as active with high health
            fm.topology.mark_node_status("r1", NodeStatus.ACTIVE)
            fm.topology.update_heartbeat("r1", health_score=95)
            fm.topology.mark_node_status("r2", NodeStatus.ACTIVE)
            fm.topology.update_heartbeat("r2", health_score=70)
            leader = await fm.elect_leader()
            assert leader == "r1"
        finally:
            await fm.stop()

    @pytest.mark.asyncio
    async def test_dashboard_returns_local_info(self, bus):
        fm = ClusterFederationManager(bus=bus, local_host="localhost", local_port=8000)
        await fm.start()
        try:
            dash = fm.dashboard()
            assert dash["local_node_id"] == fm.local_node_id
            assert dash["is_leader"] is True
            assert "topology" in dash
        finally:
            await fm.stop()


# ── DistributedBrainRegistry ───────────────────────────────────────────


class TestDistributedBrainRegistry:
    @pytest.mark.asyncio
    async def test_add_remote_brain_publishes_event(self, bus, registry):
        events: list[Any] = []

        async def capture(e):
            events.append(e)

        sub_id = await bus.subscribe("cluster.brain.discovered", capture)
        try:
            fm = ClusterFederationManager(bus=bus, local_host="localhost", local_port=8000)
            await fm.start()
            dr = DistributedBrainRegistry(local_registry=registry, federation=fm, bus=bus)
            try:
                await dr.add_remote_brain(
                    brain_id="rb1",
                    node_id="remote-1",
                    display_name="RemoteBrain",
                    capabilities=("chat", "code"),
                    health=85,
                )
                await asyncio.sleep(0.05)
                assert any(e.topic == "cluster.brain.discovered" for e in events)
                assert dr.get_remote_brain("rb1", "remote-1") is not None
            finally:
                await fm.stop()
        finally:
            await bus.unsubscribe(sub_id)

    @pytest.mark.asyncio
    async def test_remove_remote_brain_publishes_event(self, bus, registry):
        events: list[Any] = []

        async def capture(e):
            events.append(e)

        sub_id = await bus.subscribe("cluster.brain.removed", capture)
        try:
            fm = ClusterFederationManager(bus=bus, local_host="localhost", local_port=8000)
            await fm.start()
            dr = DistributedBrainRegistry(local_registry=registry, federation=fm, bus=bus)
            try:
                await dr.add_remote_brain("rb1", "remote-1", capabilities=("chat",))
                await asyncio.sleep(0.05)  # let add event drain
                await dr.remove_remote_brain("rb1", "remote-1")
                await asyncio.sleep(0.2)  # LocalBus dispatches via create_task
                assert any(e.topic == "cluster.brain.removed" for e in events)
                assert dr.get_remote_brain("rb1", "remote-1") is None
            finally:
                await fm.stop()
        finally:
            await bus.unsubscribe(sub_id)

    @pytest.mark.asyncio
    async def test_remove_all_for_node(self, bus, registry):
        fm = ClusterFederationManager(bus=bus, local_host="localhost", local_port=8000)
        await fm.start()
        dr = DistributedBrainRegistry(local_registry=registry, federation=fm, bus=bus)
        try:
            await dr.add_remote_brain("rb1", "remote-1", capabilities=("chat",))
            await dr.add_remote_brain("rb2", "remote-1", capabilities=("code",))
            await dr.add_remote_brain("rb3", "remote-2", capabilities=("chat",))
            count = await dr.remove_all_for_node("remote-1")
            assert count == 2
            assert len(dr.list_remote_brains()) == 1
        finally:
            await fm.stop()

    @pytest.mark.asyncio
    async def test_list_all_distributed_combines_local_and_remote(self, bus, populated_registry):
        fm = ClusterFederationManager(bus=bus, local_host="localhost", local_port=8000)
        await fm.start()
        dr = DistributedBrainRegistry(local_registry=populated_registry, federation=fm, bus=bus)
        try:
            await dr.add_remote_brain("rb1", "remote-1", capabilities=("chat",))
            all_brains = await dr.list_all_distributed()
            assert len(all_brains) == 4  # 3 local + 1 remote
            scopes = {b["scope"] for b in all_brains}
            assert scopes == {"local", "remote"}
        finally:
            await fm.stop()

    @pytest.mark.asyncio
    async def test_sync_from_node_idempotent(self, bus, registry):
        fm = ClusterFederationManager(bus=bus, local_host="localhost", local_port=8000)
        await fm.start()
        dr = DistributedBrainRegistry(local_registry=registry, federation=fm, bus=bus)
        try:
            payload = [
                {"id": "rb1", "display_name": "R1", "capabilities": ["chat"], "health": 90},
                {"id": "rb2", "display_name": "R2", "capabilities": ["code"], "health": 80},
            ]
            await dr.sync_from_node("remote-1", payload)
            assert len(dr.list_remote_brains()) == 2
            # Sync again with one removed — should drop rb1
            payload2 = [
                {"id": "rb2", "display_name": "R2", "capabilities": ["code"], "health": 80},
            ]
            await dr.sync_from_node("remote-1", payload2)
            assert len(dr.list_remote_brains()) == 1
            assert dr.get_remote_brain("rb2", "remote-1") is not None
        finally:
            await fm.stop()

    def test_stats(self, registry):
        fm = ClusterFederationManager(
            bus=None,  # type: ignore[arg-type]
            local_host="localhost",
            local_port=8000,
        )
        dr = DistributedBrainRegistry(local_registry=registry, federation=fm)
        s = dr.stats()
        assert "local_brains" in s
        assert "remote_brains" in s
        assert "total_brains" in s


# ── GlobalMissionScheduler ─────────────────────────────────────────────


class TestGlobalMissionScheduler:
    @pytest.mark.asyncio
    async def test_select_optimal_picks_healthiest_local(self, bus, populated_registry):
        fm = ClusterFederationManager(bus=bus, local_host="localhost", local_port=8000)
        await fm.start()
        dr = DistributedBrainRegistry(local_registry=populated_registry, federation=fm, bus=bus)
        sched = GlobalMissionScheduler(
            bus=bus,
            local_registry=populated_registry,
            distributed_registry=dr,
            federation=fm,
        )
        try:
            winner = await sched.select_optimal(required_capabilities=["chat"])
            assert winner is not None
            # Alpha (health=95, latency=50) beats Beta (health=70, latency=200)
            assert winner.brain_id == "b1"
            assert winner.node_id == fm.local_node_id
        finally:
            await fm.stop()

    @pytest.mark.asyncio
    async def test_select_optimal_includes_remote_candidates(self, bus, populated_registry):
        fm = ClusterFederationManager(bus=bus, local_host="localhost", local_port=8000)
        await fm.start()
        dr = DistributedBrainRegistry(local_registry=populated_registry, federation=fm, bus=bus)
        # Add a remote brain with very high health
        await dr.add_remote_brain(
            brain_id="rb1",
            node_id="remote-1",
            display_name="RemoteAlpha",
            capabilities=("chat",),
            health=99,
            latency=10,
        )
        # Mark remote-1 as active with low CPU/memory
        fm.topology.mark_node_status("remote-1", NodeStatus.ACTIVE)
        fm.topology.update_heartbeat("remote-1", cpu_usage=10, memory_usage=20, health_score=99)
        sched = GlobalMissionScheduler(
            bus=bus,
            local_registry=populated_registry,
            distributed_registry=dr,
            federation=fm,
        )
        try:
            winner = await sched.select_optimal(required_capabilities=["chat"])
            assert winner is not None
            # Remote brain has higher health (99 vs 95) and lower latency (10 vs 50)
            assert winner.brain_id == "rb1"
            assert winner.node_id == "remote-1"
        finally:
            await fm.stop()

    @pytest.mark.asyncio
    async def test_select_optimal_returns_none_when_no_candidates(self, bus, populated_registry):
        fm = ClusterFederationManager(bus=bus, local_host="localhost", local_port=8000)
        await fm.start()
        dr = DistributedBrainRegistry(local_registry=populated_registry, federation=fm, bus=bus)
        sched = GlobalMissionScheduler(
            bus=bus,
            local_registry=populated_registry,
            distributed_registry=dr,
            federation=fm,
        )
        try:
            winner = await sched.select_optimal(required_capabilities=["nonexistent_cap"])
            assert winner is None
        finally:
            await fm.stop()

    @pytest.mark.asyncio
    async def test_select_optimal_is_deterministic(self, bus, populated_registry):
        """Same inputs → same winner. Never random."""
        fm = ClusterFederationManager(bus=bus, local_host="localhost", local_port=8000)
        await fm.start()
        dr = DistributedBrainRegistry(local_registry=populated_registry, federation=fm, bus=bus)
        sched = GlobalMissionScheduler(
            bus=bus,
            local_registry=populated_registry,
            distributed_registry=dr,
            federation=fm,
        )
        try:
            w1 = await sched.select_optimal(required_capabilities=["chat"])
            w2 = await sched.select_optimal(required_capabilities=["chat"])
            assert w1 is not None
            assert w2 is not None
            assert w1.brain_id == w2.brain_id
            assert w1.total_score == w2.total_score
        finally:
            await fm.stop()

    @pytest.mark.asyncio
    async def test_select_optimal_publishes_scheduler_events(self, bus, populated_registry):
        events: list[Any] = []

        async def capture(e):
            events.append(e)

        sub_start = await bus.subscribe("cluster.scheduler.started", capture)
        sub_done = await bus.subscribe("cluster.scheduler.completed", capture)
        try:
            fm = ClusterFederationManager(bus=bus, local_host="localhost", local_port=8000)
            await fm.start()
            dr = DistributedBrainRegistry(local_registry=populated_registry, federation=fm, bus=bus)
            sched = GlobalMissionScheduler(
                bus=bus,
                local_registry=populated_registry,
                distributed_registry=dr,
                federation=fm,
            )
            try:
                await sched.select_optimal(required_capabilities=["chat"])
                await asyncio.sleep(0.05)
                topics = {e.topic for e in events}
                assert "cluster.scheduler.started" in topics
                assert "cluster.scheduler.completed" in topics
            finally:
                await fm.stop()
        finally:
            await bus.unsubscribe(sub_start)
            await bus.unsubscribe(sub_done)


# ── ClusterConsensusManager ────────────────────────────────────────────


class TestClusterConsensusManager:
    def test_majority_accept_with_more_yes(self):
        cm = ClusterConsensusManager(quorum_size=1)
        from agentic_os.core.cluster.domain import ConsensusVote

        votes = [
            ConsensusVote(node_id="n1", vote="yes"),
            ConsensusVote(node_id="n2", vote="yes"),
            ConsensusVote(node_id="n3", vote="no"),
        ]
        result = cm.run_consensus("proposal", votes, ConsensusType.MAJORITY)
        assert result.decision == "accepted"
        assert result.agreement == 2 / 3

    def test_majority_reject_with_more_no(self):
        cm = ClusterConsensusManager(quorum_size=1)
        from agentic_os.core.cluster.domain import ConsensusVote

        votes = [
            ConsensusVote(node_id="n1", vote="no"),
            ConsensusVote(node_id="n2", vote="no"),
            ConsensusVote(node_id="n3", vote="yes"),
        ]
        result = cm.run_consensus("proposal", votes, ConsensusType.MAJORITY)
        assert result.decision == "rejected"

    def test_weighted_accept(self):
        cm = ClusterConsensusManager(quorum_size=1)
        from agentic_os.core.cluster.domain import ConsensusVote

        votes = [
            ConsensusVote(node_id="n1", vote="yes", weight=3.0),
            ConsensusVote(node_id="n2", vote="no", weight=1.0),
            ConsensusVote(node_id="n3", vote="no", weight=1.0),
        ]
        result = cm.run_consensus("proposal", votes, ConsensusType.WEIGHTED)
        # yes_weight=3, total=5, 3/5=0.6 > 0.5 → accepted
        assert result.decision == "accepted"

    def test_confidence_accept_above_threshold(self):
        cm = ClusterConsensusManager(quorum_size=1)
        from agentic_os.core.cluster.domain import ConsensusVote

        votes = [
            ConsensusVote(node_id="n1", vote="yes", confidence=0.8),
            ConsensusVote(node_id="n2", vote="yes", confidence=0.7),
        ]
        result = cm.run_consensus("proposal", votes, ConsensusType.CONFIDENCE)
        # avg confidence = 0.75 > 0.6 threshold → accepted
        assert result.decision == "accepted"

    def test_confidence_reject_below_threshold(self):
        cm = ClusterConsensusManager(quorum_size=1)
        from agentic_os.core.cluster.domain import ConsensusVote

        votes = [
            ConsensusVote(node_id="n1", vote="yes", confidence=0.4),
            ConsensusVote(node_id="n2", vote="yes", confidence=0.5),
        ]
        result = cm.run_consensus("proposal", votes, ConsensusType.CONFIDENCE)
        # avg = 0.45 < 0.6 → rejected
        assert result.decision == "rejected"

    def test_leader_decides(self):
        cm = ClusterConsensusManager(quorum_size=1, leader_id="n1")
        from agentic_os.core.cluster.domain import ConsensusVote

        votes = [
            ConsensusVote(node_id="n1", vote="yes"),
            ConsensusVote(node_id="n2", vote="no"),
            ConsensusVote(node_id="n3", vote="no"),
        ]
        result = cm.run_consensus("proposal", votes, ConsensusType.LEADER)
        # Leader (n1) voted yes → accepted despite majority no
        assert result.decision == "accepted"

    def test_quorum_no_quorum_rejected(self):
        cm = ClusterConsensusManager(quorum_size=3)
        from agentic_os.core.cluster.domain import ConsensusVote

        votes = [
            ConsensusVote(node_id="n1", vote="yes"),
            ConsensusVote(node_id="n2", vote="yes"),
        ]
        result = cm.run_consensus("proposal", votes, ConsensusType.QUORUM)
        # Only 2 voters, quorum=3 → no_quorum
        assert result.decision == "no_quorum"
        assert result.quorum_met is False

    def test_quorum_with_quorum_accepts(self):
        cm = ClusterConsensusManager(quorum_size=2)
        from agentic_os.core.cluster.domain import ConsensusVote

        votes = [
            ConsensusVote(node_id="n1", vote="yes"),
            ConsensusVote(node_id="n2", vote="yes"),
            ConsensusVote(node_id="n3", vote="no"),
        ]
        result = cm.run_consensus("proposal", votes, ConsensusType.QUORUM)
        assert result.quorum_met is True
        assert result.decision == "accepted"

    def test_history_recorded(self):
        cm = ClusterConsensusManager(quorum_size=1)
        from agentic_os.core.cluster.domain import ConsensusVote

        cm.run_consensus("p1", [ConsensusVote(node_id="n1", vote="yes")])
        cm.run_consensus("p2", [ConsensusVote(node_id="n1", vote="no")])
        assert len(cm.list_history()) == 2
        stats = cm.stats()
        assert stats["total_consensuses"] == 2
        assert stats["by_decision"]["accepted"] == 1
        assert stats["by_decision"]["rejected"] == 1


# ── FailoverEngine ─────────────────────────────────────────────────────


class TestFailoverEngine:
    @pytest.mark.asyncio
    async def test_detect_node_offline_triggers_quarantine(self, bus, populated_registry):
        fm = ClusterFederationManager(bus=bus, local_host="localhost", local_port=8000)
        await fm.start()
        dr = DistributedBrainRegistry(local_registry=populated_registry, federation=fm, bus=bus)
        sched = GlobalMissionScheduler(
            bus=bus,
            local_registry=populated_registry,
            distributed_registry=dr,
            federation=fm,
        )
        fe = FailoverEngine(bus=bus, federation=fm, distributed_registry=dr, scheduler=sched)
        try:
            await fm.add_remote_node("r1", "10.0.0.2", 8000)
            fm.topology.mark_node_status("r1", NodeStatus.UNREACHABLE)
            action = await fe.detect_node_offline("r1")
            assert action is not None
            assert action.action_type == FailoverActionType.QUARANTINE_NODE
            assert action.target_node_id == "r1"
            assert action.status == "completed"
        finally:
            await fm.stop()

    @pytest.mark.asyncio
    async def test_detect_runtime_offline_finds_replacement(self, bus, populated_registry):
        fm = ClusterFederationManager(bus=bus, local_host="localhost", local_port=8000)
        await fm.start()
        dr = DistributedBrainRegistry(local_registry=populated_registry, federation=fm, bus=bus)
        sched = GlobalMissionScheduler(
            bus=bus,
            local_registry=populated_registry,
            distributed_registry=dr,
            federation=fm,
        )
        fe = FailoverEngine(bus=bus, federation=fm, distributed_registry=dr, scheduler=sched)
        try:
            # Add a remote brain with low health
            await dr.add_remote_brain(
                brain_id="rb1",
                node_id="remote-1",
                capabilities=("chat",),
                health=10,  # below threshold
            )
            action = await fe.detect_runtime_offline("rb1", "remote-1")
            assert action is not None
            assert action.trigger == FailoverTrigger.RUNTIME_OFFLINE
            # Scheduler should have found a replacement (b1 has chat capability)
            assert action.replacement_brain_id != ""
        finally:
            await fm.stop()

    @pytest.mark.asyncio
    async def test_detect_high_latency_triggers_replace(self, bus, populated_registry):
        fm = ClusterFederationManager(bus=bus, local_host="localhost", local_port=8000)
        await fm.start()
        dr = DistributedBrainRegistry(local_registry=populated_registry, federation=fm, bus=bus)
        sched = GlobalMissionScheduler(
            bus=bus,
            local_registry=populated_registry,
            distributed_registry=dr,
            federation=fm,
        )
        fe = FailoverEngine(bus=bus, federation=fm, distributed_registry=dr, scheduler=sched)
        try:
            await dr.add_remote_brain(
                brain_id="rb1",
                node_id="remote-1",
                capabilities=("chat",),
                health=80,
                latency=6000,  # above 5000ms threshold
            )
            action = await fe.detect_high_latency("rb1", "remote-1")
            assert action is not None
            assert action.trigger == FailoverTrigger.HIGH_LATENCY
            assert action.action_type == FailoverActionType.REPLACE_RUNTIME
        finally:
            await fm.stop()

    @pytest.mark.asyncio
    async def test_manual_failover(self, bus, populated_registry):
        fm = ClusterFederationManager(bus=bus, local_host="localhost", local_port=8000)
        await fm.start()
        dr = DistributedBrainRegistry(local_registry=populated_registry, federation=fm, bus=bus)
        sched = GlobalMissionScheduler(
            bus=bus,
            local_registry=populated_registry,
            distributed_registry=dr,
            federation=fm,
        )
        fe = FailoverEngine(bus=bus, federation=fm, distributed_registry=dr, scheduler=sched)
        try:
            action = await fe.trigger_manual_failover(
                brain_id="b1", node_id=fm.local_node_id, mission_id="m1"
            )
            assert action.trigger == FailoverTrigger.MANUAL
            assert action.status == "completed"
        finally:
            await fm.stop()

    @pytest.mark.asyncio
    async def test_failover_publishes_events(self, bus, populated_registry):
        events: list[Any] = []

        async def capture(e):
            events.append(e)

        sub_start = await bus.subscribe("cluster.failover.started", capture)
        sub_done = await bus.subscribe("cluster.failover.completed", capture)
        try:
            fm = ClusterFederationManager(bus=bus, local_host="localhost", local_port=8000)
            await fm.start()
            dr = DistributedBrainRegistry(local_registry=populated_registry, federation=fm, bus=bus)
            sched = GlobalMissionScheduler(
                bus=bus,
                local_registry=populated_registry,
                distributed_registry=dr,
                federation=fm,
            )
            fe = FailoverEngine(bus=bus, federation=fm, distributed_registry=dr, scheduler=sched)
            try:
                await fe.trigger_manual_failover("b1", fm.local_node_id)
                await asyncio.sleep(0.05)
                topics = {e.topic for e in events}
                assert "cluster.failover.started" in topics
                assert "cluster.failover.completed" in topics
            finally:
                await fm.stop()
        finally:
            await bus.unsubscribe(sub_start)
            await bus.unsubscribe(sub_done)


# ── FederatedKnowledgeGraph ────────────────────────────────────────────


class TestFederatedKnowledgeGraph:
    def test_add_remote_brain_creates_provides_edges(self):
        g = FederatedKnowledgeGraph()
        g.add_remote_brain(
            brain_id="rb1",
            node_id="remote-1",
            display_name="Remote",
            capabilities=["chat", "code"],
            health=85,
        )
        # Should have 1 brain node + 2 capability nodes = 3 nodes
        from agentic_os.core.ecosystem.domain import NodeType

        assert len(g.list_nodes(NodeType.BRAIN)) == 1
        assert len(g.list_nodes(NodeType.CAPABILITY)) == 2

    def test_record_cross_host_collaboration(self):
        g = FederatedKnowledgeGraph()
        g.add_remote_brain("a1", "node-a", capabilities=["chat"])
        g.add_remote_brain("b1", "node-b", capabilities=["code"])
        g.record_cross_host_collaboration("a1", "node-a", "b1", "node-b")
        from agentic_os.core.ecosystem.domain import EdgeType

        collab = g.list_edges(EdgeType.COLLABORATES_WITH)
        # 2 directions
        assert len(collab) == 2

    def test_cluster_providers_of(self):
        g = FederatedKnowledgeGraph()
        g.add_remote_brain("a1", "node-a", capabilities=["chat"])
        g.add_remote_brain("b1", "node-b", capabilities=["chat"])
        providers = g.cluster_providers_of("chat")
        assert ("node-a", "a1") in providers
        assert ("node-b", "b1") in providers

    def test_global_impact_analysis(self):
        g = FederatedKnowledgeGraph()
        g.add_remote_brain("a1", "node-a", capabilities=["chat"])
        g.add_remote_brain("b1", "node-b", capabilities=["chat"])
        impact = g.global_impact_analysis("chat")
        assert impact["provider_count"] == 2
        assert "node-a" in impact["at_risk_nodes"]
        assert "node-b" in impact["at_risk_nodes"]


# ── ClusterController (event subscriptions) ────────────────────────────


class TestClusterController:
    @pytest.mark.asyncio
    async def test_starts_with_local_node(self, bus, populated_registry, collaboration_network):
        cc = ClusterController(
            bus=bus,
            brain_registry=populated_registry,
            local_host="localhost",
            local_port=8000,
            collaboration_network=collaboration_network,
        )
        await cc.start()
        try:
            assert cc.started is True
            assert cc.federation.is_leader is True
            assert len(cc.topology.list_nodes()) == 1
        finally:
            await cc.stop()

    @pytest.mark.asyncio
    async def test_node_joined_event_syncs_brains(
        self, bus, populated_registry, collaboration_network
    ):
        from agentic_os.domain.events import EventEnvelope

        cc = ClusterController(
            bus=bus,
            brain_registry=populated_registry,
            local_host="localhost",
            local_port=8000,
            collaboration_network=collaboration_network,
        )
        await cc.start()
        try:
            # Publish a cluster.node.joined event with a brains payload
            await bus.publish(
                EventEnvelope(
                    type="cluster.node.joined",
                    source="test",
                    topic="cluster.node.joined",
                    payload={
                        "id": "remote-1",
                        "host": "10.0.0.2",
                        "port": 8000,
                        "brains": [
                            {
                                "id": "rb1",
                                "display_name": "RemoteBrain",
                                "capabilities": ["chat"],
                                "health": 85,
                            }
                        ],
                    },
                )
            )
            await asyncio.sleep(0.2)
            # Should have synced the remote brain
            assert cc.distributed_registry.get_remote_brain("rb1", "remote-1") is not None
        finally:
            await cc.stop()

    @pytest.mark.asyncio
    async def test_node_left_event_removes_remote_brains(
        self, bus, populated_registry, collaboration_network
    ):
        from agentic_os.domain.events import EventEnvelope

        cc = ClusterController(
            bus=bus,
            brain_registry=populated_registry,
            local_host="localhost",
            local_port=8000,
            collaboration_network=collaboration_network,
        )
        await cc.start()
        try:
            # Manually add a remote brain
            await cc.distributed_registry.add_remote_brain(
                brain_id="rb1", node_id="remote-1", capabilities=("chat",)
            )
            assert cc.distributed_registry.get_remote_brain("rb1", "remote-1") is not None
            # Publish node.left
            await bus.publish(
                EventEnvelope(
                    type="cluster.node.left",
                    source="test",
                    topic="cluster.node.left",
                    payload={"node_id": "remote-1"},
                )
            )
            await asyncio.sleep(0.2)
            # Should be removed
            assert cc.distributed_registry.get_remote_brain("rb1", "remote-1") is None
        finally:
            await cc.stop()

    @pytest.mark.asyncio
    async def test_brain_registered_adds_to_federated_graph(
        self, bus, populated_registry, collaboration_network
    ):
        from agentic_os.domain.events import EventEnvelope

        cc = ClusterController(
            bus=bus,
            brain_registry=populated_registry,
            local_host="localhost",
            local_port=8000,
            collaboration_network=collaboration_network,
        )
        await cc.start()
        try:
            await bus.publish(
                EventEnvelope(
                    type="brain.registered",
                    source="test",
                    topic="brain.registered",
                    payload={
                        "id": "new_brain",
                        "display_name": "NewBrain",
                        "capabilities": ["chat"],
                        "health": 90,
                    },
                )
            )
            await asyncio.sleep(0.2)
            from agentic_os.core.ecosystem.domain import NodeType

            brains = cc.graph.list_nodes(NodeType.BRAIN)
            brain_ids = [n.id for n in brains]
            assert any("new_brain" in bid for bid in brain_ids)
        finally:
            await cc.stop()

    @pytest.mark.asyncio
    async def test_rebuild_regenerates_graph(self, bus, populated_registry, collaboration_network):
        cc = ClusterController(
            bus=bus,
            brain_registry=populated_registry,
            local_host="localhost",
            local_port=8000,
            collaboration_network=collaboration_network,
        )
        await cc.start()
        try:
            result = await cc.rebuild()
            assert result["rebuilt"] is True
            # Should have local brains in graph
            from agentic_os.core.ecosystem.domain import NodeType

            assert len(cc.graph.list_nodes(NodeType.BRAIN)) >= 1
        finally:
            await cc.stop()

    @pytest.mark.asyncio
    async def test_dashboard_returns_all_subsystems(
        self, bus, populated_registry, collaboration_network
    ):
        cc = ClusterController(
            bus=bus,
            brain_registry=populated_registry,
            local_host="localhost",
            local_port=8000,
            collaboration_network=collaboration_network,
        )
        await cc.start()
        try:
            dash = cc.dashboard()
            assert "federation" in dash
            assert "topology" in dash
            assert "distributed_registry" in dash
            assert "scheduler" in dash
            assert "consensus" in dash
            assert "failover" in dash
            assert "graph" in dash
            assert "statistics" in dash
        finally:
            await cc.stop()


# ── REST API ───────────────────────────────────────────────────────────


class TestClusterAPI:
    @pytest.fixture
    async def app_with_cluster(self, bus, populated_registry, collaboration_network):
        from agentic_os.api.app import create_app
        from agentic_os.kernel import Kernel

        kernel = Kernel()
        platform = kernel.platform()
        platform.bus = bus
        platform.brain_registry = populated_registry

        cc = ClusterController(
            bus=bus,
            brain_registry=populated_registry,
            local_host="localhost",
            local_port=8000,
            collaboration_network=collaboration_network,
        )
        await cc.start()
        platform.cluster_controller = cc

        app = create_app(platform)
        try:
            yield app
        finally:
            await cc.stop()

    def test_cluster_status(self, app_with_cluster):
        with TestClient(app_with_cluster) as client:
            r = client.get("/api/cluster/status")
            assert r.status_code == 200
            data = r.json()
            assert data["started"] is True
            assert "local_node_id" in data

    def test_cluster_nodes(self, app_with_cluster):
        with TestClient(app_with_cluster) as client:
            r = client.get("/api/cluster/nodes")
            assert r.status_code == 200
            nodes = r.json()
            assert len(nodes) >= 1  # at least the local node

    def test_cluster_topology(self, app_with_cluster):
        with TestClient(app_with_cluster) as client:
            r = client.get("/api/cluster/topology")
            assert r.status_code == 200
            data = r.json()
            assert "nodes" in data
            assert "connections" in data

    def test_cluster_brains(self, app_with_cluster):
        with TestClient(app_with_cluster) as client:
            r = client.get("/api/cluster/brains")
            assert r.status_code == 200
            data = r.json()
            assert "remote_brains" in data
            assert "stats" in data

    def test_cluster_dashboard(self, app_with_cluster):
        with TestClient(app_with_cluster) as client:
            r = client.get("/api/cluster/dashboard")
            assert r.status_code == 200
            data = r.json()
            assert "federation" in data
            assert "statistics" in data

    def test_cluster_statistics(self, app_with_cluster):
        with TestClient(app_with_cluster) as client:
            r = client.get("/api/cluster/statistics")
            assert r.status_code == 200
            data = r.json()
            assert "total_nodes" in data
            assert "total_brains" in data

    def test_cluster_discover(self, app_with_cluster):
        with TestClient(app_with_cluster) as client:
            r = client.post("/api/cluster/discover")
            assert r.status_code == 200
            data = r.json()
            assert "discovered" in data

    def test_cluster_rebalance(self, app_with_cluster):
        with TestClient(app_with_cluster) as client:
            r = client.post("/api/cluster/rebalance")
            assert r.status_code == 200
            data = r.json()
            assert data["rebalanced"] is True

    def test_cluster_rebuild(self, app_with_cluster):
        with TestClient(app_with_cluster) as client:
            r = client.post("/api/cluster/rebuild")
            assert r.status_code == 200
            data = r.json()
            assert data["rebuilt"] is True

    def test_cluster_synchronize(self, app_with_cluster):
        with TestClient(app_with_cluster) as client:
            r = client.post("/api/cluster/synchronize")
            assert r.status_code == 200
            data = r.json()
            assert "synced" in data

    def test_cluster_elect_leader(self, app_with_cluster):
        with TestClient(app_with_cluster) as client:
            r = client.post("/api/cluster/elect-leader", json={})
            assert r.status_code == 200
            data = r.json()
            assert "leader_id" in data

    def test_cluster_failover(self, app_with_cluster):
        with TestClient(app_with_cluster) as client:
            r = client.post(
                "/api/cluster/failover",
                json={"brain_id": "b1", "node_id": "local", "mission_id": "m1"},
            )
            assert r.status_code == 200
            data = r.json()
            assert data["trigger"] == "manual"
            assert data["status"] == "completed"

    def test_cluster_add_node(self, app_with_cluster):
        with TestClient(app_with_cluster) as client:
            r = client.post(
                "/api/cluster/nodes/add",
                json={
                    "node_id": "remote-test",
                    "host": "10.0.0.5",
                    "port": 8000,
                    "display_name": "Test Node",
                },
            )
            assert r.status_code == 200
            data = r.json()
            assert data["id"] == "remote-test"
            assert data["host"] == "10.0.0.5"

    def test_cluster_consensus(self, app_with_cluster):
        with TestClient(app_with_cluster) as client:
            r = client.post(
                "/api/cluster/consensus",
                json={
                    "proposal": "add new node",
                    "consensus_type": "majority",
                    "votes": [
                        {"node_id": "n1", "vote": "yes"},
                        {"node_id": "n2", "vote": "yes"},
                    ],
                },
            )
            assert r.status_code == 200
            data = r.json()
            assert data["decision"] == "accepted"


# ── WebSocket Propagation ─────────────────────────────────────────────


class TestDashboardBroadcasterClusterForwarding:
    def test_dashboard_topics_include_cluster_events(self):
        from agentic_os.api.dashboard import _DASHBOARD_TOPIC_STRINGS

        required = {
            "cluster.started",
            "cluster.updated",
            "cluster.node.joined",
            "cluster.node.left",
            "cluster.node.updated",
            "cluster.brain.discovered",
            "cluster.brain.removed",
            "cluster.scheduler.started",
            "cluster.scheduler.completed",
            "cluster.failover.started",
            "cluster.failover.completed",
            "cluster.consensus.completed",
            "cluster.topology.updated",
            "cluster.statistics.updated",
        }
        missing = required - set(_DASHBOARD_TOPIC_STRINGS)
        assert not missing, f"Missing cluster topics: {missing}"

    @pytest.mark.asyncio
    async def test_broadcaster_forwards_cluster_events(
        self, bus, populated_registry, collaboration_network
    ):

        from agentic_os.api.dashboard import DashboardBroadcaster

        broadcaster = DashboardBroadcaster(bus=bus)
        await broadcaster.start()
        recv, send = broadcaster.add_client()
        received: list[str] = []

        async def reader():
            async for msg in recv:
                received.append(msg.get("topic", ""))
                if len(received) >= 1:
                    break

        try:
            cc = ClusterController(
                bus=bus,
                brain_registry=populated_registry,
                local_host="localhost",
                local_port=8000,
                collaboration_network=collaboration_network,
            )
            await cc.start()
            try:
                # Trigger a node add which publishes cluster.node.joined
                await cc.federation.add_remote_node("r1", "10.0.0.2", 8000)
                # Trigger a topology update
                await cc.federation.discover_nodes()
                # Wait for delivery
                import anyio

                with anyio.move_on_after(2.0):
                    await reader()
            finally:
                await cc.stop()
            assert any(t.startswith("cluster.") for t in received)
        finally:
            broadcaster.remove_client(send)
            await broadcaster.stop()


# ── Recovery Workflow (integration) ────────────────────────────────────


class TestRecoveryWorkflow:
    @pytest.mark.asyncio
    async def test_node_left_triggers_failover_and_brain_removal(
        self, bus, populated_registry, collaboration_network
    ):
        from agentic_os.domain.events import EventEnvelope

        cc = ClusterController(
            bus=bus,
            brain_registry=populated_registry,
            local_host="localhost",
            local_port=8000,
            collaboration_network=collaboration_network,
        )
        await cc.start()
        try:
            # Setup: add a remote node + remote brain
            await cc.federation.add_remote_node("r1", "10.0.0.2", 8000)
            await cc.distributed_registry.add_remote_brain(
                brain_id="rb1", node_id="r1", capabilities=("chat",)
            )
            assert cc.distributed_registry.get_remote_brain("rb1", "r1") is not None

            # Trigger: publish cluster.node.left
            await bus.publish(
                EventEnvelope(
                    type="cluster.node.left",
                    source="test",
                    topic="cluster.node.left",
                    payload={"node_id": "r1", "reason": "test failure"},
                )
            )
            await asyncio.sleep(0.3)

            # Verify: brain should be removed (failover may also have run)
            assert cc.distributed_registry.get_remote_brain("rb1", "r1") is None
        finally:
            await cc.stop()
