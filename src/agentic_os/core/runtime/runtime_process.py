"""Subprocess Manager — spawn, kill, and monitor OS subprocesses.

Provides a thread-safe async API for managing child processes with
cross-platform Windows/Linux support.
"""

from __future__ import annotations

import asyncio
import os
import signal
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from agentic_os.infrastructure.logging import get_logger

log = get_logger("runtime.process")

__all__ = [
    "SubprocessHandle",
    "SubprocessManager",
    "ProcessStatus",
]


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _is_windows() -> bool:
    return sys.platform == "win32"


class ProcessStatus:
    """Simple process status constants."""

    RUNNING = "running"
    STOPPED = "stopped"
    CRASHED = "crashed"
    UNKNOWN = "unknown"


@dataclass
class SubprocessHandle:
    """Handle tracking a spawned subprocess."""

    pid: int
    name: str
    command: str
    args: tuple[str, ...] = ()
    cwd: str | None = None
    env: dict[str, str] | None = None
    process: asyncio.subprocess.Process | None = None
    created_at: datetime = field(default_factory=_utcnow)
    stopped_at: datetime | None = None
    exit_code: int | None = None
    status: str = ProcessStatus.RUNNING
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def running(self) -> bool:
        return self.status == ProcessStatus.RUNNING

    @property
    def uptime(self) -> float:
        start = self.created_at.timestamp()
        end = (self.stopped_at or _utcnow()).timestamp()
        return end - start


