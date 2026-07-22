"""Tool-permission and approval-gate logic (Security Framework).

:class:`ToolPermissionsImpl` maps a capability name to the permission string it
requires, then consults RBAC (and optional workspace) to produce a
:class:`Decision`. Capabilities flagged ``requires_approval`` (declared by the
Capability Engine, ADR-0007) always return a *pending* decision that the
:class:`ApprovalGate` must resolve with a human.
"""

from __future__ import annotations

from agentic_os.domain.security import (
    Decision,
    Permission,
    Principal,
    ToolRequest,
)
from agentic_os.ports.security import AccessControl, ToolPermissions

# Capability name → required permission. Anything not listed is denied by
# default (deny-by-default posture).
_CAP_TO_PERM: dict[str, str] = {
    "terminal": "tool.terminal",
    "git": "tool.git",
    "docker": "tool.docker",
    "filesystem": "tool.filesystem",
    "browser": "tool.browser",
    "memory": "memory.write",
    "reasoning": "agent.compose",
    "planning": "agent.compose",
    "coding": "agent.compose",
    "research": "agent.compose",
    "vision": "agent.compose",
}


class ToolPermissionsImpl(ToolPermissions):
    def __init__(self, ac: AccessControl) -> None:
        self._ac = ac

    def decision_for(self, principal: Principal, request: ToolRequest) -> Decision:
        perm_name = _CAP_TO_PERM.get(request.capability)
        if perm_name is None:
            return Decision(allowed=False, reason=f"unknown capability {request.capability!r}")
        if not self._ac.is_allowed(principal, Permission(name=perm_name)):
            return Decision(
                allowed=False,
                reason=f"principal lacks permission {perm_name}",
            )
        if request.requires_approval:
            # RBAC allows, but a human must approve before execution.
            return Decision(allowed=False, reason="pending human approval")
        return Decision(allowed=True, reason="rbac allow")
