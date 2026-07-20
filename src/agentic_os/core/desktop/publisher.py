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

    # ── Phase 4 M6 Part 2 events ──

    async def publish_installed(self, version: str) -> None:
        await self._publish(DesktopEventType.INSTALLED, {"version": version})

    async def publish_updated(self, from_version: str, to_version: str) -> None:
        await self._publish(
            DesktopEventType.UPDATED, {"from_version": from_version, "to_version": to_version}
        )

    async def publish_update_available(self, version: str, channel: str) -> None:
        await self._publish(
            DesktopEventType.UPDATE_AVAILABLE, {"version": version, "channel": channel}
        )

    async def publish_update_started(self, version: str) -> None:
        await self._publish(DesktopEventType.UPDATE_STARTED, {"version": version})

    async def publish_update_completed(self, version: str) -> None:
        await self._publish(DesktopEventType.UPDATE_COMPLETED, {"version": version})

    async def publish_update_failed(self, version: str, error: str) -> None:
        await self._publish(DesktopEventType.UPDATE_FAILED, {"version": version, "error": error})

    async def publish_rollback_started(self, version: str) -> None:
        await self._publish(DesktopEventType.ROLLBACK_STARTED, {"version": version})

    async def publish_rollback_completed(self, version: str) -> None:
        await self._publish(DesktopEventType.ROLLBACK_COMPLETED, {"version": version})

    async def publish_runtime_discovered(self, runtime_type: str, version: str) -> None:
        await self._publish(
            DesktopEventType.RUNTIME_DISCOVERED, {"runtime_type": runtime_type, "version": version}
        )

    async def publish_runtime_removed(self, runtime_type: str) -> None:
        await self._publish(DesktopEventType.RUNTIME_REMOVED, {"runtime_type": runtime_type})

    async def publish_offline_enabled(self) -> None:
        await self._publish(DesktopEventType.OFFLINE_ENABLED, {})

    async def publish_offline_disabled(self) -> None:
        await self._publish(DesktopEventType.OFFLINE_DISABLED, {})

    async def publish_backup_created(self, backup_path: str, scope: str) -> None:
        await self._publish(
            DesktopEventType.BACKUP_CREATED, {"backup_path": backup_path, "scope": scope}
        )

    async def publish_restore_completed(self, backup_path: str) -> None:
        await self._publish(DesktopEventType.RESTORE_COMPLETED, {"backup_path": backup_path})

    async def publish_first_run_completed(self) -> None:
        await self._publish(DesktopEventType.FIRST_RUN_COMPLETED, {})

    # ── Production Hardening events ──

    async def publish_hardening_started(self) -> None:
        await self._publish(DesktopEventType.HARDENING_STARTED, {})

    async def publish_hardening_completed(self, result: dict[str, Any]) -> None:
        await self._publish(DesktopEventType.HARDENING_COMPLETED, result)

    async def publish_hardening_failed(self, error: str) -> None:
        await self._publish(DesktopEventType.HARDENING_FAILED, {"error": error})

    async def publish_integrity_check_passed(self, check_id: str) -> None:
        await self._publish(DesktopEventType.INTEGRITY_CHECK_PASSED, {"check_id": check_id})

    async def publish_integrity_check_failed(self, check_id: str, errors: list[str]) -> None:
        await self._publish(
            DesktopEventType.INTEGRITY_CHECK_FAILED, {"check_id": check_id, "errors": errors}
        )

    async def publish_recovery_started(self, mode: str) -> None:
        await self._publish(DesktopEventType.RECOVERY_STARTED, {"mode": mode})

    async def publish_recovery_completed(self, success: bool) -> None:
        await self._publish(DesktopEventType.RECOVERY_COMPLETED, {"success": success})

    async def publish_recovery_failed(self, error: str) -> None:
        await self._publish(DesktopEventType.RECOVERY_FAILED, {"error": error})

    async def publish_memory_leak_detected(self, report: dict[str, Any]) -> None:
        await self._publish(DesktopEventType.MEMORY_LEAK_DETECTED, report)

    async def publish_thread_anomaly_detected(self, report: dict[str, Any]) -> None:
        await self._publish(DesktopEventType.THREAD_ANOMALY_DETECTED, report)

    async def publish_cleanup_started(self) -> None:
        await self._publish(DesktopEventType.CLEANUP_STARTED, {})

    async def publish_cleanup_completed(self, result: dict[str, Any]) -> None:
        await self._publish(DesktopEventType.CLEANUP_COMPLETED, result)

    async def publish_graceful_shutdown(self, plan: dict[str, Any]) -> None:
        await self._publish(DesktopEventType.GRACEFUL_SHUTDOWN, plan)

    async def publish_recovery_mode_entered(self) -> None:
        await self._publish(DesktopEventType.RECOVERY_MODE_ENTERED, {})

    async def publish_recovery_mode_exited(self) -> None:
        await self._publish(DesktopEventType.RECOVERY_MODE_EXITED, {})
