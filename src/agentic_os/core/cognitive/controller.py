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
        await self._scheduler.start()
        log.info("CognitiveController started")

    async def stop(self) -> None:
        self._started = False
        await self._scheduler.stop()
        await self._world.stop()
        log.info("CognitiveController stopped")

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
        }
