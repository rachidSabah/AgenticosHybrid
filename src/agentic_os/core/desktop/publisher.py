"""Desktop Event Publisher — publishes desktop lifecycle events to the bus."""

from __future__ import annotations

from typing import Any

from agentic_os.domain.desktop import DesktopEventType
from agentic_os.infrastructure.logging import get_logger

log = get_logger("desktop.publisher")


class DesktopEventPublisher:
    """Publishes desktop lifecycle and state events to the event bus."""

    def __init__(self, bus: Any) -> None:
        self._bus = bus

    async def _publish(
        self, event_type: DesktopEventType, payload: dict[str, Any] | None = None
    ) -> None:
        try:
            await self._bus.publish(event_type.value, payload or {})
            log.debug("Desktop event published", event_type=event_type.value)
        except Exception as exc:
            log.warning(
                "Failed to publish desktop event", event_type=event_type.value, error=str(exc)
            )

    async def publish_started(self) -> None:
        await self._publish(DesktopEventType.STARTED)

    async def publish_stopped(self) -> None:
        await self._publish(DesktopEventType.STOPPED)

    async def publish_ready(self) -> None:
        await self._publish(DesktopEventType.READY)

    async def publish_workspace_created(self, workspace_id: str, name: str) -> None:
        await self._publish(
            DesktopEventType.WORKSPACE_CREATED, {"workspace_id": workspace_id, "name": name}
        )

    async def publish_workspace_loaded(self, workspace_id: str) -> None:
        await self._publish(DesktopEventType.WORKSPACE_LOADED, {"workspace_id": workspace_id})

    async def publish_layout_changed(self, workspace_id: str, layout_id: str) -> None:
        await self._publish(
            DesktopEventType.LAYOUT_CHANGED, {"workspace_id": workspace_id, "layout_id": layout_id}
        )

    async def publish_window_opened(self, window_id: str, label: str) -> None:
        await self._publish(
            DesktopEventType.WINDOW_OPENED, {"window_id": window_id, "label": label}
        )

    async def publish_window_closed(self, window_id: str) -> None:
        await self._publish(DesktopEventType.WINDOW_CLOSED, {"window_id": window_id})

    async def publish_performance_updated(self, metrics: dict[str, Any]) -> None:
        await self._publish(DesktopEventType.PERFORMANCE_UPDATED, metrics)

    async def publish_diagnostics_updated(self, diagnostics: dict[str, Any]) -> None:
        await self._publish(DesktopEventType.DIAGNOSTICS_UPDATED, diagnostics)

    async def publish_notification_created(
        self, notification_id: str, title: str, level: str
    ) -> None:
        await self._publish(
            DesktopEventType.NOTIFICATION_CREATED,
            {"notification_id": notification_id, "title": title, "level": level},
        )

    async def publish_notification_clicked(self, notification_id: str) -> None:
        await self._publish(
            DesktopEventType.NOTIFICATION_CLICKED, {"notification_id": notification_id}
        )

    async def publish_workspace_switched(self, workspace_id: str) -> None:
        await self._publish(DesktopEventType.WORKSPACE_SWITCHED, {"workspace_id": workspace_id})

    async def publish_theme_changed(self, theme: str) -> None:
        await self._publish(DesktopEventType.THEME_CHANGED, {"theme": theme})

    async def publish_menu_action(self, menu_id: str, item_id: str, action: str) -> None:
        await self._publish(
            DesktopEventType.MENU_ACTION, {"menu_id": menu_id, "item_id": item_id, "action": action}
        )

    async def publish_config_changed(self, changes: dict[str, Any]) -> None:
        await self._publish(DesktopEventType.CONFIG_CHANGED, changes)
