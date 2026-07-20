"""Native Menu Manager — manages native application menus."""

from __future__ import annotations

from collections.abc import Sequence

from agentic_os.domain.desktop import MenuConfig, MenuItem, MenuItemType, MenuType
from agentic_os.infrastructure.logging import get_logger

log = get_logger("desktop.menu")


class NativeMenuManager:
    """In-memory menu manager. Integrates with Tauri for native menus."""

    def __init__(self) -> None:
        self._menus: dict[str, MenuConfig] = {}

    async def create_menu(self, menu: MenuConfig) -> MenuConfig:
        self._menus[menu.id] = menu
        log.info("Menu created", menu_id=menu.id, menu_type=menu.menu_type.value)
        return menu

    async def get_menu(self, menu_id: str) -> MenuConfig | None:
        return self._menus.get(menu_id)

    async def list_menus(self) -> Sequence[MenuConfig]:
        return list(self._menus.values())

    async def delete_menu(self, menu_id: str) -> bool:
        if menu_id in self._menus:
            del self._menus[menu_id]
            return True
        return False

    async def add_menu_item(self, menu_id: str, item: MenuItem) -> MenuItem | None:
        menu = self._menus.get(menu_id)
        if menu is None:
            return None
        menu.items.append(item)
        return item

    async def remove_menu_item(self, menu_id: str, item_id: str) -> bool:
        menu = self._menus.get(menu_id)
        if menu is None:
            return False
        menu.items = [i for i in menu.items if i.id != item_id]
        return True

    async def trigger_menu_action(self, menu_id: str, item_id: str) -> dict[str, str] | None:
        menu = self._menus.get(menu_id)
        if menu is None:
            return None
        for item in menu.items:
            if item.id == item_id:
                return {"menu_id": menu_id, "item_id": item_id, "action": item.action or ""}
        return None

    async def get_default_menus(self) -> Sequence[MenuConfig]:
        return [
            MenuConfig(
                menu_type=MenuType.FILE,
                label="File",
                items=[
                    MenuItem(label="New Workspace", action="workspace.new", shortcut="CmdOrCtrl+N"),
                    MenuItem(label="Open...", action="file.open", shortcut="CmdOrCtrl+O"),
                    MenuItem(item_type=MenuItemType.SEPARATOR),
                    MenuItem(label="Save", action="file.save", shortcut="CmdOrCtrl+S"),
                    MenuItem(
                        label="Save As...", action="file.save_as", shortcut="CmdOrCtrl+Shift+S"
                    ),
                    MenuItem(item_type=MenuItemType.SEPARATOR),
                    MenuItem(label="Exit", action="app.exit", shortcut="Alt+F4"),
                ],
            ),
            MenuConfig(
                menu_type=MenuType.EDIT,
                label="Edit",
                items=[
                    MenuItem(label="Undo", action="edit.undo", shortcut="CmdOrCtrl+Z"),
                    MenuItem(label="Redo", action="edit.redo", shortcut="CmdOrCtrl+Shift+Z"),
                    MenuItem(item_type=MenuItemType.SEPARATOR),
                    MenuItem(label="Cut", action="edit.cut", shortcut="CmdOrCtrl+X"),
                    MenuItem(label="Copy", action="edit.copy", shortcut="CmdOrCtrl+C"),
                    MenuItem(label="Paste", action="edit.paste", shortcut="CmdOrCtrl+V"),
                    MenuItem(item_type=MenuItemType.SEPARATOR),
                    MenuItem(label="Select All", action="edit.select_all", shortcut="CmdOrCtrl+A"),
                ],
            ),
            MenuConfig(
                menu_type=MenuType.VIEW,
                label="View",
                items=[
                    MenuItem(
                        label="Command Palette",
                        action="view.command_palette",
                        shortcut="CmdOrCtrl+Shift+P",
                    ),
                    MenuItem(
                        label="Global Search",
                        action="view.global_search",
                        shortcut="CmdOrCtrl+Shift+F",
                    ),
                    MenuItem(item_type=MenuItemType.SEPARATOR),
                    MenuItem(
                        label="Toggle Sidebar", action="view.toggle_sidebar", shortcut="CmdOrCtrl+B"
                    ),
                    MenuItem(
                        label="Toggle Panel", action="view.toggle_panel", shortcut="CmdOrCtrl+J"
                    ),
                    MenuItem(item_type=MenuItemType.SEPARATOR),
                    MenuItem(label="Zoom In", action="view.zoom_in", shortcut="CmdOrCtrl+Plus"),
                    MenuItem(label="Zoom Out", action="view.zoom_out", shortcut="CmdOrCtrl+Minus"),
                    MenuItem(label="Toggle Full Screen", action="view.fullscreen", shortcut="F11"),
                ],
            ),
            MenuConfig(
                menu_type=MenuType.WINDOW,
                label="Window",
                items=[
                    MenuItem(label="Minimize", action="window.minimize", shortcut="CmdOrCtrl+M"),
                    MenuItem(label="Close Window", action="window.close", shortcut="CmdOrCtrl+W"),
                    MenuItem(item_type=MenuItemType.SEPARATOR),
                    MenuItem(
                        label="Next Workspace", action="workspace.next", shortcut="CmdOrCtrl+Tab"
                    ),
                    MenuItem(
                        label="Previous Workspace",
                        action="workspace.prev",
                        shortcut="CmdOrCtrl+Shift+Tab",
                    ),
                ],
            ),
            MenuConfig(
                menu_type=MenuType.HELP,
                label="Help",
                items=[
                    MenuItem(label="About AgenticOS", action="help.about"),
                    MenuItem(label="Documentation", action="help.docs"),
                    MenuItem(label="Report Issue", action="help.report_issue"),
                ],
            ),
        ]
