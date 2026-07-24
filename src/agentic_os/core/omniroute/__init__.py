"""OmniRoute Core — provider/model routing engine for AgenticOS.

Factory: :func:`create_omniroute_engine` wires all OmniRoute ports
together and registers them in the DI Container.
"""

from __future__ import annotations

from agentic_os.core.container import Container
from agentic_os.core.health_registry import HealthRegistry
from agentic_os.core.observability_registry import ObservabilityRegistry
from agentic_os.core.omniroute.aggregation import AggregationEngineImpl
from agentic_os.core.omniroute.budgets import BudgetEngineImpl
from agentic_os.core.omniroute.executor import ExecutionEngineImpl
from agentic_os.core.omniroute.failover import CircuitBreakerEngineImpl
from agentic_os.core.omniroute.learning import AdaptiveLearningEngineImpl
from agentic_os.core.omniroute.model_registry import ModelRegistryImpl
from agentic_os.core.omniroute.provider_registry import ProviderRegistryImpl
from agentic_os.core.omniroute.rate_limiter import RateLimiterEngineImpl
from agentic_os.core.omniroute.router import RouterEngineImpl
from agentic_os.core.omniroute.routing_policies import RoutingPolicyEngineImpl
from agentic_os.core.omniroute.scheduler import SchedulerEngineImpl
from agentic_os.ports.event_bus import EventBus as EventBusPort


def create_omniroute_engine(
    container: Container,
    event_bus: EventBusPort,
    health_registry: HealthRegistry,
    observability_registry: ObservabilityRegistry,
) -> None:
    """Build all OmniRoute ports and register them in the Container.

    This is called during kernel Phase OMNIROUTE startup.
    """
    # ── Phase 5.1: Provider Registry ──
    provider_registry = ProviderRegistryImpl(event_bus=event_bus)
    container.register_instance(
        ProviderRegistryImpl,
        provider_registry,
        description="OmniRoute provider registry — CRUD + health + capabilities",
    )
    health_registry.track_service("omniroute.provider_registry")

    # ── Phase 5.2: Model Registry ──
    model_registry = ModelRegistryImpl(
        provider_registry=provider_registry,
        event_bus=event_bus,
    )
    container.register_instance(
        ModelRegistryImpl,
        model_registry,
        description="OmniRoute model registry — CRUD + search + discovery sync",
    )
    health_registry.track_service("omniroute.model_registry")

    # ── Phase 5.4 (wired before 5.3): Routing Policy Engine ──
    policy_engine = RoutingPolicyEngineImpl(event_bus=event_bus)
    container.register_instance(
        RoutingPolicyEngineImpl,
        policy_engine,
        description="OmniRoute routing policy engine — configurable decision layer",
    )
    health_registry.track_service("omniroute.routing_policy_engine")

    # ── Phase 5.5: Circuit Breaker Engine ──
    circuit_breaker = CircuitBreakerEngineImpl(
        event_bus=event_bus,
    )
    container.register_instance(
        CircuitBreakerEngineImpl,
        circuit_breaker,
        description=(
            "OmniRoute circuit breaker engine — provider resilience + failover state machine"
        ),
    )
    health_registry.track_service("omniroute.circuit_breaker")

    # ── Phase 5.6: Budget Engine ──
    budget_engine = BudgetEngineImpl(
        event_bus=event_bus,
    )
    container.register_instance(
        BudgetEngineImpl,
        budget_engine,
        description="OmniRoute budget engine — financial decision layer + spending policies",
    )
    health_registry.track_service("omniroute.budget_engine")

    # ── Phase 5.7: Adaptive Learning Engine ──
    learning_engine = AdaptiveLearningEngineImpl(
        event_bus=event_bus,
    )
    container.register_instance(
        AdaptiveLearningEngineImpl,
        learning_engine,
        description="OmniRoute adaptive learning engine — continuous provider/model intelligence",
    )
    health_registry.track_service("omniroute.adaptive_learning_engine")

    # ── Phase 5.8: Intelligent Rate Limiter & Quota Engine ──
    rate_limiter = RateLimiterEngineImpl(
        event_bus=event_bus,
    )
    container.register_instance(
        RateLimiterEngineImpl,
        rate_limiter,
        description="OmniRoute rate limiter — distributed-capable quota & rate limiting engine",
    )
    health_registry.track_service("omniroute.rate_limiter")

    # ── Phase 5.9: Intelligent Request Scheduler & Queue Manager ──
    scheduler = SchedulerEngineImpl(
        event_bus=event_bus,
    )
    container.register_instance(
        SchedulerEngineImpl,
        scheduler,
        description=(
            "OmniRoute intelligent scheduler — priority queue, fairness, "
            "deadline-aware dispatch, backpressure, and scheduling metrics"
        ),
    )
    health_registry.track_service("omniroute.scheduler")

    # ── Phase 5.10: Execution Engine ──
    execution_engine = ExecutionEngineImpl(
        event_bus=event_bus,
    )
    container.register_instance(
        ExecutionEngineImpl,
        execution_engine,
        description="OmniRoute execution engine — provider invocation, retries, streaming",
    )
    health_registry.track_service("omniroute.execution_engine")

    # ── Phase 5.11: Aggregation Engine ──
    aggregation_engine = AggregationEngineImpl(
        event_bus=event_bus,
    )
    container.register_instance(
        AggregationEngineImpl,
        aggregation_engine,
        description="OmniRoute aggregation engine — response synthesis, consensus, ranking, merge",
    )
    health_registry.track_service("omniroute.aggregation_engine")

    # Phase 5.3: Router Engine (policy, CB, budget, learning, rate limiter, scheduler, exec, agg)
    router_engine = RouterEngineImpl(
        provider_registry=provider_registry,
        model_registry=model_registry,
        event_bus=event_bus,
        routing_policy_engine=policy_engine,
        circuit_breaker=circuit_breaker,
        budget_engine=budget_engine,
        adaptive_learning_engine=learning_engine,
        rate_limiter=rate_limiter,
        scheduler=scheduler,
        execution_engine=execution_engine,
        aggregation_engine=aggregation_engine,
    )
    container.register_instance(
        RouterEngineImpl,
        router_engine,
        description="OmniRoute router engine — intelligent routing pipeline + scoring",
    )
    health_registry.track_service("omniroute.router_engine")


__all__ = [
    "create_omniroute_engine",
]
