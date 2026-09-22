"""Kernel Daemon — process lifecycle, safe execution, and graceful shutdown."""

from __future__ import annotations

import asyncio
import os
import signal
import sys
import time
from typing import Any

from agentic_os.infrastructure.logging import get_logger

log = get_logger("server.daemon")

VERSION = "1.0.0-rc10"


class KernelDaemon:
    """Core Kernel Daemon managing OS process lifecycle, non-blocking execution, and shutdown."""

    def __init__(self) -> None:
        self.start_time: float = time.time()
        self._child_pids: set[int] = set()
        self._lock: asyncio.Lock = asyncio.Lock()
        self._stopping: bool = False

    @property
    def uptime_sec(self) -> float:
        return round(time.time() - self.start_time, 2)

    def track_pid(self, pid: int) -> None:
        if pid > 0:
            self._child_pids.add(pid)

    def untrack_pid(self, pid: int) -> None:
        self._child_pids.discard(pid)

    async def exec_process(
        self,
        cmd: str,
        args: list[str] | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        """Execute a process asynchronously with non-blocking pipe reads and strict timeout."""
        args = args or []
        merged_env = {**os.environ, **(env or {})}
        t0 = time.perf_counter()

        try:
            proc = await asyncio.create_subprocess_exec(
                cmd,
                *args,
                cwd=cwd,
                env=merged_env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            pid = proc.pid or 0
            if pid:
                self.track_pid(pid)

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
                duration_ms = round((time.perf_counter() - t0) * 1000, 2)
                return {
                    "pid": pid,
                    "returncode": proc.returncode,
                    "stdout": stdout_bytes.decode("utf-8", errors="replace"),
                    "stderr": stderr_bytes.decode("utf-8", errors="replace"),
                    "duration_ms": duration_ms,
                    "timeout": False,
                }
            except TimeoutError:
                await self.kill_pid(pid, force=True)
                return {
                    "pid": pid,
                    "returncode": -1,
                    "stdout": "",
                    "stderr": f"Process exceeded timeout of {timeout}s",
                    "duration_ms": round((time.perf_counter() - t0) * 1000, 2),
                    "timeout": True,
                }
            finally:
                if pid:
                    self.untrack_pid(pid)
        except Exception as exc:
            return {
                "pid": 0,
                "returncode": -1,
                "stdout": "",
                "stderr": str(exc),
                "duration_ms": round((time.perf_counter() - t0) * 1000, 2),
                "timeout": False,
            }

    async def kill_pid(self, pid: int, force: bool = False) -> None:
        """Terminate or kill a process by PID."""
        if not pid:
            return
        if sys.platform == "win32":
            flags = ["/F", "/T"] if force else ["/T"]
            try:
                proc = await asyncio.create_subprocess_exec(
                    "taskkill",
                    *flags,
                    "/PID",
                    str(pid),
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await proc.wait()
            except Exception as exc:
                log.warning("taskkill error", pid=pid, error=str(exc))
        else:
            sig = signal.SIGKILL if force else signal.SIGTERM
            try:
                os.kill(pid, sig)
            except ProcessLookupError:
                pass
            except Exception as exc:
                log.warning("kill error", pid=pid, error=str(exc))

    async def shutdown(self) -> None:
        """Gracefully shutdown all child processes: SIGTERM -> wait 3s -> SIGKILL."""
        async with self._lock:
            if self._stopping:
                return
            self._stopping = True

        pids = list(self._child_pids)
        if not pids:
            log.info("No active child processes to terminate")
            return

        log.info("Gracefully stopping child processes", pids=pids)

        # Step 1: Send gentle termination signal
        for pid in pids:
            await self.kill_pid(pid, force=False)

        # Wait 3 seconds for exit
        await asyncio.sleep(3.0)

        # Step 2: Force kill remaining
        for pid in list(self._child_pids):
            await self.kill_pid(pid, force=True)

        self._child_pids.clear()
        log.info("All child processes cleanly terminated")

    def health(self) -> dict[str, Any]:
        """Return standardized daemon health dict."""
        return {
            "status": "ok",
            "uptime_sec": self.uptime_sec,
            "version": VERSION,
            "event_loop": "running",
        }


# Global singleton daemon instance
kernel_daemon = KernelDaemon()
