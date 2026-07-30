# AgenticOS Roadmap

> **Current Version:** v1.0.0-rc1 (Release Candidate)
>
> AgenticOS is built incrementally. Interfaces are frozen once validated; each
> phase lands production-ready, fully tested, and documented. Every version tag
> represents a shippable milestone with zero regressions against previous phases.

---

## Version History

| Version | Date | Phase / Milestone | Key Deliverables |
|---------|------|-------------------|------------------|
| v0.1.0 | 2026-07-16 | Phase 1 Foundation | Hexagonal kernel, EventBus (Local/Redis/NATS), Planner→Dispatcher→Supervisor→Health→Recovery, plugin system, CI gates |
| v0.2.0 | 2026-07-17 | Phase 2 Core 4 Subsystems | Provider Management, Capability Engine, Memory System, Security Framework, REST API, ADRs 0006–0009 |
| v0.3.0 | 2026-07-17 | Phase 3A — Mission Control UI | Next.js 15 + React 19 SPA, 12 views, WebSocket dashboard, glassmorphism design, ⌘K palette |
| v0.4.0 | 2026-07-18 | Phase 3B — Backend Engines | Workflow Engine, Pipeline Engine, Observability Framework (OTel/Prometheus), MCP domain models, Plugin SDK, stress tests |
| v0.5.0 | 2026-07-18 | Phase 4 M1 — Execution Framework | Universal ExecutionEnginePort, RuntimeManager, CapabilityNegotiator, CompositeEngine, Generic adapter, 195 tests |
| v0.5.1 | 2026-07-18 | Phase 4 M2 — Discovery Framework | DiscoveryFramework, 10 providers, ValidationPipeline, ProfilingEngine, hot-reload, 616 tests |
| v0.6.0 | 2026-07-18 | Phase 4 M1–M3 Sync | Synchronized M1/M2/M3 baseline with OrchestrationFoundation, 294 orchestration tests, Python 3.14 |
| v0.7.0 | 2026-07-19 | Phase 4 M3 — MCP Runtime | MCP domain/ports/core/SDK, 5 adapters, 23 REST endpoints, WebSocket, 107 tests, sub-µs domain ops |
| v0.7.1 | 2026-07-19 | Phase 4 M3 — Patch | Bug fixes, ADRs 0011–0015, ARCHITECTURE.md update |
| v0.7.2 | 2026-07-19 | Phase 4 M3 — Patch | Registry fixes, SDK None-guards, 1526 tests pass |
| v0.8.0 | 2026-07-20 | Phase 4 M4 — Swarm Engine | Swarm SDK, 48 REST endpoints, 12 orchestration subsystems, 6 coordination patterns, 7 merge strategies, 14 test files |
| v0.9.0 | 2026-07-20 | Phase 5 — Learning Engine | Learning & Optimization Engine with 18 modules, 13 EventBus topics, telemetry/policy/recommendation |
| v0.9.1 | 2026-07-20 | Phase 4 M6 P1 — Desktop Foundation | Desktop Runtime Manager with 15 core subsystems (window, workspace, notification, file, clipboard, terminal, process, logging, config, diagnostics, performance, menu, dragdrop, database, publisher) |
| v0.9.2 | 2026-07-20 | Phase 4 M6 P2 — Desktop Operational | 12 additional subsystems (runtime discovery, update, installer, first run, channel, rollback, portable, offline, backup, delta update, signature, windows platform) |
| v0.9.3 | 2026-07-20 | Phase 4 M6 P3 — Hardening | DesktopHardeningManager: startup validation, integrity checks, memory leak detection, thread monitoring, self-diagnostics, recovery mode, heal/repair, shutdown planning |
| v0.9.4 | 2026-07-20 | Phase 4 M6 — Stabilization | Full desktop runtime integration, keyboard shortcuts, command palette, global search, lifecycle management |
| v1.0.0-rc1 | 2026-07-20 | Release Candidate | All Phase 1–5 features stabilized, 1500+ tests passing, zero known regressions |
| v1.0.0-rc2 | 2026-07-29 | Phase 6 — Runtime Discovery & AI Brain Registry | LocalDiscoveryService, BrainRegistry (canonical source of truth), BrainDiscoveryBridge, DashboardBroadcaster WebSocket fan-out, 14 brain.* events, Mission Control store synchronization, live runtime add/remove via WebSocket |
| v1.0.0-rc3 | 2026-07-29 | Phase 11 — Executive Intelligence | ExecutiveController (10 subscriptions), GoalManager (12 ops, 10 states), DecisionEngine (7-factor scoring + risk_factors + reasoning), ReflectionEngine (12-field analysis), ExecutiveMemory |
| v1.0.0-rc4 | 2026-07-29 | Phase 12 — Cognitive Intelligence | CognitiveController, WorldModel, KnowledgeGraph (BFS), StrategicPlanner, PredictionEngine, ExperienceReplay, EvaluationEngine, ImprovementPlanner, ObjectiveManager |
| v1.0.0-rc5 | 2026-07-29 | Phase 13 — Executive Orchestration | ExecutiveOrchestrator (world state, policies, resource allocation, mission supervision), 9 API endpoints, 12 executive.* events |
| v1.0.0-rc6 | 2026-07-29 | Phase 14 — Swarm Execution | SwarmCoordinator, ConsensusManager (4 types), SharedMissionMemory, DynamicRoleAssigner (8 roles), automatic failure recovery, 12 swarm.* events |
| v1.0.0-rc7 | 2026-07-30 | Phase 15 — Autonomous Ecosystem | EcosystemManager, CapabilityGraph (5 nodes/6 edges), CollaborationNetwork (EMA trust), EvolutionEngine (4 analyzers), TaskMarketplace (deterministic 6-factor bid selection), continuous self-optimization, 16 ecosystem.* events |
| v1.0.0-rc8 | 2026-07-30 | Phase 16 — Distributed Federation | ClusterController, ClusterFederationManager, DistributedBrainRegistry, GlobalMissionScheduler (9-factor), ClusterConsensusManager (5 types), FailoverEngine (5 triggers/5 actions), ClusterTopology, FederatedKnowledgeGraph, 14 cluster.* events, single-node backward compatible |
| v1.0.0-rc9 | 2026-07-30 | Pre-Phase 17 — Production Readiness Audit | Route ordering fix (swarm/history), version consistency (all files → rc9), documentation modernization (README/ARCHITECTURE/ROADMAP/CHANGELOG), cross-platform validation, 4733 tests passing, zero regressions |

