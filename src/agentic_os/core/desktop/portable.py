"""Portable Runtime Manager — manages portable/embedded runtimes."""

from __future__ import annotations

from pathlib import Path

from agentic_os.infrastructure.logging import get_logger

log = get_logger("desktop.portable")


class PortableRuntimeManager:
    """Manages portable (self-contained) runtimes bundled with the application."""

    def __init__(self, base_dir: str | None = None) -> None:
        self._base_dir = base_dir or str(Path.home() / ".agentic_os" / "portable")
        self._available: dict[str, dict[str, object]] = {
            "python": {"version": "3.14.0", "size_mb": 45},
        }

    async def get_available_runtimes(self) -> dict[str, dict[str, object]]:
        return self._available

    async def get_portable_path(self, runtime: str) -> str | None:
        p = Path(self._base_dir) / runtime
        return str(p) if p.exists() else None

    async def is_portable_available(self, runtime: str) -> bool:
        p = Path(self._base_dir) / runtime
        return p.exists()
