"""Tests for Production Hardening — Phase 4 M6 Part 3."""

from __future__ import annotations

import pytest

from agentic_os.core.desktop import DesktopHardeningManager
from agentic_os.domain.desktop import (
    HardeningConfig,
    IntegrityStatus,
    RecoveryModeConfig,
)


class TestDesktopHardeningManager:
    @pytest.mark.asyncio
    async def test_default_config(self) -> None:
        mgr = DesktopHardeningManager()
        config = await mgr.get_config()
        assert config.validate_on_startup is True
        assert config.integrity_check_interval_seconds == 300
        assert config.enable_memory_leak_detection is True
        assert config.enable_thread_monitoring is True

    @pytest.mark.asyncio
    async def test_update_config(self) -> None:
        mgr = DesktopHardeningManager()
        new_config = HardeningConfig(
            validate_on_startup=False, integrity_check_interval_seconds=600
        )
        updated = await mgr.update_config(new_config)
        assert updated.validate_on_startup is False
        assert updated.integrity_check_interval_seconds == 600

    @pytest.mark.asyncio
    async def test_default_recovery_config(self) -> None:
        mgr = DesktopHardeningManager()
        config = await mgr.get_recovery_config()
        assert config.enabled is True
        assert config.auto_recover is True
        assert config.max_retries == 3

    @pytest.mark.asyncio
    async def test_update_recovery_config(self) -> None:
        mgr = DesktopHardeningManager()
        new_config = RecoveryModeConfig(auto_recover=False, max_retries=5)
        updated = await mgr.update_recovery_config(new_config)
        assert updated.auto_recover is False
        assert updated.max_retries == 5

    @pytest.mark.asyncio
    async def test_validate_startup(self) -> None:
        mgr = DesktopHardeningManager()
        result = await mgr.validate_startup()
        assert result.success is True
        assert len(result.checks) > 0
        assert result.duration_seconds >= 0

    @pytest.mark.asyncio
    async def test_get_last_startup_validation(self) -> None:
        mgr = DesktopHardeningManager()
        assert await mgr.get_last_startup_validation() is None
        await mgr.validate_startup()
        assert await mgr.get_last_startup_validation() is not None

    @pytest.mark.asyncio
    async def test_check_integrity(self) -> None:
        mgr = DesktopHardeningManager()
        result = await mgr.check_integrity()
        assert result.status in (IntegrityStatus.HEALTHY, IntegrityStatus.DEGRADED)
        assert len(result.checks) > 0
        assert result.duration_seconds >= 0

    @pytest.mark.asyncio
    async def test_get_last_integrity_check(self) -> None:
        mgr = DesktopHardeningManager()
        assert await mgr.get_last_integrity_check() is None
        await mgr.check_integrity()
        assert await mgr.get_last_integrity_check() is not None

    @pytest.mark.asyncio
    async def test_run_self_diagnostics(self) -> None:
        mgr = DesktopHardeningManager()
        report = await mgr.run_self_diagnostics()
        assert len(report.services) >= 1
        assert len(report.recommendations) >= 1

    @pytest.mark.asyncio
    async def test_memory_leak_detection(self) -> None:
        mgr = DesktopHardeningManager()
        report = await mgr.check_memory_leaks()
        assert report.detected is False
        assert report.detected_at is not None

    @pytest.mark.asyncio
    async def test_get_last_memory_report(self) -> None:
        mgr = DesktopHardeningManager()
        assert await mgr.get_last_memory_report() is None
        await mgr.check_memory_leaks()
        assert await mgr.get_last_memory_report() is not None

    @pytest.mark.asyncio
    async def test_monitor_threads(self) -> None:
        mgr = DesktopHardeningManager()
        report = await mgr.monitor_threads()
        assert report.total_threads >= 1
        assert report.active_threads >= 1
        assert report.sampled_at is not None

    @pytest.mark.asyncio
    async def test_get_last_thread_report(self) -> None:
        mgr = DesktopHardeningManager()
        assert await mgr.get_last_thread_report() is None
        await mgr.monitor_threads()
        assert await mgr.get_last_thread_report() is not None

    @pytest.mark.asyncio
    async def test_cleanup_resources(self) -> None:
        mgr = DesktopHardeningManager()
        result = await mgr.cleanup_resources()
        assert result.success is True
        assert result.duration_seconds >= 0

    @pytest.mark.asyncio
    async def test_get_cleanup_history(self) -> None:
        mgr = DesktopHardeningManager()
        history = await mgr.get_cleanup_history()
        assert len(history) == 0
        await mgr.cleanup_resources()
        history = await mgr.get_cleanup_history()
        assert len(history) == 1

    @pytest.mark.asyncio
    async def test_repair_all(self) -> None:
        mgr = DesktopHardeningManager()
        result = await mgr.repair()
        assert len(result.actions) >= 1

    @pytest.mark.asyncio
    async def test_repair_specific(self) -> None:
        mgr = DesktopHardeningManager()
        result = await mgr.repair(["workspace"])
        assert len(result.actions) == 1
        assert result.actions[0].target == "workspace"

    @pytest.mark.asyncio
    async def test_repair_unknown(self) -> None:
        mgr = DesktopHardeningManager()
        result = await mgr.repair(["nonexistent"])
        assert result.actions[0].status == "skipped"

    @pytest.mark.asyncio
    async def test_recovery_mode(self) -> None:
        mgr = DesktopHardeningManager()
        assert await mgr.is_in_recovery() is False
        assert await mgr.enter_recovery_mode() is True
        assert await mgr.is_in_recovery() is True
        assert await mgr.enter_recovery_mode() is False  # Already in recovery
        assert await mgr.exit_recovery_mode() is True
        assert await mgr.is_in_recovery() is False
        assert await mgr.exit_recovery_mode() is False  # Already exited

    @pytest.mark.asyncio
    async def test_recover(self) -> None:
        mgr = DesktopHardeningManager()
        await mgr.recover()
        assert mgr._in_recovery is False

    @pytest.mark.asyncio
    async def test_get_resource_usage(self) -> None:
        mgr = DesktopHardeningManager()
        usage = await mgr.get_resource_usage()
        assert usage.thread_count >= 1
        assert usage.sampled_at is not None

    @pytest.mark.asyncio
    async def test_plan_shutdown(self) -> None:
        mgr = DesktopHardeningManager()
        plan = await mgr.plan_shutdown()
        assert plan.timeout_seconds == 30
        assert len(plan.steps) >= 1

    @pytest.mark.asyncio
    async def test_plan_shutdown_force(self) -> None:
        mgr = DesktopHardeningManager()
        plan = await mgr.plan_shutdown(force=True)
        assert plan.force is True

    @pytest.mark.asyncio
    async def test_get_shutdown_plan(self) -> None:
        mgr = DesktopHardeningManager()
        assert await mgr.get_shutdown_plan() is None
        await mgr.plan_shutdown()
        assert await mgr.get_shutdown_plan() is not None

    @pytest.mark.asyncio
    async def test_get_recovery_history(self) -> None:
        mgr = DesktopHardeningManager()
        history = await mgr.get_recovery_history()
        assert isinstance(history, list)

    @pytest.mark.asyncio
    async def test_get_repair_history(self) -> None:
        mgr = DesktopHardeningManager()
        history = await mgr.get_repair_history()
        assert isinstance(history, list)

    @pytest.mark.asyncio
    async def test_hardening_config_to_dict(self) -> None:
        config = HardeningConfig()
        d = config.to_dict()
        assert d["validate_on_startup"] is True
        assert d["memory_leak_threshold_mb"] == 50

    @pytest.mark.asyncio
    async def test_recovery_config_to_dict(self) -> None:
        config = RecoveryModeConfig()
        d = config.to_dict()
        assert d["auto_recover"] is True
        assert d["max_retries"] == 3
