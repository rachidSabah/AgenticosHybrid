"""Tests for all 10 discovery providers.

Tests cover empty results, executable discovery, error handling,
and proper EngineRegistration construction for each provider.
"""

import json
import os
import subprocess
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agentic_os.domain.execution import EngineCapability, EngineType
from agentic_os.ports.execution import EngineRegistration

# ============================================================================
# 1. PathDiscovery
# ============================================================================


class TestPathDiscovery:
    @pytest.fixture
    def provider(self):
        from agentic_os.adapters.discovery.path import PathDiscovery

        return PathDiscovery()

    @pytest.mark.asyncio
    async def test_get_provider_name(self, provider) -> None:
        assert provider.get_provider_name() == "path-discovery"

    @pytest.mark.asyncio
    async def test_get_provider_type(self, provider) -> None:
        assert provider.get_provider_type() == "path"

    @pytest.mark.asyncio
    async def test_discover_empty(self, provider) -> None:
        with patch.object(provider, "_which", return_value=None):
            results = await provider.discover()
            assert results == []

    @pytest.mark.asyncio
    async def test_discover_finds_python(self, provider) -> None:
        def which_side_effect(binary: str) -> str | None:
            if binary == "python3":
                return "/usr/bin/python3"
            return None

        with patch.object(provider, "_which", side_effect=which_side_effect):
            with patch.object(provider, "_get_version", return_value="3.10.0"):
                results = await provider.discover()
                assert len(results) >= 1
                assert any(r.name == "python-local" for r in results)
                py_reg = next(r for r in results if r.name == "python-local")
                assert py_reg.engine_type == EngineType.CUSTOM
                assert EngineCapability.CODING in py_reg.capabilities
                assert py_reg.version == "3.10.0"
                assert py_reg.transport == "local"

    @pytest.mark.asyncio
    async def test_discover_finds_claude(self, provider) -> None:
        def which_side_effect(binary: str) -> str | None:
            if binary == "claude":
                return "/usr/local/bin/claude"
            return None

        with patch.object(provider, "_which", side_effect=which_side_effect):
            with patch.object(provider, "_get_version", return_value="1.5.0"):
                results = await provider.discover()
                assert len(results) >= 1
                claude_reg = next(r for r in results if r.name == "claude-local")
                assert claude_reg.engine_type == EngineType.CLAUDE_CODE

    @pytest.mark.asyncio
    async def test_discover_platform_filter_wsl_on_linux(self, provider) -> None:
        # wsl.exe is Windows-only; on non-Windows it should be skipped
        def which_side_effect(binary: str) -> str | None:
            if binary == "python3":
                return "/usr/bin/python3"
            return None

        with (
            patch.object(provider, "_which", side_effect=which_side_effect),
            patch.object(provider, "_get_version", return_value="3.9"),
            patch("platform.system", return_value="Linux"),
        ):
            results = await provider.discover()
            # wsl.exe should be skipped on Linux
            assert not any("wsl" in r.name for r in results)

    @pytest.mark.asyncio
    async def test_discover_multiple_executables(self, provider) -> None:
        all_binaries = ["python3", "node", "docker", "claude"]

        def which_side_effect(binary: str) -> str | None:
            return f"/usr/bin/{binary}" if binary in all_binaries else None

        with patch.object(provider, "_which", side_effect=which_side_effect):
            with patch.object(provider, "_get_version", return_value="1.0"):
                results = await provider.discover()
                assert len(results) >= 4

    @pytest.mark.asyncio
    async def test_get_version_timeout(self, provider) -> None:
        with patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="test", timeout=5),
        ):
            version = await provider._get_version("/usr/bin/python3", "--version")
            assert version is None

    @pytest.mark.asyncio
    async def test_get_version_os_error(self, provider) -> None:
        with patch("subprocess.run", side_effect=OSError("not found")):
            version = await provider._get_version("/usr/bin/python3", "--version")
            assert version is None

    @pytest.mark.asyncio
    async def test_which_checks_path(self, provider) -> None:
        with (
            patch("os.path.isfile", return_value=True),
            patch("os.access", return_value=True),
            patch.dict(os.environ, {"PATH": "/custom/bin"}, clear=True),
        ):
            result = provider._which("tool")
            assert result is not None
            assert "tool" in result

    @pytest.mark.asyncio
    async def test_which_returns_none_when_not_found(self, provider) -> None:
        with (
            patch("os.path.isfile", return_value=False),
            patch.dict(os.environ, {"PATH": ""}, clear=True),
        ):
            result = provider._which("nonexistent-tool")
            assert result is None

    @pytest.mark.asyncio
    async def test_build_description_with_version(self, provider) -> None:
        desc = provider._build_description({"name": "claude", "binary": "claude"}, "2.0")
        assert "Claude v2.0" in desc
        assert "PATH" in desc

    @pytest.mark.asyncio
    async def test_build_description_without_version(self, provider) -> None:
        desc = provider._build_description({"name": "aider", "binary": "aider"}, None)
        assert "Aider" in desc
        assert "PATH" in desc


# ============================================================================
# 2. WindowsRegistryDiscovery
# ============================================================================


