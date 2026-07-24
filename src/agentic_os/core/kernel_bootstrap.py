"""Kernel v2 Container Bootstrap — migrates the 6 core subsystems into the DI Container.

Phase 0 (CRITICAL): Logging, Settings, Configuration, Secrets
Phase 1 (INFRASTRUCTURE): EventBus, Scheduler

Each subsystem is wrapped in a ServiceProtocol implementation so the
LifecycleManager can manage its startup/shutdown/health lifecycle.
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path
from typing import Any

from agentic_os.adapters.bus.factory import build_bus
from agentic_os.adapters.security.encrypted_store import EncryptedSecretStore
from agentic_os.config import Settings
from agentic_os.config import settings as _settings_singleton
from agentic_os.core.compatibility import CompatibilityKernelProxy
from agentic_os.core.container import Container
from agentic_os.core.di_validator import ValidationPipeline
from agentic_os.core.health_registry import HealthRegistry
from agentic_os.core.lifecycle import (
    LifecycleManager,
    Phase,
    ServiceProtocol,
)
from agentic_os.core.observability_registry import ObservabilityRegistry
from agentic_os.core.scheduler import Scheduler as _Scheduler
from agentic_os.core.service_registry import BackgroundService, ServiceRegistry
from agentic_os.infrastructure.logging import configure_logging, get_logger
from agentic_os.ports.event_bus import EventBus

log = get_logger("kernel.bootstrap")
_STARTUP_LOG_PREFIX = "[AgenticOS-Startup]"


def _diag(stage: str, status: str, detail: str = "") -> None:
    msg = f"{_STARTUP_LOG_PREFIX} {stage}: {status}"
    if detail:
        msg += f" — {detail}"
    print(msg, file=sys.stderr, flush=True)


# ═══════════════════════════════════════════════════════════════════════
# Service Wrappers  (all 6 implement ServiceProtocol)
# ═══════════════════════════════════════════════════════════════════════


class LoggingService(ServiceProtocol):
    """Wraps configure_logging and get_logger as a Kernel service."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._configured = False

    async def initialize(self) -> None:
        configure_logging(self._settings.log_level)
        self._configured = True

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def dispose(self) -> None:
        pass

    async def health(self) -> dict[str, Any]:
        return {"status": "healthy", "configured": self._configured}

    async def heartbeat(self) -> bool:
        return self._configured

    async def metadata(self) -> dict[str, Any]:
        return {
            "type": "LoggingService",
            "level": self._settings.log_level,
            "configured": self._configured,
        }

    async def dependencies(self) -> list[str]:
        return []

    async def capabilities(self) -> list[dict[str, Any]]:
        return [{"name": "logging", "description": "Structured logging via structlog"}]


class SettingsService(ServiceProtocol):
    """Wraps the pydantic-settings Settings singleton as a Kernel service."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._started = False

    async def initialize(self) -> None:
        self._started = True

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def dispose(self) -> None:
        pass

    async def health(self) -> dict[str, Any]:
        return {"status": "healthy", "bus_type": self._settings.bus_type}

    async def heartbeat(self) -> bool:
        return self._started

    async def metadata(self) -> dict[str, Any]:
        return {
            "type": "SettingsService",
            "version": "1.0.0",
            "bus_type": self._settings.bus_type,
        }

    async def dependencies(self) -> list[str]:
        return []

    async def capabilities(self) -> list[dict[str, Any]]:
        return [{"name": "configuration", "description": "12-factor app configuration"}]

    async def configuration(self) -> dict[str, Any]:
        return self._settings.model_dump()

    @property
    def settings(self) -> Settings:
        return self._settings


class ConfigurationService(ServiceProtocol):
    """Hot-reloadable configuration manager wrapping Settings."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._reload_count = 0
        self._last_reload: float | None = None

    async def initialize(self) -> None:
        pass

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def dispose(self) -> None:
        pass

    async def health(self) -> dict[str, Any]:
        return {"status": "healthy", "reload_count": self._reload_count}

    async def heartbeat(self) -> bool:
        return True

    async def reload(self) -> None:
        """Reload settings from .env."""
        self._settings.model_config["env_file"] = ".env"
        self._reload_count += 1
        self._last_reload = time.time()

    async def metadata(self) -> dict[str, Any]:
        return {"type": "ConfigurationService", "reload_count": self._reload_count}

    async def dependencies(self) -> list[str]:
        return ["settings"]

    async def capabilities(self) -> list[dict[str, Any]]:
        return [{"name": "configuration", "description": "Configuration reload and management"}]

    async def configuration(self) -> dict[str, Any]:
        return self._settings.model_dump()


