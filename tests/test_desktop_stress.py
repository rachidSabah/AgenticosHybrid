"""Stress tests for production hardening, runtime discovery, and installer subsystems."""

from __future__ import annotations

import asyncio
import time

import pytest

from agentic_os.core.desktop import (
    DesktopHardeningManager,
    DesktopInstallerManager,
    RuntimeDiscoveryManager,
)
from agentic_os.domain.desktop import InstallerConfig, RuntimeType


class TestStressHardening:
    @pytest.mark.asyncio
    async def test_concurrent_validation(self) -> None:
        mgr = DesktopHardeningManager()
        results = await asyncio.gather(
            *[mgr.validate_startup() for _ in range(50)],
            *[mgr.check_integrity() for _ in range(50)],
        )
        assert len(results) == 100
        for r in results:
            assert r is not None

    @pytest.mark.asyncio
    async def test_concurrent_memory_checks(self) -> None:
        mgr = DesktopHardeningManager()
        results = await asyncio.gather(*[mgr.check_memory_leaks() for _ in range(50)])
        assert len(results) == 50

    @pytest.mark.asyncio
    async def test_concurrent_thread_monitoring(self) -> None:
        mgr = DesktopHardeningManager()
        results = await asyncio.gather(*[mgr.monitor_threads() for _ in range(50)])
        assert len(results) == 50

    @pytest.mark.asyncio
    async def test_repeated_cleanup(self) -> None:
        mgr = DesktopHardeningManager()
        for _ in range(20):
            result = await mgr.cleanup_resources()
            assert result.success is True

    @pytest.mark.asyncio
    async def test_repeated_repair(self) -> None:
        mgr = DesktopHardeningManager()
        targets_list = [
            ["workspace"],
            ["config"],
            ["cache"],
            ["database"],
            ["workspace", "config"],
            ["workspace", "config", "cache"],
            ["workspace", "config", "cache", "database"],
        ]
        for i in range(30):
            targets = targets_list[i % len(targets_list)]
            result = await mgr.repair(targets)
            assert result.success is True

    @pytest.mark.asyncio
    async def test_recovery_mode_toggle_stress(self) -> None:
        mgr = DesktopHardeningManager()
        for _ in range(50):
            assert await mgr.enter_recovery_mode() is True
            assert await mgr.exit_recovery_mode() is True

    @pytest.mark.asyncio
    async def test_high_frequency_diagnostics(self) -> None:
        mgr = DesktopHardeningManager()
        start = time.monotonic()
        for _ in range(200):
            await mgr.run_self_diagnostics()
        avg_ms = ((time.monotonic() - start) / 200) * 1000
        assert avg_ms < 100

    @pytest.mark.asyncio
    async def test_resource_usage_threshold(self) -> None:
        mgr = DesktopHardeningManager()
        for _ in range(50):
            usage = await mgr.get_resource_usage()
            assert usage.thread_count >= 1
            if usage.memory_mb > 0:
                assert usage.memory_mb < 2000


class TestStressRuntimeDiscovery:
    @pytest.mark.asyncio
    async def test_concurrent_discovery(self) -> None:
        mgr = RuntimeDiscoveryManager()
        from asyncio import wait_for

        results = await wait_for(
            asyncio.gather(*[mgr.discover_runtimes() for _ in range(20)]),
            timeout=15,
        )
        assert len(results) == 20

    @pytest.mark.asyncio
    async def test_get_runtime_concurrent(self) -> None:
        mgr = RuntimeDiscoveryManager()
        await mgr.discover_runtimes()
        runtimes = await mgr.get_discovered_runtimes()
        types = [r.runtime_type for r in runtimes]
        if types:
            results = await asyncio.gather(*[mgr.get_runtime(t) for t in types])
            assert len(results) == len(types)

    @pytest.mark.asyncio
    async def test_verify_runtime_stress(self) -> None:
        mgr = RuntimeDiscoveryManager()
        for rt in RuntimeType:
            for _ in range(50):
                await mgr.verify_runtime(rt)


class TestStressInstaller:
    @pytest.mark.asyncio
    async def test_generate_installer_stress(self) -> None:
        mgr = DesktopInstallerManager()
        supported = await mgr.get_supported_types()
        for installer_type in supported:
            for _ in range(10):
                result = await mgr.generate_installer(
                    InstallerConfig(installer_type=installer_type)
                )
                assert result.success is True

    @pytest.mark.asyncio
    async def test_validate_installer_concurrent(self) -> None:
        mgr = DesktopInstallerManager()
        supported = await mgr.get_supported_types()
        cfg = InstallerConfig(installer_type=supported[0])
        gen = await mgr.generate_installer(cfg)
        path = gen.installer_path
        outcomes = await asyncio.gather(*[mgr.validate_installer(path) for _ in range(100)])
        assert len(outcomes) == 100
        for o in outcomes:
            assert o["valid"] is True

    @pytest.mark.asyncio
    async def test_generate_all_stress(self) -> None:
        mgr = DesktopInstallerManager()
        for _ in range(20):
            results = await mgr.generate_all(InstallerConfig())
            assert len(results) >= 2