class TestWindowsRegistryDiscovery:
    @pytest.fixture
    def provider(self):
        from agentic_os.adapters.discovery.registry_provider import (
            WindowsRegistryDiscovery,
        )

        return WindowsRegistryDiscovery()

    @pytest.mark.asyncio
    async def test_get_provider_name(self, provider) -> None:
        assert provider.get_provider_name() == "windows-registry"

    @pytest.mark.asyncio
    async def test_get_provider_type(self, provider) -> None:
        assert provider.get_provider_type() == "registry"

    @pytest.mark.asyncio
    async def test_discover_empty_on_non_windows(self, provider) -> None:
        with patch("platform.system", return_value="Linux"):
            results = await provider.discover()
            assert results == []

    @pytest.mark.asyncio
    async def test_discover_on_windows_with_registry(self, provider) -> None:
        mock_key = MagicMock()
        mock_key.__enter__.return_value = mock_key

        with (
            patch("platform.system", return_value="Windows"),
            patch.object(provider, "_query_registry", return_value=r"C:\Program Files\Claude"),
            patch.object(
                provider, "_find_executable", return_value=r"C:\Program Files\Claude\claude.exe"
            ),
            patch.object(provider, "_get_version", return_value="1.5"),
        ):
            results = await provider.discover()
            assert len(results) >= 1
            assert any("claude" in r.name for r in results)

    @pytest.mark.asyncio
    async def test_query_registry_import_error(self, provider) -> None:
        # Simulate winreg not available
        with patch("builtins.__import__", side_effect=ImportError("no winreg")):
            result = provider._query_registry(["SOFTWARE\\Claude"])
            assert result is None

    @pytest.mark.asyncio
    async def test_find_executable_found(self, provider) -> None:
        with (
            patch("os.path.isfile", return_value=True),
            patch("os.access", return_value=True),
        ):
            result = provider._find_executable(r"C:\Tools")
            assert result is not None

    @pytest.mark.asyncio
    async def test_find_executable_not_found(self, provider) -> None:
        with (
            patch("os.path.isfile", return_value=False),
        ):
            result = provider._find_executable(r"C:\Empty")
            assert result is None

    @pytest.mark.asyncio
    async def test_discover_registry_returns_empty_no_executable(self, provider) -> None:
        with (
            patch("platform.system", return_value="Windows"),
            patch.object(provider, "_query_registry", return_value=r"C:\Program Files\Claude"),
            patch.object(provider, "_find_executable", return_value=None),
        ):
            results = await provider.discover()
            assert results == []

    @pytest.mark.asyncio
    async def test_build_description_with_version(self, provider) -> None:
        desc = provider._build_description({"name": "claude-code"}, r"C:\Claude", "2.0")
        assert "Claude-Code v2.0" in desc
        assert "Registry" in desc

    @pytest.mark.asyncio
    async def test_build_description_without_version(self, provider) -> None:
        desc = provider._build_description({"name": "docker"}, r"C:\Docker", None)
        assert "Docker" in desc
        assert "C:\\Docker" in desc


# ============================================================================
# 3. WslDiscovery
# ============================================================================


@pytest.mark.filterwarnings("ignore::RuntimeWarning")
class TestWslDiscovery:
    @pytest.fixture
    def provider(self):
        from agentic_os.adapters.discovery.wsl_provider import WslDiscovery

        return WslDiscovery()

    @pytest.mark.asyncio
    async def test_get_provider_name(self, provider) -> None:
        assert provider.get_provider_name() == "wsl-discovery"

    @pytest.mark.asyncio
    async def test_get_provider_type(self, provider) -> None:
        assert provider.get_provider_type() == "wsl"

    @pytest.mark.asyncio
    async def test_discover_empty_on_linux(self, provider) -> None:
        with patch("platform.system", return_value="Linux"):
            results = await provider.discover()
            assert results == []

    @pytest.mark.asyncio
    async def test_discover_empty_on_macos(self, provider) -> None:
        with patch("platform.system", return_value="Darwin"):
            results = await provider.discover()
            assert results == []

    @pytest.mark.asyncio
    async def test_discover_no_distros(self, provider) -> None:
        with (
            patch("platform.system", return_value="Windows"),
            patch.object(provider, "_list_distros", return_value=[]),
        ):
            results = await provider.discover()
            assert results == []

    @pytest.mark.asyncio
    async def test_discover_with_distro(self, provider) -> None:

        with (
            patch("platform.system", return_value="Windows"),
            patch.object(provider, "_list_distros", return_value=["Ubuntu"]),
            patch.object(provider, "_which_in_wsl", new=AsyncMock(return_value="/usr/bin/python3")),
            patch.object(provider, "_get_version_in_wsl", new=AsyncMock(return_value="3.11")),
        ):
            results = await provider.discover()
            assert len(results) >= 1
            assert any("wsl" in r.name for r in results)

    @pytest.mark.asyncio
    async def test_list_distros_parses_output(self, provider) -> None:
        mock_output = (
            "  NAME                   STATE           VERSION\n"
            "  Ubuntu                 Running         2\n"
            "  Debian                 Stopped         2\n"
        )
        with patch(
            "subprocess.run",
            return_value=MagicMock(returncode=0, stdout=mock_output, stderr=""),
        ):
            distros = provider._list_distros()
            assert "Ubuntu" in distros
            assert "Debian" in distros

    @pytest.mark.asyncio
    async def test_list_distros_nonzero_returncode(self, provider) -> None:
        with patch(
            "subprocess.run",
            return_value=MagicMock(returncode=1, stdout="", stderr="error"),
        ):
            distros = provider._list_distros()
            assert distros == []

    @pytest.mark.asyncio
    async def test_list_distros_file_not_found(self, provider) -> None:
        with patch("subprocess.run", side_effect=FileNotFoundError("wsl.exe not found")):
            distros = provider._list_distros()
            assert distros == []

    @pytest.mark.asyncio
    async def test_which_in_wsl_found(self, provider) -> None:
        mock_result = MagicMock(returncode=0, stdout="/usr/bin/node\n", stderr="")
        with patch("subprocess.run", return_value=mock_result):
            result = provider._which_in_wsl("Ubuntu", "node")
            assert result == "/usr/bin/node"

    @pytest.mark.asyncio
    async def test_which_in_wsl_not_found(self, provider) -> None:
        mock_result = MagicMock(returncode=1, stdout="", stderr="")
        with patch("subprocess.run", return_value=mock_result):
            result = provider._which_in_wsl("Ubuntu", "nonexistent")
            assert result is None

    @pytest.mark.asyncio
    async def test_discover_with_multiple_distros(self, provider) -> None:

        with (
            patch("platform.system", return_value="Windows"),
            patch.object(provider, "_list_distros", return_value=["Ubuntu", "Debian"]),
            patch.object(provider, "_which_in_wsl", new=AsyncMock(return_value="/usr/bin/python3")),
            patch.object(provider, "_get_version_in_wsl", new=AsyncMock(return_value="3.11")),
        ):
            results = await provider.discover()
            assert len(results) >= 2

    @pytest.mark.asyncio
    async def test_build_description(self, provider) -> None:
        desc = provider._build_description({"name": "claude"}, "Ubuntu", "/usr/bin/claude", "1.0")
        assert "Claude v1.0 (WSL Ubuntu: /usr/bin/claude)" == desc


