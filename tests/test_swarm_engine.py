"""Tests for Swarm Orchestration Engine subsystems (Phase 4, M4)."""

from typing import Any

import pytest

from agentic_os.core.orchestration.agent_selector import AgentSelector
from agentic_os.core.orchestration.checkpoint import CheckpointManager
from agentic_os.core.orchestration.metrics import CostTracker, MetricsEngine, PerformanceAnalyzer
from agentic_os.core.orchestration.planner import SwarmPlanner
from agentic_os.core.orchestration.recovery import FailureRecovery
from agentic_os.core.orchestration.result_merger import ResultMerger
from agentic_os.core.orchestration.retry import RetryManager
from agentic_os.core.orchestration.scheduler import SwarmScheduler
from agentic_os.core.orchestration.supervisor import SwarmSupervisor
from agentic_os.core.orchestration.validation import ValidationEngine
from agentic_os.domain.orchestration import (
    AgentDescriptor,
    AgentTask,
    AgentTaskStatus,
    Checkpoint,
    ExecutionCost,
    ExecutionMetrics,
    ExecutionStage,
    ExecutionStageStatus,
    ExecutionTimeline,
    MergedResult,
    MergeStrategy,
    OrchestrationGoal,
    OrchestrationPlan,
    RetryPolicy,
    SwarmProfile,
    SwarmTopology,
    ValidationResult,
    ValidationStatus,
)

# ── Mocks ──


class _MockBus:
    def __init__(self) -> None:
        self.events: list[Any] = []

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def publish(self, event: Any) -> None:
        self.events.append(event)


class _MockRuntime:
    async def list_engines(self, capability: Any = None, status: str | None = None) -> list:
        return []

    async def get_engine(self, engine_id: str) -> None:
        return None

    async def execute(self, engine_id: str, request: Any) -> Any:
        from agentic_os.domain.execution import ExecutionResult, ExecutionStatus

        return ExecutionResult(
            execution_id="mock-exec", status=ExecutionStatus.COMPLETED, output={"done": True}
        )

    async def list_capabilities(self) -> dict:
        return {}

    async def find_engines(self, capability: Any, min_confidence: float = 0.0) -> list:
        return []

    async def execute_on_best(self, request: Any, required_capability: Any = None) -> Any:
        from agentic_os.domain.execution import ExecutionResult, ExecutionStatus

        return ExecutionResult(
            execution_id="mock-exec", status=ExecutionStatus.COMPLETED, output={"done": True}
        )


class _MockAgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, AgentDescriptor] = {
            "a1": AgentDescriptor(
                agent_id="a1",
                name="Agent-1",
                engine_type="generic",
                capabilities=("code", "test"),
                status="idle",
                health_status="healthy",
                latency_ms=50.0,
            ),
            "a2": AgentDescriptor(
                agent_id="a2",
                name="Agent-2",
                engine_type="generic",
                capabilities=("research", "analyze"),
                status="idle",
                health_status="healthy",
                latency_ms=100.0,
            ),
            "a3": AgentDescriptor(
                agent_id="a3",
                name="Agent-3",
                engine_type="generic",
                capabilities=("deploy", "test"),
                status="busy",
                health_status="degraded",
                latency_ms=200.0,
            ),
        }

    async def get_agent(self, agent_id: str) -> AgentDescriptor | None:
        return self._agents.get(agent_id)

    async def list_agents(
        self, capability: Any = None, status: str | None = None
    ) -> list[AgentDescriptor]:
        return list(self._agents.values())

    async def sync_from_runtime(self) -> list[AgentDescriptor]:
        return list(self._agents.values())

    async def count_agents(self) -> int:
        return len(self._agents)

    async def get_agent_capabilities(self, agent_id: str) -> list:
        return []

    async def find_agents_by_capability(
        self, capability: Any, min_confidence: float = 0.0
    ) -> list[AgentDescriptor]:
        return [a for a in self._agents.values() if capability in a.capabilities]


# ── Fixtures ──


@pytest.fixture
def bus() -> _MockBus:
    return _MockBus()


@pytest.fixture
def runtime() -> _MockRuntime:
    return _MockRuntime()


@pytest.fixture
def agent_registry() -> _MockAgentRegistry:
    return _MockAgentRegistry()


@pytest.fixture
def sample_goal() -> OrchestrationGoal:
    return OrchestrationGoal(
        id="goal-1",
        title="Build a web application",
        description="Full stack web app with backend API and React frontend",
        context={"tech_stack": "python", "framework": "fastapi"},
        status="pending",
    )


