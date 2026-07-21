"""
Execution Engine Domain Models

Domain layer for the Universal Execution Engine Framework - pure Python, no
external dependencies. Follows hexagonal architecture: domain depends on nothing.

Every execution engine — regardless of backend (MCP, Docker, WSL, subprocess,
cloud API) — is described by these types. The :class:`ExecutionEnginePort` in
``ports/execution.py`` is the single interface all engines must implement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4


def _utcnow() -> datetime:
    return datetime.now(UTC)


# ── Enums ──


class EngineType(StrEnum):
    """Classification of an execution engine's backend technology."""

    GENERIC = "generic"
    MCP = "mcp"
    DOCKER = "docker"
    WSL = "wsl"
    CLAUDE_CODE = "claude_code"
    HERMES = "hermes"
    OPENCODE = "opencode"
    CODEX = "codex"
    GEMINI_CLI = "gemini_cli"
    OPENHANDS = "openhands"
    CONTINUE = "continue"
    AIDER = "aider"
    GOOSE = "goose"
    CURSOR = "cursor"
    QWEN = "qwen"
    DEEPSEEK = "deepseek"
    GLM = "glm"
    OPEN_INTERPRETER = "open_interpreter"
    CLINE = "cline"
    ROO_CODE = "roo_code"
    OLLAMA = "ollama"
    OPENCODE = "opencode"
    AGY_CLI = "agy_cli"
    CUSTOM = "custom"

class EngineStatus(StrEnum):
    """Runtime lifecycle status of an execution engine."""

    CREATED = "created"
    INITIALIZING = "initializing"
    RUNNING = "running"
    BUSY = "busy"
    IDLE = "idle"
    PAUSED = "paused"
    STOPPED = "stopped"
    FAILED = "failed"
    RECOVERING = "recovering"
    UNKNOWN = "unknown"


class EngineCapability(StrEnum):
    """A discrete capability an execution engine can advertise.

    Engines declare their support for these capabilities during registration.
    The capability negotiator uses these to match execution requests to engines.
    """

    PLANNING = "planning"
    CODING = "coding"
    REASONING = "reasoning"
    RESEARCH = "research"
    TERMINAL = "terminal"
    GIT = "git"
    DOCKER = "docker"
    FILESYSTEM = "filesystem"
    VISION = "vision"
    MULTIMODAL = "multimodal"
    MCP = "mcp"
    STREAMING = "streaming"
    LARGE_CONTEXT = "large_context"
    OFFLINE = "offline"
    CLOUD = "cloud"


class EngineHealthStatus(StrEnum):
    """Health status of an execution engine."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class ExecutionStatus(StrEnum):
    """Runtime status of a single execution request."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"
    TIMEOUT = "timeout"


class ExecutionEventType(StrEnum):
    """Types of events emitted during engine execution."""

    ENGINE_REGISTERED = "engine.registered"
    ENGINE_INITIALIZED = "engine.initialized"
    ENGINE_SHUTDOWN = "engine.shutdown"
    ENGINE_HEALTH_CHANGED = "engine.health_changed"
    ENGINE_CAPABILITIES_CHANGED = "engine.capabilities_changed"
    ENGINE_ERROR = "engine.error"
    EXECUTION_STARTED = "execution.started"
    EXECUTION_COMPLETED = "execution.completed"
    EXECUTION_FAILED = "execution.failed"
    EXECUTION_CANCELLED = "execution.cancelled"
    BENCHMARK_STARTED = "benchmark.started"
    BENCHMARK_COMPLETED = "benchmark.completed"


# ── Domain Models ──


@dataclass(frozen=True, slots=True)
class ExecutionCapability:
    """A capability an execution engine provides, with optional metadata."""

    type: EngineCapability
    confidence: float = 1.0
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            "confidence": self.confidence,
            "description": self.description,
            "metadata": self.metadata,
        }

    @classmethod
    def from_type(cls, cap: EngineCapability, description: str = "") -> ExecutionCapability:
        return cls(type=cap, description=description or cap.value)


@dataclass(frozen=True, slots=True)
class ExecutionHealth:
    """Health snapshot for an execution engine."""

    status: EngineHealthStatus
    latency_ms: float = 0.0
    error: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    checked_at: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "latency_ms": self.latency_ms,
            "error": self.error,
            "details": self.details,
            "checked_at": self.checked_at.isoformat(),
        }

    @classmethod
    def healthy(cls, latency_ms: float = 0.0) -> ExecutionHealth:
        return cls(status=EngineHealthStatus.HEALTHY, latency_ms=latency_ms)

    @classmethod
    def unhealthy(cls, error: str) -> ExecutionHealth:
        return cls(status=EngineHealthStatus.UNHEALTHY, error=error)

    def with_status(self, status: EngineHealthStatus) -> ExecutionHealth:
        return ExecutionHealth(
            status=status,
            latency_ms=self.latency_ms,
            error=self.error,
            details=self.details,
            checked_at=_utcnow(),
        )


