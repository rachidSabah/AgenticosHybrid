"""
Execution Engine Base

Abstract base implementation of ExecutionEnginePort with common lifecycle tracking,
default implementations for optional methods, and a CompositeEngine for combining
multiple engines behind a single interface.
"""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from agentic_os.domain.execution import (
    EngineCapability,
    EngineStatus,
    EngineType,
    ExecutionBenchmark,
    ExecutionCapability,
    ExecutionConfiguration,
    ExecutionEngine,
    ExecutionEvent,
    ExecutionHealth,
    ExecutionMetrics,
    ExecutionResult,
    ExecutionStatus,
    ExecutionWorkspace,
)
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.execution import (
    ExecutionEnginePort,
    ExecutionRequest,
)

log = get_logger("runtime.engine")


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class ExecutionEngineBase:
    """
    Abstract base for execution engines.

    Provides:
    - Common lifecycle tracking (status state machine)
    - Default implementations for optional methods (raise NotImplementedError)
    - Telemetry collection helpers
    - Cost/latency estimation defaults

    Engines subclass this and override the methods they support.
    """

    name: str
    engine_type: EngineType = EngineType.GENERIC
    descriptor: ExecutionEngine = field(default_factory=ExecutionEngine)

    def __post_init__(self) -> None:
        """Initialize the engine descriptor with the given name and type."""
        object.__setattr__(
            self,
            "descriptor",
            ExecutionEngine(
                name=self.name,
                engine_type=self.engine_type,
                status=EngineStatus.CREATED,
            ),
        )

    # ── Lifecycle ──

    async def initialize(self) -> ExecutionEngine:
        """Start the engine. Subclasses must override to implement actual init."""
        self._set_status(EngineStatus.INITIALIZING)
        try:
            # Subclasses should perform actual initialization here
            self._set_status(EngineStatus.RUNNING)
        except Exception as exc:
            log.error("Engine initialization failed", engine=self.name, error=str(exc))
            self._set_status(EngineStatus.FAILED)
            raise
        return self.descriptor

    async def shutdown(self) -> None:
        """Stop the engine. Subclasses must override."""
        self._set_status(EngineStatus.STOPPED)

    # ── Discovery & Health ──

    async def health_check(self) -> ExecutionHealth:
        """Default health check — return healthy with zero latency."""
        return ExecutionHealth.healthy()

    # ── Execution ──

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """Execute an action. Subclasses must override."""
        raise NotImplementedError(f"{type(self).__name__} must implement execute()")

    async def cancel(self, execution_id: str) -> bool:
        """Cancel a running execution."""
        raise NotImplementedError(f"{type(self).__name__} does not support cancel()")

    async def pause(self, execution_id: str) -> bool:
        """Pause a running execution."""
        raise NotImplementedError(f"{type(self).__name__} does not support pause()")

    async def resume(self, execution_id: str) -> bool:
        """Resume a paused execution."""
        raise NotImplementedError(f"{type(self).__name__} does not support resume()")

    async def stream(self, execution_id: str) -> AsyncIterator[bytes]:
        """Stream output — not supported by default."""
        raise NotImplementedError(f"{type(self).__name__} does not support stream()")

    # ── Performance ──

    async def benchmark(self, config: dict[str, Any] | None = None) -> ExecutionBenchmark:
        """Default benchmark — raise NotImplementedError."""
        raise NotImplementedError(f"{type(self).__name__} does not support benchmark()")

    async def telemetry(self) -> list[ExecutionEvent]:
        """Default telemetry — empty list."""
        return []

    # ── Metadata ──

    async def get_version(self) -> str:
        """Return engine version from the descriptor."""
        return self.descriptor.version

    async def get_configuration(self) -> ExecutionConfiguration:
        """Return engine configuration from the descriptor."""
        if self.descriptor.config:
            return self.descriptor.config
        return ExecutionConfiguration(engine_id=self.descriptor.id)

    async def get_descriptor(self) -> ExecutionEngine:
        """Return the current engine descriptor."""
        return self.descriptor

    async def get_capabilities(self) -> list[ExecutionCapability]:
        """Return capabilities from the descriptor."""
        return list(self.descriptor.capabilities)

    # ── Compatibility ──

    async def supports(self, capability: EngineCapability) -> bool:
        """Check if this engine supports a given capability."""
        return self.descriptor.supports_capability(capability)

    async def estimate_cost(self, request: ExecutionRequest) -> float:
        """Default cost estimation — return 0."""
        return 0.0

    async def estimate_latency(self, request: ExecutionRequest) -> float:
        """Default latency estimation — return 0."""
        return 0.0

    # ── Workspace ──

    async def get_workspace(self) -> ExecutionWorkspace:
        """Return workspace info from the descriptor."""
        return self.descriptor.workspace

    # ── Recovery ──

    async def interrupt(self, execution_id: str) -> bool:
        """Hard-interrupt — default delegates to cancel()."""
        return await self.cancel(execution_id)

    async def recover(self, execution_id: str, timeout_seconds: float = 30.0) -> ExecutionResult:
        """Attempt recovery after crash — default raises NotImplementedError."""
        raise NotImplementedError(f"{type(self).__name__} does not support recover()")

    # ── Internal Helpers ──

    def _set_status(self, status: EngineStatus) -> None:
        """Update the engine descriptor status immutably."""
        object.__setattr__(self, "descriptor", self.descriptor.with_status(status))

    async def _create_result(
        self,
        execution_id: str,
        output: Any = None,
        error: str | None = None,
        metrics: ExecutionMetrics | None = None,
    ) -> ExecutionResult:
        """Create an execution result with the given parameters."""
        result = ExecutionResult(
            execution_id=execution_id,
            status=ExecutionStatus.COMPLETED if error is None else ExecutionStatus.FAILED,
            output=output,
            error=error,
            metrics=metrics or ExecutionMetrics(),
        )
        if error:
            result = result.with_failed(error)
        else:
            result = result.with_completed(output)
        return result


