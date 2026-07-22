"""Composition root — assembles the kernel from ports + adapters.

This is the ONLY place that knows about concrete implementations. Swapping the
bus, a provider, or a subsystem changes nothing here beyond the factory/config.
Phase 2 subsystems (provider management, memory, capability, security) are wired
here behind their ports. The :class:`Platform` bundle is the single object the
API layer receives.
"""

from dataclasses import dataclass

from agentic_os.adapters.bus.factory import build_bus
from agentic_os.adapters.discovery.config_file import ConfigFileDiscovery
from agentic_os.adapters.discovery.docker_provider import DockerDiscovery
from agentic_os.adapters.discovery.env_var import EnvVarDiscovery
from agentic_os.adapters.discovery.filesystem import FilesystemDiscovery
from agentic_os.adapters.discovery.jetbrains import JetBrainsDiscovery
from agentic_os.adapters.discovery.known_install_dirs import KnownInstallDirDiscovery
from agentic_os.adapters.discovery.path import PathDiscovery
from agentic_os.adapters.discovery.choco import ChocolateyDiscovery
from agentic_os.adapters.discovery.npm import NpmDiscovery
from agentic_os.adapters.discovery.cargo import CargoDiscovery
from agentic_os.adapters.discovery.uv_provider import UvDiscovery
from agentic_os.adapters.discovery.shell_profile import ShellProfileDiscovery
from agentic_os.adapters.discovery.winget import WingetDiscovery
from agentic_os.adapters.discovery.scoop import ScoopDiscovery

# Discovery providers (M2)
from agentic_os.adapters.discovery.registry_provider import WindowsRegistryDiscovery
from agentic_os.adapters.discovery.vscode import VSCodeDiscovery
from agentic_os.adapters.discovery.wsl_provider import WslDiscovery

# Engine adapters
from agentic_os.adapters.engines.generic import GenericExecutionEngine
from agentic_os.adapters.plugins.loader import load_plugins
from agentic_os.adapters.security.encrypted_store import EncryptedSecretStore
from agentic_os.api.dashboard import DashboardBroadcaster
from agentic_os.api.mcp_ws import MCPBroadcaster
from agentic_os.config import settings
from agentic_os.core.capability.engine import CapabilityEngine

# Phase 4, M6: Desktop Runtime Foundation
from agentic_os.core.desktop import DesktopRuntimeManager

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

# Phase 5: Learning & Optimization Engine
from agentic_os.core.learning import LearningManager

# Phase 4, M3: MCP Runtime Foundation
from agentic_os.core.mcp.manager import MCPManager
from agentic_os.core.mcp.registry import MCPRegistryImpl
from agentic_os.core.mcp.security import MCPSecurity
from agentic_os.core.memory.manager import MemoryManagerImpl

# Mission Orchestrator
from agentic_os.core.mission import MissionPlannerImpl
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


def _ensure_env() -> None:
    """Generate .env from .env.example if .env doesn't exist yet.

    This ensures first-time users get a ready-to-edit configuration without
    manual file copying. Existing .env files are never overwritten.
    """
    from pathlib import Path

    env_path = Path(".env")
    example_path = Path(".env.example")

    if env_path.exists():
        log.debug("env_check.present", path=str(env_path))
        return

    if not example_path.exists():
        log.warning("env_check.no_template", path=str(example_path))
        return

    try:
        content = example_path.read_text(encoding="utf-8")
        env_path.write_text(content, encoding="utf-8")
        log.info("env_check.generated", path=str(env_path), source=str(example_path))
    except OSError as exc:
        log.error("env_check.failed", error=str(exc))


# Startup diagnostics — written to stderr so the Tauri Rust launcher captures them
_STARTUP_LOG_PREFIX = "[AgenticOS-Startup]"


def _diag(stage: str, status: str, detail: str = "") -> None:
    import sys

    msg = f"{_STARTUP_LOG_PREFIX} {stage}: {status}"
    if detail:
        msg += f" — {detail}"
    print(msg, file=sys.stderr, flush=True)


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
    # Phase 4, M3: Installer Intelligence
    installer_intelligence: object | None = None
    # Phase 4, M3: Orchestration Framework
    orchestration: OrchestrationFramework | None = None
    # Phase 4, M3: MCP Runtime Foundation
    mcp: MCPManager | None = None
    # Phase 4, M3: MCP WebSocket broadcaster
    mcp_ws: MCPBroadcaster | None = None
    # Phase 5: Learning & Optimization Engine
    learning: LearningManager | None = None
    # Phase 4, M6: Desktop Runtime Foundation
    desktop: DesktopRuntimeManager | None = None
    # Mission Orchestrator
    mission_planner: MissionPlannerImpl | None = None


