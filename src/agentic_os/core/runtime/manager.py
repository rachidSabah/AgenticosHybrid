"""
Runtime Manager

High-level subsystem orchestrating engine lifecycle, discovery, capability
negotiation, and execution. This is the single point of integration wired
into the kernel.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from agentic_os.core.runtime.capabilities import CapabilityNegotiator
from agentic_os.core.runtime.discovery import DiscoveryEngine
from agentic_os.core.runtime.registry import RuntimeRegistryImpl
from agentic_os.domain.events import EventEnvelope, Topic
from agentic_os.domain.execution import (
    EngineCapability,
    EngineStatus,
    EngineType,
    ExecutionBenchmark,
    ExecutionCapability,
    ExecutionEngine,
    ExecutionHealth,
    ExecutionResult,
    ExecutionSession,
    ExecutionStatus,
)
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.event_bus import EventBus
from agentic_os.ports.execution import (
    EngineRegistration,
    EngineUpdate,
    ExecutionEnginePort,
    ExecutionRequest,
)

log = get_logger("runtime.manager")


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class RuntimeManager:
    """
    High-level runtime manager wired into the kernel.

    Composes:
    - RuntimeRegistryImpl — engine CRUD and state tracking
    - DiscoveryEngine — automatic engine discovery
    - CapabilityNegotiator — capability matching
    - adapter instances — live ExecutionEnginePort connections
    """

    bus: EventBus
    registry: RuntimeRegistryImpl
    discovery: DiscoveryEngine
    negotiator: CapabilityNegotiator
    _adapters: dict[str, ExecutionEnginePort] = field(default_factory=dict)
    _health_tasks: dict[str, asyncio.Task] = field(default_factory=dict)
    _running: bool = field(default=False, init=False, repr=False)
    _health_interval: float = 30.0

    # ── Lifecycle ──

    async def initialize(self) -> None:
        """Initialize the runtime — start discovery, register found engines."""
        if self._running:
            return

        self._running = True
        log.info("Runtime manager initializing")

        # Discover engines
        if self._has_providers():
            discovered = await self.discovery.discover_all()
            for result in discovered:
                try:
                    engine = await self.registry.register_engine(result.registration)
                    # Store provider info in metadata
                    log.info(
                        "Discovered engine",
                        name=engine.name,
                        type=engine.engine_type.value,
                        confidence=result.confidence,
                        provider=result.provider_name,
                    )
                except ValueError:
                    # Already registered — that's fine
                    pass

        # Register capabilities for discovered engines
        for engine in await self.registry.list_engines():
            if engine.capabilities:
                await self.negotiator.register_capabilities(
                    engine.id,
                    list(engine.capabilities),
                )

        # Set all engines to IDLE
        for engine in await self.registry.list_engines():
            await self.registry.set_engine_status(engine.id, EngineStatus.IDLE)

        log.info(
            "Runtime manager initialized",
            engine_count=len(self._adapters),
            discovered=len(self._adapters),
        )

    async def shutdown(self) -> None:
        """Shutdown all engines and release resources."""
        if not self._running:
            return

        self._running = False
        log.info("Runtime manager shutting down")

        # Cancel health check tasks
        for task in self._health_tasks.values():
            task.cancel()
        self._health_tasks.clear()

        # Shutdown all adapters
        for engine_id, adapter in list(self._adapters.items()):
            try:
                await adapter.shutdown()
            except Exception as exc:
                log.warning("Engine shutdown error", engine=engine_id, error=str(exc))

        self._adapters.clear()

        # Clear registry
        for engine in await self.registry.list_engines():
            await self.registry.unregister_engine(engine.id)

        await self.negotiator.clear()
        log.info("Runtime manager shutdown complete")

    # ── Engine Registration ──

    async def register_engine(self, registration: EngineRegistration) -> ExecutionEngine:
        """Register a new execution engine from descriptor data."""
        return await self.registry.register_engine(registration)

    async def register_from_adapter(
        self,
        engine_id: str,
        adapter: ExecutionEnginePort,
    ) -> ExecutionEngine:
        """Register a live adapter instance."""
        engine = await adapter.get_descriptor()
        registered = await self.registry.register_engine(
            EngineRegistration(
                name=engine.name,
                engine_type=engine.engine_type,
                endpoint=engine.endpoint,
                transport=engine.transport,
                capabilities=[c.type for c in engine.capabilities],
                description=engine.description,
                version=engine.version,
                tags=list(engine.tags),
                metadata=engine.metadata,
            )
        )

        # Preserve the adapter's actual status
        registered = await self.registry.set_engine_status(registered.id, engine.status)
        assert registered is not None

        self._adapters[registered.id] = adapter
        self.registry.map_adapter(registered.id, engine_id)

        # Register capabilities with negotiator
        if engine.capabilities:
            await self.negotiator.register_capabilities(
                registered.id,
                list(engine.capabilities),
            )

        return registered

    async def get_engine(self, engine_id: str) -> ExecutionEngine | None:
        """Look up an engine by ID."""
        return await self.registry.get_engine(engine_id)

    async def list_engines(
        self,
        engine_type: EngineType | None = None,
        capability: EngineCapability | None = None,
        status: str | None = None,
    ) -> list[ExecutionEngine]:
        """List engines, optionally filtered."""
        return await self.registry.list_engines(
            engine_type=engine_type,
            capability=capability,
            status=status,
        )

    async def update_engine(
        self,
        engine_id: str,
        update: EngineUpdate,
    ) -> ExecutionEngine | None:
        """Update an engine's metadata."""
        return await self.registry.update_engine(engine_id, update)

    async def unregister_engine(self, engine_id: str) -> bool:
        """Unregister an engine."""
        # Shutdown adapter if present
        adapter = self._adapters.pop(engine_id, None)
        if adapter is not None:
            try:
                await adapter.shutdown()
            except Exception:
                pass
            self.registry.unmap_adapter(engine_id)

        # Cancel health check
        task = self._health_tasks.pop(engine_id, None)
        if task is not None:
            task.cancel()

        # Clear capability cache
        await self.negotiator.unregister_capabilities(engine_id)

        return await self.registry.unregister_engine(engine_id)

    # ── Discovery ──

    async def discover_engines(self) -> list[ExecutionEngine]:
        """Run discovery providers and register found engines."""
        results = await self.discovery.discover_all()
        registered: list[ExecutionEngine] = []

        for result in results:
            try:
                engine = await self.registry.register_engine(result.registration)
                await self.registry.set_engine_status(engine.id, EngineStatus.IDLE)
                registered.append(engine)
                await self.bus.publish(
                    EventEnvelope(
                        type="event",
                        source="runtime-manager",
                        topic=Topic.ENGINE_DISCOVERED.value,
                        payload={"engine_id": engine.id, "provider": result.provider_name},
                    )
                )
            except ValueError:
                # Already registered — update capabilities
                existing = await self.registry.get_engine(result.registration.name)
                if existing:
                    await self.registry.update_capabilities(
                        existing.id,
                        [
                            ExecutionCapability.from_type(c)
                            for c in result.registration.capabilities
                        ],
                    )
                continue

        return registered

    # ── Execution ──

    async def execute(
        self,
        engine_id: str,
        request: ExecutionRequest,
    ) -> ExecutionResult:
        """Execute on a specific engine."""
        adapter = self._adapters.get(engine_id)
        if adapter is None:
            return ExecutionResult(
                execution_id="",
                status=ExecutionStatus.FAILED,
                error=f"Engine not found or not connected: {engine_id}",
            )

        engine = await self.registry.get_engine(engine_id)
        if engine and not engine.is_online():
            return ExecutionResult(
                execution_id="",
                status=ExecutionStatus.FAILED,
                error=f"Engine is offline: {engine_id}",
            )

        # Update status to BUSY
        if engine:
            await self.registry.set_engine_status(engine_id, EngineStatus.BUSY)

        try:
            result = await adapter.execute(request)
            await self._emit_execution_event(
                Topic.ENGINE_EXECUTION_COMPLETED
                if result.status == ExecutionStatus.COMPLETED
                else Topic.ENGINE_EXECUTION_FAILED,
                engine_id,
                result,
            )
            return result
        except Exception as exc:
            error_result = ExecutionResult(
                execution_id="",
                status=ExecutionStatus.FAILED,
                error=str(exc),
            )
            await self._emit_execution_event(Topic.ENGINE_EXECUTION_FAILED, engine_id, error_result)
            return error_result
        finally:
            # Restore to IDLE
            if engine:
                await self.registry.set_engine_status(engine_id, EngineStatus.IDLE)

    async def execute_on_best(
        self,
        request: ExecutionRequest,
        required_capability: EngineCapability | None = None,
    ) -> ExecutionResult:
        """Execute on the best-matching engine for the capability."""
        if required_capability:
            # Find engines matching the capability
            engines = await self.registry.find_engines_by_capability(required_capability)
            best = await self.negotiator.find_best_match(
                [required_capability],
                engines,
            )
            if best is None:
                return ExecutionResult(
                    execution_id="",
                    status=ExecutionStatus.FAILED,
                    error=f"No available engine supports capability: {required_capability}",
                )
            engine_id = best.id
        elif self._adapters:
            # Pick the engine with the most capabilities. Query all adapters
            # concurrently — the previous sequential loop added per-adapter
            # latency to every "execute on best" call.
            adapter_items = list(self._adapters.items())

            async def _count_caps(eid: str, adap: Any) -> tuple[str, int]:
                try:
                    desc = await adap.get_descriptor()
                    return eid, len(desc.capabilities)
                except Exception:
                    return eid, -1

            results = await asyncio.gather(*[_count_caps(eid, a) for eid, a in adapter_items])
            best_eid, best_count = None, -1
            for eid, count in results:
                if count > best_count:
                    best_count = count
                    best_eid = eid
            engine_id = best_eid
            if engine_id is None:
                return ExecutionResult(
                    execution_id="",
                    status=ExecutionStatus.FAILED,
                    error="No engines available",
                )
        else:
            return ExecutionResult(
                execution_id="",
                status=ExecutionStatus.FAILED,
                error="No engines available",
            )

        return await self.execute(engine_id, request)

    async def cancel_execution(self, engine_id: str, execution_id: str) -> bool:
        """Cancel execution on a specific engine."""
        adapter = self._adapters.get(engine_id)
        if adapter is None:
            return False
        return await adapter.cancel(execution_id)

    async def pause_execution(self, engine_id: str, execution_id: str) -> bool:
        """Pause execution on a specific engine."""
        adapter = self._adapters.get(engine_id)
        if adapter is None:
            return False
        return await adapter.pause(execution_id)

    async def resume_execution(self, engine_id: str, execution_id: str) -> bool:
        """Resume execution on a specific engine."""
        adapter = self._adapters.get(engine_id)
        if adapter is None:
            return False
        return await adapter.resume(execution_id)

    # ── Health & Benchmark ──

    async def health_check(self, engine_id: str) -> ExecutionHealth:
        """Check health of a specific engine."""
        adapter = self._adapters.get(engine_id)
        if adapter is None:
            return ExecutionHealth.unhealthy(f"No adapter for engine: {engine_id}")

        try:
            health = await adapter.health_check()
            await self.registry.update_health(engine_id, health)
            return health
        except Exception as exc:
            health = ExecutionHealth.unhealthy(str(exc))
            await self.registry.update_health(engine_id, health)
            return health

    async def benchmark(
        self,
        engine_id: str,
        config: dict[str, Any] | None = None,
    ) -> ExecutionBenchmark:
        """Run benchmark on a specific engine."""
        adapter = self._adapters.get(engine_id)
        if adapter is None:
            raise ValueError(f"No adapter for engine: {engine_id}")
        return await adapter.benchmark(config)

    async def health_check_all(self) -> dict[str, ExecutionHealth]:
        """Check health of all registered engines."""
        results: dict[str, ExecutionHealth] = {}
        for engine_id in self._adapters:
            results[engine_id] = await self.health_check(engine_id)
        return results

    # ── Query & Search ──

    async def find_engines(
        self,
        capability: EngineCapability,
        min_confidence: float = 0.0,
    ) -> list[ExecutionEngine]:
        """Find engines matching a capability."""
        return await self.registry.find_engines_by_capability(capability, min_confidence)

    async def list_capabilities(self) -> dict[str, list[ExecutionCapability]]:
        """Return all registered capabilities grouped by engine ID."""
        result: dict[str, list[ExecutionCapability]] = {}
        for engine in await self.registry.list_engines():
            if engine.capabilities:
                result[engine.id] = list(engine.capabilities)
        return result

    # ── Sessions ──

    async def get_session(self, engine_id: str, session_id: str) -> ExecutionSession | None:
        """Get an execution session."""
        return await self.registry.get_session(session_id)

    async def list_sessions(
        self,
        engine_id: str | None = None,
        limit: int = 50,
    ) -> list[ExecutionSession]:
        """List execution sessions, optionally filtered."""
        return await self.registry.list_sessions(engine_id=engine_id, limit=limit)

    # ── Adapter Access ──

    async def get_adapter(self, engine_id: str) -> ExecutionEnginePort | None:
        """Get the live adapter instance for an engine."""
        return self._adapters.get(engine_id)

    async def get_registry_snapshot(self) -> dict:
        """Return a snapshot of the full registry for monitoring."""
        return await self.registry.get_registry_snapshot()

    # ── Internal ──

    def _has_providers(self) -> bool:
        """Check if any discovery providers are registered."""
        return len(self.discovery._providers) > 0  # type: ignore[attr-defined]

    async def _emit_execution_event(
        self,
        topic: Topic,
        engine_id: str,
        result: ExecutionResult,
    ) -> None:
        """Emit an execution lifecycle event."""
        await self.bus.publish(
            EventEnvelope(
                type="event",
                source="runtime-manager",
                topic=topic.value,
                payload={
                    "engine_id": engine_id,
                    "execution_id": result.execution_id,
                    "status": result.status.value,
                    "error": result.error,
                },
            )
        )

    async def _start_periodic_health_check(
        self,
        engine_id: str,
        interval_seconds: float = 30.0,
    ) -> None:
        """Start a periodic health check task for an engine."""
        if engine_id in self._health_tasks:
            return

        async def _check_loop() -> None:
            while self._running:
                try:
                    await self.health_check(engine_id)
                except Exception:
                    pass
                await asyncio.sleep(interval_seconds)

        self._health_tasks[engine_id] = asyncio.create_task(_check_loop())
