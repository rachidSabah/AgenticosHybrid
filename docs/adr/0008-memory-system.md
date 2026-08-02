# ADR-0008: Memory System

- Status: Accepted
- Date: 2026-07-17
- Phase: 2 (Subsystem 2)

## Context

The orchestrator and agents have no durable or associative state between tasks.
We need memory that is (a) partitioned by logical scope (working / conversation
/ project / shared / long-term), (b) searchable lexically and semantically,
(c) self-grooming under bounded storage via retention policies, and (d)
observable so dashboards and other subsystems react to writes/evictions.

## Decision

1. **Four ports, swappable backends.** `ports/memory.py` defines
   `MemoryStore` (primary CRUD+search), `VectorStore` (optional semantic),
   `KnowledgeGraph` (optional relations), and `MemoryManager` (lifecycle
   facade). The default backend is fully in-memory (`adapters/memory/in_memory.py`):
   brute-force cosine over embeddings and an adjacency-list graph. Production
   can swap any of these for a vector DB / graph DB without touching the kernel.

2. **Scoped items.** `domain/memory.py` defines `MemoryScope` (5 scopes) and
   `MemoryItem` (id, scope, key, value, embedding, agent/project ids, created_at,
   optional expires_at). `MemoryItem.is_expired` is the single source of truth
   for TTL expiry.

3. **Retention policies.** `core/memory/lifecycle.py` `RetentionPolicy` stamps
   TTLs per scope on write (`with_expiry`) and computes eviction candidates
   (`evictable`) — expired items first, then oldest-first until under the
   per-scope cap. Sensible defaults: working/conversation are ephemeral;
   project/shared/long-term are durable with large caps.

4. **Manager orchestration + observability.** `core/memory/manager.py`
   `MemoryManagerImpl` composes store+vector+graph+policy. Every `write`
   publishes `MEMORY_WRITTEN`; every eviction publishes `MEMORY_EVICTED`
   (topics already declared in `domain/events.py`). `enforce_retention()`
   performs cap/TTL eviction across all scopes.

5. **Recall path.** `recall()` prefers the semantic vector path when the item
   carries an embedding (deterministic default embedder keeps it functional
   without an external model), falling back to lexical substring search.

6. **Kernel + REST.** `kernel.py` wires `MemoryManagerImpl` (with the in-memory
   vector store + graph) into the `Platform`. `api/app.py` exposes
   `/api/memory` (POST), `/api/memory/{scope}`, `/api/memory/{scope}/recall`,
   `/api/memory/{item_id}` (DELETE), `/api/memory/retention`.

## Consequences

- Memory is a first-class, pluggable subsystem. New storage tech = new adapter,
  zero kernel/port change.
- Bounded memory by construction (retention enforced on demand; a periodic
  scheduler hook can call `enforce_retention` — left to the supervision layer).
- Public interface frozen: `MemoryStore`, `VectorStore`, `KnowledgeGraph`,
  `MemoryManager` ports; `MemoryItem`, `MemoryScope` domain; manager
  `write/read/recall/forget/enforce_retention`.
- LocalBus gained a `drain()` helper so event-driven tests deterministically
  observe published events (shared with the capability test fix, ADR-0007).

## Alternatives considered

- *Single flat store keyed by string.* Rejected: no natural isolation between
  ephemeral working memory and durable long-term facts; retention would be
  global and coarse.
- *Push retention into the bus/scheduler only.* Rejected: retention is a
  memory-internal concern (per-scope policy + eviction semantics); the manager
  owns it and exposes `enforce_retention` for the scheduler to invoke.
