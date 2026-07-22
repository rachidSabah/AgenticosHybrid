"""Ports: Security Framework.

The Security subsystem is decomposed into small, independently implementable
interfaces so the kernel can depend on each capability without coupling to a
concrete policy engine:

* :class:`SecretsManager` — issue/resolve named secrets (API keys, tokens).
  Delegates to the already-shipped :class:`SecretStore` (encrypted at rest).
* :class:`AccessControl` — role/permission RBAC: *who* may do *what*.
* :class:`WorkspaceIsolation` — scopes agent execution to a sandboxed root so
  capabilities (terminal/git/docker/filesystem) cannot escape their workspace.
* :class:`ToolPermissions` — maps a capability/tool name to the permission it
  requires and decides allow/deny, consulting RBAC + workspace.
* :class:`ApprovalGate` — human-in-the-loop: requests approval for
  ``requires_approval`` actions and resolves them via bus events.
* :class:`AuditLog` — append-only, tamper-evident record of security-relevant
  actions (used by every other interface here).

The :class:`SecurityFramework` facade wires these together and is what the
kernel and API depend on.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from agentic_os.domain.security import (
    AuditEntry,
    Decision,
    Permission,
    Principal,
    Role,
    ToolRequest,
)


@runtime_checkable
class SecretsManager(Protocol):
    """Issue and resolve named secrets (API keys, tokens)."""

    async def put(self, name: str, secret: str) -> None: ...

    async def get(self, name: str) -> str | None: ...

    async def delete(self, name: str) -> bool: ...


@runtime_checkable
class AccessControl(Protocol):
    """Role/permission RBAC."""

    def assign(self, principal: Principal, role: Role) -> None: ...

    def grant(self, role: Role, permission: Permission) -> None: ...

    def is_allowed(self, principal: Principal, permission: Permission) -> bool: ...


@runtime_checkable
class WorkspaceIsolation(Protocol):
    """Scope an agent to a sandboxed workspace root."""

    def workspace_for(self, agent_id: str) -> str: ...


@runtime_checkable
class ToolPermissions(Protocol):
    """Decide allow/deny for a capability/tool invocation."""

    def decision_for(self, principal: Principal, request: ToolRequest) -> Decision: ...


@runtime_checkable
class ApprovalGate(Protocol):
    """Human-in-the-loop approval for sensitive actions."""

    async def request(self, request: ToolRequest) -> Decision: ...

    async def decide(self, request_id: str, approved: bool, by: str = "") -> None: ...

    def status(self, request_id: str) -> Decision | None: ...


@runtime_checkable
class AuditLog(Protocol):
    """Append-only security audit trail."""

    async def record(self, entry: AuditEntry) -> AuditEntry: ...

    async def query(self, principal: str | None = None, limit: int = 100) -> list[AuditEntry]: ...
