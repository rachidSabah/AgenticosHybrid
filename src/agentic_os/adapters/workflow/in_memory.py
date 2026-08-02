"""
In-Memory Workflow Adapter

Implements WorkflowEnginePort using in-memory storage.
Used for development and testing; can be swapped for persistent storage.
"""

from __future__ import annotations

import logging

from agentic_os.core.providers.router import ProviderRouter
from agentic_os.core.registry import AgentRegistry
from agentic_os.domain.workflow import (
    WorkflowEdge,
    WorkflowExecution,
    WorkflowExecutionStatus,
    WorkflowNode,
    WorkflowStatus,
    WorkflowVersion,
)
from agentic_os.ports.event_bus import EventBus
from agentic_os.ports.workflow import (
    ValidationResult,
    WorkflowApproval,
    WorkflowCreate,
    WorkflowDetail,
    WorkflowEnginePort,
    WorkflowExecute,
    WorkflowReplay,
    WorkflowSummary,
    WorkflowUpdate,
)

logger = logging.getLogger(__name__)


class InMemoryWorkflowAdapter(WorkflowEnginePort):
    """
    In-memory implementation of WorkflowEnginePort.

    All data is stored in memory and lost on restart.
    For production, replace with PostgresWorkflowAdapter or similar.
    """

    def __init__(
        self,
        event_bus: EventBus,
        provider_router: ProviderRouter,
        agent_registry: AgentRegistry,
    ):
        # Delegate to the core implementation
        from agentic_os.core.workflow.engine import WorkflowEngineImpl

        self._engine = WorkflowEngineImpl(event_bus, provider_router, agent_registry)

    # Delegate all methods to the core implementation

    async def create_workflow(self, data: WorkflowCreate) -> WorkflowDetail:
        return await self._engine.create_workflow(data)

    async def get_workflow(self, workflow_id: str) -> WorkflowDetail | None:
        return await self._engine.get_workflow(workflow_id)

    async def list_workflows(
        self,
        status: WorkflowStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[WorkflowSummary]:
        return await self._engine.list_workflows(status, limit, offset)

    async def update_workflow(self, workflow_id: str, data: WorkflowUpdate) -> WorkflowDetail:
        return await self._engine.update_workflow(workflow_id, data)

    async def delete_workflow(self, workflow_id: str) -> bool:
        return await self._engine.delete_workflow(workflow_id)

    async def get_workflow_versions(self, workflow_id: str) -> list[WorkflowVersion]:
        return await self._engine.get_workflow_versions(workflow_id)

    async def get_workflow_version(self, workflow_id: str, version: int) -> WorkflowDetail | None:
        return await self._engine.get_workflow_version(workflow_id, version)

    async def execute_workflow(self, workflow_id: str, data: WorkflowExecute) -> WorkflowExecution:
        return await self._engine.execute_workflow(workflow_id, data)

    async def replay_workflow(self, workflow_id: str, data: WorkflowReplay) -> WorkflowExecution:
        return await self._engine.replay_workflow(workflow_id, data)

    async def approve_workflow(self, workflow_id: str, data: WorkflowApproval) -> WorkflowExecution:
        return await self._engine.approve_workflow(workflow_id, data)

    async def get_execution(self, execution_id: str) -> WorkflowExecution | None:
        return await self._engine.get_execution(execution_id)

    async def get_workflow_executions(
        self,
        workflow_id: str,
        status: WorkflowExecutionStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[WorkflowExecution]:
        return await self._engine.get_workflow_executions(workflow_id, status, limit, offset)

    async def get_running_executions(self) -> list[WorkflowExecution]:
        return await self._engine.get_running_executions()

    async def cancel_execution(self, execution_id: str) -> WorkflowExecution:
        return await self._engine.cancel_execution(execution_id)

    async def pause_execution(self, execution_id: str) -> WorkflowExecution:
        return await self._engine.pause_execution(execution_id)

    async def resume_execution(self, execution_id: str) -> WorkflowExecution:
        return await self._engine.resume_execution(execution_id)

    async def validate_workflow(
        self,
        nodes: list[WorkflowNode],
        edges: list[WorkflowEdge],
    ) -> ValidationResult:
        return await self._engine.validate_workflow(nodes, edges)
