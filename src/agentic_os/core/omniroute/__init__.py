"""OmniRoute Core — provider/model routing engine for AgenticOS.

Factory: :func:`create_omniroute_engine` wires all OmniRoute ports
together and registers them in the DI Container.
"""

from __future__ import annotations

from agentic_os.core.container import Container
from agentic_os.core.health_registry import HealthRegistry
from agentic_os.core.observability_registry import ObservabilityRegistry
from agentic_os.core.omniroute.model_registry import ModelRegistryImpl
from agentic_os.core.omniroute.provider_registry import ProviderRegistryImpl
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


__all__ = [
    "create_omniroute_engine",
]
