"""Tests for PathScanner and ExecutableLocator (Phase 6.1)."""

from __future__ import annotations

import os
import platform
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from agentic_os.core.discovery.local.path_scanner import (
    ExecutableLocator,
    KNOWN_TOOLS,
    PathScanner,
)


# ═══════════════════════════════════════════════════════════════════════════════
# ExecutableLocator — find_in_path
# ═══════════════════════════════════════════════════════════════════════════════


class TestExecutableLocatorFindInPath:
    def test_find_in_path_returns_path_when_found(self, tmp_path) -> None:
        with patch("platform.system", return_value="Linux"):
            with patch("shutil.which", return_value="/usr/local/bin/my-tool"):
                locator = ExecutableLocator()
                result = locator.find_in_path("my-tool")
                assert result is not None
                assert "my-tool" in result

    def test_find_in_path_returns_none_for_missing(self) -> None:
        with patch("platform.system", return_value="Linux"):
            with patch("os.environ", {"PATH": "/usr/bin"}):
                with patch("shutil.which", return_value=None):
                    locator = ExecutableLocator()
                    result = locator.find_in_path("nonexistent-tool-xyz")
                    assert result is None

    def test_empty_path_returns_none(self) -> None:
        with patch("platform.system", return_value="Linux"):
            with patch("os.environ", {"PATH": ""}):
                with patch("shutil.which", return_value=None):
                    locator = ExecutableLocator()
                    result = locator.find_in_path("python")
                    assert result is None

    def test_windows_exe_resolution(self) -> None:
        with patch("platform.system", return_value="Windows"):
            locator = ExecutableLocator()
            # With mock path containing a .exe
            with patch("shutil.which", return_value="C:\\tools\\tool.exe"):
                result = locator.find_in_path("tool")
                assert result is not None
                assert "tool.exe" in result or "tool" in result

    def test_windows_prefers_shorter_path(self) -> None:
        with patch("platform.system", return_value="Windows"):
            locator = ExecutableLocator()
            # Simulate shutil.which returning .exe first
            with patch("shutil.which", side_effect=lambda x: f"C:\\bin\\{x}" if x else None):
                result = locator.find_in_path("tool")
                assert result is not None

    def test_find_in_path_uses_shutil_which(self) -> None:
        with patch("platform.system", return_value="Linux"):
            with patch("shutil.which", return_value="/usr/bin/fake-tool"):
                locator = ExecutableLocator()
                result = locator.find_in_path("fake-tool")
                assert result == os.path.abspath("/usr/bin/fake-tool")


# ═══════════════════════════════════════════════════════════════════════════════
# ExecutableLocator — find_in_common_dirs
# ═══════════════════════════════════════════════════════════════════════════════


class TestExecutableLocatorFindInCommonDirs:
    def test_find_in_common_dirs_linux(self) -> None:
        with patch("platform.system", return_value="Linux"):
            locator = ExecutableLocator()
            with (
                patch.object(locator, "_get_common_dirs", return_value=["/opt"]),
                patch("os.path.isdir", return_value=True),
                patch("os.listdir", return_value=["ollama"]),
                patch("os.path.isfile", return_value=True),
                patch("os.path.splitext", return_value=("ollama", "")),
            ):
                results = locator.find_in_common_dirs("ollama")
                assert len(results) >= 1

    def test_find_in_common_dirs_none_when_not_found(self) -> None:
        with patch("platform.system", return_value="Linux"):
            locator = ExecutableLocator()
            with (
                patch.object(locator, "_get_common_dirs", return_value=["/opt"]),
                patch("os.path.isdir", return_value=True),
                patch("os.listdir", return_value=["some-other-file"]),
                patch("os.path.isfile", return_value=True),
                patch("os.path.splitext", return_value=("some-other-file", "")),
            ):
                results = locator.find_in_common_dirs("ollama")
                assert len(results) == 0

    def test_find_in_common_dirs_permission_denied(self) -> None:
        with patch("platform.system", return_value="Linux"):
            locator = ExecutableLocator()
            with (
                patch.object(locator, "_get_common_dirs", return_value=["/opt"]),
                patch("os.path.isdir", return_value=True),
                patch("os.listdir", side_effect=PermissionError("denied")),
            ):
                results = locator.find_in_common_dirs("ollama")
                assert len(results) == 0

    def test_find_in_common_dirs_dirs_not_exist(self) -> None:
        with patch("platform.system", return_value="Linux"):
            locator = ExecutableLocator()
            with (
                patch.object(locator, "_get_common_dirs", return_value=["/nonexistent"]),
                patch("os.path.isdir", return_value=False),
            ):
                results = locator.find_in_common_dirs("ollama")
                assert len(results) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# ExecutableLocator — _get_common_dirs
