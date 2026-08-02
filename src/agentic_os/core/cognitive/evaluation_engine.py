"""Evaluation Engine — continuously evaluates system quality.

Evaluates: decision quality, goal quality, reflection quality,
routing quality, runtime utilization, mission efficiency, memory quality.
Generates: overall executive score, overall system score.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agentic_os.core.cognitive.domain import EvaluationScore
from agentic_os.infrastructure.logging import get_logger

if TYPE_CHECKING:
    from agentic_os.core.cognitive.memory import CognitiveMemory
    from agentic_os.core.cognitive.world_model import WorldModel

log = get_logger("cognitive.evaluation")


class EvaluationEngine:
    """Continuously evaluates system quality."""

    def __init__(
        self,
        world_model: WorldModel | None = None,
        cognitive_memory: CognitiveMemory | None = None,
    ) -> None:
        self._world = world_model
        self._mem = cognitive_memory
        self._scores: list[EvaluationScore] = []

    def set_world_model(self, wm: WorldModel) -> None:
        self._world = wm

    def set_memory(self, mem: CognitiveMemory) -> None:
        self._mem = mem

    async def evaluate(self) -> EvaluationScore:
        """Run a full system evaluation."""
        if self._world is None:
            s = EvaluationScore()
            self._scores.append(s)
            return s

        world = await self._world.snapshot()
        mission_stats = world.get("mission_stats", {})
        goal_stats = world.get("goal_stats", {})
        historical = world.get("historical", {})
        runtime_count = world.get("runtime_count", 0)

        # Decision quality: based on success rate
        total_missions = mission_stats.get("completed", 0) + mission_stats.get("failed", 0)
        mission_success_rate = (
            mission_stats.get("completed", 0) / total_missions if total_missions > 0 else 0.5
        )
        decision_quality = mission_success_rate

        # Goal quality: ratio of completed to total
        total_goals = goal_stats.get("total", 0)
        goal_quality = goal_stats.get("completed", 0) / total_goals if total_goals > 0 else 0.5

        # Reflection quality: based on having reflections in memory
        reflection_quality = 0.5  # default neutral
        if self._mem is not None:
            try:
                reflections = await self._mem.list_reflections(limit=100)
                if reflections:
                    with_analysis = sum(
                        1 for r in reflections if r.get("success_factors") or r.get("improvements")
                    )
                    reflection_quality = with_analysis / len(reflections)
            except Exception:
                pass

        # Routing quality: based on success rate from historical data
        total_hist = historical.get("successes", 0) + historical.get("failures", 0)
        routing_quality = historical.get("successes", 0) / total_hist if total_hist > 0 else 0.5

        # Runtime utilization: how many runtimes are being used
        runtime_utilization = min(runtime_count / 10.0, 1.0) if runtime_count > 0 else 0.0

        # Mission efficiency: inverse of failure rate
        mission_efficiency = mission_success_rate

        # Memory quality: based on cognitive memory metrics
        memory_quality = 0.5  # default
        if self._mem is not None:
            try:
                m = await self._mem.metrics()
                total_indexed = sum(m.values())
                memory_quality = min(total_indexed / 100.0, 1.0)
            except Exception:
                pass

        # Overall scores
        overall_executive = (
            decision_quality * 0.25
            + goal_quality * 0.25
            + reflection_quality * 0.15
            + routing_quality * 0.20
            + mission_efficiency * 0.15
        )
        overall_system = overall_executive * 0.6 + runtime_utilization * 0.2 + memory_quality * 0.2

        s = EvaluationScore(
            decision_quality=decision_quality,
            goal_quality=goal_quality,
            reflection_quality=reflection_quality,
            routing_quality=routing_quality,
            runtime_utilization=runtime_utilization,
            mission_efficiency=mission_efficiency,
            memory_quality=memory_quality,
            overall_executive_score=overall_executive,
            overall_system_score=overall_system,
            factors={
                "total_missions": total_missions,
                "total_goals": total_goals,
                "runtime_count": runtime_count,
                "historical_successes": historical.get("successes", 0),
                "historical_failures": historical.get("failures", 0),
            },
        )
        self._scores.append(s)
        if len(self._scores) > 100:
            self._scores = self._scores[-100:]
        if self._mem is not None:
            try:
                await self._mem.store_evaluation(s.id, s.to_dict())
            except Exception:
                log.exception("Failed to store evaluation")
        return s

    def get_history(self, limit: int = 50) -> list[dict[str, Any]]:
        return [s.to_dict() for s in self._scores[-limit:]]

    def get_latest(self) -> dict[str, Any] | None:
        return self._scores[-1].to_dict() if self._scores else None
