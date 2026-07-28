"""Strategic Planner — generates strategic recommendations.

Given the current WorldModel, objectives, goals, and capabilities,
produces: recommended goals, priorities, mission ordering, resource
allocation, and runtime selection.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agentic_os.infrastructure.logging import get_logger

if TYPE_CHECKING:
    from agentic_os.core.cognitive.world_model import WorldModel

log = get_logger("cognitive.strategic_planner")


class StrategicPlanner:
    """Generates strategic recommendations from the world model."""

    def __init__(self, world_model: WorldModel | None = None) -> None:
        self._world = world_model

    def set_world_model(self, wm: WorldModel) -> None:
        self._world = wm

    async def generate_strategy(self) -> dict[str, Any]:
        """Generate strategic recommendations from the current world state."""
        if self._world is None:
            return {"recommendations": [], "resource_allocation": {}, "mission_ordering": []}

        world = await self._world.snapshot()
        runtimes = world.get("runtimes", {})
        runtime_count = world.get("runtime_count", 0)
        mission_stats = world.get("mission_stats", {})
        goal_stats = world.get("goal_stats", {})
        historical = world.get("historical", {})

        recommendations: list[dict[str, Any]] = []

        # Recommend goals based on system capacity
        if runtime_count > 0 and goal_stats.get("active", 0) < runtime_count:
            recommendations.append(
                {
                    "type": "increase_goal_throughput",
                    "rationale": (
                        f"Only {goal_stats.get('active', 0)} active"
                        f" goals but {runtime_count} runtimes available"
                    ),
                    "priority": "high",
                }
            )

        # Recommend based on failure rate
        total_missions = mission_stats.get("completed", 0) + mission_stats.get("failed", 0)
        if total_missions > 0:
            failure_rate = mission_stats.get("failed", 0) / total_missions
            if failure_rate > 0.3:
                recommendations.append(
                    {
                        "type": "investigate_failures",
                        "rationale": (f"Failure rate {failure_rate:.0%} exceeds 30% threshold"),
                        "priority": "critical",
                    }
                )

        # Recommend based on historical success
        total_hist = historical.get("successes", 0) + historical.get("failures", 0)
        if total_hist > 0:
            success_rate = historical.get("successes", 0) / total_hist
            if success_rate > 0.8:
                recommendations.append(
                    {
                        "type": "scale_up",
                        "rationale": (
                            f"High success rate ({success_rate:.0%})"
                            " — system is stable, consider scaling"
                        ),
                        "priority": "low",
                    }
                )

        # Resource allocation: distribute goals across runtimes
        resource_allocation: dict[str, float] = {}
        if runtimes:
            per_runtime = 1.0 / max(runtime_count, 1)
            for rid in runtimes:
                resource_allocation[rid] = round(per_runtime, 3)

        # Mission ordering: prioritize critical goals
        mission_ordering: list[dict[str, Any]] = []
        if goal_stats.get("active", 0) > 0:
            mission_ordering.append({"priority": "critical", "action": "execute_active_goals"})
        if goal_stats.get("failed", 0) > 0:
            mission_ordering.append({"priority": "high", "action": "retry_failed_goals"})

        return {
            "recommendations": recommendations,
            "resource_allocation": resource_allocation,
            "mission_ordering": mission_ordering,
            "world_snapshot": world,
        }
