"""Retention policies for memory scopes.

A :class:`RetentionPolicy` decides (a) whether a freshly written item should get
a TTL and (b) which items to evict when a scope exceeds its size budget. The
default policy applies sensible per-scope defaults: working/conversation memory
is ephemeral (TTL + small cap), project/shared/long-term are durable with a
much larger cap and no auto-expiry.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from agentic_os.domain.memory import MemoryItem, MemoryScope


def _utcnow() -> datetime:
    return datetime.now(UTC)


class RetentionPolicy:
    """Per-scope TTL + max-size retention rules."""

    def __init__(
        self,
        ttl_seconds: dict[MemoryScope, float | None] | None = None,
        max_size: dict[MemoryScope, int] | None = None,
    ) -> None:
        # Default TTLs (seconds); None = never expires.
        self._ttl: dict[MemoryScope, float | None] = {
            MemoryScope.WORKING: 600.0,
            MemoryScope.CONVERSATION: 3600.0,
            MemoryScope.PROJECT: None,
            MemoryScope.SHARED: None,
            MemoryScope.LONG_TERM: None,
        }
        if ttl_seconds:
            self._ttl.update(ttl_seconds)
        # Default caps on stored items per scope.
        self._max: dict[MemoryScope, int] = {
            MemoryScope.WORKING: 256,
            MemoryScope.CONVERSATION: 1024,
            MemoryScope.PROJECT: 8192,
            MemoryScope.SHARED: 8192,
            MemoryScope.LONG_TERM: 65536,
        }
        if max_size:
            self._max.update(max_size)

    def ttl_for(self, scope: MemoryScope) -> float | None:
        return self._ttl.get(scope)

    def applies_expiry(self, scope: MemoryScope) -> bool:
        return self._ttl.get(scope) is not None

    def max_size(self, scope: MemoryScope) -> int:
        return self._max.get(scope, 1024)

    def with_expiry(self, item: MemoryItem) -> MemoryItem:
        """Stamp ``expires_at`` on the item if its scope has a TTL."""
        ttl = self._ttl.get(item.scope)
        if ttl is not None and item.expires_at is None:
            item.expires_at = _utcnow() + timedelta(seconds=ttl)
        return item

    def evictable(self, items: list[MemoryItem]) -> list[MemoryItem]:
        """Pick items to drop so a scope respects its cap.

        Expired items are always evicted first (oldest first); then, if still
        over the cap, the oldest-by-created items go.
        """
        if not items:
            return []
        cap = self._max.get(items[0].scope, 1024)
        expired = sorted((i for i in items if i.is_expired), key=lambda i: i.created_at)
        if len(items) <= cap:
            return expired  # only evict already-expired
        over = len(items) - cap
        live = sorted((i for i in items if not i.is_expired), key=lambda i: i.created_at)
        return expired + live[:over]
