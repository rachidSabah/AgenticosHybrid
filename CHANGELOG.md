# Changelog

All notable changes to AgenticOS are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/) and this project adheres to
[Semantic Versioning](https://semver.org/).

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
