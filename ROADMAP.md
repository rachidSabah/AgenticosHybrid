# Roadmap

AgenticOS is built incrementally. Interfaces are frozen once validated; each
phase lands production-ready, fully tested, and documented.

## ✅ Phase 1 — Foundation + Vertical Slice (v0.1.0)

- Hexagonal kernel and abstract Event Bus (Local / Redis / NATS adapters).
- Planner → Dispatcher → Provider Adapter → Supervisor → Health → Recovery →
  WebSocket Dashboard.
- Plugin system, provider abstraction, CI quality gates.

## ✅ Phase 2 — Core 4 Subsystems (v0.2.0)

- Provider Management, Capability Engine, Memory System, Security Framework.
- Frozen public interfaces (ADRs 0006–0009).
- REST control plane + live integration tests.

## ✅ Phase 3 — Mission Control Platform (v0.3.0 3A, v0.4.0 3B)

**3A — UI framework (done):**
- **Mission Control** — Next.js 15 + React 19 immersive OS UI: glassmorphism,
  dark/light, command palette, keyboard shortcuts, 120Hz motion.
- **AI Brain centerpiece** — reacts to real EventBus pulses; idle state rendered
  honestly (no fake animation).
- **Agent Constellation** + **Execution Graph** — live `reactflow` topologies
  from real agent/task events.
- **Provider Control Center**, **System Monitor**, **Task Timeline**,
  **Memory Explorer**, **Plugin Marketplace**, **MCP Manager**, **Workspace
  Explorer** — all over existing REST + `/ws/dashboard`.
- **Workflow Studio** + **Pipeline Builder** — interactive local editors.

**3B — Backend engines (done):**
- **Workflow Engine** — DAG-based execution with topological sort, versioning,
  replay, approval gates, and full CRUD. In-memory persistence. 90%+ coverage.
- **Pipeline Engine** — stage-based execution with scheduling, retry policies,
  rollback, parallel stages, and full CRUD. In-memory persistence. 90%+ coverage.
- **Observability Framework** — OpenTelemetry tracing (W3C TraceContext),
  Prometheus metrics, structured logging with correlation IDs. In-memory
  implementations for dev/test. 90%+ coverage.
- **MCP Framework** — domain models and ports for Model Context Protocol server
  configuration, tool discovery, and lifecycle management.
- **Plugin Framework** — Plugin SDK (TypeScript/Python base classes), validation,
  manifest generation, template generation, and registry client.
- **Stress/Benchmark testing** — 30 tests covering concurrency (5/10/25),
  large workflows (50-node), large pipelines (50-stage), observability load
  (5000 spans, 1000 metrics, 1000 logs), mixed engine + observability scenarios.
- **Documentation** — `ARCHITECTURE.md` updated with Phase 3B subsystem table,
  `README.md` updated, `CHANGELOG.md` updated.

## ✅ Phase 4 — Universal Execution Framework (v0.5.0, Milestone 1)

**Phase 4 transforms AgenticOS into a universal execution platform capable of
discovering, binding, orchestrating, supervising and optimizing ANY AI execution
engine. The kernel never depends on a specific AI coding assistant.**

**Milestone 1 — Universal Execution Engine Framework (done):**
- **Domain models** (`domain/execution.py`) — 10+ frozen dataclass entities
  (ExecutionEngine, ExecutionSession, ExecutionResult, etc.), 6 StrEnums
  (EngineType, EngineStatus, EngineCapability, etc.).
- **Port interfaces** (`ports/execution.py`) — `ExecutionEnginePort` (~22 method
  universal interface), `RuntimeManagerPort` (high-level orchestration),
  `DiscoveryProvider` (engine scanning).
- **Core engine base** (`core/runtime/engine.py`) — `ExecutionEngineBase` with
  default implementations, `CompositeEngine` for multi-engine routing.
- **Capability negotiator** (`core/runtime/capabilities.py`) — scored matching:
  required capabilities weighted 10x, confidence-based filtering, TTL cache.
- **Runtime registry** (`core/runtime/registry.py`) — in-memory engine CRUD,
  health caching, session tracking, capability search, event emission.
- **Discovery engine** (`core/runtime/discovery.py`) — multi-provider
  orchestration, deduplication by name (highest confidence wins), confidence
  scoring by provider type.