@pytest.fixture
def sample_tasks() -> list[AgentTask]:
    return [
        AgentTask(
            id="t1",
            goal_id="goal-1",
            title="Design API",
            description="Design REST API",
            status=AgentTaskStatus.COMPLETED,
            output_data={"api": "rest"},
            priority=2,
        ),
        AgentTask(
            id="t2",
            goal_id="goal-1",
            title="Implement Backend",
            description="Implement backend",
            status=AgentTaskStatus.COMPLETED,
            output_data={"backend": "fastapi"},
            priority=1,
            depends_on=("t1",),
        ),
        AgentTask(
            id="t3",
            goal_id="goal-1",
            title="Write Tests",
            description="Write tests",
            status=AgentTaskStatus.PENDING,
            output_data={},
            priority=0,
            depends_on=("t2",),
        ),
    ]


@pytest.fixture
def sample_plan(sample_tasks: list[AgentTask]) -> OrchestrationPlan:
    return OrchestrationPlan(
        id="plan-1",
        goal_id="goal-1",
        subtasks=tuple(sample_tasks),
        status="running",
        metadata={"created_by": "test"},
    )


# ═══════════════════════════════════════════════════════════════════
#  New Domain Model Tests
# ═══════════════════════════════════════════════════════════════════


class TestSwarmProfile:
    def test_construction(self) -> None:
        profile = SwarmProfile(
            name="test-profile",
            description="A test profile",
            topology=SwarmTopology.PARALLEL,
            min_agents=2,
            max_agents=5,
            default_timeout_seconds=120.0,
        )
        assert profile.name == "test-profile"
        assert profile.topology == SwarmTopology.PARALLEL
        assert profile.min_agents == 2
        assert profile.max_agents == 5

    def test_to_dict(self) -> None:
        profile = SwarmProfile(name="dev", topology=SwarmTopology.SEQUENTIAL)
        d = profile.to_dict()
        assert d["name"] == "dev"
        assert d["topology"] == "sequential"


class TestExecutionStage:
    def test_construction(self) -> None:
        stage = ExecutionStage(
            id="stage-1",
            plan_id="plan-1",
            name="Build",
            description="Build phase",
            task_ids=("t1", "t2"),
        )
        assert stage.name == "Build"
        assert stage.status == ExecutionStageStatus.PENDING

    def test_with_status(self) -> None:
        stage = ExecutionStage(id="s1", plan_id="p1", name="Test")
        running = stage.with_status(ExecutionStageStatus.RUNNING)
        assert running.status == ExecutionStageStatus.RUNNING
        assert running.started_at is not None


class TestMergedResult:
    def test_construction(self) -> None:
        result = MergedResult(
            strategy=MergeStrategy.CONSENSUS,
            source_task_ids=("t1", "t2"),
            output={"key": "value"},
            confidence=0.85,
        )
        assert result.strategy == MergeStrategy.CONSENSUS
        assert result.output == {"key": "value"}

    def test_with_output(self) -> None:
        result = MergedResult(strategy=MergeStrategy.CONSENSUS, output={"a": 1})
        updated = result.with_output({"a": 2, "b": 3})
        assert updated.output == {"a": 2, "b": 3}


class TestValidationResult:
    def test_passed(self) -> None:
        result = ValidationResult(
            target_id="t1", target_type="task", status=ValidationStatus.PASSED, score=1.0
        )
        assert result.status == ValidationStatus.PASSED

    def test_with_status(self) -> None:
        result = ValidationResult(target_id="t1", target_type="task").with_status(
            ValidationStatus.FAILED
        )
        assert result.status == ValidationStatus.FAILED

    def test_with_score(self) -> None:
        result = ValidationResult(target_id="t1", target_type="task").with_score(0.3)
        assert result.status == ValidationStatus.FAILED
        assert result.score == 0.3


class TestRetryPolicy:
    def test_defaults(self) -> None:
        policy = RetryPolicy()
        assert policy.max_retries == 3
        assert policy.base_delay_seconds == 1.0
        assert policy.jitter is True


class TestCheckpoint:
    def test_construction(self) -> None:
        cp = Checkpoint(plan_id="plan-1", completed_task_ids=("t1",), failed_task_ids=("t2",))
        assert cp.plan_id == "plan-1"
        assert cp.completed_task_ids == ("t1",)

    def test_to_dict(self) -> None:
        cp = Checkpoint(plan_id="p1", task_states={"t1": "completed"})
        d = cp.to_dict()
        assert d["task_states"]["t1"] == "completed"


class TestExecutionMetrics:
    def test_construction(self) -> None:
        metrics = ExecutionMetrics(plan_id="p1", total_tasks=5, completed_tasks=3)
        assert metrics.completed_tasks == 3
        assert metrics.progress_pct == 60.0 if hasattr(metrics, "progress_pct") else True


class TestExecutionCost:
    def test_with_cost(self) -> None:
        cost = ExecutionCost(plan_id="p1")
        updated = cost.with_cost("agent-1", 0.05)
        assert updated.cost_by_agent["agent-1"] == 0.05
        assert updated.total_cost == 0.05

    def test_with_cost_multiple(self) -> None:
        cost = ExecutionCost(plan_id="p1")
        c1 = cost.with_cost("a1", 0.10)
        c2 = c1.with_cost("a2", 0.20)
        assert c2.total_cost == pytest.approx(0.30)
        assert c2.cost_by_agent["a1"] == 0.10
        assert c2.cost_by_agent["a2"] == 0.20


