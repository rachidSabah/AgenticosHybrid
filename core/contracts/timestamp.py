from __future__ import annotations

from datetime import UTC, datetime, timezone


def utc_now() -> datetime:
    return datetime.now(UTC)
