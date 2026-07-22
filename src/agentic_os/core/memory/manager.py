"""Memory manager: lifecycle orchestration over the memory ports.

This is the concrete :class:`MemoryManager`. It composes a :class:`MemoryStore`
(primary), an optional :class:`VectorStore` (semantic search) and an optional
:class:`KnowledgeGraph`, applies the :class:`RetentionPolicy`, and publishes
``memory.written`` / ``memory.evicted`` events on the bus so dashboards and
other subsystems (e.g. the capability engine's memory capability) stay in sync.
"""

from __future__ import annotations

from agentic_os.domain.events import EventEnvelope, Topic
from agentic_os.domain.memory import MemoryItem, MemoryScope
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.event_bus import EventBus
from agentic_os.ports.memory import (
    KnowledgeGraph,
    MemoryManager,
    MemoryStore,
    VectorStore,
)

from .lifecycle import RetentionPolicy

log = get_logger("memory.manager")


class MemoryManagerImpl(MemoryManager):
    def __init__(
        self,
        bus: EventBus,
        store: MemoryStore | None = None,
        vector: VectorStore | None = None,
        graph: KnowledgeGraph | None = None,
        policy: RetentionPolicy | None = None,
    ) -> None:
        self.bus = bus
        self.store = store or _default_store()
        self.vector = vector
        self.graph = graph
        self.policy = policy or RetentionPolicy()

    async def write(self, item: MemoryItem) -> MemoryItem:
        self.policy.with_expiry(item)
        stored = await self.store.put(item)
        if self.vector is not None and stored.embedding:
            await self.vector.upsert(stored)
        await self.bus.publish(
            EventEnvelope(
                type="memory.written",
                source="memory-manager",
                topic=Topic.MEMORY_WRITTEN.value,
                payload=stored.model_dump(mode="json"),
            )
        )
        log.info("memory.written", scope=stored.scope.value, key=stored.key)
        return stored

    async def read(self, scope: MemoryScope, key: str, agent_id: str = "") -> MemoryItem | None:
        item = await self.store.get(scope, key)
        if item is None:
            return None
        if item.is_expired:
            await self._evict(item)
            return None
        if agent_id and item.agent_id and item.agent_id != agent_id:
            return None
        return item

    async def recall(
        self, scope: MemoryScope, query: str, limit: int = 10, agent_id: str = ""
    ) -> list[MemoryItem]:
        # Semantic path: if the item carries an embedding, search by similarity.
        if self.vector is not None:
            vec = _embed(query)
            if vec:
                near = await self.vector.nearest(scope, vec, limit, agent_id)
                near = [i for i in near if not i.is_expired]
                if near:
                    return near
        # Fallback / lexical path.
        hits = await self.store.search(scope, query, limit, agent_id)
        return [i for i in hits if not i.is_expired]

    async def forget(self, item_id: str) -> bool:
        item = await self.store.get_by_id(item_id)
        if item is None:
            return False
        return await self._evict(item)

    async def enforce_retention(self) -> int:
        evicted = 0
        by_scope: dict[MemoryScope, list[MemoryItem]] = {}
        for item in await self._all():
            by_scope.setdefault(item.scope, []).append(item)
        for scope, items in by_scope.items():
            policy = RetentionPolicy(
                ttl_seconds={scope: self.policy.ttl_for(scope)},
                max_size={scope: self.policy.max_size(scope)},
            )
            for victim in policy.evictable(items):
                if await self._evict(victim):
                    evicted += 1
        if evicted:
            log.info("memory.retention", evicted=evicted)
        return evicted

    async def _evict(self, item: MemoryItem) -> bool:
        ok = await self.store.delete(item.id)
        if ok:
            if self.vector is not None:
                await self.vector.remove(item.id)
            await self.bus.publish(
                EventEnvelope(
                    type="memory.evicted",
                    source="memory-manager",
                    topic=Topic.MEMORY_EVICTED.value,
                    payload={"id": item.id, "scope": item.scope.value, "key": item.key},
                )
            )
            log.info("memory.evicted", scope=item.scope.value, key=item.key)
        return ok

    async def _all(self) -> list[MemoryItem]:
        out: list[MemoryItem] = []
        for scope in MemoryScope:
            out.extend(await self.store.list_scope(scope))
        return out


def _default_store() -> MemoryStore:
    from agentic_os.adapters.memory.in_memory import InMemoryStore

    return InMemoryStore()  # type: ignore[return-value]


def _embed(text: str) -> list[float]:
    """Trivial deterministic embedding for the default (no-DB) path.

    Real semantic recall would call an embedding model; the default just hashes
    tokens into a fixed-width vector so similarity is non-trivial without an
    external dependency. This keeps the ``recall()`` semantic branch functional.
    """
    width = 32
    vec = [0.0] * width
    for tok in text.lower().split():
        h = hash(tok)
        vec[abs(h) % width] += 1.0
    if not any(vec):
        return []
    return vec
