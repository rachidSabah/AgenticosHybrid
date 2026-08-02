"""RBAC access control + workspace isolation (Security Framework)."""

from __future__ import annotations

from pathlib import Path

from agentic_os.domain.security import (
    PERMISSIONS,
    Permission,
    Principal,
    Role,
)
from agentic_os.ports.security import AccessControl, WorkspaceIsolation

# Default role → permission grants. ADMIN gets everything; others get a
# least-privilege subset. This map is the single source of truth for defaults.
_DEFAULT_GRANTS: dict[Role, set[str]] = {
    Role.ADMIN: set(PERMISSIONS),
    Role.OPERATOR: {
        "provider.manage",
        "agent.compose",
        "memory.read",
        "memory.write",
        "tool.browser",
        "tool.terminal",
        "tool.docker",
        "security.audit",
    },
    Role.AGENT: {"memory.read", "memory.write", "tool.browser", "agent.compose"},
    Role.AUDITOR: {"security.audit"},
    Role.GUEST: set(),
}


class AccessControlImpl(AccessControl):
    def __init__(self) -> None:
        self._roles: dict[Principal, set[Role]] = {}
        self._grants: dict[Role, set[str]] = {r: set(p) for r, p in _DEFAULT_GRANTS.items()}

    def assign(self, principal: Principal, role: Role) -> None:
        self._roles.setdefault(principal, set()).add(role)

    def grant(self, role: Role, permission: Permission) -> None:
        self._grants.setdefault(role, set()).add(permission.name)

    def is_allowed(self, principal: Principal, permission: Permission) -> bool:
        roles = self._roles.get(principal, set(principal.roles))
        for role in roles:
            if permission.name in self._grants.get(role, set()):
                return True
        return False


class WorkspaceIsolationImpl(WorkspaceIsolation):
    """Maps each agent to a sandboxed workspace root under a base dir."""

    def __init__(self, base_dir: str = "./workspaces") -> None:
        self._base = base_dir.rstrip("/\\")
        self._cache: dict[str, str] = {}

    def workspace_for(self, agent_id: str) -> str:
        if agent_id not in self._cache:
            safe_id = agent_id.replace("..", "").strip("/\\")
            base = Path(self._base).resolve()
            candidate = (base / safe_id).resolve()
            if not str(candidate).startswith(str(base)):
                raise ValueError(f"agent_id {agent_id!r} escapes workspace root")
            self._cache[agent_id] = str(candidate)
        return self._cache[agent_id]
