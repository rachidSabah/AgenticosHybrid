"""
Execution Engine Ports

Defines the universal execution engine interface and runtime manager contract.
Domain logic depends on these interfaces, never on implementations.

Every execution engine — MCP, Docker, WSL, Claude Code, subprocess, cloud API —
implements :class:`ExecutionEnginePort`. The kernel only imports this port.
"""

from __future__ import annotations


from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from agentic_os.domain.execution import (
    EngineCapability,
    EngineType,
    ExecutionBenchmark,
    ExecutionCapability,
    ExecutionConfiguration,
    ExecutionEngine,
    ExecutionEvent,
    ExecutionHealth,
    ExecutionProfile,
    ExecutionResult,
    ExecutionSession,
    ExecutionWorkspace,
)

# ── Input DTOs ──


@dataclass(frozen=True, slots=True)
class EngineRegistration:
    """Input for registering a new execution engine."""

    name: str
    engine_type: EngineType = EngineType.GENERIC
    endpoint: str | None = None
    transport: str = "local"
    capabilities: list[EngineCapability] = field(default_factory=list)
    description: str = ""
    version: str = "1.0.0"
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class EngineUpdate:
    """Partial update for an execution engine registration."""

    name: str | None = None
    endpoint: str | None = None
    transport: str | None = None
    description: str | None = None
    version: str | None = None
    tags: list[str] | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class ExecutionRequest:
    """Input for executing an action on an execution engine."""

    action: str
    payload: dict[str, Any] = field(default_factory=dict)
    timeout_seconds: float = 60.0
    stream: bool = False
    parent_session_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ExecutionQuery:
    """Filter and sort parameters for querying execution history."""

    engine_id: str | None = None
    status: str | None = None
    limit: int = 50
    offset: int = 0
    sort_by: str = "started_at"
    sort_desc: bool = True


@dataclass(frozen=True, slots=True)
class DiscoveryConfig:
    """Configuration for a discovery provider."""

    enabled: bool = True
    interval_seconds: float = 60.0
    timeout_seconds: float = 10.0
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class EngineSummary:
    """Lightweight engine summary for listing."""

    id: str
    name: str
    engine_type: str
    status: str
    version: str
    capabilities: list[str]
    health_status: str
    latency_ms: float
    endpoint: str | None = None

    @classmethod
    def from_engine(cls, engine: ExecutionEngine) -> EngineSummary:
        return cls(
            id=engine.id,
            name=engine.name,
            engine_type=engine.engine_type.value,
            status=engine.status.value,
            version=engine.version,
            capabilities=[c.type.value for c in engine.capabilities],
            health_status=engine.health.status.value,
            latency_ms=engine.health.latency_ms,
            endpoint=engine.endpoint,
        )


@dataclass(frozen=True, slots=True)
class EngineDetail:
    """Full engine detail including config, workspace, and profile."""

    engine: ExecutionEngine
    recent_sessions: list[ExecutionSession] = field(default_factory=list)
    config: ExecutionConfiguration | None = None
    workspace: ExecutionWorkspace | None = None
    profile: ExecutionProfile | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "engine": self.engine.to_dict(),
            "recent_sessions": [s.to_dict() for s in self.recent_sessions],
            "config": self.config.to_dict() if self.config else None,
            "workspace": self.workspace.to_dict() if self.workspace else None,
            "profile": self.profile.to_dict() if self.profile else None,
        }


# ── Ports ──


@runtime_checkable
class ExecutionEnginePort(Protocol):
    """Universal interface every execution engine must implement.

    Engines implement ALL 22 methods. Default implementations are provided by
    :class:`~agentic_os.core.runtime.engine.ExecutionEngineBase` for optional methods.
    """

    # ── Lifecycle ──

    async def initialize(self) -> ExecutionEngine:
        """Start the engine and return its engine descriptor."""
        ...

    async def shutdown(self) -> None:
        """Cleanly stop the engine and release resources."""
        ...

    # ── Discovery & Health ──

    async def health_check(self) -> ExecutionHealth:
        """Return current health status with latency."""
        ...

    # ── Execution ──

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """Execute an action on this engine."""
        ...

    async def cancel(self, execution_id: str) -> bool:
        """Cancel a running execution. Returns True if cancelled."""
        ...

    async def pause(self, execution_id: str) -> bool:
        """Pause a running execution. Returns True if paused."""
        ...

    async def resume(self, execution_id: str) -> bool:
        """Resume a paused execution. Returns True if resumed."""
        ...

    async def stream(self, execution_id: str) -> AsyncIterator[bytes]:
        """Stream live output from a running execution."""
        ...

    # ── Performance ──

    async def benchmark(self, config: dict[str, Any] | None = None) -> ExecutionBenchmark:
        """Run a benchmark and return metrics."""
        ...

    async def telemetry(self) -> list[ExecutionEvent]:
        """Return runtime telemetry data points."""
        ...

    # ── Metadata ──

    async def get_version(self) -> str:
        """Return the engine's software version."""
        ...

    async def get_configuration(self) -> ExecutionConfiguration:
        """Return current configuration snapshot."""
        ...

    async def get_descriptor(self) -> ExecutionEngine:
        """Return the full engine descriptor."""
        ...

    async def get_capabilities(self) -> list[ExecutionCapability]:
        """Return advertised capabilities."""
        ...

    # ── Compatibility ──

    async def supports(self, capability: EngineCapability) -> bool:
        """Check if this engine supports a given capability."""
        ...

    async def estimate_cost(self, request: ExecutionRequest) -> float:
        """Predict cost for executing a given request."""
        ...

    async def estimate_latency(self, request: ExecutionRequest) -> float:
        """Predict latency for executing a given request."""
        ...

    # ── Workspace ──

    async def get_workspace(self) -> ExecutionWorkspace:
        """Return workspace information (cwd, env, mounts)."""
        ...

    # ── Recovery ──

    async def interrupt(self, execution_id: str) -> bool:
        """Hard-interrupt a running execution. Returns True if interrupted."""
        ...

    async def recover(self, execution_id: str, timeout_seconds: float = 30.0) -> ExecutionResult:
        """Attempt to recover an execution after a crash."""
        ...


