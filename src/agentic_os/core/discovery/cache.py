"""Discovery cache -- delegates to services/runtime_discovery/ implementation.

The canonical TTL-based discovery cache lives in
services.runtime_discovery.cache. This module wraps
services.runtime_discovery.cache.RuntimeCache as the backing store while
preserving the DiscoveryCache public API used by the kernel and
:class:.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import timedelta

from services.runtime_discovery.cache import RuntimeCache
from services.runtime_discovery.models import RuntimeCacheEntry, RuntimeType

from agentic_os.domain.discovery import DiscoveryCacheEntry, _utcnow


@dataclass
class DiscoveryCache:
    """TTL-based cache for discovery results -- delegates to RuntimeCache.

    Entries are keyed by a deterministic hash of (provider, engine_name, endpoint).
    Expired entries are skipped on get() and can be bulk-cleaned.

    When cache_dir is provided, entries are persisted to disk and survive
    process restarts (see services.runtime_discovery.cache.RuntimeCache).
    """

    ttl_seconds: float = 300.0
    max_entries: int = 1000
    cache_dir: str | None = None

    def __post_init__(self) -> None:
        self._backend = RuntimeCache(
            ttl_seconds=int(self.ttl_seconds),
            max_entries=self.max_entries,
            cache_dir=self.cache_dir,
        )

    # -- Core operations --

    def get(self, key: str) -> DiscoveryCacheEntry | None:
        """Get a non-expired entry by key. Returns None if missing or expired."""
        entry = self._backend.get(key)
        if entry is None:
            return None
        return self._to_discovery_entry(entry)

    def set(self, entry: DiscoveryCacheEntry) -> None:
        """Store a cache entry, evicting if over capacity."""
        # Sync max_entries if set after init
        self._sync_config()
        self._backend.set(self._to_runtime_entry(entry))

    # -- Key management --

    @staticmethod
    def make_key(provider: str, engine_name: str, endpoint: str) -> str:
        """Generate a deterministic cache key from provider + engine identity."""
        raw = f"{provider}::{engine_name}::{endpoint or ''}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]

    # -- Entry creation --

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

    # -- Invalidation --

    def invalidate(self, key: str) -> None:
        """Remove a single cache entry by key."""
        self._backend.invalidate(key)

    def invalidate_by_provider(self, provider_name: str) -> int:
        """Remove all entries for a given provider. Returns count removed."""
        self._backend.clean_expired()
        to_remove = [
            k
            for k, v in self._backend._entries.items()
            if v.data.get("provider_name") == provider_name
        ]
        for k in to_remove:
            self._backend._entries.pop(k, None)
        return len(to_remove)

    def invalidate_by_engine(self, engine_name: str) -> int:
        """Remove all entries for a given engine name. Returns count removed."""
        self._backend.clean_expired()
        to_remove = [
            k for k, v in self._backend._entries.items() if v.data.get("engine_name") == engine_name
        ]
        for k in to_remove:
            self._backend._entries.pop(k, None)
        return len(to_remove)

    def invalidate_all(self) -> int:
        """Remove all entries. Returns count removed."""
        before = self._backend.count()
        self._backend.invalidate_all()
        return before

    def clean_expired(self) -> int:
        """Remove all expired entries. Returns count removed."""
        return self._backend.clean_expired()

    # -- Query --

    def list_entries(self) -> list[DiscoveryCacheEntry]:
        """Return all non-expired entries."""
        return [self._to_discovery_entry(e) for e in self._backend.list_entries()]

    def count(self) -> int:
        """Return the number of active (non-expired) entries."""
        return self._backend.count()

    def get_stats(self) -> dict:
        """Return cache statistics."""
        stats = self._backend.get_stats()
        entries = self._backend.list_entries()
        stats["active_entries"] = len(entries)
        return stats

    # -- Internal --

    def _sync_config(self) -> None:
        """Sync max_entries to backend if changed after init."""
        if self._backend._max_entries != self.max_entries:
            self._backend._max_entries = self.max_entries
        if self._backend._ttl_seconds != int(self.ttl_seconds):
            self._backend._ttl_seconds = int(self.ttl_seconds)

    @staticmethod
    def _to_discovery_entry(entry: RuntimeCacheEntry) -> DiscoveryCacheEntry:
        """Convert a RuntimeCacheEntry to a DiscoveryCacheEntry."""
        return DiscoveryCacheEntry(
            key=entry.key,
            registration_json=entry.data.get("registration_json", "{}"),
            confidence=entry.data.get("confidence", 0.0),
            provider_name=entry.data.get("provider_name", entry.name),
            discovered_at=entry.created_at,
            expires_at=entry.expires_at,
            hit_count=entry.hit_count,
        )

    @staticmethod
    def _to_runtime_entry(entry: DiscoveryCacheEntry) -> RuntimeCacheEntry:
        """Convert a DiscoveryCacheEntry to a RuntimeCacheEntry."""
        return RuntimeCacheEntry(
            key=entry.key,
            runtime_type=RuntimeType.CUSTOM,
            name=entry.provider_name,
            data={
                "registration_json": entry.registration_json,
                "confidence": entry.confidence,
                "provider_name": entry.provider_name,
                "engine_name": entry.provider_name,
            },
            created_at=entry.discovered_at,
            expires_at=entry.expires_at,
            hit_count=entry.hit_count,
        )
