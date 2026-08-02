"""Health Manager — periodic health checks for runtime processes.

Monitors process liveness, resource usage, uptime, and heartbeat recency.
Emits callbacks on health state changes and supports configurable check
intervals per runtime.
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from agentic_os.core.runtime.runtime import Runtime, RuntimeHealth, RuntimeMetrics
from agentic_os.core.runtime.runtime_process import SubprocessManager
from agentic_os.infrastructure.logging import get_logger

log = get_logger("runtime.health")

__all__ = [
    "HealthCheckResult",
    "HealthManager",
]


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _is_windows() -> bool:
    return sys.platform == "win32"


HealthChangeCallback = Callable[
    [str, RuntimeHealth, RuntimeHealth, dict[str, Any]],
    Coroutine[Any, Any, None] | None,
]
"""Signature: async def callback(runtime_id, old_health, new_health, details)"""


@dataclass
class HealthCheckResult:
    """Result of a single health check cycle."""

    runtime_id: str
    runtime_name: str
    health: RuntimeHealth
    pid_alive: bool
    uptime_seconds: float
    cpu_percent: float = 0.0
    memory_mb: float = 0.0
    last_heartbeat: datetime | None = None
    heartbeat_recency: float | None = None
    errors: list[str] = field(default_factory=list)
    checked_at: datetime = field(default_factory=_utcnow)

    @property
    def healthy(self) -> bool:
        return self.health == RuntimeHealth.HEALTHY

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_id": self.runtime_id,
            "runtime_name": self.runtime_name,
            "health": self.health.value,
            "pid_alive": self.pid_alive,
            "uptime_seconds": self.uptime_seconds,
            "cpu_percent": self.cpu_percent,
            "memory_mb": self.memory_mb,
            "last_heartbeat": self.last_heartbeat.isoformat() if self.last_heartbeat else None,
            "heartbeat_recency": self.heartbeat_recency,
            "errors": self.errors,
            "checked_at": self.checked_at.isoformat(),
        }

    def to_metrics(self) -> RuntimeMetrics:
        """Convert to a RuntimeMetrics snapshot."""
        return RuntimeMetrics(
            cpu_percent=self.cpu_percent,
            memory_mb=self.memory_mb,
            uptime_seconds=self.uptime_seconds,
        )


def _get_process_cpu_memory(pid: int) -> tuple[float, float]:
    """Get CPU percent and memory (MB) for a process.

    Returns (0.0, 0.0) on platforms without process stats support.
    """
    cpu = 0.0
    mem_mb = 0.0
    try:
        if _is_windows():
            # Use tasklist /FI on Windows for basic info
            pass  # psutil not available; return 0 for now
        else:
            # Linux /proc/<pid>/stat and /proc/<pid>/status
            pid = int(pid)

            # Read CPU ticks from /proc/<pid>/stat
            try:
                with open(f"/proc/{pid}/stat") as f:
                    parts = f.read().split()
                    utime = int(parts[13]) if len(parts) > 13 else 0
                    stime = int(parts[14]) if len(parts) > 14 else 0
                    total_ticks = utime + stime
                    # Approximate CPU percent (simplified)
                    # Real impl would diff over time, but for single shot:
                    cpu = min(total_ticks / 100.0, 100.0)
            except (FileNotFoundError, ValueError, IndexError):
                pass

            # Read memory from /proc/<pid>/status
            try:
                with open(f"/proc/{pid}/status") as f:
                    for line in f:
                        if line.startswith("VmRSS:"):
                            parts = line.split()
                            if len(parts) >= 2:
                                mem_kb = int(parts[1])
                                mem_mb = mem_kb / 1024.0
                            break
            except (FileNotFoundError, ValueError):
                pass
    except Exception:
        log.debug("could not read process stats", pid=pid)

    return cpu, mem_mb


class HealthManager:
    """Periodic health monitoring for runtime processes.

    Runs configurable-interval health checks per runtime. Each check
    evaluates:

    - Process liveness (PID exists)
    - Uptime (time since process start)
    - Resource usage (CPU %, memory MB) where available
    - Heartbeat recency (how long since last heartbeat)

    State changes are reported via an optional async callback.
    All mutable state is thread-safe via asyncio.Lock.
    """

    def __init__(
        self,
        process_manager: SubprocessManager | None = None,
        health_interval: float = 5.0,
        heartbeat_timeout: float = 30.0,
    ) -> None:
        self._proc_mgr = process_manager or SubprocessManager()
        self._lock: asyncio.Lock = asyncio.Lock()
        # runtime_id -> HealthState
        self._states: dict[str, _HealthState] = {}
        # runtime_id -> asyncio.Task (monitoring task)
        self._tasks: dict[str, asyncio.Task] = {}
        # runtime_id -> callback
        self._callbacks: dict[str, HealthChangeCallback] = {}
        self._default_interval = health_interval
        self._heartbeat_timeout = heartbeat_timeout

    # ── Core check ────────────────────────────────────────────────────────────

    async def check(self, runtime: Runtime) -> HealthCheckResult:
        """Perform a single health check for a runtime.

        Evaluates process liveness, uptime, resource usage, and heartbeat
        recency against the given ``Runtime`` model.

        Returns a ``HealthCheckResult`` — does NOT update internal state
        or fire callbacks (use ``start_monitoring`` for ongoing checks).
        """
        errors: list[str] = []
        pid_alive = False
        cpu = 0.0
        mem_mb = 0.0
        uptime = 0.0

        pid = runtime.pid
        if pid is not None and pid > 0:
            pid_alive = await self._is_pid_alive(pid)
            if pid_alive:
                cpu, mem_mb = _get_process_cpu_memory(pid)
                # Compute uptime
                if runtime.started_at:
                    uptime = (_utcnow() - runtime.started_at).total_seconds()
            else:
                errors.append("process not found")
        else:
            errors.append("no pid set")

        # Heartbeat recency
        heartbeat_recency: float | None = None
        if runtime.heartbeat:
            delta = _utcnow() - runtime.heartbeat
            heartbeat_recency = delta.total_seconds()

        # Determine health
        health = self._determine_health(pid_alive, heartbeat_recency, errors)

        return HealthCheckResult(
            runtime_id=runtime.id,
            runtime_name=runtime.name,
            health=health,
            pid_alive=pid_alive,
            uptime_seconds=uptime,
            cpu_percent=cpu,
            memory_mb=mem_mb,
            last_heartbeat=runtime.heartbeat,
            heartbeat_recency=heartbeat_recency,
            errors=errors,
        )

    def _determine_health(
        self,
        pid_alive: bool,
        heartbeat_recency: float | None,
        errors: list[str],
    ) -> RuntimeHealth:
        """Determine health status from check signals."""
        if not pid_alive:
            return RuntimeHealth.UNHEALTHY if errors else RuntimeHealth.STOPPED

        if errors:
            return RuntimeHealth.DEGRADED

        if heartbeat_recency is not None and heartbeat_recency > self._heartbeat_timeout:
            return RuntimeHealth.DEGRADED

        return RuntimeHealth.HEALTHY

    # ── Monitoring ────────────────────────────────────────────────────────────

    async def start_monitoring(
        self,
        runtime_id: str,
        runtime_getter: Callable[[], Runtime | None],
        interval: float | None = None,
    ) -> bool:
        """Start periodic health monitoring for a runtime.

        Spawns an ``asyncio.Task`` that runs health checks every *interval*
        seconds. On health state changes, the registered callback (if any)
        is invoked.

        Args:
            runtime_id: The runtime to monitor.
            runtime_getter: A callable that returns the current ``Runtime``
                state (or ``None`` if the runtime has been removed).
            interval: Check interval in seconds (default: 5s).

        Returns:
            ``True`` if monitoring was started (or already running).
        """
        async with self._lock:
            if runtime_id in self._tasks and not self._tasks[runtime_id].done():
                return True  # already monitored

            state = _HealthState(
                runtime_id=runtime_id,
                interval=interval or self._default_interval,
            )
            self._states[runtime_id] = state

        task = asyncio.create_task(
            self._monitor_loop(runtime_id, runtime_getter, state),
            name=f"health-check-{runtime_id}",
        )
        async with self._lock:
            self._tasks[runtime_id] = task

        log.info(
            "health monitoring started",
            runtime_id=runtime_id,
            interval=interval or self._default_interval,
        )
        return True

    async def stop_monitoring(self, runtime_id: str) -> bool:
        """Stop periodic health monitoring for a runtime.

        Cancels the monitoring task and removes internal state.

        Returns ``True`` if monitoring was active and now stopped.
        """
        async with self._lock:
            task = self._tasks.pop(runtime_id, None)
            self._states.pop(runtime_id, None)

        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        log.info("health monitoring stopped", runtime_id=runtime_id)
        return task is not None

    async def _monitor_loop(
        self,
        runtime_id: str,
        runtime_getter: Callable[[], Runtime | None],
        state: _HealthState,
    ) -> None:
        """Background loop: run health checks at interval."""
        while True:
            try:
                await asyncio.sleep(state.interval)

                runtime = runtime_getter()
                if runtime is None:
                    log.info(
                        "runtime removed, stopping monitoring",
                        runtime_id=runtime_id,
                    )
                    break

                result = await self._perform_monitored_check(runtime, state)
                if result is None:
                    continue

                # Fire callback on health change
                if result.health != state.last_health:
                    old = state.last_health
                    state.last_health = result.health
                    await self._fire_health_change(
                        runtime_id,
                        old,
                        result.health,
                        result.to_dict(),
                    )

            except asyncio.CancelledError:
                log.debug("monitoring cancelled", runtime_id=runtime_id)
                break
            except Exception:
                log.exception(
                    "health check error",
                    runtime_id=runtime_id,
                )

        # Cleanup
        async with self._lock:
            self._tasks.pop(runtime_id, None)
            self._states.pop(runtime_id, None)

    async def _perform_monitored_check(
        self,
        runtime: Runtime,
        state: _HealthState,
    ) -> HealthCheckResult | None:
        """Run a single health check using tracked state.

        Compares against the last known health to detect transitions.
        """
        errors: list[str] = []
        pid_alive = False
        cpu = 0.0
        mem_mb = 0.0
        uptime = 0.0

        pid = runtime.pid
        if pid is not None and pid > 0:
            pid_alive = await self._is_pid_alive(pid)
            if pid_alive:
                cpu, mem_mb = _get_process_cpu_memory(pid)
                if runtime.started_at:
                    uptime = (_utcnow() - runtime.started_at).total_seconds()
            else:
                errors.append("process not found")
        else:
            errors.append("no pid set")

        heartbeat_recency: float | None = None
        if runtime.heartbeat:
            delta = _utcnow() - runtime.heartbeat
            heartbeat_recency = delta.total_seconds()

        health = self._determine_health(pid_alive, heartbeat_recency, errors)

        return HealthCheckResult(
            runtime_id=runtime.id,
            runtime_name=runtime.name,
            health=health,
            pid_alive=pid_alive,
            uptime_seconds=uptime,
            cpu_percent=cpu,
            memory_mb=mem_mb,
            last_heartbeat=runtime.heartbeat,
            heartbeat_recency=heartbeat_recency,
            errors=errors,
        )

    # ── PID Aliveness ─────────────────────────────────────────────────────────

    async def _is_pid_alive(self, pid: int) -> bool:
        """Check if a PID exists on the system."""
        try:
            if _is_windows():
                # Use tasklist /FI to check for the PID
                proc = await asyncio.create_subprocess_exec(
                    "tasklist",
                    "/FI",
                    f"PID eq {pid}",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                stdout, _ = await proc.communicate()
                # tasklist output includes the PID if the process exists
                output = stdout.decode("utf-8", errors="replace")
                return str(pid) in output and "INFO: No tasks" not in output
            else:
                # POSIX: os.kill with signal 0
                os.kill(pid, 0)
                return True
        except (ProcessLookupError, PermissionError, OSError):
            return False

    # ── Callbacks ─────────────────────────────────────────────────────────────

    def set_callback(
        self,
        runtime_id: str,
        callback: HealthChangeCallback | None,
    ) -> None:
        """Register (or clear) a health-change callback.

        The callback is invoked as:
            callback(runtime_id, old_health, new_health, details_dict)
        It may be a coroutine or a plain callable.
        """
        if callback is None:
            self._callbacks.pop(runtime_id, None)
        else:
            self._callbacks[runtime_id] = callback

    async def _fire_health_change(
        self,
        runtime_id: str,
        old_health: RuntimeHealth,
        new_health: RuntimeHealth,
        details: dict[str, Any],
    ) -> None:
        """Invoke the health change callback (if registered)."""
        callback = self._callbacks.get(runtime_id)
        if callback is None:
            return
        try:
            result = callback(runtime_id, old_health, new_health, details)
            if result is not None:
                await result
        except Exception:
            log.exception(
                "health change callback failed",
                runtime_id=runtime_id,
                old_health=old_health.value,
                new_health=new_health.value,
            )

    # ── Status ────────────────────────────────────────────────────────────────

    async def is_monitoring(self, runtime_id: str) -> bool:
        """Check if health monitoring is active for a runtime."""
        async with self._lock:
            task = self._tasks.get(runtime_id)
            return task is not None and not task.done()

    async def list_monitored(self) -> list[str]:
        """Return all runtime IDs currently being monitored."""
        async with self._lock:
            return [rid for rid, t in self._tasks.items() if not t.done()]

    async def stop_all(self) -> int:
        """Stop monitoring all runtimes.

        Returns the number of monitors stopped.
        """
        async with self._lock:
            rids = list(self._tasks.keys())
        count = 0
        for rid in rids:
            if await self.stop_monitoring(rid):
                count += 1
        return count

    async def get_last_health(self, runtime_id: str) -> RuntimeHealth | None:
        """Get the last known health for a monitored runtime."""
        async with self._lock:
            state = self._states.get(runtime_id)
            return state.last_health if state else None


@dataclass
class _HealthState:
    """Internal state for a monitored runtime."""

    runtime_id: str
    interval: float
    last_health: RuntimeHealth = RuntimeHealth.UNKNOWN
    last_check: datetime | None = None
    consecutive_failures: int = 0