class SecretsService(ServiceProtocol):
    """Wraps EncryptedSecretStore as a Kernel service."""

    def __init__(
        self,
        path: Path | None = None,
        existing_store: EncryptedSecretStore | None = None,
    ) -> None:
        self._store: EncryptedSecretStore | None = existing_store
        self._path = path
        self._initialized = existing_store is not None

    async def initialize(self) -> None:
        if self._store is None:
            self._store = EncryptedSecretStore(path=self._path)
            self._initialized = True

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def dispose(self) -> None:
        self._store = None
        self._initialized = False

    async def health(self) -> dict[str, Any]:
        return {
            "status": "healthy" if self._initialized else "failed",
            "initialized": self._initialized,
        }

    async def heartbeat(self) -> bool:
        return self._initialized

    async def metadata(self) -> dict[str, Any]:
        return {
            "type": "SecretsService",
            "class": "EncryptedSecretStore",
            "initialized": self._initialized,
        }

    async def dependencies(self) -> list[str]:
        return []

    async def capabilities(self) -> list[dict[str, Any]]:
        return [{"name": "secrets", "description": "Fernet-encrypted at-rest secret storage"}]

    @property
    def store(self) -> EncryptedSecretStore:
        assert self._store is not None  # nosec
        return self._store


class EventBusService(ServiceProtocol):
    """Wraps the EventBus protocol as a Kernel service.

    Accepts an optional existing_bus — when migrating alongside the old
    Kernel, pass the old Kernel's EventBus instance to avoid split-brain.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        existing_bus: EventBus | None = None,
    ) -> None:
        self._settings = settings
        self._bus: EventBus | None = existing_bus
        self._started = existing_bus is not None
        # Eagerly build the bus if settings are provided (needed for
        # container registration before initialize() is called).
        if self._bus is None and self._settings is not None:
            self._bus = build_bus(self._settings)

    async def initialize(self) -> None:
        """Build the EventBus if one wasn't provided."""
        if self._bus is None and self._settings is not None:
            self._bus = build_bus(self._settings)

    async def start(self) -> None:
        """Start the EventBus."""
        if self._bus and not self._started:
            await self._bus.start()
            self._started = True

    async def stop(self) -> None:
        """Stop the EventBus."""
        if self._bus:
            await self._bus.stop()
            self._started = False

    async def dispose(self) -> None:
        await self.stop()
        self._bus = None

    async def health(self) -> dict[str, Any]:
        if not self._bus:
            return {"status": "failed", "error": "EventBus not built"}
        return {
            "status": "started" if self._started else "stopped",
            "bus_type": type(self._bus).__name__,
            "started": self._started,
        }

    async def heartbeat(self) -> bool:
        return self._started

    async def metadata(self) -> dict[str, Any]:
        return {
            "type": "EventBusService",
            "bus_type": type(self._bus).__name__ if self._bus else "None",
            "transport": self._settings.bus_type if self._settings else "unknown",
        }

    async def dependencies(self) -> list[str]:
        return ["settings"]

    async def capabilities(self) -> list[dict[str, Any]]:
        return [
            {"name": "event_bus", "description": "Inter-service communication (pub/sub)"},
            {"name": "publish", "description": "Publish events to topics"},
            {"name": "subscribe", "description": "Subscribe to event topics"},
        ]

    async def metrics(self) -> dict[str, Any]:
        return {
            "bus_type": self._settings.bus_type if self._settings else "unknown",
            "started": self._started,
        }

    @property
    def bus(self) -> EventBus:
        assert self._bus is not None  # nosec
        return self._bus


