from __future__ import annotations

import asyncio
import subprocess
import time
from typing import Any

from core.event_bus.bus import EventBus
from core.logging import get_logger
from services.execution_engine.discovery import EngineDiscovery
from services.execution_engine.manager import ExecutionEngineManager
from services.runtime_discovery.binding import RuntimeBindingManager
from services.runtime_discovery.cache import RuntimeCache
from services.runtime_discovery.configuration import RuntimeConfigurationManager
from services.runtime_discovery.events import (
    RuntimeEventPublisher,
    publish_binding_completed,
    publish_binding_started,
    publish_discovery_engine_found,
    publish_discovery_scan_completed,
    publish_discovery_scan_started,
    publish_health_check_passed,
    publish_profile_created,
    publish_registry_registered,
    publish_validation_passed,
)
from services.runtime_discovery.health_monitor import RuntimeHealthMonitor
from services.runtime_discovery.models import (
    DiscoveryProviderType,
    Runtime,
    RuntimeCapability,
    RuntimeConfiguration,
    RuntimeDiscoveryResult,
    RuntimeMetadata,
    RuntimeStatus,
    RuntimeTelemetry,
    RuntimeType,
    ValidationStatus,
)
from services.runtime_discovery.profiling import ProfilingEngine
from services.runtime_discovery.registry import RuntimeRegistry
from services.runtime_discovery.scheduler import RuntimeDiscoveryScheduler
from services.runtime_discovery.telemetry import RuntimeTelemetryCollector
from services.runtime_discovery.validation import (
    CapabilityMatchValidator,
    ExecutableExistsValidator,
    HealthProbeValidator,
    PermissionValidator,
    ValidationPipeline,
    VersionDetectValidator,
)

_log = get_logger(__name__)

__all__ = ["RuntimeDiscoveryManager"]

# Mapping from EngineDiscovery source values to DiscoveryProviderType
_SOURCE_TO_PROVIDER_TYPE: dict[str, DiscoveryProviderType] = {
    "path": DiscoveryProviderType.PATH,
    "wsl": DiscoveryProviderType.WSL,
    "docker": DiscoveryProviderType.DOCKER,
    "registry": DiscoveryProviderType.REGISTRY,
    "config": DiscoveryProviderType.CONFIG_FILE,
    "env": DiscoveryProviderType.ENV_VAR,
    "install_dir": DiscoveryProviderType.KNOWN_INSTALL_DIRS,
}

# Map discovered binary names to RuntimeType
_BINARY_TO_RUNTIME: dict[str, RuntimeType] = {
    "claude": RuntimeType.CLAUDE_CODE,
    "gemini": RuntimeType.GEMINI_CLI,
    "gemini-cli": RuntimeType.GEMINI_CLI,
    "codex": RuntimeType.CODEX_CLI,
    "openai-codex": RuntimeType.CODEX_CLI,
    "hermes": RuntimeType.HERMES,
    "hermes-daemon": RuntimeType.HERMES,
    "openhands": RuntimeType.OPENHANDS,
    "openhands-cli": RuntimeType.OPENHANDS,
    "aider": RuntimeType.AIDER,
    "continue": RuntimeType.CONTINUE,
    "continue-cli": RuntimeType.CONTINUE,
    "cline": RuntimeType.CLINE,
    "roo": RuntimeType.ROO_CODE,
    "roo-cli": RuntimeType.ROO_CODE,
    "roo-code": RuntimeType.ROO_CODE,
    "ollama": RuntimeType.OLLAMA,
    "python": RuntimeType.PYTHON,
    "python3": RuntimeType.PYTHON,
    "node": RuntimeType.NODEJS,
    "nodejs": RuntimeType.NODEJS,
    "docker": RuntimeType.DOCKER,
    "git": RuntimeType.GIT,
    "gh": RuntimeType.GH_CLI,
}

_RUNTIME_DISPLAY_NAMES: dict[RuntimeType, str] = {
    RuntimeType.CLAUDE_CODE: "Claude Code",
    RuntimeType.GEMINI_CLI: "Gemini CLI",
    RuntimeType.CODEX_CLI: "OpenAI Codex CLI",
    RuntimeType.HERMES: "Hermes Desktop Agent",
    RuntimeType.OPENHANDS: "OpenHands",
    RuntimeType.AIDER: "Aider",
    RuntimeType.CONTINUE: "Continue",
    RuntimeType.CLINE: "Cline",
    RuntimeType.ROO_CODE: "Roo Code",
    RuntimeType.OLLAMA: "Ollama",
    RuntimeType.PYTHON: "Python",
    RuntimeType.NODEJS: "Node.js",
    RuntimeType.DOCKER: "Docker",
    RuntimeType.GIT: "Git",
    RuntimeType.GH_CLI: "GitHub CLI",
}

