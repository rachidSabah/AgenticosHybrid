"""Tests for TaskOrchestrator (Phase 4, M3)."""

import pytest

from agentic_os.core.orchestration.coordination import CoordinationEngine
from agentic_os.core.orchestration.task_orchestrator import TaskOrchestrator
from agentic_os.domain.orchestration import (
    AgentDescriptor,
    AgentTask,
    OrchestrationGoal,
    SwarmSpec,
)


class _MockBus:
    def __init__(self):
        self.events = []

    async def publish(self, envelope):
        self.events.append(envelope)


class _MockAgentRegistry:
    def __init__(self):
        self._agents = {
            "a1": AgentDescriptor(
                agent_id="a1", name="A1", engine_type="generic", capabilities=("code",)
            ),
            "a2": AgentDescriptor(
                agent_id="a2", name="A2", engine_type="generic", capabilities=("research",)
            ),
        }
        self._runtime = _MockRuntime()

    async def get_agent(self, agent_id):
        return self._agents.get(agent_id)

    async def list_agents(self):
        return list(self._agents.values())

    async def sync_from_runtime(self):
        return list(self._agents.values())

    async def count_agents(self):
        return len(self._agents)

    async def get_agent_capabilities(self, agent_id):
        return []

    async def find_agents_by_capability(self, capability, min_confidence=0.0):
        return [a for a in self._agents.values() if capability in a.capabilities]


class _MockRuntime:
    async def execute(self, engine_id, request):
        from agentic_os.ports.execution import ExecutionResult

        return ExecutionResult(status="completed", output={"done": True})

    async def list_engines(self, capability=None, status=None):
        return []

    async def get_engine(self, engine_id):
        return None

    async def list_capabilities(self):
        return {}

    async def find_engines(self, capability, min_confidence=0.0):
        return []

    async def execute_on_best(self, request, required_capability):
        from agentic_os.ports.execution import ExecutionResult

        return ExecutionResult(status="completed", output={"done": True})


class _MockSwarmManager:
    def __init__(self):
        self._swarms: dict[str, SwarmSpec] = {}
        self._agents: dict[str, list[AgentDescriptor]] = {}

    async def get_swarm(self, swarm_id):
        return self._swarms.get(swarm_id)

    async def create_swarm(self, spec):
        self._swarms[spec.id] = spec
        self._agents[spec.id] = [
            AgentDescriptor(agent_id=aid, name=aid, engine_type="generic") for aid in spec.agent_ids
        ]
        return spec

    async def get_agents_in_swarm(self, swarm_id):
        return self._agents.get(swarm_id, [])


class _MockCoordination(CoordinationEngine):
    def __init__(self):
        super().__init__()

    async def execute(self, plan, swarm, agents, runtime, bus):
        from agentic_os.domain.orchestration import OrchestrationPlan

        updated = []
        for task in plan.subtasks:
            if task.assigned_agent_id:
                updated.append(task.with_output({"done": True}))
            else:
                updated.append(task)
        return OrchestrationPlan(
            id=plan.id,
            goal_id=plan.goal_id,
            subtasks=tuple(updated),
            status="completed",
            metadata=plan.metadata,
            created_at=plan.created_at,
        )


@pytest.fixture
def bus():
    return _MockBus()


@pytest.fixture
def registry():
    return _MockAgentRegistry()


@pytest.fixture
def swarm_manager():
    return _MockSwarmManager()


@pytest.fixture
def coordination():
    return _MockCoordination()


@pytest.fixture
def orchestrator(bus, registry, swarm_manager, coordination):
    return TaskOrchestrator(
        bus=bus,
        agent_registry=registry,
        swarm_manager=swarm_manager,
        coordination=coordination,
    )


