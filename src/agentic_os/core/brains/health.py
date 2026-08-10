"""BrainHealthMonitor — periodic heartbeat checks and stale detection.

Runs a background asyncio loop that periodically checks all registered
brains, marks stale or unresponsive ones, and publishes health change
events.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import replace
from typing import Any

from agentic_os.domain.brains import BrainRecord, BrainStatus
from agentic_os.domain.events import EventEnvelope, Topic
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.event_bus import EventBus

log = get_logger("brains.health")


class BrainHealthMonitor:
    """Periodic health monitor for registered brains.

    Runs a background asyncio loop that iterates all tracked brains,
    checks their last heartbeat timestamp, and transitions stale/unhealthy
    brains to :attr:`BrainStatus.UNHEALTHY`.

    Thread-safety
    -------------
    Internal state (``_brains`` dict) is guarded by an ``asyncio.Lock``.

    Lifecycle
    ---------
    ::

        monitor = BrainHealthMonitor(interval_seconds=30)
        await monitor.start(get_brains_fn, event_bus=bus)
        # ... system runs ...
        await monitor.stop()
    """

    def __init__(
        self,
        interval_seconds: float = 30.0,
        stale_timeout_seconds: float = 120.0,
    ) -> None:
        """Initialise the health monitor.

        Args:
            interval_seconds: How often to run the health check loop.
            stale_timeout_seconds: Heartbeat age (in seconds) beyond
                which a brain is considered stale.
        """
        self._interval = interval_seconds
        self._stale_timeout = stale_timeout_seconds
        self._lock = asyncio.Lock()
        self._brains: dict[str, _BrainHeartbeat] = {}
        self._task: asyncio.Task[None] | None = None
        self._event_bus: EventBus | None = None
        self._get_brains_fn: Any = None
        self._update_fn: Any = None
        self._started = False

    # ── Lifecycle ───────────────────────────────────────────────────────────

    async def start(
        self,
        get_brains: Any,
        update_brain: Any | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        """Start the background health check loop.

        Args:
            get_brains: An async callable ``() -> list[BrainRecord]`` that
                returns all currently registered brains.
            update_brain: Optional async callable ``(brain_id, **updates)``
                to persist status changes.
            event_bus: Optional event bus for publishing health events.
        """
        self._get_brains_fn = get_brains
        self._update_fn = update_brain
        self._event_bus = event_bus
        self._started = True

        # Seed heartbeat timestamps from current brains
        try:
            brains = await get_brains()
            async with self._lock:
                for b in brains:
                    self._brains[b.id] = _BrainHeartbeat(
                        brain_id=b.id,
                        last_heartbeat=time.time(),
                    )
        except Exception:
            log.exception("Failed to seed brains on start")

        self._task = asyncio.create_task(self._loop())
        log.info(
            "BrainHealthMonitor started (interval=%ss, stale_timeout=%ss)",
            self._interval,
            self._stale_timeout,
        )

    async def stop(self) -> None:
        """Stop the background health check loop."""
        self._started = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        async with self._lock:
            self._brains.clear()
        log.info("BrainHealthMonitor stopped")

    # ── Heartbeat recording ─────────────────────────────────────────────────

    async def record_heartbeat(self, brain_id: str) -> None:
        """Record a heartbeat for a brain (called by the brain itself or
        an external reporter).

        Args:
            brain_id: The brain that is still alive.
        """
        async with self._lock:
            if brain_id in self._brains:
                hb = self._brains[brain_id]
                self._brains[brain_id] = _BrainHeartbeat(
                    brain_id=hb.brain_id,
                    last_heartbeat=time.time(),
                )
            else:
                self._brains[brain_id] = _BrainHeartbeat(
                    brain_id=brain_id,
                    last_heartbeat=time.time(),
                )

    async def remove_brain(self, brain_id: str) -> None:
        """Stop tracking a brain (e.g. on unregister)."""
        async with self._lock:
            self._brains.pop(brain_id, None)

    # ── Status query ────────────────────────────────────────────────────────

    async def last_heartbeat(self, brain_id: str) -> float | None:
        """Return the last heartbeat timestamp for a brain, or ``None``."""
        async with self._lock:
            hb = self._brains.get(brain_id)
            return hb.last_heartbeat if hb else None

    async def is_stale(self, brain_id: str) -> bool:
        """Return ``True`` if the brain's heartbeat is older than the
        stale timeout."""
        ts = await self.last_heartbeat(brain_id)
        if ts is None:
            return True
        return (time.time() - ts) > self._stale_timeout

    async def tracking_summary(self) -> dict[str, Any]:
        """Return a snapshot of tracked brains and their heartbeat status."""
        now = time.time()
        async with self._lock:
            summary: dict[str, Any] = {}
            for bid, hb in self._brains.items():
                age = now - hb.last_heartbeat
                summary[bid] = {
                    "last_heartbeat": hb.last_heartbeat,
                    "age_seconds": round(age, 1),
                    "stale": age > self._stale_timeout,
                }
            return summary

    # ── Background loop ─────────────────────────────────────────────────────

    async def _loop(self) -> None:
        """Periodic health check loop."""
        while self._started:
            try:
                await asyncio.sleep(self._interval)
                await self._check_all()
            except asyncio.CancelledError:
                break
            except Exception:
                log.exception("Health check loop error")

    async def _check_all(self) -> None:
        """Check all registered brains for staleness."""
        brains: list[BrainRecord] = []
        try:
            brains = await self._get_brains_fn()
        except Exception:
            log.warning("Failed to fetch brains for health check")
            return

        now = time.time()
        for brain in brains:
            async with self._lock:
                hb = self._brains.get(brain.id)

            if hb is None:
                # Newly registered brain without heartbeat yet
                async with self._lock:
                    self._brains[brain.id] = _BrainHeartbeat(
                        brain_id=brain.id,
                        last_heartbeat=now,
                    )
                continue

            # Auto-heartbeat local CLI and tool agents so active system brains remain healthy
            if brain.brain_type.value in ("local_cli", "custom", "native"):
                async with self._lock:
                    self._brains[brain.id] = _BrainHeartbeat(
                        brain_id=brain.id,
                        last_heartbeat=now,
                    )
                continue

            age = now - hb.last_heartbeat

            if age > self._stale_timeout and brain.status != BrainStatus.UNHEALTHY:
                log.warning(
                    "Brain %s (%s) is stale (age=%.1fs) — marking UNHEALTHY",
                    brain.id,
                    brain.display_name,
                    age,
                )
                await self._mark_unhealthy(brain)

    async def _mark_unhealthy(self, brain: BrainRecord) -> None:
        """Transition a brain to UNHEALTHY and publish an event."""
        updated = replace(brain, status=BrainStatus.UNHEALTHY, health=max(brain.health - 20.0, 0.0))

        # Try to persist
        if self._update_fn is not None:
            try:
                await self._update_fn(
                    brain.id,
                    status=BrainStatus.UNHEALTHY,
                    health=updated.health,
                )
            except Exception:
                log.exception("Failed to update brain %s health", brain.id)

        await self._publish(Topic.BRAIN_HEALTH_CHANGED, updated)

    # ── Event publishing ────────────────────────────────────────────────────

    async def _publish(self, topic: Topic, record: BrainRecord) -> None:
        """Publish a brain lifecycle event."""
        bus = self._event_bus
        if bus is None:
            return
        try:
            event = EventEnvelope(
                type=topic.value,
                source="brain_health_monitor",
                topic=topic.value,
                payload=record.to_dict(),
            )
            await bus.publish(event)
        except Exception:
            log.exception("Failed to publish %s for brain %s", topic.value, record.id)


# ── Internal heartbeat tracking ─────────────────────────────────────────


class _BrainHeartbeat:
    """Lightweight heartbeat tracker for one brain."""

    __slots__ = ("brain_id", "last_heartbeat")

    def __init__(self, brain_id: str, last_heartbeat: float) -> None:
        self.brain_id = brain_id
        self.last_heartbeat = last_heartbeat
