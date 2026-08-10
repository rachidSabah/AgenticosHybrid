"""Tests for the shared Remote Prompt Service + local QR rendering.

These cover the mission-routing layer that BOTH the Telegram and WhatsApp
gateways share: authorization, rate limiting, idempotency, validation,
cancel ownership, and channel/remote metadata propagation.  The channel
gateways themselves are transport adapters (python-telegram-bot / the Node
bridge) and are exercised by live smoke tests rather than unit tests here.
"""

from __future__ import annotations

import pytest

from agentic_os.adapters.gateway.remote_prompt import (
    CHANNEL_TELEGRAM,
    CHANNEL_WHATSAPP,
    AuthorizationError,
    DuplicateMessageError,
    RateLimitError,
    RemoteIdentity,
    RemotePromptService,
    ValidationError,
)
from agentic_os.adapters.gateway.whatsapp_gateway import WhatsAppGateway
from agentic_os.domain.events import Topic
from agentic_os.domain.mission import Mission, MissionStatus


class _FakeMissionStore:
    """Shared in-memory store mirroring the app's `_missions` dict."""

    def __init__(self) -> None:
        self._missions: dict[str, Mission] = {}

    def get(self, key: str) -> Mission | None:
        return self._missions.get(key)

    def values(self):
        return list(self._missions.values())


def _make_service(
    bus,
    store: _FakeMissionStore | None = None,
    allowed: dict[str, set[str]] | None = None,
    rate_limit: int = 50,
) -> RemotePromptService:
    store = store or _FakeMissionStore()

    async def create_mission(body: dict) -> dict:
        m = Mission(
            title=body.get("title", ""),
            description=body.get("description", ""),
            prompt=body.get("prompt", ""),
            preferred_agents=body.get("preferred_agents", []),
            channel=body.get("channel", "WEB"),
            remote=body.get("remote", {}),
        )
        store._missions[m.id] = m
        return m.to_dict()

    async def plan_mission(mission_id: str) -> dict:
        store.get(mission_id).status = MissionStatus.PLANNED
        return {}

    async def start_mission(mission_id: str) -> dict:
        store.get(mission_id).status = MissionStatus.EXECUTING
        return store.get(mission_id).to_dict()

    async def cancel_mission(mission_id: str) -> dict:
        store.get(mission_id).status = MissionStatus.CANCELLED
        return store.get(mission_id).to_dict()

    return RemotePromptService(
        bus=bus,
        create_mission_fn=create_mission,
        plan_mission_fn=plan_mission,
        start_mission_fn=start_mission,
        cancel_mission_fn=cancel_mission,
        missions_store=store._missions,
        allowed_identities=allowed,
        rate_limit_per_minute=rate_limit,
    )


# ── submit ───────────────────────────────────────────────────────────────────


async def test_submit_routes_through_mission_pipeline(bus):
    svc = _make_service(bus)
    identity = RemoteIdentity(channel=CHANNEL_WHATSAPP, external_account_id="15551234567")

    mission = await svc.submit(prompt="Build a hello world app", identity=identity, message_id="m1")

    assert mission["channel"] == "WHATSAPP"
    assert mission["remote"]["external_account_id"] == "15551234567"
    assert mission["remote"]["channel"] == "WHATSAPP"
    # Mission was actually planned + started via the shared pipeline.
    assert mission["status"] == "executing"
    assert mission["title"] == "Build a hello world app"


async def test_submit_publishes_audit_allow(bus):
    svc = _make_service(bus)
    identity = RemoteIdentity(channel=CHANNEL_TELEGRAM, external_account_id="42")

    # Subscribe a recorder to the audit topic (LocalBus dispatches by topic).
    recorded: list[dict] = []

    async def recorder(event) -> None:
        recorded.append(event.payload)

    await bus.subscribe(Topic.AUDIT.value, recorder)

    await svc.submit(prompt="Audit me", identity=identity, message_id="a1")
    await bus.drain()

    assert any(a["action"] == "mission.submit" and a["outcome"] == "allow" for a in recorded)


async def test_duplicate_message_rejected(bus):
    svc = _make_service(bus)
    identity = RemoteIdentity(channel=CHANNEL_WHATSAPP, external_account_id="15551234567")

    await svc.submit(prompt="Do the thing", identity=identity, message_id="dup-1")
    with pytest.raises(DuplicateMessageError):
        await svc.submit(prompt="Do the thing", identity=identity, message_id="dup-1")


async def test_empty_prompt_rejected(bus):
    svc = _make_service(bus)
    identity = RemoteIdentity(channel=CHANNEL_WHATSAPP, external_account_id="15551234567")

    with pytest.raises(ValidationError):
        await svc.submit(prompt="   ", identity=identity, message_id="e1")


