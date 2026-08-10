"""Remote Prompt Service — single shared adapter for remote mission submission.

Telegram and WhatsApp gateways route every user message through this
service, which forwards the prompt into the SAME mission pipeline the
browser Prompt Center uses.  It holds references to the exact mission
endpoint functions and the shared in-memory mission store, so a remote
mission is indistinguishable from a web mission — no duplicated mission
logic lives here (DRY by construction).

Responsibilities that live HERE (never in the channel adapters):

* authorization — map a remote identity to an allowed AgenticOS identity
* rate limiting — per (channel, external account)
* idempotency — never submit the same message twice
* validation — prompt length, empty prompts
* audit — publish ``audit.event`` for every decision
* workspace safety — remote input can NEVER carry a workspace path; the
  mission pipeline uses the backend's own workspace root only.

The channel adapters remain responsible for transport (polling / bridge
subprocess), their own connection state, and formatting replies.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from agentic_os.domain.events import EventEnvelope, Topic
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.event_bus import EventBus

log = get_logger("gateway.remote_prompt")

# ── channel constants ─────────────────────────────────────────────────────────

CHANNEL_WEB = "WEB"
CHANNEL_LOCAL = "LOCAL"
CHANNEL_TELEGRAM = "TELEGRAM"
CHANNEL_WHATSAPP = "WHATSAPP"
CHANNEL_API = "API"
VALID_CHANNELS = {CHANNEL_WEB, CHANNEL_LOCAL, CHANNEL_TELEGRAM, CHANNEL_WHATSAPP, CHANNEL_API}

# Sensitive operations are NEVER exposed through messaging, regardless of
# allow-list configuration.
SENSITIVE_ACTIONS = frozenset(
    {
        "provider.config",
        "security.settings",
        "plugin.install",
        "workspace.delete",
        "user.manage",
        "system.shutdown",
    }
)

_DEFAULT_RATE_PER_MINUTE = 20
_DEFAULT_MAX_PROMPT_CHARS = 4000


# ── exceptions ────────────────────────────────────────────────────────────────


class RemotePromptError(Exception):
    """Base class for remote-prompt failures (user-safe messages only)."""

    def __init__(self, message: str, kind: str = "error") -> None:
        super().__init__(message)
        self.kind = kind


class AuthorizationError(RemotePromptError):
    def __init__(self, channel: str, external_id: str) -> None:
        super().__init__(
            "You are not authorized to perform this action on Mission Control.",
            kind="unauthorized",
        )
        self.channel = channel
        self.external_id = external_id


class RateLimitError(RemotePromptError):
    def __init__(self) -> None:
        super().__init__(
            "Too many requests. Please slow down and try again shortly.", kind="rate_limited"
        )


class DuplicateMessageError(RemotePromptError):
    def __init__(self, message_id: str) -> None:
        super().__init__("This message was already processed.", kind="duplicate")
        self.message_id = message_id


class ValidationError(RemotePromptError):
    def __init__(self, message: str) -> None:
        super().__init__(message, kind="validation")


class NotFoundError(RemotePromptError):
    def __init__(self, mission_id: str) -> None:
        super().__init__(
            f"Mission {mission_id[:12]} was not found. Use /missions to list your missions.",
            kind="not_found",
        )
        self.mission_id = mission_id


# ── identity ──────────────────────────────────────────────────────────────────


@dataclass
class RemoteIdentity:
    """A remote device/account mapped to an AgenticOS identity.

    The external identifiers (Telegram user id, WhatsApp number) are
    considered *claims*, not trust.  Authorization is decided by the
    allow-list configured for the channel.
    """

    channel: str  # TELEGRAM | WHATSAPP
    external_account_id: str
    session_id: str = ""
    workspace_id: str = ""  # resolved from backend state, never remote input
    display_name: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    last_seen: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def key(self) -> str:
        return f"{self.channel}:{self.external_account_id}"

    def to_dict(self) -> dict:
        return {
            "channel": self.channel,
            "external_account_id": self.external_account_id,
            "session_id": self.session_id,
            "workspace_id": self.workspace_id,
            "display_name": self.display_name,
            "created_at": self.created_at,
            "last_seen": self.last_seen,
        }


# ── service ───────────────────────────────────────────────────────────────────


MissionFn = Callable[..., Awaitable[dict]]


async def _empty_agents() -> list[dict]:
    return []


class RemotePromptService:
    """Shared remote-mission service used by Telegram + WhatsApp gateways.

    Args:
        bus: the platform EventBus (audit + notification events).
        create_mission_fn: the ``POST /api/missions`` handler body.
        plan_mission_fn: the ``/api/missions/{id}/plan`` handler.
        start_mission_fn: the ``/api/missions/{id}/start`` handler.
        cancel_mission_fn: the ``/api/missions/{id}/cancel`` handler.
        missions_store: the shared in-memory ``{mission_id: Mission}`` dict.
        agents_fn: callable returning the live agent list (same source as
            ``/api/agents``); used by the ``/agents`` command.
        allowed_identities: ``{channel: {external_account_id, ...}}``.  When a
            channel is absent, that channel defaults to allow (matching the
            legacy behavior where no allow-list means everyone may submit).
        rate_limit_per_minute: max submissions per identity per minute.
        max_prompt_chars: hard cap on remote prompt length.
    """

    def __init__(
        self,
        *,
        bus: EventBus,
        create_mission_fn: MissionFn,
        plan_mission_fn: MissionFn,
        start_mission_fn: MissionFn,
        cancel_mission_fn: MissionFn,
        missions_store: dict[str, Any],
        agents_fn: Callable[[], Awaitable[list[dict]]] | None = None,
        allowed_identities: dict[str, set[str]] | None = None,
        rate_limit_per_minute: int = _DEFAULT_RATE_PER_MINUTE,
        max_prompt_chars: int = _DEFAULT_MAX_PROMPT_CHARS,
    ) -> None:
        self._bus = bus
        self._create = create_mission_fn
        self._plan = plan_mission_fn
        self._start = start_mission_fn
        self._cancel = cancel_mission_fn
        self._missions = missions_store
        self._agents_fn = agents_fn or _empty_agents
        self._allowed = allowed_identities or {}
        self._rate_limit_per_minute = rate_limit_per_minute
        self._max_prompt_chars = max_prompt_chars
        self._processed_messages: deque[str] = deque(maxlen=500)
        self._rate: dict[str, list[float]] = {}

    # ── public API ──────────────────────────────────────────────────────────

    def validate_channel(self, channel: str) -> str:
        """Normalize + validate a channel string (used at wiring time)."""
        channel = (channel or CHANNEL_WEB).upper()
        if channel not in VALID_CHANNELS:
            raise ValueError(f"Unknown channel: {channel}")
        return channel

    def authorize(self, identity: RemoteIdentity, action: str = "mission.submit") -> bool:
        """True if *identity* may perform *action* on this channel."""
        if action in SENSITIVE_ACTIONS:
            return False
        allowed = self._allowed.get(identity.channel)
        if not allowed:
            return True  # no allow-list → default allow (legacy behavior)
        return identity.external_account_id in allowed

    async def submit(
        self,
        *,
        prompt: str,
        identity: RemoteIdentity,
        agents: list[str] | None = None,
        message_id: str = "",
    ) -> dict:
        """Create + plan + start a real mission from a remote prompt.

        Returns the mission dict (with channel + remote identity metadata).
        Raises a user-safe :class:`RemotePromptError` subclass on any failure.
        """
        # idempotency
        if self._seen_message(message_id):
            await self._audit(
                identity, "mission.submit", "duplicate", meta={"message_id": message_id}
            )
            raise DuplicateMessageError(message_id)

        # authorization
        if not self.authorize(identity, "mission.submit"):
            await self._audit(identity, "mission.submit", "deny")
            raise AuthorizationError(identity.channel, identity.external_account_id)

        # rate limiting
        if not self._check_rate(identity):
            await self._audit(identity, "mission.submit", "rate_limited")
            raise RateLimitError()

        # validation — remote input can never carry a workspace path here
        prompt = (prompt or "").strip()
        if not prompt:
            raise ValidationError("The prompt is empty. Send a task description.")
        if len(prompt) > self._max_prompt_chars:
            raise ValidationError(
                f"Prompt is too long ({len(prompt)} > {self._max_prompt_chars} chars)."
            )

        identity.last_seen = datetime.now(UTC).isoformat()
        title = prompt.split("\n")[0][:60] or "Remote Prompt Mission"
        body: dict = {
            "title": title,
            "description": prompt,
            "prompt": prompt,
            "priority": "high",
            "execution_mode": "hybrid",
            "preferred_agents": [str(a) for a in agents] if agents else [],
            "channel": identity.channel,
            "remote": identity.to_dict(),
        }

        try:
            mission = await self._create(body)
        except RemotePromptError:
            raise
        except Exception as exc:
            await self._audit(identity, "mission.submit", "failed", meta={"error": str(exc)})
            log.warning("remote.create_failed", error=str(exc))
            raise RemotePromptError(
                "Mission could not be created. The orchestrator may be busy.", kind="failed"
            ) from exc

        mid = mission.get("id", "")
        await self._audit(identity, "mission.submit", "allow", target=mid)

        # plan + start through the exact browser path
        try:
            await self._plan(mid)
            await self._start(mid)
        except Exception as exc:
            log.warning("remote.mission_start_failed", mission=mid, error=str(exc))

        current = self._missions.get(mid)
        return current.to_dict() if hasattr(current, "to_dict") else mission

    async def cancel(self, mission_id: str, identity: RemoteIdentity) -> dict:
        """Cancel a mission through the existing cancellation mechanism."""
        mission = self._missions.get(mission_id)
        if mission is None:
            await self._audit(identity, "mission.cancel", "not_found", target=mission_id)
            raise NotFoundError(mission_id)
        if not self.authorize(identity, "mission.cancel"):
            await self._audit(identity, "mission.cancel", "deny", target=mission_id)
            raise AuthorizationError(identity.channel, identity.external_account_id)
        # Ownership: only the originating external account may cancel its own
        # remote mission (unless it is an internal/empty identity).
        remote = getattr(mission, "remote", {}) or {}
        owner = remote.get("external_account_id", "")
        if owner and identity.external_account_id and owner != identity.external_account_id:
            await self._audit(
                identity,
                "mission.cancel",
                "deny",
                target=mission_id,
                meta={"reason": "not_owner"},
            )
            raise AuthorizationError(identity.channel, identity.external_account_id)
        result = await self._cancel(mission_id)
        await self._audit(identity, "mission.cancel", "allow", target=mission_id)
        return result

    def list_missions(self) -> list[dict]:
        missions = sorted(self._missions.values(), key=lambda x: x.created_at, reverse=True)
        return [m.to_dict() for m in missions]

    def get_mission(self, mission_id: str) -> dict | None:
        m = self._missions.get(mission_id)
        return m.to_dict() if m else None

    async def list_agents(self) -> list[dict]:
        return list(await self._agents_fn() or [])

    # ── internals ───────────────────────────────────────────────────────────

    def _seen_message(self, message_id: str) -> bool:
        if not message_id:
            return False
        if message_id in self._processed_messages:
            return True
        self._processed_messages.append(message_id)
        return False

    def _check_rate(self, identity: RemoteIdentity) -> bool:
        now = time.monotonic()
        key = identity.key()
        window = [t for t in self._rate.get(key, []) if now - t < 60.0]
        if len(window) >= self._rate_limit_per_minute:
            return False
        window.append(now)
        self._rate[key] = window
        return True

    async def _audit(
        self,
        identity: RemoteIdentity,
        action: str,
        outcome: str,
        target: str = "",
        meta: dict | None = None,
    ) -> None:
        try:
            await self._bus.publish(
                EventEnvelope(
                    type="audit.event",
                    source="remote_prompt",
                    topic=Topic.AUDIT.value,
                    payload={
                        "timestamp": datetime.now(UTC).isoformat(),
                        "principal": identity.external_account_id,
                        "channel": identity.channel,
                        "action": action,
                        "outcome": outcome,
                        "target": target,
                        "meta": meta or {},
                    },
                )
            )
        except Exception:
            log.debug("remote.audit_failed", exc_info=True)


__all__ = [
    "RemotePromptService",
    "RemoteIdentity",
    "RemotePromptError",
    "AuthorizationError",
    "RateLimitError",
    "DuplicateMessageError",
    "ValidationError",
    "NotFoundError",
    "CHANNEL_TELEGRAM",
    "CHANNEL_WHATSAPP",
    "CHANNEL_WEB",
    "CHANNEL_API",
]
