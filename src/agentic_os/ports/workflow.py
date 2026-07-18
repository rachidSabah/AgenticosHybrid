"""
Workflow Engine Port

Defines the interface for workflow engine operations.
Domain logic depends on this interface, not implementations.
"""

from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass, field
from typing import Any, Protocol

from agentic_os.domain.workflow import (
    Workflow,
    WorkflowEdge,
    WorkflowExecution,
    WorkflowExecutionStatus,
    WorkflowNode,
    WorkflowStatus,
    WorkflowVersion,
)


@dataclass(frozen=True, slots=True)
class WorkflowCreate:
    """Input for creating a new workflow."""

    name: str
    description: str
    nodes: list[WorkflowNode]
    edges: list[WorkflowEdge]
    template_id: str | None = None
    created_by: str = "system"


@dataclass(frozen=True, slots=True)
class WorkflowUpdate:
    """Input for updating a workflow."""

    name: str | None = None
    description: str | None = None
    nodes: list[WorkflowNode] | None = None
    edges: list[WorkflowEdge] | None = None
    updated_by: str = "system"


@dataclass(frozen=True, slots=True)
class WorkflowExecute:
    """Input for executing a workflow."""

    inputs: dict[str, Any] = field(default_factory=dict)
    version: int | None = None
    parent_execution_id: str | None = None
    replay_from_node: str | None = None


@dataclass(frozen=True, slots=True)
class WorkflowReplay:
    """Input for replaying a workflow execution."""

    inputs: dict[str, Any] = field(default_factory=dict)
    version: int | None = None
    from_node: str | None = None
    parent_execution_id: str | None = None


@dataclass(frozen=True, slots=True)
class WorkflowApproval:
    """Input for approving/rejecting a workflow approval gate."""

    node_id: str
    approved: bool
    decided_by: str
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class WorkflowSummary:
    """Lightweight workflow summary for lists."""

    id: str
    name: str
    version: int
    status: WorkflowStatus
    updated_at: str

    @classmethod
    def from_workflow(cls, workflow: Workflow) -> WorkflowSummary:
        return cls(
            id=workflow.id,
            name=workflow.name,
            version=workflow.version,
            status=workflow.status,
            updated_at=workflow.updated_at.isoformat(),
        )


@dataclass(frozen=True, slots=True)
class WorkflowDetail:
    """Full workflow detail for single-workflow views."""

    id: str
    name: str
    description: str
    nodes: list[WorkflowNode]
    edges: list[WorkflowEdge]
    version: int
    status: WorkflowStatus
    template_id: str | None
    created_at: str
    updated_at: str
    created_by: str

    @classmethod
    def from_workflow(cls, workflow: Workflow) -> WorkflowDetail:
        return cls(
            id=workflow.id,
            name=workflow.name,
            description=workflow.description,
            nodes=list(workflow.nodes),
            edges=list(workflow.edges),
            version=workflow.version,
            status=workflow.status,
            template_id=workflow.template_id,
            created_at=workflow.created_at.isoformat(),
            updated_at=workflow.updated_at.isoformat(),
            created_by=workflow.created_by,
        )

    @classmethod
    def from_version(cls, version: WorkflowVersion) -> WorkflowDetail:
        return cls(
            id=version.workflow_id,
            name=version.name,
            description=version.description,
            nodes=list(version.nodes),
            edges=list(version.edges),
            version=version.version,
            status=WorkflowStatus.DRAFT,  # Historical versions are effectively draft
            template_id=None,
            created_at=version.created_at.isoformat(),
            updated_at=version.created_at.isoformat(),
            created_by=version.created_by,
        )


class WorkflowEnginePort(Protocol):
    """
    Port interface for workflow engine operations.

    All implementations must provide these methods.
    Domain logic depends on this interface, not implementations.
    """

    # CRUD Operations
    @abstractmethod
    async def create_workflow(self, data: WorkflowCreate) -> WorkflowDetail:
        """Create a new workflow definition."""
        ...

    @abstractmethod
    async def get_workflow(self, workflow_id: str) -> WorkflowDetail | None:
        """Get workflow by ID."""
        ...

    @abstractmethod
    async def list_workflows(
        self,
        status: WorkflowStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[WorkflowSummary]:
        """List workflows with optional filtering."""
        ...

    @abstractmethod
    async def update_workflow(self, workflow_id: str, data: WorkflowUpdate) -> WorkflowDetail:
        """Update workflow definition (creates new version if structure changes)."""
        ...

    @abstractmethod
    async def delete_workflow(self, workflow_id: str) -> bool:
        """Delete workflow definition and all its versions."""
        ...

    # Version Management
    @abstractmethod
    async def get_workflow_versions(self, workflow_id: str) -> list[WorkflowVersion]:
        """Get all versions of a workflow."""
        ...

    @abstractmethod
    async def get_workflow_version(self, workflow_id: str, version: int) -> WorkflowDetail | None:
        """Get specific version of a workflow."""
        ...

    # Execution Operations
    @abstractmethod
    async def execute_workflow(self, workflow_id: str, data: WorkflowExecute) -> WorkflowExecution:
        """Start a new workflow execution."""
        ...

    @abstractmethod
    async def replay_workflow(self, workflow_id: str, data: WorkflowReplay) -> WorkflowExecution:
        """Replay a workflow from a specific node or execution."""
        ...

    @abstractmethod
    async def approve_workflow(self, workflow_id: str, data: WorkflowApproval) -> WorkflowExecution:
        """Approve or reject a workflow approval gate."""
        ...

    # Query Operations
    @abstractmethod
    async def get_execution(self, execution_id: str) -> WorkflowExecution | None:
        """Get execution by ID."""
        ...

    @abstractmethod
    async def get_workflow_executions(
        self,
        workflow_id: str,
        status: WorkflowExecutionStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[WorkflowExecution]:
        """Get executions for a workflow."""
        ...

    @abstractmethod
    async def get_running_executions(self) -> list[WorkflowExecution]:
        """Get all currently running executions."""
        ...

    # Control Operations
    @abstractmethod
    async def cancel_execution(self, execution_id: str) -> WorkflowExecution:
        """Cancel a running workflow execution."""
        ...

    @abstractmethod
    async def pause_execution(self, execution_id: str) -> WorkflowExecution:
        """Pause a running workflow execution."""
        ...

    @abstractmethod
    async def resume_execution(self, execution_id: str) -> WorkflowExecution:
        """Resume a paused workflow execution."""
        ...

    # Validation
    @abstractmethod
    async def validate_workflow(
        self,
        nodes: list[WorkflowNode],
        edges: list[WorkflowEdge],
    ) -> ValidationResult:
        """Validate workflow structure (DAG, no cycles, valid references)."""
        ...


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Result of workflow/pipeline validation."""

    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
