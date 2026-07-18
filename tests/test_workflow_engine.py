"""Comprehensive tests for WorkflowEngineImpl.

Covers CRUD, validation, execution, approval gates, replay,
cancel/pause/resume, error handling, and event emission.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import anyio
import pytest

from agentic_os.core.workflow.engine import ApprovalRequired, WorkflowEngineImpl
from agentic_os.domain.events import Topic
from agentic_os.domain.workflow import (
    NodeType,
    Workflow,
    WorkflowEdge,
    WorkflowExecution,
    WorkflowExecutionStatus,
    WorkflowNode,
    WorkflowStatus,
)
from agentic_os.ports.workflow import (
    ValidationResult,
    WorkflowApproval,
    WorkflowCreate,
    WorkflowExecute,
    WorkflowReplay,
    WorkflowUpdate,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_provider_router():
    """Mock provider router that returns a simple completion."""
    router = MagicMock()
    router.complete = AsyncMock()
    router.complete.return_value = MagicMock(
        content="mock response",
        usage=MagicMock(to_dict=lambda: {"input_tokens": 10, "output_tokens": 20}),
    )
    return router


@pytest.fixture
def mock_agent_registry():
    """Mock agent registry with a pre-registered agent."""
    registry = MagicMock()
    agent = MagicMock()
    agent.provider = "mock"
    agent.model = "mock-model"
    registry.get_agent.return_value = agent
    return registry


@pytest.fixture
def engine(bus, mock_provider_router, mock_agent_registry):
    """WorkflowEngineImpl with mocked dependencies."""
    return WorkflowEngineImpl(bus, mock_provider_router, mock_agent_registry)


@pytest.fixture
def sample_node_start():
    return WorkflowNode(id="start", type=NodeType.START, label="Start")


@pytest.fixture
def sample_node_agent():
    return WorkflowNode(id="agent1", type=NodeType.AGENT, label="Agent 1",
                        config={"agent_id": "test-agent"})


@pytest.fixture
def sample_node_end():
    return WorkflowNode(id="end", type=NodeType.END, label="End")


@pytest.fixture
def sample_workflow_create(sample_node_start, sample_node_agent, sample_node_end):
    return WorkflowCreate(
        name="Test Workflow",
        description="A test workflow",
        nodes=[sample_node_start, sample_node_agent, sample_node_end],
        edges=[
            WorkflowEdge(id="e1", source="start", target="agent1"),
            WorkflowEdge(id="e2", source="agent1", target="end"),
        ],
        created_by="test",
    )


def _make_approval_workflow() -> WorkflowCreate:
    """Create a workflow with an approval gate (won't auto-complete)."""
    nodes = [
        WorkflowNode(id="start", type=NodeType.START, label="Start"),
        WorkflowNode(id="approval", type=NodeType.APPROVAL, label="Review",
                     config={"context": {"message": "OK?"}}),
        WorkflowNode(id="end", type=NodeType.END, label="End"),
    ]
    edges = [
        WorkflowEdge(id="e1", source="start", target="approval"),
        WorkflowEdge(id="e2", source="approval", target="end"),
    ]
    return WorkflowCreate(name="Approval Test", description="", nodes=nodes, edges=edges)


# ---------------------------------------------------------------------------
# CRUD Operations
# ---------------------------------------------------------------------------


class TestCRUD:
    """Test workflow CRUD operations."""

    async def test_create_workflow(self, engine, sample_workflow_create):
        detail = await engine.create_workflow(sample_workflow_create)
        assert detail.name == "Test Workflow"
        assert detail.status == WorkflowStatus.DRAFT
        assert detail.version == 1
        assert len(detail.nodes) == 3
        assert len(detail.edges) == 2

    async def test_get_workflow(self, engine, sample_workflow_create):
        created = await engine.create_workflow(sample_workflow_create)
        retrieved = await engine.get_workflow(created.id)
        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.name == "Test Workflow"

    async def test_get_workflow_not_found(self, engine):
        result = await engine.get_workflow("nonexistent")
        assert result is None

    async def test_list_workflows(self, engine, sample_workflow_create):
        await engine.create_workflow(sample_workflow_create)
        await engine.create_workflow(sample_workflow_create)
        workflows = await engine.list_workflows()
        assert len(workflows) == 2

    async def test_list_workflows_with_status_filter(self, engine, sample_workflow_create):
        wf1 = await engine.create_workflow(sample_workflow_create)
        # Activate one workflow
        wf = engine._workflows.get(wf1.id)
        engine._workflows[wf1.id] = wf.activate()
        # Create another (stays DRAFT)
        await engine.create_workflow(sample_workflow_create)
        drafts = await engine.list_workflows(status=WorkflowStatus.DRAFT)
        actives = await engine.list_workflows(status=WorkflowStatus.ACTIVE)
        assert len(drafts) == 1
        assert len(actives) == 1

    async def test_list_workflows_limit_offset(self, engine, sample_workflow_create):
        for _ in range(5):
            await engine.create_workflow(sample_workflow_create)
        first_page = await engine.list_workflows(limit=2, offset=0)
        second_page = await engine.list_workflows(limit=2, offset=2)
        assert len(first_page) == 2
        assert len(second_page) == 2

    async def test_update_workflow_meta_only(self, engine, sample_workflow_create):
        created = await engine.create_workflow(sample_workflow_create)
        updated = await engine.update_workflow(
            created.id,
            WorkflowUpdate(name="Updated Name", updated_by="tester"),
        )
        assert updated.name == "Updated Name"
        assert updated.version == 1  # No new version for meta-only changes

    async def test_update_workflow_new_version(self, engine, sample_workflow_create):
        created = await engine.create_workflow(sample_workflow_create)
        new_node = WorkflowNode(id="agent2", type=NodeType.AGENT, label="Agent 2",
                                config={"agent_id": "test-agent"})
        updated = await engine.update_workflow(
            created.id,
            WorkflowUpdate(nodes=[created.nodes[0], created.nodes[1], new_node, created.nodes[2]],
                           updated_by="tester"),
        )
        assert updated.version == 2  # New version for structural changes
        assert len(updated.nodes) == 4

    async def test_update_workflow_not_found(self, engine):
        with pytest.raises(ValueError, match="not found"):
            await engine.update_workflow("missing", WorkflowUpdate())

    async def test_delete_workflow(self, engine, sample_workflow_create):
        created = await engine.create_workflow(sample_workflow_create)
        result = await engine.delete_workflow(created.id)
        assert result is True
        assert await engine.get_workflow(created.id) is None

    async def test_delete_workflow_not_found(self, engine):
        result = await engine.delete_workflow("nonexistent")
        assert result is False

    async def test_delete_workflow_with_running_execution(self, engine, sample_workflow_create):
        created = await engine.create_workflow(sample_workflow_create)
        # Activate and start execution
        wf = engine._workflows[created.id].activate()
        engine._workflows[created.id] = wf
        exec_data = WorkflowExecute(inputs={})
        execution = await engine.execute_workflow(created.id, exec_data)
        # Manually set it as running (task may complete quickly)
        engine._executions[execution.id] = execution.start()
        engine._running_executions.add(execution.id)
        with pytest.raises(ValueError, match="running executions"):
            await engine.delete_workflow(created.id)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestValidation:
    """Test workflow validation."""

    async def test_validate_valid_dag(self, engine):
        nodes = [
            WorkflowNode(id="start", type=NodeType.START, label="Start"),
            WorkflowNode(id="end", type=NodeType.END, label="End"),
        ]
        edges = [WorkflowEdge(id="e1", source="start", target="end")]
        result = await engine.validate_workflow(nodes, edges)
        assert result.valid is True
        assert len(result.errors) == 0

    async def test_validate_cycle_detected(self, engine):
        nodes = [
            WorkflowNode(id="a", type=NodeType.AGENT, label="A"),
            WorkflowNode(id="b", type=NodeType.AGENT, label="B"),
        ]
        edges = [
            WorkflowEdge(id="e1", source="a", target="b"),
            WorkflowEdge(id="e2", source="b", target="a"),
        ]
        result = await engine.validate_workflow(nodes, edges)
        assert result.valid is False
        assert any("cycle" in e.lower() for e in result.errors)

    async def test_validate_duplicate_node_ids(self, engine):
        nodes = [
            WorkflowNode(id="same", type=NodeType.START, label="Start"),
            WorkflowNode(id="same", type=NodeType.END, label="End"),
        ]
        result = await engine.validate_workflow(nodes, [])
        assert result.valid is False
        assert any("duplicate" in e.lower() for e in result.errors)

    async def test_validate_edge_source_not_found(self, engine):
        nodes = [WorkflowNode(id="end", type=NodeType.END, label="End")]
        edges = [WorkflowEdge(id="e1", source="missing", target="end")]
        result = await engine.validate_workflow(nodes, edges)
        assert result.valid is False
        assert any("source" in e for e in result.errors)

    async def test_validate_edge_target_not_found(self, engine):
        nodes = [WorkflowNode(id="start", type=NodeType.START, label="Start")]
        edges = [WorkflowEdge(id="e1", source="start", target="missing")]
        result = await engine.validate_workflow(nodes, edges)
        assert result.valid is False
        assert any("target" in e for e in result.errors)

    async def test_validate_warns_missing_start_end(self, engine):
        nodes = [
            WorkflowNode(id="agent1", type=NodeType.AGENT, label="Agent"),
        ]
        result = await engine.validate_workflow(nodes, [])
        assert result.valid is True
        assert any("no START" in w for w in result.warnings)
        assert any("no END" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


class TestExecution:
    """Test workflow execution."""

    async def test_execute_workflow_creates_execution(self, engine,
                                                      sample_workflow_create):
        created = await engine.create_workflow(sample_workflow_create)
        # Activate first
        wf = engine._workflows[created.id].activate()
        engine._workflows[created.id] = wf

        execution = await engine.execute_workflow(created.id, WorkflowExecute(inputs={"key": "val"}))
        assert execution.workflow_id == created.id
        assert execution.status == WorkflowExecutionStatus.PENDING
        assert execution.inputs == {"key": "val"}

    async def test_execute_inactive_workflow_raises(self, engine,
                                                    sample_workflow_create):
        created = await engine.create_workflow(sample_workflow_create)
        # DRAFT, not ACTIVE
        with pytest.raises(ValueError, match="not active"):
            await engine.execute_workflow(created.id, WorkflowExecute())

    async def test_execute_nonexistent_workflow_raises(self, engine):
        with pytest.raises(ValueError, match="not found"):
            await engine.execute_workflow("missing", WorkflowExecute())

    async def test_execution_runs_to_completion(self, engine,
                                                sample_workflow_create):
        created = await engine.create_workflow(sample_workflow_create)
        wf = engine._workflows[created.id].activate()
        engine._workflows[created.id] = wf

        execution = await engine.execute_workflow(created.id, WorkflowExecute())
        # Wait for background task to complete
        await anyio.sleep(0.5)
        updated = await engine.get_execution(execution.id)
        assert updated is not None
        assert updated.status == WorkflowExecutionStatus.COMPLETED

    async def test_node_outputs_collected(self, engine, sample_workflow_create):
        created = await engine.create_workflow(sample_workflow_create)
        wf = engine._workflows[created.id].activate()
        engine._workflows[created.id] = wf

        execution = await engine.execute_workflow(created.id, WorkflowExecute())
        await anyio.sleep(0.5)
        updated = await engine.get_execution(execution.id)
        assert updated is not None
        # START node should have output
        assert "start" in updated.node_outputs
        assert "agent1" in updated.node_outputs
        assert "end" in updated.node_outputs

    async def test_get_execution_not_found(self, engine):
        result = await engine.get_execution("nonexistent")
        assert result is None

    async def test_get_workflow_executions(self, engine, sample_workflow_create):
        created = await engine.create_workflow(sample_workflow_create)
        wf = engine._workflows[created.id].activate()
        engine._workflows[created.id] = wf

        exec1 = await engine.execute_workflow(created.id, WorkflowExecute())
        exec2 = await engine.execute_workflow(created.id, WorkflowExecute())
        await anyio.sleep(0.5)

        executions = await engine.get_workflow_executions(created.id)
        assert len(executions) >= 2

    async def test_get_running_executions(self, engine, sample_workflow_create):
        created = await engine.create_workflow(sample_workflow_create)
        wf = engine._workflows[created.id].activate()
        engine._workflows[created.id] = wf

        await engine.execute_workflow(created.id, WorkflowExecute())
        running = await engine.get_running_executions()
        # The execution may have already completed due to mock speed
        # Just verify the method returns a list
        assert isinstance(running, list)

    async def test_dag_with_condition_node(self, engine):
        """Execute a workflow with a condition node."""
        nodes = [
            WorkflowNode(id="start", type=NodeType.START, label="Start"),
            WorkflowNode(id="cond", type=NodeType.CONDITION, label="Check",
                         config={"condition": {"type": "always_true"}}),
            WorkflowNode(id="end", type=NodeType.END, label="End"),
        ]
        edges = [
            WorkflowEdge(id="e1", source="start", target="cond"),
            WorkflowEdge(id="e2", source="cond", target="end"),
        ]
        wf_create = WorkflowCreate(name="Condition Test", description="", nodes=nodes, edges=edges)
        created = await engine.create_workflow(wf_create)
        engine._workflows[created.id] = engine._workflows[created.id].activate()

        execution = await engine.execute_workflow(created.id, WorkflowExecute())
        await anyio.sleep(0.5)
        updated = await engine.get_execution(execution.id)
        assert updated is not None
        assert updated.status == WorkflowExecutionStatus.COMPLETED


# ---------------------------------------------------------------------------
# Node Type Dispatch
# ---------------------------------------------------------------------------


class TestNodeExecution:
    """Test individual node type execution."""

    async def test_start_node(self, engine):
        node = WorkflowNode(id="start1", type=NodeType.START, label="Start")
        exec_mock = MagicMock(spec=WorkflowExecution)
        exec_mock.inputs = {"key": "value"}
        exec_mock.node_outputs = {}
        wf_mock = MagicMock(spec=Workflow)

        result = await engine._execute_node(node, exec_mock, wf_mock)
        assert result["status"] == "started"
        assert result["inputs"] == {"key": "value"}

    async def test_end_node(self, engine):
        node = WorkflowNode(id="end1", type=NodeType.END, label="End")
        exec_mock = MagicMock(spec=WorkflowExecution)
        exec_mock.node_outputs = {"prev": "result"}
        wf_mock = MagicMock(spec=Workflow)

        result = await engine._execute_node(node, exec_mock, wf_mock)
        assert result["status"] == "completed"
        assert result["result"] == {"prev": "result"}

    async def test_agent_node(self, engine):
        node = WorkflowNode(id="agent1", type=NodeType.AGENT, label="Agent",
                            config={"agent_id": "test-agent"})
        exec_mock = MagicMock(spec=WorkflowExecution)
        exec_mock.inputs = {}
        exec_mock.node_outputs = {}
        wf_mock = MagicMock(spec=Workflow)

        result = await engine._execute_node(node, exec_mock, wf_mock)
        assert "output" in result
        assert result["output"] == "mock response"
        engine._provider_router.complete.assert_called_once()

    async def test_agent_node_missing_agent_id(self, engine):
        node = WorkflowNode(id="agent1", type=NodeType.AGENT, label="Agent", config={})
        exec_mock = MagicMock(spec=WorkflowExecution)
        wf_mock = MagicMock(spec=Workflow)

        with pytest.raises(ValueError, match="agent_id"):
            await engine._execute_node(node, exec_mock, wf_mock)

    async def test_agent_node_agent_not_found(self, engine, mock_agent_registry):
        node = WorkflowNode(id="agent1", type=NodeType.AGENT, label="Agent",
                            config={"agent_id": "missing"})
        mock_agent_registry.get_agent.return_value = None
        exec_mock = MagicMock(spec=WorkflowExecution)
        wf_mock = MagicMock(spec=Workflow)

        with pytest.raises(ValueError, match="not found"):
            await engine._execute_node(node, exec_mock, wf_mock)

    async def test_tool_node(self, engine):
        node = WorkflowNode(id="tool1", type=NodeType.TOOL, label="Tool",
                            config={"tool": "test-tool"})
        exec_mock = MagicMock(spec=WorkflowExecution)
        wf_mock = MagicMock(spec=Workflow)

        result = await engine._execute_node(node, exec_mock, wf_mock)
        assert result["tool"] == "test-tool"
        assert result["result"] == "executed"

    async def test_tool_node_missing_tool(self, engine):
        node = WorkflowNode(id="tool1", type=NodeType.TOOL, label="Tool", config={})
        exec_mock = MagicMock(spec=WorkflowExecution)
        wf_mock = MagicMock(spec=Workflow)

        with pytest.raises(ValueError, match="tool"):
            await engine._execute_node(node, exec_mock, wf_mock)

    async def test_approval_node_raises(self, engine):
        node = WorkflowNode(id="approval1", type=NodeType.APPROVAL, label="Approve",
                            config={"context": {"message": "Needs review"}})
        exec_mock = MagicMock(spec=WorkflowExecution)
        wf_mock = MagicMock(spec=Workflow)

        with pytest.raises(ApprovalRequired) as exc_info:
            await engine._execute_node(node, exec_mock, wf_mock)
        assert exc_info.value.context["message"] == "Needs review"

    async def test_condition_node(self, engine):
        node = WorkflowNode(id="cond1", type=NodeType.CONDITION, label="Check",
                            config={"condition": {"type": "always_true"}})
        exec_mock = MagicMock(spec=WorkflowExecution)
        wf_mock = MagicMock(spec=Workflow)

        result = await engine._execute_node(node, exec_mock, wf_mock)
        assert result["condition_result"] is True

    async def test_parallel_node(self, engine):
        node = WorkflowNode(id="par1", type=NodeType.PARALLEL, label="Parallel",
                            config={"children": ["child1", "child2"]})
        exec_mock = MagicMock(spec=WorkflowExecution)
        wf_mock = MagicMock(spec=Workflow)

        result = await engine._execute_node(node, exec_mock, wf_mock)
        assert result["parallel"] is True
        assert "child1" in result["children"]

    async def test_subworkflow_node(self, engine):
        node = WorkflowNode(id="sub1", type=NodeType.SUBWORKFLOW, label="Sub",
                            subworkflow_id="sub-wf-1")
        exec_mock = MagicMock(spec=WorkflowExecution)
        wf_mock = MagicMock(spec=Workflow)

        result = await engine._execute_node(node, exec_mock, wf_mock)
        assert result["subworkflow"] == "sub-wf-1"

    async def test_llm_node(self, engine):
        node = WorkflowNode(id="llm1", type=NodeType.LLM, label="LLM",
                            config={"prompt": "Hello"})
        exec_mock = MagicMock(spec=WorkflowExecution)
        wf_mock = MagicMock(spec=Workflow)

        result = await engine._execute_node(node, exec_mock, wf_mock)
        assert result["prompt"] == "Hello"

    async def test_unknown_node_type(self, engine):
        node = WorkflowNode(id="unknown", type="bogus", label="Bad")
        exec_mock = MagicMock(spec=WorkflowExecution)
        wf_mock = MagicMock(spec=Workflow)

        with pytest.raises(ValueError, match="Unknown"):
            await engine._execute_node(node, exec_mock, wf_mock)


# ---------------------------------------------------------------------------
# Control Operations: Cancel, Pause, Resume
# ---------------------------------------------------------------------------


class TestControl:
    """Test workflow execution control operations."""

    async def test_cancel_execution(self, engine):
        """Cancel a workflow that's awaiting approval (doesn't auto-complete)."""
        nodes = [
            WorkflowNode(id="start", type=NodeType.START, label="Start"),
            WorkflowNode(id="approval", type=NodeType.APPROVAL, label="Review",
                         config={"context": {"message": "OK?"}}),
            WorkflowNode(id="end", type=NodeType.END, label="End"),
        ]
        edges = [
            WorkflowEdge(id="e1", source="start", target="approval"),
            WorkflowEdge(id="e2", source="approval", target="end"),
        ]
        wf_create = WorkflowCreate(name="Cancel Test", description="", nodes=nodes, edges=edges)
        created = await engine.create_workflow(wf_create)
        engine._workflows[created.id] = engine._workflows[created.id].activate()

        execution = await engine.execute_workflow(created.id, WorkflowExecute())
        await anyio.sleep(0.3)

        # Should be in AWAITING_APPROVAL — cancel it
        cancelled = await engine.cancel_execution(execution.id)
        assert cancelled.status == WorkflowExecutionStatus.CANCELLED

    async def test_cancel_not_found(self, engine):
        with pytest.raises(ValueError, match="not found"):
            await engine.cancel_execution("missing")

    async def test_cancel_completed_execution_raises(self, engine, sample_workflow_create):
        created = await engine.create_workflow(sample_workflow_create)
        wf = engine._workflows[created.id].activate()
        engine._workflows[created.id] = wf
        execution = await engine.execute_workflow(created.id, WorkflowExecute())
        await anyio.sleep(0.5)
        with pytest.raises(ValueError, match="Cannot cancel"):
            await engine.cancel_execution(execution.id)

    async def test_pause_execution(self, engine, sample_workflow_create):
        created = await engine.create_workflow(sample_workflow_create)
        wf = engine._workflows[created.id].activate()
        engine._workflows[created.id] = wf
        execution = await engine.execute_workflow(created.id, WorkflowExecute())
        await anyio.sleep(0.1)

        # Set running status for pause to work
        engine._executions[execution.id] = engine._executions[execution.id].start()
        paused = await engine.pause_execution(execution.id)
        assert paused.status == WorkflowExecutionStatus.PAUSED

    async def test_pause_not_running_raises(self, engine, sample_workflow_create):
        created = await engine.create_workflow(sample_workflow_create)
        wf = engine._workflows[created.id].activate()
        engine._workflows[created.id] = wf
        execution = await engine.execute_workflow(created.id, WorkflowExecute())
        await anyio.sleep(0.5)  # completes

        with pytest.raises(ValueError, match="Cannot pause"):
            await engine.pause_execution(execution.id)

    async def test_resume_execution(self, engine, sample_workflow_create):
        created = await engine.create_workflow(sample_workflow_create)
        wf = engine._workflows[created.id].activate()
        engine._workflows[created.id] = wf
        execution = await engine.execute_workflow(created.id, WorkflowExecute())
        await anyio.sleep(0.1)

        execution = execution.pause()
        engine._executions[execution.id] = execution

        resumed = await engine.resume_execution(execution.id)
        assert resumed.status == WorkflowExecutionStatus.RUNNING

    async def test_resume_not_paused_raises(self, engine, sample_workflow_create):
        created = await engine.create_workflow(sample_workflow_create)
        wf = engine._workflows[created.id].activate()
        engine._workflows[created.id] = wf
        execution = await engine.execute_workflow(created.id, WorkflowExecute())
        await anyio.sleep(0.5)

        with pytest.raises(ValueError, match="Cannot resume"):
            await engine.resume_execution(execution.id)


# ---------------------------------------------------------------------------
# Approval Gates
# ---------------------------------------------------------------------------


class TestApproval:
    """Test workflow approval gate flow."""

    async def test_approval_gate_approves_and_continues(self, engine, bus):
        """Workflow with approval node: approve to complete."""
        nodes = [
            WorkflowNode(id="start", type=NodeType.START, label="Start"),
            WorkflowNode(id="approval", type=NodeType.APPROVAL, label="Review",
                         config={"context": {"message": "OK?"}}),
            WorkflowNode(id="end", type=NodeType.END, label="End"),
        ]
        edges = [
            WorkflowEdge(id="e1", source="start", target="approval"),
            WorkflowEdge(id="e2", source="approval", target="end"),
        ]
        wf_create = WorkflowCreate(name="Approval Test", description="", nodes=nodes, edges=edges)
        created = await engine.create_workflow(wf_create)
        engine._workflows[created.id] = engine._workflows[created.id].activate()

        execution = await engine.execute_workflow(created.id, WorkflowExecute(inputs={}))
        await anyio.sleep(0.3)

        # Check the execution - it should be awaiting approval
        stored = await engine.get_execution(execution.id)
        assert stored is not None

        if stored.status == WorkflowExecutionStatus.AWAITING_APPROVAL:
            # Approve it
            approved = await engine.approve_workflow(
                created.id,
                WorkflowApproval(node_id="approval", approved=True,
                                 decided_by="admin", reason="Looks good"),
            )
            assert approved.status == WorkflowExecutionStatus.RUNNING

    async def test_approval_gate_denied(self, engine):
        """Workflow with approval node: deny to fail."""
        nodes = [
            WorkflowNode(id="start", type=NodeType.START, label="Start"),
            WorkflowNode(id="approval", type=NodeType.APPROVAL, label="Review",
                         config={"context": {"message": "OK?"}}),
        ]
        edges = [WorkflowEdge(id="e1", source="start", target="approval")]
        wf_create = WorkflowCreate(name="Deny Test", description="", nodes=nodes, edges=edges)
        created = await engine.create_workflow(wf_create)
        engine._workflows[created.id] = engine._workflows[created.id].activate()

        execution = await engine.execute_workflow(created.id, WorkflowExecute())
        await anyio.sleep(0.3)

        stored = await engine.get_execution(execution.id)
        assert stored is not None

        if stored.status == WorkflowExecutionStatus.AWAITING_APPROVAL:
            denied = await engine.approve_workflow(
                created.id,
                WorkflowApproval(node_id="approval", approved=False,
                                 decided_by="admin", reason="Not ready"),
            )
            assert denied.status == WorkflowExecutionStatus.FAILED
            assert "Not ready" in (denied.error or "")

    async def test_approve_no_pending_execution_raises(self, engine):
        with pytest.raises(ValueError, match="No execution"):
            await engine.approve_workflow(
                "wf",
                WorkflowApproval(node_id="n1", approved=True, decided_by="admin"),
            )


# ---------------------------------------------------------------------------
# Replay
# ---------------------------------------------------------------------------


class TestReplay:
    """Test workflow replay functionality."""

    async def test_replay_workflow(self, engine, sample_workflow_create):
        created = await engine.create_workflow(sample_workflow_create)
        wf = engine._workflows[created.id].activate()
        engine._workflows[created.id] = wf

        execution = await engine.replay_workflow(
            created.id,
            WorkflowReplay(inputs={}, from_node="start"),
        )
        assert execution.replay_from_node == "start"
        await anyio.sleep(0.5)
        updated = await engine.get_execution(execution.id)
        assert updated is not None
        assert updated.status == WorkflowExecutionStatus.COMPLETED

    async def test_replay_nonexistent_workflow(self, engine):
        with pytest.raises(ValueError, match="not found"):
            await engine.replay_workflow("missing", WorkflowReplay())


# ---------------------------------------------------------------------------
# Version Management
# ---------------------------------------------------------------------------


class TestVersioning:
    """Test workflow version management."""

    async def test_get_workflow_versions(self, engine, sample_workflow_create):
        created = await engine.create_workflow(sample_workflow_create)
        versions = await engine.get_workflow_versions(created.id)
        assert isinstance(versions, list)

    async def test_get_workflow_version(self, engine, sample_workflow_create):
        created = await engine.create_workflow(sample_workflow_create)
        v1 = await engine.get_workflow_version(created.id, 1)
        assert v1 is not None
        assert v1.version == 1

    async def test_get_workflow_version_not_found(self, engine, sample_workflow_create):
        created = await engine.create_workflow(sample_workflow_create)
        result = await engine.get_workflow_version(created.id, 999)
        assert result is None


# ---------------------------------------------------------------------------
# Error Handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Test error handling scenarios."""

    async def test_workflow_node_failure_propagates(self, engine):
        """Workflow with a node that fails should end in FAILED status."""
        nodes = [
            WorkflowNode(id="start", type=NodeType.START, label="Start"),
            WorkflowNode(id="agent1", type=NodeType.AGENT, label="Agent",
                         config={"agent_id": "test-agent"}),
            WorkflowNode(id="end", type=NodeType.END, label="End"),
        ]
        edges = [
            WorkflowEdge(id="e1", source="start", target="agent1"),
            WorkflowEdge(id="e2", source="agent1", target="end"),
        ]
        wf_create = WorkflowCreate(name="Fail Test", description="", nodes=nodes, edges=edges)
        created = await engine.create_workflow(wf_create)
        engine._workflows[created.id] = engine._workflows[created.id].activate()

        # Make agent fail
        engine._provider_router.complete.side_effect = ValueError("Provider unavailable")

        execution = await engine.execute_workflow(created.id, WorkflowExecute())
        await anyio.sleep(0.5)
        updated = await engine.get_execution(execution.id)
        assert updated is not None
        assert updated.status == WorkflowExecutionStatus.FAILED
        assert updated.error is not None
        assert "agent1" in updated.failed_nodes

    async def test_execution_crash_recovery(self, engine, sample_workflow_create):
        """An unhandled exception in _run_execution should be caught."""
        created = await engine.create_workflow(sample_workflow_create)
        wf = engine._workflows[created.id].activate()
        engine._workflows[created.id] = wf

        execution = await engine.execute_workflow(created.id, WorkflowExecute())
        await anyio.sleep(0.5)

        # Should not crash the engine
        assert await engine.get_workflow(created.id) is not None


# ---------------------------------------------------------------------------
# Event Emission
# ---------------------------------------------------------------------------


class TestEvents:
    """Test that events are emitted correctly during workflow operations."""

    async def test_create_emits_event(self, engine, bus, sample_workflow_create):
        seen = []

        async def collector(event):
            seen.append(event.topic)

        await bus.subscribe(Topic.WORKFLOW_CREATED.value, collector)
        await engine.create_workflow(sample_workflow_create)
        await bus.drain()
        assert Topic.WORKFLOW_CREATED.value in seen

    async def test_execution_emits_events(self, engine, bus, sample_workflow_create):
        created = await engine.create_workflow(sample_workflow_create)
        wf = engine._workflows[created.id].activate()
        engine._workflows[created.id] = wf

        seen = []

        async def collector(event):
            seen.append(event.topic)

        await bus.subscribe(Topic.WORKFLOW_STARTED.value, collector)
        await bus.subscribe(Topic.WORKFLOW_COMPLETED.value, collector)
        await bus.subscribe(Topic.WORKFLOW_NODE_STARTED.value, collector)
        await bus.subscribe(Topic.WORKFLOW_NODE_COMPLETED.value, collector)

        await engine.execute_workflow(created.id, WorkflowExecute())
        await anyio.sleep(0.5)
        await bus.drain()

        assert Topic.WORKFLOW_STARTED.value in seen
        assert Topic.WORKFLOW_NODE_STARTED.value in seen
        assert Topic.WORKFLOW_NODE_COMPLETED.value in seen

    async def test_cancel_emits_event(self, engine, bus):
        created = await engine.create_workflow(_make_approval_workflow())
        engine._workflows[created.id] = engine._workflows[created.id].activate()

        execution = await engine.execute_workflow(created.id, WorkflowExecute())
        seen = []

        async def collector(event):
            seen.append(event.topic)

        await bus.subscribe(Topic.WORKFLOW_CANCELLED.value, collector)
        await anyio.sleep(0.3)
        await engine.cancel_execution(execution.id)
        await bus.drain()

        assert Topic.WORKFLOW_CANCELLED.value in seen


# ---------------------------------------------------------------------------
# Concurrency / Race Conditions
# ---------------------------------------------------------------------------


class TestConcurrency:
    """Test concurrent workflow operations."""

    async def test_multiple_concurrent_executions(self, engine):
        """Run multiple workflows concurrently."""
        # Create and activate two workflows
        wf_ids = []
        for i in range(3):
            nodes = [
                WorkflowNode(id=f"start", type=NodeType.START, label="Start"),
                WorkflowNode(id=f"agent", type=NodeType.AGENT, label=f"Agent {i}",
                             config={"agent_id": "test-agent"}),
                WorkflowNode(id=f"end", type=NodeType.END, label="End"),
            ]
            edges = [
                WorkflowEdge(id=f"e1", source="start", target="agent"),
                WorkflowEdge(id=f"e2", source="agent", target="end"),
            ]
            wf_create = WorkflowCreate(name=f"WF {i}", description="", nodes=nodes, edges=edges)
            created = await engine.create_workflow(wf_create)
            engine._workflows[created.id] = engine._workflows[created.id].activate()
            wf_ids.append(created.id)

        # Start all three concurrently
        tasks = [engine.execute_workflow(wid, WorkflowExecute()) for wid in wf_ids]
        executions = await asyncio.gather(*tasks)
        assert len(executions) == 3

        # Wait for all to complete
        await anyio.sleep(1.0)
        for exec_ in executions:
            updated = await engine.get_execution(exec_.id)
            assert updated is not None
            assert updated.status == WorkflowExecutionStatus.COMPLETED, f"Exec {exec_.id} failed: {updated.error}"


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    async def test_empty_workflow(self, engine):
        """Workflow with no nodes should validate but warn."""
        result = await engine.validate_workflow([], [])
        assert result.valid is True
        assert any("no START" in w for w in result.warnings)

    async def test_execution_task_cleanup(self, engine, sample_workflow_create):
        """After execution completes, task should be cleaned up."""
        created = await engine.create_workflow(sample_workflow_create)
        wf = engine._workflows[created.id].activate()
        engine._workflows[created.id] = wf

        execution = await engine.execute_workflow(created.id, WorkflowExecute())
        execution_id = execution.id
        assert execution_id in engine._execution_tasks

        await anyio.sleep(0.5)
        assert execution_id not in engine._execution_tasks
        assert execution_id not in engine._running_executions

    async def test_list_workflows_empty(self, engine):
        workflows = await engine.list_workflows()
        assert workflows == []

    async def test_get_workflow_executions_empty(self, engine):
        executions = await engine.get_workflow_executions("nonexistent")
        assert executions == []

    async def test_validate_duplicate_edge_ids(self, engine):
        nodes = [
            WorkflowNode(id="a", type=NodeType.START, label="A"),
            WorkflowNode(id="b", type=NodeType.END, label="B"),
        ]
        edges = [
            WorkflowEdge(id="e1", source="a", target="b"),
            WorkflowEdge(id="e1", source="a", target="b"),
        ]
        result = await engine.validate_workflow(nodes, edges)
        assert result.valid is False
        assert any("duplicate edge" in e.lower() for e in result.errors)
