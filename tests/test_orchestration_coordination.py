"""Tests for CoordinationEngine (Phase 4, M3)."""

import pytest

from agentic_os.core.orchestration.coordination import CoordinationEngine
from agentic_os.domain.execution import ExecutionMetrics, ExecutionStatus
from agentic_os.domain.orchestration import (
    AgentDescriptor,
    AgentTask,
    AgentTaskStatus,
    CoordinationPattern,
    OrchestrationPlan,
    SwarmSpec,
)
from agentic_os.ports.execution import ExecutionResult


class _MockRuntime:
    async def execute(self, engine_id, request):
        return ExecutionResult(
            execution_id="test-exec",
            status=ExecutionStatus.COMPLETED,
            output={"done": True},
            metrics=ExecutionMetrics(),
        )

    async def list_engines(self, capability=None, status=None):
        return []

    async def get_engine(self, engine_id):
        return None

    async def list_capabilities(self):
        return {}

    async def find_engines(self, capability, min_confidence=0.0):
        return []

    async def execute_on_best(self, request, required_capability):
        return ExecutionResult(
            execution_id="test-exec-best",
            status=ExecutionStatus.COMPLETED,
            output={"done": True},
            metrics=ExecutionMetrics(),
        )


class _FailingMockRuntime:
    async def execute(self, engine_id, request):
        raise RuntimeError("Engine failure")


class _SlowMockRuntime:
    async def execute(self, engine_id, request):
        import asyncio

        await asyncio.sleep(3600)  # will timeout


class _MockBus:
    def __init__(self):
        self.events = []

    async def publish(self, envelope):
        self.events.append(envelope)


@pytest.fixture
def engine():
    return CoordinationEngine()


@pytest.fixture
def runtime():
    return _MockRuntime()


@pytest.fixture
def failing_runtime():
    return _FailingMockRuntime()


@pytest.fixture
def slow_runtime():
    return _SlowMockRuntime()


@pytest.fixture
def bus():
    return _MockBus()


@pytest.fixture
def agents():
    return [
        AgentDescriptor(agent_id="e1", name="Agent-1", engine_type="generic"),
        AgentDescriptor(agent_id="e2", name="Agent-2", engine_type="generic"),
    ]


@pytest.fixture
def swarm():
    return SwarmSpec(name="s1", agent_ids=("e1", "e2"))


def _make_plan(goal_id="g1", tasks=None) -> OrchestrationPlan:
    if tasks is None:
        tasks = [
            AgentTask(title="task-1", goal_id=goal_id),
            AgentTask(title="task-2", goal_id=goal_id),
        ]
    return OrchestrationPlan(goal_id=goal_id, subtasks=tuple(tasks))


def _make_assigned_tasks() -> list[AgentTask]:
    return [
        AgentTask(
            title="t1",
            assigned_agent_id="e1",
            coordination_pattern=CoordinationPattern.SEQUENTIAL,
            input_data={"cmd": "echo 1"},
            timeout_seconds=30.0,
        ),
        AgentTask(
            title="t2",
            assigned_agent_id="e2",
            coordination_pattern=CoordinationPattern.PARALLEL,
            input_data={"cmd": "echo 2"},
            timeout_seconds=30.0,
        ),
    ]


