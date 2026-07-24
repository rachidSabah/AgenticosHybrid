"""Tests for AutoUpdateManager refactoring — Phase 11 comprehensive update test suite."""

import asyncio
import hashlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agentic_os.core.desktop.update import (
    AutoUpdateManager,
    DownloadProgress,
    RepositoryConfig,
    Version,
    discover_current_version,
)
from agentic_os.domain.desktop import (
    InstallerType,
    UpdateChannel,
    UpdateManifest,
    UpdateStatus,
)


class TestRepositoryConfig:
    def test_default_repository_config(self) -> None:
        config = RepositoryConfig()
        assert config.repository_owner == "rachidSabah"
        assert config.repository_name == "AgenticosHybrid"
        assert config.full_name == "rachidSabah/AgenticosHybrid"
        assert (
            config.release_api
            == "https://api.github.com/repos/rachidSabah/AgenticosHybrid/releases"
        )
        assert (
            config.latest_release_api
            == "https://api.github.com/repos/rachidSabah/AgenticosHybrid/releases/latest"
        )
        assert config.release_page == "https://github.com/rachidSabah/AgenticosHybrid/releases"
        assert (
            config.latest_release_url
            == "https://github.com/rachidSabah/AgenticosHybrid/releases/latest"
        )
        assert (
            config.raw_content_url
            == "https://raw.githubusercontent.com/rachidSabah/AgenticosHybrid/main"
        )
        assert config.issues_url == "https://github.com/rachidSabah/AgenticosHybrid/issues"
        assert config.actions_url == "https://github.com/rachidSabah/AgenticosHybrid/actions"

    def test_custom_repository_config_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GITHUB_OWNER", "testowner")
        monkeypatch.setenv("GITHUB_REPOSITORY", "testrepo")
        config = RepositoryConfig()
        assert config.full_name == "testowner/testrepo"
        assert config.release_api == "https://api.github.com/repos/testowner/testrepo/releases"


class TestSemanticVersion:
    def test_version_parsing(self) -> None:
        v1 = Version("1.0.9")
        assert v1.major == 1 and v1.minor == 0 and v1.patch == 9
        assert not v1.is_prerelease
        assert v1.channel == UpdateChannel.STABLE

        v2 = Version("v2.0.0-beta.1")
        assert v2.major == 2 and v2.minor == 0 and v2.patch == 0
        assert v2.is_prerelease
        assert v2.channel == UpdateChannel.BETA

        v3 = Version("1.0.0-rc1")
        assert v3.is_prerelease
        assert v3.channel == UpdateChannel.BETA

        v4 = Version("v1.0.0-nightly.20260724")
        assert v4.channel == UpdateChannel.NIGHTLY

    def test_version_comparison(self) -> None:
        assert Version("v1.0.9") < Version("v1.0.10")
        assert Version("1.0.10") < Version("1.1.0")
        assert Version("1.1.0-alpha") < Version("1.1.0-beta")
        assert Version("1.1.0-beta") < Version("1.1.0-rc1")
        assert Version("1.1.0-rc1") < Version("1.1.0")
        assert Version("1.0.0") == Version("v1.0.0")
        assert Version("2.0.0") > Version("1.9.9")


class TestVersionDiscovery:
    def test_discover_version_pyproject(self, tmp_path: Path) -> None:
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\nname = "test"\nversion = "2.1.0-test"\n')
        version = discover_current_version(tmp_path)
        assert version == "2.1.0-test"

    def test_discover_version_metadata(self, tmp_path: Path) -> None:
        meta = tmp_path / "installed_version.json"
        meta.write_text('{"version": "3.0.0"}')
        version = discover_current_version(tmp_path)
        assert version == "3.0.0"


