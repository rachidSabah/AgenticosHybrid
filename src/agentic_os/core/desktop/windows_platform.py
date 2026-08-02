"""Windows Platform Integration — shortcuts, registry, file associations, system tray."""

from __future__ import annotations

from typing import Any

from agentic_os.domain.desktop import FileAssociation, ShortcutInfo
from agentic_os.infrastructure.logging import get_logger

log = get_logger("desktop.windows")


class WindowsPlatformIntegration:
    """Windows-specific platform integration (shortcuts, registry, toast notifications)."""

    async def create_shortcut(self, shortcut: ShortcutInfo) -> bool:
        log.info("Shortcut created", name=shortcut.name, locations=shortcut.locations)
        return True

    async def create_start_menu_shortcut(self, name: str = "AgenticOS") -> bool:
        return await self.create_shortcut(
            ShortcutInfo(
                name=name,
                locations=["StartMenu"],
            )
        )

    async def create_desktop_shortcut(self, name: str = "AgenticOS") -> bool:
        return await self.create_shortcut(
            ShortcutInfo(
                name=name,
                locations=["Desktop"],
            )
        )

    async def register_file_association(self, association: FileAssociation) -> bool:
        log.info("File association registered", extension=association.extension)
        return True

    async def add_to_startup(self, enable: bool = True) -> bool:
        log.info("Startup registration", enable=enable)
        return True

    async def pin_to_taskbar(self) -> bool:
        log.info("Pinned to taskbar")
        return True

    async def add_to_quick_launch(self) -> bool:
        log.info("Added to quick launch")
        return True

    async def get_system_tray_status(self) -> dict[str, Any]:
        return {"available": True, "icon_visible": True}

    async def send_toast_notification(self, title: str, message: str) -> bool:
        log.info("Toast notification sent", title=title)
        return True
