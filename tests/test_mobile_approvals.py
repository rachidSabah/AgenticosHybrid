"""Mobile approval bridge — one-time tokens, TTL expiry, QR, decision page.

No mocks for the security mechanics: tokens are real one-time secrets, the
QR is really rendered (skipped honestly when qrcode is unavailable), expiry
really expires, and every transition lands in the audit JSONL.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from agentic_os.core.security.mobile_approval import (
    MobileApprovalBridge,
    MobileApprovalError,
    decision_page_html,
)


@pytest.fixture
def bridge(tmp_path):
    return MobileApprovalBridge(data_dir=str(tmp_path / "apr"), ttl_s=120)


def test_create_returns_token_once(bridge):
    req = bridge.create(operation="delete production table", detail="DROP TABLE users")
    assert req["state"] == "pending"
    assert req["token"]
    # the pending view shows the request but never re-reveals the token
    stored = bridge.get(req["request_id"])
    assert "token" not in stored
    assert req["token"] not in str(bridge.pending())
    assert req["request_id"] in str(bridge.pending())


def test_operation_required(bridge):
    with pytest.raises(MobileApprovalError):
        bridge.create(operation="  ")


def test_decide_by_token_approves_and_is_single_use(bridge):
    req = bridge.create(operation="restart service", ttl_s=60)
    out = bridge.decide_by_token(req["token"], approved=True, by="alice")
    assert out["state"] == "approved"
    assert out["decided_by"] == "alice"
    # second use refused
    with pytest.raises(MobileApprovalError) as exc:
        bridge.decide_by_token(req["token"], approved=True)
    assert "single-use" in str(exc.value)


def test_wrong_token_refused_and_nothing_decided(bridge):
    req = bridge.create(operation="pay invoice", ttl_s=60)
    with pytest.raises(MobileApprovalError) as exc:
        bridge.decide_by_token("wrong-token", approved=True)
    assert "unknown or expired" in str(exc.value)
    assert bridge.get(req["request_id"])["state"] == "pending"


def test_reject_by_token(bridge):
    req = bridge.create(operation="wipe disk", ttl_s=60)
    out = bridge.decide_by_token(req["token"], approved=False, by="bob")
    assert out["state"] == "rejected"


def test_expiry_is_a_refusal_not_a_yes(bridge):
    bridge2 = MobileApprovalBridge(data_dir=str(bridge._dir), ttl_s=0.05)
    req = bridge2.create(operation="very short window")
    time.sleep(0.08)
    with pytest.raises(MobileApprovalError) as exc:
        bridge2.decide_by_token(req["token"], approved=True)
    assert "expired" in str(exc.value) or "already" in str(exc.value)
    assert bridge2.get(req["request_id"])["state"] == "expired"
    assert bridge2.pending() == []


def test_wait_for_decision_resolves_on_approval(bridge):
    async def scenario():
        req = bridge.create(operation="deploy to prod", ttl_s=30)
        decision = bridge.decide_by_token(req["token"], True, by="carol")
        waiter = await bridge.wait_for_decision(req["request_id"], timeout_s=5)
        return decision, waiter

    decision, waiter = asyncio.run(scenario())
    assert decision["state"] == "approved"
    assert waiter["state"] == "approved"


def test_wait_for_decision_times_out_without_approval(bridge):
    async def scenario():
        req = bridge.create(operation="never decided", ttl_s=1)
        return await bridge.wait_for_decision(req["request_id"], timeout_s=0.2)

    out = asyncio.run(scenario())
    assert out["state"] == "pending"


def test_telegram_text_contains_exact_replies(bridge):
    req = bridge.create(operation="flush cache", risk="data loss", ttl_s=120)
    text = bridge.telegram_text(req["request_id"])
    assert "/approve " in text
    assert "/reject " in text
    assert "flush cache" in text
    assert "data loss" in text
    assert req["token"] in text


def test_approval_url_and_qr(bridge):
    req = bridge.create(operation="rotate keys", ttl_s=120)
    url = bridge.approval_url(req["request_id"], "http://192.168.1.10:8000")
    assert url.startswith("http://192.168.1.10:8000/approve/")
    assert "token=" in url
    pytest.importorskip("qrcode")
    svg = bridge.qr_svg(req["request_id"], "http://192.168.1.10:8000")
    assert svg.lstrip().startswith("<?xml") or "<svg" in svg


def test_qr_requires_base_url(bridge):
    req = bridge.create(operation="no base", ttl_s=60)
    with pytest.raises(MobileApprovalError) as exc:
        bridge.approval_url(req["request_id"], "")
    assert "base_url" in str(exc.value)


def test_audit_trail_records_transitions(bridge):
    req = bridge.create(operation="audit me", ttl_s=60)
    bridge.decide_by_token(req["token"], approved=True, by="dave")
    entries = bridge.audit_tail()
    actions = [e["action"] for e in entries]
    assert "requested" in actions
    assert "decided" in actions
    decided = [e for e in entries if e["action"] == "decided"][-1]
    assert decided["by"] == "dave"


def test_decision_page_html_is_honest(bridge):
    assert "Invalid or expired link" in decision_page_html("x", "", "", valid=False)
    page = decision_page_html("x", "danger <op>", "detail", valid=True)
    assert "danger &lt;op&gt;" in page  # escaped
    assert "Approve" in page and "Reject" in page


async def test_publishes_bus_events(tmp_path):
    from agentic_os.adapters.bus.local import LocalBus

    bus = LocalBus()
    seen: list[str] = []

    async def spy(envelope) -> None:
        seen.append(str(envelope.type))

    await bus.subscribe("system", spy)
    await bus.start()
    bridge = MobileApprovalBridge(data_dir=str(tmp_path / "apr2"), bus=bus, ttl_s=60)
    req = bridge.create(operation="bus check")
    bridge.decide_by_token(req["token"], approved=True, by="eve")
    await asyncio.sleep(0.2)
    assert "approval.mobile.requested" in seen
    assert "approval.mobile.decided" in seen
