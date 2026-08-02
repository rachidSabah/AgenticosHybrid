"""
Pipeline Engine Port

Defines the interface for pipeline engine operations.
Domain logic depends on this interface, not implementations.
"""

from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from agentic_os.domain.pipeline import (
    Pipeline,
    PipelineEdge,
    PipelineExecution,
    PipelineExecutionStatus,
    PipelineSchedule,
    PipelineStage,
    PipelineStatus,
    PipelineVersion,
)


@dataclass(frozen=True, slots=True)
class PipelineCreate:
    """Input for creating a new pipeline."""

    name: str
    description: str
    stages: list[PipelineStage]
    edges: list[PipelineEdge]
    schedule_cron: str | None = None
    schedule_timezone: str = "UTC"
    created_by: str = "system"


@dataclass(frozen=True, slots=True)
class PipelineUpdate:
    """Input for updating a pipeline."""

    name: str | None = None
    description: str | None = None
    stages: list[PipelineStage] | None = None
    edges: list[PipelineEdge] | None = None
    schedule_cron: str | None = None
    schedule_timezone: str | None = None
    status: PipelineStatus | None = None
    updated_by: str = "system"


@dataclass(frozen=True, slots=True)
class PipelineExecute:
    """Input for executing a pipeline."""

    inputs: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PipelineScheduleRequest:
    """Input for scheduling a pipeline."""

    cron: str
    timezone: str = "UTC"


@dataclass(frozen=True, slots=True)
class PipelineRollback:
    """Input for rolling back a pipeline execution."""

    to_execution_id: str


@dataclass(frozen=True, slots=True)
class PipelineSummary:
    """Lightweight pipeline summary for lists."""

    id: str
    name: str
    version: int
    status: PipelineStatus
    schedule_cron: str | None
    schedule_timezone: str
    next_run: datetime | None
    stage_count: int
    updated_at: datetime

    @classmethod
    def from_pipeline(
        cls, pipeline: Pipeline, schedule: PipelineSchedule | None = None
    ) -> PipelineSummary:
        return cls(
            id=pipeline.id,
            name=pipeline.name,
            version=pipeline.version,
            status=pipeline.status,
            schedule_cron=pipeline.schedule_cron,
            schedule_timezone=pipeline.schedule_timezone,
            next_run=schedule.next_run if schedule else None,
            stage_count=len(pipeline.stages),
            updated_at=pipeline.updated_at,
        )


@dataclass(frozen=True, slots=True)
class PipelineDetail:
    """Full pipeline detail for single-pipeline views."""

    id: str
    name: str
    description: str
    stages: list[PipelineStage]
    edges: list[PipelineEdge]
    version: int
    status: PipelineStatus
    schedule_cron: str | None
    schedule_timezone: str
    created_at: datetime
    updated_at: datetime
    created_by: str

    @classmethod
    def from_pipeline(cls, pipeline: Pipeline) -> PipelineDetail:
        return cls(
            id=pipeline.id,
            name=pipeline.name,
            description=pipeline.description,
            stages=list(pipeline.stages),
            edges=list(pipeline.edges),
            version=pipeline.version,
            status=pipeline.status,
            schedule_cron=pipeline.schedule_cron,
            schedule_timezone=pipeline.schedule_timezone,
            created_at=pipeline.created_at,
            updated_at=pipeline.updated_at,
            created_by=pipeline.created_by,
        )

    @classmethod
    def from_version(cls, version: PipelineVersion) -> PipelineDetail:
        return cls(
            id=version.pipeline_id,
            name=version.name,
            description=version.description,
            stages=list(version.stages),
            edges=list(version.edges),
            version=version.version,
            status=PipelineStatus.DRAFT,
            schedule_cron=version.schedule_cron,
            schedule_timezone=version.schedule_timezone,
            created_at=version.created_at,
            updated_at=version.created_at,
            created_by=version.created_by,
        )


class PipelineEnginePort(Protocol):
    """
    Port interface for pipeline engine operations.

    All implementations must provide these methods.
    Domain logic depends on this interface, not implementations.
    """

    # CRUD Operations
    @abstractmethod
    async def create_pipeline(self, data: PipelineCreate) -> PipelineDetail:
        """Create a new pipeline definition."""
        ...

    @abstractmethod
    async def get_pipeline(self, pipeline_id: str) -> PipelineDetail | None:
        """Get pipeline by ID."""
        ...

    @abstractmethod
    async def list_pipelines(
        self,
        status: PipelineStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[PipelineSummary]:
        """List pipelines with optional filtering."""
        ...

    @abstractmethod
    async def update_pipeline(self, pipeline_id: str, data: PipelineUpdate) -> PipelineDetail:
        """Update pipeline definition (creates new version if structure changes)."""
        ...

    @abstractmethod
    async def delete_pipeline(self, pipeline_id: str) -> bool:
        """Delete pipeline definition and all its versions."""
        ...

    # Version Management
    @abstractmethod
    async def get_pipeline_versions(self, pipeline_id: str) -> list[PipelineVersion]:
        """Get all versions of a pipeline."""
        ...

    @abstractmethod
    async def get_pipeline_version(self, pipeline_id: str, version: int) -> PipelineDetail | None:
        """Get specific version of a pipeline."""
        ...

    # Execution Operations
    @abstractmethod
    async def execute_pipeline(self, pipeline_id: str, data: PipelineExecute) -> PipelineExecution:
        """Start a new pipeline execution."""
        ...

    # Scheduling
    @abstractmethod
    async def schedule_pipeline(
        self, pipeline_id: str, data: PipelineScheduleRequest
    ) -> PipelineSchedule:
        """Schedule a pipeline for recurring execution."""
        ...

    @abstractmethod
    async def unschedule_pipeline(self, pipeline_id: str) -> bool:
        """Remove pipeline schedule."""
        ...

    @abstractmethod
    async def get_pipeline_schedule(self, pipeline_id: str) -> PipelineSchedule | None:
        """Get pipeline schedule if exists."""
        ...

    # Rollback
    @abstractmethod
    async def rollback_pipeline(
        self, pipeline_id: str, data: PipelineRollback
    ) -> PipelineExecution:
        """Rollback a pipeline execution to a previous execution."""
        ...

    # Query Operations
    @abstractmethod
    async def get_execution(self, execution_id: str) -> PipelineExecution | None:
        """Get execution by ID."""
        ...

    @abstractmethod
    async def get_pipeline_executions(
        self,
        pipeline_id: str,
        status: PipelineExecutionStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[PipelineExecution]:
        """Get executions for a pipeline."""
        ...

    @abstractmethod
    async def get_running_executions(self) -> list[PipelineExecution]:
        """Get all currently running executions."""
        ...

    @abstractmethod
    async def get_scheduled_executions(self) -> list[PipelineExecution]:
        """Get all scheduled executions."""
        ...

    # Control Operations
    @abstractmethod
    async def cancel_execution(self, execution_id: str) -> PipelineExecution:
        """Cancel a running pipeline execution."""
        ...

    @abstractmethod
    async def pause_execution(self, execution_id: str) -> PipelineExecution:
        """Pause a running pipeline execution."""
        ...

    @abstractmethod
    async def resume_execution(self, execution_id: str) -> PipelineExecution:
        """Resume a paused pipeline execution."""
        ...

    # Validation
    @abstractmethod
    async def validate_pipeline(
        self,
        stages: list[PipelineStage],
        edges: list[PipelineEdge],
    ) -> ValidationResult:
        """Validate pipeline structure (DAG, no cycles, valid references)."""
        ...


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Result of pipeline validation."""

    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