class TestCoordinationEngine:
    async def test_execute_empty_plan(self, engine, swarm, agents, runtime, bus) -> None:
        plan = _make_plan(tasks=[])
        result = await engine.execute(plan, swarm, agents, runtime, bus)
        assert result.status == "completed"

    async def test_execute_sequential_default(self, engine, swarm, agents, runtime, bus) -> None:
        tasks = _make_assigned_tasks()
        plan = _make_plan(tasks=tasks)
        result = await engine.execute(plan, swarm, agents, runtime, bus)
        assert result.status == "completed"
        assert all(t.status == AgentTaskStatus.COMPLETED for t in result.subtasks)

    async def test_sequential_stops_on_failure(
        self, engine, swarm, agents, failing_runtime, bus
    ) -> None:
        tasks = _make_assigned_tasks()
        plan = _make_plan(tasks=tasks)
        result = await engine.execute(plan, swarm, agents, failing_runtime, bus)
        # First task fails, second gets cancelled
        assert any(t.status == AgentTaskStatus.FAILED for t in result.subtasks)
        assert any(t.status == AgentTaskStatus.CANCELLED for t in result.subtasks)

    async def test_parallel_execution(self, engine, swarm, agents, runtime, bus) -> None:
        tasks = [
            AgentTask(
                title="t1",
                assigned_agent_id="e1",
                coordination_pattern=CoordinationPattern.PARALLEL,
                timeout_seconds=30.0,
            ),
            AgentTask(
                title="t2",
                assigned_agent_id="e2",
                coordination_pattern=CoordinationPattern.PARALLEL,
                timeout_seconds=30.0,
            ),
        ]
        plan = _make_plan(tasks=tasks)
        result = await engine.execute(plan, swarm, agents, runtime, bus)
        assert all(t.status == AgentTaskStatus.COMPLETED for t in result.subtasks)

    async def test_parallel_handles_exceptions(
        self, engine, swarm, agents, failing_runtime, bus
    ) -> None:
        tasks = [
            AgentTask(
                title="t1",
                assigned_agent_id="e1",
                coordination_pattern=CoordinationPattern.PARALLEL,
                timeout_seconds=30.0,
            ),
            AgentTask(
                title="t2",
                assigned_agent_id="e2",
                coordination_pattern=CoordinationPattern.PARALLEL,
                timeout_seconds=30.0,
            ),
        ]
        plan = _make_plan(tasks=tasks)
        result = await engine.execute(plan, swarm, agents, failing_runtime, bus)
        assert all(t.status == AgentTaskStatus.FAILED for t in result.subtasks)

    async def test_fan_out(self, engine, swarm, agents, runtime, bus) -> None:
        tasks = [
            AgentTask(
                title="broadcast",
                assigned_agent_id="e1",
                coordination_pattern=CoordinationPattern.FAN_OUT,
                timeout_seconds=30.0,
            ),
        ]
        plan = _make_plan(tasks=tasks)
        result = await engine.execute(plan, swarm, agents, runtime, bus)
        assert len(result.subtasks) > 0
        # Fan-out creates one result per agent
        assert all(t.status == AgentTaskStatus.COMPLETED for t in result.subtasks)

    async def test_fan_out_no_tasks(self, engine, swarm, agents, runtime, bus) -> None:
        plan = _make_plan(tasks=[])
        result = await engine.execute(plan, swarm, agents, runtime, bus)
        assert result.status == "completed"

    async def test_fan_in(self, engine, swarm, agents, runtime, bus) -> None:
        tasks = [
            AgentTask(
                title="collect",
                assigned_agent_id="e1",
                coordination_pattern=CoordinationPattern.FAN_IN,
                timeout_seconds=30.0,
            ),
        ]
        plan = _make_plan(tasks=tasks)
        result = await engine.execute(plan, swarm, agents, runtime, bus)
        assert all(t.status == AgentTaskStatus.COMPLETED for t in result.subtasks)

    async def test_hierarchical_with_deps(self, engine, swarm, agents, runtime, bus) -> None:
        tasks = [
            AgentTask(
                title="root",
                id="root",
                assigned_agent_id="e1",
                coordination_pattern=CoordinationPattern.HIERARCHICAL,
                timeout_seconds=30.0,
            ),
            AgentTask(
                title="child",
                id="child",
                assigned_agent_id="e2",
                depends_on=("root",),
                timeout_seconds=30.0,
            ),
        ]
        plan = _make_plan(tasks=tasks)
        result = await engine.execute(plan, swarm, agents, runtime, bus)
        assert all(t.status == AgentTaskStatus.COMPLETED for t in result.subtasks)

    async def test_hierarchical_deadlock(self, engine, swarm, agents, runtime, bus) -> None:
        tasks = [
            AgentTask(
                title="a",
                id="a",
                assigned_agent_id="e1",
                coordination_pattern=CoordinationPattern.HIERARCHICAL,
                depends_on=("b",),
                timeout_seconds=30.0,
            ),
            AgentTask(
                title="b",
                id="b",
                assigned_agent_id="e2",
                coordination_pattern=CoordinationPattern.HIERARCHICAL,
                depends_on=("a",),
                timeout_seconds=30.0,
            ),
        ]
        plan = _make_plan(tasks=tasks)
        result = await engine.execute(plan, swarm, agents, runtime, bus)
        assert any(t.status == AgentTaskStatus.FAILED for t in result.subtasks)

    async def test_execute_single_task_no_agent(self, engine, runtime, bus) -> None:
        task = AgentTask(title="no-agent")
        result = await engine._execute_single_task(task, {}, runtime)
        assert result.status == AgentTaskStatus.FAILED
        assert "No agent assigned" in (result.error or "")

    async def test_execute_single_task_no_mapping(self, engine, runtime, bus) -> None:
        task = AgentTask(title="no-map", assigned_agent_id="unknown")
        result = await engine._execute_single_task(task, {"e1": "e1"}, runtime)
        assert result.status == AgentTaskStatus.FAILED

    async def test_execute_sequential_emits_events(self, engine, agents, runtime, bus) -> None:
        tasks = _make_assigned_tasks()
        plan = _make_plan(tasks=tasks)
        await engine.execute(
            plan, SwarmSpec(name="s1", agent_ids=("e1", "e2")), agents, runtime, bus
        )
        assert len(bus.events) >= 2

    async def test_execute_with_timeout(self, engine, swarm, agents, slow_runtime, bus) -> None:
        tasks = [
            AgentTask(title="slow", assigned_agent_id="e1", timeout_seconds=0.1),
        ]
        plan = _make_plan(tasks=tasks)
        result = await engine.execute(plan, swarm, agents, slow_runtime, bus)
        assert result.subtasks[0].status == AgentTaskStatus.FAILED

    async def test_engine_map_uses_agent_id(self, engine, swarm, agents, runtime, bus) -> None:
        tasks = [AgentTask(title="t1", assigned_agent_id="e1", timeout_seconds=30.0)]
        plan = _make_plan(tasks=tasks)
        result = await engine.execute(plan, swarm, agents, runtime, bus)
        assert result.subtasks[0].status == AgentTaskStatus.COMPLETED

    async def test_last_non_none_pattern_wins(self, engine, swarm, agents, runtime, bus) -> None:
        tasks = [
            AgentTask(
                title="t1",
                assigned_agent_id="e1",
                coordination_pattern=CoordinationPattern.SEQUENTIAL,
                timeout_seconds=30.0,
            ),
            AgentTask(
                title="t2",
                assigned_agent_id="e2",
                coordination_pattern=CoordinationPattern.SEQUENTIAL,
                timeout_seconds=30.0,
            ),
        ]
        plan = _make_plan(tasks=tasks)
        result = await engine.execute(plan, swarm, agents, runtime, bus)
        assert result.status == "completed"
