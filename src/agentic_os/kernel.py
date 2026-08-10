"""Composition root — assembles the kernel from ports + adapters.

This is the ONLY place that knows about concrete implementations. Swapping the
bus, a provider, or a subsystem changes nothing here beyond the factory/config.
Phase 2 subsystems (provider management, memory, capability, security) are wired
here behind their ports. The :class:`Platform` bundle is the single object the
API layer receives.
"""

import os
from dataclasses import dataclass
from typing import Any

from agentic_os.adapters.bus.factory import build_bus
from agentic_os.adapters.discovery.cargo import CargoDiscovery
from agentic_os.adapters.discovery.choco import ChocolateyDiscovery
from agentic_os.adapters.discovery.config_file import ConfigFileDiscovery
from agentic_os.adapters.discovery.docker_provider import DockerDiscovery
from agentic_os.adapters.discovery.env_var import EnvVarDiscovery
from agentic_os.adapters.discovery.filesystem import FilesystemDiscovery
from agentic_os.adapters.discovery.jetbrains import JetBrainsDiscovery
from agentic_os.adapters.discovery.known_install_dirs import KnownInstallDirDiscovery
from agentic_os.adapters.discovery.npm import NpmDiscovery
from agentic_os.adapters.discovery.path import PathDiscovery

# Discovery providers (M2)
from agentic_os.adapters.discovery.registry_provider import WindowsRegistryDiscovery
from agentic_os.adapters.discovery.scoop import ScoopDiscovery
from agentic_os.adapters.discovery.shell_profile import ShellProfileDiscovery
from agentic_os.adapters.discovery.uv_provider import UvDiscovery
from agentic_os.adapters.discovery.vscode import VSCodeDiscovery
from agentic_os.adapters.discovery.winget import WingetDiscovery
from agentic_os.adapters.discovery.wsl_provider import WslDiscovery

# Engine adapters
from agentic_os.adapters.engines.generic import GenericExecutionEngine
from agentic_os.adapters.plugins.loader import load_plugins
from agentic_os.adapters.security.encrypted_store import EncryptedSecretStore
from agentic_os.api.dashboard import DashboardBroadcaster
from agentic_os.api.mcp_ws import MCPBroadcaster
from agentic_os.config import settings
from agentic_os.core.brains import (
    BrainCatalog,
    BrainDiscoveryBridge,
    BrainHealthMonitor,
    BrainManager,
    BrainRegistry,
    BrainRelationshipGraph,
    BrainStatistics,
    RuntimeBridge,
)
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
    LocalDiscoveryService,
    ProfilingEngine,
    ValidationPipeline,
)
from agentic_os.core.discovery.validation import (
    CapabilityMatchValidator,
    ExecutableExistsValidator,
    PermissionValidator,
    VersionDetectValidator,
)

# Mission Orchestrator
from agentic_os.core.execution_log import ExecutionLog
from agentic_os.core.health import HealthMonitorImpl

# Phase 5: Learning & Optimization Engine
from agentic_os.core.learning import LearningManager

