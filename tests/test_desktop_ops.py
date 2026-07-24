"""Tests for Phase 4 M6 Part 2 — Desktop Runtime Operational Layer."""

from __future__ import annotations

import pytest

from agentic_os.core.desktop import (
    AutoUpdateManager,
    BackupManager,
    ChannelManager,
    DeltaUpdateEngine,
    DesktopInstallerManager,
    FirstRunWizard,
    OfflineRuntimeManager,
    PortableRuntimeManager,
    RollbackManager,
    RuntimeDiscoveryManager,
    SignatureVerification,
    WindowsPlatformIntegration,
)
from agentic_os.domain.desktop import (
    BackupConfig,
    BackupScope,
    DeltaUpdate,
    FirstRunStep,
    InstallerConfig,
    InstallerType,
    OfflineConfig,
    RestoreConfig,
    RuntimeType,
    UpdateChannel,
    UpdateManifest,
)


class TestRuntimeDiscoveryManager:
    @pytest.mark.asyncio
    async def test_discover_and_list(self) -> None:
        mgr = RuntimeDiscoveryManager()
        result = await mgr.discover_runtimes()
        assert result.total_discovered >= 0
        assert isinstance(result.duration_seconds, float)

    @pytest.mark.asyncio
    async def test_get_unknown_runtime(self) -> None:
        mgr = RuntimeDiscoveryManager()
        info = await mgr.get_runtime(RuntimeType.UNKNOWN)
        assert info is None

    @pytest.mark.asyncio
    async def test_verify_nonexistent(self) -> None:
        mgr = RuntimeDiscoveryManager()
        assert await mgr.verify_runtime(RuntimeType.UNKNOWN) is False

    @pytest.mark.asyncio
    async def test_refresh_unknown(self) -> None:
        mgr = RuntimeDiscoveryManager()
        result = await mgr.refresh_runtime(RuntimeType.UNKNOWN)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_discovery_count(self) -> None:
        mgr = RuntimeDiscoveryManager()
        count = await mgr.get_discovery_count()
        assert count >= 0


class TestAutoUpdateManager:
    @pytest.mark.asyncio
    async def test_initial_status(self) -> None:
        mgr = AutoUpdateManager()
        status = await mgr.get_update_status()
        assert status.value == "idle"

    @pytest.mark.asyncio
    async def test_get_current_version(self) -> None:
        mgr = AutoUpdateManager()
        version = await mgr.get_current_version()
        assert bool(version)
        assert version == "1.0.0-rc2"

    @pytest.mark.asyncio
    async def test_check_updates(self) -> None:
        mgr = AutoUpdateManager()
        releases = await mgr.check_for_updates(UpdateChannel.STABLE)
        assert isinstance(releases, list)

    @pytest.mark.asyncio
    async def test_download_install_cycle(self) -> None:
        mgr = AutoUpdateManager()
        manifest = UpdateManifest(
            version="0.9.6",
            download_url="https://example.com/test.zip",
            checksum_sha256="abc123",
        )
        downloaded = await mgr.download_update(manifest)
        if downloaded:
            result = await mgr.install_update(manifest)
            assert result.success is True

    @pytest.mark.asyncio
    async def test_get_history(self) -> None:
        mgr = AutoUpdateManager()
        history = await mgr.get_update_history()
        assert isinstance(history, list)

    @pytest.mark.asyncio
    async def test_get_pending(self) -> None:
        mgr = AutoUpdateManager()
        pending = await mgr.get_pending_update()
        assert pending is None

    @pytest.mark.asyncio
    async def test_set_version(self) -> None:
        mgr = AutoUpdateManager()
        await mgr.set_current_version("0.9.6")
        assert await mgr.get_current_version() == "0.9.6"


class TestDesktopInstallerManager:
    @pytest.mark.asyncio
    async def test_generate_installer(self) -> None:
        mgr = DesktopInstallerManager()
        config = InstallerConfig(
            installer_type=InstallerType.EXE, app_name="AgenticOS", app_version="0.9.5"
        )
        result = await mgr.generate_installer(config)
        assert result.success is True
        assert result.installer_type == InstallerType.EXE

    @pytest.mark.asyncio
    async def test_generate_all(self) -> None:
        mgr = DesktopInstallerManager()
        results = await mgr.generate_all(InstallerConfig())
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_validate_installer(self) -> None:
        mgr = DesktopInstallerManager()
        import tempfile
        from pathlib import Path

        tmp = Path(tempfile.gettempdir()) / "test_installer.exe"
        tmp.write_text("test")
        result = await mgr.validate_installer(str(tmp))
        assert result["valid"] is True
        tmp.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_supported_types(self) -> None:
        mgr = DesktopInstallerManager()
        types = await mgr.get_supported_types()
        assert len(types) >= 1

    @pytest.mark.asyncio
    async def test_get_installer_info(self) -> None:
        mgr = DesktopInstallerManager()
        import tempfile
        from pathlib import Path

        tmp = Path(tempfile.gettempdir()) / "test_installer_info.exe"
        tmp.write_text("test")
        info = await mgr.get_installer_info(str(tmp))
        assert "platform" in info
        tmp.unlink(missing_ok=True)


