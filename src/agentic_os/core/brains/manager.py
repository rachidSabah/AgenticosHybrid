"""BrainManager — lifecycle controls for registered brains.

Provides pause / resume / restart / shutdown / recover operations that
transition a brain's :class:`BrainStatus` and publish events.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import Any

from agentic_os.domain.brains import BrainRecord, BrainStatus
from agentic_os.domain.events import EventEnvelope, Topic
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.event_bus import EventBus

log = get_logger("brains.manager")


async def _none_get(brain_id: str) -> None:
    """Default get-brain callback (returns None)."""
    return None


async def _none_update(brain_id: str, **kwargs: Any) -> None:
    """Default update-brain callback (no-op)."""
    return None


class BrainManager:
    """Lifecycle manager for :class:`BrainRecord` instances.

    Provides high-level operations (pause, resume, restart, shutdown,
    recover) that transition a brain's status and publish corresponding
    events.  The manager reads from a :class:`BrainRegistry` (or can be
    given a dict-like mapping of brain_id → BrainRecord) and writes
    status updates back through a writeable store.

    Thread-safety
    -------------
    Internal state is guarded by an ``asyncio.Lock``.
    """

    def __init__(
        self,
        *,
        get_brain: Any | None = None,
        update_brain: Any | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        """Initialise the manager.

        Args:
            get_brain: An async callable ``(brain_id) -> BrainRecord | None``.
                Defaults to a no-op that returns ``None``.
            update_brain: An async callable ``(brain_id, **updates) -> BrainRecord | None``.
                Defaults to a no-op.
            event_bus: Optional event bus for publishing lifecycle events.
        """
        self._lock = asyncio.Lock()
        self._event_bus = event_bus
        self._get = get_brain or _none_get
        self._update = update_brain or _none_update

    # ── Lifecycle operations ────────────────────────────────────────────────

    async def pause(self, brain_id: str) -> BrainRecord | None:
        """Transition a brain to :attr:`BrainStatus.PAUSED`.

        The brain must currently be in an active state (connected, idle,
        busy, or executing).

        Returns:
            The updated :class:`BrainRecord`, or ``None`` if not found.
        """
        async with self._lock:
            current = await self._get(brain_id)  # type: ignore[misc]
            if current is None:
                return None
            if not self._can_pause(current):
                log.warning(
                    "Cannot pause brain %s in status %s",
                    brain_id,
                    current.status.value,
                )
                return None
            updated = replace(current, status=BrainStatus.PAUSED)
            result = await self._update(brain_id, status=BrainStatus.PAUSED)  # type: ignore[misc]

        await self._publish(Topic.BRAIN_DISCONNECTED, updated)
        log.info("Paused brain %s (%s)", brain_id, updated.display_name)
        return result

    async def resume(self, brain_id: str) -> BrainRecord | None:
        """Transition a paused brain back to :attr:`BrainStatus.IDLE`.

        Returns:
            The updated :class:`BrainRecord`, or ``None`` if not found
            or not currently paused.
        """
        async with self._lock:
            current = await self._get(brain_id)  # type: ignore[misc]
            if current is None:
                return None
            if current.status != BrainStatus.PAUSED:
                log.warning(
                    "Cannot resume brain %s (status=%s)",
                    brain_id,
                    current.status.value,
                )
                return None
            result = await self._update(brain_id, status=BrainStatus.IDLE)  # type: ignore[misc]

        if result is not None:
            await self._publish(Topic.BRAIN_CONNECTED, result)
            log.info("Resumed brain %s (%s)", brain_id, result.display_name)
        return result

    async def restart(self, brain_id: str) -> BrainRecord | None:
        """Restart a brain by transitioning through ``RESTARTING`` → ``IDLE``.

        Returns:
            The updated :class:`BrainRecord`, or ``None`` if not found.
        """
        async with self._lock:
            current = await self._get(brain_id)  # type: ignore[misc]
            if current is None:
                return None
            restarting = replace(current, status=BrainStatus.RESTARTING)
            result = await self._update(  # type: ignore[misc]
                brain_id, status=BrainStatus.IDLE
            )

        if result is not None:
            await self._publish(Topic.BRAIN_UPDATED, restarting)
            await self._publish(Topic.BRAIN_CONNECTED, result)
            log.info("Restarted brain %s (%s)", brain_id, result.display_name)
        return result

    async def shutdown(self, brain_id: str) -> BrainRecord | None:
        """Shut down a brain and mark it as :attr:`BrainStatus.SHUTDOWN`.

        Returns:
            The updated :class:`BrainRecord`, or ``None`` if not found.
        """
        async with self._lock:
            current = await self._get(brain_id)  # type: ignore[misc]
            if current is None:
                return None
            result = await self._update(  # type: ignore[misc]
                brain_id, status=BrainStatus.SHUTDOWN
            )

        if result is not None:
            await self._publish(Topic.BRAIN_DISCONNECTED, result)
            log.info("Shutdown brain %s (%s)", brain_id, result.display_name)
        return result

    async def recover(self, brain_id: str) -> BrainRecord | None:
        """Attempt recovery of a failed or unhealthy brain.

        Transitions through ``RECOVERING`` → ``IDLE``.

        Returns:
            The updated :class:`BrainRecord`, or ``None`` if the brain
            is not found or not in a recoverable state.
        """
        async with self._lock:
            current = await self._get(brain_id)  # type: ignore[misc]
            if current is None:
                return None
            if current.status not in (
                BrainStatus.FAILED,
                BrainStatus.UNHEALTHY,
                BrainStatus.DEGRADED,
                BrainStatus.DISCONNECTED,
            ):
                log.warning(
                    "Cannot recover brain %s in status %s",
                    brain_id,
                    current.status.value,
                )
                return None
            result = await self._update(  # type: ignore[misc]
                brain_id, status=BrainStatus.IDLE
            )

        if result is not None:
            await self._publish(Topic.AGENT_RECOVERED, result)
            await self._publish(Topic.BRAIN_CONNECTED, result)
            log.info("Recovered brain %s (%s)", brain_id, result.display_name)
        return result

    # ── Status introspection ────────────────────────────────────────────────

    @staticmethod
    def _can_pause(record: BrainRecord) -> bool:
        """Check whether a brain can be paused from its current status."""
        return record.status in (
            BrainStatus.CONNECTED,
            BrainStatus.IDLE,
            BrainStatus.BUSY,
            BrainStatus.EXECUTING,
            BrainStatus.HEALTHY,
        )

    # ── Internals ───────────────────────────────────────────────────────────

    async def _publish(self, topic: Topic, record: BrainRecord) -> None:
        """Publish a brain lifecycle event."""
        bus = self._event_bus
        if bus is None:
            return
        try:
            event = EventEnvelope(
                type=topic.value,
                source="brain_manager",
                topic=topic.value,
                payload=record.to_dict(),
            )
            await bus.publish(event)
        except Exception:
            log.exception("Failed to publish %s for brain %s", topic.value, record.id)
