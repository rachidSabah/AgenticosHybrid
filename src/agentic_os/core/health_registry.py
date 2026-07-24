"""Health Registry — Tracks ALL subsystem states with phased health aggregation.

Purpose:
    The Kernel's health nervous system. Every service reports state through here.
    Provides wait-for-healthy gating for lifecycle phases and real-time
    degraded/failure detection via pull (health checks) and push (EventBus events).

Usage:
    registry = HealthRegistry(lifecycle_manager)
    await registry.wait_for_healthy(Phase.CORE, timeout=10.0)
    status = await registry.aggregate_health()
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from agentic_os.core.lifecycle import (
    LifecycleManager,
    Phase,
    ServiceState,
)

log = logging.getLogger("agentic_os.health_registry")


class HealthStatus(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"
    OFFLINE = "offline"
    UNKNOWN = "unknown"


@dataclass
class ServiceHealthSnapshot:
    """Snapshot of a single service's health at a point in time."""

    service_id: str
    state: ServiceState
    status: HealthStatus
    last_heartbeat: datetime | None = None
    failure_count: int = 0
    last_error: str | None = None
    response_time_ms: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class PhaseHealthAggregate:
    """Aggregated health for all services in a phase."""

    phase: Phase
    total: int
    healthy: int
    degraded: int
    failed: int
    offline: int
    status: HealthStatus

    @property
    def is_healthy(self) -> bool:
        return self.status == HealthStatus.HEALTHY


