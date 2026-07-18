"""
Workflow Domain Models

Domain layer for workflow engine - pure Python, no external dependencies.
Follows hexagonal architecture: domain depends on nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4


def _utcnow() -> datetime:
    return datetime.now(UTC)


class WorkflowStatus(StrEnum):
    """Lifecycle status of a workflow definition."""

    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    ARCHIVED = "archived"


class WorkflowExecutionStatus(StrEnum):
    """Runtime status of a workflow execution."""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class NodeType(StrEnum):
    """Built-in workflow node types."""

    AGENT = "agent"
    TOOL = "tool"
    LLM = "llm"
    CONDITION = "condition"
    PARALLEL = "parallel"
    APPROVAL = "approval"
    SUBWORKFLOW = "subworkflow"
    START = "start"
    END = "end"


@dataclass(frozen=True, slots=True)
class WorkflowNode:
    """
    A node in a workflow DAG.

    Immutable after creation - use replace() to create modified copies.
    """

    id: str
    type: NodeType
    label: str
    config: dict[str, Any] = field(default_factory=dict)
    position: dict[str, float] = field(default_factory=lambda: {"x": 0.0, "y": 0.0})
    # Optional: for subworkflow nodes
    subworkflow_id: str | None = None

    def with_position(self, x: float, y: float) -> WorkflowNode:
        return WorkflowNode(
            id=self.id,
            type=self.type,
            label=self.label,
            config=self.config,
            position={"x": x, "y": y},
            subworkflow_id=self.subworkflow_id,
        )

    def with_config(self, config: dict[str, Any]) -> WorkflowNode:
        return WorkflowNode(
            id=self.id,
            type=self.type,
            label=self.label,
            config=config,
            position=self.position,
            subworkflow_id=self.subworkflow_id,
        )


@dataclass(frozen=True, slots=True)
class WorkflowEdge:
    """
    A directed edge connecting two nodes in a workflow DAG.

    Immutable after creation.
    """

    id: str
    source: str  # source node id
    target: str  # target node id
    source_handle: str | None = None
    target_handle: str | None = None
    # Optional condition for conditional edges
    condition: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class WorkflowTemplate:
    """
    A reusable workflow template with parameterization support.
    """

    id: str
    name: str
    description: str
    nodes: tuple[WorkflowNode, ...]
    edges: tuple[WorkflowEdge, ...]
    parameters: dict[str, Any] = field(default_factory=dict)
    version: int = 1
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)
    created_by: str = "system"

    @classmethod
    def create(
        cls,
        name: str,
        description: str,
        nodes: list[WorkflowNode],
        edges: list[WorkflowEdge],
        parameters: dict[str, Any] | None = None,
        created_by: str = "system",
    ) -> WorkflowTemplate:
        return cls(
            id=str(uuid4()),
            name=name,
            description=description,
            nodes=tuple(nodes),
            edges=tuple(edges),
            parameters=parameters or {},
            version=1,
            created_by=created_by,
        )


@dataclass(frozen=True, slots=True)
class Workflow:
    """
    Workflow definition - the static DAG structure.

    Versioned immutable entity. New versions create new Workflow instances.
    """

    id: str
    name: str
    description: str
    nodes: tuple[WorkflowNode, ...]
    edges: tuple[WorkflowEdge, ...]
    version: int
    status: WorkflowStatus
    template_id: str | None = None
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)
    created_by: str = "system"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "nodes": [
                {
                    "id": n.id,
                    "type": n.type.value,
                    "label": n.label,
                    "config": n.config,
                    "position": n.position,
                    "subworkflow_id": n.subworkflow_id,
                }
                for n in self.nodes
            ],
            "edges": [
                {
                    "id": e.id,
                    "source": e.source,
                    "target": e.target,
                    "source_handle": e.source_handle,
                    "target_handle": e.target_handle,
                    "condition": e.condition,
                }
                for e in self.edges
            ],
            "version": self.version,
            "status": self.status.value,
            "template_id": self.template_id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "created_by": self.created_by,
        }

    @classmethod
    def create(
        cls,
        name: str,
        description: str,
        nodes: list[WorkflowNode],
        edges: list[WorkflowEdge],
        template_id: str | None = None,
        created_by: str = "system",
    ) -> Workflow:
        return cls(
            id=str(uuid4()),
            name=name,
            description=description,
            nodes=tuple(nodes),
            edges=tuple(edges),
            version=1,
            status=WorkflowStatus.DRAFT,
            template_id=template_id,
            created_by=created_by,
        )

    def new_version(
        self,
        name: str | None = None,
        description: str | None = None,
        nodes: list[WorkflowNode] | None = None,
        edges: list[WorkflowEdge] | None = None,
        created_by: str = "system",
    ) -> Workflow:
        """Create a new version of this workflow."""
        return Workflow(
            id=self.id,
            name=name or self.name,
            description=description or self.description,
            nodes=tuple(nodes) if nodes is not None else self.nodes,
            edges=tuple(edges) if edges is not None else self.edges,
            version=self.version + 1,
            status=WorkflowStatus.DRAFT,
            template_id=self.template_id,
            created_at=self.created_at,
            updated_at=_utcnow(),
            created_by=created_by,
        )

    def activate(self, created_by: str = "system") -> Workflow:
        return Workflow(
            id=self.id,
            name=self.name,
            description=self.description,
            nodes=self.nodes,
            edges=self.edges,
            version=self.version,
            status=WorkflowStatus.ACTIVE,
            template_id=self.template_id,
            created_at=self.created_at,
            updated_at=_utcnow(),
            created_by=created_by,
        )

    def archive(self, created_by: str = "system") -> Workflow:
        return Workflow(
            id=self.id,
            name=self.name,
            description=self.description,
            nodes=self.nodes,
            edges=self.edges,
            version=self.version,
            status=WorkflowStatus.ARCHIVED,
            template_id=self.template_id,
            created_at=self.created_at,
            updated_at=_utcnow(),
            created_by=created_by,
        )


@dataclass(frozen=True, slots=True)
class WorkflowExecution:
    """
    Runtime instance of a workflow execution.

    Tracks the dynamic state as the workflow runs through nodes.
    """

    id: str
    workflow_id: str
    workflow_version: int
    status: WorkflowExecutionStatus
    inputs: dict[str, Any] = field(default_factory=dict)
    current_node: str | None = None
    completed_nodes: frozenset[str] = field(default_factory=frozenset)
    failed_nodes: frozenset[str] = field(default_factory=frozenset)
    node_outputs: dict[str, Any] = field(default_factory=dict)
    node_errors: dict[str, str] = field(default_factory=dict)
    # For approval gates
    pending_approval: str | None = None  # node_id awaiting approval
    approval_history: dict[str, dict[str, Any]] = field(default_factory=dict)
    started_at: datetime = field(default_factory=_utcnow)
    completed_at: datetime | None = None
    error: str | None = None
    # For replay support
    parent_execution_id: str | None = None
    replay_from_node: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "workflow_id": self.workflow_id,
            "workflow_version": self.workflow_version,
            "status": self.status.value,
            "inputs": self.inputs,
            "current_node": self.current_node,
            "completed_nodes": list(self.completed_nodes),
            "failed_nodes": list(self.failed_nodes),
            "node_outputs": self.node_outputs,
            "node_errors": self.node_errors,
            "pending_approval": self.pending_approval,
            "approval_history": self.approval_history,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
            "parent_execution_id": self.parent_execution_id,
            "replay_from_node": self.replay_from_node,
        }

    @classmethod
    def create(
        cls,
        workflow_id: str,
        workflow_version: int,
        inputs: dict[str, Any],
        parent_execution_id: str | None = None,
        replay_from_node: str | None = None,
    ) -> WorkflowExecution:
        return cls(
            id=str(uuid4()),
            workflow_id=workflow_id,
            workflow_version=workflow_version,
            status=WorkflowExecutionStatus.PENDING,
            inputs=inputs,
            parent_execution_id=parent_execution_id,
            replay_from_node=replay_from_node,
        )

    def start(self) -> WorkflowExecution:
        return WorkflowExecution(
            id=self.id,
            workflow_id=self.workflow_id,
            workflow_version=self.workflow_version,
            status=WorkflowExecutionStatus.RUNNING,
            inputs=self.inputs,
            current_node=self.current_node,
            completed_nodes=self.completed_nodes,
            failed_nodes=self.failed_nodes,
            node_outputs=self.node_outputs,
            node_errors=self.node_errors,
            pending_approval=self.pending_approval,
            approval_history=self.approval_history,
            started_at=self.started_at,
            completed_at=None,
            error=None,
            parent_execution_id=self.parent_execution_id,
            replay_from_node=self.replay_from_node,
        )

    def pause(self) -> WorkflowExecution:
        return WorkflowExecution(
            id=self.id,
            workflow_id=self.workflow_id,
            workflow_version=self.workflow_version,
            status=WorkflowExecutionStatus.PAUSED,
            inputs=self.inputs,
            current_node=self.current_node,
            completed_nodes=self.completed_nodes,
            failed_nodes=self.failed_nodes,
            node_outputs=self.node_outputs,
            node_errors=self.node_errors,
            pending_approval=self.pending_approval,
            approval_history=self.approval_history,
            started_at=self.started_at,
            completed_at=None,
            error=self.error,
            parent_execution_id=self.parent_execution_id,
            replay_from_node=self.replay_from_node,
        )

    def complete(self, result: Any | None = None) -> WorkflowExecution:
        return WorkflowExecution(
            id=self.id,
            workflow_id=self.workflow_id,
            workflow_version=self.workflow_version,
            status=WorkflowExecutionStatus.COMPLETED,
            inputs=self.inputs,
            current_node=None,
            completed_nodes=self.completed_nodes,
            failed_nodes=self.failed_nodes,
            node_outputs=self.node_outputs,
            node_errors=self.node_errors,
            pending_approval=None,
            approval_history=self.approval_history,
            started_at=self.started_at,
            completed_at=_utcnow(),
            error=None,
            parent_execution_id=self.parent_execution_id,
            replay_from_node=self.replay_from_node,
        )

    def fail(self, error: str, failed_node: str | None = None) -> WorkflowExecution:
        failed = self.failed_nodes
        if failed_node:
            failed = failed | {failed_node}
        return WorkflowExecution(
            id=self.id,
            workflow_id=self.workflow_id,
            workflow_version=self.workflow_version,
            status=WorkflowExecutionStatus.FAILED,
            inputs=self.inputs,
            current_node=self.current_node,
            completed_nodes=self.completed_nodes,
            failed_nodes=failed,
            node_outputs=self.node_outputs,
            node_errors={**self.node_errors, failed_node: error}
            if failed_node
            else self.node_errors,
            pending_approval=None,
            approval_history=self.approval_history,
            started_at=self.started_at,
            completed_at=_utcnow(),
            error=error,
            parent_execution_id=self.parent_execution_id,
            replay_from_node=self.replay_from_node,
        )

    def cancel(self) -> WorkflowExecution:
        return WorkflowExecution(
            id=self.id,
            workflow_id=self.workflow_id,
            workflow_version=self.workflow_version,
            status=WorkflowExecutionStatus.CANCELLED,
            inputs=self.inputs,
            current_node=None,
            completed_nodes=self.completed_nodes,
            failed_nodes=self.failed_nodes,
            node_outputs=self.node_outputs,
            node_errors=self.node_errors,
            pending_approval=None,
            approval_history=self.approval_history,
            started_at=self.started_at,
            completed_at=_utcnow(),
            error="Cancelled by user",
            parent_execution_id=self.parent_execution_id,
            replay_from_node=self.replay_from_node,
        )

    def set_current_node(self, node_id: str) -> WorkflowExecution:
        return WorkflowExecution(
            id=self.id,
            workflow_id=self.workflow_id,
            workflow_version=self.workflow_version,
            status=self.status,
            inputs=self.inputs,
            current_node=node_id,
            completed_nodes=self.completed_nodes,
            failed_nodes=self.failed_nodes,
            node_outputs=self.node_outputs,
            node_errors=self.node_errors,
            pending_approval=self.pending_approval,
            approval_history=self.approval_history,
            started_at=self.started_at,
            completed_at=self.completed_at,
            error=self.error,
            parent_execution_id=self.parent_execution_id,
            replay_from_node=self.replay_from_node,
        )

    def complete_node(self, node_id: str, output: Any) -> WorkflowExecution:
        return WorkflowExecution(
            id=self.id,
            workflow_id=self.workflow_id,
            workflow_version=self.workflow_version,
            status=self.status,
            inputs=self.inputs,
            current_node=self.current_node,
            completed_nodes=self.completed_nodes | {node_id},
            failed_nodes=self.failed_nodes,
            node_outputs={**self.node_outputs, node_id: output},
            node_errors=self.node_errors,
            pending_approval=self.pending_approval,
            approval_history=self.approval_history,
            started_at=self.started_at,
            completed_at=self.completed_at,
            error=self.error,
            parent_execution_id=self.parent_execution_id,
            replay_from_node=self.replay_from_node,
        )

    def request_approval(self, node_id: str, context: dict[str, Any]) -> WorkflowExecution:
        return WorkflowExecution(
            id=self.id,
            workflow_id=self.workflow_id,
            workflow_version=self.workflow_version,
            status=WorkflowExecutionStatus.AWAITING_APPROVAL,
            inputs=self.inputs,
            current_node=node_id,
            completed_nodes=self.completed_nodes,
            failed_nodes=self.failed_nodes,
            node_outputs=self.node_outputs,
            node_errors=self.node_errors,
            pending_approval=node_id,
            approval_history={
                **self.approval_history,
                node_id: {"requested_at": _utcnow().isoformat(), "context": context},
            },
            started_at=self.started_at,
            completed_at=None,
            error=self.error,
            parent_execution_id=self.parent_execution_id,
            replay_from_node=self.replay_from_node,
        )

    def decide_approval(
        self, node_id: str, approved: bool, decided_by: str, reason: str | None = None
    ) -> WorkflowExecution:
        new_history = {
            **self.approval_history,
            node_id: {
                **self.approval_history.get(node_id, {}),
                "decided_at": _utcnow().isoformat(),
                "decided_by": decided_by,
                "approved": approved,
                "reason": reason,
            },
        }
        return WorkflowExecution(
            id=self.id,
            workflow_id=self.workflow_id,
            workflow_version=self.workflow_version,
            status=WorkflowExecutionStatus.RUNNING if approved else WorkflowExecutionStatus.FAILED,
            inputs=self.inputs,
            current_node=node_id if approved else None,
            completed_nodes=self.completed_nodes | ({node_id} if approved else set()),
            failed_nodes=self.failed_nodes | (set() if approved else {node_id}),
            node_outputs=self.node_outputs,
            node_errors=self.node_errors
            if approved
            else {**self.node_errors, node_id: reason or "Approval denied"},
            pending_approval=None,
            approval_history=new_history,
            started_at=self.started_at,
            completed_at=None if approved else _utcnow(),
            error=None if approved else (reason or "Approval denied"),
            parent_execution_id=self.parent_execution_id,
            replay_from_node=self.replay_from_node,
        )


@dataclass(frozen=True, slots=True)
class WorkflowVersion:
    """Historical version record for a workflow."""

    version: int
    workflow_id: str
    name: str
    description: str
    nodes: tuple[WorkflowNode, ...]
    edges: tuple[WorkflowEdge, ...]
    created_at: datetime
    created_by: str
    changelog: str
