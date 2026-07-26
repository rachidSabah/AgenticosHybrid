"""File-based runtime persistence using JSON stored on disk.

Each runtime is saved as ``{runtime_id}.json`` in the configured data
directory (default ``~/.agentic_os/runtimes/``). All file I/O is
offloaded via :func:`asyncio.to_thread` to avoid blocking the event loop.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

from agentic_os.core.runtime.runtime import Runtime
from agentic_os.infrastructure.logging import get_logger

__all__ = [
    "RuntimePersistence",
]

log = get_logger("runtime.persistence")

DEFAULT_DATA_DIR = os.path.expanduser("~/.agentic_os/runtimes")


class RuntimePersistence:
    """Persists runtime state to JSON files on disk.

    All public methods are async safe for the event loop.
    """

    def __init__(self, data_dir: str | None = None) -> None:
        self._data_dir = Path(data_dir or DEFAULT_DATA_DIR)
        self._data_dir.mkdir(parents=True, exist_ok=True)

    @property
    def data_dir(self) -> str:
        """The directory where runtime JSON files are stored."""
        return str(self._data_dir)

    # ── CRUD ────────────────────────────────────────────────────────────────

    async def save(self, runtime: Runtime) -> str:
        """Persist a runtime to disk.

        Args:
            runtime: The :class:`Runtime` instance to save.

        Returns:
            The absolute path to the saved file.
        """
        data = runtime.to_dict()
        filepath = self._data_dir / f"{runtime.id}.json"
        await asyncio.to_thread(self._write_json, str(filepath), data)
        log.debug("persistence.saved", runtime_id=runtime.id, path=str(filepath))
        return str(filepath)

    async def load(self, runtime_id: str) -> Runtime | None:
        """Load a runtime from disk by its ID.

        Args:
            runtime_id: The unique runtime identifier.

        Returns:
            The :class:`Runtime` instance, or ``None`` if not found or corrupt.
        """
        filepath = self._data_dir / f"{runtime_id}.json"
        if not filepath.exists():
            return None

        data = await asyncio.to_thread(self._read_json, str(filepath))
        if data is None:
            return None

        try:
            return Runtime.from_dict(data)
        except Exception:
            log.exception("persistence.load_failed", runtime_id=runtime_id)
            return None

    async def load_all(self) -> list[Runtime]:
        """Load every persisted runtime from the data directory.

        Corrupt or unparseable files are skipped with a warning.
        """
        pattern: str = "*.json"
        files: list[Path] = await asyncio.to_thread(lambda: sorted(self._data_dir.glob(pattern)))

        runtimes: list[Runtime] = []
        for fpath in files:
            rid = fpath.stem
            runtime = await self.load(rid)
            if runtime is not None:
                runtimes.append(runtime)

        return runtimes

    async def delete(self, runtime_id: str) -> bool:
        """Delete a persisted runtime file.

        Args:
            runtime_id: The unique runtime identifier.

        Returns:
            ``True`` if the file was deleted, ``False`` if it did not exist.
        """
        filepath = self._data_dir / f"{runtime_id}.json"
        if not filepath.exists():
            return False

        await asyncio.to_thread(os.remove, str(filepath))
        log.debug("persistence.deleted", runtime_id=runtime_id)
        return True

    async def list_saved(self) -> list[str]:
        """Return all saved runtime IDs (sorted).

        Returns:
            Sorted list of runtime ID strings (without ``.json`` extension).
        """
        files: list[Path] = await asyncio.to_thread(lambda: list(self._data_dir.glob("*.json")))
        return sorted(f.stem for f in files)

    # ── Sync helpers (dispatched via ``asyncio.to_thread``) ─────────────────

    @staticmethod
    def _write_json(path: str, data: dict[str, Any]) -> None:
        """Synchronously write JSON data to *path*."""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)

    @staticmethod
    def _read_json(path: str) -> dict[str, Any] | None:
        """Synchronously read JSON data from *path*.

        Returns ``None`` on decode errors or I/O failures.
        """
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None
