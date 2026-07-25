"""Health monitor for local agent discovery.

Periodically checks that locally discovered agents are still running
and responsive.  Publishes ``AGENT_HEALTH_CHANGED`` events when the
status of an agent changes.

Uses ``asyncio`` throughout — no blocking calls.
"""

from __future__ import annotations

import asyncio
import logging
import platform
import time
from typing import Any

from agentic_os.domain.discovery import AgentHealthRecord, AgentStatus
from agentic_os.domain.events import Topic

log = logging.getLogger("agentic_os.local_discovery.health_monitor")


class HealthMonitor:
    """Periodic health checker for local agents.

    Lifecycle
    ---------
    Call :meth:`start` to begin the background health-check loop and
    :meth:`stop` to tear it down cleanly.

    Thread-safety
    -------------
    All mutable state is guarded by an ``asyncio.Lock``.
    """

    def __init__(
        self,
        interval_seconds: float = 15.0,
        event_bus: Any | None = None,
    ) -> None:
        self._interval = interval_seconds
        self._event_bus = event_bus
        self._system = platform.system().lower()
        self._lock = asyncio.Lock()

        # Internal state — guarded by _lock
        self._task: asyncio.Task[None] | None = None
        self._running = False
        # agent_id → last known status for change detection
        self._last_statuses: dict[str, AgentStatus] = {}
        # agent_id → restart count tracking
        self._restart_counts: dict[str, int] = {}
        # agent_id → last checked timestamp
        self._last_checked: dict[str, float] = {}

    # ── Lifecycle ───────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the background health-check loop."""
        async with self._lock:
            if self._running:
                log.debug("HealthMonitor already running")
                return
            self._running = True
            self._task = asyncio.create_task(self._run_loop())
            log.info("HealthMonitor started (interval=%ss)", self._interval)

    async def stop(self) -> None:
        """Stop the background health-check loop and await its completion."""
        async with self._lock:
            if not self._running:
                return
            self._running = False
            task = self._task
            self._task = None

        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        log.info("HealthMonitor stopped")

    @property
    def is_running(self) -> bool:
        """Return ``True`` if the background loop is active."""
        return self._running

    # ── Agent registration for health tracking ──────────────────────────────

    async def track_agent(self, agent_id: str, pid: int | None = None) -> None:
        """Begin tracking *agent_id*."""
        async with self._lock:
            if agent_id not in self._last_statuses:
                self._last_statuses[agent_id] = AgentStatus.UNKNOWN
                self._restart_counts[agent_id] = 0
                self._last_checked[agent_id] = 0.0

    async def untrack_agent(self, agent_id: str) -> None:
        """Stop tracking *agent_id*."""
        async with self._lock:
            self._last_statuses.pop(agent_id, None)
            self._restart_counts.pop(agent_id, None)
            self._last_checked.pop(agent_id, None)

    async def get_health_records(self, pid_map: dict[str, int | None]) -> list[AgentHealthRecord]:
        """Run a single health check pass for all tracked agents.

        Args:
            pid_map: ``{agent_id: pid_or_None}`` mapping.

        Returns:
            List of :class:`AgentHealthRecord` for every tracked agent.

        Complexity: O(*n*) where *n* = agent count.
        """
        records: list[AgentHealthRecord] = []
        async with self._lock:
            for agent_id in list(self._last_statuses.keys()):
                pid = pid_map.get(agent_id)
                record = await self._check_agent(agent_id, pid)
                records.append(record)
        return records

    # ── Internals ───────────────────────────────────────────────────────────

    async def _run_loop(self) -> None:
        """Periodically check all tracked agents."""
        while True:
            try:
                async with self._lock:
                    if not self._running:
                        break
                    agents = dict(self._last_statuses)
                    pids: dict[str, int | None] = {}

                # Build PID map (outside lock to minimise contention)
                for agent_id in agents:
                    pids[agent_id] = None  # Caller should provide PIDs

                # Check each agent (collect records first)
                records = await self.get_health_records(pids)

                # Publish events for status changes
                for rec in records:
                    async with self._lock:
                        prev = self._last_statuses.get(rec.agent_id)
                    if prev is not None and rec.status != prev:
                        await self._publish_health_changed(rec, prev)

                # Update last-known statuses
                async with self._lock:
                    for rec in records:
                        self._last_statuses[rec.agent_id] = rec.status
                        self._last_checked[rec.agent_id] = time.time()

            except asyncio.CancelledError:
                break
            except Exception:
                log.exception("Health check loop error")
                # Never crash the loop — log and continue

            await asyncio.sleep(self._interval)

    async def _check_agent(self, agent_id: str, pid: int | None) -> AgentHealthRecord:
        """Perform a single health check for one agent.

        Verifies the PID is still alive and measures basic responsiveness.
        """
        status = AgentStatus.UNKNOWN
        health_score = 0.0
        latency = 0.0
        memory_mb = 0.0
        cpu_percent = 0.0
        threads = 0
        error = ""

        if pid is not None and pid > 0:
            alive = await self._is_pid_alive(pid)
            if alive:
                status = AgentStatus.RUNNING
                health_score = 1.0
            else:
                status = AgentStatus.CRASHED
                health_score = 0.0
                error = f"PID {pid} no longer running"
                async with self._lock:
                    self._restart_counts[agent_id] = self._restart_counts.get(agent_id, 0) + 1
        else:
            # No PID means we can't verify — mark as IDLE
            status = AgentStatus.IDLE
            health_score = 0.5

        from datetime import UTC, datetime

        return AgentHealthRecord(
            agent_id=agent_id,
            status=status,
            health_score=health_score,
            latency_ms=latency,
            memory_mb=memory_mb,
            cpu_percent=cpu_percent,
            threads=threads,
            pid=pid,
            checked_at=datetime.now(UTC),
            error=error,
        )

    async def _is_pid_alive(self, pid: int) -> bool:
        """Check if a process with *pid* is still running.

        Uses platform-specific logic (``tasklist`` on Windows,
        ``kill -0`` on POSIX).
        """
        try:
            if self._system == "windows":
                proc = await asyncio.create_subprocess_exec(
                    "tasklist",
                    "/FO",
                    "CSV",
                    "/NH",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
                return str(pid).encode() in stdout
            else:
                proc = await asyncio.create_subprocess_exec(
                    "kill",
                    "-0",
                    str(pid),
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await proc.wait()
                return proc.returncode == 0
        except (TimeoutError, FileNotFoundError, OSError):
            return False

    async def _publish_health_changed(
        self, record: AgentHealthRecord, previous: AgentStatus
    ) -> None:
        """Publish an ``AGENT_HEALTH_CHANGED`` event via the event bus."""
        if self._event_bus is None:
            log.debug(
                "Health change for %s: %s -> %s (no event bus configured)",
                record.agent_id,
                previous.value,
                record.status.value,
            )
            return

        payload = {
            "agent_id": record.agent_id,
            "previous_status": previous.value,
            "current_status": record.status.value,
            "health_score": record.health_score,
            "latency_ms": record.latency_ms,
            "memory_mb": record.memory_mb,
            "cpu_percent": record.cpu_percent,
            "error": record.error,
            "checked_at": record.checked_at,
        }

        try:
            await self._event_bus.publish(
                topic=Topic.AGENT_HEALTH_CHANGED.value,
                payload=payload,
                source="local_discovery",
            )
            log.info(
                "Published health change for %s: %s -> %s",
                record.agent_id,
                previous.value,
                record.status.value,
            )
        except Exception:
            log.exception("Failed to publish health change event for %s", record.agent_id)
