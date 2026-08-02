"""Phase 15 — CapabilityGraph.

Live graph of Brain / Capability / Mission / Goal / Swarm nodes connected
by provides / depends_on / learned / shares / collaborates_with / executed
edges. Automatically updates whenever:

    brain.registered
    brain.updated
    brain.removed
    mission.completed
    goal.completed
    swarm.execution.completed

The graph is a pure consumer of the EventBus + BrainRegistry — it does
NOT publish discovery events and is NOT a second source of truth for
runtime data (BrainRegistry remains canonical).
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Any

from agentic_os.core.ecosystem.domain import (
    EdgeType,
    GraphEdge,
    GraphNode,
    NodeType,
)
from agentic_os.infrastructure.logging import get_logger

if TYPE_CHECKING:
    pass

log = get_logger("ecosystem.capability_graph")


class CapabilityGraph:
    """In-memory directed graph of ecosystem capabilities.

    Nodes are keyed by ``id``. Edges are keyed by ``(source, target, type)``
    so multiple typed edges can exist between the same pair.
    """

    def __init__(self) -> None:
        self._nodes: dict[str, GraphNode] = {}
        self._edges: dict[str, GraphEdge] = {}
        # Adjacency lists for fast traversal
        self._outgoing: dict[str, set[str]] = defaultdict(set)
        self._incoming: dict[str, set[str]] = defaultdict(set)
        self._updates_count = 0

    # ── Node CRUD ──────────────────────────────────────────────────

    def add_node(
        self,
        node_id: str,
        node_type: NodeType | str,
        label: str = "",
        properties: dict[str, Any] | None = None,
    ) -> GraphNode:
        """Insert or update a node. Updates bump ``updated_at``."""
        if isinstance(node_type, str):
            node_type = NodeType(node_type)
        existing = self._nodes.get(node_id)
        props = dict(properties or {})
        if existing is not None:
            existing.type = node_type
            if label:
                existing.label = label
            existing.properties.update(props)
            from datetime import UTC, datetime

            existing.updated_at = datetime.now(UTC).isoformat()
            self._updates_count += 1
            return existing
        node = GraphNode(
            id=node_id,
            type=node_type,
            label=label or node_id,
            properties=props,
        )
        self._nodes[node_id] = node
        self._updates_count += 1
        return node

    def remove_node(self, node_id: str) -> bool:
        """Remove a node and all edges touching it. Returns True if removed."""
        if node_id not in self._nodes:
            return False
        del self._nodes[node_id]
        # Cascade-remove edges
        for edge_key in list(self._edges.keys()):
            edge = self._edges[edge_key]
            if edge.source == node_id or edge.target == node_id:
                del self._edges[edge_key]
                self._outgoing[edge.source].discard(edge.target)
                self._incoming[edge.target].discard(edge.source)
        self._outgoing.pop(node_id, None)
        self._incoming.pop(node_id, None)
        self._updates_count += 1
        return True

    def get_node(self, node_id: str) -> GraphNode | None:
        return self._nodes.get(node_id)

    def list_nodes(self, node_type: NodeType | str | None = None) -> list[GraphNode]:
        if node_type is None:
            return list(self._nodes.values())
        if isinstance(node_type, str):
            node_type = NodeType(node_type)
        return [n for n in self._nodes.values() if n.type == node_type]

    # ── Edge CRUD ──────────────────────────────────────────────────

    def add_edge(
        self,
        source: str,
        target: str,
        edge_type: EdgeType | str,
        weight: float = 1.0,
        properties: dict[str, Any] | None = None,
    ) -> GraphEdge:
        if isinstance(edge_type, str):
            edge_type = EdgeType(edge_type)
        if source not in self._nodes:
            self.add_node(source, NodeType.BRAIN)
        if target not in self._nodes:
            self.add_node(target, NodeType.CAPABILITY)
        edge = GraphEdge(
            source=source,
            target=target,
            type=edge_type,
            weight=weight,
            properties=dict(properties or {}),
        )
        self._edges[edge.edge_id] = edge
        self._outgoing[source].add(target)
        self._incoming[target].add(source)
        self._updates_count += 1
        return edge

    def remove_edge(self, source: str, target: str, edge_type: EdgeType | str) -> bool:
        if isinstance(edge_type, str):
            edge_type = EdgeType(edge_type)
        edge = GraphEdge(source=source, target=target, type=edge_type)
        if edge.edge_id not in self._edges:
            return False
        del self._edges[edge.edge_id]
        self._outgoing[source].discard(target)
        self._incoming[target].discard(source)
        self._updates_count += 1
        return True

    def list_edges(self, edge_type: EdgeType | str | None = None) -> list[GraphEdge]:
        if edge_type is None:
            return list(self._edges.values())
        if isinstance(edge_type, str):
            edge_type = EdgeType(edge_type)
        return [e for e in self._edges.values() if e.type == edge_type]

    # ── Traversal ──────────────────────────────────────────────────

    def neighbors(self, node_id: str) -> list[str]:
        """Outgoing neighbors of ``node_id``."""
        return sorted(self._outgoing.get(node_id, set()))

    def reverse_neighbors(self, node_id: str) -> list[str]:
        """Incoming neighbors of ``node_id``."""
        return sorted(self._incoming.get(node_id, set()))

    def find_path(self, source: str, target: str, max_depth: int = 5) -> list[str]:
        """BFS shortest path between two nodes. Empty list if no path."""
        if source not in self._nodes or target not in self._nodes:
            return []
        if source == target:
            return [source]
        visited: set[str] = {source}
        queue: list[tuple[str, list[str]]] = [(source, [source])]
        while queue:
            current, path = queue.pop(0)
            if len(path) > max_depth:
                continue
            for neighbor in self._outgoing.get(current, set()):
                if neighbor == target:
                    return [*path, neighbor]
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, [*path, neighbor]))
        return []

    def subgraph(self, node_ids: set[str]) -> tuple[list[GraphNode], list[GraphEdge]]:
        """Return the induced subgraph on ``node_ids``."""
        nodes = [self._nodes[n] for n in node_ids if n in self._nodes]
        edges = [e for e in self._edges.values() if e.source in node_ids and e.target in node_ids]
        return nodes, edges

    # ── Queries ────────────────────────────────────────────────────

    def providers_of(self, capability: str) -> list[str]:
        """Return all brain node ids that ``provides`` a capability."""
        cap_id = f"cap:{capability}"
        return [
            e.source
            for e in self._edges.values()
            if e.type == EdgeType.PROVIDES and e.target == cap_id
        ]

    def capabilities_of(self, brain_id: str) -> list[str]:
        """Return all capabilities provided by ``brain_id``."""
        return [
            e.target
            for e in self._edges.values()
            if e.type == EdgeType.PROVIDES and e.source == brain_id
        ]

    def collaborators_of(self, brain_id: str) -> list[str]:
        """Return all brains that ``brain_id`` has collaborated with."""
        return [
            e.target
            for e in self._edges.values()
            if e.type == EdgeType.COLLABORATES_WITH and e.source == brain_id
        ]

    def executed_missions_of(self, brain_id: str) -> list[str]:
        """Return all missions executed by ``brain_id``."""
        return [
            e.target
            for e in self._edges.values()
            if e.type == EdgeType.EXECUTED and e.source == brain_id
        ]

    # ── Statistics ─────────────────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        return {
            "total_nodes": len(self._nodes),
            "total_edges": len(self._edges),
            "nodes_by_type": {
                t.value: sum(1 for n in self._nodes.values() if n.type == t) for t in NodeType
            },
            "edges_by_type": {
                t.value: sum(1 for e in self._edges.values() if e.type == t) for t in EdgeType
            },
            "updates_count": self._updates_count,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": [n.to_dict() for n in self._nodes.values()],
            "edges": [e.to_dict() for e in self._edges.values()],
            "stats": self.stats(),
        }

    # ── Event-driven updaters ──────────────────────────────────────
    #
    # These methods are called by the EcosystemController when it
    # receives brain.* / mission.* / swarm.* events. They translate
    # the event payloads into graph mutations. They are deliberately
    # tolerant of malformed payloads (log + skip) so the graph never
    # crashes the bus.

    def apply_brain_registered(self, payload: dict[str, Any]) -> None:
        brain_id = str(payload.get("id", ""))
        if not brain_id:
            return
        display_name = str(payload.get("display_name", brain_id))
        caps = list(payload.get("capabilities", []) or [])
        vendor = str(payload.get("vendor", "unknown"))
        health = float(payload.get("health", 100) or 0)
        latency = float(payload.get("latency", 0) or 0)

        self.add_node(
            brain_id,
            NodeType.BRAIN,
            label=display_name,
            properties={
                "vendor": vendor,
                "health": health,
                "latency": latency,
                "capabilities": caps,
            },
        )
        # Brain → provides → Capability
        for cap in caps:
            cap_id = f"cap:{cap}"
            self.add_node(cap_id, NodeType.CAPABILITY, label=cap)
            self.add_edge(brain_id, cap_id, EdgeType.PROVIDES)

    def apply_brain_updated(self, payload: dict[str, Any]) -> None:
        brain_id = str(payload.get("id", ""))
        if not brain_id:
            return
        if brain_id not in self._nodes:
            self.apply_brain_registered(payload)
            return
        node = self._nodes[brain_id]
        node.properties.update(
            {
                "health": float(payload.get("health", node.properties.get("health", 0)) or 0),
                "latency": float(payload.get("latency", node.properties.get("latency", 0)) or 0),
            }
        )
        # If capabilities changed, rewire PROVIDES edges
        new_caps = list(payload.get("capabilities", []) or [])
        if new_caps:
            current_caps = set(self.capabilities_of(brain_id))
            desired_caps = {f"cap:{c}" for c in new_caps}
            for cap_id in current_caps - desired_caps:
                self.remove_edge(brain_id, cap_id, EdgeType.PROVIDES)
            for cap_id in desired_caps - current_caps:
                cap_name = cap_id.removeprefix("cap:")
                self.add_node(cap_id, NodeType.CAPABILITY, label=cap_name)
                self.add_edge(brain_id, cap_id, EdgeType.PROVIDES)
        from datetime import UTC, datetime

        node.updated_at = datetime.now(UTC).isoformat()

    def apply_brain_removed(self, payload: dict[str, Any]) -> None:
        brain_id = str(payload.get("id", ""))
        if brain_id:
            self.remove_node(brain_id)

    def apply_mission_completed(self, payload: dict[str, Any]) -> None:
        mission_id = str(payload.get("mission_id") or payload.get("id") or "")
        if not mission_id:
            return
        self.add_node(
            mission_id,
            NodeType.MISSION,
            label=str(payload.get("title", mission_id)),
            properties={
                "status": "completed",
                "goal": payload.get("goal", ""),
                "completed_at": payload.get("completed_at", ""),
            },
        )
        # If members are listed, draw EXECUTED edges + pairwise COLLABORATES_WITH
        members = payload.get("members") or payload.get("agents") or []
        member_ids: list[str] = []
        for m in members:
            member_id = str(m if isinstance(m, str) else (m.get("id") or m.get("brain_id") or ""))
            if member_id and member_id in self._nodes:
                self.add_edge(member_id, mission_id, EdgeType.EXECUTED)
                member_ids.append(member_id)
        # Pairwise COLLABORATES_WITH edges among members that executed together
        for i, a in enumerate(member_ids):
            for b in member_ids[i + 1 :]:
                self.add_edge(a, b, EdgeType.COLLABORATES_WITH)
                self.add_edge(b, a, EdgeType.COLLABORATES_WITH)

    def apply_goal_completed(self, payload: dict[str, Any]) -> None:
        goal_id = str(payload.get("goal_id") or payload.get("id") or "")
        if not goal_id:
            return
        self.add_node(
            goal_id,
            NodeType.GOAL,
            label=str(payload.get("title", goal_id)),
            properties={"status": "completed", "priority": payload.get("priority", "")},
        )

    def apply_swarm_completed(self, payload: dict[str, Any]) -> None:
        swarm_id = str(payload.get("swarm_id") or payload.get("id") or "")
        if not swarm_id:
            return
        self.add_node(
            swarm_id,
            NodeType.SWARM,
            label=str(payload.get("goal", swarm_id)),
            properties={
                "completed": payload.get("completed", 0),
                "failed": payload.get("failed", 0),
                "phase": "completed",
            },
        )
        members = payload.get("members") or []
        member_ids: list[str] = []
        for m in members:
            member_id = str(m if isinstance(m, str) else (m.get("id") or ""))
            if member_id and member_id in self._nodes:
                # Member executed the swarm
                self.add_edge(member_id, swarm_id, EdgeType.EXECUTED)
                member_ids.append(member_id)
        # Pairwise COLLABORATES_WITH edges among members
        for i, a in enumerate(member_ids):
            for b in member_ids[i + 1 :]:
                self.add_edge(a, b, EdgeType.COLLABORATES_WITH)
                self.add_edge(b, a, EdgeType.COLLABORATES_WITH)

    def clear(self) -> None:
        self._nodes.clear()
        self._edges.clear()
        self._outgoing.clear()
        self._incoming.clear()
        self._updates_count += 1