class Kernel:
    def __init__(self) -> None:
        _diag("Configuration", "LOADED", f"bus={settings.bus_type} log_level={settings.log_level}")
        configure_logging(settings.log_level)
        self.bus = build_bus(settings)
        _diag("EventBus", "CREATED", type(self.bus).__name__)
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
        self.mcp_ws = MCPBroadcaster(self.bus)

        self.capability = CapabilityEngine(self.bus)
        self.mission_planner = MissionPlannerImpl(self.bus, settings)
        self._plugins: list = []

        # Phase 4: Runtime Manager — universal execution engine framework
        runtime_registry = RuntimeRegistryImpl(self.bus)
        discovery_engine = DiscoveryEngine()
        if settings.runtime_discovery_enabled:
            discovery_engine.add_provider(PathDiscovery())
            discovery_engine.add_provider(ChocolateyDiscovery())
            discovery_engine.add_provider(NpmDiscovery())
            discovery_engine.add_provider(CargoDiscovery())
            discovery_engine.add_provider(UvDiscovery())
            discovery_engine.add_provider(ShellProfileDiscovery())
            discovery_engine.add_provider(WingetDiscovery())
            discovery_engine.add_provider(ScoopDiscovery())
        negotiator = CapabilityNegotiator()
        self.runtime = RuntimeManager(
            bus=self.bus,
            registry=runtime_registry,
            discovery=discovery_engine,
            negotiator=negotiator,
        )

        # Phase 4, M2: Discovery Framework — automatic runtime discovery & binding
        self.discovery_framework = self._build_discovery_framework(discovery_engine)

        # Phase 4, M3: Installer Intelligence — automatic agent discovery, validation & binding
        try:
            from services.installer.engine import InstallerIntelligence

            self.installer_intelligence = InstallerIntelligence()
            _diag("Installer", "CONSTRUCTED")
        except Exception as exc:
            _diag("Installer", "SKIPPED", str(exc))
            self.installer_intelligence = None

        # Phase 4, M3: Orchestration Framework — multi-agent orchestration & swarm intelligence
        self.orchestration = self._build_orchestration_framework()

        # Phase 4, M3: MCP Runtime Foundation — universal MCP server runtime
        self.mcp = self._build_mcp_framework()

        # Phase 5: Learning & Optimization Engine
        self.learning = self._build_learning_framework()

        # Phase 4, M6: Desktop Runtime Foundation
        self.desktop = DesktopRuntimeManager(self.bus)

        _diag("Kernel", "INITIALIZED", "all subsystems constructed")

    async def start(self) -> None:
        _ensure_env()
        _diag("EventBus", "STARTING")
        await self.bus.start()
        _diag("EventBus", "STARTED")

        _diag("Plugins", "LOADING")
        try:
            self._plugins = load_plugins(self.registry, self.providers)
            _diag("Plugins", "LOADED", f"{len(self._plugins)} plugin(s)")
        except Exception as exc:
            _diag("Plugins", "FAILED", str(exc))
            self._plugins = []
        # Seed provider manager from the Phase-1 plugin-loaded providers.
        for adapter in self.providers._providers.values():
            self.provider_mgr.register(adapter)
        self._seed_default_models()
        _diag("Providers", "SEEDED")

        _diag("Orchestrator", "STARTING")
        await self.orchestrator.start()
        _diag("Orchestrator", "STARTED")
        await self.scheduler.start()
        _diag("Scheduler", "STARTED")
        await self.health.start()
        _diag("Health", "STARTED")
        await self.recovery.start()
        _diag("Recovery", "STARTED")
        await self.provider_health.start()
        _diag("ProviderHealth", "STARTED")
        await self.capability.start()
        _diag("Capability", "STARTED")
        await self.dashboard.start()
        _diag("Dashboard", "STARTED")
        await self.mcp_ws.start()
        _diag("MCP-WS", "STARTED")

        # Phase 4: Initialize runtime and register generic engine
        if self.runtime:
            _diag("Runtime", "INITIALIZING")
            try:
                generic = GenericExecutionEngine(name="generic", engine_type=EngineType.GENERIC)
                await generic.initialize()
                await self.runtime.register_from_adapter("generic", generic)
                await self.runtime.initialize()
                _diag("Runtime", "INITIALIZED")
            except Exception as exc:
                _diag("Runtime", "FAILED", str(exc))

        # Phase 4, M2: Start discovery framework
        if self.discovery_framework:
            _diag("Discovery", "STARTING")
            try:
                await self.discovery_framework.start_auto_discovery()
                if settings.discovery_hot_reload_enabled:
                    await self.discovery_framework.start_hot_reload()
                _diag("Discovery", "STARTED")
            except Exception as exc:
                _diag("Discovery", "FAILED", str(exc))

        # Phase 4, M3: Start installer intelligence
        if self.installer_intelligence:
            _diag("Installer", "STARTING")
            try:
                from services.installer.engine import InstallerIntelligence

                engine: InstallerIntelligence = self.installer_intelligence
                await engine.first_launch()
                _diag("Installer", "STARTED", f"bound={len(engine.bound_providers)} providers")
            except Exception as exc:
                _diag("Installer", "FAILED", str(exc))

        # Phase 4, M3: Start orchestration framework
        if self.orchestration:
            _diag("Orchestration", "STARTING")
            try:
                await self.orchestration.start()
                _diag("Orchestration", "STARTED")
            except Exception as exc:
                _diag("Orchestration", "FAILED", str(exc))

        # Phase 4, M3: Start MCP runtime
        if self.mcp:
            _diag("MCP", "STARTING")
            try:
                await self.mcp.start()
                _diag("MCP", "STARTED")
            except Exception as exc:
                _diag("MCP", "FAILED", str(exc))

        # Phase 5: Start Learning & Optimization Engine
        if self.learning:
            _diag("Learning", "STARTING")
            try:
                await self.learning.start()
                _diag("Learning", "STARTED")
            except Exception as exc:
                _diag("Learning", "FAILED", str(exc))

        # Phase 4, M6: Start Desktop Runtime
        if self.desktop and settings.desktop_enabled:
            _diag("DesktopRuntime", "STARTING")
            try:
                await self.desktop.start()
                _diag("DesktopRuntime", "STARTED")
            except Exception as exc:
                _diag("DesktopRuntime", "FAILED", str(exc))

        _diag("Kernel", "STARTED", f"bus={settings.bus_type} plugins={len(self._plugins)}")
        log.info("kernel.started", bus=settings.bus_type, plugins=len(self._plugins))

    async def stop(self) -> None:
        # Phase 4, M6: Stop Desktop Runtime
        if self.desktop and settings.desktop_enabled:
            await self.desktop.stop()
        # Phase 5: Stop Learning & Optimization Engine
        if self.learning:
            await self.learning.stop()
        # Phase 4, M3: Shutdown MCP runtime
        if self.mcp:
            await self.mcp.shutdown()
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
        await self.mcp_ws.stop()
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

    def _build_mcp_framework(self) -> MCPManager | None:
        """Build and return the M3 MCP Runtime Framework."""
        if not settings.mcp_enabled:
            return None

        registry = MCPRegistryImpl(bus=self.bus)
        security = MCPSecurity(framework=self.security, bus=self.bus)
        manager = MCPManager(registry=registry, bus=self.bus, security=security)

        log.info(
            "mcp_framework.built",
            transport=settings.mcp_default_transport,
            auto_reconnect=settings.mcp_auto_reconnect,
            security_integrated=self.security is not None,
        )
        return manager

    def _build_learning_framework(self) -> LearningManager | None:
        """Build and return the Phase 5 Learning & Optimization Engine."""
        if not settings.learning_enabled:
            return None

        manager = LearningManager(bus=self.bus)

        log.info("learning_framework.built")
        return manager

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
            installer_intelligence=self.installer_intelligence,
            orchestration=self.orchestration,
            mcp=self.mcp,
            mcp_ws=self.mcp_ws,
            desktop=self.desktop,
            learning=self.learning,
            mission_planner=self.mission_planner,
        )


