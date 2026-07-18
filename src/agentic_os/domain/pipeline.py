"""
Pipeline Domain Models

Domain layer for pipeline engine - pure Python, no external dependencies.
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


class PipelineStatus(StrEnum):
    """Lifecycle status of a pipeline definition."""

    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ARCHIVED = "archived"


class PipelineExecutionStatus(StrEnum):
    """Runtime status of a pipeline execution."""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StageType(StrEnum):
    """Built-in pipeline stage types."""

    AGENT = "agent"
    WORKFLOW = "workflow"
    TOOL = "tool"
    LLM = "llm"
    CONDITION = "condition"
    PARALLEL = "parallel"
    APPROVAL = "approval"
    MCP = "mcp"
    PLUGIN = "plugin"
    CUSTOM = "custom"


@dataclass(frozen=True, slots=True)
class PipelineStage:
    """
    A stage in a pipeline.

    Immutable after creation - use replace() pattern for modifications.
    """

    id: str
    type: StageType
    label: str
    config: dict[str, Any] = field(default_factory=dict)
    # Dependencies: stage IDs that must complete before this stage
    depends_on: tuple[str, ...] = field(default_factory=tuple)
    # Retry policy
    retry_count: int = 0
    retry_delay_seconds: int = 5
    # Timeout
    timeout_seconds: int | None = None
    # Conditional execution
    condition: dict[str, Any] | None = None
    # For parallel stages: child stages
    children: tuple[str, ...] = field(default_factory=tuple)

    def with_config(self, config: dict[str, Any]) -> PipelineStage:
        return PipelineStage(
            id=self.id,
            type=self.type,
            label=self.label,
            config=config,
            depends_on=self.depends_on,
            retry_count=self.retry_count,
            retry_delay_seconds=self.retry_delay_seconds,
            timeout_seconds=self.timeout_seconds,
            condition=self.condition,
            children=self.children,
        )

    def with_depends_on(self, depends_on: list[str]) -> PipelineStage:
        return PipelineStage(
            id=self.id,
            type=self.type,
            label=self.label,
            config=self.config,
            depends_on=tuple(depends_on),
            retry_count=self.retry_count,
            retry_delay_seconds=self.retry_delay_seconds,
            timeout_seconds=self.timeout_seconds,
            condition=self.condition,
            children=self.children,
        )


@dataclass(frozen=True, slots=True)
class PipelineEdge:
    """
    A dependency edge between pipeline stages.
    """

    id: str
    from_stage: str  # source stage id
    to_stage: str  # target stage id
    # Optional condition for conditional edges
    condition: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class Pipeline:
    """
    Pipeline definition - ordered sequence of stages with dependencies.

    Versioned immutable entity. New versions create new Pipeline instances.
    """

    id: str
    name: str
    description: str
    stages: tuple[PipelineStage, ...]
    edges: tuple[PipelineEdge, ...]
    version: int
    status: PipelineStatus
    # Cron schedule for scheduled pipelines
    schedule_cron: str | None = None
    schedule_timezone: str = "UTC"
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)
    created_by: str = "system"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "stages": [
                {
                    "id": s.id,
                    "type": s.type.value,
                    "label": s.label,
                    "config": s.config,
                    "depends_on": list(s.depends_on),
                    "retry_count": s.retry_count,
                    "retry_delay_seconds": s.retry_delay_seconds,
                    "timeout_seconds": s.timeout_seconds,
                    "condition": s.condition,
                    "children": list(s.children),
                }
                for s in self.stages
            ],
            "edges": [
                {
                    "id": e.id,
                    "from_stage": e.from_stage,
                    "to_stage": e.to_stage,
                    "condition": e.condition,
                }
                for e in self.edges
            ],
            "version": self.version,
            "status": self.status.value,
            "schedule_cron": self.schedule_cron,
            "schedule_timezone": self.schedule_timezone,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "created_by": self.created_by,
        }

    @classmethod
    def create(
        cls,
        name: str,
        description: str,
        stages: list[PipelineStage],
        edges: list[PipelineEdge],
        schedule_cron: str | None = None,
        schedule_timezone: str = "UTC",
        created_by: str = "system",
    ) -> Pipeline:
        return cls(
            id=str(uuid4()),
            name=name,
            description=description,
            stages=tuple(stages),
            edges=tuple(edges),
            version=1,
            status=PipelineStatus.DRAFT,
            schedule_cron=schedule_cron,
            schedule_timezone=schedule_timezone,
            created_by=created_by,
        )

    def new_version(
        self,
        name: str | None = None,
        description: str | None = None,
        stages: list[PipelineStage] | None = None,
        edges: list[PipelineEdge] | None = None,
        schedule_cron: str | None = None,
        schedule_timezone: str | None = None,
        created_by: str = "system",
    ) -> Pipeline:
        """Create a new version of this pipeline."""
        return Pipeline(
            id=self.id,
            name=name or self.name,
            description=description or self.description,
            stages=tuple(stages) if stages is not None else self.stages,
            edges=tuple(edges) if edges is not None else self.edges,
            version=self.version + 1,
            status=PipelineStatus.DRAFT,
            schedule_cron=schedule_cron if schedule_cron is not None else self.schedule_cron,
            schedule_timezone=schedule_timezone or self.schedule_timezone,
            created_at=self.created_at,
            updated_at=_utcnow(),
            created_by=created_by,
        )

    def activate(self, created_by: str = "system") -> Pipeline:
        return Pipeline(
            id=self.id,
            name=self.name,
            description=self.description,
            stages=self.stages,
            edges=self.edges,
            version=self.version,
            status=PipelineStatus.ACTIVE,
            schedule_cron=self.schedule_cron,
            schedule_timezone=self.schedule_timezone,
            created_at=self.created_at,
            updated_at=_utcnow(),
            created_by=created_by,
        )

    def pause(self, created_by: str = "system") -> Pipeline:
        return Pipeline(
            id=self.id,
            name=self.name,
            description=self.description,
            stages=self.stages,
            edges=self.edges,
            version=self.version,
            status=PipelineStatus.PAUSED,
            schedule_cron=self.schedule_cron,
            schedule_timezone=self.schedule_timezone,
            created_at=self.created_at,
            updated_at=_utcnow(),
            created_by=created_by,
        )

    def archive(self, created_by: str = "system") -> Pipeline:
        return Pipeline(
            id=self.id,
            name=self.name,
            description=self.description,
            stages=self.stages,
            edges=self.edges,
            version=self.version,
            status=PipelineStatus.ARCHIVED,
            schedule_cron=self.schedule_cron,
            schedule_timezone=self.schedule_timezone,
            created_at=self.created_at,
            updated_at=_utcnow(),
            created_by=created_by,
        )


@dataclass(frozen=True, slots=True)
class PipelineExecution:
    """
    Runtime instance of a pipeline execution.

    Tracks the dynamic state as the pipeline runs through stages.
    """

    id: str
    pipeline_id: str
    pipeline_version: int
    status: PipelineExecutionStatus
    inputs: dict[str, Any] = field(default_factory=dict)
    current_stage: str | None = None
    completed_stages: frozenset[str] = field(default_factory=frozenset)
    failed_stages: frozenset[str] = field(default_factory=frozenset)
    stage_outputs: dict[str, Any] = field(default_factory=dict)
    stage_errors: dict[str, str] = field(default_factory=dict)
    stage_retries: dict[str, int] = field(default_factory=dict)
    # For scheduled executions
    scheduled_at: datetime | None = None
    # For rollback support
    parent_execution_id: str | None = None
    rollback_to_execution_id: str | None = None
    started_at: datetime = field(default_factory=_utcnow)
    completed_at: datetime | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "pipeline_id": self.pipeline_id,
            "pipeline_version": self.pipeline_version,
            "status": self.status.value,
            "inputs": self.inputs,
            "current_stage": self.current_stage,
            "completed_stages": list(self.completed_stages),
            "failed_stages": list(self.failed_stages),
            "stage_outputs": self.stage_outputs,
            "stage_errors": self.stage_errors,
            "stage_retries": self.stage_retries,
            "scheduled_at": self.scheduled_at.isoformat() if self.scheduled_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
            "parent_execution_id": self.parent_execution_id,
            "rollback_to_execution_id": self.rollback_to_execution_id,
        }

    @classmethod
    def create(
        cls,
        pipeline_id: str,
        pipeline_version: int,
        inputs: dict[str, Any],
        scheduled_at: datetime | None = None,
        parent_execution_id: str | None = None,
        rollback_to_execution_id: str | None = None,
    ) -> PipelineExecution:
        return cls(
            id=str(uuid4()),
            pipeline_id=pipeline_id,
            pipeline_version=pipeline_version,
            status=PipelineExecutionStatus.PENDING,
            inputs=inputs,
            scheduled_at=scheduled_at,
            parent_execution_id=parent_execution_id,
            rollback_to_execution_id=rollback_to_execution_id,
        )

    def schedule(self, scheduled_at: datetime) -> PipelineExecution:
        return PipelineExecution(
            id=self.id,
            pipeline_id=self.pipeline_id,
            pipeline_version=self.pipeline_version,
            status=PipelineExecutionStatus.PENDING,
            inputs=self.inputs,
            current_stage=None,
            completed_stages=self.completed_stages,
            failed_stages=self.failed_stages,
            stage_outputs=self.stage_outputs,
            stage_errors=self.stage_errors,
            stage_retries=self.stage_retries,
            scheduled_at=scheduled_at,
            parent_execution_id=self.parent_execution_id,
            rollback_to_execution_id=self.rollback_to_execution_id,
            started_at=self.started_at,
            completed_at=None,
            error=None,
        )

    def start(self) -> PipelineExecution:
        return PipelineExecution(
            id=self.id,
            pipeline_id=self.pipeline_id,
            pipeline_version=self.pipeline_version,
            status=PipelineExecutionStatus.RUNNING,
            inputs=self.inputs,
            current_stage=self.current_stage,
            completed_stages=self.completed_stages,
            failed_stages=self.failed_stages,
            stage_outputs=self.stage_outputs,
            stage_errors=self.stage_errors,
            stage_retries=self.stage_retries,
            scheduled_at=self.scheduled_at,
            parent_execution_id=self.parent_execution_id,
            rollback_to_execution_id=self.rollback_to_execution_id,
            started_at=_utcnow(),
            completed_at=None,
            error=None,
        )

    def pause(self) -> PipelineExecution:
        return PipelineExecution(
            id=self.id,
            pipeline_id=self.pipeline_id,
            pipeline_version=self.pipeline_version,
            status=PipelineExecutionStatus.PAUSED,
            inputs=self.inputs,
            current_stage=self.current_stage,
            completed_stages=self.completed_stages,
            failed_stages=self.failed_stages,
            stage_outputs=self.stage_outputs,
            stage_errors=self.stage_errors,
            stage_retries=self.stage_retries,
            scheduled_at=self.scheduled_at,
            parent_execution_id=self.parent_execution_id,
            rollback_to_execution_id=self.rollback_to_execution_id,
            started_at=self.started_at,
            completed_at=None,
            error=self.error,
        )

    def complete(self) -> PipelineExecution:
        return PipelineExecution(
            id=self.id,
            pipeline_id=self.pipeline_id,
            pipeline_version=self.pipeline_version,
            status=PipelineExecutionStatus.COMPLETED,
            inputs=self.inputs,
            current_stage=None,
            completed_stages=self.completed_stages,
            failed_stages=self.failed_stages,
            stage_outputs=self.stage_outputs,
            stage_errors=self.stage_errors,
            stage_retries=self.stage_retries,
            scheduled_at=self.scheduled_at,
            parent_execution_id=self.parent_execution_id,
            rollback_to_execution_id=self.rollback_to_execution_id,
            started_at=self.started_at,
            completed_at=_utcnow(),
            error=None,
        )

    def fail(self, error: str, failed_stage: str | None = None) -> PipelineExecution:
        failed = self.failed_stages
        if failed_stage:
            failed = failed | {failed_stage}
        return PipelineExecution(
            id=self.id,
            pipeline_id=self.pipeline_id,
            pipeline_version=self.pipeline_version,
            status=PipelineExecutionStatus.FAILED,
            inputs=self.inputs,
            current_stage=self.current_stage,
            completed_stages=self.completed_stages,
            failed_stages=failed,
            stage_outputs=self.stage_outputs,
            stage_errors={**self.stage_errors, failed_stage: error}
            if failed_stage
            else self.stage_errors,
            stage_retries=self.stage_retries,
            scheduled_at=self.scheduled_at,
            parent_execution_id=self.parent_execution_id,
            rollback_to_execution_id=self.rollback_to_execution_id,
            started_at=self.started_at,
            completed_at=_utcnow(),
            error=error,
        )

    def cancel(self) -> PipelineExecution:
        return PipelineExecution(
            id=self.id,
            pipeline_id=self.pipeline_id,
            pipeline_version=self.pipeline_version,
            status=PipelineExecutionStatus.CANCELLED,
            inputs=self.inputs,
            current_stage=None,
            completed_stages=self.completed_stages,
            failed_stages=self.failed_stages,
            stage_outputs=self.stage_outputs,
            stage_errors=self.stage_errors,
            stage_retries=self.stage_retries,
            scheduled_at=self.scheduled_at,
            parent_execution_id=self.parent_execution_id,
            rollback_to_execution_id=self.rollback_to_execution_id,
            started_at=self.started_at,
            completed_at=_utcnow(),
            error="Cancelled by user",
        )

    def set_current_stage(self, stage_id: str) -> PipelineExecution:
        return PipelineExecution(
            id=self.id,
            pipeline_id=self.pipeline_id,
            pipeline_version=self.pipeline_version,
            status=self.status,
            inputs=self.inputs,
            current_stage=stage_id,
            completed_stages=self.completed_stages,
            failed_stages=self.failed_stages,
            stage_outputs=self.stage_outputs,
            stage_errors=self.stage_errors,
            stage_retries=self.stage_retries,
            scheduled_at=self.scheduled_at,
            parent_execution_id=self.parent_execution_id,
            rollback_to_execution_id=self.rollback_to_execution_id,
            started_at=self.started_at,
            completed_at=self.completed_at,
            error=self.error,
        )

    def complete_stage(self, stage_id: str, output: Any) -> PipelineExecution:
        return PipelineExecution(
            id=self.id,
            pipeline_id=self.pipeline_id,
            pipeline_version=self.pipeline_version,
            status=self.status,
            inputs=self.inputs,
            current_stage=self.current_stage,
            completed_stages=self.completed_stages | {stage_id},
            failed_stages=self.failed_stages - {stage_id},
            stage_outputs={**self.stage_outputs, stage_id: output},
            stage_errors=self.stage_errors,
            stage_retries=self.stage_retries,
            scheduled_at=self.scheduled_at,
            parent_execution_id=self.parent_execution_id,
            rollback_to_execution_id=self.rollback_to_execution_id,
            started_at=self.started_at,
            completed_at=self.completed_at,
            error=self.error,
        )

    def fail_stage(self, stage_id: str, error: str) -> PipelineExecution:
        return PipelineExecution(
            id=self.id,
            pipeline_id=self.pipeline_id,
            pipeline_version=self.pipeline_version,
            status=self.status,
            inputs=self.inputs,
            current_stage=stage_id,
            completed_stages=self.completed_stages,
            failed_stages=self.failed_stages | {stage_id},
            stage_outputs=self.stage_outputs,
            stage_errors={**self.stage_errors, stage_id: error},
            stage_retries=self.stage_retries,
            scheduled_at=self.scheduled_at,
            parent_execution_id=self.parent_execution_id,
            rollback_to_execution_id=self.rollback_to_execution_id,
            started_at=self.started_at,
            completed_at=self.completed_at,
            error=self.error,
        )

    def increment_retry(self, stage_id: str) -> PipelineExecution:
        return PipelineExecution(
            id=self.id,
            pipeline_id=self.pipeline_id,
            pipeline_version=self.pipeline_version,
            status=self.status,
            inputs=self.inputs,
            current_stage=stage_id,
            completed_stages=self.completed_stages,
            failed_stages=self.failed_stages,
            stage_outputs=self.stage_outputs,
            stage_errors=self.stage_errors,
            stage_retries={**self.stage_retries, stage_id: self.stage_retries.get(stage_id, 0) + 1},
            scheduled_at=self.scheduled_at,
            parent_execution_id=self.parent_execution_id,
            rollback_to_execution_id=self.rollback_to_execution_id,
            started_at=self.started_at,
            completed_at=self.completed_at,
            error=self.error,
        )

    def rollback(self, to_execution_id: str) -> PipelineExecution:
        return PipelineExecution(
            id=self.id,
            pipeline_id=self.pipeline_id,
            pipeline_version=self.pipeline_version,
            status=PipelineExecutionStatus.PENDING,
            inputs=self.inputs,
            current_stage=None,
            completed_stages=frozenset(),
            failed_stages=frozenset(),
            stage_outputs={},
            stage_errors={},
            stage_retries={},
            scheduled_at=self.scheduled_at,
            parent_execution_id=self.parent_execution_id,
            rollback_to_execution_id=to_execution_id,
            started_at=_utcnow(),
            completed_at=None,
            error=None,
        )


@dataclass(frozen=True, slots=True)
class PipelineSchedule:
    """Schedule configuration for a pipeline."""

    pipeline_id: str
    cron: str
    timezone: str
    next_run: datetime
    enabled: bool = True
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)

    @classmethod
    def create(cls, pipeline_id: str, cron: str, timezone: str = "UTC") -> PipelineSchedule:
        # Simple next_run calculation - in reality would use croniter
        return cls(
            pipeline_id=pipeline_id,
            cron=cron,
            timezone=timezone,
            next_run=_utcnow(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "pipeline_id": self.pipeline_id,
            "cron": self.cron,
            "timezone": self.timezone,
            "next_run": self.next_run.isoformat() if self.next_run else None,
            "enabled": self.enabled,
        }


@dataclass(frozen=True, slots=True)
class PipelineVersion:
    """Historical version record for a pipeline."""

    version: int
    pipeline_id: str
    name: str
    description: str
    stages: tuple[PipelineStage, ...]
    edges: tuple[PipelineEdge, ...]
    schedule_cron: str | None
    schedule_timezone: str
    created_at: datetime
    created_by: str
    changelog: str
