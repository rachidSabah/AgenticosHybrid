# ADR 0010 — Mission Control UI

- **Status:** Accepted
- **Date:** 2026-07-17
- **Phase:** Phase 3 (Mission Control Platform), deliverable 3A
- **Deciders:** Architecture review

## Context

Phase 1–2 delivered a headless, hexagonal backend (FastAPI control plane over the
EventBus). There is no human-facing surface. Phase 3 upgrades AgenticOS from a
backend library into an immersive **AI Operating System** with a premium Mission
Control interface.

Constraints carried from earlier phases:

- **No backend redesign.** Public interfaces are frozen; the dashboard WebSocket
  broadcaster was *extended* (additive topic coverage), never changed.
- **No duplicated logic.** The UI only reads via existing REST endpoints and the
  existing `/ws/dashboard` WebSocket; it never re-implements routing, security,
  or memory logic.
- **No fabrication.** Every pixel of displayed data traces to a real EventBus
  envelope or a real REST response. The AI Brain, Agent Constellation, and
  Execution Graph are driven by live events, not scripted animations.

## Decision

Build Mission Control as a **Next.js 15 (App Router) + React 19 + TypeScript**
single-page app under `apps/mission-control/`, consuming the backend strictly
through its published ports:

1. **Transport.** A Zustand store opens one WebSocket to `/ws/dashboard` and
   feeds a reducer (`ingest`) that derives all view state from real envelopes.
   REST calls go through a typed `api` client mapped 1:1 onto existing endpoints.
2. **Theming.** CSS-variable design tokens (`globals.css`) support dark/light via
   a `.dark` class toggled by `ThemeProvider`; premium glassmorphism, focus
   rings, and motion come from `framer-motion` and Tailwind.
3. **Navigation.** A `Sidebar` + `TopBar` shell with a `⌘K` command palette and
   single-key shortcuts. The active view is shared via React context
   (`ActiveViewCtx`) so `page.tsx` routes to one of 13 view components.
4. **AI Brain (centerpiece).** Reads the store's rolling `pulses` ring; pulse
   rings and orbiting agent nodes animate strictly from real event arrivals.
   Idle state is explicitly rendered (no synthetic "busy" look).
5. **Graphs.** Agent Constellation and Execution Graph use `reactflow` with
   nodes/edges derived from live `agents`/`tasks` maps (supervisor links, task
   stages).
6. **Testing.** Vitest + Testing Library cover the store reducer and UI
   primitives; the build, typecheck, lint, and tests run in CI.

### Views delivered in 3A

`MissionOverview`, `AIBrain`, `AgentConstellation`, `ExecutionGraph`,
`ProviderControlCenter`, `SystemMonitor`, `TaskTimeline`, `MemoryExplorer`,
`PluginMarketplace`, `McpManager`, `WorkspaceExplorer`, `WorkflowStudio`,
`PipelineBuilder`.

The last three (`WorkflowStudio`, `PipelineBuilder`, and deeper MCP/Memory
editors) are interactive local editors in 3A; their persistence to the backend
workflow engine is **Phase 3B**.

## Consequences

- **Positive.** A real, GPU-accelerated OS interface with zero backend changes
  and zero duplicated business logic. All data is verifiable against the bus.
- **Positive.** Frontend is independently tested and CI-gated, matching the
  repo's "maximum test coverage" standard.
- **Positive.** The `ingest` reducer is a single, unit-tested place that defines
  how every topic maps to UI state — easy to extend for 3B.
- **Negative / deferred.** Workflow/Pipeline graphs are not yet persisted to a
  backend engine (3B). Plugin Marketplace and MCP Manager surface *existing*
  provider/capability registries rather than a separate plugin store (also 3B).
- **Risk.** Tight coupling to the `/ws/dashboard` envelope shape; mitigated by
  the `EventEnvelope` type mirrored from the backend and the store tests.

## Alternatives considered

- **Admin dashboard (Grafana/Docker-Desktop style).** Rejected — the brief
  explicitly forbids CRUD/admin clones; the OS needs an immersive, branded
  surface.
- **Server-rendered Jinja templates.** Rejected — no rich real-time animation,
  command palette, or 120Hz graph rendering.
- **Extend the FastAPI app with HTML.** Rejected — would violate the
  headless/port boundary and duplicate transport concerns.