# Phase 4, M3: MCP Runtime Foundation
from agentic_os.core.mcp.manager import MCPManager
from agentic_os.core.mcp.registry import MCPRegistryImpl
from agentic_os.core.mcp.security import MCPSecurity
from agentic_os.core.memory.manager import MemoryManagerImpl
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
from agentic_os.domain.brains import RelationshipType
from agentic_os.domain.discovery import DiscoveryProfile, DiscoveryProviderConfig
from agentic_os.domain.events import EventEnvelope  # EventEnvelope for event publishing
from agentic_os.domain.execution import EngineType
from agentic_os.infrastructure.logging import configure_logging, get_logger
from agentic_os.ports.event_bus import EventBus
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

    bus: EventBus
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
    # Phase 6.1: Local Agent Discovery & Auto-Binding
    local_discovery: LocalDiscoveryService | None = None
    # Phase 6.2: AI Brain Registry & Agent Constellation
    brain_registry: BrainRegistry | None = None
    brain_manager: BrainManager | None = None
    brain_catalog: BrainCatalog | None = None
    brain_graph: BrainRelationshipGraph | None = None
    brain_stats: BrainStatistics | None = None
    brain_health: BrainHealthMonitor | None = None
    brain_discovery_bridge: BrainDiscoveryBridge | None = None
    brain_runtime_bridge: RuntimeBridge | None = None
    # Phase 11: Executive Intelligence Layer
    executive_controller: Any = None  # ExecutiveController | None
    # Phase 12: Cognitive Intelligence Layer
    cognitive_controller: Any = None  # CognitiveController | None
    swarm_coordinator: Any = None  # SwarmCoordinator | None
    # Phase 15: Autonomous Agent Ecosystem
    ecosystem_controller: Any = None  # EcosystemController | None
    # Phase 16: Distributed Runtime Federation
    cluster_controller: Any = None  # ClusterController | None
    # Phase 17: Autonomous Agent Evolution
    evolution_controller: Any = None  # EvolutionController | None
    # Phase 17: Distributed Execution Fabric
    distributed_controller: Any = None  # DistributedController | None
    # Phase 18: Persistent Runtime
    persistent_controller: Any = None  # PersistentController | None
    execution_log: Any = None  # ExecutionLog | None


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
        self.execution_log = ExecutionLog(self.bus)
        from agentic_os.core.worktree_manager import WorktreeManager

        self.worktree_manager = WorktreeManager()
        self.orchestrator = Orchestrator(
            self.bus,
            self.registry,
            self.providers,
            settings,
            execution_log=self.execution_log,
            worktree_manager=self.worktree_manager,
            memory=self.memory,
        )
        self.health = HealthMonitorImpl(self.bus, self.registry, self.scheduler, settings)
        self.recovery = RecoveryManagerImpl(self.bus, self.orchestrator, settings)
        self.dashboard = DashboardBroadcaster(self.bus)
        self.mcp_ws = MCPBroadcaster(self.bus)

        self.capability = CapabilityEngine(self.bus)
        self.mission_planner = MissionPlannerImpl(self.bus, settings)
        self._plugins: list = []
        self._started = False
        self._platform_instance: Platform | None = None
        self.local_discovery = None
        self.executive_controller = None
        self.cognitive_controller = None
        self.swarm_coordinator = None
        # Phase 15-18 controllers (initialized in _start_subsystems; keep None
        # defaults so stop() can shut down cleanly if startup never reached them).
        self.ecosystem_controller = None
        self.cluster_controller = None
        self.evolution_controller = None
        self.distributed_controller = None
        self.persistent_controller = None
        # Phase 6.2: AI Brain Registry & Constellation (initialized in _start_subsystems)
        self.brain_registry = None
        self.brain_manager = None
        self.brain_catalog = None
        self.brain_graph = None
        self.brain_stats = None
        self.brain_health = None
        self.brain_discovery_bridge = None
        self.brain_runtime_bridge = None
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

    async def _start_critical(self) -> None:
        """Start the minimum critical path needed for API to function.

        Starts the EventBus synchronously (required by every endpoint), then
        schedules ALL remaining subsystem init as background tasks so uvicorn
        starts listening in <3 seconds instead of 30+.
        """
        _ensure_env()
        import asyncio

        _diag("EventBus", "STARTING")
        await self.bus.start()
        _diag("EventBus", "STARTED")

        # ── Background: plugins, core subsystems, all frameworks ──
        async def _bg_start() -> None:
            try:
                await self._start_subsystems()
            except BaseException as exc:
                # Catch BaseException (not just Exception) so that
                # SystemExit / KeyboardInterrupt / asyncio.CancelledError
                # are logged instead of silently killing the bg task.
                # On Windows CI we've seen the backend die silently
                # partway through subsystem init; this is a diagnostic
                # net to surface the cause.
                import traceback as _tb

                _diag(
                    "BackgroundInit",
                    "FATAL",
                    f"{type(exc).__name__}: {exc}",
                )
                print(
                    f"{_STARTUP_LOG_PREFIX} BackgroundInit traceback:\n{_tb.format_exc()}",
                    file=__import__("sys").stderr,
                    flush=True,
                )

        asyncio.create_task(_bg_start())
        _diag("Kernel", "CRITICAL_READY", "API server will start immediately")

    async def _start_subsystems(self) -> None:
        """Start all non-critical subsystems in the background."""
        import asyncio

        # Ensure the legacy kernel's bus is started. When ContainerKernel is
        # used, it starts its OWN container-resolved bus but does NOT call
        # legacy._start_critical() — so self.bus (the legacy kernel's bus)
        # may still be unstarted. Without this, events published during
        # subsystem init (e.g. AGENT_DISCOVERED from LocalDiscoveryService)
        # are queued in _pending and never dispatched, breaking the entire
        # Discovery → BrainRegistry → API synchronization pipeline.
        # LocalBus.start() is idempotent.
        try:
            await self.bus.start()
        except Exception:
            log.exception("Failed to start legacy kernel bus in _start_subsystems")

        # ── Plugins ──
        _diag("Plugins", "LOADING")
        try:
            self._plugins = load_plugins(self.registry, self.providers)
            _diag("Plugins", "LOADED", f"{len(self._plugins)} plugin(s)")
        except Exception as exc:
            _diag("Plugins", "FAILED", str(exc))
            self._plugins = []
        for adapter in self.providers._providers.values():
            self.provider_mgr.register(adapter)
        self._seed_default_models()
        _diag("Providers", "SEEDED")

        # ── Orchestrator (core but non-blocking) ──
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

        # ── Runtime ──
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

        # ── Discovery framework ──
        if self.discovery_framework:
            _diag("Discovery", "STARTING")
            try:
                await self.discovery_framework.start_auto_discovery()
                if settings.discovery_hot_reload_enabled:
                    await self.discovery_framework.start_hot_reload()
                _diag("Discovery", "STARTED")
            except Exception as exc:
                _diag("Discovery", "FAILED", str(exc))

        # ── Installer intelligence (was already background) ──
        if self.installer_intelligence:
            _diag("Installer", "SCHEDULING_BACKGROUND")
            try:
                from services.installer.engine import InstallerIntelligence

                engine: InstallerIntelligence = self.installer_intelligence

                async def _installer_bg() -> None:
                    try:
                        await engine.first_launch()
                        _diag(
                            "Installer",
                            "STARTED",
                            f"bound={len(engine.bound_providers)} providers",
                        )
                    except Exception as exc:
                        _diag("Installer", "FAILED", str(exc))

                asyncio.create_task(_installer_bg())
                _diag("Installer", "BACKGROUND_TASK_SCHEDULED")
            except Exception as exc:
                _diag("Installer", "SCHEDULE_FAILED", str(exc))

        # ── Orchestration framework ──
        if self.orchestration:
            _diag("Orchestration", "STARTING")
            try:
                await self.orchestration.start()
                _diag("Orchestration", "STARTED")
            except Exception as exc:
                _diag("Orchestration", "FAILED", str(exc))

        # ── MCP runtime ──
        if self.mcp:
            _diag("MCP", "STARTING")
            try:
                await self.mcp.start()
                _diag("MCP", "STARTED")
            except Exception as exc:
                _diag("MCP", "FAILED", str(exc))

        # ── Learning engine ──
        if self.learning:
            _diag("Learning", "STARTING")
            try:
                await self.learning.start()
                _diag("Learning", "STARTED")
            except Exception as exc:
                _diag("Learning", "FAILED", str(exc))

        # ── Desktop runtime ──
        if self.desktop and settings.desktop_enabled:
            _diag("DesktopRuntime", "STARTING")
            try:
                await self.desktop.start()
                _diag("DesktopRuntime", "STARTED")
            except Exception as exc:
                _diag("DesktopRuntime", "FAILED", str(exc))

        _diag("Kernel", "STARTED", f"bus={settings.bus_type} plugins={len(self._plugins)}")

        # ── Brain Registry & Constellation (Phase 6.2) ────────────────────
        _diag("Brains", "INITIALIZING")
        try:
            self.brain_registry = BrainRegistry()
            self.brain_catalog = BrainCatalog()
            self.brain_graph = BrainRelationshipGraph()
            self.brain_stats = BrainStatistics()
            self.brain_health = BrainHealthMonitor()

            await self.brain_registry.start(event_bus=self.bus)
            await self.brain_graph.start(event_bus=self.bus)

            # Manager needs registry callbacks
            self.brain_manager = BrainManager(
                get_brain=self.brain_registry.get,
                update_brain=self.brain_registry.update,
                event_bus=self.bus,
            )

            # Health monitor needs registry access
            await self.brain_health.start(
                get_brains=self.brain_registry.list_all,
                update_brain=self.brain_registry.update,
                event_bus=self.bus,
            )

            # Bridge subscribes to Phase 6.1 local agent discovery events
            self.brain_discovery_bridge = BrainDiscoveryBridge()
            await self.brain_discovery_bridge.start(
                event_bus=self.bus,
                on_brain_registered=self.brain_registry.register,
                on_brain_removed=self.brain_registry.unregister,
            )

            # Runtime bridge for CLI tool detection
            self.brain_runtime_bridge = RuntimeBridge()

            # ── Auto-detect locally installed brains ──
            # Allow skipping via env var (AGENTICOS_SKIP_BRAIN_AUTODETECT=1)
            # — useful in CI where the Windows process scan has been
            # observed to crash the backend silently.
            import os as _os

            _skip_flag = _os.environ.get("AGENTICOS_SKIP_BRAIN_AUTODETECT", "")
            _skip_brain_autodetect = _skip_flag.lower() in ("1", "true", "yes", "on")
            if _skip_brain_autodetect:
                _diag("Brains", "AUTO_DETECT_SKIPPED", "AGENTICOS_SKIP_BRAIN_AUTODETECT set")
            else:
                _diag("Brains", "AUTO_DETECTING")
                try:
                    detected = await self.brain_runtime_bridge.detect_all_with_windows()
                    registered = 0
                    # Central hub ID for the constellation graph
                    _HUB_ID = "agenticos-hub"
                    for record in detected:
                        # Only register brains that are actually installed
                        if record.health < 50:
                            continue
                        await self.brain_registry.register(record)
                        registered += 1

                        # Add a constellation graph edge: hub → brain
                        if self.brain_graph is not None:
                            await self.brain_graph.add_edge(
                                source_id=_HUB_ID,
                                target_id=record.id,
                                rel_type=RelationshipType.PARENT,
                                metadata={"label": f"{record.display_name} managed by AgenticOS"},
                                weight=max(1.0, record.health / 100.0),
                            )
                        # Publish events the frontend main store understands
                        if self.bus:
                            await self.bus.publish(
                                EventEnvelope(
                                    type="provider.registered",
                                    source="kernel",
                                    topic="provider.registered",
                                    payload={
                                        "name": record.display_name,
                                        "provider": record.display_name,
                                        "vendor": record.vendor,
                                        "status": "healthy" if record.health >= 80 else "degraded",
                                        "latency_ms": record.latency,
                                    },
                                )
                            )
                            if record.health >= 50:
                                await self.bus.publish(
                                    EventEnvelope(
                                        type="agent.started",
                                        source="kernel",
                                        topic="agent.started",
                                        payload={
                                            "id": record.id,
                                            "name": record.display_name,
                                            "provider": record.display_name,
                                            "role": "assistant",
                                            "status": "running"
                                            if record.status in ("connected", "busy", "executing")
                                            else "idle",
                                            "capabilities": list(record.capabilities),
                                        },
                                    )
                                )
                    _diag("Brains", "AUTO_DETECTED", f"{registered} runtimes found")
                except Exception as exc:
                    _diag("Brains", "AUTO_DETECT_FAILED", str(exc))

            _diag(
                "Brains",
                "INITIALIZED",
                f"registry={await self.brain_registry.count()}, graph=ready",
            )

            # Update platform snapshot so existing API routes see live brains
            if self._platform_instance is not None:
                self._platform_instance.brain_registry = self.brain_registry
                self._platform_instance.brain_manager = self.brain_manager
                self._platform_instance.brain_catalog = self.brain_catalog
                self._platform_instance.brain_graph = self.brain_graph
                self._platform_instance.brain_stats = self.brain_stats
                self._platform_instance.brain_health = self.brain_health
                self._platform_instance.brain_discovery_bridge = self.brain_discovery_bridge
                self._platform_instance.brain_runtime_bridge = self.brain_runtime_bridge

            # ── Phase 6.1: Local Agent Discovery Service ──
            # Wire LocalDiscoveryService so that /api/local-agents* endpoints
            # work and AGENT_DISCOVERED/REGISTERED/UPDATED/REMOVED events fire
            # on the bus. BrainDiscoveryBridge subscribes to those events and
            # converts them into BrainRecord registrations, so this is the
            # event-driven path that keeps BrainRegistry in sync with the
            # installed tools at runtime (not just at startup auto-detect).
            #
            # Same env var as Brains auto-detect: LocalDiscovery also spawns
            # subprocesses (tasklist, reg query, ps) on Windows via the
            # asyncio ProactorEventLoop, and has been observed to crash
            # the backend silently. Skip when the env var is set.
            if _skip_brain_autodetect:
                _diag(
                    "LocalDiscovery",
                    "SKIPPED",
                    "AGENTICOS_SKIP_BRAIN_AUTODETECT set",
                )
            else:
                _diag("LocalDiscovery", "STARTING")
                try:
                    self.local_discovery = LocalDiscoveryService()
                    await self.local_discovery.start(event_bus=self.bus)
                    if self._platform_instance is not None:
                        self._platform_instance.local_discovery = self.local_discovery
                    _diag(
                        "LocalDiscovery",
                        "STARTED",
                        f"{len(await self.local_discovery.get_agents())} agents found",
                    )
                except Exception as exc:
                    _diag("LocalDiscovery", "FAILED", str(exc))

            # ── Phase 11: Executive Intelligence Layer ──
            _diag("Executive", "STARTING")
            try:
                from agentic_os.core.executive import ExecutiveController

                self.executive_controller = ExecutiveController(
                    bus=self.bus,
                    brain_registry=self.brain_registry,
                    mission_planner=self.mission_planner,
                    memory=self.memory,
                    learning=self.learning,
                )
                await self.executive_controller.start()
                if self._platform_instance is not None:
                    self._platform_instance.executive_controller = self.executive_controller
                _diag("Executive", "STARTED")
            except Exception as exc:
                _diag("Executive", "FAILED", str(exc))

            # ── Phase 12: Cognitive Intelligence Layer ──
            _diag("Cognitive", "STARTING")
            try:
                from agentic_os.core.cognitive import CognitiveController

                self.cognitive_controller = CognitiveController(
                    bus=self.bus,
                    brain_registry=self.brain_registry,
                    goal_manager=(
                        self.executive_controller.goal_manager
                        if self.executive_controller is not None
                        else None
                    ),
                    exec_memory=(
                        self.executive_controller.memory
                        if self.executive_controller is not None
                        else None
                    ),
                )
                await self.cognitive_controller.start()
                if self._platform_instance is not None:
                    self._platform_instance.cognitive_controller = self.cognitive_controller
                _diag("Cognitive", "STARTED")
            except Exception as exc:
                _diag("Cognitive", "FAILED", str(exc))

            # ── Phase 14: Swarm Coordinator ──
            _diag("Swarm", "STARTING")
            try:
                from agentic_os.core.orchestration.swarm_coordinator import SwarmCoordinator

                self.swarm_coordinator = SwarmCoordinator(
                    bus=self.bus,
                    brain_registry=self.brain_registry,
                    orchestrator=self.orchestrator,
                )
                await self.swarm_coordinator.start()
                if self._platform_instance is not None:
                    self._platform_instance.swarm_coordinator = self.swarm_coordinator
                _diag("Swarm", "STARTED")
            except Exception as exc:
                _diag("Swarm", "FAILED", str(exc))

            # ── Phase 15: Autonomous Agent Ecosystem ──
            _diag("Ecosystem", "STARTING")
            try:
                from agentic_os.core.ecosystem import EcosystemController

                self.ecosystem_controller = EcosystemController(
                    bus=self.bus,
                    brain_registry=self.brain_registry,
                    exec_memory=(
                        self.executive_controller.memory
                        if self.executive_controller is not None
                        else None
                    ),
                    cognitive_memory=(
                        self.cognitive_controller.memory
                        if self.cognitive_controller is not None
                        else None
                    ),
                    swarm_coordinator=self.swarm_coordinator,
                )
                await self.ecosystem_controller.start()
                if self._platform_instance is not None:
                    self._platform_instance.ecosystem_controller = self.ecosystem_controller
                _diag("Ecosystem", "STARTED")
            except Exception as exc:
                _diag("Ecosystem", "FAILED", str(exc))

            # ── Phase 16: Distributed Runtime Federation ──
            _diag("Cluster", "STARTING")
            try:
                from agentic_os.core.cluster import ClusterController

                # Use configured HTTP host/port for the local node identity
                local_host = getattr(settings, "http_host", "localhost")
                local_port = int(getattr(settings, "http_port", 8000))
                self.cluster_controller = ClusterController(
                    bus=self.bus,
                    brain_registry=self.brain_registry,
                    local_host=local_host,
                    local_port=local_port,
                    local_base_url=f"http://{local_host}:{local_port}",
                    collaboration_network=(
                        self.ecosystem_controller.manager.collaboration_network
                        if self.ecosystem_controller is not None
                        else None
                    ),
                )
                await self.cluster_controller.start()
                if self._platform_instance is not None:
                    self._platform_instance.cluster_controller = self.cluster_controller
                _diag("Cluster", "STARTED")
            except Exception as exc:
                _diag("Cluster", "FAILED", str(exc))

            # ── Phase 17: Autonomous Agent Evolution ──
            _diag("Evolution", "STARTING")
            try:
                from agentic_os.core.evolution import EvolutionController

                self.evolution_controller = EvolutionController(
                    bus=self.bus,
                    evolution_engine=(
                        self.ecosystem_controller.manager.evolution_engine
                        if self.ecosystem_controller is not None
                        else None
                    ),
                    improvement_planner=(
                        self.cognitive_controller.improvement_planner
                        if self.cognitive_controller is not None
                        else None
                    ),
                    exec_memory=(
                        self.executive_controller.memory
                        if self.executive_controller is not None
                        else None
                    ),
                    cognitive_memory=(
                        self.cognitive_controller.memory
                        if self.cognitive_controller is not None
                        else None
                    ),
                )
                await self.evolution_controller.start()
                if self._platform_instance is not None:
                    self._platform_instance.evolution_controller = self.evolution_controller
                _diag("Evolution", "STARTED")
            except Exception as exc:
                _diag("Evolution", "FAILED", str(exc))

            # ── Phase 17: Distributed Execution Fabric ──
            _diag("Distributed", "STARTING")
            try:
                from agentic_os.core.distributed import DistributedController

                dist_host = getattr(settings, "http_host", "localhost")
                dist_port = int(getattr(settings, "http_port", 8000))
                self.distributed_controller = DistributedController(
                    bus=self.bus,
                    local_node_id=f"node-{dist_host}-{dist_port}",
                    local_base_url=f"http://{dist_host}:{dist_port}",
                    federation=(
                        self.cluster_controller.federation
                        if self.cluster_controller is not None
                        else None
                    ),
                )
                await self.distributed_controller.start()
                if self._platform_instance is not None:
                    self._platform_instance.distributed_controller = self.distributed_controller
                _diag("Distributed", "STARTED")
            except Exception as exc:
                _diag("Distributed", "FAILED", str(exc))

            # ── Phase 18: Persistent Runtime ──
            _diag("Persistent", "STARTING")
            try:
                from agentic_os.core.persistent import PersistentController

                persistent_data_dir = os.path.expanduser("~/.agentic_os/persistent")
                self.persistent_controller = PersistentController(
                    bus=self.bus,
                    data_dir=persistent_data_dir,
                )
                await self.persistent_controller.start()
                if self._platform_instance is not None:
                    self._platform_instance.persistent_controller = self.persistent_controller
                _diag("Persistent", "STARTED")
            except Exception as exc:
                _diag("Persistent", "FAILED", str(exc))

        except Exception as exc:
            _diag("Brains", "FAILED", str(exc))
        log.info("kernel.started", bus=settings.bus_type, plugins=len(self._plugins))

    async def stop(self) -> None:
        # Phase 18: Stop Persistent Controller (stops first — creates pre-shutdown snapshot)
        if self.persistent_controller is not None:
            try:
                await self.persistent_controller.stop()
            except Exception:
                log.exception("Failed to stop PersistentController")
            self.persistent_controller = None
        # Phase 17: Stop Distributed Controller (stops first — depends on others)
        if self.distributed_controller is not None:
            try:
                await self.distributed_controller.stop()
            except Exception:
                log.exception("Failed to stop DistributedController")
            self.distributed_controller = None
        # Phase 17: Stop Evolution Controller (stops first — depends on others)
        if self.evolution_controller is not None:
            try:
                await self.evolution_controller.stop()
            except Exception:
                log.exception("Failed to stop EvolutionController")
            self.evolution_controller = None
        # Phase 16: Stop Cluster Controller (stops first — depends on others)
        if self.cluster_controller is not None:
            try:
                await self.cluster_controller.stop()
            except Exception:
                log.exception("Failed to stop ClusterController")
            self.cluster_controller = None
        # Phase 15: Stop Ecosystem Controller (stops first — depends on others)
        if self.ecosystem_controller is not None:
            try:
                await self.ecosystem_controller.stop()
            except Exception:
                log.exception("Failed to stop EcosystemController")
            self.ecosystem_controller = None
        # Phase 14: Stop Swarm Coordinator
        if self.swarm_coordinator is not None:
            try:
                await self.swarm_coordinator.stop()
            except Exception:
                log.exception("Failed to stop SwarmCoordinator")
            self.swarm_coordinator = None
        # Phase 12: Stop Cognitive Intelligence Layer
        if self.cognitive_controller is not None:
            try:
                await self.cognitive_controller.stop()
            except Exception:
                log.exception("Failed to stop CognitiveController")
            self.cognitive_controller = None
        # Phase 11: Stop Executive Intelligence Layer
        if self.executive_controller is not None:
            try:
                await self.executive_controller.stop()
            except Exception:
                log.exception("Failed to stop ExecutiveController")
            self.executive_controller = None
        # Phase 6.1: Stop Local Discovery Service
        if self.local_discovery is not None:
            try:
                await self.local_discovery.stop()
            except Exception:
                log.exception("Failed to stop LocalDiscoveryService")
            self.local_discovery = None
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
        """Register the mock model only when a mock provider is registered.

        The mock provider is registered explicitly by tests and by
        ``ProviderFactory.create(kind=\"mock\")`` — never auto-registered in
        production. Real provider models are populated from their /models
        endpoint at runtime, and discovered local CLI brains surface their
        models via the BrainRegistry → /v1/models gateway path. The previous
        unconditional seed was removed because it injected a model for a
        provider that is not present in production.
        """
        from agentic_os.ports.provider_management import ModelInfo

        # Only seed when the provider actually exists (tests / explicit mock).
        if self.provider_mgr.get("mock") is None:
            return

        seeds = [
            ModelInfo(
                id="mock-fast", provider="mock", capabilities=["reasoning", "coding", "research"]
            ),
        ]
        for m in seeds:
            if self.provider_mgr.get_model(m.provider, m.id) is None:
                self.provider_mgr.register_model(m)

    def platform(self) -> Platform:
        if self._platform_instance is not None:
            return self._platform_instance
        self._platform_instance = Platform(
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
            local_discovery=self.local_discovery,
            brain_registry=self.brain_registry,
            brain_manager=self.brain_manager,
            brain_catalog=self.brain_catalog,
            brain_graph=self.brain_graph,
            brain_stats=self.brain_stats,
            brain_health=self.brain_health,
            brain_discovery_bridge=self.brain_discovery_bridge,
            brain_runtime_bridge=self.brain_runtime_bridge,
            executive_controller=self.executive_controller,
            cognitive_controller=self.cognitive_controller,
            swarm_coordinator=self.swarm_coordinator,
            execution_log=self.execution_log,
        )
        return self._platform_instance


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
        app = _build_app(kernel)
        _diag("API", "BUILT")
    except Exception as exc:
        import traceback as _tb

        _diag("API", "BUILD_FAILED", f"{type(exc).__name__}: {exc}")
        print(f"{_STARTUP_LOG_PREFIX} Traceback:\n{_tb.format_exc()}", flush=True)
        return

    # Start critical subsystems synchronously, then launch the API server
    # while the remaining subsystems initialize in the background.
    await kernel._start_critical()

    _diag("REST-API", "STARTING", f"http://{h}:{p}")
    import uvicorn

    config = uvicorn.Config(app, host=h, port=p, log_level="warning")
    server = uvicorn.Server(config)
    _diag("REST-API", "LISTENING", f"http://{h}:{p}")
    await server.serve()


def _build_app(kernel: Kernel):
    from agentic_os.api.app import create_app

    return create_app(kernel.platform())
