"""Mobile approval bridge — dangerous operations pause until a human decides.

When an enforcement point (approval gate, tool permissions, the step
debugger) marks an operation as requiring a human, the operation must
PAUSE. This bridge is the phone-side of that pause:

* a pending approval carries the operation, its detail, a TTL, and ONE
  one-time decision token — possession of that token IS the authority to
  decide, which is why it is only ever shown to the operator (QR code,
  Telegram message) and never returned twice;
* **Telegram push** — the bridge renders a plain-text message with the
  operation summary and the exact ``/approve <token>`` / ``/reject
  <token>`` replies; the TelegramGateway delivers it and routes the
  replies back via ``decide_by_token``;
* **QR link** — the QR encodes a LOCAL approval URL on this machine (no
  cloud relay, no third-party tunnel): scanning it on a phone in the same
  network opens the decision page. The QR is rendered locally as SVG; if
  the ``qrcode`` package is missing the caller gets an explicit error,
  never a fabricated QR;
* **await** — enforcement code can ``await_decision(request_id)`` and is
  woken the moment the human decides (or on expiry/timeout);
* every transition (requested / decided / expired) is appended to a local
  audit JSONL and published on the bus.

Honesty rules: a decision with a wrong, used, or expired token is refused
with the exact reason; the pending list never re-reveals tokens; nothing
auto-approves on timeout — expiry is a refusal, not a silent yes.
"""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import time
from pathlib import Path
from typing import Any

from agentic_os.infrastructure.logging import get_logger

log = get_logger("security.mobile_approval")

DEFAULT_APPROVALS_DIR = "~/.agentic_os/data/approvals"
DEFAULT_TTL_S = 300.0

STATE_PENDING = "pending"
STATE_APPROVED = "approved"
STATE_REJECTED = "rejected"
STATE_EXPIRED = "expired"


class MobileApprovalError(ValueError):
    """Operator-facing approval error (mapped to HTTP 400/404)."""


