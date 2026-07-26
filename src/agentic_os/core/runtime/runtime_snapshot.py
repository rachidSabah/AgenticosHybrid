"""Runtime snapshot manager — immutable point-in-time snapshots with TTL."""

from __future__ import annotations

import time
import uuid
from typing import Any

from agentic_os.core.runtime.runtime import Runtime
from agentic_os.infrastructure.logging import get_logger

__all__ = [
    "RuntimeSnapshotManager",
]

log = get_logger("runtime.snapshot")

DEFAULT_TTL_SECONDS = 300  # 5 minutes


class RuntimeSnapshotManager:
    """Manages immutable point-in-time snapshots of runtime state.

    Snapshots are plain dicts produced by :meth:`Runtime.to_snapshot`.
    Each snapshot has a unique ID and inherits its runtime's ID for
    ``get_latest`` lookups. Expired snapshots are removed lazily on
    access or eagerly via :meth:`cleanup`.
    """

    def __init__(self, ttl: int = DEFAULT_TTL_SECONDS) -> None:
        self._ttl = ttl
        # snapshot_id -> (expires_at_monotonic, snapshot_dict)
        self._snapshots: dict[str, tuple[float, dict[str, Any]]] = {}
        # runtime_id -> list[snapshot_id]  (newest first)
        self._runtime_index: dict[str, list[str]] = {}

    # ── Core operations ─────────────────────────────────────────────────────

    def take(self, runtime: Runtime) -> str:
        """Capture a point-in-time snapshot of *runtime*.

        Args:
            runtime: The :class:`Runtime` instance to snapshot.

        Returns:
            A unique snapshot ID string.
        """
        snapshot_id = uuid.uuid4().hex[:16]
        snapshot = runtime.to_snapshot()
        expires_at = time.monotonic() + self._ttl

        self._snapshots[snapshot_id] = (expires_at, snapshot)

        # Maintain runtime index (newest first)
        if runtime.id not in self._runtime_index:
            self._runtime_index[runtime.id] = []
        self._runtime_index[runtime.id].insert(0, snapshot_id)

        log.debug("snapshot.taken", runtime_id=runtime.id, snapshot_id=snapshot_id)
        return snapshot_id

    def get(self, snapshot_id: str) -> dict[str, Any] | None:
        """Retrieve a snapshot by its ID.

        Returns ``None`` if the snapshot does not exist or has expired
        (expired snapshots are removed as a side effect).
        """
        entry = self._snapshots.get(snapshot_id)
        if entry is None:
            return None

        expires_at, snapshot = entry
        if time.monotonic() > expires_at:
            self._remove(snapshot_id)
            return None

        return dict(snapshot)  # return a shallow copy for immutability

    def get_latest(self, runtime_id: str) -> dict[str, Any] | None:
        """Get the most recent (non-expired) snapshot for *runtime_id*.

        Returns ``None`` if no snapshots exist or all have expired.
        """
        snapshot_ids = self._runtime_index.get(runtime_id)
        if not snapshot_ids:
            return None

        for sid in snapshot_ids:
            snapshot = self.get(sid)
            if snapshot is not None:
                return snapshot
        return None

    # ── Comparison ──────────────────────────────────────────────────────────

    def compare(
        self,
        snapshot_a: dict[str, Any],
        snapshot_b: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        """Compare two snapshots and return their differences.

        Only top-level keys are compared. Returns::

            {
                "changed": {"field": {"old": …, "new": …}, …},
                "added":   {"field": …, …},
                "removed": {"field": …, …},
            }
        """
        result: dict[str, dict[str, Any]] = {
            "changed": {},
            "added": {},
            "removed": {},
        }
        keys_a = set(snapshot_a.keys())
        keys_b = set(snapshot_b.keys())

        for key in keys_a & keys_b:
            val_a = snapshot_a[key]
            val_b = snapshot_b[key]
            if val_a != val_b:
                result["changed"][key] = {"old": val_a, "new": val_b}

        for key in keys_b - keys_a:
            result["added"][key] = snapshot_b[key]

        for key in keys_a - keys_b:
            result["removed"][key] = snapshot_a[key]

        return result

    # ── Cleanup ─────────────────────────────────────────────────────────────

    def cleanup(self) -> int:
        """Remove all expired snapshots.

        Returns:
            Number of snapshots removed.
        """
        now = time.monotonic()
        expired_ids = [sid for sid, (expires_at, _) in self._snapshots.items() if now > expires_at]
        for sid in expired_ids:
            self._remove(sid)

        if expired_ids:
            log.debug("snapshot.cleanup", removed=len(expired_ids))
        return len(expired_ids)

    def _remove(self, snapshot_id: str) -> None:
        """Remove a snapshot from all indices."""
        self._snapshots.pop(snapshot_id, None)

        for runtime_id, snapshot_ids in list(self._runtime_index.items()):
            if snapshot_id in snapshot_ids:
                snapshot_ids.remove(snapshot_id)
            if not snapshot_ids:
                del self._runtime_index[runtime_id]
