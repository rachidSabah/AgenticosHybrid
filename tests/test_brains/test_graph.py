"""Tests for BrainRelationshipGraph — directed edges between brains.

Covers edge management, queries, constellation graph snapshots, bulk
operations, and event publishing.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

from agentic_os.core.brains.graph import BrainRelationshipGraph
from agentic_os.domain.brains import (
    BrainRelationship,
    ConstellationGraph,
    RelationshipType,
)
from agentic_os.domain.events import Topic

# ═══════════════════════════════════════════════════════════════════════
# Lifecycle
# ═══════════════════════════════════════════════════════════════════════


class TestBrainRelationshipGraphLifecycle:
    """start / stop behaviour."""

    async def test_initial_state(self) -> None:
        graph = BrainRelationshipGraph()
        assert graph._edges == []
        assert graph._nodes == set()
        assert graph._event_bus is None

    async def test_start_sets_event_bus(self, mock_event_bus: AsyncMock) -> None:
        graph = BrainRelationshipGraph()
        await graph.start(event_bus=mock_event_bus)
        assert graph._event_bus is mock_event_bus

    async def test_stop_clears_state(self) -> None:
        graph = BrainRelationshipGraph()
        await graph.start()
        await graph.add_edge("a", "b", RelationshipType.PEER)
        await graph.stop()
        assert graph._edges == []
        assert graph._nodes == set()

    async def test_stop_when_not_started_is_safe(self) -> None:
        graph = BrainRelationshipGraph()
        await graph.stop()  # should not raise


# ═══════════════════════════════════════════════════════════════════════
# Adding edges
# ═══════════════════════════════════════════════════════════════════════


class TestBrainRelationshipGraphAddEdge:
    """add_edge() — creation and node tracking."""

    async def test_add_edge_basic(self) -> None:
        graph = BrainRelationshipGraph()
        rel = await graph.add_edge("a", "b", RelationshipType.PEER)
        assert rel.source_id == "a"
        assert rel.target_id == "b"
        assert rel.relationship_type == RelationshipType.PEER
        assert abs(rel.weight - 1.0) < 0.01

    async def test_add_edge_tracks_nodes(self) -> None:
        graph = BrainRelationshipGraph()
        await graph.add_edge("a", "b", RelationshipType.PARENT)
        assert "a" in graph._nodes
        assert "b" in graph._nodes

    async def test_add_edge_tracks_multiple_nodes(self) -> None:
        graph = BrainRelationshipGraph()
        await graph.add_edge("a", "b", RelationshipType.PEER)
        await graph.add_edge("a", "c", RelationshipType.CHILD)
        assert len(graph._nodes) == 3

    async def test_add_edge_with_metadata(self) -> None:
        graph = BrainRelationshipGraph()
        rel = await graph.add_edge(
            "a",
            "b",
            RelationshipType.EXECUTOR,
            metadata={"role": "executor"},
            weight=2.5,
        )
        assert rel.metadata == {"role": "executor"}
        assert abs(rel.weight - 2.5) < 0.01

    async def test_add_edge_creates_timestamp(self) -> None:
        graph = BrainRelationshipGraph()
        rel = await graph.add_edge("a", "b", RelationshipType.PEER)
        assert rel.created_at != ""  # timestamp is set

    async def test_add_edge_publishes_update(
        self,
        mock_event_bus: AsyncMock,
    ) -> None:
        graph = BrainRelationshipGraph()
        await graph.start(event_bus=mock_event_bus)
        await graph.add_edge("a", "b", RelationshipType.PEER)
        mock_event_bus.publish.assert_called_once()
        assert mock_event_bus.publish.call_args[0][0].topic == Topic.BRAIN_GRAPH_UPDATED.value


# ═══════════════════════════════════════════════════════════════════════
# Removing edges
# ═══════════════════════════════════════════════════════════════════════


class TestBrainRelationshipGraphRemoveEdge:
    """remove_edge() — by index."""

    async def test_remove_edge_by_index(self) -> None:
        graph = BrainRelationshipGraph()
        await graph.add_edge("a", "b", RelationshipType.PEER)
        result = await graph.remove_edge(0)
        assert result is True
        assert len(graph._edges) == 0

    async def test_remove_edge_invalid_index(self) -> None:
        graph = BrainRelationshipGraph()
        result = await graph.remove_edge(5)
        assert result is False

    async def test_remove_edge_negative_index(self) -> None:
        graph = BrainRelationshipGraph()
        await graph.add_edge("a", "b", RelationshipType.PEER)
        result = await graph.remove_edge(-1)
        assert result is False

    async def test_remove_edge_publishes_update(
        self,
        mock_event_bus: AsyncMock,
    ) -> None:
        graph = BrainRelationshipGraph()
        await graph.start(event_bus=mock_event_bus)
        await graph.add_edge("a", "b", RelationshipType.PEER)
        mock_event_bus.publish.reset_mock()
        await graph.remove_edge(0)
        assert mock_event_bus.publish.called


class TestBrainRelationshipGraphRemoveEdgesBetween:
    """remove_edges_between() — remove all edges between two nodes."""

    async def test_remove_edges_between(self) -> None:
        graph = BrainRelationshipGraph()
        await graph.add_edge("a", "b", RelationshipType.PEER)
        await graph.add_edge("b", "a", RelationshipType.PEER)
        count = await graph.remove_edges_between("a", "b")
        assert count == 2
        assert len(graph._edges) == 0

    async def test_remove_edges_between_no_match(self) -> None:
        graph = BrainRelationshipGraph()
        await graph.add_edge("a", "b", RelationshipType.PEER)
        count = await graph.remove_edges_between("a", "c")
        assert count == 0
        assert len(graph._edges) == 1


class TestBrainRelationshipGraphRemoveNode:
    """remove_node() — remove a brain and all its incident edges."""

    async def test_remove_node_removes_edges(self) -> None:
        graph = BrainRelationshipGraph()
        await graph.add_edge("a", "b", RelationshipType.PEER)
        await graph.add_edge("a", "c", RelationshipType.CHILD)
        count = await graph.remove_node("a")
        assert count == 2
        assert len(graph._edges) == 0

    async def test_remove_node_removes_from_node_set(self) -> None:
        graph = BrainRelationshipGraph()
        await graph.add_edge("a", "b", RelationshipType.PEER)
        await graph.remove_node("a")
        assert "a" not in graph._nodes
        assert "b" in graph._nodes  # b still has no edges but remains

    async def test_remove_node_unknown(self) -> None:
        graph = BrainRelationshipGraph()
        await graph.add_edge("a", "b", RelationshipType.PEER)
        count = await graph.remove_node("unknown")
        assert count == 0
        assert len(graph._edges) == 1


# ═══════════════════════════════════════════════════════════════════════
# Querying edges
# ═══════════════════════════════════════════════════════════════════════


class TestBrainRelationshipGraphGetEdges:
    """get_edges() — filtered and unfiltered."""

    async def test_get_edges_all(self) -> None:
        graph = BrainRelationshipGraph()
        await graph.add_edge("a", "b", RelationshipType.PEER)
        await graph.add_edge("b", "c", RelationshipType.PARENT)
        edges = await graph.get_edges()
        assert len(edges) == 2

    async def test_get_edges_empty(self) -> None:
        graph = BrainRelationshipGraph()
        edges = await graph.get_edges()
        assert edges == []

    async def test_get_edges_filtered_by_brain_id(self) -> None:
        graph = BrainRelationshipGraph()
        await graph.add_edge("a", "b", RelationshipType.PEER)
        await graph.add_edge("b", "c", RelationshipType.PARENT)
        edges = await graph.get_edges(brain_id="a")
        assert len(edges) == 1
        assert edges[0].source_id == "a"

    async def test_get_edges_filtered_by_rel_type(self) -> None:
        graph = BrainRelationshipGraph()
        await graph.add_edge("a", "b", RelationshipType.PEER)
        await graph.add_edge("a", "c", RelationshipType.PARENT)
        edges = await graph.get_edges(rel_type=RelationshipType.PEER)
        assert len(edges) == 1
        assert edges[0].relationship_type == RelationshipType.PEER


class TestBrainRelationshipGraphGetChildren:
    """get_children() — outgoing edges."""

    async def test_get_children(self) -> None:
        graph = BrainRelationshipGraph()
        await graph.add_edge("a", "b", RelationshipType.CHILD)
        await graph.add_edge("a", "c", RelationshipType.DELEGATION)
        children = await graph.get_children("a")
        assert len(children) == 2
        targets = {t for t, _ in children}
        assert targets == {"b", "c"}

    async def test_get_children_no_outgoing(self) -> None:
        graph = BrainRelationshipGraph()
        await graph.add_edge("a", "b", RelationshipType.CHILD)
        children = await graph.get_children("b")
        assert children == []


class TestBrainRelationshipGraphGetParents:
    """get_parents() — incoming edges."""

    async def test_get_parents(self) -> None:
        graph = BrainRelationshipGraph()
        await graph.add_edge("a", "b", RelationshipType.PARENT)
        await graph.add_edge("c", "b", RelationshipType.PARENT)
        parents = await graph.get_parents("b")
        assert len(parents) == 2
        sources = {s for s, _ in parents}
        assert sources == {"a", "c"}

    async def test_get_parents_no_incoming(self) -> None:
        graph = BrainRelationshipGraph()
        await graph.add_edge("a", "b", RelationshipType.PARENT)
        parents = await graph.get_parents("a")
        assert parents == []


class TestBrainRelationshipGraphHasEdge:
    """has_edge() — existence check."""

    async def test_has_edge_true(self) -> None:
        graph = BrainRelationshipGraph()
        await graph.add_edge("a", "b", RelationshipType.PEER)
        assert await graph.has_edge("a", "b") is True

    async def test_has_edge_false_no_edge(self) -> None:
        graph = BrainRelationshipGraph()
        await graph.add_edge("a", "b", RelationshipType.PEER)
        assert await graph.has_edge("a", "c") is False

    async def test_has_edge_false_reverse(self) -> None:
        """Direction matters."""
        graph = BrainRelationshipGraph()
        await graph.add_edge("a", "b", RelationshipType.PEER)
        assert await graph.has_edge("b", "a") is False


# ═══════════════════════════════════════════════════════════════════════
# Counts
# ═══════════════════════════════════════════════════════════════════════


class TestBrainRelationshipGraphCounts:
    """count_edges(), count_nodes(), edge_count_for()."""

    async def test_count_edges(self) -> None:
        graph = BrainRelationshipGraph()
        assert await graph.count_edges() == 0
        await graph.add_edge("a", "b", RelationshipType.PEER)
        assert await graph.count_edges() == 1

    async def test_count_nodes(self) -> None:
        graph = BrainRelationshipGraph()
        assert await graph.count_nodes() == 0
        await graph.add_edge("a", "b", RelationshipType.PEER)
        assert await graph.count_nodes() == 2

    async def test_edge_count_for(self) -> None:
        graph = BrainRelationshipGraph()
        await graph.add_edge("a", "b", RelationshipType.PEER)
        await graph.add_edge("a", "c", RelationshipType.CHILD)
        assert await graph.edge_count_for("a") == 2
        assert await graph.edge_count_for("b") == 1


# ═══════════════════════════════════════════════════════════════════════
# Constellation graph snapshot
# ═══════════════════════════════════════════════════════════════════════


class TestBrainRelationshipGraphConstellationGraph:
    """to_constellation_graph() — serialisable snapshot."""

    async def test_empty_graph(self) -> None:
        graph = BrainRelationshipGraph()
        cg = await graph.to_constellation_graph()
        assert isinstance(cg, ConstellationGraph)
        assert cg.nodes == ()
        assert cg.edges == ()

    async def test_graph_with_edges(self) -> None:
        graph = BrainRelationshipGraph()
        await graph.add_edge("a", "b", RelationshipType.PEER)
        cg = await graph.to_constellation_graph()
        assert "a" in cg.nodes
        assert "b" in cg.nodes
        assert len(cg.edges) == 1
        assert cg.updated_at != ""

    async def test_nodes_are_sorted(self) -> None:
        graph = BrainRelationshipGraph()
        await graph.add_edge("z", "a", RelationshipType.PEER)
        cg = await graph.to_constellation_graph()
        assert cg.nodes == ("a", "z")  # sorted


# ═══════════════════════════════════════════════════════════════════════
# Bulk operations
# ═══════════════════════════════════════════════════════════════════════


class TestBrainRelationshipGraphBulk:
    """set_edges() and clear()."""

    async def test_set_edges_replaces_all(self) -> None:
        graph = BrainRelationshipGraph()
        await graph.add_edge("a", "b", RelationshipType.PEER)
        new_edges = [
            BrainRelationship(
                source_id="x",
                target_id="y",
                relationship_type=RelationshipType.PARENT,
            ),
        ]
        await graph.set_edges(new_edges)
        assert await graph.count_edges() == 1
        assert await graph.count_nodes() == 2
        assert "x" in graph._nodes
        assert "y" in graph._nodes
        assert "a" not in graph._nodes

    async def test_clear_removes_all(self) -> None:
        graph = BrainRelationshipGraph()
        await graph.add_edge("a", "b", RelationshipType.PEER)
        await graph.clear()
        assert await graph.count_edges() == 0
        assert await graph.count_nodes() == 0

    async def test_clear_publishes_event(
        self,
        mock_event_bus: AsyncMock,
    ) -> None:
        graph = BrainRelationshipGraph()
        await graph.start(event_bus=mock_event_bus)
        await graph.add_edge("a", "b", RelationshipType.PEER)
        mock_event_bus.publish.reset_mock()
        await graph.clear()
        mock_event_bus.publish.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════
# Event bus edge cases
# ═══════════════════════════════════════════════════════════════════════


class TestBrainRelationshipGraphEventBus:
    """Publishing edge cases."""

    async def test_no_event_bus_does_not_raise(self) -> None:
        graph = BrainRelationshipGraph()
        await graph.add_edge("a", "b", RelationshipType.PEER)  # no bus
        await graph.remove_edge(0)  # no bus

    async def test_event_bus_exception_caught(
        self,
        mock_event_bus: AsyncMock,
    ) -> None:
        mock_event_bus.publish.side_effect = RuntimeError("publish failed")
        graph = BrainRelationshipGraph()
        await graph.start(event_bus=mock_event_bus)
        await graph.add_edge("a", "b", RelationshipType.PEER)  # should not raise
