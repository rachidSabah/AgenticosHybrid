"""Native Drag & Drop Service — handles drag and drop payloads."""

from __future__ import annotations

from agentic_os.domain.desktop import DragDropPayload
from agentic_os.infrastructure.logging import get_logger

log = get_logger("desktop.dragdrop")


class NativeDragDropService:
    """Handles drag-and-drop payloads. Integrates with Tauri for native DnD."""

    async def handle_drop(self, payload: DragDropPayload) -> dict[str, object]:
        log.info(
            "Drag-drop received", files=len(payload.file_paths), has_text=payload.text is not None
        )
        return {
            "accepted": True,
            "file_count": len(payload.file_paths),
            "has_text": payload.text is not None,
            "url_count": len(payload.urls),
        }

    async def get_supported_formats(self) -> list[str]:
        return ["files", "text", "urls", "custom"]
