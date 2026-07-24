from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any

from core.logging import get_logger

from services.runtime_discovery.models import RuntimeCacheEntry, RuntimeType

_log = get_logger(__name__)

__all__ = ["RuntimeCache"]

_DEFAULT_CACHE_DIR = Path.home() / ".cache" / "aaios" / "discovery"
_CACHE_FILE_NAME = "discovery_cache.json"


def _serialize(obj: Any) -> str:
    """Serialize non-JSON-serializable types for cache persistence."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, RuntimeType):
        return obj.value
    return str(obj)


def _parse_datetime(value: str) -> datetime:
    """Parse an ISO datetime string to a datetime object."""
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def _entry_to_dict(entry: RuntimeCacheEntry) -> dict[str, Any]:
    """Serialize a RuntimeCacheEntry to a JSON-safe dict."""
    return {
        "key": entry.key,
        "runtime_type": entry.runtime_type.value,
        "name": entry.name,
        "data": entry.data,
        "created_at": entry.created_at.isoformat(),
        "expires_at": entry.expires_at.isoformat(),
        "hit_count": entry.hit_count,
    }


def _entry_from_dict(d: dict[str, Any]) -> RuntimeCacheEntry:
    """Deserialize a dict back into a RuntimeCacheEntry."""
    return RuntimeCacheEntry(
        key=d["key"],
        runtime_type=RuntimeType(d["runtime_type"]),
        name=d["name"],
        data=d.get("data", {}),
        created_at=_parse_datetime(d["created_at"]),
        expires_at=_parse_datetime(d["expires_at"]),
        hit_count=d.get("hit_count", 0),
    )


class RuntimeCache:
    """TTL-based cache for discovery results with file persistence.

    Entries are persisted to ``~/.cache/aaios/discovery/discovery_cache.json``
    so they survive process restarts. Expired entries are cleaned lazily on
    access and on every persistence write.
    """

    def __init__(
        self,
        ttl_seconds: int = 300,
        max_entries: int = 1000,
        cache_dir: str | Path | None = None,
    ) -> None:
        self._entries: dict[str, RuntimeCacheEntry] = {}
        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries
        self._cache_dir: Path | None = Path(cache_dir) if cache_dir else None
        self._cache_file: Path | None = (
            self._cache_dir / _CACHE_FILE_NAME if self._cache_dir else None
        )
        if self._cache_dir:
            self._load()

    # ── File persistence ──────────────────────────────────────────────────

    def _load(self) -> None:
        """Load cache entries from disk, skipping any that are expired."""
        if not self._cache_file or not self._cache_file.exists():
            return
        try:
            raw = self._cache_file.read_text(encoding="utf-8")
            data = json.loads(raw)
            loaded = 0
            expired = 0
            for entry_dict in data.get("entries", {}).values():
                entry = _entry_from_dict(entry_dict)
                if entry.is_expired():
                    expired += 1
                else:
                    self._entries[entry.key] = entry
                    loaded += 1
            if loaded or expired:
                _log.debug(
                    "Loaded %d cache entries (%d expired skipped) from %s",
                    loaded,
                    expired,
                    self._cache_file,
                )
        except (json.JSONDecodeError, OSError, KeyError, ValueError) as exc:
            _log.warning("Failed to load cache from %s: %s", self._cache_file, exc)

    def _save(self) -> None:
        """Atomically persist cache entries to disk."""
        if not self._cache_dir or not self._cache_file:
            return
        self.clean_expired()
        try:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            serializable: dict[str, Any] = {}
            for key, entry in self._entries.items():
                serializable[key] = _entry_to_dict(entry)

            payload = json.dumps(
                {
                    "version": 1,
                    "updated_at": datetime.now(UTC).isoformat(),
                    "entries": serializable,
                },
                indent=2,
                default=_serialize,
            )

            # Atomic write: write to temp, then rename
            fd, tmp_path = tempfile.mkstemp(
                suffix=".tmp",
                prefix="discovery_cache_",
                dir=str(self._cache_dir),
            )
            try:
                os.write(fd, payload.encode("utf-8"))
            finally:
                os.close(fd)

            os.replace(tmp_path, str(self._cache_file))
        except OSError as exc:
            _log.warning("Failed to persist cache to %s: %s", self._cache_file, exc)

    # ── Key management ────────────────────────────────────────────────────

    def make_key(self, provider: str, name: str, endpoint: str = "") -> str:
        """Generate a deterministic cache key."""
        raw = f"{provider}|{name}|{endpoint}"
        return sha256(raw.encode()).hexdigest()[:16]

    # ── Entry lifecycle ───────────────────────────────────────────────────

    def create_entry(
        self, provider: str, engine_name: str, runtime_type: RuntimeType, data: dict[str, Any]
    ) -> RuntimeCacheEntry:
        """Create and store a new cache entry."""
        key = self.make_key(provider, engine_name, data.get("endpoint", ""))
        entry_data = {"provider": provider, **data}
        entry = RuntimeCacheEntry(
            key=key,
            runtime_type=runtime_type,
            name=engine_name,
            data=entry_data,
            expires_at=datetime.now(UTC) + timedelta(seconds=self._ttl_seconds),
        )
        self.set(entry)
        return entry

    def get(self, key: str) -> RuntimeCacheEntry | None:
        """Get a non-expired entry by key."""
        entry = self._entries.get(key)
        if entry and entry.is_expired():
            self._entries.pop(key, None)
            self._save()
            return None
        if entry:
            entry.with_hit()
        return entry

    def set(self, entry: RuntimeCacheEntry) -> None:
        """Store a cache entry and persist to disk."""
        # Evict if over capacity
        if len(self._entries) >= self._max_entries and entry.key not in self._entries:
            self._evict_one()
        self._entries[entry.key] = entry
        self._save()

    # ── Invalidation ─────────────────────────────────────────────────────

    def invalidate(self, key: str) -> None:
        """Remove a single cache entry."""
        self._entries.pop(key, None)
        self._save()

    def invalidate_by_provider(self, provider: str) -> None:
        """Remove all entries for a provider."""
        to_remove = [k for k, v in self._entries.items() if v.data.get("provider") == provider]
        for k in to_remove:
            self._entries.pop(k, None)
        if to_remove:
            self._save()

    def invalidate_by_engine(self, engine_name: str) -> None:
        """Remove all entries for an engine."""
        to_remove = [k for k, v in self._entries.items() if v.name == engine_name]
        for k in to_remove:
            self._entries.pop(k, None)
        if to_remove:
            self._save()

    def invalidate_all(self) -> None:
        """Remove all entries and optionally delete the cache file."""
        self._entries.clear()
        if self._cache_file:
            try:
                self._cache_file.unlink(missing_ok=True)
            except OSError:
                pass

    # ── Maintenance ──────────────────────────────────────────────────────

    def clean_expired(self) -> int:
        """Remove all expired entries and persist if any were removed."""
        before = len(self._entries)
        self._entries = {k: v for k, v in self._entries.items() if not v.is_expired()}
        removed = before - len(self._entries)
        if removed:
            self._save()
        return removed

    def list_entries(self) -> list[RuntimeCacheEntry]:
        """Return all non-expired entries."""
        self.clean_expired()
        return list(self._entries.values())

    def count(self) -> int:
        """Return the number of active entries."""
        self.clean_expired()
        return len(self._entries)

    def get_stats(self) -> dict[str, Any]:
        """Return cache statistics."""
        self.clean_expired()
        total_hits = sum(e.hit_count for e in self._entries.values())
        return {
            "total_entries": len(self._entries),
            "total_hits": total_hits,
            "max_entries": self._max_entries,
            "ttl_seconds": self._ttl_seconds,
            "cache_file": str(self._cache_file),
        }

    def _evict_one(self) -> None:
        """Evict the oldest entry when over capacity."""
        if not self._entries:
            return
        oldest = min(self._entries.keys(), key=lambda k: self._entries[k].created_at)
        self._entries.pop(oldest, None)