@runtime_checkable
class RuntimeManagerPort(Protocol):
    """High-level interface for managing execution engines.

    The kernel wires a RuntimeManager that implements this port.
    """

    # ── Engine lifecycle ──

    async def register_engine(self, registration: EngineRegistration) -> ExecutionEngine:
        """Register a new execution engine from its descriptor."""
        ...

    async def register_from_adapter(
        self, engine_id: str, adapter: ExecutionEnginePort
    ) -> ExecutionEngine:
        """Register a live adapter instance."""
        ...

    async def get_engine(self, engine_id: str) -> ExecutionEngine | None:
        """Look up an engine by ID."""
        ...

    async def list_engines(
        self,
        engine_type: EngineType | None = None,
        capability: EngineCapability | None = None,
        status: str | None = None,
    ) -> list[ExecutionEngine]:
        """List engines, optionally filtered."""
        ...

    async def update_engine(self, engine_id: str, update: EngineUpdate) -> ExecutionEngine | None:
        """Update an engine's metadata."""
        ...

    async def unregister_engine(self, engine_id: str) -> bool:
        """Unregister an engine. Returns True if removed."""
        ...

    # ── Discovery ──

    async def discover_engines(self) -> list[ExecutionEngine]:
        """Run discovery providers and register found engines."""
        ...

    # ── Execution ──

    async def execute(
        self,
        engine_id: str,
        request: ExecutionRequest,
    ) -> ExecutionResult:
        """Execute on a specific engine."""
        ...

    async def execute_on_best(
        self,
        request: ExecutionRequest,
        required_capability: EngineCapability | None = None,
    ) -> ExecutionResult:
        """Execute on the best-matching engine for the capability."""
        ...

    async def cancel_execution(self, engine_id: str, execution_id: str) -> bool:
        """Cancel execution on a specific engine."""
        ...

    async def pause_execution(self, engine_id: str, execution_id: str) -> bool:
        """Pause execution on a specific engine."""
        ...

    async def resume_execution(self, engine_id: str, execution_id: str) -> bool:
        """Resume execution on a specific engine."""
        ...

    # ── Health & Benchmark ──

    async def health_check(self, engine_id: str) -> ExecutionHealth:
        """Check health of a specific engine."""
        ...

    async def benchmark(
        self, engine_id: str, config: dict[str, Any] | None = None
    ) -> ExecutionBenchmark:
        """Run benchmark on a specific engine."""
        ...

    async def health_check_all(self) -> dict[str, ExecutionHealth]:
        """Check health of all registered engines."""
        ...

    # ── Query & Search ──

    async def find_engines(
        self,
        capability: EngineCapability,
        min_confidence: float = 0.0,
    ) -> list[ExecutionEngine]:
        """Find engines matching a capability."""
        ...

    async def list_capabilities(self) -> dict[str, list[ExecutionCapability]]:
        """Return all registered capabilities grouped by engine ID."""
        ...

    # ── Sessions ──

    async def get_session(self, engine_id: str, session_id: str) -> ExecutionSession | None:
        """Get an execution session."""
        ...

    async def list_sessions(
        self,
        engine_id: str | None = None,
        limit: int = 50,
    ) -> list[ExecutionSession]:
        """List execution sessions, optionally filtered by engine."""
        ...

    # ── System ──

    async def initialize(self) -> None:
        """Initialize the runtime — start discovery, register found engines."""
        ...

    async def shutdown(self) -> None:
        """Shutdown all engines and release resources."""
        ...

    async def get_adapter(self, engine_id: str) -> ExecutionEnginePort | None:
        """Get the live adapter instance for an engine."""
        ...

    async def get_registry_snapshot(self) -> dict:
        """Return a snapshot of the full registry for monitoring."""
        ...


@runtime_checkable
class DiscoveryProvider(Protocol):
    """Interface for engine discovery providers.

    Implementations scan for available execution engines using a specific method
    (PATH scanning, WSL probing, Docker inspection, config files, etc.)
    """

    async def discover(self) -> list[EngineRegistration]:
        """Scan and return all discovered engine registrations."""
        ...

    def get_provider_name(self) -> str:
        """Return a human-readable name for this provider."""
        ...

    def get_provider_type(self) -> str:
        """Return the discovery method identifier."""
        ...
