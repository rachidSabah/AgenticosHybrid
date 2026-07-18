# Agentic OS

A **local-first, event-bus-driven AI Agent Operating System**. Runs on Windows via
WSL2, fully containerized, modular, and plugin-based. Every component communicates
through an abstract **Event Bus** and is replaceable behind a port interface.

> Status: **Phase 3 — Mission Control Platform (v0.4.0, 3B complete)**. Phase 1–2
> delivered a headless, hexagonal backend (kernel, EventBus, Provider Management,
> Capability Engine, Memory System, Security Framework). Phase 3 upgrades
> AgenticOS into an immersive **AI Operating System** with a premium Mission
> Control interface. **3A** shipped the UI framework, live WebSocket integration, the
> AI Brain centerpiece, Agent Constellation, Provider Control Center, System
> Monitor, Task Timeline, Memory Explorer, and interactive Workflow/Pipeline
> editors. **3B** ships the backend Workflow Engine, Pipeline Engine,
> Observability Framework (OpenTelemetry tracing, Prometheus metrics, structured
> logging), MCP Framework domain/ports, Plugin Framework SDK, and comprehensive
> test coverage (>90% on all new modules).

## Project Vision

A local-first operating system for AI agents: modular, observable, and secure
by construction. Agents are composed from capabilities at runtime, providers are
swappable behind ports, and every action flows through an event bus that any
dashboard or subsystem can observe.

## Mission

Make autonomous, multi-agent systems **trustworthy and extensible** without
sacrificing simplicity. AgenticOS proves each architectural idea with one
production-ready, fully tested vertical slice before expanding scope.

## Features

- **Hexagonal kernel** — ports before implementations; swap any adapter without
  touching business logic.
- **Pluggable Event Bus** — Local (dev), Redis Streams (prod), NATS JetStream
  (alt prod).
- **Provider Management** — multi-provider catalog, encrypted secrets, health,
  routing (latency/cost/round-robin) with failover, cost + rate tracking.
- **Capability Engine** — agents composed from 11 built-in capabilities;
  sensitive capabilities require human approval.
- **Memory System** — scoped, searchable (lexical + semantic), self-grooming
  via retention policies.
- **Security Framework** — RBAC (deny-by-default), workspace isolation, approval
  gate, append-only audit log.
- **Live dashboard** — WebSocket event stream; REST control plane.
- **Workflow Engine** — DAG-based workflow execution with versioning, replay,
  approval gates, and topological sort ordering.
- **Pipeline Engine** — Stage-based pipeline execution with scheduling, retry
  policies, rollback support, and parallel stage execution.
- **Observability Framework** — OpenTelemetry tracing (W3C TraceContext), Prometheus
  metrics, structured logging with correlation IDs. In-memory implementations for
  dev/test.
- **Plugin SDK** — TypeScript/Python interfaces for external plugin developers:
  agent, tool, provider, MCP, workflow node, and pipeline stage base classes.
- **Mission Control (Phase 3)** — Next.js + React 19 immersive OS UI: AI Brain,
  Agent Constellation, Execution Graph, Provider Control Center, Memory Explorer,
  Workflow/Pipeline studios, command palette, dark/light, 120Hz motion.
- **Quality gates** — ruff, `ty` (strict), pytest, **and** Next.js
  typecheck/lint/test/build enforced in CI.

## Technology Stack

Python 3.13+ · FastAPI · asyncio / AnyIO · Pydantic v2 · pydantic-settings ·
structlog · Prometheus client · httpx · `cryptography` (Fernet) · uv ·
Docker / WSL2.

**Mission Control frontend:** Next.js 15 (App Router) · React 19 · TypeScript ·
TailwindCSS · Framer Motion · React Flow · Zustand · Monaco Editor · Vitest.

## Architecture (hexagonal / clean)

```
                 ┌──────────────────────────────────────────────────┐
   User/UI  ───▶ │                  API (FastAPI)                     │
                 │        REST + WebSocket live dashboard            │
                 └───────────────┬──────────────────────────────────┘
                                 │ ports (interfaces)
        ┌────────────────────────┼────────────────────────────────┐
        │                        │                                  │
  ┌─────▼─────┐          ┌───────▼────────┐                ┌───────▼───────┐
  │  CORE     │          │  DOMAIN        │                │  ADAPTERS     │
  │ Orchestrator          │ Agent/Task/    │                │ Local/Redis/  │
  │ Registry   │          │ Role/Provider  │◀── ports ────▶│ NATS Bus      │
  │ Scheduler  │          │ EventEnvelope  │                │ Provider(s)  │
  │ Health/Rec │          └────────────────┘               │ Plugins      │
  └────────────┘                                            └───────────────┘
```