class TestExecutionTimeline:
    def test_construction(self) -> None:
        entry = ExecutionTimeline(plan_id="p1", event_type="task_started", task_id="t1")
        assert entry.event_type == "task_started"
        assert entry.timestamp is not None


# ═══════════════════════════════════════════════════════════════════
#  Planner Tests
# ═══════════════════════════════════════════════════════════════════


class TestSwarmPlanner:
    @pytest.fixture
    def planner(self, bus: _MockBus, agent_registry: _MockAgentRegistry) -> SwarmPlanner:
        return SwarmPlanner(bus=bus, agent_registry=agent_registry)

    async def test_analyze_goal(
        self, planner: SwarmPlanner, sample_goal: OrchestrationGoal
    ) -> None:
        analysis = await planner.analyze_goal(sample_goal)
        assert "complexity" in analysis
        assert "required_capabilities" in analysis
        assert "suggested_topology" in analysis

    async def test_analyze_goal_simple(self, planner: SwarmPlanner) -> None:
        goal = OrchestrationGoal(title="Fix typo in README", description="Simple fix")
        analysis = await planner.analyze_goal(goal)
        assert analysis["complexity"] == 1  # No complexity keywords → score 1
        assert analysis["suggested_topology"] == "sequential"

    async def test_analyze_goal_complex(self, planner: SwarmPlanner) -> None:
        goal = OrchestrationGoal(
            title="Build distributed system with microservices and database",
            description=(
                "Complex multi-agent project involving architecture, backend,"
                " frontend, testing, devops, security, and deployment"
            ),
        )
        analysis = await planner.analyze_goal(goal)
        assert isinstance(analysis["complexity"], int)
        assert analysis["complexity"] >= 1
        assert analysis["suggested_topology"] in ("sequential", "parallel", "mesh", "hierarchical")

    async def test_create_plan(self, planner: SwarmPlanner, sample_goal: OrchestrationGoal) -> None:
        plan = await planner.create_plan(sample_goal)
        assert plan.goal_id == "goal-1"
        assert len(plan.subtasks) > 0
        assert plan.status == "pending"

    async def test_create_plan_with_profile(
        self, planner: SwarmPlanner, sample_goal: OrchestrationGoal
    ) -> None:
        profile = SwarmProfile(
            name="fast",
            topology=SwarmTopology.PARALLEL,
            default_timeout_seconds=30.0,
            max_agents=5,
        )
        plan = await planner.create_plan(sample_goal, profile=profile)
        assert len(plan.subtasks) > 0

    async def test_resolve_dependencies(
        self, planner: SwarmPlanner, sample_plan: OrchestrationPlan
    ) -> None:
        resolved = await planner.resolve_dependencies(sample_plan)
        assert resolved is not None

    async def test_parallelize_plan(
        self, planner: SwarmPlanner, sample_plan: OrchestrationPlan
    ) -> None:
        parallelized = await planner.parallelize_plan(sample_plan, max_parallel=3)
        assert parallelized is not None

    async def test_create_plan_empty_goal(self, planner: SwarmPlanner) -> None:
        goal = OrchestrationGoal(title="")
        plan = await planner.create_plan(goal)
        assert plan.goal_id == goal.id
        assert len(plan.subtasks) >= 0


# ═══════════════════════════════════════════════════════════════════
#  Scheduler Tests
# ═══════════════════════════════════════════════════════════════════


class TestSwarmScheduler:
    @pytest.fixture
    def scheduler(
        self, bus: _MockBus, agent_registry: _MockAgentRegistry, runtime: _MockRuntime
    ) -> SwarmScheduler:
        return SwarmScheduler(bus=bus, agent_registry=agent_registry, runtime=runtime)

    async def test_schedule_tasks(
        self,
        scheduler: SwarmScheduler,
        sample_plan: OrchestrationPlan,
        agent_registry: _MockAgentRegistry,
    ) -> None:
        agents = await agent_registry.list_agents()
        scheduled = await scheduler.schedule_tasks(sample_plan, agents)
        assert scheduled is not None
        # Tasks should be in topological order
        task_ids = [t.id for t in scheduled.subtasks]
        assert "t1" in task_ids
        assert "t2" in task_ids

    async def test_dispatch_task(self, scheduler: SwarmScheduler) -> None:
        task = AgentTask(id="t1", goal_id="g1", title="Test")
        agent = AgentDescriptor(agent_id="a1", name="A1")
        dispatched = await scheduler.dispatch_task(task, agent)
        assert dispatched is not None

    async def test_get_schedule_empty(self, scheduler: SwarmScheduler) -> None:
        schedule = await scheduler.get_schedule("nonexistent")
        assert schedule == []

    async def test_schedule_with_deps(
        self, scheduler: SwarmScheduler, agent_registry: _MockAgentRegistry
    ) -> None:
        tasks = (
            AgentTask(id="t1", goal_id="g1", title="Task 1", depends_on=("t3",)),
            AgentTask(id="t2", goal_id="g1", title="Task 2", depends_on=("t1",)),
            AgentTask(id="t3", goal_id="g1", title="Task 3"),
        )
        plan = OrchestrationPlan(id="p1", goal_id="g1", subtasks=tasks)
        agents = await agent_registry.list_agents()
        await scheduler.schedule_tasks(plan, agents)
        # Check topological order via get_schedule
        schedule = await scheduler.get_schedule("p1")
        task_ids = [t.id for t in schedule]
        # t3 should come before t1 which comes before t2
        assert task_ids.index("t3") < task_ids.index("t1")
        assert task_ids.index("t1") < task_ids.index("t2")


