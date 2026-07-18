"""Tests for GenericExecutionEngine reference adapter."""

import pytest

from agentic_os.adapters.engines.generic import GenericExecutionEngine
from agentic_os.domain.execution import (
    EngineCapability,
    EngineStatus,
    EngineType,
)
from agentic_os.ports.execution import ExecutionRequest


class TestGenericExecutionEngine:
    @pytest.fixture
    def engine(self) -> GenericExecutionEngine:
        return GenericExecutionEngine(name="test-generic", engine_type=EngineType.GENERIC)

    @pytest.mark.asyncio
    async def test_initialize(self, engine: GenericExecutionEngine) -> None:
        descriptor = await engine.initialize()
        assert descriptor.status == EngineStatus.RUNNING
        assert descriptor.name == "test-generic"
        assert len(descriptor.capabilities) > 0

    @pytest.mark.asyncio
    async def test_shutdown(self, engine: GenericExecutionEngine) -> None:
        await engine.initialize()
        await engine.shutdown()
        assert engine.descriptor.status == EngineStatus.STOPPED

    @pytest.mark.asyncio
    async def test_health_check(self, engine: GenericExecutionEngine) -> None:
        await engine.initialize()
        health = await engine.health_check()
        assert health.status == "healthy"
        assert health.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_execute_echo(self, engine: GenericExecutionEngine) -> None:
        await engine.initialize()
        result = await engine.execute(ExecutionRequest(action="echo", payload={"key": "value"}))
        assert result.status == "completed"
        assert result.output == {"key": "value"}

    @pytest.mark.asyncio
    async def test_execute_ping(self, engine: GenericExecutionEngine) -> None:
        await engine.initialize()
        result = await engine.execute(ExecutionRequest(action="ping"))
        assert result.status == "completed"
        assert result.output["pong"] is True

    @pytest.mark.asyncio
    async def test_execute_sleep(self, engine: GenericExecutionEngine) -> None:
        await engine.initialize()
        result = await engine.execute(ExecutionRequest(action="sleep", payload={"seconds": 0.01}))
        assert result.status == "completed"
        assert result.output["slept"] == 0.01

    @pytest.mark.asyncio
    async def test_execute_info(self, engine: GenericExecutionEngine) -> None:
        await engine.initialize()
        result = await engine.execute(ExecutionRequest(action="info"))
        assert result.status == "completed"
        assert "system" in result.output

    @pytest.mark.asyncio
    async def test_execute_fail(self, engine: GenericExecutionEngine) -> None:
        await engine.initialize()
        result = await engine.execute(ExecutionRequest(action="fail", payload={"message": "oops"}))
        assert result.status == "failed"
        assert "oops" in result.error

    @pytest.mark.asyncio
    async def test_execute_unknown_action(self, engine: GenericExecutionEngine) -> None:
        await engine.initialize()
        result = await engine.execute(ExecutionRequest(action="nonexistent"))
        assert result.status == "failed"

    @pytest.mark.asyncio
    async def test_cancel(self, engine: GenericExecutionEngine) -> None:
        await engine.initialize()
        result = await engine.cancel("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_get_capabilities(self, engine: GenericExecutionEngine) -> None:
        await engine.initialize()
        caps = await engine.get_capabilities()
        assert len(caps) > 0
        types = {c.type for c in caps}
        assert EngineCapability.PLANNING in types

    @pytest.mark.asyncio
    async def test_supports(self, engine: GenericExecutionEngine) -> None:
        await engine.initialize()
        assert await engine.supports(EngineCapability.PLANNING) is True
        assert await engine.supports(EngineCapability.DOCKER) is False

    @pytest.mark.asyncio
    async def test_get_version(self, engine: GenericExecutionEngine) -> None:
        await engine.initialize()
        version = await engine.get_version()
        assert version == "0.1.0"

    @pytest.mark.asyncio
    async def test_get_configuration(self, engine: GenericExecutionEngine) -> None:
        await engine.initialize()
        config = await engine.get_configuration()
        assert config.engine_id == engine.descriptor.id
        assert "supported_actions" in config.settings

    @pytest.mark.asyncio
    async def test_get_workspace(self, engine: GenericExecutionEngine) -> None:
        await engine.initialize()
        ws = await engine.get_workspace()
        assert ws.path is not None

    @pytest.mark.asyncio
    async def test_estimate_cost(self, engine: GenericExecutionEngine) -> None:
        await engine.initialize()
        cost = await engine.estimate_cost(ExecutionRequest(action="echo"))
        assert cost == 0.0

    @pytest.mark.asyncio
    async def test_estimate_latency(self, engine: GenericExecutionEngine) -> None:
        await engine.initialize()
        latency = await engine.estimate_latency(ExecutionRequest(action="echo"))
        assert latency == 10.0

    @pytest.mark.asyncio
    async def test_estimate_latency_sleep(self, engine: GenericExecutionEngine) -> None:
        await engine.initialize()
        latency = await engine.estimate_latency(
            ExecutionRequest(action="sleep", payload={"seconds": 2})
        )
        assert latency == 2000.0

    @pytest.mark.asyncio
    async def test_execute_before_initialize(self, engine: GenericExecutionEngine) -> None:
        # Engine should work even without explicit initialize
        result = await engine.execute(ExecutionRequest(action="ping"))
        assert result.status == "completed"