@dataclass
class CompositeEngine:
    """
    Combines multiple execution engines behind one ExecutionEnginePort interface.

    Supports:
    - Capability-based routing: execute() routes to the best-match sub-engine
    - Fallback: if primary engine fails, auto-retry on secondary
    - Load balancing: round-robin across identical engines
    - Fan-out: broadcast same request to all engines
    """

    name: str
    engines: dict[str, ExecutionEnginePort] = field(default_factory=dict)
    _round_robin_index: dict[str, int] = field(default_factory=dict)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def add_engine(self, engine_id: str, adapter: ExecutionEnginePort) -> None:
        """Register a sub-engine."""
        self.engines[engine_id] = adapter

    def remove_engine(self, engine_id: str) -> bool:
        """Remove a sub-engine. Returns True if removed."""
        if engine_id in self.engines:
            del self.engines[engine_id]
            self._round_robin_index.pop(engine_id, None)
            return True
        return False

    async def find_best_engine(
        self,
        required_capability: EngineCapability | None = None,
    ) -> tuple[str, ExecutionEnginePort] | None:
        """Find the best sub-engine for a capability."""
        if not self.engines:
            return None

        if required_capability is None:
            # Return the first available engine (round-robin)
            engine_ids = list(self.engines.keys())
            idx = self._round_robin_index.get(self.name, 0) % len(engine_ids)
            async with self._lock:
                self._round_robin_index[self.name] = idx + 1
            eid = engine_ids[idx]
            return (eid, self.engines[eid])

        # Find engine matching the capability
        for eid, adapter in self.engines.items():
            try:
                if await adapter.supports(required_capability):
                    return (eid, adapter)
            except Exception:
                continue

        return None

    async def execute_on_best(
        self,
        request: ExecutionRequest,
        required_capability: EngineCapability | None = None,
    ) -> ExecutionResult:
        """Execute on the best-matching sub-engine with fallback."""
        best = await self.find_best_engine(required_capability)
        if best is None:
            return ExecutionResult(
                execution_id="",
                status=ExecutionStatus.FAILED,
                error="No available engine found",
            )

        eid, adapter = best
        try:
            return await adapter.execute(request)
        except Exception as exc:
            log.warning(
                "Primary engine failed, attempting fallback",
                engine=eid,
                error=str(exc),
            )
            # Try any other engine as fallback
            for fallback_eid, fallback_adapter in self.engines.items():
                if fallback_eid == eid:
                    continue
                try:
                    return await fallback_adapter.execute(request)
                except Exception:
                    continue

            return ExecutionResult(
                execution_id="",
                status=ExecutionStatus.FAILED,
                error=f"All engines failed, last error: {exc}",
            )
