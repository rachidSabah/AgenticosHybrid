from __future__ import annotations

import json
import time
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any

from core.logging import get_logger
from services.runtime_discovery.models import RuntimeCacheEntry, RuntimeType

_log = get_logger(__name__)

__all__ = ["RuntimeCache"]


class RuntimeCache:
    def __init__(self, ttl_seconds: int = 300, max_entries: int = 1000) -> None:
        self._entries: dict[str, RuntimeCacheEntry] = {}
        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries

    def make_key(self, provider: str, name: str, endpoint: str = "") -> str:
        raw = f"{provider}|{name}|{endpoint}"
        return sha256(raw.encode()).hexdigest()[:16]

    def create_entry(
        self, provider: str, engine_name: str, runtime_type: RuntimeType, data: dict[str, Any]
    ) -> RuntimeCacheEntry:
        key = self.make_key(provider, engine_name, data.get("endpoint", ""))
        return RuntimeCacheEntry(
            key=key,
            runtime_type=runtime_type,
            name=engine_name,
            data=data,
            expires_at=datetime.now(UTC) + timedelta(seconds=self._ttl_seconds),
        )

    def get(self, key: str) -> RuntimeCacheEntry | None:
        entry = self._entries.get(key)
        if entry and entry.is_expired():
            self._entries.pop(key, None)
            return None
        if entry:
            entry.with_hit()
        return entry

    def set(self, entry: RuntimeCacheEntry) -> None:
        if len(self._entries) >= self._max_entries:
            self._evict_one()
        self._entries[entry.key] = entry

    def invalidate(self, key: str) -> None:
        self._entries.pop(key, None)

    def invalidate_by_provider(self, provider: str) -> None:
        prefix = sha256(f"{provider}|".encode()).hexdigest()[:16][:8]
        to_remove = [k for k in self._entries if k.startswith(prefix)]
        for k in to_remove:
            self._entries.pop(k, None)

    def invalidate_by_engine(self, engine_name: str) -> None:
        to_remove = [k for k, v in self._entries.items() if v.name == engine_name]
        for k in to_remove:
            self._entries.pop(k, None)

    def invalidate_all(self) -> None:
        self._entries.clear()

    def clean_expired(self) -> int:
        now = datetime.now(UTC)
        expired = [k for k, v in self._entries.items() if v.is_expired()]
        for k in expired:
            self._entries.pop(k, None)
        return len(expired)

    def list_entries(self) -> list[RuntimeCacheEntry]:
        self.clean_expired()
        return list(self._entries.values())

    def count(self) -> int:
        self.clean_expired()
        return len(self._entries)

    def get_stats(self) -> dict[str, Any]:
        self.clean_expired()
        total_hits = sum(e.hit_count for e in self._entries.values())
        return {
            "total_entries": len(self._entries),
            "total_hits": total_hits,
            "max_entries": self._max_entries,
            "ttl_seconds": self._ttl_seconds,
        }

    def _evict_one(self) -> None:
        if not self._entries:
            return
        oldest = min(self._entries.keys(), key=lambda k: self._entries[k].created_at)
        self._entries.pop(oldest, None)
