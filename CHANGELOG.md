# Changelog

All notable changes to AgenticOS are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/) and this project adheres to
[Semantic Versioning](https://semver.org/).

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
