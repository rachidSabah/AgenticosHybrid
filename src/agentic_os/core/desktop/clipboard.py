"""Native Clipboard Service — clipboard read/write operations."""

from __future__ import annotations

from agentic_os.domain.desktop import ClipboardContent
from agentic_os.infrastructure.logging import get_logger

log = get_logger("desktop.clipboard")


class NativeClipboardService:
    """In-memory clipboard manager. Integrates with Tauri for native clipboard."""

    def __init__(self) -> None:
        self._content = ClipboardContent()

    async def read_text(self) -> str:
        return self._content.text or ""

    async def write_text(self, text: str) -> None:
        self._content = ClipboardContent(text=text)

    async def read_html(self) -> str | None:
        return self._content.html

    async def write_html(self, html: str) -> None:
        self._content.html = html

    async def read_files(self) -> list[str]:
        return self._content.file_paths

    async def write_files(self, paths: list[str]) -> None:
        self._content.file_paths = paths

    async def clear(self) -> None:
        self._content = ClipboardContent()

    async def get_content(self) -> ClipboardContent:
        return self._content

    async def set_content(self, content: ClipboardContent) -> None:
        self._content = content
