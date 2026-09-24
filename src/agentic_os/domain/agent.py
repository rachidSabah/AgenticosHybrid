"""Domain entities: Agent, Role, Task, Provider.

Design note: the 22 "primary agents" and 26 "orchestration roles" from the
product brief overlap heavily. Rather than ~48 near-duplicate classes, we model
a single generic :class:`Agent` instantiated with a :class:`Role`. A Role is a
declarative config (prompt template + allowed tools + target provider). This
keeps the system modular and replaceable (ADR-0004).
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(UTC)


class AgentStatus(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RECOVERING = "recovering"


class Role(BaseModel):
    """A declarative agent role. One Agent runtime, many Roles."""

    name: str
    description: str = ""
    system_prompt: str = ""
    allowed_tools: list[str] = Field(default_factory=list)
    default_provider: str | None = None


class Agent(BaseModel):
    """A running/concrete agent instance bound to a Role."""

    id: str = Field(default_factory=lambda: uuid4().hex)
    role: str
    name: str = ""
    provider: str
    model: str = ""
    status: AgentStatus = AgentStatus.IDLE
    current_task_id: str | None = None
    attempts: int = 0
    last_heartbeat: datetime | None = None
    created_at: datetime = Field(default_factory=_utcnow)

    def mark_running(self, task_id: str) -> None:
        self.status = AgentStatus.RUNNING
        self.current_task_id = task_id
        self.attempts += 1
        self.last_heartbeat = _utcnow()

    def heartbeat(self) -> None:
        self.last_heartbeat = _utcnow()

    def mark_completed(self) -> None:
        self.status = AgentStatus.COMPLETED
        self.last_heartbeat = _utcnow()

    def mark_failed(self) -> None:
        self.status = AgentStatus.FAILED
        self.last_heartbeat = _utcnow()

    def mark_recovering(self) -> None:
        self.status = AgentStatus.RECOVERING


class TaskStatus(StrEnum):
    PENDING = "pending"
    PLANNED = "planned"
    DISPATCHED = "dispatched"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    RECOVERED = "recovered"
    # The agent returned only a plan/report (e.g. a Markdown document) with
    # no independently verified workspace artifact. Never rendered as a
    # successful build: "PLAN GENERATED — DELIVERABLE NOT VERIFIED".
    PLAN_GENERATED = "plan_generated"


class Task(BaseModel):
    """A unit of work routed through the orchestrator.

    Carries the original user_prompt (preserved verbatim end-to-end so it
    reaches the CLI) alongside the planner-generated description.
    """

    id: str = Field(default_factory=lambda: uuid4().hex)
    title: str
    role: str
    description: str = ""
    user_prompt: str = ""
    status: TaskStatus = TaskStatus.PENDING
    assigned_agent_id: str | None = None
    attempts: int = 0
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    result: str | None = None
    error: str | None = None
    mission_id: str = ""
    # Restricts dispatch to a named set of providers (agent selection from the
    # Prompt Center). Empty means "route through the default selection logic".
    preferred_agents: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    pid: int | None = None
    exit_code: int | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    workspace: str = ""
    requested_deliverables: list[str] = Field(default_factory=list)
    selected_agent: str | None = None
    agent_capabilities: list[str] = Field(default_factory=list)
    process_start_time: datetime | None = None
    process_end_time: datetime | None = None
    stdout: str | None = None
    stderr: str | None = None
    changed_files: list[str] = Field(default_factory=list)
    created_files: list[str] = Field(default_factory=list)
    modified_files: list[str] = Field(default_factory=list)
    deleted_files: list[str] = Field(default_factory=list)
    tests_run: list[str] = Field(default_factory=list)
    test_results: dict[str, Any] = Field(default_factory=dict)
    verification_status: str | None = None
    verification_reason: str | None = None
    failure_reason: str | None = None
    # Independent artifact verification result (artifact_verification module).
    # Populated by the orchestrator after real execution — never fabricated.
    verification: dict = Field(default_factory=dict)

    @property
    def task_id(self) -> str:
        return self.id

    @property
    def prompt(self) -> str:
        return self.user_prompt or self.description

    def touch(self) -> None:
        self.updated_at = _utcnow()


class ProviderInfo(BaseModel):
    """Metadata registered by a provider adapter."""

    name: str
    kind: str  # e.g. "claude_code", "openai", "mock"
    supports_streaming: bool = False
    supports_tools: bool = False
    capabilities: list[str] = Field(default_factory=list)
