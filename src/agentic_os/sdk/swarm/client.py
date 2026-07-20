"""Swarm Client SDK — programmatic multi-agent orchestration interface.

Usage::

    swarm = SwarmClient()
    await swarm.initialize()

    spec = await swarm.create_swarm(
        name="code-review-team",
        topology="hierarchical",
    )

    goal = await swarm.create_goal("Refactor the authentication module")
    plan = await swarm.decompose_goal(goal.id)
    result = await swarm.execute_plan(plan.id)
"""

from collections.abc import Sequence
from dataclasses import dataclass

from agentic_os.domain.orchestration import (
    OrchestrationGoal,
    OrchestrationPlan,
    SwarmSpec,
    SwarmTopology,
)
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.orchestration import SwarmManagerPort, TaskOrchestratorPort

log = get_logger("sdk.swarm")


@dataclass
class SwarmRunResult:
    """Result of a swarm execution run."""

    goal_id: str
    plan: OrchestrationPlan
    success: bool


class SwarmClient:
    """High-level developer-facing client for multi-agent orchestration."""

    def __init__(
        self,
        swarm_manager: SwarmManagerPort | None = None,
        task_orchestrator: TaskOrchestratorPort | None = None,
    ) -> None:
        self._swarm_manager = swarm_manager
        self._task_orchestrator = task_orchestrator
        self._initialized = False

    async def initialize(self) -> None:
        self._initialized = True
        log.info("SwarmClient initialized")

    async def create_swarm(
        self,
        name: str,
        topology: str = "sequential",
        tags: Sequence[str] | None = None,
    ) -> SwarmSpec:
        self._require_initialized()
        try:
            topo = SwarmTopology(topology)
        except ValueError:
            topo = SwarmTopology.SEQUENTIAL
        spec = SwarmSpec(name=name, topology=topo, tags=tuple(tags or []))
        if self._swarm_manager:
            spec = await self._swarm_manager.create_swarm(spec)
        log.info(f"Created swarm '{name}' with topology {topology}")
        return spec

    async def create_goal(
        self,
        description: str,
        title: str = "",
        swarm_id: str | None = None,
    ) -> OrchestrationGoal:
        self._require_initialized()
        goal = OrchestrationGoal(
            title=title or description[:50],
            description=description,
            swarm_id=swarm_id,
        )
        if self._task_orchestrator:
            goal = await self._task_orchestrator.create_goal(goal)
        return goal

    async def decompose_goal(self, goal_id: str) -> OrchestrationPlan:
        self._require_initialized()
        if self._task_orchestrator:
            return await self._task_orchestrator.decompose_goal(goal_id)
        return OrchestrationPlan(goal_id=goal_id)

    async def execute_plan(self, plan_id: str) -> OrchestrationPlan:
        self._require_initialized()
        if self._task_orchestrator:
            return await self._task_orchestrator.execute_plan(plan_id)
        return OrchestrationPlan(goal_id="")

    async def run_goal(
        self,
        description: str,
        swarm_id: str | None = None,
    ) -> SwarmRunResult:
        goal = await self.create_goal(description, swarm_id=swarm_id)
        plan = await self.decompose_goal(goal.id)
        result = await self.execute_plan(plan.id)
        return SwarmRunResult(
            goal_id=goal.id,
            plan=result,
            success=result.status == "completed",
        )

    async def get_plan(self, plan_id: str) -> OrchestrationPlan | None:
        self._require_initialized()
        if self._task_orchestrator:
            return await self._task_orchestrator.get_plan(plan_id)
        return None

    async def list_swarms(self) -> Sequence[SwarmSpec]:
        self._require_initialized()
        if self._swarm_manager:
            return await self._swarm_manager.list_swarms()
        return []

    async def get_swarm(self, swarm_id: str) -> SwarmSpec | None:
        self._require_initialized()
        if self._swarm_manager:
            return await self._swarm_manager.get_swarm(swarm_id)
        return None

    async def delete_swarm(self, swarm_id: str) -> None:
        self._require_initialized()
        if self._swarm_manager:
            await self._swarm_manager.delete_swarm(swarm_id)

    def _require_initialized(self) -> None:
        if not self._initialized:
            raise RuntimeError("SwarmClient not initialized. Call await .initialize() first.")


__all__ = ["SwarmClient", "SwarmRunResult"]