@dataclass(frozen=True, slots=True)
class ExecutionMetrics:
    """Metrics snapshot from an engine execution."""

    duration_ms: float = 0.0
    cpu_percent: float = 0.0
    memory_mb: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    cost: float = 0.0
    custom: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "duration_ms": self.duration_ms,
            "cpu_percent": self.cpu_percent,
            "memory_mb": self.memory_mb,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "cost": self.cost,
            "custom": self.custom,
        }


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    """Result of a single execution request against an engine."""

    execution_id: str
    status: ExecutionStatus
    output: Any = None
    error: str | None = None
    metrics: ExecutionMetrics = field(default_factory=ExecutionMetrics)
    started_at: datetime = field(default_factory=_utcnow)
    completed_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "status": self.status.value,
            "output": self.output,
            "error": self.error,
            "metrics": self.metrics.to_dict(),
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }

    def with_completed(
        self, output: Any, metrics: ExecutionMetrics | None = None
    ) -> ExecutionResult:
        return ExecutionResult(
            execution_id=self.execution_id,
            status=ExecutionStatus.COMPLETED,
            output=output,
            metrics=metrics or self.metrics,
            started_at=self.started_at,
            completed_at=_utcnow(),
        )

    def with_failed(self, error: str) -> ExecutionResult:
        return ExecutionResult(
            execution_id=self.execution_id,
            status=ExecutionStatus.FAILED,
            error=error,
            started_at=self.started_at,
            completed_at=_utcnow(),
        )


@dataclass(frozen=True, slots=True)
class ExecutionSession:
    """A logical execution session tied to an engine."""

    engine_id: str
    id: str = field(default_factory=lambda: uuid4().hex)
    status: ExecutionStatus = ExecutionStatus.PENDING
    request: dict[str, Any] = field(default_factory=dict)
    result: ExecutionResult | None = None
    started_at: datetime = field(default_factory=_utcnow)
    completed_at: datetime | None = None
    parent_session_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "engine_id": self.engine_id,
            "status": self.status.value,
            "request": self.request,
            "result": self.result.to_dict() if self.result else None,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "parent_session_id": self.parent_session_id,
            "metadata": self.metadata,
        }

    def with_status(self, status: ExecutionStatus) -> ExecutionSession:
        return ExecutionSession(
            id=self.id,
            engine_id=self.engine_id,
            status=status,
            request=self.request,
            result=self.result,
            started_at=self.started_at,
            completed_at=_utcnow()
            if status
            in (ExecutionStatus.COMPLETED, ExecutionStatus.FAILED, ExecutionStatus.CANCELLED)
            else None,
            parent_session_id=self.parent_session_id,
            metadata=self.metadata,
        )

    def with_result(self, result: ExecutionResult) -> ExecutionSession:
        return ExecutionSession(
            id=self.id,
            engine_id=self.engine_id,
            status=result.status,
            request=self.request,
            result=result,
            started_at=self.started_at,
            completed_at=result.completed_at,
            parent_session_id=self.parent_session_id,
            metadata=self.metadata,
        )


@dataclass(frozen=True, slots=True)
class ExecutionWorkspace:
    """Workspace information for an execution engine."""

    path: str = ""
    environment: dict[str, str] = field(default_factory=dict)
    mounts: list[dict[str, str]] = field(default_factory=list)
    constraints: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "environment": self.environment,
            "mounts": self.mounts,
            "constraints": self.constraints,
        }


@dataclass(frozen=True, slots=True)
class ExecutionTelemetry:
    """A telemetry data point collected from an engine."""

    engine_id: str
    metric_name: str
    value: float
    labels: dict[str, str] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=_utcnow)
    unit: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "engine_id": self.engine_id,
            "metric_name": self.metric_name,
            "value": self.value,
            "labels": self.labels,
            "timestamp": self.timestamp.isoformat(),
            "unit": self.unit,
        }


