"""Task Orchestrator — goal decomposition, subtask assignment, and plan execution.

Central orchestrator that:
1. Manages goals (CRUD)
2. Decomposes goals into plans with subtasks via pluggable strategies
3. Assigns subtasks to the best-matching agents
4. Executes plans through the CoordinationEngine
5. Monitors completion and publishes lifecycle events
"""

from typing import Any

from agentic_os.core.orchestration.coordination import CoordinationEngine
from agentic_os.core.orchestration.registry import OrchestrationAgentRegistry
from agentic_os.core.orchestration.swarm import SwarmManager
from agentic_os.domain.events import EventEnvelope, Topic
from agentic_os.domain.orchestration import (
    AgentTask,
    AgentTaskStatus,
    CoordinationPattern,
    OrchestrationGoal,
    OrchestrationPlan,
    SwarmSpec,
)
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.event_bus import EventBus
from agentic_os.ports.orchestration import DecompositionStrategy

log = get_logger("orchestration.task_orchestrator")


class TaskOrchestrator:
    """Manages goals, decomposition, assignment, and execution of orchestration plans."""

    def __init__(
        self,
        bus: EventBus,
        agent_registry: OrchestrationAgentRegistry,
        swarm_manager: SwarmManager,
        coordination: CoordinationEngine,
        default_strategy: DecompositionStrategy | None = None,
    ) -> None:
        self._bus = bus
        self._agent_registry = agent_registry
        self._swarm_manager = swarm_manager
        self._coordination = coordination
        self._default_strategy = default_strategy
        self._goals: dict[str, OrchestrationGoal] = {}
        self._plans: dict[str, OrchestrationPlan] = {}
        self._decomposition_strategies: dict[str, DecompositionStrategy] = {}

    # ── Goal Management ──

    async def create_goal(
        self,
        goal: OrchestrationGoal,
    ) -> OrchestrationGoal:
        """Create a new orchestration goal."""
        self._goals[goal.id] = goal

        await self._publish_event(
            Topic.ORCH_TASK_CREATED,
            {
                "goal_id": goal.id,
                "title": goal.title,
                "swarm_id": goal.swarm_id,
            },
        )

        log.info("Goal created", goal_id=goal.id, title=goal.title)
        return goal

    async def get_goal(self, goal_id: str) -> OrchestrationGoal | None:
        """Get a goal by ID."""
        return self._goals.get(goal_id)

    async def list_goals(self, status: str | None = None) -> list[OrchestrationGoal]:
        """List all goals, optionally filtered by status."""
        goals = list(self._goals.values())
        if status:
            goals = [g for g in goals if g.status == status]
        return goals

    async def cancel_goal(self, goal_id: str) -> OrchestrationGoal | None:
        """Cancel a goal and all its in-progress subtasks."""
        goal = self._goals.get(goal_id)
        if goal is None:
            return None

        goal = goal.with_status("cancelled")
        self._goals[goal_id] = goal

        # Cancel all in-progress tasks
        for plan in self._plans.values():
            if plan.goal_id == goal_id:
                updated_tasks = [
                    t.with_status(AgentTaskStatus.CANCELLED)
                    for t in plan.subtasks
                    if t.status
                    in (AgentTaskStatus.PENDING, AgentTaskStatus.ASSIGNED, AgentTaskStatus.RUNNING)
                    or t.status == AgentTaskStatus.PENDING
                ]
                unchanged = [
                    t
                    for t in plan.subtasks
                    if t.status
                    not in (
                        AgentTaskStatus.PENDING,
                        AgentTaskStatus.ASSIGNED,
                        AgentTaskStatus.RUNNING,
                    )
                ]
                self._plans[plan.id] = OrchestrationPlan(
                    id=plan.id,
                    goal_id=plan.goal_id,
                    subtasks=tuple(unchanged + updated_tasks),
                    status="cancelled",
                    metadata=plan.metadata,
                    created_at=plan.created_at,
                    completed_at=None,
                )

        await self._publish_event(
            Topic.ORCH_TASK_CANCELLED,
            {"goal_id": goal.id},
        )

        return goal

    # ── Goal Assignment ──

    async def assign_to_swarm(
        self,
        goal_id: str,
        swarm_id: str,
    ) -> OrchestrationPlan | None:
        """Assign a goal to a swarm — create a plan for execution."""
        goal = self._goals.get(goal_id)
        if goal is None:
            return None

        swarm = await self._swarm_manager.get_swarm(swarm_id)
        if swarm is None:
            return None

        # Update goal with swarm
        goal = goal.with_swarm(swarm_id)
        self._goals[goal_id] = goal

        # Decompose into a plan
        plan = await self._decompose_goal(goal, swarm)
        self._plans[plan.id] = plan

        await self._publish_event(
            Topic.ORCH_PLAN_CREATED,
            {
                "plan_id": plan.id,
                "goal_id": goal_id,
                "swarm_id": swarm_id,
                "subtask_count": len(plan.subtasks),
            },
        )

        return plan

    # ── Decomposition ──

    def register_decomposition_strategy(self, name: str, strategy: DecompositionStrategy) -> None:
        """Register a decomposition strategy by name."""
        self._decomposition_strategies[name] = strategy

    async def decompose_goal(
        self,
        goal_id: str,
        strategy_name: str | None = None,
    ) -> OrchestrationPlan | None:
        """Decompose a goal into a plan using the specified strategy."""
        goal = self._goals.get(goal_id)
        if goal is None:
            return None

        # Determine strategy
        strategy = self._default_strategy
        if strategy_name and strategy_name in self._decomposition_strategies:
            strategy = self._decomposition_strategies[strategy_name]

        if strategy is None:
            # Fallback: create a single composite task
            task = AgentTask(
                goal_id=goal.id,
                title=goal.title,
                description=goal.description,
                input_data=dict(goal.context),
                coordination_pattern=CoordinationPattern.SEQUENTIAL,
            )
            subtasks = (task,)
        else:
            subtasks = tuple(await strategy.decompose(goal))

        plan = OrchestrationPlan(
            goal_id=goal.id,
            subtasks=subtasks,
            status="pending",
        )

        self._plans[plan.id] = plan

        await self._publish_event(
            Topic.ORCH_TASK_DECOMPOSED,
            {
                "goal_id": goal.id,
                "plan_id": plan.id,
                "strategy": strategy_name or "default",
                "subtask_count": len(subtasks),
            },
        )

        return plan

    async def assign_subtask(self, task_id: str, agent_id: str) -> AgentTask | None:
        """Assign a specific subtask to an agent."""
        for plan in self._plans.values():
            for task in plan.subtasks:
                if task.id == task_id:
                    assigned = task.with_assigned(agent_id)
                    # Update in plan
                    new_tasks = list(plan.subtasks)
                    for i, t in enumerate(new_tasks):
                        if t.id == task_id:
                            new_tasks[i] = assigned
                    self._plans[plan.id] = OrchestrationPlan(
                        id=plan.id,
                        goal_id=plan.goal_id,
                        subtasks=tuple(new_tasks),
                        status=plan.status,
                        metadata=plan.metadata,
                        created_at=plan.created_at,
                        completed_at=plan.completed_at,
                    )

                    await self._publish_event(
                        Topic.ORCH_TASK_ASSIGNED,
                        {"task_id": task_id, "agent_id": agent_id},
                    )
                    return assigned
        return None

    # ── Execution ──

    async def get_plan(self, plan_id: str) -> OrchestrationPlan | None:
        """Get a plan by ID."""
        return self._plans.get(plan_id)

    async def get_task(self, task_id: str) -> AgentTask | None:
        """Get a subtask by ID across all plans."""
        for plan in self._plans.values():
            for task in plan.subtasks:
                if task.id == task_id:
                    return task
        return None

    async def list_tasks(
        self,
        goal_id: str | None = None,
        status: str | None = None,
    ) -> list[AgentTask]:
        """List all tasks, optionally filtered by goal or status."""
        tasks: list[AgentTask] = []
        for plan in self._plans.values():
            if goal_id and plan.goal_id != goal_id:
                continue
            for task in plan.subtasks:
                if status and task.status.value != status:
                    continue
                tasks.append(task)
        return tasks

    async def execute_plan(self, plan_id: str) -> OrchestrationPlan | None:
        """Execute a plan through the coordination engine."""
        plan = self._plans.get(plan_id)
        if plan is None:
            return None

        goal = self._goals.get(plan.goal_id)
        if goal is None:
            return plan

        # Get swarm and agents
        swarm_id = goal.swarm_id
        if swarm_id is None:
            log.warning("Plan has no swarm assigned", plan_id=plan_id)
            return plan

        swarm = await self._swarm_manager.get_swarm(swarm_id)
        if swarm is None:
            log.warning("Swarm not found for plan", plan_id=plan_id, swarm_id=swarm_id)
            return plan

        agents = await self._swarm_manager.get_agents_in_swarm(swarm_id)
        if not agents:
            log.warning("No agents in swarm for plan execution", plan_id=plan_id, swarm_id=swarm_id)
            return plan

        # Update goal status
        goal = goal.with_status("running")
        self._goals[plan.goal_id] = goal

        # Execute via coordination engine
        runtime = self._agent_registry._runtime  # noqa: SLF001  # intentional bridge
        result = await self._coordination.execute(plan, swarm, agents, runtime, self._bus)

        # Store result
        self._plans[plan_id] = result

        # Update goal status based on plan result
        if result.status == "completed":
            goal = goal.with_status("completed")
        elif result.status in ("failed", "cancelled"):
            goal = goal.with_status(result.status)

        self._goals[plan.goal_id] = goal

        await self._publish_event(
            Topic.ORCH_PLAN_COMPLETED,
            {
                "plan_id": plan_id,
                "goal_id": plan.goal_id,
                "status": result.status,
            },
        )

        return result

    # ── Internal ──

    async def _decompose_goal(
        self,
        goal: OrchestrationGoal,
        swarm: SwarmSpec,
    ) -> OrchestrationPlan:
        """Decompose a goal into subtasks based on context and swarm topology."""
        context = goal.context

        # Use registered strategy if available
        strategy_name = context.get("decomposition_strategy")
        strategy = None
        if strategy_name:
            strategy = self._decomposition_strategies.get(strategy_name)
        if strategy is None:
            strategy = self._default_strategy

        if strategy:
            subtasks = await strategy.decompose(goal)
        else:
            # Manual decomposition: one task per agent in the swarm
            subtasks = []
            for aid in swarm.agent_ids:
                task = AgentTask(
                    goal_id=goal.id,
                    title=f"{goal.title} — {aid}",
                    description=goal.description,
                    assigned_agent_id=aid,
                    coordination_pattern=CoordinationPattern.PARALLEL,
                    input_data=dict(goal.context),
                )
                subtasks.append(task)

            # If no agents, create a single unassigned task
            if not subtasks:
                subtasks = [
                    AgentTask(
                        goal_id=goal.id,
                        title=goal.title,
                        description=goal.description,
                        input_data=dict(goal.context),
                    )
                ]

        return OrchestrationPlan(
            goal_id=goal.id,
            subtasks=tuple(subtasks),
            status="decomposed",
        )

    async def _publish_event(self, topic: Topic, payload: dict[str, Any]) -> None:
        """Publish a task lifecycle event."""
        try:
            await self._bus.publish(
                EventEnvelope(
                    type="event",
                    source="task-orchestrator",
                    topic=topic.value,
                    payload=payload,
                )
            )
        except Exception as exc:
            log.warning(
                "Failed to publish task event",
                topic=topic.value,
                error=str(exc),
            )
