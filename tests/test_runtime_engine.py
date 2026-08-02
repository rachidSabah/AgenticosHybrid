"""Tests for execution engine base and composite engine."""

import pytest

from agentic_os.core.runtime.engine import CompositeEngine, ExecutionEngineBase
from agentic_os.domain.execution import (
    EngineCapability,
    EngineStatus,
    EngineType,
    ExecutionCapability,
)
from agentic_os.ports.execution import ExecutionRequest


class TestExecutionEngineBase:
    @pytest.fixture
    def engine(self) -> ExecutionEngineBase:
        return ExecutionEngineBase(name="test-base", engine_type=EngineType.GENERIC)

    @pytest.mark.asyncio
    async def test_initialize(self, engine: ExecutionEngineBase) -> None:
        descriptor = await engine.initialize()
        assert descriptor.status == EngineStatus.RUNNING
        assert descriptor.name == "test-base"

    @pytest.mark.asyncio
    async def test_shutdown(self, engine: ExecutionEngineBase) -> None:
        await engine.shutdown()
        assert engine.descriptor.status == EngineStatus.STOPPED

    @pytest.mark.asyncio
    async def test_health_check_default(self, engine: ExecutionEngineBase) -> None:
        health = await engine.health_check()
        assert health.status == "healthy"

    @pytest.mark.asyncio
    async def test_execute_not_implemented(self, engine: ExecutionEngineBase) -> None:
        request = ExecutionRequest(action="ping")
        with pytest.raises(NotImplementedError):
            await engine.execute(request)

    @pytest.mark.asyncio
    async def test_cancel_not_implemented(self, engine: ExecutionEngineBase) -> None:
        with pytest.raises(NotImplementedError):
            await engine.cancel("exec-1")

    @pytest.mark.asyncio
    async def test_pause_not_implemented(self, engine: ExecutionEngineBase) -> None:
        with pytest.raises(NotImplementedError):
            await engine.pause("exec-1")

    @pytest.mark.asyncio
    async def test_resume_not_implemented(self, engine: ExecutionEngineBase) -> None:
        with pytest.raises(NotImplementedError):
            await engine.resume("exec-1")

    @pytest.mark.asyncio
    async def test_stream_not_implemented(self, engine: ExecutionEngineBase) -> None:
        with pytest.raises(NotImplementedError):
            await engine.stream("exec-1")

    @pytest.mark.asyncio
    async def test_benchmark_not_implemented(self, engine: ExecutionEngineBase) -> None:
        with pytest.raises(NotImplementedError):
            await engine.benchmark({})

    @pytest.mark.asyncio
    async def test_telemetry_default(self, engine: ExecutionEngineBase) -> None:
        telemetry = await engine.telemetry()
        assert telemetry == []

    @pytest.mark.asyncio
    async def test_get_version(self, engine: ExecutionEngineBase) -> None:
        version = await engine.get_version()
        assert version == "1.0.0"

    @pytest.mark.asyncio
    async def test_get_configuration(self, engine: ExecutionEngineBase) -> None:
        config = await engine.get_configuration()
        assert config.engine_id == engine.descriptor.id

    @pytest.mark.asyncio
    async def test_get_descriptor(self, engine: ExecutionEngineBase) -> None:
        desc = await engine.get_descriptor()
        assert desc is engine.descriptor

    @pytest.mark.asyncio
    async def test_get_capabilities_default(self, engine: ExecutionEngineBase) -> None:
        caps = await engine.get_capabilities()
        assert caps == []

    @pytest.mark.asyncio
    async def test_supports_no_capabilities(self, engine: ExecutionEngineBase) -> None:
        assert not await engine.supports(EngineCapability.CODING)

    @pytest.mark.asyncio
    async def test_estimate_cost_default(self, engine: ExecutionEngineBase) -> None:
        cost = await engine.estimate_cost(ExecutionRequest(action="test"))
        assert cost == 0.0

    @pytest.mark.asyncio
    async def test_estimate_latency_default(self, engine: ExecutionEngineBase) -> None:
        latency = await engine.estimate_latency(ExecutionRequest(action="test"))
        assert latency == 0.0

    @pytest.mark.asyncio
    async def test_get_workspace(self, engine: ExecutionEngineBase) -> None:
        ws = await engine.get_workspace()
        assert ws.path == ""

    @pytest.mark.asyncio
    async def test_interrupt_delegates_to_cancel(self, engine: ExecutionEngineBase) -> None:
        with pytest.raises(NotImplementedError):
            await engine.interrupt("exec-1")

    @pytest.mark.asyncio
    async def test_recover_not_implemented(self, engine: ExecutionEngineBase) -> None:
        with pytest.raises(NotImplementedError):
            await engine.recover("exec-1")

    @pytest.mark.asyncio
    async def test_post_init_sets_descriptor(self) -> None:
        e = ExecutionEngineBase(name="auto", engine_type=EngineType.MCP)
        assert e.descriptor.name == "auto"
        assert e.descriptor.engine_type == EngineType.MCP
        assert e.descriptor.status == EngineStatus.CREATED