### Cumulative Test Count

```
v0.1.0  →   50+ tests
v0.2.0  →  200+ tests
v0.3.0  →  350+ tests
v0.4.0  →  500+ tests
v0.5.0  →  672 tests
v0.5.1  → 1125 tests
v0.6.0  → 1419 tests
v0.7.0  → 1526 tests
v0.8.0  → 1540+ tests
v0.9.4  → 1550+ tests
v1.0.0-rc1 → 1550+ tests
v1.0.0-rc2 → 3600+ tests (Phase 6 discovery + brain registry)
v1.0.0-rc3 → 4200+ tests (Phase 11 executive intelligence)
v1.0.0-rc4 → 4400+ tests (Phase 12 cognitive intelligence)
v1.0.0-rc5 → 4450+ tests (Phase 13 executive orchestration)
v1.0.0-rc6 → 4550+ tests (Phase 14 swarm execution)
v1.0.0-rc7 → 4600+ tests (Phase 15 autonomous ecosystem)
v1.0.0-rc8 → 4700+ tests (Phase 16 distributed federation)
v1.0.0-rc9 → 4733 tests (Pre-Phase 17 production audit)
```

---

## ✅ Phase 1 — Foundation (v0.1.0)

**Duration:** Week 1, July 2026

### Goals
- Establish hexagonal kernel architecture
- Implement abstract EventBus with 3 adapters
- Build vertical slice: Planner → Dispatcher → Provider → Supervisor → Health → Recovery → Dashboard