class MobileApprovalBridge:
    """Pending approvals with one-time tokens, Telegram + QR delivery."""

    def __init__(
        self,
        data_dir: str = "",
        bus: Any = None,
        ttl_s: float = DEFAULT_TTL_S,
    ) -> None:
        base = Path(data_dir or os.path.expanduser(DEFAULT_APPROVALS_DIR))
        base.mkdir(parents=True, exist_ok=True)
        self._dir = base
        self._audit_path = base / "decisions.jsonl"
        self._bus = bus
        self._ttl_s = float(ttl_s)
        # request_id -> request dict (pending and decided, for the audit view)
        self._requests: dict[str, dict[str, Any]] = {}
        # request_id -> asyncio.Event (set on decision)
        self._events: dict[str, asyncio.Event] = {}
        self._bg_tasks: set[asyncio.Task] = set()

    # ── creation ─────────────────────────────────────────────────────────

    def create(
        self,
        operation: str,
        detail: str = "",
        principal: str = "",
        risk: str = "",
        ttl_s: float | None = None,
        request_id: str = "",
    ) -> dict[str, Any]:
        if not str(operation).strip():
            raise MobileApprovalError("operation is required")
        rid = str(request_id) or f"apr-{secrets.token_hex(5)}"
        token = secrets.token_urlsafe(16)
        now = time.time()
        req: dict[str, Any] = {
            "request_id": rid,
            "operation": str(operation),
            "detail": str(detail or ""),
            "principal": str(principal or ""),
            "risk": str(risk or ""),
            "state": STATE_PENDING,
            "token": token,
            "created_at": now,
            "expires_at": now + (self._ttl_s if ttl_s is None else float(ttl_s)),
            "decided_at": None,
            "decided_by": "",
            "decision_via": "",
        }
        self._requests[rid] = req
        self._events[rid] = asyncio.Event()
        self._audit("requested", req)
        self._publish("approval.mobile.requested", self._public(req, include_token=False))
        # The token is returned exactly once, here, to whoever created the
        # request. Every later view hides it.
        return self._public(req, include_token=True)

    def _sweep_expired(self) -> None:
        now = time.time()
        for req in self._requests.values():
            if req["state"] == STATE_PENDING and now >= float(req["expires_at"]):
                req["state"] = STATE_EXPIRED
                self._audit("expired", req)
                self._publish("approval.mobile.expired", self._public(req, include_token=False))
                ev = self._events.get(req["request_id"])
                if ev is not None:
                    ev.set()

    # ── views ────────────────────────────────────────────────────────────

    def _public(self, req: dict[str, Any], include_token: bool = False) -> dict[str, Any]:
        out = {
            "request_id": req["request_id"],
            "operation": req["operation"],
            "detail": req["detail"],
            "principal": req["principal"],
            "risk": req["risk"],
            "state": req["state"],
            "created_at": req["created_at"],
            "expires_at": req["expires_at"],
            "decided_by": req.get("decided_by", ""),
            "decision_via": req.get("decision_via", ""),
        }
        if include_token:
            out["token"] = req["token"]
        return out

    def pending(self) -> list[dict[str, Any]]:
        self._sweep_expired()
        now = time.time()
        rows = [self._public(r) for r in self._requests.values() if r["state"] == STATE_PENDING]
        rows.sort(key=lambda x: float(x["created_at"]), reverse=True)
        _ = now
        return rows

    def history(self, limit: int = 50) -> list[dict[str, Any]]:
        self._sweep_expired()
        rows = sorted(
            (self._public(r) for r in self._requests.values()),
            key=lambda x: float(x["created_at"]),
            reverse=True,
        )
        return rows[:limit]

    def get(self, request_id: str) -> dict[str, Any]:
        req = self._requests.get(request_id)
        if req is None:
            raise MobileApprovalError(f"no approval request {request_id!r}")
        return self._public(req)

    # ── delivery payloads ────────────────────────────────────────────────

    def telegram_text(self, request_id: str) -> str:
        """The exact message pushed to Telegram (token included once)."""
        req = self._requests.get(request_id)
        if req is None:
            raise MobileApprovalError(f"no approval request {request_id!r}")
        token = req["token"]
        lines = [
            "AGENTICOS APPROVAL REQUIRED",
            f"operation: {req['operation']}",
        ]
        if req["detail"]:
            lines.append(f"detail: {req['detail'][:400]}")
        if req["risk"]:
            lines.append(f"risk: {req['risk']}")
        if req["principal"]:
            lines.append(f"principal: {req['principal']}")
        ttl = max(0, int(float(req["expires_at"]) - time.time()))
        lines += [
            f"expires in: {ttl}s",
            "",
            f"approve: /approve {token}",
            f"reject:  /reject {token}",
        ]
        return "\n".join(lines)

    def approval_url(self, request_id: str, base_url: str) -> str:
        """The LOCAL decision-page URL encoded into the QR code."""
        req = self._requests.get(request_id)
        if req is None:
            raise MobileApprovalError(f"no approval request {request_id!r}")
        base = str(base_url or "").rstrip("/")
        if not base:
            raise MobileApprovalError(
                "base_url is required to build the approval link (the machine's "
                "LAN address, e.g. http://192.168.1.10:8000)"
            )
        return f"{base}/approve/{req['request_id']}?token={req['token']}"

    def qr_svg(self, request_id: str, base_url: str) -> str:
        """Locally rendered SVG QR for the approval URL."""
        url = self.approval_url(request_id, base_url)
        try:
            from agentic_os.adapters.gateway.qr_render import render_qr_svg

            return render_qr_svg(url)
        except Exception as exc:
            raise MobileApprovalError(f"QR rendering failed: {exc}") from exc

    # ── decisions ────────────────────────────────────────────────────────

    def _decide(self, req: dict[str, Any], approved: bool, by: str, via: str) -> dict[str, Any]:
        req["state"] = STATE_APPROVED if approved else STATE_REJECTED
        req["decided_at"] = time.time()
        req["decided_by"] = str(by)
        req["decision_via"] = str(via)
        self._audit("decided", req)
        self._publish(
            "approval.mobile.decided",
            {
                "request_id": req["request_id"],
                "approved": approved,
                "by": req["decided_by"],
                "via": req["decision_via"],
            },
        )
        ev = self._events.get(req["request_id"])
        if ev is not None:
            ev.set()
        return self._public(req)

    def decide_by_token(self, token: str, approved: bool, by: str = "") -> dict[str, Any]:
        self._sweep_expired()
        if not str(token).strip():
            raise MobileApprovalError("token is required")
        for req in self._requests.values():
            if secrets.compare_digest(str(req.get("token", "")), str(token)):
                if req["state"] != STATE_PENDING:
                    raise MobileApprovalError(
                        f"request {req['request_id']} is already {req['state']} "
                        "(the token is single-use)"
                    )
                return self._decide(req, approved, by=by, via="token")
        raise MobileApprovalError("unknown or expired token; nothing was decided")

    def decide(self, request_id: str, approved: bool, by: str = "operator") -> dict[str, Any]:
        self._sweep_expired()
        req = self._requests.get(request_id)
        if req is None:
            raise MobileApprovalError(f"no approval request {request_id!r}")
        if req["state"] != STATE_PENDING:
            raise MobileApprovalError(f"request is already {req['state']}")
        return self._decide(req, approved, by=by, via="console")

    async def wait_for_decision(
        self, request_id: str, timeout_s: float | None = None
    ) -> dict[str, Any]:
        """Await the human decision (or expiry). Returns the final state."""
        self._sweep_expired()
        req = self._requests.get(request_id)
        if req is None:
            raise MobileApprovalError(f"no approval request {request_id!r}")
        ev = self._events.get(request_id)
        if ev is None:
            raise MobileApprovalError(f"no waiter for {request_id!r}")
        budget = self._ttl_s if timeout_s is None else float(timeout_s)
        remaining = max(0.0, float(req["expires_at"]) - time.time())
        try:
            await asyncio.wait_for(ev.wait(), timeout=min(budget, remaining))
        except TimeoutError:
            self._sweep_expired()
        self._sweep_expired()
        return self._public(req)

    # ── audit + bus ──────────────────────────────────────────────────────

    def _audit(self, action: str, req: dict[str, Any]) -> None:
        entry = {
            "ts": time.time(),
            "action": action,
            "request_id": req["request_id"],
            "operation": req["operation"],
            "state": req["state"],
            "by": req.get("decided_by", ""),
            "via": req.get("decision_via", ""),
        }
        try:
            with self._audit_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception:
            log.debug("approval audit append failed", exc_info=True)

    def audit_tail(self, limit: int = 50) -> list[dict[str, Any]]:
        if not self._audit_path.exists():
            return []
        rows: list[dict[str, Any]] = []
        try:
            for line in self._audit_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
        except Exception:
            return []
        return rows[-limit:]

    def _publish(self, event_type: str, payload: dict[str, Any]) -> None:
        if self._bus is None:
            return
        try:
            from agentic_os.domain.events import EventEnvelope

            envelope = EventEnvelope(
                type=event_type,
                source="security.mobile_approval",
                topic="system",
                payload=payload,
            )
            loop = asyncio.get_running_loop()
            task = loop.create_task(self._apublish(envelope))
            self._bg_tasks.add(task)
            task.add_done_callback(self._bg_tasks.discard)
        except RuntimeError:
            log.debug("approval publish skipped: no running loop")
        except Exception:
            log.debug("approval publish failed", exc_info=True)

    async def _apublish(self, envelope: Any) -> None:
        try:
            await self._bus.publish(envelope)
        except Exception:
            log.debug("approval bus publish failed", exc_info=True)


