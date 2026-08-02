"""Phase 17 — EvolutionController.

Long-running controller that owns the EvolutionManager lifecycle and
subscribes it to the EventBus so evolution triggers automatically on
key events:

  - ecosystem.evolution.generated → trigger analysis
  - mission.completed → trigger readiness assessment
  - cognitive.evaluation.completed → trigger knowledge synthesis

The controller is a pure consumer — it does NOT publish discovery
events, does NOT modify production code, does NOT replace any existing
controller.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agentic_os.core.evolution.manager import EvolutionManager
from agentic_os.infrastructure.logging import get_logger

if TYPE_CHECKING:
    from agentic_os.core.cognitive.improvement_planner import ImprovementPlanner
    from agentic_os.core.cognitive.memory import CognitiveMemory
    from agentic_os.core.ecosystem.evolution_engine import EvolutionEngine
    from agentic_os.core.executive.memory import ExecutiveMemory
    from agentic_os.ports.event_bus import EventBus

log = get_logger("evolution.controller")

# Topics the EvolutionController subscribes to.
_OBSERVED_TOPICS = [
    "ecosystem.evolution.generated",
    "mission.completed",
    "cognitive.evaluation.completed",
    "ecosystem.optimization.completed",
]


class EvolutionController:
    """Long-running controller for the evolution layer."""

    def __init__(
        self,
        bus: EventBus,
        evolution_engine: EvolutionEngine | None = None,
        improvement_planner: ImprovementPlanner | None = None,
        exec_memory: ExecutiveMemory | None = None,
        cognitive_memory: CognitiveMemory | None = None,
    ) -> None:
        self._bus = bus
        self._started = False
        self._subscriptions: list[str] = []
        self._manager = EvolutionManager(
            bus=bus,
            evolution_engine=evolution_engine,
            improvement_planner=improvement_planner,
            exec_memory=exec_memory,
            cognitive_memory=cognitive_memory,
        )
        self._events_processed = 0
        self._analyses_triggered = 0

    @property
    def manager(self) -> EvolutionManager:
        return self._manager

    @property
    def started(self) -> bool:
        return self._started

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        await self._manager.start()
        for topic in _OBSERVED_TOPICS:
            try:
                sub_id = await self._bus.subscribe(topic, self._on_event)
                self._subscriptions.append(sub_id)
            except Exception:
                log.exception("Failed to subscribe to %s", topic)
        log.info(
            "EvolutionController started (%d subscriptions)",
            len(self._subscriptions),
        )

    async def stop(self) -> None:
        self._started = False
        for sub_id in self._subscriptions:
            try:
                await self._bus.unsubscribe(sub_id)
            except Exception:
                pass
        self._subscriptions.clear()
        await self._manager.stop()
        log.info("EvolutionController stopped")

    async def _on_event(self, event: Any) -> None:
        """Route events to the EvolutionManager."""
        self._events_processed += 1
        topic = event.topic

        try:
            if topic == "ecosystem.evolution.generated":
                # New recommendations available → trigger analysis
                await self._manager.analyze()
                self._analyses_triggered += 1
            elif topic == "mission.completed":
                # Mission done → assess readiness
                await self._manager.assess_readiness()
            elif topic == "cognitive.evaluation.completed":
                # Evaluation done → could synthesize knowledge
                pass  # Knowledge synthesis is on-demand via API
            elif topic == "ecosystem.optimization.completed":
                # Optimization cycle done → assess readiness
                await self._manager.assess_readiness()
        except Exception:
            log.exception("EvolutionController failed to handle %s", topic)

    def status(self) -> dict[str, Any]:
        return {
            "started": self._started,
            "events_processed": self._events_processed,
            "analyses_triggered": self._analyses_triggered,
            "subscriptions": len(self._subscriptions),
            "manager": self._manager.status(),
        }