async def run_serve(host: str | None = None, port: int | None = None) -> None:
    h = host or settings.http_host
    p = port or settings.http_port
    settings.http_host = h
    settings.http_port = p
    _diag("Backend", "INITIALIZING", f"host={h} port={p}")

    kernel: Kernel | None = None
    try:
        kernel = Kernel()
        _diag("Kernel", "CONSTRUCTED")
    except Exception as exc:
        import traceback as _tb

        _diag("Kernel", "CONSTRUCTION_FAILED", f"{type(exc).__name__}: {exc}")
        print(f"{_STARTUP_LOG_PREFIX} Traceback:\n{_tb.format_exc()}", flush=True)
        return

    try:
        await kernel.start()
    except Exception as exc:
        import traceback as _tb

        _diag("Kernel", "START_FAILED", f"{type(exc).__name__}: {exc}")
        print(f"{_STARTUP_LOG_PREFIX} Traceback:\n{_tb.format_exc()}", flush=True)
        return

    try:
        app = _build_app(kernel)
        _diag("API", "BUILT")
    except Exception as exc:
        import traceback as _tb

        _diag("API", "BUILD_FAILED", f"{type(exc).__name__}: {exc}")
        print(f"{_STARTUP_LOG_PREFIX} Traceback:\n{_tb.format_exc()}", flush=True)
        return

    _diag("REST-API", "STARTING", f"http://{h}:{p}")
    import uvicorn

    config = uvicorn.Config(app, host=h, port=p, log_level="warning")
    server = uvicorn.Server(config)
    _diag("REST-API", "LISTENING", f"http://{h}:{p}")
    await server.serve()


def _build_app(kernel: Kernel):
    from agentic_os.api.app import create_app

    return create_app(kernel.platform())
