"""Offline Runtime Manager — manages offline mode and event queuing."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from agentic_os.domain.desktop import OfflineConfig, OfflineEvent, OfflineState
from agentic_os.infrastructure.logging import get_logger

log = get_logger("desktop.offline")


class OfflineRuntimeManager:
    """Manages offline mode — event queuing, caching, and synchronization."""

    def __init__(self) -> None:
        self._state = OfflineState.ONLINE
        self._config = OfflineConfig()
        self._queue: list[OfflineEvent] = []

    async def enable_offline_mode(self) -> None:
        self._state = OfflineState.OFFLINE
        log.info("Offline mode enabled")

    async def disable_offline_mode(self) -> None:
        if self._queue:
            self._state = OfflineState.SYNCHRONIZING
            synced = await self.sync_queued_events()
            log.info("Offline events synced before going online", count=synced)
        self._state = OfflineState.ONLINE
        log.info("Offline mode disabled")

    async def get_offline_state(self) -> OfflineState:
        return self._state

    async def get_offline_config(self) -> OfflineConfig:
        return self._config

    async def update_offline_config(self, config: OfflineConfig) -> OfflineConfig:
        self._config = config
        return self._config

    async def get_queued_events(self) -> Sequence[dict[str, Any]]:
        return [e.to_dict() for e in self._queue]

    async def sync_queued_events(self) -> int:
        count = len(self._queue)
        for event in self._queue:
            event.synced = True
            event.synced_at = datetime.now(UTC)
        self._queue.clear()
        log.info("Queued events synced", count=count)
        return count

    async def queue_event(self, event_type: str, payload: dict[str, Any]) -> None:
        event = OfflineEvent(event_type=event_type, payload=payload)
        self._queue.append(event)

    async def get_queue_size(self) -> int:
        return len(self._queue)