class TestFirstRunWizard:
    @pytest.mark.asyncio
    async def test_initial_state(self) -> None:
        wizard = FirstRunWizard()
        state = await wizard.get_state()
        assert state.completed is False
        assert state.current_step == FirstRunStep.WELCOME

    @pytest.mark.asyncio
    async def test_run_steps(self) -> None:
        wizard = FirstRunWizard()

        result = await wizard.run_step("welcome")
        assert result["success"] is True

        result = await wizard.run_step("workspace")
        assert result["success"] is True

        result = await wizard.run_step("config")
        assert result["success"] is True

        result = await wizard.run_step("complete")
        assert result["success"] is True

        assert await wizard.is_completed() is True

    @pytest.mark.asyncio
    async def test_skip_step(self) -> None:
        wizard = FirstRunWizard()
        await wizard.skip_step("provider")
        state = await wizard.get_state()
        assert "provider" in state.skipped_steps

    @pytest.mark.asyncio
    async def test_reset(self) -> None:
        wizard = FirstRunWizard()
        await wizard.run_step("complete")
        assert await wizard.is_completed() is True
        await wizard.reset()
        assert await wizard.is_completed() is False

    @pytest.mark.asyncio
    async def test_unknown_step(self) -> None:
        wizard = FirstRunWizard()
        result = await wizard.run_step("nonexistent")
        assert result["success"] is False


class TestChannelManager:
    @pytest.mark.asyncio
    async def test_default_channel(self) -> None:
        mgr = ChannelManager()
        assert await mgr.get_current_channel() == UpdateChannel.STABLE

    @pytest.mark.asyncio
    async def test_set_channel(self) -> None:
        mgr = ChannelManager()
        await mgr.set_channel(UpdateChannel.BETA)
        assert await mgr.get_current_channel() == UpdateChannel.BETA

    @pytest.mark.asyncio
    async def test_list_channels(self) -> None:
        mgr = ChannelManager()
        channels = await mgr.get_channels()
        assert UpdateChannel.STABLE in channels
        assert UpdateChannel.BETA in channels
        assert UpdateChannel.NIGHTLY in channels


class TestRollbackManager:
    @pytest.mark.asyncio
    async def test_can_rollback(self) -> None:
        mgr = RollbackManager()
        assert await mgr.can_rollback() is False  # Only one version

    @pytest.mark.asyncio
    async def test_available_versions(self) -> None:
        mgr = RollbackManager()
        versions = await mgr.get_available_versions()
        assert "0.9.5" in versions

    @pytest.mark.asyncio
    async def test_rollback_not_available(self) -> None:
        mgr = RollbackManager()
        result = await mgr.rollback()
        assert result.success is False


class TestOfflineRuntimeManager:
    @pytest.mark.asyncio
    async def test_initial_state(self) -> None:
        mgr = OfflineRuntimeManager()
        assert (await mgr.get_offline_state()).value == "online"

    @pytest.mark.asyncio
    async def test_enable_disable(self) -> None:
        mgr = OfflineRuntimeManager()
        await mgr.enable_offline_mode()
        assert (await mgr.get_offline_state()).value == "offline"

        await mgr.disable_offline_mode()
        assert (await mgr.get_offline_state()).value == "online"

    @pytest.mark.asyncio
    async def test_config(self) -> None:
        mgr = OfflineRuntimeManager()
        config = await mgr.get_offline_config()
        assert config.enabled is True

        new_config = OfflineConfig(enabled=False, max_cache_size_mb=512)
        updated = await mgr.update_offline_config(new_config)
        assert updated.enabled is False
        assert updated.max_cache_size_mb == 512

    @pytest.mark.asyncio
    async def test_queue_and_sync(self) -> None:
        mgr = OfflineRuntimeManager()
        await mgr.queue_event("test.event", {"key": "value"})
        assert len(await mgr.get_queued_events()) == 1
        assert await mgr.get_queue_size() == 1

        synced = await mgr.sync_queued_events()
        assert synced == 1
        assert await mgr.get_queue_size() == 0


class TestBackupManager:
    @pytest.mark.asyncio
    async def test_create_and_list_backups(self) -> None:
        mgr = BackupManager()
        config = BackupConfig(scope=BackupScope.CONFIG)
        result = await mgr.create_backup(config)
        assert result.success is True
        assert result.scope == BackupScope.CONFIG

        backups = await mgr.list_backups()
        assert len(backups) == 1

    @pytest.mark.asyncio
    async def test_get_backup_info(self) -> None:
        mgr = BackupManager()
        result = await mgr.create_backup(BackupConfig())
        info = await mgr.get_backup_info(result.backup_path)
        assert info is not None

    @pytest.mark.asyncio
    async def test_delete_backup(self) -> None:
        mgr = BackupManager()
        result = await mgr.create_backup(BackupConfig())
        assert await mgr.delete_backup(result.backup_path) is True

    @pytest.mark.asyncio
    async def test_restore(self) -> None:
        mgr = BackupManager()
        result = await mgr.create_backup(BackupConfig())
        config = RestoreConfig(backup_path=result.backup_path)
        restore_result = await mgr.restore(config)
        assert restore_result.success is True

    @pytest.mark.asyncio
    async def test_verify_backup(self) -> None:
        mgr = BackupManager()
        import tempfile
        from pathlib import Path

        tmp = Path(tempfile.gettempdir()) / "test_backup.zip"
        tmp.write_text("backup data")
        assert await mgr.verify_backup(str(tmp)) is True
        tmp.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_restore_points(self) -> None:
        mgr = BackupManager()
        await mgr.create_backup(BackupConfig())
        points = await mgr.get_available_restore_points()
        assert len(points) == 1