class SchedulerService(BackgroundService):
    """Wraps the Scheduler as a Kernel BackgroundService.

    Accepts an optional existing_scheduler — when migrating alongside the
    old Kernel, pass the old Kernel's Scheduler instance.
    """

    def __init__(self, existing_scheduler: _Scheduler | None = None) -> None:
        super().__init__()
        self._scheduler = existing_scheduler or _Scheduler()

    async def initialize(self) -> None:
        pass

    async def start(self) -> None:
        await self._scheduler.start()
        self._running = True

    async def stop(self) -> None:
        await self._scheduler.stop()
        self._running = False

    async def dispose(self) -> None:
        await self.stop()

    async def health(self) -> dict[str, Any]:
        return {"status": "healthy" if self._running else "stopped"}

    async def heartbeat(self) -> bool:
        return self._running

    async def metadata(self) -> dict[str, Any]:
        return {"type": "SchedulerService", "class": "Scheduler"}

    async def dependencies(self) -> list[str]:
        return []

    async def capabilities(self) -> list[dict[str, Any]]:
        return [{"name": "scheduling", "description": "Periodic task execution"}]

    async def run(self) -> None:
        while self._running:
            await asyncio.sleep(1)

    @property
    def scheduler(self) -> _Scheduler:
        return self._scheduler


# ═══════════════════════════════════════════════════════════════════════
# Container Bootstrap
# ═══════════════════════════════════════════════════════════════════════


