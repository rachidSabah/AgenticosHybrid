"""Domain entities for the Security Framework.

Defines the RBAC vocabulary (:class:`Role`, :class:`Permission`,
:class:`Principal`), the :class:`ToolRequest` / :class:`Decision` pair that the
approval gate and tool-permission layers speak, and the append-only
:class:`AuditEntry`. Permissions are coarse-grained strings (``tool.terminal``,
``memory.write``, …) so roles can be composed declaratively.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Role(StrEnum):
    ADMIN = "admin"
    OPERATOR = "operator"
    AGENT = "agent"
    AUDITOR = "auditor"
    GUEST = "guest"


# Canonical permission strings. Tools/capabilities reference these by name.
PERMISSIONS: frozenset[str] = frozenset(
    {
        "tool.terminal",
        "tool.git",
        "tool.docker",
        "tool.filesystem",
        "tool.browser",
        "memory.read",
        "memory.write",
        "provider.manage",
        "agent.compose",
        "security.audit",
        # MCP Runtime permissions (Phase 4, M3 — B1 Security Integration)
        "mcp.server.create",
        "mcp.server.read",
        "mcp.server.update",
        "mcp.server.delete",
        "mcp.server.start",
        "mcp.server.stop",
        "mcp.server.restart",
        "mcp.server.reload",
        "mcp.tool.invoke",
        "mcp.tool.discover",
        "mcp.tool.read",
        "mcp.resource.read",
        "mcp.resource.subscribe",
        "mcp.prompt.get",
        "mcp.prompt.list",
        "mcp.session.manage",
        "mcp.session.read",
        "mcp.permissions.manage",
        "mcp.permissions.read",
        "mcp.health.read",
        "mcp.config.read",
        "mcp.config.update",
        "mcp.telemetry.read",
        "mcp.audit.read",
    }
)


class Permission(BaseModel):
    """A single coarse-grained permission (e.g. ``tool.terminal``)."""

    name: str

    def __str__(self) -> str:
        return self.name


class Principal(BaseModel):
    """An actor (user or agent) that holds roles."""

    id: str
    roles: list[Role] = Field(default_factory=lambda: [Role.AGENT])

    def __hash__(self) -> int:  # allow use in sets/dicts
        return hash(self.id)


class ToolRequest(BaseModel):
    """A request to exercise a capability/tool, requiring a decision."""

    id: str = Field(default_factory=lambda: uuid4().hex)
    principal: Principal
    capability: str
    workspace: str = ""
    detail: str = ""
    requires_approval: bool = False
    created_at: datetime = Field(default_factory=_utcnow)


class Decision(BaseModel):
    """Outcome of an authorization/approval evaluation."""

    allowed: bool
    reason: str = ""
    approved_by: str = ""  # set when a human approved via the gate


class AuditEntry(BaseModel):
    """One append-only, tamper-evident security record."""

    id: str = Field(default_factory=lambda: uuid4().hex)
    timestamp: datetime = Field(default_factory=_utcnow)
    principal: str
    action: str  # e.g. "tool.denied", "approval.granted", "role.assigned"
    target: str = ""
    outcome: str = ""  # "allow" | "deny" | "approved" | "rejected"
    meta: dict = Field(default_factory=dict)
