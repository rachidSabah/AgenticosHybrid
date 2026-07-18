"""Agent Registry — wraps RuntimeManager to present engines as agents.

This is the bridge between M1's execution engine model and M3's agent model.
Every agent is a lightweight read-only wrapper around an ExecutionEngine.
"""

from typing import Any

from agentic_os.core.runtime.manager import RuntimeManager
from agentic_os.domain.execution import EngineCapability, ExecutionCapability, ExecutionEngine
from agentic_os.domain.orchestration import AgentDescriptor
from agentic_os.infrastructure.logging import get_logger

log = get_logger("orchestration.registry")


class OrchestrationAgentRegistry:
    """Wraps RuntimeManager to present execution engines as agents.

    Maintains a local cache of AgentDescriptors that is refreshed on every
    call to ``list_agents()`` from the underlying runtime. The cache provides
    fast lookup by agent ID without repeated calls to the registry.
    """

    def __init__(
        self,
        runtime: RuntimeManager,
        **kwargs: Any,
    ) -> None:
        self._runtime = runtime
        self._cache: dict[str, AgentDescriptor] = {}

    async def list_agents(
        self,
        capability: EngineCapability | None = None,
        status: str | None = None,
    ) -> list[AgentDescriptor]:
        """List all available agents (wrapped execution engines), optionally filtered."""
        engines = await self._runtime.list_engines(
            capability=capability,
            status=status,
        )
        agents = [self._engine_to_descriptor(e) for e in engines]
        self._cache = {a.agent_id: a for a in agents}
        return agents

    async def get_agent(self, agent_id: str) -> AgentDescriptor | None:
        """Get an agent by its engine ID, from cache or runtime."""
        # Fast path: check cache first
        cached = self._cache.get(agent_id)
        if cached is not None:
            return cached

        # Slow path: query runtime
        engine = await self._runtime.get_engine(agent_id)
        if engine is None:
            return None

        descriptor = self._engine_to_descriptor(engine)
        self._cache[agent_id] = descriptor
        return descriptor

    async def get_agent_capabilities(self, agent_id: str) -> list[ExecutionCapability]:
        """Get capabilities of a specific agent."""
        agent = await self.get_agent(agent_id)
        if agent is None:
            return []
        caps = await self._runtime.list_capabilities()
        return caps.get(agent_id, [])

    async def count_agents(self) -> int:
        """Total number of available agents."""
        engines = await self._runtime.list_engines()
        return len(engines)

    async def find_agents_by_capability(
        self, capability: EngineCapability, min_confidence: float = 0.0
    ) -> list[AgentDescriptor]:
        """Find agents matching a capability."""
        engines = await self._runtime.find_engines(capability, min_confidence)
        return [self._engine_to_descriptor(e) for e in engines]

    async def sync_from_runtime(self) -> list[AgentDescriptor]:
        """Refresh the full agent cache from the runtime."""
        engines = await self._runtime.list_engines()
        agents = [self._engine_to_descriptor(e) for e in engines]
        self._cache = {a.agent_id: a for a in agents}
        log.info("Agent cache synced from runtime", count=len(agents))
        return agents

    def invalidate_cache(self, agent_id: str | None = None) -> None:
        """Invalidate the cache for a specific agent or the entire cache."""
        if agent_id:
            self._cache.pop(agent_id, None)
        else:
            self._cache.clear()

    # ── Internal ──

    def _engine_to_descriptor(self, engine: ExecutionEngine) -> AgentDescriptor:
        """Convert an M1 ExecutionEngine to an M3 AgentDescriptor.

        This is a lightweight read-only conversion — no state is duplicated.
        The descriptor reflects the engine's current metadata at the time
        of conversion.
        """
        return AgentDescriptor(
            agent_id=engine.id,
            name=engine.name or engine.id,
            engine_type=engine.engine_type.value
            if hasattr(engine.engine_type, "value")
            else str(engine.engine_type),
            capabilities=tuple(
                c.type.value if hasattr(c.type, "value") else str(c.type)
                for c in engine.capabilities
            ),
            status=engine.status.value if hasattr(engine.status, "value") else engine.status,
            health_status=engine.health.status.value
            if hasattr(engine.health, "status")
            else "unknown",
            latency_ms=0.0,
            metadata=dict(engine.metadata) if hasattr(engine, "metadata") else {},
        )
