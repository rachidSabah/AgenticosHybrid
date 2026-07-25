"""Tests for ProcessScanner (Phase 6.1)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agentic_os.core.discovery.local.process_scanner import ProcessScanner


# ═══════════════════════════════════════════════════════════════════════════════
# ProcessScanner — Windows (tasklist)
# ═══════════════════════════════════════════════════════════════════════════════


class TestProcessScannerWindows:
    @pytest.fixture
    def scanner(self) -> ProcessScanner:
        s = ProcessScanner()
        s._system = "windows"
        return s

    async def test_windows_returns_results(self, scanner: ProcessScanner) -> None:
        tasklist_output = (
            '"python.exe","12345","Console","1","45,678 K"\r\n'
            '"ollama.exe","54321","Console","1","98,765 K"\r\n'
        )
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            proc = AsyncMock()
            proc.communicate = AsyncMock(
                return_value=(tasklist_output.encode("utf-8"), b"")
            )
            proc.returncode = 0
            mock_exec.return_value = proc

            results = await scanner.scan()
            assert len(results) == 2
            assert any(r["tool_type"] == "python" for r in results)
            assert any(r["tool_type"] == "ollama" for r in results)

    async def test_windows_parses_pid_and_memory(self, scanner: ProcessScanner) -> None:
        tasklist_output = '"hermes.exe","9999","Console","1","12,345 K"\r\n'
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            proc = AsyncMock()
            proc.communicate = AsyncMock(
                return_value=(tasklist_output.encode("utf-8"), b"")
            )
            proc.returncode = 0
            mock_exec.return_value = proc

            results = await scanner.scan()
            assert len(results) == 1
            r = results[0]
            assert r["tool_type"] == "hermes"
            assert r["pid"] == 9999
            # 12,345 K / 1024 ≈ 12.1 MB
            assert r["memory_mb"] == pytest.approx(12.1, abs=0.2)
            assert r["cpu_percent"] == 0.0

    async def test_windows_empty_process_list(self, scanner: ProcessScanner) -> None:
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            proc = AsyncMock()
            proc.communicate = AsyncMock(return_value=(b"", b""))
            proc.returncode = 0
            mock_exec.return_value = proc

            results = await scanner.scan()
            assert results == []

    async def test_windows_no_matching_tools(self, scanner: ProcessScanner) -> None:
        tasklist_output = '"notepad.exe","1234","Console","1","10,000 K"\r\n'
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            proc = AsyncMock()
            proc.communicate = AsyncMock(
                return_value=(tasklist_output.encode("utf-8"), b"")
            )
            proc.returncode = 0
            mock_exec.return_value = proc

            results = await scanner.scan()
            assert results == []

    async def test_windows_tasklist_timeout(self, scanner: ProcessScanner) -> None:
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            proc = AsyncMock()
            proc.communicate = AsyncMock(side_effect=TimeoutError("timeout"))
            mock_exec.return_value = proc

            results = await scanner.scan()
            assert results == []

    async def test_windows_tasklist_not_found(self, scanner: ProcessScanner) -> None:
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_exec.side_effect = FileNotFoundError("tasklist not found")
            results = await scanner.scan()
            assert results == []

    async def test_windows_memory_format_m(self, scanner: ProcessScanner) -> None:
        tasklist_output = '"codex.exe","1111","Console","1","50 M"\r\n'
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            proc = AsyncMock()
            proc.communicate = AsyncMock(
                return_value=(tasklist_output.encode("utf-8"), b"")
            )
            proc.returncode = 0
            mock_exec.return_value = proc

            results = await scanner.scan()
            assert len(results) == 1
            assert results[0]["memory_mb"] == pytest.approx(50.0, abs=0.1)  # 50*1024/1024 = 50

    async def test_windows_memory_bare_number(self, scanner: ProcessScanner) -> None:
        tasklist_output = '"test.exe","2222","Console","1","100000"\r\n'
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            proc = AsyncMock()
            proc.communicate = AsyncMock(
                return_value=(tasklist_output.encode("utf-8"), b"")
            )
            proc.returncode = 0
            mock_exec.return_value = proc

            results = await scanner.scan()
            assert len(results) == 0  # "test" not a known tool


# ═══════════════════════════════════════════════════════════════════════════════
# ProcessScanner — POSIX (ps aux)
# ═══════════════════════════════════════════════════════════════════════════════


class TestProcessScannerPosix:
    @pytest.fixture
    def scanner(self) -> ProcessScanner:
        s = ProcessScanner()
        s._system = "linux"
        return s

    async def test_posix_returns_results(self, scanner: ProcessScanner) -> None:
        ps_output = (
            "USER       PID %CPU %MEM    VSZ   RSS TT  STAT STARTED       TIME COMMAND\n"
            "user      1001  1.0  2.0  12345  6789 ??  S    10:00AM   0:01.23 python\n"
            "user      2002  0.5  1.5  54321  4321 ??  S    10:01AM   0:00.45 ollama\n"
        )
        with patch.object(scanner, "_system", "linux"):
            with patch("asyncio.create_subprocess_exec") as mock_exec:
                proc = AsyncMock()
                proc.communicate = AsyncMock(
                    return_value=(ps_output.encode("utf-8"), b"")
                )
                proc.returncode = 0
                mock_exec.return_value = proc

                results = await scanner.scan()
                assert len(results) == 2

    async def test_posix_parses_pid_and_cpu(self, scanner: ProcessScanner) -> None:
        ps_output = (
            "USER       PID %CPU %MEM    VSZ   RSS TT  STAT STARTED       TIME COMMAND\n"
            "user      1001  5.5  3.0  12345  6789 ??  S    10:00AM   0:01.23 ollama\n"
        )
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            proc = AsyncMock()
            proc.communicate = AsyncMock(
                return_value=(ps_output.encode("utf-8"), b"")
            )
            proc.returncode = 0
            mock_exec.return_value = proc

            results = await scanner.scan()
            assert len(results) == 1
            r = results[0]
            assert r["tool_type"] == "ollama"
            assert r["pid"] == 1001
            assert r["cpu_percent"] == 5.5

    async def test_posix_empty_process_list(self, scanner: ProcessScanner) -> None:
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            proc = AsyncMock()
            proc.communicate = AsyncMock(return_value=(b"", b""))
            proc.returncode = 0
            mock_exec.return_value = proc

            results = await scanner.scan()
            assert results == []

    async def test_posix_ps_not_found(self, scanner: ProcessScanner) -> None:
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_exec.side_effect = FileNotFoundError("ps not found")
            results = await scanner.scan()
            assert results == []

    async def test_posix_ps_timeout(self, scanner: ProcessScanner) -> None:
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            proc = AsyncMock()
            proc.communicate = AsyncMock(side_effect=TimeoutError("timeout"))
            mock_exec.return_value = proc
            results = await scanner.scan()
            assert results == []

    async def test_posix_no_matching_tools(self, scanner: ProcessScanner) -> None:
        ps_output = (
            "USER       PID %CPU %MEM    VSZ   RSS TT  STAT STARTED       TIME COMMAND\n"
            "user      3003  0.0  0.1  12345   678 ??  S    10:00AM   0:00.01 bash\n"
        )
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            proc = AsyncMock()
            proc.communicate = AsyncMock(
                return_value=(ps_output.encode("utf-8"), b"")
            )
            proc.returncode = 0
            mock_exec.return_value = proc

            results = await scanner.scan()
            assert len(results) == 0

    async def test_posix_no_header_uses_fallback(self, scanner: ProcessScanner) -> None:
        ps_output = (
            " 1234  1.0  2.0  python /usr/bin/python\n"
            " 5678  0.5  1.0  ollama serve\n"
        )
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            proc = AsyncMock()
            proc.communicate = AsyncMock(
                return_value=(ps_output.encode("utf-8"), b"")
            )
            proc.returncode = 0
            mock_exec.return_value = proc
            # The fallback uses last column as command; these lines won't
            # parse cleanly because "1.0" is not a valid PID, so results
            # should be safely empty rather than crash.
            results = await scanner.scan()
            assert isinstance(results, list)


class TestProcessScannerHelpers:
    def test_match_process_name_returns_tool_type(self) -> None:
        scanner = ProcessScanner()
        result = scanner._match_process_name("ollama.exe")
        assert result == "ollama"

    def test_match_process_name_returns_none(self) -> None:
        scanner = ProcessScanner()
        result = scanner._match_process_name("notepad.exe")
        assert result is None

    def test_match_process_name_case_insensitive(self) -> None:
        scanner = ProcessScanner()
        result = scanner._match_process_name("OLLAMA")
        assert result == "ollama"

    def test_match_process_name_hermes(self) -> None:
        scanner = ProcessScanner()
        result = scanner._match_process_name("hermes")
        assert result == "hermes"
        result2 = scanner._match_process_name("hermes-agent")
        assert result2 == "hermes"

    def test_find_cmd_idx_standard(self) -> None:
        cols = ["user", "pid", "%cpu", "%mem", "vsz", "rss", "tt", "stat", "started", "time", "command"]
        idx = ProcessScanner._find_cmd_idx(cols)
        assert idx == cols.index("command")

    def test_find_cmd_idx_no_known(self) -> None:
        cols = ["a", "b", "c"]
        idx = ProcessScanner._find_cmd_idx(cols)
        assert idx == 0  # first unknown column