# ============================================================================
# 4. DockerDiscovery
# ============================================================================


class TestDockerDiscovery:
    @pytest.fixture
    def provider(self):
        from agentic_os.adapters.discovery.docker_provider import DockerDiscovery

        return DockerDiscovery()

    @pytest.mark.asyncio
    async def test_get_provider_name(self, provider) -> None:
        assert provider.get_provider_name() == "docker-discovery"

    @pytest.mark.asyncio
    async def test_get_provider_type(self, provider) -> None:
        assert provider.get_provider_type() == "docker"

    @pytest.mark.asyncio
    async def test_discover_empty_when_docker_not_available(self, provider) -> None:
        with patch("shutil.which", return_value=None):
            results = await provider.discover()
            assert results == []

    @pytest.mark.asyncio
    async def test_docker_available(self, provider) -> None:
        with patch("shutil.which", return_value="/usr/bin/docker"):
            assert provider._docker_available() is True

    @pytest.mark.asyncio
    async def test_docker_not_available(self, provider) -> None:
        with patch("shutil.which", return_value=None):
            assert provider._docker_available() is False

    @pytest.mark.asyncio
    async def test_discover_with_engine_only(self, provider) -> None:
        with (
            patch("shutil.which", return_value="/usr/bin/docker"),
            patch.object(provider, "_get_docker_version", return_value="24.0.5"),
            patch.object(provider, "_list_containers", return_value=[]),
        ):
            results = await provider.discover()
            assert len(results) >= 1
            assert any(r.name == "docker-engine" for r in results)
            engine_reg = next(r for r in results if r.name == "docker-engine")
            assert engine_reg.version == "24.0.5"

    @pytest.mark.asyncio
    async def test_discover_with_containers(self, provider) -> None:
        mock_container = {
            "ID": "abc123",
            "Image": "claude-code:latest",
            "Names": "claude-agent",
            "Labels": "",
            "Status": "running",
        }
        with (
            patch("shutil.which", return_value="/usr/bin/docker"),
            patch.object(provider, "_get_docker_version", return_value="24.0.0"),
            patch.object(provider, "_list_containers", return_value=[mock_container]),
        ):
            results = await provider.discover()
            assert len(results) >= 2
            container_results = [
                r for r in results if "docker-" in r.name and r.name != "docker-engine"
            ]
            assert len(container_results) >= 1

    @pytest.mark.asyncio
    async def test_classify_container_by_label(self, provider) -> None:
        container = {
            "ID": "def456",
            "Image": "some-image",
            "Names": "ai-agent",
            "Labels": "com.anthropic.claude.version=1.0",
            "Status": "running",
        }
        result = provider._classify_container(container)
        assert result is not None
        assert "claude-code" in result.name

    @pytest.mark.asyncio
    async def test_classify_container_by_image(self, provider) -> None:
        container = {
            "ID": "ghi789",
            "Image": "aider:latest",
            "Names": "aider-agent",
            "Labels": "",
            "Status": "running",
        }
        result = provider._classify_container(container)
        assert result is not None
        assert "aider" in result.name

    @pytest.mark.asyncio
    async def test_classify_container_no_match(self, provider) -> None:
        container = {
            "ID": "xyz999",
            "Image": "nginx:latest",
            "Names": "web-server",
            "Labels": "",
            "Status": "running",
        }
        result = provider._classify_container(container)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_docker_version_success(self, provider) -> None:
        mock_result = MagicMock(returncode=0, stdout="24.0.5\n", stderr="")
        with patch("subprocess.run", return_value=mock_result):
            version = await provider._get_docker_version()
            assert version == "24.0.5"

    @pytest.mark.asyncio
    async def test_get_docker_version_failure(self, provider) -> None:
        mock_result = MagicMock(returncode=1, stdout="", stderr="error")
        with patch("subprocess.run", return_value=mock_result):
            version = await provider._get_docker_version()
            assert version is None

    @pytest.mark.asyncio
    async def test_list_containers_parse_json(self, provider) -> None:
        json_line = json.dumps(
            {"ID": "c1", "Image": "image", "Names": "n1", "Labels": "", "Status": "running"}
        )
        mock_result = MagicMock(returncode=0, stdout=json_line + "\n", stderr="")
        with patch("subprocess.run", return_value=mock_result):
            containers = await provider._list_containers()
            assert len(containers) == 1
            assert containers[0]["ID"] == "c1"


