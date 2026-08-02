"""Desktop Logging — in-memory log buffer for the desktop runtime."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any


class DesktopLogging:
    """In-memory desktop-native log buffer."""

    def __init__(self, max_entries: int = 1000) -> None:
        self._logs: list[dict[str, Any]] = []
        self._max_entries = max_entries

    async def log_info(self, message: str, **kwargs: Any) -> None:
        self._add_entry("info", message, kwargs)

    async def log_warning(self, message: str, **kwargs: Any) -> None:
        self._add_entry("warning", message, kwargs)

    async def log_error(self, message: str, **kwargs: Any) -> None:
        self._add_entry("error", message, kwargs)

    async def log_debug(self, message: str, **kwargs: Any) -> None:
        self._add_entry("debug", message, kwargs)

    async def get_logs(
        self, level: str | None = None, limit: int = 100, offset: int = 0
    ) -> Sequence[dict[str, Any]]:
        results = self._logs
        if level:
            results = [r for r in results if r.get("level") == level]
        return results[offset : offset + limit]

    async def clear_logs(self) -> None:
        self._logs.clear()

    def _add_entry(self, level: str, message: str, kwargs: dict[str, Any]) -> None:
        entry = {
            "level": level,
            "message": message,
            "timestamp": datetime.now(UTC).isoformat(),
            **kwargs,
        }
        self._logs.append(entry)
        if len(self._logs) > self._max_entries:
            self._logs.pop(0)
