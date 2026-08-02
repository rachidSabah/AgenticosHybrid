"""ReflectionEngine — post-mission analysis for self-improvement.

After a mission completes (or fails), the ReflectionEngine analyzes:
  - Was the goal achieved?
  - Were retries needed?
  - Which runtime performed best?
  - Which runtimes failed?
  - Could routing improve?

The analysis is stored in ExecutiveMemory (which wraps the existing
MemoryManager) and published as an ``executive.reflection`` event.
The Learning engine can subscribe to this event to improve future
routing decisions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agentic_os.core.executive.domain import Reflection
from agentic_os.infrastructure.logging import get_logger

if TYPE_CHECKING:
    from agentic_os.core.executive.goal_manager import GoalManager
    from agentic_os.core.executive.memory import ExecutiveMemory
    from agentic_os.ports.event_bus import EventBus

log = get_logger("executive.reflection")


class ReflectionEngine:
    """Generates post-mission reflections.

    The engine is stateless — each call to ``reflect`` is independent.
    Reflections are stored in ExecutiveMemory and published as events.
    """

    MAX_HISTORY = 200

    def __init__(
        self,
        bus: EventBus,
        memory: ExecutiveMemory | None = None,
        goal_manager: GoalManager | None = None,
    ) -> None:
        self._bus: EventBus = bus
        self._memory: ExecutiveMemory | None = memory
        self._goals: GoalManager | None = goal_manager
        self._reflections: list[Reflection] = []

    def set_memory(self, memory: ExecutiveMemory) -> None:
        self._memory = memory

    def set_goal_manager(self, gm: GoalManager) -> None:
        self._goals = gm

    async def reflect(
        self,
        goal_id: str,
        mission_id: str,
        goal_achieved: bool,
        retries_needed: int = 0,
        best_runtime: str = "",
        failed_runtimes: list[str] | None = None,
        routing_could_improve: bool = False,
        summary: str = "",
    ) -> Reflection:
        """Generate a reflection for a completed/failed mission.

        Stores the reflection in ExecutiveMemory, publishes an
        ``executive.reflection`` event, and updates the goal's
        reflection field (if the goal manager has it).
        """
        r = Reflection(
            goal_id=goal_id,
            mission_id=mission_id,
            goal_achieved=goal_achieved,
            retries_needed=retries_needed,
            best_runtime=best_runtime,
            failed_runtimes=failed_runtimes or [],
            routing_could_improve=routing_could_improve,
            summary=summary
            or self._generate_summary(
                goal_achieved, retries_needed, best_runtime, failed_runtimes or []
            ),
        )

        # Record in history
        self._reflections.append(r)
        if len(self._reflections) > self.MAX_HISTORY:
            self._reflections = self._reflections[-self.MAX_HISTORY :]

        # Store in ExecutiveMemory
        if self._memory is not None:
            try:
                await self._memory.store_reflection(r)
            except Exception:
                log.exception("Failed to store reflection %s", r.id)

        # Update the goal's reflection field
        if self._goals is not None:
            try:
                if goal_achieved:
                    await self._goals.complete(goal_id, r.summary)
                else:
                    await self._goals.fail(goal_id, r.summary)
            except Exception:
                log.exception("Failed to update goal %s with reflection", goal_id)

        # Publish reflection event
        await self._publish("executive.reflection", r.to_dict())
        log.info(
            "Reflection %s: goal=%s achieved=%s retries=%d best=%s",
            r.id,
            goal_id,
            goal_achieved,
            retries_needed,
            best_runtime,
        )
        return r

    def get_history(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return recent reflections for the ``/api/executive/reflections`` endpoint."""
        return [r.to_dict() for r in self._reflections[-limit:]]

    def get_metrics(self) -> dict[str, Any]:
        """Return reflection metrics for observability."""
        total = len(self._reflections)
        achieved = sum(1 for r in self._reflections if r.goal_achieved)
        with_retries = sum(1 for r in self._reflections if r.retries_needed > 0)
        with_improvement = sum(1 for r in self._reflections if r.routing_could_improve)
        return {
            "total_reflections": total,
            "goals_achieved": achieved,
            "goals_with_retries": with_retries,
            "routing_improvable": with_improvement,
            "success_rate": round(achieved / total, 3) if total > 0 else 0.0,
        }

    @staticmethod
    def _generate_summary(
        achieved: bool,
        retries: int,
        best: str,
        failed: list[str],
    ) -> str:
        """Generate a human-readable reflection summary."""
        status = "achieved" if achieved else "not achieved"
        parts = [f"Goal {status}"]
        if retries:
            parts.append(f"{retries} retries needed")
        if best:
            parts.append(f"best runtime: {best}")
        if failed:
            parts.append(f"failed runtimes: {', '.join(failed)}")
        return "; ".join(parts) + "."

    async def _publish(self, topic_str: str, payload: dict) -> None:
        from agentic_os.domain.events import EventEnvelope

        try:
            await self._bus.publish(
                EventEnvelope(
                    type=topic_str,
                    source="executive.reflection",
                    topic=topic_str,
                    payload=payload,
                )
            )
        except Exception:
            log.exception("Failed to publish %s", topic_str)
