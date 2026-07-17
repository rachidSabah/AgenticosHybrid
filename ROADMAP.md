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

## 🔜 Phase 3 — Extensibility & Control Plane

- **MCP Framework** — Model Context Protocol server/client adapters so external
  tools and data sources plug into agents behind a port.
- **Mission Control dashboard** — unified web UI replacing the minimal provider
  page; real-time control over agents, providers, memory, and security.
- **Workflow Engine** — compose multi-agent workflows with orchestration,
  branching, and human checkpoints.

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
