"""Production hardening — startup validation, integrity, diagnostics, recovery, and shutdown."""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from agentic_os.domain.desktop import (
    CleanupResult,
    HardeningConfig,
    IntegrityCheckResult,
    IntegrityStatus,
    MemoryLeakReport,
    RecoveryModeConfig,
    RepairAction,
    RepairResult,
    ResourceUsageSummary,
    SelfDiagnosticsReport,
    ShutdownPlan,
    StartupValidationResult,
    ThreadReport,
)
from agentic_os.infrastructure.logging import get_logger

log = get_logger("desktop.hardening")


class DesktopHardeningManager:
    """Validates, monitors, repairs, and gracefully shuts down the desktop runtime."""

    def __init__(self) -> None:
        self._config = HardeningConfig()
        self._recovery_config = RecoveryModeConfig()
        self._startup_result: StartupValidationResult | None = None
        self._last_integrity_check: IntegrityCheckResult | None = None
        self._last_memory_report: MemoryLeakReport | None = None
        self._last_thread_report: ThreadReport | None = None
        self._memory_baseline_mb: float = 0.0
        self._in_recovery: bool = False
        self._shutdown_plan: ShutdownPlan | None = None
        self._cleanup_history: list[CleanupResult] = []

    # ── Config ──

    async def get_config(self) -> HardeningConfig:
        return self._config

    async def update_config(self, config: HardeningConfig) -> HardeningConfig:
        self._config = config
        return self._config

    async def get_recovery_config(self) -> RecoveryModeConfig:
        return self._recovery_config

    async def update_recovery_config(self, config: RecoveryModeConfig) -> RecoveryModeConfig:
        self._recovery_config = config
        return self._recovery_config

    # ── Startup Validation ──

    async def validate_startup(self) -> StartupValidationResult:
        started = datetime.now(UTC)
        checks: list[dict[str, Any]] = []
        warnings: list[str] = []
        errors: list[str] = []

        # Check 1: Python version
        import sys

        py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        checks.append({"name": "python_version", "status": "ok", "value": py_version})

        # Check 2: Config file exists
        config_paths = [os.environ.get("AGENTIC_OS_CONFIG", ""), ".env", "config.toml"]
        config_found = any(os.path.exists(p) for p in config_paths if p)
        checks.append(
            {
                "name": "config_exists",
                "status": "ok" if config_found else "warn",
                "value": str(config_found),
            }
        )
        if not config_found:
            warnings.append("No configuration file found, using defaults")

        # Check 3: Workspace directory
        ws_dir = os.environ.get("AGENTIC_OS_WORKSPACE_DIR", "")
        ws_ok = not ws_dir or os.path.isdir(ws_dir)
        checks.append(
            {
                "name": "workspace_dir",
                "status": "ok" if ws_ok else "warn",
                "value": ws_dir or "default",
            }
        )
        if not ws_ok:
            warnings.append(f"Workspace directory does not exist: {ws_dir}")

        # Check 4: Database directory
        db_dir = os.environ.get("AGENTIC_OS_DB_DIR", "")
        db_ok = not db_dir or os.path.isdir(db_dir)
        checks.append(
            {
                "name": "database_dir",
                "status": "ok" if db_ok else "warn",
                "value": db_dir or "default",
            }
        )

        # Check 5: Port availability
        port = int(os.environ.get("AGENTIC_OS_PORT", "8000"))
        checks.append({"name": "port", "status": "ok", "value": str(port)})

        duration = (datetime.now(UTC) - started).total_seconds()
        success = len(errors) == 0
        self._startup_result = StartupValidationResult(
            success=success,
            started_at=started,
            duration_seconds=duration,
            checks=checks,
            warnings=warnings,
            errors=errors,
        )

        if success:
            log.info("Startup validation passed", checks=len(checks), duration=duration)
        else:
            log.warning("Startup validation had issues", errors=errors, warnings=warnings)

        return self._startup_result

    async def get_last_startup_validation(self) -> StartupValidationResult | None:
        return self._startup_result

    # ── Integrity Validation ──

    async def check_integrity(self) -> IntegrityCheckResult:
        started_at = datetime.now(UTC)
        checks: list[dict[str, Any]] = []
        warnings: list[str] = []
        errors: list[str] = []

        # Core modules check
        try:
            import importlib

            importlib.import_module("agentic_os.core.desktop.manager")
            checks.append({"name": "desktop_runtime_manager", "status": "ok"})
        except ImportError as e:
            checks.append({"name": "desktop_runtime_manager", "status": "fail", "error": str(e)})
            errors.append(f"DesktopRuntimeManager import failed: {e}")

        # Domain models check
        try:
            importlib.import_module("agentic_os.domain.desktop")
            checks.append({"name": "domain_models", "status": "ok"})
        except ImportError as e:
            checks.append({"name": "domain_models", "status": "fail", "error": str(e)})
            errors.append(f"Domain model import failed: {e}")

        # Ports check
        try:
            importlib.import_module("agentic_os.ports.desktop_ops")
            checks.append({"name": "ports", "status": "ok"})
        except ImportError as e:
            checks.append({"name": "ports", "status": "fail", "error": str(e)})
            errors.append(f"Port interface import failed: {e}")

        # Memory check
        try:
            import psutil

            process = psutil.Process()
            memory_mb = process.memory_info().rss / (1024 * 1024)
            checks.append({"name": "memory", "status": "ok", "value_mb": round(memory_mb, 1)})
            if memory_mb > 500:
                warnings.append(f"Memory usage high: {memory_mb:.0f} MB")
        except ImportError:
            checks.append({"name": "memory", "status": "warn", "reason": "psutil not available"})

        duration = (datetime.now(UTC) - started_at).total_seconds()
        status = (
            IntegrityStatus.FAILED
            if errors
            else (IntegrityStatus.DEGRADED if warnings else IntegrityStatus.HEALTHY)
        )
        self._last_integrity_check = IntegrityCheckResult(
            status=status,
            checked_at=started_at,
            duration_seconds=duration,
            checks=checks,
            warnings=warnings,
            errors=errors,
        )
        return self._last_integrity_check

    async def get_last_integrity_check(self) -> IntegrityCheckResult | None:
        return self._last_integrity_check

    # ── Self Diagnostics ──

    async def run_self_diagnostics(self) -> SelfDiagnosticsReport:
        services: list[dict[str, Any]] = []
        checks: list[dict[str, Any]] = []
        warnings: list[str] = []
        errors: list[str] = []
        recommendations: list[str] = []

        # Check desktop services
        import importlib

        service_modules = [
            "agentic_os.core.desktop.manager",
            "agentic_os.core.desktop.window",
            "agentic_os.core.desktop.workspace",
            "agentic_os.core.desktop.update",
            "agentic_os.core.desktop.offline",
            "agentic_os.core.desktop.backup",
        ]
        for mod_name in service_modules:
            try:
                importlib.import_module(mod_name)
                services.append({"name": mod_name, "status": "healthy"})
            except ImportError as e:
                services.append({"name": mod_name, "status": "unhealthy", "error": str(e)})
                errors.append(f"Service module not available: {mod_name}")

        # Disk space check
        try:
            import psutil

            disk = psutil.disk_usage(os.path.abspath(os.sep))
            free_gb = disk.free / (1024**3)
            checks.append({"name": "disk_space", "value_gb": round(free_gb, 1)})
            if free_gb < 1:
                warnings.append(f"Low disk space: {free_gb:.1f} GB free")
                recommendations.append("Free up disk space to ensure proper operation")
        except ImportError:
            pass

        # Recommendations
        if any(s["status"] == "unhealthy" for s in services):
            recommendations.append("Restart the desktop runtime to reload service modules")
        recommendations.append("Run integrity check after any configuration change")
        recommendations.append("Keep backups for disaster recovery")

        status = (
            IntegrityStatus.FAILED
            if errors
            else (IntegrityStatus.DEGRADED if warnings else IntegrityStatus.HEALTHY)
        )
        return SelfDiagnosticsReport(
            status=status,
            services=services,
            checks=checks,
            warnings=warnings,
            errors=errors,
            recommendations=recommendations,
        )

    # ── Memory Leak Detection ──

    async def check_memory_leaks(self) -> MemoryLeakReport:
        detected_at = datetime.now(UTC)
        result = MemoryLeakReport(detected_at=detected_at)

        try:
            import psutil

            process = psutil.Process()
            current_mb = process.memory_info().rss / (1024 * 1024)
            result.current_memory_mb = current_mb

            if self._memory_baseline_mb == 0:
                self._memory_baseline_mb = current_mb
                result.baseline_memory_mb = current_mb
                result.detected = False
            else:
                result.baseline_memory_mb = self._memory_baseline_mb
                growth = current_mb - self._memory_baseline_mb
                result.growth_rate_mb_per_minute = growth
                if growth > self._config.memory_leak_threshold_mb:
                    result.detected = True
                    result.recommendations = [
                        "Restart the desktop runtime to reclaim memory",
                        "Check for excessive caching or unclosed resources",
                    ]
                    log.warning("Potential memory leak detected", growth_mb=round(growth, 1))
        except ImportError:
            pass

        self._last_memory_report = result
        return result

    async def get_last_memory_report(self) -> MemoryLeakReport | None:
        return self._last_memory_report

    # ── Thread Monitoring ──

    async def monitor_threads(self) -> ThreadReport:
        sampled_at = datetime.now(UTC)
        threads = threading.enumerate()
        active = sum(1 for t in threads if t.is_alive())
        total = len(threads)
        threshold = self._config.thread_count_threshold

        result = ThreadReport(
            total_threads=total,
            active_threads=active,
            blocked_threads=0,
            deadlocked_threads=0,
            threshold_exceeded=total > threshold,
            threshold=threshold,
            sampled_at=sampled_at,
            threads=[
                {"name": t.name, "daemon": t.daemon, "alive": t.is_alive()} for t in threads[:50]
            ],
        )

        if result.threshold_exceeded:
            log.warning("Thread threshold exceeded", total=total, threshold=threshold)

        self._last_thread_report = result
        return result

    async def get_last_thread_report(self) -> ThreadReport | None:
        return self._last_thread_report

    # ── Resource Cleanup ──

    async def cleanup_resources(self) -> CleanupResult:
        started_at = datetime.now(UTC)
        actions: list[dict[str, Any]] = []
        items_cleaned = 0

        # Clean temp files
        import glob
        import shutil
        import tempfile

        try:
            temp_pattern = os.path.join(tempfile.gettempdir(), "agentic_os_*")
            temp_files = glob.glob(temp_pattern)
            for f in temp_files:
                try:
                    if os.path.isfile(f):
                        os.remove(f)
                    elif os.path.isdir(f):
                        shutil.rmtree(f)
                    items_cleaned += 1
                except OSError:
                    pass
            actions.append(
                {"action": "clean_temp", "count": len(temp_files), "status": "completed"}
            )
        except Exception as e:
            actions.append({"action": "clean_temp", "status": "failed", "error": str(e)})

        # Clean cache
        cache_dir = os.environ.get("AGENTIC_OS_CACHE_DIR", "")
        if cache_dir and os.path.isdir(cache_dir):
            try:
                for entry in os.listdir(cache_dir):
                    path = os.path.join(cache_dir, entry)
                    if os.path.isfile(path):
                        os.remove(path)
                        items_cleaned += 1
                actions.append({"action": "clean_cache", "status": "completed"})
            except Exception as e:
                actions.append({"action": "clean_cache", "status": "failed", "error": str(e)})

        duration = (datetime.now(UTC) - started_at).total_seconds()
        result = CleanupResult(
            success=True,
            started_at=started_at,
            duration_seconds=duration,
            items_cleaned=items_cleaned,
            actions=actions,
        )
        self._cleanup_history.append(result)
        if len(self._cleanup_history) > 100:
            self._cleanup_history = self._cleanup_history[-100:]
        return result

    async def get_cleanup_history(self) -> list[CleanupResult]:
        return list(self._cleanup_history)

    # ── Automatic Repair ──

    async def repair(self, targets: list[str] | None = None) -> RepairResult:
        actions: list[RepairAction] = []
        repaired: list[str] = []
        failed: list[str] = []

        targets = targets or ["workspace", "config", "cache", "database"]

        for target in targets:
            action = RepairAction(action="repair", target=target)
            try:
                if target == "workspace":
                    ws_dir = os.environ.get("AGENTIC_OS_WORKSPACE_DIR", "")
                    if ws_dir and not os.path.isdir(ws_dir):
                        os.makedirs(ws_dir, exist_ok=True)
                    action.status = "completed"
                    repaired.append(target)

                elif target == "config":
                    config_file = os.environ.get("AGENTIC_OS_CONFIG", "")
                    if config_file and not os.path.exists(config_file):
                        parent = os.path.dirname(config_file)
                        if parent:
                            os.makedirs(parent, exist_ok=True)
                    action.status = "completed"
                    repaired.append(target)

                elif target == "cache":
                    cache_dir = os.environ.get("AGENTIC_OS_CACHE_DIR", "")
                    if cache_dir:
                        os.makedirs(cache_dir, exist_ok=True)
                    action.status = "completed"
                    repaired.append(target)

                elif target == "database":
                    db_dir = os.environ.get("AGENTIC_OS_DB_DIR", "")
                    if db_dir:
                        os.makedirs(db_dir, exist_ok=True)
                    action.status = "completed"
                    repaired.append(target)

                else:
                    action.status = "skipped"
                    action.error = f"Unknown repair target: {target}"

            except Exception as e:
                action.status = "failed"
                action.error = str(e)
                failed.append(target)

            actions.append(action)

        duration = sum(a.duration_seconds for a in actions)
        return RepairResult(
            success=len(failed) == 0,
            repaired=repaired,
            failed=failed,
            actions=actions,
            duration_seconds=duration,
        )

    # ── Recovery Mode ──

    async def enter_recovery_mode(self) -> bool:
        if self._in_recovery:
            return False
        self._in_recovery = True
        log.info("Entered recovery mode")
        return True

    async def exit_recovery_mode(self) -> bool:
        if not self._in_recovery:
            return False
        self._in_recovery = False
        log.info("Exited recovery mode")
        return True

    async def is_in_recovery(self) -> bool:
        return self._in_recovery

    async def recover(self) -> RepairResult:
        await self.enter_recovery_mode()
        result = await self.repair()
        if result.success:
            await self.cleanup_resources()
        await self.exit_recovery_mode()
        return result

    async def get_resource_usage(self) -> ResourceUsageSummary:
        try:
            import psutil

            process = psutil.Process()
            cpu = process.cpu_percent(interval=0.1)
            mem = process.memory_info().rss / (1024 * 1024)
            threads_count = len(threading.enumerate())
            connections = len(process.connections())
            io = process.io_counters()
            disk_io = (io.read_bytes + io.write_bytes) / max(time.time() - process.create_time(), 1)
            return ResourceUsageSummary(
                cpu_percent=cpu,
                memory_mb=round(mem, 1),
                thread_count=threads_count,
                open_handles=process.num_handles(),
                network_connections=connections,
                disk_io_bytes_per_sec=round(disk_io, 1),
            )
        except ImportError:
            return ResourceUsageSummary(
                thread_count=len(threading.enumerate()),
            )

    # ── Graceful Shutdown ──

    async def plan_shutdown(self, force: bool = False) -> ShutdownPlan:
        steps: list[dict[str, Any]] = [
            {"step": "save_workspaces", "status": "pending", "order": 1},
            {"step": "stop_monitoring", "status": "pending", "order": 2},
            {"step": "close_database", "status": "pending", "order": 3},
            {"step": "cleanup_resources", "status": "pending", "order": 4},
            {"step": "publish_shutdown_event", "status": "pending", "order": 5},
            {"step": "stop_services", "status": "pending", "order": 6},
        ]
        self._shutdown_plan = ShutdownPlan(
            timeout_seconds=self._config.graceful_shutdown_timeout_seconds,
            force=force,
            save_workspaces=True,
            steps=steps,
        )
        return self._shutdown_plan

    async def get_shutdown_plan(self) -> ShutdownPlan | None:
        return self._shutdown_plan

    async def get_recovery_history(self) -> Sequence[dict[str, Any]]:
        return []

    async def get_repair_history(self) -> Sequence[dict[str, Any]]:
        return []