_RUNTIME_VENDORS: dict[RuntimeType, str] = {
    RuntimeType.CLAUDE_CODE: "Anthropic",
    RuntimeType.GEMINI_CLI: "Google",
    RuntimeType.CODEX_CLI: "OpenAI",
    RuntimeType.HERMES: "AAiOS",
    RuntimeType.OPENHANDS: "All Hands AI",
    RuntimeType.AIDER: "Aider AI",
    RuntimeType.CONTINUE: "Continue Dev",
    RuntimeType.CLINE: "Cline Bot",
    RuntimeType.ROO_CODE: "Roo",
    RuntimeType.OLLAMA: "Ollama",
    RuntimeType.PYTHON: "Python Software Foundation",
    RuntimeType.NODEJS: "OpenJS Foundation",
    RuntimeType.DOCKER: "Docker Inc.",
    RuntimeType.GIT: "Git SCM",
    RuntimeType.GH_CLI: "GitHub",
}


class RuntimeDiscoveryManager:
    def __init__(
        self,
        bus: EventBus | None = None,
        engine_manager: ExecutionEngineManager | None = None,
    ) -> None:
        self._bus = bus
        self._engine_manager = engine_manager or ExecutionEngineManager(bus=bus)
        self._discovery = EngineDiscovery()
        self._registry = RuntimeRegistry()
        self._binding_manager = RuntimeBindingManager(self._engine_manager)
        self._validation = ValidationPipeline()
        self._profiling = ProfilingEngine()
        self._health_monitor = RuntimeHealthMonitor()
        self._config_manager = RuntimeConfigurationManager()
        self._cache = RuntimeCache()
        self._scheduler = RuntimeDiscoveryScheduler()
        self._telemetry_collector = RuntimeTelemetryCollector()
        self._event_publisher = RuntimeEventPublisher(bus) if bus else None
        self._initialized = False

        self._setup_default_validators()

    def _setup_default_validators(self) -> None:
        self._validation.add_validator("executable_exists", ExecutableExistsValidator.validate)
        self._validation.add_validator("version_detect", VersionDetectValidator.validate)
        self._validation.add_validator("capability_match", CapabilityMatchValidator.validate)
        self._validation.add_validator("permissions", PermissionValidator.validate)
        self._validation.add_validator("health_probe", HealthProbeValidator.validate)

    async def initialize(self) -> None:
        if self._initialized:
            return
        await self._engine_manager.initialize()
        discovered = await self.discover_all()
        for result in discovered:
            await self.discover_and_bind(result)
        self._initialized = True
        _log.info(
            "RuntimeDiscoveryManager initialized with %d runtimes", await self._registry.count()
        )

    async def shutdown(self) -> None:
        await self._scheduler.stop_all()
        await self._health_monitor.stop_all()
        bound_runtimes = await self._registry.list(status=RuntimeStatus.BOUND.value)
        bound_runtimes += await self._registry.list(status=RuntimeStatus.ACTIVE.value)
        for runtime in bound_runtimes:
            await self._binding_manager.unbind(runtime.runtime_id)
        await self._engine_manager.shutdown()
        self._initialized = False
        _log.info("RuntimeDiscoveryManager shutdown")

    async def discover_all(self) -> list[RuntimeDiscoveryResult]:
        if self._bus:
            await publish_discovery_scan_started(self._bus, "default", 10)

        start = time.monotonic()
        results = await self._discovery.discover_all()
        discovered_runtimes: list[RuntimeDiscoveryResult] = []

        for result in results:
            runtime_type = _BINARY_TO_RUNTIME.get(result.name, RuntimeType.CUSTOM)
            provider_type = _SOURCE_TO_PROVIDER_TYPE.get(
                result.source, DiscoveryProviderType.CUSTOM
            ) if result.source else DiscoveryProviderType.PATH
            runtime_result = RuntimeDiscoveryResult(
                runtime_type=runtime_type,
                name=result.name,
                display_name=_RUNTIME_DISPLAY_NAMES.get(runtime_type, result.name),
                version=result.version,
                binary_path=result.binary_path,
                executable=result.binary_path,
                source=provider_type,
                confidence=0.8 if result.found else 0.0,
                found=result.found,
                error=result.error,
            )
            discovered_runtimes.append(runtime_result)

            if result.found and self._bus:
                await publish_discovery_engine_found(
                    self._bus,
                    runtime_type.value,
                    result.name,
                    result.version,
                    result.source,
                )

        # Add built-in runtimes that discovery may not find
        for rt in (RuntimeType.PYTHON, RuntimeType.NODEJS, RuntimeType.GIT, RuntimeType.DOCKER):
            if not any(r.runtime_type == rt for r in discovered_runtimes):
                rr = await self._discover_builtin(rt)
                if rr:
                    discovered_runtimes.append(rr)

        duration_ms = (time.monotonic() - start) * 1000
        if self._bus:
            await publish_discovery_scan_completed(
                self._bus, "default", len(discovered_runtimes), duration_ms
            )

        return discovered_runtimes

    async def _discover_builtin(self, runtime_type: RuntimeType) -> RuntimeDiscoveryResult | None:
        binary_name = runtime_type.value
        try:
            result = subprocess.run(
                ["where", binary_name] if binary_name == "python" else [binary_name, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                binary_path = None
                try:
                    import shutil

                    binary_path = shutil.which(binary_name)
                except Exception:
                    pass
                version = (
                    (result.stdout or result.stderr).strip().split("\n")[0]
                    if result.returncode == 0
                    else None
                )
                return RuntimeDiscoveryResult(
                    runtime_type=runtime_type,
                    name=binary_name,
                    display_name=_RUNTIME_DISPLAY_NAMES.get(runtime_type, binary_name),
                    version=version,
                    binary_path=binary_path,
                    executable=binary_path,
                    source=DiscoveryProviderType.PATH,
                    confidence=0.7,
                    found=True,
                )
        except Exception:
            pass
        return None

    async def discover_and_bind(self, result: RuntimeDiscoveryResult) -> Runtime | None:
        if not result.found:
            return None

        runtime = await self._create_runtime(result)

        cached = self._cache.get(self._cache.make_key(result.source.value, result.name))
        if cached:
            runtime.status = RuntimeStatus.DISCOVERED

        self._cache.set(
            self._cache.create_entry(
                result.source.value,
                result.name,
                result.runtime_type,
                {
                    "version": result.version,
                    "binary_path": result.binary_path,
                },
            )
        )

        runtime = await self._registry.register(runtime)
        if self._bus:
            await publish_registry_registered(
                self._bus, runtime.runtime_id, runtime.name, runtime.runtime_type.value
            )

        validation_result = await self._validation.validate(runtime)
        if validation_result.status == ValidationStatus.FAILED:
            runtime.status = RuntimeStatus.DISABLED
            runtime = await self._registry.update(runtime)
            _log.warning("Validation failed for %s: %s", runtime.name, validation_result.errors)
            return runtime

        runtime.status = RuntimeStatus.VALIDATED
        if self._bus:
            await publish_validation_passed(self._bus, runtime.runtime_id, runtime.name)

        profile = await self._profiling.profile(runtime)
        runtime.profile = profile
        if self._bus:
            await publish_profile_created(self._bus, runtime.runtime_id, profile.version)

        config = RuntimeConfiguration(
            runtime_id=runtime.runtime_id,
            enabled=True,
            auto_start=True,
        )
        await self._config_manager.set_config(runtime.runtime_id, config)
        runtime.configuration = config

        await self._binding_manager.bind(runtime)
        if self._bus:
            await publish_binding_started(self._bus, runtime.runtime_id, runtime.name)

        if runtime.binding and runtime.binding.status.value == "bound":
            runtime.status = RuntimeStatus.ACTIVE

        telemetry = RuntimeTelemetry(
            runtime_id=runtime.runtime_id,
            runtime_type=runtime.runtime_type,
            name=runtime.name,
        )
        await self._telemetry_collector.record(runtime.runtime_id, telemetry)
        runtime.telemetry = telemetry

        await self._health_monitor.check(runtime)
        if runtime.health and runtime.health.healthy and self._bus:
            await publish_health_check_passed(
                self._bus, runtime.runtime_id, runtime.name, runtime.health.response_time_ms
            )

        await self._registry.update(runtime)
        _log.info(
            "Runtime discovered and bound: %s (%s) [%s]",
            runtime.name,
            runtime.runtime_type.value,
            runtime.status.value,
        )

        if self._bus:
            await publish_binding_completed(self._bus, runtime.runtime_id, runtime.name)

        return runtime

    async def _create_runtime(self, result: RuntimeDiscoveryResult) -> Runtime:
        runtime_type = result.runtime_type
        return Runtime(
            runtime_type=runtime_type,
            name=result.name,
            display_name=result.display_name
            or _RUNTIME_DISPLAY_NAMES.get(runtime_type, result.name),
            version=result.version,
            binary_path=result.binary_path,
            status=RuntimeStatus.DISCOVERED,
            capabilities=[
                RuntimeCapability(namespace=c) for c in self._get_default_capabilities(runtime_type)
            ],
            metadata=RuntimeMetadata(
                vendor=_RUNTIME_VENDORS.get(runtime_type, ""),
                tags=[runtime_type.value],
            ),
            confidence=result.confidence,
            source=result.source,
        )

    @staticmethod
    def _get_default_capabilities(runtime_type: RuntimeType) -> list[str]:
        caps = {
            RuntimeType.CLAUDE_CODE: [
                "code.read",
                "code.write",
                "code.refactor",
                "code.review",
                "test.run",
                "shell.execute",
            ],
            RuntimeType.GEMINI_CLI: [
                "code.read",
                "code.write",
                "code.review",
                "test.run",
                "shell.execute",
            ],
            RuntimeType.CODEX_CLI: [
                "code.read",
                "code.write",
                "code.refactor",
                "code.review",
                "test.run",
                "shell.execute",
            ],
            RuntimeType.HERMES: [
                "desktop.ui.click",
                "desktop.screen.screenshot",
                "desktop.app.open",
                "browser.navigate",
            ],
            RuntimeType.PYTHON: ["script.execute", "package.install"],
            RuntimeType.NODEJS: ["script.execute", "package.install"],
            RuntimeType.GIT: ["git.clone", "git.commit", "git.push", "git.pull"],
            RuntimeType.DOCKER: ["container.run", "container.build", "image.pull"],
            RuntimeType.GH_CLI: ["pr.create", "pr.review", "issue.list"],
            RuntimeType.OLLAMA: ["model.run", "model.pull"],
        }
        return caps.get(runtime_type, [])

    async def rescan(self) -> list[Runtime]:
        self._cache.invalidate_all()
        results = await self.discover_all()
        runtimes = []
        for result in results:
            runtime = await self.discover_and_bind(result)
            if runtime:
                runtimes.append(runtime)
        return runtimes

    # --- Delegates ---

    async def start_auto_discovery(self, interval_s: int = 300) -> None:
        await self._scheduler.start_all()
        await self._scheduler.schedule("auto_discovery", interval_s, self.rescan)

    async def stop_auto_discovery(self) -> None:
        await self._scheduler.stop_all()

    async def start_health_monitoring(self) -> None:
        runtimes = await self._registry.list()
        await self._health_monitor.start_all(runtimes)

    async def stop_health_monitoring(self) -> None:
        await self._health_monitor.stop_all()

    def get_runtime(self, runtime_id: str) -> Runtime | None:

        return asyncio.run(self._registry.get(runtime_id))

    async def get_runtime_async(self, runtime_id: str) -> Runtime | None:
        return await self._registry.get(runtime_id)

    async def list_runtimes(self, status: str | None = None) -> list[dict[str, Any]]:
        runtimes = await self._registry.list(status)
        return [r.to_dict() for r in runtimes]

    async def get_registry_snapshot(self) -> dict[str, Any]:
        return await self._registry.get_registry_snapshot()

    async def get_config(self, runtime_id: str) -> RuntimeConfiguration | None:
        return await self._config_manager.get_config(runtime_id)

    async def update_config(
        self, runtime_id: str, updates: dict[str, Any]
    ) -> RuntimeConfiguration | None:
        return await self._config_manager.update_config(runtime_id, updates)

    def get_health(self, runtime_id: str) -> Any:
        return self._health_monitor.get_health(runtime_id)

    def get_all_health(self) -> dict[str, Any]:
        return self._health_monitor.get_all_health()

    async def get_telemetry(self, runtime_id: str) -> RuntimeTelemetry | None:
        return await self._telemetry_collector.get(runtime_id)

    async def get_all_telemetry(self) -> list[RuntimeTelemetry]:
        return await self._telemetry_collector.get_all()

    def get_cache_stats(self) -> dict[str, Any]:
        return self._cache.get_stats()

    @property
    def engine_manager(self) -> ExecutionEngineManager:
        return self._engine_manager

    @property
    def registry(self) -> RuntimeRegistry:
        return self._registry

    @property
    def health_monitor(self) -> RuntimeHealthMonitor:
        return self._health_monitor

    @property
    def binding_manager(self) -> RuntimeBindingManager:
        return self._binding_manager
