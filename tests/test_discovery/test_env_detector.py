"""Tests for EnvironmentDetector (Phase 6.1)."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from agentic_os.core.discovery.local.env_detector import EnvironmentDetector


class TestEnvironmentDetector:
    @pytest.fixture
    def detector(self) -> EnvironmentDetector:
        d = EnvironmentDetector()
        d._system = "linux"
        return d

    @pytest.fixture
    def detector_win(self) -> EnvironmentDetector:
        d = EnvironmentDetector()
        d._system = "windows"
        return d

    async def test_detect_returns_env_vars_for_hermes(self, detector: EnvironmentDetector) -> None:
        with patch.dict(os.environ, {"HERMES_CONFIG": "/etc/hermes/config.yaml"}, clear=True):
            result = await detector.scan()
            assert "hermes" in result["env_vars"]
            assert result["env_vars"]["hermes"]["HERMES_CONFIG"] == "/etc/hermes/config.yaml"

    async def test_detect_returns_env_vars_ollama(self, detector: EnvironmentDetector) -> None:
        with patch.dict(os.environ, {"OLLAMA_HOST": "localhost:11434"}, clear=True):
            result = await detector.scan()
            assert "ollama" in result["env_vars"]
            assert result["env_vars"]["ollama"]["OLLAMA_HOST"] == "localhost:11434"

    async def test_detect_empty_env_vars(self, detector: EnvironmentDetector) -> None:
        with patch.dict(os.environ, {}, clear=True):
            result = await detector.scan()
            assert result["env_vars"] == {}

    async def test_detect_python_version(self, detector: EnvironmentDetector) -> None:
        result = await detector.scan()
        assert result["python_version"] != ""
        parts = result["python_version"].split(".")
        assert len(parts) >= 3

    async def test_detect_docker_available_true(self, detector: EnvironmentDetector) -> None:
        with patch.object(detector, "_check_docker", return_value=True):
            result = await detector.scan()
            assert result["docker_available"] is True

    async def test_detect_docker_available_false(self, detector: EnvironmentDetector) -> None:
        with patch.object(detector, "_check_docker", return_value=False):
            result = await detector.scan()
            assert result["docker_available"] is False

    async def test_detect_node_version_present(self, detector: EnvironmentDetector) -> None:
        with patch.object(detector, "_get_node_version", return_value="18.0.0"):
            result = await detector.scan()
            assert result["node_version"] == "18.0.0"

    async def test_detect_node_version_empty(self, detector: EnvironmentDetector) -> None:
        with patch.object(detector, "_get_node_version", return_value=""):
            result = await detector.scan()
            assert result["node_version"] == ""

    async def test_detect_system_field(self, detector: EnvironmentDetector) -> None:
        result = await detector.scan()
        assert result["system"] == "linux"

    async def test_detect_system_windows(self, detector_win: EnvironmentDetector) -> None:
        result = await detector_win.scan()
        assert result["system"] == "windows"

    async def test_detect_python_and_node(self, detector: EnvironmentDetector) -> None:
        with (
            patch.object(detector, "_get_node_version", return_value="20.0.0"),
            patch.object(detector, "_check_docker", return_value=True),
        ):
            result = await detector.scan()
            assert result["python_version"] != ""
            assert result["node_version"] == "20.0.0"
            assert result["docker_available"] is True

    async def test_detect_node_version_timeout(self, detector: EnvironmentDetector) -> None:
        """Simulate timeout when calling node --version."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_exec.side_effect = TimeoutError("node timed out")
            ver = await detector._get_node_version()
            assert ver == ""

    async def test_detect_docker_not_found(self, detector: EnvironmentDetector) -> None:
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_exec.side_effect = FileNotFoundError("docker not found")
            avail = await detector._check_docker()
            assert avail is False

    async def test_detect_docker_timeout(self, detector: EnvironmentDetector) -> None:
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_exec.side_effect = TimeoutError("docker info timed out")
            avail = await detector._check_docker()
            assert avail is False

    async def test_detect_claude_config(self, detector: EnvironmentDetector) -> None:
        with patch.dict(os.environ, {"CLAUDE_CONFIG": "/home/user/.claude"}, clear=True):
            result = await detector.scan()
            assert "claude-code" in result["env_vars"]

    async def test_detect_multiple_env_vars(self, detector: EnvironmentDetector) -> None:
        with patch.dict(
            os.environ,
            {
                "DOCKER_HOST": "tcp://localhost:2375",
                "DOCKER_CONFIG": "/home/user/.docker",
                "PYTHONPATH": "/home/user/project",
            },
            clear=True,
        ):
            result = await detector.scan()
            assert "docker" in result["env_vars"]
            assert "python" in result["env_vars"]
