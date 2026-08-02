# PHASE E — SYSTEM TRANSFORMATION BLUEPRINT
## AgenticOS v2.0 — Master Architecture & Evolution Plan

> **Status**: Architecture & Design Phase
> **Predecessor**: ARCHITECTURE_AUDIT.md (v1.0.0-rc1 Analysis)
> **Next Phase**: Implementation (Phased over 12-18 months)
> **Rule**: No code implementation. No refactoring. No feature removal. This document is the canonical engineering specification.

---

## Table of Contents

1. [System Architecture Overview](#1-system-architecture-overview)
2. [Kernel Design](#2-kernel-design)
3. [Runtime Discovery](#3-runtime-discovery)
4. [OmniRoute as Native Subsystem](#4-omniroute-as-native-subsystem)
5. [Mission Orchestrator](#5-mission-orchestrator)
6. [Prompt Center](#6-prompt-center)
7. [AI Brain](#7-ai-brain)
8. [Agent Constellation](#8-agent-constellation)
9. [Desktop Diagnostics](#9-desktop-diagnostics)
10. [Desktop Runtime](#10-desktop-runtime)
11. [EventBus](#11-eventbus)
12. [API Gateway](#12-api-gateway)
13. [Plugin Marketplace](#13-plugin-marketplace)
14. [Persistence Architecture](#14-persistence-architecture)
15. [Self-Healing](#15-self-healing)
16. [Security Architecture](#16-security-architecture)
17. [Installer Architecture](#17-installer-architecture)
18. [Deployment Architecture](#18-deployment-architecture)
19. [Complete Subsystem Dependency Graph](#19-complete-subsystem-dependency-graph)
20. [Migration Matrix](#20-migration-matrix)
21. [Implementation Roadmap](#21-implementation-roadmap)
22. [Architecture Decision Records](#22-architecture-decision-records)
23. [Non-Regression Requirements](#23-non-regression-requirements)

---

## 1. System Architecture Overview

### 1.1 v1.0 vs v2.0 Architecture Comparison

| Aspect | v1.0.0-rc1 | v2.0 Target |
|--------|-----------|-------------|
| Kernel | Monolithic __init__ with 30+ hardcoded constructors | Typed DI container with lifecycle hooks |
| Desktop | 27 concrete subsystems, zero ports, god object | 27 port protocols, Rust native layer, IPC bridge |
| Routing | ProviderRouter + Manager + ModelManager + CostTracker | OmniRoute as single unified routing engine |
| Discovery | Two engines (Runtime + Discovery) with partial overlap | Unified Discovery Framework, single source of truth |
| AI Brain | 17 subsystems, all in-memory stubs | Real EventBus consumer, persistent telemetry, real optimization |
| Orchestration | 20 subsystems wired manually in framework.py | Plugin-based decomposition, OmniRoute-integrated routing |
| Persistence | In-memory dicts everywhere | Port-based persistence: SQLite/PostgreSQL/Redis/Vector DB |
| Self-Healing | Dead imports, unbounded lists, no persistence | Port-based healing, circuit breakers, persistent issue log |
| Plugins | Local filesystem only, SHA-256 stub | Registry + marketplace + signing + auto-update + SDK |
| API Gateway | Single app.py with 396 endpoints, no auth | Layered gateway with auth, rate limiting, protocol adapters |
| EventBus | 260 topics, no filtering, no telemetry | Persistent event store, subscription filtering, telemetry |
| Desktop Runtime | Pure Python, in-memory stubs | Rust/Tauri native layer, IPC bridge, real process mgmt |
| Installer | None (run from source) | MSI / NSIS / AppImage / Deb / RPM / DMG |
| Deployment | None (manual start) | GitHub Actions CI/CD, signing, telemetry, crash reporting |

### 1.2 Architecture Layers

| Layer | Technology | Responsibility |
|-------|-----------|----------------|
| Presentation | Next.js 15 / Tauri v2 / CLI | User interfaces, dashboard, desktop shell |
| API Gateway | FastAPI / WebSocket / SSE | Protocol adaptation, auth, rate limiting |
| Auth & Security | JWT / OAuth2 / Fernet | Authentication, authorization, encryption, auditing |
| OmniBus & Events | Redis Streams / NATS / EventBus | Inter-service communication, event sourcing, replay |
| OmniRoute Routing | Pure Python / async | Provider selection, routing policies, cost optimization, telemetry |
| Execution | Adapters / MCP / Plugins / Swarm | AI provider execution, MCP protocol, plugin sandbox, swarm coordination |
| Core Domain | Pure Python / Ports / Adapters | Mission orchestration, orchestration framework, prompt management, learning, workflows, pipelines, memory |
| Discovery | Pluggable providers / Validation | Runtime discovery, provider discovery, model discovery, MCP discovery, hot reload |
| Persistence | SQLite / PostgreSQL / Redis / Vector DB | State persistence, caching, queues, vector search |
| Desktop Runtime | Rust / Tauri v2 | Native process management, IPC bridge, auto-updater, crash reporter, GPU rendering |

### 1.3 Architecture Principles (v2.0)

1. **Every subsystem behind a Port Protocol** - No concrete class accessed without a port interface
2. **OmniRoute is the single routing authority** - No other component makes provider routing decisions
3. **Runtime Discovery is the single source of truth** - All discovered entities flow through Discovery first
4. **EventBus is the nervous system** - All state changes publish events; subscribers never poll
5. **Persistence is mandatory** - No subsystem stores critical state in-memory only
6. **Immutable domain models** - All domain entities are frozen dataclasses with with_*() helpers
7. **Background-first startup** - System starts in <3 seconds; background tasks load remaining subsystems
8. **Total backward compatibility** - Every v1.0 endpoint, workflow, and UI continues working

---

## 2. Kernel Design

### 2.1 v2.0 Kernel Architecture

```
+------------------------------------------------------------------+
|                    Kernel v2 (Typed DI Container)                  |
|                                                                    |
|  +------------------+  +---------------------------------------+  |
|  |  Settings        |  |  Container                             |  |
|  |  (pydantic-settings)| |  _registry: dict[type, Factory[T]]    |  |
|  |                   |  |  _singletons: dict[type, T]           |  |
|  |                   |  |  _lifecycle: dict[type, LifecycleHook]|  |
|  |                   |  |  +register[T](factory, singleton)     |  |
|  |                   |  |  +resolve[T]() -> T                   |  |
|  |                   |  |  +start_all() / stop_all()            |  |
|  +------------------+  +---------------------------------------+  |
|                                                                    |
|  +--------------------------------------------------------------+ |
|  |  Lifecycle Phases                                              | |
|  |  Phase 0: CRITICAL (EventBus, Vault, Logging)                | |
|  |  Phase 1: INFRASTRUCTURE (Persistence, Discovery, Security)  | |
|  |  Phase 2: CORE (Orchestrator, Scheduler, Health)            | |
|  |  Phase 3: DOMAIN (Mission, Workflow, Pipeline, Memory)      | |
|  |  Phase 4: OMNIROUTE (Router, Registry, Gateway, Budget)     | |
|  |  Phase 5: ADVANCED (Orchestration, MCP, Learning, Desktop)  | |
|  +--------------------------------------------------------------+ |
|                                                                    |
|  +--------------------------------------------------------------+ |
|  |  Platform Dataclass                                            | |
|  |  Single typed container for all subsystems                    | |
|  |  Generated automatically from Container registry             | |
|  +--------------------------------------------------------------+ |
+------------------------------------------------------------------+
```

### 2.2 Kernel Responsibilities

| Responsibility | Implementation |
|----------------|---------------|
| Dependency Injection | Typed `Container` with `register[T]` + `resolve[T]` |
| Lifecycle Management | Phase-based startup with `LifecycleHook` (before_start, after_start, before_stop, after_stop) |
| Configuration | pydantic-settings with layered overrides (env > file > defaults) |
| Health Aggregation | `GET /healthz` aggregates all subsystem health |
| Shutdown Coordination | Ordered reverse-phase shutdown with timeout per subsystem |
| Background Workers | Typed worker registry with auto-restart on failure |
| Task Scheduling | Internal scheduler for periodic tasks (heartbeat, sync, cleanup) |
| Startup Telemetry | Per-subsystem startup timing logged to EventBus |
| Graceful Degradation | Failed subsystem = degraded mode + 503 for dependent endpoints |

### 2.3 Container API (Protocol)

```python
class Container:
    """Typed dependency injection container with lifecycle management."""

    def register[T](
        self,
        interface: type[T],
        factory: Callable[[], T],
        *,
        singleton: bool = True,
        lifecycle: LifecycleHook[T] | None = None,
        phase: Phase = Phase.CORE,
    ) -> None: ...

    def resolve[T](self, interface: type[T]) -> T: ...

    def try_resolve[T](self, interface: type[T]) -> T | None: ...

    def resolve_all[T](self, interface: type[T]) -> list[T]: ...

    async def start_phase(self, phase: Phase) -> PhaseResult: ...

    async def stop(self, timeout: float = 30.0) -> None: ...

    def health(self) -> dict[str, HealthStatus]: ...


class LifecycleHook[T]:
    before_start: Callable[[T], Awaitable[None]] | None
    after_start: Callable[[T], Awaitable[None]] | None
    before_stop: Callable[[T], Awaitable[None]] | None
    after_stop: Callable[[T], Awaitable[None]] | None


class Phase(StrEnum):
    CRITICAL = "critical"         # EventBus, Vault, Logging
    INFRASTRUCTURE = "infra"      # Persistence, Discovery, Security
    CORE = "core"                 # Orchestrator, Scheduler, Health
    DOMAIN = "domain"             # Mission, Workflow, Pipeline, Memory
    OMNIROUTE = "omniroute"       # Router, Registry, Gateway
    ADVANCED = "advanced"         # Orchestration, MCP, Learning, Desktop
```

### 2.4 Startup Sequence (v2.0)

```
run_serve(host, port)
  |
  +-- Kernel() [~50ms]
  |     +-- Container() - empty registry
  |     +-- Load Settings
  |     +-- Register ALL factories (no construction yet)
  |     +-- Build Platform dataclass (lazy resolution)
  |
  +-- _build_app(kernel) -> FastAPI
  |     +-- Mount all routers (some return 503 until phase loads)
  |     +-- Register CORS, middleware, exception handlers
  |
  +-- kernel.start()
        |
        +-- Phase 0: CRITICAL [~50ms]
        |     +-- Logging startup
        |     +-- EventBus (sync start - blocks until ready)
        |     +-- Vault (decrypt master key)
        |
        +-- Phase 1: INFRASTRUCTURE [~200ms]
        |     +-- Persistence (SQLite connect / PostgreSQL pool)
        |     +-- Discovery Framework (load profiles, warm cache)
        |     +-- Security Framework (load RBAC policies)
        |     +-- Secrets Store (load API keys into Vault)
        |
        +-- Phase 2: CORE [~200ms]
        |     +-- Scheduler (start periodic tasks)
        |     +-- Health Monitor (start heartbeat polling)
        |     +-- Recovery Manager (subscribe to failure events)
        |     +-- Capability Engine (load capability catalog)
        |
        +-- Phase 3: DOMAIN [~300ms]
        |     +-- Memory Manager (load stores, warm vectors)
        |     +-- Mission Planner (load mission templates)
        |     +-- Workflow Engine (load workflow definitions)
        |     +-- Pipeline Engine (load pipeline definitions)
        |     +-- Self-Healing Engine (subscribe to events)
        |
        +-- Phase 4: OMNIROUTE [~500ms]
        |     +-- Provider Registry (load configured providers)
        |     +-- Model Registry (discover models from providers)
        |     +-- Router Engine (build routing tables)
        |     +-- Budget Engine (load cost tables)
        |     +-- Gateway Adapters (connect OpenAI/Anthropic APIs)
        |     +-- Failover Engine (configure failover policies)
        |
        +-- Phase 5: ADVANCED [asyncio.create_task - background]
              +-- Runtime Discovery (scan PATH, registries, etc.)
              +-- Orchestration Framework (build swarm schemas)
              +-- MCP Registry (connect registered MCP servers)
              +-- Learning Engine (start telemetry consumer)
              +-- Desktop Runtime (start if Tauri)
              +-- Plugin Engine (load installed plugins)
              +-- AI Brain (start background learning loop)
              +-- Dashboard (subscribe to 96+ dashboard topics)
              |
              +-- TOTAL STARTUP: <1s critical path, ~1.5s full warm
```

### 2.5 Shutdown Sequence (v2.0)

```
kernel.stop(timeout=30.0)
  |
  +-- Phase 5: ADVANCED [timeout: 10s]
  |     +-- Unsubscribe all EventBus handlers
  |     +-- Stop Desktop Runtime
  |     +-- Disconnect MCP servers
  |     +-- Save Learning checkpoints
  |     +-- Stop Plugin Engine
  |     +-- Persist Runtime cache
  |
  +-- Phase 4: OMNIROUTE [timeout: 5s]
  |     +-- Drain in-flight requests
  |     +-- Flush telemetry buffer
  |     +-- Save cost/budget state
  |     +-- Disconnect gateway adapters
  |
  +-- Phase 3: DOMAIN [timeout: 5s]
  |     +-- Save pending missions
  |     +-- Persist workflow state
  |     +-- Flush memory buffers
  |     +-- Persist self-healing issue log
  |
  +-- Phase 2: CORE [timeout: 3s]
  |     +-- Stop scheduler
  |     +-- Recover active tasks
  |     +-- Stop health monitor
  |
  +-- Phase 1: INFRASTRUCTURE [timeout: 3s]
  |     +-- Close database connections
  |     +-- Persist discovery cache
  |     +-- Flush audit log
  |
  +-- Phase 0: CRITICAL [timeout: 2s]
        +-- Flush EventBus (XADD remaining messages)
        +-- Stop EventBus
        +-- Close vault
```

### 2.6 Dependency Injection Pattern (v2.0)

```python
# Instead of manual __init__ in kernel.py:
# Each subsystem module declares its dependencies and factory:

# core/omniroute/__init__.py
def register_routing(container: Container) -> None:
    container.register(
        ProviderRegistryPort,
        lambda: OmniRouteProviderRegistry(
            config=container.resolve(Settings),
            vault=container.resolve(SecretStore),
        ),
        singleton=True,
        lifecycle=LifecycleHook(
            before_start=lambda r: r.load_providers(),
            after_stop=lambda r: r.persist_state(),
        ),
        phase=Phase.OMNIROUTE,
    )

# kernel.py would just call:
# register_routing(container)
# register_mcp(container)
# register_discovery(container)
# ...
# container.start()  # everything auto-wired and started by phase
```

### 2.7 Key Design Changes from v1.0

| v1.0 Problem | v2.0 Solution |
|-------------|---------------|
| Manual constructor ordering creates fragile coupling | Container handles dependency graph automatically |
| Subsystems must start in sync __init__ | Phased startup with background task support |
| No lifecycle hooks - can't react to start/stop | LifecycleHook per subsystem with before/after hooks |
| 30+ subsystems all constructed even if disabled | Lazy resolution + conditional registration |
| Platform dataclass has 19+9 optional fields | Auto-generated from container registry |
| No health per subsystem | Container.health() aggregates all registered health checks |
| Shutdown order must be manually reversed | Phase-based reverse-order stop with per-phase timeout |
| Background workers have no restart policy | Worker registry with auto-restart on failure |

---

## 3. Runtime Discovery

### 3.1 v2.0 Discovery Architecture

Runtime Discovery becomes the single source of truth for all discovered entities.

```
+------------------------------------------------------------------+
|                    RUNTIME DISCOVERY v2.0                          |
|                                                                    |
|  INPUTS                    PROCESSING                     OUTPUTS |
|  +------------------+    +------------------+    +--------------+ |
|  | PATH Discovery   | -> | Validation       | -> | Registry     | |
|  | Registry         |    | Pipeline         |    | (Persistent) | |
|  | WSL              |   +------------------+    |              | |
|  | Docker           | -> | Deduplication    | -> | EventBus     | |
|  | Package Mgrs    |    | Engine           |    | Publisher    | |
|  | (choco, winget,  |   +------------------+    |              | |
|  |  scoop, npm,     | -> | Profiling        | -> | Cache        | |
|  |  cargo, uv)      |    | Engine           |    | (TTL, LRU)   | |
|  | VS Code          |   +------------------+    |              | |
|  | JetBrains        | -> | Capability       | -> | Hot Reload   | |
|  | Known Dirs       |    | Mapper           |    | (File Watch) | |
|  | Config Files     |   +------------------+    |              | |
|  | Environment      | -> | Health Check     | -> | WebSocket    | |
|  +------------------+    | Engine           |    | Push         | |
|                            +------------------+    +--------------+ |
+------------------------------------------------------------------+
```

### 3.2 Expanded Discovery Coverage

| Domain | Discoverers | Published As |
|--------|-------------|-------------|
| Runtimes | PATH, Registry, known-dirs, WSL, Docker | ExecutionEngine descriptors |
| Providers | Config, environment, MCP, plugin manifests | ProviderInfo with capabilities |
| Models | Provider API responses, MCP server capabilities | ModelInfo with cost/context/features |
| Capabilities | Engine manifests, provider model metadata, MCP | CapabilityDescriptor with scoring |
| MCP Servers | Config, discovery providers, known install dirs | MCPServerDetail with transport info |
| CLI Tools | PATH, choco, winget, scoop, npm, cargo, uv | ToolDescriptor |
| Plugins | Plugin directories, marketplace, config | PluginManifest |
| Desktop Apps | Install dirs, registry, package managers | AppDescriptor |

### 3.3 Key Design Changes from v1.0

| v1.0 Problem | v2.0 Solution |
|-------------|---------------|
| Two separate engines (Runtime + Discovery) overlap | Single unified DiscoveryFramework |
| No persistence - cache lost on restart | SQLite-backed persistent cache |
| No model discovery | Model discovery via provider API / MCP |
| No MCP discovery | MCP server discovery via multiple methods |
| No WebSocket push for real-time updates | WebSocket push on every scan/change |
| Cache is in-memory TTL only | LRU + TTL + persistence |

---

## 4. OmniRoute as Native Subsystem

### 4.1 Architecture - Single Routing Authority

OmniRoute sits between the API Gateway and Execution layers. No other component may make provider routing decisions. All provider selection, failover, cost tracking, and telemetry flows through OmniRoute.

```
API Gateway        Domain Services             Execution
  /v1/chat          Mission Orchestrator        Claude Code Adapter
  /api/*            Workflow Engine             GPT-4o Adapter
  /ws/*             Pipeline Engine             Ollama Adapter
       |              Prompt Center                 |
       v              Swarm Engine                  v
  +--------------------------------------------------------+
  |                     OMNIROUTE                           |
  |                                                         |
  |  +------------------+  +-----------------------------+  |
  |  | ProviderRegistry |  | RouterEngine                |  |
  |  | - config         |  | - latency routing           |  |
  |  | - credentials    |  | - cost routing              |  |
  |  | - health cache   |  | - round robin routing       |  |
  |  | - model catalog  |  | - hybrid routing            |  |
  |  +------------------+  | - priority routing          |  |
  |                        +-----------------------------+  |
  |  +------------------+  +-----------------------------+  |
  |  | ModelRegistry    |  | BudgetEngine                |  |
  |  | - model metadata |  | - cost tracking             |  |
  |  | - capability map |  | - budget enforcement        |  |
  |  | - pricing table  |  | - spend alerts              |  |
  |  +------------------+  | - cost projections          |  |
  |                        +-----------------------------+  |
  |  +------------------+  +-----------------------------+  |
  |  | FailoverEngine   |  | GatewayAdapter              |  |
  |  | - circuit breaker|  | - OpenAI compat             |  |
  |  | - retry backoff  |  | - Anthropic compat          |  |
  |  | - fallback chain |  | - custom providers          |  |
  |  +------------------+  +-----------------------------+  |
  |                                                         |
  |  +------------------+  +-----------------------------+  |
  |  | ReasoningRouter  |  | ToolRouter / VisionRouter   |  |
  |  | + effort mapping |  | + tool capability routing   |  |
  |  +------------------+  +-----------------------------+  |
  +--------------------------------------------------------+
```

### 4.2 Routing Flow

```
1. RouteRequest received (from API, Orchestrator, Mission, Prompt, etc.)
2. Capability-based filtering:
   a) Filter by capability (ModelRegistry.find(query))
   b) Filter by health / circuit breaker state
   c) Filter by rate limit remaining
   d) Apply budget constraint (max_cost, max_latency)
3. Score candidates by policy:
   - Default: HybridRoutingPolicy (latency + cost)
   - Reasoning: ReasoningRouter
   - Vision: VisionRouter
   - Tools: ToolRouter
4. Select highest-scored provider+model
5. Execute via GatewayAdapter with streaming/compression
6. Record telemetry (latency, tokens, cost, model, provider)
7. On failure: CircuitBreaker -> Retry -> Failover -> Fallback
```

### 4.3 OmniRoute Module Location

```
src/agentic_os/core/omniroute/
  __init__.py           # register_omniroute(container)
  registry.py           # OmniRouteProviderRegistry
  router.py             # OmniRouteRouterEngine
  models.py             # ModelRegistry
  budget.py             # BudgetEngine
  failover.py           # FailoverEngine + CircuitBreaker
  compression.py        # CompressionEngine
  telemetry.py          # OmniRouteTelemetry
  gateway.py            # GatewayAdapter base
  gateways/
    openai.py           # OpenAI-compatible gateway adapter
    anthropic.py        # Anthropic-compatible gateway adapter
    custom.py           # Custom provider gateway adapter
  policies/
    __init__.py
    latency.py          # LatencyRoutingPolicy
    cost.py             # CostRoutingPolicy
    round_robin.py      # RoundRobinRoutingPolicy
    hybrid.py           # HybridRoutingPolicy
  routers/
    reasoning.py        # ReasoningRouter
    vision.py           # VisionRouter
    tool.py             # ToolRouter
    ocr.py              # OCRRouter
  config.py             # OmniRouteConfiguration
```

### 4.4 Key Design Changes from v1.0

| v1.0 Problem | v2.0 Solution |
|-------------|---------------|
| ProviderRouter + Manager + ModelManager + CostTracker are separate | All unified under OmniRoute as single routing authority |
| 10 OmniRoute endpoints return hardcoded stub data | Real endpoints backed by OmniRoute state |
| No circuit breaker | FailoverEngine with configurable circuit breaker |
| No specialized routers for reasoning/vision/tools/OCR | Dedicated routers per feature |
| No gateway adapters | GatewayAdapter base + real implementations |
| Routing policies simple (latency/cost/round_robin) | Hybrid, Priority policies added |
| No model registry | ModelRegistry with metadata, capabilities, pricing |
| No budget engine | BudgetEngine with spend tracking, alerts, projections |

---

## 5. Mission Orchestrator

### 5.1 v2.0 Architecture

Mission Orchestrator evolves to use plugin-based decomposition, delegates routing to OmniRoute, and persists all state.

```
+------------------------------------------------------------------+
|                    MISSION ORCHESTRATOR v2.0                       |
|                                                                    |
|  +------------------+  +------------------+  +------------------+  |
|  | MissionPlanner   |  | TaskDecomposer   |  | ResourceAllocator|  |
|  | - goal analysis  |  | - plugin-based   |  | - agent matching |  |
|  | - complexity est |  | - strategy chain |  | - provider pick  |  |
|  | - risk analysis  |  | - DAG generation |  | -> OmniRoute     |  |
|  +------------------+  +------------------+  +------------------+  |
|                                                                    |
|  +------------------+  +------------------+  +------------------+  |
|  | ExecutionEngine  |  | RecoveryManager  |  | MissionStore     |  |
|  | - task dispatch  |  | - checkpoint     |  | (Persistent)     |  |
|  | - parallel exec  |  | - retry policies |  | - all CRUD       |  |
|  | - coordination   |  | - rollback      |  | - query+history  |  |
|  +------------------+  +------------------+  +------------------+  |
+------------------------------------------------------------------+
```

### 5.2 Key Changes from v1.0

| v1.0 | v2.0 |
|------|------|
| Hardcoded 9-task template | Plugin-based decomposition strategies |
| DEFAULT_ROLE_MAP with hardcoded providers | Delegates ALL provider selection to OmniRoute |
| In-memory _missions dict | Persistent MissionStore (SQLite/PostgreSQL) |
| Keyword heuristic complexity | Historical data + heuristics from AI Brain |
| Sequential execution default | HYBRID parallel execution default |
| Fixed role-to-provider map | Mission specifies role+capability, OmniRoute resolves |

### 5.3 Decomposition Strategy Chain

```python
strategies = [
    LLMDecomposition,           # Highest accuracy, needs working LLM
    TemplateBasedDecomposition, # Uses saved templates
    RuleBasedDecomposition,     # Enhanced keyword matching
    SimpleDecomposition,        # Fallback: single task per objective
]
```

### 5.4 Mission Lifecycle (with OmniRoute Integration)

```
1. CREATE -> DRAFT (saved to MissionStore)
2. ANALYZE -> PLANNING
   a) Complexity from AI Brain historical data
   b) Risk analysis (priority + deadline + complexity)
   c) Decompose via best-matching strategy
   d) For each task: OmniRoute.select(capability) -> provider+model
   e) Build dependency DAG
   f) Save to MissionStore, emit MISSION_PLANNED
3. EXECUTE -> EXECUTING
   a) Topological sort, dispatch via CoordinationEngine
   b) OmniRoute handles routing per task
   c) Checkpoint every N tasks
   d) AI Brain records execution telemetry
4. COMPLETE -> COMPLETED / FAILED / CANCELLED
```

---

## 6. Prompt Center

### 6.1 v2.0 Architecture

Prompt Center evolves from 4 stub endpoints to a full prompt management service.

```
+------------------------------------------------------------------+
|                        PROMPT CENTER v2.0                          |
|                                                                    |
|  +------------------+  +------------------+  +------------------+  |
|  | PromptRegistry   |  | PromptComposer   |  | ContextEngine    |  |
|  | - CRUD templates |  | - template fill  |  | - memory inject  |  |
|  | - versioning     |  | - attachment     |  | - knowledge      |  |
|  | - categorization |  |   processing     |  |   retrieval      |  |
|  | - A/B testing    |  | - multi-modal    |  | - mission ctx    |  |
|  +------------------+  |   assembly       |  | - conversation   |  |
|                         +------------------+  +------------------+  |
|  +------------------+  +------------------+  +------------------+  |
|  | AttachmentEngine |  | StreamingEngine  |  | -> OmniRoute     |  |
|  | - OCR processing |  | - SSE streaming  |  |    for provider  |  |
|  | - image analysis |  | - chunked output |  |    selection     |  |
|  | - PDF extraction |  | - token counting |  +------------------+  |
|  | - screenshot     |  +------------------+                       |
|  +------------------+                                              |
+------------------------------------------------------------------+
```

### 6.2 Key Changes from v1.0

| v1.0 | v2.0 |
|------|------|
| 4 stub endpoints | Full CRUD + compose + execute + streaming |
| Delegates to mission_planner | Standalone service with own store |
| No template management | Versioned templates with categories + A/B testing |
| No attachment processing | OCR, image analysis, PDF extraction |
| No streaming | SSE streaming with token counting |
| No OmniRoute integration | Routes through OmniRoute for provider selection |

---

## 7. AI Brain

### 7.1 Architecture - The Intelligence Center

The AI Brain becomes the central intelligence layer consuming real EventBus data.

```
+------------------------------------------------------------------+
|                         AI BRAIN v2.0                              |
|                                                                    |
|  DATA INGESTION:          KNOWLEDGE LAYER:       INTELLIGENCE:     |
|  +-------+ +-------+    +----------+ +--------+  +---------+      |
|  |EventBus| |OmniRte|    |Knowledge | |Provider|  |Optimiz  |      |
|  |Consumer| |Telem   |    |Graph     | |Profiles|  |Engine   |      |
|  +-------+ +-------+    +----------+ +--------+  +---------+      |
|  +-------+ +-------+    +----------+ +--------+  +---------+      |
|  |Mission | |Memory  |    |Metric    | |Cap     |  |Recommend|      |
|  |History | |Snapshot|    |Store     | |Map     |  |Engine   |      |
|  +-------+ +-------+    +----------+ +--------+  +---------+      |
|                                                                    |
|  ACTION LAYER:                                                     |
|  +---------+ +---------+ +---------+                              |
|  |EventBus  | |OmniRoute| |Dashboard|                              |
|  |Publisher | |Policy   | |Alerts   |                              |
|  +---------+ +---------+ +---------+                              |
+------------------------------------------------------------------+
```

### 7.2 Real Data Sources (No Mocks)

| Source | Data | Frequency | Storage |
|--------|------|-----------|---------|
| EventBus | All execution events | Real-time | Telemetry Store |
| OmniRoute | Routing decisions, latency, costs | Per-execution | Telemetry Store |
| Mission Orchestrator | Mission plans, task results | Per-mission | Mission Store |
| Runtime Discovery | Engine info, capabilities | On-change | Discovery Cache |
| MCP Registry | Tool invocations | Per-invocation | Telemetry Store |
| Self-Healing | Issues, repairs | Per-event | Issue Store |
| Provider Health | Health checks, failures | 2-second intervals | Health Store |

### 7.3 Key Changes from v1.0

| v1.0 Problem | v2.0 Solution |
|-------------|---------------|
| 17 subsystems, all in-memory stubs | Real implementations backed by persistent stores |
| No real EventBus consumption | EventBus consumer ingests ALL events |
| Learning data is mocked | All telemetry is real execution data |
| Knowledge graph is in-memory | Knowledge Graph in Vector DB (persistent) |
| No provider performance profiling | Provider Profiles maintained per provider/model |
| No routing optimization | Optimization Engine tunes OmniRoute policies |
| Benchmarks are fake | Real benchmarks against actual execution history |

---

## 8. Agent Constellation

### 8.1 Architecture - Live Visualization

Every node = REAL discovered runtime. Every edge = REAL communication.

```
+------------------------------------------------------------------+
|                    AGENT CONSTELLATION v2.0                        |
|                                                                    |
|  DATA SOURCES:                  VISUALIZATION:                    |
|  +------------------+          +------------------+               |
|  | EventBus         | -------> | Node Registry    |               |
|  | Mission Planner  | -------> | Edge Tracker     |               |
|  | Runtime Discovery| -------> | Live WebSocket   |               |
|  | MCP Registry     | -------> | Push to Next.js  |               |
|  | OmniRoute        | -------> | Constellation    |               |
|  +------------------+          | View             |               |
|                                 +------------------+               |
+------------------------------------------------------------------+
```

### 8.2 Node Types

| Type | Source | Real Data |
|------|--------|-----------|
| Runtime | Runtime Discovery | Engine name, type, version, health |
| Provider | OmniRoute Registry | Provider name, models, status, latency |
| Agent | Orchestration Framework | Agent ID, swarm membership, task |
| MCP Server | MCP Registry | Server name, transport, tools |
| Plugin | Plugin Registry | Plugin name, capabilities, status |
| Local Model | Discovery + Config | Model name, context, status |

### 8.3 Key Changes from v1.0

| v1.0 | v2.0 |
|------|------|
| Static provider list | Real discovered runtimes |
| Placeholder nodes | Every node is a real runtime |
| No edge tracking | Edge tracker records real communication |
| No MCP nodes | MCP servers as first-class nodes |
| No OmniRoute integration | Active routes shown in real-time |
| Dashboard polls | WebSocket push for all updates |

---

## 9. Desktop Diagnostics

### 9.1 v2.0 Architecture

Diagnostics becomes a real validation system backed by the Discovery and Self-Healing engines.

```
+------------------------------------------------------------------+
|                    DESKTOP DIAGNOSTICS v2.0                        |
|                                                                    |
|  SCANS:                    CHECKS:                  REPAIRS:       |
|  +------------------+     +------------------+    +-------------+ |
|  | Deep Scan        |     | Pipeline         |    | Auto Heal   | |
|  | - all subsystems |     | Engine validation |    | (LOW/MED)  | |
|  | - full validation|     | Runtime validation|    +-------------+ |
|  | - capability test|     | Provider check   |    +-------------+ |
|  | - integration    |     | Installer verify |    | Guided      | |
|  |   verification   |     | Config check     |    | Repair      | |
|  +------------------+     | DB integrity     |    | (HIGH/CRIT) | |
|  +------------------+     | Plugin validation|    +-------------+ |
|  | Surface Scan     |     | MCP connectivity |                     |
|  | - quick check    |     +------------------+                     |
|  | - health status  |                                              |
|  | - error log      |                                              |
|  +------------------+                                              |
|  +------------------+                                              |
|  | Quick Scan       |                                              |
|  | - 5-second check |                                              |
|  | - core health    |                                              |
|  +------------------+                                              |
|                                                                    |
|  OUTPUTS:                                                          |
|  +------------------+  +------------------+  +------------------+  |
|  | Diagnostics      |  | Repair History   |  | Health Dashboard |  |
|  | Report (JSON)    |  | (Persistent)     |  | (EventBus feed)  |  |
|  +------------------+  +------------------+  +------------------+  |
+------------------------------------------------------------------+
```

### 9.2 Scan Levels

| Scan | Duration | Coverage | Validations |
|------|----------|----------|-------------|
| Quick | <5s | Core | EventBus, Vault, Persistence, Health |
| Surface | <30s | Standard | Quick + Providers, Runtime, MCP, Plugins |
| Deep | <5min | All | Surface + full capability tests, integration verification, end-to-end flows |

### 9.3 Validation Targets (All Real)

| Target | Validator | What's Checked |
|--------|-----------|---------------|
| Pipeline | PipelineValidator | Syntax, dependencies, stage health |
| Runtime | RuntimeValidator | Engine connectivity, capability match |
| Provider | ProviderValidator | API key valid, auth works, model responds |
| Installer | InstallerValidator | Path exists, version matches, dependencies |
| Configuration | ConfigValidator | All settings valid, no conflicts |
| Database | DBValidator | Schema version, integrity check, migration status |
| Plugin | PluginValidator | Manifest valid, sandbox works, capability declared |
| MCP | MCPValidator | Transport works, protocol handshake, tool list |
| EventBus | EventBusValidator | Publish/subscribe, ordering, delivery |
| OmniRoute | OmniRouteValidator | Route resolution, failover, telemetry |

---

## 10. Desktop Runtime

### 10.1 Architecture - Rust/Tauri v2 with Embedded Backend

The Desktop Runtime moves from pure Python in-memory stubs to a Rust/Tauri native layer with IPC bridge to the Python backend.

```
+------------------------------------------------------------------+
|                    DESKTOP RUNTIME v2.0 (Tauri/Rust)               |
|                                                                    |
|  +--------------------------------------------------------------+ |
|  |                   TAURI SHELL (Rust)                           | |
|  |  +------------------+  +------------------+  +-------------+ | |
|  |  | Window Manager   |  | Process Manager  |  | System Tray | | |
|  |  | - multi-window   |  | - spawn/terminate|  | - menu      | | |
|  |  | - workspace mgmt |  | - monitor health |  | - status    | | |
|  |  | - WebView2 GPU   |  | - resource limits|  | - quick cmds| | |
|  |  +------------------+  +------------------+  +-------------+ | |
|  |                                                               | |
|  |  +------------------+  +------------------+  +-------------+ | |
|  |  | Auto-Updater     |  | Crash Reporter   |  | IPC Bridge  | | |
|  |  | - version check  |  | - minidump       |  | (Tauri cmd) | | |
|  |  | - delta updates  |  | - upload to      |  | - JSON-RPC  | | |
|  |  | - rollback       |  |   Sentry/host    |  | - streaming | | |
|  |  +------------------+  +------------------+  +-------------+ | |
|  +--------------------------------------------------------------+ |
|                               |                                    |
|                     IPC Bridge (JSON-RPC over stdin/stdout)        |
|                               |                                    |
|  +--------------------------------------------------------------+ |
|  |                  EMBEDDED PYTHON BACKEND                       | |
|  |  +------------------+  +------------------+  +-------------+ | |
|  |  | AgenticOS Kernel |  | OmniRoute        |  | Discovery   | | |
|  |  | (All subsystems) |  | (Embedded engine) |  | Framework   | | |
|  |  +------------------+  +------------------+  +-------------+ | |
|  |                                                               | |
|  |  +------------------+  +------------------+  +-------------+ | |
|  |  | Local Persistence|  | Mission Control   |  | Plugin      | | |
|  |  | (SQLite/Redis)   |  | (Tauri embedded)  |  | Engine     | | |
|  |  +------------------+  +------------------+  +-------------+ | |
|  +--------------------------------------------------------------+ |
+------------------------------------------------------------------+
```

### 10.2 IPC Protocol

```json
// Request from Rust -> Python
{
  "id": "req_001",
  "method": "omniroute.route",
  "params": { "capability": "chat", "features": ["streaming"] }
}

// Response from Python -> Rust
{
  "id": "req_001",
  "result": { "provider": "claude_code", "model": "claude-sonnet-5", ... }
}

// Streaming (for chat completions)
{
  "id": "req_001",
  "stream": true,
  "data": { "chunk": "Hello", "done": false }
}
```

### 10.3 Key Changes from v1.0

| v1.0 Problem | v2.0 Solution |
|-------------|---------------|
| 27 concrete subsystems with zero ports | 27 port protocols implemented in Rust |
| All in-memory stubs | Real implementations (process, window, clipboard, etc.) |
| Pure Python desktop layer | Rust/Tauri v2 native layer |
| No auto-update | Auto-Updater with delta updates + rollback |
| No crash reporting | Crash Reporter with minidump + Sentry |
| No IPC (REST for local) | IPC Bridge (JSON-RPC) for local calls |
| No GPU rendering | WebView2 GPU-accelerated rendering |

---

## 11. EventBus

### 11.1 v2.0 Architecture

```
+------------------------------------------------------------------+
|                       EVENTBUS v2.0                                |
|                                                                    |
|  CORE BUS:                    FEATURES:                           |
|  +------------------+        +------------------+                  |
|  | LocalBus         |        | Persistence      |                  |
|  | (in-process)     |        | (Redis Streams   |                  |
|  +------------------+        |  XADD / XREAD)   |                  |
|  +------------------+        +------------------+                  |
|  | RedisStreamsBus  |        +------------------+                  |
|  | (default prod)   |        | Ordering         |                  |
|  +------------------+        | (per-stream FIFO)|                  |
|  +------------------+        +------------------+                  |
|  | NatsJetStreamBus |        +------------------+                  |
|  | (distributed)    |        | Replay Engine    |                  |
|  +------------------+        | (XREAD from ID)  |                  |
|                               +------------------+                  |
|  SUBSCRIPTIONS:              +------------------+                  |
|  +------------------+        | Telemetry        |                  |
|  | Topic matching   |        | (event count,    |                  |
|  | Wildcard support |        |  latency, errors)|                  |
|  | Filter by source |        +------------------+                  |
|  | Filter by type   |        +------------------+                  |
|  +------------------+        | Dead Letter      |                  |
|  +------------------+        | (failed events)  |                  |
|  | Consumer Groups  |        +------------------+                  |
|  | (Redis XGROUP)   |                                             |
|  +------------------+                                             |
+------------------------------------------------------------------+
```

### 11.2 Port Contract (v2.0, Expanded)

```python
class EventBusPort(Protocol):
    async def start(self) -> None: ...
    async def stop(self) -> None: ...

    async def publish(self, event: EventEnvelope) -> None: ...
    async def publish_many(self, events: list[EventEnvelope]) -> None: ...

    async def subscribe(
        self,
        topic: str | list[str],     # Topic(s), supports wildcard
        handler: Handler,
        *,
        filter: EventFilter | None = None,
        group: str | None = None,   # Consumer group (Redis/NATS)
    ) -> str: ...                    # Returns subscription_id

    async def unsubscribe(self, subscription_id: str) -> None: ...
    async def unsubscribe_all(self) -> None: ...

    # New v2.0 methods
    async def replay(
        self,
        topic: str,
        from_id: str,
        handler: Handler,
        limit: int = 100,
    ) -> int: ...                    # Returns count of replayed events

    async def get_stats(self) -> EventBusStats: ...
    async def get_dead_letters(self, limit: int = 50) -> list[DeadLetter]: ...
    async def flush(self) -> None: ...
```

### 11.3 Key Changes from v1.0

| v1.0 Problem | v2.0 Solution |
|-------------|---------------|
| No persistence | Persistence via Redis Streams XADD (always-on for production buses) |
| No replay capability | Replay Engine: XREAD from event ID, filter by topic |
| No subscription filtering | EventFilter: filter by source, type, payload content |
| No telemetry per event | Per-event latency, count, error tracking |
| No dead letter queue | DeadLetter store for failed event processing |
| No wildcard subscriptions | Topic wildcards: "agent.*" matches all agent events |
| No publish_many | Batch publish for high-throughput scenarios |
| No consumer groups | Redis XGROUP for distributed consumers |
| No bus statistics | EventBusStats: count, rate, latency p50/p95/p99 |

---

## 12. API Gateway

### 12.1 v2.0 Architecture

```
+------------------------------------------------------------------+
|                       API GATEWAY v2.0                             |
|                                                                    |
|  +------------------+  +------------------+  +------------------+  |
|  | REST Gateway     |  | WebSocket Gateway|  | Streaming Gateway|  |
|  | - /api/*         |  | - /ws/dashboard  |  | - SSE endpoints  |  |
|  | - versioning     |  | - /ws/mcp        |  | - chunked output |  |
|  | - auto-openapi   |  | - /ws/omniroute  |  | - token counting |  |
|  +------------------+  +------------------+  +------------------+  |
|                                                                    |
|  +------------------+  +------------------+  +------------------+  |
|  | OpenAI Gateway   |  | Anthropic Gateway|  | A2A Gateway      |  |
|  | - /v1/chat/comp  |  | - /v1/messages   |  | - /a2a/*        |  |
|  | - /v1/completions|  | - /v1/stream     |  | - agent-to-agent|  |
|  | - /v1/embeddings |  | - /v1/batch      |  +------------------+  |
|  | - /v1/models     |  +------------------+  +------------------+  |
|  +------------------+                       | MCP Gateway      |  |
|  +------------------+                       | - /mcp/*         |  |
|  | Auth Middleware  |                       | - tool calls      |  |
|  | - JWT validation |                       | - resource access |  |
|  | - API key auth   |                       +------------------+  |
|  | - rate limiting  |                                             |
|  +------------------+                                             |
+------------------------------------------------------------------+
```

### 12.2 Protocol Adapters (v2.0, Expanded from 2 to 6)

| Protocol | Base Path | Purpose |
|----------|-----------|---------|
| REST | /api/* | All AgenticOS management APIs (396+ endpoints) |
| WebSocket | /ws/* | Real-time dashboard, MCP, OmniRoute, diagnostics |
| OpenAI | /v1/* | OpenAI-compatible chat, completions, embeddings, models |
| Anthropic | /v1/anthropic/* | Anthropic-compatible messages, stream |
| A2A | /a2a/* | Agent-to-Agent protocol for inter-agent communication |
| MCP | /mcp/* | MCP protocol (stdio/SSE/HTTP) for external MCP clients |

### 12.3 Key Changes from v1.0

| v1.0 Problem | v2.0 Solution |
|-------------|---------------|
| Single app.py with 396 endpoints | Modular routers per gateway |
| No auth middleware | JWT validation + API key auth + RBAC |
| No rate limiting | Rate limiting per API key per endpoint |
| Only OpenAI gateway | OpenAI + Anthropic + A2A + MCP |
| No WebSocket auth | WebSocket auth with JWT token |
| No API versioning | Versioned API routes (/api/v1/*) |
| No streaming gateway | Dedicated streaming gateway with SSE |

---

## 13. Plugin Marketplace

### 13.1 v2.0 Architecture

```
+------------------------------------------------------------------+
|                    PLUGIN MARKETPLACE v2.0                         |
|                                                                    |
|  LOCAL LIFECYCLE:          MARKETPLACE:              DEVELOPER:    |
|  +------------------+     +------------------+    +-------------+ |
|  | PluginRegistry   |     | Remote Repository |    | Plugin SDK  | |
|  | - CRUD lifecycle |     | - plugin listings |    | - template  | |
|  | - dependency     |     | - version catalog |    | - generators| |
|  |   resolution     |     | - download/install|    | - testing   | |
|  | - capability     |     | - ratings/reviews |    |   harness   | |
|  |   scanning       |     | - publisher auth  |    | - packaging | |
|  +------------------+     +------------------+    +-------------+ |
|                                                                    |
|  SANDBOX:                  SIGNING:                  UPDATES:      |
|  +------------------+     +------------------+    +-------------+ |
|  | PluginSandbox    |     | SignatureVerify   |    | Auto-Update | |
|  | - restricted env |     | - SHA-256 hash    |    | - version   | |
|  | - capability     |     | - signer cert     |    |   check     | |
|  |   permissions    |     | - chain-of-trust  |    | - delta     | |
|  | - resource limits|     | - revocation      |    |   download  | |
|  +------------------+     +------------------+    +-------------+ |
+------------------------------------------------------------------+
```

### 13.2 Plugin Manifest (v2.0)

```python
class PluginManifest(BaseModel):
    id: str                       # Unique plugin ID
    name: str                     # Display name
    version: str                  # Semver
    min_agentic_os_version: str   # Compatibility requirement
    author: str
    description: str
    capabilities: list[str]       # Declared capabilities
    permissions: list[str]        # Required permissions (filesystem, network, etc.)
    dependencies: list[str]       # Required plugin IDs
    entry_point: str              # Main module path
    sandbox_config: SandboxConfig | None
    signature: str | None         # Signed hash
    marketplace_url: str | None   # Marketplace listing URL
```

### 13.3 Key Changes from v1.0

| v1.0 Problem | v2.0 Solution |
|-------------|---------------|
| Local filesystem only | Marketplace: remote repository with version catalog |
| SHA-256 stub | Real signature verification with signing key + chain-of-trust |
| No auto-update | Auto-Update with version check + delta download |
| No plugin SDK | Plugin SDK with templates, generators, testing harness |
| No permission model | Declared permissions in manifest, enforced by sandbox |
| No dependency resolution | Topological sort with cycle detection |

---

## 14. Persistence Architecture

### 14.1 v2.0 Storage Layer

```
+------------------------------------------------------------------+
|                     PERSISTENCE ARCHITECTURE v2.0                  |
|                                                                    |
|  +------------------+  +------------------+  +------------------+  |
|  | SQLite (Local)   |  | PostgreSQL       |  | Redis            |  |
|  | - Desktop state  |  | (Server/Multi)   |  | (Cache/Queue)    |  |
|  | - Discovery cache|  | - Mission store  |  | - EventBus       |  |
|  | - User settings  |  | - Telemetry      |  | - Session cache  |  |
|  | - Offline queue  |  | - Workflow state |  | - Rate limits    |  |
|  | - Local audit    |  | - User accounts  |  | - Locks          |  |
|  +------------------+  | - Plugin data    |  +------------------+  |
|                         +------------------+  +------------------+  |
|  +------------------+  +------------------+  | Vector DB        |  |
|  | All stores       |  | All stores       |  | - Knowledge Graph|  |
|  | behind Port      |  | behind Port      |  | - Memory vectors |  |
|  | Protocol         |  | Protocol         |  | - Semantic search|  |
|  +------------------+  +------------------+  | - Embedding store |  |
|                                                +------------------+  |
+------------------------------------------------------------------+
```

### 14.2 Store Protocols

```python
class Store[T](Protocol):
    """Generic persistent store interface."""

    async def get(self, id: str) -> T | None: ...
    async def put(self, item: T) -> str: ...
    async def delete(self, id: str) -> None: ...
    async def list(self, query: Query[T]) -> list[T]: ...
    async def count(self, query: Query[T]) -> int: ...


class MissionStorePort(Protocol):
    """Persistent mission storage."""

    async def save_mission(self, mission: Mission) -> str: ...
    async def get_mission(self, id: str) -> Mission | None: ...
    async def list_missions(self, status: MissionStatus | None = None) -> list[Mission]: ...
    async def save_plan(self, plan: MissionPlan) -> str: ...
    async def get_plan(self, id: str) -> MissionPlan | None: ...


class TelemetryStorePort(Protocol):
    """Execution telemetry storage."""

    async def record(self, entry: TelemetryEntry) -> str: ...
    async def query(self, q: TelemetryQuery) -> list[TelemetryEntry]: ...
    async def aggregate(self, q: AggregateQuery) -> AggregateResult: ...


class HealthStorePort(Protocol):
    """Health check and issue storage."""

    async def record_health(self, status: HealthStatus) -> None: ...
    async def get_latest(self, subsystem: str) -> HealthStatus | None: ...
    async def record_issue(self, issue: HealingIssue) -> str: ...
    async def list_issues(self, resolved: bool = False) -> list[HealingIssue]: ...
```

### 14.3 Store Implementations

| Store | SQLite | PostgreSQL | Redis | Vector DB |
|-------|--------|-----------|-------|-----------|
| MissionStore | YES | YES | NO | NO |
| WorkflowStore | YES | YES | NO | NO |
| PipelineStore | YES | YES | NO | NO |
| TelemetryStore | NO | YES | YES (ephemeral) | NO |
| HealthStore | YES | YES | NO | NO |
| DiscoveryCache | YES | NO | YES | NO |
| SecretStore | YES (encrypted) | YES (encrypted) | NO | NO |
| EventStore | NO | YES | YES (Streams) | NO |
| KnowledgeGraph | NO | NO | NO | YES |
| MemoryStore | NO | NO | NO | YES |
| SessionStore | NO | NO | YES | NO |
| RateLimitStore | NO | NO | YES | NO |

### 14.4 Key Changes from v1.0

| v1.0 Problem | v2.0 Solution |
|-------------|---------------|
| In-memory dicts for all core state | Persistent stores behind Port protocols |
| Only Fernet vault + SQLite desktop | Full storage stack: SQLite + PostgreSQL + Redis + Vector DB |
| No telemetry store | TelemetryStore for AI Brain data |
| No health history | HealthStore with persistent issue log |
| No mission/workflow/pipeline persistence | MissionStore, WorkflowStore, PipelineStore |
| No migration system | Schema migration per store (versioned) |
| SQLite has no migratons | Alembic-style migration runner |

---

## 15. Self-Healing

### 15.1 v2.0 Architecture

```
+------------------------------------------------------------------+
|                    SELF-HEALING ENGINE v2.0                        |
|                                                                    |
|  HEALTH INPUTS:              DECISION:                  ACTIONS:   |
|  +------------------+     +------------------+    +-------------+ |
|  | EventBus Events  |     | Severity         |    | Auto-Repair | |
|  | - AGENT_FAILED   |     | Classifier       |    | (LOW/MED)   | |
|  | - HEALTH_DEGRADED|     | - failure type   |    |             | |
|  | - PROVIDER_FAILED|     | - impact scope   |    | Guided      | |
|  | - CONNECTION_LOST|     | - frequency      |    | Repair      | |
|  | - TASK_FAILED    |     | - dependency     |    | (HIGH/CRIT) | |
|  | - PLUGIN_FAILED  |     +------------------+    +-------------+ |
|  +------------------+                            +-------------+ |
|  +------------------+     +------------------+    | Circuit     | |
|  | Health Probes    |     | Resolution Engine|    | Breaker     | |
|  | - Subsystem check|     | - healing steps  |    | (NEW)       | |
|  | - Provider check |     | - rollback plan  |    +-------------+ |
|  | - Process check  |     | - verification  |                     |
|  | - Port check     |     +------------------+                     |
|  +------------------+                                              |
|                                                                    |
|  ISSUE TRACKING:            PERSISTENCE:                           |
|  +------------------+     +------------------+                    |
|  | Issue Store      |     | History Store    |                    |
|  | (Persistent)     |     | (All resolutions)|                    |
|  | - fixed: pruned  |     | - for AI Brain   |                    |
|  | - open: retained |     | - for reporting  |                    |
|  +------------------+     +------------------+                    |
+------------------------------------------------------------------+
```

### 15.2 Healing Actions (v2.0, Expanded)

| Action | Severity | Auto | v2.0 Change |
|--------|----------|------|-------------|
| websocket_reconnect | MEDIUM | YES | Fixed - uses EventBus.stop/start |
| rebuild_cache | LOW | YES | Fixed - uses DiscoveryCache.clear() |
| reload_config | MEDIUM | NO | Now uses ConfigStore.reload() |
| restart_provider | MEDIUM | YES | Circuit breaker check before restart |
| repair_bindings | MEDIUM | YES | OmniRoute re-registers failed provider |
| restart_backend | CRITICAL | NO | Now actually restarts backend process |
| rebuild_indexes | LOW | YES | MemoryManager.rebuild() |
| resync_state | LOW | YES | Fixed - uses EventBus replay from last checkpoint |
| restart_plugin | MEDIUM | YES | Fixed - uses PluginRegistry restart |
| repair_runtime | MEDIUM | YES | RuntimeManager re-discovers engine |

**New v2.0 Actions:**
| Action | Severity | Description |
|--------|----------|-------------|
| circuit_breaker_trip | HIGH | Open circuit for failing provider |
| circuit_breaker_half_open | MEDIUM | Test if provider recovered |
| omniroute_failover | MEDIUM | Failover to alternate provider |
| kill_zombie_task | MEDIUM | Force-kill hung task |
| rotate_vault_key | HIGH | Rotate encryption master key |
| reset_rate_limiter | LOW | Clear rate limit state for provider |

### 15.3 Circuit Breaker (v2.0, New)

```python
class CircuitBreaker:
    """Circuit breaker for provider/endpoint health."""

    state: Literal["closed", "open", "half-open"]
    failure_count: int
    failure_threshold: int       # Default: 5
    recovery_timeout: float      # Default: 30.0 seconds
    half_open_max_requests: int  # Default: 1

    async def call(self, fn: Callable) -> Result:
        """Execute fn with circuit breaker protection."""
        ...

    async def record_success(self) -> None: ...
    async def record_failure(self) -> None: ...
    async def reset(self) -> None: ...
```

### 15.4 Key Changes from v1.0

| v1.0 Problem | v2.0 Solution |
|-------------|---------------|
| Dead imports crash at runtime | All imports verified; code paths tested |
| Unbounded _issues list | Persistent store with fixed-size active set |
| No locks on shared state | asyncio.Lock on all mutable state |
| No circuit breaker | CircuitBreaker per provider/endpoint |
| No persistence | IssueStore + HistoryStore (SQLite) |
| No AI Brain integration | Resolution patterns fed to learning engine |
| SelfHealingEngine has dead code (_restart_backend always False) | All actions implemented and tested |
| No integration with OmniRoute | Circuit breaker feeds failover decisions |

---

## 16. Security Architecture

### 16.1 v2.0 Architecture

```
+------------------------------------------------------------------+
|                    SECURITY ARCHITECTURE v2.0                      |
|                                                                    |
|  +------------------+  +------------------+  +------------------+  |
|  | Vault            |  | API Key Manager  |  | Secrets Rotation |  |
|  | - Fernet AES-256 |  | - CRUD keys      |  | - auto-rotation  |  |
|  | - master key     |  | - masked display |  | - scheduled      |  |
|  | - file-based     |  | - encryption     |  | - history        |  |
|  | - env fallback   |  | - scoping        |  +------------------+  |
|  +------------------+  +------------------+                       |
|                                                                    |
|  +------------------+  +------------------+  +------------------+  |
|  | RBAC Engine      |  | Auth Middleware  |  | Audit Log        |  |
|  | - roles          |  | - JWT validation |  | - all operations |  |
|  | - permissions    |  | - API key auth   |  | - tamper-proof   |  |
|  | - role hierarchy |  | - OAuth2 support |  | - persistent     |  |
|  | - policy eval    |  | - session mgmt  |  | - queryable      |  |
|  +------------------+  +------------------+  +------------------+  |
|                                                                    |
|  +------------------+  +------------------+  +------------------+  |
|  | Sandbox          |  | Cert Manager     |  | Token Manager    |  |
|  | - plugin sandbox |  | - TLS certs      |  | - OAuth tokens    |  |
|  | - restricted env |  | - signing keys   |  | - refresh flow    |  |
|  | - permission     |  | - trust store    |  | - revocation      |  |
|  |   enforcement    |  | - expiry alerts  |  +------------------+  |
|  +------------------+  +------------------+                       |
+------------------------------------------------------------------+
```

### 16.2 Key Changes from v1.0

| v1.0 | v2.0 |
|------|------|
| No auth middleware | JWT validation + API key auth + OAuth2 |
| No RBAC | RBAC engine with role hierarchy + policy evaluation |
| No audit log | Persistent tamper-proof audit log |
| No auto-rotation | Scheduled secrets rotation |
| No cert management | Cert Manager with expiry alerts |
| No token management | OAuth token manager with refresh flow |
| Sandbox is basic | Hardened sandbox with permission enforcement |
| No session management | Session store with expiry |

---

## 17. Installer Architecture

### 17.1 Platform Installers

| Platform | Format | Bundled | Size (est) |
|----------|--------|---------|------------|
| Windows | MSI (WiX) | Backend, Frontend, OmniRoute, Discovery, Plugins, Python runtime | ~150-250 MB |
| Windows | NSIS (Portable) | Same (no registry, USB portable) | ~120-200 MB |
| Linux | AppImage | Backend, Frontend, OmniRoute, Discovery, Plugins, Python runtime | ~150-250 MB |
| Linux | Deb (APT) | Same + systemd service + desktop entry | ~150-250 MB |
| Linux | RPM (Fedora) | Same for Fedora/RHEL | ~150-250 MB |
| macOS | DMG | Same as DMG standard | ~150-250 MB |

### 17.2 Installer Contents

```
AgenticOS Installer
  +-- backend/agentic_os/       # Python package (compiled .pyc)
  +-- backend/python/           # Embedded Python 3.12+ runtime
  +-- frontend/mission-control/ # Next.js static export
  +-- frontend/desktop/         # Tauri app binary
  +-- omniroute/core/           # Routing engine
  +-- omniroute/providers/      # Default provider configs
  +-- omniroute/models/         # Model registry defaults
  +-- discovery/providers/      # Discovery provider configs
  +-- discovery/profiles/       # Default scan profiles
  +-- plugins/built-in/         # Pre-installed plugins
  +-- config/                   # Default YAML configs
  +-- resources/                # Icons, assets, locales
  +-- tools/agentic-os-cli      # CLI binary
  +-- tools/agentic-os-diag     # Diagnostic tool
```

### 17.3 First-Run Sequence

```
1. INSTALL: Extract -> Register app -> Create config dir
   -> Generate master key -> (optional) Add to startup
2. FIRST LAUNCH: Discovery scan -> Detect AI providers
   -> Detect local models -> Generate health report
   -> Launch dashboard -> Show first-run wizard
3. CONTINUOUS: Auto-update checks -> Periodic discovery
   -> Health monitoring -> Telemetry (opt-in)
```

### 17.4 Auto-Updater

| Feature | Implementation |
|---------|---------------|
| Version check | GitHub Releases API on startup + periodic |
| Download | Delta updates (binary diff) when possible |
| Verification | SHA-256 + code signing certificate verify |
| Rollback | Previous version preserved; one-click rollback |
| Channels | Stable, Beta, Nightly |
| Silent install | Background download + next-launch install |

---

## 18. Deployment Architecture

### 18.1 CI/CD Pipeline

```
GitHub Repository
  +-- Push / PR (any branch)
  |     +-- Lint (ruff) + Type check (mypy)
  |     +-- Unit tests (pytest, >80% coverage)
  |     +-- Security scan (bandit, safety)
  |     +-- Build Python package (hatchling)
  |     +-- Build frontend (Next.js build)
  |     +-- Integration tests
  |
  +-- Tag (v*.*.*) -> Release
        +-- Full test suite
        +-- Build all installers
        +-- Code signing (Authenticode, macOS notarize)
        +-- Generate checksums
        +-- Create GitHub Release
        +-- Publish to package managers (winget, brew, apt)
        +-- Deploy telemetry backend
```

### 18.2 Test Matrix

| Suite | PR | Nightly | RC | Release |
|-------|-----|---------|-----|---------|
| Unit | 100% | 100% | 100% | 100% |
| Integration | Core | All | All | All |
| E2E (Playwright) | - | Core | All | All |
| Performance | - | - | Yes | Yes |
| Security | - | - | Yes | Yes |
| Compatibility | - | - | Matrix | Matrix |
| Installer | - | - | All | All |
| Upgrade | - | - | Matrix | Matrix |

---

## 19. Complete Subsystem Dependency Graph

### 19.1 Layer Dependency Map

```
LEVEL 0 (No Dependencies)
  Domain Models (events.py, agent.py, mission.py, orchestration.py, mcp.py)
  Settings (config.py)

LEVEL 1 (Depends on Level 0)
  Port Protocols (ports/*.py)
  EventBus Adapters (adapters/bus/*.py)
  Logging (infrastructure/logging.py)

LEVEL 2 (Depends on Level 1)
  Security: Vault, SecretStore, EncryptedStore
  Persistence: SQLite connect, PostgreSQL pool, Redis client
  Core: Scheduler, Orchestrator

LEVEL 3 (Depends on Level 2)
  Health: HealthMonitor, RecoveryManager
  Runtime: ExecutionEngineBase, RuntimeManager, GenericEngine
  Discovery: DiscoveryEngine, DiscoveryFramework, all providers
  Memory: MemoryManager, in-memory stores
  Provider: ProviderManager, ModelManager, CostTracker, RateLimitMonitor
  Plugin: PluginRegistry, PluginLoader, PluginSandbox

LEVEL 4 (Depends on Level 3)
  OMNIROUTE: ProviderRegistry, RouterEngine, ModelRegistry, BudgetEngine,
             FailoverEngine, CompressionEngine, GatewayAdapter, Policies, Routers
  Mission: MissionPlanner, MissionStore
  Workflow: WorkflowEngine
  Pipeline: PipelineEngine
  Security Framework: RBAC, Auth, Audit

LEVEL 5 (Depends on Level 4)
  Orchestration Framework: SwarmPlanner, Scheduler, Supervisor, Coordination,
                           Communication, Intelligence, Checkpoint, Recovery,
                           ResultMerger, Validation, Metrics, CostTracker
  MCP Framework: MCPRegistry, MCPManager, MCPClient, all sub-registries
  AI Brain: LearningManager, all optimization/recommendation engines

LEVEL 6 (Depends on Level 5)
  Desktop Runtime: Window, Process, IPC, Auto-Updater, Crash Reporter
  API Gateway: FastAPI app, all routers, middleware
  Dashboard: WebSocket broadcaster, MCP broadcaster

LEVEL 7 (Depends on Level 6)
  Tauri Desktop: Rust shell, IPC bridge
  Mission Control: Next.js frontend
  CLI: argparse interface
```

### 19.2 Event Flow Map

```
EventBus Topics -> Subscribers:
  task.created          -> Orchestrator, Dashboard, AI Brain, Logging
  task.completed        -> Orchestrator, Dashboard, AI Brain, Logging
  task.failed           -> Orchestrator, Recovery, Self-Healing, Dashboard, AI Brain
  agent.heartbeat       -> HealthMonitor, Dashboard
  agent.failed          -> Recovery, Self-Healing, Dashboard
  health.check          -> Dashboard, AI Brain
  health.degraded       -> Self-Healing, Dashboard
  provider.failed       -> OmniRoute (CircuitBreaker), Self-Healing, Dashboard
  provider.failover     -> OmniRoute, Dashboard, AI Brain
  cost.recorded         -> OmniRoute Budget, AI Brain, Dashboard
  mission.created       -> Mission Orchestrator, Dashboard
  mission.planned       -> Mission Orchestrator, Dashboard
  discovery.item_found  -> Runtime Registry, OmniRoute Registry, Dashboard
  discovery.scan_done   -> Dashboard, AI Brain
  mcp.server_registered -> MCP Framework, Dashboard
  mcp.server_failed     -> MCP Framework, Self-Healing, Dashboard
  plugin.installed      -> Plugin Registry, Dashboard
  plugin.failed         -> Self-Healing, Dashboard
  self_healing.issue    -> AI Brain, Dashboard, Issue Store
  learning.optimization -> OmniRoute (Policy update), Dashboard
  learning.recommend    -> Dashboard, OmniRoute
```

### 19.3 API to Core Dependencies

```
396 Endpoints -> Dependencies:
  /api/tasks/*              -> Orchestrator, OmniRoute
  /api/missions/*           -> MissionPlanner, MissionStore
  /api/agents/*             -> OrchestrationFramework
  /api/providers/*          -> OmniRoute ProviderRegistry
  /api/omniroute/*          -> OmniRoute (Router, Budget, Failover, Telemetry)
  /api/runtime/engines/*    -> RuntimeManager
  /api/discovery/*          -> DiscoveryFramework
  /api/mcp/servers/*        -> MCPManager, MCPRegistry
  /api/swarm/*              -> OrchestrationFramework
  /api/learning/*           -> LearningManager
  /api/workflows/*          -> WorkflowEngine
  /api/pipelines/*          -> PipelineEngine
  /api/memory/*             -> MemoryManager
  /api/diagnostics/*        -> SelfHealing, HealthMonitor
  /api/plugins/*            -> PluginRegistry
  /api/security/*           -> SecurityFramework
  /api/desktop/*            -> DesktopRuntime
  /api/prompts/*            -> PromptCenter
  /v1/*                     -> OmniRoute Gateway
  /ws/*                     -> Dashboard, MCP
```

### 19.4 Data Flow Map

```
PERSISTENT DATA FLOWS:
  EventBus Stream    -> Telemetry Store (AI Brain)
  OmniRoute Telemetry -> Telemetry Store
  Mission Executions  -> Mission Store
  Workflow Executions -> Workflow Store
  Pipeline Executions -> Pipeline Store
  Health Checks      -> Health Store
  Healing Issues     -> Issue Store
  Audit Events       -> Audit Log
  Secrets            -> Vault (encrypted)
  Discovery Items    -> Discovery Cache (SQLite + Redis)

EPHEMERAL DATA FLOWS:
  Real-time dashboard -> WebSocket (ring buffer)
  Inter-agent messages -> CommunicationBus (ring buffer)
  Orchestration checkpoints -> In-memory
  Rate limits         -> Redis (TTL)
  Locks               -> Redis (asyncio locks)
```

---

## 20. Migration Matrix

### 20.1 Subsystem Classification

Every v1.0.0-rc1 subsystem classified as KEEP / EXTEND / REFACTOR / REPLACE / REMOVE.

| Subsystem | File(s) | Decision | Reasoning |
|-----------|---------|----------|-----------|
| EventBus | ports/event_bus.py, adapters/bus/* | EXTEND | Protocol solid. Add persistence, replay, filtering, telemetry |
| EventEnvelope | domain/events.py | KEEP | Solid model |
| Settings | config.py | KEEP | pydantic-settings works. Add OmniRoute sections |
| Kernel | kernel.py | REPLACE | Replace manual __init__ with typed Container |
| Platform dataclass | kernel.py | REPLACE | Auto-generate from Container registry |
| ProviderManager | core/providers/manager.py | REPLACE | Move into OmniRoute ProviderRegistry |
| ModelManager | core/providers/manager.py | REPLACE | Move into OmniRoute ModelRegistry |
| ProviderRouter | core/providers/router.py | REPLACE | Move into OmniRoute RouterEngine |
| RoutingPolicy | core/providers/routing.py | EXTEND | Keep policies, move to OmniRoute policies/ |
| CostTracker | core/providers/routing.py | REPLACE | Move into OmniRoute BudgetEngine |
| RateLimitMonitor | core/providers/routing.py | REPLACE | Move into OmniRoute |
| ProviderHealth | core/providers/health.py | REPLACE | Move into OmniRoute + CircuitBreaker |
| ApiKeyVault | core/providers/vault.py | KEEP | Fernet works. Extend with auto-rotation |
| SelfHealingEngine | core/self_healing.py | REPLACE | Dead imports, unbounded list, no locks |
| HealthMonitor | core/health.py | EXTEND | Add system metrics, persistent store |
| RecoveryManager | core/recovery.py | EXTEND | Add exponential backoff, circuit breaker |
| MissionPlanner | core/mission.py | EXTEND | Plugin decomposition, OmniRoute delegation |
| MissionStore | (in-memory _missions) | REPLACE | New persistent store |
| WorkflowEngine | core/workflow/engine.py | EXTEND | Add persistence, OmniRoute routing |
| PipelineEngine | core/pipeline/engine.py | EXTEND | Add persistence, OmniRoute routing |
| MemoryManager | core/memory/manager.py | EXTEND | Add persistent backend |
| SecurityFramework | core/security/framework.py | EXTEND | Add RBAC, auth, audit log |
| RuntimeManager | core/runtime/manager.py | EXTEND | Add MCP/plugin runtime support |
| RuntimeRegistry | core/runtime/registry.py | EXTEND | Add persistence |
| DiscoveryEngine | core/runtime/discovery.py | REFACTOR | Merge into unified DiscoveryFramework |
| DiscoveryFramework | core/discovery/framework.py | EXTEND | Add model/MCP/plugin discovery |
| OrchestrationFramework | core/orchestration/framework.py | REFACTOR | Reduce manual wiring, add OmniRoute |
| Swarm subsystems | core/orchestration/*.py | EXTEND | Add OmniRoute routing integration |
| SwarmIntelligence | core/orchestration/intelligence.py | KEEP | Consensus/voting/leader election works |
| MCPRegistry | core/mcp/registry.py | KEEP | Solid: 3 transports, CRUD, lifecycle |
| MCPClient | core/mcp/client.py | KEEP | 3 transports + auto-reconnect |
| MCP sub-registries | core/mcp/*.py | KEEP | All 14 MCP files solid |
| PluginRegistry | core/plugins/registry.py | EXTEND | Add marketplace, signing, auto-update |
| PluginLoader | core/plugins/loader.py | KEEP | Sandboxed exec works |
| LearningManager | core/learning/manager.py | REPLACE | Replace stubs with real consumers |
| DesktopRuntimeManager | core/desktop/manager.py | REPLACE | Split into 27 ports, implement in Rust |
| DesktopHardening | core/desktop/hardening.py | REPLACE | Circular import, in-memory, no persistence |
| DashboardBroadcaster | api/dashboard.py | EXTEND | Add WebSocket auth, per-client filtering |
| FastAPI app | api/app.py (3926 lines) | REFACTOR | Split into modular routers |
| OpenAI Gateway | api/gateway.py | REPLACE | Move into OmniRoute GatewayAdapter |
| OmniRoute stubs | api/app.py (10 endpoints) | REPLACE | Real OmniRoute implementation |
| CLI | cli.py | EXTEND | Add diagnostic, discovery, OmniRoute subcommands |
| Domain models | domain/*.py | KEEP | Frozen/slots/immutable patterns are correct |
| Port protocols | ports/*.py | KEEP | Add OmniRoute + desktop ports |
| Logging | infrastructure/logging.py | KEEP | structlog works |

### 20.2 Classification Summary

| Decision | Count | Key Items |
|----------|-------|-----------|
| KEEP | 12 | EventEnvelope, Settings, SwarmIntelligence, MCPRegistry, MCPClient, PluginLoader, MCP sub-registries, domain models, port protocols, logging |
| EXTEND | 17 | EventBus, RoutingPolicies, HealthMonitor, RecoveryManager, MissionPlanner, WorkflowEngine, PipelineEngine, MemoryManager, SecurityFramework, RuntimeManager, DiscoveryFramework, orchestration subsystems, PluginRegistry, dashboard broadcasters, CLI |
| REFACTOR | 4 | DiscoveryEngine merge, OrchestrationFramework wiring, FastAPI app splitting |
| REPLACE | 14 | Kernel, Platform, ProviderManager, ModelManager, ProviderRouter, CostTracker, RateLimitMonitor, ProviderHealth, SelfHealingEngine, MissionStore, LearningManager, DesktopRuntimeManager, DesktopHardening, OpenAI gateway, OmniRoute stubs |
| REMOVE | 1 | Phase 1 Provider/Agent Registry |

### 20.3 One Source of Truth

| Responsibility | v1.0 Owner | v2.0 Owner |
|---------------|-----------|-------------|
| Provider registration | ProviderManager + Phase1 Registry | OmniRoute ProviderRegistry |
| Model catalog | ModelManager | OmniRoute ModelRegistry |
| Routing decisions | ProviderRouter | OmniRoute RouterEngine |
| Cost tracking | CostTracker | OmniRoute BudgetEngine |
| Rate limiting | RateLimitMonitor | OmniRoute (Redis-backed) |
| Provider health | ProviderHealthMonitor | OmniRoute + CircuitBreaker |
| Provider failover | ProviderRouter.failover() | OmniRoute FailoverEngine |
| API keys | ApiKeyVault | ApiKeyVault (no change) |
| Secrets | EncryptedSecretStore | EncryptedSecretStore (no change) |
| Runtime discovery | DiscoveryEngine (runtime/) | DiscoveryFramework (unified) |
| Provider discovery | (none) | DiscoveryFramework (unified) |
| Model discovery | (none) | DiscoveryFramework (unified) |
| MCP discovery | (none) | DiscoveryFramework (unified) |
| Self-healing | SelfHealingEngine | SelfHealingEngine v2 |
| Health monitoring | HealthMonitor | HealthMonitor v2 |
| Task recovery | RecoveryManager | RecoveryManager v2 |
| Mission storage | In-memory _missions dict | MissionStore (persistent) |
| Workflow storage | In-memory | WorkflowStore (persistent) |
| Pipeline storage | In-memory | PipelineStore (persistent) |
| Learning telemetry | In-memory stubs | TelemetryStore (persistent) |
| Event persistence | None (volatile) | Redis Streams (always-on) |
| Authentication | None | Auth Middleware + Vault |

---

## 21. Implementation Roadmap

### 21.1 Phase Overview

```
Phase 0: Foundation         (Weeks 1-4)    [4 weeks]
Phase 1: OmniRoute Core     (Weeks 5-8)    [4 weeks]
Phase 2: Discovery v2       (Weeks 9-12)   [4 weeks]
Phase 3: Persistence        (Weeks 13-16)  [4 weeks]
Phase 4: Self-Healing v2    (Weeks 17-19)  [3 weeks]
Phase 5: AI Brain           (Weeks 20-24)  [5 weeks]
Phase 6: Desktop v2         (Weeks 25-32)  [8 weeks]  <- LARGEST
Phase 7: Installer & CI/CD  (Weeks 33-36)  [4 weeks]
Phase 8: API Gateway v2     (Weeks 37-40)  [4 weeks]
Phase 9: Polish & Release   (Weeks 41-48)  [8 weeks]
                                WALL TIME: ~48 weeks (12 months)
```

### 21.2 Phase 0: Foundation (Weeks 1-4)

**Objectives:** Lay the architectural groundwork. Extract port protocols. Fix critical bugs.

**Deliverables:**
- [ ] Typed Container DI with lifecycle phases (Phase.CRITICAL through Phase.ADVANCED)
- [ ] Platform dataclass auto-generated from Container registry
- [ ] Phase-based startup/shutdown with LifecycleHook support
- [ ] Container.register() API for all existing subsystems (no functional changes)
- [ ] Fix 3 dead imports in SelfHealingEngine (type:ignore lines)
- [ ] Fix uninitialized DesktopLogging._logs field
- [ ] Fix DesktopRuntimeManager <-> DesktopHardening circular import
- [ ] Add asyncio.Lock to SelfHealingEngine._issues
- [ ] EventBus v2: Add EventFilter, wildcard subscription support
- [ ] EventBus v2: Add publish_many() for batch publishing
- [ ] EventBus v2: Add get_stats() with p50/p95/p99 latency
- [ ] Port protocols: Add OmniRouteProviderRegistryPort, OmniRouteRouterPort
- [ ] Port protocols: Add ModelRegistryPort, BudgetEnginePort

**Risks:** Container DI may expose hidden dependency cycles. Need thorough testing.
**Dependencies:** None (foundation phase)
**Complexity:** Medium (3-4 engineers)
**Regression Risk:** LOW - adding abstractions without changing behavior

### 21.3 Phase 1: OmniRoute Core (Weeks 5-8)

**Objectives:** Build OmniRoute as a real routing engine. Move provider management into OmniRoute.

**Deliverables:**
- [ ] src/agentic_os/core/omniroute/ directory structure
- [ ] OmniRouteProviderRegistry: provider CRUD, config, health cache
- [ ] ModelRegistry: model metadata, capability mapping, pricing tables
- [ ] RouterEngine: capability-based filtering, health/rate/budget filtering, scoring
- [ ] RoutingPolicy base + LatencyRoutingPolicy + CostRoutingPolicy + RoundRobinRoutingPolicy
- [ ] HybridRoutingPolicy: latency (60%) + cost (40%) weighted scoring
- [ ] FailoverEngine: fallback chain, retry with exponential backoff
- [ ] CircuitBreaker: closed/half-open/open, configurable thresholds
- [ ] CompressionEngine: prompt compression, context optimization
- [ ] OmniRouteTelemetry: latency/tokens/cost recording
- [ ] BudgetEngine: spend tracking, alerts, projections
- [ ] GatewayAdapter base + OpenAI-compatible adapter + Anthropic-compatible adapter
- [ ] ReasoningRouter: reasoning-effort to provider mapping
- [ ] VisionRouter: multimodal-capable provider selection
- [ ] ToolRouter: tool type to provider capability mapping
- [ ] 20 OmniRoute REST API endpoints (real, not stubs)
- [ ] Migrate ProviderRouter -> OmniRoute RouterEngine (backward compat wrapper)
- [ ] Migrate CostTracker -> OmniRoute BudgetEngine
- [ ] Migrate RateLimitMonitor -> OmniRoute (Redis-backed)
- [ ] Migrate ProviderHealth -> OmniRoute CircuitBreaker

**Risks:** Existing code depends on old ProviderRouter API. Wrappers needed.
**Dependencies:** Phase 0 (Container, Ports)
**Complexity:** HIGH (4-5 engineers)
**Regression Risk:** HIGH - routing decisions change. Backward compat wrappers required.

### 21.4 Phase 2: Discovery v2 (Weeks 9-12)

**Objectives:** Unify Runtime Discovery and Discovery Framework. Add model/MCP discovery.

**Deliverables:**
- [ ] Merge DiscoveryEngine (runtime/) into DiscoveryFramework (discovery/)
- [ ] Add ModelDiscovery: discover models from provider API responses
- [ ] Add MCPDiscovery: discover MCP servers from config, install dirs
- [ ] Add PluginDiscovery: discover installed plugins
- [ ] Add CloudProviderDiscovery: discover configured cloud providers
- [ ] Persistent DiscoveryCache (SQLite-backed, LRU + TTL)
- [ ] WebSocket push for real-time discovery updates
- [ ] Discovery telemetry: scan stats, hit rate, latency
- [ ] Expand discovery REST API from 17 to 25 endpoints
- [ ] Integration: found items auto-register in OmniRoute ProviderRegistry

**Risks:** Merging two engines may break existing discovery consumers.
**Dependencies:** Phase 0 (Container), Phase 1 (OmniRoute ProviderRegistry for auto-registration)
**Complexity:** MEDIUM (2-3 engineers)
**Regression Risk:** MEDIUM

### 21.5 Phase 3: Persistence (Weeks 13-16)

**Objectives:** Replace all in-memory state with persistent stores.

**Deliverables:**
- [ ] Store[T] port protocol (generic CRUD + query)
- [ ] SQLiteStore implementation (default for local)
- [ ] PostgreSQLStore implementation (for server/multi-tenant)
- [ ] RedisStore implementation (for cache/queue)
- [ ] MissionStore: persistent missions, plans, tasks, history
- [ ] WorkflowStore: persistent workflow definitions, executions
- [ ] PipelineStore: persistent pipeline definitions, executions
- [ ] HealthStore: persistent health checks, status history
- [ ] IssueStore: persistent healing issues, resolutions
- [ ] TelemetryStore: persistent execution telemetry (AI Brain)
- [ ] Schema migration runner (Alembic-style)
- [ ] ConfigStore: persistent configuration (replaces in-memory)

**Risks:** Schema design must support both SQLite and PostgreSQL equally.
**Dependencies:** Phase 0 (Container)
**Complexity:** HIGH (3-4 engineers)
**Regression Risk:** HIGH - state becomes persistent. Need migration from in-memory.

### 21.6 Phase 4: Self-Healing v2 (Weeks 17-19)

**Objectives:** Rewrite SelfHealingEngine. Add circuit breaker integration.

**Deliverables:**
- [ ] SelfHealingEngine v2 (clean room rewrite)
- [ ] Port-based healing actions (instead of hardcoded _repair_ methods)
- [ ] Healing Action: websocket_reconnect (uses EventBus.stop/start)
- [ ] Healing Action: rebuild_cache (uses DiscoveryCache.clear())
- [ ] Healing Action: restart_provider (uses OmniRoute reregister)
- [ ] Healing Action: circuit_breaker_trip (opens circuit)
- [ ] Healing Action: circuit_breaker_half_open (tests recovery)
- [ ] Healing Action: omniroute_failover (fails over via OmniRoute)
- [ ] Healing Action: kill_zombie_task (force-kill hung task)
- [ ] CircuitBreaker integration: feed failover decisions
- [ ] Persistent IssueStore (from Phase 3)
- [ ] Healing telemetry: what healed, what failed, trends
- [ ] AI Brain integration: resolution patterns fed to learning

**Risks:** Clean room rewrite must handle ALL edge cases from v1.0.
**Dependencies:** Phase 1 (OmniRoute for failover), Phase 3 (IssueStore)
**Complexity:** MEDIUM (2 engineers)
**Regression Risk:** MEDIUM - must preserve all existing healing workflows.

### 21.7 Phase 5: AI Brain (Weeks 20-24)

**Objectives:** Replace all learning stubs with real EventBus consumers and persistent telemetry.

**Deliverables:**
- [ ] EventBus consumer for ALL execution events (ingestion layer)
- [ ] Real TelemetryStore writes at scale
- [ ] Knowledge Graph in Vector DB (persistent, not in-memory)
- [ ] Provider Profiles: real performance, cost, reliability data
- [ ] Optimization Engine: routing optimization based on real data
- [ ] Recommendation Engine: provider, model, cost recommendations
- [ ] Cost Optimization: budget-aware provider selection suggestions
- [ ] Performance Optimization: latency optimization suggestions
- [ ] Benchmark Engine: real benchmarks against execution history
- [ ] Experiment Manager: A/B test routing policies in production
- [ ] Dashboard: real-time learning dashboard (not stubs)

**Risks:** Scale - EventBus consumer must handle peak throughput without falling behind.
**Dependencies:** Phase 1 (OmniRoute Telemetry), Phase 3 (TelemetryStore)
**Complexity:** VERY HIGH (4-5 engineers)
**Regression Risk:** LOW - new functionality, existing code unchanged.

### 21.8 Phase 6: Desktop v2 (Weeks 25-32) [LARGEST]

**Objectives:** Extract 27 port protocols. Implement Rust/Tauri native layer.

**Deliverables:**
- [ ] 27 port protocols for all desktop subsystems
- [ ] IPC Bridge: Rust <-> Python JSON-RPC over stdin/stdout
- [ ] WindowManagerPort + Rust implementation (Tauri window)
- [ ] ProcessManagerPort + Rust implementation
- [ ] ClipboardPort + Rust implementation
- [ ] TerminalPort + Rust implementation
- [ ] FileDialogPort + Rust implementation
- [ ] NotificationPort + Rust implementation
- [ ] MenuPort + Rust implementation
- [ ] DragDropPort + Rust implementation
- [ ] DatabasePort + Rust implementation (SQLite via rusqlite)
- [ ] SystemMetricsPort + Rust implementation (sysinfo crate)
- [ ] AutoUpdaterPort + Rust implementation
- [ ] CrashReporterPort + Rust implementation (Sentry)
- [ ] CodeSigningPort + Rust implementation (signing verify)
- [ ] DesktopRuntimeManager: composition of all Rust services
- [ ] GPU rendering: WebView2 hardware acceleration
- [ ] System tray: native system tray with status/quick commands
- [ ] First-run wizard: Tauri window with welcome flow
- [ ] Break DesktopHardeningManager into focused port implementations
- [ ] Keyboard shortcuts: global hotkey registration

**Risks:** LARGEST PHASE. Rust team requires separate expertise. Python<Rust IPC must be robust.
**Dependencies:** Phase 0 (Port Protocols), Phase 1 (OmniRoute - embedded in Desktop)
**Complexity:** VERY HIGH (4-5 Rust engineers + 2 Python engineers)
**Regression Risk:** MEDIUM - the Python layer must continue working during transition.

### 21.9 Phase 7: Installer & CI/CD (Weeks 33-36)

**Objectives:** Build all platform installers. Automate CI/CD.

**Deliverables:**
- [ ] MSI installer (WiX toolset)
- [ ] NSIS portable installer
- [ ] AppImage Linux installer
- [ ] Deb Linux installer
- [ ] RPM Linux installer
- [ ] DMG macOS installer
- [ ] Installer test suite (test all formats on all platforms)
- [ ] GitHub Actions CI/CD pipeline
- [ ] Auto-updater integration with GitHub Releases
- [ ] Code signing (Windows Authenticode, macOS notarize)
- [ ] Release channel management (Nightly/Beta/RC/Stable)
- [ ] Version numbering scheme (SemVer + CalVer)

**Risks:** Each platform has unique packaging quirks. CI runners needed per platform.
**Dependencies:** Phase 6 (Desktop v2 binary to package)
**Complexity:** MEDIUM (2 DevOps + 2 engineers)
**Regression Risk:** LOW - packaging changes only.

### 21.10 Phase 8: API Gateway v2 (Weeks 37-40)

**Objectives:** Refactor 3926-line app.py into modular routers. Add auth.

**Deliverables:**
- [ ] Auth middleware (JWT validation + API key auth + OAuth2)
- [ ] RBAC middleware (role resolution + permission check)
- [ ] Rate limiting middleware (sliding window, per-key)
- [ ] Split app.py into:
  - api/routers/tasks.py
  - api/routers/providers.py
  - api/routers/missions.py
  - api/routers/omniroute.py
  - api/routers/discovery.py
  - api/routers/mcp.py
  - api/routers/swarm.py
  - api/routers/learning.py
  - api/routers/desktop.py
  - api/routers/prompts.py
  - api/routers/workflows.py
  - api/routers/pipelines.py
  - api/routers/security.py
  - api/routers/diagnostics.py
  - api/routers/plugins.py
  - api/routers/memory.py
- [ ] WebSocket auth with JWT token validation
- [ ] Anthropic-compatible /v1/messages and /v1/stream endpoints
- [ ] A2A gateway: /a2a/* endpoints for agent-to-agent
- [ ] MCP gateway: /mcp/* endpoints for external MCP clients
- [ ] API versioning: deprecation headers
- [ ] OpenAPI docs with auth
- [ ] Remove 503 sentinel pattern (use health check instead)

**Risks:** Refactoring 3926-line file is risky. Must maintain exact backward compatibility.
**Dependencies:** Phase 0 (Container), Phase 1 (OmniRoute for gateway adapters)
**Complexity:** MEDIUM (2 engineers)
**Regression Risk:** HIGH - all 396 endpoints must behave identically.

### 21.11 Phase 9: Polish & Release (Weeks 41-48)

**Objectives:** Stabilization, security audit, performance testing, documentation.

**Deliverables:**
- [ ] End-to-end test suite (Playwright, full workflow coverage)
- [ ] Performance testing: startup time, throughput, latency
- [ ] Security audit (third-party)
- [ ] Penetration testing
- [ ] Documentation: architecture, API, user guide
- [ ] Migration guide: v1.0 to v2.0
- [ ] Release notes
- [ ] Marketing site updates
- [ ] Community outreach
- [ ] Performance optimization (profile hotspots)
- [ ] Memory leak testing (24h+ runs)
- [ ] Stress testing (1000+ concurrent missions)
- [ ] Upgrade testing (v1.0 -> v2.0 with existing configs)

**Risks:** Showstopper bugs may delay release.
**Dependencies:** ALL phases complete
**Complexity:** MEDIUM (2-3 engineers + QA team)
**Regression Risk:** HIGH - final validation must be exhaustive.

---

## 22. Architecture Decision Records

### ADR-001: OmniRoute as the Single Routing Authority

**Context:** The v1.0 codebase has routing logic scattered across ProviderRouter, ProviderManager, ModelManager, CostTracker, and RateLimitMonitor. Multiple components make independent routing decisions, leading to inconsistent provider selection and duplicated logic.

**Decision:** OmniRoute becomes the single routing authority. No other component may make provider routing decisions. All provider selection, failover, cost tracking, rate limiting, and telemetry must flow through OmniRoute.

**Alternatives Considered:**
1. *Keep existing split* - Leads to continued inconsistency and duplicated logic
2. *Centralized in API Gateway* - Violates separation of concerns; gateway should route HTTP, not AI providers
3. *Distributed with OmniRoute as coordinator* - Adds complexity without clear benefit

**Consequences:**
- Positive: Single path for all routing decisions; consistent policy enforcement; unified telemetry
- Positive: New providers added once in OmniRoute; all consumers benefit immediately
- Negative: OmniRoute becomes a bottleneck if not properly scaled
- Negative: All existing routing code must be migrated (backward compat wrappers needed)

**Risks:** OmniRoute must handle peak throughput. Mitigation: async design, Redis-backed state.
**Future Evolution:** OmniRoute may be extracted as standalone service for multi-process deployments.

### ADR-002: Typed Dependency Injection Container

**Context:** The v1.0 kernel manually constructs 30+ subsystems in strict dependency order. Adding a new subsystem requires editing the constructor. Subsystem startup is monolithic and fragile.

**Decision:** Replace manual construction with a typed Container that manages dependency resolution, lifecycle phases, and health aggregation.

**Alternatives Considered:**
1. *Manual construction (v1.0 style)* - Brittle, doesn't scale, no lifecycle management
2. *Third-party DI framework* - Adds external dependency; Python DI frameworks are not type-safe
3. *Lazy singleton pattern per module* - Global state, testability issues

**Consequences:**
- Positive: Subsystems register themselves; Container resolves dependency graph
- Positive: Phase-based startup enables faster critical path
- Positive: Automatic health aggregation
- Negative: Internal complexity of Container implementation
- Negative: Learning curve for engineers

**Risks:** Container may hide dependency cycles until runtime. Mitigation: startup validation with cycle detection.
**Future Evolution:** Container could be serialized for hot-reload of subsystem configurations.

### ADR-003: Runtime Discovery as Single Source of Truth

**Context:** The v1.0 codebase has two overlapping discovery engines (RuntimeEngine in core/runtime/ and DiscoveryFramework in core/discovery/). Both find runtimes but with different registries and cache strategies.

**Decision:** Merge both into a single DiscoveryFramework that serves as the ONLY source of truth for all discovered entities: runtimes, providers, models, MCP servers, capabilities, executables, and plugins.

**Alternatives Considered:**
1. *Keep two engines* - Duplication, inconsistent results, no clear owner
2. *Runtime Discovery owns everything* - DiscoveryFramework has richer features (validation pipeline, profiling, hot-reload)
3. *External discovery service* - Premature for v2.0; adds network dependency

**Consequences:**
- Positive: Single registration point for all discovered entities
- Positive: Unified cache, validation, telemetry
- Positive: Auto-registration in OmniRoute ProviderRegistry
- Negative: Must migrate all consumers to new API

**Risks:** Merging two active registries may lose in-flight discovery state. Mitigation: dual-read during migration.
**Future Evolution:** DiscoveryFramework could be distributed via Redis pub/sub.

### ADR-004: Persistence Through Port Protocols

**Context:** The v1.0 codebase stores ALL core state in-memory dicts. Nothing survives restart. The only persistence is the Fernet-encrypted vault and SQLite for desktop state.

**Decision:** Every subsystem that maintains state must use a Store[T] port protocol backed by a persistent implementation. SQLite for local/single-user, PostgreSQL for multi-user/server deployments.

**Alternatives Considered:**
1. *Keep in-memory* - Features lost on restart; no production-readiness
2. *Single MongoDB dependency* - Not portable; adds heavy dependency
3. *SQLite only* - Doesn't scale to server deployments

**Consequences:**
- Positive: State survives restart; production-ready
- Positive: SQLite suitable for desktop/embedded; PostgreSQL for server
- Positive: Port protocol allows future storage backends
- Negative: Storage must be designed for both SQLite and PostgreSQL compatibility
- Negative: Migration from in-memory to persistent is high effort

**Risks:** Performance overhead compared to in-memory dicts. Mitigation: Redis caching layer for hot paths.
**Future Evolution:** Add read replicas, sharding for multi-tenant deployments.

### ADR-005: Desktop Subsystems as Port Protocols with Rust Implementation

**Context:** The v1.0 desktop layer has 27 concrete classes with zero port abstractions. Most implementations are in-memory stubs. DesktopRuntimeManager is a god object with 27 fields.

**Decision:** Extract 27 port protocols for all desktop subsystems. Implement each port first in Python (preserving backward compatibility), then in Rust/Tauri. IPC bridge connects Rust and Python layers.

**Alternatives Considered:**
1. *Keep pure Python* - Cannot access native OS APIs reliably; no Tauri integration
2. *Full Rust rewrite* - Too risky; losing existing Python desktop functionality
3. *IPC bridge with gradual migration* - Best balance of risk and progress

**Consequences:**
- Positive: Rust implementations are real (process, window, clipboard, etc.)
- Positive: Python layer continues working during transition
- Positive: Port protocols enable testing with mock implementations
- Negative: IPC bridge adds latency vs direct Rust calls
- Negative: Requires Rust expertise in the team

**Risks:** IPC protocol design must handle all data types correctly. Mitigation: JSON-RPC with comprehensive test suite.
**Future Evolution:** Desktop could run without Python backend for simple operations.

### ADR-006: EventBus with Always-On Persistence

**Context:** The v1.0 EventBus has no persistence. Redis Streams XADD stores events but they're not replayed for recovery. All events are fire-and-forget.

**Decision:** EventBus v2 always persists events through the transport layer (Redis Streams XADD or NATS JetStream). Replay engine allows re-consuming events from any point. Dead letter queue captures failed event processing.

**Alternatives Considered:**
1. *In-memory only (v1.0 style)* - No recovery, no replay, no audit
2. *Separate event store* - Adds consistency complexity (dual-write problem)
3. *Always-on persistence in transport* - Uses existing Redis/NATS durability guarantees

**Consequences:**
- Positive: Events survive restarts; replay for recovery
- Positive: Dead letter queue for debugging failed handlers
- Positive: Telemetry for event latency and throughput
- Negative: Storage growth over time (mitigation: TTL + compaction)
- Negative: Slight latency increase for XADD vs in-memory publish

**Risks:** Redis memory usage. Mitigation: stream trimming (MAXLEN), TTL policies.
**Future Evolution:** Event sourcing for complete system state reconstruction.

### ADR-007: Self-Healing with Circuit Breaker Pattern

**Context:** The v1.0 SelfHealingEngine has dead imports, unbounded lists, no state protection, and no connection to the outside world. It can only react to events it knows about.

**Decision:** Rewrite SelfHealingEngine v2 with clean port-based architecture. Add CircuitBreaker pattern for provider/endpoint health. Circuit breaker feeds into OmniRoute failover decisions.

**Alternatives Considered:**
1. *Patch v1.0* - Too many fundamental issues (dead code, no locking, no persistence)
2. *External health service* - Premature for v2.0
3. *Clean rewrite with circuit breaker* - Best foundation for growth

**Consequences:**
- Positive: All healing actions work correctly (no dead imports)
- Positive: Circuit breaker prevents cascading failures
- Positive: Persistent issue log for diagnostics and learning
- Negative: Must re-validate all healing workflows

**Risks:** Circuit breaker false positives could reduce throughput. Mitigation: configurable thresholds, half-open testing.
**Future Evolution:** Predictive healing based on AI Brain telemetry trends.

---

## 23. Non-Regression Requirements

### 23.1 Mandatory Preservation

The following MUST work identically in v2.0 as in v1.0.0-rc1:

**ALL EXISTING API ENDPOINTS (396)**
- Same URL paths
- Same request/response schemas
- Same HTTP status codes
- Same error messages
- Same headers

**ALL EXISTING EVENT TOPICS (260+)**
- Same topic names
- Same payload structures
- Same delivery semantics (at-least-once for Redis/NATS)

**ALL EXISTING UI PAGES (26+ Mission Control views)**
- Same layout and navigation
- Same cards and animations
- Same particles and glow effects
- Same color palette and typography
- Same responsive behavior

**ALL EXISTING USER WORKFLOWS**
- Task creation and execution
- Mission planning and execution
- Provider configuration
- MCP server registration
- Plugin installation
- System monitoring
- Desktop operations

### 23.2 Backward Compatibility Guarantee

| Compatibility Level | Requirement |
|--------------------|-------------|
| API | ALL v1.0 endpoints available in v2.0; deprecated endpoints warn via header |
| EventBus | ALL v1.0 topic names valid; new topics added only |
| Configuration | v1.0 config files load without errors in v2.0 |
| Plugin API | v1.0 plugins run in v2.0 without modification |
| Database | v1.0 SQLite schemas migrated to v2.0 automatically |
| WebSocket | v1.0 WebSocket clients connect to v2.0 without modification |
| CLI | v1.0 CLI commands work in v2.0 |

### 23.3 Performance Targets (v2.0 vs v1.0)

| Metric | v1.0 Baseline | v2.0 Target | Measurement |
|--------|--------------|-------------|-------------|
| Startup to listening | <1s | <1s | Time from run_serve() to uvicorn listen |
| Full startup | ~3s | <3s | Time to all subsystems ready |
| EventBus publish latency | 5-15ms | <10ms p50 | P99 <50ms |
| API response (no AI) | <50ms | <50ms | P95 for cache-hit endpoints |
| Route selection | <10ms | <10ms | P50 for OmniRoute select() |
| WebSocket event latency | 5-20ms | <15ms | P50 from publish to dashboard receive |
| Provider discovery scan | 2-10s | <5s | Complete scan with 10+ providers |
| Concurrent active missions | ~20 | 100+ | Without resource contention |

### 23.4 Zero-Tolerance Regressions

The following are NOT ACCEPTABLE in v2.0:
- Any existing API endpoint returning 404, 500, or incorrect data
- Any existing dashboard page failing to load
- Any existing animation or visual effect disappearing
- Any existing user workflow becoming slower by >2x
- Any existing configuration file failing to parse
- Any existing plugin failing to load
- Any existing WebSocket connection failing to establish
- Any existing CLI command changing behavior

### 23.5 Validation Strategy

```
PRE-RELEASE VALIDATION:
1. Automated test suite (100% pass required):
   - Unit: 80%+ coverage, all critical paths
   - Integration: All API endpoints, all EventBus topics, all WebSocket paths
   - E2E: Playwright tests for all 26+ dashboard views
   - Compatibility: v1.0 config loaded, plugins loaded, migrations run

2. Manual verification (QA team):
   - Visual regression testing (all pages)
   - Workflow regression testing (all user flows)
   - Performance benchmarking (all metrics above)
   - Edge case testing (error states, recovery paths)

3. Staged rollout:
   - Phase A: Internal dogfood (2 weeks)
   - Phase B: Beta channel (2 weeks, opt-in users)
   - Phase C: RC channel (2 weeks, early adopters)
   - Phase D: Stable (gradual rollout, 25% -> 50% -> 100%)

4. Rollback plan:
   - If P0 bug detected: rollback within 1 hour
   - Installer preserves previous version for instant rollback
   - Database migrations reversible (down-migration scripts)
```

---

*End of Phase E — System Transformation Blueprint*
*Prepared for: AgenticOS v2.0 Architecture Design Review*
*Status: Architecture & Design Phase — No implementation, no refactoring, no feature removal*

