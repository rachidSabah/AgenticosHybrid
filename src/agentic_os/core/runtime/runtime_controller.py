"""Runtime Controller — orchestrates the full lifecycle of Runtime instances."""

from __future__ import annotations

import asyncio
import platform
from datetime import UTC, datetime
from typing import Any

from agentic_os.core.runtime.runtime import Runtime, RuntimeHealth, RuntimeStatus
from agentic_os.core.runtime.runtime_events import (
    publish_runtime_crashed,
    publish_runtime_ready,
    publish_runtime_restarted,
    publish_runtime_started,
    publish_runtime_stopped,
)
from agentic_os.core.runtime.runtime_registry import RuntimeRegistry
from agentic_os.infrastructure.logging import get_logger

log = get_logger("runtime.controller")

_GRACEFUL_TIMEOUT = 30.0


class RuntimeController:
    """Orchestrates the lifecycle of Runtime instances.

    Coordinates between the registry, launcher, supervisor, and session
    manager to provide clean start/stop/restart/kill semantics.
    """

    def __init__(
        self,
        registry: RuntimeRegistry,
        launcher: Any | None = None,
        supervisor: Any | None = None,
        session_manager: Any | None = None,
        bus: Any | None = None,
    ) -> None:
        self._registry = registry
        self._launcher = launcher
        self._supervisor = supervisor
        self._session_manager = session_manager
        self._bus = bus
        self._lock: asyncio.Lock = asyncio.Lock()

    def _utcnow(self) -> datetime:
        return datetime.now(UTC)

    # ── Lifecycle ───────────────────────────────────────────────────────

    async def start(self, runtime_id: str) -> Runtime:
        """Transition a runtime from STARTING -> READY.

        Updates status, publishes events, and updates metrics.
        Returns the updated Runtime (internal reference).
        """
        async with self._lock:
            runtime = await self._registry.get_raw(runtime_id)
            if runtime is None:
                raise ValueError(f"Runtime not found: {runtime_id}")

            if runtime.status not in (
                RuntimeStatus.DISCOVERED,
                RuntimeStatus.REGISTERED,
                RuntimeStatus.STOPPED,
                RuntimeStatus.FAILED,
                RuntimeStatus.CRASHED,
            ):
                raise RuntimeError(
                    f"Cannot start runtime {runtime_id} from status {runtime.status.value}"
                )

            # Transition to STARTING
            runtime.status = RuntimeStatus.STARTING
            runtime.health = RuntimeHealth.STARTING
            runtime.started_at = self._utcnow()
            await self._registry.update(runtime)

            await publish_runtime_started(self._bus, runtime_id, runtime.name, pid=runtime.pid)

            try:
                # Delegate to launcher if available
                if self._launcher is not None and hasattr(self._launcher, "launch"):
                    launched = await self._launcher.launch(runtime)
                    runtime.pid = launched.pid if hasattr(launched, "pid") else launched.get("pid")

                # Transition to READY
                runtime.status = RuntimeStatus.READY
                runtime.health = RuntimeHealth.HEALTHY
                runtime.uptime = 0.0
                await self._registry.update(runtime)

                await publish_runtime_ready(
                    self._bus,
                    runtime_id,
                    runtime.name,
                    pid=runtime.pid,
                    type=runtime.type.value,
                )

                log.info(
                    "Runtime started",
                    runtime_id=runtime_id,
                    name=runtime.name,
                    pid=runtime.pid,
                )

            except Exception as exc:
                runtime.status = RuntimeStatus.FAILED
                runtime.health = RuntimeHealth.UNHEALTHY
                runtime.last_error = str(exc)
                await self._registry.update(runtime)
                await publish_runtime_crashed(
                    self._bus,
                    runtime_id,
                    runtime.name,
                    error=str(exc),
                )
                log.error("Runtime start failed", runtime_id=runtime_id, error=str(exc))
                raise

            return runtime

    async def stop(self, runtime_id: str, force: bool = False) -> Runtime:
        """Gracefully stop a runtime with 30s timeout, then force-kill.

        Returns the updated Runtime.
        """
        async with self._lock:
            runtime = await self._registry.get_raw(runtime_id)
            if runtime is None:
                raise ValueError(f"Runtime not found: {runtime_id}")

            if runtime.status in (RuntimeStatus.STOPPED, RuntimeStatus.STOPPING):
                log.warning("Runtime already stopping/stopped", runtime_id=runtime_id)
                return runtime

            # Transition to STOPPING
            runtime.status = RuntimeStatus.STOPPING
            await self._registry.update(runtime)

            exit_code: int | None = None
            try:
                if force:
                    exit_code = await self._force_kill(runtime)
                else:
                    # Graceful stop with timeout
                    try:
                        async with asyncio.timeout(_GRACEFUL_TIMEOUT):
                            exit_code = await self._graceful_stop(runtime)
                    except TimeoutError:
                        log.warning(
                            "Graceful stop timed out, force killing",
                            runtime_id=runtime_id,
                        )
                        exit_code = await self._force_kill(runtime)

            except Exception as exc:
                log.error("Stop error", runtime_id=runtime_id, error=str(exc))
                exit_code = -1

            runtime.status = RuntimeStatus.STOPPED
            runtime.health = RuntimeHealth.STOPPED
            runtime.last_exit_code = exit_code
            runtime.pid = None
            await self._registry.update(runtime)

            await publish_runtime_stopped(
                self._bus,
                runtime_id,
                runtime.name,
                exit_code=exit_code,
            )

            log.info(
                "Runtime stopped",
                runtime_id=runtime_id,
                name=runtime.name,
                exit_code=exit_code,
            )
            return runtime

    async def restart(self, runtime_id: str) -> Runtime:
        """Restart a runtime by stopping then starting."""
        runtime = await self._registry.get_raw(runtime_id)
        if runtime is None:
            raise ValueError(f"Runtime not found: {runtime_id}")

        old_status = runtime.status
        log.info("Restarting runtime", runtime_id=runtime_id, name=runtime.name)

        # Stop first (skip force for restart)
        if runtime.status not in (
            RuntimeStatus.STOPPED,
            RuntimeStatus.CRASHED,
            RuntimeStatus.FAILED,
        ):
            await self.stop(runtime_id, force=False)

        # Restart
        runtime = await self.start(runtime_id)

        runtime.restart_count += 1

        await publish_runtime_restarted(
            self._bus,
            runtime_id,
            runtime.name,
            old_status=old_status.value,
        )

        log.info(
            "Runtime restarted",
            runtime_id=runtime_id,
            name=runtime.name,
            restart_count=runtime.restart_count,
        )
        return runtime

    async def kill(self, runtime_id: str) -> Runtime:
        """Force-kill a runtime immediately (SIGKILL / taskkill /F).

        Shorter path than stop() — no grace period.
        """
        async with self._lock:
            runtime = await self._registry.get_raw(runtime_id)
            if runtime is None:
                raise ValueError(f"Runtime not found: {runtime_id}")

            exit_code: int | None = None
            try:
                exit_code = await self._force_kill(runtime)
            except Exception as exc:
                log.error("Kill error", runtime_id=runtime_id, error=str(exc))
                exit_code = -1

            runtime.status = RuntimeStatus.STOPPED
            runtime.health = RuntimeHealth.STOPPED
            runtime.last_exit_code = exit_code
            runtime.pid = None
            await self._registry.update(runtime)

            await publish_runtime_stopped(
                self._bus,
                runtime_id,
                runtime.name,
                exit_code=exit_code,
                forced=True,
            )

            log.info(
                "Runtime killed",
                runtime_id=runtime_id,
                name=runtime.name,
                exit_code=exit_code,
            )
            return runtime

    # ── Internal helpers ────────────────────────────────────────────────

    async def _graceful_stop(self, runtime: Runtime) -> int | None:
        """Send a graceful termination signal (SIGTERM / CtrlBreak)."""
        if runtime.pid is None:
            return None

        if self._launcher is not None and hasattr(self._launcher, "stop"):
            return await self._launcher.stop(runtime)

        # Fallback: no launcher, return 0 as assumed clean
        return 0

    async def _force_kill(self, runtime: Runtime) -> int | None:
        """Force-kill by sending SIGKILL or taskkill /F."""
        if runtime.pid is None:
            return None

        if self._launcher is not None and hasattr(self._launcher, "kill"):
            return await self._launcher.kill(runtime)

        import subprocess  # noqa: PLC0415

        try:
            if platform.system() == "Windows":
                result = subprocess.run(
                    ["taskkill", "/F", "/PID", str(runtime.pid)],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
            else:
                result = subprocess.run(
                    ["kill", "-9", str(runtime.pid)],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
            return result.returncode
        except Exception as exc:
            log.warning("Force-kill subprocess failed", pid=runtime.pid, error=str(exc))
            return -1


__all__ = [
    "RuntimeController",
]