### Deliverables
- **Hexagonal kernel** with clean domain/ports/core/adapters layering
- **EventBus** protocol with LocalBus, RedisStreamsBus, NatsJetStreamBus adapters
- **Planner** — task creation and planning logic
- **Dispatcher** — task dispatch to registered agents
- **Supervisor** — agent supervision and heartbeat monitoring
- **Health Monitor** — periodic health checks with degraded/failed detection
- **Recovery Manager** — automatic retry with configurable max attempts
- **WebSocket Dashboard** — `DashboardBroadcaster` streaming events to connected clients
- **Plugin system** — basic plugin loading and provider abstraction
- **CI gates** — ruff lint, format, pytest, type checking

### Key Decisions
- EventBus as frozen abstraction (ADR-0001)
- LocalBus for dev/CI, Redis for production (ADR-0002)
- EventEnvelope as uniform wire format (ADR-0003)
- Plugin discovery via entry points (ADR-0004)

---

## ✅ Phase 2 — Core 4 Subsystems (v0.2.0)

**Duration:** Week 2, July 2026

### Goals
- Implement the four core subsystems behind frozen port interfaces
- Expose REST control plane for all subsystems
- Achieve full integration test coverage

### Deliverables

#### Subsystem 1: Provider Management
- `ProviderManager` — provider and model catalog with config CRUD
- `ModelManager` — model registry per-provider
- `EncryptedSecretStore` — Fernet-encrypted API key storage
- `ApiKeyVault` — scoped per-provider key management
- `ProviderHealthMonitor` — periodic health checks, benchmarking
- `Router` — routing policies: latency, cost, round_robin
- `CostTracker` — per-provider cost accumulation
- `RateLimitMonitor` — per-provider rate limit tracking
- REST: `/api/providers`, `/api/provider-configs`, `/api/models`, `/api/provider-health`, `/api/cost`, `/api/rate-limits`, `/api/routing/policy`

#### Subsystem 2: Memory System
- `MemoryStore` — scoped memory (working, conversation, project, shared, long-term)
- `VectorStore` — brute-force cosine similarity search
- `KnowledgeGraph` — in-memory adjacency graph
- `MemoryManager` — composition root with retention policies (TTL + max-size)
- Event topics: MEMORY_WRITTEN, MEMORY_EVICTED
- REST: `/api/memory/*`

#### Subsystem 3: Capability Engine
- `CapabilityRegistry` — 11 built-in capabilities
- `AgentComposer` — intent → capability → agent composition
- Sensitive capabilities flag `requires_approval`
- REST: `/api/capabilities`, `/api/agents/compose`, `/api/agents/compose-for-task`

#### Subsystem 4: Security Framework
- `RBAC` — roles (admin, operator, agent, auditor, guest), deny-by-default
- `WorkspaceIsolation` — per-agent sandboxed workspace, .. traversal neutralised
- `ToolPermissions` — capability-level permission checks
- `ApprovalGate` — human-in-the-loop for sensitive actions
- `AuditLog` — append-only authorization trail
- Secrets management over encrypted store
- REST: `/api/security/*`
- ADRs 0006–0009

---

## ✅ Phase 3 — Mission Control Platform (v0.3.0 – v0.4.0)

**Duration:** Week 3, July 2026

### 3A — Mission Control UI Framework (v0.3.0)

