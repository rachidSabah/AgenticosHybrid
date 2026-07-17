"""Ports: Memory System.

The Memory subsystem exposes four interfaces, each independently implementable:

* :class:`MemoryStore` — write/read/search/delete of :class:`MemoryItem`s,
  partitioned by :class:`MemoryScope`. This is the primary port the rest of the
  kernel depends on.
* :class:`VectorStore` — optional semantic search backend. The default in-memory
  store implements this trivially (brute-force cosine); a real deployment may
  swap in a dedicated vector DB without touching the rest of the system.
* :class:`KnowledgeGraph` — optional entity/relation store. The default is a
  simple in-memory graph; production may back it with a graph database.
* :class:`MemoryManager` — lifecycle orchestration over scopes and retention
  policies (TTL / max-size eviction).

All evolution of memory is observable: writes/evictions publish bus events
(:data:`Topic.MEMORY_WRITTEN` / :data:`Topic.MEMORY_EVICTED`).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from agentic_os.domain.memory import MemoryItem, MemoryScope


@runtime_checkable
class MemoryStore(Protocol):
    """Write/read/search/delete memory items by scope."""

    async def put(self, item: MemoryItem) -> MemoryItem: ...

    async def get(self, scope: MemoryScope, key: str) -> MemoryItem | None: ...

    async def get_by_id(self, item_id: str) -> MemoryItem | None: ...

    async def search(
        self, scope: MemoryScope, query: str, limit: int = 10, agent_id: str = ""
    ) -> list[MemoryItem]: ...

    async def list_scope(self, scope: MemoryScope, agent_id: str = "") -> list[MemoryItem]: ...

    async def delete(self, item_id: str) -> bool: ...


@runtime_checkable
class VectorStore(Protocol):
    """Optional semantic backend. Default impl does brute-force cosine."""

    async def upsert(self, item: MemoryItem) -> None: ...

    async def nearest(
        self, scope: MemoryScope, vector: list[float], limit: int, agent_id: str
    ) -> list[MemoryItem]: ...

    async def remove(self, item_id: str) -> None: ...


@runtime_checkable
class KnowledgeGraph(Protocol):
    """Optional entity/relation store."""

    async def add_entity(
        self, scope: MemoryScope, entity: str, props: dict | None = None
    ) -> None: ...

    async def link(self, scope: MemoryScope, a: str, relation: str, b: str) -> None: ...

    async def neighbors(self, scope: MemoryScope, entity: str) -> list[dict]: ...


@runtime_checkable
class MemoryManager(Protocol):
    """Lifecycle orchestration: scopes, retention, eviction, compaction."""

    async def write(self, item: MemoryItem) -> MemoryItem: ...

    async def read(self, scope: MemoryScope, key: str, agent_id: str = "") -> MemoryItem | None: ...

    async def recall(
        self, scope: MemoryScope, query: str, limit: int = 10, agent_id: str = ""
    ) -> list[MemoryItem]: ...

    async def forget(self, item_id: str) -> bool: ...

    async def enforce_retention(self) -> int:
        """Evict expired/excess items per policy. Returns count evicted."""
        ...
