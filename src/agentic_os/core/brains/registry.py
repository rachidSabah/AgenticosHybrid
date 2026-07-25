"""BrainRegistry — central registry for all known AI brains.

Thread-safe dict-backed registry that manages :class:`BrainRecord` instances
and publishes lifecycle events via the event bus.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import Any

from agentic_os.domain.brains import BrainRecord, BrainStatus
from agentic_os.domain.events import EventEnvelope, Topic
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.event_bus import EventBus

log = get_logger("brains.registry")


class BrainRegistry:
    """Central registry for all known :class:`BrainRecord` instances.

    Thread-safety
    -------------
    All public methods that read or mutate internal state acquire an
    ``asyncio.Lock``.  The lock is *not* re-entrant; never call a public
    method from inside another public method on the same instance.

    Lifecycle
    ---------
    ::

        registry = BrainRegistry()
        await registry.start(event_bus=bus)
        # ... use registry ...
        await registry.stop()
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._brains: dict[str, BrainRecord] = {}
        self._event_bus: EventBus | None = None
        self._started = False

    # ── Lifecycle ───────────────────────────────────────────────────────────

    async def start(self, event_bus: EventBus | None = None) -> None:
        """Initialise the registry with an optional event bus.

        Args:
            event_bus: When provided, lifecycle events will be published
                automatically on register / unregister / update.
        """
        self._event_bus = event_bus
        self._started = True
        log.info("BrainRegistry started")

    async def stop(self) -> None:
        """Clear all brains and stop the registry."""
        async with self._lock:
            self._brains.clear()
            self._started = False
        log.info("BrainRegistry stopped")

    # ── Registration ────────────────────────────────────────────────────────

    async def register(self, record: BrainRecord) -> BrainRecord:
        """Register a brain record, or update an existing one.

        If a brain with the same ``.id`` already exists it is replaced.
        Publishes ``BRAIN_REGISTERED`` / ``BRAIN_UPDATED``.

        Returns:
            The stored (possibly updated) :class:`BrainRecord`.
        """
        async with self._lock:
            existing = self._brains.get(record.id)
            if existing is not None:
                merged = self._merge(record, existing)
                self._brains[record.id] = merged
                stored = merged
                event_topic = Topic.BRAIN_UPDATED
            else:
                self._brains[record.id] = record
                stored = record
                event_topic = Topic.BRAIN_REGISTERED

        await self._publish(event_topic, stored)
        log.debug("Registered brain %s (%s)", stored.id, stored.display_name)
        return stored

    async def unregister(self, brain_id: str) -> bool:
        """Remove a brain from the registry.

        Args:
            brain_id: The unique identifier of the brain to remove.

        Returns:
            ``True`` if the brain existed and was removed, ``False`` otherwise.
        """
        async with self._lock:
            record = self._brains.pop(brain_id, None)
            if record is None:
                return False
            removed = replace(record, status=BrainStatus.REMOVED)

        await self._publish(Topic.BRAIN_REMOVED, removed)
        log.info("Unregistered brain %s (%s)", brain_id, removed.display_name)
        return True

    async def update(self, brain_id: str, **updates: Any) -> BrainRecord | None:
        """Update selected fields on an existing brain record.

        Only the fields passed as keyword arguments are changed; the rest
        remain untouched.  Publishes ``BRAIN_UPDATED``.

        Args:
            brain_id: The unique identifier of the brain to update.

        Returns:
            The updated :class:`BrainRecord`, or ``None`` if not found.
        """
        async with self._lock:
            existing = self._brains.get(brain_id)
            if existing is None:
                log.warning("update: unknown brain_id '%s'", brain_id)
                return None
            updated = replace(existing, **updates)
            self._brains[brain_id] = updated

        await self._publish(Topic.BRAIN_UPDATED, updated)
        return updated

    async def mark_status(self, brain_id: str, status: BrainStatus) -> BrainRecord | None:
        """Convenience: update a brain's status field only.

        Delegates to :meth:`update` and publishes the appropriate topic
        automatically based on the new status.
        """
        return await self.update(brain_id, status=status)

    # ── Lookup / Query ──────────────────────────────────────────────────────

    async def get(self, brain_id: str) -> BrainRecord | None:
        """Retrieve a single brain by ID.

        Complexity: O(1) dict lookup.
        """
        async with self._lock:
            return self._brains.get(brain_id)

    async def list_all(self) -> list[BrainRecord]:
        """Return a snapshot of all registered brains.

        Complexity: O(*n*) — returns a shallow copy.
        """
        async with self._lock:
            return list(self._brains.values())

    async def search(
        self,
        *,
        brain_type: str | None = None,
        vendor: str | None = None,
        status: str | None = None,
        tag: str | None = None,
        running: bool | None = None,
        limit: int = 0,
    ) -> list[BrainRecord]:
        """Filter brains by one or more criteria.

        Args:
            brain_type: Optional ``BrainType`` value to match.
            vendor: Optional ``BrainVendor`` value to match.
            status: Optional ``BrainStatus`` value to match.
            tag: Optional tag string; matches any brain whose ``.tags``
                tuple contains this value.
            running: When ``True`` only return brains in an active state
                (see :meth:`BrainRecord.running`); when ``False`` return
                those that are *not* active.
            limit: Maximum number of results.  0 means unlimited.

        Returns:
            A list of matching :class:`BrainRecord` objects.  Order is
            not guaranteed.
        """
        async with self._lock:
            results = list(self._brains.values())

        if brain_type is not None:
            results = [r for r in results if r.brain_type.value == brain_type]
        if vendor is not None:
            results = [r for r in results if r.vendor.value == vendor]
        if status is not None:
            results = [r for r in results if r.status.value == status]
        if tag is not None:
            results = [r for r in results if tag in r.tags]
        if running is True:
            results = [r for r in results if r.running()]
        elif running is False:
            results = [r for r in results if not r.running()]

        if limit > 0:
            results = results[:limit]
        return results

    async def count(self) -> int:
        """Return the total number of registered brains.

        Complexity: O(1).
        """
        async with self._lock:
            return len(self._brains)

    # ── Internals ───────────────────────────────────────────────────────────

    @staticmethod
    def _merge(record: BrainRecord, existing: BrainRecord) -> BrainRecord:
        """Merge a new record into an existing one, preserving fields that
        are not provided (empty / default) in the new record.

        Both records are frozen — this builds a new instance via ``replace``.
        """
        kwargs: dict[str, Any] = {}
        for field_name in (
            "display_name",
            "version",
            "brain_type",
            "vendor",
            "runtime",
            "health",
            "workspace",
        ):
            new_val = getattr(record, field_name)
            if new_val != getattr(type(existing), field_name, None) and new_val:
                kwargs[field_name] = new_val

        kwargs["capabilities"] = (
            record.capabilities if record.capabilities else existing.capabilities
        )
        kwargs["supported_models"] = (
            record.supported_models if record.supported_models else existing.supported_models
        )
        kwargs["supported_tools"] = (
            record.supported_tools if record.supported_tools else existing.supported_tools
        )
        kwargs["tags"] = record.tags if record.tags else existing.tags
        kwargs["metadata"] = {
            **existing.metadata,
            **record.metadata,
        }
        return replace(existing, **kwargs)

    async def _publish(self, topic: Topic, record: BrainRecord) -> None:
        """Publish a brain lifecycle event."""
        bus = self._event_bus
        if bus is None:
            return
        try:
            event = EventEnvelope(
                type=topic.value,
                source="brain_registry",
                topic=topic.value,
                payload=record.to_dict(),
            )
            await bus.publish(event)
        except Exception:
            log.exception("Failed to publish %s for brain %s", topic.value, record.id)