@dataclass(frozen=True, slots=True)
class ExecutionBenchmark:
    """Results of a benchmark run against an execution engine."""

    engine_id: str
    benchmark_type: str  # "latency", "throughput", "capability", "custom"
    score: float
    id: str = field(default_factory=lambda: uuid4().hex)
    metrics: dict[str, float] = field(default_factory=dict)
    started_at: datetime = field(default_factory=_utcnow)
    completed_at: datetime | None = None
    config: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "engine_id": self.engine_id,
            "benchmark_type": self.benchmark_type,
            "score": self.score,
            "metrics": self.metrics,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "config": self.config,
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class ExecutionConfiguration:
    """Configuration parameters for an execution engine."""

    engine_id: str
    settings: dict[str, Any] = field(default_factory=dict)
    version: str = "1.0.0"
    updated_at: datetime = field(default_factory=_utcnow)
    updated_by: str = "system"

    def to_dict(self) -> dict[str, Any]:
        return {
            "engine_id": self.engine_id,
            "settings": self.settings,
            "version": self.version,
            "updated_at": self.updated_at.isoformat(),
            "updated_by": self.updated_by,
        }

    def with_settings(self, settings: dict[str, Any]) -> ExecutionConfiguration:
        return ExecutionConfiguration(
            engine_id=self.engine_id,
            settings=settings,
            version=self.version,
            updated_at=_utcnow(),
            updated_by=self.updated_by,
        )


@dataclass(frozen=True, slots=True)
class ExecutionProfile:
    """A named configuration profile for an execution engine.

    Profiles allow users to save and switch between different engine
    configurations (e.g. "fast", "cheap", "high-quality").
    """

    name: str
    engine_type: EngineType
    id: str = field(default_factory=lambda: uuid4().hex)
    capabilities: tuple[ExecutionCapability, ...] = field(default_factory=tuple)
    config: ExecutionConfiguration | None = None
    description: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)
    created_by: str = "system"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "engine_type": self.engine_type.value,
            "capabilities": [c.to_dict() for c in self.capabilities],
            "config": self.config.to_dict() if self.config else None,
            "description": self.description,
            "tags": list(self.tags),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "created_by": self.created_by,
        }

    def with_capabilities(self, caps: list[ExecutionCapability]) -> ExecutionProfile:
        return ExecutionProfile(
            id=self.id,
            name=self.name,
            engine_type=self.engine_type,
            capabilities=tuple(caps),
            config=self.config,
            description=self.description,
            tags=self.tags,
            created_at=self.created_at,
            updated_at=_utcnow(),
            created_by=self.created_by,
        )


@dataclass(frozen=True, slots=True)
class ExecutionEvent:
    """An event emitted during engine or execution lifecycle."""

    event_type: ExecutionEventType
    engine_id: str
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=_utcnow)
    session_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type.value,
            "engine_id": self.engine_id,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
            "session_id": self.session_id,
        }