def build_container_kernel(
    old_kernel: Any = None,
) -> tuple[
    Container,
    LifecycleManager,
    CompatibilityKernelProxy,
    HealthRegistry,
    ObservabilityRegistry,
    ServiceRegistry,
]:
    """Build a fully-wired Kernel v2 Container for the 6 core subsystems.

    When *old_kernel* is provided (a ``Kernel()`` instance), its existing
    EventBus, Scheduler, and SecretStore are registered in the Container
    instead of creating new ones.  This avoids split-brain situations
    where non-migrated subsystems use one bus instance and Container-managed
    code uses another.
    """
    container = Container()
    lifecycle = LifecycleManager(container)
    health_registry = HealthRegistry(lifecycle)
    observability = ObservabilityRegistry(lifecycle, container, health_registry)
    service_registry = ServiceRegistry(lifecycle, container)
    compatibility = CompatibilityKernelProxy(
        container=container,
        lifecycle=lifecycle,
        old_kernel=old_kernel,
    )

    # ── Register Settings (no deps, Phase 0 ── CRITICAL) ──────────────
    settings_service = SettingsService(_settings_singleton)
    container.register_instance(Settings, _settings_singleton, name="settings_default")
    container.register_instance(
        Settings,
        _settings_singleton,
        description="Default unnamed settings resolve",
    )
    container.register_instance(
        SettingsService,
        settings_service,
        description="12-factor application settings",
    )
    lifecycle.register_service(
        "settings",
        SettingsService,
        settings_service,
        phase=Phase.CRITICAL,
        container_key="SettingsService",
    )
    service_registry.register(
        "settings",
        settings_service,
        interface=SettingsService,
        version="1.0.0",
        description="Settings Manager — pydantic-settings 12-factor config",
        phase="critical",
    )
    health_registry.track_service("settings")
    compatibility.register_legacy_bridge("settings", SettingsService, "settings")

    # ── Register Logging (depends on Settings, Phase 0 ── CRITICAL) ───
    logging_service = LoggingService(_settings_singleton)
    container.register_instance(LoggingService, logging_service)
    lifecycle.register_service("logging", LoggingService, logging_service, phase=Phase.CRITICAL)
    service_registry.register(
        "logging",
        logging_service,
        description="Structured logging via structlog",
        phase="critical",
        dependencies=["settings"],
    )
    health_registry.track_service("logging")
    compatibility.register_legacy_bridge("logger", LoggingService, "logging")

    # ── Register Configuration (depends on Settings, Phase 0 ── CRITICAL) ──
    config_service = ConfigurationService(_settings_singleton)
    container.register_instance(ConfigurationService, config_service)
    lifecycle.register_service(
        "configuration",
        ConfigurationService,
        config_service,
        phase=Phase.CRITICAL,
    )
    service_registry.register(
        "configuration",
        config_service,
        description="Hot-reloadable configuration manager",
        phase="critical",
        dependencies=["settings"],
    )
    health_registry.track_service("configuration")
    compatibility.register_legacy_bridge("configuration", ConfigurationService, "configuration")

    # ── Determine whether we have a pre-built old Kernel to share ─────
    if old_kernel is not None:
        # Use old Kernel's existing instances to avoid split-brain
        _diag(
            "Container",
            "SHARING_OLD_KERNEL_INSTANCES",
            "bus, scheduler, secret_store will be shared",
        )
        existing_bus = getattr(old_kernel, "bus", None)
        existing_scheduler = getattr(old_kernel, "scheduler", None)
        existing_secret_store = getattr(old_kernel, "secret_store", None)
    else:
        existing_bus = None
        existing_scheduler = None
        existing_secret_store = None

    # ── Register Secrets (no deps, Phase 0 ── CRITICAL) ──────────────
    secrets_service = SecretsService(existing_store=existing_secret_store)
    container.register_instance(SecretsService, secrets_service)
    if existing_secret_store is not None:
        container.register_instance(
            EncryptedSecretStore,
            existing_secret_store,
            description="Legacy secret store (shared)",
        )
    lifecycle.register_service("secrets", SecretsService, secrets_service, phase=Phase.CRITICAL)
    service_registry.register(
        "secrets",
        secrets_service,
        description="Fernet-encrypted at-rest secret store",
        phase="critical",
    )
    health_registry.track_service("secrets")
    compatibility.register_legacy_bridge("secret_store", SecretsService, "secrets")

    # ── Register EventBus (depends on Settings, Phase 1 ── INFRASTRUCTURE) ──
    eventbus_service = EventBusService(settings=_settings_singleton, existing_bus=existing_bus)
    if existing_bus is not None:
        # Register the shared bus instance so everyone resolves the same object
        container.register_instance(
            EventBus,
            existing_bus,
            description="EventBus protocol instance (shared with legacy)",
        )
    else:
        container.register_instance(
            EventBus,
            eventbus_service.bus,  # type: ignore[type-abstract]
            description="EventBus protocol instance",
        )
    lifecycle.register_service(
        "event_bus",
        EventBusService,
        eventbus_service,
        phase=Phase.INFRASTRUCTURE,
    )
    service_registry.register(
        "event_bus",
        eventbus_service,
        interface=EventBus,
        description="Inter-service communication via pub/sub EventBus",
        phase="infrastructure",
        dependencies=["settings"],
    )
    health_registry.track_service("event_bus")
    compatibility.register_legacy_bridge("bus", EventBus, "event_bus")

    # ── Register Scheduler (no deps, Phase 1 ── INFRASTRUCTURE) ───────
    scheduler_service = SchedulerService(existing_scheduler=existing_scheduler)
    container.register_instance(
        _Scheduler,
        scheduler_service.scheduler,
        description="Scheduler singleton",
    )
    lifecycle.register_service(
        "scheduler",
        SchedulerService,
        scheduler_service,
        phase=Phase.INFRASTRUCTURE,
    )
    service_registry.register(
        "scheduler",
        scheduler_service,
        interface=_Scheduler,
        description="Periodic task scheduler",
        phase="infrastructure",
    )
    health_registry.track_service("scheduler")
    compatibility.register_legacy_bridge("scheduler", _Scheduler, "scheduler")

    # Default event publisher — logs until EventBus is connected
    lifecycle.publish_event = lifecycle._default_publish

    return container, lifecycle, compatibility, health_registry, observability, service_registry


