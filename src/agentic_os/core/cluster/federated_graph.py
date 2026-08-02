"""Phase 16 — FederatedKnowledgeGraph.

Extends the existing CapabilityGraph with cross-host support. Does
NOT replace CapabilityGraph — it subclasses it.

Adds:
  - Cross-host PROVIDES edges (brain on node A provides capability)
  - Cross-host COLLABORATES_WITH edges (brain on A collaborated with brain on B)
  - Cross-host EXECUTED edges (brain on A executed mission on B)
  - Cluster capability index (which nodes provide a capability)
  - Global impact analysis (which nodes are affected if a capability disappears)

All cross-host nodes are tagged with their ``node_id`` in properties.
The graph remains a pure consumer of brain.* + cluster.* events.
"""

from __future__ import annotations

from typing import Any

from agentic_os.core.ecosystem.capability_graph import CapabilityGraph
from agentic_os.core.ecosystem.domain import EdgeType, NodeType
from agentic_os.infrastructure.logging import get_logger

log = get_logger("cluster.federated_graph")


class FederatedKnowledgeGraph(CapabilityGraph):
    """CapabilityGraph + cross-host edges + cluster index."""

    def __init__(self) -> None:
        super().__init__()
        # Cluster capability index: capability → set of (node_id, brain_id)
        self._cluster_cap_index: dict[str, set[tuple[str, str]]] = {}
        # Cross-host collaboration index: (node_a, brain_a) → set of (node_b, brain_b)
        self._cross_host_collabs: dict[tuple[str, str], set[tuple[str, str]]] = {}

    # ── Cross-host node IDs ────────────────────────────────────────

    @staticmethod
    def _federated_brain_id(brain_id: str, node_id: str) -> str:
        """Generate a unique ID for a brain on a specific node.

        Local brains use just their brain_id (backward compat with
        CapabilityGraph). Remote brains use ``node_id:brain_id``.
        """
        if node_id == "local" or node_id == "":
            return brain_id
        return f"{node_id}:{brain_id}"

    # ── Cross-host operations ──────────────────────────────────────

    def add_remote_brain(
        self,
        brain_id: str,
        node_id: str,
        display_name: str = "",
        capabilities: list[str] | None = None,
        health: float = 100.0,
        latency: float = 0.0,
        provider: str = "",
    ) -> None:
        """Add a remote brain node + PROVIDES edges to its capabilities."""
        fed_id = self._federated_brain_id(brain_id, node_id)
        self.add_node(
            fed_id,
            NodeType.BRAIN,
            label=display_name or fed_id,
            properties={
                "node_id": node_id,
                "brain_id": brain_id,
                "scope": "remote",
                "health": health,
                "latency": latency,
                "provider": provider,
                "capabilities": list(capabilities or []),
            },
        )
        for cap in capabilities or []:
            cap_id = f"cap:{cap}"
            self.add_node(cap_id, NodeType.CAPABILITY, label=cap)
            self.add_edge(fed_id, cap_id, EdgeType.PROVIDES)
            # Update cluster index
            self._cluster_cap_index.setdefault(cap, set()).add((node_id, brain_id))

    def remove_remote_brain(self, brain_id: str, node_id: str) -> bool:
        """Remove a remote brain + cascade."""
        fed_id = self._federated_brain_id(brain_id, node_id)
        removed = self.remove_node(fed_id)
        if removed:
            # Purge from cluster index
            for cap_list in list(self._cluster_cap_index.values()):
                cap_list.discard((node_id, brain_id))
        return removed

    def record_cross_host_collaboration(
        self,
        brain_a: str,
        node_a: str,
        brain_b: str,
        node_b: str,
    ) -> None:
        """Record a collaboration between two brains on different nodes."""
        fed_a = self._federated_brain_id(brain_a, node_a)
        fed_b = self._federated_brain_id(brain_b, node_b)
        # Ensure both nodes exist
        if fed_a not in self._nodes:
            self.add_remote_brain(brain_a, node_a)
        if fed_b not in self._nodes:
            self.add_remote_brain(brain_b, node_b)
        self.add_edge(fed_a, fed_b, EdgeType.COLLABORATES_WITH)
        self.add_edge(fed_b, fed_a, EdgeType.COLLABORATES_WITH)
        self._cross_host_collabs.setdefault((node_a, brain_a), set()).add((node_b, brain_b))
        self._cross_host_collabs.setdefault((node_b, brain_b), set()).add((node_a, brain_a))

    def record_cross_host_mission(
        self,
        mission_id: str,
        executors: list[tuple[str, str]],
    ) -> None:
        """Record a mission executed by brains across multiple nodes.

        ``executors`` is a list of (brain_id, node_id) tuples.
        """
        self.add_node(
            mission_id,
            NodeType.MISSION,
            label=mission_id,
            properties={"scope": "cross-host", "executor_count": len(executors)},
        )
        for brain_id, node_id in executors:
            fed_id = self._federated_brain_id(brain_id, node_id)
            if fed_id not in self._nodes:
                self.add_remote_brain(brain_id, node_id)
            self.add_edge(fed_id, mission_id, EdgeType.EXECUTED)
        # Pairwise collaborations
        for i, (a_brain, a_node) in enumerate(executors):
            for b_brain, b_node in executors[i + 1 :]:
                self.record_cross_host_collaboration(a_brain, a_node, b_brain, b_node)

    # ── Cluster queries ────────────────────────────────────────────

    def cluster_providers_of(self, capability: str) -> list[tuple[str, str]]:
        """Return all (node_id, brain_id) pairs that provide a capability."""
        return sorted(self._cluster_cap_index.get(capability, set()))

    def cross_host_collaborators_of(self, brain_id: str, node_id: str) -> list[tuple[str, str]]:
        """Return all (brain_id, node_id) pairs that collaborated with this brain."""
        return sorted(self._cross_host_collabs.get((node_id, brain_id), set()))

    def global_impact_analysis(self, capability: str) -> dict[str, Any]:
        """Analyze what would be affected if a capability disappeared.

        Returns:
          - providers: list of (node_id, brain_id) currently providing it
          - dependent_missions: missions that used this capability
          - at_risk_nodes: nodes that would lose all providers of this capability
        """
        providers = self.cluster_providers_of(capability)
        # Group by node to find at-risk nodes
        nodes_with_cap: dict[str, list[str]] = {}
        for node_id, brain_id in providers:
            nodes_with_cap.setdefault(node_id, []).append(brain_id)
        # Find missions that used brains providing this capability
        dependent_missions: list[str] = []
        for edge in self._edges.values():
            if edge.type == EdgeType.EXECUTED and edge.source in [
                self._federated_brain_id(b, n) for n, b in providers
            ]:
                dependent_missions.append(edge.target)
        return {
            "capability": capability,
            "provider_count": len(providers),
            "providers": [(n, b) for n, b in providers],
            "nodes_with_capability": dict(nodes_with_cap),
            "dependent_mission_count": len(dependent_missions),
            "dependent_missions": dependent_missions[:20],
            "at_risk_nodes": list(nodes_with_cap.keys()),
        }

    def cluster_stats(self) -> dict[str, Any]:
        """Extended stats including cluster-specific metrics."""
        base = self.stats()
        return {
            **base,
            "cluster_capabilities_indexed": len(self._cluster_cap_index),
            "cross_host_collaborations": sum(len(v) for v in self._cross_host_collabs.values())
            // 2,  # each pair counted twice
            "nodes_represented": len({n for n, _ in self._cluster_cap_index.get("", set())}),
        }

    def clear(self) -> None:
        super().clear()
        self._cluster_cap_index.clear()
        self._cross_host_collabs.clear()
