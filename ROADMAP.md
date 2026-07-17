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

## 🚧 Phase 3 — Mission Control Platform (v0.3.0, 3A shipped)

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

**3B — remaining:**
- **MCP Framework** — Model Context Protocol server/client adapters so external
  tools and data sources plug into agents behind a port.
- **Workflow Engine persistence** — save/load pipelines to the backend engine.
- **Deeper Memory / Plugin stores** — backend plugin registry + semantic recall
  wired into the UI.

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
