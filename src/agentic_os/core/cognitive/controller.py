"""Cognitive Controller — long-running cognitive intelligence.

Maintains WorldModel, refreshes KnowledgeGraph, runs StrategicPlanner,
PredictionEngine, ExperienceReplay, SelfEvaluation, generates
Improvement Plans, and publishes cognitive.* events.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agentic_os.core.cognitive.evaluation_engine import EvaluationEngine
from agentic_os.core.cognitive.experience_replay import ExperienceReplay
from agentic_os.core.cognitive.improvement_planner import ImprovementPlanner
from agentic_os.core.cognitive.knowledge_graph import KnowledgeGraph
from agentic_os.core.cognitive.memory import CognitiveMemory
from agentic_os.core.cognitive.objective_manager import ObjectiveManager
from agentic_os.core.cognitive.prediction_engine import PredictionEngine
from agentic_os.core.cognitive.scheduler import CognitiveScheduler
from agentic_os.core.cognitive.strategic_planner import StrategicPlanner
from agentic_os.core.cognitive.world_model import WorldModel
from agentic_os.infrastructure.logging import get_logger

if TYPE_CHECKING:
    from agentic_os.core.brains.registry import BrainRegistry
    from agentic_os.core.executive.goal_manager import GoalManager
    from agentic_os.core.executive.memory import ExecutiveMemory
    from agentic_os.ports.event_bus import EventBus

log = get_logger("cognitive.controller")

# Topics the CognitiveController subscribes to for integration with Discovery
_COGNITIVE_OBSERVED_TOPICS = [
    "brain.registered",
    "brain.removed",
    "brain.health_changed",
    "brain.updated",
]


class CognitiveController:
    """The continuously running cognitive intelligence."""

    def __init__(
        self,
        bus: EventBus,
        brain_registry: BrainRegistry | None = None,
        goal_manager: GoalManager | None = None,
        exec_memory: ExecutiveMemory | None = None,
    ) -> None:
        self._bus = bus
        self._started = False
        self._subscriptions: list[str] = []

        # Components
        self._memory = CognitiveMemory()
        self._world = WorldModel(bus, brain_registry, goal_manager, exec_memory)
        self._planner = StrategicPlanner(self._world)
        self._planner.set_bus(bus)
        self._predictor = PredictionEngine(self._world, self._memory)
        self._experience = ExperienceReplay(self._memory)
        self._evaluation = EvaluationEngine(self._world, self._memory)
        self._improvement = ImprovementPlanner(self._evaluation, self._experience, goal_manager)
        self._objectives = ObjectiveManager(bus)
        self._kg = KnowledgeGraph(self._memory)
        self._scheduler = CognitiveScheduler(
            self._world,
            self._planner,
            self._predictor,
            self._experience,
            self._evaluation,
            self._improvement,
        )

        # Stats
        self._predictions_made = 0
        self._evaluations_run = 0
        self._improvements_generated = 0
        self._events_processed = 0

    @property
    def world_model(self) -> WorldModel:
        return self._world

    @property
    def knowledge_graph(self) -> KnowledgeGraph:
        return self._kg

    @property
    def objective_manager(self) -> ObjectiveManager:
        return self._objectives

    @property
    def prediction_engine(self) -> PredictionEngine:
        return self._predictor

    @property
    def experience_replay(self) -> ExperienceReplay:
        return self._experience

    @property
    def evaluation_engine(self) -> EvaluationEngine:
        return self._evaluation

    @property
    def improvement_planner(self) -> ImprovementPlanner:
        return self._improvement

    @property
    def memory(self) -> CognitiveMemory:
        return self._memory

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        await self._world.start()
        # Subscribe to brain.* events so the Cognitive Layer reacts to
        # runtime discovery/removal in real time.
        for topic in _COGNITIVE_OBSERVED_TOPICS:
            try:
                sub_id = await self._bus.subscribe(topic, self._on_event)
                self._subscriptions.append(sub_id)
            except Exception:
                log.exception("Failed to subscribe to %s", topic)
        await self._scheduler.start()
        log.info(
            "CognitiveController started (%d subscriptions)",
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
        await self._scheduler.stop()
        await self._world.stop()
        log.info("CognitiveController stopped")

    async def _on_event(self, event: Any) -> None:
        """Handle brain.* events from the Discovery pipeline.

        When a runtime is discovered (brain.registered), the Cognitive
        Layer:
          1. Adds the brain as a node in the KnowledgeGraph
          2. Links it to its capabilities
          3. The WorldModel already updates its state (separate subscription)

        When a runtime is removed (brain.removed):
          1. The KnowledgeGraph node remains for history (edges still
             queryable) — the WorldModel state is cleared separately

        When health changes (brain.health_changed):
          1. The KnowledgeGraph node data is updated
        """
        self._events_processed += 1
        topic = event.topic
        payload = event.payload or {}

        try:
            if topic == "brain.registered":
                brain_id = str(payload.get("id", ""))
                display_name = str(payload.get("display_name", brain_id))
                caps = list(payload.get("capabilities", []))
                vendor = str(payload.get("vendor", "unknown"))
                health = payload.get("health", 0)
                latency = payload.get("latency", 0)

                # Add brain node to KnowledgeGraph
                await self._kg.add_entity(
                    brain_id,
                    "brain",
                    {
                        "name": display_name,
                        "vendor": vendor,
                        "health": health,
                        "latency": latency,
                        "capabilities": caps,
                    },
                )
                # Link brain to each capability
                for cap in caps:
                    cap_id = f"cap:{cap}"
                    await self._kg.add_entity(cap_id, "capability", {"name": cap})
                    await self._kg.link(brain_id, cap_id, "has_capability")

                # Link brain to provider entry
                provider_id = f"provider:{display_name}"
                await self._kg.add_entity(provider_id, "provider", {"name": display_name})
                await self._kg.link(brain_id, provider_id, "maps_to_provider")

                log.info(
                    "KnowledgeGraph: added brain %s (%s) with %d capabilities",
                    brain_id,
                    display_name,
                    len(caps),
                )

            elif topic == "brain.removed":
                brain_id = str(payload.get("id", ""))
                # Update KG node to mark as removed (keep for history)
                await self._kg.add_entity(
                    brain_id,
                    "brain_removed",
                    {
                        "removed": True,
                        "name": payload.get("display_name", brain_id),
                    },
                )
                log.info("KnowledgeGraph: marked brain %s as removed", brain_id)

            elif topic == "brain.health_changed":
                brain_id = str(payload.get("id", ""))
                health = payload.get("health", 0)
                latency = payload.get("latency", 0)
                await self._kg.add_entity(
                    brain_id,
                    "brain",
                    {
                        "name": payload.get("display_name", brain_id),
                        "health": health,
                        "latency": latency,
                        "updated": True,
                    },
                )

        except Exception:
            log.exception("Failed to handle cognitive event %s", topic)

    async def publish(self, topic: str, payload: dict[str, Any]) -> None:
        from agentic_os.domain.events import EventEnvelope

        try:
            await self._bus.publish(
                EventEnvelope(
                    type=topic, source="cognitive.controller", topic=topic, payload=payload
                )
            )
        except Exception:
            log.exception("Failed to publish %s", topic)

    def status(self) -> dict[str, Any]:
        return {
            "started": self._started,
            "predictions_made": self._predictions_made,
            "evaluations_run": self._evaluations_run,
            "improvements_generated": self._improvements_generated,
            "events_processed": self._events_processed,
            "subscriptions": len(self._subscriptions),
        }