class SubprocessManager:
    """Async subprocess lifecycle manager.

    Spawns, tracks, and signals OS processes. Thread-safe via asyncio.Lock.
    """

    def __init__(self) -> None:
        self._lock: asyncio.Lock = asyncio.Lock()
        self._handles: dict[int, SubprocessHandle] = {}
        # name -> set[pids]
        self._by_name: dict[str, set[int]] = {}

    # ── Spawn ─────────────────────────────────────────────────────────────────

    async def spawn(
        self,
        name: str,
        command: str,
        args: list[str] | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> SubprocessHandle:
        """Spawn a subprocess and return a handle.

        On Windows, ``command`` may be resolved with ``.exe`` suffix if the
        bare name is not found on ``PATH``.
        """
        resolved_cmd = await self._resolve_command(command)
        resolved_args = args or []
        full_args = [resolved_cmd, *resolved_args]

        merged_env: dict[str, str] | None = None
        if env:
            merged_env = {**os.environ, **env}

        log.debug(
            "spawning subprocess",
            name=name,
            command=resolved_cmd,
            args=resolved_args,
            cwd=cwd,
        )

        try:
            process = await asyncio.create_subprocess_exec(
                *full_args,
                cwd=cwd,
                env=merged_env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                **kwargs,
            )
        except FileNotFoundError:
            log.error("command not found", name=name, command=command)
            raise
        except Exception:
            log.exception("failed to spawn process", name=name, command=command)
            raise

        handle = SubprocessHandle(
            pid=process.pid or 0,
            name=name,
            command=command,
            args=tuple(resolved_args),
            cwd=cwd,
            env=merged_env,
            process=process,
        )

        async with self._lock:
            self._handles[handle.pid] = handle
            self._by_name.setdefault(name, set()).add(handle.pid)

        log.info("process spawned", pid=handle.pid, name=name, command=command)
        return handle

    async def _resolve_command(self, command: str) -> str:
        """Resolve the command to an executable path.

        On Windows, appends ``.exe`` automatically when the bare name
        doesn't contain a path separator.
        """
        if os.path.isabs(command):
            if _is_windows() and not command.lower().endswith(".exe"):
                exe = command + ".exe"
                if os.path.isfile(exe):
                    return exe
            return command

        # If command already has a separator, treat as relative path
        if os.sep in command or (_is_windows() and "/" in command):
            return command

        # Check if exe already suffixed
        if _is_windows() and not command.lower().endswith(".exe"):
            # Search PATH for the .exe version
            path_dirs = os.environ.get("PATH", "").split(os.pathsep)
            for d in path_dirs:
                candidate = os.path.join(d, command + ".exe")
                if os.path.isfile(candidate):
                    return candidate
            # Fallback to original — the error will surface naturally
            return command

        return command

    # ── Kill / Signal ─────────────────────────────────────────────────────────

    async def kill(
        self,
        pid: int,
        signal_name: str = "SIGTERM",
    ) -> bool:
        """Send a signal to the process identified by *pid*.

        On Windows, ``signal=`` is used as a hint:
        - ``SIGTERM`` / ``terminate`` → ``TerminateProcess`` (``taskkill /F``)
        - ``SIGINT`` / ``CTRL_C`` → ``GenerateConsoleCtrlEvent`` (via ``taskkill``)
        - ``SIGKILL`` / ``kill`` → ``taskkill /F``

        Returns ``True`` if the operation completed, ``False`` if the
        process was not tracked.
        """
        async with self._lock:
            handle = self._handles.get(pid)
            if handle is None:
                log.warning("kill called for unknown pid", pid=pid)
                return False

            if handle.status != ProcessStatus.RUNNING:
                log.debug("process already stopped", pid=pid, status=handle.status)
                return True

        if _is_windows():
            return await self._kill_windows(pid, handle, signal_name)
        return await self._kill_posix(pid, handle, signal_name)

    async def _kill_posix(
        self,
        pid: int,
        handle: SubprocessHandle,
        signal_name: str,
    ) -> bool:
        """POSIX kill via os.kill."""
        sig = getattr(signal, signal_name.upper(), signal.SIGTERM)
        try:
            os.kill(pid, sig)
            if sig != getattr(signal, "SIGKILL", signal.SIGTERM):
                # Give it time to exit gracefully
                if handle and handle.process:
                    try:
                        await asyncio.wait_for(handle.process.wait(), timeout=10)
                    except TimeoutError:
                        os.kill(pid, getattr(signal, "SIGKILL", signal.SIGTERM))
                    await handle.process.wait()
        except ProcessLookupError:
            pass  # already dead
        except Exception:
            log.exception("error killing process", pid=pid)
            return False

        async with self._lock:
            handle.status = ProcessStatus.STOPPED
            handle.stopped_at = _utcnow()
            handle.exit_code = handle.process.returncode if handle.process else -1

        log.info("process killed", pid=pid, signal=signal_name)
        return True

    async def _kill_windows(
        self,
        pid: int,
        handle: SubprocessHandle,
        signal_name: str,
    ) -> bool:
        """Windows kill via ``taskkill``."""
        sig_upper = signal_name.upper()
        if sig_upper in ("SIGKILL", "KILL"):
            taskkill_flag = "/F"
        elif sig_upper in ("SIGTERM", "TERM", "TERMINATE"):
            taskkill_flag = "/F"  # Windows needs /F to actually terminate
        else:
            taskkill_flag = ""  # try gentle first

        proc = await asyncio.create_subprocess_exec(
            "taskkill",
            "/PID",
            str(pid),
            taskkill_flag,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()

        # If gentle failed, force kill
        if proc.returncode != 0 and not taskkill_flag:
            proc2 = await asyncio.create_subprocess_exec(
                "taskkill",
                "/F",
                "/PID",
                str(pid),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc2.wait()

        async with self._lock:
            handle.status = ProcessStatus.STOPPED
            handle.stopped_at = _utcnow()
            if handle.process and handle.process.returncode is not None:
                handle.exit_code = handle.process.returncode

        log.info("process killed (windows)", pid=pid, signal=signal_name)
        return True

    async def terminate(self, pid: int) -> bool:
        """Convenience: send SIGTERM."""
        return await self.kill(pid, "SIGTERM")

    async def terminate_all(self) -> None:
        """Terminate every tracked process."""
        async with self._lock:
            pids = list(self._handles.keys())
        for pid in pids:
            await self.terminate(pid)

    # ── Status ────────────────────────────────────────────────────────────────

    async def get_status(self, pid: int) -> str:
        """Return the current status of the process (running/stopped/unknown)."""
        async with self._lock:
            handle = self._handles.get(pid)
            if handle is None:
                return ProcessStatus.UNKNOWN
            if handle.process and handle.process.returncode is not None:
                if handle.status == ProcessStatus.RUNNING:
                    handle.status = ProcessStatus.STOPPED
                    handle.stopped_at = _utcnow()
                    handle.exit_code = handle.process.returncode
                return ProcessStatus.STOPPED
            return handle.status

    async def get_children(self, pid: int) -> list[int]:
        """List child process PIDs of the given process.

        Uses platform-specific utilities:
        - Linux: /proc/<pid>/task/<pid>/children
        - Windows: wmic process where ParentProcessId=<pid> get ProcessId
        """
        if _is_windows():
            return await self._get_children_windows(pid)
        return await self._get_children_posix(pid)

    async def _get_children_posix(self, pid: int) -> list[int]:
        """POSIX: read /proc/<pid>/task/<pid>/children."""
        children: list[int] = []
        try:
            proc = await asyncio.create_subprocess_exec(
                "ps",
                "--ppid",
                str(pid),
                "-o",
                "pid=",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await proc.communicate()
            for line in stdout.decode().strip().split("\n"):
                line = line.strip()
                if line:
                    try:
                        children.append(int(line))
                    except ValueError:
                        continue
        except Exception:
            log.debug("could not list children on posix", pid=pid)
        return children

    async def _get_children_windows(self, pid: int) -> list[int]:
        """Windows: wmic to find child processes."""
        children: list[int] = []
        try:
            proc = await asyncio.create_subprocess_exec(
                "wmic",
                "process",
                "where",
                f"ParentProcessId={pid}",
                "get",
                "ProcessId",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await proc.communicate()
            for line in stdout.decode().strip().split("\n")[1:]:  # skip header
                line = line.strip()
                if line:
                    try:
                        children.append(int(line))
                    except ValueError:
                        continue
        except Exception:
            log.debug("could not list children on windows", pid=pid)
        return children

    # ── Handle Access ─────────────────────────────────────────────────────────

    async def get_handle(self, pid: int) -> SubprocessHandle | None:
        """Get the handle for a tracked pid."""
        async with self._lock:
            return self._handles.get(pid)

    async def list_handles(self) -> list[SubprocessHandle]:
        """Return all tracked process handles."""
        async with self._lock:
            return list(self._handles.values())

    async def list_by_name(self, name: str) -> list[SubprocessHandle]:
        """Return all handles matching *name*."""
        async with self._lock:
            pids = self._by_name.get(name, set())
            return [self._handles[pid] for pid in pids if pid in self._handles]

    async def remove(self, pid: int) -> bool:
        """Remove a completed process from tracking."""
        async with self._lock:
            handle = self._handles.pop(pid, None)
            if handle is None:
                return False
            self._by_name.get(handle.name, set()).discard(pid)
        return True

    async def wait(self, pid: int, timeout: float | None = None) -> int | None:
        """Wait for a process to exit and return its exit code."""
        async with self._lock:
            handle = self._handles.get(pid)
        if handle is None or handle.process is None:
            return None
        try:
            code = await asyncio.wait_for(handle.process.wait(), timeout=timeout)
        except TimeoutError:
            return None
        async with self._lock:
            handle.status = ProcessStatus.STOPPED
            handle.stopped_at = _utcnow()
            handle.exit_code = code
        return code
