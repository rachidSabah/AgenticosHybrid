# Mission Control Spec

Status: **Phase 3 — 3A shipped (v0.3.0).** The minimal provider-management HTML
page is replaced by the immersive Mission Control SPA under `apps/mission-control`.
See `docs/adr/0010-mission-control.md` for the architecture decision.

## Goals (delivered in 3A)

- Single real-time OS surface over agents, providers, memory, and security.
- WebSocket event stream (`/ws/dashboard`) drives every view — no fabricated
  data, no duplicated backend logic.
- Operator controls: compose agents (Capability Engine), inspect providers/
  models, browse memory, review audit log, manage providers, explore workspaces.
- Backed strictly by the existing REST surface and `/ws/dashboard` — no new
  backend ports.

## Layout

| Area | View | Source of truth |
|------|------|----------------|
| Command | Mission Overview, AI Brain | EventBus + REST |
| Compose | Agent Constellation, Workflow Studio, Pipeline Builder | EventBus + local (3B persist) |
| Inspect | Execution Graph, Provider Control Center, Memory Explorer, Plugin Marketplace, MCP Manager, Workspace Explorer, Task Timeline, System Monitor | EventBus + REST |

## Design principles

- **Glassmorphism + depth**, **smooth transitions**, **animated topology**,
  **interactive graphs**, **dark/light**, **multi-monitor**, **responsive**,
  **keyboard shortcuts** (⌘K palette, single-key nav), **command palette**,
  **accessibility**, **120Hz** motion.
- **AI Brain** is the centerpiece and reacts only to real EventBus pulses.
- Everything displayed traces to a real EventBus envelope or REST response.

## Tech stack

Next.js 15 (App Router) · React 19 · TypeScript · TailwindCSS · Framer Motion ·
React Flow · Zustand · Monaco Editor · Vitest · WebSockets.

## Open design questions (carried to 3B)

- Operator UI authn/authz (reuse Security Framework RBAC).
- Workflow/Pipeline persistence to a backend engine.
- Deeper MCP Framework + plugin registry store.
- Desktop Client (Tauri) shell over the same API.
