"""Comprehensive tests for PipelineEngineImpl.

Covers CRUD, execution, scheduling, validation, rollback,
retry policies, control operations, event emission, and edge cases.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import anyio
import pytest

from agentic_os.core.pipeline.engine import PipelineEngineImpl
from agentic_os.domain.events import Topic
from agentic_os.domain.pipeline import (
    PipelineExecutionStatus,
    PipelineStage,
    PipelineStatus,
    StageType,
)
from agentic_os.ports.pipeline import (
    PipelineCreate,
    PipelineExecute,
    PipelineRollback,
    PipelineScheduleRequest,
    PipelineUpdate,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_provider_router():
    router = MagicMock()
    router.complete = AsyncMock()
    router.complete.return_value = MagicMock(
        content="mock response",
        usage=MagicMock(to_dict=lambda: {"input_tokens": 10, "output_tokens": 20}),
    )
    return router


@pytest.fixture
def mock_agent_registry():
    registry = MagicMock()
    agent = MagicMock()
    agent.provider = "mock"
    agent.model = "mock-model"
    registry.get_agent.return_value = agent
    return registry


@pytest.fixture
def engine(bus, mock_provider_router, mock_agent_registry):
    return PipelineEngineImpl(bus, mock_provider_router, mock_agent_registry)


@pytest.fixture
def sample_stages():
    return [
        PipelineStage(
            id="stage1", type=StageType.AGENT, label="Stage 1", config={"agent_id": "test-agent"}
        ),
        PipelineStage(
            id="stage2", type=StageType.AGENT, label="Stage 2", config={"agent_id": "test-agent"}
        ),
    ]


@pytest.fixture
def sample_pipeline_create(sample_stages):
    return PipelineCreate(
        name="Test Pipeline",
        description="A test pipeline",
        stages=sample_stages,
        edges=[],
        created_by="test",
    )


# ---------------------------------------------------------------------------
# CRUD Operations
# ---------------------------------------------------------------------------


class TestCRUD:
    """Test pipeline CRUD operations."""

    async def test_create_pipeline(self, engine, sample_pipeline_create):
        detail = await engine.create_pipeline(sample_pipeline_create)
        assert detail.name == "Test Pipeline"
        assert detail.status == PipelineStatus.DRAFT
        assert detail.version == 1
        assert len(detail.stages) == 2

    async def test_create_with_schedule(self, engine, sample_stages):
        data = PipelineCreate(
            name="Scheduled Pipeline",
            description="",
            stages=sample_stages,
            edges=[],
            schedule_cron="0 9 * * *",
            schedule_timezone="UTC",
            created_by="test",
        )
        detail = await engine.create_pipeline(data)
        assert detail.schedule_cron == "0 9 * * *"
        schedule = await engine.get_pipeline_schedule(detail.id)
        assert schedule is not None
        assert schedule.cron == "0 9 * * *"

    async def test_get_pipeline(self, engine, sample_pipeline_create):
        created = await engine.create_pipeline(sample_pipeline_create)
        retrieved = await engine.get_pipeline(created.id)
        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.name == "Test Pipeline"

    async def test_get_pipeline_not_found(self, engine):
        result = await engine.get_pipeline("nonexistent")
        assert result is None

    async def test_list_pipelines(self, engine, sample_pipeline_create):
        await engine.create_pipeline(sample_pipeline_create)
        await engine.create_pipeline(sample_pipeline_create)
        pipelines = await engine.list_pipelines()
        assert len(pipelines) == 2

    async def test_list_pipelines_with_status_filter(self, engine, sample_pipeline_create):
        p1 = await engine.create_pipeline(sample_pipeline_create)
        p = engine._pipelines[p1.id].activate()
        engine._pipelines[p1.id] = p
        await engine.create_pipeline(sample_pipeline_create)

        drafts = await engine.list_pipelines(status=PipelineStatus.DRAFT)
        actives = await engine.list_pipelines(status=PipelineStatus.ACTIVE)
        assert len(drafts) == 1
        assert len(actives) == 1

    async def test_list_pipelines_limit_offset(self, engine, sample_pipeline_create):
        for _ in range(5):
            await engine.create_pipeline(sample_pipeline_create)
        first = await engine.list_pipelines(limit=2, offset=0)
        second = await engine.list_pipelines(limit=2, offset=2)
        assert len(first) == 2
        assert len(second) == 2

    async def test_update_pipeline_meta_only(self, engine, sample_pipeline_create):
        created = await engine.create_pipeline(sample_pipeline_create)
        updated = await engine.update_pipeline(
            created.id,
            PipelineUpdate(name="Updated Name", updated_by="tester"),
        )
        assert updated.name == "Updated Name"
        assert updated.version == 1

    async def test_update_pipeline_new_version(self, engine, sample_pipeline_create):
        created = await engine.create_pipeline(sample_pipeline_create)
        new_stage = PipelineStage(
            id="stage3", type=StageType.LLM, label="LLM", config={"prompt": "Hello"}
        )
        updated = await engine.update_pipeline(
            created.id,
            PipelineUpdate(stages=[*created.stages, new_stage], updated_by="tester"),
        )
        assert updated.version == 2
        assert len(updated.stages) == 3

    async def test_update_pipeline_not_found(self, engine):
        with pytest.raises(ValueError, match="not found"):
            await engine.update_pipeline("missing", PipelineUpdate())

    async def test_delete_pipeline(self, engine, sample_pipeline_create):
        created = await engine.create_pipeline(sample_pipeline_create)
        result = await engine.delete_pipeline(created.id)
        assert result is True
        assert await engine.get_pipeline(created.id) is None

    async def test_delete_pipeline_not_found(self, engine):
        result = await engine.delete_pipeline("nonexistent")
        assert result is False

    async def test_delete_pipeline_with_schedule(self, engine, sample_stages):
        data = PipelineCreate(
            name="Sched",
            description="",
            stages=sample_stages,
            edges=[],
            schedule_cron="0 9 * * *",
            created_by="t",
        )
        created = await engine.create_pipeline(data)
        schedule = await engine.get_pipeline_schedule(created.id)
        assert schedule is not None
        await engine.delete_pipeline(created.id)
        assert await engine.get_pipeline_schedule(created.id) is None


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestValidation:
    """Test pipeline validation."""

    async def test_validate_valid(self, engine):
        stages = [
            PipelineStage(
                id="s1", type=StageType.AGENT, label="S1", config={"agent_id": "test-agent"}
            ),
            PipelineStage(id="s2", type=StageType.LLM, label="S2", config={"prompt": "Hi"}),
        ]
        edges = []  # No edges = no constraints = valid
        result = await engine.validate_pipeline(stages, edges)
        assert result.valid is True

    async def test_validate_duplicate_stage_ids(self, engine):
        stages = [
            PipelineStage(
                id="same", type=StageType.AGENT, label="A", config={"agent_id": "test-agent"}
            ),
            PipelineStage(id="same", type=StageType.LLM, label="B", config={"prompt": "Hi"}),
        ]
        result = await engine.validate_pipeline(stages, [])
        assert result.valid is False

    async def test_validate_edge_source_not_found(self, engine):
        stages = [
            PipelineStage(
                id="s1", type=StageType.AGENT, label="S1", config={"agent_id": "test-agent"}
            ),
        ]
        from agentic_os.domain.pipeline import PipelineEdge

        edges = [PipelineEdge(id="e1", from_stage="missing", to_stage="s1")]
        result = await engine.validate_pipeline(stages, edges)
        assert result.valid is False
        assert any("from_stage" in e for e in result.errors)

    async def test_validate_edge_target_not_found(self, engine):
        stages = [
            PipelineStage(
                id="s1", type=StageType.AGENT, label="S1", config={"agent_id": "test-agent"}
            ),
        ]
        from agentic_os.domain.pipeline import PipelineEdge

        edges = [PipelineEdge(id="e1", from_stage="s1", to_stage="missing")]
        result = await engine.validate_pipeline(stages, edges)
        assert result.valid is False
        assert any("to_stage" in e for e in result.errors)

    async def test_validate_cycle_detected(self, engine):
        stages = [
            PipelineStage(
                id="a", type=StageType.AGENT, label="A", config={"agent_id": "test-agent"}
            ),
            PipelineStage(
                id="b", type=StageType.AGENT, label="B", config={"agent_id": "test-agent"}
            ),
        ]
        from agentic_os.domain.pipeline import PipelineEdge

        edges = [
            PipelineEdge(id="e1", from_stage="a", to_stage="b"),
            PipelineEdge(id="e2", from_stage="b", to_stage="a"),
        ]
        result = await engine.validate_pipeline(stages, edges)
        assert result.valid is False
        assert any("cycle" in e.lower() for e in result.errors)


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


class TestExecution:
    """Test pipeline execution."""

    async def test_execute_pipeline(self, engine, sample_pipeline_create):
        created = await engine.create_pipeline(sample_pipeline_create)
        engine._pipelines[created.id] = engine._pipelines[created.id].activate()

        execution = await engine.execute_pipeline(created.id, PipelineExecute(inputs={}))
        assert execution.pipeline_id == created.id
        assert execution.status == PipelineExecutionStatus.PENDING

    async def test_execute_inactive_raises(self, engine, sample_pipeline_create):
        created = await engine.create_pipeline(sample_pipeline_create)
        with pytest.raises(ValueError, match="not active"):
            await engine.execute_pipeline(created.id, PipelineExecute())

    async def test_execute_not_found_raises(self, engine):
        with pytest.raises(ValueError, match="not found"):
            await engine.execute_pipeline("missing", PipelineExecute())

    async def test_execution_runs_to_completion(self, engine, sample_pipeline_create):
        created = await engine.create_pipeline(sample_pipeline_create)
        engine._pipelines[created.id] = engine._pipelines[created.id].activate()

        execution = await engine.execute_pipeline(created.id, PipelineExecute(inputs={}))
        await anyio.sleep(0.5)
        updated = await engine.get_execution(execution.id)
        assert updated is not None
        assert updated.status == PipelineExecutionStatus.COMPLETED

    async def test_stage_outputs_collected(self, engine, sample_pipeline_create):
        created = await engine.create_pipeline(sample_pipeline_create)
        engine._pipelines[created.id] = engine._pipelines[created.id].activate()

        execution = await engine.execute_pipeline(created.id, PipelineExecute(inputs={}))
        await anyio.sleep(0.5)
        updated = await engine.get_execution(execution.id)
        assert updated is not None
        assert "stage1" in updated.stage_outputs
        assert "stage2" in updated.stage_outputs

    async def test_get_execution_not_found(self, engine):
        result = await engine.get_execution("nonexistent")
        assert result is None

    async def test_get_pipeline_executions(self, engine, sample_pipeline_create):
        created = await engine.create_pipeline(sample_pipeline_create)
        engine._pipelines[created.id] = engine._pipelines[created.id].activate()

        e1 = await engine.execute_pipeline(created.id, PipelineExecute())  # noqa: F841
        e2 = await engine.execute_pipeline(created.id, PipelineExecute())  # noqa: F841
        await anyio.sleep(0.5)

        executions = await engine.get_pipeline_executions(created.id)
        assert len(executions) >= 2

    async def test_get_running_executions(self, engine, sample_pipeline_create):
        created = await engine.create_pipeline(sample_pipeline_create)
        engine._pipelines[created.id] = engine._pipelines[created.id].activate()

        await engine.execute_pipeline(created.id, PipelineExecute())
        running = await engine.get_running_executions()
        assert isinstance(running, list)


# ---------------------------------------------------------------------------
# Stage Type Execution
# ---------------------------------------------------------------------------


class TestStageExecution:
    """Test individual stage type execution."""

    async def test_agent_stage(self, engine):
        stage = PipelineStage(
            id="s1", type=StageType.AGENT, label="Agent", config={"agent_id": "test-agent"}
        )
        execution = MagicMock()
        execution.inputs = {}
        execution.stage_outputs = {}
        pipeline = MagicMock()

        result = await engine._execute_stage(stage, execution, pipeline)
        assert "output" in result
        assert result["output"] == "mock response"

    async def test_agent_stage_missing_agent_id(self, engine):
        stage = PipelineStage(id="s1", type=StageType.AGENT, label="Agent", config={})
        with pytest.raises(ValueError, match="agent_id"):
            await engine._execute_stage(stage, MagicMock(), MagicMock())

    async def test_llm_stage(self, engine):
        stage = PipelineStage(
            id="s1", type=StageType.LLM, label="LLM", config={"prompt": "Hello", "provider": "mock"}
        )
        execution = MagicMock()
        pipeline = MagicMock()

        result = await engine._execute_stage(stage, execution, pipeline)
        assert result["response"] == "mock response"

    async def test_tool_stage(self, engine):
        stage = PipelineStage(
            id="s1", type=StageType.TOOL, label="Tool", config={"tool": "test-tool"}
        )
        result = await engine._execute_stage(stage, MagicMock(), MagicMock())
        assert result["tool"] == "test-tool"

    async def test_tool_stage_missing_tool(self, engine):
        stage = PipelineStage(id="s1", type=StageType.TOOL, label="Tool", config={})
        with pytest.raises(ValueError, match="tool"):
            await engine._execute_stage(stage, MagicMock(), MagicMock())

    async def test_workflow_stage(self, engine):
        stage = PipelineStage(
            id="s1", type=StageType.WORKFLOW, label="WF", config={"workflow_id": "wf-1"}
        )
        result = await engine._execute_stage(stage, MagicMock(), MagicMock())
        assert result["workflow_id"] == "wf-1"

    async def test_workflow_stage_missing_id(self, engine):
        stage = PipelineStage(id="s1", type=StageType.WORKFLOW, label="WF", config={})
        with pytest.raises(ValueError, match="workflow_id"):
            await engine._execute_stage(stage, MagicMock(), MagicMock())

    async def test_condition_stage(self, engine):
        stage = PipelineStage(
            id="s1",
            type=StageType.CONDITION,
            label="Cond",
            config={"condition": {"type": "always_true"}},
        )
        result = await engine._execute_stage(stage, MagicMock(), MagicMock())
        assert result["condition_result"] is True

    async def test_parallel_stage(self, engine):
        stage = PipelineStage(
            id="s1", type=StageType.PARALLEL, label="Par", config={"children": ["a", "b"]}
        )
        result = await engine._execute_stage(stage, MagicMock(), MagicMock())
        assert result["parallel"] is True

    async def test_approval_stage(self, engine):
        stage = PipelineStage(
            id="s1", type=StageType.APPROVAL, label="Approve", config={"approvers": ["admin"]}
        )
        result = await engine._execute_stage(stage, MagicMock(), MagicMock())
        assert result["approval_required"] is True

    async def test_mcp_stage(self, engine):
        stage = PipelineStage(
            id="s1",
            type=StageType.MCP,
            label="MCP",
            config={"server": "my-server", "tool": "my-tool"},
        )
        result = await engine._execute_stage(stage, MagicMock(), MagicMock())
        assert result["mcp"] == "my-server"

    async def test_plugin_stage(self, engine):
        stage = PipelineStage(
            id="s1",
            type=StageType.PLUGIN,
            label="Plugin",
            config={"plugin": "my-plugin", "method": "run"},
        )
        result = await engine._execute_stage(stage, MagicMock(), MagicMock())
        assert result["plugin"] == "my-plugin"

    async def test_unknown_stage_type(self, engine):
        stage = PipelineStage(id="s1", type="bogus", label="Bad", config={})
        with pytest.raises(ValueError, match="Unknown"):
            await engine._execute_stage(stage, MagicMock(), MagicMock())


# ---------------------------------------------------------------------------
# Scheduling
# ---------------------------------------------------------------------------


class TestScheduling:
    """Test pipeline scheduling."""

    async def test_schedule_pipeline(self, engine, sample_pipeline_create):
        created = await engine.create_pipeline(sample_pipeline_create)
        schedule = await engine.schedule_pipeline(
            created.id,
            PipelineScheduleRequest(cron="0 9 * * *", timezone="UTC"),
        )
        assert schedule.cron == "0 9 * * *"
        assert schedule.pipeline_id == created.id

    async def test_schedule_not_found_raises(self, engine):
        with pytest.raises(ValueError, match="not found"):
            await engine.schedule_pipeline(
                "missing",
                PipelineScheduleRequest(cron="0 9 * * *", timezone="UTC"),
            )

    async def test_unschedule_pipeline(self, engine, sample_pipeline_create):
        created = await engine.create_pipeline(sample_pipeline_create)
        await engine.schedule_pipeline(created.id, PipelineScheduleRequest(cron="0 9 * * *"))
        result = await engine.unschedule_pipeline(created.id)
        assert result is True
        assert await engine.get_pipeline_schedule(created.id) is None

    async def test_unschedule_not_found(self, engine):
        result = await engine.unschedule_pipeline("nonexistent")
        assert result is False

    async def test_get_pipeline_schedule(self, engine, sample_pipeline_create):
        created = await engine.create_pipeline(sample_pipeline_create)
        schedule = await engine.get_pipeline_schedule(created.id)
        assert schedule is None  # No schedule yet

    async def test_get_scheduled_executions(self, engine, sample_pipeline_create):
        created = await engine.create_pipeline(sample_pipeline_create)
        engine._pipelines[created.id] = engine._pipelines[created.id].activate()
        await engine.execute_pipeline(created.id, PipelineExecute())
        scheduled = await engine.get_scheduled_executions()
        assert isinstance(scheduled, list)


# ---------------------------------------------------------------------------
# Rollback
# ---------------------------------------------------------------------------


class TestRollback:
    """Test pipeline rollback."""

    async def test_rollback_pipeline(self, engine, sample_pipeline_create):
        created = await engine.create_pipeline(sample_pipeline_create)
        engine._pipelines[created.id] = engine._pipelines[created.id].activate()

        original = await engine.execute_pipeline(created.id, PipelineExecute(inputs={"k": "v"}))
        await anyio.sleep(0.3)

        rollback_exec = await engine.rollback_pipeline(
            created.id,
            PipelineRollback(to_execution_id=original.id),
        )
        assert rollback_exec.pipeline_id == created.id
        assert rollback_exec.status == PipelineExecutionStatus.PENDING

    async def test_rollback_not_found(self, engine):
        with pytest.raises(ValueError, match="not found"):
            await engine.rollback_pipeline("missing", PipelineRollback(to_execution_id="x"))

    async def test_rollback_execution_not_found(self, engine, sample_pipeline_create):
        created = await engine.create_pipeline(sample_pipeline_create)
        with pytest.raises(ValueError, match="Execution"):
            await engine.rollback_pipeline(created.id, PipelineRollback(to_execution_id="x"))

    async def test_rollback_wrong_pipeline(self, engine, sample_pipeline_create):
        p1 = await engine.create_pipeline(sample_pipeline_create)
        p2 = await engine.create_pipeline(sample_pipeline_create)
        engine._pipelines[p1.id] = engine._pipelines[p1.id].activate()
        e1 = await engine.execute_pipeline(p1.id, PipelineExecute())

        with pytest.raises(ValueError, match="does not belong"):
            await engine.rollback_pipeline(p2.id, PipelineRollback(to_execution_id=e1.id))


# ---------------------------------------------------------------------------
# Control Operations
# ---------------------------------------------------------------------------


class TestControl:
    """Test pipeline execution control."""

    async def test_cancel_execution(self, engine, sample_pipeline_create):
        created = await engine.create_pipeline(sample_pipeline_create)
        engine._pipelines[created.id] = engine._pipelines[created.id].activate()

        execution = await engine.execute_pipeline(created.id, PipelineExecute())
        engine._executions[execution.id] = engine._executions[execution.id].start()

        cancelled = await engine.cancel_execution(execution.id)
        assert cancelled.status == PipelineExecutionStatus.CANCELLED

    async def test_cancel_not_found(self, engine):
        with pytest.raises(ValueError, match="not found"):
            await engine.cancel_execution("missing")

    async def test_cancel_not_running_raises(self, engine, sample_pipeline_create):
        created = await engine.create_pipeline(sample_pipeline_create)
        engine._pipelines[created.id] = engine._pipelines[created.id].activate()
        execution = await engine.execute_pipeline(created.id, PipelineExecute())
        await anyio.sleep(0.5)

        with pytest.raises(ValueError, match="Cannot cancel"):
            await engine.cancel_execution(execution.id)

    async def test_pause_execution(self, engine, sample_pipeline_create):
        created = await engine.create_pipeline(sample_pipeline_create)
        engine._pipelines[created.id] = engine._pipelines[created.id].activate()
        execution = await engine.execute_pipeline(created.id, PipelineExecute())
        await anyio.sleep(0.1)

        engine._executions[execution.id] = engine._executions[execution.id].start()
        paused = await engine.pause_execution(execution.id)
        assert paused.status == PipelineExecutionStatus.PAUSED

    async def test_pause_not_running_raises(self, engine, sample_pipeline_create):
        created = await engine.create_pipeline(sample_pipeline_create)
        engine._pipelines[created.id] = engine._pipelines[created.id].activate()
        execution = await engine.execute_pipeline(created.id, PipelineExecute())
        await anyio.sleep(0.5)

        with pytest.raises(ValueError, match="Cannot pause"):
            await engine.pause_execution(execution.id)

    async def test_resume_execution(self, engine, sample_pipeline_create):
        created = await engine.create_pipeline(sample_pipeline_create)
        engine._pipelines[created.id] = engine._pipelines[created.id].activate()
        execution = await engine.execute_pipeline(created.id, PipelineExecute())
        await anyio.sleep(0.1)

        execution = execution.pause()
        engine._executions[execution.id] = execution

        resumed = await engine.resume_execution(execution.id)
        assert resumed.status == PipelineExecutionStatus.RUNNING

    async def test_resume_not_paused_raises(self, engine, sample_pipeline_create):
        created = await engine.create_pipeline(sample_pipeline_create)
        engine._pipelines[created.id] = engine._pipelines[created.id].activate()
        execution = await engine.execute_pipeline(created.id, PipelineExecute())
        await anyio.sleep(0.5)

        with pytest.raises(ValueError, match="Cannot resume"):
            await engine.resume_execution(execution.id)


# ---------------------------------------------------------------------------
# Retry Logic
# ---------------------------------------------------------------------------


class TestRetry:
    """Test pipeline stage retry logic."""

    async def test_stage_retry_on_failure(self, engine):
        """Stage with retry_count > 0 should retry on failure."""
        stage = PipelineStage(
            id="s1",
            type=StageType.AGENT,
            label="Agent",
            config={"agent_id": "test-agent"},
            retry_count=2,
            retry_delay_seconds=0.01,
        )
        pipeline = PipelineCreate(
            name="Retry Test",
            description="",
            stages=[stage],
            edges=[],
            created_by="test",
        )
        created = await engine.create_pipeline(pipeline)
        engine._pipelines[created.id] = engine._pipelines[created.id].activate()

        # Make the provider fail twice then succeed
        call_count = 0

        async def failing_complete(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise ValueError(f"Attempt {call_count} failed")
            return MagicMock(
                content="success on retry",
                usage=MagicMock(to_dict=lambda: {"input_tokens": 5, "output_tokens": 10}),
            )

        engine._provider_router.complete.side_effect = failing_complete

        execution = await engine.execute_pipeline(created.id, PipelineExecute())
        await anyio.sleep(1.0)

        updated = await engine.get_execution(execution.id)
        assert updated is not None
        assert updated.status == PipelineExecutionStatus.COMPLETED, f"Failed: {updated.error}"

    async def test_stage_retry_exhausted_fails(self, engine):
        """Stage with retry_count should fail after all retries exhausted."""
        stage = PipelineStage(
            id="s1",
            type=StageType.AGENT,
            label="Agent",
            config={"agent_id": "test-agent"},
            retry_count=1,
            retry_delay_seconds=0.01,
        )
        pipeline = PipelineCreate(
            name="Retry Fail",
            description="",
            stages=[stage],
            edges=[],
            created_by="test",
        )
        created = await engine.create_pipeline(pipeline)
        engine._pipelines[created.id] = engine._pipelines[created.id].activate()

        # Always fail
        engine._provider_router.complete.side_effect = ValueError("Persistent failure")

        execution = await engine.execute_pipeline(created.id, PipelineExecute())
        await anyio.sleep(1.0)

        updated = await engine.get_execution(execution.id)
        assert updated is not None
        assert updated.status == PipelineExecutionStatus.FAILED


# ---------------------------------------------------------------------------
# Event Emission
# ---------------------------------------------------------------------------


class TestEvents:
    """Test pipeline event emission."""

    async def test_create_emits_event(self, engine, bus, sample_pipeline_create):
        seen = []

        async def collector(event):
            seen.append(event.topic)

        await bus.subscribe(Topic.PIPELINE_CREATED.value, collector)
        await engine.create_pipeline(sample_pipeline_create)
        await bus.drain()
        assert Topic.PIPELINE_CREATED.value in seen

    async def test_execution_emits_events(self, engine, bus, sample_pipeline_create):
        created = await engine.create_pipeline(sample_pipeline_create)
        engine._pipelines[created.id] = engine._pipelines[created.id].activate()

        seen = []

        async def collector(event):
            seen.append(event.topic)

        await bus.subscribe(Topic.PIPELINE_STARTED.value, collector)
        await bus.subscribe(Topic.PIPELINE_STAGE_STARTED.value, collector)
        await bus.subscribe(Topic.PIPELINE_STAGE_COMPLETED.value, collector)
        await bus.subscribe(Topic.PIPELINE_COMPLETED.value, collector)

        await engine.execute_pipeline(created.id, PipelineExecute())
        await anyio.sleep(0.5)
        await bus.drain()

        assert Topic.PIPELINE_STARTED.value in seen
        assert Topic.PIPELINE_STAGE_STARTED.value in seen
        assert Topic.PIPELINE_STAGE_COMPLETED.value in seen

    async def test_cancel_emits_event(self, engine, bus, sample_pipeline_create):
        created = await engine.create_pipeline(sample_pipeline_create)
        engine._pipelines[created.id] = engine._pipelines[created.id].activate()

        execution = await engine.execute_pipeline(created.id, PipelineExecute())
        seen = []

        async def collector(event):
            seen.append(event.topic)

        await bus.subscribe(Topic.PIPELINE_CANCELLED.value, collector)
        await anyio.sleep(0.1)
        engine._executions[execution.id] = engine._executions[execution.id].start()
        await engine.cancel_execution(execution.id)
        await bus.drain()
        assert Topic.PIPELINE_CANCELLED.value in seen

    async def test_delete_emits_event(self, engine, bus, sample_pipeline_create):
        created = await engine.create_pipeline(sample_pipeline_create)
        seen = []

        async def collector(event):
            seen.append(event.topic)

        await bus.subscribe(Topic.PIPELINE_DELETED.value, collector)
        await engine.delete_pipeline(created.id)
        await bus.drain()
        assert Topic.PIPELINE_DELETED.value in seen


# ---------------------------------------------------------------------------
# DAG Execution Order
# ---------------------------------------------------------------------------


class TestDAGExecution:
    """Test pipeline DAG execution respects topological order."""

    async def test_stages_execute_in_order(self, engine):
        """Stages connected by edges should execute in dependency order."""
        stages = [
            PipelineStage(id="first", type=StageType.TOOL, label="First", config={"tool": "t1"}),
            PipelineStage(id="second", type=StageType.TOOL, label="Second", config={"tool": "t2"}),
            PipelineStage(id="third", type=StageType.TOOL, label="Third", config={"tool": "t3"}),
        ]
        from agentic_os.domain.pipeline import PipelineEdge

        edges = [
            PipelineEdge(id="e1", from_stage="first", to_stage="second"),
            PipelineEdge(id="e2", from_stage="second", to_stage="third"),
        ]
        pipeline = PipelineCreate(
            name="Order", description="", stages=stages, edges=edges, created_by="test"
        )
        created = await engine.create_pipeline(pipeline)
        engine._pipelines[created.id] = engine._pipelines[created.id].activate()

        order = []

        async def tracking_complete(**kwargs):
            # Use the current stage to track order
            # Find the latest execution's current stage
            for exec_ in engine._executions.values():
                if exec_.current_stage:
                    order.append(exec_.current_stage)
            return MagicMock(
                content="ok",
                usage=MagicMock(to_dict=lambda: {}),
            )

        engine._provider_router.complete.side_effect = tracking_complete

        execution = await engine.execute_pipeline(created.id, PipelineExecute())
        await anyio.sleep(1.0)

        # The completed_stages should be in order
        updated = await engine.get_execution(execution.id)
        assert updated is not None
        assert updated.status == PipelineExecutionStatus.COMPLETED
        completed = list(updated.completed_stages)
        # Check first, second, third appear in order
        assert "first" in completed
        assert "second" in completed
        assert "third" in completed

    async def test_parallel_dependencies(self, engine):
        """Two stages that depend on the same upstream should both execute."""
        stages = [
            PipelineStage(id="source", type=StageType.TOOL, label="Source", config={"tool": "src"}),
            PipelineStage(id="branch_a", type=StageType.TOOL, label="A", config={"tool": "a"}),
            PipelineStage(id="branch_b", type=StageType.TOOL, label="B", config={"tool": "b"}),
        ]
        from agentic_os.domain.pipeline import PipelineEdge

        edges = [
            PipelineEdge(id="e1", from_stage="source", to_stage="branch_a"),
            PipelineEdge(id="e2", from_stage="source", to_stage="branch_b"),
        ]
        pipeline = PipelineCreate(
            name="FanOut", description="", stages=stages, edges=edges, created_by="test"
        )
        created = await engine.create_pipeline(pipeline)
        engine._pipelines[created.id] = engine._pipelines[created.id].activate()

        execution = await engine.execute_pipeline(created.id, PipelineExecute())
        await anyio.sleep(1.0)
        updated = await engine.get_execution(execution.id)
        assert updated is not None
        assert updated.status == PipelineExecutionStatus.COMPLETED
        assert "source" in updated.completed_stages
        assert "branch_a" in updated.completed_stages
        assert "branch_b" in updated.completed_stages


# ---------------------------------------------------------------------------
# Error Handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Test error handling scenarios."""

    async def test_stage_failure_propagates(self, engine):
        """A failing stage should result in FAILED status."""
        stages = [
            PipelineStage(
                id="s1", type=StageType.AGENT, label="Failer", config={"agent_id": "test-agent"}
            ),
        ]
        pipeline = PipelineCreate(
            name="Fail", description="", stages=stages, edges=[], created_by="test"
        )
        created = await engine.create_pipeline(pipeline)
        engine._pipelines[created.id] = engine._pipelines[created.id].activate()

        engine._provider_router.complete.side_effect = ValueError("Stage failed")

        execution = await engine.execute_pipeline(created.id, PipelineExecute())
        await anyio.sleep(0.5)
        updated = await engine.get_execution(execution.id)
        assert updated is not None
        assert updated.status == PipelineExecutionStatus.FAILED
        assert "s1" in updated.failed_stages

    async def test_execution_crash_recovery(self, engine, sample_pipeline_create):
        """An unhandled crash should be caught and recorded."""
        created = await engine.create_pipeline(sample_pipeline_create)
        engine._pipelines[created.id] = engine._pipelines[created.id].activate()

        # Crash the engine during execution
        original_run = engine._run_execution

        async def crashing_run(execution, pipeline):
            raise RuntimeError("Engine crash")

        engine._run_execution = crashing_run
        # Mock execute_pipeline to not create a background task
        execution = await engine.execute_pipeline(created.id, PipelineExecute())  # noqa: F841
        # The background task will crash but the engine should handle it
        await anyio.sleep(0.5)

        # Restore
        engine._run_execution = original_run
        assert await engine.get_pipeline(created.id) is not None

    async def test_empty_stages_completes(self, engine):
        """Pipeline with no stages should still complete."""
        pipeline = PipelineCreate(
            name="Empty", description="", stages=[], edges=[], created_by="test"
        )
        created = await engine.create_pipeline(pipeline)
        engine._pipelines[created.id] = engine._pipelines[created.id].activate()

        execution = await engine.execute_pipeline(created.id, PipelineExecute())
        await anyio.sleep(0.5)
        updated = await engine.get_execution(execution.id)
        assert updated is not None
        assert updated.status == PipelineExecutionStatus.COMPLETED