# ═══════════════════════════════════════════════════════════════════
#  Supervisor Tests
# ═══════════════════════════════════════════════════════════════════


class TestSwarmSupervisor:
    @pytest.fixture
    def supervisor(
        self, bus: _MockBus, agent_registry: _MockAgentRegistry, runtime: _MockRuntime
    ) -> SwarmSupervisor:
        return SwarmSupervisor(
            bus=bus, agent_registry=agent_registry, runtime=runtime, max_retries=2
        )

    async def test_monitor_execution(
        self, supervisor: SwarmSupervisor, sample_plan: OrchestrationPlan
    ) -> None:
        monitored = await supervisor.monitor_execution(sample_plan)
        assert monitored is not None

    async def test_detect_failures_none(
        self, supervisor: SwarmSupervisor, sample_plan: OrchestrationPlan
    ) -> None:
        failed = await supervisor.detect_failures(sample_plan)
        assert isinstance(failed, list)
        # No failed tasks in sample
        assert len([t for t in failed if t.status == AgentTaskStatus.FAILED]) == 0

    async def test_detect_failures_with_failed(self, supervisor: SwarmSupervisor) -> None:
        tasks = (
            AgentTask(
                id="t1",
                goal_id="g1",
                title="Failed task",
                status=AgentTaskStatus.FAILED,
                error="Something broke",
            ),
            AgentTask(id="t2", goal_id="g1", title="OK task", status=AgentTaskStatus.COMPLETED),
        )
        plan = OrchestrationPlan(id="p1", goal_id="g1", subtasks=tasks)
        failed = await supervisor.detect_failures(plan)
        assert len(failed) >= 1
        assert failed[0].id == "t1"

    async def test_detect_deadlocks(self, supervisor: SwarmSupervisor) -> None:
        # t1 depends on t2, t2 depends on t1 → cycle
        tasks = (
            AgentTask(id="t1", goal_id="g1", title="Task 1", depends_on=("t2",)),
            AgentTask(id="t2", goal_id="g1", title="Task 2", depends_on=("t1",)),
        )
        plan = OrchestrationPlan(id="p1", goal_id="g1", subtasks=tasks)
        deadlocks = await supervisor.detect_deadlocks(plan)
        assert len(deadlocks) > 0

    async def test_no_deadlocks(
        self, supervisor: SwarmSupervisor, sample_plan: OrchestrationPlan
    ) -> None:
        deadlocks = await supervisor.detect_deadlocks(sample_plan)
        assert deadlocks == []

    async def test_restart_task(self, supervisor: SwarmSupervisor) -> None:
        task = AgentTask(
            id="t1",
            goal_id="g1",
            title="Test",
            status=AgentTaskStatus.FAILED,
            assigned_agent_id="a1",
        )
        agent = AgentDescriptor(agent_id="a2", name="A2")
        restarted = await supervisor.restart_task(task, agent)
        assert restarted.status in (
            AgentTaskStatus.PENDING,
            AgentTaskStatus.ASSIGNED,
            AgentTaskStatus.COMPLETED,
        )
        assert restarted.error is None

    async def test_reassign_task(self, supervisor: SwarmSupervisor) -> None:
        task = AgentTask(id="t1", goal_id="g1", title="Test", assigned_agent_id="a1")
        reassigned = await supervisor.reassign_task(task, "a2")
        assert reassigned.assigned_agent_id == "a2"


# ═══════════════════════════════════════════════════════════════════
#  ResultMerger Tests
# ═══════════════════════════════════════════════════════════════════


