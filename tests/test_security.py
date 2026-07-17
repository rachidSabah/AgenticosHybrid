"""Tests for the Security Framework (Subsystem 4)."""

from __future__ import annotations

import pytest

from agentic_os.core.security.approval import ApprovalGateImpl, AuditLogImpl
from agentic_os.core.security.framework import SecurityFramework
from agentic_os.core.security.rbac import AccessControlImpl, WorkspaceIsolationImpl
from agentic_os.core.security.tool_perms import ToolPermissionsImpl
from agentic_os.domain.security import (
    AuditEntry,
    Permission,
    Principal,
    Role,
    ToolRequest,
)
from agentic_os.ports.provider_management import SecretStore


class _MemStore(SecretStore):
    def __init__(self) -> None:
        self._d: dict[str, str] = {}

    async def put(self, key: str, value: str) -> None:
        self._d[key] = value

    async def get(self, key: str) -> str | None:
        return self._d.get(key)

    async def delete(self, key: str) -> None:
        self._d.pop(key, None)

    async def exists(self, key: str) -> bool:
        return key in self._d


@pytest.fixture
async def bus():
    from agentic_os.adapters.bus.local import LocalBus

    b = LocalBus()
    await b.start()
    yield b
    await b.stop()


@pytest.fixture
def ac():
    return AccessControlImpl()


@pytest.fixture
def framework(bus):
    return SecurityFramework(bus, _MemStore())


async def test_rbac_deny_by_default(ac):
    p = Principal(id="u1", roles=[Role.GUEST])
    assert ac.is_allowed(p, Permission(name="tool.terminal")) is False


async def test_rbac_admin_allows(ac):
    p = Principal(id="admin", roles=[Role.ADMIN])
    assert ac.is_allowed(p, Permission(name="tool.docker")) is True


async def test_rbac_assign_and_grant(ac):
    p = Principal(id="op", roles=[Role.OPERATOR])
    ac.assign(p, Role.AGENT)
    ac.grant(Role.AGENT, Permission(name="tool.docker"))
    assert ac.is_allowed(p, Permission(name="tool.docker")) is True


def test_workspace_isolation_safe():
    ws = WorkspaceIsolationImpl(base_dir="/srv/ws")
    root = ws.workspace_for("agent-1")
    assert "agent-1" in root
    # Path-traversal attempt is neutralised.
    assert ".." not in ws.workspace_for("../escape")


async def test_tool_permissions_denies_unknown(ac):
    tp = ToolPermissionsImpl(ac)
    p = Principal(id="u", roles=[Role.AGENT])
    req = ToolRequest(principal=p, capability="nonexistent")
    dec = tp.decision_for(p, req)
    assert dec.allowed is False and "unknown" in dec.reason


async def test_tool_permissions_requires_approval(ac):
    tp = ToolPermissionsImpl(ac)
    p = Principal(id="u", roles=[Role.OPERATOR])
    req = ToolRequest(principal=p, capability="terminal", requires_approval=True)
    dec = tp.decision_for(p, req)
    assert dec.allowed is False and "approval" in dec.reason


async def test_tool_permissions_allows_operator_terminal(ac):
    tp = ToolPermissionsImpl(ac)
    p = Principal(id="op", roles=[Role.OPERATOR])
    req = ToolRequest(principal=p, capability="terminal", requires_approval=False)
    dec = tp.decision_for(p, req)
    assert dec.allowed is True


async def test_approval_gate_flow(bus):
    audit = AuditLogImpl()
    gate = ApprovalGateImpl(bus, audit)
    p = Principal(id="operator", roles=[Role.OPERATOR])
    req = ToolRequest(principal=p, capability="docker", requires_approval=True)
    await gate.request(req)
    assert gate.status(req.id) is None  # not yet decided
    await gate.decide(req.id, approved=True, by="human")
    decided = gate.status(req.id)
    assert decided is not None and decided.allowed is True
    entries = await audit.query("operator")
    assert any(e.action == "approval.granted" for e in entries)


async def test_framework_authorize_denies_and_audits(framework):
    p = Principal(id="guest", roles=[Role.GUEST])
    req = ToolRequest(principal=p, capability="terminal", requires_approval=False)
    decision = await framework.authorize(p, req)
    assert decision.allowed is False
    entries = await framework.audit.query("guest")
    assert any(e.outcome == "deny" for e in entries)


async def test_framework_authorize_approval_pending(framework):
    p = Principal(id="op", roles=[Role.OPERATOR])
    req = ToolRequest(principal=p, capability="docker", requires_approval=True)
    decision = await framework.authorize(p, req)
    assert decision.allowed is False
    assert decision.reason == "pending human approval"
    await framework.gate.decide(req.id, approved=True, by="human")
    assert framework.gate.status(req.id).allowed is True


async def test_secrets_manager_roundtrip(framework):
    await framework.secrets.put("provider:x", "super-secret")
    assert await framework.secrets.get("provider:x") == "super-secret"
    assert await framework.secrets.delete("provider:x") is True
    assert await framework.secrets.get("provider:x") is None


async def test_audit_log_query(framework):
    await framework.audit.record(AuditEntry(principal="a", action="x", outcome="allow"))
    rows = await framework.audit.query("a")
    assert len(rows) == 1
