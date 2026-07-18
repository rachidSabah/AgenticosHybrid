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

## Phase 3B Subsystems (v0.4.0)

| Subsystem | Ports | Core Impl | Status |
|-----------|-------|-----------|--------|
| Workflow Engine | `WorkflowEnginePort` | `WorkflowEngineImpl` — DAG execution, topological sort, versioning, replay, approval gates | ✅ Verified |
| Pipeline Engine | `PipelineEnginePort` | `PipelineEngineImpl` — stage execution, scheduling, retry, rollback, parallel stages | ✅ Verified |
| Observability Framework | `TracingPort`, `MetricsPort`, `LoggingPort` | `InMemoryTracing`, `InMemoryMetrics`, `InMemoryStructuredLogging` (Prometheus/OTel bridges available) | ✅ Verified |
| MCP Framework | `MCPRegistryPort` | domain models + ports (server config, tools) | ✅ Domain/Ports |
| Plugin Framework | `PluginRegistryPort` | `PluginSDK`, `PluginValidator`, `PluginRegistryClient`, `generate_plugin_template` | ✅ Domain/Ports/SDK |

All core engines achieve >90% test coverage with comprehensive unit, integration, and stress tests.

## Phase 4 Subsystem (v0.5.0, M1)

| Subsystem | Ports | Core Impl | Status |
|-----------|-------|-----------|--------|
| Universal Execution Engine Framework | `ExecutionEnginePort`, `RuntimeManagerPort`, `DiscoveryProvider` | `RuntimeManager` + `RuntimeRegistryImpl` + `CapabilityNegotiator` + `DiscoveryEngine` + `CompositeEngine` | ✅ Verified |

The Universal Execution Engine Framework is a hexagonal abstraction layer where
ANY execution engine (MCP, Docker, WSL, Claude Code, subprocess, cloud API)
implements a single `ExecutionEnginePort` interface (~22 methods). The kernel
discovers, binds, orchestrates, supervises, and optimizes engines through this
shared contract. Adding a new engine = one new adapter file = zero kernel changes.

**Key components:**
- **`ExecutionEnginePort`** (ports) — universal interface: lifecycle, execution,
  health, benchmark, telemetry, compatibility, workspace, recovery.
- **`RuntimeManager`** (core) — high-level subsystem wiring registry + discovery +
  negotiator + adapters. Single integration point in the kernel.
- **`RuntimeRegistryImpl`** (core) — in-memory engine CRUD, capability search,
  health caching, session tracking, EventBus emissions.
- **`CapabilityNegotiator`** (core) — scored matching (required 10x weighting,
  confidence-based filtering, TTL cache).
- **`DiscoveryEngine`** (core) — multi-provider orchestration with deduplication
  and confidence scoring.
- **`CompositeEngine`** (core) — combines multiple engines behind one port for
  fallback, load balancing, and fan-out routing.
- **`GenericExecutionEngine`** (adapter) — reference adapter demonstrating the
  port contract with echo/ping/sleep/info/fail actions.
- **`PathDiscovery`** (adapter) — scans system PATH for known AI executables.

**Phase 4 event topics:** 14 new `engine.*` topics on the EventBus.

## Phase 2 Subsystems (frozen interfaces)

| Subsystem | Ports | Default impl |
|-----------|-------|-------------|
| Provider Management | `ProviderManager`, `ModelManager`, `SecretStore`, `ApiKeyVault`, `ProviderHealthMonitor`, `RoutingPolicy`, `CostTracker`, `RateLimitMonitor`, `FailoverPolicy` | encrypted Fernet vault, OpenAI-compatible adapter |
| Memory System | `MemoryStore`, `VectorStore`, `KnowledgeGraph`, `MemoryManager` | in-memory store + cosine vector + adjacency graph |
| Capability Engine | `Capability`, `CapabilityRegistry`, `AgentComposer` | 11 built-ins + intent composer |
| Security Framework | `SecretsManager`, `AccessControl`, `WorkspaceIsolation`, `ToolPermissions`, `ApprovalGate`, `AuditLog` | RBAC + workspace isolation + approval gate + audit |

See `docs/adr/0001`–`0009` for the design rationale behind each.

## Phase 3B Engine Control Flow

### Workflow Execution
`WorkflowCreate → WorkflowEngineImpl.create_workflow() → ACTIVATE → execute_workflow() → topological_sort() → [execute_node() for each ready node] → EventBus emissions (workflow.*)`

### Pipeline Execution
`PipelineCreate → PipelineEngineImpl.create_pipeline() → ACTIVATE → execute_pipeline() → [execute_stage() for each ready stage, respecting depends_on] → retry policy evaluation → EventBus emissions (pipeline.*)`

### Observability (cross-cutting)
All engines emit structured events through the EventBus. The `InMemoryTracing`, `InMemoryMetrics`, and `InMemoryStructuredLogging` implementations are wired via the observability ports for development and testing; production deployments can substitute OpenTelemetry and Prometheus adapters.

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
