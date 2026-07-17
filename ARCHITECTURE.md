# Architecture

AgenticOS is a **local-first, event-bus-driven AI Agent Operating System**
built on a strict **hexagonal (clean) architecture**. Business logic depends on
*interfaces* (ports); concrete infrastructure lives behind those ports as
adapters. The composition root (`kernel.py`) is the only place that knows about
concrete classes.

## Layers

```
User / UI / CLI
      │  ports (interfaces)
      ▼
┌────────────────────────────────────────────────────────────┐
│  API (FastAPI) — REST + WebSocket live dashboard            │
└───────────────┬────────────────────────────────────────────┘
                │
   ┌────────────┼─────────────────────────────────────────┐
   │  CORE       │  orchestrator, registry, scheduler,      │
   │            │  health, recovery, providers/, capability/│
   │            │  memory/, security/                       │
   ├────────────┼─────────────────────────────────────────┤
   │  DOMAIN    │  Agent, Task, ProviderConfig, ModelInfo,  │
   │            │  AgentSpec, MemoryItem, Security entities  │
   ├────────────┼─────────────────────────────────────────┤
   │  PORTS     │  EventBus, ProviderAdapter, Plugin, and   │
   │            │  the four Phase-2 subsystem ports          │
   ├────────────┼─────────────────────────────────────────┤
   │  ADAPTERS  │  bus (local/redis/nats), providers,        │
   │            │  capability, memory, security              │
   └────────────┴─────────────────────────────────────────┘
```

| Layer | Path | Responsibility |
|-------|------|----------------|
| `domain/` | entities + value objects (Pydantic v2) | state, no behavior beyond validation |
| `ports/` | interfaces (`Protocol`) | contracts; no implementation |
| `core/` | orchestration + subsystem logic | depends only on ports |
| `adapters/` | concrete infrastructure | bus, providers, capability, memory, security |
| `api/` | FastAPI app | REST + WebSocket (an adapter over the core ports) |
| `kernel.py` | composition root | wires ports → concrete impls → `Platform` |

## Event Bus (frozen abstraction)

One `EventBus` port, three interchangeable adapters selected by `BUS_TYPE`:

| Adapter | Use | Default in |
|---------|-----|-----------|
| `LocalBus` | in-process asyncio | dev / CI |
| `RedisStreamsBus` | Redis Streams (persistent, replayable) | **production** |
| `NatsJetStreamBus` | NATS JetStream (alt prod) | prod (opt-in) |

Every bus message is wrapped in an `EventEnvelope` (id, type, source,
timestamp, topic, payload). Topics are centralized in `domain/events.py`.

## Phase 2 Subsystems (frozen interfaces)

| Subsystem | Ports | Default impl |
|-----------|-------|-------------|
| Provider Management | `ProviderManager`, `ModelManager`, `SecretStore`, `ApiKeyVault`, `ProviderHealthMonitor`, `RoutingPolicy`, `CostTracker`, `RateLimitMonitor`, `FailoverPolicy` | encrypted Fernet vault, OpenAI-compatible adapter |
| Memory System | `MemoryStore`, `VectorStore`, `KnowledgeGraph`, `MemoryManager` | in-memory store + cosine vector + adjacency graph |
| Capability Engine | `Capability`, `CapabilityRegistry`, `AgentComposer` | 11 built-ins + intent composer |
| Security Framework | `SecretsManager`, `AccessControl`, `WorkspaceIsolation`, `ToolPermissions`, `ApprovalGate`, `AuditLog` | RBAC + workspace isolation + approval gate + audit |

See `docs/adr/0001`–`0009` for the design rationale behind each.

## Control Flow

### Task execution (Phase 1)
`Planner → Task Dispatcher → Provider Adapter → Event Bus → Supervisor ↔
Health Monitor → Recovery Manager → WebSocket Dashboard`.

### Agent composition (Phase 2)
`Task → CapabilityEngine.spec_for_task(intent) → AgentSpec` (capabilities +
provider/model). Sensitive capabilities are gated by the Security Framework's
`authorize()` pipeline (RBAC → approval gate → audit) before execution.

### Memory lifecycle
`write() → retention (TTL/max-size) → MEMORY_WRITTEN` and eviction →
`MEMORY_EVICTED`, both observable on the bus.

## Configuration

All knobs are environment-driven via `pydantic-settings` (`config.py`). Sensible
defaults boot the system on the in-process bus with the mock provider — zero
infrastructure. See `.env.example`.

## Technology Stack

Python 3.13+, FastAPI, asyncio/AnyIO, Pydantic v2, pydantic-settings,
structlog, Prometheus client, httpx, `cryptography` (Fernet), uv, Docker/WSL2.

## Diagrams

C4 diagrams (mermaid) live in [`docs/c4/diagrams.md`](docs/c4/diagrams.md).
