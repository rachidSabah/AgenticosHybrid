"""Discovery cache — TTL-based caching of provider results."""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import timedelta

from agentic_os.domain.discovery import DiscoveryCacheEntry, _utcnow


@dataclass
class DiscoveryCache:
    """TTL-based cache for discovery results to avoid redundant scanning.

    Entries are keyed by a deterministic hash of (provider, engine_name, endpoint).
    Expired entries are skipped on get() and can be bulk-cleaned.
    """

    _entries: dict[str, DiscoveryCacheEntry] = field(default_factory=dict)
    ttl_seconds: float = 300.0
    max_entries: int = 1000

    # ── Core operations ──

    def get(self, key: str) -> DiscoveryCacheEntry | None:
        """Get a non-expired entry by key. Returns None if missing or expired."""
        entry = self._entries.get(key)
        if entry is None:
            return None
        if entry.is_expired():
            del self._entries[key]
            return None
        # Bump hit count
        bumped = entry.with_hit()
        self._entries[key] = bumped
        return bumped

    def set(self, entry: DiscoveryCacheEntry) -> None:
        """Store a cache entry, evicting if over capacity."""
        if len(self._entries) >= self.max_entries and entry.key not in self._entries:
            self._evict_one()
        self._entries[entry.key] = entry

    # ── Key management ──

    @staticmethod
    def make_key(provider: str, engine_name: str, endpoint: str) -> str:
        """Generate a deterministic cache key from provider + engine identity."""
        raw = f"{provider}::{engine_name}::{endpoint or ''}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]

    # ── Entry creation ──

    def create_entry(
        self,
        provider_name: str,
        engine_name: str,
        endpoint: str,
        registration_dict: dict,
        confidence: float,
    ) -> DiscoveryCacheEntry:
        """Create and store a new cache entry for a discovery result."""
        now = _utcnow()
        key = self.make_key(provider_name, engine_name, endpoint)
        entry = DiscoveryCacheEntry(
            key=key,
            registration_json=json.dumps(registration_dict, default=str),
            confidence=confidence,
            provider_name=provider_name,
            discovered_at=now,
            expires_at=now + timedelta(seconds=self.ttl_seconds),
        )
        self.set(entry)
        return entry

    # ── Invalidation ──

    def invalidate(self, key: str) -> None:
        """Remove a single cache entry by key."""
        self._entries.pop(key, None)

    def invalidate_by_provider(self, provider_name: str) -> int:
        """Remove all entries for a given provider. Returns count removed."""
        before = len(self._entries)
        self._entries = {k: v for k, v in self._entries.items() if v.provider_name != provider_name}
        return before - len(self._entries)

    def invalidate_by_engine(self, engine_name: str) -> int:
        """Remove all entries for a given engine name. Returns count removed."""
        before = len(self._entries)
        self._entries = {k: v for k, v in self._entries.items() if v.provider_name != engine_name}
        return before - len(self._entries)

    def invalidate_all(self) -> int:
        """Remove all entries. Returns count removed."""
        count = len(self._entries)
        self._entries.clear()
        return count

    def clean_expired(self) -> int:
        """Remove all expired entries. Returns count removed."""
        before = len(self._entries)
        self._entries = {k: v for k, v in self._entries.items() if not v.is_expired()}
        return before - len(self._entries)

    # ── Query ──

    def list_entries(self) -> list[DiscoveryCacheEntry]:
        """Return all non-expired entries."""
        now = _utcnow()
        return [e for e in self._entries.values() if e.expires_at > now]

    def count(self) -> int:
        """Return the number of entries (including expired, cleaned lazily)."""
        return len(self._entries)

    def get_stats(self) -> dict:
        """Return cache statistics."""
        entries = self.list_entries()
        total_hits = sum(e.hit_count for e in entries)
        return {
            "total_entries": len(self._entries),
            "active_entries": len(entries),
            "total_hits": total_hits,
            "max_entries": self.max_entries,
            "ttl_seconds": self.ttl_seconds,
        }

    # ── Internal ──

    def _evict_one(self) -> None:
        """Evict the oldest (or expired) entry when over capacity."""
        # Prefer evicting expired first
        if self.clean_expired() > 0:
            return
        # Otherwise evict the entry with the lowest hit count (LRU-like)
        if not self._entries:
            return
        oldest_key = min(self._entries, key=lambda k: self._entries[k].hit_count)
        del self._entries[oldest_key]
