"""Composition root — assembles the kernel from ports + adapters.

This is the ONLY place that knows about concrete implementations. Swapping the
bus, a provider, or a subsystem changes nothing here beyond the factory/config.
Phase 2 subsystems (provider management, memory, capability, security) are wired
here behind their ports. The :class:`Platform` bundle is the single object the
API layer receives.
"""

from __future__ import annotations

from dataclasses import dataclass

from agentic_os.adapters.bus.factory import build_bus
from agentic_os.adapters.plugins.loader import load_plugins
from agentic_os.adapters.security.encrypted_store import EncryptedSecretStore
from agentic_os.api.dashboard import DashboardBroadcaster
from agentic_os.config import settings
from agentic_os.core.capability.engine import CapabilityEngine
from agentic_os.core.health import HealthMonitorImpl
from agentic_os.core.memory.manager import MemoryManagerImpl
from agentic_os.core.orchestrator import Orchestrator
from agentic_os.core.providers.health import ProviderHealthMonitorImpl
from agentic_os.core.providers.manager import ModelManagerImpl, ProviderManagerImpl
from agentic_os.core.providers.router import ProviderRouter
from agentic_os.core.providers.routing import CostTrackerImpl, RateLimitMonitorImpl
from agentic_os.core.providers.vault import ApiKeyVaultImpl
from agentic_os.core.recovery import RecoveryManagerImpl
from agentic_os.core.registry import AgentRegistry, ProviderRegistry
from agentic_os.core.scheduler import Scheduler
from agentic_os.core.security.framework import SecurityFramework
from agentic_os.infrastructure.logging import configure_logging, get_logger

log = get_logger("kernel")


@dataclass
class Platform:
    """Bundle of every subsystem, handed to the API layer."""

    bus: object
    registry: AgentRegistry
    providers: ProviderRegistry
    orchestrator: Orchestrator
    scheduler: Scheduler
    health: HealthMonitorImpl
    recovery: RecoveryManagerImpl
    dashboard: DashboardBroadcaster
    provider_mgr: ProviderManagerImpl
    model_mgr: ModelManagerImpl
    vault: ApiKeyVaultImpl
    provider_health: ProviderHealthMonitorImpl
    cost: CostTrackerImpl
    rate: RateLimitMonitorImpl
    router: ProviderRouter
    secret_store: EncryptedSecretStore
    # Subsystems 2-4 attached by the kernel (may be None until wired).
    memory: MemoryManagerImpl | None = None
    capability: CapabilityEngine | None = None
    security: SecurityFramework | None = None


class Kernel:
    def __init__(self) -> None:
        configure_logging(settings.log_level)
        self.bus = build_bus(settings)
        self.registry = AgentRegistry()
        self.providers = ProviderRegistry()
        self.scheduler = Scheduler()

        # Provider Management subsystem
        self.provider_mgr = ProviderManagerImpl()
        self.model_mgr = ModelManagerImpl(self.provider_mgr)
        self.secret_store = EncryptedSecretStore()
        self.vault = ApiKeyVaultImpl(self.secret_store)
        self.provider_health = ProviderHealthMonitorImpl(
            self.bus, self.provider_mgr, self.scheduler
        )
        self.cost = CostTrackerImpl()
        self.rate = RateLimitMonitorImpl()
        self.cost.bind_models(self.model_mgr)

        # Memory subsystem (S2): default in-memory store + vector + graph.
        from agentic_os.adapters.memory.in_memory import (
            InMemoryKnowledgeGraph,
            InMemoryVectorStore,
        )

        self.memory = MemoryManagerImpl(
            self.bus,
            vector=InMemoryVectorStore(),
            graph=InMemoryKnowledgeGraph(),
        )

        # Security Framework (S4): RBAC + workspace isolation + approval gate +
        # audit, over the encrypted secret store (ADR-0006).
        self.security = SecurityFramework(self.bus, self.secret_store)
        self.router = ProviderRouter(
            self.bus,
            self.provider_mgr,
            self.model_mgr,
            self.provider_health,
            self.rate,
            policy=settings.routing_policy,
        )

        # Orchestrator + supervision
        self.orchestrator = Orchestrator(self.bus, self.registry, self.providers, settings)
        self.health = HealthMonitorImpl(self.bus, self.registry, self.scheduler, settings)
        self.recovery = RecoveryManagerImpl(self.bus, self.orchestrator, settings)
        self.dashboard = DashboardBroadcaster(self.bus)

        self.capability = CapabilityEngine(self.bus)
        self._plugins: list = []

    async def start(self) -> None:
        await self.bus.start()
        self._plugins = load_plugins(self.registry, self.providers)
        # Seed provider manager from the Phase-1 plugin-loaded providers.
        for adapter in self.providers._providers.values():
            self.provider_mgr.register(adapter)
        self._seed_default_models()
        await self.orchestrator.start()
        await self.scheduler.start()
        await self.health.start()
        await self.recovery.start()
        await self.provider_health.start()
        await self.capability.start()
        await self.dashboard.start()
        log.info("kernel.started", bus=settings.bus_type, plugins=len(self._plugins))

    async def stop(self) -> None:
        await self.dashboard.stop()
        await self.recovery.stop()
        await self.health.stop()
        await self.provider_health.stop()
        await self.scheduler.stop()
        await self.orchestrator.stop()
        await self.bus.stop()
        log.info("kernel.stopped")

    def _seed_default_models(self) -> None:
        """Register example models so routing/cost have candidates.

        Real providers would populate this from their /models endpoint; for the
        foundation we seed representative entries (mock is free; claude_code is
        a placeholder economy). OpenAI-compatible providers add models via the
        API at runtime.
        """
        from agentic_os.ports.provider_management import ModelInfo

        seeds = [
            ModelInfo(
                id="mock-fast", provider="mock", capabilities=["reasoning", "coding", "research"]
            ),
            ModelInfo(
                id="claude-code",
                provider="claude_code",
                capabilities=["coding", "planning", "terminal", "filesystem"],
            ),
        ]
        for m in seeds:
            if self.provider_mgr.get_model(m.provider, m.id) is None:
                self.provider_mgr.register_model(m)

    def platform(self) -> Platform:
        return Platform(
            bus=self.bus,
            registry=self.registry,
            providers=self.providers,
            orchestrator=self.orchestrator,
            scheduler=self.scheduler,
            health=self.health,
            recovery=self.recovery,
            dashboard=self.dashboard,
            provider_mgr=self.provider_mgr,
            model_mgr=self.model_mgr,
            vault=self.vault,
            provider_health=self.provider_health,
            cost=self.cost,
            rate=self.rate,
            router=self.router,
            secret_store=self.secret_store,
            memory=self.memory,
            capability=self.capability,
            security=self.security,
        )


async def run_serve() -> None:
    kernel = Kernel()
    await kernel.start()
    app = _build_app(kernel)
    import uvicorn

    config = uvicorn.Config(
        app, host=settings.http_host, port=settings.http_port, log_level="warning"
    )
    server = uvicorn.Server(config)
    await server.serve()


def _build_app(kernel: Kernel):
    from agentic_os.api.app import create_app

    return create_app(kernel.platform())
