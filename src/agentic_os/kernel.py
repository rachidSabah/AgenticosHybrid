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
from agentic_os.adapters.discovery.config_file import ConfigFileDiscovery
from agentic_os.adapters.discovery.docker_provider import DockerDiscovery
from agentic_os.adapters.discovery.env_var import EnvVarDiscovery
from agentic_os.adapters.discovery.filesystem import FilesystemDiscovery
from agentic_os.adapters.discovery.jetbrains import JetBrainsDiscovery
from agentic_os.adapters.discovery.known_install_dirs import KnownInstallDirDiscovery
from agentic_os.adapters.discovery.path import PathDiscovery

# Discovery providers (M2)
from agentic_os.adapters.discovery.registry_provider import WindowsRegistryDiscovery
from agentic_os.adapters.discovery.vscode import VSCodeDiscovery
from agentic_os.adapters.discovery.wsl_provider import WslDiscovery

# Engine adapters
from agentic_os.adapters.engines.generic import GenericExecutionEngine
from agentic_os.adapters.plugins.loader import load_plugins
from agentic_os.adapters.security.encrypted_store import EncryptedSecretStore
from agentic_os.api.dashboard import DashboardBroadcaster
from agentic_os.config import settings
from agentic_os.core.capability.engine import CapabilityEngine

# Phase 4, M2: Discovery Framework
from agentic_os.core.discovery import (
    DiscoveryCache,
    DiscoveryConfiguration,
    DiscoveryEventPublisher,
    DiscoveryFramework,
    DiscoveryRegistry,
    DiscoveryScheduler,
    DiscoveryTelemetry,
    ProfilingEngine,
    ValidationPipeline,
)
from agentic_os.core.discovery.validation import (
    CapabilityMatchValidator,
    ExecutableExistsValidator,
    PermissionValidator,
    VersionDetectValidator,
)
from agentic_os.core.health import HealthMonitorImpl
from agentic_os.core.memory.manager import MemoryManagerImpl
from agentic_os.core.orchestration.config import OrchestrationConfiguration

# Phase 4, M3: Orchestration Framework
from agentic_os.core.orchestration.framework import OrchestrationFramework
from agentic_os.core.orchestrator import Orchestrator
from agentic_os.core.pipeline.engine import PipelineEngineImpl
from agentic_os.core.providers.health import ProviderHealthMonitorImpl
from agentic_os.core.providers.manager import ModelManagerImpl, ProviderManagerImpl
from agentic_os.core.providers.router import ProviderRouter
from agentic_os.core.providers.routing import CostTrackerImpl, RateLimitMonitorImpl
from agentic_os.core.providers.vault import ApiKeyVaultImpl
from agentic_os.core.recovery import RecoveryManagerImpl
from agentic_os.core.registry import AgentRegistry, ProviderRegistry
from agentic_os.core.runtime.capabilities import CapabilityNegotiator
from agentic_os.core.runtime.discovery import DiscoveryEngine

