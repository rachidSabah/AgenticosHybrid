"""Prediction Engine — estimates mission outcomes.

Uses historical decisions, reflection history, learning metrics,
and runtime statistics to predict:
  - probability of success
  - expected runtime
  - expected cost
  - expected failures / retries
  - confidence
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agentic_os.core.cognitive.domain import Prediction
from agentic_os.infrastructure.logging import get_logger

if TYPE_CHECKING:
    from agentic_os.core.cognitive.memory import CognitiveMemory
    from agentic_os.core.cognitive.world_model import WorldModel

log = get_logger("cognitive.prediction")


class PredictionEngine:
    """Predicts mission outcomes from historical data."""

    def __init__(
        self,
        world_model: WorldModel | None = None,
        cognitive_memory: CognitiveMemory | None = None,
    ) -> None:
        self._world = world_model
        self._mem = cognitive_memory
        self._predictions: list[Prediction] = []

    def set_world_model(self, wm: WorldModel) -> None:
        self._world = wm

    def set_memory(self, mem: CognitiveMemory) -> None:
        self._mem = mem

    async def predict(self, goal_id: str = "", required_capability: str = "") -> Prediction:
        """Generate a prediction for a goal/task."""
        if self._world is None:
            p = Prediction(goal_id=goal_id, confidence=0.0)
            self._predictions.append(p)
            return p

        world = await self._world.snapshot()
        runtimes = world.get("runtimes", {})
        mission_stats = world.get("mission_stats", {})
        historical = world.get("historical", {})

        # Probability of success from historical data
        total_hist = historical.get("successes", 0) + historical.get("failures", 0)
        base_success_rate = historical.get("successes", 0) / total_hist if total_hist > 0 else 0.5

        # Confidence: more history = higher confidence
        confidence = min(total_hist / 100.0, 1.0) if total_hist > 0 else 0.1

        # Expected failures / retries from mission stats
        total_missions = mission_stats.get("completed", 0) + mission_stats.get("failed", 0)
        expected_failures = 0
        expected_retries = 0
        if total_missions > 0:
            failure_rate = mission_stats.get("failed", 0) / total_missions
            expected_failures = max(0, int(failure_rate * 2))
            expected_retries = expected_failures

        # Expected runtime: based on available runtimes
        runtime_count = max(len(runtimes), 1)
        expected_runtime = max(60.0, 300.0 / runtime_count)

        # Expected cost: estimate based on runtime count
        expected_cost = 0.0

        # Factor in capability match
        cap_factor = 0.0
        if required_capability:
            matching = sum(
                1 for r in runtimes.values() if required_capability in r.get("capabilities", [])
            )
            cap_factor = matching / max(runtime_count, 1)
            if cap_factor > 0:
                base_success_rate = min(base_success_rate + 0.1, 1.0)
                confidence = min(confidence + 0.1, 1.0)
            else:
                base_success_rate = max(base_success_rate - 0.3, 0.0)

        p = Prediction(
            goal_id=goal_id,
            probability_of_success=round(base_success_rate, 3),
            expected_runtime_seconds=round(expected_runtime, 1),
            expected_cost=expected_cost,
            expected_failures=expected_failures,
            expected_retries=expected_retries,
            confidence=round(confidence, 3),
            factors={
                "total_historical": total_hist,
                "total_missions": total_missions,
                "available_runtimes": runtime_count,
                "capability_match": round(cap_factor, 3) if required_capability else None,
            },
        )
        self._predictions.append(p)
        if self._mem is not None:
            try:
                await self._mem.store_prediction(p.id, p.to_dict())
            except Exception:
                log.exception("Failed to store prediction")
        return p

    def get_history(self, limit: int = 50) -> list[dict[str, Any]]:
        return [p.to_dict() for p in self._predictions[-limit:]]
