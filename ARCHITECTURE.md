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
| MCP Framework | `MCPRegistryPort` | domain models + ports + full runtime (registry, client, manager, security, SDK) | ✅ Verified |
| Plugin Framework | `PluginRegistryPort` | `PluginSDK`, `PluginValidator`, `PluginRegistryClient`, `generate_plugin_template` | ✅ Domain/Ports/SDK |

All core engines achieve >90% test coverage with comprehensive unit, integration, and stress tests.

## Phase 4, Milestone 3: MCP Runtime Foundation (v0.7.0)

The MCP Runtime Foundation completes the MCP Framework from Phase 3B into a
production-ready runtime with registry, client, manager, security, and SDK layers.

### Architecture Layers

```
┌─────────────────────────────────────────────┐
│              MCP SDK                         │
│  McpServerSdk · ToolSdk · ResourceSdk ·    │
│  PromptSdk · Auth · Testing · Validation     │
├─────────────────────────────────────────────┤
│              MCP Core Runtime                │
│  MCPRegistryImpl · MCPClient · MCPManager   │
│  MCPSecurity · EventBus integration          │
├─────────────────────────────────────────────┤
│              MCP Ports                       │
│  MCPRegistryPort · MCPTransportPort          │
├─────────────────────────────────────────────┤
│              MCP Domain                      │
│  MCPServerDetail · MCPTool · MCPResource    │
│  MCSServerConfig · MCPServerCreate/Update    │
│  MCPPermissionMapping · MCPSession           │
└─────────────────────────────────────────────┘
```

### Components

| Component | Path | Responsibility |
|-----------|------|----------------|
| Domain Models | `domain/mcp.py` | Frozen dataclasses for server, tool, resource, prompt, session, permission entities |
| Port Interfaces | `ports/mcp.py` | MCPRegistryPort, MCPTransportPort runtime-checkable protocols |
| Registry | `core/mcp/registry.py` | In-memory async server CRUD, lifecycle, tool/resource/prompt management, EventBus integration |
| Client | `core/mcp/client.py` | stdio/subprocess, SSE, Streamable HTTP transport client with auto-reconnect |
| Manager | `core/mcp/manager.py` | Lifecycle orchestration, health monitoring, session tracking |
| Security | `core/mcp/security.py` | 20 authorization methods wrapping SecurityFramework |
| SDK Server | `sdk/mcp/server.py` | McpServerSdk — fluent server lifecycle |
| SDK Tool | `sdk/mcp/tool.py` | ToolBuilder, ToolSdk — tool construction and invocation |
| SDK Resource | `sdk/mcp/resource.py` | ResourceSdk — resource reading and subscription |
| SDK Prompt | `sdk/mcp/prompt.py` | PromptSdk — prompt listing and retrieval |
| SDK Auth | `sdk/mcp/auth.py` | McpAuthHelper — MCP authorization helpers |
| SDK Config | `sdk/mcp/config.py` | McpConfigHelper — server configuration building |
| SDK Registration | `sdk/mcp/registration.py` | RegistrationHelper — server registration/unregistration |
| SDK Validation | `sdk/mcp/validation.py` | McpValidator — MCP protocol validation |
| SDK Testing | `sdk/mcp/testing.py` | McpTestHelper, FakeMCPRegistry, FakeMCPManager |

### Key Design Decisions

- **Immutable domain models** — All dataclasses are frozen; state transitions use
  `with_*` builder methods returning new instances.
- **Registry as event source** — Every lifecycle transition emits an EventBus event.
- **Lazy transport binding** — MCPClient doesn't connect until `connect()` is called.
- **Per-server async locks** — Thread-safe lifecycle transitions via `asyncio.Lock`.
- **Security as a gate** — MCPSecurity wraps every MCP operation with authorization.

### Performance

All MCP operations are sub-millisecond:
- Domain model instantiation: <4 µs
- State transition (`with_status`): <1 µs
- Registry register/get/unregister: <57 µs
- Serialization to dict/JSON: <7 µs

See ADRs `0011`–`0015` for detailed design rationale.

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

See `docs/adr/0001`–`0015` for the full set of Architecture Decision Records.

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