# ============================================================================
# 5. FilesystemDiscovery
# ============================================================================


class TestFilesystemDiscovery:
    @pytest.fixture
    def provider(self):
        from agentic_os.adapters.discovery.filesystem import FilesystemDiscovery

        return FilesystemDiscovery()

    @pytest.mark.asyncio
    async def test_get_provider_name(self, provider) -> None:
        assert provider.get_provider_name() == "filesystem-discovery"

    @pytest.mark.asyncio
    async def test_get_provider_type(self, provider) -> None:
        assert provider.get_provider_type() == "filesystem"

    @pytest.mark.asyncio
    async def test_discover_empty_when_no_matches(self, provider) -> None:
        with (
            patch("glob.glob", return_value=[]),
            patch("platform.system", return_value="Linux"),
        ):
            results = await provider.discover()
            assert results == []

    @pytest.mark.asyncio
    async def test_discover_finds_executable_on_linux(self, provider) -> None:
        with (
            patch("glob.glob", return_value=["/usr/local/bin/claude"]),
            patch("os.path.isfile", return_value=True),
            patch("os.access", return_value=True),
            patch("platform.system", return_value="Linux"),
            patch.object(provider, "_get_version", return_value="2.0"),
        ):
            results = await provider.discover()
            assert len(results) >= 1
            assert any("claude" in r.name for r in results)

    @pytest.mark.asyncio
    async def test_discover_empty_on_windows(self, provider) -> None:
        # Only Linux/Darwin patterns exist in test data
        with (
            patch("glob.glob", return_value=[]),
            patch("platform.system", return_value="Windows"),
        ):
            results = await provider.discover()
            # Windows patterns exist too, but glob returns empty
            assert results == []

    @pytest.mark.asyncio
    async def test_discover_skips_non_executable(self, provider) -> None:
        with (
            patch("glob.glob", return_value=["/usr/local/bin/claude"]),
            patch("os.path.isfile", return_value=True),
            patch("os.access", return_value=False),
            patch("platform.system", return_value="Linux"),
        ):
            results = await provider.discover()
            assert results == []

    @pytest.mark.asyncio
    async def test_discover_multiple_patterns(self, provider) -> None:
        def glob_side_effect(pattern: str) -> list[str]:
            if "node" in pattern:
                return [pattern]
            return []

        with (
            patch("glob.glob", side_effect=glob_side_effect),
            patch("os.path.isfile", return_value=True),
            patch("os.access", return_value=True),
            patch("platform.system", return_value="Linux"),
            patch.object(provider, "_get_version", return_value="18.0"),
        ):
            results = await provider.discover()
            assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_build_description(self, provider) -> None:
        desc = provider._build_description({"name": "claude-code"}, "/usr/bin/claude", "1.0")
        assert "Claude-Code v1.0" in desc
        assert "/usr/bin/claude" in desc


# ============================================================================
# 6. KnownInstallDirDiscovery
# ============================================================================


