# ADR-0009: Security Framework

- Status: Accepted
- Date: 2026-07-17
- Phase: 2 (Subsystem 4)

## Context

With capabilities (ADR-0007) and dynamic agents, a sensitive capability
(`terminal`, `git`, `docker`, `filesystem`) can be composed into any agent at
runtime. Without enforcement, a composed agent could escape its sandbox or run
privileged tools unmoderated. We need: authenticated principals with roles,
least-privilege permissions, workspace isolation, a human approval gate for
sensitive actions, and an immutable audit trail — all as swappable ports.

## Decision

1. **Six ports, one facade.** `ports/security.py` defines `SecretsManager`,
   `AccessControl` (RBAC), `WorkspaceIsolation`, `ToolPermissions`,
   `ApprovalGate`, `AuditLog`. `core/security/framework.py`
   `SecurityFramework` composes them behind a single `authorize()` pipeline.

2. **RBAC with deny-by-default.** `domain/security.py` defines `Role`,
   `Permission`, `Principal`, and a canonical `PERMISSIONS` set. `AccessControlImpl`
   ships least-privilege default grants (ADMIN gets all; OPERATOR gets
   provider/memory/terminal/docker/browser/audit; AGENT gets memory/browser/
   compose; AUDITOR gets audit; GUEST gets nothing). Any capability not mapped
   to a granted permission is denied.

3. **Capability → permission map.** `ToolPermissionsImpl` maps capability names
   to permission strings (`terminal→tool.terminal`, …). Unknown capabilities
   are denied. Capabilities flagged `requires_approval` (set by the Capability
   Engine, ADR-0007) return a *pending* decision even when RBAC allows.

4. **Human approval gate.** `ApprovalGateImpl` publishes `APPROVAL_REQUESTED`,
   records a `pending` audit entry, and returns a pending decision; a human
   resolves it via `decide()` which emits `APPROVAL_DECIDED` and records the
   outcome. `SecurityFramework.authorize` runs: RBAC → (if pending) gate → audit,
   and emits `TOOL_DENIED` on denial.

5. **Workspace isolation.** `WorkspaceIsolationImpl` maps each agent to a
   sandboxed root and neutralises `..` traversal. This root is what the
   shell-backed capabilities (`_ShellCapability`) execute within.

6. **Secrets over the frozen store.** `SecretStoreSecretsManager` wraps the
   already-shipped encrypted `SecretStore` (ADR-0006) so secrets management has
   one persistence path. All secret access is async (matching the port).

7. **Append-only audit.** `AuditLogImpl` keeps an ordered, in-memory trail;
   production can back it with an append-only store. Every authorize/approve
   action is recorded with principal, action, target, outcome.

8. **Kernel + REST.** `kernel.py` wires `SecurityFramework(bus, secret_store)`
   into `Platform.security`. `api/app.py` exposes assignment, `authorize`,
   approval decide/status, audit query, and workspace lookup.

## Consequences

- Sensitive capabilities are gated by RBAC *and* human approval before
  execution, with a full audit trail — the system is defensible by construction.
- Deny-by-default ensures new capabilities are blocked until explicitly granted.
- Public interface frozen: the six security ports; `Principal`, `Role`,
  `Permission`, `ToolRequest`, `Decision`, `AuditEntry` domain; framework
  `authorize`/`workspace_for`.
- The approval gate is synchronous-return (pending) by design; the API exposes
  explicit decide/status endpoints so an operator UI (Phase 3) can drive it.

## Alternatives considered

- *Enforce approval inside the capability `run()`.* Rejected: scatters policy
  across every capability; the framework keeps authorization centralized and
  capability-agnostic.
- *Coarse single "is_admin" check.* Rejected: no least-privilege, no per-tool
  audit, no path to multi-tenant isolation.