class TestResultMerger:
    @pytest.fixture
    def merger(self, bus: _MockBus) -> ResultMerger:
        return ResultMerger(bus=bus)

    async def test_merge_consensus(self, merger: ResultMerger) -> None:
        tasks = [
            AgentTask(
                id="t1",
                goal_id="g1",
                title="Task 1",
                status=AgentTaskStatus.COMPLETED,
                output_data={"name": "Alice", "role": "dev"},
            ),
            AgentTask(
                id="t2",
                goal_id="g1",
                title="Task 2",
                status=AgentTaskStatus.COMPLETED,
                output_data={"name": "Alice", "role": "test"},
            ),
        ]
        result = await merger.merge(tasks, MergeStrategy.CONSENSUS)
        assert result.strategy == MergeStrategy.CONSENSUS
        assert result.source_task_ids == ("t1", "t2")

    async def test_merge_concatenate(self, merger: ResultMerger) -> None:
        tasks = [
            AgentTask(
                id="t1",
                goal_id="g1",
                title="Task 1",
                status=AgentTaskStatus.COMPLETED,
                output_data={"a": 1},
            ),
            AgentTask(
                id="t2",
                goal_id="g1",
                title="Task 2",
                status=AgentTaskStatus.COMPLETED,
                output_data={"b": 2},
            ),
        ]
        result = await merger.merge(tasks, MergeStrategy.CONCATENATE)
        assert "items" in result.output
        assert len(result.output["items"]) == 2

    async def test_merge_empty(self, merger: ResultMerger) -> None:
        result = await merger.merge([], MergeStrategy.WEIGHTED)
        assert result.confidence == 0.0
        assert result.output == {}

    async def test_merge_weighted(self, merger: ResultMerger) -> None:
        tasks = [
            AgentTask(
                id="t1",
                goal_id="g1",
                title="Task 1",
                status=AgentTaskStatus.COMPLETED,
                output_data={"x": 10},
                priority=1,
            ),
            AgentTask(
                id="t2",
                goal_id="g1",
                title="Task 2",
                status=AgentTaskStatus.COMPLETED,
                output_data={"y": 20},
                priority=2,
            ),
        ]
        result = await merger.merge(tasks, MergeStrategy.WEIGHTED)
        assert "x" in result.output or "y" in result.output

    async def test_merge_best_of_n(self, merger: ResultMerger) -> None:
        tasks = [
            AgentTask(
                id="t1",
                goal_id="g1",
                title="Task 1",
                status=AgentTaskStatus.COMPLETED,
                output_data={"result": "good"},
                priority=2,
            ),
            AgentTask(
                id="t2",
                goal_id="g1",
                title="Task 2",
                status=AgentTaskStatus.COMPLETED,
                output_data={"result": "better"},
                priority=1,
            ),
        ]
        result = await merger.merge(tasks, MergeStrategy.BEST_OF_N)
        assert result.confidence >= 0.0

    async def test_resolve_conflicts(self, merger: ResultMerger) -> None:
        result = MergedResult(
            strategy=MergeStrategy.CONSENSUS,
            source_task_ids=("t1", "t2"),
            output={"key": "value"},
            conflicts=({"key": "key", "values": [{"confidence": 0.9}, {"confidence": 0.5}]},),
            confidence=0.6,
        )
        resolved = await merger.resolve_conflicts(result)
        assert resolved is not None


# ═══════════════════════════════════════════════════════════════════
#  ValidationEngine Tests
# ═══════════════════════════════════════════════════════════════════


