"""Security Framework facade.

Composes RBAC, workspace isolation, tool permissions, the approval gate, the
audit log, and secrets management into one object the kernel and API depend on.
It also offers a top-level :meth:`authorize` that runs the full pipeline:
RBAC check → approval gate for sensitive capabilities → audit, returning a
final :class:`Decision`.
"""

from __future__ import annotations

from agentic_os.adapters.security.secrets_manager import SecretStoreSecretsManager
from agentic_os.domain.events import EventEnvelope, Topic
from agentic_os.domain.security import (
    AuditEntry,
    Decision,
    Principal,
    ToolRequest,
)
from agentic_os.ports.event_bus import EventBus
from agentic_os.ports.provider_management import SecretStore
from agentic_os.ports.security import (
    AccessControl,
    ApprovalGate,
    AuditLog,
    SecretsManager,
    ToolPermissions,
    WorkspaceIsolation,
)

from .approval import ApprovalGateImpl, AuditLogImpl
from .rbac import AccessControlImpl, WorkspaceIsolationImpl
from .tool_perms import ToolPermissionsImpl


class SecurityFramework:
    def __init__(
        self,
        bus: EventBus,
        secret_store: SecretStore,
        ac: AccessControl | None = None,
        workspace: WorkspaceIsolation | None = None,
        tools: ToolPermissions | None = None,
        gate: ApprovalGate | None = None,
        audit: AuditLog | None = None,
        secrets: SecretsManager | None = None,
    ) -> None:
        self.bus = bus
        self.ac: AccessControl = ac or AccessControlImpl()
        self.workspace: WorkspaceIsolation = workspace or WorkspaceIsolationImpl()
        self.audit: AuditLog = audit or AuditLogImpl()
        self.gate: ApprovalGate = gate or ApprovalGateImpl(bus, self.audit)
        self.tools: ToolPermissions = tools or ToolPermissionsImpl(self.ac)
        self.secrets: SecretsManager = secrets or SecretStoreSecretsManager(secret_store)

    async def authorize(self, principal: Principal, request: ToolRequest) -> Decision:
        """Run the full authorization pipeline and record the outcome."""
        decision = self.tools.decision_for(principal, request)
        if decision.reason == "pending human approval":
            decision = await self.gate.request(request)
        outcome = (
            "allow"
            if decision.allowed
            else ("pending" if decision.reason == "pending human approval" else "deny")
        )
        await self.audit.record(
            AuditEntry(
                principal=principal.id,
                action="tool.authorized" if decision.allowed else "tool.denied",
                target=request.capability,
                outcome=outcome,
                meta={"reason": decision.reason},
            )
        )
        if not decision.allowed and outcome == "deny":
            await self.bus.publish(
                EventEnvelope(
                    type="tool.denied",
                    source="security-framework",
                    topic=Topic.TOOL_DENIED.value,
                    payload={"capability": request.capability, "principal": principal.id},
                )
            )
        return decision

    def workspace_for(self, agent_id: str) -> str:
        return self.workspace.workspace_for(agent_id)