# Phase 4: Runtime Manager
from agentic_os.core.runtime.manager import RuntimeManager
from agentic_os.core.runtime.registry import RuntimeRegistryImpl
from agentic_os.core.scheduler import Scheduler
from agentic_os.core.security.framework import SecurityFramework
from agentic_os.core.workflow.engine import WorkflowEngineImpl
from agentic_os.domain.discovery import DiscoveryProfile, DiscoveryProviderConfig
from agentic_os.domain.execution import EngineType
from agentic_os.infrastructure.logging import configure_logging, get_logger
from agentic_os.ports.execution import DiscoveryProvider

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
    # Phase 3B: Workflow and Pipeline engines
    workflow: WorkflowEngineImpl | None = None
    pipeline: PipelineEngineImpl | None = None
    # Phase 4: Runtime Manager
    runtime: RuntimeManager | None = None
    # Phase 4, M2: Discovery Framework
    discovery_framework: DiscoveryFramework | None = None
    # Phase 4, M3: Orchestration Framework
    orchestration: OrchestrationFramework | None = None


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

        # Workflow & Pipeline engines (Phase 3B)
        self.workflow = WorkflowEngineImpl(self.bus, self.router, self.registry)
        self.pipeline = PipelineEngineImpl(self.bus, self.router, self.registry)

        # Orchestrator + supervision
        self.orchestrator = Orchestrator(self.bus, self.registry, self.providers, settings)
        self.health = HealthMonitorImpl(self.bus, self.registry, self.scheduler, settings)
        self.recovery = RecoveryManagerImpl(self.bus, self.orchestrator, settings)
        self.dashboard = DashboardBroadcaster(self.bus)

        self.capability = CapabilityEngine(self.bus)
        self._plugins: list = []

        # Phase 4: Runtime Manager — universal execution engine framework
        runtime_registry = RuntimeRegistryImpl(self.bus)
        discovery_engine = DiscoveryEngine()
        if settings.runtime_discovery_enabled:
            discovery_engine.add_provider(PathDiscovery())
        negotiator = CapabilityNegotiator()
        self.runtime = RuntimeManager(
            bus=self.bus,
            registry=runtime_registry,
            discovery=discovery_engine,
            negotiator=negotiator,
        )

        # Phase 4, M2: Discovery Framework — automatic runtime discovery & binding
        self.discovery_framework = self._build_discovery_framework(discovery_engine)

        # Phase 4, M3: Orchestration Framework — multi-agent orchestration & swarm intelligence
        self.orchestration = self._build_orchestration_framework()

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

        # Phase 4: Initialize runtime and register generic engine
        if self.runtime:
            generic = GenericExecutionEngine(name="generic", engine_type=EngineType.GENERIC)
            await generic.initialize()
            await self.runtime.register_from_adapter("generic", generic)
            await self.runtime.initialize()

        # Phase 4, M2: Start discovery framework
        if self.discovery_framework:
            await self.discovery_framework.start_auto_discovery()
            if settings.discovery_hot_reload_enabled:
                await self.discovery_framework.start_hot_reload()

        # Phase 4, M3: Start orchestration framework
        if self.orchestration:
            await self.orchestration.start()

        log.info("kernel.started", bus=settings.bus_type, plugins=len(self._plugins))

    async def stop(self) -> None:
        # Phase 4, M3: Stop orchestration framework first (depends on runtime & bus)
        if self.orchestration:
            await self.orchestration.stop()
        # Phase 4, M2: Stop discovery framework
        if self.discovery_framework:
            await self.discovery_framework.stop_hot_reload()
            await self.discovery_framework.stop_auto_discovery()
        # Phase 4: Shutdown runtime
        if self.runtime:
            await self.runtime.shutdown()
        await self.dashboard.stop()
        await self.recovery.stop()
        await self.health.stop()
        await self.provider_health.stop()
        await self.scheduler.stop()
        await self.orchestrator.stop()
        await self.bus.stop()
        log.info("kernel.stopped")

    def _build_discovery_framework(
        self, discovery_engine: DiscoveryEngine
    ) -> DiscoveryFramework | None:
        """Build and return the M2 DiscoveryFramework with all providers."""
        if not settings.runtime_discovery_enabled:
            return None

        # ── Build sub-components ──
        cache = DiscoveryCache(
            ttl_seconds=settings.discovery_cache_ttl_seconds,
            max_entries=settings.discovery_max_cache_entries,
        )
        telemetry = DiscoveryTelemetry(max_entries=settings.discovery_telemetry_max_entries)
        publisher = DiscoveryEventPublisher(bus=self.bus)

        config_m2 = DiscoveryConfiguration(
            enabled=True,
            default_profile=settings.discovery_default_profile,
            cache_ttl_seconds=settings.discovery_cache_ttl_seconds,
            max_cache_entries=settings.discovery_max_cache_entries,
            telemetry_max_entries=settings.discovery_telemetry_max_entries,
        )

        # Add default profile
        config_m2.add_profile(
            DiscoveryProfile(
                name="default",
                description="Default discovery profile — all providers, balanced settings",
                interval_seconds=settings.runtime_discovery_interval_seconds,
                validate_after_discovery=settings.discovery_validation_enabled,
                profile_after_discovery=settings.discovery_profiling_enabled,
                auto_register=True,
                tags=("default", "all-providers"),
            )
        )

        registry = DiscoveryRegistry()

        # ── Register all discovery providers ──
        providers: list[tuple[str, DiscoveryProvider]] = [
            ("path", PathDiscovery()),
            ("registry", WindowsRegistryDiscovery()),
            ("wsl", WslDiscovery()),
            ("docker", DockerDiscovery()),
            ("filesystem", FilesystemDiscovery()),
            ("known-install-dirs", KnownInstallDirDiscovery()),
            ("config-file", ConfigFileDiscovery()),
            ("env-var", EnvVarDiscovery()),
            ("vscode", VSCodeDiscovery()),
            ("jetbrains", JetBrainsDiscovery()),
        ]
        for name, provider in providers:
            config = DiscoveryProviderConfig(
                name=name,
                provider_type=provider.get_provider_type(),
                enabled=True,
                interval_seconds=settings.runtime_discovery_interval_seconds,
            )
            registry.register(name, provider, config)
            discovery_engine.add_provider(provider)

        # ── Build validation pipeline ──
        validation_pipeline = ValidationPipeline()
        if settings.discovery_validation_enabled:
            validation_pipeline.add_validator(ExecutableExistsValidator())
            validation_pipeline.add_validator(VersionDetectValidator())
            validation_pipeline.add_validator(CapabilityMatchValidator())
            validation_pipeline.add_validator(PermissionValidator())

        # ── Build profiling engine ──
        profiling_engine = ProfilingEngine()

        # ── Build scheduler ──
        scheduler = DiscoveryScheduler()

        # ── Build the framework ──
        framework = DiscoveryFramework(
            bus=self.bus,
            core_engine=discovery_engine,
            registry=registry,
            cache=cache,
            telemetry=telemetry,
            scheduler=scheduler,
            config=config_m2,
            validation=validation_pipeline,
            profiling=profiling_engine,
            publisher=publisher,
        )
        framework.bind_runtime(self.runtime)

        log.info(
            "discovery_framework.built",
            providers=len(providers),
            validators=len(validation_pipeline._validators),
            default_profile=settings.discovery_default_profile,
        )
        return framework

    def _build_orchestration_framework(self) -> OrchestrationFramework | None:
        """Build and return the M3 OrchestrationFramework."""
        if not settings.orchestration_enabled or self.runtime is None:
            return None

        config_m3 = OrchestrationConfiguration(
            enabled=True,
            default_topology=settings.orchestration_default_topology,
            agent_sync_interval_seconds=settings.runtime_discovery_interval_seconds,
            communication_history_max=1000,
            telemetry_max_entries=settings.orchestration_telemetry_max_entries,
        )

        framework = OrchestrationFramework(
            bus=self.bus,
            runtime=self.runtime,
            config=config_m3,
        )

        log.info("orchestration_framework.built")
        return framework

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
            workflow=self.workflow,
            pipeline=self.pipeline,
            runtime=self.runtime,
            discovery_framework=self.discovery_framework,
            orchestration=self.orchestration,
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