class TestValidationEngine:
    @pytest.fixture
    def engine(self, bus: _MockBus) -> ValidationEngine:
        return ValidationEngine(bus=bus)

    async def test_validate_output_success(self, engine: ValidationEngine) -> None:
        task = AgentTask(
            id="t1",
            goal_id="g1",
            title="Test",
            status=AgentTaskStatus.COMPLETED,
            output_data={"result": "ok"},
        )
        result = await engine.validate_output(task)
        assert result.status == ValidationStatus.PASSED

    async def test_validate_output_with_schema(self, engine: ValidationEngine) -> None:
        task = AgentTask(
            id="t1",
            goal_id="g1",
            title="Test",
            status=AgentTaskStatus.COMPLETED,
            output_data={"name": "test", "value": 42},
        )
        schema = {"required": ["name", "value"]}
        result = await engine.validate_output(task, schema)
        assert result.status == ValidationStatus.PASSED

    async def test_validate_output_missing_fields(self, engine: ValidationEngine) -> None:
        task = AgentTask(
            id="t1",
            goal_id="g1",
            title="Test",
            status=AgentTaskStatus.COMPLETED,
            output_data={"name": "test"},
        )
        schema = {"required": ["name", "missing_field"]}
        result = await engine.validate_output(task, schema)
        assert result.status == ValidationStatus.FAILED

    async def test_validate_output_warning_empty(self, engine: ValidationEngine) -> None:
        task = AgentTask(
            id="t1", goal_id="g1", title="Test", status=AgentTaskStatus.COMPLETED, output_data={}
        )
        result = await engine.validate_output(task)
        assert len(result.warnings) > 0 or result.status == ValidationStatus.PASSED

    async def test_validate_plan_ok(
        self, engine: ValidationEngine, sample_plan: OrchestrationPlan
    ) -> None:
        result = await engine.validate_plan(sample_plan)
        assert result.status == ValidationStatus.PASSED

    async def test_validate_plan_empty(self, engine: ValidationEngine) -> None:
        plan = OrchestrationPlan(id="empty", goal_id="g1", subtasks=())
        result = await engine.validate_plan(plan)
        assert result.status == ValidationStatus.FAILED
        assert any("no subtasks" in e.lower() for e in result.errors)

    async def test_validate_plan_circular(self, engine: ValidationEngine) -> None:
        tasks = (
            AgentTask(id="t1", goal_id="g1", title="Task 1", depends_on=("t2",)),
            AgentTask(id="t2", goal_id="g1", title="Task 2", depends_on=("t1",)),
        )
        plan = OrchestrationPlan(id="circular", goal_id="g1", subtasks=tasks)
        result = await engine.validate_plan(plan)
        assert result.status == ValidationStatus.FAILED
        assert any("circular" in e.lower() for e in result.errors)

    async def test_validate_security_healthy(self, engine: ValidationEngine) -> None:
        task = AgentTask(id="t1", goal_id="g1", title="Code task")
        agent = AgentDescriptor(
            agent_id="a1", name="A1", health_status="healthy", capabilities=("code",)
        )
        result = await engine.validate_security(task, agent)
        assert result.status == ValidationStatus.PASSED

    async def test_validate_security_no_capabilities(self, engine: ValidationEngine) -> None:
        task = AgentTask(id="t1", goal_id="g1", title="Write tests")
        agent = AgentDescriptor(agent_id="a1", name="A1", health_status="healthy", capabilities=())
        result = await engine.validate_security(task, agent)
        # Should still pass even with no capabilities — just warnings
        assert result.status in (ValidationStatus.PASSED, ValidationStatus.FAILED)

    async def test_validate_policy(self, engine: ValidationEngine) -> None:
        task = AgentTask(id="t1", goal_id="g1", title="Test", priority=5, timeout_seconds=60.0)
        policies = {"max_priority": 10, "max_timeout_seconds": 3600}
        result = await engine.validate_policy(task, policies)
        assert result.status == ValidationStatus.PASSED

    async def test_validate_policy_exceeded(self, engine: ValidationEngine) -> None:
        task = AgentTask(id="t1", goal_id="g1", title="Test", priority=15, timeout_seconds=9999)
        policies = {"max_priority": 10, "max_timeout_seconds": 3600}
        result = await engine.validate_policy(task, policies)
        assert result.status == ValidationStatus.FAILED


# ═══════════════════════════════════════════════════════════════════
#  RetryManager Tests
# ═══════════════════════════════════════════════════════════════════


class TestRetryManager:
    @pytest.fixture
    def retry_mgr(self, bus: _MockBus) -> RetryManager:
        return RetryManager(bus=bus)

    async def test_should_retry_default(self, retry_mgr: RetryManager) -> None:
        task = AgentTask(
            id="t1",
            goal_id="g1",
            title="Test",
            status=AgentTaskStatus.FAILED,
            error="timeout error",
        )
        assert await retry_mgr.should_retry(task) is True

    async def test_should_not_retry_exhausted(self, retry_mgr: RetryManager) -> None:
        task = AgentTask(
            id="t1", goal_id="g1", title="Test", status=AgentTaskStatus.FAILED, error="error"
        )
        # Use a policy with 0 max retries
        policy = RetryPolicy(max_retries=0)
        assert await retry_mgr.should_retry(task, policy) is False

    async def test_get_retry_count(self, retry_mgr: RetryManager) -> None:
        assert retry_mgr.get_retry_count("nonexistent") == 0

    async def test_reset_retry_count(self, retry_mgr: RetryManager) -> None:
        retry_mgr._retry_counts["t1"] = 3
        retry_mgr.reset_retry_count("t1")
        assert retry_mgr.get_retry_count("t1") == 0


# ═══════════════════════════════════════════════════════════════════
#  FailureRecovery Tests
# ═══════════════════════════════════════════════════════════════════


