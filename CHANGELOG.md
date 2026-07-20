# Changelog

All notable changes to AgenticOS are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/) and this project adheres to
[Semantic Versioning](https://semver.org/).

## [0.8.0] — 2026-07-20

### Added — Phase 4, Milestone 4: Swarm Orchestration Engine

- **Swarm SDK** (`sdk/swarm/`) — `SwarmClient` class with create_swarm, run_goal,
  get_plan, cancel_plan, list_swarms, get_swarm, delete_swarm methods.
- **Mission Control Swarm Dashboard** (`apps/mission-control/`) — Multi-tab view
  (Dashboard, Swarms, Agents, Tasks, Execution) with real-time metrics,
  agent lists, task queues, and execution plan monitoring.
- **Swarm types + API client** — Full frontend type definitions and API client
  methods for all 48 swarm REST endpoints.
- **Navigation** — "Swarm Orchestration" entry in the Mission Control sidebar
  (core group) with globe icon.

### Enhanced — Swarm Orchestration Backend

- **REST API** — 48 endpoints at `/api/swarm/*` (profiles, swarms, planner,
  scheduler, supervisor, merge, validation, checkpoints, agent selection,
  metrics, cost, recovery, retry, goals, plans, tasks).
- **Swarm Intelligence** — Consensus engine with simple-majority and weighted
  voting, leader election, 6 coordination patterns.
- **Validation Pipeline** — Output, plan, security, policy validation with
  quality scoring.
- **Result Merger** — 7 merge strategies (weighted, priority, consensus,
  voting, best-of-n, concatenate, semantic).
- **Recovery & Resilience** — Checkpoint-based recovery, retry with exponential
  backoff, failure/deadlock detection, task reassignment.
- **Metrics & Cost** — Per-plan/agent/stage cost tracking, timeline recording,
  performance analysis.
- **Swarm Agent Registry** — Bridges RuntimeManager engines as swarm agents,
  capability-based agent matching.
- **EventBus** — 50+ swarm-specific topics (swarm lifecycle, coordination,
  consensus, communication, planner, scheduler, supervisor, merger, validation,
  retry, recovery, checkpoint, metrics, agent selection).
- **Tests** — 14 orchestration/swarm test files covering all subsystems.
- **Configuration** — 12 orchestration settings in config.py.

## [0.7.0] — 2026-07-19

### Added — Phase 4, Milestone 3: MCP Runtime Foundation

**MCP Domain Models** (`domain/mcp.py`) — 16 frozen dataclass entities, 6 StrEnums
- MCPTool, MCPToolResult, MCPResource, MCPResourceTemplate, MCPPrompt, MCPRoot
- MCPPermissionMapping, MCPServerConfig (with factory methods for stdio/SSE/HTTP transports)
- MCPServerDetail (rich lifecycle including started_at/stopped_at/restart_count/health)
- MCPRegistry (immutable collection with get_server_by_name, with_server/without_server)
- MCPSession, MCPSubscription, MCPCapability
- MCPTransport, MCPServerStatus, MCPHealthStatus, MCPSessionStatus (StrEnums)
- 621 lines, zero external dependencies

**MCP Port Interfaces** (`ports/mcp.py`) — 2 runtime-checkable Protocols
- MCPRegistryPort — 18 abstract methods (CRUD, lifecycle, tools, health, permissions, snapshots)
- MCPTransportPort — connect/disconnect/session management
- MCPServerCreate, MCPServerUpdate, MCPToolInvoke input DTOs

**MCP Core Runtime** (`core/mcp/`) — 4 modules, 2,165 lines
- **Registry** (`registry.py`) — MCPRegistryImpl with in-memory persistence, duplicate name detection,
  per-server async locks, 6 EventBus lifecycle topics, tool caching, resource/prompt delegation
- **Client** (`client.py`) — Full stdio (subprocess), SSE, and Streamable HTTP transport support.
  Capability negotiation, auto-reconnect, 748 lines.
- **Manager** (`manager.py`) — MCPManager: lifecycle orchestration, periodic health monitoring with auto-restart,
  tool/resource/prompt discovery, session tracking, 27 public methods
- **Security** (`security.py`) — MCPSecurity: 20 authorization methods wrapping SecurityFramework.
  Fine-grained RBAC for every MCP operation.

**MCP Adapter Framework** (`adapters/mcp/`) — 6 modules, 1,663 lines
- **BaseMCPAdapter** — abstract base with lifecycle, health, discovery, prompting defaults
- **FilesystemAdapter** — 5 tools (read, write, list, file_info, search_files), path sandboxing
- **GitAdapter** — 5 tools (status, log, diff, branches, commit), subprocess execution
- **HTTPAdapter** — 4 tools (GET, POST, PUT, DELETE), SSL validation, timeout handling
- **SQLiteAdapter** — 3 tools (query, statement, list_tables), write-statement detection
- **TerminalAdapter** — 2 tools (command, script), command allowlisting

**MCP SDK** (`sdk/mcp/`) — 9 modules, 1,595 lines
- McpServerSdk — high-level developer-facing server builder
- ToolSdk, ResourceSdk, PromptSdk — fluent builder interfaces
- McpAuthHelper, McpConfigHelper, RegistrationHelper — convenience wrappers
- McpValidator — input validation against MCP protocol
- McpTestHelper, FakeMCPRegistry, FakeMCPManager — testing utilities

**MCP REST API** — 23 endpoints at `/api/mcp/`
- Server CRUD (list, get, register, update, delete)
- Server lifecycle (start, stop, restart, reload)
- Tool operations (list, discover, call)
- Resource operations (list, read, subscribe, unsubscribe)
- Prompt operations (list, get)
- Health & monitoring (server health, health summary)
- Sessions (list), Permissions (set, get)
- WebSocket endpoint at `/ws/mcp` — 20 MCP topics streamed in real-time

**MCP WebSocket Broadcaster** (`api/mcp_ws.py`) — MCPBroadcaster fans 20 MCP-specific
EventBus topics to connected Mission Control clients.

**Integration**
- 18 MCP-specific EventBus topics (registration, lifecycle, health, tools, permissions,
  sessions, resources, transport, capabilities)
- Platform bundle integration via `platform.mcp` and `platform.mcp_ws`
- 107 MCP-specific tests (domain: 67, registry: 40)

### Fixed

- `registry.py` — Duplicate server name detection now raises ValueError
- `registry.py` — Lazy import of MCPClient moved to module level (no circular deps)
- `domain/mcp.py` — `with_status()` correctly sets `started_at` on RUNNING transition and
  clears `stopped_at` for clean restart semantics
- `get_tools()` now returns `[]` for missing servers (consistent with `get_permissions`/`get_health`)
- SDK `auth.py`, `server.py`, `testing.py` — Removed 5 unused imports
- `core/mcp/__init__.py` — Created (was missing)

### Performance (benchmarked)

| Operation | Avg latency |
|-----------|-----------|
| MCPTool() creation | 1 µs |
| MCPServerConfig.create_stdio() | 4 µs |
| MCPServerDetail() creation | 1 µs |
| MCPTool.to_dict() | <1 µs |
| register_server (async) | 57 µs |
| get_server (async) | <1 µs |
| list_servers (100 entries, async) | 1 µs |
| MCPServerDetail.to_dict() | 7 µs |

## [0.7.2] — 2026-07-19

### Fixed — MCP Runtime bug fixes

- `registry.py` — `MCPClient` import moved from lazy inside `start_server()` to
  module level, enabling proper async mocking in tests (regression from 0.7.0).
- `registry.py` — `get_tools()` returns `[]` instead of raising `KeyError` for
  missing servers, matching the behavior of `get_permissions()` and `get_health()`.
- `domain/mcp.py` — `with_status()` now correctly sets `started_at` on both
  `STARTING` and `RUNNING` transitions; clears `stopped_at` on `RUNNING` for clean
  restart semantics.
- SDK `auth.py`, `server.py`, `testing.py` — Removed unused imports.
- SDK `registration.py` — Added None-guards on `_registry` for `unregister()` and
  `list_registered()`.
- All 1526 tests pass (zero regressions).

### Added — Documentation

- **ADRs 0011–0015** — MCP Runtime Architecture, Session Lifecycle, Tool Registry,
  Connection Pool, and SDK Architecture decision records.
- **ARCHITECTURE.md** — MCP Runtime Foundation section with full component table,
  architecture layers diagram, and performance metrics.
- **README.md** — MCP Runtime and SDK feature bullets, updated status line and
  roadmap.

## [0.6.0] — 2026-07-18

### Added — Phase 4: Universal Execution Framework (Milestones 1–3)

This release synchronizes three Phase 4 milestones into a single, validated
baseline. All M1 and M2 code has been present in the working tree; this commit
establishes the canonical release tag.

**Phase 4, Milestone 1** — Universal Execution Engine Framework
- Domain models (`domain/execution.py`) — 12 dataclass entities, 6 StrEnums
- Port interfaces (`ports/execution.py`) — ExecutionEnginePort, RuntimeManagerPort
- CapabilityNegotiator, RuntimeRegistryImpl, ExecutionEngineBase + CompositeEngine
- DiscoveryEngine, RuntimeManager, GenericExecutionEngine adapter, PathDiscovery adapter
- Kernel wiring, config, 12 REST API endpoints, 14 engine.* event topics
- 195 tests

**Phase 4, Milestone 2** — Automatic Runtime Discovery & Binding
- Discovery domain models (`domain/discovery.py`), DiscoveryFramework, 10 providers
- Validation pipeline (6 validators), ProfilingEngine, DiscoveryScheduler
- DiscoveryCache, DiscoveryTelemetry, DiscoveryEventPublisher, hot-reload lifecycle
- Kernel wiring, 18 REST API endpoints, Mission Control Discovery dashboard
- 616 tests

**Phase 4, Milestone 3** — Orchestration Foundation (Core Engine)
- Orchestration domain models (`domain/orchestration.py`) — 11 dataclass entities,
  5 StrEnums (AgentDescriptor, SwarmSpec, SwarmState, OrchestrationGoal, AgentTask,
  OrchestrationPlan, Vote, ConsensusResult, LeaderElectionResult, AgentMessage,
  OrchestrationTelemetryEntry)
- Orchestration port interfaces (`ports/orchestration.py`) — 6 runtime-checkable
  Protocols (AgentRegistryPort, SwarmManagerPort, TaskOrchestratorPort,
  CoordinationStrategy, DecompositionStrategy, ConsensusStrategy)
- 34 orchestration.* event topics
- AgentRegistry — wraps RuntimeManager engines as swarm agents
- SwarmManager — team definitions (MESH/STAR/HIERARCHICAL/RING topologies)
- TaskOrchestrator — goal decomposition (rule-based + template-based strategies)
- CoordinationEngine — 6 patterns (SEQUENTIAL, PARALLEL, FAN_OUT, FAN_IN,
  HIERARCHICAL, VOTING) with deadlock detection and timeout handling
- SwarmIntelligenceEngine — consensus, voting, leader election
- CommunicationBus — inter-agent messaging over EventBus
- OrchestrationTelemetry — event history and aggregated stats
- OrchestrationEventPublisher — EventBus lifecycle events
- OrchestrationFramework — M3 composition root with async lifecycle and background
  agent sync loop
- 294 tests

### Deferred (Next Milestone)

- **Orchestration REST API endpoints** (`/api/orchestration/`) — agent discovery,
  swarm management, task orchestration, consensus/voting, communication, and
  telemetry endpoints are designed but not yet implemented.
- **Mission Control orchestration UI** — the orchestration dashboard, swarm
  topology visualizer, and task monitoring views are designed but not yet built.

### Changed

- `kernel.py` — OrchestrationFramework composed at startup with async lifecycle
  (start/stop). Platform bundle includes `orchestration` field.
- `config.py` — 12 orchestration settings (enabled, topology, strategy, timeouts,
  telemetry limits, leader election, consensus quorum, decomposition strategy).
- `domain/events.py` — 34 new orchestration.* topics across swarm lifecycle, task
  orchestration, coordination patterns, swarm intelligence, and communication.
- Observability core modules — cross-cutting lint/format alignment (6 modules).

## [0.5.1] — 2026-07-18

### Added — Phase 4, Milestone 2: Automatic Runtime Discovery & Binding

- **Discovery domain models** (`domain/discovery.py`) — 7 frozen dataclass
  entities (DiscoveryProviderConfig, DiscoveryProfile, DiscoveryRule,
  DiscoveryCacheEntry, DiscoveryTelemetryEntry, ValidationResult, ProfileResult)
  with factory methods, builder patterns (with_enabled, with_provider,
  with_schedule), and serialization (to_dict).
- **Discovery Framework core** (`core/discovery/`) — 9 modules:
  - `DiscoveryFramework` — main M2 orchestrator wrapping M1 DiscoveryEngine
  - `DiscoveryRegistry` — provider registry with per-provider configs
  - `DiscoveryCache` — TTL-based dedup with max-entries eviction
  - `DiscoveryScheduler` — periodic per-profile scanning
  - `DiscoveryTelemetry` — scan metrics, history, and aggregated stats
  - `DiscoveryConfiguration` — profile and rule management
  - `ValidationPipeline` — 6 validators (ExecutableExists, VersionDetect,
    HealthCheck, CapabilityMatch, Permission, Integrity)
  - `ProfilingEngine` — auto-generated ExecutionProfile from engine metadata
  - `DiscoveryEventPublisher` — EventBus emissions for lifecycle events
- **10 discovery providers** (`adapters/discovery/`) — PathDiscovery,
  WindowsRegistryDiscovery, WslDiscovery, DockerDiscovery, FilesystemDiscovery,
  KnownInstallDirDiscovery, ConfigFileDiscovery, EnvVarDiscovery,
  VSCodeDiscovery, JetBrainsDiscovery. Each implements the M1
  DiscoveryProvider Protocol with platform guards.
- **Kernel wiring** (`kernel.py`) — DiscoveryFramework composed at startup with
  all 10 providers, 4 validators (ExecutableExists, VersionDetect,
  CapabilityMatch, Permission), ProfilingEngine, DiscoveryScheduler, and
  hot-reload lifecycle in start()/stop().
- **REST API** (`api/app.py`) — 18 new endpoints: provider management, scan
  trigger, cache control, history, stats, profiles CRUD, validation, profiling,
  hot-reload control.
- **Mission Control UI** (`apps/mission-control/`) — Tabbed Discovery page
  (Dashboard, History, Profiles, Validation) in the navigation sidebar.
- **Config** (`config.py`) — 8 new discovery settings: cache TTL, max entries,
  telemetry max entries, hot-reload toggle/interval, default profile,
  validation/profiling toggles.
- **Event topics** (`domain/events.py`) — 21 new topics: 16 discovery.*,
  3 validation.*, 2 profiling.*.
- **Python 3.14 support** — `target-version` set to `py314` for PEP 649 lazy
  annotation support.
- **Tests** — 616 new tests across 11 test files (domain, config, registry,
  cache, telemetry, validation, profiling, framework, providers, hot-reload,
  integration). All pass with zero regressions (1125 total, up from 668 pre-M2).

## [0.5.0] — 2026-07-18

### Added — Phase 4, Milestone 1: Universal Execution Engine Framework

- **Domain models** (`domain/execution.py`) — 12 frozen dataclass entities
  (ExecutionEngine, ExecutionSession, ExecutionResult, ExecutionHealth,
  ExecutionMetrics, ExecutionBenchmark, ExecutionConfiguration, ExecutionProfile,
  ExecutionCapability, ExecutionTelemetry, ExecutionWorkspace, ExecutionEvent,
  EngineRegistry) and 6 StrEnums (EngineType, EngineStatus, EngineCapability,
  EngineHealthStatus, ExecutionStatus, ExecutionEventType).
- **Port interfaces** (`ports/execution.py`) — `ExecutionEnginePort` (~22 method
  universal interface), `RuntimeManagerPort` (high-level orchestration),
  `DiscoveryProvider` (engine scanning). Input DTOs: EngineRegistration,
  EngineUpdate, ExecutionRequest, ExecutionQuery, EngineSummary, EngineDetail.
- **CapabilityNegotiator** (`core/runtime/capabilities.py`) — scored capability
  matching with 10x required weighting, confidence-based filtering, TTL cache,
  and async-safe registration/unregistration.
- **RuntimeRegistryImpl** (`core/runtime/registry.py`) — in-memory engine CRUD
  with per-engine locks, health caching, session tracking, capability-based
  search, EventBus emission for all lifecycle transitions.
- **ExecutionEngineBase + CompositeEngine** (`core/runtime/engine.py`) — abstract
  base with default implementations for all 22 port methods; CompositeEngine
  combines multiple engines for fallback, load balancing, and routing.
- **DiscoveryEngine** (`core/runtime/discovery.py`) — multi-provider orchestration
  with deduplication (highest confidence wins), confidence scoring per provider
  type, and optional continuous watching.
- **RuntimeManager** (`core/runtime/manager.py`) — high-level subsystem composing
  registry + discovery + negotiator + adapters. Full lifecycle management,
  execution routing, health checks, benchmark, and session tracking.
- **GenericExecutionEngine adapter** (`adapters/engines/generic.py`) — reference
  adapter demonstrating the port contract with echo/ping/sleep/info/fail actions.
- **PathDiscovery adapter** (`adapters/discovery/path.py`) — scans system PATH
  for known AI executables (claude, docker, wsl, aider, code, etc.).
- **Kernel wiring** (`kernel.py`, `config.py`, `api/app.py`) — RuntimeManager
  composed at kernel startup, GenericExecutionEngine registered as default,
  12 new REST API endpoints (`/api/runtime/engines/*`, `/api/runtime/execute`,
  `/api/runtime/discover`, `/api/runtime/capabilities`), 4 new config settings.
- **Event topics** — 14 new `engine.*` topics on the EventBus.
- **Tests** — 195 new tests across 7 test files (domain, registry, capabilities,
  engine base, discovery, manager, generic adapter). All pass with zero regressions
  (672 total).

## [0.4.0] — 2026-07-18

### Added — Phase 3 Mission Control (3B) Backend Engines

- **Workflow Engine** (`src/agentic_os/core/workflow/engine.py`) — DAG-based
  execution with topological sort, versioning, replay, approval gates, and full
  CRUD. Supports START/END/AGENT/TOOL/LLM/CONDITION/PARALLEL/APPROVAL/SUBWORKFLOW
  node types. In-memory persistence with EventBus emissions for all lifecycle
  transitions (`workflow.*` topics).
- **Pipeline Engine** (`src/agentic_os/core/pipeline/engine.py`) — Stage-based
  execution with scheduling (cron-like), retry policies, rollback, and parallel
  stage execution. Supports AGENT/WORKFLOW/TOOL/LLM/CONDITION/PARALLEL/APPROVAL
  stage types. In-memory persistence with EventBus emissions (`pipeline.*` topics).
- **Observability Framework** (`src/agentic_os/core/observability/`) — Three
  in-memory implementations:
  - `InMemoryTracing`: W3C TraceContext propagation, span hierarchies, trace
    export, OpenTelemetry-compatible API.
  - `InMemoryMetrics`: counters, gauges, histograms, Prometheus export format.
  - `InMemoryStructuredLogging`: structured log entries with correlation context,
    levels (DEBUG–CRITICAL), context binding.
  - `TraceContextPropagator`: W3C `traceparent`/`tracestate` header inject/extract.
- **MCP Framework** — Domain models (`MCPServerConfig`, `MCPTool`) and ports
  (`MCPRegistryPort`) for Model Context Protocol server lifecycle and tool
  discovery. Ready for adapter implementation in Phase 4.
- **Plugin SDK** (`src/agentic_os/core/plugin/sdk.py`) — TypeScript/Python plugin
  base classes: `PluginBase`, `AgentPlugin`, `ToolPlugin`, `ProviderPlugin`,
  `MCPServerPlugin`, `WorkflowNodePlugin`, `PipelineStagePlugin`. Includes
  `PluginValidator`, `PluginEventBus`, manifest helpers, template generator,
  and `PluginRegistryClient` for marketplace integration.
- **Domain Models** — Workflow, Pipeline, and Observability domain entities
  (frozen dataclasses with slot-based immutability): `Workflow`, `WorkflowNode`,
  `WorkflowEdge`, `WorkflowExecution`, `Pipeline`, `PipelineStage`,
  `PipelineExecution`, `Span`, `Trace`, `Metric`, `LogEntry`, `CorrelationContext`.
- **Port Interfaces** — `WorkflowEnginePort`, `PipelineEnginePort`, `TracingPort`,
  `MetricsPort`, `LoggingPort`, `MCPRegistryPort`, `PluginRegistryPort`.
- **Test Suite** — 30 stress/benchmark tests covering concurrency (5/10/25),
  large workflows (50-node chain), large pipelines (50-stage chain), observability
  load (5000 spans, 1000 metrics, 1000 logs), mixed engine + observability
  scenarios, rapid create/execute/delete cycles.
- **Documentation** — `ARCHITECTURE.md` updated with Phase 3B subsystem table
  and control flow; `README.md` status line updated to v0.4.0; `ROADMAP.md`
  Phase 3 marked complete.

### Fixed

- `PipelineExecution.complete_stage()` no longer leaves retried stages in
  `failed_stages`, which previously caused pipeline failure during finalization
  even after a retried stage succeeded.
- Workflow cancel tests now use approval-gated workflows to avoid auto-completion
  race conditions.
- `otel.py` frozen dataclass assignment issue documented (known regression;
  `tracing.py` is the canonical OTel implementation).

## [0.3.0] — 2026-07-17

### Added — Phase 3 Mission Control (3A)

- **Mission Control frontend** (`apps/mission-control`) — Next.js 15 App Router +
  React 19 + TypeScript premium OS interface. Glassmorphism, dark/light theming,
  command palette (⌘K), single-key navigation, smooth 120Hz motion.
- **Live WebSocket integration** — Zustand store consumes `/ws/dashboard` and
  derives all view state from real EventBus envelopes. Restricted to the
  existing, frozen broadcaster (additive topic coverage only).
- **AI Brain centerpiece** — orbiting agents and pulse rings driven strictly by
  real event arrivals; honest idle state. In-view agent composition routed
  through the Capability Engine (`/api/agents/compose`).
- **Agent Constellation** + **Execution Graph** — live React Flow topologies
  from real agent/task maps (supervisor links, task stages).
- **Provider Control Center**, **System Monitor**, **Task Timeline**,
  **Memory Explorer**, **Plugin Marketplace**, **MCP Manager**, **Workspace
  Explorer** — all read-only over existing REST endpoints.
- **Workflow Studio** + **Pipeline Builder** — interactive graph editors
  (provider-seeded), exportable as canonical JSON (persistence is Phase 3B).
- **ADR 0010** — Mission Control UI architecture and constraints.
- **Frontend CI** — typecheck, lint, Vitest tests, and `next build` gated in
  GitHub Actions (`mission-control` job) and `scripts/ci.sh --only=frontend`.

### Notes

- Backend public interfaces remain frozen; the dashboard WebSocket broadcaster
  topic set was **extended** (additive) to feed the UI, not changed.
- Workflow/pipeline persistence and the deeper MCP/Memory plugin store are
  deferred to Phase 3B.

## [0.2.0] — 2026-07-17

### Added — Phase 2 Core 4 Subsystems

- **Provider Management** — provider/model catalog, encrypted secret vault
  (Fernet), API-key vault, health monitoring, routing policies
  (latency / cost / round_robin) with failover, cost tracking, and rate-limit
  monitoring. OpenAI-compatible adapter. REST surface
  (`/api/providers`, `/api/provider-configs`, `/api/provider-health`,
  `/api/cost`, `/api/rate-limits`, `/api/routing/policy`, `/api/models`).
- **Capability Engine** — composable capabilities replace fixed roles.
  11 built-in capabilities (sensitive ones flag `requires_approval`),
  capability registry, intent→capability agent composer, `AgentSpec`. REST
  surface (`/api/capabilities`, `/api/agents/compose`,
  `/api/agents/compose-for-task`).
- **Memory System** — scoped memory (working / conversation / project / shared /
  long-term) with `MemoryStore`, `VectorStore` (brute-force cosine),
  `KnowledgeGraph`, retention policies (TTL + max-size), and `MEMORY_WRITTEN` /
  `MEMORY_EVICTED` events. REST surface (`/api/memory`, `/api/memory/{scope}`,
  `/api/memory/{scope}/recall`, `/api/memory/retention`).
- **Security Framework** — RBAC (deny-by-default), workspace isolation,
  capability→permission mapping, human approval gate, append-only audit log, and
  secrets management over the encrypted store. REST surface
  (`/api/security/authorize`, `/api/security/approval/...`,
  `/api/security/audit`, `/api/security/workspace/{agent_id}`).
- **Integration tests** — live kernel + API smoke tests exercising all four
  subsystems over HTTP (`tests/test_phase2_integration.py`).
- **ADRs 0006–0009** — Provider Management, Capability Engine, Memory System,
  Security Framework.
- **Repository standards** — `ARCHITECTURE.md`, `ROADMAP.md`, `CONTRIBUTING.md`,
  `SECURITY.md`, `CODE_OF_CONDUCT.md`, `LICENSE`, `.editorconfig`,
  `.gitattributes`, expanded `.gitignore`.

### Changed

- `Platform` bundle extended with `memory`, `capability`, `security`.
- `LocalBus.stop()` now drains in-flight event dispatches so subscribers
  observe events published immediately before shutdown.
- `MockProvider` now honors the configured provider name/kind.

## [0.1.0] — Phase 1 Foundation + Vertical Slice

- Hexagonal kernel: Planner → Dispatcher → Provider Adapter → Event Bus →
  Supervisor → Health Monitor → Recovery Manager → WebSocket Dashboard.
- Abstract `EventBus` with `LocalBus` (default), `RedisStreamsBus`, and
  `NatsJetStreamBus` adapters.
- Plugin system, provider abstraction, structured logging, metrics, CI gates.
