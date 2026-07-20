"""Native Window Manager — manages native desktop windows."""

from __future__ import annotations

from collections.abc import Sequence

from agentic_os.domain.desktop import WindowConfig, WindowInfo, WindowState
from agentic_os.infrastructure.logging import get_logger

log = get_logger("desktop.window")


class NativeWindowManager:
    """In-memory window manager. Integrates with Tauri for native operations."""

    def __init__(self) -> None:
        self._windows: dict[str, WindowInfo] = {}

    async def create_window(self, config: WindowConfig) -> WindowInfo:
        info = WindowInfo(
            label=config.label,
            title=config.title,
            url=config.url,
            width=config.width,
            height=config.height,
            x=config.x,
            y=config.y,
            state=config.state,
        )
        self._windows[info.id] = info
        log.info("Window created", window_id=info.id, label=config.label)
        return info

    async def close_window(self, window_id: str) -> bool:
        if window_id in self._windows:
            self._windows[window_id].state = WindowState.CLOSED
            del self._windows[window_id]
            return True
        return False

    async def get_window(self, window_id: str) -> WindowInfo | None:
        return self._windows.get(window_id)

    async def list_windows(self) -> Sequence[WindowInfo]:
        return list(self._windows.values())

    async def focus_window(self, window_id: str) -> bool:
        win = self._windows.get(window_id)
        if win is None:
            return False
        win.focused = True
        return True

    async def minimize_window(self, window_id: str) -> bool:
        win = self._windows.get(window_id)
        if win is None:
            return False
        win.state = WindowState.MINIMIZED
        return True

    async def maximize_window(self, window_id: str) -> bool:
        win = self._windows.get(window_id)
        if win is None:
            return False
        win.state = WindowState.MAXIMIZED
        return True

    async def restore_window(self, window_id: str) -> bool:
        win = self._windows.get(window_id)
        if win is None:
            return False
        win.state = WindowState.NORMAL
        return True

    async def set_window_title(self, window_id: str, title: str) -> bool:
        win = self._windows.get(window_id)
        if win is None:
            return False
        win.title = title
        return True

    async def set_window_size(self, window_id: str, width: int, height: int) -> bool:
        win = self._windows.get(window_id)
        if win is None:
            return False
        win.width = width
        win.height = height
        return True

    async def set_window_position(self, window_id: str, x: int, y: int) -> bool:
        win = self._windows.get(window_id)
        if win is None:
            return False
        win.x = x
        win.y = y
        return True

    async def enter_fullscreen(self, window_id: str) -> bool:
        win = self._windows.get(window_id)
        if win is None:
            return False
        win.state = WindowState.FULLSCREEN
        return True

    async def exit_fullscreen(self, window_id: str) -> bool:
        win = self._windows.get(window_id)
        if win is None:
            return False
        win.state = WindowState.NORMAL
        return True

    async def is_window_focused(self, window_id: str) -> bool:
        win = self._windows.get(window_id)
        return win.focused if win else False

    async def show_window(self, window_id: str) -> bool:
        win = self._windows.get(window_id)
        if win is None:
            return False
        if win.state == WindowState.HIDDEN:
            win.state = WindowState.NORMAL
        return True

    async def hide_window(self, window_id: str) -> bool:
        win = self._windows.get(window_id)
        if win is None:
            return False
        win.state = WindowState.HIDDEN
        return True

    async def get_window_count(self) -> int:
        return len(self._windows)
