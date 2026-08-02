"""Native File Integration — file dialogs and file system operations."""

from __future__ import annotations

from pathlib import Path

from agentic_os.domain.desktop import DialogConfig, DialogResult
from agentic_os.infrastructure.logging import get_logger

log = get_logger("desktop.file")


class NativeFileIntegration:
    """File dialog and file system operations. Integrates with Tauri for native dialogs."""

    async def open_file_dialog(self, config: DialogConfig) -> DialogResult:
        log.info("Open file dialog requested", title=config.title)
        return DialogResult()

    async def save_file_dialog(self, config: DialogConfig) -> DialogResult:
        log.info("Save file dialog requested", title=config.title)
        return DialogResult()

    async def select_folder_dialog(self, config: DialogConfig) -> DialogResult:
        log.info("Select folder dialog requested", title=config.title)
        return DialogResult()

    async def read_file(self, path: str) -> bytes:
        return Path(path).read_bytes()

    async def write_file(self, path: str, data: bytes) -> bool:
        try:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_bytes(data)
            return True
        except OSError:
            return False

    async def file_exists(self, path: str) -> bool:
        return Path(path).exists()

    async def get_file_info(self, path: str) -> dict[str, object]:
        p = Path(path)
        if not p.exists():
            return {"exists": False}
        stat = p.stat()
        return {
            "exists": True,
            "size": stat.st_size,
            "is_file": p.is_file(),
            "is_dir": p.is_dir(),
            "modified": stat.st_mtime,
            "created": stat.st_ctime,
        }

    async def ensure_dir(self, path: str) -> bool:
        try:
            Path(path).mkdir(parents=True, exist_ok=True)
            return True
        except OSError:
            return False
