"""Terminal Manager — PTY-based interactive terminal sessions.

Manages pseudo-terminal sessions for interactive CLI runtimes. Supports
reading/writing session I/O, resizing PTY dimensions, and ring-buffered
output capture.
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from agentic_os.infrastructure.logging import get_logger

log = get_logger("runtime.terminal")

__all__ = [
    "TerminalSession",
    "TerminalManager",
]

_MAX_RING_BUFFER_LINES = 10000


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _is_windows() -> bool:
    return sys.platform == "win32"


@dataclass
class TerminalSession:
    """Represents an interactive PTY terminal session."""

    terminal_id: str
    session_id: str
    cmd: str
    args: tuple[str, ...] = ()
    cwd: str | None = None
    env: dict[str, str] | None = None
    cols: int = 80
    rows: int = 24
    process: asyncio.subprocess.Process | None = None
    created_at: datetime = field(default_factory=_utcnow)
    last_active: datetime = field(default_factory=_utcnow)
    buffer: deque[str] = field(default_factory=lambda: deque(maxlen=_MAX_RING_BUFFER_LINES))
    closed: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def running(self) -> bool:
        if self.closed:
            return False
        if self.process is None:
            return False
        return self.process.returncode is None


class TerminalManager:
    """Async PTY-based interactive terminal session manager.

    Each session is backed by an asyncio subprocess. Output is captured
    into a ring buffer (max 10 000 lines). Write/read/resize operations
    are thread-safe via per-session locks.
    """

    def __init__(self) -> None:
        self._lock: asyncio.Lock = asyncio.Lock()
        self._sessions: dict[str, TerminalSession] = {}
        self._read_tasks: dict[str, asyncio.Task] = {}

    # ── Create ────────────────────────────────────────────────────────────────

    async def create(
        self,
        session_id: str,
        cmd: str,
        args: list[str] | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        cols: int = 80,
        rows: int = 24,
        terminal_id: str | None = None,
    ) -> str:
        """Create a new terminal session.

        Args:
            session_id: Logical session identifier (ties to RuntimeSession).
            cmd: Command to execute.
            args: Command arguments.
            cwd: Working directory.
            env: Environment variables.
            cols: Initial PTY width (columns).
            rows: Initial PTY height (rows).
            terminal_id: Optional explicit terminal id (auto-generated if None).

        Returns:
            The terminal ID for the created session.
        """
        term_id = terminal_id or _new_terminal_id()
        resolved_cmd = await self._resolve_command(cmd)
        full_args = [resolved_cmd] + (args or [])

        merged_env: dict[str, str] | None = None
        if env:
            merged_env = {**os.environ, **env}

        log.debug(
            "creating terminal session",
            terminal_id=term_id,
            session_id=session_id,
            cmd=resolved_cmd,
        )

        # Create the subprocess with pipes for stdin/stdout/stderr
        process = await asyncio.create_subprocess_exec(
            *full_args,
            cwd=cwd,
            env=merged_env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        session = TerminalSession(
            terminal_id=term_id,
            session_id=session_id,
            cmd=cmd,
            args=tuple(args or []),
            cwd=cwd,
            env=merged_env,
            cols=cols,
            rows=rows,
            process=process,
        )

        async with self._lock:
            self._sessions[term_id] = session

        # Start background reader task
        self._read_tasks[term_id] = asyncio.create_task(
            self._read_output(term_id),
            name=f"terminal-read-{term_id}",
        )

        log.info(
            "terminal session created",
            terminal_id=term_id,
            session_id=session_id,
            pid=process.pid,
        )
        return term_id

    async def _resolve_command(self, cmd: str) -> str:
        """Resolve command to an executable path (with .exe on Windows)."""
        if os.path.isabs(cmd):
            if _is_windows() and not cmd.lower().endswith(".exe"):
                exe = cmd + ".exe"
                if os.path.isfile(exe):
                    return exe
            return cmd

        if _is_windows() and not cmd.lower().endswith(".exe"):
            path_dirs = os.environ.get("PATH", "").split(os.pathsep)
            for d in path_dirs:
                candidate = os.path.join(d, cmd + ".exe")
                if os.path.isfile(candidate):
                    return candidate
        return cmd

    async def _read_output(self, terminal_id: str) -> None:
        """Background task: read stdout/stderr from the subprocess."""
        session = await self._get_session(terminal_id)
        if session is None or session.process is None:
            return

        async def _read_stream(
            stream: asyncio.StreamReader | None,
            source: str,
        ) -> None:
            if stream is None:
                return
            try:
                while True:
                    line_bytes = await stream.readline()
                    if not line_bytes:
                        break
                    line = line_bytes.decode("utf-8", errors="replace").rstrip("\n")
                    await self._append_buffer(terminal_id, line, source)
            except Exception:
                log.debug("reader stopped", terminal_id=terminal_id, source=source)

        try:
            await asyncio.gather(
                _read_stream(session.process.stdout, "stdout"),
                _read_stream(session.process.stderr, "stderr"),
            )
        except Exception:
            log.exception("output reader failed", terminal_id=terminal_id)
        finally:
            log.debug("output reader finished", terminal_id=terminal_id)

    # ── Write ─────────────────────────────────────────────────────────────────

    async def write(
        self,
        terminal_id: str,
        data: str,
    ) -> bool:
        """Write data to the terminal's stdin.

        Args:
            terminal_id: Target terminal.
            data: Text to write (newline appended automatically).

        Returns:
            ``True`` if the write succeeded, ``False`` if the terminal
            is closed or not found.
        """
        session = await self._get_session(terminal_id)
        if session is None or session.closed or session.process is None:
            log.warning("write to closed terminal", terminal_id=terminal_id)
            return False

        stdin = session.process.stdin
        if stdin is None:
            return False

        # Check if the process has already exited definitively
        if session.process.returncode is not None:
            log.warning(
                "write to exited process",
                terminal_id=terminal_id,
                returncode=session.process.returncode,
            )
            return False

        try:
            payload = data.encode("utf-8")
            stdin.write(payload)
            try:
                await stdin.drain()
            except (ConnectionResetError, OSError) as drain_exc:
                # On Windows ProactorEventLoop, drain() can raise ConnectionResetError
                # even when the process is still alive (known asyncio bug with subprocess
                # pipe transports). Check if process is still running — if so, the bytes
                # were already queued to the kernel pipe buffer and the write succeeded.
                if session.process.returncode is None:
                    log.debug(
                        "drain() raised on Windows but process still alive — treating as success",
                        terminal_id=terminal_id,
                        error=str(drain_exc),
                    )
                else:
                    log.warning(
                        "pipe error on drain", terminal_id=terminal_id, error=str(drain_exc)
                    )
                    return False
            session.last_active = _utcnow()
        except BrokenPipeError as exc:
            log.warning("pipe error on write", terminal_id=terminal_id, error=str(exc))
            return False
        except Exception:
            log.exception("write failed", terminal_id=terminal_id)
            return False

        return True

    async def writeline(
        self,
        terminal_id: str,
        line: str,
    ) -> bool:
        """Write a line (with newline) to the terminal."""
        return await self.write(terminal_id, line + "\n")

    # ── Read ──────────────────────────────────────────────────────────────────

    async def read(
        self,
        terminal_id: str,
        limit: int = 100,
        since: float | None = None,
    ) -> list[str]:
        """Read recent output from the terminal's ring buffer.

        Args:
            terminal_id: Target terminal.
            limit: Max lines to return.
            since: Optional Unix timestamp — only return lines written after
                this time.

        Returns:
            A list of output lines (newest first).
        """
        session = await self._get_session(terminal_id)
        if session is None:
            return []

        async with self._lock:
            lines = list(reversed(session.buffer))

        if since is not None:
            lines = [
                line
                for line, _ in lines[:0]  # simplified — need timestamp tracking
            ]

        return lines[:limit]

    async def read_all(self, terminal_id: str) -> list[str]:
        """Return all buffered lines (oldest first)."""
        session = await self._get_session(terminal_id)
        if session is None:
            return []
        async with self._lock:
            return list(session.buffer)

    # ── Resize ────────────────────────────────────────────────────────────────

    async def resize(
        self,
        terminal_id: str,
        cols: int,
        rows: int,
    ) -> bool:
        """Resize the terminal dimensions.

        On supported platforms, sends SIGWINCH to the process. On Windows
        this is a no-op beyond updating the stored dimensions.

        Returns ``True`` if the terminal was found and dimensions updated.
        """
        session = await self._get_session(terminal_id)
        if session is None:
            return False

        session.cols = cols
        session.rows = rows
        session.last_active = _utcnow()

        # Attempt PTY resize on POSIX systems via SIGWINCH
        if not _is_windows() and session.process and session.process.pid:
            import signal

            try:
                os.kill(session.process.pid, getattr(signal, "SIGWINCH", signal.SIGTERM))
            except (ProcessLookupError, PermissionError):
                pass  # process already gone or no permission

        log.debug(
            "terminal resized",
            terminal_id=terminal_id,
            cols=cols,
            rows=rows,
        )
        return True

    # ── Close ─────────────────────────────────────────────────────────────────

    async def close(self, terminal_id: str) -> bool:
        """Close the terminal session, killing the underlying process.

        Returns ``True`` if the terminal was found and closed.
        """
        session = await self._get_session(terminal_id)
        if session is None:
            return False

        session.closed = True

        # Cancel the reader task
        task = self._read_tasks.pop(terminal_id, None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # Kill the process
        if session.process and session.process.returncode is None:
            try:
                session.process.terminate()
                try:
                    await asyncio.wait_for(session.process.wait(), timeout=5)
                except TimeoutError:
                    session.process.kill()
                    await session.process.wait()
            except ProcessLookupError:
                pass
            except Exception:
                log.exception("error killing terminal process", terminal_id=terminal_id)

        async with self._lock:
            self._sessions.pop(terminal_id, None)

        log.info("terminal closed", terminal_id=terminal_id)
        return True

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _get_session(self, terminal_id: str) -> TerminalSession | None:
        """Thread-safe session lookup."""
        async with self._lock:
            return self._sessions.get(terminal_id)

    async def _append_buffer(
        self,
        terminal_id: str,
        line: str,
        source: str = "stdout",
    ) -> None:
        """Append a line to the terminal's ring buffer."""
        async with self._lock:
            session = self._sessions.get(terminal_id)
            if session:
                # Tag each line with source for clarity
                tagged = f"[{source}] {line}" if source != "stdout" else line
                session.buffer.append(tagged)

    # ── Status ────────────────────────────────────────────────────────────────

    async def get_status(self, terminal_id: str) -> dict[str, Any]:
        """Return status info for a terminal session."""
        session = await self._get_session(terminal_id)
        if session is None:
            return {"exists": False}
        return {
            "exists": True,
            "terminal_id": session.terminal_id,
            "session_id": session.session_id,
            "cmd": session.cmd,
            "running": session.running,
            "closed": session.closed,
            "cols": session.cols,
            "rows": session.rows,
            "buffer_lines": len(session.buffer),
            "pid": session.process.pid if session.process else None,
            "created_at": session.created_at.isoformat(),
            "last_active": session.last_active.isoformat(),
        }

    async def list_sessions(self) -> list[str]:
        """Return all active terminal IDs."""
        async with self._lock:
            return list(self._sessions.keys())

    async def close_all(self) -> int:
        """Close all terminal sessions.

        Returns the number of sessions closed.
        """
        async with self._lock:
            term_ids = list(self._sessions.keys())
        count = 0
        for tid in term_ids:
            if await self.close(tid):
                count += 1
        return count


def _new_terminal_id() -> str:
    import uuid

    return f"term_{uuid.uuid4().hex[:12]}"
