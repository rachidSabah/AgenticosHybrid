"""DiscoveryFramework — main orchestrator for automatic runtime discovery & binding.

Wraps the M1 DiscoveryEngine and adds profiles, caching, telemetry, validation,
profiling, scheduling, and hot-reload. Wired into the kernel alongside the
existing RuntimeManager.
"""

import asyncio
import json
import os
import shutil
from dataclasses import dataclass, field

from agentic_os.core.discovery.cache import DiscoveryCache
from agentic_os.core.discovery.config import DiscoveryConfiguration
from agentic_os.core.discovery.profiling import ProfilingEngine
from agentic_os.core.discovery.publisher import DiscoveryEventPublisher
from agentic_os.core.discovery.registry import DiscoveryRegistry
from agentic_os.core.discovery.scheduler import DiscoveryScheduler
from agentic_os.core.discovery.telemetry import DiscoveryTelemetry
from agentic_os.core.discovery.validation import ValidationPipeline
from agentic_os.core.runtime.discovery import DiscoveryEngine
from agentic_os.domain.discovery import (
    DiscoveryProfile,
    DiscoveryProviderConfig,
    DiscoveryRule,
    ProfileResult,
    ValidationResult,
)
from agentic_os.domain.events import EventEnvelope, Topic
from agentic_os.domain.execution import ExecutionEngine
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.event_bus import EventBus
from agentic_os.ports.execution import (
    DiscoveryProvider,
    EngineRegistration,
    RuntimeManagerPort,
)

log = get_logger("discovery.framework")