@dataclass(frozen=True, slots=True)
class ExecutionEngine:
    """
    Core entity representing an execution engine instance.

    This is the central domain object for the Universal Execution Engine
    Framework. Every engine — whether MCP, Docker, WSL, or custom — is
    represented by an instance of this type.
    """

    id: str = field(default_factory=lambda: uuid4().hex)
    name: str = ""
    engine_type: EngineType = EngineType.GENERIC
    status: EngineStatus = EngineStatus.CREATED
    capabilities: tuple[ExecutionCapability, ...] = field(default_factory=tuple)
    version: str = "1.0.0"
    description: str = ""
    transport: str = "local"
    endpoint: str | None = None
    health: ExecutionHealth = field(
        default_factory=lambda: ExecutionHealth(status=EngineHealthStatus.UNKNOWN)
    )
    profile: ExecutionProfile | None = None
    config: ExecutionConfiguration | None = None
    workspace: ExecutionWorkspace = field(default_factory=ExecutionWorkspace)
    tags: tuple[str, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)
    created_by: str = "system"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "engine_type": self.engine_type.value,
            "status": self.status.value,
            "capabilities": [c.to_dict() for c in self.capabilities],
            "version": self.version,
            "description": self.description,
            "transport": self.transport,
            "endpoint": self.endpoint,
            "health": self.health.to_dict(),
            "profile": self.profile.to_dict() if self.profile else None,
            "config": self.config.to_dict() if self.config else None,
            "workspace": self.workspace.to_dict(),
            "tags": list(self.tags),
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "created_by": self.created_by,
        }

    # ── Immutable update helpers ──

    def with_status(self, status: EngineStatus) -> ExecutionEngine:
        return ExecutionEngine(
            id=self.id,
            name=self.name,
            engine_type=self.engine_type,
            status=status,
            capabilities=self.capabilities,
            version=self.version,
            description=self.description,
            transport=self.transport,
            endpoint=self.endpoint,
            health=self.health,
            profile=self.profile,
            config=self.config,
            workspace=self.workspace,
            tags=self.tags,
            metadata=self.metadata,
            created_at=self.created_at,
            updated_at=_utcnow(),
            created_by=self.created_by,
        )

    def with_capabilities(self, caps: list[ExecutionCapability]) -> ExecutionEngine:
        return ExecutionEngine(
            id=self.id,
            name=self.name,
            engine_type=self.engine_type,
            status=self.status,
            capabilities=tuple(caps),
            version=self.version,
            description=self.description,
            transport=self.transport,
            endpoint=self.endpoint,
            health=self.health,
            profile=self.profile,
            config=self.config,
            workspace=self.workspace,
            tags=self.tags,
            metadata=self.metadata,
            created_at=self.created_at,
            updated_at=_utcnow(),
            created_by=self.created_by,
        )

    def with_health(self, health: ExecutionHealth) -> ExecutionEngine:
        return ExecutionEngine(
            id=self.id,
            name=self.name,
            engine_type=self.engine_type,
            status=self.status,
            capabilities=self.capabilities,
            version=self.version,
            description=self.description,
            transport=self.transport,
            endpoint=self.endpoint,
            health=health,
            profile=self.profile,
            config=self.config,
            workspace=self.workspace,
            tags=self.tags,
            metadata=self.metadata,
            created_at=self.created_at,
            updated_at=_utcnow(),
            created_by=self.created_by,
        )

    def with_config(self, config: ExecutionConfiguration) -> ExecutionEngine:
        return ExecutionEngine(
            id=self.id,
            name=self.name,
            engine_type=self.engine_type,
            status=self.status,
            capabilities=self.capabilities,
            version=self.version,
            description=self.description,
            transport=self.transport,
            endpoint=self.endpoint,
            health=self.health,
            profile=self.profile,
            config=config,
            workspace=self.workspace,
            tags=self.tags,
            metadata=self.metadata,
            created_at=self.created_at,
            updated_at=_utcnow(),
            created_by=self.created_by,
        )

    def with_profile(self, profile: ExecutionProfile) -> ExecutionEngine:
        return ExecutionEngine(
            id=self.id,
            name=self.name,
            engine_type=self.engine_type,
            status=self.status,
            capabilities=self.capabilities,
            version=self.version,
            description=self.description,
            transport=self.transport,
            endpoint=self.endpoint,
            health=self.health,
            profile=profile,
            config=self.config,
            workspace=self.workspace,
            tags=self.tags,
            metadata=self.metadata,
            created_at=self.created_at,
            updated_at=_utcnow(),
            created_by=self.created_by,
        )

    def is_online(self) -> bool:
        return self.status in (EngineStatus.RUNNING, EngineStatus.IDLE, EngineStatus.BUSY)

    def supports_capability(self, cap: EngineCapability) -> bool:
        return any(c.type == cap for c in self.capabilities)


@dataclass(frozen=True, slots=True)
class EngineRegistry:
    """Snapshot of all registered execution engines."""

    engines: tuple[ExecutionEngine, ...] = field(default_factory=tuple)
    updated_at: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "engines": [e.to_dict() for e in self.engines],
            "updated_at": self.updated_at.isoformat(),
            "total": len(self.engines),
        }

    def get_engine(self, engine_id: str) -> ExecutionEngine | None:
        for e in self.engines:
            if e.id == engine_id:
                return e
        return None

    def get_engine_by_name(self, name: str) -> ExecutionEngine | None:
        for e in self.engines:
            if e.name == name:
                return e
        return None

    def with_engine(self, engine: ExecutionEngine) -> EngineRegistry:
        existing = [e for e in self.engines if e.id != engine.id]
        return EngineRegistry(
            engines=tuple(existing) + (engine,),
            updated_at=_utcnow(),
        )

    def without_engine(self, engine_id: str) -> EngineRegistry:
        return EngineRegistry(
            engines=tuple(e for e in self.engines if e.id != engine_id),
            updated_at=_utcnow(),
        )

    def list_by_status(self, status: EngineStatus) -> list[ExecutionEngine]:
        return [e for e in self.engines if e.status == status]

    def list_by_capability(self, cap: EngineCapability) -> list[ExecutionEngine]:
        return [e for e in self.engines if e.supports_capability(cap)]

    def list_by_type(self, engine_type: EngineType) -> list[ExecutionEngine]:
        return [e for e in self.engines if e.engine_type == engine_type]

    def list_online(self) -> list[ExecutionEngine]:
        return [e for e in self.engines if e.is_online()]


__all__ = [
    "EngineType",
    "EngineStatus",
    "EngineCapability",
    "EngineHealthStatus",
    "ExecutionStatus",
    "ExecutionEventType",
    "ExecutionCapability",
    "ExecutionHealth",
    "ExecutionMetrics",
    "ExecutionResult",
    "ExecutionSession",
    "ExecutionWorkspace",
    "ExecutionTelemetry",
    "ExecutionBenchmark",
    "ExecutionConfiguration",
    "ExecutionProfile",
    "ExecutionEvent",
    "ExecutionEngine",
    "EngineRegistry",
]
