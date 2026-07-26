"""Runtime Launcher — translates a Runtime config into an OS subprocess.

Reads a Runtime dataclass's command, arguments, working_directory, and
environment fields, then delegates to the SubprocessManager to actually
spawn the process. Handles OS-specific launch quirks such as Windows .exe
suffix resolution and PATH discovery.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from agentic_os.core.runtime.runtime import Runtime
from agentic_os.core.runtime.runtime_process import (
    ProcessStatus,
    SubprocessHandle,
    SubprocessManager,
)
from agentic_os.infrastructure.logging import get_logger

log = get_logger("runtime.launcher")

__all__ = [
    "LaunchResult",
    "RuntimeLauncher",
]


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _is_windows() -> bool:
    return sys.platform == "win32"


@dataclass
class LaunchResult:
    """Result of a runtime launch operation."""

    pid: int
    handle: SubprocessHandle
    runtime_id: str
    runtime_name: str
    command: str
    working_directory: str | None = None
    launched_at: datetime = field(default_factory=_utcnow)
    platform: str = field(default=sys.platform)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pid": self.pid,
            "runtime_id": self.runtime_id,
            "runtime_name": self.runtime_name,
            "command": self.command,
            "working_directory": self.working_directory,
            "launched_at": self.launched_at.isoformat(),
            "platform": self.platform,
        }


class RuntimeLauncher:
    """Translates ``Runtime`` configuration to a running OS subprocess.

    Composes a ``SubprocessManager`` internally to handle the actual
    spawn / kill / signal operations. Auto-detects OS-specific quirks:

    - Windows: appends ``.exe`` when the command has no extension.
    - PATH resolution: searches ``PATH`` for the executable.
    - Platform-appropriate signal handling for stop/kill.
    """

    def __init__(
        self,
        process_manager: SubprocessManager | None = None,
    ) -> None:
        self._proc_mgr = process_manager or SubprocessManager()

    # ── Launch ────────────────────────────────────────────────────────────────

    async def launch(
        self,
        runtime: Runtime,
        **extra_env: str,
    ) -> LaunchResult:
        """Launch a Runtime as a subprocess.

        Uses the ``Runtime`` fields:
        - ``command``: the executable (with platform resolution)
        - ``arguments``: CLI arguments
        - ``working_directory``: process cwd
        - ``environment``: environment variables (merged with current env)

        Args:
            runtime: The Runtime config to translate into a process.
            **extra_env: Additional environment variables to merge.

        Returns:
            A ``LaunchResult`` with the PID and handle.

        Raises:
            FileNotFoundError: If the command cannot be found on the system.
            RuntimeError: If the process fails to start for another reason.
        """
        resolved_cmd = await self._resolve_runtime_command(runtime)
        cwd = await self._resolve_working_directory(runtime)
        env = self._build_environment(runtime, **extra_env)

        handle = await self._proc_mgr.spawn(
            name=runtime.name,
            command=resolved_cmd,
            args=runtime.arguments,
            cwd=cwd,
            env=env,
        )

        log.info(
            "runtime launched",
            runtime_id=runtime.id,
            name=runtime.name,
            pid=handle.pid,
            command=resolved_cmd,
            cwd=cwd,
        )

        return LaunchResult(
            pid=handle.pid,
            handle=handle,
            runtime_id=runtime.id,
            runtime_name=runtime.name,
            command=resolved_cmd,
            working_directory=cwd,
        )

    # ── Stop ──────────────────────────────────────────────────────────────────

    async def stop(
        self,
        pid: int,
        timeout: float = 30.0,
    ) -> bool:
        """Gracefully stop a launched process.

        Sends SIGTERM (or equivalent), then waits up to *timeout* seconds
        for the process to exit. If the process does not exit within the
        timeout, it is force-killed.

        Args:
            pid: Process ID to stop.
            timeout: Seconds to wait for graceful shutdown.

        Returns:
            ``True`` if the process was stopped (or already dead).
        """
        handle = await self._proc_mgr.get_handle(pid)
        if handle is None:
            log.warning("stop called for unknown pid", pid=pid)
            return False

        status = await self._proc_mgr.get_status(pid)
        if status != ProcessStatus.RUNNING:
            return True

        await self._proc_mgr.terminate(pid)

        # Wait for graceful shutdown
        exit_code = await self._proc_mgr.wait(pid, timeout=timeout)
        if exit_code is None:
            # Timed out — force kill
            log.warning(
                "graceful stop timed out, force killing",
                pid=pid,
                timeout=timeout,
            )
            await self._proc_mgr.kill(pid, "SIGKILL")
            await self._proc_mgr.wait(pid, timeout=10)

        log.info("runtime stopped", pid=pid)
        return True

    # ── Kill ──────────────────────────────────────────────────────────────────

    async def kill(self, pid: int) -> bool:
        """Force-kill a launched process immediately."""
        result = await self._proc_mgr.kill(pid, "SIGKILL")
        if result:
            log.info("runtime killed", pid=pid)
        return result

    # ── Resolve helpers ───────────────────────────────────────────────────────

    async def _resolve_runtime_command(self, runtime: Runtime) -> str:
        """Resolve the runtime's command to a concrete executable path.

        Priority:
        1. ``runtime.binary_path`` or ``runtime.executable`` (if set)
        2. ``runtime.command`` (as written)
        3. Platform-specific PATH resolution (e.g., .exe on Windows)

        For well-known runtime types, known binary names are tried.
        """
        # Priority 1: explicit binary/executable path
        explicit = runtime.binary_path or runtime.executable
        if explicit:
            return self._resolve_path(explicit)

        # Priority 2: command field
        cmd = runtime.command.strip()
        if not cmd:
            raise ValueError(f"Runtime {runtime.id!r} ({runtime.name}) has no command configured")

        return self._resolve_path(cmd)

    def _resolve_path(self, cmd: str) -> str:
        """Resolve a command path, handling Windows .exe suffix."""
        if os.path.isabs(cmd):
            if _is_windows() and not cmd.lower().endswith(".exe"):
                exe_candidate = cmd + ".exe"
                if os.path.isfile(exe_candidate):
                    return exe_candidate
            return cmd

        # If command already has .exe on Windows, return as-is
        if _is_windows() and cmd.lower().endswith(".exe"):
            return cmd

        # On Windows, append .exe if not present
        if _is_windows():
            cmd_exe = cmd + ".exe"
            path_dirs = os.environ.get("PATH", "").split(os.pathsep)
            for d in path_dirs:
                candidate = os.path.join(d, cmd_exe)
                if os.path.isfile(candidate):
                    return candidate
            # Check if the bare command exists
            for d in path_dirs:
                candidate = os.path.join(d, cmd)
                if os.path.isfile(candidate):
                    return candidate
            return cmd_exe  # let spawn time raise a proper error

        return cmd

    async def _resolve_working_directory(self, runtime: Runtime) -> str | None:
        """Resolve the working directory for the runtime process.

        Falls back to the runtime's discovery binary_path directory if
        no explicit ``working_directory`` is set.
        """
        if runtime.working_directory:
            wd = os.path.expanduser(runtime.working_directory)
            if os.path.isdir(wd):
                return wd
            log.warning(
                "working_directory does not exist",
                runtime_id=runtime.id,
                working_directory=wd,
            )
            return wd

        # Fallback: parent directory of the binary
        binary = runtime.binary_path or runtime.executable
        if binary:
            bdir = os.path.dirname(os.path.abspath(binary))
            if os.path.isdir(bdir):
                return bdir

        return None

    def _build_environment(
        self,
        runtime: Runtime,
        **extra_env: str,
    ) -> dict[str, str]:
        """Build the merged environment dict for the process."""
        env: dict[str, str] = {}
        env.update(os.environ)
        env.update(runtime.environment or {})
        env.update(extra_env)
        return env

    # ── Delegated access ──────────────────────────────────────────────────────

    @property
    def process_manager(self) -> SubprocessManager:
        """Access to the underlying process manager."""
        return self._proc_mgr

    async def is_running(self, pid: int) -> bool:
        """Check if a launched process is still running."""
        status = await self._proc_mgr.get_status(pid)
        return status == ProcessStatus.RUNNING

    async def wait(self, pid: int, timeout: float | None = None) -> int | None:
        """Wait for a process to exit and return its exit code."""
        return await self._proc_mgr.wait(pid, timeout=timeout)

    async def get_handle(self, pid: int) -> SubprocessHandle | None:
        """Get the process handle for a PID."""
        return await self._proc_mgr.get_handle(pid)

    async def get_children(self, pid: int) -> list[int]:
        """Get child process PIDs."""
        return await self._proc_mgr.get_children(pid)