# ═══════════════════════════════════════════════════════════════════════════════


class TestGetCommonDirs:
    def test_linux_common_dirs(self) -> None:
        with patch("platform.system", return_value="Linux"):
            locator = ExecutableLocator()
            locator._system = "linux"
            dirs = locator._get_common_dirs()
            assert "/usr/local/bin" in dirs
            assert "/opt" in dirs

    def test_windows_common_dirs(self) -> None:
        with patch("platform.system", return_value="Windows"):
            with patch.dict(
                os.environ,
                {
                    "PROGRAMFILES": "C:\\Program Files",
                    "PROGRAMFILES(X86)": "C:\\Program Files (x86)",
                    "LOCALAPPDATA": "C:\\Users\\test\\AppData\\Local",
                    "APPDATA": "C:\\Users\\test\\AppData\\Roaming",
                    "USERPROFILE": "C:\\Users\\test",
                },
            ):
                locator = ExecutableLocator()
                locator._system = "windows"
                dirs = locator._get_common_dirs()
                assert any("Program Files" in d for d in dirs)
                assert any("AppData" in d for d in dirs)


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWN_TOOLS
# ═══════════════════════════════════════════════════════════════════════════════


class TestKnownTools:
    def test_all_tools_have_names(self) -> None:
        for tool_type, names in KNOWN_TOOLS.items():
            assert isinstance(tool_type, str)
            assert isinstance(names, list)

    def test_hermes_has_two_names(self) -> None:
        assert "hermes" in KNOWN_TOOLS["hermes"]
        assert "hermes-agent" in KNOWN_TOOLS["hermes"]

    def test_lm_studio_empty_names(self) -> None:
        assert KNOWN_TOOLS.get("lm-studio") == []


# ═══════════════════════════════════════════════════════════════════════════════
# PathScanner
# ═══════════════════════════════════════════════════════════════════════════════


class TestPathScanner:
    def test_scan_all_returns_known_tools(self) -> None:
        locator = MagicMock()
        locator.find_in_path = MagicMock(
            side_effect=lambda name: f"/usr/bin/{name}" if name in ("ollama", "docker") else None
        )
        scanner = PathScanner(locator=locator)
        results = scanner.scan_all()
        assert len(results) == 2
        tool_types = [r[0] for r in results]
        assert "ollama" in tool_types
        assert "docker" in tool_types

    def test_scan_all_empty_when_none_found(self) -> None:
        locator = MagicMock()
        locator.find_in_path = MagicMock(return_value=None)
        scanner = PathScanner(locator=locator)
        results = scanner.scan_all()
        assert results == []

    def test_scan_all_lm_studio_skipped(self) -> None:
        """lm-studio has empty exec names so it should be skipped."""
        locator = MagicMock()
        locator.find_in_path = MagicMock(return_value="/usr/bin/hermes")
        scanner = PathScanner(locator=locator)
        results = scanner.scan_all()
        # lm-studio should not appear since exec_names = []
        for tool_type, _ in results:
            assert tool_type != "lm-studio"

    def test_scan_all_breaks_after_first_match(self) -> None:
        """For tool with multiple names, stop at first match."""
        locator = MagicMock()
        locator.find_in_path = MagicMock(
            side_effect=lambda name: "/usr/bin/hermes" if name == "hermes" else None
        )
        scanner = PathScanner(locator=locator)
        results = scanner.scan_all()
        # hermes should be found via "hermes", never reaches "hermes-agent"
        hermes_found = [r for r in results if r[0] == "hermes"]
        assert len(hermes_found) == 1
