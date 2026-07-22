"""Human-in-the-loop approval gate + append-only audit log (Security)."""

from __future__ import annotations

from agentic_os.domain.events import EventEnvelope, Topic
from agentic_os.domain.security import AuditEntry, Decision, ToolRequest
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.event_bus import EventBus
from agentic_os.ports.security import ApprovalGate, AuditLog

log = get_logger("security.approval")


class ApprovalGateImpl(ApprovalGate):
    """Requests approval for sensitive actions, resolves via bus events."""

    def __init__(self, bus: EventBus, audit: AuditLog) -> None:
        self._bus = bus
        self._audit = audit
        self._pending: dict[str, ToolRequest] = {}
        self._decisions: dict[str, Decision] = {}

    async def request(self, request: ToolRequest) -> Decision:
        self._pending[request.id] = request
        await self._audit.record(
            AuditEntry(
                principal=request.principal.id,
                action="approval.requested",
                target=request.capability,
                outcome="pending",
                meta={"detail": request.detail},
            )
        )
        await self._bus.publish(
            EventEnvelope(
                type="approval.requested",
                source="approval-gate",
                topic=Topic.APPROVAL_REQUESTED.value,
                payload=request.model_dump(mode="json"),
            )
        )
        # Synchronous default: deny until a human decides. Callers that want to
        # wait should poll/await `status` after the human acts via `decide`.
        return Decision(allowed=False, reason="pending human approval")

    async def decide(self, request_id: str, approved: bool, by: str = "") -> None:
        request = self._pending.pop(request_id, None)
        decision = Decision(
            allowed=approved,
            reason="human decision",
            approved_by=by,
        )
        self._decisions[request_id] = decision
        action = "approval.granted" if approved else "approval.rejected"
        await self._audit.record(
            AuditEntry(
                principal=request.principal.id if request else request_id,
                action=action,
                target=request.capability if request else "",
                outcome="approved" if approved else "rejected",
                meta={"by": by},
            )
        )
        await self._bus.publish(
            EventEnvelope(
                type="approval.decided",
                source="approval-gate",
                topic=Topic.APPROVAL_DECIDED.value,
                payload={"request_id": request_id, "approved": approved, "by": by},
            )
        )
        log.info("approval.decided", request_id=request_id, approved=approved, by=by)

    def status(self, request_id: str) -> Decision | None:
        return self._decisions.get(request_id)


class AuditLogImpl(AuditLog):
    """In-memory append-only audit log (single-writer, ordered)."""

    def __init__(self) -> None:
        self._entries: list[AuditEntry] = []

    async def record(self, entry: AuditEntry) -> AuditEntry:
        self._entries.append(entry)
        return entry

    async def query(self, principal: str | None = None, limit: int = 100) -> list[AuditEntry]:
        rows = self._entries
        if principal:
            rows = [e for e in rows if e.principal == principal]
        return rows[-limit:]
