from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "EngineConfig",
    "EngineHealthState",
    "EngineInfo",
    "EngineType",
    "ExecutionEnginePort",
    "ExecutionEngineError",
    "EngineDiscoveryResult",
    "EngineCapabilities",
    "EngineTelemetry",
    "EngineCostEstimate",
    "EngineLatencyEstimate",
]


class EngineType(StrEnum):
    CLAUDE_CODE = "claude_code"
    GEMINI_CLI = "gemini_cli"
    CODEX_CLI = "codex_cli"
    HERMES = "hermes"
    OPENHANDS = "openhands"
    AIDER = "aider"
    CONTINUE = "continue"
    CLINE = "cline"
    ROO_CODE = "roo_code"
    LOCAL = "local"
    CUSTOM = "custom"


class EngineConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: EngineType
    name: str
    enabled: bool = True
    priority: int = Field(default=10, ge=1)
    binary_path: str | None = None
    version: str | None = None
    environment: dict[str, str] = Field(default_factory=dict)
    extra: dict[str, Any] = Field(default_factory=dict)


class EngineCapabilities(BaseModel):
    model_config = ConfigDict(frozen=True)

    supports_streaming: bool = False
    supports_cancellation: bool = True
    supports_sessions: bool = False
    supports_tools: bool = True
    supports_vision: bool = False
    max_concurrent_tasks: int = Field(default=1, ge=1)
    task_timeout_s: float = Field(default=600.0, ge=1.0)
    features: list[str] = Field(default_factory=list)


class EngineInfo(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: EngineType
    name: str
    display_name: str = ""
    version: str | None = None
    vendor: str | None = None
    description: str = ""
    capabilities: EngineCapabilities = Field(default_factory=EngineCapabilities)
    homepage: str | None = None
    docs_url: str | None = None
    license_info: str | None = None


class EngineHealthState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    engine: str
    engine_type: EngineType
    healthy: bool = True
    initialized: bool = False
    consecutive_failures: int = 0
    total_tasks: int = 0
    total_failures: int = 0
    last_error: str | None = None
    last_health_check: datetime | None = None

    def record_success(self) -> None:
        self.consecutive_failures = 0
        self.total_tasks += 1
        self.healthy = True

    def record_failure(self, error: str) -> None:
        self.consecutive_failures += 1
        self.total_tasks += 1
        self.total_failures += 1
        self.last_error = error
        if self.consecutive_failures >= 3:
            self.healthy = False


class EngineTelemetry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    engine: str
    engine_type: EngineType
    tasks_completed: int = 0
    tasks_failed: int = 0
    tasks_cancelled: int = 0
    total_duration_s: float = 0.0
    avg_duration_s: float = 0.0
    total_tokens_input: int = 0
    total_tokens_output: int = 0
    total_cost_usd: float = 0.0
    last_used: datetime | None = None


class EngineCostEstimate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    estimated_cost_usd: float = 0.0
    estimated_tokens_input: int = 0
    estimated_tokens_output: int = 0
    currency: str = "USD"
    breakdown: dict[str, float] = Field(default_factory=dict)


class EngineLatencyEstimate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    estimated_duration_s: float = 0.0
    p50_latency_s: float = 0.0
    p95_latency_s: float = 0.0
    p99_latency_s: float = 0.0
    based_on_samples: int = 0


class EngineDiscoveryResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    engine_type: EngineType
    name: str
    binary_path: str | None = None
    version: str | None = None
    found: bool = False
    healthy: bool = False
    error: str | None = None
    source: str = ""  # "path", "wsl", "docker", "registry", "config", "env"


@runtime_checkable
class ExecutionEnginePort(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def engine_type(self) -> EngineType: ...

    async def initialize(self, config: EngineConfig) -> None: ...

    async def shutdown(self) -> None: ...

    async def health_check(self) -> EngineHealthState: ...

    async def execute(self, task: Any) -> Any: ...

    async def cancel(self, task_id: str) -> bool: ...

    def stream(self, task: Any) -> AsyncIterator[Any]: ...

    async def benchmark(self) -> dict[str, Any]: ...

    async def version(self) -> str: ...

    @property
    def configuration(self) -> EngineConfig: ...

    async def telemetry(self) -> EngineTelemetry: ...

    async def discover_capabilities(self) -> EngineCapabilities: ...

    def supports(self, capability: str) -> bool: ...

    async def estimate_cost(self, task: Any) -> EngineCostEstimate: ...

    async def estimate_latency(self, task: Any) -> EngineLatencyEstimate: ...


class ExecutionEngineError(RuntimeError):
    def __init__(self, engine: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(f"[{engine}] {message}")
        self.engine = engine
        self.retryable = retryable
