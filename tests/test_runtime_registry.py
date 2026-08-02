"""Tests for runtime registry implementation."""

import pytest

from agentic_os.core.runtime.registry import RuntimeRegistryImpl
from agentic_os.domain.execution import (
    EngineCapability,
    EngineHealthStatus,
    EngineStatus,
    EngineType,
    ExecutionCapability,
    ExecutionHealth,
    ExecutionSession,
    ExecutionStatus,
)
from agentic_os.ports.execution import EngineRegistration, EngineUpdate


class TestRuntimeRegistry:
    @pytest.fixture
    async def registry(self, bus) -> RuntimeRegistryImpl:
        """Create a registry with a real local bus."""
        return RuntimeRegistryImpl(bus=bus)

    @pytest.fixture
    def sample_registration(self) -> EngineRegistration:
        return EngineRegistration(
            name="test-engine",
            engine_type=EngineType.GENERIC,
            capabilities=[EngineCapability.CODING, EngineCapability.REASONING],
        )

    @pytest.mark.asyncio
    async def test_register_engine(
        self, registry: RuntimeRegistryImpl, sample_registration: EngineRegistration
    ) -> None:
        engine = await registry.register_engine(sample_registration)
        assert engine.name == "test-engine"
        assert engine.engine_type == EngineType.GENERIC
        assert engine.status == EngineStatus.CREATED
        assert len(engine.capabilities) == 2

    @pytest.mark.asyncio
    async def test_register_duplicate_raises(
        self, registry: RuntimeRegistryImpl, sample_registration: EngineRegistration
    ) -> None:
        await registry.register_engine(sample_registration)
        with pytest.raises(ValueError, match="already registered"):
            await registry.register_engine(sample_registration)

    @pytest.mark.asyncio
    async def test_get_engine(
        self, registry: RuntimeRegistryImpl, sample_registration: EngineRegistration
    ) -> None:
        engine = await registry.register_engine(sample_registration)
        found = await registry.get_engine(engine.id)
        assert found is not None
        assert found.name == "test-engine"

    @pytest.mark.asyncio
    async def test_get_engine_not_found(self, registry: RuntimeRegistryImpl) -> None:
        assert await registry.get_engine("nonexistent") is None

    @pytest.mark.asyncio
    async def test_list_engines_empty(self, registry: RuntimeRegistryImpl) -> None:
        engines = await registry.list_engines()
        assert engines == []

    @pytest.mark.asyncio
    async def test_list_engines_all(
        self, registry: RuntimeRegistryImpl, sample_registration: EngineRegistration
    ) -> None:
        await registry.register_engine(sample_registration)
        engines = await registry.list_engines()
        assert len(engines) == 1

    @pytest.mark.asyncio
    async def test_list_engines_filter_by_type(self, registry: RuntimeRegistryImpl) -> None:
        _g = await registry.register_engine(
            EngineRegistration(name="g", engine_type=EngineType.GENERIC)
        )
        _m = await registry.register_engine(
            EngineRegistration(name="m", engine_type=EngineType.MCP)
        )
        assert len(await registry.list_engines(engine_type=EngineType.GENERIC)) == 1
        assert len(await registry.list_engines(engine_type=EngineType.MCP)) == 1
        assert len(await registry.list_engines(engine_type=EngineType.DOCKER)) == 0

    @pytest.mark.asyncio
    async def test_list_engines_filter_by_capability(self, registry: RuntimeRegistryImpl) -> None:
        await registry.register_engine(
            EngineRegistration(
                name="coder",
                capabilities=[EngineCapability.CODING],
            )
        )
        await registry.register_engine(
            EngineRegistration(
                name="planner",
                capabilities=[EngineCapability.PLANNING],
            )
        )
        coders = await registry.list_engines(capability=EngineCapability.CODING)
        assert len(coders) == 1
        assert coders[0].name == "coder"

    @pytest.mark.asyncio
    async def test_list_engines_filter_by_status(self, registry: RuntimeRegistryImpl) -> None:
        await registry.register_engine(EngineRegistration(name="e1"))
        await registry.set_engine_status("fake-id", EngineStatus.RUNNING)  # no-op
        engines = await registry.list_engines(status="created")
        assert len(engines) == 1

    @pytest.mark.asyncio
    async def test_update_engine(
        self, registry: RuntimeRegistryImpl, sample_registration: EngineRegistration
    ) -> None:
        engine = await registry.register_engine(sample_registration)
        updated = await registry.update_engine(engine.id, EngineUpdate(description="updated desc"))
        assert updated is not None
        assert updated.description == "updated desc"

    @pytest.mark.asyncio
    async def test_update_engine_not_found(self, registry: RuntimeRegistryImpl) -> None:
        assert await registry.update_engine("nonexistent", EngineUpdate()) is None

    @pytest.mark.asyncio
    async def test_unregister_engine(
        self, registry: RuntimeRegistryImpl, sample_registration: EngineRegistration
    ) -> None:
        engine = await registry.register_engine(sample_registration)
        removed = await registry.unregister_engine(engine.id)
        assert removed is True
        assert await registry.get_engine(engine.id) is None

    @pytest.mark.asyncio
    async def test_unregister_engine_not_found(self, registry: RuntimeRegistryImpl) -> None:
        assert await registry.unregister_engine("nonexistent") is False

    @pytest.mark.asyncio
    async def test_set_engine_status(
        self, registry: RuntimeRegistryImpl, sample_registration: EngineRegistration
    ) -> None:
        engine = await registry.register_engine(sample_registration)
        updated = await registry.set_engine_status(engine.id, EngineStatus.RUNNING)
        assert updated is not None
        assert updated.status == EngineStatus.RUNNING
        # Verify persisted
        fetched = await registry.get_engine(engine.id)
        assert fetched is not None
        assert fetched.status == EngineStatus.RUNNING

    @pytest.mark.asyncio
    async def test_set_engine_status_not_found(self, registry: RuntimeRegistryImpl) -> None:
        assert await registry.set_engine_status("nonexistent", EngineStatus.RUNNING) is None

    @pytest.mark.asyncio
    async def test_update_capabilities(
        self, registry: RuntimeRegistryImpl, sample_registration: EngineRegistration
    ) -> None:
        engine = await registry.register_engine(sample_registration)
        caps = [ExecutionCapability(type=EngineCapability.DOCKER)]
        updated = await registry.update_capabilities(engine.id, caps)
        assert updated is not None
        assert len(updated.capabilities) == 1
        assert updated.capabilities[0].type == EngineCapability.DOCKER

    @pytest.mark.asyncio
    async def test_update_capabilities_not_found(self, registry: RuntimeRegistryImpl) -> None:
        assert await registry.update_capabilities("nonexistent", []) is None

    @pytest.mark.asyncio
    async def test_update_health(
        self, registry: RuntimeRegistryImpl, sample_registration: EngineRegistration
    ) -> None:
        engine = await registry.register_engine(sample_registration)
        health = ExecutionHealth.healthy(latency_ms=5.0)
        updated = await registry.update_health(engine.id, health)
        assert updated is not None
        assert updated.health.status == EngineHealthStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_get_health_cached(
        self, registry: RuntimeRegistryImpl, sample_registration: EngineRegistration
    ) -> None:
        engine = await registry.register_engine(sample_registration)
        health = ExecutionHealth.healthy()
        await registry.update_health(engine.id, health)
        cached = await registry.get_health(engine.id)
        assert cached is not None
        assert cached.status == EngineHealthStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_get_health_not_cached(self, registry: RuntimeRegistryImpl) -> None:
        assert await registry.get_health("nonexistent") is None

    @pytest.mark.asyncio
    async def test_session_tracking(self, registry: RuntimeRegistryImpl) -> None:
        session = ExecutionSession(engine_id="eng-1")
        await registry.track_session(session)
        found = await registry.get_session(session.id)
        assert found is not None
        assert found.engine_id == "eng-1"

    @pytest.mark.asyncio
    async def test_session_update(self, registry: RuntimeRegistryImpl) -> None:
        session = ExecutionSession(engine_id="eng-1")
        await registry.track_session(session)
        updated = session.with_status(ExecutionStatus.RUNNING)
        await registry.update_session(updated)
        found = await registry.get_session(session.id)
        assert found is not None
        assert found.status == ExecutionStatus.RUNNING

    @pytest.mark.asyncio
    async def test_list_sessions_by_engine(self, registry: RuntimeRegistryImpl) -> None:
        s1 = ExecutionSession(engine_id="eng-1")
        s2 = ExecutionSession(engine_id="eng-2")
        await registry.track_session(s1)
        await registry.track_session(s2)
        sessions = await registry.list_sessions(engine_id="eng-1")
        assert len(sessions) == 1
        assert sessions[0].engine_id == "eng-1"

    @pytest.mark.asyncio
    async def test_find_engines_by_capability(self, registry: RuntimeRegistryImpl) -> None:
        await registry.register_engine(
            EngineRegistration(
                name="coder",
                capabilities=[EngineCapability.CODING],
            )
        )
        await registry.set_engine_status("fake", EngineStatus.RUNNING)  # set status on runner
        # Register and set online
        engine = await registry.register_engine(
            EngineRegistration(
                name="docked",
                capabilities=[EngineCapability.DOCKER],
            )
        )
        await registry.set_engine_status(engine.id, EngineStatus.RUNNING)

        dockers = await registry.find_engines_by_capability(EngineCapability.DOCKER)
        assert len(dockers) == 1
        assert dockers[0].name == "docked"

    @pytest.mark.asyncio
    async def test_adapter_map(self, registry: RuntimeRegistryImpl) -> None:
        registry.map_adapter("eng-1", "adapter-key")
        assert registry.get_adapter_key("eng-1") == "adapter-key"
        registry.unmap_adapter("eng-1")
        assert registry.get_adapter_key("eng-1") is None

    @pytest.mark.asyncio
    async def test_registry_snapshot(self, registry: RuntimeRegistryImpl) -> None:
        await registry.register_engine(EngineRegistration(name="e1"))
        snapshot = await registry.get_registry_snapshot()
        assert snapshot["total_engines"] == 1
        assert snapshot["online_engines"] == 0
