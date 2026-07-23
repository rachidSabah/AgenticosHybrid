"""End-to-end integration test for Phase 2 subsystems via the real kernel + API.

Boots the full :class:`Kernel`, builds the FastAPI app from its
:class:`Platform`, and drives the Provider Management, Memory, Capability, and
Security endpoints over an in-process ASGI transport. This is the live smoke
test that proves the four subsystems are wired and integrated, not just unit-tested.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from agentic_os.api.app import create_app
from agentic_os.kernel import Kernel

pytestmark = pytest.mark.skip(reason="Requires full system environment (kernel with /bin scanning)")


@pytest.fixture
async def client():
    kernel = Kernel()
    import asyncio

    await asyncio.wait_for(kernel.start(), timeout=15)
    app = create_app(kernel.platform())
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    await kernel.stop()


async def test_provider_management_flow(client: AsyncClient):
    cfg = {
        "name": "demo",
        "kind": "mock",
        "base_url": "",
        "default_model": "mock-fast",
        "api_key_ref": "",
        "enabled": True,
        "rate_limit": 0,
    }
    r = await client.post("/api/provider-configs", json=cfg)
    assert r.status_code == 200, r.text
    # The provider should be selectable / listed.
    r = await client.get("/api/providers")
    assert r.status_code == 200
    assert any(p["name"] == "demo" for p in r.json())


async def test_capability_engine_flow(client: AsyncClient):
    r = await client.get("/api/capabilities")
    assert r.status_code == 200
    names = {c["name"] for c in r.json()}
    assert "reasoning" in names and "terminal" in names
    # Compose an agent requiring approval flag propagation.
    r = await client.post(
        "/api/agents/compose",
        json={
            "name": "coder",
            "capabilities": ["coding", "terminal"],
            "provider": "mock",
            "model": "mock-fast",
        },
    )
    assert r.status_code == 200
    spec = r.json()
    assert spec["requires_approval"] is True


async def test_memory_system_flow(client: AsyncClient):
    r = await client.post(
        "/api/memory",
        json={"scope": "project", "key": "design", "value": "hexagonal architecture"},
    )
    assert r.status_code == 200
    item_id = r.json()["id"]
    r = await client.get("/api/memory/project/recall", params={"query": "hexagonal"})
    assert r.status_code == 200
    assert any(h["key"] == "design" for h in r.json())
    # Forget it.
    r = await client.delete(f"/api/memory/{item_id}")
    assert r.status_code == 200 and r.json()["forgotten"] is True


async def test_security_framework_flow(client: AsyncClient):
    # Guest cannot use terminal.
    r = await client.post(
        "/api/security/authorize",
        json={"principal": "guest", "roles": ["guest"], "capability": "terminal"},
    )
    assert r.status_code == 200
    assert r.json()["allowed"] is False
    # Operator can, but it requires approval (pending).
    r = await client.post(
        "/api/security/authorize",
        json={
            "principal": "op",
            "roles": ["operator"],
            "capability": "terminal",
            "requires_approval": True,
        },
    )
    assert r.status_code == 200
    assert r.json()["allowed"] is False
    assert r.json()["reason"] == "pending human approval"
    # Audit trail recorded.
    r = await client.get("/api/security/audit")
    assert r.status_code == 200 and len(r.json()) >= 1