class TestCompositeEngine:
    @pytest.fixture
    def composite(self) -> CompositeEngine:
        return CompositeEngine(name="composite")

    @pytest.fixture
    def mock_engine(self) -> ExecutionEngineBase:
        e = ExecutionEngineBase(name="mock-1", engine_type=EngineType.GENERIC)
        # Add a capability via descriptor
        caps = (ExecutionCapability(type=EngineCapability.CODING),)
        object.__setattr__(e, "descriptor", e.descriptor.with_capabilities(list(caps)))
        return e

    def test_add_engine(self, composite: CompositeEngine, mock_engine: ExecutionEngineBase) -> None:
        composite.add_engine("eng-1", mock_engine)
        assert "eng-1" in composite.engines

    def test_remove_engine(
        self, composite: CompositeEngine, mock_engine: ExecutionEngineBase
    ) -> None:
        composite.add_engine("eng-1", mock_engine)
        assert composite.remove_engine("eng-1") is True
        assert composite.remove_engine("nonexistent") is False

    @pytest.mark.asyncio
    async def test_find_best_engine_no_engines(self, composite: CompositeEngine) -> None:
        result = await composite.find_best_engine()
        assert result is None

    @pytest.mark.asyncio
    async def test_find_best_engine_any(
        self, composite: CompositeEngine, mock_engine: ExecutionEngineBase
    ) -> None:
        composite.add_engine("eng-1", mock_engine)
        result = await composite.find_best_engine()
        assert result is not None
        assert result[0] == "eng-1"

    @pytest.mark.asyncio
    async def test_find_best_engine_with_capability(
        self, composite: CompositeEngine, mock_engine: ExecutionEngineBase
    ) -> None:
        composite.add_engine("eng-1", mock_engine)
        result = await composite.find_best_engine(required_capability=EngineCapability.CODING)
        assert result is not None
        assert result[0] == "eng-1"

    @pytest.mark.asyncio
    async def test_find_best_engine_missing_capability(
        self, composite: CompositeEngine, mock_engine: ExecutionEngineBase
    ) -> None:
        composite.add_engine("eng-1", mock_engine)
        result = await composite.find_best_engine(required_capability=EngineCapability.DOCKER)
        assert result is None

    @pytest.mark.asyncio
    async def test_execute_on_best_no_engines(self, composite: CompositeEngine) -> None:
        result = await composite.execute_on_best(ExecutionRequest(action="test"))
        assert result.status == "failed"
        assert "No available engine" in result.error

    @pytest.mark.asyncio
    async def test_execute_on_best_not_implemented(
        self, composite: CompositeEngine, mock_engine: ExecutionEngineBase
    ) -> None:
        composite.add_engine("eng-1", mock_engine)
        result = await composite.execute_on_best(ExecutionRequest(action="test"))
        assert result.status == "failed"
