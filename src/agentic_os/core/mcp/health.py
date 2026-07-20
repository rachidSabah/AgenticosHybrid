"""
MCP Health Monitor

Dedicated health monitoring service for MCP servers with:
- Periodic health checks
- Automatic failure detection
- Degraded state handling
- Health history tracking
"""

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from agentic_os.domain.events import EventEnvelope, Topic
from agentic_os.domain.mcp import MCPHealthStatus
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.event_bus import EventBus

log = get_logger("mcp.health")


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class HealthCheckResult:
    """Result of a health check operation."""

    server_id: str
    status: MCPHealthStatus
    latency_ms: float | None = None
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=_utcnow)
    error: str | None = None


@dataclass
class ServerHealthHistory:
    """Historical health data for a server."""

    server_id: str
    server_name: str
    checks_total: int = 0
    checks_healthy: int = 0
    checks_degraded: int = 0
    checks_unhealthy: int = 0
    checks_unknown: int = 0
    consecutive_failures: int = 0
    last_check_at: datetime | None = None
    last_healthy_at: datetime | None = None
    last_failure_at: datetime | None = None
    avg_latency_ms: float = 0.0
    health_transitions: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class HealthSummary:
    """Summary of all server health status."""

    timestamp: datetime
    total_servers: int
    healthy_count: int
    degraded_count: int
    unhealthy_count: int
    unknown_count: int
    running_servers: int
    stopped_servers: int
    server_health: dict[str, dict[str, Any]]