async def run_container_startup(
    lifecycle: LifecycleManager,
    health_registry: HealthRegistry,
    observability: ObservabilityRegistry,
    validation_pipeline: ValidationPipeline | None = None,
    container: Container | None = None,
) -> bool:
    """Run the full Container-backed startup sequence with validation, phase gating,
    health checks, and observability capture.

    Returns True if startup succeeded, False if it failed validation or startup.
    """
    observability.mark_started()

    # Step 1: Dependency Validation
    if validation_pipeline and container:
        log.info("Running dependency validation…")
        report = await validation_pipeline.validate(container, lifecycle)
        if not report.success:
            log.error("Dependency validation FAILED — refusing startup")
            for check in report.failed:
                log.error("  FAIL: [%s] %s", check.name, check.details)
            return False
        for warning in report.warnings:
            log.warning("  WARN: [%s] %s", warning.name, warning.details)
        log.info("Dependency validation passed (%d checks)", report.total_checks)

    # Step 2: Phase 0 — CRITICAL (Logging, Settings, Configuration, Secrets)
    log.info("Starting Phase 0 (CRITICAL)…")
    phase0_result = await lifecycle.start_phase(Phase.CRITICAL)
    observability.record_phase_timing(phase0_result)
    if not phase0_result.success:
        log.error("Phase 0 (CRITICAL) FAILED — refusing startup")
        for err in phase0_result.errors:
            log.error("  %s", err)
        return False

    phase0_healthy = await health_registry.wait_for_phase_healthy(Phase.CRITICAL, timeout=10.0)
    if not phase0_healthy:
        log.error("Phase 0 services did not become healthy")
        return False
    log.info("Phase 0 healthy — %d services started", len(phase0_result.started_services))
    await health_registry.start_periodic_checks()

    # Step 3: Phase 1 — INFRASTRUCTURE (EventBus, Scheduler)
    log.info("Starting Phase 1 (INFRASTRUCTURE)…")
    phase1_result = await lifecycle.start_phase(Phase.INFRASTRUCTURE)
    observability.record_phase_timing(phase1_result)
    if not phase1_result.success:
        log.error("Phase 1 (INFRASTRUCTURE) FAILED")
        for err in phase1_result.errors:
            log.error("  %s", err)
        return False

    phase1_healthy = await health_registry.wait_for_phase_healthy(
        Phase.INFRASTRUCTURE,
        timeout=10.0,
    )
    if not phase1_healthy:
        log.error("Phase 1 services did not become healthy")
        return False
    log.info("Phase 1 healthy — %d services started", len(phase1_result.started_services))

    # Wire EventBus publishing into LifecycleManager so state transitions
    # are broadcast to all EventBus subscribers.
    eventbus_record = lifecycle.get_service("event_bus")
    if eventbus_record and eventbus_record.instance:
        eventbus_svc: EventBusService = eventbus_record.instance  # type: ignore[assignment]
        bus = eventbus_svc.bus if hasattr(eventbus_svc, "bus") else None
        if bus is not None and hasattr(bus, "publish"):

            async def _publish(topic: str, payload: dict[str, Any]) -> None:
                try:
                    from agentic_os.domain.events import EventEnvelope

                    await bus.publish(
                        EventEnvelope(
                            type=topic,
                            source="lifecycle",
                            topic=topic,
                            payload=payload,
                        )
                    )
                except Exception:
                    pass  # nosec

            def _fire_and_forget(topic: str, payload: dict[str, Any]) -> None:
                asyncio.create_task(_publish(topic, payload))

            lifecycle.publish_event = _fire_and_forget

    await observability.snapshot()
    log.info("Container startup complete (%.1fms)", observability.total_startup_duration_ms())
    return True


async def run_container_shutdown(
    lifecycle: LifecycleManager,
    health_registry: HealthRegistry,
    timeout: float = 15.0,
) -> bool:
    """Reverse-phase Container shutdown with health registry stop."""
    _diag("Container", "SHUTTING_DOWN")
    await health_registry.stop_periodic_checks()
    results = await lifecycle.stop(timeout=timeout)
    all_success = all(r.success for r in results)
    if all_success:
        _diag("Container", "STOPPED")
    else:
        for r in results:
            if not r.success:
                for err in r.errors:
                    _diag("Container", f"STOP_ERROR_{r.phase.value}", err)
    return all_success


