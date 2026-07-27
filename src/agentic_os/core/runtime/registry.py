"""
Runtime Registry Implementation

In-memory implementation of RuntimeRegistryPort with engine lifecycle management,
capability caching, and health monitoring integration.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from agentic_os.domain.events import EventEnvelope, Topic
from agentic_os.domain.execution import (
    EngineCapability,
    EngineRegistry,
    EngineStatus,
    EngineType,
    ExecutionCapability,
    ExecutionEngine,
    ExecutionHealth,
    ExecutionSession,
)
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.event_bus import EventBus
from agentic_os.ports.execution import (
    EngineRegistration,
    EngineUpdate,
)

log = get_logger("runtime.registry")


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class RuntimeRegistryImpl:
    """
    In-memory Runtime Registry Implementation.

    Features:
    - Engine lifecycle management (register, update, unregister)
    - Capability-based engine search
    - Health cache management
    - Session tracking
    - Event emission for all lifecycle transitions
    - Per-engine locks for thread safety
    """

    bus: EventBus
    _registry: EngineRegistry = field(default_factory=EngineRegistry)
    _health_cache: dict[str, ExecutionHealth] = field(default_factory=dict)
    _sessions: dict[str, ExecutionSession] = field(default_factory=dict)
    _locks: dict[str, asyncio.Lock] = field(default_factory=dict)
    _adapter_map: dict[str, str] = field(default_factory=dict)  # engine_id -> adapter_key
    _registry_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _max_sessions: int = 500

    async def _get_lock(self, engine_id: str) -> asyncio.Lock:
        """Return the per-engine lock, creating it if needed.

        Guarded by ``_registry_lock`` so two concurrent callers cannot each create
        distinct ``asyncio.Lock`` instances for the same engine_id (which would
        defeat the purpose of the lock). Callers must NOT already hold
        ``_registry_lock`` — asyncio.Lock is not reentrant.
        """
        async with self._registry_lock:
            lock = self._locks.get(engine_id)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[engine_id] = lock
            return lock

    async def _emit(self, topic: Topic, payload: dict[str, Any]) -> None:
        """Emit an event to the event bus."""
        await self.bus.publish(
            EventEnvelope(
                type="event",
                source="runtime-registry",
                topic=topic.value,
                payload=payload,
            )
        )

    # ── Engine CRUD ──

    async def register_engine(
        self,
        data: EngineRegistration,
    ) -> ExecutionEngine:
        """Register a new execution engine."""
        engine = ExecutionEngine(
            name=data.name,
            engine_type=data.engine_type,
            status=EngineStatus.CREATED,
            endpoint=data.endpoint,
            transport=data.transport,
            version=data.version,
            description=data.description,
            tags=tuple(data.tags),
            metadata=data.metadata,
            capabilities=tuple(ExecutionCapability.from_type(c) for c in data.capabilities),
        )

        # Check for duplicate by name (user-facing identifier) under the registry
        # lock so two concurrent register_engine calls for the same name cannot
        # both pass the duplicate check before either takes the per-engine lock.
        # We also create the per-engine lock here (still under _registry_lock) so
        # the lookup-then-create is atomic; then we release _registry_lock and
        # acquire the engine lock separately. asyncio.Lock is NOT reentrant, so
        # we must not call _get_lock() while holding _registry_lock.
        async with self._registry_lock:
            existing = self._registry.get_engine_by_name(engine.name)
            if existing is not None:
                raise ValueError(f"Engine already registered: {engine.name}")
            engine_lock = self._locks.get(engine.id)
            if engine_lock is None:
                engine_lock = asyncio.Lock()
                self._locks[engine.id] = engine_lock

        async with engine_lock:
            # Re-check under the engine lock in case a concurrent caller won
            # the race between the duplicate check above and acquiring the lock.
            existing = self._registry.get_engine_by_name(engine.name)
            if existing is not None:
                raise ValueError(f"Engine already registered: {engine.name}")
            self._registry = self._registry.with_engine(engine)

        await self._emit(Topic.ENGINE_REGISTERED, {"engine_id": engine.id, "name": engine.name})
        log.info(
            "Engine registered",
            engine_id=engine.id,
            name=engine.name,
            type=engine.engine_type.value,
        )
        return engine

    async def get_engine(self, engine_id: str) -> ExecutionEngine | None:
        """Look up an engine by ID."""
        return self._registry.get_engine(engine_id)

    async def list_engines(
        self,
        engine_type: EngineType | None = None,
        capability: EngineCapability | None = None,
        status: str | None = None,
    ) -> list[ExecutionEngine]:
        """List engines, optionally filtered."""
        result = list(self._registry.engines)

        if engine_type is not None:
            result = [e for e in result if e.engine_type == engine_type]

        if capability is not None:
            result = [e for e in result if e.supports_capability(capability)]

        if status is not None:
            result = [e for e in result if e.status.value == status]

        return result

    async def update_engine(
        self,
        engine_id: str,
        update: EngineUpdate,
    ) -> ExecutionEngine | None:
        """Update an engine's metadata."""
        engine = self._registry.get_engine(engine_id)
        if engine is None:
            return None

        changes: dict[str, Any] = {}
        kwargs: dict[str, Any] = {}

        if update.name is not None:
            kwargs["name"] = update.name
            changes["name"] = update.name
        if update.endpoint is not None:
            kwargs["endpoint"] = update.endpoint
            changes["endpoint"] = update.endpoint
        if update.transport is not None:
            kwargs["transport"] = update.transport
            changes["transport"] = update.transport
        if update.description is not None:
            kwargs["description"] = update.description
            changes["description"] = update.description
        if update.version is not None:
            kwargs["version"] = update.version
            changes["version"] = update.version
        if update.tags is not None:
            kwargs["tags"] = tuple(update.tags)
            changes["tags"] = update.tags
        if update.metadata is not None:
            kwargs["metadata"] = {**engine.metadata, **update.metadata}
            changes["metadata"] = update.metadata

        if not kwargs:
            return engine

        updated = ExecutionEngine(
            id=engine.id,
            name=kwargs.get("name", engine.name),
            engine_type=engine.engine_type,
            status=engine.status,
            capabilities=engine.capabilities,
            version=kwargs.get("version", engine.version),
            description=kwargs.get("description", engine.description),
            transport=kwargs.get("transport", engine.transport),
            endpoint=kwargs.get("endpoint", engine.endpoint),
            health=engine.health,
            profile=engine.profile,
            config=engine.config,
            workspace=engine.workspace,
            tags=kwargs.get("tags", engine.tags),
            metadata=kwargs.get("metadata", engine.metadata),
            created_at=engine.created_at,
            updated_at=_utcnow(),
            created_by=engine.created_by,
        )

        async with await self._get_lock(engine_id):
            self._registry = self._registry.with_engine(updated)

        await self._emit(Topic.ENGINE_UPDATED, {"engine_id": engine_id, "changes": changes})
        return updated

    async def unregister_engine(self, engine_id: str) -> bool:
        """Unregister an engine. Returns True if removed."""
        engine = self._registry.get_engine(engine_id)
        if engine is None:
            return False

        async with await self._get_lock(engine_id):
            self._registry = self._registry.without_engine(engine_id)
            self._health_cache.pop(engine_id, None)
            self._adapter_map.pop(engine_id, None)
            # Drop sessions belonging to this engine so the _sessions dict
            # cannot grow unboundedly across engine churn.
            self._sessions = {
                sid: s for sid, s in self._sessions.items() if s.engine_id != engine_id
            }
            # Discard the per-engine lock to avoid lingering state for unregistered engines.
            self._locks.pop(engine_id, None)

        await self._emit(Topic.ENGINE_UNREGISTERED, {"engine_id": engine_id})
        log.info("Engine unregistered", engine_id=engine_id)
        return True

    # ── Status Management ──

    async def set_engine_status(
        self, engine_id: str, status: EngineStatus
    ) -> ExecutionEngine | None:
        """Set the status of an engine."""
        engine = self._registry.get_engine(engine_id)
        if engine is None:
            return None

        updated = engine.with_status(status)
        async with await self._get_lock(engine_id):
            self._registry = self._registry.with_engine(updated)

        # Emit online/offline specific events
        if status == EngineStatus.RUNNING or status == EngineStatus.IDLE:
            await self._emit(Topic.ENGINE_ONLINE, {"engine_id": engine_id})
        elif status == EngineStatus.STOPPED or status == EngineStatus.FAILED:
            await self._emit(Topic.ENGINE_OFFLINE, {"engine_id": engine_id})

        return updated

    async def update_capabilities(
        self,
        engine_id: str,
        capabilities: list[ExecutionCapability],
    ) -> ExecutionEngine | None:
        """Update an engine's capabilities."""
        engine = self._registry.get_engine(engine_id)
        if engine is None:
            return None

        updated = engine.with_capabilities(capabilities)
        async with await self._get_lock(engine_id):
            self._registry = self._registry.with_engine(updated)

        await self._emit(
            Topic.ENGINE_CAPABILITIES_CHANGED,
            {"engine_id": engine_id, "capabilities": [c.to_dict() for c in capabilities]},
        )
        return updated

    # ── Health Cache ──

    async def update_health(
        self, engine_id: str, health: ExecutionHealth
    ) -> ExecutionEngine | None:
        """Update the health of an engine."""
        engine = self._registry.get_engine(engine_id)
        if engine is None:
            return None

        updated = engine.with_health(health)
        self._health_cache[engine_id] = health

        async with await self._get_lock(engine_id):
            self._registry = self._registry.with_engine(updated)

        await self._emit(
            Topic.ENGINE_HEALTH_CHANGED,
            {
                "engine_id": engine_id,
                "status": health.status.value,
            },
        )
        return updated

    async def get_health(self, engine_id: str) -> ExecutionHealth | None:
        """Get the cached health for an engine."""
        return self._health_cache.get(engine_id)

    # ── Session Tracking ──

    async def track_session(self, session: ExecutionSession) -> None:
        """Track an execution session.

        Keeps ``_sessions`` bounded: if we are at ``_max_sessions`` and a new
        session arrives, the oldest session (by ``started_at``) is evicted.
        """
        if len(self._sessions) >= self._max_sessions:
            oldest_id = min(
                self._sessions.keys(),
                key=lambda sid: self._sessions[sid].started_at,
                default=None,
            )
            if oldest_id is not None:
                self._sessions.pop(oldest_id, None)
        self._sessions[session.id] = session

    async def update_session(self, session: ExecutionSession) -> None:
        """Update a tracked session."""
        self._sessions[session.id] = session

    async def get_session(self, session_id: str) -> ExecutionSession | None:
        """Get a tracked session."""
        return self._sessions.get(session_id)

    async def list_sessions(
        self,
        engine_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[ExecutionSession]:
        """List tracked sessions, optionally filtered."""
        sessions = list(self._sessions.values())

        if engine_id is not None:
            sessions = [s for s in sessions if s.engine_id == engine_id]

        if status is not None:
            sessions = [s for s in sessions if s.status.value == status]

        sessions.sort(key=lambda s: s.started_at, reverse=True)
        return sessions[:limit]

    # ── Adapter Map ──

    def map_adapter(self, engine_id: str, adapter_key: str) -> None:
        """Map an engine to its adapter instance key."""
        self._adapter_map[engine_id] = adapter_key

    def get_adapter_key(self, engine_id: str) -> str | None:
        """Get the adapter key for an engine."""
        return self._adapter_map.get(engine_id)

    def unmap_adapter(self, engine_id: str) -> None:
        """Remove the adapter mapping for an engine."""
        self._adapter_map.pop(engine_id, None)

    # ── Capability Search ──

    async def find_engines_by_capability(
        self,
        capability: EngineCapability,
        min_confidence: float = 0.0,
    ) -> list[ExecutionEngine]:
        """Find online engines matching a capability."""
        result = []
        for engine in self._registry.engines:
            if not engine.is_online():
                continue
            for cap in engine.capabilities:
                if cap.type == capability and cap.confidence >= min_confidence:
                    result.append(engine)
                    break
        return result

    # ── Snapshot ──

    async def get_registry_snapshot(self) -> dict[str, Any]:
        """Return a diagnostic snapshot of the registry state."""
        engine_count = len(self._registry.engines)
        online_count = len(self._registry.list_online())
        return {
            "total_engines": engine_count,
            "online_engines": online_count,
            "offline_engines": engine_count - online_count,
            "tracked_sessions": len(self._sessions),
            "cached_health": len(self._health_cache),
            "engines": [e.to_dict() for e in self._registry.engines],
        }