class TestKnownInstallDirDiscovery:
    @pytest.fixture
    def provider(self):
        from agentic_os.adapters.discovery.known_install_dirs import (
            KnownInstallDirDiscovery,
        )

        return KnownInstallDirDiscovery()

    @pytest.mark.asyncio
    async def test_get_provider_name(self, provider) -> None:
        assert provider.get_provider_name() == "known-install-dirs"

    @pytest.mark.asyncio
    async def test_get_provider_type(self, provider) -> None:
        assert provider.get_provider_type() == "known_install_dirs"

    @pytest.mark.asyncio
    async def test_discover_empty(self, provider) -> None:
        with (
            patch("os.path.isfile", return_value=False),
            patch("platform.system", return_value="Linux"),
        ):
            results = await provider.discover()
            assert results == []

    @pytest.mark.asyncio
    async def test_discover_finds_claude_in_home(self, provider) -> None:
        with (
            patch("os.path.isfile", side_effect=lambda p: "claude" in p),
            patch("os.access", return_value=True),
            patch("platform.system", return_value="Linux"),
            patch.object(provider, "_get_version", return_value="1.5"),
        ):
            results = await provider.discover()
            assert any("claude" in r.name for r in results)

    @pytest.mark.asyncio
    async def test_discover_platform_filter_darwin(self, provider) -> None:
        with (
            patch("os.path.isfile", return_value=True),
            patch("os.access", return_value=True),
            patch("platform.system", return_value="Darwin"),
            patch.object(provider, "_get_version", return_value="1.5"),
        ):
            results = await provider.discover()
            # Darwin should have the Homebrew entries
            assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_discover_platform_filter_windows(self, provider) -> None:
        # KnownInstallDirDiscovery doesn't have Windows-specific entries,
        # but cross-platform entries (home dir) should still work
        with (
            patch("os.path.isfile", return_value=True),
            patch("os.access", return_value=True),
            patch("platform.system", return_value="Windows"),
            patch.object(provider, "_get_version", return_value="1.0"),
        ):
            results = await provider.discover()
            # Windows matches the None-platform entries
            assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_discover_platform_filter_linux(self, provider) -> None:
        with (
            patch("os.path.isfile", side_effect=lambda p: "claude" in p or "python" in p),
            patch("os.access", return_value=True),
            patch("platform.system", return_value="Linux"),
            patch.object(provider, "_get_version", return_value="1.0"),
        ):
            results = await provider.discover()
            # Linux should include Snap entries
            assert len(results) >= 1


# ============================================================================
# 7. ConfigFileDiscovery
# ============================================================================


class TestConfigFileDiscovery:
    @pytest.fixture
    def provider(self):
        from agentic_os.adapters.discovery.config_file import ConfigFileDiscovery

        return ConfigFileDiscovery()

    @pytest.mark.asyncio
    async def test_get_provider_name(self, provider) -> None:
        assert provider.get_provider_name() == "config-file-discovery"

    @pytest.mark.asyncio
    async def test_get_provider_type(self, provider) -> None:
        assert provider.get_provider_type() == "config_file"

    @pytest.mark.asyncio
    async def test_discover_empty_when_no_configs(self, provider) -> None:
        with (
            patch("os.path.isfile", return_value=False),
            patch("os.path.isdir", return_value=False),
        ):
            results = await provider.discover()
            assert results == []

    @pytest.mark.asyncio
    async def test_discover_finds_json_config(self, provider) -> None:
        config_content = json.dumps({"executable": "/usr/bin/claude", "version": "2.0"})
        mock_file = MagicMock()
        mock_file.__enter__.return_value = mock_file
        mock_file.read.return_value = config_content

        with (
            patch("os.path.isfile", return_value=True),
            patch("builtins.open", return_value=mock_file),
        ):
            results = await provider.discover()
            assert len(results) >= 1
            assert any("claude" in r.name for r in results)

    @pytest.mark.asyncio
    async def test_discover_with_config_dir_fallback(self, provider) -> None:
        config_content = json.dumps({"executable": "/usr/bin/claude"})
        mock_file = MagicMock()
        mock_file.__enter__.return_value = mock_file
        mock_file.read.return_value = config_content

        def isfile_side_effect(path: str) -> bool:
            # Return False for all explicit config paths, True for dir-scanned files
            if "claude" in path and "config.json" in path:
                return False
            if "claude" in path and "config.yaml" in path:
                return False
            if "claude" in path and "config.yml" in path:
                return False
            if "config.json" in path:
                return True
            return False

        with (
            patch("os.path.isfile", side_effect=isfile_side_effect),
            patch("os.path.isdir", return_value=True),
            patch("builtins.open", return_value=mock_file),
        ):
            results = await provider.discover()
            assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_discover_config_without_executable(self, provider) -> None:
        config_content = json.dumps({"setting": "value"})
        mock_file = MagicMock()
        mock_file.__enter__.return_value = mock_file
        mock_file.read.return_value = config_content

        with (
            patch("os.path.isfile", return_value=True),
            patch("builtins.open", return_value=mock_file),
        ):
            results = await provider.discover()
            # Config exists but no executable reference -- still register with lower confidence
            assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_parse_config_file_unreadable(self, provider) -> None:
        with (
            patch("os.path.isfile", return_value=True),
            patch("builtins.open", side_effect=PermissionError("denied")),
        ):
            entry = await provider._parse_config_file(
                {"name": "test", "engine_type": EngineType.CUSTOM, "capabilities": []},
                "~/.config/test.json",
            )
            assert entry is None

    @pytest.mark.asyncio
    async def test_extract_executable_found(self, provider) -> None:
        result = provider._extract_executable({"executable": "/usr/bin/claude"})
        assert result == "/usr/bin/claude"

    @pytest.mark.asyncio
    async def test_extract_executable_not_found(self, provider) -> None:
        result = provider._extract_executable({"other": "value"})
        assert result is None

    @pytest.mark.asyncio
    async def test_parse_yaml_simple(self, provider) -> None:
        yaml_content = "executable: /usr/bin/claude\nversion: 1.0\n"
        result = provider._parse_yaml_simple(yaml_content)
        assert result is not None
        assert result["executable"] == "/usr/bin/claude"

    @pytest.mark.asyncio
    async def test_parse_yaml_simple_comments(self, provider) -> None:
        yaml_content = "# This is a comment\nexecutable: /usr/bin/claude\n"
        result = provider._parse_yaml_simple(yaml_content)
        assert result is not None
        assert result["executable"] == "/usr/bin/claude"

    @pytest.mark.asyncio
    async def test_parse_toml_simple(self, provider) -> None:
        toml_content = 'executable = "/usr/bin/claude"\nversion = "1.0"\n'
        result = provider._parse_toml_simple(toml_content)
        assert result is not None
        assert result["executable"] == "/usr/bin/claude"