#### Deliverables
- **Next.js 15 App Router + React 19 + TypeScript** SPA
- **Glassmorphism** design system with dark/light theming
- **Command palette** (⌘K) with keyboard-driven navigation
- **120Hz smooth motion** animations
- **AI Brain** centerpiece — orbiting agents and pulse rings driven by real EventBus events
- **Agent Constellation** — live React Flow topology from real agent/task maps
- **Execution Graph** — task stage visualization
- **Provider Control Center** — provider config, health, models, API keys
- **System Monitor** — real-time metrics, bus health, event throughput
- **Task Timeline** — chronological task history
- **Memory Explorer** — scoped memory inspection and search
- **Plugin Marketplace** — plugin discovery and install
- **MCP Manager** — MCP server configuration
- **Workspace Explorer** — file browser
- **Workflow Studio** — interactive DAG editor (local-only, persistence in 3B)
- **Pipeline Builder** — stage pipeline editor (local-only, persistence in 3B)
- **Zustand** WebSocket-driven store consuming `/ws/dashboard`
- **ADR 0010** — Mission Control UI architecture

### 3B — Backend Engines (v0.4.0)

#### Deliverables
- **Workflow Engine** — DAG-based execution with:
  - Topological sort execution ordering
  - Versioning with full history
  - Replay from any node
  - Approval gates (START/END/AGENT/TOOL/LLM/CONDITION/PARALLEL/APPROVAL/SUBWORKFLOW node types)
  - 14 workflow.* EventBus topics
  - Full CRUD via REST API
- **Pipeline Engine** — stage-based execution with:
  - Cron-like scheduling
  - Retry policies with exponential backoff
  - Rollback to previous execution
  - Parallel stage execution
  - 15 pipeline.* EventBus topics
  - Full CRUD via REST API
- **Observability Framework**:
  - `InMemoryTracing` — W3C TraceContext propagation, span hierarchies, OTel-compatible API
  - `InMemoryMetrics` — counters, gauges, histograms, Prometheus export format
  - `InMemoryStructuredLogging` — structured log entries with correlation context
  - `TraceContextPropagator` — W3C traceparent/tracestate inject/extract
- **MCP Framework** (domain/ports):
  - Domain models: MCPServerConfig, MCPTool, MCPResource, MCPPrompt
  - Port interfaces: MCPRegistryPort, MCPTransportPort
- **Plugin SDK**:
  - PluginBase, AgentPlugin, ToolPlugin, ProviderPlugin, MCPServerPlugin
  - WorkflowNodePlugin, PipelineStagePlugin
  - PluginValidator, PluginEventBus, PluginRegistryClient
  - Template generator and manifest helpers
- **Stress/Benchmark tests**: 30 tests covering concurrency (5/10/25), large workflows (50-node chain), large pipelines (50-stage chain), observability load (5000 spans, 1000 metrics, 1000 logs)
- **ADR 0005** — Observability architecture

---

## ✅ Phase 4 — MCP & Swarm (v0.5.0 – v0.8.0)

**Duration:** Week 4, July 2026

### Milestone 1: Universal Execution Engine Framework (v0.5.0)

The foundation that transforms AgenticOS into a universal execution platform.

#### Domain Models (`domain/execution.py`)
- 12 frozen dataclass entities: ExecutionEngine, ExecutionSession, ExecutionResult, ExecutionHealth, ExecutionMetrics, ExecutionBenchmark, ExecutionConfiguration, ExecutionProfile, ExecutionCapability, ExecutionTelemetry, ExecutionWorkspace, ExecutionEvent, EngineRegistry
- 6 StrEnums: EngineType, EngineStatus, EngineCapability, EngineHealthStatus, ExecutionStatus, ExecutionEventType

#### Port Interfaces (`ports/execution.py`)
- `ExecutionEnginePort` — ~22 method universal interface
- `RuntimeManagerPort` — high-level orchestration
- `DiscoveryProvider` — engine scanning
- Input DTOs: EngineRegistration, EngineUpdate, ExecutionRequest, ExecutionQuery, EngineSummary, EngineDetail

#### Core Implementation
- `ExecutionEngineBase` + `CompositeEngine` — abstract base with default implementations, composite for fallback/load-balancing/routing
- `CapabilityNegotiator` — scored matching: required capabilities weighted 10x, confidence-based filtering, TTL cache
- `RuntimeRegistryImpl` — in-memory CRUD, per-engine locks, health caching, session tracking, EventBus emissions
- `DiscoveryEngine` — multi-provider orchestration, deduplication (highest confidence wins)
- `RuntimeManager` — high-level subsystem: lifecycle, execution routing, health checks, benchmark, session tracking

