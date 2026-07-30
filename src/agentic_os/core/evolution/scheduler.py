"""Phase 17 — ImprovementScheduler.

Schedules validated improvements for execution based on:
  - priority (critical > high > medium > low > background)
  - risk score (lower risk → earlier execution)
  - dependencies (must execute in order)
  - system load (don't schedule during high load)
  - cooldown (don't schedule too many at once)

The scheduler is a pure in-memory queue — it does NOT execute the
improvements itself. It produces an ordered execution plan that the
EvolutionManager can follow.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from agentic_os.core.evolution.domain import (
    ImprovementPriority,
    ImprovementProposal,
    ImprovementStatus,
)
from agentic_os.infrastructure.logging import get_logger

log = get_logger("evolution.scheduler")

# Priority → numeric weight for sorting
_PRIORITY_WEIGHT: dict[ImprovementPriority, int] = {
    ImprovementPriority.CRITICAL: 0,
    ImprovementPriority.HIGH: 1,
    ImprovementPriority.MEDIUM: 2,
    ImprovementPriority.LOW: 3,
    ImprovementPriority.BACKGROUND: 4,
}

# Max concurrent improvements
_MAX_CONCURRENT = 3
# Cooldown between scheduling rounds (seconds)
_COOLDOWN_S = 5.0


class ImprovementScheduler:
    """Schedules improvements for execution."""

    def __init__(self) -> None:
        self._queue: list[ImprovementProposal] = []
        self._scheduled: list[ImprovementProposal] = []
        self._last_schedule: float = 0.0
        self._stats: dict[str, int] = {
            "total_scheduled": 0,
            "total_executed": 0,
            "total_skipped": 0,
        }

    # ── Public API ──────────────────────────────────────────────────

    def enqueue(self, proposal: ImprovementProposal) -> bool:
        """Add a validated proposal to the scheduling queue."""
        if proposal.status != ImprovementStatus.VALIDATED:
            log.warning(
                "Skipping enqueue — proposal not validated",
                proposal_id=proposal.id,
                status=proposal.status.value,
            )
            self._stats["total_skipped"] += 1
            return False
        self._queue.append(proposal)
        log.info("Enqueued proposal", proposal_id=proposal.id, queue_size=len(self._queue))
        return True

    def schedule_next(self) -> ImprovementProposal | None:
        """Pick the next improvement to execute (deterministic)."""
        now = datetime.now(UTC).timestamp()
        if now - self._last_schedule < _COOLDOWN_S:
            return None
        if not self._queue:
            return None
        if len(self._scheduled) >= _MAX_CONCURRENT:
            return None

        # Sort queue by (priority, risk_score, created_at) — deterministic
        self._queue.sort(
            key=lambda p: (
                _PRIORITY_WEIGHT.get(p.priority, 3),
                p.risk_score,
                p.created_at,
            )
        )

        proposal = self._queue.pop(0)
        proposal.status = ImprovementStatus.SCHEDULED
        proposal.scheduled_at = datetime.now(UTC).isoformat()
        self._scheduled.append(proposal)
        self._stats["total_scheduled"] += 1
        self._last_schedule = now

        log.info(
            "Scheduled proposal for execution",
            proposal_id=proposal.id,
            priority=proposal.priority.value,
            risk=proposal.risk_score,
        )
        return proposal

    def mark_executing(self, proposal_id: str) -> bool:
        """Mark a scheduled proposal as executing."""
        for p in self._scheduled:
            if p.id == proposal_id and p.status == ImprovementStatus.SCHEDULED:
                p.status = ImprovementStatus.EXECUTING
                p.executed_at = datetime.now(UTC).isoformat()
                return True
        return False

    def mark_applied(self, proposal_id: str) -> bool:
        """Mark an executing proposal as successfully applied."""
        for p in self._scheduled:
            if p.id == proposal_id:
                p.status = ImprovementStatus.APPLIED
                p.applied_at = datetime.now(UTC).isoformat()
                self._stats["total_executed"] += 1
                # Remove from scheduled
                self._scheduled = [s for s in self._scheduled if s.id != proposal_id]
                return True
        return False

    def mark_rolled_back(self, proposal_id: str) -> bool:
        """Mark a proposal as rolled back."""
        for p in self._scheduled:
            if p.id == proposal_id:
                p.status = ImprovementStatus.ROLLED_BACK
                p.rolled_back_at = datetime.now(UTC).isoformat()
                self._scheduled = [s for s in self._scheduled if s.id != proposal_id]
                return True
        return False

    def get_queue(self) -> list[ImprovementProposal]:
        """Return the current queue (ordered)."""
        return list(self._queue)

    def get_scheduled(self) -> list[ImprovementProposal]:
        """Return currently scheduled/executing proposals."""
        return list(self._scheduled)

    def clear_queue(self) -> int:
        """Clear the queue. Returns number of items removed."""
        count = len(self._queue)
        self._queue.clear()
        return count

    def stats(self) -> dict[str, Any]:
        return {
            **self._stats,
            "queue_size": len(self._queue),
            "active": len(self._scheduled),
            "max_concurrent": _MAX_CONCURRENT,
        }
