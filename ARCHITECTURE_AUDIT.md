# AgenticOS v1.0.0-rc1 — Complete Architecture Audit

> **Pre-OmniRoute Integration Blueprint**
> Prepared for senior software engineering design review.
> Analysis-only phase — no implementation, no refactoring, no code modification.

---

## Table of Contents

1. [Overall Architecture](#1-overall-architecture)
2. [Request Lifecycle](#2-request-lifecycle)
3. [Mission Orchestrator](#3-mission-orchestrator)
4. [Runtime Discovery Engine](#4-runtime-discovery-engine)
5. [Provider Registry & Routing](#5-provider-registry--routing)
6. [Execution Engine Framework](#6-execution-engine-framework)
7. [AI Brain (Learning & Optimization)](#7-ai-brain-learning--optimization)
8. [Agent Constellation (Orchestration & Swarm Intelligence)](#8-agent-constellation-orchestration--swarm-intelligence)
9. [Prompt Center](#9-prompt-center)
10. [Diagnostics & Self-Healing](#10-diagnostics--self-healing)
11. [EventBus Architecture](#11-eventbus-architecture)
12. [WebSocket Architecture](#12-websocket-architecture)
13. [REST API — Complete Endpoint Inventory](#13-rest-api--complete-endpoint-inventory)
14. [Database & Persistence](#14-database--persistence)
15. [Plugin System](#15-plugin-system)
16. [MCP (Model Context Protocol) Framework](#16-mcp-model-context-protocol-framework)
17. [Swarm Orchestration Engine](#17-swarm-orchestration-engine)
18. [Desktop Runtime & Installer](#18-desktop-runtime--installer)
19. [Technical Debt Analysis](#19-technical-debt-analysis)
20. [OmniRoute Readiness Assessment](#20-omniroute-readiness-assessment)

---

## 1. Overall Architecture

### 1.1 Architecture Style

AgenticOS uses **Hexagonal (Clean) Architecture** with a **layered onion** structure:

```
┌─────────────────────────────────────────────────────────────────────┐
│                        API Layer (FastAPI)                           │
│  app.py (3926 loc), gateway.py, dashboard.py                         │
│  396 endpoints in 20+ groups                                          │
├─────────────────────────────────────────────────────────────────────┤
│                     Composition Root (kernel.py)                      │
│  Kernel class → constructs 30+ subsystems → bundles → Platform       │
│  This is the ONLY place that knows about concrete implementations     │
├─────────────────────────────────────────────────────────────────────┤
│                        Core Layer                                     │
│  │                                                                    │
│  ├── Orchestration (framework.py, planner.py, scheduler.py, ...)      │
│  ├── MCP (registry.py, manager.py, client.py, pool.py, ...)          │
│  ├── Providers (manager.py, router.py, routing.py, vault.py, ...)    │
│  ├── Runtime (manager.py, engine.py, registry.py, discovery.py, ...) │
│  ├── Discovery (framework.py, cache.py, validation.py, ...)          │
│  ├── Learning (manager.py, benchmark.py, optimization.py, ...)       │
│  ├── Desktop (manager.py, +28 subsystem modules)                     │
│  ├── Memory (manager.py, lifecycle.py)                                │
│  ├── Security (framework.py)                                          │
│  ├── Plugin (registry.py, loader.py)                                  │
│  ├── Self-Healing (self_healing.py, health.py, recovery.py)           │
│  └── Observability (metrics.py, logging.py, tracing.py, otel.py)     │
├─────────────────────────────────────────────────────────────────────┤
│                        Port Layer (Protocols)                         │
│  event_bus.py, execution.py, orchestration.py, mcp.py, memory.py,    │
│  provider_management.py, provider.py, plugin.py, security.py,        │
│  learning.py, capability.py, observability.py                         │
│  18 protocol files defining ~30 Port interfaces                       │
├─────────────────────────────────────────────────────────────────────┤
│                        Adapter Layer                                   │
│  │                                                                    │
│  ├── Bus: local.py (asyncio), redis_streams.py, nats_jetstream.py    │
│  ├── Discovery: path, choco, npm, cargo, uv, winget, scoop,          │
│  │             docker, wsl, vscode, jetbrains, registry, etc.        │
│  ├── Memory: in_memory.py (vector, graph, kv)                        │
│  ├── Security: encrypted_store.py (Fernet AES-128-GCM)               │
│  ├── Engines: generic.py                                              │
│  └── Plugins: loader.py, builtins.py                                  │
├─────────────────────────────────────────────────────────────────────┤
│                        Domain Layer (Pure Python)                     │
│  events.py (260+ topics), agent.py, mission.py, orchestration.py,    │
│  mcp.py, workflow.py, pipeline.py, learning.py, provider_mgmt.py,    │
│  discovery.py, execution.py, memory.py, security.py, desktop.py      │
│  ~5000 lines total — all Pydantic or frozen dataclasses               │
└─────────────────────────────────────────────────────────────────────┘
```

### 1.2 Kernel Composition Root

**File**: `src/agentic_os/kernel.py` (~720 lines)

The `Kernel.__init__()` constructs subsystems in strict dependency order:

```
Constructor Order (30+ subsystems):
 1. EventBus (from factory by bus_type config)
 2. AgentRegistry + ProviderRegistry  (Phase 1)
 3. Scheduler
 4. ProviderManagerImpl + ModelManagerImpl  (Phase 2)
 5. EncryptedSecretStore + ApiKeyVaultImpl
 6. ProviderHealthMonitorImpl
 7. CostTrackerImpl + RateLimitMonitorImpl
 8. Router (wires manager + health + models + rate + failover)
 9. MemoryManagerImpl (in-memory store + vector + graph)
10. SecurityFramework (RBAC + workspace isolation + approval + audit)
11. WorkflowEngineImpl + PipelineEngineImpl (Phase 3B)
12. Orchestrator + HealthMonitor + RecoveryManager
13. DashboardBroadcaster + MCPBroadcaster
14. CapabilityEngine
15. MissionPlannerImpl
16. RuntimeManager + Registry + DiscoveryEngine + Negotiator (Phase 4 M1)
17. DiscoveryFramework (Phase 4 M2) — _build_discovery_framework()
18. InstallerIntelligence (Phase 4 M3)
19. OrchestrationFramework (Phase 4 M3) — _build_orchestration_framework()
20. MCPManager + MCPRegistryImpl (Phase 4 M3) — _build_mcp_framework()
21. LearningManager (Phase 5) — _build_learning_framework()
22. DesktopRuntimeManager (Phase 4 M6)
```

**Container**: `Platform` dataclass — the single object the API layer receives. Contains 19 mandatory fields + 9 optional `| None` fields.

### 1.3 Startup Sequence

```
run_serve(host, port)
  │
  ├─ Kernel()                                          ~0ms  (sync constructor)
  │   ├─ _ensure_env()                                  ~2ms  (optional .env generation)
  │   ├─ build_bus(settings) → EventBus adapter         ~5ms
  │   └─ __init__ contructs 30+ subsystems              ~50ms (all sync)
  │
  ├─ _build_app(kernel) → FastAPI app                    ~100ms
  │
  └─ kernel._start_critical()                            ~200ms
      │
      ├─ EventBus.start()  [SYNCHRONOUS]                 ~50ms  (Redis/NATS connect)
      │
      └─ asyncio.create_task(_bg_start)                  ~1ms   (BACKGROUND)
          │
          ├─ Plugins loading                             ~200ms
          ├─ Provider seeding (default models)           ~10ms
          ├─ Orchestrator.start()                        ~100ms
          ├─ Scheduler.start()                           ~10ms
          ├─ Health.start()                              ~10ms
          ├─ Recovery.start()                            ~10ms
          ├─ ProviderHealth.start()                      ~10ms
          ├─ Capability.start()                          ~10ms
          ├─ Dashboard.start() (subscribes 96 topics)    ~20ms
          ├─ MCP-WS.start()                              ~10ms
          ├─ Runtime.initialize()                        ~500ms (discovery)
          ├─ Discovery.start_auto_discovery()             ~200ms
          ├─ Installer (background task)                  ~500ms
          ├─ Orchestration.start()                       ~100ms
          ├─ MCP.start()                                 ~100ms
          ├─ Learning.start()                            ~50ms
          └─ Desktop.start()                             ~200ms (if enabled)
          │
          └─ TOTAL BACKGROUND: ~1.5-3s  (API serves immediately)
```

**Key design decision**: EventBus starts **synchronously** before uvicorn listen. ALL other subsystems initialize as background tasks. This means the API server starts listening in <1 second, but many endpoints return 503 until their subsystem finishes loading.

### 1.4 Shutdown Sequence

```
stop()
  └─ Reverse order of start:
      Desktop.stop() → Learning.stop() → MCP.shutdown() → Orchestration.stop()
      → Discovery.stop_hot_reload/stop_auto_discovery → Runtime.shutdown()
      → Dashboard.stop() → MCP-WS.stop() → Recovery.stop() → Health.stop()
      → ProviderHealth.stop() → Scheduler.stop() → Orchestrator.stop() → Bus.stop()
```

### 1.5 File Map (src/agentic_os/)

```
agentic_os/
├── kernel.py                   # Composition root (720 lines)
├── config.py                   # pydantic-settings (12-factor)
├── cli.py                      # argparse entrypoint
├── domain/                     # ~5000 lines total
│   ├── events.py               # EventEnvelope + Topic (260+)
│   ├── agent.py                # Agent, Task, Role, ProviderInfo
│   ├── mission.py              # Mission, MissionPlan, AgentRole
│   ├── orchestration.py        # SwarmSpec, AgentTask, Voting, Consensus (400+)
│   ├── mcp.py                  # MCPTool, MCPServerConfig, MCPSession (629)
│   ├── workflow.py             # WorkflowNode, WorkflowEdge, Workflow
│   ├── pipeline.py             # PipelineStage, PipelineEdge, Pipeline
│   ├── learning.py             # LearningProfile, ExecutionHistory, etc.
│   ├── provider_mgmt.py        # ProviderConfig, CostRecord
│   ├── discovery.py            # DiscoveryProfile, DiscoveryResult
│   ├── execution.py            # ExecutionEngine, ExecutionResult
│   ├── memory.py               # MemoryItem, MemoryScope
│   ├── security.py             # Principal, Role, AuthDecision
│   └── desktop.py              # ~80 dataclasses (~1900 lines)
├── ports/                      # 18 Protocol interfaces
│   ├── event_bus.py            # EventBus Protocol (5 methods)
│   ├── execution.py            # ExecutionEnginePort, RuntimeManagerPort
│   ├── orchestration.py        # 6+ Protocols (Planner, Scheduler, etc.)
│   ├── mcp.py                  # MCPRegistryPort + DTOs
│   ├── memory.py               # MemoryStore, VectorStore, KnowledgeGraph
│   ├── provider_management.py  # ProviderAdapter, ModelInfo, RoutingPolicy
│   ├── provider.py             # ProviderAdapter base
│   ├── plugin.py               # PluginRegistryPort
│   ├── security.py             # SecretStore, SecurityFramework
│   ├── learning.py             # LearningPort
│   ├── capability.py           # CapabilityPort
│   └── observability.py       # MetricsPort, TracingPort
├── adapters/                   # Concrete implementations
│   ├── bus/
│   │   ├── local.py            # In-memory asyncio bus
│   │   ├── redis_streams.py    # Redis Streams (default production)
│   │   ├── nats_jetstream.py   # NATS JetStream
│   │   └── factory.py          # build_bus() selector
│   ├── discovery/              # 15+ discovery providers
│   ├── memory/
│   │   └── in_memory.py        # Vector store, knowledge graph, KV
│   ├── security/
│   │   └── encrypted_store.py  # Fernet-encrypted secret store
│   ├── engines/
│   │   └── generic.py          # Generic execution engine
│   └── plugins/
│       ├── loader.py           # Plugin sandboxed loader
│       └── builtins.py         # Built-in plugins
├── core/                       # ~15,000+ lines total
│   ├── orchestration/          # Multi-agent orchestration (20+ files)
│   ├── mcp/                    # MCP framework (14 files)
│   ├── providers/              # Provider management (5 files)
│   ├── runtime/                # Execution engine (6 files)
│   ├── discovery/              # Discovery framework (10 files)
│   ├── learning/               # Learning engine (18 files)
│   ├── desktop/                # Desktop runtime (28 files)
│   ├── plugins/                # Plugin lifecycle (2 files)
│   ├── memory/                 # Memory lifecycle (2 files)
│   ├── observability/          # Metrics, tracing, logging (5 files)
│   ├── mission.py              # Mission planner
│   ├── health.py               # Health monitor
│   ├── recovery.py             # Recovery manager
│   └── self_healing.py         # Self-healing engine
├── api/                        # ~4,500 lines total
│   ├── app.py                  # FastAPI app (3926 lines, 396 endpoints)
│   ├── gateway.py              # OpenAI-compatible /v1 gateway
│   ├── dashboard.py            # Dashboard WebSocket broadcaster
│   └── mcp_ws.py               # MCP WebSocket broadcaster
└── infrastructure/
    └── logging.py              # Structured logging (structlog)
```

---

## 2. Request Lifecycle

### 2.1 FastAPI Request → Response Flow

```
HTTP Request
  │
  ├─ CORSMiddleware (localhost:3000, tauri://localhost)
  │
  ├─ Request handler in app.py
  │   │
  │   ├── If subsystem is None → raise HTTPException(503)
  │   │
  │   ├── Parse Pydantic body/params
  │   │
  │   ├── Call core subsystem (e.g., orchestrator.dispatch_task)
  │   │   │
  │   │   ├── Core publishes EventEnvelope to EventBus
  │   │   ├── Subscribers react asynchronously
  │   │   └── Core returns result
  │   │
  │   └── Return Pydantic model as dict
  │
  └─ HTTP Response (JSON)
```

### 2.2 Task Execution Lifecycle

```
POST /api/tasks  (or POST /api/runtime/engines/{id}/execute)
  │
  ├─ Event: task.created  →  Topic.TASK_CREATED
  │
  ├─ Orchestrator.handle_task_created()
  │   ├─ Plans task (MissionPlanner or SwarmPlanner)
  │   ├─ Event: task.planned → Topic.TASK_PLANNED
  │   └─ Dispatches to agent
  │
  ├─ Event: agent.started → Topic.AGENT_STARTED
  │
  ├─ Agent executes via ProviderRouter
  │   ├─ Router.select(capability) → (provider, model)
  │   │   ├─ Policy: latency | cost | round_robin
  │   │   ├─ Rate limit check
  │   │   └─ Health check filter
  │   ├─ Adapter.execute(agent, task) → result
  │   └─ Event: cost.recorded → Topic.COST_RECORDED
  │
  ├─ Event: agent.completed → Topic.AGENT_COMPLETED
  │
  ├─ RecoveryManager: heartbeat timeout check
  │   ├─ Event: health.check → Topic.HEALTH_CHECK
  │   └─ Event: health.degraded → Topic.HEALTH_DEGRADED (on timeout)
  │
  ├─ SelfHealingEngine: on AGENT_FAILED, HEALTH_DEGRADED
  │   ├─ Auto-repair (MEDIUM/LOW severity)
  │   └─ Approval queue (HIGH/CRITICAL severity)
  │
  └─ Event: task.completed → Topic.TASK_COMPLETED
```

### 2.3 OpenAI-Compatible Gateway Flow

```
POST /v1/chat/completions
  │
  ├─ Parse ChatCompletionRequest (model, messages, stream, etc.)
  ├─ _resolve_provider(provider_hint, model) → (provider, model)
  │   ├─ 1. Backend provider API
  │   ├─ 2. Router.select(capability)
  │   └─ 3. Hardcoded fallback (mock provider)
  ├─ Execute via ProviderAdapter (ClaudeCodeProvider, etc.)
  ├─ Stream SSE responses if stream=True
  └─ Return OpenAI-format response
```

### 2.4 EventBus Message Lifecycle (All Communication)

```
Publisher → EventEnvelope → EventBus.publish() → Topic → Subscribers
                                                       │
                                              ┌────────┼────────┐
                                         Dashboard  Core     Logging
                                        (96 topics) (varies) (all)
```

---

## 3. Mission Orchestrator

### 3.1 Architecture

The Mission Planner (`src/agentic_os/core/mission.py`, ~285 lines) is a standalone planner that decomposes high-level user goals into executable task DAGs with role assignments.

```
User Goal
  │
  ├─ MissionPlannerImpl.analyze(goal)
  │   ├─ _estimate_complexity()  (keyword heuristic: 1-5)
  │   ├─ _estimate_risk()        (complexity + priority + deadline)
  │   ├─ _decompose()            → 9 standard tasks with dependency DAG
  │   ├─ _assign_roles()         → role-to-provider mapping
  │   └─ Emit: mission.planned    → Topic.MISSION_PLANNED
  │
  └─ MissionPlan (domain/mission.py)
       ├─ MissionTask[] with dependencies
       ├─ AgentRole assignments
       └─ Risk/complexity metadata
```

### 3.2 Role-to-Provider Mapping

```python
DEFAULT_ROLE_MAP = {
    AgentRole.CHIEF_ARCHITECT:    "claude_code",   # Architecture decisions
    AgentRole.REPOSITORY_AUDITOR: "hermes",         # Code review
    AgentRole.BACKEND_ENGINEER:   "opencode",       # Implementation
    AgentRole.FRONTEND_ENGINEER:  "opencode",       # UI work
    AgentRole.DEVOPS_ENGINEER:    "claude_code",    # Infrastructure
    AgentRole.QA_ENGINEER:        "hermes",         # Testing
    AgentRole.SECURITY_ENGINEER:  "hermes",         # Security audit
    AgentRole.DOCUMENTATION_WRITER: "gemini_cli",   # Documentation
    AgentRole.PROJECT_MANAGER:    "claude_code",    # Planning
    AgentRole.DATA_SCIENTIST:     "hermes",         # Analysis
}
```

### 3.3 Mission Domain Model

```python
class MissionPriority(StrEnum): LOW, MEDIUM, HIGH, CRITICAL
class ExecutionMode(StrEnum): SEQUENTIAL, PARALLEL, HYBRID
class MissionStatus(StrEnum): DRAFT, PLANNING, PLANNED, EXECUTING, PAUSED, COMPLETED, FAILED, CANCELLED
class TaskStatus(StrEnum): PENDING, PLANNED, ASSIGNED, RUNNING, COMPLETED, FAILED, BLOCKED, SKIPPED
class AgentRole(StrEnum): CHIEF_ARCHITECT, REPOSITORY_AUDITOR, BACKEND_ENGINEER, FRONTEND_ENGINEER, DEVOPS_ENGINEER, QA_ENGINEER, SECURITY_ENGINEER, DOCUMENTATION_WRITER, PROJECT_MANAGER, DATA_SCIENTIST, RESEARCHER

Mission: id, title, description, priority, execution_mode, status, plan, created_at, updated_at
MissionPlan: id, mission_id, tasks[MissionTask], dependencies, metadata, risk_score, complexity_score
MissionTask: id, title, description, role, status, assigned_agent, dependencies[], result, error
```

### 3.4 Complexity Estimation

Heuristic scoring based on prompt content keywords:
- **1**: Simple (no keywords)
- **2**: Normal  
- **3**: Medium (multiple, full, complete)
- **4**: Complex (comprehensive, end-to-end)
- **5**: Very complex (complex, large)

### 3.5 Standard 9-Task Decomposition

The `_decompose()` method generates a fixed pipeline:
1. Analysis → 2. Architecture → 3. Implementation Plan → 4. Frontend → 5. Backend → 6. Integration → 7. Testing → 8. Documentation → 9. Review

With a DAG dependency structure allowing parallel execution where possible.

### 3.6 Mission Planner REST API

9 endpoints under `/api/missions/`: CRUD + plan, start, pause, cancel. All in-memory (`_missions` dict).

---

## 4. Runtime Discovery Engine

### 4.1 Architecture

Multi-layer discovery with two engines:

```
Layer 1: DiscoveryEngine  (core/runtime/discovery.py)
  ├─ Pluggable DiscoveryProvider[] (PATH, Choco, NPM, Cargo, etc.)
  ├─ Deduplication (same engine from multiple providers)
  └─ Confidence scoring

Layer 2: DiscoveryFramework  (core/discovery/framework.py)
  ├─ DiscoveryRegistry (named providers with configs)
  ├─ DiscoveryCache (TTL-based, max entries)
  ├─ ValidationPipeline (executable, version, capability, permission)
  ├─ ProfilingEngine (latency, resource footprint)
  ├─ DiscoveryTelemetry (aggregated stats)
  ├─ DiscoveryScheduler (periodic scanning)
  ├─ DiscoveryEventPublisher (EventBus bridge)
  ├─ Hot-reload (file change polling)
  └─ Named profiles (default, deep, minimal)
```

### 4.2 Discovery Providers (15+)

| Provider | Adapter | Method |
|----------|---------|--------|
| PATH | `PathDiscovery` | `$PATH` scanning |
| Windows Registry | `WindowsRegistryDiscovery` | Registry keys |
| WSL | `WslDiscovery` | WSL detection |
| Docker | `DockerDiscovery` | Docker socket |
| Chocolatey | `ChocolateyDiscovery` | Choco installs |
| Scoop | `ScoopDiscovery` | Scoop buckets |
| WinGet | `WingetDiscovery` | WinGet packages |
| NPM | `NpmDiscovery` | Global NPM packages |
| Cargo | `CargoDiscovery` | Cargo installs |
| UV | `UvDiscovery` | UV tool installs |
| VS Code | `VSCodeDiscovery` | Extensions |
| JetBrains | `JetBrainsDiscovery` | Toolbox |
| Known Install Dirs | `KnownInstallDirDiscovery` | Common paths |
| Config File | `ConfigFileDiscovery` | YAML/JSON config |
| Env Var | `EnvVarDiscovery` | Environment variables |
| Shell Profile | `ShellProfileDiscovery` | Shell configs |
| Filesystem | `FilesystemDiscovery` | Recursive scan |

### 4.3 Discovery REST API (17 endpoints)

Under `/api/discovery/`: providers, profiles, scan, cache, history, stats, validation, profiling, hot-reload.

### 4.4 Configuration

```python
class DiscoveryConfiguration:
    enabled: bool
    default_profile: str
    cache_ttl_seconds: float
    max_cache_entries: int
    telemetry_max_entries: int
    profiles: dict[str, DiscoveryProfile]
```

---

## 5. Provider Registry & Routing

### 5.1 Provider Manager

**File**: `src/agentic_os/core/providers/manager.py`

```python
class ProviderManagerImpl:
    _providers: dict[str, ProviderAdapter]     # name → adapter
    _models: dict[str, ModelInfo]              # "provider::model" → ModelInfo
    _configs: dict[str, ProviderConfig]        # name → config
    # register, get, list_providers, set_config, get_config, list_configs
    # register_model, list_models, get_model
```

### 5.2 Provider Registry (Phase 1 Legacy)

**File**: `src/agentic_os/core/registry.py`
Simple dict-based `dict[str, ProviderAdapter]` — superseded by `ProviderManagerImpl`.

### 5.3 Routing Policies

| Policy | Strategy | Location |
|--------|----------|----------|
| **LatencyRoutingPolicy** | Lowest latency (via health monitor) → cost as proxy | `core/providers/routing.py:18-41` |
| **CostRoutingPolicy** | Cheapest model (input+output cost per 1K) | `core/providers/routing.py:44-58` |
| **RoundRobinRoutingPolicy** | Even distribution across providers | `core/providers/routing.py:61-74` |

### 5.4 Provider Router

**File**: `src/agentic_os/core/providers/router.py`

```python
class ProviderRouter:
    def __init__(self, bus, manager, models, health, rate, policy):
        # Wires: Manager + HealthMonitor + ModelManager + RateLimit + Failover

    async def select(self, capability) → (provider, model):
        # 1. Get candidate models by latency proxy
        # 2. Filter by rate limit remaining
        # 3. Apply policy selection (latency | cost | round_robin)

    async def failover(self, failed_provider, capability) → (provider, model):
        # 1. Get healthy providers for capability
        # 2. FailoverPolicy selects next
        # 3. Publishes PROVIDER_FAILOVER event

    async def complete(self, provider, model, messages) → result:
        # Execute via ProviderAdapter
```

### 5.5 Cost Tracker

```python
class CostTrackerImpl:
    _records: list[CostRecord]
    async def record(provider, model, task_id, input_tokens, output_tokens) → float
    def total_cost(provider=None) → float
```

### 5.6 Rate Limit Monitor

```python
class RateLimitMonitorImpl:
    _limits: dict[str, int]  # provider → max requests
    _used: dict[str, int]    # provider → used count
    def set_limit(provider, limit)
    def consume(provider, weight=1) → bool
    def remaining(provider) → int
```

### 5.7 Provider Health Monitor

**File**: `src/agentic_os/core/providers/health.py` (not directly read, referenced)
Tracks provider health status with periodic health checks, feed into router selections.

### 5.8 API Key Vault

**File**: `src/agentic_os/core/providers/vault.py`
`ApiKeyVaultImpl` → `SecretStore` protocol → `EncryptedSecretStore` (Fernet AES-128-GCM, file-backed).

### 5.9 Provider Management REST API

Under `/api/providers/`: list, configs, API keys, test, health, benchmarks, models.
Under `/api/routing/`: policy selection.

---

## 6. Execution Engine Framework

### 6.1 Architecture

```
ExecutionEnginePort  (ports/execution.py: Protocol)
    │
    ├── ExecutionEngineBase  (core/runtime/engine.py)
    │   ├─ Lifecycle: initialize() → health_check() → execute() → shutdown()
    │   ├─ ExecutionRequest → ExecutionResult
    │   └─ Optional: cancel(), pause(), resume(), stream()
    │
    ├── GenericExecutionEngine  (adapters/engines/generic.py)
    │
    └── Other engines implement ExecutionEnginePort directly
```

### 6.2 Runtime Manager

**File**: `src/agentic_os/core/runtime/manager.py`

```python
class RuntimeManager:
    registry: RuntimeRegistryImpl    # Engine CRUD + state
    discovery: DiscoveryEngine        # Automatic engine discovery
    negotiator: CapabilityNegotiator # Capability matching
    _adapters: dict[str, ExecutionEnginePort]  # Live connections
```

**Lifecycle**: `initialize()` → discover engines → register found engines → start health tasks → `RUNNING`.

### 6.3 Runtime Registry

**File**: `src/agentic_os/core/runtime/registry.py`

```python
class RuntimeRegistryImpl:
    _registry: EngineRegistry          # In-memory
    _health_cache: dict[str, ExecutionHealth]
    _sessions: dict[str, ExecutionSession]
    _locks: dict[str, asyncio.Lock]    # Per-engine thread safety
    _adapter_map: dict[str, str]       # engine_id → adapter_key
    # register_engine, update_engine, unregister_engine, get_engine, list_engines
    # find_by_capability, get_health, update_health, create_session, etc.
```

### 6.4 Capability Negotiator

**File**: `src/agentic_os/core/runtime/capabilities.py`

Handles capability advertisement, matching, and negotiation between engines and tasks. Scoring algorithm: required capabilities weighted 10x, optional 1x, missing required → zero score. TTL cache (default 60s) with `asyncio.Lock` for thread safety.

### 6.5 Execution Engine REST API

Under `/api/runtime/engines/`: CRUD, execute, discover, capabilities, health, benchmark, sessions.

---

## 7. AI Brain (Learning & Optimization)

### 7.1 Architecture — LearningManager

**File**: `src/agentic_os/core/learning/manager.py`

Composition root that wires **17 subsystems**:

```
LearningManager
  ├─ History Management:
  │   ├─ HistoricalAnalyzer    (history.py)
  │   └─ LearningTelemetry     (telemetry.py)
  │
  ├─ Optimization Engines:
  │   ├─ OptimizationManager   (optimization.py)
  │   ├─ RoutingOptimizer      (routing.py)
  │   ├─ CostOptimizer         (cost.py)
  │   ├─ PerformanceOptimizer  (performance.py)
  │   ├─ QualityOptimizer      (quality.py)
  │   ├─ SwarmOptimizer        (swarm.py)
  │   └─ PromptOptimizationManager (prompt.py)
  │
  ├─ Analysis & Evaluation:
  │   ├─ BenchmarkManager      (benchmark.py)
  │   ├─ EvaluationEngine      (evaluation.py)
  │   ├─ ModelSelectionEngine  (model_selection.py)
  │   └─ Performance Analyzer
  │
  ├─ Recommendations & Policies:
  │   ├─ RecommendationEngine  (recommendation.py)
  │   ├─ PolicyEngine          (policy.py)
  │   └─ StrategyManager       (strategy.py)
  │
  ├─ Experimentation:
  │   └─ ExperimentManager     (experiment.py)
  │
  ├─ Publishing:
  │   └─ LearningEventPublisher (publisher.py)
  │
  └─ Profiles: dict[str, LearningProfile]
```

### 7.2 Learning Domain Model (~300 lines)

```python
class OptimizationTarget(StrEnum):
    ROUTING, ENGINE_SELECTION, SWARM_COMPOSITION, PLANNER_SELECTION,
    VALIDATOR_SELECTION, CONSENSUS_STRATEGY, RETRY_POLICY, PARALLELISM,
    SCHEDULING, CHECKPOINT_FREQUENCY, MEMORY_USAGE, PROMPT_SELECTION,
    EXECUTION_COST, RESPONSE_QUALITY  (14 targets)

class LearningMetric(StrEnum):
    EXECUTION_LATENCY, FAILURE_RATE, RESOURCE_USAGE, TASK_SUCCESS_RATE,
    RETRY_COUNT, CAPABILITY_UTILIZATION, COST_PER_EXECUTION,
    RESPONSE_QUALITY, USER_SATISFACTION  (9 metrics)

# Key Models:
LearningProfile, ExecutionHistory, OptimizationResult, OptimizationRecommendation,
Recommendation, OptimizationPolicy, Benchmark, BenchmarkResult,
Experiment, Evaluation, RoutingDecision, PerformanceProfile
```

### 7.3 Learning REST API (~50 endpoints)

Under `/api/learning/`: profiles, executions, analysis, metrics, recommendations, optimization, routing, benchmarks, experiments, evaluation, performance, cost, quality, failure-analysis, policies, latency.

### 7.4 Key Insight

The Learning Engine is comprehensive in scope but **all implementations are in-memory stubs**. No actual ML training, no persistent model storage, no online learning. It provides the **scaffolding** for learning behaviors but needs real backends.

---

## 8. Agent Constellation (Orchestration & Swarm Intelligence)

### 8.1 Orchestration Framework

**File**: `src/agentic_os/core/orchestration/framework.py` (~947 lines)

The Orchestration Framework composes **20 subsystems**:

```
OrchestrationFramework
  ├─ Communication & Data:
  │   ├─ OrchestrationEventPublisher  (publisher.py)
  │   ├─ CommunicationBus             (communication.py)
  │   └─ OrchestrationAgentRegistry   (registry.py)
  │
  ├─ Intelligence & Decisions:
  │   ├─ SwarmIntelligenceEngine      (intelligence.py)
  │   ├─ AgentSelector                (agent_selector.py)
  │   ├─ SwarmPlanner                 (planner.py)
  │   ├─ SwarmScheduler               (scheduler.py)
  │   └─ SwarmSupervisor              (supervisor.py)
  │
  ├─ Execution:
  │   ├─ SwarmManager                 (swarm.py)
  │   ├─ CoordinationEngine           (coordination.py)
  │   └─ TaskOrchestrator             (orchestrator.py)
  │
  ├─ Results & Validation:
  │   ├─ ResultMerger                 (result_merger.py)
  │   ├─ ValidationEngine             (validation.py)
  │   ├─ CheckpointManager            (checkpoint.py)
  │   └─ FailureRecovery              (recovery.py)
  │
  ├─ Resilience:
  │   ├─ RetryManager                 (retry.py)
  │   └─ FailureRecovery              (recovery.py)
  │
  └─ Observability:
      ├─ MetricsEngine                (metrics.py)
      ├─ CostTracker                  (cost_tracker.py)
      └─ PerformanceAnalyzer          (performance.py)
```

### 8.2 Coordination Patterns (6)

| Pattern | Description | Method |
|---------|-------------|--------|
| SEQUENTIAL | One task at a time | `_execute_sequential()` |
| PARALLEL | All tasks simultaneously | `_execute_parallel()` |
| FAN_OUT | One task to all agents | `_execute_fan_out()` |
| FAN_IN | All agents produce, one aggregates | `_execute_fan_in()` |
| HIERARCHICAL | Tree-structured parent-child | `_execute_hierarchical()` |
| VOTING | Agents vote on proposals | `_execute_voting()` |

### 8.3 Swarm Topologies (12)

```python
class SwarmTopology(StrEnum):
    SEQUENTIAL, PARALLEL, HIERARCHICAL, SUPERVISOR, MESH,
    TREE, PIPELINE, HUB_AND_SPOKE, STAR, RING, GRAPH, DYNAMIC
```

### 8.4 Swarm Intelligence

**File**: `core/orchestration/intelligence.py`

- **Consensus**: Agents vote on proposals with configurable thresholds (default 51% quorum)
- **Voting**: Structured polls (YES/NO/ABSTAIN)
- **Leader Election**: Select swarm leader based on capability score

### 8.5 Planner → Scheduler → Supervisor Pipeline

```
SwarmPlanner.analyze_goal(goal)
  ├─ Keyword-based complexity estimation
  ├─ Capability inference from goal text
  ├─ Suggested topology (SEQUENTIAL ≤ 2, PARALLEL ≤ 3, HIERARCHICAL ≤ 5)
  └─ Returns GoalAnalysis with complexity, capabilities, topology

SwarmScheduler.schedule_tasks(plan, agents)
  ├─ Topological sort of tasks (dependency resolution)
  ├─ Priority ordering (higher priority first)
  ├─ Deadlock detection (missing dependencies)
  └─ Returns ordered list

SwarmSupervisor.monitor_execution(plan)
  ├─ Failed task detection
  ├─ Hung task detection (configurable timeout, default 120s)
  ├─ Deadlock detection (stalled dependencies)
  └─ Returns updated plan
```

### 8.6 Swarm Manager

CRUD management of named agent teams + lifecycle events published on EventBus.

### 8.7 Key Domain Models

```python
SwarmSpec: id, name, description, topology, agent_ids, leader_id
AgentDescriptor: agent_id, name, engine_type, capabilities, health_status, is_leader
AgentTask: id, goal_id, title, status, assigned_agent, depends_on, output_data
OrchestrationPlan: id, goal_id, subtasks, status, metadata
Checkpoint: plan_id, stage_id, task_states, completed/failed_ids, partial_outputs
RetryPolicy: max_retries, base_delay, backoff_multiplier, max_delay, jitter
ConsensusResult: swarm_id, topic, votes, status, threshold, outcome
MergeStrategy: WEIGHTED, PRIORITY, CONSENSUS, VOTING, BEST_OF_N, CONCATENATE
```

---

## 9. Prompt Center

### 9.1 Current State

The Prompt Center is **minimal** — 4 API endpoints that delegate to `mission_planner`:

```python
GET  /api/prompts         → mission_planner.list_prompts(limit)
POST /api/prompts         → mission_planner.create_prompt(body)
GET  /api/prompts/{id}    → mission_planner.get_prompt(id)
DEL  /api/prompts/{id}    → mission_planner.delete_prompt(id)
```

### 9.2 Implementation

The endpoints use `hasattr()` checks to verify the mission planner supports prompt operations. If `mission_planner` is None or lacks the methods, they return 501. **No dedicated prompt domain or storage** exists yet — this is a Phase 3B/Phase Ψ feature that was partially scaffolded but not fully implemented.

### 9.3 Integration Path for OmniRoute

The Prompt Center should become a **Prompt Registry** service in OmniRoute:
- Versioned prompt templates
- A/B testing via `ExperimentManager`
- Optimization via `PromptOptimizationManager` (already existing in Learning Engine)
- Routing decisions based on prompt category

---

## 10. Diagnostics & Self-Healing

### 10.1 Self-Healing Engine

**File**: `src/agentic_os/core/self_healing.py` (~489 lines)

Severity classification (4 levels):

| Level | Value | Auto-Repair | Requires Approval |
|-------|-------|-------------|-------------------|
| LOW | 1 | ✅ Silent | ❌ |
| MEDIUM | 2 | ✅ If confident | ❌ |
| HIGH | 3 | ❌ | ✅ |
| CRITICAL | 4 | ❌ | ✅ |

**9 Built-in Healing Actions**:

| Action | Severity | Auto | Implementation |
|--------|----------|------|----------------|
| `websocket_reconnect` | MEDIUM | ✅ | Bus stop/start cycle |
| `rebuild_cache` | LOW | ✅ | RuntimeDiscovery cache clear/rebuild |
| `reload_config` | MEDIUM | ❌ | Settings reload |
| `restart_provider` | MEDIUM | ✅ | Provider vault restart |
| `repair_bindings` | MEDIUM | ✅ | Provider auto-bind |
| `restart_backend` | CRITICAL | ❌ | Returns False |
| `rebuild_indexes` | LOW | ✅ | Memory manager reindex |
| `resync_state` | LOW | ✅ | EventBus replay resync |
| `restart_plugin` | MEDIUM | ✅ | Plugin loader restart |

**Event Subscriptions**: `AGENT_FAILED`, `HEALTH_DEGRADED`, `PROVIDER_FAILED`, `CONNECTION_LOST`

**Issue Tracking**: In-memory `_issues: list[HealingIssue]` (UNBOUNDED — memory leak risk)

### 10.2 Health Monitor

**File**: `src/agentic_os/core/health.py` (~67 lines)

- **Tick interval**: `settings.health_interval_seconds` (default: 2.0s)
- **Heartbeat timeout**: `settings.heartbeat_timeout_seconds` (default: 6.0s)
- Agent healthy if `last_heartbeat` age ≤ heartbeat_timeout
- **Events**: `HEALTH_CHECK` per agent per tick, `HEALTH_DEGRADED` on timeout
- **Gap**: In-memory only; no system-level metrics (CPU/mem/disk)

### 10.3 Recovery Manager

**File**: `src/agentic_os/core/recovery.py` (~79 lines)

- Subscribes to `AGENT_FAILED`, `HEALTH_DEGRADED`
- Retry logic: checks `task.attempts < max_attempts` → re-dispatches via Orchestrator
- On exhaustion: marks task FAILED, agent FAILED, emits `AGENT_FAILED`
- **Gap**: No exponential backoff, no circuit breaker, no dead-letter queue

### 10.4 Hardening Manager

**File**: `src/agentic_os/core/desktop/hardening.py` (~532 lines)

| Feature | Implementation |
|---------|----------------|
| Startup Validation | Python version, config files, workspace/db dirs, port check |
| Integrity Checks | Module imports, memory (psutil), 500MB warning |
| Self-Diagnostics | Service imports, disk space, recommendations |
| Memory Leak Detection | Baseline tracking, growth rate vs threshold |
| Thread Monitoring | `threading.enumerate()`, configurable threshold |
| Resource Cleanup | Temp files, cache directory cleanup |
| Auto-Repair | Workspace/config/cache/db directory recreation |
| Recovery Mode | Flag-gated startup with repair + cleanup |
| Graceful Shutdown | 6-step ordered shutdown plan |

---

## 11. EventBus Architecture

### 11.1 Port Contract

```python
class EventBus(Protocol):
    async def start(self) -> None
    async def stop(self) -> None
    async def publish(self, event: EventEnvelope) -> None
    async def subscribe(self, topic: str, handler: Handler) -> str  # returns subscription_id
    async def unsubscribe(self, subscription_id: str) -> None

Handler = Callable[[EventEnvelope], Awaitable[None]]
```

### 11.2 EventEnvelope

```python
class EventEnvelope(BaseModel):
    id: str = field(default_factory=lambda: uuid4().hex)
    type: str         # e.g., "task.created", "agent.heartbeat"
    source: str       # Producer identifier
    topic: str        # Canonical topic from Topic enum
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    payload: dict = {}
```

### 11.3 Topic Taxonomy (~260 topics)

| Category | Topics | Example |
|----------|--------|---------|
| Task/Agent | 8 | `task.created`, `agent.heartbeat`, `agent.failed` |
| Supervision | 3 | `health.check`, `health.degraded`, `recovery.triggered` |
| Provider | 5 | `provider.registered`, `provider.failover`, `cost.recorded` |
| Memory | 2 | `memory.written`, `memory.evicted` |
| Security | 4 | `approval.requested`, `audit.event` |
| Workflow | 14 | `workflow.created`, `workflow.executed`, `workflow.replayed` |
| Mission | 15 | `mission.created` → `mission.task_failed` |
| Self-Healing | 3 | `self_healing.issue`, `connection.lost` |
| Pipeline | 15 | `pipeline.created` → `pipeline.rolled_back` |
| MCP | 23 | `mcp.server_registered` → `mcp.capability_negotiated` |
| Orchestration | 76 | `orchestration.swarm_created` → `orchestration.execution_stage_failed` |
| Learning | 14 | `learning.execution_recorded` → `learning.experience_recorded` |
| Plugin | 7 | `plugin.installed` → `plugin.capability_registered` |
| Engine | 13 | `engine.registered` → `engine.benchmark_completed` |
| Discovery | 18 | `discovery.scan_started` → `profiling.completed` |
| Desktop | ~48 | Desktop lifecycle, workspace, window, notification events |

### 11.4 Adapter Comparison

| Property | LocalBus | RedisStreamsBus | NatsJetStreamBus |
|----------|----------|-----------------|------------------|
| **Transport** | In-memory asyncio | Redis Streams | NATS JetStream |
| **Ordering** | Per-topic FIFO | Per-stream FIFO | Per-subject FIFO |
| **Delivery** | At-most-once | At-least-once | At-least-once |
| **Persistence** | None | Redis (disk) | JetStream (disk) |
| **Replay** | None | `XREAD` from ID | Durable consumer |
| **Backpressure** | None | COUNT/BLOCK polling | Flow control |
| **Consumer Groups** | N/A | ✅ XGROUP | ✅ Queue groups |
| **Reconnect** | N/A | redis-py auto | NATS auto |

---

## 12. WebSocket Architecture

### 12.1 Dashboard WebSocket (`/ws/dashboard`)

- **Broadcaster**: `DashboardBroadcaster` (~135 lines, `api/dashboard.py`)
- **Subscribed Topics**: 96 topics across Task, Agent, Health, Provider, Memory, Capability, Security, MCP, Learning
- **History**: Ring buffer `deque(maxlen=256)`
- **REST Replay**: `GET /api/events/recent?limit=50`
- **Heartbeat**: 30s interval `{"topic": "heartbeat", "ts": ...}`
- **Fan-out**: `anyio.create_memory_object_stream(max_buffer_size=256)` per client
- **Direction**: Server → Client only (unidirectional broadcast)

### 12.2 MCP WebSocket (`/ws/mcp`)

- **Broadcaster**: `MCPBroadcaster` (`api/mcp_ws.py`)
- **Subscribed Topics**: 21 MCP server lifecycle topics
- **History**: None (no ring buffer)
- **Heartbeat**: Same 30s pattern

### 12.3 Gap Analysis

| Gap | Impact |
|-----|--------|
| No WebSocket authentication | Any client can connect |
| No client→server messages | No subscription filtering |
| No per-client topic filtering | All clients get all events |
| No reconnection state sync | Clients must REST-replay on reconnect |
| No backpressure handling | `BrokenResourceError` drops clients silently |

---

## 13. REST API — Complete Endpoint Inventory

**Total**: **396 endpoints** in 20+ groups across `app.py` (3926 lines)

### 13.1 Endpoint Summary by Group

| Group | Endpoints | File (app.py lines) | Dependencies |
|-------|-----------|---------------------|--------------|
| System | 4 | 2299-2353 | Bus, Dashboard |
| Tasks/Agents | 3 | 2375-2406 | Registry, Orchestrator |
| Providers | 16 | 2412-2585 | ProviderManager, Router |
| Capability | 2 | 2591-2621 | CapabilityEngine |
| Missions | 9 | 2627-2730 | In-memory `_missions` dict |
| Memory | 5 | 2736-2795 | MemoryManager |
| Security | 6 | 2801-2875 | SecurityFramework |
| Workflows | 16 | 2881-3055 | WorkflowEngineImpl |
| Pipelines | 19 | 3061-3255 | PipelineEngineImpl |
| Runtime Engines | 11 | 3261-3420 | RuntimeManager |
| Discovery | 17 | 3426-3614 | DiscoveryFramework |
| Installer | 4 | 3620-3660 | InstallerIntelligence |
| MCP | 23 | 3666-3820 | MCP Manager |
| Swarm/Orch | ~80 | 1733-2170 | OrchestrationFramework |
| Learning | ~50 | 2243-2590 | LearningManager |
| Desktop | ~100 | 2606-3348 | DesktopRuntimeManager |
| Event History | 1 | 3350-3353 | Dashboard ring buffer |
| WebSockets | 2 | 3360-3442 | Dashboard/MCP broadcasters |
| Binding Center | 10 | 3540-3717 | auto_bind + ProviderRegistry |
| OmniRoute | 10 | 3719-3867 | Stub/hardcoded data |
| Prompt Center | 4 | 3483-3515 | MissionPlanner |
| OpenAI Gateway | 4 | 3870-3878 | gateway.py mounted router |

### 13.2 Unavailable Sentinel Pattern

When any subsystem is `None` (not yet initialized), the API returns HTTP 503:

```python
async def some_endpoint():
    if platform.mission_planner is None:
        raise HTTPException(503, "Mission planner not available")
```

This affects ~150+ endpoints during startup (before background init completes).

### 13.3 Middleware

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "tauri://localhost"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

No other middleware (no auth, no request logging, no rate limiting at API level).

---

## 14. Database & Persistence

### 14.1 Persistence Layers

| Layer | Implementation | Loc | Type |
|-------|---------------|-----|------|
| Secret Store | `EncryptedSecretStore` | `adapters/security/` | Fernet AES-128-GCM, file-backed JSON |
| API Key Vault | `ApiKeyVaultImpl` | `core/providers/vault.py` | Namespaced over SecretStore |
| Memory System | `MemoryManagerImpl` | `core/memory/manager.py` | In-memory (vector, graph, KV) |
| Desktop DB | `DesktopDatabase` | `core/desktop/database.py` | SQLite (aiosqlite) |
| Discovery Cache | `DiscoveryCache` | `core/discovery/cache.py` | In-memory TTL cache |
| All Orchestration | In-memory dicts | Throughout core/ | No persistence |

### 14.2 Secret Store Details

- **Encryption**: Fernet (AES-128-GCM with HMAC-SHA256)
- **Key source**: 1) `AGENTIC_OS_MASTER_KEY` env, 2) `~/.agentic-os/master.key` file, 3) auto-generated
- **Persistence**: Atomic write (.tmp → rename, `chmod 600`)
- **Storage**: JSON at `AGENTIC_OS_VAULT_PATH` or in-memory

### 14.3 Desktop Database (SQLite)

Tables: `windows`, `workspaces`, `workspace_layouts`, `tabs`, `panels`, `notifications`, `config`, `clipboard_history`, `terminals`, `shortcuts`, `command_palette`, `search_index`, `runtime_discovery`, `update_history`, `backup_metadata`, `restore_points`, `hardening_config`, `hardening_history`.

**Gaps**: No schema migrations (CREATE TABLE IF NOT EXISTS only), no PostgreSQL support, no connection pooling.

### 14.4 Zero Permanent Persistence for Core Domain

All core orchestration state (missions, workflows, pipelines, swarms, agents, tasks, learning history) is **in-memory only** — lost on restart. The EventBus (Redis/NATS) provides at-least-once delivery but no state reconstruction.

---

## 15. Plugin System

### 15.1 Plugin Registry

**File**: `src/agentic_os/core/plugins/registry.py` (~759 lines)

Full lifecycle management:
- **Install/Uninstall**: Plugin directory management
- **Start/Stop/Restart**: Process lifecycle
- **Dependency Resolution**: Topological sort with cycle detection (DFS)
- **Capability Discovery**: Scan manifests + `@capability` decorators
- **Signature Verification**: SHA-256 (placeholder)
- **Health Monitoring**: Process poll (DummyProcess mock)
- **Per-plugin asyncio.Lock**: Thread safety

### 15.2 Plugin Loader

**File**: `src/agentic_os/core/plugins/loader.py` (~376 lines)

- **PluginSandbox**: Restricted `__builtins__` (no `open`, `eval`, `exec`, etc.)
- **Sandboxed `exec()`**: `_load_module()` with sandbox globals
- **Decorators**: `@capability`, `@plugin_main`, `@plugin_config`
- **Manifest scanning**: `_extract_capabilities()` decorator scanning
- **Plugin class discovery**: Via `_plugin_main` attribute

### 15.3 Built-in Plugins

`adapters/plugins/builtins.py` — list of pre-installed plugins registered in kernel.

### 15.4 Plugin Events

7 event topics: `plugin.installed`, `plugin.uninstalled`, `plugin.started`, `plugin.stopped`, `plugin.failed`, `plugin.updated`, `plugin.capability_registered`.

---

## 16. MCP (Model Context Protocol) Framework

### 16.1 Architecture — 14 Files in `core/mcp/`

```
core/mcp/
├── registry.py       # MCPRegistryImpl — server CRUD + lifecycle (600+ lines)
├── manager.py         # MCPManager — orchestrates all MCP subsystems
├── client.py          # MCPClient — all 3 transports (300+ lines)
├── pool.py            # Connection pool
├── capability.py      # MCPCapabilityMapper
├── security.py        # MCPSecurity
├── tool_registry.py   # MCPToolRegistry
├── resource_registry.py # MCPResourceRegistry
├── prompt_registry.py # MCPPromptRegistry
├── session.py         # Session management
├── health.py          # Health monitoring
├── discovery.py       # MCP server discovery
├── telemetry.py       # Telemetry
├── version.py         # Version management
└── __init__.py
```

### 16.2 MCP Client Transports

**File**: `core/mcp/client.py` (~300+ lines)

| Transport | Implementation | Reconnection |
|-----------|----------------|--------------|
| **stdio** | `subprocess.Popen` with stdin/stdout JSON-RPC | Auto-reconnect with exponential backoff (max 5 retries, base 1s, max 30s) |
| **SSE** | `httpx.AsyncClient` + SSE stream listener | Same auto-reconnect |
| **Streamable HTTP** | `httpx.AsyncClient` + POST streaming | Same auto-reconnect |

**Protocol**: JSON-RPC 2.0, MCP protocol version `2024-11-05`.

### 16.3 MCP Registry

**File**: `core/mcp/registry.py` (600+ lines)

```python
class MCPRegistryImpl(MCPRegistryPort):
    bus: EventBus
    _registry: MCPRegistry
    _permissions: dict[str, list[MCPPermissionMapping]]
    _health_cache: dict[str, tuple[MCPHealthStatus, dict]]
    _clients: dict[str, MCPClient]
    _locks: dict[str, asyncio.Lock]
    
    # CRUD: register, get, update, delete servers
    # Lifecycle: start, stop, restart, hot-reload
    # Tools: list, invoke, discover
    # Resources: list, read, subscribe
    # Prompts: list, get
    # Permissions: set, get permission mappings
    # Health: check, cache
```

### 16.4 MCP Manager

**File**: `core/mcp/manager.py`

```python
class MCPManager:
    registry: MCPRegistryImpl
    bus: EventBus
    security: MCPSecurity | None
    version_manager: MCPVersionManager
    capability_mapper: MCPCapabilityMapper
    tool_registry: MCPToolRegistry
    resource_registry: MCPResourceRegistry
    prompt_registry: MCPPromptRegistry
    default_principal: Principal (ADMIN)
    
    # Lifecycle: initialize, start, stop, shutdown
    # Server lifecycle: start/stop/restart with supervision
    # Auto-restart: configurable (default: on)
```

### 16.5 MCP Domain Models (629 lines)

Key models: `MCPTool` (with `input_schema`/`output_schema`), `MCPResource`, `MCPPrompt`, `MCPRoot`, `MCPPermissionMapping`, `MCPServerConfig` (immutable, with `create_stdio()`/`create_sse()`/`create_streamable_http()` class methods + `with_enabled()`/`with_sandbox()` pattern), `MCPServerDetail` (with `with_status()`/`with_tools()`/`with_health()` immutable updates), `MCPRegistry`, `MCPSession`, `MCPSubscription`, `MCPCapability`.

### 16.6 MCP REST API (23 endpoints)

Under `/api/mcp/servers/`: CRUD, start/stop/restart, tools (list, discover, call), resources (list, read, subscribe), prompts (list, get), health, permissions. Plus `/api/mcp/health` summary and `/api/mcp/sessions`.

---

## 17. Swarm Orchestration Engine

### 17.1 Execution Flow

```
Goal → Plan → Schedule → Execute → Monitor → Merge → Complete
 │        │        │         │         │        │        │
 │        │        │     Coordination    │        │        │
 │        │        │     Engine          │        │        │
 │        │        │       │             │        │        │
 │    Swarm    Swarm    parallel    Swarm    Result    Plan
 │    Planner Scheduler fan-out   Supervisor Merger   Status
 │                    voting
```

### 17.2 Agent Selection

**File**: `core/orchestration/agent_selector.py`

Scoring algorithm:
1. **Capability match** (50% weight): keyword overlap between task title and agent capabilities
2. **Health status** (25% weight): healthy = 1.0, degraded = 0.5, unknown = 0.3, unhealthy = 0.0
3. **Latency** (15% weight): normalized inverse (lower = better)
4. **Load** (10% weight): fewer running tasks = higher score

### 17.3 Retry Manager

**File**: `core/orchestration/retry.py`

Exponential backoff with jitter:
```
delay = min(base_delay × multiplier^retry_count, max_delay)
if jitter: delay += random(0, delay × 0.1)
```

Configurable: `max_retries`, `retry_on_error`, `retry_on_timeout`, `base_delay_seconds`, `backoff_multiplier`, `max_delay_seconds`.

### 17.4 Checkpoint Manager

**File**: `core/orchestration/checkpoint.py`

In-memory checkpoints saving task states, partial outputs, and metadata. Default: every 5 completed tasks.

### 17.5 Result Merger

**File**: `core/orchestration/result_merger.py`

6 merge strategies: `WEIGHTED`, `PRIORITY`, `CONSENSUS`, `VOTING`, `BEST_OF_N`, `CONCATENATE`. Conflict resolution via highest-confidence selection.

### 17.6 Consensus & Voting

**File**: `core/orchestration/intelligence.py`

- `start_consensus(swarm_id, topic, proposals, agents, quorum)` → collects votes
- `resolve_consensus(consensus_id)` → determines REACHED/FAILED/TIE
- `elect_leader(swarm_id, agents)` → highest capability score wins

### 17.7 Orchestration REST API (~80 endpoints)

Under `/api/swarm/`: profiles, swarms, planner, scheduler, supervisor, merger, validation, checkpoints, agent selection, metrics, cost, recovery, retry, goals, plans, tasks.

---

## 18. Desktop Runtime & Installer

### 18.1 DesktopRuntimeManager

**File**: `core/desktop/manager.py` (God object — 309 lines, 27 fields)

Wires **27 subsystems**:
`window`, `workspace`, `notification`, `file`, `clipboard`, `terminal`, `process`, `logging`, `configuration`, `diagnostics`, `performance`, `menu`, `dragdrop`, `database`, `publisher`, `runtime_discovery`, `update`, `installer`, `first_run`, `channel`, `rollback`, `portable`, `offline`, `backup`, `delta_update`, `signature`, `windows_platform`, `hardening`.

### 18.2 Desktop Domain (~1900 lines, ~80 dataclasses)

Covers: windows, workspaces, layouts, panels, tabs, menus, notifications, dialogs, performance, diagnostics, configuration, shortcuts, database, clipboard, drag-drop, terminal, processes, updates, deltas, installers, signatures, offline, backup, restore, first-run, runtime discovery, platform integration, hardening, diagnostics, recovery, repair, shutdown.

### 18.3 Installer Intelligence

- Auto-detects and validates installed providers
- First-launch wizard for initial setup
- Agent discovery, validation, and binding
- REST API: `/api/installer/report`, `/api/installer/scan`, `/api/installer/heal`, `/api/installer/providers`

### 18.4 Hardening Manager (~532 lines)

Comprehensive but **all in-memory**: startup validation, integrity checks, memory leak detection, thread monitoring, resource cleanup, recovery mode, graceful shutdown.

### 18.5 Key Gaps

- **Zero port abstractions**: All 27 subsystems are concrete classes
- **Most implementations are stubs**: performance, process, delta_update, rollback
- **God class problem**: `DesktopRuntimeManager` violates SRP
- **In-memory state**: Backup, rollback, offline queue, cleanup history all lost on restart

---

## 19. Technical Debt Analysis

### 19.1 Architectural Weaknesses

| # | Issue | Severity | Location | Impact |
|---|-------|----------|----------|--------|
| 1 | DesktopRuntimeManager holds 27 concrete subsystems | **Critical** | `desktop/manager.py` | SRP violation; untestable; impossible to swap |
| 2 | Domain models imported in core layer | **High** | All `desktop/*.py` | Port/adapter boundary violated |
| 3 | Hardcoded subprocess calls in domain | **High** | `desktop/signature.py` | Infrastructure in domain layer |
| 4 | psutil imported in domain logic | **High** | `desktop/hardening.py` | Infrastructure concern |
| 5 | EventBus passed as `Any` | **Medium** | `desktop/manager.py:52` | Type safety lost |
| 6 | In-memory state in all services | **Medium** | Throughout | No persistence; not distributed-safe |

### 19.2 Circular Dependencies

| Cycle | Files | Impact |
|-------|-------|--------|
| `manager.py` ↔ `hardening.py` | `manager.py` imports `DesktopHardeningManager`; `hardening.py` imports `agentic_os.core.desktop.manager` | Runtime circular import risk at `hardening.py:149` |
| `self_healing.py` ↔ `recovery.py` | Event subscriptions create runtime cycles | Runtime coupling |

### 19.3 Code Smells

| Smell | Location | Detail |
|-------|----------|--------|
| **God Class** | `DesktopRuntimeManager` | 309 lines, 27 fields, 27 subsystems |
| **Large File** | `domain/desktop.py` | 1913 lines, ~80 dataclasses — needs splitting |
| **Long Method** | `DesktopHardeningManager.validate_startup()` | 70 lines — multiple validations in one method |
| **Stub Implementations** | `performance.py`, `process.py`, `delta_update.py`, `rollback.py` | Return fake/random data |
| **Magic Numbers** | `hardening.py:180` (500MB), `hardening.py:309` (threshold) | Should be config |
| **Uninitialized Fields** | `DesktopLogging._logs` | `_add_entry` references `self._logs` but never initialized |
| **Unbounded Lists** | `SelfHealingEngine._issues` | Never pruned — memory leak |
| **Dead Code** | `SelfHealingEngine._restart_backend()` | Always returns `False`; no call path |

### 19.4 Missing Port Abstractions

| Should Be Port | Concrete Class | Count |
|----------------|----------------|-------|
| `WindowManagerPort` | `NativeWindowManager` | |
| `ProcessManagerPort` | `NativeProcessManager` | |
| `ClipboardPort` | `NativeClipboardService` | |
| `FileDialogPort` | `NativeFileIntegration` | |
| `TerminalPort` | `NativeTerminalIntegration` | |
| `NotificationPort` | `NativeNotificationService` | |
| `MenuPort` | `NativeMenuManager` | |
| `DragDropPort` | `NativeDragDropService` | |
| `DatabasePort` | `LocalDatabaseManager` | |
| `SystemMetricsPort` | psutil calls in hardening/performance | |
| `CodeSigningPort` | subprocess calls in signature.py | |
| `BackupPort` | `BackupManager` | |
| **Total** | **Zero ports for 27 desktop subsystems** | |

### 19.5 Performance Bottlenecks

| Issue | Location | Impact |
|-------|----------|--------|
| Sync I/O in async methods | `signature.py` (subprocess.run), `hardening.py` (glob/os.remove) | Blocks event loop |
| No caching | `RuntimeDiscoveryManager.discover_runtimes()` called on startup | Repeated expensive operations |
| Unbounded in-memory lists | `SelfHealingEngine._issues`, `OfflineRuntimeManager._queue` | Memory leak risk |
| Linear search | `BackupManager.get_backup_info()` O(n) | Slow at scale |

### 19.6 Race Conditions

| Issue | Location |
|-------|----------|
| No locks on shared mutable state | `SelfHealingEngine._issues` (list append/read from async handlers) |
| No locks | `BackupManager._backups`, `OfflineRuntimeManager._queue` |
| No locks | `DesktopHardeningManager._cleanup_history` |
| `psutil.Process()` calls | `hardening.py:177, 275, 485` — not thread-safe for rapid calls |

### 19.7 Dead Imports in Self-Healing

Multiple `_repair_*` methods in `self_healing.py` use `# type:ignore[unresolved-import]`:
- `from agentic_os.services.runtime_discovery import cache`
- `from agentic_os.domain.events import replay`
- `from agentic_os.core.plugins import loader`

These imports don't exist and will raise `ImportError` at runtime if those healing actions are triggered.

---

## 20. OmniRoute Readiness Assessment

### 20.1 Can OmniRoute Be Embedded Cleanly? **Conditional Yes**

| Factor | Assessment |
|--------|------------|
| EventBus-centric architecture | ✅ Excellent fit — OmniRoute is event-driven routing |
| Port/adapter pattern at core | ✅ EventBus, Scheduler, Orchestrator already port-based |
| Desktop layer has ZERO ports | ❌ **Critical blocker** — must extract 27 port interfaces |
| SelfHealingEngine/HealthMonitor concrete | ❌ Not behind ports |
| God object DesktopRuntimeManager | ❌ Prevents clean composition |

### 20.2 Modules Reusable by OmniRoute

| Module | Reuse | Reason |
|--------|-------|--------|
| `EventBus` protocol + adapters | **High** | Core routing fabric |
| `EventEnvelope` + `Topic` taxonomy | **High** | Message format (260+ topics) |
| `ProviderRouter` + routing policies | **High** | Selection/failover patterns |
| `SelfHealingEngine` severity + actions | **Medium** | Adapt for route health |
| `HealthMonitor` heartbeat pattern | **Medium** | Adapt for endpoint health |
| `RecoveryManager` retry logic | **Medium** | Adapt for circuit breaker |
| `CostTrackerImpl` | **Medium** | Route cost tracking |
| `DesktopEventPublisher` topic mapping | **High** | Event bridging pattern |

### 20.3 Modules That Must Be Replaced

| Module | Reason |
|--------|--------|
| `DesktopRuntimeManager` | God object → OmniRoute Runtime Composition Root |
| All 27 `Native*Manager` classes | Concrete → OmniRoute Provider Adapters |
| `SelfHealingEngine` | Agent-centric → OmniRoute route-level healing |
| `HealthMonitor` | Agent-centric → OmniRoute endpoint health |
| `RecoveryManager` | Task-retry → OmniRoute circuit breaker |
| `DesktopHardeningManager` | Desktop → OmniRoute infrastructure hardening |
| `BackupManager` / `RollbackManager` | App backup → OmniRoute state management |

### 20.4 Overlapping Functionality

| Functionality | Current | OmniRoute Equivalent |
|---------------|---------|---------------------|
| Event routing | `EventBus` + `Topic` | OmniRoute Router |
| Health checks | `HealthMonitor` (agent) | OmniRoute Endpoint Health |
| Failure recovery | `RecoveryManager` (task retry) | OmniRoute Circuit Breaker |
| Auto-repair | `SelfHealingEngine` (9 actions) | OmniRoute Healing Policies |
| Configuration | `DesktopConfigurationManager` | OmniRoute Config Registry |
| Logging | `DesktopLogging` + EventPublisher | OmniRoute Telemetry |
| Process management | `NativeProcessManager` | OmniRoute Runtime Manager |
| Offline queue | `OfflineRuntimeManager` | OmniRoute Persistent Queue |
| Update/rollback | `AutoUpdateManager` + `RollbackManager` | OmniRoute Versioned Deploy |

### 20.5 Abstractions That Must Become Shared Ports

| Port Name | Current | OmniRoute Use |
|-----------|---------|---------------|
| `EventBus` | ✅ Exists | Core routing fabric |
| `HealthCheckPort` | `HealthMonitor` (concrete) | Route/endpoint health |
| `RecoveryPort` | `RecoveryManager` (concrete) | Circuit breaker, retry |
| `ConfigurationPort` | `DesktopConfigurationManager` | Unified config |
| `MetricsPort` | `DesktopPerformanceMonitor` | Telemetry |
| `ProcessPort` | `NativeProcessManager` | Runtime spawning |
| `StoragePort` | `LocalDatabaseManager` | State persistence |
| `QueuePort` | `OfflineRuntimeManager._queue` | Persistent event queue |
| `SignaturePort` | `SignatureVerification` | Policy verification |
| `BackupPort` | `BackupManager` | State snapshots |

### 20.6 Recommended Integration Points

| OmniRoute Subsystem | Location | Integration |
|---------------------|----------|-------------|
| **Router Engine** | `src/agentic_os/core/omniroute/router.py` | Adjacent to orchestrator, scheduler, event_bus |
| **Provider Registry** | `src/agentic_os/core/omniroute/registry.py` | Implements `ProviderRegistryPort` |
| **Health Checks** | `src/agentic_os/core/omniroute/health.py` | Wraps HealthMonitor + Endpoint Health |
| **Healing Policies** | `src/agentic_os/core/omniroute/healing.py` | Wraps SelfHealingEngine patterns |
| **Model Discovery** | `src/agentic_os/core/omniroute/discovery.py` | Aggregates Runtime + MCP + Provider discovery |
| **Authentication** | `src/agentic_os/core/security/auth.py` | EventBus middleware for auth |

### 20.7 Recommended Migration Plan (12 Weeks)

#### Phase 0: Foundation (Week 1-2)
- [ ] Extract **Port protocols** for all 27 desktop subsystems
- [ ] Create `EventBus` middleware for auth, logging, metrics
- [ ] Add `ProviderRegistryPort` + reference implementation
- [ ] Fix circular import: `hardening.py` → `manager.py`
- [ ] Fix uninitialized `DesktopLogging._logs` and unbounded `SelfHealingEngine._issues`

#### Phase 1: OmniRoute Core (Week 3-4)
- [ ] Implement `Router` (`core/omniroute/router.py`)
- [ ] Implement `ProviderRegistry` (`core/omniroute/registry.py`)
- [ ] Implement `HealthCheckPort` + adapter for `HealthMonitor`
- [ ] Implement `RecoveryPort` + adapter for `RecoveryManager`
- [ ] Migrate `EventBus` topic taxonomy to OmniRoute schema

#### Phase 2: Desktop as Provider (Week 5-6)
- [ ] Wrap each `Native*Manager` as `ProviderAdapter` implementing ports
- [ ] Register desktop subsystems in `ProviderRegistry`
- [ ] Replace `DesktopRuntimeManager` with `OmniRouteRuntime` composition
- [ ] Migrate `DesktopEventPublisher` → OmniRoute event router

#### Phase 3: Diagnostics Migration (Week 7-8)
- [ ] Port `SelfHealingEngine` → OmniRoute `HealingPolicyEngine`
- [ ] Port `HealthMonitor` → OmniRoute `HealthCheckFramework`
- [ ] Port `RecoveryManager` → OmniRoute `CircuitBreaker` + `RetryPolicy`
- [ ] Port `HardeningManager` → OmniRoute `StartupValidator`
- [ ] Port `OfflineRuntimeManager` → OmniRoute `PersistentQueue`

#### Phase 4: Advanced Features (Week 9-10)
- [ ] Model Discovery aggregation (Runtime + Provider + MCP)
- [ ] Mission Orchestrator → Workflow Engine migration
- [ ] AI Brain → Routing Policy Engine integration
- [ ] Agent Constellation → Coordination Primitives

#### Phase 5: Cleanup (Week 11-12)
- [ ] Remove `DesktopRuntimeManager` and all `Native*Manager` direct instantiation
- [ ] Remove `SelfHealingEngine`, `HealthMonitor`, `RecoveryManager` from core
- [ ] Remove `DesktopEventPublisher` (replaced by OmniRoute router)
- [ ] Consolidate `domain/desktop.py` → split into subdomain modules
- [ ] Delete stub implementations (`performance.py`, `process.py`, `delta_update.py`, `rollback.py`)
- [ ] Add integration tests for OmniRoute + Desktop providers

### 20.8 Summary Assessment

| Aspect | Assessment |
|--------|------------|
| **Architectural Fit** | ✅ Good at core (EventBus, ports); ❌ Poor at desktop (no ports, god object) |
| **Reusable Code** | ~30% (EventBus, Topic taxonomy, Scheduler, Orchestrator patterns) |
| **Must Replace** | ~70% (All desktop subsystems, healing, health, recovery, hardening) |
| **Biggest Blocker** | 27 concrete desktop managers with zero port abstractions |
| **Quick Wins** | Extract ports; fix circular import; fix uninitialized lists |
| **Migration Effort** | **High** — 12-week phased approach recommended |

---

## Appendix A: Dependency Graph

```
kernel.py ──────────────────────────────────────────────────────────────────┐
    │                                                                       │
    ├──> adapters/bus/factory.py ──> local.py / redis_streams.py / nats_jetstream.py
    ├──> ports/event_bus.py (EventBus Protocol)
    ├──> adapters/discovery/* (15+ DiscoveryProviders)
    ├──> adapters/engines/generic.py
    ├──> adapters/plugins/loader.py
    ├──> adapters/security/encrypted_store.py
    ├──> api/dashboard.py, api/mcp_ws.py, api/app.py
    ├──> config.py (pydantic-settings)
    │
    ├──> core/capability/engine.py
    ├──> core/desktop/manager.py ──> 28 subsystem files
    ├──> core/discovery/* (10 files)
    ├──> core/health.py
    ├──> core/learning/manager.py ──> 18 subsystem files
    ├──> core/mcp/manager.py ──> 14 subsystem files
    ├──> core/memory/manager.py
    ├──> core/mission.py
    ├──> core/orchestration/framework.py ──> 20+ subsystem files
    ├──> core/orchestrator.py
    ├──> core/pipeline/engine.py
    ├──> core/plugins/registry.py
    ├──> core/providers/* (router, manager, routing, vault, health)
    ├──> core/recovery.py
    ├──> core/registry.py
    ├──> core/runtime/* (manager, engine, registry, discovery, capabilities)
    ├──> core/scheduler.py
    ├──> core/security/framework.py
    ├──> core/self_healing.py
    ├──> core/workflow/engine.py
    │
    ├──> domain/* (events, agent, mission, orchestration, mcp, workflow,
    │              pipeline, learning, provider_mgmt, discovery, execution,
    │              memory, security, desktop)
    │
    └──> ports/* (18 protocol files)
```

## Appendix B: Key Metrics

| Metric | Value |
|--------|-------|
| Total Python files | ~250+ |
| Total lines of code | ~60,000+ |
| Domain layer (pure Python) | ~5,000 lines |
| Ports layer (Protocols) | ~1,000 lines |
| API layer (FastAPI) | ~4,500 lines |
| Core layer | ~30,000 lines |
| Adapters layer | ~5,000 lines |
| REST API endpoints | 396 |
| Event topics | 260+ |
| Orchestration subsystems | 20 |
| MCP files | 14 |
| Desktop subsystems | 27 |
| Learning subsystems | 17 |
| Discovery providers | 15+ |
| External dependencies | 25+ (pyproject.toml) |

---

*Report generated from source code analysis of AgenticOS v1.0.0-rc1 at E:\AgenticOsHybrid*
*Analysis-only phase — no code was modified, refactored, or implemented.*