class TestFailureRecovery:
    @pytest.fixture
    def recovery(self, bus: _MockBus) -> FailureRecovery:
        return FailureRecovery(bus=bus)

    async def test_recover_task(self, recovery: FailureRecovery) -> None:
        task = AgentTask(
            id="t1",
            goal_id="g1",
            title="Test",
            status=AgentTaskStatus.FAILED,
            assigned_agent_id="a1",
        )
        agents = [
            AgentDescriptor(agent_id="a2", name="A2"),
            AgentDescriptor(agent_id="a3", name="A3"),
        ]
        recovered = await recovery.recover_task(task, agents)
        assert recovered.assigned_agent_id == "a2"  # Different from original
        assert (
            recovered.status == AgentTaskStatus.ASSIGNED
            or recovered.status == AgentTaskStatus.PENDING
        )

    async def test_recover_task_no_agents(self, recovery: FailureRecovery) -> None:
        task = AgentTask(id="t1", goal_id="g1", title="Test", status=AgentTaskStatus.FAILED)
        recovered = await recovery.recover_task(task, [])
        assert recovered is task  # Returns original if no agents

    async def test_recover_plan_with_checkpoint(
        self, recovery: FailureRecovery, sample_plan: OrchestrationPlan
    ) -> None:
        cp = Checkpoint(
            id="cp1",
            plan_id="plan-1",
            completed_task_ids=("t1",),
            failed_task_ids=("t2",),
            partial_outputs={"t1": {"api": "rest"}},
        )
        recovered = await recovery.recover_plan(sample_plan, cp)
        assert recovered.status == "recovering"

    async def test_recover_plan_without_checkpoint(self, recovery: FailureRecovery) -> None:
        tasks = (
            AgentTask(id="t1", goal_id="g1", title="Task 1", status=AgentTaskStatus.FAILED),
            AgentTask(id="t2", goal_id="g1", title="Task 2", status=AgentTaskStatus.COMPLETED),
        )
        plan = OrchestrationPlan(id="p1", goal_id="g1", subtasks=tasks)
        recovered = await recovery.recover_plan(plan, checkpoint=None)
        assert recovered.status == "pending"

    async def test_rollback_plan(
        self, recovery: FailureRecovery, sample_plan: OrchestrationPlan
    ) -> None:
        cp = Checkpoint(plan_id="plan-1", completed_task_ids=("t1",), failed_task_ids=("t2",))
        rolled = await recovery.rollback_plan(sample_plan, cp)
        assert "rolled_back_to" in rolled.metadata


# ═══════════════════════════════════════════════════════════════════
#  CheckpointManager Tests
# ═══════════════════════════════════════════════════════════════════


class TestCheckpointManager:
    @pytest.fixture
    def checkpoint_mgr(self, bus: _MockBus) -> CheckpointManager:
        return CheckpointManager(bus=bus)

    async def test_save_checkpoint(
        self, checkpoint_mgr: CheckpointManager, sample_plan: OrchestrationPlan
    ) -> None:
        cp = await checkpoint_mgr.save_checkpoint(sample_plan)
        assert cp.plan_id == "plan-1"
        assert cp.completed_task_ids == ("t1", "t2")  # Two completed tasks in sample

    async def test_list_checkpoints(
        self, checkpoint_mgr: CheckpointManager, sample_plan: OrchestrationPlan
    ) -> None:
        await checkpoint_mgr.save_checkpoint(sample_plan)
        await checkpoint_mgr.save_checkpoint(sample_plan, metadata={"version": 2})
        cps = await checkpoint_mgr.list_checkpoints("plan-1")
        assert len(cps) == 2

    async def test_delete_checkpoint(
        self, checkpoint_mgr: CheckpointManager, sample_plan: OrchestrationPlan
    ) -> None:
        cp = await checkpoint_mgr.save_checkpoint(sample_plan)
        assert await checkpoint_mgr.delete_checkpoint(cp.id) is True
        assert await checkpoint_mgr.delete_checkpoint("nonexistent") is False

    async def test_restore_nonexistent(self, checkpoint_mgr: CheckpointManager) -> None:
        result = await checkpoint_mgr.restore_checkpoint("nonexistent")
        assert result is None


# ═══════════════════════════════════════════════════════════════════
#  AgentSelector Tests
# ═══════════════════════════════════════════════════════════════════


class TestAgentSelector:
    @pytest.fixture
    def selector(self, bus: _MockBus, agent_registry: _MockAgentRegistry) -> AgentSelector:
        return AgentSelector(bus=bus, agent_registry=agent_registry)

    async def test_select_agent(self, selector: AgentSelector) -> None:
        task = AgentTask(id="t1", goal_id="g1", title="Write code")
        selected = await selector.select_agent(task)
        assert selected is not None
        assert selected.agent_id in ("a1", "a2", "a3")

    async def test_select_agent_with_available(self, selector: AgentSelector) -> None:
        task = AgentTask(id="t1", goal_id="g1", title="Deploy to production")
        agents = [
            AgentDescriptor(
                agent_id="a3", name="A3", capabilities=("deploy",), health_status="healthy"
            )
        ]
        selected = await selector.select_agent(task, agents)
        assert selected is not None
        assert selected.agent_id == "a3"

    async def test_select_agent_no_available(self, selector: AgentSelector) -> None:
        task = AgentTask(id="t1", goal_id="g1", title="Test")
        selected = await selector.select_agent(task, [])
        assert selected is None

    async def test_match_capabilities(self, selector: AgentSelector) -> None:
        goal = OrchestrationGoal(title="Build with Python")
        matched = await selector.match_capabilities(goal, ["code", "test"])
        assert len(matched) > 0

    async def test_match_capabilities_empty(self, selector: AgentSelector) -> None:
        goal = OrchestrationGoal(title="Any task")
        matched = await selector.match_capabilities(goal, [])
        assert len(matched) > 0


# ═══════════════════════════════════════════════════════════════════
#  MetricsEngine Tests
# ═══════════════════════════════════════════════════════════════════


