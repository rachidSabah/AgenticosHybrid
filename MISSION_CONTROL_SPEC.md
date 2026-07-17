# Mission Control Spec (deferred to Phase 3)

Status: **Planned (Phase 3).** The minimal provider-management HTML page
(`/providers` in `api/app.py`) is a temporary stand-in. Mission Control is the
unified web control plane.

## Goals

- Single real-time dashboard over agents, providers, memory, and security.
- WebSocket event stream (`/ws/dashboard`) already streams every bus event.
- Operator controls: compose agents, approve/reject pending tool requests,
  inspect memory, review audit log, manage providers/models.
- Backed by the existing REST surface (provider, memory, capability, security
  endpoints) — no new ports required.

## Open design questions (for ADR-0010)

- Authn/authz for the operator UI (reuse the Security Framework RBAC).
- Stateful vs. purely event-driven views.
- Desktop Client (Tauri) shell over the same API.