async def test_prompt_too_long_rejected(bus):
    svc = _make_service(bus, rate_limit=50)
    identity = RemoteIdentity(channel=CHANNEL_WHATSAPP, external_account_id="15551234567")

    with pytest.raises(ValidationError):
        await svc.submit(prompt="x" * 5000, identity=identity, message_id="long")


# ── authorization ────────────────────────────────────────────────────────────


async def test_allowlist_denies_unlisted_identity(bus):
    svc = _make_service(bus, allowed={CHANNEL_TELEGRAM: {"42"}})
    stranger = RemoteIdentity(channel=CHANNEL_TELEGRAM, external_account_id="999")

    with pytest.raises(AuthorizationError):
        await svc.submit(prompt="secret thing", identity=stranger, message_id="s1")


async def test_allowlist_allows_listed_identity(bus):
    svc = _make_service(bus, allowed={CHANNEL_TELEGRAM: {"42"}})
    owner = RemoteIdentity(channel=CHANNEL_TELEGRAM, external_account_id="42")

    mission = await svc.submit(prompt="ok thing", identity=owner, message_id="ok1")
    assert mission["status"] == "executing"


async def test_sensitive_actions_never_authorized(bus):
    svc = _make_service(bus)  # no allowlist → default allow for normal actions
    identity = RemoteIdentity(channel=CHANNEL_TELEGRAM, external_account_id="42")

    for action in ("provider.config", "system.shutdown", "workspace.delete"):
        assert svc.authorize(identity, action) is False


# ── rate limiting ────────────────────────────────────────────────────────────


async def test_rate_limit_enforced_per_identity(bus):
    svc = _make_service(bus, rate_limit=2)
    identity = RemoteIdentity(channel=CHANNEL_TELEGRAM, external_account_id="42")

    await svc.submit(prompt="t1", identity=identity, message_id="r1")
    await svc.submit(prompt="t2", identity=identity, message_id="r2")
    with pytest.raises(RateLimitError):
        await svc.submit(prompt="t3", identity=identity, message_id="r3")


# ── cancel ───────────────────────────────────────────────────────────────────


async def test_owner_can_cancel_own_mission(bus):
    svc = _make_service(bus)
    owner = RemoteIdentity(channel=CHANNEL_TELEGRAM, external_account_id="42")

    mission = await svc.submit(prompt="cancel me", identity=owner, message_id="c1")
    result = await svc.cancel(mission["id"], owner)
    assert result["status"] == "cancelled"


async def test_stranger_cannot_cancel_own_mission(bus):
    svc = _make_service(bus)
    owner = RemoteIdentity(channel=CHANNEL_TELEGRAM, external_account_id="42")
    stranger = RemoteIdentity(channel=CHANNEL_TELEGRAM, external_account_id="999")

    mission = await svc.submit(prompt="mine", identity=owner, message_id="c2")
    with pytest.raises(AuthorizationError):
        await svc.cancel(mission["id"], stranger)


# ── workspace safety ─────────────────────────────────────────────────────────


async def test_validate_channel_normalizes_and_rejects_forged(bus):
    svc = _make_service(bus)
    assert svc.validate_channel("WEB") == "WEB"
    assert svc.validate_channel("telegram") == "TELEGRAM"
    with pytest.raises(ValueError):
        svc.validate_channel("GARBAGE")


# ── secret non-disclosure (WhatsApp pairing QR) ──────────────────────────────
# The raw QR string is a pairing secret. It must never appear in the status
# API response, on the WS event feed, or in the ring-buffer replay.


async def test_whatsapp_status_never_exposes_qr_string(bus):
    gw = WhatsAppGateway(bus=bus)
    gw._qr_code = "2@SECRET_PAIRING_TOKEN_SUPER_SENSITIVE"  # noqa: SLF001 — direct state injection for the test

    status = gw.get_status()

    assert status["has_qr"] is True
    # The raw secret must be absent from every serialized value.
    serialized = repr(status)
    assert "SECRET_PAIRING_TOKEN" not in serialized
    assert "qr_code" not in status


async def test_whatsapp_qr_event_payload_has_no_secret(bus):
    gw = WhatsAppGateway(bus=bus)
    recorded: list[dict] = []

    async def recorder(event) -> None:
        recorded.append(event.payload)

    await bus.subscribe("gateway.whatsapp.qr", recorder)

    await gw._handle_bridge_event(  # noqa: SLF001 — direct event injection for the test
        {"type": "qr", "qr": "2@SECRET_PAIRING_TOKEN_SUPER_SENSITIVE"}
    )
    await bus.drain()

    assert len(recorded) == 1
    payload = recorded[0]
    assert payload.get("has_qr") is True
    assert "qr" not in payload
    assert "SECRET_PAIRING_TOKEN" not in repr(payload)


async def test_whatsapp_status_reports_no_qr_when_disconnected(bus):
    gw = WhatsAppGateway(bus=bus)
    status = gw.get_status()
    assert status["has_qr"] is False
    assert "qr_code" not in status
