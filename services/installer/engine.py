"""Installer Intelligence Engine — orchestrates automatic agent discovery,
validation, binding, monitoring, and self-healing.

This is the main entry point for the installer intelligence system.
It coordinates all phases specified in the installer spec.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from core.logging import get_logger
from services.installer.healer import HealReport, SelfHealingEngine
from services.installer.provider_catalog import PROVIDER_CATALOG, ProviderDef
from services.installer.report import InstallReport, InstallReportGenerator
from services.installer.upgrade import UpgradeManager
from services.installer.validator import ValidationPipeline, ValidationReport, ValidationResult
from services.installer.watcher import RuntimeChangeEvent, RuntimeWatcher

log = get_logger("installer.engine")


@dataclass
class InstallerPhaseResult:
    """Result of a single installation phase."""

    phase: str
    success: bool
    duration_seconds: float = 0.0
    details: str = ""


@dataclass
class InstallerResult:
    """Complete result of the installation intelligence run."""

    success: bool
    phases: list[InstallerPhaseResult] = field(default_factory=list)
    validation_report: ValidationReport | None = None
    install_report: InstallReport | None = None
    heal_report: HealReport | None = None
    bound_providers: list[str] = field(default_factory=list)
    binding_errors: list[str] = field(default_factory=list)
    total_duration_seconds: float = 0.0


class InstallerIntelligence:
    """Main orchestrator for installer intelligence.

    Manages the complete lifecycle:
        Phase 1: install, verify integrity, runtimes, permissions
        Phase 2: discover every AI runtime on the machine
        Phase 3: validate every discovered runtime
        Phase 4: automatically bind validated providers
        Phase 5: generate install report
        Phase 6: start continuous watcher
        Phase 7: start self-healing engine
    """

    def __init__(
        self,
        providers: list[ProviderDef] | None = None,
        validation_timeout: float = 15.0,
        watcher_poll_interval: float = 30.0,
        report_path: str | None = None,
    ):
        self._providers = providers or list(PROVIDER_CATALOG)
        self._validator = ValidationPipeline(timeout=validation_timeout)
        self._healer = SelfHealingEngine()
        self._watcher = RuntimeWatcher(
            providers=self._providers,
            poll_interval=watcher_poll_interval,
        )
        self._report_gen = InstallReportGenerator(report_path=report_path)
        self._upgrade_mgr = UpgradeManager()

        # Current state
        self._validation_report: ValidationReport | None = None
        self._install_report: InstallReport | None = None
        self._bound_providers: dict[str, dict[str, Any]] = {}
        self._running: bool = False

        # Register watcher handler for auto-bind on change
        self._watcher.on_change(self._on_runtime_change)

    # ── Properties ──

    @property
    def validation_report(self) -> ValidationReport | None:
        return self._validation_report

    @property
    def install_report(self) -> InstallReport | None:
        return self._install_report

    @property
    def bound_providers(self) -> dict[str, dict[str, Any]]:
        return dict(self._bound_providers)

    # ── Full Install Run ──

    async def run_full_install(
        self,
        previous_version: str | None = None,
    ) -> InstallerResult:
        """Run the complete installation intelligence pipeline."""
        t0 = time.perf_counter()
        result = InstallerResult(success=True)

        # Phase 1: Discovery
        p1 = await self._run_phase("Phase 1: Runtime Discovery", self._discover_runtimes)
        result.phases.append(p1)

        # Phase 2: Validation
        p2 = await self._run_phase("Phase 2: Provider Validation", self._validate_providers)
        result.phases.append(p2)

        # Phase 3: Binding
        p3 = await self._run_phase("Phase 3: Automatic Binding", self._bind_providers)
        result.phases.append(p3)
        result.bound_providers = list(self._bound_providers.keys())
        result.binding_errors = self._detect_binding_errors()

        # Phase 4: Report generation
        p4 = await self._run_phase("Phase 4: Report Generation", self._generate_report)
        result.phases.append(p4)

        # Phase 5: Upgrade migration (if applicable)
        if previous_version:
            p5 = await self._run_phase("Phase 5: Upgrade Migration",
                lambda: self._run_upgrade(previous_version))
            result.phases.append(p5)

        # Phase 6: Start watcher
        p6 = await self._run_phase("Phase 6: Start Watcher", self._start_watcher)
        result.phases.append(p6)

        result.validation_report = self._validation_report
        result.install_report = self._install_report
        result.total_duration_seconds = time.perf_counter() - t0

        result.success = all(p.success for p in result.phases)
        return result

    # ── Individual Phase Execution ──

    async def _run_phase(
        self, name: str, coro_fn: Callable[[], Any]
    ) -> InstallerPhaseResult:
        """Execute a phase with timing."""
        t0 = time.perf_counter()
        try:
            if asyncio.iscoroutinefunction(coro_fn):
                await coro_fn()
            else:
                coro_fn()
            return InstallerPhaseResult(
                phase=name,
                success=True,
                duration_seconds=time.perf_counter() - t0,
            )
        except Exception as exc:
            log.error("Phase failed", phase=name, error=str(exc))
            return InstallerPhaseResult(
                phase=name,
                success=False,
                duration_seconds=time.perf_counter() - t0,
                details=str(exc),
            )

    async def run_quick_scan(self) -> ValidationReport:
        """Quick scan — validate without full install phases."""
        self._validation_report = await self._validator.validate_many(self._providers)
        log.info("Quick scan completed",
                 total=len(self._validation_report.results),
                 passed=self._validation_report.total_passed)
        return self._validation_report

    # ── Phase Implementations ──

    async def _discover_runtimes(self) -> None:
        """Phase 2: search every location for every provider."""
        found = 0
        for provider in self._providers:
            paths = self._search_all_locations(provider)
            if paths:
                found += 1
        log.info("Discovery completed",
                 providers=len(self._providers),
                 found=found)

    def _search_all_locations(self, provider: ProviderDef) -> list[str]:
        """Search every known location for a provider's executable."""
        found: list[str] = []

        # PATH
        for name in provider.exe_names:
            import shutil
            exe = shutil.which(name)
            if exe:
                found.append(exe)

        # Install dirs
        for path in provider.install_paths:
            for name in provider.exe_names:
                full = os.path.join(path, name)
                if os.path.isfile(full):
                    found.append(full)

        # Environment variables
        for var in provider.env_vars:
            val = os.environ.get(var)
            if val:
                if os.path.isfile(val):
                    found.append(val)
                else:
                    for name in provider.exe_names:
                        full = os.path.join(val, name)
                        if os.path.isfile(full):
                            found.append(full)

        # Package managers (check if installable, not necessarily installed)
        self._check_package_manager(provider, "npm", found)
        self._check_package_manager(provider, "pip", found)
        self._check_package_manager(provider, "cargo", found)

        return found

    def _check_package_manager(self, provider: ProviderDef, pkg_type: str, found: list[str]) -> None:
        """Check if a package manager has the provider."""
        pkg_names = {
            "npm": provider.pkg_npm,
            "pip": provider.pkg_pip,
            "cargo": provider.pkg_cargo,
        }.get(pkg_type, ())

        if not pkg_names:
            return

        exe = shutil.which(pkg_type)
        if not exe:
            return

        import subprocess
        for pkg in pkg_names:
            try:
                if pkg_type == "npm":
                    result = subprocess.run(
                        [exe, "list", "-g", pkg],
                        capture_output=True, text=True, timeout=5
                    )
                    if result.returncode == 0 and pkg in result.stdout:
                        # Find the actual executable
                        node_bin = os.path.join(
                            os.path.dirname(os.path.dirname(exe)), "bin"
                        )
                        for name in provider.exe_names:
                            full = os.path.join(node_bin, name)
                            if os.path.isfile(full):
                                found.append(full)
                                break
            except (subprocess.TimeoutExpired, OSError):
                pass

    async def _validate_providers(self) -> None:
        """Phase 3: validate every discovered runtime."""
        self._validation_report = await self._validator.validate_many(self._providers)
        log.info("Validation completed",
                 total=len(self._validation_report.results),
                 passed=self._validation_report.total_passed,
                 failed=self._validation_report.total_failed)

    async def _bind_providers(self) -> None:
        """Phase 4: auto-bind every validated provider."""
        if not self._validation_report:
            return

        for result in self._validation_report.passed:
            binding = self._create_binding(result)
            self._bound_providers[result.provider_id] = binding
            self._healer.register_binding(result.provider_id, binding)
            log.info("Provider bound", provider=result.provider_id,
                     exe=result.executable_path)

    def _create_binding(self, result: ValidationResult) -> dict[str, Any]:
        """Create a complete binding configuration for a validated provider."""
        provider_def = None
        for p in self._providers:
            if p.id == result.provider_id:
                provider_def = p
                break

        return {
            "provider_id": result.provider_id,
            "display_name": provider_def.display_name if provider_def else result.provider_id,
            "engine_type": provider_def.engine_type if provider_def else "CUSTOM",
            "executable_path": result.executable_path,
            "version": result.version,
            "version_raw": result.version_raw,
            "status": "healthy",
            "capabilities": list(result.detected_capabilities),
            "features": {
                "streaming": result.supports_streaming,
                "vision": result.supports_vision,
                "attachments": result.supports_attachments,
                "code_execution": result.supports_code_execution,
                "shell": result.supports_shell,
                "web_browsing": result.supports_web_browsing,
            },
            "launch_time_ms": round(result.launch_time_ms, 1),
            "exe_names": list(provider_def.exe_names) if provider_def else [],
            "install_paths": list(provider_def.install_paths) if provider_def else [],
            "env_vars": list(provider_def.env_vars) if provider_def else [],
            "config_path": "",
            "permissions": {},
            "routing_rules": {
                "priority": 10,
                "tags": [],
            },
            "bound_at": time.time(),
        }

    def _detect_binding_errors(self) -> list[str]:
        """Detect any binding errors."""
        errors = []
        for pid, binding in self._bound_providers.items():
            if not binding.get("executable_path"):
                errors.append(f"{pid}: No executable path in binding")
        return errors

    async def _generate_report(self) -> None:
        """Phase 5: generate and save the install report."""
        if not self._validation_report:
            return

        self._install_report = self._report_gen.generate_from_validation(
            validation_report=self._validation_report,
            bound_ids=list(self._bound_providers.keys()),
            binding_errors=self._detect_binding_errors(),
        )
        self._report_gen.save(self._install_report)

    async def _run_upgrade(self, previous_version: str) -> None:
        """Phase 5b: run upgrade migration."""
        import agentic_os
        current_version = getattr(agentic_os, "__version__", "1.0.0-rc1")
        manifest = self._upgrade_mgr.perform_upgrade(
            from_version=previous_version,
            to_version=current_version,
        )
        if not manifest.success:
            log.warning("Upgrade had errors", errors=manifest.migration_errors)

    async def _start_watcher(self) -> None:
        """Phase 6: start the runtime watcher."""
        await self._watcher.start()
        self._running = True

    # ── First Launch (load cache, background verify) ──

    async def first_launch(self) -> None:
        """Handle first launch after installation.

        Loads the installer discovery cache and performs a background
        verification to detect any changes since installation.
        """
        # Load cached report
        cached = self._report_gen.load()
        if cached:
            log.info("Loaded cached install report",
                     generated_at=cached.generated_at,
                     providers=len(cached.detected_providers))
        else:
            log.info("No cached install report — running full discovery")
            await self.run_full_install()
            return

        # Background verification
        log.info("Running background verification")
        asyncio.create_task(self._background_verify(cached))

    async def _background_verify(self, cached: InstallReport) -> None:
        """Verify cached bindings against current system state."""
        # Quick scan current providers
        report = await self._validator.validate_many(self._providers)

        # Compare with cached state
        for cached_p in cached.detected_providers:
            pid = cached_p.get("provider_id", "")
            current = next(
                (r for r in report.results if r.provider_id == pid and r.passed),
                None,
            )
            if current:
                # Provider still present — verify binding
                if pid in self._bound_providers:
                    self._bound_providers[pid]["status"] = "healthy"
            else:
                # Provider missing — try to repair
                log.info("Provider missing since install, attempting repair", provider=pid)
                await self._healer.heal_provider(pid)

        # Find newly added providers
        for r in report.results:
            if r.passed and r.provider_id not in [p.get("provider_id") for p in cached.detected_providers]:
                log.info("New provider detected since install", provider=r.provider_id)
                binding = self._create_binding(r)
                self._bound_providers[r.provider_id] = binding
                self._healer.register_binding(r.provider_id, binding)

    # ── Watcher Event Handler ──

    async def _on_runtime_change(self, event: RuntimeChangeEvent) -> None:
        """Handle runtime change events from the watcher."""
        log.info("Runtime change event",
                 provider=event.provider_id,
                 change=event.change_type)

        if event.change_type == "added":
            provider = next(
                (p for p in self._providers if p.id == event.provider_id),
                None,
            )
            if provider and event.new_path:
                result = await self._validator.validate(provider, event.new_path)
                if result.passed:
                    binding = self._create_binding(result)
                    self._bound_providers[result.provider_id] = binding
                    self._healer.register_binding(result.provider_id, binding)
                    log.info("Auto-bound new provider", provider=result.provider_id)

        elif event.change_type == "removed":
            self._bound_providers.pop(event.provider_id, None)
            self._healer.unregister_binding(event.provider_id)
            log.info("Unbound removed provider", provider=event.provider_id)

        elif event.change_type == "path_changed":
            # Update binding with new path
            binding = self._bound_providers.get(event.provider_id)
            if binding and event.new_path:
                binding["executable_path"] = event.new_path
                log.info("Updated binding path",
                         provider=event.provider_id,
                         new_path=event.new_path)

    # ── Self-Healing ──

    async def heal_all(self) -> HealReport:
        """Run self-healing on all bound providers."""
        return await self._healer.heal_all()

    # ── Lifecycle ──

    async def shutdown(self) -> None:
        """Gracefully shut down the installer intelligence system."""
        await self._watcher.stop()
        self._running = False
        log.info("Installer intelligence shut down")


# Needed for os.path / shutil in _search_all_locations
import os
import shutil
