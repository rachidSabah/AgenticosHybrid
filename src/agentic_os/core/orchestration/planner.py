"""Swarm Planner — autonomous goal analysis, task decomposition, and plan generation.

Analyzes high-level goals, decomposes them into dependency-resolved task graphs,
identifies parallelization opportunities, and produces execution-ready plans.
"""

from typing import Any

from agentic_os.core.orchestration.registry import OrchestrationAgentRegistry
from agentic_os.core.orchestration.strategies.decomposition import RuleBasedDecomposition
from agentic_os.domain.events import EventEnvelope, Topic
from agentic_os.domain.orchestration import (
    AgentTask,
    CoordinationPattern,
    OrchestrationGoal,
    OrchestrationPlan,
    SwarmSpec,
    SwarmTopology,
)
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.event_bus import EventBus
from agentic_os.ports.orchestration import DecompositionStrategy, PlannerPort

log = get_logger("orchestration.planner")


class SwarmPlanner(PlannerPort):
    """Autonomous planner for swarm orchestration.

    Analyzes goals, selects decomposition strategies, builds dependency graphs,
    identifies parallelization opportunities, and generates execution plans.
    """

    def __init__(
        self,
        bus: EventBus,
        agent_registry: OrchestrationAgentRegistry,
        default_strategy: DecompositionStrategy | None = None,
    ) -> None:
        self._bus = bus
        self._agent_registry = agent_registry
        self._strategies: dict[str, DecompositionStrategy] = {}
        self._default_strategy = default_strategy or RuleBasedDecomposition()

    def register_strategy(self, name: str, strategy: DecompositionStrategy) -> None:
        """Register a named decomposition strategy."""
        self._strategies[name] = strategy

    async def analyze_goal(self, goal: OrchestrationGoal) -> dict[str, Any]:
        """Analyze a goal and return metadata about complexity and requirements."""
        title_lower = goal.title.lower()
        context = goal.context

        # Estimate complexity based on keywords
        complexity_keywords = {
            "complex": 5,
            "large": 4,
            "big": 4,
            "multiple": 3,
            "full": 4,
            "complete": 3,
            "end-to-end": 5,
            "comprehensive": 4,
        }
        complexity = 1
        for kw, val in complexity_keywords.items():
            if kw in title_lower:
                complexity = max(complexity, val)

        # Identify required capabilities from context
        required_capabilities = context.get("required_capabilities", [])
        if not required_capabilities:
            # Infer from goal keywords
            cap_map = {
                "code": "code",
                "implement": "code",
                "build": "code",
                "test": "test",
                "deploy": "deploy",
                "research": "research",
                "analyze": "analyze",
                "design": "design",
                "document": "documentation",
                "secure": "security",
                "optimize": "performance",
            }
            for kw, cap in cap_map.items():
                if kw in title_lower and cap not in required_capabilities:
                    required_capabilities.append(cap)

        # Suggest topology based on complexity
        suggested_topology = SwarmTopology.MESH
        if complexity <= 2:
            suggested_topology = SwarmTopology.SEQUENTIAL
        elif complexity <= 3:
            suggested_topology = SwarmTopology.PARALLEL
        elif complexity >= 5:
            suggested_topology = SwarmTopology.HIERARCHICAL

        analysis: dict[str, Any] = {
            "complexity": complexity,
            "required_capabilities": required_capabilities,
            "suggested_topology": suggested_topology.value,
            "estimated_subtasks": min(complexity * 2, 20),
            "parallelization_opportunity": complexity >= 3,
        }

        await self._bus.publish(
            EventEnvelope(
                type="event",
                source="planner",
                topic=Topic.ORCH_PLANNER_STARTED.value,
                payload={"goal_id": goal.id, "analysis": analysis},
            )
        )
        return analysis

    async def create_plan(
        self,
        goal: OrchestrationGoal,
        swarm: SwarmSpec | None = None,
        profile: Any | None = None,
    ) -> OrchestrationPlan:
        """Create a full execution plan from a goal."""
        await self._bus.publish(
            EventEnvelope(
                type="event",
                source="planner",
                topic=Topic.ORCH_PLANNER_STARTED.value,
                payload={"goal_id": goal.id, "title": goal.title},
            )
        )

        # Analyze to determine strategy
        analysis = await self.analyze_goal(goal)

        # Select decomposition strategy
        strategy_name = goal.context.get("decomposition_strategy", "")
        strategy = self._strategies.get(strategy_name, self._default_strategy)

        # Decompose into tasks
        subtasks = await strategy.decompose(goal)

        # Build dependency graph from task depends_on
        subtasks = self._resolve_dependency_ids(subtasks)

        # Assign agents if swarm is specified
        if swarm and swarm.agent_ids:
            subtasks = await self._assign_agents(subtasks, swarm, analysis)

        # Annotate coordination patterns
        subtasks = self._annotate_patterns(subtasks, analysis, swarm)

        plan = OrchestrationPlan(
            goal_id=goal.id,
            subtasks=tuple(subtasks),
            status="pending",
            metadata={
                "complexity": analysis["complexity"],
                "suggested_topology": analysis["suggested_topology"],
                "parallelization": analysis["parallelization_opportunity"],
                "required_capabilities": analysis["required_capabilities"],
            },
        )

        # Auto-parallelize if beneficial
        if analysis["parallelization_opportunity"]:
            plan = await self.parallelize_plan(plan)

        await self._bus.publish(
            EventEnvelope(
                type="event",
                source="planner",
                topic=Topic.ORCH_PLANNER_COMPLETED.value,
                payload={
                    "goal_id": goal.id,
                    "plan_id": plan.id,
                    "subtask_count": len(subtasks),
                },
            )
        )
        log.info("Plan created", plan_id=plan.id, goal_id=goal.id, tasks=len(subtasks))
        return plan

    async def resolve_dependencies(self, plan: OrchestrationPlan) -> OrchestrationPlan:
        """Resolve and validate all task dependencies in a plan."""
        task_ids = {t.id for t in plan.subtasks}
        invalid: list[str] = []
        for task in plan.subtasks:
            for dep in task.depends_on:
                if dep not in task_ids:
                    invalid.append(f"Task {task.id} depends on unknown task {dep}")

        if invalid:
            log.warning("Dependency resolution found issues", issues=invalid)

        return plan

    async def parallelize_plan(
        self, plan: OrchestrationPlan, max_parallel: int = 5
    ) -> OrchestrationPlan:
        """Identify tasks with no interdependencies and mark them parallel."""
        # Tasks with no depends_on can run in parallel
        # Tasks whose dependents are all completed can also run in parallel
        updated_tasks: list[AgentTask] = []
        for task in plan.subtasks:
            if not task.depends_on:
                updated_tasks.append(
                    AgentTask(
                        id=task.id,
                        goal_id=task.goal_id,
                        title=task.title,
                        description=task.description,
                        status=task.status,
                        assigned_agent_id=task.assigned_agent_id,
                        depends_on=task.depends_on,
                        coordination_pattern=CoordinationPattern.PARALLEL,
                        input_data=task.input_data,
                        output_data=task.output_data,
                        error=task.error,
                        priority=task.priority,
                        timeout_seconds=task.timeout_seconds,
                        created_at=task.created_at,
                        started_at=task.started_at,
                        completed_at=task.completed_at,
                    )
                )
            else:
                updated_tasks.append(task)

        return OrchestrationPlan(
            id=plan.id,
            goal_id=plan.goal_id,
            subtasks=tuple(updated_tasks),
            status=plan.status,
            metadata={**plan.metadata, "parallelized": True, "max_parallel": max_parallel},
            created_at=plan.created_at,
            completed_at=plan.completed_at,
        )

    # ── Internal ──

    def _resolve_dependency_ids(self, tasks: list[AgentTask]) -> list[AgentTask]:
        """Resolve dependency titles to task IDs within the list."""
        title_to_id = {t.title: t.id for t in tasks}
        resolved: list[AgentTask] = []
        for task in tasks:
            resolved_deps = tuple(title_to_id.get(dep, dep) for dep in task.depends_on)
            if resolved_deps != task.depends_on:
                task = AgentTask(
                    id=task.id,
                    goal_id=task.goal_id,
                    title=task.title,
                    description=task.description,
                    status=task.status,
                    assigned_agent_id=task.assigned_agent_id,
                    depends_on=resolved_deps,
                    coordination_pattern=task.coordination_pattern,
                    input_data=task.input_data,
                    output_data=task.output_data,
                    error=task.error,
                    priority=task.priority,
                    timeout_seconds=task.timeout_seconds,
                    created_at=task.created_at,
                    started_at=task.started_at,
                    completed_at=task.completed_at,
                )
            resolved.append(task)
        return resolved

    async def _assign_agents(
        self, tasks: list[AgentTask], swarm: SwarmSpec, analysis: dict[str, Any]
    ) -> list[AgentTask]:
        """Assign agents to tasks based on capability matching."""
        agents = await self._agent_registry.list_agents()
        available_agents = [a for a in agents if a.agent_id in swarm.agent_ids]
        if not available_agents:
            return tasks

        agent_idx = 0
        assigned: list[AgentTask] = []
        for task in tasks:
            if task.assigned_agent_id:
                assigned.append(task)
                continue
            # Round-robin through available agents
            agent = available_agents[agent_idx % len(available_agents)]
            agent_idx += 1
            assigned.append(task.with_assigned(agent.agent_id))
        return assigned

    def _annotate_patterns(
        self, tasks: list[AgentTask], analysis: dict[str, Any], swarm: SwarmSpec | None
    ) -> list[AgentTask]:
        """Annotate tasks with coordination patterns based on dependencies."""
        has_parallel = analysis.get("parallelization_opportunity", False)
        annotated: list[AgentTask] = []
        for task in tasks:
            pattern = task.coordination_pattern
            if pattern is None:
                if not task.depends_on and has_parallel:
                    pattern = CoordinationPattern.PARALLEL
                else:
                    pattern = CoordinationPattern.SEQUENTIAL
            if pattern != task.coordination_pattern:
                task = AgentTask(
                    id=task.id,
                    goal_id=task.goal_id,
                    title=task.title,
                    description=task.description,
                    status=task.status,
                    assigned_agent_id=task.assigned_agent_id,
                    depends_on=task.depends_on,
                    coordination_pattern=pattern,
                    input_data=task.input_data,
                    output_data=task.output_data,
                    error=task.error,
                    priority=task.priority,
                    timeout_seconds=task.timeout_seconds,
                    created_at=task.created_at,
                    started_at=task.started_at,
                    completed_at=task.completed_at,
                )
            annotated.append(task)
        return annotated
