"""Runtime Watcher — continuously monitors the system for changes to AI runtimes.

Uses a polling approach (cross-platform) with intelligent debouncing.
Detects new installations, removals, path changes, and version changes.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from agentic_os.infrastructure.logging import get_logger
from services.installer.provider_catalog import ProviderDef

log = get_logger("installer.watcher")

ChangeHandler = Callable[["RuntimeChangeEvent"], Coroutine[Any, Any, None]]


@dataclass
class RuntimeChangeEvent:
    """Event emitted when a runtime change is detected."""

    provider_id: str
    change_type: str  # "added", "removed", "path_changed", "version_changed"
    old_path: str | None = None
    new_path: str | None = None
    old_version: str | None = None
    new_version: str | None = None


@dataclass
class RuntimeSnapshot:
    """Snapshot of a runtime's state at a point in time."""

    provider_id: str
    executable_path: str | None
    version: str | None
    last_seen: float


class RuntimeWatcher:
    """Watches the system for changes to installed AI runtimes.

    Uses polling with configurable intervals. Discovers changes by
    comparing periodic snapshots against the previous state.
    """

    def __init__(
        self,
        providers: list[ProviderDef],
        poll_interval: float = 30.0,
        fast_poll_interval: float = 5.0,
        debounce_seconds: float = 2.0,
    ):
        self._providers = providers
        self._poll_interval = poll_interval
        self._fast_poll_interval = fast_poll_interval
        self._debounce_seconds = debounce_seconds

        self._snapshots: dict[str, RuntimeSnapshot] = {}
        self._handlers: list[ChangeHandler] = []
        self._running = False
        self._task: asyncio.Task | None = None
        self._last_change: float = 0.0
        self._fast_mode = False

    def on_change(self, handler: ChangeHandler) -> None:
        """Register a handler for runtime change events."""
        self._handlers.append(handler)

    async def start(self) -> None:
        """Start the watcher loop."""
        if self._running:
            return
        self._running = True

        # Take initial snapshot
        self._snapshots = await self._take_snapshot()
        log.info("Watcher started", providers=len(self._providers), poll=self._poll_interval)

        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        """Stop the watcher loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        log.info("Watcher stopped")

    async def force_scan(self) -> list[RuntimeChangeEvent]:
        """Trigger an immediate scan and return any changes."""
        new_snapshots = await self._take_snapshot()
        changes = self._detect_changes(self._snapshots, new_snapshots)
        self._snapshots = new_snapshots
        return changes

    async def _run_loop(self) -> None:
        """Main watcher loop."""
        while self._running:
            interval = self._fast_poll_interval if self._fast_mode else self._poll_interval
            await asyncio.sleep(interval)

            try:
                new_snapshots = await self._take_snapshot()
                changes = self._detect_changes(self._snapshots, new_snapshots)

                if changes:
                    self._snapshots = new_snapshots
                    now = time.time()

                    # Debounce: group rapid changes
                    if now - self._last_change > self._debounce_seconds:
                        await self._emit_changes(changes)
                        self._last_change = now

                    # Enter fast mode temporarily after changes
                    self._fast_mode = True
                    asyncio.create_task(self._reset_poll_after(30))
                else:
                    self._fast_mode = False

            except Exception as exc:
                log.warning("Watcher scan error", error=str(exc))

    async def _reset_poll_after(self, seconds: float) -> None:
        """Reset to normal polling interval after a delay."""
        await asyncio.sleep(seconds)
        self._fast_mode = False

    async def _take_snapshot(self) -> dict[str, RuntimeSnapshot]:
        """Take a snapshot of all provider states."""
        snapshots: dict[str, RuntimeSnapshot] = {}
        for provider in self._providers:
            exe = self._find_executable(provider)
            version = await self._get_version(provider, exe) if exe else None
            snapshots[provider.id] = RuntimeSnapshot(
                provider_id=provider.id,
                executable_path=exe,
                version=version,
                last_seen=time.time(),
            )
        return snapshots

    def _find_executable(self, provider: ProviderDef) -> str | None:
        """Find a provider's executable."""
        for name in provider.exe_names:
            exe = shutil.which(name)
            if exe:
                return exe
        for path in provider.install_paths:
            for name in provider.exe_names:
                full = os.path.join(path, name)
                if os.path.isfile(full):
                    return full
        for var in provider.env_vars:
            val = os.environ.get(var)
            if val and os.path.isfile(val):
                return val
            if val:
                for name in provider.exe_names:
                    full = os.path.join(val, name)
                    if os.path.isfile(full):
                        return full
        return None

    async def _get_version(self, provider: ProviderDef, exe: str) -> str | None:
        """Get the version of a provider's executable."""
        if not provider.version_flags or not exe:
            return None
        try:
            proc = await asyncio.create_subprocess_exec(
                exe, *provider.version_flags,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10.0)
                if proc.returncode == 0:
                    return stdout.decode("utf-8", errors="replace").strip().split("\n")[0].strip()
            except TimeoutError:
                proc.kill()
        except (FileNotFoundError, PermissionError, OSError, NotImplementedError):
            pass
        return None

    def _detect_changes(
        self,
        old: dict[str, RuntimeSnapshot],
        new: dict[str, RuntimeSnapshot],
    ) -> list[RuntimeChangeEvent]:
        """Compare two snapshots and detect changes."""
        changes: list[RuntimeChangeEvent] = []

        for pid in set(list(old.keys()) + list(new.keys())):
            old_snap = old.get(pid)
            new_snap = new.get(pid)

            # Provider appeared
            if old_snap is None and new_snap and new_snap.executable_path:
                changes.append(RuntimeChangeEvent(
                    provider_id=pid,
                    change_type="added",
                    new_path=new_snap.executable_path,
                    new_version=new_snap.version,
                ))
                continue

            # Provider disappeared
            if old_snap and old_snap.executable_path and (new_snap is None or not new_snap.executable_path):
                changes.append(RuntimeChangeEvent(
                    provider_id=pid,
                    change_type="removed",
                    old_path=old_snap.executable_path,
                    old_version=old_snap.version,
                ))
                continue

            # Path changed
            if old_snap and new_snap and old_snap.executable_path != new_snap.executable_path:
                changes.append(RuntimeChangeEvent(
                    provider_id=pid,
                    change_type="path_changed",
                    old_path=old_snap.executable_path,
                    new_path=new_snap.executable_path,
                ))
                continue

            # Version changed
            if (
                old_snap and new_snap
                and old_snap.executable_path and new_snap.executable_path
                and old_snap.version != new_snap.version
                and old_snap.version is not None
                and new_snap.version is not None
            ):
                changes.append(RuntimeChangeEvent(
                    provider_id=pid,
                    change_type="version_changed",
                    old_path=old_snap.executable_path,
                    new_path=new_snap.executable_path,
                    old_version=old_snap.version,
                    new_version=new_snap.version,
                ))

        return changes

    async def _emit_changes(self, changes: list[RuntimeChangeEvent]) -> None:
        """Emit change events to all registered handlers."""
        for change in changes:
            log.info("Runtime change detected",
                      provider=change.provider_id,
                      change=change.change_type)
            for handler in self._handlers:
                try:
                    await handler(change)
                except Exception as exc:
                    log.error("Change handler failed",
                              provider=change.provider_id,
                              error=str(exc))
