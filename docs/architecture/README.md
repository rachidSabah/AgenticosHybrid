# AgenticOS Architecture

> **Version:** v1.0.0-rc1 — Release Candidate
>
> AgenticOS is a **local-first, event-bus-driven AI Agent Operating System**
> built on strict hexagonal (clean) architecture. Business logic depends on
> *interfaces* (ports); concrete infrastructure lives behind those ports as
> *adapters*. The composition root (`kernel.py`) is the only place that knows
> about concrete classes. Swapping the bus, a provider, or a subsystem requires
> zero call-site changes.

---

## Table of Contents

1. [High-Level System Architecture](#high-level-system-architecture)
2. [Hexagonal Architecture Pattern](#hexagonal-architecture-pattern)
3. [Kernel & Bootstrap Process](#kernel--bootstrap-process)
4. [Event Bus](#event-bus)
5. [Desktop Runtime Composition](#desktop-runtime-composition)
6. [Desktop Runtime Manager (Composition Root)](#desktop-runtime-manager-composition-root)
7. [Mission Control Frontend](#mission-control-frontend)
8. [MCP Runtime Architecture](#mcp-runtime-architecture)
9. [Swarm Engine Architecture](#swarm-engine-architecture)
10. [Learning & Optimization Engine](#learning--optimization-engine)
11. [Security Framework](#security-framework)
12. [Plugin System](#plugin-system)
13. [Provider Management](#provider-management)
14. [Recovery & Failover Mechanisms](#recovery--failover-mechanisms)
15. [Offline Mode Architecture](#offline-mode-architecture)
16. [Update System Architecture](#update-system-architecture)

---

## High-Level System Architecture

```
  ┌──────────────────────────────────────────────────────────────────────┐
  │                    MISSION CONTROL (Next.js 15 SPA)                   │
  │  15 Views · Glassmorphism · Dark/Light · ⌘K Palette · 120Hz Motion   │
  └──────────────┬───────────────────────────────────────────┬───────────┘
                 │ HTTP REST (800+)                          │ WebSocket
                 ▼                                           ▼
  ┌──────────────────────────────────────────────────────────────────────┐
  │                    API LAYER (FastAPI Control Plane)                  │
  │  /api/* (120+ endpoints) · /ws/dashboard · /ws/mcp · /healthz       │
  │  CORS: localhost:3000, 127.0.0.1:3000, tauri://localhost            │
  └──────────────────────────┬───────────────────────────────────────────┘
                             │
  ┌──────────────────────────┴───────────────────────────────────────────┐
  │                       KERNEL — Composition Root                       │
  │                     kernel.py · Platform dataclass                    │
  ├──────────────────────────────────────────────────────────────────────┤
  │                                                                       │
  │  ┌───────────────────────────────────────────────────────────────┐   │
  │  │                     CORE — Subsystem Logic                     │   │
  │  │                                                               │   │
  │  │  Runtime         Discovery       Orchestration     MCP        │   │
  │  │  Manager         Framework       Framework        Manager     │   │
  │  │  Registry        Cache/Telemetry SwarmPlanner     Registry    │   │
  │  │  CapNegotiator   Validators     SwarmScheduler    Client      │   │
  │  │  CompositeEngine Profiling      SwarmSupervisor   Pool        │   │
  │  │                                 ResultMerger      Security    │   │
  │  │  Workflow        Pipeline       Coordination      ToolReg     │   │
  │  │  Engine          Engine         Intelligence      ResourceReg │   │
  │  │                                 Communication     PromptReg   │   │
  │  │  Provider        Capability     Checkpoint        VersionMgmt │   │
  │  │  Manager         Engine         Retry             CapMapper   │   │
  │  │  Router/Vault    Memory         Recovery          Discovery   │   │
  │  │  Health/Cost     Manager        Metrics/Cost      Health      │   │
  │  │                                                               │   │
  │  │  Security        Learning       Scheduler        Recovery     │   │
  │  │  Framework       Engine         Orchestrator     Manager      │   │
  │  │  ─────────────────────────────────────────────────────────    │   │
  │  │  Desktop Runtime Manager (28 subsystems)                      │   │
  │  └───────────────────────────────────────────────────────────────┘   │
  │                              │                                        │
  │  ┌──────────────────────────┼────────────────────────────────────┐   │
  │  │        PORTS — Interfaces (Protocols)                          │   │
  │  │  EventBus   ExecEngine   MCPRegistry   DiscoveryProvider      │   │
  │  │  ProvMgr    Orchestration  Security     Plugin     Workflow    │   │
  │  │  Pipeline   Tracing     Metrics       Logging    Supervision   │   │
  │  └────────────────────────────────────────────────────────────────┘   │
  │                              │                                        │
  │  ┌──────────────────────────┼────────────────────────────────────┐   │
  │  │      ADAPTERS — Concrete Infrastructure                       │   │
  │  │  Bus: Local | Redis | NATS   Discovery: 10 providers          │   │
  │  │  Memory: InMemory | Vec | KG  Security: RBAC+Enc+Approval    │   │
  │  │  Engines: Generic | (MCP adapters: FS/Git/HTTP/SQLite/Term)   │   │
  │  │  Plugins: Builtins | Loader   Providers: Mock | Claude | ...  │   │
  │  └────────────────────────────────────────────────────────────────┘   │
  │                              │                                        │
  │  ┌──────────────────────────┴────────────────────────────────────┐   │
  │  │                     DOMAIN — Entities + Value Objects           │   │
  │  │  Agent · Task · Capability · Security · Memory · Provider      │   │
  │  │  Workflow · Pipeline · MCP · Orchestration · Execution          │   │
  │  │  Discovery · Learning · Desktop · Events                       │   │
  │  └─────────────────────────────────────────────────────────────────┘  │
  │                                                                       │
  └───────────────────────────────────────────────────────────────────────┘
                             │
  ┌──────────────────────────┴────────────────────────────────────────────┐
  │                   INFRASTRUCTURE & SERVICES                            │
  │  Structured Logging · Prometheus Metrics · OpenTelemetry Tracing       │
  │  Desktop Services: Backup · Installer · Update · Diagnostics · Tray   │
  │  Platform Services: Windows Native · WSL2 · Docker · Registry         │
  └────────────────────────────────────────────────────────────────────────┘
```

---

## Hexagonal Architecture Pattern

AgenticOS follows strict **hexagonal (clean) architecture** with six layers:

| Layer | Directory | Responsibility | Depends On |
|-------|-----------|---------------|------------|
| **Domain** | `src/agentic_os/domain/` | Pure frozen dataclasses & StrEnums — state, no behavior beyond validation | Nothing |
| **Ports** | `src/agentic_os/ports/` | `Protocol` interfaces — contracts with zero implementation | Domain |
| **Core** | `src/agentic_os/core/` | Orchestration + subsystem logic — implements business rules | Ports, Domain |
| **Adapters** | `src/agentic_os/adapters/` | Concrete infrastructure — bus drivers, provider impls, engines | Ports |
| **API** | `src/agentic_os/api/` | FastAPI REST + WebSocket — user-facing top of the stack | Core (via Platform) |
| **Kernel** | `kernel.py` | Composition root — wires ports → concrete impls → `Platform` | Everything (only place) |

### Dependency Rule

> Source code dependencies always point **inward**. Nothing in an inner circle
> knows about anything in an outer circle.

```
Domain ← Ports ← Core ← Adapters ← API
                        ↑
                   Kernel (composition root — depends on all)
```

### Key Principle

The kernel (`kernel.py`) is the **only** file that imports both ports and
concrete adapters. If you need to swap Redis for NATS, or replace the in-memory
vector store with Pinecone, you change the kernel (or its config) — **zero**
business logic changes.

---

## Kernel & Bootstrap Process

The **`Kernel`** class (in `kernel.py`) is the composition root. It creates every
subsystem, wires dependencies, and exposes a frozen `Platform` bundle.

### Bootstrap Sequence

```
1. Kernel.__init__()
   ├── configure_logging() ── structlog, levels from Settings
   ├── build_bus(settings) ── LocalBus | RedisStreamsBus | NatsJetStreamBus
   ├── AgentRegistry, ProviderRegistry, Scheduler
   ├── Provider Management subsystem
   │   ├── ProviderManagerImpl, ModelManagerImpl
   │   ├── EncryptedSecretStore, ApiKeyVaultImpl
   │   ├── ProviderHealthMonitorImpl
   │   ├── CostTrackerImpl, RateLimitMonitorImpl
   │   └── ProviderRouter (latency | cost | round_robin)
   ├── Memory subsystem (in-memory store + vector + graph)
   ├── Security Framework (RBAC + workspace + approval + audit)
   ├── WorkflowEngine, PipelineEngine
   ├── Orchestrator, HealthMonitor, RecoveryManager
   ├── DashboardBroadcaster, MCPBroadcaster
   ├── CapabilityEngine
   ├── RuntimeManager (M1: Universal Execution Framework)
   ├── DiscoveryFramework (M2: 10 providers, validation, profiling)
   ├── OrchestrationFramework (M3: multi-agent orchestration)
   ├── MCPManager (M3: MCP runtime with registry, client, pool)
   ├── LearningManager (M5: Learning & Optimization Engine)
   └── DesktopRuntimeManager (M6: 28-subsystem desktop runtime)

2. Kernel.start()
   ├── bus.start()
   ├── load_plugins() ── discover and activate plugins
   ├── Seed providers, register models
   ├── Start orchestrator, scheduler, health, recovery
   ├── Start provider health monitoring, capability engine
   ├── Start dashboard & MCP WebSocket broadcasters
   ├── Initialize RuntimeManager + GenericExecutionEngine
   ├── Start DiscoveryFramework (auto-discovery + hot-reload)
   ├── Start OrchestrationFramework
   ├── Start MCPManager (initialize servers, health monitoring)
   ├── Start LearningManager
   └── Start DesktopRuntimeManager (if desktop_enabled)

3. run_serve()
   ├── Instantiate Kernel
   ├── await kernel.start()
   ├── Build FastAPI app from Platform bundle
   └── uvicorn.serve()
```

### Platform Bundle

The `Platform` dataclass is the single object handed to the API layer:

```python
@dataclass
class Platform:
    bus: EventBus
    registry: AgentRegistry
    providers: ProviderRegistry
    orchestrator: Orchestrator
    scheduler: Scheduler
    health: HealthMonitorImpl
    recovery: RecoveryManagerImpl
    dashboard: DashboardBroadcaster
    provider_mgr: ProviderManagerImpl
    model_mgr: ModelManagerImpl
    vault: ApiKeyVaultImpl
    provider_health: ProviderHealthMonitorImpl
    cost: CostTrackerImpl
    rate: RateLimitMonitorImpl
    router: ProviderRouter
    secret_store: EncryptedSecretStore
    memory: MemoryManagerImpl | None
    capability: CapabilityEngine | None
    security: SecurityFramework | None
    workflow: WorkflowEngineImpl | None
    pipeline: PipelineEngineImpl | None
    runtime: RuntimeManager | None
    discovery_framework: DiscoveryFramework | None
    orchestration: OrchestrationFramework | None
    mcp: MCPManager | None
    mcp_ws: MCPBroadcaster | None
    learning: LearningManager | None
    desktop: DesktopRuntimeManager | None
```

---

## Event Bus

One port (`EventBus` protocol), three interchangeable adapters, selected by the
`BUS_TYPE` environment variable:

```
┌──────────────────────────────────────────────┐
│              EventBus (Protocol)               │
│  start · stop · publish · subscribe · drain   │
└──────────┬──────────┬──────────────┬──────────┘
           │          │              │
     ┌─────┴────┐ ┌──┴───┐   ┌─────┴──────┐
     │ LocalBus  │ │ Redis│   │ NATS        │
     │ (in-proc) │ │Stream│   │ JetStream   │
     │ async io  │ │Bus   │   │ Bus         │
     └───────────┘ └──────┘   └─────────────┘
```

| Adapter | Use Case | Default |
|---------|----------|---------|
| **LocalBus** | In-process asyncio fan-out. Tasks tracked in set, cancelled on stop. | Dev / CI / single-process |
| **RedisStreamsBus** | Redis Streams — persistent, replayable, cross-process | Production (HA) |
| **NatsJetStreamBus** | NATS JetStream — alternative production backend | Production (opt-in) |

### Event Envelope

Every message on the bus is wrapped in an `EventEnvelope`:

```python
class EventEnvelope(BaseModel):
    id: str          # uuid4 hex
    type: str        # semantic type (e.g. "agent.started")
    source: str      # producer identifier
    topic: str       # canonical topic string
    timestamp: datetime
    payload: dict    # application data
```

### Topics

Topics are centralized in `domain/events.py` as a `StrEnum` with **120+
canonical values** covering:

- **Phase 1:** `task.*`, `agent.*`, `health.*`, `recovery.*`, `dashboard.*`
- **Phase 2:** `provider.*`, `memory.*`, `approval.*`, `audit.*`, `tool.*`, `cost.*`
- **Phase 3B:** `workflow.*` (14), `pipeline.*` (15), `plugin.*` (7)
- **Phase 4 M1:** `engine.*` (14) — execution engine lifecycle
- **Phase 4 M2:** `discovery.*` (16), `validation.*` (4), `profiling.*` (2)
- **Phase 4 M3 MCP:** `mcp.*` (18) — server, session, transport, resources, pool, capabilities
- **Phase 4 M3 Orchestration:** `orchestration.*` (50+) — swarm lifecycle, coordination, consensus, communication, planner, scheduler, supervisor, merger, validation, retry, recovery, checkpoints, metrics, agent selection
- **Phase 5:** `learning.*` (13) — execution recording, profiling, optimization, anomaly detection

---

## Desktop Runtime Composition

The Desktop Runtime comprises **28 subsystems** organized in three tiers:

### Tier 1 — Core Desktop Services (M6 Part 1)

| # | Subsystem | Module | Responsibility |
|---|-----------|--------|----------------|
| 1 | **Window Manager** | `window.py` | Multi-window lifecycle, focus, minimize, close, bounds management |
| 2 | **Workspace Manager** | `workspace.py` | Virtual desktops, tab management, workspace CRUD (count, list, create) |
| 3 | **Notification Service** | `notification.py` | Native OS notifications, toast display, action callbacks |
| 4 | **File Integration** | `file_integration.py` | File open/save dialogs, drag-and-drop file handling, file type associations |
| 5 | **Clipboard Service** | `clipboard.py` | Native clipboard read/write, format negotiation |
| 6 | **Terminal Integration** | `terminal.py` | Embedded terminal emulator, shell spawning, PTY management |
| 7 | **Process Manager** | `process.py` | Child process lifecycle, stdout/stderr capture, signal handling |
| 8 | **Desktop Logging** | `logging.py` | Desktop-specific structured logging, log rotation, file output |
| 9 | **Configuration Manager** | `configuration.py` | User preferences persistence, settings CRUD, defaults registry |
| 10 | **Diagnostics Manager** | `diagnostics.py` | System diagnostics, hardware info, crash reports |
| 11 | **Performance Monitor** | `performance.py` | CPU/memory/disk metrics, real-time monitoring, historical tracking |
| 12 | **Menu Manager** | `menu.py` | Application menus, context menus, default menu templates |
| 13 | **Drag & Drop Service** | `dragdrop.py` | Native drag-and-drop targets, MIME type handling, drop zones |
| 14 | **Local Database** | `database.py` | Local SQLite/sled database for persistent state, schema migration |
| 15 | **Event Publisher** | `publisher.py` | Dispatches desktop domain events onto the EventBus (`desktop.*`) |

### Tier 2 — Operational Layer (M6 Part 2)

| # | Subsystem | Module | Responsibility |
|---|-----------|--------|----------------|
| 16 | **Runtime Discovery** | `runtime_discovery.py` | Detects local runtimes (Docker, WSL, Python, Node) for desktop use |
| 17 | **Auto Update Manager** | `update.py` | GitHub Releases checking, downloading, checksum verification, installation |
| 18 | **Installer Manager** | `installer.py` | Package installation, MSI/DMG/AppImage generation, first-run setup |
| 19 | **First Run Wizard** | `first_run.py` | Onboarding flow, initial configuration, tour completion tracking |
| 20 | **Channel Manager** | `channel.py` | Update channel management (stable/beta/nightly), per-channel version pinning |
| 21 | **Rollback Manager** | `rollback.py` | Version state snapshots, rollback to previous version, database migration revert |
| 22 | **Portable Runtime** | `portable.py` | USB-drive / portable install mode, self-contained runtime bundle |
| 23 | **Offline Runtime** | `offline.py` | Offline/online state management, event queuing, sync on reconnect |
| 24 | **Backup Manager** | `backup.py` | Scheduled & manual backups, incremental/delta backup, restore |
| 25 | **Delta Update Engine** | `delta_update.py` | Binary diff (bsdiff) generation and application, patch-based updates |
| 26 | **Signature Verification** | `signature.py` | Code signing verification, GPG/Ed25519 signature validation |
| 27 | **Windows Platform** | `windows_platform.py` | Windows-specific: registry, shortcuts, start menu, context menu, taskbar |

### Tier 3 — Production Hardening (M6 Part 3)

| # | Subsystem | Module | Responsibility |
|---|-----------|--------|----------------|
| 28 | **Hardening Manager** | `hardening.py` | Startup validation, integrity checks, memory leak detection, thread monitoring, resource leak detection, self-diagnostics, recovery mode, heal/repair actions, graceful shutdown planning, cleanup orchestration |

---

## Desktop Runtime Manager (Composition Root)

The `DesktopRuntimeManager` (`core/desktop/manager.py`) is the **composition
root** for all 28 desktop subsystems. It:

1. **Owns** all subsystem instances (one field per subsystem)
2. **Wires** their cross-dependencies (e.g., Hardening → Performance Monitor)
3. **Manages lifecycle** — `start()` / `stop()` / `restart()` in the correct order
4. **Provides aggregate state** — `get_state()` collects status from all subsystems
5. **Exposes command palette** — 8 built-in command palette items for keyboard-driven navigation
6. **Registers keyboard shortcuts** — 8 default shortcuts (Cmd/Ctrl+N, W, S, B, P, F, Tab, M)
7. **Implements global search** — Searches workspaces and shortcuts

### Lifecycle

```
start()
  ├── hardening.validate_startup() — checks integrity, runs self-diagnostics
  ├── database.initialize() — opens local DB, runs migrations
  ├── workspace.create_workspace("Default") — if none exist
  ├── menu.create_menu(default menus)
  ├── Register 8 keyboard shortcuts
  └── publisher.publish_started() / publish_ready()

stop()
  ├── hardening.plan_shutdown() — graceful teardown plan
  ├── hardening.cleanup_resources() — release file handles, temp files
  ├── performance.stop_monitoring() — cease metrics collection
  ├── database.close() — flush and close local DB
  └── publisher.publish_stopped()
```

---

## Mission Control Frontend

**Mission Control** is the web-based dashboard — a Next.js 15 App Router SPA
with React 19, TypeScript, Tailwind CSS, and Zustand state management.

### Technology Stack

```
Next.js 15 (App Router) + React 19 + TypeScript
Tailwind CSS + Glassmorphism design system
Zustand (WebSocket-driven store)
React Flow (agent constellation, execution graphs)
Vitest (unit tests)
ESLint + Prettier (code quality)
```

### 15 Views

| # | View | File | Purpose |
|---|------|------|---------|
| 1 | **AI Brain** | `ai-brain.tsx` | Central intelligence: orbiting agents, pulse rings, real-time event visualization |
| 2 | **Agent Constellation** | `agent-constellation.tsx` | Live React Flow topology of all agents with supervisor links |
| 3 | **Execution Graph** | `execution-graph.tsx` | Task execution DAG with stage visualization |
| 4 | **Mission Overview** | `mission-overview.tsx` | High-level dashboard: active tasks, health, recent events |
| 5 | **Discovery Dashboard** | `discovery-dashboard.tsx` | Runtime discovery: providers, scan history, profiles, validation |
| 6 | **Provider Control Center** | `provider-control-center.tsx` | Provider config, health, models, API keys, cost tracking |
| 7 | **System Monitor** | `system-monitor.tsx` | Real-time system metrics, bus health, event throughput |
| 8 | **Task Timeline** | `task-timeline.tsx` | Chronological task history with status transitions |
| 9 | **Memory Explorer** | `memory-explorer.tsx` | Scoped memory inspection, search, vector recall |
| 10 | **Plugin Marketplace** | `plugin-marketplace.tsx` | Plugin discovery, install, update, config |
| 11 | **MCP Manager** | `mcp-manager.tsx` | MCP server CRUD, transport config, tool/resource browsing, version matrix |
| 12 | **Workspace Explorer** | `workspace-explorer.tsx` | File browser, workspace management |
| 13 | **Workflow Studio** | `workflow-studio.tsx` | Interactive DAG editor, node/edge CRUD, replay controls |
| 14 | **Pipeline Builder** | `pipeline-builder.tsx` | Stage pipeline editor, scheduling, retry policy config |
| 15 | **Swarm Dashboard** | `swarm-dashboard.tsx` | Multi-tab: Dashboard, Swarms, Agents, Tasks, Execution |

### Data Flow

```
EventBus (backend)
    │
    ▼
DashboardBroadcaster (api/dashboard.py)
MCPBroadcaster (api/mcp_ws.py)
    │
    ▼ WebSocket (/ws/dashboard, /ws/mcp)
    │
    ▼
Zustand store (lib/store.ts)
    │
    ├── Derives view-specific state
    ├── Consumes EventEnvelope topics
    └── Reactively updates 15 view components
```

---

## MCP Runtime Architecture

The Model Context Protocol (MCP) Runtime provides a universal server lifecycle
management layer. It is built in four layers:

```
┌──────────────────────────────────────────────────────────────┐
│                     MCP SDK (sdk/mcp/)                        │
│  ServerSdk · ToolSdk · ResourceSdk · PromptSdk · Auth ·     │
│  Config · Registration · Validation · Testing                │
├──────────────────────────────────────────────────────────────┤
│                  MCP Core Runtime (core/mcp/)                 │
│  Manager · Registry · Client · Pool · Security · Capability  │
│  ToolReg · ResourceReg · PromptReg · Version · Discovery     │
│  Health · Session · Telemetry                                │
├──────────────────────────────────────────────────────────────┤
│                    MCP Ports (ports/mcp.py)                    │
│  MCPRegistryPort (18 methods) · MCPTransportPort              │
├──────────────────────────────────────────────────────────────┤
│                    MCP Domain (domain/mcp.py)                  │
│  16 frozen dataclasses · 6 StrEnums · Zero external deps     │
└──────────────────────────────────────────────────────────────┘
```

### Core Components

| Component | Description |
|-----------|-------------|
| **MCPClient** (`client.py`, 751 lines) | Full transport implementation: stdio (subprocess), SSE (HTTP streaming), Streamable HTTP (POST+stream). Capability negotiation per MCP protocol `2024-11-05`. Auto-reconnect with exponential backoff (5 retries, base 1s, max 30s). |
| **MCPRegistryImpl** (`registry.py`) | In-memory async server CRUD with per-server `asyncio.Lock`, duplicate name detection, 6 EventBus lifecycle topics, tool caching, resource/prompt delegation, health caching, snapshot export. |
| **MCPManager** (`manager.py`) | Lifecycle orchestration: `initialize()` → `start()` → `shutdown()`. Periodic health monitoring with auto-restart (3 retry limit). Tool/resource/prompt discovery. Session tracking. Version & capability management. |
| **MCPSecurity** (`security.py`) | 20 authorization methods wrapping `SecurityFramework`. Fine-grained RBAC for every MCP operation: server lifecycle, tool invocation, resource read/subscribe, prompt list/get. |
| **MCPConnectionPool** (`pool.py`) | Connection pooling per server: configurable min/max connections, max idle time (5min), max lifetime (1hr), acquire timeout (30s). Health checking, automatic cleanup, graceful degradation. Statistics: wait times, error rates, per-server metrics. |

### Transport Support

| Transport | Description |
|-----------|-------------|
| **stdio** | Subprocess management with JSON-RPC over stdin/stdout. Full lifecycle: spawn → initialize → negotiate → invoke → shutdown. |
| **SSE** | HTTP Server-Sent Events for streaming server-sent messages. Long-lived HTTP connection with event stream parsing. |
| **Streamable HTTP** | HTTP POST with streaming response bodies. Full duplex communication over standard HTTP. |

### Adapter Framework (adapters/mcp/)

| Adapter | Tools | Description |
|---------|-------|-------------|
| **FilesystemAdapter** | 5 | read, write, list, file_info, search_files — path sandboxed |
| **GitAdapter** | 5 | status, log, diff, branches, commit — subprocess execution |
| **HTTPAdapter** | 4 | GET, POST, PUT, DELETE — SSL validation, timeout handling |
| **SQLiteAdapter** | 3 | query, statement, list_tables — write-statement detection |
| **TerminalAdapter** | 2 | command, script — command allowlisting |
| **DockerAdapter** | * | Docker container management |
| **PostgresAdapter** | * | PostgreSQL database operations |
| **GitHubAdapter** | * | GitHub API operations |

### Performance Benchmarks

| Operation | Avg Latency |
|-----------|-------------|
| MCPTool creation | 1 µs |
| MCPServerConfig.create_stdio() | 4 µs |
| MCPServerDetail creation | 1 µs |
| MCPTool.to_dict() | <1 µs |
| register_server (async) | 57 µs |
| get_server (async) | <1 µs |
| list_servers (100 entries) | 1 µs |
| MCPServerDetail.to_dict() | 7 µs |

---

## Swarm Engine Architecture

The Swarm Orchestration Engine provides multi-agent coordination through 12
specialized subsystems, all composed behind a single `OrchestrationFramework`
facade.

```
OrchestrationFramework (composition root)
  │
  ├── SwarmPlanner ───────── analyze_goal(), create_plan(), resolve_dependencies()
  ├── SwarmScheduler ─────── topological_sort() (Kahn's O(V+E)), dispatch()
  ├── SwarmSupervisor ────── monitor_execution(), detect_failure/deadlock(), restart()
  ├── AgentSelector ──────── weighted: 50% cap + 20% health + 15% latency + 15% status
  ├── TaskOrchestrator ───── goal decomposition (rule-based, template-based, LLM)
  ├── CoordinationEngine ─── 6 patterns (sequential, parallel, fan-out, fan-in, hierarchical, voting)
  ├── SwarmIntelligence ──── consensus (simple-majority, weighted), leader election
  ├── CommunicationBus ───── p2p messaging, broadcast, request-response over EventBus
  ├── ResultMerger ───────── 7 strategies (weighted, priority, consensus, voting, best-of-n, concat, semantic)
  ├── ValidationEngine ───── output, plan, security, policy validation with quality scoring
  ├── CheckpointManager ──── save/restore/list/delete execution snapshots
  ├── RetryManager ───────── exponential backoff (2x, 10% jitter), per-task exhaustion
  ├── FailureRecovery ────── task reassignment, plan rollback, checkpoint restore
  ├── MetricsEngine ──────── per-plan/agent/stage metrics, timelines, performance analysis
  ├── CostTracker ────────── estimate/track/query costs per agent and plan
  └── SwarmAgentRegistry ─── bridges RuntimeManager engines as swarm agents
```

### Topology Support

| Topology | Description |
|----------|-------------|
| **MESH** | Fully connected — every agent can communicate with every other agent |
| **STAR** | Central coordinator agent with leaf agents |
| **HIERARCHICAL** | Tree structure with parent-child delegation |
| **RING** | Agents arranged in a ring, each talking to their neighbors |

### Coordination Patterns

| Pattern | Behavior |
|---------|----------|
| **SEQUENTIAL** | Tasks execute one after another in schedule order |
| **PARALLEL** | All tasks execute concurrently |
| **FAN_OUT** | One task fans out to multiple agents |
| **FAN_IN** | Multiple agent results merge into one |
| **HIERARCHICAL** | Tree-structured with parent-child dependencies |
| **VOTING** | Agents vote on a decision; merged by consensus |

### REST API

48 endpoints at `/api/swarm/*` covering profiles, swarms, planner, scheduler,
supervisor, merge, validation, checkpoints, agent selection, metrics, cost,
recovery, retry, goals, plans, and tasks.

---

## Learning & Optimization Engine

The Learning & Optimization Engine (Phase 5, M5) analyzes execution patterns to
continuously improve system performance.

### Components

| Module | Purpose |
|--------|---------|
| `manager.py` | Lifecycle orchestration, data collection coordination |
| `history.py` | Execution history storage and query |
| `benchmark.py` | Benchmarking framework for model/provider comparison |
| `cost.py` | Cost analysis and optimization recommendations |
| `evaluation.py` | Execution quality evaluation and scoring |
| `experiment.py` | A/B experiment framework for routing decisions |
| `model_selection.py` | Model selection optimization based on task patterns |
| `optimization.py` | System-wide optimization strategies |
| `performance.py` | Performance tracking and trend analysis |
| `policy.py` | Learned routing and execution policies |
| `prompt.py` | Prompt optimization and template management |
| `publisher.py` | Learning event publishing onto the EventBus |
| `quality.py` | Quality metrics and monitoring |
| `recommendation.py` | Recommendation engine for proactive optimization |
| `routing.py` | Learned provider/model routing |
| `strategy.py` | Optimization strategy definitions |
| `swarm.py` | Swarm learning and coordination improvement |
| `telemetry.py` | Telemetry collection for model training |

### Event Topics

13 `learning.*` topics: execution recording, profile updates, recommendations,
benchmarking, predictions, pattern detection, knowledge extraction, routing
decisions, optimizations, anomaly detection, trend changes, experience recording.

---

## Security Framework

The Security Framework provides defense-in-depth through five integrated
subsystems:

```
SecurityFramework
  ├── RBAC (AccessControlImpl)
  │   ├── Roles: admin, operator, agent, auditor, guest
  │   ├── Deny-by-default — unknown capabilities denied
  │   └── Role→permission mapping
  ├── Workspace Isolation (WorkspaceIsolationImpl)
  │   ├── Per-agent sandboxed workspace root
  │   ├── .. traversal neutralized
  │   └── Workspace→agent mapping
  ├── Tool Permissions (ToolPermissionsImpl)
  │   ├── Capability-level permission checks
  │   ├── Sensitive capabilities flagged requires_approval
  │   └── Decision pipeline: RBAC → approval → audit
  ├── Approval Gate (ApprovalGateImpl)
  │   ├── Human-in-the-loop for sensitive actions
  │   ├── Pending → approve/deny lifecycle
  │   └── APPROVAL_REQUESTED / APPROVAL_DECIDED events
  └── Audit Log (AuditLogImpl)
      ├── Append-only trail of authz decisions
      ├── Queryable by principal
      └── REST: /api/security/audit

Secrets Management
  ├── EncryptedSecretStore (Fernet symmetric encryption)
  ├── ApiKeyVaultImpl — scoped per-provider key storage
  ├── Master key via AGENTIC_OS_MASTER_KEY env or key file
  └── Provider API keys encrypted at rest
```

### Authorization Pipeline

```
ToolRequest
  → RBAC.ac().allowed(principal, capability)
  → ToolPermissions.decision_for(principal, request)
    → Requires approval? → ApprovalGate.request() → human decides
  → AuditLog.record(entry)
  → Decision(allowed=True/False, reason)
```

---

## Plugin System

The Plugin System enables third-party extension through a loader, registry, and SDK.

### Architecture

```
Plugin System
  ├── Loader (adapters/plugins/loader.py)
  │   ├── Discovers plugins from configured directories
  │   ├── Builtins loader (adapters/plugins/builtins.py)
  │   └── Activates and wires into registry
  ├── Registry (core/plugin/registry.py)
  │   ├── Plugin registry with status tracking
  │   ├── Lifecycle management (install, uninstall, update)
  │   └── Health and capability tracking
  └── SDK (core/plugin/sdk.py)
      ├── PluginBase — abstract base class
      ├── AgentPlugin — custom agent implementations
      ├── ToolPlugin — custom tool providers
      ├── ProviderPlugin — AI provider adapters
      ├── MCPServerPlugin — MCP-compatible servers
      ├── WorkflowNodePlugin — custom workflow nodes
      ├── PipelineStagePlugin — custom pipeline stages
      ├── PluginValidator — manifest and code validation
      ├── PluginEventBus — scoped event bus for plugins
      └── PluginRegistryClient — marketplace integration
```

### Event Topics

7 `plugin.*` EventBus topics: installed, uninstalled, updated, started, stopped,
failed, health_changed, capability_registered.

---

## Provider Management

Provider Management handles AI provider lifecycle, routing, health, and secrets.

```
ProviderManager
  ├── ProviderManagerImpl — provider/config/model catalog
  ├── ModelManagerImpl — model registry per-provider
  ├── ProviderRouter
  │   ├── Routing policies: latency | cost | round_robin
  │   ├── Integration with ProviderHealthMonitor
  │   └── RateLimit integration
  ├── ProviderHealthMonitorImpl
  │   ├── Periodic health checks
  │   ├── Benchmarking support
  │   └── Health status: HEALTHY | DEGRADED | DOWN
  ├── ApiKeyVaultImpl
  │   ├── Fernet-encrypted key storage
  │   └── Scoped per-provider API keys
  ├── CostTrackerImpl
  │   ├── Per-provider cost accumulation
  │   └── Historical cost records
  ├── RateLimitMonitorImpl
  │   ├── Per-provider rate limit tracking
  │   └── Remaining quota queries
  └── Failover Policy
      ├── Automatic provider failover on health degradation
      └── configurable routing policy
```

---

## Recovery & Failover Mechanisms

### Recovery Manager

The `RecoveryManagerImpl` (`core/recovery.py`) handles automatic failure
recovery:

```
AGENT_FAILED event
  └─→ RecoveryManager._on_failed()
       └─→ handle_failure(agent, reason)
            ├─→ Check task attempt count
            ├─→ if attempts >= max_attempts:
            │    └─→ Mark task FAILED, agent FAILED, stop
            └─→ else:
                 ├─→ Mark agent RECOVERING
                 ├─→ Increment attempt count
                 └─→ orchestrator.dispatch_task(task) — retry
```

### MCP Auto-Recovery

- **Auto-restart**: Failed MCP servers auto-restarted up to 3 times
- **Backoff**: Exponential backoff (attempt × 5 seconds, max 30s)
- **Health monitoring**: Periodic checks with auto-restart on failure detection

### Orchestration Recovery

- **Checkpoint-based**: Save/restore execution snapshots
- **Retry Manager**: Exponential backoff with 10% jitter
- **Failure Recovery**: Task reassignment or full plan rollback
- **Deadlock Detection**: Cycle detection with timeout-based resolution

### Provider Failover

- **Router**: Automatic failover to next healthy provider when primary degrades
- **Health Monitor**: Detects degradation via periodic checks
- **Rate Limit**: Automatic routing away from rate-limited providers

---

## Offline Mode Architecture

The Offline Runtime Manager (`core/desktop/offline.py`) provides graceful
degradation when network connectivity is lost.

### States

```
ONLINE ──→ OFFLINE ──→ SYNCHRONIZING ──→ ONLINE
```

### Behavior

- **OFFLINE**: All outbound events queued in-memory `OfflineEvent` list
- **SYNCHRONIZING**: On reconnect, queued events replayed in order
- **ONLINE**: Normal operation, events flow immediately

### Components

| Component | Description |
|-----------|-------------|
| `OfflineState` | ONLINE, OFFLINE, SYNCHRONIZING enum |
| `OfflineConfig` | Configurable offline behavior settings |
| `OfflineEvent` | Queued event with type, payload, timestamp |
| **Queue** | In-memory FIFO list of pending events |
| **Sync Engine** | Batch replay on reconnect with ordering guarantees |

---

## Update System Architecture

The Auto Update Framework (`core/desktop/update.py`) provides end-to-end update
management from checking to installation.

### Pipeline

```
check_for_updates()
  ├── Query GitHub Releases API (api.github.com)
  ├── Filter by channel (stable, beta, nightly)
  ├── Parse release assets, checksums, release notes
  └── Return sorted ReleaseInfo list

download_update(manifest)
  ├── Download ZIP from asset URL to temp directory
  ├── Verify SHA-256 checksum
  └── Mark as ready for installation

install_update(manifest)
  ├── Apply update (in-memory: set current version)
  ├── Record in update history
  └── Return UpdateResult (success, duration, versions)
```

### Update Channels

| Channel | Description |
|---------|-------------|
| **STABLE** | Production releases (default) |
| **BETA** | Pre-release candidates |
| **NIGHTLY** | Daily builds from main branch |

### Integrity & Rollback

- **Signature Verification** (`signature.py`): Code signing verification with GPG/Ed25519
- **Rollback Manager** (`rollback.py`): Version state snapshots, DB migration revert
- **Delta Updates** (`delta_update.py`): Binary diff (bsdiff) for bandwidth-efficient updates
