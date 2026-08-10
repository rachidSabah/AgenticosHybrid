"""Mission Orchestrator Domain Models.

Pure domain layer for the Mission Orchestrator subsystem — zero external
dependencies. Defines missions, plans, tasks, agent assignments, and
lifecycle state machines used by the planner and execution engine.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _new_id() -> str:
    return uuid4().hex[:12]


# ── Enums ──


class MissionPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ExecutionMode(StrEnum):
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    HYBRID = "hybrid"


class MissionStatus(StrEnum):
    DRAFT = "draft"
    PLANNING = "planning"
    PLANNED = "planned"
    QUEUED = "queued"
    EXECUTING = "executing"
    RUNNING = "running"
    WAITING = "waiting"
    BLOCKED = "blocked"
    RETRYING = "retrying"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RECOVERED = "recovered"


class TaskStatus(StrEnum):
    PENDING = "pending"
    PLANNED = "planned"
    QUEUED = "queued"
    ASSIGNED = "assigned"
    RUNNING = "running"
    WAITING = "waiting"
    BLOCKED = "blocked"
    RETRYING = "retrying"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    RECOVERED = "recovered"


class AgentRole(StrEnum):
    """Vendor-agnostic roles mapped to providers by the Provider Framework."""

    CHIEF_ARCHITECT = "chief_architect"
    REPOSITORY_AUDITOR = "repository_auditor"
    BACKEND_ENGINEER = "backend_engineer"
    FRONTEND_ENGINEER = "frontend_engineer"
    SECURITY_ENGINEER = "security_engineer"
    TEST_ENGINEER = "test_engineer"
    DOCUMENTATION_WRITER = "documentation_writer"
    RELEASE_ENGINEER = "release_engineer"
    RESEARCHER = "researcher"
    DEBUGGER = "debugger"
    VALIDATOR = "validator"


# ── Data types ──


@dataclass
class Attachment:
    """A file or reference attached to a mission."""

    id: str = field(default_factory=_new_id)
    filename: str = ""
    mime_type: str = ""
    size_bytes: int = 0
    path: str = ""
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "filename": self.filename,
            "mime_type": self.mime_type,
            "size_bytes": self.size_bytes,
            "path": self.path,
            "description": self.description,
        }


@dataclass
class MissionTask:
    """A single decomposed task within a mission.

    Carries BOTH the original user_prompt (preserved verbatim so it reaches
    the CLI) AND the planner_description (the planner's generated narrative).
    """

    id: str = field(default_factory=_new_id)
    mission_id: str = ""
    title: str = ""
    description: str = ""
    user_prompt: str = ""
    status: TaskStatus = TaskStatus.PENDING
    assigned_role: AgentRole | None = None
    assigned_provider: str = ""
    dependencies: list[str] = field(default_factory=list)
    estimated_minutes: int = 0
    required_capability: str = "chat"
    output: str = ""
    error: str = ""
    started_at: datetime | None = None
    completed_at: datetime | None = None
    attachments: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "mission_id": self.mission_id,
            "title": self.title,
            "description": self.description,
            "user_prompt": self.user_prompt,
            "status": self.status.value,
            "assigned_role": self.assigned_role.value if self.assigned_role else None,
            "assigned_provider": self.assigned_provider,
            "dependencies": self.dependencies,
            "estimated_minutes": self.estimated_minutes,
            "output": self.output,
            "error": self.error,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "attachments": self.attachments,
        }


@dataclass
class MissionPlan:
    """The execution plan produced by the planner."""

    id: str = field(default_factory=_new_id)
    mission_id: str = ""
    summary: str = ""
    complexity: str = ""
    estimated_total_minutes: int = 0
    risk_level: str = "low"
    tasks: list[MissionTask] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "mission_id": self.mission_id,
            "summary": self.summary,
            "complexity": self.complexity,
            "estimated_total_minutes": self.estimated_total_minutes,
            "risk_level": self.risk_level,
            "tasks": [t.to_dict() for t in self.tasks],
            "task_count": len(self.tasks),
        }


@dataclass
class Mission:
    """Top-level mission representing a user's goal."""

    id: str = field(default_factory=_new_id)
    title: str = ""
    description: str = ""
    prompt: str = ""
    objectives: list[str] = field(default_factory=list)
    deliverables: list[str] = field(default_factory=list)
    priority: MissionPriority = MissionPriority.MEDIUM
    execution_mode: ExecutionMode = ExecutionMode.HYBRID
    constraints: list[str] = field(default_factory=list)
    # Named agents (providers) the user selected for this mission. When
    # non-empty, every planned task is dispatched ONLY to these agents.
    preferred_agents: list[str] = field(default_factory=list)
    deadline: datetime | None = None
    tags: list[str] = field(default_factory=list)
    attachments: list[Attachment] = field(default_factory=list)
    # Origin channel: "WEB" | "LOCAL" | "TELEGRAM" | "WHATSAPP" | "API".
    # Defaults to WEB so existing browser-created missions are unaffected.
    channel: str = "WEB"
    # Remote identity metadata for channel-originated missions. Carries the
    # authenticated external account/session, never raw untrusted identifiers.
    remote: dict = field(default_factory=dict)
    status: MissionStatus = MissionStatus.DRAFT
    plan: MissionPlan | None = None
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime | None = None
    completed_at: datetime | None = None
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "prompt": self.prompt,
            "objectives": self.objectives,
            "deliverables": self.deliverables,
            "priority": self.priority.value,
            "execution_mode": self.execution_mode.value,
            "constraints": self.constraints,
            "preferred_agents": self.preferred_agents,
            "deadline": self.deadline.isoformat() if self.deadline else None,
            "tags": self.tags,
            "attachments": [a.to_dict() for a in self.attachments],
            "channel": self.channel,
            "remote": self.remote,
            "status": self.status.value,
            "plan": self.plan.to_dict() if self.plan else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
        }
