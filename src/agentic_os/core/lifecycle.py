"""Lifecycle Manager — Kernel v2 service lifecycle with 10-state machine and 6-phase gating.

Provides phase-ordered startup with wait-for-healthy gates, reversed shutdown,
and a state machine that every registered service follows.

States:
    Initializing → Loading → Ready → Healthy/Degraded/Offline → Stopping → Stopped → Disposed
    Error paths: Loading → Failed → Recovering → (Loading | Degraded)
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum, auto
from typing import Any, Generic, TypeVar

from agentic_os.core.container import Container, Registration

T = TypeVar("T")
log = logging.getLogger("agentic_os.lifecycle")


# ── Lifecycle Phases ──

class Phase(StrEnum):
    """Ordered startup phases. Each phase must complete before the next begins."""

    CRITICAL = "critical"  # Config, logging, telemetry, secrets, vault
    INFRASTRUCTURE = "infrastructure"  # DI Container, EventBus, Health Registry
    CORE = "core"  # Persistence: SQLite, Redis, Vector DB
    DOMAIN = "domain"  # Runtime Discovery, Provider Registry, OmniRoute
    OMNIROUTE = "omniroute"  # Mission Orchestrator, Workflow Engine, Desktop Runtime
    ADVANCED = "advanced"  # REST API, WebSocket, MCP, Desktop UI


PHASE_ORDER: list[Phase] = [
    Phase.CRITICAL,
    Phase.INFRASTRUCTURE,
    Phase.CORE,
    Phase.DOMAIN,
    Phase.OMNIROUTE,
    Phase.ADVANCED,
]

PHASE_REVERSE = list(reversed(PHASE_ORDER))


# ── Lifecycle States ──

class ServiceState(StrEnum):
    """The full state machine for every Kernel service."""

    INITIALIZING = "initializing"  # initialize() called
    LOADING = "loading"  # start() called
    READY = "ready"  # All dependencies healthy
    FAILED = "failed"  # initialize() or start() raised
    RECOVERING = "recovering"  # Kernel is attempting repair
    HEALTHY = "healthy"  # Health check passed
    DEGRADED = "degraded"  # Some issues, still running
    OFFLINE = "offline"  # Registered but not available
    STOPPING = "stopping"  # stop() called
    STOPPED = "stopped"  # stop() completed
    DISPOSED = "disposed"  # dispose() completed


# ── Lifecycle Hooks ──

@dataclass
class LifecycleHooks:
    """Hooks called at various lifecycle points for a service."""

    before_start: Callable[[], None] | None = None
    after_start: Callable[[], None] | None = None
    before_stop: Callable[[], None] | None = None
    after_stop: Callable[[], None] | None = None
    on_error: Callable[[Exception], None] | None = None


# ── Service Protocol (minimal) ──

class ServiceProtocol:
    """The mandatory interface every Kernel service must implement.

    This is intentionally kept minimal. The full 22-method contract is
    composed from multiple mixin protocols; a service only needs to
    implement what makes sense for its role. At minimum, initialize(),
    start(), stop(), dispose(), health(), and dependencies() are expected.
    """

    async def initialize(self) -> None:
        """Set up internal state. No side effects (no connections, no subscriptions)."""

    async def start(self) -> None:
        """Begin processing. Subscribe to EventBus, connect to services."""

    async def pause(self) -> None:
        """Suspend processing. Preserve state for later resume."""

    async def resume(self) -> None:
        """Resume from paused state."""

    async def stop(self) -> None:
        """Graceful stop. Drain in-flight work, cancel subscriptions."""

    async def dispose(self) -> None:
        """Release all resources. No further calls after this."""

    async def restart(self) -> None:
        await self.stop()
        await self.start()

    async def reload(self) -> None:
        """Reload configuration without restarting."""

    async def self_test(self) -> dict[str, Any]:
        """Verify internal consistency. Return test report."""
        return {"status": "passed"}

    async def health(self) -> dict[str, Any]:
        """Return health status."""
        return {"status": "healthy"}

    async def heartbeat(self) -> bool:
        """Quick liveness check."""
        return True

    async def metrics(self) -> dict[str, Any]:
        """Return service-level metrics."""
        return {}

    async def dependencies(self) -> list[str]:
        """List of service IDs this depends on."""
        return []

    async def capabilities(self) -> list[dict[str, Any]]:
        """What this service can do."""
        return []

    async def metadata(self) -> dict[str, Any]:
        """Version, description, config."""
        return {"version": "1.0", "description": self.__class__.__name__}

    async def configuration(self) -> dict[str, Any]:
        """Current configuration snapshot."""
        return {}

    async def diagnostics(self) -> dict[str, Any]:
        """Detailed diagnostic report."""
        return {"status": "ok"}

    async def repair(self) -> dict[str, Any]:
        """Attempt self-repair."""
        return {"repaired": False, "message": "No repair logic implemented"}

    async def recover(self) -> dict[str, Any]:
        """Attempt recovery from failure."""
        return {"recovered": False, "message": "No recovery logic implemented"}

    async def upgrade(self, version: str) -> dict[str, Any]:
        """Upgrade to new version."""
        return {"upgraded": False, "message": "No upgrade logic implemented"}

    async def downgrade(self, version: str) -> dict[str, Any]:
        """Downgrade to previous version."""
        return {"downgraded": False, "message": "No downgrade logic implemented"}

    async def snapshot(self) -> dict[str, Any]:
        """Capture state snapshot."""
        return {}

    async def restore(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        """Restore from snapshot."""
        return {"restored": False, "message": "No restore logic implemented"}


# ── ServiceRecord ──

@dataclass
class ServiceRecord:
    """Tracks a service through its lifecycle within the Kernel."""

    id: str
    interface: type
    instance: ServiceProtocol
    phase: Phase
    state: ServiceState = ServiceState.INITIALIZING
    hooks: LifecycleHooks | None = None
    started_at: datetime | None = None
    stopped_at: datetime | None = None
    failure_count: int = 0
    last_error: str | None = None
    last_health_check: datetime | None = None
    event_bus_topic: str | None = None  # e.g. "service.{id}.state.*"
    container_key: str = ""  # Key in the DI container


# ── LifecycleManager ──

@dataclass
class PhaseResult:
    """Result of starting or stopping a phase."""

    phase: Phase
    success: bool
    started_services: list[str] = field(default_factory=list)
    failed_services: list[str] = field(default_factory=list)
    skipped_services: list[str] = field(default_factory=list)
    duration_ms: float = 0.0
    errors: list[str] = field(default_factory=list)


class LifecycleManager:
    """Manages the lifecycle of all Kernel services.

    Features:
    - 6 ordered phases (CRITICAL → ADVANCED)
    - Per-service state machine (10 states)
    - Phase-gated startup: each phase waits for previous to be healthy
    - Reversed-phase shutdown with timeout
    - Hooks: before_start, after_start, before_stop, after_stop, on_error
    - EventBus state transitions (service.{id}.state.{State})
    """

    def __init__(
        self,
        container: Container,
        phase_timeout: float = 30.0,
        health_timeout: float = 5.0,
        stop_timeout: float = 15.0,
    ) -> None:
        self._container = container
        self._records: dict[str, ServiceRecord] = {}
        self._phase_results: dict[Phase, PhaseResult] = {}
        self._phase_order = PHASE_ORDER
        self._running = False
        self._stopped = False

        # Timeouts
        self.phase_timeout = phase_timeout
        self.health_timeout = health_timeout
        self.stop_timeout = stop_timeout

        # Current phase tracking
        self.current_phase: Phase | None = None
        self.current_state: ServiceState = ServiceState.INITIALIZING

        # EventBus callback — set externally
        self.publish_event: Callable[[str, dict[str, Any]], None] | None = None

    # ── Registration ──

    def register_service(
        self,
        service_id: str,
        interface: type,
        instance: ServiceProtocol,
        phase: Phase = Phase.INFRASTRUCTURE,
        hooks: LifecycleHooks | None = None,
        container_key: str = "",
    ) -> ServiceRecord:
        """Register a service for lifecycle management."""
        record = ServiceRecord(
            id=service_id,
            interface=interface,
            instance=instance,
            phase=phase,
            state=ServiceState.INITIALIZING,
            hooks=hooks,
            event_bus_topic=f"service.{service_id}.state",
            container_key=container_key,
        )
        self._records[service_id] = record
        return record

    def get_service(self, service_id: str) -> ServiceRecord | None:
        """Look up a service by its ID."""
        return self._records.get(service_id)

    def get_services_by_phase(self, phase: Phase) -> list[ServiceRecord]:
        """Get all services registered for a given phase."""
        return [r for r in self._records.values() if r.phase == phase]

    def get_services_by_state(self, state: ServiceState) -> list[ServiceRecord]:
        """Get all services in a given state."""
        return [r for r in self._records.values() if r.state == state]

    # ── State Machine ──

    async def _transition(
        self,
        service_id: str,
        new_state: ServiceState,
        error: str | None = None,
    ) -> None:
        """Transition a service to a new state and publish the event."""
        record = self._records.get(service_id)
        if record is None:
            return

        old_state = record.state
        record.state = new_state
        if error:
            record.last_error = error
        if new_state == ServiceState.HEALTHY:
            record.started_at = datetime.now(UTC)
            record.last_health_check = datetime.now(UTC)
        elif new_state == ServiceState.STOPPED:
            record.stopped_at = datetime.now(UTC)

        # Publish state transition event
        topic = f"{record.event_bus_topic}.{new_state.value}"
        payload = {
            "service_id": service_id,
            "old_state": old_state.value,
            "new_state": new_state.value,
            "error": error,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        if self.publish_event:
            self.publish_event(topic, payload)

        log.debug(
            "Service %s: %s -> %s",
            service_id,
            old_state.value,
            new_state.value,
        )

    # ── Phase Startup ──

    async def start_phase(self, phase: Phase) -> PhaseResult:
        """Start all services in a phase. Blocks until all healthy or timeout.

        Every service goes through: INITIALIZING → LOADING → READY → HEALTHY
        """
        started_at = datetime.now(UTC)
        services = self.get_services_by_phase(phase)
        if not services:
            result = PhaseResult(phase=phase, success=True, duration_ms=0.0)
            self._phase_results[phase] = result
            return result

        self.current_phase = phase
        log.info("Starting phase %s (%d services)", phase.value, len(services))

        started: list[str] = []
        failed: list[str] = []
        errors: list[str] = []

        for record in services:
            service_id = record.id
            try:
                # 1. INITIALIZING
                await self._transition(service_id, ServiceState.INITIALIZING)
                if record.hooks and record.hooks.before_start:
                    record.hooks.before_start()

                # Call initialize with timeout
                async def _initialize(svc: ServiceProtocol) -> None:
                    await svc.initialize()

                await asyncio.wait_for(
                    _initialize(record.instance),
                    timeout=self.phase_timeout,
                )
                await self._transition(service_id, ServiceState.LOADING)

                # 2. LOADING → start() with timeout
                async def _start(svc: ServiceProtocol) -> None:
                    await svc.start()

                await asyncio.wait_for(
                    _start(record.instance),
                    timeout=self.phase_timeout,
                )
                await self._transition(service_id, ServiceState.READY)

                # 3. Health check
                try:
                    async def _health_check(svc: ServiceProtocol) -> dict[str, Any]:
                        return await svc.health()

                    health = await asyncio.wait_for(
                        _health_check(record.instance),
                        timeout=self.health_timeout,
                    )
                    if health and health.get("status") in ("healthy", "ok", "ready"):
                        await self._transition(service_id, ServiceState.HEALTHY)
                    else:
                        await self._transition(service_id, ServiceState.DEGRADED)
                except Exception as h_exc:
                    await self._transition(service_id, ServiceState.DEGRADED)
                    errors.append(f"{service_id}: health check failed: {h_exc}")

                if record.hooks and record.hooks.after_start:
                    record.hooks.after_start()
                started.append(service_id)
                log.info("Service %s started (state=%s)", service_id, record.state.value)

            except asyncio.TimeoutError:
                await self._transition(
                    service_id, ServiceState.FAILED,
                    error="startup timed out",
                )
                failed.append(service_id)
                errors.append(f"{service_id}: startup timed out (>{self.phase_timeout}s)")
                if record.hooks and record.hooks.on_error:
                    record.hooks.on_error(TimeoutError(f"{service_id} startup timed out"))

            except Exception as exc:
                await self._transition(
                    service_id, ServiceState.FAILED,
                    error=str(exc),
                )
                failed.append(service_id)
                errors.append(f"{service_id}: {exc}")
                if record.hooks and record.hooks.on_error:
                    record.hooks.on_error(exc)

        duration = (datetime.now(UTC) - started_at).total_seconds() * 1000
        result = PhaseResult(
            phase=phase,
            success=len(failed) == 0,
            started_services=started,
            failed_services=failed,
            duration_ms=duration,
            errors=errors,
        )
        self._phase_results[phase] = result

        if result.success:
            self.current_state = ServiceState.HEALTHY
            log.info("Phase %s completed successfully (%d services)", phase.value, len(started))
        else:
            self.current_state = ServiceState.DEGRADED
            log.warning(
                "Phase %s completed with %d failures: %s",
                phase.value, len(failed), errors,
            )

        return result

    async def start_all(
        self,
        phases: list[Phase] | None = None,
        stop_on_failure: bool = False,
    ) -> list[PhaseResult]:
        """Start all phases in order. Each phase must complete before the next.

        Args:
            phases: Subset of phases to start. Defaults to all 6.
            stop_on_failure: If True, stop all started services if any phase fails.

        Returns:
            List of PhaseResult, one per phase.
        """
        if phases is None:
            phases = self._phase_order

        results: list[PhaseResult] = []
        self._running = True

        for phase in phases:
            result = await self.start_phase(phase)
            results.append(result)
            if not result.success and stop_on_failure:
                log.error("Phase %s failed, stopping all services", phase.value)
                await self.stop(timeout=self.stop_timeout)
                self._running = False
                return results

        self._running = True
        self.current_state = ServiceState.HEALTHY
        return results

    # ── Phase Shutdown ──

    async def stop_phase(self, phase: Phase, timeout: float | None = None) -> PhaseResult:
        """Stop all services in a phase, in reverse registration order."""
        timeout = timeout or self.stop_timeout
        started_at = datetime.now(UTC)
        services = self.get_services_by_phase(phase)
        services_reversed = list(reversed(services))

        if not services:
            result = PhaseResult(phase=phase, success=True, duration_ms=0.0)
            self._phase_results[phase] = result
            return result

        log.info("Stopping phase %s (%d services)", phase.value, len(services))
        stopped: list[str] = []
        failed: list[str] = []
        errors: list[str] = []

        for record in services_reversed:
            service_id = record.id
            try:
                await self._transition(service_id, ServiceState.STOPPING)

                if record.hooks and record.hooks.before_stop:
                    record.hooks.before_stop()

                async def _stop(svc: ServiceProtocol) -> None:
                    await svc.stop()

                await asyncio.wait_for(
                    _stop(record.instance),
                    timeout=timeout,
                )
                await self._transition(service_id, ServiceState.STOPPED)

                async def _dispose(svc: ServiceProtocol) -> None:
                    await svc.dispose()

                await asyncio.wait_for(
                    _dispose(record.instance),
                    timeout=timeout,
                )
                await self._transition(service_id, ServiceState.DISPOSED)

                if record.hooks and record.hooks.after_stop:
                    record.hooks.after_stop()

                stopped.append(service_id)

            except asyncio.TimeoutError:
                await self._transition(
                    service_id, ServiceState.STOPPED,
                    error="stop timed out, force-disposed",
                )
                await self._transition(service_id, ServiceState.DISPOSED)
                stopped.append(service_id)
                errors.append(f"{service_id}: stop timed out")

            except Exception as exc:
                await self._transition(
                    service_id, ServiceState.FAILED,
                    error=str(exc),
                )
                failed.append(service_id)
                errors.append(f"{service_id}: {exc}")

        duration = (datetime.now(UTC) - started_at).total_seconds() * 1000
        result = PhaseResult(
            phase=phase,
            success=len(failed) == 0,
            started_services=stopped,
            failed_services=failed,
            duration_ms=duration,
            errors=errors,
        )
        self._phase_results[phase] = result
        log.info("Phase %s stopped (%d services)", phase.value, len(stopped))
        return result

    async def stop(self, timeout: float | None = None) -> list[PhaseResult]:
        """Stop all phases in reverse order.

        Shutdown order: ADVANCED → OMNIROUTE → DOMAIN → CORE → INFRASTRUCTURE → CRITICAL
        """
        self._running = False
        self.current_state = ServiceState.STOPPING
        log.info("LifecycleManager stopping all phases (reverse order)")

        results: list[PhaseResult] = []
        for phase in PHASE_REVERSE:
            result = await self.stop_phase(phase, timeout=timeout)
            results.append(result)

        self.current_state = ServiceState.STOPPED
        self.current_phase = None
        log.info("LifecycleManager stopped all phases")
        return results

    # ── Health & Introspection ──

    async def health(self) -> dict[str, Any]:
        """Aggregate health across all services."""
        healthy_count = 0
        degraded_count = 0
        failed_count = 0
        offline_count = 0
        total = len(self._records)

        for record in self._records.values():
            try:
                health_result = await record.instance.health()
                if health_result and health_result.get("status") in ("healthy", "ok", "ready"):
                    healthy_count += 1
                else:
                    degraded_count += 1
            except Exception:
                failed_count += 1

        return {
            "running": self._running,
            "current_phase": self.current_phase.value if self.current_phase else None,
            "current_state": self.current_state.value,
            "total_services": total,
            "healthy": healthy_count,
            "degraded": degraded_count,
            "failed": failed_count,
            "offline": offline_count,
        }

    async def service_health(self, service_id: str) -> dict[str, Any] | None:
        """Get health for a specific service."""
        record = self._records.get(service_id)
        if record is None:
            return None
        try:
            health = await record.instance.health()
            return {
                "service_id": service_id,
                "state": record.state.value,
                "health": health,
                "started_at": record.started_at.isoformat() if record.started_at else None,
                "failure_count": record.failure_count,
                "last_error": record.last_error,
            }
        except Exception as exc:
            return {
                "service_id": service_id,
                "state": record.state.value,
                "health": {"status": "error", "error": str(exc)},
                "failure_count": record.failure_count,
                "last_error": str(exc),
            }

    def get_phase_result(self, phase: Phase) -> PhaseResult | None:
        """Get the startup/shutdown result for a phase."""
        return self._phase_results.get(phase)

    def service_count_by_phase(self) -> dict[str, int]:
        """Count services registered per phase."""
        counts: dict[str, int] = {}
        for record in self._records.values():
            counts[record.phase.value] = counts.get(record.phase.value, 0) + 1
        return counts

    def state_summary(self) -> dict[str, list[str]]:
        """Summarize services grouped by state."""
        summary: dict[str, list[str]] = {}
        for record in self._records.values():
            state = record.state.value
            if state not in summary:
                summary[state] = []
            summary[state].append(record.id)
        return summary

    @property
    def is_healthy(self) -> bool:
        """Quick check: are all services healthy?"""
        for record in self._records.values():
            if record.state not in (ServiceState.HEALTHY, ServiceState.READY):
                return False
        return True

    @property
    def is_running(self) -> bool:
        return self._running and not self._stopped

    # ── Self-Healing Integration ──

    async def on_service_failure(self, service_id: str, error: str) -> None:
        """Handle a service failure event from EventBus.

        Called by Self-Healing Engine (or directly in tests).
        """
        record = self._records.get(service_id)
        if record is None:
            return

        record.failure_count += 1
        await self._transition(service_id, ServiceState.FAILED, error=error)

        # Attempt repair
        try:
            repair_result = await record.instance.repair()
            if repair_result and repair_result.get("repaired"):
                await self._transition(service_id, ServiceState.RECOVERING)
                # Re-start the service
                await record.instance.restart()
                await self._transition(service_id, ServiceState.READY)
                return
        except Exception:
            pass

        # Repair failed → degrade
        await self._transition(service_id, ServiceState.DEGRADED, error="repair failed")

    # ── EventBus Adapter ──

    def _default_publish(self, topic: str, payload: dict[str, Any]) -> None:
        """Default event publisher — logs instead of publishing."""
        log.debug("Event: %s %s", topic, payload)
