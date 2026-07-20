from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from core.contracts.execution_engine import EngineType

__all__ = [
    "ExecutionTask",
    "ExecutionTaskStatus",
    "ExecutionTaskPriority",
    "ExecutionSession",
    "ExecutionSessionStatus",
    "ExecutionMetrics",
    "ExecutionBenchmarkResult",
    "ExecutionPlan",
]


class ExecutionTaskStatus(StrEnum):
    PENDING = "pending"
    QUEUED = "queued"
    DISPATCHED = "dispatched"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


class ExecutionTaskPriority(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"
    BACKGROUND = "background"


class ExecutionSessionStatus(StrEnum):
    CREATED = "created"
    ACTIVE = "active"
    IDLE = "idle"
    CLOSED = "closed"
    ERROR = "error"


@dataclass
class ExecutionTask:
    task_id: str = field(default_factory=lambda: uuid4().hex[:16])
    engine_type: EngineType = EngineType.LOCAL
    engine_name: str = ""
    goal: str = ""
    input: dict[str, Any] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)
    priority: ExecutionTaskPriority = ExecutionTaskPriority.NORMAL
    status: ExecutionTaskStatus = ExecutionTaskStatus.PENDING
    session_id: str | None = None
    timeout_s: float = 600.0
    max_retries: int = 2
    retry_count: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_s: float = 0.0
    output: Any = None
    error: str | None = None
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "engine_type": self.engine_type.value,
            "engine_name": self.engine_name,
            "goal": self.goal,
            "priority": self.priority.value,
            "status": self.status.value,
            "session_id": self.session_id,
            "timeout_s": self.timeout_s,
            "retry_count": self.retry_count,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_s": round(self.duration_s, 4),
            "error": self.error,
            "tags": list(self.tags),
        }


@dataclass
class ExecutionSession:
    session_id: str = field(default_factory=lambda: uuid4().hex[:16])
    engine_type: EngineType = EngineType.LOCAL
    engine_name: str = ""
    status: ExecutionSessionStatus = ExecutionSessionStatus.CREATED
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_active_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    closed_at: datetime | None = None
    task_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionMetrics:
    engine_type: EngineType = EngineType.LOCAL
    engine_name: str = ""
    tasks_completed: int = 0
    tasks_failed: int = 0
    tasks_cancelled: int = 0
    tasks_timed_out: int = 0
    total_duration_s: float = 0.0
    avg_duration_s: float = 0.0
    total_tokens_input: int = 0
    total_tokens_output: int = 0
    total_cost_usd: float = 0.0
    last_execution: datetime | None = None

    def record_task(self, duration_s: float, success: bool, tokens_input: int = 0, tokens_output: int = 0, cost_usd: float = 0.0) -> None:
        if success:
            self.tasks_completed += 1
        else:
            self.tasks_failed += 1
        self.total_duration_s += duration_s
        self.total_tokens_input += tokens_input
        self.total_tokens_output += tokens_output
        self.total_cost_usd += cost_usd
        self.last_execution = datetime.now(UTC)
        total = self.tasks_completed + self.tasks_failed + self.tasks_cancelled + self.tasks_timed_out
        self.avg_duration_s = self.total_duration_s / max(1, total)


@dataclass
class ExecutionBenchmarkResult:
    benchmark_id: str = field(default_factory=lambda: uuid4().hex[:16])
    engine_type: EngineType = EngineType.LOCAL
    engine_name: str = ""
    tasks_run: int = 0
    tasks_passed: int = 0
    tasks_failed: int = 0
    avg_duration_s: float = 0.0
    p50_duration_s: float = 0.0
    p95_duration_s: float = 0.0
    p99_duration_s: float = 0.0
    total_duration_s: float = 0.0
    error_rate: float = 0.0
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionPlan:
    plan_id: str = field(default_factory=lambda: uuid4().hex[:12])
    goal: str = ""
    tasks: list[ExecutionTask] = field(default_factory=list)
    routing_strategy: str = "fastest"
    fallback_engines: list[EngineType] = field(default_factory=list)
    max_retries: int = 2
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
