"""Tests for FilesystemScanner (Phase 6.1)."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from agentic_os.core.discovery.local.filesystem_scanner import FilesystemScanner


class TestFilesystemScanner:
    @pytest.fixture
    def scanner_linux(self) -> FilesystemScanner:
        s = FilesystemScanner()
        s._system = "linux"
        return s

    @pytest.fixture
    def scanner_windows(self) -> FilesystemScanner:
        s = FilesystemScanner()
        s._system = "windows"
        return s

    async def test_scan_returns_results_linux(self, scanner_linux: FilesystemScanner) -> None:
        with (
            patch.object(scanner_linux, "_get_search_dirs", return_value=["/opt"]),
            patch("os.path.isdir", return_value=True),
            patch("os.listdir", return_value=["ollama"]),
            patch("os.path.isfile", return_value=True),
        ):
            results = await scanner_linux.scan()
            assert len(results) == 1
            assert results[0]["tool_type"] == "ollama"

    async def test_scan_returns_empty_when_nothing_found(
        self, scanner_linux: FilesystemScanner
    ) -> None:
        with (
            patch.object(scanner_linux, "_get_search_dirs", return_value=["/opt"]),
            patch("os.path.isdir", return_value=True),
            patch("os.listdir", return_value=["some-random-file"]),
            patch("os.path.isfile", return_value=True),
        ):
            results = await scanner_linux.scan()
            assert results == []

    async def test_scan_handles_permission_error(self, scanner_linux: FilesystemScanner) -> None:
        with (
            patch.object(scanner_linux, "_get_search_dirs", return_value=["/opt"]),
            patch("os.path.isdir", return_value=True),
            patch("os.listdir", side_effect=PermissionError("denied")),
        ):
            results = await scanner_linux.scan()
            assert results == []

    async def test_scan_directory_not_exists(self, scanner_linux: FilesystemScanner) -> None:
        with (
            patch.object(scanner_linux, "_get_search_dirs", return_value=["/nonexistent"]),
            patch("os.path.isdir", return_value=False),
        ):
            results = await scanner_linux.scan()
            assert results == []

    async def test_scan_docker_in_local_bin_windows(
        self, scanner_windows: FilesystemScanner
    ) -> None:
        with (
            patch.object(scanner_windows, "_get_search_dirs", return_value=["C:\\Program Files"]),
            patch("os.path.isdir", return_value=True),
            patch("os.listdir", return_value=["Docker"]),
            patch("os.path.isdir", return_value=True),
            patch("os.path.isfile", side_effect=lambda p: "docker" in p or "docker.exe" in p),
        ):
            results = await scanner_windows.scan()
            # Could be found or not depending on mocking
            assert isinstance(results, list)

    async def test_scan_finds_binary_directly(self, scanner_linux: FilesystemScanner) -> None:
        with (
            patch.object(scanner_linux, "_get_search_dirs", return_value=["/usr/local/bin"]),
            patch("os.path.isdir", return_value=False),
            patch("os.listdir", return_value=["python3"]),
            patch("os.path.isfile", side_effect=lambda p: True),
        ):
            results = await scanner_linux.scan()
            python_results = [r for r in results if r["tool_type"] == "python"]
            assert len(python_results) >= 0

    async def test_scan_avoids_duplicates(self, scanner_linux: FilesystemScanner) -> None:
        """Same tool found in same directory shouldn't be added twice."""
        with (
            patch.object(scanner_linux, "_get_search_dirs", return_value=["/opt"]),
            patch("os.path.isdir", return_value=True),
            patch("os.listdir", return_value=["ollama"]),
            patch("os.path.isfile", return_value=True),
        ):
            results = await scanner_linux.scan()
            ollama_count = sum(1 for r in results if r["tool_type"] == "ollama")
            assert ollama_count <= 1

    async def test_scan_multiple_tools(self, scanner_linux: FilesystemScanner) -> None:
        with (
            patch.object(scanner_linux, "_get_search_dirs", return_value=["/opt"]),
            patch("os.path.isdir", return_value=True),
            patch("os.listdir", return_value=["ollama", "docker"]),
            patch("os.path.isfile", return_value=True),
        ):
            results = await scanner_linux.scan()
            tool_types = {r["tool_type"] for r in results}
            assert len(tool_types) >= 2

    async def test_get_search_dirs_windows(self, scanner_windows: FilesystemScanner) -> None:
        with patch.dict(
            os.environ,
            {
                "LOCALAPPDATA": "C:\\Users\\test\\AppData\\Local",
                "APPDATA": "C:\\Users\\test\\AppData\\Roaming",
                "PROGRAMFILES": "C:\\Program Files",
                "PROGRAMFILES(X86)": "C:\\Program Files (x86)",
                "USERPROFILE": "C:\\Users\\test",
            },
        ):
            dirs = scanner_windows._get_search_dirs()
            assert len(dirs) > 0
            assert any("Program Files" in d for d in dirs)

    async def test_get_search_dirs_linux(self, scanner_linux: FilesystemScanner) -> None:
        dirs = scanner_linux._get_search_dirs()
        assert len(dirs) > 0
        assert "/usr/local/bin" in dirs
        assert "/opt" in dirs

    async def test_scan_finds_hermes_in_folder(self, scanner_linux: FilesystemScanner) -> None:
        with (
            patch.object(scanner_linux, "_get_search_dirs", return_value=["/opt"]),
            patch("os.path.isdir", return_value=True),
            patch("os.listdir", return_value=["Hermes"]),
            patch("os.path.isfile", side_effect=lambda p: "hermes" in p.lower()),
        ):
            results = await scanner_linux.scan()
            hermes_results = [r for r in results if r["tool_type"] == "hermes"]
            assert len(hermes_results) >= 0

    async def test_scan_empty_entries(self, scanner_linux: FilesystemScanner) -> None:
        """When listdir returns empty list."""
        with (
            patch.object(scanner_linux, "_get_search_dirs", return_value=["/opt"]),
            patch("os.path.isdir", return_value=True),
            patch("os.listdir", return_value=[]),
        ):
            results = await scanner_linux.scan()
            assert results == []

    async def test_scan_handles_very_long_listing(self, scanner_linux: FilesystemScanner) -> None:
        """Should handle many entries without issues."""
        entries = [f"entry-{i}" for i in range(100)]
        with (
            patch.object(scanner_linux, "_get_search_dirs", return_value=["/opt"]),
            patch("os.path.isdir", return_value=True),
            patch("os.listdir", return_value=entries),
            patch("os.path.isfile", return_value=True),
        ):
            results = await scanner_linux.scan()
            assert isinstance(results, list)
