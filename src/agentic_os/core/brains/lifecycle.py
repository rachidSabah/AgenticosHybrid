"""BrainLifecycleManager — state machine for BrainStatus transitions.

Tracks allowed status transitions and maintains an ordered history of
status changes for each brain.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime

from agentic_os.domain.brains import BrainRecord, BrainStatus
from agentic_os.infrastructure.logging import get_logger

log = get_logger("brains.lifecycle")


@dataclass(frozen=True)
class StatusTransition:
    """A single recorded status transition."""

    brain_id: str
    from_status: BrainStatus | None
    to_status: BrainStatus
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    reason: str = ""


# ── Transition rules ────────────────────────────────────────────────────────
# Maps each source status to the set of allowed target statuses.

_ALLOWED_TRANSITIONS: dict[BrainStatus, set[BrainStatus]] = {
    BrainStatus.DISCOVERED: {
        BrainStatus.REGISTERED,
        BrainStatus.REMOVED,
        BrainStatus.FAILED,
    },
    BrainStatus.REGISTERED: {
        BrainStatus.CONNECTED,
        BrainStatus.DISCONNECTED,
        BrainStatus.REMOVED,
        BrainStatus.FAILED,
    },
    BrainStatus.CONNECTED: {
        BrainStatus.IDLE,
        BrainStatus.BUSY,
        BrainStatus.DISCONNECTED,
        BrainStatus.HEALTHY,
        BrainStatus.UNHEALTHY,
        BrainStatus.DEGRADED,
        BrainStatus.REMOVED,
    },
    BrainStatus.DISCONNECTED: {
        BrainStatus.CONNECTED,
        BrainStatus.REMOVED,
        BrainStatus.FAILED,
        BrainStatus.RECOVERING,
    },
    BrainStatus.BUSY: {
        BrainStatus.IDLE,
        BrainStatus.EXECUTING,
        BrainStatus.DISCONNECTED,
        BrainStatus.FAILED,
        BrainStatus.PAUSED,
    },
    BrainStatus.IDLE: {
        BrainStatus.BUSY,
        BrainStatus.CONNECTED,
        BrainStatus.DISCONNECTED,
        BrainStatus.HEALTHY,
        BrainStatus.UNHEALTHY,
        BrainStatus.PAUSED,
        BrainStatus.REMOVED,
    },
    BrainStatus.EXECUTING: {
        BrainStatus.IDLE,
        BrainStatus.FAILED,
        BrainStatus.DISCONNECTED,
        BrainStatus.PAUSED,
    },
    BrainStatus.HEALTHY: {
        BrainStatus.IDLE,
        BrainStatus.DEGRADED,
        BrainStatus.UNHEALTHY,
        BrainStatus.DISCONNECTED,
    },
    BrainStatus.UNHEALTHY: {
        BrainStatus.HEALTHY,
        BrainStatus.DEGRADED,
        BrainStatus.FAILED,
        BrainStatus.RECOVERING,
        BrainStatus.DISCONNECTED,
    },
    BrainStatus.DEGRADED: {
        BrainStatus.HEALTHY,
        BrainStatus.UNHEALTHY,
        BrainStatus.FAILED,
        BrainStatus.RECOVERING,
    },
    BrainStatus.FAILED: {
        BrainStatus.RECOVERING,
        BrainStatus.REMOVED,
        BrainStatus.DISCONNECTED,
    },
    BrainStatus.REMOVED: set(),  # Terminal state — no valid transitions out.
    BrainStatus.PAUSED: {
        BrainStatus.IDLE,  # resume
        BrainStatus.REMOVED,
    },
    BrainStatus.RESUMED: {
        BrainStatus.IDLE,
        BrainStatus.CONNECTED,
    },
    BrainStatus.RESTARTING: {
        BrainStatus.IDLE,
        BrainStatus.FAILED,
        BrainStatus.REMOVED,
    },
    BrainStatus.SHUTDOWN: {
        BrainStatus.REMOVED,
    },
    BrainStatus.RECOVERING: {
        BrainStatus.IDLE,
        BrainStatus.HEALTHY,
        BrainStatus.FAILED,
        BrainStatus.DISCONNECTED,
    },
}


class BrainLifecycleManager:
    """State machine governing :class:`BrainStatus` transitions.

    Tracks allowed transitions and maintains an ordered history of every
    status change per brain.

    Thread-safety
    -------------
    Internal state (history) is guarded by an ``asyncio.Lock``.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._history: list[StatusTransition] = []

    # ── Transition ──────────────────────────────────────────────────────────

    async def transition(
        self,
        record: BrainRecord,
        target_status: BrainStatus,
        reason: str = "",
    ) -> BrainRecord | None:
        """Attempt a status transition for a brain.

        Args:
            record: The current :class:`BrainRecord`.
            target_status: The desired new status.
            reason: Optional human-readable explanation for the transition.

        Returns:
            A new :class:`BrainRecord` with the updated status if the
            transition is allowed, or ``None`` if the transition is
            rejected by the rules.

        Raises:
            ValueError: If *target_status* equals the current status
                (no-op transitions are rejected unless explicitly desired).
        """
        current_status = record.status
        if current_status == target_status:
            raise ValueError(
                f"Transition rejected: brain {record.id} is already "
                f"in status {current_status.value}"
            )

        allowed = _ALLOWED_TRANSITIONS.get(current_status, set())
        if target_status not in allowed:
            log.warning(
                "Transition %s -> %s rejected for brain %s",
                current_status.value,
                target_status.value,
                record.id,
            )
            return None

        updated = replace(record, status=target_status)
        transition = StatusTransition(
            brain_id=record.id,
            from_status=current_status,
            to_status=target_status,
            reason=reason,
        )

        async with self._lock:
            self._history.append(transition)

        log.debug(
            "Transition: %s %s -> %s %s",
            record.id,
            current_status.value,
            target_status.value,
            reason,
        )
        return updated

    # ── History ─────────────────────────────────────────────────────────────

    async def get_history(
        self,
        brain_id: str | None = None,
        limit: int = 0,
    ) -> list[StatusTransition]:
        """Return recorded status transitions.

        Args:
            brain_id: If provided, only return transitions for this brain.
            limit: Maximum entries to return.  0 means unlimited.

        Returns:
            Chronologically ordered list of :class:`StatusTransition`.
        """
        async with self._lock:
            if brain_id is not None:
                results = [t for t in self._history if t.brain_id == brain_id]
            else:
                results = list(self._history)

        if limit > 0:
            results = results[-limit:]
        return results

    async def clear_history(self, brain_id: str | None = None) -> int:
        """Clear transition history.

        Args:
            brain_id: If provided, only clear entries for this brain.
                If ``None``, clear all history.

        Returns:
            Number of entries removed.
        """
        async with self._lock:
            if brain_id is None:
                count = len(self._history)
                self._history.clear()
            else:
                before = len(self._history)
                self._history = [t for t in self._history if t.brain_id != brain_id]
                count = before - len(self._history)
        return count

    async def last_transition(self, brain_id: str) -> StatusTransition | None:
        """Return the most recent transition for a specific brain, or ``None``."""
        async with self._lock:
            for t in reversed(self._history):
                if t.brain_id == brain_id:
                    return t
        return None

    # ── Rules introspection ─────────────────────────────────────────────────

    def allowed_transitions(self, status: BrainStatus | None = None) -> dict[str, list[str]]:
        """Return the full transition map or allowed targets for one status.

        Args:
            status: If provided, only return the allowed target statuses
                for this source status.

        Returns:
            A dict mapping ``source_status.value`` → list of ``target_status.value``.
        """
        if status is not None:
            allowed = _ALLOWED_TRANSITIONS.get(status, set())
            return {status.value: sorted(s.value for s in allowed)}
        return {
            src.value: sorted(s.value for s in targets)
            for src, targets in _ALLOWED_TRANSITIONS.items()
        }

    def is_terminal(self, status: BrainStatus) -> bool:
        """Return ``True`` if *status* is a terminal state (no outgoing edges)."""
        return len(_ALLOWED_TRANSITIONS.get(status, set())) == 0

    @property
    def terminal_statuses(self) -> list[str]:
        """Return the list of terminal status values."""
        return [s.value for s, targets in _ALLOWED_TRANSITIONS.items() if len(targets) == 0]