- **Runtime manager** (`core/runtime/manager.py`) — high-level subsystem
  composing registry + discovery + negotiator + adapters. Full lifecycle
  management, execution routing, health checks.
- **Generic reference adapter** (`adapters/engines/generic.py`) — in-process
  engine demonstrating the port contract with echo/ping/sleep/info/fail actions.
- **PATH discovery** (`adapters/discovery/path.py`) — scans system PATH for
  known AI executables (claude, docker, wsl, aider, code, etc.).
- **Kernel wiring** (`kernel.py`, `config.py`, `api/app.py`) — RuntimeManager
  composed at startup, 12 REST API endpoints, 4 new config knobs.
- **Tests** — 195 new tests across 7 test files, all passing with zero
  regressions (672 total).

## ✅ Phase 4 — Universal Execution Framework (v0.5.1, Milestone 2)

**Milestone 2 — Automatic Runtime Discovery & Binding (done):**
- **Discovery domain models** (`domain/discovery.py`) — 7 frozen dataclass entities
  (DiscoveryProviderConfig, DiscoveryProfile, DiscoveryRule, DiscoveryCacheEntry,
  DiscoveryTelemetryEntry, ValidationResult, ProfileResult) with factory methods,
  builder patterns, and serialization.
- **Discovery Framework core** (`core/discovery/`) — 9 modules: DiscoveryFramework
  (main orchestrator wrapping M1 DiscoveryEngine), DiscoveryRegistry (provider
  registry + profiles), DiscoveryCache (TTL-based dedup), DiscoveryScheduler
  (periodic scanning), DiscoveryTelemetry (scan metrics + history),
  DiscoveryConfiguration (profiles + rules), ValidationPipeline (6 validators:
  ExecutableExists, VersionDetect, HealthCheck, CapabilityMatch, Permission,
  Integrity), ProfilingEngine (auto-generates ExecutionProfile), and
  DiscoveryEventPublisher (EventBus lifecycle events).
- **10 discovery providers** (`adapters/discovery/`) — PathDiscovery,
  WindowsRegistryDiscovery, WslDiscovery, DockerDiscovery, FilesystemDiscovery,
  KnownInstallDirDiscovery, ConfigFileDiscovery, EnvVarDiscovery,
  VSCodeDiscovery, JetBrainsDiscovery. Each implements the M1 DiscoveryProvider
  Protocol with platform guards.
- **Kernel wiring** — DiscoveryFramework composed at startup with all 10
  providers, 4 validators, profiling engine, scheduler, and hot-reload lifecycle
  (start/stop in kernel start/shutdown).
- **REST API** — 18 new endpoints on the FastAPI control plane: provider
  management, scan triggers, cache control, history, stats, profiles CRUD,
  validation, profiling, hot-reload control.
- **Mission Control UI** — Tabbed Discovery page (Dashboard, History, Profiles,
  Validation) registered in the navigation sidebar.
- **EventBus integration** — 16 new `discovery.*`, 3 `validation.*`, and 2
  `profiling.*` EventBus topics.
- **Event topics** — 21 new topics on the EventBus (`discovery.*`,
  `validation.*`, `profiling.*`).
- **Config** — 8 new discovery settings for cache TTL, max entries, hot-reload
  interval, validation/profiling toggles.
- **Tests** — 453 new tests across 11 test files, all passing with zero
  regressions (1121 total).

## 🔮 Phase 5+ — Ecosystem

- **Plugin Marketplace** — discoverable, signed community plugins.
- **Provider Framework SDKs** — `PROVIDER_SDK.md`, `CAPABILITY_SDK.md`,
  `PLUGIN_SDK.md` for third-party extension.
- **Desktop Client** — Tauri-based native shell over Mission Control.
- **Multi-tenant isolation** — workspace-scoped tenancy with policy boundaries.
- **Long-term memory persistence** — production vector DB + graph DB backends
  behind the existing memory ports.

## Documentation backlog

- `PROVIDER_SDK.md`, `CAPABILITY_SDK.md`, `PLUGIN_SDK.md`, `EVENT_SCHEMA.md`
  (specs: placeholder stubs deferred until their subsystems ship).
- `docs/api/`, `docs/architecture/`, `docs/ui/` (generated/expanded with Phase 3).