class MCPHealthMonitor:
    """
    MCP Health Monitor for server health tracking.

    Features:
    - Periodic health checks
    - Consecutive failure tracking
    - Degraded state management
    - Health history retention
    - Alert on health transitions
    """

    def __init__(
        self,
        bus: EventBus,
        check_interval_seconds: int = 30,
        timeout_seconds: int = 10,
        consecutive_failures_threshold: int = 3,
    ) -> None:
        self._bus = bus
        self._check_interval = check_interval_seconds
        self._timeout = timeout_seconds
        self._failure_threshold = consecutive_failures_threshold

        self._health_cache: dict[str, MCPHealthStatus] = {}
        self._health_details: dict[str, dict[str, Any]] = {}
        self._health_history: dict[str, ServerHealthHistory] = {}
        self._check_tasks: dict[str, asyncio.Task] = {}
        self._running = False
        self._monitor_lock = asyncio.Lock()

        # Callbacks for actual health checking (provided by registry)
        self._health_check_callbacks: dict[str, Any] = {}

    async def _emit(self, topic: Topic, payload: dict[str, Any]) -> None:
        """Emit an event to the event bus."""
        await self._bus.publish(
            EventEnvelope(
                type="event",
                source="mcp-health-monitor",
                topic=topic.value,
                payload=payload,
            )
        )

    # ── Registration ────────────────────────────────────────────────────

    def register_server(
        self,
        server_id: str,
        server_name: str,
        health_check_callback: Any,
    ) -> None:
        """Register a server for health monitoring."""
        if server_id not in self._health_history:
            self._health_history[server_id] = ServerHealthHistory(
                server_id=server_id,
                server_name=server_name,
            )

        self._health_check_callbacks[server_id] = health_check_callback
        log.debug(f"Registered server {server_id} for health monitoring")

    def unregister_server(self, server_id: str) -> None:
        """Unregister a server from health monitoring."""
        self._health_history.pop(server_id, None)
        self._health_cache.pop(server_id, None)
        self._health_details.pop(server_id, None)
        self._health_check_callbacks.pop(server_id, None)

        # Cancel any running check task
        if server_id in self._check_tasks:
            self._check_tasks[server_id].cancel()
            del self._check_tasks[server_id]

        log.debug(f"Unregistered server {server_id} from health monitoring")

    # ── Health Checking ─────────────────────────────────────────────────

    async def check_server(self, server_id: str) -> HealthCheckResult:
        """Perform a health check on a specific server."""
        callback = self._health_check_callbacks.get(server_id)
        if not callback:
            return HealthCheckResult(
                server_id=server_id,
                status=MCPHealthStatus.UNKNOWN,
                error="No health check callback registered",
            )

        start_time = asyncio.get_event_loop().time()

        try:
            result = await asyncio.wait_for(callback(), timeout=self._timeout)
            latency_ms = (asyncio.get_event_loop().time() - start_time) * 1000

            if isinstance(result, tuple) and len(result) == 2:
                status, details = result
            elif isinstance(result, dict):
                status = MCPHealthStatus(result.get("status", "unknown"))
                details = result
            else:
                status = MCPHealthStatus.HEALTHY
                details = {}

            check_result = HealthCheckResult(
                server_id=server_id,
                status=status,
                latency_ms=latency_ms,
                details=details,
            )

        except TimeoutError:
            check_result = HealthCheckResult(
                server_id=server_id,
                status=MCPHealthStatus.UNHEALTHY,
                error=f"Health check timed out after {self._timeout}s",
            )

        except Exception as e:
            check_result = HealthCheckResult(
                server_id=server_id,
                status=MCPHealthStatus.UNHEALTHY,
                error=str(e),
            )

        # Update state
        self._update_health_state(server_id, check_result)
        return check_result

    def _update_health_state(self, server_id: str, result: HealthCheckResult) -> None:
        """Update health state after a check."""
        old_status = self._health_cache.get(server_id)
        new_status = result.status

        # Update cache
        self._health_cache[server_id] = new_status
        self._health_details[server_id] = result.details

        # Update history
        history = self._health_history.get(server_id)
        if history:
            history.checks_total += 1
            history.last_check_at = result.timestamp

            if result.latency_ms is not None:
                # Update average latency
                total_latency = history.avg_latency_ms * (history.checks_total - 1)
                history.avg_latency_ms = (total_latency + result.latency_ms) / history.checks_total

            # Count by status
            if new_status == MCPHealthStatus.HEALTHY:
                history.checks_healthy += 1
                history.consecutive_failures = 0
                history.last_healthy_at = result.timestamp
            elif new_status == MCPHealthStatus.DEGRADED:
                history.checks_degraded += 1
                history.consecutive_failures += 1
            elif new_status == MCPHealthStatus.UNHEALTHY:
                history.checks_unhealthy += 1
                history.consecutive_failures += 1
                history.last_failure_at = result.timestamp
            else:
                history.checks_unknown += 1

            # Track status transitions
            if old_status and old_status != new_status:
                history.health_transitions.append(
                    {
                        "timestamp": result.timestamp.isoformat(),
                        "from": old_status.value,
                        "to": new_status.value,
                        "error": result.error,
                    }
                )
                # Keep only recent transitions
                if len(history.health_transitions) > 50:
                    history.health_transitions = history.health_transitions[-50:]

    # ── Monitor Control ────────────────────────────────────────────────

    async def start_monitoring(self) -> None:
        """Start health monitoring for all registered servers."""
        async with self._monitor_lock:
            if self._running:
                log.warning("Health monitor already running")
                return

            self._running = True
            log.info("Starting MCP health monitor")

            # Start monitoring tasks for each server
            for server_id in list(self._health_check_callbacks.keys()):
                await self._start_server_monitoring(server_id)

    async def stop_monitoring(self) -> None:
        """Stop health monitoring."""
        async with self._monitor_lock:
            if not self._running:
                return

            self._running = False

            # Cancel all monitoring tasks
            for task in self._check_tasks.values():
                task.cancel()
            self._check_tasks.clear()

            log.info("Stopped MCP health monitor")

    async def _start_server_monitoring(self, server_id: str) -> None:
        """Start monitoring a specific server."""
        if server_id in self._check_tasks:
            return

        async def monitor_loop():
            while self._running:
                try:
                    await asyncio.sleep(self._check_interval)
                    if not self._running:
                        break

                    await self.check_server(server_id)

                    # Emit health changed event
                    status = self._health_cache.get(server_id)
                    if status:
                        await self._emit(
                            Topic.MCP_HEALTH_CHANGED,
                            {
                                "server_id": server_id,
                                "health": status.value,
                                "details": self._health_details.get(server_id, {}),
                            },
                        )

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    log.error(f"Health monitoring error for {server_id}: {e}")

        task = asyncio.create_task(monitor_loop())
        self._check_tasks[server_id] = task

    # ── State Access ────────────────────────────────────────────────────

    def get_health(self, server_id: str) -> MCPHealthStatus | None:
        """Get the current health status of a server."""
        return self._health_cache.get(server_id)

    def get_health_details(self, server_id: str) -> dict[str, Any] | None:
        """Get the health details for a server."""
        return self._health_details.get(server_id)

    def get_all_health(self) -> dict[str, MCPHealthStatus]:
        """Get health status for all servers."""
        return self._health_cache.copy()

    def get_health_history(self, server_id: str) -> ServerHealthHistory | None:
        """Get health history for a server."""
        return self._health_history.get(server_id)

    def get_summary(self) -> HealthSummary:
        """Get a summary of all server health."""
        healthy = degraded = unhealthy = unknown = 0
        running = stopped = 0

        server_health: dict[str, dict[str, Any]] = {}

        for server_id, status in self._health_cache.items():
            history = self._health_history.get(server_id)

            if status == MCPHealthStatus.HEALTHY:
                healthy += 1
            elif status == MCPHealthStatus.DEGRADED:
                degraded += 1
            elif status == MCPHealthStatus.UNHEALTHY:
                unhealthy += 1
            else:
                unknown += 1

            if history:
                server_health[server_id] = {
                    "status": status.value,
                    "server_name": history.server_name,
                    "consecutive_failures": history.consecutive_failures,
                    "last_check_at": (
                        history.last_check_at.isoformat() if history.last_check_at else None
                    ),
                    "avg_latency_ms": history.avg_latency_ms,
                    "uptime_ratio": (
                        history.checks_healthy / history.checks_total
                        if history.checks_total > 0
                        else 0.0
                    ),
                }

        return HealthSummary(
            timestamp=_utcnow(),
            total_servers=len(self._health_cache),
            healthy_count=healthy,
            degraded_count=degraded,
            unhealthy_count=unhealthy,
            unknown_count=unknown,
            running_servers=running,
            stopped_servers=stopped,
            server_health=server_health,
        )

    def is_server_degraded(self, server_id: str) -> bool:
        """Check if a server is in degraded state."""
        status = self._health_cache.get(server_id)
        if status == MCPHealthStatus.DEGRADED:
            return True

        history = self._health_history.get(server_id)
        return history is not None and history.consecutive_failures >= 1

    def is_server_unhealthy(self, server_id: str) -> bool:
        """Check if a server is unhealthy (past failure threshold)."""
        history = self._health_history.get(server_id)
        if not history:
            return False

        return history.consecutive_failures >= self._failure_threshold

    def get_degraded_servers(self) -> list[str]:
        """Get list of servers in degraded state."""
        return [sid for sid in self._health_cache if self.is_server_degraded(sid)]

    def get_unhealthy_servers(self) -> list[str]:
        """Get list of servers past the failure threshold."""
        return [sid for sid in self._health_cache if self.is_server_unhealthy(sid)]

    def should_auto_restart(self, server_id: str) -> bool:
        """Check if a server should be automatically restarted."""
        history = self._health_history.get(server_id)
        if not history:
            return False

        # Auto-restart if consecutive failures exceeded threshold
        return history.consecutive_failures >= self._failure_threshold


__all__ = ["MCPHealthMonitor", "HealthCheckResult", "ServerHealthHistory", "HealthSummary"]
