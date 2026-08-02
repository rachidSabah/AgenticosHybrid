"""Tests for Phase 15 — Full Autonomous Agent Ecosystem & Self-Evolving Mission Control.

Covers:
  - CapabilityGraph node/edge CRUD + traversal + event-driven updaters
  - CollaborationNetwork trust/confidence evolution
  - EvolutionEngine analyzers (capability gaps, routing, collaboration, performance)
  - TaskMarketplace publish/bid/select/complete lifecycle
  - EcosystemManager stats/health/refresh/optimize/rebuild
  - EcosystemController event subscription + autonomous optimization trigger
  - REST API endpoints under /api/ecosystem/*
  - WebSocket propagation via DashboardBroadcaster
  - Failure recovery (brain.removed → graph updated → recommendations refreshed)
  - Dynamic runtime discovery (brain.registered → graph node added)
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agentic_os.adapters.bus.local import LocalBus
from agentic_os.core.brains.registry import BrainRegistry
from agentic_os.core.cognitive.memory import CognitiveMemory
from agentic_os.core.ecosystem import (
    CapabilityGraph,
    CollaborationNetwork,
    EcosystemController,
    EcosystemManager,
    EvolutionEngine,
    TaskMarketplace,
)
from agentic_os.core.ecosystem.domain import (
    EcosystemHealthLevel,
    EdgeType,
    NodeType,
    RecommendationType,
    TaskBidStrategy,
)
from agentic_os.core.executive.memory import ExecutiveMemory
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
    """BrainRegistry bound to the test bus so its events propagate."""
    r = BrainRegistry()
    await r.start(event_bus=bus)
    yield r
    await r.stop()


@pytest.fixture
async def populated_registry(registry):
    """A registry with three test brains of varying health/capability."""
    await registry.register(make_brain("b1", "Alpha", ("chat", "code"), health=95, latency=50))
    await registry.register(make_brain("b2", "Beta", ("chat", "vision"), health=70, latency=200))
    await registry.register(make_brain("b3", "Gamma", ("code",), health=30, latency=2500))
    return registry


@pytest.fixture
def exec_memory():
    return ExecutiveMemory()


@pytest.fixture
def cog_memory():
    return CognitiveMemory()


@pytest.fixture
async def controller(bus, populated_registry, exec_memory, cog_memory):
    ec = EcosystemController(
        bus=bus,
        brain_registry=populated_registry,
        exec_memory=exec_memory,
        cognitive_memory=cog_memory,
    )
    await ec.start()
    yield ec
    await ec.stop()


# ── CapabilityGraph ────────────────────────────────────────────────────


class TestCapabilityGraph:
    def test_add_node_and_query(self):
        g = CapabilityGraph()
        n = g.add_node("b1", NodeType.BRAIN, "Alpha", {"health": 90})
        assert n.id == "b1"
        assert n.type == NodeType.BRAIN
        assert n.label == "Alpha"
        assert n.properties["health"] == 90
        assert g.get_node("b1") is n

    def test_add_edge_creates_missing_nodes(self):
        g = CapabilityGraph()
        g.add_edge("b1", "cap:chat", EdgeType.PROVIDES)
        # Auto-created nodes
        assert g.get_node("b1") is not None
        assert g.get_node("cap:chat") is not None
        assert "cap:chat" in g.neighbors("b1")
        assert "b1" in g.reverse_neighbors("cap:chat")

    def test_remove_node_cascades_edges(self):
        g = CapabilityGraph()
        g.add_node("b1", NodeType.BRAIN)
        g.add_node("cap:chat", NodeType.CAPABILITY)
        g.add_edge("b1", "cap:chat", EdgeType.PROVIDES)
        assert len(g.list_edges()) == 1
        assert g.remove_node("b1") is True
        assert g.get_node("b1") is None
        assert len(g.list_edges()) == 0

    def test_find_path_bfs(self):
        g = CapabilityGraph()
        g.add_node("a", NodeType.BRAIN)
        g.add_node("b", NodeType.BRAIN)
        g.add_node("c", NodeType.BRAIN)
        g.add_edge("a", "b", EdgeType.COLLABORATES_WITH)
        g.add_edge("b", "c", EdgeType.COLLABORATES_WITH)
        assert g.find_path("a", "c") == ["a", "b", "c"]
        assert g.find_path("a", "a") == ["a"]
        # No path
        g.add_node("z", NodeType.BRAIN)
        assert g.find_path("a", "z") == []

    def test_providers_of(self):
        g = CapabilityGraph()
        g.apply_brain_registered(
            {"id": "b1", "display_name": "Alpha", "capabilities": ["chat", "code"]}
        )
        g.apply_brain_registered({"id": "b2", "display_name": "Beta", "capabilities": ["chat"]})
        providers = g.providers_of("chat")
        assert set(providers) == {"b1", "b2"}
        providers_code = g.providers_of("code")
        assert providers_code == ["b1"]

    def test_apply_brain_registered(self):
        g = CapabilityGraph()
        g.apply_brain_registered(
            {
                "id": "b1",
                "display_name": "Alpha",
                "capabilities": ["chat", "code"],
                "vendor": "ollama",
                "health": 95,
                "latency": 50,
            }
        )
        assert g.get_node("b1") is not None
        assert g.get_node("b1").label == "Alpha"
        assert g.get_node("cap:chat") is not None
        assert g.get_node("cap:code") is not None
        assert len(g.list_edges(EdgeType.PROVIDES)) == 2

    def test_apply_brain_updated_changes_capabilities(self):
        g = CapabilityGraph()
        g.apply_brain_registered({"id": "b1", "display_name": "Alpha", "capabilities": ["chat"]})
        # Update to remove "chat" and add "vision"
        g.apply_brain_updated(
            {"id": "b1", "display_name": "Alpha", "capabilities": ["vision"], "health": 80}
        )
        assert g.providers_of("chat") == []
        assert g.providers_of("vision") == ["b1"]
        assert g.get_node("b1").properties["health"] == 80

    def test_apply_brain_removed(self):
        g = CapabilityGraph()
        g.apply_brain_registered({"id": "b1", "display_name": "Alpha", "capabilities": ["chat"]})
        assert g.get_node("b1") is not None
        g.apply_brain_removed({"id": "b1"})
        assert g.get_node("b1") is None
        # Capability node remains (it can still be provided by others)
        assert g.get_node("cap:chat") is not None
        # But the PROVIDES edge from b1 is gone
        assert g.providers_of("chat") == []

    def test_apply_mission_completed_links_members(self):
        g = CapabilityGraph()
        g.apply_brain_registered({"id": "b1", "display_name": "Alpha", "capabilities": []})
        g.apply_brain_registered({"id": "b2", "display_name": "Beta", "capabilities": []})
        g.apply_mission_completed(
            {
                "mission_id": "m1",
                "title": "Test Mission",
                "members": [{"id": "b1"}, {"id": "b2"}],
            }
        )
        assert g.get_node("m1") is not None
        assert g.get_node("m1").type == NodeType.MISSION
        # EXECUTED edges from each member to the mission
        executed = g.list_edges(EdgeType.EXECUTED)
        assert len(executed) == 2
        # Pairwise COLLABORATES_WITH edges (b1→b2 and b2→b1)
        collab = g.list_edges(EdgeType.COLLABORATES_WITH)
        assert len(collab) == 2

    def test_apply_swarm_completed_links_pairwise(self):
        g = CapabilityGraph()
        g.apply_brain_registered({"id": "b1", "display_name": "A", "capabilities": []})
        g.apply_brain_registered({"id": "b2", "display_name": "B", "capabilities": []})
        g.apply_brain_registered({"id": "b3", "display_name": "C", "capabilities": []})
        g.apply_swarm_completed(
            {
                "swarm_id": "s1",
                "goal": "Test Swarm",
                "members": [{"id": "b1"}, {"id": "b2"}, {"id": "b3"}],
            }
        )
        # 3 pairs × 2 directions = 6 collaboration edges
        collab = g.list_edges(EdgeType.COLLABORATES_WITH)
        assert len(collab) == 6

    def test_stats(self):
        g = CapabilityGraph()
        g.apply_brain_registered({"id": "b1", "display_name": "A", "capabilities": ["chat"]})
        g.apply_brain_registered(
            {"id": "b2", "display_name": "B", "capabilities": ["chat", "code"]}
        )
        stats = g.stats()
        assert stats["total_nodes"] == 4  # 2 brains + 2 unique capabilities
        assert stats["nodes_by_type"]["brain"] == 2
        assert stats["nodes_by_type"]["capability"] == 2
        assert stats["edges_by_type"]["provides"] == 3
        assert stats["updates_count"] > 0


# ── CollaborationNetwork ──────────────────────────────────────────────


class TestCollaborationNetwork:
    def test_record_collaboration_updates_both_directions(self):
        net = CollaborationNetwork()
        net.record_collaboration("a", "b", success=True, confidence=0.8)
        link = net.get_link("a", "b")
        assert link is not None
        assert link.successful == 1
        assert link.failed == 0
        # Mirror direction
        mirror = net.get_link("b", "a")
        assert mirror is not None
        assert mirror.successful == 1

    def test_trust_score_increases_on_success(self):
        net = CollaborationNetwork()
        # Initial trust = 0.5
        assert net.trust_score("a", "b") == 0.5
        for _ in range(5):
            net.record_collaboration("a", "b", success=True, confidence=0.9)
        # After 5 successful collaborations, trust should be high
        trust = net.trust_score("a", "b")
        assert trust > 0.8

    def test_trust_score_decreases_on_failure(self):
        net = CollaborationNetwork()
        for _ in range(5):
            net.record_collaboration("a", "b", success=False, confidence=0.1)
        trust = net.trust_score("a", "b")
        assert trust < 0.3

    def test_average_trust(self):
        net = CollaborationNetwork()
        net.record_collaboration("a", "b", success=True)
        net.record_collaboration("a", "c", success=False)
        # b has 1 incoming collaboration from a with success
        avg_b = net.average_trust("b")
        avg_c = net.average_trust("c")
        assert avg_b > avg_c

    def test_top_collaborators(self):
        net = CollaborationNetwork()
        for _ in range(3):
            net.record_collaboration("x", "good", success=True, confidence=0.9)
        for _ in range(2):
            net.record_collaboration("x", "bad", success=False, confidence=0.1)
        top = net.top_collaborators("x", limit=2)
        assert top[0][0] == "good"
        assert top[0][1] > top[1][1]

    def test_runtime_stats(self):
        net = CollaborationNetwork()
        net.record_collaboration("a", "b", success=True)
        net.record_collaboration("a", "c", success=False)
        stats = net.runtime_stats("a")
        assert stats["total"] == 2
        assert stats["successful"] == 1
        assert stats["failed"] == 1
        assert stats["success_rate"] == 0.5
        assert stats["collaborator_count"] == 2

    def test_network_stats(self):
        net = CollaborationNetwork()
        net.record_collaboration("a", "b", success=True)
        net.record_collaboration("a", "c", success=False)
        s = net.stats()
        # 2 collaborations recorded → 4 directional links (a→b, b→a, a→c, c→a)
        assert s["total_links"] == 4
        assert s["unique_runtimes"] == 3
        assert s["total_collaborations"] == 2
        assert s["successful_collaborations"] == 1
        assert s["failed_collaborations"] == 1


# ── EvolutionEngine ────────────────────────────────────────────────────


class TestEvolutionEngine:
    @pytest.mark.asyncio
    async def test_analyze_capability_gaps_finds_underprovisioned(
        self, populated_registry, exec_memory
    ):
        # Store 5 decisions for capability "rare_cap", only 1 satisfied
        for i in range(4):
            await exec_memory.store_decision(
                {
                    "id": f"d{i}",
                    "selected_runtime": "",  # unsatisfied
                    "factors": {"required_capability": "rare_cap"},
                }
            )
        await exec_memory.store_decision(
            {
                "id": "d4",
                "selected_runtime": "b1",  # satisfied
                "factors": {"required_capability": "rare_cap"},
            }
        )
        graph = CapabilityGraph()
        graph.apply_brain_registered(
            {"id": "b1", "display_name": "Alpha", "capabilities": ["rare_cap"]}
        )
        engine = EvolutionEngine(
            brain_registry=populated_registry,
            exec_memory=exec_memory,
            capability_graph=graph,
        )
        recs = await engine.analyze_capability_gaps()
        # Should find "rare_cap" as underprovisioned (1/5 = 20% satisfaction)
        titles = [r.title for r in recs]
        assert any("rare_cap" in t for t in titles)

    @pytest.mark.asyncio
    async def test_analyze_capability_gaps_finds_single_provider(
        self, populated_registry, exec_memory
    ):
        graph = CapabilityGraph()
        graph.apply_brain_registered(
            {"id": "b1", "display_name": "Alpha", "capabilities": ["unique_cap"]}
        )
        engine = EvolutionEngine(
            brain_registry=populated_registry,
            exec_memory=exec_memory,
            capability_graph=graph,
        )
        recs = await engine.analyze_capability_gaps()
        titles = [r.title for r in recs]
        assert any("Single-provider" in t for t in titles)

    @pytest.mark.asyncio
    async def test_analyze_routing_optimizations_for_unhealthy(self, populated_registry):
        # b3 has health=30 and latency=2500 — should be re-routed
        graph = CapabilityGraph()
        for b in await populated_registry.list_all():
            graph.apply_brain_registered(
                {
                    "id": b.id,
                    "display_name": b.display_name,
                    "capabilities": list(b.capabilities),
                    "health": b.health,
                    "latency": b.latency,
                }
            )
        engine = EvolutionEngine(
            brain_registry=populated_registry,
            capability_graph=graph,
        )
        recs = await engine.analyze_routing_optimizations()
        # b3 is unhealthy — should have a re-route recommendation
        titles = [r.title for r in recs]
        assert any("Gamma" in t for t in titles)

    @pytest.mark.asyncio
    async def test_analyze_collaboration_opportunities(self, populated_registry):
        net = CollaborationNetwork()
        graph = CapabilityGraph()
        for b in await populated_registry.list_all():
            graph.apply_brain_registered(
                {
                    "id": b.id,
                    "display_name": b.display_name,
                    "capabilities": list(b.capabilities),
                }
            )
        engine = EvolutionEngine(
            brain_registry=populated_registry,
            capability_graph=graph,
            collaboration_network=net,
        )
        recs = await engine.analyze_collaboration_opportunities()
        # Alpha has {chat, code}, Beta has {chat, vision} — complementary
        titles = [r.title for r in recs]
        assert any("Alpha" in t and "Beta" in t for t in titles)

    @pytest.mark.asyncio
    async def test_analyze_performance_optimizations_demotes_low_success(self, populated_registry):
        net = CollaborationNetwork()
        # Make b3 have many failed collaborations
        for _ in range(5):
            net.record_collaboration("b3", "b1", success=False)
        engine = EvolutionEngine(
            brain_registry=populated_registry,
            collaboration_network=net,
        )
        recs = await engine.analyze_performance_optimizations()
        titles = [r.title for r in recs]
        assert any("Demote" in t and "Gamma" in t for t in titles)

    @pytest.mark.asyncio
    async def test_analyze_all_runs_every_analyzer(
        self, populated_registry, exec_memory, cog_memory
    ):
        graph = CapabilityGraph()
        net = CollaborationNetwork()
        for b in await populated_registry.list_all():
            graph.apply_brain_registered(
                {
                    "id": b.id,
                    "display_name": b.display_name,
                    "capabilities": list(b.capabilities),
                }
            )
        engine = EvolutionEngine(
            brain_registry=populated_registry,
            exec_memory=exec_memory,
            cognitive_memory=cog_memory,
            capability_graph=graph,
            collaboration_network=net,
        )
        recs = await engine.analyze_all()
        # Should produce at least some recommendations
        assert isinstance(recs, list)
        assert engine.stats()["analyses_run"] == 1

    def test_list_recommendations_filters_by_type(self):
        from agentic_os.core.ecosystem.domain import EvolutionRecommendation

        engine = EvolutionEngine()
        engine._recommendations = [
            EvolutionRecommendation(type=RecommendationType.CAPABILITY, title="c1"),
            EvolutionRecommendation(type=RecommendationType.ROUTING, title="r1"),
            EvolutionRecommendation(type=RecommendationType.CAPABILITY, title="c2"),
        ]
        cap_only = engine.list_recommendations(rec_type=RecommendationType.CAPABILITY)
        assert len(cap_only) == 2
        routing_only = engine.list_recommendations(rec_type=RecommendationType.ROUTING)
        assert len(routing_only) == 1


# ── TaskMarketplace ────────────────────────────────────────────────────


class TestTaskMarketplace:
    @pytest.mark.asyncio
    async def test_publish_task_collects_bids_from_eligible_runtimes(self, bus, populated_registry):
        m = TaskMarketplace(brain_registry=populated_registry, bus=bus)
        task = await m.publish_task(
            title="Chat task",
            required_capabilities=["chat"],
        )
        # Alpha and Beta both have "chat" — should bid
        assert len(task.bids) == 2
        assert task.status == "bidding"

    @pytest.mark.asyncio
    async def test_publish_task_with_no_matching_capability_gets_no_bids(
        self, bus, populated_registry
    ):
        m = TaskMarketplace(brain_registry=populated_registry, bus=bus)
        task = await m.publish_task(
            title="Rare task",
            required_capabilities=["nonexistent_cap"],
        )
        assert len(task.bids) == 0

    @pytest.mark.asyncio
    async def test_select_bid_balanced_chooses_best_score(self, bus, populated_registry):
        m = TaskMarketplace(brain_registry=populated_registry, bus=bus)
        task = await m.publish_task(
            title="Code task",
            required_capabilities=["code"],
        )
        # Alpha and Gamma have "code" — Alpha is healthier
        bid = await m.select_bid(task.id, strategy=TaskBidStrategy.BALANCED)
        assert bid is not None
        assert bid.runtime_id == "b1"  # Alpha has health=95, latency=50
        assert task.selected_bid is bid
        assert task.status == "awarded"
        assert "balanced" in task.selection_rationale

    @pytest.mark.asyncio
    async def test_select_bid_health_optimized_prefers_healthier(self, bus, populated_registry):
        m = TaskMarketplace(brain_registry=populated_registry, bus=bus)
        task = await m.publish_task(
            title="Chat task",
            required_capabilities=["chat"],
        )
        # Health strategy → Alpha (95) beats Beta (70)
        bid = await m.select_bid(task.id, strategy=TaskBidStrategy.HEALTH_OPTIMIZED)
        assert bid.runtime_id == "b1"

    @pytest.mark.asyncio
    async def test_select_bid_latency_optimized_prefers_faster(self, bus, populated_registry):
        m = TaskMarketplace(brain_registry=populated_registry, bus=bus)
        task = await m.publish_task(
            title="Chat task",
            required_capabilities=["chat"],
        )
        # Latency strategy → Alpha (50ms) beats Beta (200ms)
        bid = await m.select_bid(task.id, strategy=TaskBidStrategy.LATENCY_OPTIMIZED)
        assert bid.runtime_id == "b1"

    @pytest.mark.asyncio
    async def test_complete_task_updates_stats_and_history(self, bus, populated_registry):
        m = TaskMarketplace(
            brain_registry=populated_registry,
            collaboration_network=CollaborationNetwork(),
            bus=bus,
        )
        task = await m.publish_task(title="T1", required_capabilities=["chat"])
        await m.select_bid(task.id)
        await m.complete_task(task.id, success=True, result={"output": "done"})
        assert task.status == "completed"
        assert task.completed_at != ""
        stats = m.stats()
        assert stats["completed"] == 1
        history = m.get_history()
        assert len(history) == 1
        assert history[0]["success"] is True

    @pytest.mark.asyncio
    async def test_cancel_task(self, bus, populated_registry):
        m = TaskMarketplace(brain_registry=populated_registry, bus=bus)
        task = await m.publish_task(title="T1", required_capabilities=["chat"])
        ok = await m.cancel_task(task.id, reason="user request")
        assert ok is True
        assert task.status == "cancelled"
        assert m.stats()["cancelled"] == 1

    @pytest.mark.asyncio
    async def test_bid_score_never_random(self, bus, populated_registry):
        """Bid scores must be deterministic — same inputs produce same scores."""
        m1 = TaskMarketplace(brain_registry=populated_registry, bus=bus)
        m2 = TaskMarketplace(brain_registry=populated_registry, bus=bus)
        t1 = await m1.publish_task(title="T", required_capabilities=["chat"])
        t2 = await m2.publish_task(title="T", required_capabilities=["chat"])
        await m1.select_bid(t1.id)
        await m2.select_bid(t2.id)
        # Same bid scores for identical inputs
        scores1 = sorted(b.bid_score for b in t1.bids)
        scores2 = sorted(b.bid_score for b in t2.bids)
        assert scores1 == scores2


# ── EcosystemManager ───────────────────────────────────────────────────


class TestEcosystemManager:
    @pytest.mark.asyncio
    async def test_manager_starts_and_populates_graph(self, bus, populated_registry):
        mgr = EcosystemManager(bus=bus, brain_registry=populated_registry)
        await mgr.start()
        try:
            # Graph should be populated from registry
            assert len(mgr.capability_graph.list_nodes(NodeType.BRAIN)) == 3
            # Stats computed
            assert mgr.stats.total_runtimes == 3
            assert mgr.stats.healthy_runtimes >= 1
        finally:
            await mgr.stop()

    @pytest.mark.asyncio
    async def test_refresh_updates_stats(self, bus, populated_registry):
        mgr = EcosystemManager(bus=bus, brain_registry=populated_registry)
        await mgr.start()
        try:
            await mgr.refresh()
            assert mgr.stats.total_runtimes == 3
            assert mgr.stats.last_updated != ""
        finally:
            await mgr.stop()

    @pytest.mark.asyncio
    async def test_optimize_publishes_recommendations(
        self, bus, populated_registry, exec_memory, cog_memory
    ):
        mgr = EcosystemManager(
            bus=bus,
            brain_registry=populated_registry,
            exec_memory=exec_memory,
            cognitive_memory=cog_memory,
        )
        await mgr.start()
        try:
            result = await mgr.optimize()
            assert "recommendations" in result
            assert "stats" in result
        finally:
            await mgr.stop()

    @pytest.mark.asyncio
    async def test_rebuild_clears_and_repopulates(self, bus, populated_registry):
        mgr = EcosystemManager(bus=bus, brain_registry=populated_registry)
        await mgr.start()
        try:
            # Add some manual garbage to the graph
            mgr.capability_graph.add_node("garbage", NodeType.BRAIN, "Garbage")
            assert mgr.capability_graph.get_node("garbage") is not None
            # Rebuild
            result = await mgr.rebuild()
            assert result["rebuilt"] is True
            # Garbage should be gone
            assert mgr.capability_graph.get_node("garbage") is None
            # Real brains should be back
            assert len(mgr.capability_graph.list_nodes(NodeType.BRAIN)) == 3
        finally:
            await mgr.stop()

    @pytest.mark.asyncio
    async def test_health_levels(self, bus, populated_registry):
        mgr = EcosystemManager(bus=bus, brain_registry=populated_registry)
        await mgr.start()
        try:
            await mgr.refresh()
            # With Alpha(95) + Beta(70) + Gamma(30), the ecosystem has
            # mixed health. The level must be a valid enum value and the
            # score must be normalized to [0, 1].
            assert mgr.health.level in set(EcosystemHealthLevel)
            assert mgr.health.level != EcosystemHealthLevel.OFFLINE
            assert 0.0 <= mgr.health.health_score <= 1.0
            # Sub-scores must also be normalized
            for score_attr in (
                "availability_score",
                "performance_score",
                "collaboration_score",
                "evolution_score",
            ):
                value = getattr(mgr.health, score_attr)
                assert 0.0 <= value <= 1.0, f"{score_attr}={value} out of [0,1]"
        finally:
            await mgr.stop()

    @pytest.mark.asyncio
    async def test_health_offline_when_no_runtimes(self, bus):
        empty_registry = BrainRegistry()
        await empty_registry.start()
        try:
            mgr = EcosystemManager(bus=bus, brain_registry=empty_registry)
            await mgr.start()
            try:
                await mgr.refresh()
                assert mgr.health.level == EcosystemHealthLevel.OFFLINE
                assert mgr.stats.total_runtimes == 0
            finally:
                await mgr.stop()
        finally:
            await empty_registry.stop()


# ── EcosystemController (event subscriptions + autonomous loop) ────────


class TestEcosystemController:
    @pytest.mark.asyncio
    async def test_controller_starts_and_publishes_started_event(
        self, bus, populated_registry, exec_memory, cog_memory
    ):
        events: list[Any] = []

        async def capture(e):
            events.append(e)

        sub_id = await bus.subscribe("ecosystem.started", capture)
        try:
            ec = EcosystemController(
                bus=bus,
                brain_registry=populated_registry,
                exec_memory=exec_memory,
                cognitive_memory=cog_memory,
            )
            await ec.start()
            try:
                # Give the bus a moment to deliver
                await asyncio.sleep(0.05)
                assert ec.started is True
                assert any(e.topic == "ecosystem.started" for e in events)
            finally:
                await ec.stop()
        finally:
            await bus.unsubscribe(sub_id)

    @pytest.mark.asyncio
    async def test_brain_registered_event_updates_graph(
        self, bus, populated_registry, exec_memory, cog_memory
    ):
        ec = EcosystemController(
            bus=bus,
            brain_registry=populated_registry,
            exec_memory=exec_memory,
            cognitive_memory=cog_memory,
        )
        await ec.start()
        try:
            from agentic_os.domain.events import EventEnvelope

            initial_count = len(ec.manager.capability_graph.list_nodes(NodeType.BRAIN))
            # Publish a new brain.registered event
            await bus.publish(
                EventEnvelope(
                    type="brain.registered",
                    source="test",
                    topic="brain.registered",
                    payload={
                        "id": "b_new",
                        "display_name": "NewBrain",
                        "capabilities": ["new_cap"],
                        "health": 90,
                        "latency": 100,
                    },
                )
            )
            await asyncio.sleep(0.05)
            after_count = len(ec.manager.capability_graph.list_nodes(NodeType.BRAIN))
            assert after_count == initial_count + 1
            assert ec.manager.capability_graph.get_node("b_new") is not None
        finally:
            await ec.stop()

    @pytest.mark.asyncio
    async def test_brain_removed_event_removes_from_graph(
        self, bus, populated_registry, exec_memory, cog_memory
    ):
        ec = EcosystemController(
            bus=bus,
            brain_registry=populated_registry,
            exec_memory=exec_memory,
            cognitive_memory=cog_memory,
        )
        await ec.start()
        try:
            from agentic_os.domain.events import EventEnvelope

            # Confirm b1 is in graph initially
            assert ec.manager.capability_graph.get_node("b1") is not None
            await bus.publish(
                EventEnvelope(
                    type="brain.removed",
                    source="test",
                    topic="brain.removed",
                    payload={"id": "b1"},
                )
            )
            await asyncio.sleep(0.05)
            assert ec.manager.capability_graph.get_node("b1") is None
        finally:
            await ec.stop()

    @pytest.mark.asyncio
    async def test_mission_completed_triggers_optimization(
        self, bus, populated_registry, exec_memory, cog_memory
    ):
        ec = EcosystemController(
            bus=bus,
            brain_registry=populated_registry,
            exec_memory=exec_memory,
            cognitive_memory=cog_memory,
        )
        await ec.start()
        try:
            from agentic_os.domain.events import EventEnvelope

            initial = ec._optimizations_triggered
            await bus.publish(
                EventEnvelope(
                    type="mission.completed",
                    source="test",
                    topic="mission.completed",
                    payload={
                        "mission_id": "m1",
                        "members": [{"id": "b1"}, {"id": "b2"}],
                    },
                )
            )
            await asyncio.sleep(0.1)
            # Optimization should have been triggered
            assert ec._optimizations_triggered > initial
        finally:
            await ec.stop()

    @pytest.mark.asyncio
    async def test_swarm_execution_completed_records_collaboration(
        self, bus, populated_registry, exec_memory, cog_memory
    ):
        ec = EcosystemController(
            bus=bus,
            brain_registry=populated_registry,
            exec_memory=exec_memory,
            cognitive_memory=cog_memory,
        )
        await ec.start()
        try:
            from agentic_os.domain.events import EventEnvelope

            await bus.publish(
                EventEnvelope(
                    type="swarm.execution.completed",
                    source="test",
                    topic="swarm.execution.completed",
                    payload={
                        "swarm_id": "s1",
                        "members": [{"id": "b1"}, {"id": "b2"}],
                        "success": True,
                    },
                )
            )
            await asyncio.sleep(0.05)
            # Collaboration should be recorded
            link = ec.manager.collaboration_network.get_link("b1", "b2")
            assert link is not None
            assert link.successful == 1
        finally:
            await ec.stop()


# ── REST API ──────────────────────────────────────────────────────────


class TestEcosystemAPI:
    @pytest.fixture
    async def app_with_ecosystem(self, bus, populated_registry, exec_memory, cog_memory):
        """Build a real Kernel-backed app and inject our test EcosystemController.

        Using Kernel.platform() ensures the full Platform dataclass (with
        orchestrator / scheduler / etc.) is present, which create_app()
        expects. We then attach our test EcosystemController so the
        /api/ecosystem/* endpoints have a populated instance to query.
        """
        from agentic_os.api.app import create_app
        from agentic_os.kernel import Kernel

        kernel = Kernel()
        platform = kernel.platform()
        # Attach our test bus + registry + ecosystem controller
        platform.bus = bus
        platform.brain_registry = populated_registry

        ec = EcosystemController(
            bus=bus,
            brain_registry=populated_registry,
            exec_memory=exec_memory,
            cognitive_memory=cog_memory,
        )
        await ec.start()
        platform.ecosystem_controller = ec

        app = create_app(platform)
        try:
            yield app
        finally:
            await ec.stop()

    def test_ecosystem_status_endpoint(self, app_with_ecosystem):
        with TestClient(app_with_ecosystem) as client:
            r = client.get("/api/ecosystem/status")
            assert r.status_code == 200
            data = r.json()
            assert data["started"] is True

    def test_ecosystem_health_endpoint(self, app_with_ecosystem):
        with TestClient(app_with_ecosystem) as client:
            r = client.get("/api/ecosystem/health")
            assert r.status_code == 200
            data = r.json()
            assert "level" in data
            assert "health_score" in data

    def test_ecosystem_capabilities_endpoint(self, app_with_ecosystem):
        with TestClient(app_with_ecosystem) as client:
            r = client.get("/api/ecosystem/capabilities")
            assert r.status_code == 200
            data = r.json()
            assert "nodes" in data
            assert "edges" in data
            assert "stats" in data

    def test_ecosystem_collaborations_endpoint(self, app_with_ecosystem):
        with TestClient(app_with_ecosystem) as client:
            r = client.get("/api/ecosystem/collaborations")
            assert r.status_code == 200
            data = r.json()
            assert "links" in data
            assert "stats" in data

    def test_ecosystem_evolution_endpoint(self, app_with_ecosystem):
        with TestClient(app_with_ecosystem) as client:
            r = client.get("/api/ecosystem/evolution")
            assert r.status_code == 200
            data = r.json()
            assert "recommendations" in data
            assert "stats" in data

    def test_ecosystem_dashboard_endpoint(self, app_with_ecosystem):
        with TestClient(app_with_ecosystem) as client:
            r = client.get("/api/ecosystem/dashboard")
            assert r.status_code == 200
            data = r.json()
            assert "stats" in data
            assert "health" in data
            assert "graph_stats" in data
            assert "network_stats" in data

    def test_ecosystem_statistics_endpoint(self, app_with_ecosystem):
        with TestClient(app_with_ecosystem) as client:
            r = client.get("/api/ecosystem/statistics")
            assert r.status_code == 200
            data = r.json()
            assert "total_runtimes" in data
            assert data["total_runtimes"] == 3

    def test_ecosystem_analyze_endpoint(self, app_with_ecosystem):
        with TestClient(app_with_ecosystem) as client:
            r = client.post("/api/ecosystem/analyze")
            assert r.status_code == 200
            data = r.json()
            assert "recommendations" in data

    def test_ecosystem_optimize_endpoint(self, app_with_ecosystem):
        with TestClient(app_with_ecosystem) as client:
            r = client.post("/api/ecosystem/optimize")
            assert r.status_code == 200
            data = r.json()
            assert "optimization_run" in data
            assert data["optimization_run"] is True

    def test_ecosystem_evolve_endpoint(self, app_with_ecosystem):
        with TestClient(app_with_ecosystem) as client:
            r = client.post("/api/ecosystem/evolve")
            assert r.status_code == 200
            assert r.json()["optimization_run"] is True

    def test_ecosystem_rebuild_endpoint(self, app_with_ecosystem):
        with TestClient(app_with_ecosystem) as client:
            r = client.post("/api/ecosystem/rebuild")
            assert r.status_code == 200
            data = r.json()
            assert data["rebuilt"] is True

    def test_marketplace_publish_and_select(self, app_with_ecosystem):
        with TestClient(app_with_ecosystem) as client:
            # Publish
            r = client.post(
                "/api/ecosystem/marketplace/publish",
                json={
                    "title": "API Test Task",
                    "required_capabilities": ["chat"],
                    "priority": 0.7,
                },
            )
            assert r.status_code == 200
            task = r.json()
            assert task["status"] == "bidding"
            task_id = task["id"]
            # Select
            r = client.post(
                "/api/ecosystem/marketplace/select",
                json={"task_id": task_id, "strategy": "balanced"},
            )
            assert r.status_code == 200
            bid = r.json()
            assert bid["runtime_id"] in {"b1", "b2"}  # Alpha or Beta

    def test_marketplace_tasks_list(self, app_with_ecosystem):
        with TestClient(app_with_ecosystem) as client:
            # Publish a task first
            client.post(
                "/api/ecosystem/marketplace/publish",
                json={"title": "T1", "required_capabilities": ["chat"]},
            )
            r = client.get("/api/ecosystem/marketplace/tasks")
            assert r.status_code == 200
            tasks = r.json()
            assert len(tasks) >= 1

    def test_marketplace_stats(self, app_with_ecosystem):
        with TestClient(app_with_ecosystem) as client:
            r = client.get("/api/ecosystem/marketplace/stats")
            assert r.status_code == 200
            stats = r.json()
            assert "published" in stats
            assert "awarded" in stats


# ── WebSocket Propagation (DashboardBroadcaster) ──────────────────────


class TestDashboardBroadcasterEcosystemForwarding:
    def test_dashboard_topics_include_ecosystem_events(self):
        from agentic_os.api.dashboard import _DASHBOARD_TOPICS

        required = {
            "ecosystem.started",
            "ecosystem.updated",
            "ecosystem.health.updated",
            "ecosystem.evolution.generated",
            "ecosystem.optimization.started",
            "ecosystem.optimization.completed",
            "ecosystem.capability.updated",
            "ecosystem.collaboration.updated",
            "ecosystem.analysis.completed",
            "ecosystem.statistics.updated",
        }
        topic_set = set(_DASHBOARD_TOPICS)
        missing = required - topic_set
        assert not missing, f"Missing ecosystem topics: {missing}"

    @pytest.mark.asyncio
    async def test_broadcaster_forwards_ecosystem_events_to_clients(
        self, bus, populated_registry, exec_memory, cog_memory
    ):
        from agentic_os.api.dashboard import DashboardBroadcaster

        broadcaster = DashboardBroadcaster(bus=bus)
        await broadcaster.start()
        recv, send = broadcaster.add_client()
        received: list[dict[str, Any]] = []

        async def reader():
            async for ev in recv:
                received.append(ev)
                if len(received) >= 1:
                    break

        try:
            ec = EcosystemController(
                bus=bus,
                brain_registry=populated_registry,
                exec_memory=exec_memory,
                cognitive_memory=cog_memory,
            )
            await ec.start()
            try:
                # Trigger a refresh → publishes ecosystem.updated + others
                await ec.manager.refresh()
                # Wait for delivery
                with anyio_timeout(2.0):
                    await reader()
            finally:
                await ec.stop()
            # At least one ecosystem.* event should have been delivered
            assert any(ev["topic"].startswith("ecosystem.") for ev in received)
        finally:
            broadcaster.remove_client(send)
            await broadcaster.stop()


def anyio_timeout(seconds: float):
    """Compatibility shim — use anyio.move_on_after."""
    import anyio

    return anyio.move_on_after(seconds)


# ── Failure Recovery (brain.removed → swarm replacement integration) ──


class TestEcosystemFailureRecovery:
    @pytest.mark.asyncio
    async def test_brain_removed_updates_ecosystem_state(
        self, bus, populated_registry, exec_memory, cog_memory
    ):
        ec = EcosystemController(
            bus=bus,
            brain_registry=populated_registry,
            exec_memory=exec_memory,
            cognitive_memory=cog_memory,
        )
        await ec.start()
        try:
            # Initial state: 3 brains in graph
            assert len(ec.manager.capability_graph.list_nodes(NodeType.BRAIN)) == 3
            # Remove b1 from the registry — this publishes brain.removed
            # which the EcosystemController handles to update its graph.
            await populated_registry.unregister("b1")
            # LocalBus dispatches handlers as asyncio.create_task — give
            # them time to complete. 200ms is plenty for the in-process
            # graph mutation + refresh + publish chain.
            await asyncio.sleep(0.2)
            # Graph should reflect removal
            assert ec.manager.capability_graph.get_node("b1") is None
            # Stats should reflect removal (registry now has 2 brains)
            assert ec.manager.stats.total_runtimes == 2
        finally:
            await ec.stop()


# ── Dynamic Runtime Discovery ─────────────────────────────────────────


class TestDynamicRuntimeDiscovery:
    @pytest.mark.asyncio
    async def test_brain_registered_event_adds_to_ecosystem(
        self, bus, populated_registry, exec_memory, cog_memory
    ):
        ec = EcosystemController(
            bus=bus,
            brain_registry=populated_registry,
            exec_memory=exec_memory,
            cognitive_memory=cog_memory,
        )
        await ec.start()
        try:
            from agentic_os.domain.events import EventEnvelope

            # Publish brain.registered for a new runtime
            await bus.publish(
                EventEnvelope(
                    type="brain.registered",
                    source="test",
                    topic="brain.registered",
                    payload={
                        "id": "b_new",
                        "display_name": "NewRuntime",
                        "capabilities": ["chat", "vision"],
                        "health": 95,
                        "latency": 30,
                    },
                )
            )
            await asyncio.sleep(0.05)
            # Should be in graph
            node = ec.manager.capability_graph.get_node("b_new")
            assert node is not None
            assert node.label == "NewRuntime"
            # Should have PROVIDES edges for both capabilities
            caps = ec.manager.capability_graph.capabilities_of("b_new")
            assert "cap:chat" in caps
            assert "cap:vision" in caps
        finally:
            await ec.stop()
