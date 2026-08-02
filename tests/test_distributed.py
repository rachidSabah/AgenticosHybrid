"""Tests for Phase 17 — Distributed Execution Fabric.

Covers:
  - Domain models (DistributedTask, HeartbeatPacket, LeaderVote, etc.)
  - NodeTransport (peer registration, HTTP mock)
  - HeartbeatManager (send, receive, failure detection)
  - NodeRegistry (join, leave, timeout)
  - LeaderElection (deterministic, quorum, term tracking)
  - DistributedEventBus (propagation, loop prevention, TTL)
  - DistributedExecutor (dispatch, ack, complete, timeout, retry)
  - ClusterScheduler (schedule + dispatch)
  - Replication (replicate, receive, version conflict)
  - ClusterHealth (aggregate snapshot)
  - DistributedController (lifecycle, join/leave, dashboard)
  - REST API endpoints under /api/distributed/*
  - WebSocket propagation via DashboardBroadcaster
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from agentic_os.adapters.bus.local import LocalBus
from agentic_os.core.distributed import (
    ClusterHealth,
    DistributedController,
    DistributedEvent,
    DistributedEventBus,
    DistributedExecutor,
    DistributedTask,
    DistributedTaskStatus,
    HeartbeatManager,
    HeartbeatPacket,
    LeaderElection,
    LeaderElectionState,
    LeaderVote,
    NodeRegistry,
    NodeTransport,
    Replication,
    ReplicationEntryType,
    TaskAcknowledgement,
)
from agentic_os.core.distributed.distributed_executor import ClusterScheduler

# ── Fixtures ───────────────────────────────────────────────────────────


@pytest.fixture
async def bus():
    b = LocalBus()
    await b.start()
    yield b
    await b.stop()


@pytest.fixture
def transport():
    return NodeTransport(local_node_id="test-node", local_base_url="http://localhost:8000")


@pytest.fixture
async def controller(bus):
    dc = DistributedController(
        bus=bus,
        local_node_id="test-node",
        local_base_url="http://localhost:8000",
    )
    await dc.start()
    yield dc
    await dc.stop()


# ── Domain Models ──────────────────────────────────────────────────────


class TestDistributedModels:
    def test_distributed_task_defaults(self):
        t = DistributedTask()
        assert t.id.startswith("dtask-")
        assert t.status == DistributedTaskStatus.PENDING
        assert t.priority == 0.5
        assert t.max_retries == 2

    def test_distributed_task_to_dict(self):
        t = DistributedTask(title="Test", priority=0.8)
        d = t.to_dict()
        assert d["title"] == "Test"
        assert d["priority"] == 0.8
        assert d["status"] == "pending"

    def test_heartbeat_packet(self):
        p = HeartbeatPacket(node_id="n1", sequence=42)
        d = p.to_dict()
        assert d["node_id"] == "n1"
        assert d["sequence"] == 42

    def test_leader_vote(self):
        v = LeaderVote(voter_id="n1", candidate_id="n2", term=3)
        d = v.to_dict()
        assert d["voter_id"] == "n1"
        assert d["candidate_id"] == "n2"
        assert d["term"] == 3

    def test_distributed_event_ttl(self):
        e = DistributedEvent(event_type="brain.registered", hop_count=2, max_hops=3)
        assert e.hop_count < e.max_hops

    def test_replication_entry_type_enum(self):
        types = {t.value for t in ReplicationEntryType}
        assert "brain_registry" in types
        assert "mission_state" in types


# ── NodeTransport ──────────────────────────────────────────────────────


class TestNodeTransport:
    def test_register_peer(self, transport):
        transport.register_peer("peer1", "http://10.0.0.2:8000")
        assert transport.get_peer_url("peer1") == "http://10.0.0.2:8000"
        assert len(transport.list_peers()) == 1

    def test_unregister_peer(self, transport):
        transport.register_peer("peer1", "http://10.0.0.2:8000")
        transport.unregister_peer("peer1")
        assert transport.get_peer_url("peer1") is None

    def test_no_peers_returns_none(self, transport):
        assert transport.get_peer_url("nonexistent") is None

    def test_stats(self, transport):
        stats = transport.stats
        assert "peer_count" in stats
        assert stats["peer_count"] == 0


# ── HeartbeatManager ───────────────────────────────────────────────────


class TestHeartbeatManager:
    def test_receive_heartbeat(self, bus, transport):
        hm = HeartbeatManager(bus=bus, transport=transport, local_node_id="n1")
        packet = HeartbeatPacket(node_id="peer1", sequence=1)
        assert hm.receive_heartbeat(packet) is True
        status = hm.get_status("peer1")
        assert status is not None
        assert status.is_alive is True
        assert status.packets_received == 1

    def test_stale_heartbeat_rejected(self, bus, transport):
        hm = HeartbeatManager(bus=bus, transport=transport, local_node_id="n1")
        hm.receive_heartbeat(HeartbeatPacket(node_id="peer1", sequence=5))
        # Older sequence should be rejected
        assert hm.receive_heartbeat(HeartbeatPacket(node_id="peer1", sequence=3)) is False

    def test_stats(self, bus, transport):
        hm = HeartbeatManager(bus=bus, transport=transport, local_node_id="n1")
        hm.receive_heartbeat(HeartbeatPacket(node_id="peer1", sequence=1))
        stats = hm.stats
        assert stats["received"] == 1
        assert stats["tracked_nodes"] == 1


# ── NodeRegistry ───────────────────────────────────────────────────────


class TestNodeRegistry:
    def test_join(self):
        reg = NodeRegistry(local_node_id="n1")
        entry = reg.register_join("peer1", "10.0.0.2", 8000, "http://10.0.0.2:8000")
        assert entry["status"] == "active"
        assert reg.count() == 1

    def test_leave(self):
        reg = NodeRegistry(local_node_id="n1")
        reg.register_join("peer1", "10.0.0.2", 8000)
        assert reg.register_leave("peer1", "test") is True
        node = reg.get_node("peer1")
        assert node["status"] == "left"

    def test_timeout(self):
        reg = NodeRegistry(local_node_id="n1")
        reg.register_join("peer1", "10.0.0.2", 8000)
        assert reg.register_timeout("peer1") is True
        node = reg.get_node("peer1")
        assert node["status"] == "timed_out"

    def test_remove(self):
        reg = NodeRegistry(local_node_id="n1")
        reg.register_join("peer1", "10.0.0.2", 8000)
        assert reg.remove("peer1") is True
        assert reg.get_node("peer1") is None

    def test_list_nodes_by_status(self):
        reg = NodeRegistry(local_node_id="n1")
        reg.register_join("peer1", "10.0.0.2", 8000)
        reg.register_join("peer2", "10.0.0.3", 8000)
        reg.register_leave("peer1")
        active = reg.list_nodes(status="active")
        assert len(active) == 1
        assert active[0]["node_id"] == "peer2"


# ── LeaderElection ─────────────────────────────────────────────────────


class TestLeaderElection:
    def test_single_node_election(self, bus):
        le = LeaderElection(bus=bus, local_node_id="n1")
        result = le.run_election()
        assert result.winner_id == "n1"
        assert result.quorum_met is True
        assert le.state == LeaderElectionState.LEADER

    def test_multi_node_deterministic(self, bus, transport):
        hm = HeartbeatManager(bus=bus, transport=transport, local_node_id="n1")
        # Add peer nodes with different health
        hm.receive_heartbeat(HeartbeatPacket(node_id="n2", sequence=1, health_score=90))
        hm.receive_heartbeat(HeartbeatPacket(node_id="n3", sequence=1, health_score=80))
        le = LeaderElection(bus=bus, local_node_id="n1", heartbeat_manager=hm)
        result = le.run_election()
        # n1 has health=100 (default for self) → should win
        assert result.winner_id == "n1"

    def test_term_increments(self, bus):
        le = LeaderElection(bus=bus, local_node_id="n1")
        le.run_election()
        le.run_election()
        assert le.current_term == 2

    def test_vote_rejected_for_old_term(self, bus):
        le = LeaderElection(bus=bus, local_node_id="n1")
        le.run_election()  # term = 1
        old_vote = LeaderVote(voter_id="n2", candidate_id="n2", term=0)
        assert le.receive_vote(old_vote) is False

    def test_step_down(self, bus):
        le = LeaderElection(bus=bus, local_node_id="n1")
        le.run_election()
        le.step_down()
        assert le.state == LeaderElectionState.FOLLOWER


# ── DistributedEventBus ────────────────────────────────────────────────


class TestDistributedEventBus:
    def test_should_propagate(self, bus, transport):
        deb = DistributedEventBus(bus=bus, transport=transport, local_node_id="n1")
        deb.register_propagation_prefix("brain.")
        assert deb.should_propagate("brain.registered") is True
        assert deb.should_propagate("mission.completed") is False

    def test_loop_prevention(self, bus, transport):
        deb = DistributedEventBus(bus=bus, transport=transport, local_node_id="n1")
        event = DistributedEvent(event_type="brain.registered", event_id="evt-123")
        # First receive: accepted
        assert deb.receive_inbound(event.to_dict()) is True
        # Second receive (same event_id): rejected (loop)
        assert deb.receive_inbound(event.to_dict()) is False

    def test_ttl_exceeded(self, bus, transport):
        deb = DistributedEventBus(bus=bus, transport=transport, local_node_id="n1")
        event = DistributedEvent(
            event_type="brain.registered",
            event_id="evt-ttl",
            hop_count=3,
            max_hops=3,
        )
        assert deb.receive_inbound(event.to_dict()) is False

    def test_no_peers_no_propagation(self, bus, transport):
        deb = DistributedEventBus(bus=bus, transport=transport, local_node_id="n1")
        deb.register_propagation_prefix("brain.")
        result = asyncio.get_event_loop().run_until_complete(
            deb.propagate_outbound("brain.registered", {})
        )
        assert result == 0  # no peers → 0 delivered


# ── DistributedExecutor ────────────────────────────────────────────────


class TestDistributedExecutor:
    @pytest.mark.asyncio
    async def test_local_execution(self, bus, transport):
        ex = DistributedExecutor(bus=bus, transport=transport, local_node_id="n1")
        task = DistributedTask(title="Local task")
        task.assigned_node_id = "n1"  # local
        success = await ex.dispatch(task)
        assert success is True
        assert task.status == DistributedTaskStatus.COMPLETED
        assert task.result["executed_locally"] is True

    @pytest.mark.asyncio
    async def test_receive_acknowledgement(self, bus, transport):
        ex = DistributedExecutor(bus=bus, transport=transport, local_node_id="n1")
        task = DistributedTask(title="Test")
        ex._tasks[task.id] = task
        ack = TaskAcknowledgement(task_id=task.id, node_id="peer1", accepted=True)
        assert ex.receive_acknowledgement(ack) is True
        assert task.status == DistributedTaskStatus.ACKNOWLEDGED

    @pytest.mark.asyncio
    async def test_receive_completion(self, bus, transport):
        ex = DistributedExecutor(bus=bus, transport=transport, local_node_id="n1")
        task = DistributedTask(title="Test")
        ex._tasks[task.id] = task
        assert ex.receive_completion(task.id, {"output": "done"}, success=True) is True
        assert task.status == DistributedTaskStatus.COMPLETED
        assert task.result["output"] == "done"

    @pytest.mark.asyncio
    async def test_receive_failure(self, bus, transport):
        ex = DistributedExecutor(bus=bus, transport=transport, local_node_id="n1")
        task = DistributedTask(title="Test")
        ex._tasks[task.id] = task
        assert ex.receive_completion(task.id, {"error": "failed"}, success=False) is True
        assert task.status == DistributedTaskStatus.FAILED

    def test_check_timeouts(self, bus, transport):
        ex = DistributedExecutor(bus=bus, transport=transport, local_node_id="n1")
        # Create a task with past dispatch time
        from datetime import UTC, datetime, timedelta

        task = DistributedTask(title="Timeout test", timeout_s=0.01)
        task.status = DistributedTaskStatus.DISPATCHED
        task.dispatch_time = (datetime.now(UTC) - timedelta(seconds=10)).isoformat()
        ex._tasks[task.id] = task
        count = ex.check_timeouts()
        assert count == 1
        assert task.status == DistributedTaskStatus.TIMEOUT

    def test_stats(self, bus, transport):
        ex = DistributedExecutor(bus=bus, transport=transport, local_node_id="n1")
        stats = ex.stats
        assert "dispatched" in stats
        assert "completed" in stats


# ── ClusterScheduler ───────────────────────────────────────────────────


class TestClusterScheduler:
    @pytest.mark.asyncio
    async def test_schedule_local(self, bus, transport):
        ex = DistributedExecutor(bus=bus, transport=transport, local_node_id="n1")
        sched = ClusterScheduler(bus=bus, executor=ex)
        task = DistributedTask(title="Local")
        success = await sched.schedule_and_dispatch(task, selected_node_id="n1")
        assert success is True
        assert sched.stats["tasks_dispatched_locally"] == 1


# ── Replication ────────────────────────────────────────────────────────


class TestReplication:
    @pytest.mark.asyncio
    async def test_replicate_no_peers(self, transport):
        rep = Replication(transport=transport, local_node_id="n1")
        count = await rep.replicate("key1", {"data": "test"})
        assert count == 0  # no peers

    def test_receive_replication(self, transport):
        rep = Replication(transport=transport, local_node_id="n1")
        entry = {
            "entry_type": "brain_registry",
            "source_node_id": "peer1",
            "key": "brain-1",
            "value": {"name": "Brain1"},
            "version": 1,
            "timestamp": "2026-01-01T00:00:00+00:00",
        }
        assert rep.receive_replication(entry) is True

    def test_stale_replication_rejected(self, transport):
        rep = Replication(transport=transport, local_node_id="n1")
        entry_v2 = {
            "entry_type": "brain_registry",
            "source_node_id": "peer1",
            "key": "brain-1",
            "value": {"name": "Brain1"},
            "version": 2,
        }
        entry_v1 = {
            "entry_type": "brain_registry",
            "source_node_id": "peer1",
            "key": "brain-1",
            "value": {"name": "Brain1"},
            "version": 1,
        }
        rep.receive_replication(entry_v2)
        assert rep.receive_replication(entry_v1) is False  # stale


# ── ClusterHealth ──────────────────────────────────────────────────────


class TestClusterHealth:
    def test_compute_snapshot(self, transport):
        hm = HeartbeatManager(
            bus=None,  # type: ignore[arg-type]
            transport=transport,
            local_node_id="n1",
        )
        ch = ClusterHealth(heartbeat_manager=hm)
        ch.update_node_metrics("n1", {"health_score": 90, "cpu_usage": 30})
        ch.update_node_metrics("n2", {"health_score": 80, "cpu_usage": 50})
        snapshot = ch.compute_snapshot(leader_id="n1")
        assert snapshot.total_nodes == 2
        assert snapshot.avg_health == 85.0
        assert snapshot.leader_id == "n1"

    def test_quorum_intact(self, transport):
        ch = ClusterHealth()
        ch.update_node_metrics("n1", {"is_alive": True, "health_score": 100})
        ch.update_node_metrics("n2", {"is_alive": True, "health_score": 100})
        ch.update_node_metrics("n3", {"is_alive": False, "health_score": 0})
        snapshot = ch.compute_snapshot()
        assert snapshot.alive_nodes == 2
        assert snapshot.dead_nodes == 1
        assert snapshot.quorum_intact is True  # 2/3 > 50%


# ── DistributedController ─────────────────────────────────────────────


class TestDistributedController:
    @pytest.mark.asyncio
    async def test_starts_and_auto_elects_self(self, bus):
        dc = DistributedController(
            bus=bus,
            local_node_id="n1",
            local_base_url="http://localhost:8000",
        )
        await dc.start()
        try:
            assert dc.started is True
            assert dc.leader_election.current_leader == "n1"
            assert dc.leader_election.state == LeaderElectionState.LEADER
        finally:
            await dc.stop()

    @pytest.mark.asyncio
    async def test_join_cluster(self, bus):
        dc = DistributedController(bus=bus, local_node_id="n1")
        await dc.start()
        try:
            result = await dc.join_cluster("http://10.0.0.2:8000", "peer1")
            assert result["joined"] is True
            assert dc.transport.get_peer_url("peer1") is not None
        finally:
            await dc.stop()

    @pytest.mark.asyncio
    async def test_leave_cluster(self, bus):
        dc = DistributedController(bus=bus, local_node_id="n1")
        await dc.start()
        try:
            await dc.join_cluster("http://10.0.0.2:8000", "peer1")
            result = await dc.leave_cluster("peer1", "test")
            assert result["left"] is True
            assert dc.transport.get_peer_url("peer1") is None
        finally:
            await dc.stop()

    @pytest.mark.asyncio
    async def test_dashboard(self, bus):
        dc = DistributedController(bus=bus, local_node_id="n1")
        await dc.start()
        try:
            dash = dc.dashboard()
            assert "local_node_id" in dash
            assert "leader_id" in dash
            assert "health" in dash
            assert "nodes" in dash
        finally:
            await dc.stop()

    @pytest.mark.asyncio
    async def test_status(self, bus):
        dc = DistributedController(bus=bus, local_node_id="n1")
        await dc.start()
        try:
            status = dc.status()
            assert status["started"] is True
            assert status["leader_id"] == "n1"
        finally:
            await dc.stop()

    @pytest.mark.asyncio
    async def test_get_cluster_health(self, bus):
        dc = DistributedController(bus=bus, local_node_id="n1")
        await dc.start()
        try:
            health = dc.get_cluster_health()
            assert "total_nodes" in health
            assert "leader_id" in health
        finally:
            await dc.stop()

    @pytest.mark.asyncio
    async def test_dispatch_local_task(self, bus):
        dc = DistributedController(bus=bus, local_node_id="n1")
        await dc.start()
        try:
            task = DistributedTask(title="Test task")
            task.assigned_node_id = "n1"  # local
            success = await dc.dispatch_task(task)
            assert success is True
            assert task.status == DistributedTaskStatus.COMPLETED
        finally:
            await dc.stop()


# ── REST API ───────────────────────────────────────────────────────────


class TestDistributedAPI:
    @pytest.fixture
    async def app_with_distributed(self, bus):
        from agentic_os.api.app import create_app
        from agentic_os.kernel import Kernel

        kernel = Kernel()
        platform = kernel.platform()
        platform.bus = bus

        dc = DistributedController(
            bus=bus,
            local_node_id="test-node",
            local_base_url="http://localhost:8000",
        )
        await dc.start()
        platform.distributed_controller = dc

        app = create_app(platform)
        try:
            yield app
        finally:
            await dc.stop()

    def test_distributed_status(self, app_with_distributed):
        with TestClient(app_with_distributed) as client:
            r = client.get("/api/distributed/status")
            assert r.status_code == 200
            data = r.json()
            assert data["started"] is True
            assert data["local_node_id"] == "test-node"

    def test_distributed_dashboard(self, app_with_distributed):
        with TestClient(app_with_distributed) as client:
            r = client.get("/api/distributed/dashboard")
            assert r.status_code == 200
            data = r.json()
            assert "leader_id" in data
            assert "health" in data

    def test_distributed_health(self, app_with_distributed):
        with TestClient(app_with_distributed) as client:
            r = client.get("/api/distributed/health")
            assert r.status_code == 200
            assert "total_nodes" in r.json()

    def test_distributed_tasks(self, app_with_distributed):
        with TestClient(app_with_distributed) as client:
            r = client.get("/api/distributed/tasks")
            assert r.status_code == 200
            assert "tasks" in r.json()

    def test_distributed_dispatch_task(self, app_with_distributed):
        with TestClient(app_with_distributed) as client:
            r = client.post(
                "/api/distributed/tasks/dispatch",
                json={"title": "API test", "target_node_id": "test-node"},
            )
            assert r.status_code == 200
            data = r.json()
            assert data["dispatched"] is True

    def test_distributed_events(self, app_with_distributed):
        with TestClient(app_with_distributed) as client:
            r = client.get("/api/distributed/events")
            assert r.status_code == 200

    def test_distributed_heartbeat(self, app_with_distributed):
        with TestClient(app_with_distributed) as client:
            r = client.post(
                "/api/distributed/heartbeat",
                json={"node_id": "peer1", "sequence": 1, "health_score": 90},
            )
            assert r.status_code == 200
            assert r.json()["accepted"] is True

    def test_distributed_join(self, app_with_distributed):
        with TestClient(app_with_distributed) as client:
            r = client.post(
                "/api/distributed/join",
                json={"peer_url": "http://10.0.0.2:8000", "peer_node_id": "peer1"},
            )
            assert r.status_code == 200
            assert r.json()["joined"] is True

    def test_distributed_leave(self, app_with_distributed):
        with TestClient(app_with_distributed) as client:
            # First join
            client.post(
                "/api/distributed/join",
                json={"peer_url": "http://10.0.0.2:8000", "peer_node_id": "peer1"},
            )
            # Then leave
            r = client.post(
                "/api/distributed/leave",
                json={"node_id": "peer1", "reason": "test"},
            )
            assert r.status_code == 200
            assert r.json()["left"] is True

    def test_distributed_leader(self, app_with_distributed):
        with TestClient(app_with_distributed) as client:
            r = client.post("/api/distributed/leader")
            assert r.status_code == 200
            assert "winner_id" in r.json()

    def test_distributed_topology(self, app_with_distributed):
        with TestClient(app_with_distributed) as client:
            r = client.get("/api/distributed/topology")
            assert r.status_code == 200
            assert "leader_id" in r.json()

    def test_distributed_scheduler(self, app_with_distributed):
        with TestClient(app_with_distributed) as client:
            r = client.get("/api/distributed/scheduler")
            assert r.status_code == 200

    def test_distributed_replicate(self, app_with_distributed):
        with TestClient(app_with_distributed) as client:
            r = client.post(
                "/api/distributed/replicate",
                json={
                    "entry_type": "brain_registry",
                    "source_node_id": "peer1",
                    "key": "brain-1",
                    "value": {"name": "Brain1"},
                    "version": 1,
                },
            )
            assert r.status_code == 200
            assert r.json()["accepted"] is True

    def test_distributed_vote(self, app_with_distributed):
        with TestClient(app_with_distributed) as client:
            r = client.post(
                "/api/distributed/vote",
                json={"voter_id": "peer1", "candidate_id": "test-node", "term": 1},
            )
            assert r.status_code == 200


# ── WebSocket Propagation ─────────────────────────────────────────────


class TestDashboardBroadcasterDistributedForwarding:
    def test_dashboard_topics_include_distributed_events(self):
        from agentic_os.api.dashboard import _DASHBOARD_TOPIC_STRINGS

        required = {
            "distributed.started",
            "distributed.stopped",
            "distributed.task.dispatched",
            "distributed.task.completed",
            "distributed.task.failed",
            "node.joined",
            "node.left",
            "node.leader.elected",
            "node.heartbeat.received",
            "node.health.updated",
        }
        missing = required - set(_DASHBOARD_TOPIC_STRINGS)
        assert not missing, f"Missing distributed topics: {missing}"

    @pytest.mark.asyncio
    async def test_broadcaster_forwards_distributed_events(self, bus):

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
            dc = DistributedController(bus=bus, local_node_id="n1")
            await dc.start()
            try:
                # Trigger leader election which publishes node.leader.elected
                await dc.elect_leader()
                import anyio

                with anyio.move_on_after(2.0):
                    await reader()
            finally:
                await dc.stop()
            assert any(t.startswith("distributed.") or t.startswith("node.") for t in received)
        finally:
            broadcaster.remove_client(send)
            await broadcaster.stop()
