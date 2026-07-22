"""Provider Router facade.

Ties together the manager, health monitor, routing policies, rate limiter, and
failover into a single decision point used by the orchestrator's dispatcher.
This is the production implementation behind the routing/failover requirements.
"""

from typing import Any

from agentic_os.core.providers.health import FailoverPolicyImpl, ProviderHealthMonitorImpl
from agentic_os.core.providers.manager import ModelManagerImpl, ProviderManagerImpl
from agentic_os.core.providers.routing import (
    CostRoutingPolicy,
    LatencyRoutingPolicy,
    RateLimitMonitorImpl,
    RoundRobinRoutingPolicy,
)
from agentic_os.domain.events import EventEnvelope, Topic
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.event_bus import EventBus
from agentic_os.ports.provider_management import RoutingPolicy

log = get_logger("providers.router")

_POLICY_REGISTRY: dict[str, type[RoutingPolicy]] = {
    "latency": LatencyRoutingPolicy,
    "cost": CostRoutingPolicy,
    "round_robin": RoundRobinRoutingPolicy,
}


class ProviderRouter:
    def __init__(
        self,
        bus: EventBus,
        manager: ProviderManagerImpl,
        models: ModelManagerImpl,
        health: ProviderHealthMonitorImpl,
        rate: RateLimitMonitorImpl,
        policy: str = "latency",
    ) -> None:
        self._bus = bus
        self._manager = manager
        self._models = models
        self._health = health
        self._rate = rate
        self._failover = FailoverPolicyImpl()
        self._policy_name = policy
        self._policy = self._build_policy(policy)

    def _build_policy(self, policy: str) -> RoutingPolicy:
        cls = _POLICY_REGISTRY.get(policy, LatencyRoutingPolicy)
        if cls is LatencyRoutingPolicy:
            return LatencyRoutingPolicy(self._manager, self._health)
        if cls is CostRoutingPolicy:
            return CostRoutingPolicy(self._models)
        return cls()

    def set_policy(self, policy: str) -> None:
        self._policy = self._build_policy(policy)
        self._policy_name = policy

    async def select(self, capability: str) -> tuple[str, str] | None:
        """Return (provider, model) for a capability, honoring rate limits."""
        candidates: list[tuple[str, str]] = []
        for m in self._models.by_latency(capability):
            if self._rate.remaining(m.provider) != 0:
                candidates.append((m.provider, m.id))
        pick = await self._policy.select(capability, candidates)
        if pick is None and candidates:
            pick = candidates[0]
        return pick

    async def failover(self, failed_provider: str, capability: str) -> tuple[str, str] | None:
        healthy = [
            m.provider
            for m in self._models.by_latency(capability)
            if self._health.status(m.provider) in ("healthy", "unknown")
        ]
        next_provider = await self._failover.next_provider(failed_provider, capability, healthy)
        if next_provider is None:
            return None
        model = next((m.id for m in self._models.models_for(next_provider)), None)
        if model is None:
            return None
        await self._bus.publish(
            EventEnvelope(
                type="provider.failover",
                source="provider-router",
                topic=Topic.PROVIDER_FAILOVER.value,
                payload={"from": failed_provider, "to": next_provider, "capability": capability},
            )
        )
        return next_provider, model

    async def complete(
        self,
        provider: str,
        model: str,
        messages: list[dict[str, str]],
    ) -> Any:
        """Execute a completion request via the provider adapter."""
        adapter = self._manager.get(provider)
        if not adapter:
            raise ValueError(f"Provider {provider} not found")
        # Use the provider adapter to execute the completion
        # This is a simplified call - in reality would need to construct proper Task/Agent
        from agentic_os.domain.agent import Agent, Task

        agent = Agent(
            id=f"router-{provider}-{model}", role="assistant", provider=provider, model=model
        )
        task = Task(
            id=f"router-task-{model}",
            title=f"router-task-{model}",
            role="assistant",
            description="\n".join(m.get("content", "") for m in messages),
        )
        result = await adapter.execute(agent, task)
        return type("obj", (object,), {"content": result, "usage": None})()

    async def call_mcp(self, server: str, tool: str, args: dict[str, Any]) -> Any:
        """Call an MCP tool via the provider."""
        # TODO: Implement MCP tool calling through provider adapter
        raise NotImplementedError("MCP tool calling not yet implemented via router")
