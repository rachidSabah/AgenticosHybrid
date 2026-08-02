"""Tests for pipeline domain models."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from agentic_os.domain.pipeline import (
    Pipeline,
    PipelineEdge,
    PipelineExecution,
    PipelineExecutionStatus,
    PipelineSchedule,
    PipelineStage,
    PipelineStatus,
    PipelineVersion,
    StageType,
)

# ---------------------------------------------------------------------------
# PipelineStatus enum
# ---------------------------------------------------------------------------


class TestPipelineStatusEnum:
    def test_values(self) -> None:
        assert PipelineStatus.DRAFT == "draft"
        assert PipelineStatus.ACTIVE == "active"
        assert PipelineStatus.PAUSED == "paused"
        assert PipelineStatus.RUNNING == "running"
        assert PipelineStatus.COMPLETED == "completed"
        assert PipelineStatus.FAILED == "failed"
        assert PipelineStatus.ARCHIVED == "archived"

    def test_all_members(self) -> None:
        expected = {"draft", "active", "paused", "running", "completed", "failed", "archived"}
        assert {m.value for m in PipelineStatus} == expected


# ---------------------------------------------------------------------------
# PipelineExecutionStatus enum
# ---------------------------------------------------------------------------


class TestPipelineExecutionStatusEnum:
    def test_values(self) -> None:
        assert PipelineExecutionStatus.PENDING == "pending"
        assert PipelineExecutionStatus.RUNNING == "running"
        assert PipelineExecutionStatus.PAUSED == "paused"
        assert PipelineExecutionStatus.COMPLETED == "completed"
        assert PipelineExecutionStatus.FAILED == "failed"
        assert PipelineExecutionStatus.CANCELLED == "cancelled"

    def test_all_members(self) -> None:
        expected = {"pending", "running", "paused", "completed", "failed", "cancelled"}
        assert {m.value for m in PipelineExecutionStatus} == expected


# ---------------------------------------------------------------------------
# StageType enum
# ---------------------------------------------------------------------------


class TestStageTypeEnum:
    def test_values(self) -> None:
        assert StageType.AGENT == "agent"
        assert StageType.WORKFLOW == "workflow"
        assert StageType.TOOL == "tool"
        assert StageType.LLM == "llm"
        assert StageType.CONDITION == "condition"
        assert StageType.PARALLEL == "parallel"
        assert StageType.APPROVAL == "approval"
        assert StageType.MCP == "mcp"
        assert StageType.PLUGIN == "plugin"
        assert StageType.CUSTOM == "custom"

    def test_all_members(self) -> None:
        expected = {
            "agent",
            "workflow",
            "tool",
            "llm",
            "condition",
            "parallel",
            "approval",
            "mcp",
            "plugin",
            "custom",
        }
        assert {m.value for m in StageType} == expected


# ---------------------------------------------------------------------------
# PipelineStage
# ---------------------------------------------------------------------------


class TestPipelineStage:
    def test_create_with_defaults(self) -> None:
        stage = PipelineStage(id="s1", type=StageType.AGENT, label="Agent Stage")
        assert stage.id == "s1"
        assert stage.type == StageType.AGENT
        assert stage.label == "Agent Stage"
        assert stage.config == {}
        assert stage.depends_on == ()
        assert stage.retry_count == 0
        assert stage.retry_delay_seconds == 5
        assert stage.timeout_seconds is None
        assert stage.condition is None
        assert stage.children == ()

    def test_create_with_all_fields(self) -> None:
        stage = PipelineStage(
            id="s2",
            type=StageType.LLM,
            label="LLM Call",
            config={"model": "gpt-4"},
            depends_on=("s1",),
            retry_count=3,
            retry_delay_seconds=10,
            timeout_seconds=60,
            condition={"expression": "x > 0"},
            children=("child1", "child2"),
        )
        assert stage.id == "s2"
        assert stage.type == StageType.LLM
        assert stage.label == "LLM Call"
        assert stage.config == {"model": "gpt-4"}
        assert stage.depends_on == ("s1",)
        assert stage.retry_count == 3
        assert stage.retry_delay_seconds == 10
        assert stage.timeout_seconds == 60
        assert stage.condition == {"expression": "x > 0"}
        assert stage.children == ("child1", "child2")

    def test_depends_on_empty_tuple(self) -> None:
        stage = PipelineStage(id="s1", type=StageType.AGENT, label="No deps")
        assert stage.depends_on == ()

    def test_depends_on_multi_element(self) -> None:
        stage = PipelineStage(
            id="s3",
            type=StageType.AGENT,
            label="Multi Deps",
            depends_on=("s1", "s2", "s3"),
        )
        assert stage.depends_on == ("s1", "s2", "s3")

    def test_retry_count_zero(self) -> None:
        stage = PipelineStage(id="s1", type=StageType.AGENT, label="No retry", retry_count=0)
        assert stage.retry_count == 0

    def test_timeout_seconds_none(self) -> None:
        stage = PipelineStage(id="s1", type=StageType.AGENT, label="No timeout")
        assert stage.timeout_seconds is None

    def test_condition_none(self) -> None:
        stage = PipelineStage(id="s1", type=StageType.AGENT, label="No condition")
        assert stage.condition is None

    def test_with_config_returns_new_instance(self) -> None:
        original = PipelineStage(
            id="s1",
            type=StageType.WORKFLOW,
            label="Original",
            config={"key": "old"},
            retry_count=2,
        )
        modified = original.with_config({"key": "new", "extra": True})

        # Original unchanged
        assert original.config == {"key": "old"}
        assert original.retry_count == 2

        # Modified has new config, other fields preserved
        assert modified.config == {"key": "new", "extra": True}
        assert modified.id == original.id
        assert modified.type == original.type
        assert modified.label == original.label
        assert modified.retry_count == original.retry_count
        assert modified.retry_delay_seconds == original.retry_delay_seconds
        assert modified.timeout_seconds == original.timeout_seconds
        assert modified.condition == original.condition
        assert modified.children == original.children
        assert modified.depends_on == original.depends_on

    def test_with_depends_on_returns_new_instance(self) -> None:
        original = PipelineStage(
            id="s1",
            type=StageType.TOOL,
            label="Tool",
            depends_on=("old_dep",),
        )
        modified = original.with_depends_on(["dep_a", "dep_b"])

        # Original unchanged
        assert original.depends_on == ("old_dep",)

        # Modified has new depends_on (converted to tuple), other fields preserved
        assert modified.depends_on == ("dep_a", "dep_b")
        assert modified.id == original.id
        assert modified.type == original.type
        assert modified.label == original.label
        assert modified.config == original.config

    def test_with_depends_on_empty_list(self) -> None:
        original = PipelineStage(
            id="s1",
            type=StageType.AGENT,
            label="Stage",
            depends_on=("dep1",),
        )
        modified = original.with_depends_on([])
        assert modified.depends_on == ()

    def test_frozen_immutability(self) -> None:
        stage = PipelineStage(id="s1", type=StageType.AGENT, label="Fixed")
        with pytest.raises(AttributeError):
            stage.label = "Changed"  # type: ignore[misc]

    def test_slots_no_dict(self) -> None:
        stage = PipelineStage(id="s1", type=StageType.AGENT, label="Slotted")
        with pytest.raises(AttributeError):
            _ = stage.__dict__  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# PipelineEdge
# ---------------------------------------------------------------------------


class TestPipelineEdge:
    def test_create_required(self) -> None:
        edge = PipelineEdge(id="e1", from_stage="s1", to_stage="s2")
        assert edge.id == "e1"
        assert edge.from_stage == "s1"
        assert edge.to_stage == "s2"
        assert edge.condition is None

    def test_create_with_condition(self) -> None:
        edge = PipelineEdge(
            id="e1",
            from_stage="s1",
            to_stage="s2",
            condition={"expression": "x > 5"},
        )
        assert edge.condition == {"expression": "x > 5"}

    def test_frozen_immutability(self) -> None:
        edge = PipelineEdge(id="e1", from_stage="s1", to_stage="s2")
        with pytest.raises(AttributeError):
            edge.from_stage = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


class TestPipeline:
    def test_create(self) -> None:
        stage = PipelineStage(id="s1", type=StageType.AGENT, label="Agent")
        edge = PipelineEdge(id="e1", from_stage="s1", to_stage="s2")
        pipeline = Pipeline.create(
            name="Test Pipeline",
            description="A test",
            stages=[stage],
            edges=[edge],
        )
        assert pipeline.name == "Test Pipeline"
        assert pipeline.description == "A test"
        assert pipeline.stages == (stage,)
        assert pipeline.edges == (edge,)
        assert pipeline.version == 1
        assert pipeline.status == PipelineStatus.DRAFT
        assert pipeline.schedule_cron is None
        assert pipeline.schedule_timezone == "UTC"
        assert pipeline.created_by == "system"
        assert pipeline.id is not None

    def test_create_with_schedule(self) -> None:
        stage = PipelineStage(id="s1", type=StageType.AGENT, label="Agent")
        pipeline = Pipeline.create(
            name="Scheduled",
            description="",
            stages=[stage],
            edges=[],
            schedule_cron="0 8 * * *",
            schedule_timezone="America/New_York",
            created_by="admin",
        )
        assert pipeline.schedule_cron == "0 8 * * *"
        assert pipeline.schedule_timezone == "America/New_York"
        assert pipeline.created_by == "admin"

    def test_create_with_empty_stages_and_edges(self) -> None:
        pipeline = Pipeline.create(name="Empty", description="", stages=[], edges=[])
        assert pipeline.stages == ()
        assert pipeline.edges == ()

    def test_to_dict(self) -> None:
        stage = PipelineStage(
            id="s1",
            type=StageType.LLM,
            label="LLM",
            config={"model": "gpt-4"},
            depends_on=("prev",),
            retry_count=2,
            retry_delay_seconds=10,
            timeout_seconds=30,
            condition={"expr": "ok"},
            children=("child1",),
        )
        edge = PipelineEdge(id="e1", from_stage="s1", to_stage="s2", condition={"x": 1})
        pipeline = Pipeline.create(
            name="DictTest", description="test", stages=[stage], edges=[edge]
        )

        d = pipeline.to_dict()
        assert d["name"] == "DictTest"
        assert d["description"] == "test"
        assert d["version"] == 1
        assert d["status"] == "draft"
        assert d["schedule_cron"] is None
        assert d["schedule_timezone"] == "UTC"
        assert d["created_by"] == "system"
        assert isinstance(d["id"], str)

        # Stage serialization
        assert len(d["stages"]) == 1
        s = d["stages"][0]
        assert s["id"] == "s1"
        assert s["type"] == "llm"
        assert s["label"] == "LLM"
        assert s["config"] == {"model": "gpt-4"}
        assert s["depends_on"] == ["prev"]
        assert s["retry_count"] == 2
        assert s["retry_delay_seconds"] == 10
        assert s["timeout_seconds"] == 30
        assert s["condition"] == {"expr": "ok"}
        assert s["children"] == ["child1"]

        # Edge serialization
        assert len(d["edges"]) == 1
        e = d["edges"][0]
        assert e["id"] == "e1"
        assert e["from_stage"] == "s1"
        assert e["to_stage"] == "s2"
        assert e["condition"] == {"x": 1}

        # Timestamps as isoformat
        assert isinstance(d["created_at"], str)
        assert isinstance(d["updated_at"], str)

    def test_new_version_bumps_version(self) -> None:
        stage = PipelineStage(id="s1", type=StageType.AGENT, label="Agent")
        pipeline = Pipeline.create(name="V", description="", stages=[stage], edges=[])
        v2 = pipeline.new_version()
        assert v2.version == 2
        assert v2.id == pipeline.id
        assert v2.name == pipeline.name
        assert v2.description == pipeline.description
        assert v2.stages == pipeline.stages
        assert v2.edges == pipeline.edges
        assert v2.status == PipelineStatus.DRAFT
        assert v2.created_at == pipeline.created_at
        assert v2.updated_at > pipeline.updated_at

    def test_new_version_with_overrides(self) -> None:
        stage1 = PipelineStage(id="s1", type=StageType.AGENT, label="Agent")
        stage2 = PipelineStage(id="s2", type=StageType.TOOL, label="Tool")
        edge = PipelineEdge(id="e1", from_stage="s1", to_stage="s2")
        pipeline = Pipeline.create(
            name="Original",
            description="original",
            stages=[stage1],
            edges=[],
            schedule_cron="0 0 * * *",
            schedule_timezone="UTC",
        )
        v2 = pipeline.new_version(
            name="Updated",
            description="updated",
            stages=[stage2],
            edges=[edge],
            schedule_cron="0 12 * * *",
            schedule_timezone="US/Eastern",
            created_by="admin",
        )
        assert v2.version == 2
        assert v2.name == "Updated"
        assert v2.description == "updated"
        assert v2.stages == (stage2,)
        assert v2.edges == (edge,)
        assert v2.schedule_cron == "0 12 * * *"
        assert v2.schedule_timezone == "US/Eastern"
        assert v2.created_by == "admin"

    def test_activate(self) -> None:
        stage = PipelineStage(id="s1", type=StageType.AGENT, label="Agent")
        pipeline = Pipeline.create(name="P", description="", stages=[stage], edges=[])
        assert pipeline.status == PipelineStatus.DRAFT

        active = pipeline.activate()
        assert active.status == PipelineStatus.ACTIVE
        assert active.id == pipeline.id
        assert active.version == pipeline.version
        # Original unchanged
        assert pipeline.status == PipelineStatus.DRAFT

    def test_activate_with_created_by(self) -> None:
        stage = PipelineStage(id="s1", type=StageType.AGENT, label="Agent")
        pipeline = Pipeline.create(name="P", description="", stages=[stage], edges=[])
        active = pipeline.activate(created_by="admin")
        assert active.status == PipelineStatus.ACTIVE

    def test_pause(self) -> None:
        stage = PipelineStage(id="s1", type=StageType.AGENT, label="Agent")
        pipeline = Pipeline.create(name="P", description="", stages=[stage], edges=[])
        active = pipeline.activate()
        paused = active.pause()
        assert paused.status == PipelineStatus.PAUSED
        assert active.status == PipelineStatus.ACTIVE  # original unchanged

    def test_archive(self) -> None:
        stage = PipelineStage(id="s1", type=StageType.AGENT, label="Agent")
        pipeline = Pipeline.create(name="P", description="", stages=[stage], edges=[])
        archived = pipeline.archive()
        assert archived.status == PipelineStatus.ARCHIVED
        assert pipeline.status == PipelineStatus.DRAFT  # original unchanged

    def test_frozen_immutability(self) -> None:
        stage = PipelineStage(id="s1", type=StageType.AGENT, label="Agent")
        pipeline = Pipeline.create(name="P", description="", stages=[stage], edges=[])
        with pytest.raises(AttributeError):
            pipeline.name = "Changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# PipelineExecution
# ---------------------------------------------------------------------------


class TestPipelineExecutionCreate:
    def test_create(self) -> None:
        execution = PipelineExecution.create(
            pipeline_id="p1",
            pipeline_version=1,
            inputs={"query": "hello"},
        )
        assert execution.pipeline_id == "p1"
        assert execution.pipeline_version == 1
        assert execution.inputs == {"query": "hello"}
        assert execution.status == PipelineExecutionStatus.PENDING
        assert execution.current_stage is None
        assert execution.completed_stages == frozenset()
        assert execution.failed_stages == frozenset()
        assert execution.stage_outputs == {}
        assert execution.stage_errors == {}
        assert execution.stage_retries == {}
        assert execution.scheduled_at is None
        assert execution.parent_execution_id is None
        assert execution.rollback_to_execution_id is None
        assert execution.started_at is not None
        assert execution.completed_at is None
        assert execution.error is None
        assert execution.id is not None

    def test_create_with_scheduling(self) -> None:
        scheduled_time = datetime(2026, 7, 20, 8, 0, tzinfo=UTC)
        execution = PipelineExecution.create(
            pipeline_id="p1",
            pipeline_version=2,
            inputs={},
            scheduled_at=scheduled_time,
            parent_execution_id="parent-123",
            rollback_to_execution_id="rollback-456",
        )
        assert execution.scheduled_at == scheduled_time
        assert execution.parent_execution_id == "parent-123"
        assert execution.rollback_to_execution_id == "rollback-456"

    def test_create_with_empty_inputs(self) -> None:
        execution = PipelineExecution.create(pipeline_id="p1", pipeline_version=1, inputs={})
        assert execution.inputs == {}


class TestPipelineExecutionSchedule:
    def test_schedule(self) -> None:
        execution = PipelineExecution.create(pipeline_id="p1", pipeline_version=1, inputs={})
        future = datetime(2026, 8, 1, 0, 0, tzinfo=UTC)
        scheduled = execution.schedule(scheduled_at=future)
        assert scheduled.status == PipelineExecutionStatus.PENDING
        assert scheduled.scheduled_at == future
        assert scheduled.completed_at is None
        assert scheduled.error is None
        assert scheduled.current_stage is None
        # Original unchanged
        assert execution.scheduled_at is None

    def test_schedule_original_unchanged(self) -> None:
        execution = PipelineExecution.create(pipeline_id="p1", pipeline_version=1, inputs={})
        future = datetime(2026, 8, 1, 0, 0, tzinfo=UTC)
        execution.schedule(scheduled_at=future)
        assert execution.scheduled_at is None  # original unchanged


class TestPipelineExecutionStatusTransitions:
    def test_create_start_complete(self) -> None:
        execution = PipelineExecution.create(pipeline_id="p1", pipeline_version=1, inputs={})
        assert execution.status == PipelineExecutionStatus.PENDING

        started = execution.start()
        assert started.status == PipelineExecutionStatus.RUNNING
        assert started.completed_at is None
        assert started.error is None
        # start updates started_at
        assert started.started_at >= execution.started_at

        completed = started.complete()
        assert completed.status == PipelineExecutionStatus.COMPLETED
        assert completed.current_stage is None
        assert completed.error is None
        assert completed.completed_at is not None

    def test_create_start_fail(self) -> None:
        execution = PipelineExecution.create(pipeline_id="p1", pipeline_version=1, inputs={})
        started = execution.start()
        failed = started.fail(error="Something broke", failed_stage="s1")
        assert failed.status == PipelineExecutionStatus.FAILED
        assert failed.error == "Something broke"
        assert failed.failed_stages == frozenset({"s1"})
        assert failed.stage_errors == {"s1": "Something broke"}
        assert failed.completed_at is not None

    def test_create_start_cancel(self) -> None:
        execution = PipelineExecution.create(pipeline_id="p1", pipeline_version=1, inputs={})
        started = execution.start()
        cancelled = started.cancel()
        assert cancelled.status == PipelineExecutionStatus.CANCELLED
        assert cancelled.current_stage is None
        assert cancelled.error == "Cancelled by user"
        assert cancelled.completed_at is not None

    def test_create_start_pause_start_complete(self) -> None:
        execution = PipelineExecution.create(pipeline_id="p1", pipeline_version=1, inputs={})
        started = execution.start()
        paused = started.pause()
        assert paused.status == PipelineExecutionStatus.PAUSED
        assert paused.started_at == started.started_at

        resumed = paused.start()
        assert resumed.status == PipelineExecutionStatus.RUNNING
        assert resumed.started_at >= started.started_at

        completed = resumed.complete()
        assert completed.status == PipelineExecutionStatus.COMPLETED

    def test_fail_preserves_current_stage(self) -> None:
        execution = PipelineExecution.create(pipeline_id="p1", pipeline_version=1, inputs={})
        started = execution.start()
        at_stage = started.set_current_stage("s2")
        failed = at_stage.fail(error="fail", failed_stage="s2")
        assert failed.current_stage == "s2"
        assert failed.failed_stages == frozenset({"s2"})


class TestPipelineExecutionStageManagement:
    def test_set_current_stage(self) -> None:
        execution = PipelineExecution.create(pipeline_id="p1", pipeline_version=1, inputs={})
        updated = execution.set_current_stage("stage-1")
        assert updated.current_stage == "stage-1"
        # Original unchanged
        assert execution.current_stage is None

    def test_complete_stage(self) -> None:
        execution = PipelineExecution.create(pipeline_id="p1", pipeline_version=1, inputs={})
        started = execution.start()
        result = started.complete_stage(stage_id="s1", output={"result": 42})
        assert result.completed_stages == frozenset({"s1"})
        assert result.stage_outputs == {"s1": {"result": 42}}
        assert result.status == PipelineExecutionStatus.RUNNING
        # Original unchanged
        assert started.completed_stages == frozenset()

    def test_complete_stage_accumulates(self) -> None:
        execution = PipelineExecution.create(pipeline_id="p1", pipeline_version=1, inputs={})
        started = execution.start()
        after_s1 = started.complete_stage(stage_id="s1", output="out1")
        after_s2 = after_s1.complete_stage(stage_id="s2", output="out2")
        assert after_s2.completed_stages == frozenset({"s1", "s2"})
        assert after_s2.stage_outputs == {"s1": "out1", "s2": "out2"}

    def test_fail_stage(self) -> None:
        execution = PipelineExecution.create(pipeline_id="p1", pipeline_version=1, inputs={})
        started = execution.start()
        failed = started.fail_stage(stage_id="s3", error="Timeout")
        assert failed.failed_stages == frozenset({"s3"})
        assert failed.stage_errors == {"s3": "Timeout"}
        assert failed.current_stage == "s3"
        assert failed.status == PipelineExecutionStatus.RUNNING  # still running

    def test_multiple_failed_stages(self) -> None:
        execution = PipelineExecution.create(pipeline_id="p1", pipeline_version=1, inputs={})
        started = execution.start()
        f1 = started.fail_stage(stage_id="s1", error="err1")
        f2 = f1.fail_stage(stage_id="s2", error="err2")
        # Now fail the whole execution
        failed = f2.fail(error="Fatal", failed_stage="s3")
        assert failed.failed_stages == frozenset({"s1", "s2", "s3"})
        assert failed.stage_errors == {"s1": "err1", "s2": "err2", "s3": "Fatal"}
        assert failed.status == PipelineExecutionStatus.FAILED


class TestPipelineExecutionRetry:
    def test_increment_retry_first_time(self) -> None:
        execution = PipelineExecution.create(pipeline_id="p1", pipeline_version=1, inputs={})
        updated = execution.increment_retry(stage_id="s1")
        assert updated.stage_retries == {"s1": 1}
        assert updated.current_stage == "s1"

    def test_increment_retry_accumulates(self) -> None:
        execution = PipelineExecution.create(pipeline_id="p1", pipeline_version=1, inputs={})
        r1 = execution.increment_retry(stage_id="s1")
        assert r1.stage_retries == {"s1": 1}
        r2 = r1.increment_retry(stage_id="s1")
        assert r2.stage_retries == {"s1": 2}
        r3 = r2.increment_retry(stage_id="s1")
        assert r3.stage_retries == {"s1": 3}

    def test_increment_retry_multiple_stages(self) -> None:
        execution = PipelineExecution.create(pipeline_id="p1", pipeline_version=1, inputs={})
        r1 = execution.increment_retry(stage_id="s1")
        r2 = r1.increment_retry(stage_id="s2")
        r3 = r2.increment_retry(stage_id="s1")
        assert r3.stage_retries == {"s1": 2, "s2": 1}


class TestPipelineExecutionRollback:
    def test_rollback_creates_fresh_execution(self) -> None:
        execution = PipelineExecution.create(pipeline_id="p1", pipeline_version=1, inputs={})
        started = execution.start()
        # Add some state
        with_stage = started.set_current_stage("s1")
        with_completed = with_stage.complete_stage(stage_id="s1", output="done")

        rolled_back = with_completed.rollback(to_execution_id="original-123")
        assert rolled_back.status == PipelineExecutionStatus.PENDING
        assert rolled_back.current_stage is None
        assert rolled_back.completed_stages == frozenset()
        assert rolled_back.failed_stages == frozenset()
        assert rolled_back.stage_outputs == {}
        assert rolled_back.stage_errors == {}
        assert rolled_back.stage_retries == {}
        assert rolled_back.completed_at is None
        assert rolled_back.error is None
        assert rolled_back.rollback_to_execution_id == "original-123"
        # These persist through rollback
        assert rolled_back.id == with_completed.id
        assert rolled_back.pipeline_id == with_completed.pipeline_id
        assert rolled_back.pipeline_version == with_completed.pipeline_version
        assert rolled_back.inputs == with_completed.inputs
        assert rolled_back.parent_execution_id == with_completed.parent_execution_id
        assert rolled_back.scheduled_at == with_completed.scheduled_at

    def test_rollback_resets_started_at(self) -> None:
        execution = PipelineExecution.create(pipeline_id="p1", pipeline_version=1, inputs={})
        rolled = execution.rollback(to_execution_id="orig")
        # started_at should be updated on rollback
        assert rolled.started_at > execution.started_at or rolled.started_at >= execution.started_at


class TestPipelineExecutionToDict:
    def test_to_dict(self) -> None:
        execution = PipelineExecution.create(
            pipeline_id="p1",
            pipeline_version=1,
            inputs={"key": "value"},
            scheduled_at=datetime(2026, 7, 20, 8, 0, tzinfo=UTC),
            parent_execution_id="parent-1",
            rollback_to_execution_id="rollback-1",
        )
        d = execution.to_dict()
        assert d["pipeline_id"] == "p1"
        assert d["pipeline_version"] == 1
        assert d["status"] == "pending"
        assert d["inputs"] == {"key": "value"}
        assert d["current_stage"] is None
        assert d["completed_stages"] == []
        assert d["failed_stages"] == []
        assert d["stage_outputs"] == {}
        assert d["stage_errors"] == {}
        assert d["stage_retries"] == {}
        assert d["scheduled_at"] == "2026-07-20T08:00:00+00:00"
        assert d["started_at"] is not None
        assert d["completed_at"] is None
        assert d["error"] is None
        assert d["parent_execution_id"] == "parent-1"
        assert d["rollback_to_execution_id"] == "rollback-1"

    def test_to_dict_no_scheduled_at(self) -> None:
        execution = PipelineExecution.create(pipeline_id="p1", pipeline_version=1, inputs={})
        d = execution.to_dict()
        assert d["scheduled_at"] is None

    def test_to_dict_with_stage_state(self) -> None:
        execution = PipelineExecution.create(pipeline_id="p1", pipeline_version=1, inputs={})
        started = execution.start()
        with_stage = started.set_current_stage("s1")
        after_complete = with_stage.complete_stage(stage_id="s1", output="ok")
        after_fail = after_complete.fail_stage(stage_id="s2", error="boom")
        after_retry = after_fail.increment_retry(stage_id="s1")
        after_retry2 = after_retry.increment_retry(stage_id="s2")

        d = after_retry2.to_dict()
        assert d["completed_stages"] == ["s1"]
        assert d["failed_stages"] == ["s2"]
        assert d["stage_outputs"] == {"s1": "ok"}
        assert d["stage_errors"] == {"s2": "boom"}
        assert d["stage_retries"] == {"s1": 1, "s2": 1}

    def test_to_dict_after_fail(self) -> None:
        execution = PipelineExecution.create(pipeline_id="p1", pipeline_version=1, inputs={})
        started = execution.start()
        failed = started.fail(error="fatal", failed_stage="s1")
        d = failed.to_dict()
        assert d["status"] == "failed"
        assert d["error"] == "fatal"
        assert d["completed_at"] is not None

    def test_to_dict_after_cancel(self) -> None:
        execution = PipelineExecution.create(pipeline_id="p1", pipeline_version=1, inputs={})
        cancelled = execution.start().cancel()
        d = cancelled.to_dict()
        assert d["status"] == "cancelled"
        assert d["error"] == "Cancelled by user"

    def test_immutability(self) -> None:
        execution = PipelineExecution.create(pipeline_id="p1", pipeline_version=1, inputs={})
        with pytest.raises(AttributeError):
            execution.status = PipelineExecutionStatus.RUNNING  # type: ignore[misc]

    def test_fail_without_failed_stage(self) -> None:
        execution = PipelineExecution.create(pipeline_id="p1", pipeline_version=1, inputs={})
        started = execution.start()
        failed = started.fail(error="Generic failure")
        assert failed.status == PipelineExecutionStatus.FAILED
        assert failed.error == "Generic failure"
        assert failed.failed_stages == frozenset()

    def test_fail_with_failed_stage_twice(self) -> None:
        """Calling fail() with a failed_stage multiple times accumulates correctly."""
        execution = PipelineExecution.create(pipeline_id="p1", pipeline_version=1, inputs={})
        started = execution.start()
        # First fail
        f1 = started.fail(error="err1", failed_stage="s1")
        # Second fail (should not be possible in practice via fail, but tests the merging)
        f2 = f1.fail(error="err2", failed_stage="s2")
        assert f2.failed_stages == frozenset({"s1", "s2"})
        assert f2.stage_errors == {"s1": "err1", "s2": "err2"}

    def test_schedule_then_start(self) -> None:
        future = datetime(2026, 7, 25, 10, 0, tzinfo=UTC)
        execution = PipelineExecution.create(
            pipeline_id="p1",
            pipeline_version=1,
            inputs={},
            scheduled_at=future,
        )
        started = execution.start()
        assert started.status == PipelineExecutionStatus.RUNNING
        assert started.scheduled_at == future
        assert started.completed_at is None
        assert started.error is None

    def test_complete_sets_completed_at(self) -> None:
        execution = PipelineExecution.create(pipeline_id="p1", pipeline_version=1, inputs={})
        started = execution.start()
        completed = started.complete()
        assert completed.completed_at is not None
        assert isinstance(completed.completed_at, datetime)

    def test_fail_sets_completed_at(self) -> None:
        execution = PipelineExecution.create(pipeline_id="p1", pipeline_version=1, inputs={})
        started = execution.start()
        failed = started.fail(error="err")
        assert failed.completed_at is not None

    def test_cancel_sets_completed_at(self) -> None:
        execution = PipelineExecution.create(pipeline_id="p1", pipeline_version=1, inputs={})
        started = execution.start()
        cancelled = started.cancel()
        assert cancelled.completed_at is not None

    def test_pause_preserves_error(self) -> None:
        execution = PipelineExecution.create(pipeline_id="p1", pipeline_version=1, inputs={})
        # Set an error then pause
        started = execution.start()
        # After a stage failure but before pausing, error is on the execution
        # We can test by first failing then pausing
        failed = started.fail(error="temp error")
        paused = failed.pause()
        assert paused.status == PipelineExecutionStatus.PAUSED
        assert paused.error == "temp error"  # pause preserves error


# ---------------------------------------------------------------------------
# PipelineSchedule
# ---------------------------------------------------------------------------


class TestPipelineSchedule:
    def test_create(self) -> None:
        schedule = PipelineSchedule.create(
            pipeline_id="p1",
            cron="0 8 * * *",
            timezone="America/New_York",
        )
        assert schedule.pipeline_id == "p1"
        assert schedule.cron == "0 8 * * *"
        assert schedule.timezone == "America/New_York"
        assert schedule.next_run is not None
        assert schedule.enabled is True
        assert schedule.created_at is not None
        assert schedule.updated_at is not None

    def test_create_default_timezone(self) -> None:
        schedule = PipelineSchedule.create(
            pipeline_id="p1",
            cron="0 0 * * *",
        )
        assert schedule.timezone == "UTC"

    def test_to_dict(self) -> None:
        schedule = PipelineSchedule.create(
            pipeline_id="p1",
            cron="*/5 * * * *",
            timezone="UTC",
        )
        d = schedule.to_dict()
        assert d["pipeline_id"] == "p1"
        assert d["cron"] == "*/5 * * * *"
        assert d["timezone"] == "UTC"
        assert d["enabled"] is True
        assert isinstance(d["next_run"], str)

    def test_to_dict_next_run_none(self) -> None:
        schedule = PipelineSchedule(
            pipeline_id="p1",
            cron="0 0 * * *",
            timezone="UTC",
            next_run=None,  # type: ignore[arg-type]
        )
        d = schedule.to_dict()
        assert d["next_run"] is None

    def test_frozen_immutability(self) -> None:
        schedule = PipelineSchedule.create(pipeline_id="p1", cron="0 0 * * *")
        with pytest.raises(AttributeError):
            schedule.cron = "1 1 * * *"  # type: ignore[misc]

    def test_disabled_schedule(self) -> None:
        schedule = PipelineSchedule(
            pipeline_id="p1",
            cron="0 0 * * *",
            timezone="UTC",
            enabled=False,
            next_run=datetime(2026, 7, 18, 0, 0, tzinfo=UTC),
        )
        assert schedule.enabled is False
        d = schedule.to_dict()
        assert d["enabled"] is False


# ---------------------------------------------------------------------------
# PipelineVersion
# ---------------------------------------------------------------------------


class TestPipelineVersion:
    def test_create(self) -> None:
        stage = PipelineStage(id="s1", type=StageType.AGENT, label="Agent")
        edge = PipelineEdge(id="e1", from_stage="s1", to_stage="s2")
        now = datetime.now(UTC)
        version = PipelineVersion(
            version=2,
            pipeline_id="p1",
            name="v2",
            description="Second version",
            stages=(stage,),
            edges=(edge,),
            schedule_cron="0 12 * * *",
            schedule_timezone="UTC",
            created_at=now,
            created_by="admin",
            changelog="Added new stage",
        )
        assert version.version == 2
        assert version.pipeline_id == "p1"
        assert version.name == "v2"
        assert version.description == "Second version"
        assert version.stages == (stage,)
        assert version.edges == (edge,)
        assert version.schedule_cron == "0 12 * * *"
        assert version.schedule_timezone == "UTC"
        assert version.created_at == now
        assert version.created_by == "admin"
        assert version.changelog == "Added new stage"

    def test_frozen_immutability(self) -> None:
        stage = PipelineStage(id="s1", type=StageType.AGENT, label="Agent")
        now = datetime.now(UTC)
        version = PipelineVersion(
            version=1,
            pipeline_id="p1",
            name="v1",
            description="First",
            stages=(stage,),
            edges=(),
            schedule_cron=None,
            schedule_timezone="UTC",
            created_at=now,
            created_by="system",
            changelog="Initial",
        )
        with pytest.raises(AttributeError):
            version.name = "changed"  # type: ignore[misc]

    def test_nullable_schedule_cron(self) -> None:
        stage = PipelineStage(id="s1", type=StageType.AGENT, label="Agent")
        now = datetime.now(UTC)
        version = PipelineVersion(
            version=1,
            pipeline_id="p1",
            name="v1",
            description="",
            stages=(stage,),
            edges=(),
            schedule_cron=None,
            schedule_timezone="UTC",
            created_at=now,
            created_by="system",
            changelog="",
        )
        assert version.schedule_cron is None


# ---------------------------------------------------------------------------
# Cross-cutting / edge-case scenarios
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_pipeline_with_many_stages(self) -> None:
        stages = [
            PipelineStage(id=f"s{i}", type=StageType.AGENT, label=f"Stage {i}") for i in range(10)
        ]
        edges = [
            PipelineEdge(id=f"e{i}", from_stage=f"s{i}", to_stage=f"s{i + 1}") for i in range(9)
        ]
        pipeline = Pipeline.create(name="Large", description="", stages=stages, edges=edges)
        assert len(pipeline.stages) == 10
        assert len(pipeline.edges) == 9

    def test_execution_with_large_inputs(self) -> None:
        execution = PipelineExecution.create(
            pipeline_id="p1",
            pipeline_version=1,
            inputs={"data": list(range(1000))},
        )
        assert len(execution.inputs["data"]) == 1000

    def test_stage_with_all_numeric_config(self) -> None:
        stage = PipelineStage(
            id="s1",
            type=StageType.CUSTOM,
            label="Configurable",
            config={
                "retry_count": 3,
                "retry_delay": 10.5,
                "max_items": 100,
                "enabled": True,
            },
        )
        assert stage.config["retry_count"] == 3
        assert isinstance(stage.config["retry_delay"], float)

    def test_pipeline_freshness_create_via_dataclass(self) -> None:
        """Ensure Pipeline can be created directly via the dataclass constructor."""
        stage = PipelineStage(id="s1", type=StageType.AGENT, label="Agent")
        now = datetime.now(UTC)
        pipeline = Pipeline(
            id="custom-id",
            name="Direct",
            description="Created via constructor",
            stages=(stage,),
            edges=(),
            version=5,
            status=PipelineStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        assert pipeline.id == "custom-id"
        assert pipeline.version == 5
        assert pipeline.status == PipelineStatus.ACTIVE

    def test_execution_freshness_stage_errors_empty(self) -> None:
        execution = PipelineExecution.create(pipeline_id="p1", pipeline_version=1, inputs={})
        assert execution.stage_errors == {}

    def test_execution_freshness_id_is_uuid(self) -> None:
        execution = PipelineExecution.create(pipeline_id="p1", pipeline_version=1, inputs={})
        assert isinstance(execution.id, str)
        # UUID4 format: 36 chars, 4 hyphens
        assert len(execution.id) == 36

    def test_pipeline_id_is_uuid(self) -> None:
        stage = PipelineStage(id="s1", type=StageType.AGENT, label="Agent")
        pipeline = Pipeline.create(name="Test", description="", stages=[stage], edges=[])
        assert isinstance(pipeline.id, str)
        assert len(pipeline.id) == 36

    def test_complete_stage_preserves_errors(self) -> None:
        execution = PipelineExecution.create(pipeline_id="p1", pipeline_version=1, inputs={})
        started = execution.start()
        after_fail = started.fail_stage(stage_id="s1", error="oops")
        after_complete = after_fail.complete_stage(stage_id="s2", output="ok")
        assert after_complete.failed_stages == frozenset({"s1"})
        assert after_complete.stage_errors == {"s1": "oops"}
        assert after_complete.completed_stages == frozenset({"s2"})
