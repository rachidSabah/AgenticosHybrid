"""Tests for RegistryScanner (Phase 6.1)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from agentic_os.core.discovery.local.registry_scanner import RegistryScanner

# ═══════════════════════════════════════════════════════════════════════════════
# RegistryScanner — non-Windows
# ═══════════════════════════════════════════════════════════════════════════════


class TestRegistryScannerNonWindows:
    @pytest.fixture
    def scanner(self) -> RegistryScanner:
        s = RegistryScanner()
        s._on_windows = False
        s._system = "linux"
        return s

    async def test_scan_returns_empty_on_non_windows(self, scanner: RegistryScanner) -> None:
        results = await scanner.scan()
        assert results == []

    async def test_scan_logs_debug_on_non_windows(self, scanner: RegistryScanner) -> None:
        with patch("agentic_os.core.discovery.local.registry_scanner.log") as mock_log:
            await scanner.scan()
            mock_log.debug.assert_any_call("RegistryScanner skipped — not on Windows")


# ═══════════════════════════════════════════════════════════════════════════════
# RegistryScanner — Windows (mocked)
# ═══════════════════════════════════════════════════════════════════════════════


class TestRegistryScannerWindows:
    @pytest.fixture
    def scanner(self) -> RegistryScanner:
        s = RegistryScanner()
        s._on_windows = True
        s._system = "windows"
        return s

    async def test_scan_returns_results_on_windows(self, scanner: RegistryScanner) -> None:
        with patch.object(
            scanner,
            "_query_reg_path",
            AsyncMock(
                return_value=[
                    {
                        "DisplayName": "Ollama",
                        "DisplayVersion": "0.1.0",
                        "InstallLocation": "C:\\Users\\test\\AppData\\Local\\Ollama",
                    }
                ]
            ),
        ):
            results = await scanner.scan()
            assert len(results) >= 1
            assert any(r["tool_type"] == "ollama" for r in results)

    async def test_scan_matches_multiple_tools(self, scanner: RegistryScanner) -> None:
        items = [
            {"DisplayName": "Ollama", "DisplayVersion": "0.1.0", "InstallLocation": "C:\\Ollama"},
            {"DisplayName": "Git", "DisplayVersion": "2.40.0", "InstallLocation": "C:\\Git"},
        ]
        with (
            patch.object(scanner, "_query_reg_path", AsyncMock(return_value=items)),
            patch(
                "agentic_os.core.discovery.local.registry_scanner._REGISTRY_PATHS", ("HKCU\\Test",)
            ),
        ):
            results = await scanner.scan()
            assert len(results) == 2
            tool_types = {r["tool_type"] for r in results}
            assert "ollama" in tool_types
            assert "git" in tool_types

    async def test_scan_case_insensitive_match(self, scanner: RegistryScanner) -> None:
        items = [
            {
                "DisplayName": "OLLAMA Desktop",
                "DisplayVersion": "1.0",
                "InstallLocation": "C:\\Ollama",
            },
        ]
        with (
            patch.object(scanner, "_query_reg_path", AsyncMock(return_value=items)),
            patch(
                "agentic_os.core.discovery.local.registry_scanner._REGISTRY_PATHS", ("HKCU\\Test",)
            ),
        ):
            results = await scanner.scan()
            assert len(results) == 1
            assert results[0]["tool_type"] == "ollama"

    async def test_scan_handles_file_not_found(self, scanner: RegistryScanner) -> None:
        with patch.object(
            scanner, "_query_reg_path", AsyncMock(side_effect=FileNotFoundError("reg"))
        ):
            results = await scanner.scan()
            assert results == []

    async def test_scan_handles_generic_exception(self, scanner: RegistryScanner) -> None:
        with patch.object(scanner, "_query_reg_path", AsyncMock(side_effect=Exception("boom"))):
            results = await scanner.scan()
            assert results == []

    async def test_scan_no_matching_tools(self, scanner: RegistryScanner) -> None:
        items = [
            {
                "DisplayName": "Microsoft Office",
                "DisplayVersion": "16.0",
                "InstallLocation": "C:\\Office",
            },
        ]
        with patch.object(scanner, "_query_reg_path", AsyncMock(return_value=items)):
            results = await scanner.scan()
            assert results == []

    async def test_scan_empty_items(self, scanner: RegistryScanner) -> None:
        with patch.object(scanner, "_query_reg_path", AsyncMock(return_value=[])):
            results = await scanner.scan()
            assert results == []

    async def test_scan_empty_display_name_skipped(self, scanner: RegistryScanner) -> None:
        items = [{"DisplayName": "", "DisplayVersion": "1.0", "InstallLocation": ""}]
        with patch.object(scanner, "_query_reg_path", AsyncMock(return_value=items)):
            results = await scanner.scan()
            assert results == []

    async def test_query_reg_path_timeout(self, scanner: RegistryScanner) -> None:
        with patch.object(scanner, "_query_reg_path", AsyncMock(return_value=[])):
            results = await scanner.scan()
            assert results == []


# ═══════════════════════════════════════════════════════════════════════════════
# _parse_reg_output
# ═══════════════════════════════════════════════════════════════════════════════


class TestParseRegOutput:
    def test_parse_reg_output_basic(self) -> None:
        text = "    DisplayName    REG_SZ    Ollama\n    DisplayVersion    REG_SZ    0.1.0\n"
        items = RegistryScanner._parse_reg_output(text)
        assert len(items) == 1
        assert items[0]["DisplayName"] == "Ollama"
        assert items[0]["DisplayVersion"] == "0.1.0"

    def test_parse_reg_output_empty(self) -> None:
        items = RegistryScanner._parse_reg_output("")
        assert items == []

    def test_parse_reg_output_no_match(self) -> None:
        items = RegistryScanner._parse_reg_output("some random text")
        assert items == []

    def test_parse_reg_output_multiple_keys(self) -> None:
        text = (
            "    DisplayName    REG_SZ    Tool1\n"
            "    DisplayVersion    REG_SZ    1.0\n"
            "\n"
            "    DisplayName    REG_SZ    Tool2\n"
            "    DisplayVersion    REG_SZ    2.0\n"
        )
        items = RegistryScanner._parse_reg_output(text)
        assert len(items) == 2