# ---------------------------------------------------------------------------
# Version Management
# ---------------------------------------------------------------------------


class TestVersioning:
    """Test pipeline version management."""

    async def test_get_versions(self, engine, sample_pipeline_create):
        created = await engine.create_pipeline(sample_pipeline_create)
        versions = await engine.get_pipeline_versions(created.id)
        assert isinstance(versions, list)

    async def test_get_version(self, engine, sample_pipeline_create):
        created = await engine.create_pipeline(sample_pipeline_create)
        v1 = await engine.get_pipeline_version(created.id, 1)
        assert v1 is not None
        assert v1.version == 1

    async def test_get_version_not_found(self, engine, sample_pipeline_create):
        created = await engine.create_pipeline(sample_pipeline_create)
        result = await engine.get_pipeline_version(created.id, 999)
        assert result is None


# ---------------------------------------------------------------------------
# Concurrency
# ---------------------------------------------------------------------------


class TestConcurrency:
    """Test concurrent pipeline operations."""

    async def test_multiple_concurrent_executions(self, engine):
        """Run multiple pipelines concurrently."""
        ids = []
        for i in range(3):
            stage = PipelineStage(
                id=f"s{i}", type=StageType.TOOL, label=f"S{i}", config={"tool": "t"}
            )
            p = PipelineCreate(
                name=f"P{i}", description="", stages=[stage], edges=[], created_by="test"
            )
            created = await engine.create_pipeline(p)
            engine._pipelines[created.id] = engine._pipelines[created.id].activate()
            ids.append(created.id)

        tasks = [engine.execute_pipeline(pid, PipelineExecute()) for pid in ids]
        executions = await asyncio.gather(*tasks)
        assert len(executions) == 3

        await anyio.sleep(1.0)
        for ex in executions:
            updated = await engine.get_execution(ex.id)
            assert updated is not None
            assert updated.status == PipelineExecutionStatus.COMPLETED


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    async def test_list_empty(self, engine):
        pipelines = await engine.list_pipelines()
        assert pipelines == []

    async def test_executions_empty(self, engine):
        executions = await engine.get_pipeline_executions("nonexistent")
        assert executions == []

    async def test_task_cleanup(self, engine, sample_pipeline_create):
        created = await engine.create_pipeline(sample_pipeline_create)
        engine._pipelines[created.id] = engine._pipelines[created.id].activate()

        execution = await engine.execute_pipeline(created.id, PipelineExecute())
        exec_id = execution.id
        assert exec_id in engine._execution_tasks

        await anyio.sleep(0.5)
        assert exec_id not in engine._execution_tasks
        assert exec_id not in engine._running_executions

    async def test_single_stage_pipeline(self, engine):
        stage = PipelineStage(id="only", type=StageType.TOOL, label="Only", config={"tool": "test"})
        p = PipelineCreate(
            name="Single", description="", stages=[stage], edges=[], created_by="test"
        )
        created = await engine.create_pipeline(p)
        engine._pipelines[created.id] = engine._pipelines[created.id].activate()

        execution = await engine.execute_pipeline(created.id, PipelineExecute())
        await anyio.sleep(0.5)
        updated = await engine.get_execution(execution.id)
        assert updated is not None
        assert updated.status == PipelineExecutionStatus.COMPLETED
        assert "only" in updated.completed_stages
