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

## 🔮 Phase 4+ — Ecosystem

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
