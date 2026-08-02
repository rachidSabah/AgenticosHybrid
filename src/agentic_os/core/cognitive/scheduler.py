"""Cognitive Scheduler — schedules cognitive background tasks.

Runs periodic cycles: update world model, run strategic planner,
run prediction engine, run experience replay, run self-evaluation,
generate improvement plans.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from agentic_os.infrastructure.logging import get_logger

if TYPE_CHECKING:
    from agentic_os.core.cognitive.evaluation_engine import EvaluationEngine
    from agentic_os.core.cognitive.experience_replay import ExperienceReplay
    from agentic_os.core.cognitive.improvement_planner import ImprovementPlanner
    from agentic_os.core.cognitive.prediction_engine import PredictionEngine
    from agentic_os.core.cognitive.strategic_planner import StrategicPlanner
    from agentic_os.core.cognitive.world_model import WorldModel

log = get_logger("cognitive.scheduler")

COGNITIVE_CYCLE_SECONDS = 120  # 2 minutes


class CognitiveScheduler:
    """Runs the cognitive cycle in the background."""

    def __init__(
        self,
        world_model: WorldModel | None = None,
        strategic_planner: StrategicPlanner | None = None,
        prediction_engine: PredictionEngine | None = None,
        experience_replay: ExperienceReplay | None = None,
        evaluation_engine: EvaluationEngine | None = None,
        improvement_planner: ImprovementPlanner | None = None,
    ) -> None:
        self._world = world_model
        self._planner = strategic_planner
        self._predictor = prediction_engine
        self._experience = experience_replay
        self._evaluation = evaluation_engine
        self._improvement = improvement_planner
        self._task: asyncio.Task | None = None
        self._started = False
        self._cycles = 0

    def set_components(
        self,
        world: WorldModel,
        planner: StrategicPlanner,
        predictor: PredictionEngine,
        experience: ExperienceReplay,
        evaluation: EvaluationEngine,
        improvement: ImprovementPlanner,
    ) -> None:
        self._world = world
        self._planner = planner
        self._predictor = predictor
        self._experience = experience
        self._evaluation = evaluation
        self._improvement = improvement

    async def start(self) -> None:
        self._started = True
        self._task = asyncio.create_task(self._cycle_loop())
        log.info("CognitiveScheduler started (cycle=%ds)", COGNITIVE_CYCLE_SECONDS)

    async def stop(self) -> None:
        self._started = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        log.info("CognitiveScheduler stopped")

    async def _cycle_loop(self) -> None:
        while self._started:
            try:
                await asyncio.sleep(COGNITIVE_CYCLE_SECONDS)
                await self._run_cycle()
            except asyncio.CancelledError:
                break
            except Exception:
                log.exception("Cognitive cycle error")

    async def _run_cycle(self) -> None:
        """Run one cognitive cycle."""
        self._cycles += 1
        log.info("Cognitive cycle %d", self._cycles)
        if self._evaluation is not None:
            await self._evaluation.evaluate()
