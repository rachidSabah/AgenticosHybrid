"""In-memory implementations of the Memory ports.

Ships as the default (zero-infra) backend and is the reference for the
:class:`MemoryStore` / :class:`VectorStore` / :class:`KnowledgeGraph` protocols.
Vector search is brute-force cosine over stored embeddings; the graph is a
plain adjacency map. A real deployment swaps these adapters for a vector DB /
graph database without changing the ports or the manager.
"""

from __future__ import annotations

import math
from collections import defaultdict

from agentic_os.domain.memory import MemoryItem, MemoryScope
from agentic_os.ports.memory import KnowledgeGraph, MemoryStore, VectorStore


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


class InMemoryVectorStore(VectorStore):
    """Brute-force cosine similarity over in-memory embeddings."""

    def __init__(self) -> None:
        self._items: dict[str, MemoryItem] = {}

    async def upsert(self, item: MemoryItem) -> None:
        self._items[item.id] = item

    async def nearest(
        self, scope: MemoryScope, vector: list[float], limit: int, agent_id: str
    ) -> list[MemoryItem]:
        if not vector:
            return []
        scored = []
        for it in self._items.values():
            if it.scope != scope:
                continue
            if agent_id and it.agent_id and it.agent_id != agent_id:
                continue
            score = _cosine(vector, it.embedding)
            scored.append((score, it))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [it for _, it in scored[:limit]]

    async def remove(self, item_id: str) -> None:
        self._items.pop(item_id, None)


class InMemoryKnowledgeGraph(KnowledgeGraph):
    """Simple adjacency-list graph keyed by scope."""

    def __init__(self) -> None:
        self._edges: dict[MemoryScope, dict[str, list[tuple[str, str]]]] = defaultdict(
            lambda: defaultdict(list)
        )
        self._props: dict[str, dict] = {}

    async def add_entity(self, scope: MemoryScope, entity: str, props: dict | None = None) -> None:
        self._props[entity] = props or {}

    async def link(self, scope: MemoryScope, a: str, relation: str, b: str) -> None:
        self._edges[scope][a].append((relation, b))

    async def neighbors(self, scope: MemoryScope, entity: str) -> list[dict]:
        return [{"relation": rel, "target": tgt} for rel, tgt in self._edges[scope].get(entity, [])]


class InMemoryStore(MemoryStore):
    """Primary in-memory :class:`MemoryStore`."""

    def __init__(self) -> None:
        self._by_id: dict[str, MemoryItem] = {}
        self._by_scope_key: dict[tuple[str, str], str] = {}

    async def put(self, item: MemoryItem) -> MemoryItem:
        self._by_id[item.id] = item
        self._by_scope_key[(item.scope.value, item.key)] = item.id
        return item

    async def get(self, scope: MemoryScope, key: str) -> MemoryItem | None:
        item_id = self._by_scope_key.get((scope.value, key))
        return self._by_id.get(item_id) if item_id else None

    async def get_by_id(self, item_id: str) -> MemoryItem | None:
        return self._by_id.get(item_id)

    async def search(
        self, scope: MemoryScope, query: str, limit: int = 10, agent_id: str = ""
    ) -> list[MemoryItem]:
        q = query.lower()
        hits = [
            it
            for it in self._by_id.values()
            if it.scope == scope
            and (not agent_id or not it.agent_id or it.agent_id == agent_id)
            and (q in it.key.lower() or q in it.value.lower())
        ]
        return hits[:limit]

    async def list_scope(self, scope: MemoryScope, agent_id: str = "") -> list[MemoryItem]:
        return [
            it
            for it in self._by_id.values()
            if it.scope == scope and (not agent_id or not it.agent_id or it.agent_id == agent_id)
        ]

    async def delete(self, item_id: str) -> bool:
        item = self._by_id.pop(item_id, None)
        if item is None:
            return False
        self._by_scope_key.pop((item.scope.value, item.key), None)
        return True