# ============================================================================
# 8. EnvVarDiscovery
# ============================================================================


class TestEnvVarDiscovery:
    @pytest.fixture
    def provider(self):
        from agentic_os.adapters.discovery.env_var import EnvVarDiscovery

        return EnvVarDiscovery()

    @pytest.mark.asyncio
    async def test_get_provider_name(self, provider) -> None:
        assert provider.get_provider_name() == "env-var-discovery"

    @pytest.mark.asyncio
    async def test_get_provider_type(self, provider) -> None:
        assert provider.get_provider_type() == "env_var"

    @pytest.mark.asyncio
    async def test_discover_empty(self, provider) -> None:
        with patch.dict(os.environ, {}, clear=True):
            results = await provider.discover()
            assert results == []

    @pytest.mark.asyncio
    async def test_discover_finds_claude_path(self, provider) -> None:
        with (
            patch.dict(os.environ, {"CLAUDE_PATH": "/usr/bin/claude"}, clear=True),
            patch("os.path.isfile", return_value=True),
            patch("os.access", return_value=True),
            patch.object(provider, "_get_version", return_value="1.0"),
        ):
            results = await provider.discover()
            assert len(results) >= 1
            assert any("claude" in r.name for r in results)

    @pytest.mark.asyncio
    async def test_discover_finds_anthropic_api_key(self, provider) -> None:
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-xxx"}, clear=True):
            results = await provider.discover()
            assert len(results) >= 1
            assert any("claude-code-env" in r.name for r in results)

    @pytest.mark.asyncio
    async def test_discover_non_executable_value(self, provider) -> None:
        with (
            patch.dict(os.environ, {"DOCKER_HOST": "tcp://127.0.0.1:2375"}, clear=True),
            patch("os.path.isfile", return_value=False),
        ):
            results = await provider.discover()
            assert len(results) >= 1
            docker_result = next(r for r in results if "docker" in r.name)
            assert docker_result.transport == "env"

    @pytest.mark.asyncio
    async def test_discover_skips_empty_values(self, provider) -> None:
        with patch.dict(
            os.environ,
            {"CLAUDE_PATH": "", "ANTHROPIC_API_KEY": "  ", "DOCKER_HOST": "tcp://host:2375"},
            clear=True,
        ):
            results = await provider.discover()
            # Only DOCKER_HOST should produce a result
            assert len(results) == 1
            assert "docker" in results[0].name

    @pytest.mark.asyncio
    async def test_discover_deduplicates_vars(self, provider) -> None:
        # Two different entries share the same env var name
        with patch.dict(
            os.environ,
            {"NODE_PATH": "/usr/bin/node"},
            clear=True,
        ):
            results = await provider.discover()
            node_results = [r for r in results if "node" in r.name]
            # Should only be one result even though NODE_PATH appears in one config
            assert len(node_results) <= 1


# ============================================================================
# 9. VSCodeDiscovery
# ============================================================================