class TestAutoUpdateManagerRefactored:
    @pytest.mark.asyncio
    async def test_initial_state(self) -> None:
        mgr = AutoUpdateManager()
        status = await mgr.get_update_status()
        assert status == UpdateStatus.IDLE
        version = await mgr.get_current_version()
        assert version is not None

    @pytest.mark.asyncio
    async def test_release_parsing_and_channel_filter(self) -> None:
        mgr = AutoUpdateManager()
        mock_data = [
            {
                "tag_name": "v1.0.0",
                "prerelease": False,
                "draft": False,
                "html_url": "https://github.com/rachidSabah/AgenticosHybrid/releases/tag/v1.0.0",
                "published_at": "2026-07-01T12:00:00Z",
                "body": "Stable release",
                "assets": [
                    {
                        "name": "setup.exe",
                        "browser_download_url": "https://example.com/setup.exe",
                        "size": 1000,
                    }
                ],
            },
            {
                "tag_name": "v1.1.0-beta.1",
                "prerelease": True,
                "draft": False,
                "html_url": "https://github.com/rachidSabah/AgenticosHybrid/releases/tag/v1.1.0-beta.1",
                "published_at": "2026-07-15T12:00:00Z",
                "body": "Beta release",
                "assets": [],
            },
        ]

        with patch.object(mgr, "_fetch_json", return_value=mock_data):
            stable_releases = await mgr.check_for_updates(UpdateChannel.STABLE)
            assert len(stable_releases) == 1
            assert stable_releases[0].version == "1.0.0"

            beta_releases = await mgr.check_for_updates(UpdateChannel.BETA)
            assert len(beta_releases) == 2

    @pytest.mark.asyncio
    async def test_asset_selection(self) -> None:
        mgr = AutoUpdateManager()
        assets = [
            {
                "name": "AgenticOS-Setup-x64.exe",
                "browser_download_url": "https://example.com/setup.exe",
                "size": 100,
            },
            {
                "name": "AgenticOS-x86_64.AppImage",
                "browser_download_url": "https://example.com/app.AppImage",
                "size": 100,
            },
            {
                "name": "AgenticOS-x64.dmg",
                "browser_download_url": "https://example.com/app.dmg",
                "size": 100,
            },
        ]

        win_asset = mgr.select_best_asset(assets, target_os="win32")
        assert win_asset is not None and win_asset["name"] == "AgenticOS-Setup-x64.exe"

        linux_asset = mgr.select_best_asset(assets, target_os="linux")
        assert linux_asset is not None and linux_asset["name"] == "AgenticOS-x86_64.AppImage"

        mac_asset = mgr.select_best_asset(assets, target_os="darwin")
        assert mac_asset is not None and mac_asset["name"] == "AgenticOS-x64.dmg"

    @pytest.mark.asyncio
    async def test_streamed_download_checksum_and_install(self, tmp_path: Path) -> None:
        mgr = AutoUpdateManager()
        mgr._cache_dir = tmp_path

        test_data = b"dummy update binary payload"
        sha256_hash = hashlib.sha256(test_data).hexdigest()

        def mock_stream(url: str, dest: Path, cb: None, cancel: asyncio.Event) -> bool:
            dest.write_bytes(test_data)
            if cb:
                cb(
                    DownloadProgress(
                        total_bytes=len(test_data),
                        downloaded_bytes=len(test_data),
                        percent=100.0,
                    )
                )
            return True

        with patch.object(mgr, "_stream_download", side_effect=mock_stream):
            manifest = UpdateManifest(
                version="1.1.0",
                download_url="https://example.com/AgenticOS-Setup-x64.exe",
                checksum_sha256=sha256_hash,
                installer_type=InstallerType.EXE,
            )

            downloaded = await mgr.download_update(manifest)
            assert downloaded is True
            assert await mgr.get_update_status() == UpdateStatus.READY

            result = await mgr.install_update(manifest)
            assert result.success is True
            assert result.new_version == "1.1.0"
            assert await mgr.get_current_version() == "1.1.0"

    @pytest.mark.asyncio
    async def test_checksum_mismatch_failure(self, tmp_path: Path) -> None:
        mgr = AutoUpdateManager()
        mgr._cache_dir = tmp_path

        def mock_stream(url: str, dest: Path, cb: None, cancel: asyncio.Event) -> bool:
            dest.write_bytes(b"corrupted data")
            return True

        with patch.object(mgr, "_stream_download", side_effect=mock_stream):
            manifest = UpdateManifest(
                version="1.1.0",
                download_url="https://example.com/AgenticOS-Setup-x64.exe",
                checksum_sha256="wrong_checksum_123",
            )
            downloaded = await mgr.download_update(manifest)
            assert downloaded is False
            assert await mgr.get_update_status() == UpdateStatus.FAILED

    @pytest.mark.asyncio
    async def test_cancellation_and_skipped_versions(self) -> None:
        mgr = AutoUpdateManager()
        cancel_evt = asyncio.Event()
        cancel_evt.set()

        manifest = UpdateManifest(
            version="1.2.0",
            download_url="https://example.com/test.exe",
        )
        downloaded = await mgr.download_update(manifest, cancel_event=cancel_evt)
        assert downloaded is False

        await mgr.skip_version("1.3.0")
        assert "1.3.0" in mgr._skipped_versions

    @pytest.mark.asyncio
    async def test_rollback_detection(self) -> None:
        mgr = AutoUpdateManager()
        await mgr.set_current_version("2.0.0")

        manifest = UpdateManifest(
            version="1.5.0",
            download_url="https://example.com/old.exe",
        )
        result = await mgr.install_update(manifest)
        assert result.success is True
        assert result.rolled_back is True
        assert result.previous_version == "2.0.0"
        assert result.new_version == "1.5.0"

    @pytest.mark.asyncio
    async def test_validate_update_infrastructure(self) -> None:
        mgr = AutoUpdateManager()
        with patch.object(mgr, "check_for_updates", return_value=[]):
            with patch("urllib.request.urlopen") as mock_url:
                mock_resp = MagicMock()
                mock_resp.read.return_value = b'{"id": 123, "stargazers_count": 10}'
                mock_url.return_value.__enter__.return_value = mock_resp

                diag = await mgr.validate_update_infrastructure()
                assert diag["config_valid"] is True
                assert diag["version_comparison_valid"] is True
                assert diag["asset_selection_valid"] is True