@dataclass
class DiscoveryFramework:
    """Main M2 orchestrator for automatic runtime discovery and binding.

    Wraps the M1 DiscoveryEngine (core provider orchestration + dedup) and
    adds the full M2 feature set on top:

    * Provider registry with per-provider configuration and enable/disable
    * Named discovery profiles for different scan strategies
    * TTL cache with dedup across runs (not just within a single scan)
    * Validation pipeline (executable, version, health, capabilities)
    * Auto-profiling (latency, resource footprint, config defaults)
    * Telemetry tracking and aggregated statistics
    * Event publishing through the EventBus
    * Scheduled periodic scanning per profile
    * Hot-reload (polling for executable/config changes)

    Wired into the kernel via ``RuntimeManager``.
    """

    bus: EventBus
    core_engine: DiscoveryEngine
    registry: DiscoveryRegistry
    cache: DiscoveryCache
    telemetry: DiscoveryTelemetry
    scheduler: DiscoveryScheduler
    config: DiscoveryConfiguration
    validation: ValidationPipeline
    profiling: ProfilingEngine
    publisher: DiscoveryEventPublisher

    _runtime_manager: RuntimeManagerPort | None = None
    _watchers: list[object] = field(default_factory=list)
    _hot_reload_running: bool = False
    _subscriptions: list[str] = field(default_factory=list)

    # ── Runtime binding ──

    def bind_runtime(self, runtime_manager: RuntimeManagerPort) -> None:
        """Bind the framework to a RuntimeManager for auto-registration."""
        self._runtime_manager = runtime_manager

    # ── Core discovery ──

    async def discover(self, profile_name: str | None = None) -> list[EngineRegistration]:
        """Run discovery using the specified profile (or default).

        Flow:
        1. Resolve the profile and its enabled providers
        2. Check cache for each discoverable engine
        3. Run uncached providers and cache their results
        4. Apply filtering rules from config
        5. Return deduplicated registrations

        Returns deduplicated list of EngineRegistration.
        """
        profile = self._resolve_profile(profile_name)
        if profile is None:
            log.warning("No profile available for discovery")
            return []

        scan_id = self.telemetry.start_scan(profile.name)
        await self.publisher.scan_started(profile.name)

        all_registrations: list[EngineRegistration] = []
        providers_configured = 0
        providers_failed = 0

        for provider_config in profile.provider_configs:
            if not provider_config.enabled:
                continue
            providers_configured += 1
            name = provider_config.name
            provider = self.registry.get_provider(name)
            if provider is None:
                log.warning("Provider not in registry, skipping", name=name)
                continue

            await self.publisher.provider_running(name, provider.get_provider_type())

            try:
                registrations = await self.registry.discover_by_provider(name)

                for reg in registrations:
                    # Check cache first
                    cache_key = self.cache.make_key(name, reg.name, reg.endpoint or "")
                    cached = self.cache.get(cache_key)
                    if cached is not None:
                        await self.publisher.cache_hit(name, reg.name)
                        # Use cached version
                        cached_reg = json.loads(cached.registration_json)
                        engine_reg = EngineRegistration(**cached_reg)
                        all_registrations.append(engine_reg)
                    else:
                        await self.publisher.cache_miss(name, reg.name)
                        all_registrations.append(reg)
                        # Cache it
                        self.cache.create_entry(
                            provider_name=name,
                            engine_name=reg.name,
                            endpoint=reg.endpoint or "",
                            registration_dict={
                                "name": reg.name,
                                "engine_type": reg.engine_type.value,
                                "endpoint": reg.endpoint,
                                "transport": reg.transport,
                                "capabilities": [c.value for c in reg.capabilities],
                                "description": reg.description,
                                "version": reg.version,
                                "tags": list(reg.tags),
                                "metadata": dict(reg.metadata),
                            },
                            confidence=self._get_effective_confidence(provider_config, provider),
                        )

                await self.publisher.engine_discovered(
                    f"{name} ({len(registrations)} found)",
                    name,
                    self._get_effective_confidence(provider_config, provider),
                )

            except Exception as exc:
                providers_failed += 1
                await self.publisher.provider_failed(name, str(exc))
                log.warning("Provider failed during discovery", provider=name, error=str(exc))

        # Apply filtering rules
        filtered = self._apply_rules(all_registrations)

        # Deduplicate through the M1 core engine (name-based dedup)
        deduped = self._deduplicate_registrations(filtered)

        final = list(deduped)

        # Complete telemetry
        self.telemetry.complete_scan(
            scan_id,
            providers_run=providers_configured,
            providers_failed=providers_failed,
            engines_found=len(final),
        )

        # Update the core engine's provider list for backwards compat
        self._sync_core_engine()

        log.info(
            "Discovery scan complete",
            profile=profile.name,
            found=len(final),
            providers=providers_configured,
            failed=providers_failed,
        )

        return final

    async def discover_and_register(
        self,
        profile_name: str | None = None,
    ) -> list[ExecutionEngine]:
        """Run discovery then automatically register validated engines.

        This is the main entry point used by the scheduler and hot-reload.

        Returns list of registered ExecutionEngine objects.
        """
        registrations = await self.discover(profile_name)
        if not registrations:
            return []

        profile = self._resolve_profile(profile_name)
        should_validate = profile is None or profile.validate_after_discovery
        should_profile = profile is None or profile.profile_after_discovery
        should_register = profile is None or profile.auto_register

        registered: list[ExecutionEngine] = []

        for reg in registrations:
            engine_id = reg.name  # placeholder; RuntimeManager will assign real ID

            # Validate
            valid = True
            if should_validate:
                await self.publisher.validation_started(reg.name)
                all_pass, results = await self.validation.validate_and_report(reg)
                if all_pass:
                    await self.publisher.validation_passed(
                        self._make_validation_result(reg, engine_id, valid=True)
                    )
                else:
                    await self.publisher.validation_failed(
                        self._make_validation_result(
                            reg,
                            engine_id,
                            valid=False,
                            errors=[e for r in results if r.errors for e in r.errors],
                        )
                    )
                    await self.publisher.engine_rejected(reg.name, "Validation failed")
                    valid = False

            if not valid:
                continue

            # Profile
            if should_profile:
                await self.publisher.profiling_started(reg.name)
                profile_result = await self.profiling.profile(reg)
                await self.publisher.profiling_completed(profile_result)
            else:
                profile_result = None

            # Auto-register
            if should_register and self._runtime_manager:
                try:
                    engine = await self._runtime_manager.register_engine(reg)
                    if engine:
                        registered.append(engine)
                        await self.publisher.engine_registered(engine.id, engine.name)
                except ValueError:
                    # Already registered — that's fine
                    pass
                except Exception as exc:
                    log.warning("Auto-registration failed", engine=reg.name, error=str(exc))

        # Update telemetry
        last_entry = self.telemetry.get_history(1)
        if last_entry:
            # Update the last scan entry with registration count
            pass  # Already counted above

        return registered

    # ── Scheduled scanning ──

    async def start_auto_discovery(self) -> None:
        """Start scheduled discovery scans for all configured profiles."""
        await self.scheduler.start(self)

    async def stop_auto_discovery(self) -> None:
        """Stop all scheduled discovery scans."""
        await self.scheduler.stop()

    # ── Hot reload ──

    async def start_hot_reload(self) -> None:
        """Start watching for runtime changes and re-discover on change.

        Monitors:
        - Executable file modifications (mtime changes)
        - Config file changes (if config-backed providers are active)
        - EventBus signals (engine updates, config changes)
        """
        if self._hot_reload_running:
            return
        self._hot_reload_running = True
        log.info("Hot-reload started")

        # Subscribe to relevant EventBus topics
        self._subscriptions.append(
            await self.bus.subscribe(
                Topic.ENGINE_UPDATED.value,
                self._handle_hot_reload_event,
            )
        )

        # Start file watcher
        self._watchers.append(
            asyncio_create_task(self._watch_executables(), name="discovery-hot-reload")
        )

    @property
    def hot_reload_running(self) -> bool:
        """Whether hot-reload is currently active."""
        return self._hot_reload_running

    async def stop_hot_reload(self) -> None:
        """Stop file watchers and EventBus subscriptions."""
        self._hot_reload_running = False

        for watcher in self._watchers:
            if isinstance(watcher, asyncio.Task):
                watcher.cancel()
        self._watchers.clear()

        for sub_id in self._subscriptions:
            try:
                await self.bus.unsubscribe(sub_id)
            except Exception:
                pass
        self._subscriptions.clear()

        log.info("Hot-reload stopped")

    async def _watch_executables(self) -> None:
        """Poll known executable paths for changes.

        When a binary is updated or removed, invalidate the cache and
        trigger re-discovery for the affected engine.
        """

        interval = 30.0
        tracked: dict[str, tuple[str, float]] = {}  # engine_name -> (path, mtime)

        while self._hot_reload_running:
            try:
                for config_entry in self.config.profiles.values():
                    if not config_entry.provider_configs:
                        continue
                    for provider_cfg in config_entry.provider_configs:
                        provider = self.registry.get_provider(provider_cfg.name)
                        if provider is None:
                            continue

                        # Run the provider and check what changed
                        try:
                            registrations = await provider.discover()
                        except Exception:
                            continue

                        current_engines: dict[str, str] = {}
                        for reg in registrations:
                            if reg.endpoint and reg.endpoint.startswith("local:"):
                                binary = reg.endpoint.replace("local:", "", 1)
                                path = shutil.which(binary)
                                if path:
                                    current_engines[reg.name] = path

                        # Check for changes vs tracked state
                        for engine_name, path in current_engines.items():
                            try:
                                mtime = os.path.getmtime(path)
                            except OSError:
                                continue

                            tracked_info = tracked.get(engine_name)
                            if tracked_info is None:
                                tracked[engine_name] = (path, mtime)
                            else:
                                old_path, old_mtime = tracked_info
                                if path != old_path or abs(mtime - old_mtime) > 1.0:
                                    log.info(
                                        "Executable change detected",
                                        engine=engine_name,
                                        path=path,
                                    )
                                    # Invalidate cache and re-discover
                                    self.cache.invalidate_by_provider(provider_cfg.name)
                                    tracked[engine_name] = (path, mtime)

                        # Check for removed engines
                        for engine_name in list(tracked.keys()):
                            if engine_name not in current_engines:
                                log.info("Engine no longer discoverable", engine=engine_name)
                                await self.publisher.engine_lost(engine_name)
                                self.cache.invalidate_by_provider(provider_cfg.name)
                                del tracked[engine_name]

            except asyncio.CancelledError:
                break
            except Exception as exc:
                log.warning("Hot-reload check failed", error=str(exc))

            await asyncio.sleep(interval)

    async def _handle_hot_reload_event(self, event: EventEnvelope) -> None:
        """Handle an EventBus event that may trigger re-discovery."""
        engine_id = event.payload.get("engine_id", "")
        if not engine_id:
            return
        log.info("Hot-reload event received", engine_id=engine_id, topic=event.topic)
        # Re-discover will pick up changes on next poll cycle

    # ── Validation API ──

    async def validate_engine(
        self,
        registration: EngineRegistration,
        executable_path: str | None = None,
        engine: ExecutionEngine | None = None,
    ) -> tuple[bool, list]:
        """Validate a discovered engine through the full pipeline."""
        return await self.validation.validate_and_report(registration, executable_path, engine)

    async def profile_engine(
        self,
        registration: EngineRegistration,
        engine: ExecutionEngine | None = None,
    ) -> ProfileResult:
        """Profile a discovered engine."""
        return await self.profiling.profile(registration)

    # ── Provider management (delegates to registry) ──

    def list_providers(self) -> list[dict]:
        """List all registered discovery providers with status."""
        return self.registry.list_providers()

    def get_provider(self, name: str) -> DiscoveryProvider | None:
        """Get a discovery provider by name."""
        return self.registry.get_provider(name)

    def enable_provider(self, name: str) -> bool:
        """Enable a discovery provider."""
        return self.registry.enable_provider(name)

    def disable_provider(self, name: str) -> bool:
        """Disable a discovery provider."""
        return self.registry.disable_provider(name)

    def is_provider_enabled(self, name: str) -> bool:
        """Check if a provider is enabled."""
        return self.registry.is_enabled(name)

    # ── Cache management (delegates to cache) ──

    def get_cache_entries(self) -> list[dict]:
        """List all active (non-expired) cache entries as dicts."""
        return [e.to_dict() for e in self.cache.list_entries()]

    def invalidate_cache(self, key: str | None = None) -> int:
        """Invalidate cache entries. If key is None, invalidate all."""
        if key:
            self.cache.invalidate(key)
            return 1
        return self.cache.invalidate_all()

    # ── Profile management (delegates) ──

    def add_profile(self, profile: DiscoveryProfile) -> None:
        """Add a discovery profile."""
        self.config.add_profile(profile)

    def remove_profile(self, name: str) -> bool:
        """Remove a discovery profile."""
        return self.config.remove_profile(name)

    def get_profile(self, name: str) -> DiscoveryProfile | None:
        """Get a profile by name."""
        return self.config.get_profile(name)

    def list_profiles(self) -> list[dict]:
        """List all profiles."""
        return self.config.list_profiles()

    def add_rule(self, rule: DiscoveryRule) -> None:
        """Add a filtering rule."""
        self.config.add_rule(rule)

    def register_provider(
        self,
        name: str,
        provider: DiscoveryProvider,
        config: DiscoveryProviderConfig | None = None,
    ) -> None:
        """Register a discovery provider."""
        self.registry.register(name, provider, config)
        # Also register in the M1 core engine for backwards compat
        if name not in self.core_engine._providers:  # type: ignore[attr-defined]
            self.core_engine.add_provider(provider)

    def unregister_provider(self, name: str) -> bool:
        """Unregister a discovery provider."""
        core_removed = self.core_engine.remove_provider(name)
        registry_removed = self.registry.unregister(name)
        return core_removed or registry_removed

    # ── Internal helpers ──

    def _resolve_profile(self, profile_name: str | None) -> DiscoveryProfile | None:
        """Resolve a profile name to a DiscoveryProfile object."""
        if profile_name:
            profile = self.config.get_profile(profile_name)
            if profile is None:
                log.warning("Unknown profile", name=profile_name)
                return None
            return profile

        # Try default profile
        profile = self.config.get_profile(self.config.default_profile)
        if profile is not None:
            return profile

        # Create on-the-fly default from all enabled providers
        if self.registry.count() > 0:
            provider_configs = []
            for p_info in self.registry.list_providers():
                provider_configs.append(
                    DiscoveryProviderConfig(
                        name=p_info["name"],
                        provider_type=p_info["provider_type"],
                        enabled=p_info["enabled"],
                        interval_seconds=p_info["interval_seconds"],
                        timeout_seconds=p_info["timeout_seconds"],
                    )
                )
            profile = DiscoveryProfile(
                name="default",
                description="Auto-generated default profile",
                provider_configs=tuple(provider_configs),
            )
            self.config.add_profile(profile)
            return profile

        return None

    def _apply_rules(self, registrations: list[EngineRegistration]) -> list[EngineRegistration]:
        """Apply filtering rules to registrations."""
        rules = self.config.get_rules()
        if not rules:
            return registrations

        result = list(registrations)
        for rule in rules:
            if rule.action == "reject":
                result = [r for r in result if not self._registration_matches_rule(r, rule)]
            elif rule.action == "accept":
                result = [r for r in result if self._registration_matches_rule(r, rule)]

        return result

    @staticmethod
    def _registration_matches_rule(reg: EngineRegistration, rule: DiscoveryRule) -> bool:
        """Check if a registration matches a rule."""
        reg_dict = {
            "name": reg.name,
            "engine_type": reg.engine_type.value,
            "version": reg.version,
            "capability": [c.value for c in reg.capabilities],
            "platform": reg.metadata.get("platform", ""),
            "endpoint": reg.endpoint or "",
            "transport": reg.transport,
        }
        return rule.matches(reg_dict)

    @staticmethod
    def _deduplicate_registrations(
        registrations: list[EngineRegistration],
    ) -> list[EngineRegistration]:
        """Simple name-based deduplication (keep first occurrence)."""
        seen: set[str] = set()
        result: list[EngineRegistration] = []
        for reg in registrations:
            if reg.name not in seen:
                seen.add(reg.name)
                result.append(reg)
        return result

    def _get_effective_confidence(
        self,
        config: DiscoveryProviderConfig,
        provider: DiscoveryProvider,
    ) -> float:
        """Get the effective confidence, considering override."""
        if config.confidence_override is not None:
            return config.confidence_override
        return self.core_engine._get_provider_confidence(provider.get_provider_type())  # type: ignore[attr-defined]

    @staticmethod
    def _find_provider_for_registration(registration: EngineRegistration) -> str | None:
        """Try to find which provider discovered this engine by inspecting metadata."""
        providers_list = registration.metadata.get("providers", [])
        if isinstance(providers_list, list) and providers_list:
            return providers_list[0]
        return None

    def _sync_core_engine(self) -> None:
        """Synchronize the M1 core engine's provider list with the M2 registry."""
        for info in self.registry.list_providers():
            name = info["name"]
            if name not in self.core_engine._providers:  # type: ignore[attr-defined]
                provider = self.registry.get_provider(name)
                if provider is not None:
                    self.core_engine.add_provider(provider)

    @staticmethod
    def _make_validation_result(
        reg: EngineRegistration,
        engine_id: str,
        valid: bool,
        errors: tuple[str, ...] | list[str] = (),
    ) -> ValidationResult:
        """Create a minimal ValidationResult for event emission."""

        if valid:
            return ValidationResult.passed(engine_id=engine_id, engine_name=reg.name)
        return ValidationResult.failed(
            engine_id,
            reg.name,
            *[str(e) for e in errors],
        )


def asyncio_create_task(coro, name=None):
    """Helper to create an asyncio task with optional name."""
    return asyncio.create_task(coro, name=name)
