"""Log Manager — runtime log collection with ring-buffer storage.

Provides async, thread-safe log management with filtering, search, and
rotation callback support.
"""

from __future__ import annotations

import asyncio
import re
from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from agentic_os.core.runtime.runtime import RuntimeLog
from agentic_os.infrastructure.logging import get_logger

log = get_logger("runtime.logs")

__all__ = [
    "LogManager",
]

_MAX_ENTRIES_PER_RUNTIME = 5000


def _utcnow() -> datetime:
    return datetime.now(UTC)


RotationCallback = Callable[[str, list[RuntimeLog]], None]
"""Signature: (runtime_id, evicted_entries) -> None."""


class LogManager:
    """Ring-buffer log collection for runtime instances.

    Stores up to ``_MAX_ENTRIES_PER_RUNTIME`` (5000) log entries per runtime.
    When the limit is exceeded, the oldest entries are evicted and the
    rotation callback (if set) is invoked with the evicted batch.

    All public methods are thread-safe via asyncio.Lock.
    """

    def __init__(self) -> None:
        self._lock: asyncio.Lock = asyncio.Lock()
        # runtime_id -> deque[RuntimeLog]
        self._buffers: dict[str, deque[RuntimeLog]] = {}
        self._rotation_callbacks: dict[str, RotationCallback] = {}

    # ── Configuration ─────────────────────────────────────────────────────────

    def set_rotation_callback(
        self,
        runtime_id: str,
        callback: RotationCallback | None,
    ) -> None:
        """Set or clear the rotation callback for a runtime.

        The callback is invoked with ``(runtime_id, evicted_entries)`` whenever
        entries are evicted from the ring buffer.
        """
        # No lock needed for simple assignment; lock used for dict mutation
        if callback is None:
            self._rotation_callbacks.pop(runtime_id, None)
        else:
            self._rotation_callbacks[runtime_id] = callback

    # ── Append ────────────────────────────────────────────────────────────────

    async def append(
        self,
        runtime_id: str,
        entry: RuntimeLog,
    ) -> None:
        """Append a log entry to the runtime's ring buffer.

        If the buffer exceeds the max size, the oldest entries are evicted
        and the rotation callback is invoked.
        """
        async with self._lock:
            buf = self._buffers.get(runtime_id)
            if buf is None:
                buf = deque(maxlen=_MAX_ENTRIES_PER_RUNTIME)
                self._buffers[runtime_id] = buf

            evicted: list[RuntimeLog] = []
            if len(buf) >= _MAX_ENTRIES_PER_RUNTIME:
                # Collect evicted entries
                while len(buf) >= _MAX_ENTRIES_PER_RUNTIME:
                    evicted.append(buf.popleft())

            buf.append(entry)

        # Fire rotation callback outside the lock
        if evicted:
            cb = self._rotation_callbacks.get(runtime_id)
            if cb:
                try:
                    cb(runtime_id, evicted)
                except Exception:
                    log.exception(
                        "rotation callback failed",
                        runtime_id=runtime_id,
                    )

    async def append_text(
        self,
        runtime_id: str,
        text: str,
        stream: str = "stdout",
        level: str = "info",
        **metadata: Any,
    ) -> None:
        """Convenience: create a RuntimeLog from raw values and append it."""
        entry = RuntimeLog(
            stream=stream,
            text=text,
            level=level,
            metadata=metadata,
        )
        await self.append(runtime_id, entry)

    # ── Read ──────────────────────────────────────────────────────────────────

    async def get_logs(
        self,
        runtime_id: str,
        limit: int = 100,
        offset: int = 0,
        stream: str | None = None,
        level: str | None = None,
        search: str | None = None,
    ) -> list[RuntimeLog]:
        """Retrieve log entries with optional filters.

        Args:
            runtime_id: The runtime whose logs to read.
            limit: Max entries to return (default 100).
            offset: How many matching entries to skip (for pagination).
            stream: If set, filter by stream ("stdout", "stderr", "system").
            level: If set, filter by level ("info", "warn", "error", "debug").
            search: If set, filter entries whose text contains this substring
                (case-insensitive).

        Returns:
            A list of RuntimeLog entries, newest first (reverse chronological).
        """
        async with self._lock:
            buf = self._buffers.get(runtime_id)
            if buf is None:
                return []

            # Work on reversed copy (newest first) for filtering
            entries = list(reversed(buf))

        # Filter outside lock
        if stream:
            entries = [e for e in entries if e.stream == stream]
        if level:
            entries = [e for e in entries if e.level == level]
        if search:
            lower = search.lower()
            entries = [e for e in entries if lower in e.text.lower()]

        # Apply offset and limit
        return entries[offset : offset + limit]

    async def clear(self, runtime_id: str) -> int:
        """Clear all log entries for a runtime.

        Returns the number of entries cleared.
        """
        async with self._lock:
            buf = self._buffers.pop(runtime_id, None)
        if buf is None:
            return 0
        count = len(buf)
        log.info("logs cleared", runtime_id=runtime_id, count=count)
        return count

    # ── Search ────────────────────────────────────────────────────────────────

    async def search(
        self,
        runtime_id: str,
        query: str,
    ) -> list[RuntimeLog]:
        """Search log entries by text pattern (case-insensitive substring match).

        Returns matching entries newest-first.
        """
        return await self.get_logs(
            runtime_id=runtime_id,
            limit=_MAX_ENTRIES_PER_RUNTIME,
            search=query,
        )

    async def search_regex(
        self,
        runtime_id: str,
        pattern: str,
    ) -> list[RuntimeLog]:
        """Search log entries using a regex pattern.

        Returns matching entries newest-first.
        """
        compiled = re.compile(pattern, re.IGNORECASE)
        async with self._lock:
            buf = self._buffers.get(runtime_id)
            if buf is None:
                return []
            entries = list(reversed(buf))

        return [e for e in entries if compiled.search(e.text)]

    # ── Stats ─────────────────────────────────────────────────────────────────

    async def count(self, runtime_id: str) -> int:
        """Return the number of log entries for a runtime."""
        async with self._lock:
            buf = self._buffers.get(runtime_id)
            return len(buf) if buf else 0

    async def list_runtimes(self) -> list[str]:
        """Return all runtime IDs that have log buffers."""
        async with self._lock:
            return list(self._buffers.keys())

    async def total_entries(self) -> int:
        """Return the total number of log entries across all runtimes."""
        async with self._lock:
            return sum(len(buf) for buf in self._buffers.values())

    # ── Export ────────────────────────────────────────────────────────────────

    async def export(
        self,
        runtime_id: str,
        fmt: str = "text",
    ) -> str:
        """Export logs as formatted text or JSON lines.

        Args:
            runtime_id: The runtime whose logs to export.
            fmt: ``"text"`` for human-readable or ``"json"`` for JSON lines.

        Returns:
            Formatted string of all log entries (newest first).
        """
        async with self._lock:
            buf = self._buffers.get(runtime_id)
            if buf is None:
                return ""
            entries = list(reversed(buf))

        if fmt == "json":
            import json

            lines = [
                json.dumps(
                    {
                        "timestamp": e.timestamp.isoformat(),
                        "stream": e.stream,
                        "level": e.level,
                        "text": e.text,
                        **e.metadata,
                    }
                )
                for e in entries
            ]
            return "\n".join(lines)

        # Text format
        lines: list[str] = []
        for e in entries:
            ts = e.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            lines.append(f"[{ts}] [{e.stream}/{e.level}] {e.text}")
        return "\n".join(lines)
