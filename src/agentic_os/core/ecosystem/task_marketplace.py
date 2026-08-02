"""Phase 15 — TaskMarketplace.

A global task market where any caller can publish a task with required
capabilities, every eligible runtime submits a bid, and the marketplace
selects the best bid using a multi-criteria score:

    bid_score = 0.30 * capability_match
              + 0.20 * health
              + 0.15 * latency
              + 0.15 * availability
              + 0.10 * historical_success
              + 0.10 * trust

The selection is NEVER random — every weight is deterministic and
traceable to the bid's evidence.

The marketplace does NOT execute tasks itself. After awarding, it
returns the selected runtime + the bid's ``action`` payload so the
caller (ExecutiveController, MissionPlanner, etc.) can dispatch the
mission through the existing pipeline.

BrainRegistry remains the canonical source of runtimes — the marketplace
queries it on every bid request rather than maintaining its own list.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from agentic_os.core.ecosystem.domain import (
    MarketTask,
    TaskBid,
    TaskBidStrategy,
)
from agentic_os.infrastructure.logging import get_logger

if TYPE_CHECKING:
    from agentic_os.core.brains.registry import BrainRegistry
    from agentic_os.core.ecosystem.collaboration_network import CollaborationNetwork
    from agentic_os.ports.event_bus import EventBus

log = get_logger("ecosystem.task_marketplace")


# Default weights for the balanced strategy. Each strategy below adjusts
# these to emphasize its namesake dimension.
_BASE_WEIGHTS: dict[str, float] = {
    "capability_match": 0.30,
    "health": 0.20,
    "latency": 0.15,
    "availability": 0.15,
    "historical_success": 0.10,
    "trust": 0.10,
}

_STRATEGY_WEIGHTS: dict[TaskBidStrategy, dict[str, float]] = {
    TaskBidStrategy.CAPABILITY_MATCH: {
        **_BASE_WEIGHTS,
        "capability_match": 0.50,
        "health": 0.15,
        "latency": 0.10,
        "availability": 0.10,
        "historical_success": 0.08,
        "trust": 0.07,
    },
    TaskBidStrategy.LATENCY_OPTIMIZED: {
        **_BASE_WEIGHTS,
        "capability_match": 0.20,
        "health": 0.15,
        "latency": 0.40,
        "availability": 0.10,
        "historical_success": 0.08,
        "trust": 0.07,
    },
    TaskBidStrategy.HEALTH_OPTIMIZED: {
        **_BASE_WEIGHTS,
        "capability_match": 0.20,
        "health": 0.45,
        "latency": 0.10,
        "availability": 0.10,
        "historical_success": 0.08,
        "trust": 0.07,
    },
    TaskBidStrategy.TRUST_OPTIMIZED: {
        **_BASE_WEIGHTS,
        "capability_match": 0.20,
        "health": 0.15,
        "latency": 0.10,
        "availability": 0.10,
        "historical_success": 0.10,
        "trust": 0.35,
    },
    TaskBidStrategy.BALANCED: _BASE_WEIGHTS,
}


class TaskMarketplace:
    """Global task market with deterministic bid selection."""

    def __init__(
        self,
        brain_registry: BrainRegistry | None = None,
        collaboration_network: CollaborationNetwork | None = None,
        bus: EventBus | None = None,
    ) -> None:
        self._registry = brain_registry
        self._network = collaboration_network
        self._bus = bus
        self._tasks: dict[str, MarketTask] = {}
        self._history: list[dict[str, Any]] = []
        self._stats: dict[str, int] = {
            "published": 0,
            "awarded": 0,
            "completed": 0,
            "failed": 0,
            "cancelled": 0,
            "no_bids": 0,
        }

    # ── Dependency injection (called by EcosystemController) ────────

    def set_brain_registry(self, registry: BrainRegistry) -> None:
        self._registry = registry

    def set_collaboration_network(self, network: CollaborationNetwork) -> None:
        self._network = network

    def set_bus(self, bus: EventBus) -> None:
        self._bus = bus

    # ── Public API ──────────────────────────────────────────────────

    async def publish_task(
        self,
        title: str,
        description: str = "",
        required_capabilities: list[str] | None = None,
        priority: float = 0.5,
        deadline: str = "",
        payload: dict[str, Any] | None = None,
    ) -> MarketTask:
        """Publish a task to the marketplace. Triggers bid collection."""
        task = MarketTask(
            title=title,
            description=description,
            required_capabilities=list(required_capabilities or []),
            priority=max(0.0, min(1.0, priority)),
            deadline=deadline,
            payload=dict(payload or {}),
        )
        self._tasks[task.id] = task
        self._stats["published"] += 1
        await self._publish_event(
            "ecosystem.task.published",
            task.to_dict(),
        )
        # Immediately collect bids from all eligible runtimes
        await self.collect_bids(task.id)
        return task

    async def collect_bids(self, task_id: str) -> list[TaskBid]:
        """Ask every runtime in BrainRegistry to bid on the task."""
        task = self._tasks.get(task_id)
        if task is None:
            return []
        if self._registry is None:
            return []

        bids: list[TaskBid] = []
        try:
            brains = await self._registry.list_all()
        except Exception:
            log.exception("Failed to list brains for bidding on %s", task_id)
            return []

        for brain in brains:
            caps = list(brain.capabilities) if brain.capabilities else []
            # Only bid if the runtime has at least one required capability
            # OR no capabilities were specified (open task)
            if task.required_capabilities:
                matching = [c for c in task.required_capabilities if c in caps]
                if not matching:
                    continue

            health_score = max(0.0, min(1.0, brain.health / 100.0))
            availability = 1.0 if brain.health >= 50 else 0.0
            historical_success = 0.5  # default when no learning data
            if self._network is not None:
                stats = self._network.runtime_stats(brain.id)
                if stats["total"] > 0:
                    historical_success = stats["success_rate"]
                trust = stats["average_trust"]
            else:
                trust = 0.5

            cap_match = (
                1.0
                if not task.required_capabilities
                else len(matching) / len(task.required_capabilities)
            )

            bid = TaskBid(
                runtime_id=brain.id,
                runtime_name=brain.display_name,
                capabilities=caps,
                health=brain.health,
                latency=brain.latency,
                availability=availability,
                historical_success=historical_success,
                trust_score=trust,
                confidence=min(1.0, (health_score + cap_match + trust) / 3.0),
            )
            bids.append(bid)

        task.bids = bids
        task.status = "bidding"
        await self._publish_event(
            "ecosystem.task.bids_collected",
            {"task_id": task_id, "bid_count": len(bids)},
        )
        return bids

    async def select_bid(
        self,
        task_id: str,
        strategy: TaskBidStrategy | str = TaskBidStrategy.BALANCED,
    ) -> TaskBid | None:
        """Select the best bid for a task using a deterministic scoring formula."""
        task = self._tasks.get(task_id)
        if task is None or not task.bids:
            return None

        if isinstance(strategy, str):
            strategy = TaskBidStrategy(strategy)
        weights = _STRATEGY_WEIGHTS[strategy]

        scored: list[tuple[TaskBid, float]] = []
        for bid in task.bids:
            cap_match = (
                1.0
                if not task.required_capabilities
                else len([c for c in task.required_capabilities if c in bid.capabilities])
                / len(task.required_capabilities)
            )
            health_norm = max(0.0, min(1.0, bid.health / 100.0))
            latency_norm = max(0.0, 1.0 - (bid.latency / 5000.0)) if bid.latency > 0 else 0.5
            score = (
                weights["capability_match"] * cap_match
                + weights["health"] * health_norm
                + weights["latency"] * latency_norm
                + weights["availability"] * bid.availability
                + weights["historical_success"] * bid.historical_success
                + weights["trust"] * bid.trust_score
            )
            bid.bid_score = round(score, 4)
            scored.append((bid, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        if not scored:
            return None

        best_bid, best_score = scored[0]
        task.selected_bid = best_bid
        task.status = "awarded"
        task.awarded_at = datetime.now(UTC).isoformat()
        task.selection_rationale = (
            f"Selected via {strategy.value} strategy with bid_score={best_score:.4f}. "
            f"Weights: {weights}. "
            f"Runtime: {best_bid.runtime_name} (health={best_bid.health:.0f}, "
            f"latency={best_bid.latency:.0f}ms, trust={best_bid.trust_score:.3f})."
        )
        self._stats["awarded"] += 1

        await self._publish_event(
            "ecosystem.task.awarded",
            {
                "task_id": task_id,
                "selected_runtime": best_bid.runtime_id,
                "runtime_name": best_bid.runtime_name,
                "bid_score": best_bid.bid_score,
                "strategy": strategy.value,
                "rationale": task.selection_rationale,
            },
        )
        return best_bid

    async def complete_task(
        self, task_id: str, success: bool, result: dict[str, Any] | None = None
    ) -> None:
        """Mark a task as completed (or failed). Updates stats."""
        task = self._tasks.get(task_id)
        if task is None:
            return
        task.status = "completed" if success else "failed"
        task.completed_at = datetime.now(UTC).isoformat()
        self._stats["completed" if success else "failed"] += 1

        # Record collaboration: selected runtime + (optionally) co-executors
        if task.selected_bid and self._network is not None:
            self._network.record_collaboration(
                source=task.selected_bid.runtime_id,
                target=task.selected_bid.runtime_id,  # self-collaboration = solo task
                success=success,
                confidence=task.selected_bid.confidence,
                metadata={"task_id": task_id, "title": task.title},
            )

        self._history.append(
            {
                "task_id": task_id,
                "title": task.title,
                "selected_runtime": (task.selected_bid.runtime_id if task.selected_bid else None),
                "success": success,
                "result": dict(result or {}),
                "completed_at": task.completed_at,
            }
        )
        await self._publish_event(
            "ecosystem.task.completed" if success else "ecosystem.task.failed",
            {
                "task_id": task_id,
                "success": success,
                "selected_runtime": (task.selected_bid.runtime_id if task.selected_bid else None),
                "result": dict(result or {}),
            },
        )

    async def cancel_task(self, task_id: str, reason: str = "") -> bool:
        task = self._tasks.get(task_id)
        if task is None:
            return False
        task.status = "cancelled"
        self._stats["cancelled"] += 1
        await self._publish_event(
            "ecosystem.task.cancelled",
            {"task_id": task_id, "reason": reason},
        )
        return True

    # ── Queries ────────────────────────────────────────────────────

    def get_task(self, task_id: str) -> MarketTask | None:
        return self._tasks.get(task_id)

    def list_open_tasks(self) -> list[MarketTask]:
        return [t for t in self._tasks.values() if t.status in {"open", "bidding"}]

    def list_all_tasks(self, limit: int = 50) -> list[MarketTask]:
        return list(self._tasks.values())[-limit:]

    def get_history(self, limit: int = 50) -> list[dict[str, Any]]:
        return list(self._history[-limit:])

    def stats(self) -> dict[str, Any]:
        return {**self._stats, "active_tasks": len(self.list_open_tasks())}

    def to_dict(self) -> dict[str, Any]:
        return {
            "tasks": [t.to_dict() for t in self._tasks.values()],
            "history": list(self._history[-50:]),
            "stats": self.stats(),
        }

    # ── Helpers ─────────────────────────────────────────────────────

    async def _publish_event(self, topic: str, payload: dict[str, Any]) -> None:
        if self._bus is None:
            return
        try:
            from agentic_os.domain.events import EventEnvelope

            await self._bus.publish(
                EventEnvelope(
                    type=topic,
                    source="task.marketplace",
                    topic=topic,
                    payload=payload,
                )
            )
        except Exception:
            log.exception("Failed to publish %s", topic)
