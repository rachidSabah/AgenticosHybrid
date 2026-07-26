"""RuntimeManager — top-level facade for the runtime orchestration system."""

from __future__ import annotations

import asyncio
import subprocess  # noqa: PLC0415
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agentic_os.core.runtime.runtime import (
    Runtime,
    RuntimeHealth,
    RuntimeMetrics,
    RuntimeStatus,
    RuntimeType,
)
from agentic_os.core.runtime.runtime_bridge import RuntimeBridge
from agentic_os.core.runtime.runtime_controller import RuntimeController
from agentic_os.core.runtime.runtime_registry import RuntimeRegistry
from agentic_os.infrastructure.logging import get_logger

log = get_logger("runtime.manager")


class RuntimeManager:
    """Top-level facade for the runtime orchestration system.

    Single entry point that instantiates and exposes all sub-systems as
    attributes. Provides coordinated lifecycle management for all runtimes
    managed by this agent.
    """

    def __init__(
        self,
        bus: Any | None = None,
        data_dir: str | Path | None = None,
    ) -> None:
        self._bus = bus
        self._data_dir = Path(data_dir) if data_dir else Path.cwd() / ".runtime"
        self._data_dir.mkdir(parents=True, exist_ok=True)

        # Sub-system instances
        self.registry: RuntimeRegistry = RuntimeRegistry()
        self.controller: RuntimeController = RuntimeController(
            registry=self.registry,
            bus=bus,
        )
        self.bridge: RuntimeBridge = RuntimeBridge(
            registry=self.registry,
            bus=bus,
        )

        # Internal state
        self._running = False
        self._lock: asyncio.Lock = asyncio.Lock()

    # ── Lifecycle ───────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the runtime management system.

        Runs initial discovery and brings the manager into service.
        """
        async with self._lock:
            if self._running:
                log.warning("RuntimeManager already started")
                return
            self._running = True
            log.info("RuntimeManager starting")

        # Auto-discover and register runtimes
        discovered = await self.bridge.sync_discovered()
        log.info(
            "RuntimeManager started",
            total_registered=await self.registry.count(),
            newly_discovered=len(discovered),
        )

    async def stop(self) -> None:
        """Gracefully stop the entire runtime management system.

        Stops all active runtimes before tearing down.
        """
        async with self._lock:
            if not self._running:
                return
            self._running = False

        log.info("RuntimeManager stopping — shutting down all runtimes")

        active = await self.registry.get_active()
        for runtime in active:
            try:
                await self.controller.stop(runtime.id, force=False)
            except Exception as exc:
                log.warning(
                    "Error stopping runtime",
                    runtime_id=runtime.id,
                    name=runtime.name,
                    error=str(exc),
                )

        log.info(
            "RuntimeManager stopped",
            total=await self.registry.count(),
        )

    # ── Discovery ───────────────────────────────────────────────────────

    async def discover(self) -> list[Runtime]:
        """Run discovery and auto-register any newly found runtimes.

        Returns the list of newly registered runtimes.
        """
        return await self.bridge.sync_discovered()

    # ─── Lifecycle actions ──────────────────────────────────────────────

    async def launch(self, runtime_id: str) -> Runtime:
        """Launch (start) a runtime by id."""
        return await self.controller.start(runtime_id)

    async def stop_runtime(self, runtime_id: str, force: bool = False) -> Runtime:
        """Stop a runtime by id."""
        return await self.controller.stop(runtime_id, force=force)

    async def restart_runtime(self, runtime_id: str) -> Runtime:
        """Restart a runtime by id (stop then start)."""
        return await self.controller.restart(runtime_id)

    async def kill(self, runtime_id: str) -> Runtime:
        """Force-kill a runtime by id."""
        return await self.controller.kill(runtime_id)

    # ── Queries ─────────────────────────────────────────────────────────

    async def get(self, runtime_id: str) -> Runtime | None:
        """Look up a runtime by id."""
        return await self.registry.get(runtime_id)

    async def list_all(
        self,
        runtime_type: RuntimeType | None = None,
        status: RuntimeStatus | None = None,
    ) -> list[Runtime]:
        """List registered runtimes, optionally filtered.

        Parameters
        ----------
        runtime_type : RuntimeType | None
            Filter by runtime type.
        status : RuntimeStatus | None
            Filter by current status.
        """
        runtimes = await self.registry.get_all()
        if runtime_type is not None:
            runtimes = [r for r in runtimes if r.type == runtime_type]
        if status is not None:
            runtimes = [r for r in runtimes if r.status == status]
        return runtimes

    # ── Command execution ───────────────────────────────────────────────

    async def execute_command(self, runtime_id: str, command: str) -> str:
        """Execute a command on the runtime. Returns output string.

        Delegates to the launcher if available; otherwise raises.
        """
        runtime = await self.registry.get_raw(runtime_id)
        if runtime is None:
            raise ValueError(f"Runtime not found: {runtime_id}")

        launcher = self.controller._launcher  # noqa: SLF001
        if launcher is not None and hasattr(launcher, "execute"):
            return await launcher.execute(runtime, command)

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=60,
            )
            return result.stdout + result.stderr
        except subprocess.TimeoutExpired:
            return "Command timed out after 60s"
        except Exception as exc:
            return f"Command failed: {exc}"

    # ── Terminal session ────────────────────────────────────────────────

    async def attach_terminal(self, runtime_id: str) -> str:
        """Attach a terminal session to the runtime.

        Returns a terminal session id.
        """
        runtime = await self.registry.get_raw(runtime_id)
        if runtime is None:
            raise ValueError(f"Runtime not found: {runtime_id}")

        session_manager = self.controller._session_manager  # noqa: SLF001
        if session_manager is not None and hasattr(session_manager, "create_session"):
            session = await session_manager.create_session(runtime)
            return session.session_id if hasattr(session, "session_id") else str(session)

        # Fallback: generate a terminal id
        terminal_id = f"term_{runtime.id}_{int(datetime.now(UTC).timestamp())}"
        runtime.terminal = terminal_id
        await self._update_immutable(runtime)
        return terminal_id

    async def list_sessions(self, runtime_id: str) -> list:
        """List sessions for a runtime."""
        session_manager = self.controller._session_manager  # noqa: SLF001
        if session_manager is not None and hasattr(session_manager, "list_sessions"):
            return await session_manager.list_sessions(runtime_id)
        return []

    # ── Logs & metrics ──────────────────────────────────────────────────

    async def get_logs(
        self,
        runtime_id: str,
        **filters: Any,
    ) -> list[dict[str, Any]]:
        """Return log entries for a runtime, optionally filtered.

        Supported filters:
        - stream (str): 'stdout', 'stderr', 'system'
        - level (str): 'info', 'warn', 'error', 'debug'
        - limit (int): max entries to return
        """
        runtime = await self.registry.get(runtime_id)
        if runtime is None:
            raise ValueError(f"Runtime not found: {runtime_id}")

        logs = [log_entry.to_dict() for log_entry in runtime.logs]

        # Apply filters
        stream_filter = filters.get("stream")
        if stream_filter:
            logs = [log for log in logs if log.get("stream") == stream_filter]

        level_filter = filters.get("level")
        if level_filter:
            logs = [log for log in logs if log.get("level") == level_filter]

        limit = filters.get("limit", 100)
        if isinstance(limit, int):
            logs = logs[-limit:]

        return logs

    async def get_metrics(self, runtime_id: str) -> RuntimeMetrics | None:
        """Return the latest metrics snapshot for a runtime."""
        runtime = await self.registry.get(runtime_id)
        if runtime is None:
            return None
        return runtime.metrics

    async def get_health(self, runtime_id: str) -> RuntimeHealth | None:
        """Return the current health status for a runtime."""
        runtime = await self.registry.get(runtime_id)
        if runtime is None:
            return None
        return runtime.health

    # ── Internal helpers ────────────────────────────────────────────────

    async def _update_immutable(self, runtime: Runtime) -> None:
        """Persist changes made to a runtime retrieved via get_raw()."""
        await self.registry.update(runtime)


__all__ = [
    "RuntimeManager",
]