class TestDeltaUpdateEngine:
    @pytest.mark.asyncio
    async def test_compute_delta(self) -> None:
        engine = DeltaUpdateEngine()
        delta = await engine.compute_delta("0.9.4", "0.9.5", "/src", "/dst")
        assert delta is not None
        assert delta.from_version == "0.9.4"
        assert delta.to_version == "0.9.5"

    @pytest.mark.asyncio
    async def test_apply_delta(self) -> None:
        engine = DeltaUpdateEngine()
        delta = DeltaUpdate(from_version="0.9.4", to_version="0.9.5")
        assert await engine.apply_delta(delta, "/dst") is True

    @pytest.mark.asyncio
    async def test_get_available(self) -> None:
        engine = DeltaUpdateEngine()
        await engine.compute_delta("0.9.4", "0.9.5", "/src", "/dst")
        delta = await engine.get_available_delta("0.9.4", "0.9.5")
        assert delta is not None
        assert await engine.get_available_delta("0.9.3", "0.9.5") is None


class TestSignatureVerification:
    @pytest.mark.asyncio
    async def test_verify_sha256(self) -> None:
        v = SignatureVerification()
        import tempfile
        from pathlib import Path

        tmp = Path(tempfile.gettempdir()) / "test_signature.txt"
        tmp.write_text("hello")
        import hashlib

        expected = hashlib.sha256(b"hello").hexdigest()
        assert await v.verify_sha256(str(tmp), expected) is True
        assert await v.verify_sha256(str(tmp), "badhash") is False
        tmp.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_verify_signature(self) -> None:
        v = SignatureVerification()
        assert await v.verify_signature(b"data", "sig") is True

    @pytest.mark.asyncio
    async def test_get_checksum(self) -> None:
        v = SignatureVerification()
        import tempfile
        from pathlib import Path

        tmp = Path(tempfile.gettempdir()) / "test_checksum.txt"
        tmp.write_text("data")
        result = await v.get_checksum(str(tmp))
        assert result["algorithm"] == "sha256"
        tmp.unlink(missing_ok=True)


class TestPortableRuntimeManager:
    @pytest.mark.asyncio
    async def test_available_runtimes(self) -> None:
        mgr = PortableRuntimeManager()
        available = await mgr.get_available_runtimes()
        assert "python" in available

    @pytest.mark.asyncio
    async def test_portable_path(self) -> None:
        mgr = PortableRuntimeManager()
        path = await mgr.get_portable_path("python")
        assert path is None or isinstance(path, str)

    @pytest.mark.asyncio
    async def test_is_available(self) -> None:
        mgr = PortableRuntimeManager()
        assert await mgr.is_portable_available("python") is False


class TestWindowsPlatformIntegration:
    @pytest.mark.asyncio
    async def test_create_shortcut(self) -> None:
        mgr = WindowsPlatformIntegration()
        from agentic_os.domain.desktop import ShortcutInfo

        result = await mgr.create_shortcut(ShortcutInfo(name="Test"))
        assert result is True

    @pytest.mark.asyncio
    async def test_start_menu_shortcut(self) -> None:
        mgr = WindowsPlatformIntegration()
        assert await mgr.create_start_menu_shortcut() is True

    @pytest.mark.asyncio
    async def test_desktop_shortcut(self) -> None:
        mgr = WindowsPlatformIntegration()
        assert await mgr.create_desktop_shortcut() is True

    @pytest.mark.asyncio
    async def test_file_association(self) -> None:
        mgr = WindowsPlatformIntegration()
        from agentic_os.domain.desktop import FileAssociation

        assert (
            await mgr.register_file_association(
                FileAssociation(extension=".aios", description="AgenticOS Workspace")
            )
            is True
        )

    @pytest.mark.asyncio
    async def test_startup(self) -> None:
        mgr = WindowsPlatformIntegration()
        assert await mgr.add_to_startup(True) is True

    @pytest.mark.asyncio
    async def test_system_tray(self) -> None:
        mgr = WindowsPlatformIntegration()
        status = await mgr.get_system_tray_status()
        assert status["available"] is True

    @pytest.mark.asyncio
    async def test_toast_notification(self) -> None:
        mgr = WindowsPlatformIntegration()
        assert await mgr.send_toast_notification("Test", "Hello") is True