class HealthRegistry:
    """Central health registry for all Kernel services.

    Provides:
    - Per-service health snapshots with heartbeat tracking
    - Per-phase health aggregation
    - Wait-for-healthy gating (used by LifecycleManager)
    - Degraded/failure detection
    """

    def __init__(
        self,
        lifecycle: LifecycleManager,
        heartbeat_interval: float = 30.0,
        heartbeat_timeout: float = 60.0,
        health_check_interval: float = 15.0,
    ) -> None:
        self._lifecycle = lifecycle
        self._heartbeat_interval = heartbeat_interval
        self._heartbeat_timeout = heartbeat_timeout
        self._health_check_interval = health_check_interval

        self._snapshots: dict[str, ServiceHealthSnapshot] = {}
        self._last_heartbeats: dict[str, datetime] = {}
        self._health_check_task: asyncio.Task | None = None
        self._running = False

    # ── Registration ──

    def track_service(self, service_id: str) -> None:
        """Start tracking health for a service."""
        self._snapshots[service_id] = ServiceHealthSnapshot(
            service_id=service_id,
            state=ServiceState.INITIALIZING,
            status=HealthStatus.UNKNOWN,
        )

    # ── Heartbeat ──

    async def record_heartbeat(self, service_id: str) -> None:
        """Record a heartbeat from a service."""
        self._last_heartbeats[service_id] = datetime.now(UTC)
        if service_id in self._snapshots:
            self._snapshots[service_id].last_heartbeat = datetime.now(UTC)

    def is_heartbeat_current(self, service_id: str) -> bool:
        """Check if a service's heartbeat is within the timeout window."""
        last = self._last_heartbeats.get(service_id)
        if last is None:
            return False
        return (datetime.now(UTC) - last).total_seconds() < self._heartbeat_timeout

    def get_missing_heartbeats(self) -> list[str]:
        """Get services that haven't heartbeated within the timeout."""
        missing: list[str] = []
        now = datetime.now(UTC)
        for sid, last in self._last_heartbeats.items():
            if (now - last).total_seconds() >= self._heartbeat_timeout:
                missing.append(sid)
        return missing

    # ── Health Checks ──

    async def check_service_health(self, service_id: str) -> ServiceHealthSnapshot:
        """Run a health check against a specific service."""
        record = self._lifecycle.get_service(service_id)
        if record is None:
            return ServiceHealthSnapshot(
                service_id=service_id,
                state=ServiceState.DISPOSED,
                status=HealthStatus.OFFLINE,
            )
        started_at = datetime.now(UTC)
        try:
            health = await record.instance.health()
            response_time = (datetime.now(UTC) - started_at).total_seconds() * 1000
            status = health.get("status", "unknown")
            if status in ("healthy", "ok", "ready"):
                hs = HealthStatus.HEALTHY
            elif status in ("degraded", "warn", "warning"):
                hs = HealthStatus.DEGRADED
            elif status in ("failed", "error", "critical"):
                hs = HealthStatus.FAILED
            else:
                hs = HealthStatus.UNKNOWN
            snapshot = ServiceHealthSnapshot(
                service_id=service_id,
                state=record.state,
                status=hs,
                last_heartbeat=self._last_heartbeats.get(service_id),
                failure_count=record.failure_count,
                last_error=record.last_error,
                response_time_ms=response_time,
                details=health,
            )
        except Exception as exc:
            snapshot = ServiceHealthSnapshot(
                service_id=service_id,
                state=record.state,
                status=HealthStatus.FAILED,
                last_error=str(exc),
            )
        self._snapshots[service_id] = snapshot
        return snapshot

    async def check_all_health(self) -> dict[str, ServiceHealthSnapshot]:
        """Run health checks on all tracked services."""
        results: dict[str, ServiceHealthSnapshot] = {}
        for sid in list(self._snapshots.keys()):
            results[sid] = await self.check_service_health(sid)
        return results

    # ── Aggregation ──

    async def aggregate_health(self) -> HealthStatus:
        """Aggregate health across ALL services."""
        snaps = await self.check_all_health()
        if not snaps:
            return HealthStatus.UNKNOWN
        if any(s.status == HealthStatus.FAILED for s in snaps.values()):
            return HealthStatus.FAILED
        if any(s.status == HealthStatus.DEGRADED for s in snaps.values()):
            return HealthStatus.DEGRADED
        if all(s.status == HealthStatus.HEALTHY for s in snaps.values()):
            return HealthStatus.HEALTHY
        return HealthStatus.DEGRADED

    async def aggregate_phase_health(self, phase: Phase) -> PhaseHealthAggregate:
        """Aggregate health for all services in a specific phase."""
        records = self._lifecycle.get_services_by_phase(phase)
        healthy = degraded = failed = offline = 0
        for record in records:
            if record.state in (ServiceState.HEALTHY, ServiceState.READY):
                healthy += 1
            elif record.state in (ServiceState.DEGRADED,):
                degraded += 1
            elif record.state in (ServiceState.FAILED, ServiceState.OFFLINE):
                failed += 1
            else:
                offline += 1
        total = len(records)
        if failed > 0:
            status = HealthStatus.FAILED
        elif degraded > 0:
            status = HealthStatus.DEGRADED
        elif healthy == total:
            status = HealthStatus.HEALTHY
        else:
            status = HealthStatus.DEGRADED
        return PhaseHealthAggregate(
            phase=phase,
            total=total,
            healthy=healthy,
            degraded=degraded,
            failed=failed,
            offline=offline,
            status=status,
        )

    # ── Wait-for-Healthy ──

    async def wait_for_phase_healthy(
        self,
        phase: Phase,
        timeout: float = 30.0,
        poll_interval: float = 0.5,
    ) -> bool:
        """Wait until all services in a phase report healthy.

        Returns True if all healthy, False if timeout exceeded.
        """
        started_at = datetime.now(UTC)
        while (datetime.now(UTC) - started_at).total_seconds() < timeout:
            agg = await self.aggregate_phase_health(phase)
            if agg.is_healthy:
                return True
            await asyncio.sleep(poll_interval)
        log.warning("Phase %s did not become healthy within %.1fs", phase.value, timeout)
        return False

    async def wait_for_all_healthy(
        self,
        timeout: float = 60.0,
        poll_interval: float = 0.5,
    ) -> bool:
        """Wait until ALL tracked services are healthy."""
        started_at = datetime.now(UTC)
        while (datetime.now(UTC) - started_at).total_seconds() < timeout:
            status = await self.aggregate_health()
            if status == HealthStatus.HEALTHY:
                return True
            if status == HealthStatus.FAILED:
                log.error("Service failed while waiting for all healthy")
                return False
            await asyncio.sleep(poll_interval)
        log.warning("Not all services became healthy within %.1fs", timeout)
        return False

    # ── Periodic Health Checks ──

    async def start_periodic_checks(self) -> None:
        """Start the background health check loop."""
        if self._running:
            return
        self._running = True

        async def _loop() -> None:
            while self._running:
                try:
                    await self.check_all_health()
                except Exception as exc:
                    log.error("Periodic health check error: %s", exc)
                await asyncio.sleep(self._health_check_interval)

        self._health_check_task = asyncio.create_task(_loop())
        log.info(
            "Periodic health checks started (interval=%.1fs)",
            self._health_check_interval,
        )

    async def stop_periodic_checks(self) -> None:
        """Stop the background health check loop."""
        self._running = False
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
            self._health_check_task = None
        log.info("Periodic health checks stopped")

    # ── Introspection ──

    def get_snapshot(self, service_id: str) -> ServiceHealthSnapshot | None:
        """Get the latest health snapshot for a service."""
        return self._snapshots.get(service_id)

    def get_all_snapshots(self) -> dict[str, ServiceHealthSnapshot]:
        """Get all health snapshots."""
        return dict(self._snapshots)

    async def health(self) -> dict[str, Any]:
        """Health endpoint for the Health Registry itself."""
        status = await self.aggregate_health()
        phase_aggregates: dict[str, dict[str, Any]] = {}
        for phase in list(Phase):
            agg = await self.aggregate_phase_health(phase)
            phase_aggregates[phase.value] = {
                "total": agg.total,
                "healthy": agg.healthy,
                "degraded": agg.degraded,
                "failed": agg.failed,
                "status": agg.status.value,
            }
        return {
            "status": status.value,
            "total_services": len(self._snapshots),
            "phases": phase_aggregates,
            "missing_heartbeats": self.get_missing_heartbeats(),
            "periodic_checks_running": self._running,
        }

    def summary(self) -> str:
        """Human-readable health summary."""
        healthy = sum(1 for s in self._snapshots.values() if s.status == HealthStatus.HEALTHY)
        degraded = sum(1 for s in self._snapshots.values() if s.status == HealthStatus.DEGRADED)
        failed = sum(1 for s in self._snapshots.values() if s.status == HealthStatus.FAILED)
        total = len(self._snapshots)
        return f"Health: {healthy}/{total} healthy, {degraded} degraded, {failed} failed"