# Process singleton wired lazily by the API layer with the live bus.
mobile_approval_bridge: MobileApprovalBridge | None = None
_bridge_lock = asyncio.Lock()


async def get_mobile_approval_bridge(bus: Any = None) -> MobileApprovalBridge:
    global mobile_approval_bridge
    async with _bridge_lock:
        if mobile_approval_bridge is None:
            mobile_approval_bridge = MobileApprovalBridge(bus=bus)
        return mobile_approval_bridge


def _escape(s: str) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def decision_page_html(request_id: str, operation: str, detail: str, valid: bool) -> str:
    """Minimal no-JS decision page served at /approve/{id}."""
    if not valid:
        return (
            "<html><head><meta charset='utf-8'><title>AgenticOS approval</title></head>"
            "<body style='font-family:sans-serif;background:#0b0d12;color:#e5e7eb;"
            "text-align:center;padding-top:4em'>"
            "<h2>Invalid or expired link</h2>"
            "<p>This approval link is unknown, expired, or already used. "
            "Nothing was decided.</p></body></html>"
        )
    safe_op = _escape(operation)[:200]
    safe_detail = _escape(detail)[:600]
    return (
        "<html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<title>AgenticOS approval</title></head>"
        "<body style='font-family:sans-serif;background:#0b0d12;color:#e5e7eb;"
        "text-align:center;padding:2em'>"
        "<h2>Approval required</h2>"
        f"<p style='font-size:1.1em'><b>{safe_op}</b></p>"
        f"<pre style='white-space:pre-wrap;color:#9ca3af;text-align:left;"
        f"background:#11141b;padding:1em;border-radius:8px'>{safe_detail}</pre>"
        "<form method='post' style='margin-top:2em'>"
        "<button name='decision' value='approve' style='padding:1em 2.5em;"
        "font-size:1.2em;background:#059669;color:white;border:0;border-radius:8px;"
        "margin:0.5em'>Approve</button>"
        "<button name='decision' value='reject' style='padding:1em 2.5em;"
        "font-size:1.2em;background:#dc2626;color:white;border:0;border-radius:8px;"
        "margin:0.5em'>Reject</button>"
        "</form></body></html>"
    )


__all__ = [
    "MobileApprovalBridge",
    "MobileApprovalError",
    "decision_page_html",
    "get_mobile_approval_bridge",
]
