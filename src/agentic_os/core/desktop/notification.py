"""Native Notification Service — manages desktop notifications."""

from __future__ import annotations

from collections.abc import Sequence

from agentic_os.domain.desktop import DesktopNotification, NotificationAction
from agentic_os.infrastructure.logging import get_logger

log = get_logger("desktop.notification")


class NativeNotificationService:
    """In-memory notification manager. Sends native notifications when Tauri is available."""

    def __init__(self) -> None:
        self._notifications: dict[str, DesktopNotification] = {}

    async def send_notification(self, notification: DesktopNotification) -> DesktopNotification:
        self._notifications[notification.id] = notification
        log.info(
            "Notification sent",
            notification_id=notification.id,
            title=notification.title,
            level=notification.level.value,
        )
        return notification

    async def dismiss_notification(self, notification_id: str) -> bool:
        if notification_id in self._notifications:
            self._notifications[notification_id].action = NotificationAction.DISMISSED
            return True
        return False

    async def list_notifications(self) -> Sequence[DesktopNotification]:
        return list(self._notifications.values())

    async def clear_notifications(self) -> None:
        self._notifications.clear()

    async def get_notification(self, notification_id: str) -> DesktopNotification | None:
        return self._notifications.get(notification_id)

    async def mark_clicked(self, notification_id: str) -> bool:
        notif = self._notifications.get(notification_id)
        if notif is None:
            return False
        notif.action = NotificationAction.CLICKED
        return True

    async def get_unread_count(self) -> int:
        return sum(
            1 for n in self._notifications.values() if n.action == NotificationAction.CREATED
        )