See [`docs/adr/`](docs/adr) for Architecture Decision Records and
[`docs/c4/`](docs/c4) for C4 diagrams.

## Event Bus

One abstract `EventBus` port with three interchangeable adapters:

| Adapter | Use | Default in |
|---------|-----|-----------|
| `LocalBus` | in-process asyncio; dev, tests, slicing | dev / CI |
| `RedisStreamsBus` | Redis Streams; persistent, replayable, consumer groups | **production** |
| `NatsJetStreamBus` | NATS JetStream; strong routing + replay + KV | production (alt) |

Set `BUS_TYPE=local|redis|nats`. The system boots on `local` with zero infra.

## Vertical slice (this release)

```
User Request ─▶ Planner ─▶ Task Dispatcher ─▶ Claude Code Adapter
                                                          │
                                                    Abstract Event Bus
                                                          │
                                   Supervisor ◀──▶ Health Monitor ──▶ Recovery Manager
                                                          │
                                                  WebSocket Dashboard (live)
```

Demonstrates: task creation, event publish/consume, orchestration, monitoring,
automatic recovery, structured logging, metrics, and live dashboard updates.

## Phase 2 subsystems (this release)

All four subsystems expose their interfaces through **ports before concrete
implementations** (hexagonal architecture) and ship with default in-memory /
encrypted backends plus a REST surface.

| Subsystem | Ports | Default impl | Key APIs |
|-----------|-------|-------------|----------|
| **Provider Management** | `ProviderManager`, `ModelManager`, `SecretStore`, `ApiKeyVault`, `ProviderHealthMonitor`, `RoutingPolicy`, `CostTracker`, `RateLimitMonitor`, `FailoverPolicy` | encrypted Fernet vault, OpenAI-compatible adapter | `/api/providers`, `/api/provider-configs`, `/api/provider-health`, `/api/cost`, `/api/rate-limits`, `/api/routing/policy` |
| **Memory System** | `MemoryStore`, `VectorStore`, `KnowledgeGraph`, `MemoryManager` | in-memory store + brute-force cosine vector + adjacency graph | `/api/memory`, `/api/memory/{scope}`, `/api/memory/{scope}/recall`, `/api/memory/retention` |
| **Capability Engine** | `Capability`, `CapabilityRegistry`, `AgentComposer` | 11 built-in capabilities, intent→capability composer | `/api/capabilities`, `/api/agents/compose`, `/api/agents/compose-for-task` |
| **Security Framework** | `SecretsManager`, `AccessControl`, `WorkspaceIsolation`, `ToolPermissions`, `ApprovalGate`, `AuditLog` | RBAC + workspace isolation + human approval gate + append-only audit | `/api/security/authorize`, `/api/security/approval/...`, `/api/security/audit`, `/api/security/workspace/{agent_id}` |

Public interfaces are **frozen** once validated — see ADRs `0006`–`0009`.

## WSL2 Installation

```bash
# Inside WSL2 (Ubuntu/Debian), from the repo root
sudo apt-get update && sudo apt-get install -y docker.io
curl -LsSf https://astral.sh/uv/install.sh | sh   # install uv
uv python install 3.13
cp .env.example .env
docker compose up --build        # starts AgenticOS + Redis
# open http://localhost:8000
```

## Docker Installation

```bash
# from E:\AAIOS (or /mnt/e/AAIOS inside WSL2)
cp .env.example .env
docker compose up --build
# open http://localhost:8000  → live dashboard at ws://localhost:8000/ws/dashboard
```

## Quick Start (local dev, no Docker)

```bash
uv python install 3.13
uv sync
uv run agentic-os serve          # or: BUS_TYPE=local uv run python -m agentic_os
```

Trigger the slice:

```bash
curl -X POST http://localhost:8000/api/tasks \
  -H 'content-type: application/json' \
  -d '{"title":"Write a hello-world function","role":"coding"}'
```

### Mission Control (frontend)

```bash
# backend (control plane + /ws/dashboard)
uv run agentic-os serve

# in another terminal
cd apps/mission-control
npm install --legacy-peer-deps
npm run dev        # http://localhost:3000
```

The UI connects to the backend via `NEXT_PUBLIC_API_BASE` (default
`http://localhost:8000`) and renders live EventBus data. Quality gate:

```bash
npm run typecheck && npm run lint && npm run test && npm run build
```

## Repository Structure

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the full layered design and the
`docs/adr/` decision records. Source layout:

```
src/agentic_os/
  domain/      entities + value objects (Pydantic v2)
  ports/       interfaces (EventBus, ProviderAdapter, Plugin, + 4 subsystem ports)
  core/        orchestrator, registries, health, recovery, scheduler,
               providers/, capability/, memory/, security/
  adapters/    bus, provider, capability, memory, security implementations
  api/         FastAPI app (REST + WebSocket)
  kernel.py    composition root → Platform bundle
  cli.py       entrypoint
tests/         unit + integration (incl. live kernel API smoke tests)
docs/adr/      Architecture Decision Records (0001–0009)
docs/c4/       C4 diagrams (mermaid)
```

## Plugin System

Agents and providers are discovered via the plugin loader
(`adapters/plugins/loader.py`). A plugin exposes a `Plugin` port
(`name`, `load()`, `unload()`) and registers providers/agents into the
registries at kernel start. See `ROADMAP.md` — the formal `PLUGIN_SDK.md` lands
with the Phase 3 plugin marketplace.

## Provider System

Providers implement the frozen `ProviderAdapter` port (`info`, `execute()`,
`healthcheck()`). The Provider Management subsystem adds a catalog, model
registry, encrypted vault, health monitor, multi-policy router with failover,
cost tracker, and rate limiter. Add a provider at runtime via
`POST /api/provider-configs`; it becomes immediately selectable by the router.

## Memory System

Memory is partitioned into scopes (working / conversation / project / shared /
long-term). `MemoryStore` provides CRUD + lexical search, `VectorStore` adds
semantic recall, `KnowledgeGraph` adds relations. `MemoryManager` applies per-scope
TTL + max-size retention and emits `MEMORY_WRITTEN` / `MEMORY_EVICTED` events.

## Capability Engine

Capabilities are the unit of agent definition. The engine seeds 11 built-ins;
sensitive ones (`terminal`, `git`, `docker`, `filesystem`) set
`requires_approval=True` so the Security Framework can intercept them. The
composer derives an `AgentSpec` from a task's intent. See `docs/adr/0007`.

## Security Framework

RBAC with deny-by-default least-privilege grants, workspace isolation (traversal
safe), capability→permission mapping, a human approval gate, and an append-only
audit log. `SecurityFramework.authorize()` runs RBAC → (if pending) approval gate
→ audit, and emits `TOOL_DENIED` on denial. See `docs/adr/0009`.

## Project layout

```
src/agentic_os/
  domain/      # entities + value objects (Pydantic v2): agent, provider_mgmt,
              #   capability, memory, security, events
  ports/       # interfaces (EventBus, ProviderAdapter, Plugin, and the four
              #   Phase-2 subsystem ports: provider_management, memory,
              #   capability, security)
  core/        # orchestrator kernel, registries, health, recovery, scheduler,
              #   providers/, capability/engine, memory/, security/
  adapters/    # bus, provider, capability, memory, security implementations
  api/         # FastAPI app, REST + WebSocket
  kernel.py    # composition root → Platform bundle
  cli.py       # entrypoint
tests/         # unit + integration (incl. live kernel API smoke tests)
docs/adr/      # Architecture Decision Records (0001–0009)
docs/c4/       # C4 diagrams (mermaid)
```

## Testing

```bash
uv run pytest -v
```

Local CI (runs ruff in repair mode, then `ty` + pytest):

```bash
./scripts/ci.sh        # macOS / Linux
.\scripts\ci.ps1       # Windows (PowerShell)
```

## Roadmap

- ✅ Phase 1 — Foundation + Vertical Slice (v0.1.0)
- ✅ Phase 2 — Core 4 Subsystems (v0.2.0)
- 🔜 Phase 3 — MCP Framework, Mission Control dashboard, Workflow Engine
- 🔮 Phase 4+ — Plugin Marketplace, Provider/Capability/Plugin SDKs, Desktop
  Client, multi-tenant isolation, production memory backends

See [`ROADMAP.md`](ROADMAP.md) for detail.

## Contributing

Read [`CONTRIBUTING.md`](CONTRIBUTING.md) and [`ARCHITECTURE.md`](ARCHITECTURE.md).
All contributions must pass the CI quality gates and include tests + docs.

## License

Released under the [MIT License](LICENSE).

## Links

- Architecture: [`ARCHITECTURE.md`](ARCHITECTURE.md)
- Decisions: [`docs/adr/`](docs/adr)
- C4 diagrams: [`docs/c4/diagrams.md`](docs/c4/diagrams.md)
- Security: [`SECURITY.md`](SECURITY.md)
- Changelog: [`CHANGELOG.md`](CHANGELOG.md)
