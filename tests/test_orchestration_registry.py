"""Tests for OrchestrationAgentRegistry (Phase 4, M3)."""

import pytest

from agentic_os.core.orchestration.registry import OrchestrationAgentRegistry
from agentic_os.domain.execution import (
    EngineCapability,
    EngineStatus,
    EngineType,
    ExecutionCapability,
    ExecutionEngine,
)
from agentic_os.domain.orchestration import AgentDescriptor


class _MockRuntime:
    """Minimal mock RuntimeManager for testing the registry."""

    def __init__(self, engines: list[ExecutionEngine] | None = None) -> None:
        self._engines = engines or []
        self._engine_map = {e.id: e for e in self._engines}

    async def list_engines(self, capability=None, status=None):
        results = list(self._engines)
        if capability:
            cap = capability.value if hasattr(capability, "value") else capability
            results = [e for e in results if cap in {c.type.value for c in e.capabilities}]
        if status:
            results = [e for e in results if e.status.value == status]
        return results

    async def get_engine(self, engine_id):
        return self._engine_map.get(engine_id)

    async def find_engines(self, capability, min_confidence=0.0):
        cap = capability.value if hasattr(capability, "value") else capability
        return [e for e in self._engines if cap in {c.type.value for c in e.capabilities}]

    async def list_capabilities(self):
        return {}

    async def execute(self, engine_id, request):
        from agentic_os.ports.execution import ExecutionResult

        return ExecutionResult(status="completed", output={})

    async def execute_on_best(self, request, required_capability):
        from agentic_os.ports.execution import ExecutionResult

        return ExecutionResult(status="completed", output={})


def _make_engine(
    engine_id: str,
    name: str = "",
    engine_type: str = "generic",
    capabilities: list[str] | None = None,
    status: str = "idle",
) -> ExecutionEngine:
    cap_map: dict[str, EngineCapability] = {
        "code": EngineCapability.CODING,
        "coding": EngineCapability.CODING,
        "research": EngineCapability.RESEARCH,
        "planning": EngineCapability.PLANNING,
        "reasoning": EngineCapability.REASONING,
        "terminal": EngineCapability.TERMINAL,
        "filesystem": EngineCapability.FILESYSTEM,
    }
    exec_caps: list[ExecutionCapability] = []
    for c in capabilities or []:
        ec = cap_map.get(c)
        if ec:
            exec_caps.append(ExecutionCapability(type=ec))
    return ExecutionEngine(
        id=engine_id,
        name=name or engine_id,
        engine_type=EngineType(engine_type)
        if hasattr(EngineType, engine_type)
        else EngineType.GENERIC,
        capabilities=exec_caps,
        status=EngineStatus(status) if hasattr(EngineStatus, status) else EngineStatus.IDLE,
        version="1.0",
    )


class TestOrchestrationAgentRegistry:
    @pytest.fixture
    def empty_runtime(self):
        return _MockRuntime()

    @pytest.fixture
    def populated_runtime(self):
        engines = [
            _make_engine("e1", "Engine-1", "generic", ["code", "research"], "idle"),
            _make_engine("e2", "Engine-2", "generic", ["code"], "running"),
            _make_engine("e3", "Engine-3", "generic", ["research"], "idle"),
        ]
        return _MockRuntime(engines)

    @pytest.fixture
    def registry(self, empty_runtime):
        return OrchestrationAgentRegistry(runtime=empty_runtime)

    @pytest.fixture
    def populated_registry(self, populated_runtime):
        return OrchestrationAgentRegistry(runtime=populated_runtime)

    async def test_list_agents_empty(self, registry) -> None:
        agents = await registry.list_agents()
        assert agents == []

    async def test_list_agents_populated(self, populated_registry) -> None:
        agents = await populated_registry.list_agents()
        assert len(agents) == 3

    async def test_list_agents_fills_cache(self, populated_registry) -> None:
        await populated_registry.list_agents()
        assert len(populated_registry._cache) == 3
        assert "e1" in populated_registry._cache

    async def test_get_agent_found(self, populated_registry) -> None:
        agent = await populated_registry.get_agent("e1")
        assert agent is not None
        assert agent.name == "Engine-1"

    async def test_get_agent_not_found(self, registry) -> None:
        agent = await registry.get_agent("nonexistent")
        assert agent is None

    async def test_get_agent_cache_hit(self, populated_registry) -> None:
        await populated_registry.list_agents()
        agent = await populated_registry.get_agent("e1")
        assert agent is not None
        assert agent.name == "Engine-1"

    async def test_get_agent_capabilities(self, populated_registry) -> None:
        caps = await populated_registry.get_agent_capabilities("e1")
        assert isinstance(caps, list)

    async def test_count_agents(self, populated_registry) -> None:
        count = await populated_registry.count_agents()
        assert count == 3

    async def test_count_agents_empty(self, registry) -> None:
        count = await registry.count_agents()
        assert count == 0

    async def test_find_agents_by_capability(self, populated_registry) -> None:
        agents = await populated_registry.find_agents_by_capability(EngineCapability.CODING)
        assert len(agents) == 2

    async def test_find_agents_by_capability_no_match(self, populated_registry) -> None:
        agents = await populated_registry.find_agents_by_capability(EngineCapability.VISION)
        assert agents == []

    async def test_sync_from_runtime(self, populated_registry) -> None:
        agents = await populated_registry.sync_from_runtime()
        assert len(agents) == 3

    async def test_invalidate_cache_single(self, populated_registry) -> None:
        await populated_registry.list_agents()
        assert "e1" in populated_registry._cache
        populated_registry.invalidate_cache("e1")
        assert "e1" not in populated_registry._cache

    async def test_invalidate_cache_all(self, populated_registry) -> None:
        await populated_registry.list_agents()
        assert len(populated_registry._cache) == 3
        populated_registry.invalidate_cache()
        assert populated_registry._cache == {}

    def test_engine_to_descriptor(self, registry) -> None:
        engine = _make_engine("test-1", "Test", "generic", ["code"], "idle")
        desc = registry._engine_to_descriptor(engine)
        assert isinstance(desc, AgentDescriptor)
        assert desc.agent_id == "test-1"
        assert desc.name == "Test"
        assert "coding" in desc.capabilities

    def test_engine_to_descriptor_no_capabilities(self, registry) -> None:
        engine = _make_engine("e1", "NoCaps")
        desc = registry._engine_to_descriptor(engine)
        assert desc.capabilities == ()

    def test_engine_to_descriptor_no_name(self, registry) -> None:
        engine = _make_engine("e1", "")
        desc = registry._engine_to_descriptor(engine)
        # Falls back to engine.id
        assert desc.name == "e1"