#### Adapters
- `GenericExecutionEngine` — reference adapter: echo/ping/sleep/info/fail
- `PathDiscovery` — scans system PATH for AI executables

#### Integration
- 12 REST API endpoints at `/api/runtime/*`
- 14 `engine.*` EventBus topics
- 195 tests, all passing (672 cumulative)

### Milestone 2: Automatic Runtime Discovery & Binding (v0.5.1)

#### Discovery Framework (`core/discovery/`)
- `DiscoveryFramework` — main orchestrator wrapping M1 DiscoveryEngine
- `DiscoveryRegistry` — provider registry with per-provider configs
- `DiscoveryCache` — TTL-based dedup with max-entries eviction
- `DiscoveryScheduler` — periodic per-profile scanning
- `DiscoveryTelemetry` — scan metrics, history, aggregated stats
- `DiscoveryConfiguration` — profile and rule management
- `ValidationPipeline` — 6 validators: ExecutableExists, VersionDetect, HealthCheck, CapabilityMatch, Permission, Integrity
- `ProfilingEngine` — auto-generates ExecutionProfile from engine metadata
- `DiscoveryEventPublisher` — EventBus emissions for lifecycle events

#### 10 Discovery Providers
1. **PathDiscovery** — scans system PATH for known executables
2. **WindowsRegistryDiscovery** — queries Windows Registry for installed tools
3. **WslDiscovery** — detects WSL2 distributions and Linux tools
4. **DockerDiscovery** — discovers Docker containers and images
5. **FilesystemDiscovery** — scans configured directories
6. **KnownInstallDirDiscovery** — checks well-known install locations
7. **ConfigFileDiscovery** — reads JSON/YAML/TOML configuration files
8. **EnvVarDiscovery** — detects engines from environment variables
9. **VSCodeDiscovery** — detects VS Code extensions and tools
10. **JetBrainsDiscovery** — detects JetBrains IDE plugins and tools

#### Integration
- 18 REST API endpoints: provider management, scan, cache, history, stats, profiles, validation, profiling, hot-reload
- Mission Control Discovery Dashboard (tabbed: Dashboard, History, Profiles, Validation)
- 21 new EventBus topics (16 discovery.*, 3 validation.*, 2 profiling.*)
- 616 tests (1125 cumulative)

### Milestone 3: MCP Runtime Foundation (v0.7.0)

#### Domain Models (`domain/mcp.py`)
- 16 frozen dataclass entities, 6 StrEnums, 621 lines, zero external dependencies
- MCPTool, MCPToolResult, MCPResource, MCPResourceTemplate, MCPPrompt, MCPRoot
- MCPPermissionMapping, MCPServerConfig (factory methods for stdio/SSE/HTTP)
- MCPServerDetail (rich lifecycle with timestamps, restart count, health)
- MCPRegistry (immutable collection with `get_server_by_name`, `with_server`/`without_server`)
- MCPSession, MCPSubscription, MCPCapability
- MCPTransport, MCPServerStatus, MCPHealthStatus, MCPSessionStatus

#### Port Interfaces (`ports/mcp.py`)
- MCPRegistryPort — 18 abstract methods (CRUD, lifecycle, tools, health, permissions, snapshots)
- MCPTransportPort — connect/disconnect/session management
- Input DTOs: MCPServerCreate, MCPServerUpdate, MCPToolInvoke

#### Core Runtime (`core/mcp/`)
- **Registry** — in-memory async CRUD, per-server locks, duplicate detection, 6 EventBus lifecycle topics
- **Client** (748 lines) — stdio, SSE, Streamable HTTP transports; capability negotiation; auto-reconnect
- **Manager** — lifecycle orchestration, health monitoring (periodic + auto-restart), session tracking
- **Security** — 20 authorization methods wrapping SecurityFramework