class TestTaskOrchestrator:
    async def test_create_goal(self, orchestrator) -> None:
        goal = OrchestrationGoal(title="test-goal", description="do something")
        result = await orchestrator.create_goal(goal)
        assert result.id == goal.id
        assert result.title == "test-goal"

    async def test_get_goal(self, orchestrator) -> None:
        goal = OrchestrationGoal(title="g1")
        await orchestrator.create_goal(goal)
        result = await orchestrator.get_goal(goal.id)
        assert result is not None

    async def test_get_goal_not_found(self, orchestrator) -> None:
        result = await orchestrator.get_goal("nonexistent")
        assert result is None

    async def test_list_goals_empty(self, orchestrator) -> None:
        goals = await orchestrator.list_goals()
        assert goals == []

    async def test_list_goals_filtered(self, orchestrator) -> None:
        await orchestrator.create_goal(OrchestrationGoal(title="g1", status="pending"))
        await orchestrator.create_goal(OrchestrationGoal(title="g2", status="completed"))
        pending = await orchestrator.list_goals(status="pending")
        assert len(pending) == 1

    async def test_cancel_goal(self, orchestrator) -> None:
        goal = OrchestrationGoal(title="g1")
        await orchestrator.create_goal(goal)
        result = await orchestrator.cancel_goal(goal.id)
        assert result is not None
        assert result.status == "cancelled"

    async def test_cancel_goal_not_found(self, orchestrator) -> None:
        result = await orchestrator.cancel_goal("nonexistent")
        assert result is None

    async def test_assign_to_swarm(self, orchestrator, swarm_manager) -> None:
        goal = OrchestrationGoal(title="g1")
        await orchestrator.create_goal(goal)
        spec = SwarmSpec(name="s1", agent_ids=("a1", "a2"))
        await swarm_manager.create_swarm(spec)
        plan = await orchestrator.assign_to_swarm(goal.id, spec.id)
        assert plan is not None
        assert plan.goal_id == goal.id
        assert len(plan.subtasks) > 0

    async def test_assign_to_swarm_goal_not_found(self, orchestrator) -> None:
        plan = await orchestrator.assign_to_swarm("nonexistent", "s1")
        assert plan is None

    async def test_assign_to_swarm_swarm_not_found(self, orchestrator) -> None:
        goal = OrchestrationGoal(title="g1")
        await orchestrator.create_goal(goal)
        plan = await orchestrator.assign_to_swarm(goal.id, "nonexistent")
        assert plan is None

    async def test_decompose_goal_no_strategy(self, orchestrator) -> None:
        goal = OrchestrationGoal(title="g1")
        await orchestrator.create_goal(goal)
        plan = await orchestrator.decompose_goal(goal.id)
        assert plan is not None
        assert len(plan.subtasks) > 0

    async def test_decompose_goal_not_found(self, orchestrator) -> None:
        plan = await orchestrator.decompose_goal("nonexistent")
        assert plan is None

    async def test_assign_subtask(self, orchestrator) -> None:
        goal = OrchestrationGoal(title="g1")
        await orchestrator.create_goal(goal)
        plan = await orchestrator.decompose_goal(goal.id)
        assert plan is not None
        if plan.subtasks:
            result = await orchestrator.assign_subtask(plan.subtasks[0].id, "a1")
            assert result is not None
            assert result.assigned_agent_id == "a1"

    async def test_assign_subtask_not_found(self, orchestrator) -> None:
        result = await orchestrator.assign_subtask("nonexistent", "a1")
        assert result is None

    async def test_execute_plan(self, orchestrator, swarm_manager) -> None:
        goal = OrchestrationGoal(title="g1")
        await orchestrator.create_goal(goal)
        spec = SwarmSpec(name="s1", agent_ids=("a1",))
        await swarm_manager.create_swarm(spec)
        plan = await orchestrator.assign_to_swarm(goal.id, spec.id)
        assert plan is not None
        result = await orchestrator.execute_plan(plan.id)
        assert result is not None
        assert result.status == "completed"

    async def test_execute_plan_not_found(self, orchestrator) -> None:
        result = await orchestrator.execute_plan("nonexistent")
        assert result is None

    async def test_get_plan(self, orchestrator) -> None:
        goal = OrchestrationGoal(title="g1")
        await orchestrator.create_goal(goal)
        plan = await orchestrator.decompose_goal(goal.id)
        assert plan is not None
        result = await orchestrator.get_plan(plan.id)
        assert result is not None

    async def test_get_task(self, orchestrator) -> None:
        goal = OrchestrationGoal(title="g1")
        await orchestrator.create_goal(goal)
        plan = await orchestrator.decompose_goal(goal.id)
        assert plan is not None
        if plan.subtasks:
            task = await orchestrator.get_task(plan.subtasks[0].id)
            assert task is not None

    async def test_get_task_not_found(self, orchestrator) -> None:
        task = await orchestrator.get_task("nonexistent")
        assert task is None

    async def test_list_tasks(self, orchestrator) -> None:
        goal = OrchestrationGoal(title="g1")
        await orchestrator.create_goal(goal)
        await orchestrator.decompose_goal(goal.id)
        tasks = await orchestrator.list_tasks()
        assert len(tasks) > 0

    async def test_list_tasks_filtered(self, orchestrator) -> None:
        goal = OrchestrationGoal(title="g1")
        await orchestrator.create_goal(goal)
        plan = await orchestrator.decompose_goal(goal.id)
        assert plan is not None
        tasks = await orchestrator.list_tasks(goal_id=goal.id)
        assert len(tasks) > 0
        assert all(t.goal_id == goal.id for t in tasks)

    async def test_create_goal_emits_event(self, orchestrator, bus) -> None:
        goal = OrchestrationGoal(title="g1")
        await orchestrator.create_goal(goal)
        topics = [e.topic for e in bus.events]
        assert "orchestration.task_created" in topics

    async def test_register_decomposition_strategy(self, orchestrator) -> None:

        class TestStrategy:
            name = "test"

            async def decompose(self, goal: OrchestrationGoal) -> list[AgentTask]:
                return [AgentTask(title="test-task")]

        strategy = TestStrategy()
        orchestrator.register_decomposition_strategy("test", strategy)
        assert "test" in orchestrator._decomposition_strategies
