"""Tests for VersionDetector (Phase 6.1)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from agentic_os.core.discovery.local.version_detector import VersionDetector


class TestVersionDetector:
    @pytest.fixture
    def detector(self) -> VersionDetector:
        return VersionDetector()

    async def test_get_version_returns_parsed(self, detector: VersionDetector) -> None:
        with patch.object(detector, "_run_version_command", return_value="2.0.0"):
            ver = await detector.get_version("/usr/bin/hermes", "hermes")
            assert ver == "2.0.0"

    async def test_get_version_empty_for_unknown_tool(self, detector: VersionDetector) -> None:
        ver = await detector.get_version("/usr/bin/strange-tool", "strange-tool")
        assert ver == ""

    async def test_get_version_unknown_tool_cached(self, detector: VersionDetector) -> None:
        ver = await detector.get_version("/bin/tool", "unknown-type")
        assert ver == ""
        assert detector.get_cache_size() == 1

    async def test_version_caching_same_call_returns_cached(
        self, detector: VersionDetector
    ) -> None:
        with patch.object(detector, "_run_version_command", return_value="3.0.0") as mock_run:
            v1 = await detector.get_version("/usr/bin/hermes", "hermes")
            v2 = await detector.get_version("/usr/bin/hermes", "hermes")
            assert v1 == v2
            assert v1 == "3.0.0"
            # Should only call subprocess once
            mock_run.assert_called_once()

    async def test_version_caching_different_paths(self, detector: VersionDetector) -> None:
        with patch.object(detector, "_run_version_command", side_effect=["1.0", "2.0"]):
            v1 = await detector.get_version("/usr/bin/hermes", "hermes")
            v2 = await detector.get_version("/usr/local/bin/hermes", "hermes")
            assert v1 == "1.0"
            assert v2 == "2.0"

    async def test_timeout_handling(self, detector: VersionDetector) -> None:
        with patch.object(detector, "_run_version_command", return_value=""):
            ver = await detector.get_version("/usr/bin/hermes", "hermes")
            assert ver == ""

    async def test_non_existent_executable_returns_empty(self, detector: VersionDetector) -> None:
        with patch.object(detector, "_run_version_command", return_value=""):
            ver = await detector.get_version("/nonexistent/tool", "hermes")
            assert ver == ""

    async def test_parse_version_hermes(self, detector: VersionDetector) -> None:
        output = "Hermes Agent v2.1.0"
        patterns = [r"(?:Hermes|hermes)\s+(?:Agent\s+)?v?(\d[\w.]*)", r"v?(\d+\.\d+\.\d+)"]
        ver = detector._parse_version(output, patterns)
        assert ver == "2.1.0"

    async def test_parse_version_python(self, detector: VersionDetector) -> None:
        output = "Python 3.12.1"
        patterns = [r"Python\s+(\d[\w.]*)", r"(\d+\.\d+\.\d+)"]
        ver = detector._parse_version(output, patterns)
        assert ver == "3.12.1"

    async def test_parse_version_node(self, detector: VersionDetector) -> None:
        output = "v18.0.0"
        patterns = [r"v?(\d+\.\d+\.\d+)"]
        ver = detector._parse_version(output, patterns)
        assert ver == "18.0.0"

    async def test_parse_version_empty_output(self, detector: VersionDetector) -> None:
        ver = detector._parse_version("", [r"v?(\d+\.\d+\.\d+)"])
        assert ver == ""

    async def test_parse_version_no_match(self, detector: VersionDetector) -> None:
        ver = detector._parse_version("some random text", [r"v?(\d+\.\d+\.\d+)"])
        assert ver == ""

    async def test_get_versions_batch(self, detector: VersionDetector) -> None:
        with patch.object(detector, "_run_version_command", side_effect=["1.0", "2.0", ""]):
            executables = [
                ("hermes", "/usr/bin/hermes"),
                ("ollama", "/usr/bin/ollama"),
                ("unknown", "/usr/bin/unknown"),
            ]
            results = await detector.get_versions_batch(executables)
            assert len(results) == 3
            assert results[0] == ("hermes", "/usr/bin/hermes", "1.0")
            assert results[1] == ("ollama", "/usr/bin/ollama", "2.0")
            assert results[2] == ("unknown", "/usr/bin/unknown", "")

    async def test_clear_cache(self, detector: VersionDetector) -> None:
        with patch.object(detector, "_run_version_command", return_value="1.0"):
            await detector.get_version("/usr/bin/hermes", "hermes")
            assert detector.get_cache_size() == 1
            detector.clear_cache()
            assert detector.get_cache_size() == 0

    async def test_get_cache_size(self, detector: VersionDetector) -> None:
        assert detector.get_cache_size() == 0