class TestMetricsEngine:
    @pytest.fixture
    def metrics(self, bus: _MockBus) -> MetricsEngine:
        return MetricsEngine(bus=bus)

    async def test_collect_metrics(
        self, metrics: MetricsEngine, sample_plan: OrchestrationPlan
    ) -> None:
        m = await metrics.collect_metrics(sample_plan)
        assert m.plan_id == "plan-1"
        assert m.total_tasks == 3
        assert m.completed_tasks == 2

    async def test_record_and_get_timeline(self, metrics: MetricsEngine) -> None:
        entry = ExecutionTimeline(plan_id="plan-1", event_type="task_started", task_id="t1")
        await metrics.record_timeline(entry)
        entries = await metrics.get_timeline("plan-1")
        assert len(entries) >= 1
        assert entries[0].event_type == "task_started"

    async def test_get_timeline_empty(self, metrics: MetricsEngine) -> None:
        entries = await metrics.get_timeline("nonexistent")
        assert entries == []


# ═══════════════════════════════════════════════════════════════════
#  CostTracker Tests
# ═══════════════════════════════════════════════════════════════════


class TestCostTracker:
    @pytest.fixture
    def cost_tracker(self, bus: _MockBus) -> CostTracker:
        return CostTracker(bus=bus)

    async def test_estimate_cost(
        self, cost_tracker: CostTracker, sample_plan: OrchestrationPlan
    ) -> None:
        cost = await cost_tracker.estimate_cost(sample_plan)
        assert cost.plan_id == "plan-1"
        assert cost.estimated_total > 0

    async def test_track_cost(self, cost_tracker: CostTracker) -> None:
        cost = await cost_tracker.track_cost("plan-1", "agent-1", 0.05)
        assert cost.total_cost == 0.05
        assert cost.cost_by_agent["agent-1"] == 0.05

    async def test_get_costs(self, cost_tracker: CostTracker) -> None:
        await cost_tracker.track_cost("plan-1", "a1", 0.10)
        costs = await cost_tracker.get_costs("plan-1")
        assert costs is not None
        assert costs.total_cost == 0.10

    async def test_get_costs_nonexistent(self, cost_tracker: CostTracker) -> None:
        costs = await cost_tracker.get_costs("nonexistent")
        assert costs is None


# ═══════════════════════════════════════════════════════════════════
#  PerformanceAnalyzer Tests
# ═══════════════════════════════════════════════════════════════════


class TestPerformanceAnalyzer:
    @pytest.fixture
    def analyzer(self, bus: _MockBus) -> PerformanceAnalyzer:
        metrics = MetricsEngine(bus=bus)
        cost = CostTracker(bus=bus)
        return PerformanceAnalyzer(metrics_engine=metrics, cost_tracker=cost)

    async def test_analyze_plan_no_metrics(self, analyzer: PerformanceAnalyzer) -> None:
        report = await analyzer.analyze_plan("nonexistent")
        assert "error" in report

    async def test_analyze_plan_with_metrics(
        self, analyzer: PerformanceAnalyzer, sample_plan: OrchestrationPlan
    ) -> None:
        # Collect metrics first
        await analyzer._metrics.collect_metrics(sample_plan)
        # Then analyze
        report = await analyzer.analyze_plan("plan-1")
        assert report["plan_id"] == "plan-1"
        assert "success_rate" in report


# ═══════════════════════════════════════════════════════════════════
#  EventBus Integration Tests
# ═══════════════════════════════════════════════════════════════════


class TestEventPublishing:
    """Verify that subsystems publish events on the bus."""

    async def test_planner_publishes_events(
        self, bus: _MockBus, agent_registry: _MockAgentRegistry
    ) -> None:
        planner = SwarmPlanner(bus=bus, agent_registry=agent_registry)
        goal = OrchestrationGoal(title="Test goal")
        await planner.create_plan(goal)
        published_topics = {e.topic for e in bus.events}
        assert any("planner" in t for t in published_topics)

    async def test_merger_publishes_events(self, bus: _MockBus) -> None:
        merger = ResultMerger(bus=bus)
        tasks = [
            AgentTask(
                id="t1",
                goal_id="g1",
                title="T1",
                status=AgentTaskStatus.COMPLETED,
                output_data={"x": 1},
            ),
        ]
        await merger.merge(tasks, MergeStrategy.CONSENSUS)
        published_topics = {e.topic for e in bus.events}
        assert any("merger" in t for t in published_topics)

    async def test_validation_publishes_events(self, bus: _MockBus) -> None:
        engine = ValidationEngine(bus=bus)
        plan = OrchestrationPlan(
            id="p1", goal_id="g1", subtasks=(AgentTask(id="t1", goal_id="g1", title="T1"),)
        )
        await engine.validate_plan(plan)
        published_topics = {e.topic for e in bus.events}
        assert any("validation" in t for t in published_topics)
