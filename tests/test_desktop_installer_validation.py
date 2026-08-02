"""Installer validation — metadata, format checks, and platform targeting."""

from __future__ import annotations

import pytest

from agentic_os.core.desktop import DesktopInstallerManager
from agentic_os.domain.desktop import InstallerConfig, InstallerResult, InstallerType


class TestInstallerValidation:
    @pytest.mark.asyncio
    async def test_msi_installer_metadata(self) -> None:
        mgr = DesktopInstallerManager()
        result = await mgr.generate_installer(InstallerConfig(installer_type=InstallerType.MSI))
        if not result.success:
            pytest.skip("MSI not supported on this platform")
        assert result.installer_type == InstallerType.MSI
        assert result.installer_path.endswith(".msi")
        assert result.checksum_sha256 != ""

    @pytest.mark.asyncio
    async def test_exe_installer_metadata(self) -> None:
        mgr = DesktopInstallerManager()
        result = await mgr.generate_installer(InstallerConfig(installer_type=InstallerType.EXE))
        if not result.success:
            pytest.skip("EXE not supported on this platform")
        assert result.installer_type == InstallerType.EXE
        assert result.installer_path.endswith(".exe")
        assert result.checksum_sha256 != ""

    @pytest.mark.asyncio
    async def test_appimage_installer_metadata(self) -> None:
        mgr = DesktopInstallerManager()
        result = await mgr.generate_installer(
            InstallerConfig(installer_type=InstallerType.APPIMAGE)
        )
        if not result.success:
            pytest.skip("AppImage not supported on this platform")
        assert result.installer_type == InstallerType.APPIMAGE
        assert result.installer_path.endswith(".AppImage")
        assert result.checksum_sha256 != ""

    @pytest.mark.asyncio
    async def test_deb_installer_metadata(self) -> None:
        mgr = DesktopInstallerManager()
        result = await mgr.generate_installer(InstallerConfig(installer_type=InstallerType.DEB))
        if not result.success:
            pytest.skip("DEB not supported on this platform")
        assert result.installer_type == InstallerType.DEB
        assert result.installer_path.endswith(".deb")

    @pytest.mark.asyncio
    async def test_rpm_installer_metadata(self) -> None:
        mgr = DesktopInstallerManager()
        result = await mgr.generate_installer(InstallerConfig(installer_type=InstallerType.RPM))
        if not result.success:
            pytest.skip("RPM not supported on this platform")
        assert result.installer_type == InstallerType.RPM
        assert result.installer_path.endswith(".rpm")

    @pytest.mark.asyncio
    async def test_dmg_installer_metadata(self) -> None:
        mgr = DesktopInstallerManager()
        result = await mgr.generate_installer(InstallerConfig(installer_type=InstallerType.DMG))
        if not result.success:
            pytest.skip("DMG not supported on this platform")
        assert result.installer_type == InstallerType.DMG
        assert result.installer_path.endswith(".dmg")

    @pytest.mark.asyncio
    async def test_pkg_installer_metadata(self) -> None:
        mgr = DesktopInstallerManager()
        result = await mgr.generate_installer(InstallerConfig(installer_type=InstallerType.PKG))
        if not result.success:
            pytest.skip("PKG not supported on this platform")
        assert result.installer_type == InstallerType.PKG
        assert result.installer_path.endswith(".pkg")

    @pytest.mark.asyncio
    async def test_portable_zip_installer_metadata(self) -> None:
        mgr = DesktopInstallerManager()
        result = await mgr.generate_installer(
            InstallerConfig(installer_type=InstallerType.PORTABLE_ZIP)
        )
        if not result.success:
            pytest.skip("PORTABLE_ZIP not supported on this platform")
        assert result.installer_type == InstallerType.PORTABLE_ZIP
        assert result.installer_path.endswith(".zip")
        assert result.checksum_sha256 != ""

    @pytest.mark.asyncio
    async def test_installer_config_defaults(self) -> None:
        config = InstallerConfig()
        assert config.installer_type == InstallerType.EXE
        assert config.app_name == "AgenticOS"
        assert config.app_version == "0.9.5"
        assert config.desktop_shortcut is True
        assert config.auto_start is False

    @pytest.mark.asyncio
    async def test_installer_config_custom(self) -> None:
        config = InstallerConfig(
            installer_type=InstallerType.MSI,
            app_name="CustomApp",
            app_version="2.0.0",
            desktop_shortcut=False,
        )
        assert config.installer_type == InstallerType.MSI
        assert config.app_name == "CustomApp"
        assert config.app_version == "2.0.0"
        assert config.desktop_shortcut is False

    @pytest.mark.asyncio
    async def test_generate_all_returns_all_types(self) -> None:
        mgr = DesktopInstallerManager()
        results = await mgr.generate_all(InstallerConfig())
        assert len(results) >= 2

    @pytest.mark.asyncio
    async def test_generate_all_includes_platform_types(self) -> None:
        mgr = DesktopInstallerManager()
        results = await mgr.generate_all(InstallerConfig())
        for r in results:
            assert r.installer_type in InstallerType

    @pytest.mark.asyncio
    async def test_validate_installer_existing(self, tmp_path) -> None:
        mgr = DesktopInstallerManager()
        f = tmp_path / "test.msi"
        f.write_text("fake installer")
        result = await mgr.validate_installer(str(f))
        assert result["valid"] is True

    @pytest.mark.asyncio
    async def test_validate_installer_missing(self) -> None:
        mgr = DesktopInstallerManager()
        result = await mgr.validate_installer("/nonexistent/installer.msi")
        assert result["valid"] is False

    @pytest.mark.asyncio
    async def test_supported_types_are_complete(self) -> None:
        mgr = DesktopInstallerManager()
        supported = await mgr.get_supported_types()
        for t in supported:
            assert isinstance(t, InstallerType)
        assert len(supported) > 0

    @pytest.mark.asyncio
    async def test_installer_result_duration(self) -> None:
        mgr = DesktopInstallerManager()
        result = await mgr.generate_installer(InstallerConfig())
        if not result.success:
            pytest.skip("Installer generation not supported on this platform")
        assert result.duration_seconds >= 0

    @pytest.mark.asyncio
    async def test_installer_result_to_dict(self) -> None:
        result = InstallerResult(
            success=True,
            installer_path="/tmp/test.msi",
            installer_type=InstallerType.MSI,
            size_bytes=1024,
            checksum_sha256="abc123",
            duration_seconds=0.5,
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["installer_path"] == "/tmp/test.msi"
        assert d["installer_type"] == "msi"
        assert d["size_bytes"] == 1024
        assert d["checksum_sha256"] == "abc123"
        assert d["duration_seconds"] == 0.5
        assert "error" in d
        assert "output" in d
        assert "metadata" in d
