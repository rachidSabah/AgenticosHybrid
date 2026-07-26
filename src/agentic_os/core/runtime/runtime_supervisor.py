"""Runtime supervisor — background watch loop for all registered runtimes.

Runs :mod:`asyncio` tasks that periodically check:

* Process liveness (via :class:`HealthManager`)
* Heartbeat recency (configurable threshold, default 30 s)
* Resource usage (CPU / memory warnings)

On crash detection the supervisor delegates to :class:`RuntimeRecovery`.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from agentic_os.core.runtime.runtime import Runtime, RuntimeHealth, RuntimeStatus
from agentic_os.core.runtime.runtime_events import (
    publish_runtime_crashed,
    publish_runtime_health_changed,
    publish_runtime_heartbeat,
)
from agentic_os.core.runtime.runtime_recovery import RuntimeRecovery
from agentic_os.infrastructure.logging import get_logger

__all__ = [
    "HealthManager",
    "RuntimeSupervisor",
]

log = get_logger("runtime.supervisor")

DEFAULT_HEARTBEAT_THRESHOLD = 30.0  # seconds
DEFAULT_WATCH_INTERVAL = 10.0  # seconds


class HealthManager:
    """Pluggable health checker for runtime process liveness.

    In production, subclasses would integrate with a process supervisor,
    PID-file monitor, or health-check endpoint.  The default
    implementation treats a runtime as "alive" when its status is not a
    terminal / dead state.
    """

    async def is_alive(self, runtime: Runtime) -> bool:
        """Check if *runtime*'s process appears to be alive.

        Args:
            runtime: The :class:`Runtime` instance to check.

        Returns:
            ``True`` if the process seems alive.
        """
        # When a PID is unavailable we rely on heartbeat as a proxy.
        return runtime.status not in (
            RuntimeStatus.STOPPED,
            RuntimeStatus.CRASHED,
            RuntimeStatus.FAILED,
            RuntimeStatus.DISCONNECTED,
        )


class RuntimeSupervisor:
    """Background watch loop for registered runtimes.

    Typical usage::

        supervisor = RuntimeSupervisor(recovery, bus=my_bus)
        supervisor.register("rt-1", my_runtime)
        supervisor.start("rt-1")
        ...
        await supervisor.stop_all()
    """

    def __init__(
        self,
        recovery: RuntimeRecovery,
        health_manager: HealthManager | None = None,
        bus: Any = None,
        heartbeat_threshold: float = DEFAULT_HEARTBEAT_THRESHOLD,
        watch_interval: float = DEFAULT_WATCH_INTERVAL,
    ) -> None:
        self._recovery = recovery
        self._health = health_manager or HealthManager()
        self._bus = bus
        self._heartbeat_threshold = heartbeat_threshold
        self._watch_interval = watch_interval

        # runtime_id -> Runtime  (caller keeps the reference alive)
        self._runtimes: dict[str, Runtime] = {}
        # runtime_id -> asyncio.Task  (watch-loop tasks)
        self._watch_tasks: dict[str, asyncio.Task[None]] = {}
        self._running = False

    # ── Registration ────────────────────────────────────────────────────────

    def register(self, runtime_id: str, runtime: Runtime) -> None:
        """Register *runtime* for supervision.

        Does NOT start the watch loop — call :meth:`start` separately.
        """
        self._runtimes[runtime_id] = runtime
        log.info("supervisor.registered", runtime_id=runtime_id)

    async def unregister(self, runtime_id: str) -> None:
        """Unregister *runtime_id* and stop its watch loop if running."""
        await self.stop(runtime_id)
        self._runtimes.pop(runtime_id, None)
        log.info("supervisor.unregistered", runtime_id=runtime_id)

    # ── Watch lifecycle ─────────────────────────────────────────────────────

    def start(self, runtime_id: str) -> bool:
        """Start the background watch loop for *runtime_id*.

        Args:
            runtime_id: The runtime to watch.

        Returns:
            ``True`` if the loop was started (or already running).
        """
        if runtime_id not in self._runtimes:
            log.warning("supervisor.start_skipped", runtime_id=runtime_id, reason="not registered")
            return False

        if runtime_id in self._watch_tasks:
            log.debug("supervisor.already_watching", runtime_id=runtime_id)
            return True

        task = asyncio.create_task(self._watch_loop(runtime_id))
        self._watch_tasks[runtime_id] = task
        log.info("supervisor.started", runtime_id=runtime_id)
        return True

    async def stop(self, runtime_id: str) -> None:
        """Stop the watch loop for *runtime_id* (cancels the task)."""
        task = self._watch_tasks.pop(runtime_id, None)
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            log.info("supervisor.stopped", runtime_id=runtime_id)

    async def stop_all(self) -> None:
        """Stop every running watch loop."""
        self._running = False
        for rid in list(self._watch_tasks.keys()):
            await self.stop(rid)
        log.info("supervisor.all_stopped")

    def is_watching(self, runtime_id: str) -> bool:
        """Return ``True`` if *runtime_id* currently has a watch loop."""
        return runtime_id in self._watch_tasks

    # ── Background watch loop ───────────────────────────────────────────────

    async def _watch_loop(self, runtime_id: str) -> None:
        """Continuously check runtime health at ``_watch_interval``."""
        self._running = True
        log.debug("supervisor.watch_loop_started", runtime_id=runtime_id)

        try:
            while self._running:
                runtime = self._runtimes.get(runtime_id)
                if runtime is None:
                    log.warning("supervisor.runtime_gone", runtime_id=runtime_id)
                    break

                await self._check_heartbeat(runtime)
                await self._check_liveness(runtime)
                await self._check_resources(runtime)

                await asyncio.sleep(self._watch_interval)
        except asyncio.CancelledError:
            pass
        except Exception:
            log.exception("supervisor.watch_loop_crashed", runtime_id=runtime_id)
        finally:
            self._watch_tasks.pop(runtime_id, None)
            log.debug("supervisor.watch_loop_ended", runtime_id=runtime_id)

    # ── Health checks ───────────────────────────────────────────────────────

    async def _check_heartbeat(self, runtime: Runtime) -> None:
        """Verify heartbeat recency and emit health events."""
        if runtime.heartbeat is None:
            return

        now = datetime.now(UTC)
        age = (now - runtime.heartbeat).total_seconds()

        await publish_runtime_heartbeat(
            self._bus,
            runtime.id,
            runtime.name,
            age_seconds=round(age, 2),
        )

        if age > self._heartbeat_threshold:
            old_health = runtime.health.value
            runtime.health = RuntimeHealth.UNHEALTHY
            runtime.last_error = f"Heartbeat stale ({age:.1f}s > {self._heartbeat_threshold}s)"
            await publish_runtime_health_changed(
                self._bus,
                runtime.id,
                runtime.name,
                old_health=old_health,
                new_health=runtime.health.value,
                reason=runtime.last_error,
            )
            log.warning(
                "supervisor.heartbeat_stale",
                runtime_id=runtime.id,
                age_seconds=round(age, 2),
                threshold=self._heartbeat_threshold,
            )

            # Trigger recovery
            if runtime.status not in (RuntimeStatus.STOPPED, RuntimeStatus.FAILED):
                runtime.status = RuntimeStatus.CRASHED
                await self._recovery.attempt_recovery(runtime)

        elif runtime.health != RuntimeHealth.HEALTHY:
            old_health = runtime.health.value
            runtime.health = RuntimeHealth.HEALTHY
            await publish_runtime_health_changed(
                self._bus,
                runtime.id,
                runtime.name,
                old_health=old_health,
                new_health=runtime.health.value,
            )

    async def _check_liveness(self, runtime: Runtime) -> None:
        """Check if the runtime's process is alive."""
        alive = await self._health.is_alive(runtime)
        if not alive and runtime.status not in (
            RuntimeStatus.STOPPED,
            RuntimeStatus.CRASHED,
            RuntimeStatus.FAILED,
            RuntimeStatus.DISCOVERED,
            RuntimeStatus.DISCONNECTED,
        ):
            log.warning(
                "supervisor.process_dead",
                runtime_id=runtime.id,
                pid=runtime.pid,
                status=runtime.status.value,
            )
            old_health = runtime.health.value
            runtime.health = RuntimeHealth.UNHEALTHY
            runtime.status = RuntimeStatus.CRASHED
            runtime.last_error = "Process is no longer alive"

            await publish_runtime_crashed(
                self._bus,
                runtime.id,
                runtime.name,
                error=runtime.last_error,
                pid=runtime.pid,
            )
            await publish_runtime_health_changed(
                self._bus,
                runtime.id,
                runtime.name,
                old_health=old_health,
                new_health=runtime.health.value,
            )
            await self._recovery.attempt_recovery(runtime)

    async def _check_resources(self, runtime: Runtime) -> None:
        """Log warnings when resource usage exceeds thresholds."""
        if runtime.cpu > 90.0:
            log.warning(
                "supervisor.cpu_high",
                runtime_id=runtime.id,
                cpu_percent=runtime.cpu,
            )
        if runtime.memory > 1024:  # 1 GB
            log.warning(
                "supervisor.memory_high",
                runtime_id=runtime.id,
                memory_mb=runtime.memory,
            )
