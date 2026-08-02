"""Knowledge Graph — relationships between entities.

Represents relationships between Goals, Missions, Brains, Capabilities,
Events, Reflections, Objectives, Failures, and Decisions.
Provides: graph traversal, relationship lookup, dependency lookup, impact analysis.
"""

from __future__ import annotations

from typing import Any

from agentic_os.core.cognitive.memory import CognitiveMemory
from agentic_os.infrastructure.logging import get_logger

log = get_logger("cognitive.knowledge_graph")


class KnowledgeGraph:
    """Builds and queries a knowledge graph of entity relationships."""

    def __init__(self, memory: CognitiveMemory) -> None:
        self._mem = memory

    async def add_entity(self, entity_id: str, entity_type: str, data: dict[str, Any]) -> None:
        await self._mem.add_kg_node(entity_id, entity_type, data)

    async def link(
        self, source: str, target: str, rel_type: str, data: dict[str, Any] | None = None
    ) -> None:
        await self._mem.add_kg_edge(source, target, rel_type, data)

    async def get_graph(self) -> dict[str, Any]:
        return await self._mem.get_kg()

    async def neighbors(self, node_id: str) -> list[dict[str, Any]]:
        return await self._mem.kg_neighbors(node_id)

    async def find_paths(self, source: str, target: str, max_depth: int = 5) -> list[list[str]]:
        """BFS graph traversal from source to target."""
        graph = await self._mem.get_kg()
        adj: dict[str, list[str]] = {}
        for e in graph["edges"]:
            adj.setdefault(e["source"], []).append(e["target"])
            adj.setdefault(e["target"], []).append(e["source"])
        if source not in adj or target not in adj:
            return []
        paths: list[list[str]] = []
        queue: list[tuple[str, list[str]]] = [(source, [source])]
        visited: set[str] = {source}
        while queue:
            node, path = queue.pop(0)
            if node == target:
                paths.append(path)
                continue
            if len(path) >= max_depth:
                continue
            for neighbor in adj.get(node, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, path + [neighbor]))
        return paths

    async def impact_analysis(self, entity_id: str, max_depth: int = 3) -> dict[str, Any]:
        """Analyze what entities would be impacted by a change to entity_id."""
        graph = await self._mem.get_kg()
        adj: dict[str, list[str]] = {}
        for e in graph["edges"]:
            adj.setdefault(e["source"], []).append(e["target"])
            adj.setdefault(e["target"], []).append(e["source"])
        visited: set[str] = set()
        queue: list[tuple[str, int]] = [(entity_id, 0)]
        while queue:
            node, depth = queue.pop(0)
            if depth > max_depth or node in visited:
                continue
            visited.add(node)
            for neighbor in adj.get(node, []):
                if neighbor not in visited:
                    queue.append((neighbor, depth + 1))
        visited.discard(entity_id)
        return {"impacted_entities": list(visited), "count": len(visited)}