class TestVSCodeDiscovery:
    @pytest.fixture
    def provider(self):
        from agentic_os.adapters.discovery.vscode import VSCodeDiscovery

        return VSCodeDiscovery()

    @pytest.mark.asyncio
    async def test_get_provider_name(self, provider) -> None:
        assert provider.get_provider_name() == "vscode-discovery"

    @pytest.mark.asyncio
    async def test_get_provider_type(self, provider) -> None:
        assert provider.get_provider_type() == "vscode"

    @pytest.mark.asyncio
    async def test_discover_empty(self, provider) -> None:
        with (
            patch.object(provider, "_find_vscode_cli", return_value=None),
            patch("os.path.isdir", return_value=False),
        ):
            results = await provider.discover()
            assert results == []

    @pytest.mark.asyncio
    async def test_discover_finds_vscode_cli(self, provider) -> None:
        with (
            patch.object(provider, "_find_vscode_cli", return_value="/usr/bin/code"),
            patch.object(provider, "_get_version", return_value="1.80.0"),
            patch("os.path.isdir", return_value=False),
        ):
            results = await provider.discover()
            assert len(results) >= 1
            assert any(r.name == "vscode" for r in results)

    @pytest.mark.asyncio
    async def test_discover_finds_extensions(self, provider) -> None:
        with (
            patch.object(provider, "_find_vscode_cli", return_value="/usr/bin/code"),
            patch.object(provider, "_get_version", return_value="1.80.0"),
            patch("os.path.isdir", return_value=True),
            patch.object(
                provider,
                "_scan_extensions_dir",
                return_value=[
                    EngineRegistration(
                        name="vscode-github-copilot",
                        engine_type=EngineType.CUSTOM,
                        endpoint="vscode:ext:github.copilot",
                        transport="local",
                        capabilities=[EngineCapability.CODING, EngineCapability.REASONING],
                        version="1.0",
                        tags=["discovered", "vscode", "extension", "github-copilot"],
                        metadata={},
                    ),
                ],
            ),
        ):
            results = await provider.discover()
            assert len(results) >= 2
            assert any("github-copilot" in r.name for r in results)

    @pytest.mark.asyncio
    async def test_find_vscode_cli_in_path(self, provider) -> None:
        with (
            patch("shutil.which", return_value="/usr/local/bin/code"),
        ):
            result = provider._find_vscode_cli()
            assert result == "/usr/local/bin/code"

    @pytest.mark.asyncio
    async def test_find_vscode_cli_not_found(self, provider) -> None:
        with (
            patch("shutil.which", return_value=None),
            patch("platform.system", return_value="Linux"),
            patch("os.path.isfile", return_value=False),
        ):
            result = provider._find_vscode_cli()
            assert result is None

    @pytest.mark.asyncio
    async def test_match_extension_found(self, provider) -> None:
        result = provider._match_extension("github.copilot-1.2.3")
        assert result is not None
        assert result["name"] == "github-copilot"

    @pytest.mark.asyncio
    async def test_match_extension_not_found(self, provider) -> None:
        result = provider._match_extension("unknown.extension-1.0")
        assert result is None

    @pytest.mark.asyncio
    async def test_scan_extensions_dir_reads_package_json(self, provider) -> None:
        pkg = json.dumps({"version": "1.5.0"})
        mock_file = MagicMock()
        mock_file.__enter__.return_value = mock_file
        mock_file.read.return_value = pkg

        with (
            patch("os.listdir", return_value=["github.copilot-1.2.3"]),
            patch("os.path.isdir", return_value=True),
            patch("os.path.isfile", return_value=True),
            patch("builtins.open", return_value=mock_file),
        ):
            results = await provider._scan_extensions_dir("/extensions")
            assert len(results) == 1
            assert results[0].version == "1.5.0"

    @pytest.mark.asyncio
    async def test_scan_extensions_dir_permission_error(self, provider) -> None:
        with patch("os.listdir", side_effect=PermissionError("denied")):
            results = await provider._scan_extensions_dir("/extensions")
            assert results == []


# ============================================================================
# 10. JetBrainsDiscovery
# ============================================================================