#### Adapter Framework (`adapters/mcp/`)
- 5 production adapters: Filesystem (5 tools), Git (5 tools), HTTP (4 tools), SQLite (3 tools), Terminal (2 tools)

#### SDK (`sdk/mcp/`)
- 9 modules: McpServerSdk, ToolSdk, ResourceSdk, PromptSdk, McpAuthHelper, McpConfigHelper, RegistrationHelper, McpValidator, McpTestHelper
- FakeMCPRegistry, FakeMCPManager for testing

#### Integration
- 23 REST API endpoints at `/api/mcp/*`
- WebSocket endpoint `/ws/mcp` — 20 MCP topics streamed in real-time
- 18 MCP-specific EventBus topics
- 107 MCP-specific tests (67 domain, 40 registry)
- Performance: domain ops <5 µs, registry ops <60 µs, serialization <10 µs
- ADRs 0011–0015 for detailed design rationale

### Milestone 4: Swarm Orchestration Engine (v0.8.0)

#### Domain Models (`domain/orchestration.py`)
- 30+ frozen dataclass entities: SwarmSpec, AgentTask, OrchestrationPlan, ConsensusResult, ExecutionStage, etc.
- 11 StrEnums: SwarmTopology, AgentRole, CoordinationPattern, ConsensusStatus, etc.

