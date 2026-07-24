"""Tests for DiscoveryCache — TTL-based caching of discovery results."""

import json
from datetime import timedelta

import pytest
from services.runtime_discovery.models import RuntimeCacheEntry, RuntimeType

from agentic_os.core.discovery.cache import DiscoveryCache
from agentic_os.domain.discovery import _utcnow


class TestDiscoveryCache:
    @pytest.fixture
    def cache(self) -> DiscoveryCache:
        return DiscoveryCache()

    # ── Create and retrieve ──

    def test_create_and_get_entry(self, cache: DiscoveryCache) -> None:
        reg = {"name": "engine1", "engine_type": "generic", "endpoint": "http://localhost:8080"}
        entry = cache.create_entry("provider1", "engine1", "http://localhost:8080", reg, 0.9)
        assert entry.key is not None
        assert entry.provider_name == "provider1"
        assert entry.confidence == 0.9

        retrieved = cache.get(entry.key)
        assert retrieved is not None
        assert retrieved.key == entry.key
        assert retrieved.provider_name == "provider1"

    def test_get_unknown_key_returns_none(self, cache: DiscoveryCache) -> None:
        assert cache.get("nonexistent") is None

    def test_create_entry_stores_json(self, cache: DiscoveryCache) -> None:
        reg = {"name": "engine1", "endpoint": "http://localhost:8080"}
        entry = cache.create_entry("p1", "engine1", "http://localhost:8080", reg, 0.9)
        assert json.loads(entry.registration_json) == reg

    # ── make_key ──

    def test_make_key_deterministic(self, cache: DiscoveryCache) -> None:
        key1 = cache.make_key("provider", "engine", "endpoint")
        key2 = cache.make_key("provider", "engine", "endpoint")
        assert key1 == key2
        assert len(key1) == 32  # SHA256 hexdigest truncated to 32

    def test_make_key_different_provider(self, cache: DiscoveryCache) -> None:
        k1 = cache.make_key("p1", "engine", "endpoint")
        k2 = cache.make_key("p2", "engine", "endpoint")
        assert k1 != k2

    def test_make_key_handles_none_endpoint(self, cache: DiscoveryCache) -> None:
        key = cache.make_key("provider", "engine", "")
        assert len(key) == 32

    def test_make_key_static_method(self) -> None:
        """make_key should be usable without an instance."""
        key = DiscoveryCache.make_key("provider", "engine", "endpoint")
        assert len(key) == 32

    # ── Invalidation ──

    def test_invalidate_single_entry(self, cache: DiscoveryCache) -> None:
        reg = {"name": "engine1", "endpoint": "http://localhost:8080"}
        entry = cache.create_entry("p1", "engine1", "http://localhost:8080", reg, 0.9)
        assert cache.get(entry.key) is not None
        cache.invalidate(entry.key)
        assert cache.get(entry.key) is None

    def test_invalidate_nonexistent_no_error(self, cache: DiscoveryCache) -> None:
        cache.invalidate("nonexistent")  # should not raise

    def test_invalidate_by_provider(self, cache: DiscoveryCache) -> None:
        cache.create_entry("p1", "engine1", "e1", {"name": "e1"}, 0.9)
        cache.create_entry("p1", "engine2", "e2", {"name": "e2"}, 0.9)
        cache.create_entry("p2", "engine3", "e3", {"name": "e3"}, 0.9)
        removed = cache.invalidate_by_provider("p1")
        assert removed == 2
        assert cache.count() == 1

    def test_invalidate_by_provider_none_matches(self, cache: DiscoveryCache) -> None:
        cache.create_entry("p1", "engine1", "e1", {"name": "e1"}, 0.9)
        removed = cache.invalidate_by_provider("nonexistent")
        assert removed == 0

    def test_invalidate_all_returns_count(self, cache: DiscoveryCache) -> None:
        cache.create_entry("p1", "e1", "ep1", {"name": "e1"}, 0.9)
        cache.create_entry("p2", "e2", "ep2", {"name": "e2"}, 0.9)
        removed = cache.invalidate_all()
        assert removed == 2
        assert cache.count() == 0

    def test_invalidate_all_empty(self, cache: DiscoveryCache) -> None:
        removed = cache.invalidate_all()
        assert removed == 0

    # ── list_entries ──

    def test_list_entries(self, cache: DiscoveryCache) -> None:
        cache.create_entry("p1", "e1", "ep1", {"name": "e1"}, 0.9)
        cache.create_entry("p2", "e2", "ep2", {"name": "e2"}, 0.7)
        entries = cache.list_entries()
        assert len(entries) == 2

    def test_list_entries_empty(self, cache: DiscoveryCache) -> None:
        assert cache.list_entries() == []

    # ── get_stats ──

    def test_get_stats(self, cache: DiscoveryCache) -> None:
        cache.create_entry("p1", "e1", "ep1", {"name": "e1"}, 0.9)
        stats = cache.get_stats()
        assert stats["active_entries"] == 1
        assert stats["total_entries"] == 1
        assert stats["max_entries"] == 1000
        assert stats["ttl_seconds"] == 300.0
        assert stats["total_hits"] == 0

    # ── TTL expiry ──

    def test_get_expired_returns_none(self, cache: DiscoveryCache) -> None:
        reg = {"name": "engine1", "endpoint": "http://localhost:8080"}
        entry = cache.create_entry("p1", "engine1", "http://localhost:8080", reg, 0.9)

        # Manually expire the entry via the backend
        rce = RuntimeCacheEntry(
            key=entry.key,
            runtime_type=RuntimeType.CUSTOM,
            name=entry.provider_name,
            data={
                "registration_json": entry.registration_json,
                "confidence": entry.confidence,
                "provider_name": entry.provider_name,
            },
            created_at=entry.discovered_at,
            expires_at=_utcnow() - timedelta(seconds=1),
        )
        cache._backend._entries[entry.key] = rce
        assert cache.get(entry.key) is None

    def test_get_bumps_hit_count(self, cache: DiscoveryCache) -> None:
        reg = {"name": "engine1", "endpoint": "http://localhost:8080"}
        entry = cache.create_entry("p1", "engine1", "http://localhost:8080", reg, 0.9)
        retrieved = cache.get(entry.key)
        assert retrieved is not None
        assert retrieved.hit_count == 1
        # Second hit
        retrieved2 = cache.get(entry.key)
        assert retrieved2 is not None
        assert retrieved2.hit_count == 2

    def test_clean_expired(self, cache: DiscoveryCache) -> None:
        reg = {"name": "e1", "endpoint": "ep1"}
        entry = cache.create_entry("p1", "e1", "ep1", reg, 0.9)

        # Add expired entry via the backend
        expired = RuntimeCacheEntry(
            key="expired_key",
            runtime_type=RuntimeType.CUSTOM,
            name="p2",
            data={
                "registration_json": '{"name": "expired"}',
                "confidence": 0.5,
                "provider_name": "p2",
            },
            expires_at=_utcnow() - timedelta(seconds=1),
        )
        cache._backend._entries["expired_key"] = expired

        removed = cache.clean_expired()
        # expired_key should be cleaned; the valid entry stays
        assert removed >= 1
        assert cache.get(entry.key) is not None

    def test_clean_expired_none(self, cache: DiscoveryCache) -> None:
        cache.create_entry("p1", "e1", "ep1", {"name": "e1"}, 0.9)
        removed = cache.clean_expired()
        assert removed == 0

    # ── Max entries enforcement ──

    def test_eviction_when_over_capacity(self, cache: DiscoveryCache) -> None:
        cache.max_entries = 2
        cache.create_entry("p1", "e1", "ep1", {"name": "e1"}, 0.9)
        cache.create_entry("p1", "e2", "ep2", {"name": "e2"}, 0.9)
        cache.create_entry("p1", "e3", "ep3", {"name": "e3"}, 0.9)
        # Should have evicted the oldest (lowest hit_count)
        assert cache.count() == 2

    def test_eviction_prefers_expired(self, cache: DiscoveryCache) -> None:
        cache.max_entries = 1
        reg = {"name": "e1", "endpoint": "ep1"}
        entry = cache.create_entry("p1", "e1", "ep1", reg, 0.9)

        # Manually expire it via the backend
        rce = RuntimeCacheEntry(
            key=entry.key,
            runtime_type=RuntimeType.CUSTOM,
            name=entry.provider_name,
            data={
                "registration_json": entry.registration_json,
                "confidence": entry.confidence,
                "provider_name": entry.provider_name,
            },
            created_at=entry.discovered_at,
            expires_at=_utcnow() - timedelta(seconds=1),
        )
        cache._backend._entries[entry.key] = rce

        # This should evict the expired entry (via clean_expired) rather than raising
        cache.create_entry("p1", "e2", "ep2", {"name": "e2"}, 0.9)
        assert cache.count() == 1
