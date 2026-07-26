"""Tests for TerminalManager — PTY terminal sessions, read/write/resize."""

import asyncio
import sys

import pytest

from agentic_os.core.runtime.runtime_terminal import TerminalManager, TerminalSession


@pytest.fixture
def term_mgr() -> TerminalManager:
    return TerminalManager()


@pytest.mark.asyncio
class TestTerminalManager:
    async def test_create_session(self, term_mgr: TerminalManager) -> None:
        term_id = await term_mgr.create(
            session_id="sess-1",
            cmd=sys.executable,
            args=["-c", "print('hello terminal')"],
        )
        assert term_id is not None
        assert term_id.startswith("term_")

    async def test_create_with_explicit_terminal_id(self, term_mgr: TerminalManager) -> None:
        term_id = await term_mgr.create(
            session_id="sess-2",
            cmd=sys.executable,
            args=["-c", "print('explicit')"],
            terminal_id="my-term-1",
        )
        assert term_id == "my-term-1"

    async def test_list_sessions(self, term_mgr: TerminalManager) -> None:
        await term_mgr.create(
            session_id="sess-list",
            cmd=sys.executable,
            args=["-c", "print('list')"],
        )
        sessions = await term_mgr.list_sessions()
        assert len(sessions) == 1

    async def test_get_status(self, term_mgr: TerminalManager) -> None:
        term_id = await term_mgr.create(
            session_id="sess-status",
            cmd=sys.executable,
            args=["-c", "import time; time.sleep(5)"],
        )
        status = await term_mgr.get_status(term_id)
        assert status["exists"] is True
        assert status["running"] is True

    async def test_get_status_for_nonexistent(self, term_mgr: TerminalManager) -> None:
        status = await term_mgr.get_status("ghost")
        assert status["exists"] is False

    async def test_write_and_read(self, term_mgr: TerminalManager) -> None:
        term_id = await term_mgr.create(
            session_id="sess-write",
            cmd=sys.executable,
            args=[
                "-c",
                "import sys, time; print('ready'); sys.stdout.flush(); time.sleep(5)",
            ],
        )
        # Give the process time to start
        await asyncio.sleep(0.3)

        written = await term_mgr.write(term_id, "hello")
        assert written is True

    async def test_writeline(self, term_mgr: TerminalManager) -> None:
        term_id = await term_mgr.create(
            session_id="sess-writeline",
            cmd=sys.executable,
            args=[
                "-c",
                "import sys, time; print('ready'); sys.stdout.flush(); time.sleep(5)",
            ],
        )
        await asyncio.sleep(0.3)
        result = await term_mgr.writeline(term_id, "test line")
        assert result is True

    async def test_write_to_closed(self, term_mgr: TerminalManager) -> None:
        term_id = await term_mgr.create(
            session_id="sess-closed",
            cmd=sys.executable,
            args=["-c", "print('quick')"],
        )
        await term_mgr.close(term_id)
        result = await term_mgr.write(term_id, "data")
        assert result is False

    async def test_write_to_nonexistent(self, term_mgr: TerminalManager) -> None:
        result = await term_mgr.write("ghost", "data")
        assert result is False

    async def test_resize(self, term_mgr: TerminalManager) -> None:
        term_id = await term_mgr.create(
            session_id="sess-resize",
            cmd=sys.executable,
            args=["-c", "import time; time.sleep(10)"],
        )
        result = await term_mgr.resize(term_id, cols=120, rows=40)
        assert result is True
        status = await term_mgr.get_status(term_id)
        assert status["cols"] == 120
        assert status["rows"] == 40

    async def test_resize_nonexistent(self, term_mgr: TerminalManager) -> None:
        result = await term_mgr.resize("ghost", 80, 24)
        assert result is False

    async def test_read_all(self, term_mgr: TerminalManager) -> None:
        term_id = await term_mgr.create(
            session_id="sess-readall",
            cmd=sys.executable,
            args=["-c", "print('line1'); print('line2')"],
        )
        # Wait for process to finish
        await asyncio.sleep(0.5)
        lines = await term_mgr.read_all(term_id)
        assert isinstance(lines, list)

    async def test_read_from_nonexistent(self, term_mgr: TerminalManager) -> None:
        lines = await term_mgr.read("ghost")
        assert lines == []

    async def test_close(self, term_mgr: TerminalManager) -> None:
        term_id = await term_mgr.create(
            session_id="sess-close",
            cmd=sys.executable,
            args=["-c", "import time; time.sleep(10)"],
        )
        result = await term_mgr.close(term_id)
        assert result is True
        status = await term_mgr.get_status(term_id)
        assert status["exists"] is False

    async def test_close_nonexistent(self, term_mgr: TerminalManager) -> None:
        result = await term_mgr.close("ghost")
        assert result is False

    async def test_close_all(self, term_mgr: TerminalManager) -> None:
        await term_mgr.create(
            session_id="s1", cmd=sys.executable, args=["-c", "import time; time.sleep(10)"]
        )
        await term_mgr.create(
            session_id="s2", cmd=sys.executable, args=["-c", "import time; time.sleep(10)"]
        )
        count = await term_mgr.close_all()
        assert count == 2

    async def test_terminal_session_running_property(self) -> None:
        session = TerminalSession(terminal_id="t1", session_id="s1", cmd="echo")
        assert session.running is False  # no process
        session.closed = True
        assert session.running is False
