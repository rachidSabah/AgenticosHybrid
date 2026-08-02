"""Universal Runtime domain model — single abstraction for all executable runtimes."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _new_id() -> str:
    return uuid.uuid4().hex[:16]


# ── Enums ───────────────────────────────────────────────────────────────────


class RuntimeType(StrEnum):
    """All supported runtime types."""

    CUSTOM = "custom"
    CLAUDE_CODE = "claude_code"
    HERMES = "hermes"
    CODEX_CLI = "codex_cli"
    GEMINI_CLI = "gemini_cli"
    AIDER = "aider"
    OPENCODE = "opencode"
    OPENHANDS = "openhands"
    CURSOR_AGENT = "cursor_agent"
    GOOSE = "goose"
    ROO_CODE = "roo_code"
    CLINE = "cline"
    QWEN_CODE = "qwen_code"
    AMP = "amp"
    WARP_AGENT = "warp_agent"
    MCP_SERVER = "mcp_server"
    PYTHON = "python"
    NODE = "node"
    DOCKER = "docker"
    GIT = "git"
    BINARY = "binary"
    SCRIPT = "script"
    CUSTOM_AGENT = "custom_agent"


class RuntimeStatus(StrEnum):
    """Runtime lifecycle states."""

    DISCOVERED = "discovered"
    REGISTERED = "registered"
    INITIALIZING = "initializing"
    STARTING = "starting"
    READY = "ready"
    BUSY = "busy"
    IDLE = "idle"
    STREAMING = "streaming"
    WAITING = "waiting"
    STOPPING = "stopping"
    STOPPED = "stopped"
    CRASHED = "crashed"
    FAILED = "failed"
    RESTARTING = "restarting"
    UPDATING = "updating"
    DISCONNECTED = "disconnected"
    UNKNOWN = "unknown"


class RuntimeHealth(StrEnum):
    """Health status values."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"
    STARTING = "starting"
    STOPPED = "stopped"


class RestartPolicy(StrEnum):
    """Restart policy types."""

    NEVER = "never"
    ALWAYS = "always"
    ON_FAILURE = "on_failure"
    ON_CRASH = "on_crash"
    BACKOFF = "backoff"


# ── Core Model ──────────────────────────────────────────────────────────────


@dataclass
class RuntimeCapability:
    """A single capability of a runtime."""

    name: str
    version: str | None = None
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RuntimeMetrics:
    """O(1) snapshot of runtime metrics."""

    cpu_percent: float = 0.0
    memory_mb: float = 0.0
    threads: int = 0
    tokens_used: int = 0
    cost: float = 0.0
    latency_ms: float = 0.0
    queue_depth: int = 0
    active_tasks: int = 0
    restart_count: int = 0
    crash_count: int = 0
    uptime_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "cpu_percent": self.cpu_percent,
            "memory_mb": self.memory_mb,
            "threads": self.threads,
            "tokens_used": self.tokens_used,
            "cost": self.cost,
            "latency_ms": self.latency_ms,
            "queue_depth": self.queue_depth,
            "active_tasks": self.active_tasks,
            "restart_count": self.restart_count,
            "crash_count": self.crash_count,
            "uptime_seconds": self.uptime_seconds,
        }

    @staticmethod
    def from_dict(d: dict[str, Any]) -> RuntimeMetrics:
        return RuntimeMetrics(
            **{k: v for k, v in d.items() if k in RuntimeMetrics.__dataclass_fields__}
        )


@dataclass
class RuntimeSession:
    """A named session attached to a runtime."""

    session_id: str = field(default_factory=_new_id)
    name: str = ""
    terminal_id: str | None = None
    working_directory: str | None = None
    environment: dict[str, str] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utcnow)
    last_active: datetime = field(default_factory=_utcnow)
    closed_at: datetime | None = None
    command_history: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    active: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "name": self.name,
            "terminal_id": self.terminal_id,
            "working_directory": self.working_directory,
            "environment": self.environment,
            "created_at": self.created_at.isoformat(),
            "last_active": self.last_active.isoformat(),
            "closed_at": self.closed_at.isoformat() if self.closed_at else None,
            "command_history": self.command_history[-50:],
            "metadata": self.metadata,
            "active": self.active,
        }


@dataclass
class RuntimeLog:
    """A single log entry."""

    timestamp: datetime = field(default_factory=_utcnow)
    stream: str = "stdout"  # stdout, stderr, system
    text: str = ""
    level: str = "info"  # info, warn, error, debug
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "stream": self.stream,
            "text": self.text,
            "level": self.level,
        }


