"""Tests for services.runtime_discovery.providers."""

from __future__ import annotations

import sys
from pathlib import Path

_services_path = str(Path(__file__).resolve().parent.parent / "services")
if _services_path not in sys.path:
    sys.path.insert(0, _services_path)

from unittest.mock import MagicMock, patch

import pytest
from services.runtime_discovery.models import DiscoveryProviderType, RuntimeType
from services.runtime_discovery.providers.config_file import ConfigFileProvider
from services.runtime_discovery.providers.env_var import EnvVarDiscoveryProvider
from services.runtime_discovery.providers.filesystem import FilesystemDiscoveryProvider
from services.runtime_discovery.providers.known_install_dirs import KnownInstallDirsProvider
from services.runtime_discovery.providers.path import PathDiscoveryProvider
from services.runtime_discovery.providers.vscode import VSCodeDiscoveryProvider


class TestPathDiscoveryProvider:
    @pytest.fixture
    def provider(self) -> PathDiscoveryProvider:
        return PathDiscoveryProvider()

    async def test_provider_type(self, provider: PathDiscoveryProvider) -> None:
        assert provider.provider_type == DiscoveryProviderType.PATH
        assert await provider.get_provider_type() == DiscoveryProviderType.PATH
        assert await provider.get_provider_name() == "path"

    @patch("shutil.which", return_value="/usr/bin/python3")
    @patch("subprocess.run")
    async def test_discover_python(
        self, mock_run, mock_which, provider: PathDiscoveryProvider
    ) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="Python 3.14.0\n", stderr="")
        results = await provider.discover(runtime_type=RuntimeType.PYTHON)
        assert len(results) >= 1
        python_results = [r for r in results if r.runtime_type == RuntimeType.PYTHON]
        assert len(python_results) >= 1
        assert python_results[0].found is True

    @patch("shutil.which", return_value=None)
    async def test_discover_none_found(self, mock_which, provider: PathDiscoveryProvider) -> None:
        results = await provider.discover()
        assert len(results) == 0

    @patch("shutil.which", return_value="/usr/bin/python3")
    @patch("subprocess.run")
    async def test_discover_all(
        self, mock_run, mock_which, provider: PathDiscoveryProvider
    ) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="Python 3.14.0\n", stderr="")
        results = await provider.discover_all()
        assert len(results) >= 1


class TestEnvVarDiscoveryProvider:
    @pytest.fixture
    def provider(self) -> EnvVarDiscoveryProvider:
        return EnvVarDiscoveryProvider()

    async def test_provider_type(self, provider: EnvVarDiscoveryProvider) -> None:
        assert provider.provider_type == DiscoveryProviderType.ENV_VAR
        assert await provider.get_provider_type() == DiscoveryProviderType.ENV_VAR
        assert await provider.get_provider_name() == "env_var"

    @patch.dict("os.environ", {"PYTHON_HOME": "/usr/local/python3"}, clear=True)
    async def test_discover_python(self, provider: EnvVarDiscoveryProvider) -> None:
        results = await provider.discover()
        python_results = [r for r in results if r.runtime_type == RuntimeType.PYTHON]
        assert len(python_results) == 1
        assert python_results[0].metadata["env_var"] == "PYTHON_HOME"

    @patch.dict("os.environ", {}, clear=True)
    async def test_discover_none(self, provider: EnvVarDiscoveryProvider) -> None:
        results = await provider.discover()
        assert len(results) == 0

    @patch.dict(
        "os.environ",
        {"PYTHON_HOME": "/usr/local/python3", "NODE_HOME": "/usr/local/node"},
        clear=True,
    )
    async def test_discover_multiple(self, provider: EnvVarDiscoveryProvider) -> None:
        results = await provider.discover()
        assert len(results) >= 1


class TestFilesystemDiscoveryProvider:
    @pytest.fixture
    def provider(self) -> FilesystemDiscoveryProvider:
        return FilesystemDiscoveryProvider()

    async def test_provider_type(self, provider: FilesystemDiscoveryProvider) -> None:
        assert provider.provider_type == DiscoveryProviderType.FILESYSTEM
        assert await provider.get_provider_type() == DiscoveryProviderType.FILESYSTEM

    @patch("os.path.exists", return_value=True)
    async def test_discover_all(self, mock_exists, provider: FilesystemDiscoveryProvider) -> None:
        results = await provider.discover()
        assert len(results) >= 1

    @patch("os.path.exists", return_value=False)
    async def test_discover_none(self, mock_exists, provider: FilesystemDiscoveryProvider) -> None:
        results = await provider.discover()
        assert len(results) == 0


class TestKnownInstallDirsProvider:
    @pytest.fixture
    def provider(self) -> KnownInstallDirsProvider:
        return KnownInstallDirsProvider()

    async def test_provider_type(self, provider: KnownInstallDirsProvider) -> None:
        assert provider.provider_type == DiscoveryProviderType.KNOWN_INSTALL_DIRS

    async def test_discover(self, provider: KnownInstallDirsProvider) -> None:
        results = await provider.discover()
        assert len(results) >= 0

    async def test_discover_by_type(self, provider: KnownInstallDirsProvider) -> None:
        results = await provider.discover(runtime_type=RuntimeType.DOCKER)
        assert len(results) >= 0


class TestConfigFileProvider:
    @pytest.fixture
    def provider(self) -> ConfigFileProvider:
        return ConfigFileProvider()

    async def test_provider_type(self, provider: ConfigFileProvider) -> None:
        assert provider.provider_type == DiscoveryProviderType.CONFIG_FILE

    async def test_discover_none(self, provider: ConfigFileProvider) -> None:
        results = await provider.discover()
        assert len(results) == 0

    async def test_get_provider_name(self, provider: ConfigFileProvider) -> None:
        assert await provider.get_provider_name() == "config_file"


class TestVSCodeDiscoveryProvider:
    @pytest.fixture
    def provider(self) -> VSCodeDiscoveryProvider:
        return VSCodeDiscoveryProvider()

    async def test_provider_type(self, provider: VSCodeDiscoveryProvider) -> None:
        assert provider.provider_type == DiscoveryProviderType.VSCODE

    async def test_discover_none(self, provider: VSCodeDiscoveryProvider) -> None:
        results = await provider.discover()
        assert len(results) == 0

    async def test_get_provider_name(self, provider: VSCodeDiscoveryProvider) -> None:
        assert await provider.get_provider_name() == "vscode"
