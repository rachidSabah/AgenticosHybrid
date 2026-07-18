"""Tests for RuntimeManager."""

import pytest

from agentic_os.core.runtime.capabilities import CapabilityNegotiator
from agentic_os.core.runtime.discovery import DiscoveryEngine
from agentic_os.core.runtime.manager import RuntimeManager
from agentic_os.core.runtime.registry import RuntimeRegistryImpl
from agentic_os.domain.execution import (
    EngineCapability,
    EngineStatus,
    EngineType,
)
from agentic_os.ports.execution import (
    EngineRegistration,
    EngineUpdate,
    ExecutionRequest,
)


class TestRuntimeManager:
    @pytest.fixture
    async def runtime(self, bus) -> RuntimeManager:
        registry = RuntimeRegistryImpl(bus=bus)
        discovery = DiscoveryEngine()
        negotiator = CapabilityNegotiator()
        rm = RuntimeManager(bus=bus, registry=registry, discovery=discovery, negotiator=negotiator)
        await rm.initialize()
        return rm

    @pytest.mark.asyncio
    async def test_initialize(self, runtime: RuntimeManager) -> None:
        engines = await runtime.list_engines()
        assert engines == []  # No providers, no engines

    @pytest.mark.asyncio
    async def test_register_engine(self, runtime: RuntimeManager) -> None:
        registration = EngineRegistration(name="e1", engine_type=EngineType.GENERIC)
        engine = await runtime.register_engine(registration)
        assert engine.name == "e1"
        assert engine.engine_type == EngineType.GENERIC

    @pytest.mark.asyncio
    async def test_get_engine(self, runtime: RuntimeManager) -> None:
        reg = EngineRegistration(name="finder", engine_type=EngineType.GENERIC)
        engine = await runtime.register_engine(reg)
        found = await runtime.get_engine(engine.id)
        assert found is not None
        assert found.name == "finder"

    @pytest.mark.asyncio
    async def test_get_engine_not_found(self, runtime: RuntimeManager) -> None:
        assert await runtime.get_engine("nonexistent") is None

    @pytest.mark.asyncio
    async def test_list_engines(self, runtime: RuntimeManager) -> None:
        await runtime.register_engine(EngineRegistration(name="e1", engine_type=EngineType.GENERIC))
        await runtime.register_engine(EngineRegistration(name="e2", engine_type=EngineType.MCP))
        engines = await runtime.list_engines()
        assert len(engines) == 2

    @pytest.mark.asyncio
    async def test_list_engines_filtered(self, runtime: RuntimeManager) -> None:
        await runtime.register_engine(
            EngineRegistration(name="gen", engine_type=EngineType.GENERIC)
        )
        await runtime.register_engine(EngineRegistration(name="mcp", engine_type=EngineType.MCP))
        mcp_engines = await runtime.list_engines(engine_type=EngineType.MCP)
        assert len(mcp_engines) == 1
        assert mcp_engines[0].name == "mcp"

    @pytest.mark.asyncio
    async def test_update_engine(self, runtime: RuntimeManager) -> None:
        engine = await runtime.register_engine(EngineRegistration(name="updatable"))
        updated = await runtime.update_engine(engine.id, EngineUpdate(description="new desc"))
        assert updated is not None
        assert updated.description == "new desc"

    @pytest.mark.asyncio
    async def test_unregister_engine(self, runtime: RuntimeManager) -> None:
        engine = await runtime.register_engine(EngineRegistration(name="removable"))
        assert await runtime.unregister_engine(engine.id) is True
        assert await runtime.get_engine(engine.id) is None

    @pytest.mark.asyncio
    async def test_unregister_engine_not_found(self, runtime: RuntimeManager) -> None:
        assert await runtime.unregister_engine("nonexistent") is False

    @pytest.mark.asyncio
    async def test_execute_on_nonexistent_engine(self, runtime: RuntimeManager) -> None:
        result = await runtime.execute("nonexistent", ExecutionRequest(action="ping"))
        assert result.status == "failed"
        assert "not found" in result.error

    @pytest.mark.asyncio
    async def test_execute_on_best_no_engines(self, runtime: RuntimeManager) -> None:
        result = await runtime.execute_on_best(ExecutionRequest(action="ping"))
        assert result.status == "failed"

    @pytest.mark.asyncio
    async def test_execute_on_best_with_capability_no_match(self, runtime: RuntimeManager) -> None:
        result = await runtime.execute_on_best(
            ExecutionRequest(action="ping"),
            required_capability=EngineCapability.DOCKER,
        )
        assert result.status == "failed"

    @pytest.mark.asyncio
    async def test_health_check_nonexistent(self, runtime: RuntimeManager) -> None:
        health = await runtime.health_check("nonexistent")
        assert health.status == "unhealthy"

    @pytest.mark.asyncio
    async def test_health_check_all_empty(self, runtime: RuntimeManager) -> None:
        results = await runtime.health_check_all()
        assert results == {}

    @pytest.mark.asyncio
    async def test_find_engines_empty(self, runtime: RuntimeManager) -> None:
        engines = await runtime.find_engines(EngineCapability.CODING)
        assert engines == []

    @pytest.mark.asyncio
    async def test_list_capabilities_empty(self, runtime: RuntimeManager) -> None:
        caps = await runtime.list_capabilities()
        assert caps == {}

    @pytest.mark.asyncio
    async def test_list_sessions_empty(self, runtime: RuntimeManager) -> None:
        sessions = await runtime.list_sessions()
        assert sessions == []

    @pytest.mark.asyncio
    async def test_get_adapter_nonexistent(self, runtime: RuntimeManager) -> None:
        adapter = await runtime.get_adapter("nonexistent")
        assert adapter is None

    @pytest.mark.asyncio
    async def test_get_registry_snapshot(self, runtime: RuntimeManager) -> None:
        snapshot = await runtime.get_registry_snapshot()
        assert snapshot["total_engines"] == 0
        assert snapshot["online_engines"] == 0

    @pytest.mark.asyncio
    async def test_shutdown(self, runtime: RuntimeManager) -> None:
        await runtime.shutdown()
        assert runtime._running is False

    @pytest.mark.asyncio
    async def test_double_initialize(self, runtime: RuntimeManager) -> None:
        await runtime.initialize()
        # Should be no-op
        assert runtime._running is True

    @pytest.mark.asyncio
    async def test_register_from_adapter(self, runtime: RuntimeManager, bus) -> None:
        from agentic_os.adapters.engines.generic import GenericExecutionEngine

        generic = GenericExecutionEngine(name="adapter-engine")
        await generic.initialize()
        engine = await runtime.register_from_adapter("generic-key", generic)
        assert engine.name == "adapter-engine"
        assert engine.status == EngineStatus.RUNNING

    @pytest.mark.asyncio
    async def test_execute_on_best_with_adapter(self, runtime: RuntimeManager, bus) -> None:
        from agentic_os.adapters.engines.generic import GenericExecutionEngine

        generic = GenericExecutionEngine(name="adapter-engine")
        await generic.initialize()
        await runtime.register_from_adapter("generic-key", generic)

        result = await runtime.execute_on_best(ExecutionRequest(action="ping"))
        assert result.status == "completed"
        assert result.output["pong"] is True

    @pytest.mark.asyncio
    async def test_cancel_execution_nonexistent(self, runtime: RuntimeManager) -> None:
        assert await runtime.cancel_execution("nonexistent", "exec-1") is False

    @pytest.mark.asyncio
    async def test_pause_execution_nonexistent(self, runtime: RuntimeManager) -> None:
        assert await runtime.pause_execution("nonexistent", "exec-1") is False

    @pytest.mark.asyncio
    async def test_resume_execution_nonexistent(self, runtime: RuntimeManager) -> None:
        assert await runtime.resume_execution("nonexistent", "exec-1") is False

    @pytest.mark.asyncio
    async def test_discover_engines_no_providers(self, runtime: RuntimeManager) -> None:
        engines = await runtime.discover_engines()
        assert engines == []
