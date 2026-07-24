"""File system watcher — live monitoring for runtime discovery changes.

Watches configured directories for file system changes (create, modify, delete)
and emits discovery events through the existing EventBus infrastructure.
Uses polling-based monitoring for cross-platform compatibility without
requiring inotify or Watchman dependencies.

Integrates with ``RuntimeDiscoveryScheduler`` for periodic rescan triggers
and emits ``engine_lost`` / ``engine_found`` events when runtimes appear
or disappear from watched paths.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Callable

from core.logging import get_logger

_log = get_logger(__name__)

__all__ = [
    "RuntimeWatcher",
    "FileChange",
    "ChangeType",
]

from enum import StrEnum


class ChangeType(StrEnum):
    """Type of filesystem change detected."""

    CREATED = "created"
    MODIFIED = "modified"
    DELETED = "deleted"


class FileChange:
    """Record of a single filesystem change."""

    def __init__(
        self,
        path: str,
        change_type: ChangeType,
        *,
        old_path: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.path = path
        self.change_type = change_type
        self.old_path = old_path
        self.metadata = metadata or {}
        self.timestamp = time.time()

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "change_type": self.change_type.value,
            "old_path": self.old_path,
            "timestamp": self.timestamp,
            "metadata": dict(self.metadata),
        }


class RuntimeWatcher:
    """Polling-based file system watcher for runtime binary changes.

    Monitors directories for added/removed executables and reports changes
    to registered callbacks. Uses polling rather than OS-level file system
    events to remain portable across platforms.

    Usage::

        watcher = RuntimeWatcher(["/usr/local/bin", "~/.local/bin"])
        watcher.on_change(my_callback)
        await watcher.poll()  # single poll cycle
        await watcher.start(interval=30)  # continuous polling
    """

    def __init__(
        self,
        watch_dirs: list[str] | None = None,
        *,
        binary_names: list[str] | None = None,
        poll_interval: float = 30.0,
    ) -> None:
        self._watch_dirs = watch_dirs or []
        self._binary_names = binary_names or []
        self._poll_interval = poll_interval
        self._snapshots: dict[str, dict[str, float]] = {}
        self._callbacks: list[Callable[[list[FileChange]], None]] = []
        self._running = False
        self._task: Any = None

    @property
    def watch_dirs(self) -> list[str]:
        return list(self._watch_dirs)

    def add_watch_dir(self, directory: str) -> None:
        """Add a directory to watch for changes."""
        resolved = str(Path(directory).resolve())
        if resolved not in self._watch_dirs:
            self._watch_dirs.append(resolved)
            _log.debug("Added watch directory: %s", resolved)

    def remove_watch_dir(self, directory: str) -> None:
        """Remove a directory from the watch list."""
        resolved = str(Path(directory).resolve())
        self._watch_dirs = [d for d in self._watch_dirs if d != resolved]

    def on_change(self, callback: Callable[[list[FileChange]], None]) -> None:
        """Register a callback invoked when changes are detected."""
        self._callbacks.append(callback)

    def _notify(self, changes: list[FileChange]) -> None:
        """Notify all registered callbacks."""
        for cb in self._callbacks:
            try:
                cb(changes)
            except Exception as exc:
                _log.error("Watcher callback failed: %s", exc)

    # ── Snapshot management ──

    def _take_snapshot(self) -> dict[str, dict[str, float]]:
        """Take a snapshot of all watched directories.

        Returns a dict mapping directory -> {filename: mtime}.
        """
        snapshot: dict[str, dict[str, float]] = {}
        for directory in self._watch_dirs:
            dir_path = Path(directory)
            if not dir_path.is_dir():
                continue
            files: dict[str, float] = {}
            try:
                for entry in dir_path.iterdir():
                    if entry.is_file():
                        files[entry.name] = entry.stat().st_mtime
            except PermissionError:
                _log.debug("Permission denied reading %s", directory)
                continue
            snapshot[directory] = files
        return snapshot

    def _diff(
        self,
        current: dict[str, dict[str, float]],
        previous: dict[str, dict[str, float]],
    ) -> list[FileChange]:
        """Diff two snapshots and return the changes."""
        changes: list[FileChange] = []

        all_dirs = set(current) | set(previous)
        for directory in all_dirs:
            cur_files = current.get(directory, {})
            prev_files = previous.get(directory, {})

            cur_names = set(cur_files)
            prev_names = set(prev_files)

            # Created
            for name in cur_names - prev_names:
                path = os.path.join(directory, name)
                changes.append(FileChange(path=path, change_type=ChangeType.CREATED))

            # Deleted
            for name in prev_names - cur_names:
                path = os.path.join(directory, name)
                changes.append(FileChange(path=path, change_type=ChangeType.DELETED))

            # Modified (mtime changed)
            for name in cur_names & prev_names:
                if cur_files[name] != prev_files[name]:
                    path = os.path.join(directory, name)
                    changes.append(FileChange(path=path, change_type=ChangeType.MODIFIED))

        return changes

    # ── Polling ──

    async def poll(self) -> list[FileChange]:
        """Perform a single poll cycle and return detected changes."""
        from datetime import UTC, datetime

        current = self._take_snapshot()

        if not self._snapshots:
            self._snapshots = current
            _log.debug("Initial snapshot taken (%d directories)", len(current))
            return []

        changes = self._diff(current, self._snapshots)
        self._snapshots = current

        if changes:
            _log.info(
                "Watcher detected %d changes",
                len(changes),
                extra={"directories": len(self._watch_dirs)},
            )
            self._notify(changes)

        return changes

    async def start(self, interval: float | None = None) -> None:
        """Start continuous polling at the given interval (seconds)."""
        if self._running:
            return

        self._running = True
        period = interval if interval is not None else self._poll_interval
        _log.info("Watcher started (interval=%ss, dirs=%d)", period, len(self._watch_dirs))

        try:
            while self._running:
                await self.poll()
                await self._sleep(period)
        except Exception as exc:
            _log.error("Watcher error: %s", exc)
            self._running = False

    async def stop(self) -> None:
        """Stop continuous polling."""
        self._running = False
        _log.info("Watcher stopped")

    @staticmethod
    async def _sleep(seconds: float) -> None:
        """Async sleep helper."""
        import asyncio

        await asyncio.sleep(seconds)