#### 12 Core Subsystems (`core/orchestration/`)
1. **OrchestrationFramework** — composition root wiring all subsystems
2. **SwarmManager** — swarm CRUD, membership, leader election
3. **TaskOrchestrator** — goal decomposition (rule-based + template-based + LLM)
4. **SwarmPlanner** — goal analysis, dependency resolution, parallelization
5. **SwarmScheduler** — topological sort (Kahn's O(V+E)), agent assignment, dispatch
6. **SwarmSupervisor** — monitoring, failure/deadlock detection, restart/reassign
7. **AgentSelector** — weighted scoring: 50% capability, 20% health, 15% latency, 15% status
8. **SwarmIntelligenceEngine** — consensus (simple-majority + weighted voting), leader election
9. **CoordinationEngine** — 6 patterns (sequential, parallel, fan-out, fan-in, hierarchical, voting)
10. **CommunicationBus** — inter-agent messaging (p2p, broadcast, request-response over EventBus)
11. **ResultMerger** — 7 merge strategies (weighted, priority, consensus, voting, best-of-n, concatenate, semantic)
12. **ValidationEngine** — output, plan, security, policy validation with quality scoring

#### Supporting Infrastructure
- CheckpointManager — save/restore/list/delete execution snapshots
- RetryManager — exponential backoff (2x, 10% jitter), exhaustion tracking
- FailureRecovery — task/plan recovery from checkpoints, rollback
- MetricsEngine + CostTracker + PerformanceAnalyzer
- OrchestrationTelemetry — event ring buffer, per-agent/per-swarm stats
- OrchestrationEventPublisher — 50+ swarm/orchestration lifecycle events
- 2 strategy modules (consensus: SimpleMajority, Weighted; decomposition: RuleBased, TemplateBased, LLM)

#### Integration
- 48 REST API endpoints at `/api/swarm/*` (profiles, swarms, planner, scheduler, supervisor, merge, validation, checkpoints, agent selection, metrics, cost, recovery, retry, goals, plans, tasks)
- 50+ orchestration-specific EventBus topics
- Swarm SDK: SwarmClient with create_swarm, run_goal, get_plan, cancel_plan, list_swarms
- Mission Control Swarm Dashboard (multi-tab: Dashboard, Swarms, Agents, Tasks, Execution)
- 12 orchestration configuration settings
- 14 orchestration/swarm test files

---

## ✅ Phase 4 — Production Desktop (v0.9.0 – v1.0.0-rc1)

**Duration:** Week 5, July 2026

### Milestone 5: Learning & Optimization Engine (v0.9.0)

The Learning & Optimization Engine analyzes execution patterns to continuously
improve system performance, provider selection, and routing decisions.

#### 18 Modules (`core/learning/`)
| Module | Purpose |
|--------|---------|
| **manager.py** | Lifecycle orchestration, data collection coordination |
| **history.py** | Execution history storage and query |
| **benchmark.py** | Benchmarking framework for model/provider comparison |
| **cost.py** | Cost analysis and optimization recommendations |
| **evaluation.py** | Execution quality evaluation and scoring |
| **experiment.py** | A/B experiment framework for routing decisions |
| **model_selection.py** | Model selection optimization based on task patterns |
| **optimization.py** | System-wide optimization strategies |
| **performance.py** | Performance tracking and trend analysis |
| **policy.py** | Learned routing and execution policies |
| **prompt.py** | Prompt optimization and template management |
| **publisher.py** | Learning event publishing onto the EventBus |
| **quality.py** | Quality metrics and monitoring |
| **recommendation.py** | Recommendation engine for proactive optimization |
| **routing.py** | Learned provider/model routing |
| **strategy.py** | Optimization strategy definitions |
| **swarm.py** | Swarm learning and coordination improvement |
| **telemetry.py** | Telemetry collection for model training |

#### Event Topics
13 `learning.*` EventBus topics: execution_recording, profile_updated,
recommendation_generated, recommendation_applied, benchmark_completed,
prediction_made, pattern_detected, knowledge_extracted, routing_decision,
optimization_applied, anomaly_detected, trend_changed, experience_recorded.

### Milestone 6 Part 1: Desktop Runtime Foundation (v0.9.1)

The Desktop Runtime provides native OS integration for AgenticOS, enabling
window management, workspace organization, file system access, and more.

#### 15 Core Desktop Subsystems

| # | Subsystem | Responsibility |
|---|-----------|----------------|
| 1 | **Window Manager** | Multi-window lifecycle, focus, minimize, close, bounds |
| 2 | **Workspace Manager** | Virtual desktops, tab management, workspace CRUD |
| 3 | **Notification Service** | Native OS notifications, toast display, action callbacks |
| 4 | **File Integration** | File open/save dialogs, drag-and-drop, file type associations |
| 5 | **Clipboard Service** | Native clipboard read/write, format negotiation |
| 6 | **Terminal Integration** | Embedded terminal, shell spawning, PTY management |
| 7 | **Process Manager** | Child process lifecycle, stdout/stderr capture, signals |
| 8 | **Desktop Logging** | Desktop-specific structured logging, log rotation, file output |
| 9 | **Configuration Manager** | User preferences persistence, settings CRUD, defaults |
| 10 | **Diagnostics Manager** | System diagnostics, hardware info, crash reports |
| 11 | **Performance Monitor** | CPU/memory/disk metrics, real-time monitoring, history |
| 12 | **Menu Manager** | Application menus, context menus, default templates |
| 13 | **Drag & Drop Service** | Native drag-and-drop targets, MIME type handling, drop zones |
| 14 | **Local Database** | Local SQLite/sled database for persistent state, migrations |
| 15 | **Event Publisher** | Desktop domain events → EventBus (`desktop.*` topics) |

### Milestone 6 Part 2: Desktop Operational Layer (v0.9.2)

#### 12 Additional Operational Subsystems

| # | Subsystem | Responsibility |
|---|-----------|----------------|
| 16 | **Runtime Discovery** | Detects local runtimes (Docker, WSL, Python, Node) |
| 17 | **Auto Update Manager** | GitHub Releases checking, download, checksum, install |
| 18 | **Installer Manager** | Package installation, MSI/DMG/AppImage, first-run setup |
| 19 | **First Run Wizard** | Onboarding flow, initial configuration, tour tracking |
| 20 | **Channel Manager** | Update channels (stable, beta, nightly), version pinning |
| 21 | **Rollback Manager** | Version snapshots, DB migration revert, rollback |
| 22 | **Portable Runtime** | USB-drive mode, self-contained runtime bundle |
| 23 | **Offline Runtime** | Offline/online state, event queuing, sync on reconnect |
| 24 | **Backup Manager** | Scheduled/manual backups, incremental, restore |
| 25 | **Delta Update Engine** | Binary diff (bsdiff), patch-based updates |
| 26 | **Signature Verification** | Code signing, GPG/Ed25519 signature validation |
| 27 | **Windows Platform** | Registry, shortcuts, start menu, taskbar, context menu |

### Milestone 6 Part 3: Production Hardening (v0.9.3)

| # | Subsystem | Responsibility |
|---|-----------|----------------|
| 28 | **Hardening Manager** | Startup validation, integrity checks, memory leak detection, thread monitoring, resource leak detection, self-diagnostics, recovery mode, heal/repair, shutdown planning, cleanup orchestration |

#### Hardening Capabilities
- **StartupValidation** — validates environment, configuration, and dependencies on boot
- **IntegrityCheck** — file integrity verification via checksums
- **MemoryLeakDetection** — baseline and periodic memory usage comparison
- **ThreadMonitoring** — active thread count, stuck thread detection
- **ResourceUsage** — CPU, memory, disk, handle counts with alerts
- **SelfDiagnostics** — comprehensive system health report
- **RecoveryMode** — safe-mode startup with minimal subsystems
- **Heal/Repair** — automatic repair of corrupted configuration, missing files
- **ShutdownPlanning** — graceful teardown with resource cleanup, timeout enforcement

### Desktop Runtime Manager Integration (v0.9.4)

- `DesktopRuntimeManager` as composition root for all 28 subsystems
- Keyboard shortcuts: 8 default (Cmd/Ctrl+N, W, S, B, P, F, Tab, M)
- Command palette: 8 built-in items
- Global search: cross-workspace, cross-shortcut
- Lifecycle management: start/stop/restart in dependency order
- Aggregate state reporting: all subsystems → unified state
- Event publishing: workspace created, started, ready, stopped

### v1.0.0-rc1 — Release Candidate

All Phase 1–5 features stabilized. Desktop Runtime complete with 28 subsystems.
Comprehensive integration testing. Zero known regressions. API surface frozen
for v1.0.0.

---

## 🚀 Future Plans

### v1.0.0 — Production Release

- All RC bugs resolved
- Performance profiling and optimization
- Production deployment documentation
- Tauri-based native desktop shell
- Windows/macOS/Linux installers
- CI/CD pipeline for automated releases

### v1.1.0 — Ecosystem & Extensions

- **Plugin Marketplace** — discoverable, signed community plugins with version management
- **Provider Framework SDKs** — formalized `PROVIDER_SDK.md`, `CAPABILITY_SDK.md`, `PLUGIN_SDK.md` for third-party extension
- **Multi-tenant isolation** — workspace-scoped tenancy with policy boundaries
- **Long-term memory persistence** — production vector DB (Pinecone, Qdrant) + graph DB (Neo4j) behind existing memory ports
- **LLM-powered orchestration** — LLM-based goal decomposition and coordination strategy selection
- **Advanced scheduling** — Cron-based pipeline scheduling, deferred execution, SLA monitoring
- **Observability dashboards** — Pre-built Grafana dashboards for Prometheus metrics and OTel traces
- **Mobile companion** — React Native app for monitoring and approvals on-the-go

---

## Documentation Backlog

The following documentation files are planned but not yet written:

- `PROVIDER_SDK.md` — Provider adapter development guide
- `CAPABILITY_SDK.md` — Custom capability development guide
- `PLUGIN_SDK.md` — Plugin development guide
- `EVENT_SCHEMA.md` — Complete event topic reference
- `docs/api/` — Generated API reference documentation
- `docs/ui/` — Mission Control UI component documentation
- `docs/c4/` — Updated C4 architecture diagrams
