"""DecisionEngine — selects the optimal runtime for a task.

Uses multi-factor scoring that considers:
  - Health (from BrainRegistry)
  - Latency (from BrainRegistry)
  - Capability match (from capability graph)
  - Historical success (from Learning engine)
  - Current load (from brain.current_tasks)
  - Availability (health >= 50)

Does NOT replace the existing ProviderRouter — it extends it with
executive-level scoring that can use the Learning engine's historical
data. The DecisionEngine records every decision for auditability.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agentic_os.core.executive.domain import Decision
from agentic_os.infrastructure.logging import get_logger

if TYPE_CHECKING:
    from agentic_os.core.brains.registry import BrainRegistry
    from agentic_os.core.learning.manager import LearningManager

log = get_logger("executive.decision")


class DecisionEngine:
    """Selects the optimal runtime for a task.

    The engine is stateless — each call to ``select`` is independent.
    Decisions are recorded in an in-memory ring buffer for the
    ``/api/executive/decisions`` endpoint.
    """

    # Scoring weights (must sum to 1.0)
    WEIGHT_HEALTH = 0.30
    WEIGHT_LATENCY = 0.20
    WEIGHT_CAPABILITY = 0.20
    WEIGHT_SUCCESS_RATE = 0.15
    WEIGHT_LOAD = 0.15

    MAX_DECISION_HISTORY = 500

    def __init__(
        self,
        brain_registry: BrainRegistry | None = None,
        learning: LearningManager | None = None,
    ) -> None:
        self._registry: BrainRegistry | None = brain_registry
        self._learning: LearningManager | None = learning
        self._decisions: list[Decision] = []

    def set_registry(self, registry: BrainRegistry) -> None:
        """Inject the BrainRegistry (called by ExecutiveController after wiring)."""
        self._registry = registry

    def set_learning(self, learning: LearningManager) -> None:
        """Inject the LearningManager."""
        self._learning = learning

    async def select(
        self,
        required_capability: str = "",
        goal_id: str = "",
        task_id: str = "",
    ) -> Decision | None:
        """Select the best runtime for a task.

        Returns:
            A :class:`Decision` with the selected runtime + alternatives,
            or ``None`` if no runtimes are available.
        """
        if self._registry is None:
            return None

        try:
            brains = await self._registry.list_all()
        except Exception:
            log.exception("Failed to list brains for decision")
            return None

        if not brains:
            return None

        # Get historical success rates from the Learning engine
        success_rates = await self._get_success_rates()

        scored: list[tuple[Decision, float]] = []
        for b in brains:
            caps = list(b.capabilities) if b.capabilities else []
            health_score = b.health / 100.0
            latency_score = max(0.0, 1.0 - (b.latency / 5000.0)) if b.latency > 0 else 0.5
            cap_match = 1.0 if required_capability in caps or not required_capability else 0.0
            availability = 1.0 if b.health >= 50 else 0.0
            success_rate = success_rates.get(b.id, 0.5)
            load_score = max(0.0, 1.0 - (b.current_tasks / 10.0)) if b.current_tasks > 0 else 1.0

            confidence = (
                health_score * self.WEIGHT_HEALTH
                + latency_score * self.WEIGHT_LATENCY
                + cap_match * self.WEIGHT_CAPABILITY
                + success_rate * self.WEIGHT_SUCCESS_RATE
                + load_score * self.WEIGHT_LOAD
            )
            # Penalize unavailable runtimes heavily
            if availability == 0.0:
                confidence *= 0.1

            # Risk: inverse of confidence, amplified by load and low health
            risk = round(
                (1.0 - confidence) * 0.5 + (1.0 - load_score) * 0.3 + (1.0 - availability) * 0.2,
                3,
            )

            # Human-readable reasoning
            reasoning_parts = [f"health={b.health:.0f}", f"latency={b.latency:.0f}ms"]
            if required_capability and cap_match == 0.0:
                reasoning_parts.append(f"missing capability '{required_capability}'")
            if b.current_tasks > 0:
                reasoning_parts.append(f"load={b.current_tasks} tasks")
            reasoning = "; ".join(reasoning_parts)

            decision = Decision(
                goal_id=goal_id,
                task_id=task_id,
                selected_runtime=b.id,
                alternatives=[],
                confidence=round(confidence, 3),
                risk=risk,
                reasoning=reasoning,
                factors={
                    "health": round(health_score, 3),
                    "latency": round(latency_score, 3),
                    "capability_match": cap_match,
                    "success_rate": round(success_rate, 3),
                    "load": round(load_score, 3),
                    "availability": availability,
                    "risk": risk,
                    "brain_name": b.display_name,
                    "health_raw": b.health,
                    "latency_raw": b.latency,
                },
            )
            scored.append((decision, confidence))

        if not scored:
            return None

        # Sort by confidence descending
        scored.sort(key=lambda x: x[1], reverse=True)
        best = scored[0][0]
        best.alternatives = [s[0].selected_runtime for s in scored[1:4]]

        # Record in history
        self._decisions.append(best)
        if len(self._decisions) > self.MAX_DECISION_HISTORY:
            self._decisions = self._decisions[-self.MAX_DECISION_HISTORY :]

        log.info(
            "Decision: selected %s (confidence=%.3f) for goal=%s task=%s",
            best.selected_runtime,
            best.confidence,
            goal_id,
            task_id,
        )
        return best

    async def _get_success_rates(self) -> dict[str, float]:
        """Get per-runtime success rates from the Learning engine.

        Returns a dict of ``{brain_id: success_rate (0.0-1.0)}``.
        Falls back to 0.5 (neutral) when no history exists.
        """
        if self._learning is None:
            return {}
        try:
            stats = await self._learning.get_routing_stats()
            # If the learning engine exposes per-runtime stats, use them
            # Otherwise return empty (neutral 0.5 used as fallback)
            if isinstance(stats, dict):
                return {
                    k: float(v.get("success_rate", 0.5))
                    for k, v in stats.items()
                    if isinstance(v, dict)
                }
        except Exception:
            pass
        return {}

    def get_history(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return recent decisions for the ``/api/executive/decisions`` endpoint."""
        return [d.to_dict() for d in self._decisions[-limit:]]

    def get_metrics(self) -> dict[str, Any]:
        """Return decision-engine metrics for observability."""
        return {
            "total_decisions": len(self._decisions),
            "weights": {
                "health": self.WEIGHT_HEALTH,
                "latency": self.WEIGHT_LATENCY,
                "capability": self.WEIGHT_CAPABILITY,
                "success_rate": self.WEIGHT_SUCCESS_RATE,
                "load": self.WEIGHT_LOAD,
            },
        }