# ═══════════════════════════════════════════════════════════════════════
# ContainerKernel — wraps legacy Kernel with Container-backed 6 services
# ═══════════════════════════════════════════════════════════════════════


class ContainerKernel:
    """Container-backed Kernel v2.

    Wraps the legacy ``Kernel`` for non-migrated subsystems while the 6 core
    services (Settings, Logging, Configuration, Secrets, EventBus, Scheduler)
    are managed by the DI Container / LifecycleManager.

    Usage (from ``run_serve``)::

        kernel = ContainerKernel()
        # …build app from kernel.platform()…
        await kernel._start_critical()
        await server.serve()
    """

    def __init__(self) -> None:
        from agentic_os.kernel import Kernel as LegacyKernel

        _diag("Configuration", "LOADED", f"bus={_settings_singleton.bus_type}")
        configure_logging(_settings_singleton.log_level)

        # ── Build legacy Kernel (constructs ALL subsystems) ──
        self._old_kernel = LegacyKernel()
        _diag("LegacyKernel", "CONSTRUCTED")

        # ── Build Container with shared instances ──
        (
            self._container,
            self._lifecycle,
            self._compatibility,
            self._health_registry,
            self._observability,
            self._service_registry,
        ) = build_container_kernel(old_kernel=self._old_kernel)

        # ── Expose 6 migrated services at top level for direct access ──
        self.bus: Any = self._container.resolve(EventBus)  # type: ignore[type-abstract]
        self.scheduler: Any = (
            self._container.resolve(_Scheduler)
            if self._container.is_registered(_Scheduler)
            else self._old_kernel.scheduler
        )
        self.secret_store: Any = getattr(
            self._container.resolve(SecretsService), "store", self._old_kernel.secret_store
        )
        self.settings = _settings_singleton
        self.configuration: Any = self._container.resolve(ConfigurationService)
        self.logger = get_logger("kernel")

        _diag("Kernel", "CONTAINER_MODE", "6 services container-backed")

    # ── Forward everything else to the old Kernel ──

    def __getattr__(self, name: str) -> Any:
        return getattr(self._old_kernel, name)

    # ── Platform generation (used by _build_app) ──

    def platform(self) -> Any:
        return self._compatibility.generate_platform(overrides={})

    # ── Startup ──

    async def _start_critical(self) -> None:
        """Container-ordered startup.

        Phase 0 (CRITICAL)  → Logging, Settings, Configuration, Secrets
        Phase 1 (INFRA)     → EventBus, Scheduler
        Then background-init the legacy subsystems.
        """
        from agentic_os.kernel import _ensure_env  # noqa: PLC0415

        _ensure_env()

        # Run Container startup (validates deps, starts Phase 0+1)
        success = await run_container_startup(
            self._lifecycle,
            self._health_registry,
            self._observability,
            validation_pipeline=ValidationPipeline(),
            container=self._container,
        )
        if not success:
            _diag("Container", "STARTUP_FAILED", "Falling back to legacy startup")
            await self._old_kernel._start_critical()
            return

        _diag("EventBus", "CONTAINER_STARTED")
        _diag("Lifecycle", "PHASE0_CRITICAL_READY")
        _diag("Lifecycle", "PHASE1_INFRASTRUCTURE_READY")

        # Background subsystems from legacy Kernel
        async def _bg_start() -> None:
            try:
                await self._old_kernel._start_subsystems()
            except Exception as exc:
                _diag("BackgroundInit", "FATAL", str(exc))

        asyncio.create_task(_bg_start())
        _diag("Kernel", "CRITICAL_READY", "API server will start immediately")

    # ── Shutdown ──

    async def stop(self) -> None:
        """Reverse-order shutdown: legacy subsystems first, then Container."""
        _diag("Kernel", "STOPPING")
        await self._old_kernel.stop()
        await run_container_shutdown(self._lifecycle, self._health_registry)
        _diag("Kernel", "STOPPED")
