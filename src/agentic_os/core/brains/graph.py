"""BrainRelationshipGraph — directed edges between brains in the constellation.

Maintains a directed graph of relationships (edges) between brains and
can produce :class:`ConstellationGraph` snapshots for downstream consumers.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from agentic_os.domain.brains import (
    BrainRelationship,
    ConstellationGraph,
    RelationshipType,
)
from agentic_os.domain.events import EventEnvelope, Topic
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.event_bus import EventBus

log = get_logger("brains.graph")


class BrainRelationshipGraph:
    """Directed graph of relationships between brains.

    Each edge is a :class:`BrainRelationship` carrying a source, target,
    and relationship type.  The graph supports adding, removing, and
    querying edges, and can produce a :class:`ConstellationGraph` snapshot.

    Thread-safety
    -------------
    Internal state is guarded by an ``asyncio.Lock``.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._edges: list[BrainRelationship] = []
        self._nodes: set[str] = set()
        self._event_bus: EventBus | None = None

    # ── Lifecycle ───────────────────────────────────────────────────────────

    async def start(self, event_bus: EventBus | None = None) -> None:
        """Initialise the graph with an optional event bus.

        Args:
            event_bus: When provided, graph update events are published.
        """
        self._event_bus = event_bus
        log.info("BrainRelationshipGraph started")

    async def stop(self) -> None:
        """Clear the graph."""
        async with self._lock:
            self._edges.clear()
            self._nodes.clear()
        log.info("BrainRelationshipGraph stopped")

    # ── Edge management ─────────────────────────────────────────────────────

    async def add_edge(
        self,
        source_id: str,
        target_id: str,
        rel_type: RelationshipType,
        metadata: dict[str, Any] | None = None,
        weight: float = 1.0,
    ) -> BrainRelationship:
        """Add a directed edge between two brains.

        Both ``source_id`` and ``target_id`` are automatically tracked
        as graph nodes.

        Args:
            source_id: The source brain's ID.
            target_id: The target brain's ID.
            rel_type: The semantic relationship type.
            metadata: Optional arbitrary metadata for the edge.
            weight: Optional edge weight (default 1.0).

        Returns:
            The newly created :class:`BrainRelationship`.
        """
        rel = BrainRelationship(
            source_id=source_id,
            target_id=target_id,
            relationship_type=rel_type,
            metadata=metadata or {},
            created_at=datetime.now(UTC).isoformat(),
            weight=weight,
        )

        async with self._lock:
            self._edges.append(rel)
            self._nodes.add(source_id)
            self._nodes.add(target_id)

        await self._publish_update()
        return rel

    async def remove_edge(self, edge_index: int) -> bool:
        """Remove an edge by its index in the internal list.

        Args:
            edge_index: The index of the edge to remove.

        Returns:
            ``True`` if the index was valid and the edge was removed.
        """
        async with self._lock:
            if edge_index < 0 or edge_index >= len(self._edges):
                return False
            self._edges.pop(edge_index)

        await self._publish_update()
        return True

    async def remove_edges_between(self, source_id: str, target_id: str) -> int:
        """Remove all edges between two brains (in either direction).

        Args:
            source_id: The source brain's ID.
            target_id: The target brain's ID.

        Returns:
            The number of edges removed.
        """
        async with self._lock:
            before = len(self._edges)
            self._edges = [
                e
                for e in self._edges
                if not (
                    (e.source_id == source_id and e.target_id == target_id)
                    or (e.source_id == target_id and e.target_id == source_id)
                )
            ]
            count = before - len(self._edges)

        if count > 0:
            await self._publish_update()
        return count

    async def remove_node(self, brain_id: str) -> int:
        """Remove a brain and all its incident edges from the graph.

        Args:
            brain_id: The brain to remove.

        Returns:
            The number of edges removed.
        """
        async with self._lock:
            before = len(self._edges)
            self._edges = [
                e for e in self._edges if e.source_id != brain_id and e.target_id != brain_id
            ]
            self._nodes.discard(brain_id)
            count = before - len(self._edges)

        if count > 0:
            await self._publish_update()
        return count

    # ── Query ───────────────────────────────────────────────────────────────

    async def get_edges(
        self,
        brain_id: str | None = None,
        rel_type: RelationshipType | None = None,
    ) -> list[BrainRelationship]:
        """Return edges, optionally filtered by brain or relationship type.

        Args:
            brain_id: When provided, only return edges where this brain
                is the source or target.
            rel_type: When provided, only return edges with this type.

        Returns:
            A list of matching :class:`BrainRelationship` objects.
        """
        async with self._lock:
            results = list(self._edges)

        if brain_id is not None:
            results = [e for e in results if e.source_id == brain_id or e.target_id == brain_id]
        if rel_type is not None:
            results = [e for e in results if e.relationship_type == rel_type]
        return results

    async def get_children(self, brain_id: str) -> list[tuple[str, RelationshipType]]:
        """Return (target_id, rel_type) pairs for all outgoing edges
        from *brain_id*."""
        async with self._lock:
            return [
                (e.target_id, e.relationship_type) for e in self._edges if e.source_id == brain_id
            ]

    async def get_parents(self, brain_id: str) -> list[tuple[str, RelationshipType]]:
        """Return (source_id, rel_type) pairs for all incoming edges
        to *brain_id*."""
        async with self._lock:
            return [
                (e.source_id, e.relationship_type) for e in self._edges if e.target_id == brain_id
            ]

    async def has_edge(self, source_id: str, target_id: str) -> bool:
        """Check if a direct edge exists between two brains."""
        async with self._lock:
            return any(e.source_id == source_id and e.target_id == target_id for e in self._edges)

    async def count_edges(self) -> int:
        """Return the total number of edges."""
        async with self._lock:
            return len(self._edges)

    async def count_nodes(self) -> int:
        """Return the total number of tracked nodes."""
        async with self._lock:
            return len(self._nodes)

    async def edge_count_for(self, brain_id: str) -> int:
        """Return the number of edges incident to a brain."""
        async with self._lock:
            return sum(1 for e in self._edges if e.source_id == brain_id or e.target_id == brain_id)

    # ── Constellation Graph ─────────────────────────────────────────────────

    async def to_constellation_graph(self) -> ConstellationGraph:
        """Produce a snapshot of the current graph as a
        :class:`ConstellationGraph`.

        The result is a frozen dataclass suitable for serialisation.
        """
        async with self._lock:
            return ConstellationGraph(
                nodes=tuple(sorted(self._nodes)),
                edges=tuple(self._edges),
                updated_at=datetime.now(UTC).isoformat(),
            )

    # ── Bulk operations ─────────────────────────────────────────────────────

    async def set_edges(self, edges: list[BrainRelationship]) -> None:
        """Replace all edges and rebuild the node set.

        Args:
            edges: The complete new list of relationships.
        """
        async with self._lock:
            self._edges = list(edges)
            self._nodes = set()
            for e in self._edges:
                self._nodes.add(e.source_id)
                self._nodes.add(e.target_id)

        await self._publish_update()
        log.debug("Replaced graph with %d edges and %d nodes", len(edges), len(self._nodes))

    async def clear(self) -> None:
        """Remove all edges and nodes."""
        async with self._lock:
            self._edges.clear()
            self._nodes.clear()
        await self._publish_update()
        log.info("Graph cleared")

    # ── Events ──────────────────────────────────────────────────────────────

    async def _publish_update(self) -> None:
        """Publish a graph update event."""
        bus = self._event_bus
        if bus is None:
            return
        try:
            graph = await self.to_constellation_graph()
            event = EventEnvelope(
                type=Topic.BRAIN_GRAPH_UPDATED.value,
                source="brain_relationship_graph",
                topic=Topic.BRAIN_GRAPH_UPDATED.value,
                payload=graph.to_dict(),
            )
            await bus.publish(event)
        except Exception:
            log.exception("Failed to publish graph update")