@dataclass
class Runtime:
    """Universal runtime model — single abstraction for every executable runtime.

    All fields defined in the Phase 6.3 spec are represented. The model uses
    immutable-style dataclass with thread-safe snapshot semantics.
    """

    # ── Identity ──
    id: str = field(default_factory=_new_id)
    name: str = ""
    brain_id: str | None = None
    provider: str = "local"

    # ── Typing ──
    type: RuntimeType = RuntimeType.CUSTOM
    version: str | None = None

    # ── Process ──
    pid: int | None = None
    status: RuntimeStatus = RuntimeStatus.DISCOVERED
    health: RuntimeHealth = RuntimeHealth.UNKNOWN
    started_at: datetime | None = None
    uptime: float = 0.0

    # ── Resource ──
    cpu: float = 0.0
    memory: float = 0.0
    threads: int = 0

    # ── Launch ──
    command: str = ""
    arguments: list[str] = field(default_factory=list)
    working_directory: str | None = None
    environment: dict[str, str] = field(default_factory=dict)

    # ── Terminal / Session ──
    terminal: str | None = None
    session_id: str | None = None
    active_session: RuntimeSession | None = None
    sessions: list[RuntimeSession] = field(default_factory=list)

    # ── Lifecycle ──
    restart_count: int = 0
    crash_count: int = 0
    last_error: str | None = None
    last_exit_code: int | None = None
    last_seen: datetime | None = None
    heartbeat: datetime | None = None

    # ── Capabilities ──
    capabilities: list[RuntimeCapability] = field(default_factory=list)
    supported_models: list[str] = field(default_factory=list)

    # ── Tasks ──
    active_tasks: int = 0
    queue_depth: int = 0

    # ── Token / Cost ──
    tokens_used: int = 0
    cost: float = 0.0
    latency: float = 0.0

    # ── Streaming ──
    streaming: bool = False

    # ── Logs ──
    logs: list[RuntimeLog] = field(default_factory=list)
    metrics: RuntimeMetrics = field(default_factory=RuntimeMetrics)

    # ── Discovery ──
    discovered: bool = False
    binary_path: str | None = None
    executable: str | None = None
    source: str = "manual"

    # ── Metadata ──
    metadata: dict[str, Any] = field(default_factory=dict)

    # ── Internal ──
    _exit_code: int | None = None
    _error: str | None = None

    # ── Serialization ──

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for JSON responses."""
        return {
            "id": self.id,
            "name": self.name,
            "brain_id": self.brain_id,
            "provider": self.provider,
            "type": self.type.value,
            "version": self.version,
            "pid": self.pid,
            "status": self.status.value,
            "health": self.health.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "uptime": self.uptime,
            "cpu": self.cpu,
            "memory": self.memory,
            "threads": self.threads,
            "command": self.command,
            "arguments": self.arguments,
            "working_directory": self.working_directory,
            "environment": self.environment,
            "terminal": self.terminal,
            "session_id": self.session_id,
            "active_session": self.active_session.to_dict() if self.active_session else None,
            "sessions": [s.to_dict() for s in self.sessions[-10:]],
            "restart_count": self.restart_count,
            "crash_count": self.crash_count,
            "last_error": self.last_error,
            "last_exit_code": self.last_exit_code,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "heartbeat": self.heartbeat.isoformat() if self.heartbeat else None,
            "capabilities": [
                {"name": c.name, "version": c.version, "enabled": c.enabled}
                for c in self.capabilities
            ],
            "supported_models": self.supported_models,
            "active_tasks": self.active_tasks,
            "queue_depth": self.queue_depth,
            "tokens_used": self.tokens_used,
            "cost": self.cost,
            "latency": self.latency,
            "streaming": self.streaming,
            "logs": [log.to_dict() for log in self.logs[-100:]],
            "metrics": self.metrics.to_dict(),
            "binary_path": self.binary_path,
            "executable": self.executable,
            "source": self.source,
            "discovered": self.discovered,
            "metadata": self.metadata,
        }

    def to_snapshot(self) -> dict[str, Any]:
        """Immutable point-in-time snapshot (shallow copy of to_dict)."""
        d = self.to_dict()
        d["_snapshot_at"] = _utcnow().isoformat()
        return d

    @staticmethod
    def from_dict(d: dict[str, Any]) -> Runtime:
        """Create a Runtime from a serialized dict (JSON round-trip)."""
        fields: dict[str, Any] = {
            "id": d.get("id", _new_id()),
            "name": d.get("name", ""),
            "brain_id": d.get("brain_id"),
            "provider": d.get("provider", "local"),
            "type": RuntimeType(d.get("type", "custom")) if d.get("type") else RuntimeType.CUSTOM,
            "version": d.get("version"),
            "pid": d.get("pid"),
            "status": RuntimeStatus(d.get("status", "discovered")),
            "health": RuntimeHealth(d.get("health", "unknown")),
            "command": d.get("command", ""),
            "arguments": d.get("arguments", []),
            "working_directory": d.get("working_directory"),
            "environment": d.get("environment", {}),
            "restart_count": d.get("restart_count", 0),
            "crash_count": d.get("crash_count", 0),
            "last_error": d.get("last_error"),
            "last_exit_code": d.get("last_exit_code"),
            "active_tasks": d.get("active_tasks", 0),
            "queue_depth": d.get("queue_depth", 0),
            "tokens_used": d.get("tokens_used", 0),
            "cost": d.get("cost", 0.0),
            "latency": d.get("latency", 0.0),
            "streaming": d.get("streaming", False),
            "binary_path": d.get("binary_path"),
            "executable": d.get("executable"),
            "source": d.get("source", "manual"),
            "discovered": d.get("discovered", False),
            "metadata": d.get("metadata", {}),
        }
        caps = d.get("capabilities", [])
        if caps and isinstance(caps[0], dict):
            fields["capabilities"] = [RuntimeCapability(**c) for c in caps]
        fields["supported_models"] = d.get("supported_models", [])
        if d.get("metrics"):
            fields["metrics"] = RuntimeMetrics.from_dict(d["metrics"])
        return Runtime(**fields)  # type: ignore[arg-type]
