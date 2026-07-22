"""
In-Memory Pipeline Adapter

Implements PipelineEnginePort using in-memory storage.
Used for development and testing; can be swapped for persistent storage.
"""

from __future__ import annotations

import logging

from agentic_os.core.providers.router import ProviderRouter
from agentic_os.core.registry import AgentRegistry
from agentic_os.domain.pipeline import (
    PipelineEdge,
    PipelineExecution,
    PipelineExecutionStatus,
    PipelineSchedule,
    PipelineStage,
    PipelineStatus,
    PipelineVersion,
)
from agentic_os.ports.event_bus import EventBus
from agentic_os.ports.pipeline import (
    PipelineCreate,
    PipelineDetail,
    PipelineEnginePort,
    PipelineExecute,
    PipelineRollback,
    PipelineScheduleRequest,
    PipelineSummary,
    PipelineUpdate,
    ValidationResult,
)

logger = logging.getLogger(__name__)


class InMemoryPipelineAdapter(PipelineEnginePort):
    """
    In-memory implementation of PipelineEnginePort.

    All data is stored in memory and lost on restart.
    For production, replace with PostgresPipelineAdapter or similar.
    """

    def __init__(
        self,
        event_bus: EventBus,
        provider_router: ProviderRouter,
        agent_registry: AgentRegistry,
    ):
        # Delegate to core implementation
        from agentic_os.core.pipeline.engine import PipelineEngineImpl

        self._engine = PipelineEngineImpl(event_bus, provider_router, agent_registry)

    # Delegate all methods to the core implementation

    async def create_pipeline(self, data: PipelineCreate) -> PipelineDetail:
        return await self._engine.create_pipeline(data)

    async def get_pipeline(self, pipeline_id: str) -> PipelineDetail | None:
        return await self._engine.get_pipeline(pipeline_id)

    async def list_pipelines(
        self,
        status: PipelineStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[PipelineSummary]:
        return await self._engine.list_pipelines(status, limit, offset)

    async def update_pipeline(self, pipeline_id: str, data: PipelineUpdate) -> PipelineDetail:
        return await self._engine.update_pipeline(pipeline_id, data)

    async def delete_pipeline(self, pipeline_id: str) -> bool:
        return await self._engine.delete_pipeline(pipeline_id)

    async def get_pipeline_versions(self, pipeline_id: str) -> list[PipelineVersion]:
        return await self._engine.get_pipeline_versions(pipeline_id)

    async def get_pipeline_version(self, pipeline_id: str, version: int) -> PipelineDetail | None:
        return await self._engine.get_pipeline_version(pipeline_id, version)

    async def execute_pipeline(self, pipeline_id: str, data: PipelineExecute) -> PipelineExecution:
        return await self._engine.execute_pipeline(pipeline_id, data)

    async def schedule_pipeline(
        self, pipeline_id: str, data: PipelineScheduleRequest
    ) -> PipelineSchedule:
        return await self._engine.schedule_pipeline(pipeline_id, data)

    async def unschedule_pipeline(self, pipeline_id: str) -> bool:
        return await self._engine.unschedule_pipeline(pipeline_id)

    async def get_pipeline_schedule(self, pipeline_id: str) -> PipelineSchedule | None:
        return await self._engine.get_pipeline_schedule(pipeline_id)

    async def rollback_pipeline(
        self, pipeline_id: str, data: PipelineRollback
    ) -> PipelineExecution:
        return await self._engine.rollback_pipeline(pipeline_id, data)

    async def get_execution(self, execution_id: str) -> PipelineExecution | None:
        return await self._engine.get_execution(execution_id)

    async def get_pipeline_executions(
        self,
        pipeline_id: str,
        status: PipelineExecutionStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[PipelineExecution]:
        return await self._engine.get_pipeline_executions(pipeline_id, status, limit, offset)

    async def get_running_executions(self) -> list[PipelineExecution]:
        return await self._engine.get_running_executions()

    async def get_scheduled_executions(self) -> list[PipelineExecution]:
        return await self._engine.get_scheduled_executions()

    async def cancel_execution(self, execution_id: str) -> PipelineExecution:
        return await self._engine.cancel_execution(execution_id)

    async def pause_execution(self, execution_id: str) -> PipelineExecution:
        return await self._engine.pause_execution(execution_id)

    async def resume_execution(self, execution_id: str) -> PipelineExecution:
        return await self._engine.resume_execution(execution_id)

    async def validate_pipeline(
        self,
        stages: list[PipelineStage],
        edges: list[PipelineEdge],
    ) -> ValidationResult:
        return await self._engine.validate_pipeline(stages, edges)
