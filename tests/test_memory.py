"""Tests for the Memory System (Subsystem 2)."""

from __future__ import annotations

import pytest

from agentic_os.adapters.memory.in_memory import (
    InMemoryKnowledgeGraph,
    InMemoryStore,
    InMemoryVectorStore,
)
from agentic_os.core.memory.lifecycle import RetentionPolicy
from agentic_os.core.memory.manager import MemoryManagerImpl
from agentic_os.domain.memory import MemoryItem, MemoryScope


@pytest.fixture
async def bus():
    from agentic_os.adapters.bus.local import LocalBus

    b = LocalBus()
    await b.start()
    yield b
    await b.stop()


@pytest.fixture
def manager(bus):
    return MemoryManagerImpl(bus, vector=InMemoryVectorStore(), graph=InMemoryKnowledgeGraph())


async def test_write_and_read(manager):
    item = MemoryItem(scope=MemoryScope.PROJECT, key="k1", value="hello")
    stored = await manager.write(item)
    assert stored.id == item.id
    got = await manager.read(MemoryScope.PROJECT, "k1")
    assert got is not None and got.value == "hello"


async def test_recall_lexical(manager):
    await manager.write(
        MemoryItem(scope=MemoryScope.LONG_TERM, key="alpha", value="the quick brown fox")
    )
    await manager.write(
        MemoryItem(scope=MemoryScope.LONG_TERM, key="beta", value="lazy dog sleeps")
    )
    hits = await manager.recall(MemoryScope.LONG_TERM, "fox", limit=5)
    assert any(h.key == "alpha" for h in hits)


async def test_recall_semantic_with_embedding(manager):
    a = MemoryItem(
        scope=MemoryScope.LONG_TERM,
        key="a",
        value="cat",
        embedding=[1.0, 0.0, 0.0],
    )
    b = MemoryItem(
        scope=MemoryScope.LONG_TERM,
        key="b",
        value="dog",
        embedding=[0.0, 1.0, 0.0],
    )
    await manager.write(a)
    await manager.write(b)
    near = await manager.recall(MemoryScope.LONG_TERM, "cat", limit=1)
    assert near and near[0].key == "a"


async def test_forget(manager):
    item = await manager.write(MemoryItem(scope=MemoryScope.WORKING, key="x", value="v"))
    assert await manager.forget(item.id) is True
    assert await manager.read(MemoryScope.WORKING, "x") is None


async def test_ttl_expiry_via_policy(manager):
    policy = RetentionPolicy(ttl_seconds={MemoryScope.WORKING: -1.0})
    manager.policy = policy
    item = await manager.write(MemoryItem(scope=MemoryScope.WORKING, key="tmp", value="v"))
    # Negative TTL already expired at write time.
    got = await manager.read(MemoryScope.WORKING, "tmp")
    assert got is None
    # The item was evicted on read.
    assert await manager.store.get_by_id(item.id) is None


async def test_retention_evicts_over_cap():
    store = InMemoryStore()
    policy = RetentionPolicy(
        ttl_seconds={MemoryScope.WORKING: None}, max_size={MemoryScope.WORKING: 3}
    )
    mgr = MemoryManagerImpl.__new__(MemoryManagerImpl)
    mgr.bus = None  # not needed for direct store/policy usage
    mgr.store = store  # type: ignore[assignment]
    mgr.vector = None
    mgr.graph = None
    mgr.policy = policy

    from agentic_os.adapters.bus.local import LocalBus

    b = LocalBus()
    await b.start()
    mgr.bus = b
    for i in range(6):
        await mgr.write(MemoryItem(scope=MemoryScope.WORKING, key=f"k{i}", value=str(i)))
    evicted = await mgr.enforce_retention()
    await b.stop()
    # 6 written, cap 3 -> 3 evicted.
    assert evicted == 3
    assert len(await store.list_scope(MemoryScope.WORKING)) == 3


async def test_written_event_published(bus):
    seen = []
    await bus.subscribe("memory.written", lambda e: seen.append(e))
    mgr = MemoryManagerImpl(bus, vector=InMemoryVectorStore())
    await mgr.write(MemoryItem(scope=MemoryScope.SHARED, key="s", value="v"))
    from agentic_os.domain.events import Topic

    await bus.drain()
    assert Topic.MEMORY_WRITTEN.value in [e.topic for e in seen]


async def test_knowledge_graph_links():
    g = InMemoryKnowledgeGraph()
    await g.add_entity(MemoryScope.PROJECT, "agent")
    await g.link(MemoryScope.PROJECT, "agent", "uses", "memory")
    nbrs = await g.neighbors(MemoryScope.PROJECT, "agent")
    assert any(n["target"] == "memory" for n in nbrs)