class TestJetBrainsDiscovery:
    @pytest.fixture
    def provider(self):
        from agentic_os.adapters.discovery.jetbrains import JetBrainsDiscovery

        return JetBrainsDiscovery()

    @pytest.mark.asyncio
    async def test_get_provider_name(self, provider) -> None:
        assert provider.get_provider_name() == "jetbrains-discovery"

    @pytest.mark.asyncio
    async def test_get_provider_type(self, provider) -> None:
        assert provider.get_provider_type() == "jetbrains"

    @pytest.mark.asyncio
    async def test_discover_empty_no_plugin_roots(self, provider) -> None:
        with (
            patch.object(provider, "_get_plugin_roots", return_value=[]),
            patch("platform.system", return_value="Linux"),
        ):
            results = await provider.discover()
            assert results == []

    @pytest.mark.asyncio
    async def test_discover_finds_ide_cli(self, provider) -> None:
        with (
            patch.object(
                provider, "_get_plugin_roots", return_value=["/home/user/.local/share/JetBrains"]
            ),
            patch.object(provider, "_find_ide_cli", return_value=["/usr/bin/idea"]),
            patch.object(
                provider,
                "_make_ide_registration",
                return_value=EngineRegistration(
                    name="jetbrains-intellij-idea",
                    engine_type=EngineType.CUSTOM,
                    endpoint="local:/usr/bin/idea",
                    transport="local",
                    capabilities=[EngineCapability.CODING, EngineCapability.FILESYSTEM],
                    version="2024.1",
                    tags=["discovered", "jetbrains", "ide", "intellij-idea"],
                    metadata={
                        "cli_path": "/usr/bin/idea",
                        "ide_name": "IntelliJ IDEA",
                        "discovery_method": "jetbrains",
                    },
                ),
            ),
            patch.object(provider, "_resolve_plugin_dir", return_value=None),
        ):
            results = await provider.discover()
            assert len(results) >= 1
            assert any("intellij" in r.name for r in results)

    @pytest.mark.asyncio
    async def test_get_plugin_roots_windows(self, provider) -> None:
        with (
            patch("platform.system", return_value="Windows"),
            patch.dict(
                os.environ,
                {
                    "LOCALAPPDATA": "C:\\Users\\test\\AppData\\Local",
                    "APPDATA": "C:\\Users\\test\\AppData\\Roaming",
                },
            ),
        ):
            roots = provider._get_plugin_roots("Windows")
            assert len(roots) >= 3
            assert any("JetBrains" in r for r in roots)

    @pytest.mark.asyncio
    async def test_get_plugin_roots_darwin(self, provider) -> None:
        with patch("platform.system", return_value="Darwin"):
            roots = provider._get_plugin_roots("Darwin")
            assert len(roots) >= 2
            assert any("Application Support" in r for r in roots)

    @pytest.mark.asyncio
    async def test_get_plugin_roots_linux(self, provider) -> None:
        with patch("platform.system", return_value="Linux"):
            roots = provider._get_plugin_roots("Linux")
            assert len(roots) >= 3
            assert any(".local" in r for r in roots)

    @pytest.mark.asyncio
    async def test_match_plugin_found(self, provider) -> None:
        result = provider._match_plugin("github-copilot-1.2.3")
        assert result is not None
        assert result["name"] == "github-copilot"

    @pytest.mark.asyncio
    async def test_match_plugin_not_found(self, provider) -> None:
        result = provider._match_plugin("random-plugin-1.0")
        assert result is None

    @pytest.mark.asyncio
    async def test_find_ide_cli_returns_path(self, provider) -> None:
        with patch("shutil.which", return_value="/usr/bin/idea"):
            result = provider._find_ide_cli(
                {"name": "IntelliJ IDEA", "cli_names": ["idea"]}, "Linux"
            )
            assert "/usr/bin/idea" in result

    @pytest.mark.asyncio
    async def test_find_ide_cli_not_found(self, provider) -> None:
        with (
            patch("shutil.which", return_value=None),
            patch("platform.system", return_value="Linux"),
            patch("os.path.isfile", return_value=False),
        ):
            result = provider._find_ide_cli(
                {"name": "IntelliJ IDEA", "cli_names": ["idea"], "apps": ["idea.sh"]}, "Linux"
            )
            assert result == []

    @pytest.mark.asyncio
    async def test_scan_plugins_dir_finds_ai_plugins(self, provider) -> None:
        with (
            patch("os.listdir", return_value=["github-copilot-1.2.3", "ai-assistant-2.0"]),
            patch("os.path.isdir", return_value=True),
            patch.object(provider, "_read_plugin_version", return_value="1.0"),
        ):
            results = await provider._scan_plugins_dir("/plugins", "IntelliJ IDEA")
            assert len(results) == 2

    @pytest.mark.asyncio
    async def test_scan_plugins_dir_permission_error(self, provider) -> None:
        with patch("os.listdir", side_effect=PermissionError("denied")):
            results = await provider._scan_plugins_dir("/plugins", "IntelliJ IDEA")
            assert results == []

    @pytest.mark.asyncio
    async def test_read_plugin_version_from_plugin_xml(self, provider) -> None:
        xml_content = '<idea-plugin version="1.5.0"><name>Test</name></idea-plugin>'
        mock_file = MagicMock()
        mock_file.__enter__.return_value = mock_file
        mock_file.read.return_value = xml_content

        with (
            patch("os.path.isfile", return_value=True),
            patch("builtins.open", return_value=mock_file),
        ):
            version = await provider._read_plugin_version("/plugin")
            assert version == "1.5.0"

    @pytest.mark.asyncio
    async def test_read_plugin_version_from_package_json(self, provider) -> None:
        pkg = json.dumps({"version": "2.0.0"})
        mock_file = MagicMock()
        mock_file.__enter__.return_value = mock_file
        mock_file.read.return_value = pkg

        with (
            patch("os.path.isfile", side_effect=[False, True]),
            patch("builtins.open", return_value=mock_file),
        ):
            version = await provider._read_plugin_version("/plugin")
            assert version == "2.0.0"

    @pytest.mark.asyncio
    async def test_read_plugin_version_not_found(self, provider) -> None:
        with patch("os.path.isfile", return_value=False):
            version = await provider._read_plugin_version("/plugin")
            assert version is None

    @pytest.mark.asyncio
    async def test_make_ide_registration(self, provider) -> None:
        with (
            patch("os.path.isfile", return_value=True),
            patch("os.access", return_value=True),
            patch.object(provider, "_get_version", return_value="2024.1"),
        ):
            reg = await provider._make_ide_registration({"name": "IntelliJ IDEA"}, "/usr/bin/idea")
            assert reg is not None
            assert "intellij" in reg.name
            assert reg.endpoint == "local:/usr/bin/idea"

    @pytest.mark.asyncio
    async def test_make_ide_registration_no_executable(self, provider) -> None:
        with (
            patch("os.path.isfile", return_value=False),
        ):
            reg = await provider._make_ide_registration({"name": "IntelliJ IDEA"}, "/usr/bin/idea")
            assert reg is None

    @pytest.mark.asyncio
    async def test_discover_with_plugins(self, provider) -> None:
        with (
            patch.object(
                provider, "_get_plugin_roots", return_value=["/home/user/.local/share/JetBrains"]
            ),
            patch.object(provider, "_find_ide_cli", return_value=[]),
            patch.object(provider, "_resolve_plugin_dir", return_value="/plugins"),
            patch("os.path.isdir", return_value=True),
            patch.object(
                provider,
                "_scan_plugins_dir",
                return_value=[
                    EngineRegistration(
                        name="jetbrains-github-copilot-intellij-idea",
                        engine_type=EngineType.CUSTOM,
                        endpoint="jetbrains:plugin:github-copilot",
                        transport="local",
                        capabilities=[EngineCapability.CODING, EngineCapability.REASONING],
                        version="1.0",
                        tags=["discovered", "jetbrains", "plugin", "github-copilot"],
                        metadata={},
                    ),
                ],
            ),
        ):
            results = await provider.discover()
            assert len(results) >= 1
            assert any("copilot" in r.name for r in results)
