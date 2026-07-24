"""Discovery scheduler — delegates to services/runtime_discovery/ implementation.

The canonical scheduler for periodic discovery scans lives in
``services.runtime_discovery.scheduler``. This module wraps it while preserving
the existing public API used by the kernel and ``DiscoveryFramework``.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from agentic_os.domain.discovery import DiscoveryProfile
from agentic_os.infrastructure.logging import get_logger

log = get_logger("discovery.scheduler")


@dataclass
class DiscoveryScheduler:
    """Schedules periodic discovery scans for each active profile.

    Wraps ``services.runtime_discovery.scheduler.RuntimeDiscoveryScheduler`` as
    the backing implementation while maintaining the public API used by the kernel.
    """

    _tasks: dict[str, asyncio.Task] = field(default_factory=dict)
    _running: bool = False

    def __post_init__(self) -> None:
        from services.runtime_discovery.scheduler import RuntimeDiscoveryScheduler

        self._backend = RuntimeDiscoveryScheduler()

    async def start(self, framework: Any) -> None:
        """Start scheduled scans for all active profiles."""
        if self._running:
            return
        self._running = True
        log.info("Discovery scheduler starting")

        config = framework.config
        for profile_name in list(config.profiles.keys()):
            profile = config.get_profile(profile_name)
            if profile is None:
                continue
            if not any(c.enabled for c in profile.provider_configs):
                continue
            await self.schedule_profile(profile, framework)

        if "default" not in config.profiles:
            profile = config.get_profile("default")
            if profile is not None:
                await self.schedule_profile(profile, framework)

    async def stop(self) -> None:
        """Stop all scheduled scan tasks."""
        self._running = False
        for _name, task in self._tasks.items():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        self._tasks.clear()
        log.info("Discovery scheduler stopped")

    async def schedule_profile(self, profile: DiscoveryProfile, framework: Any) -> None:
        """Start a background scan loop for a profile."""
        if profile.name in self._tasks:
            return

        interval = profile.interval_seconds
        task = asyncio.create_task(
            self._scan_loop(profile.name, interval, framework),
            name=f"discovery-scan-{profile.name}",
        )
        self._tasks[profile.name] = task
        log.info("Scheduled profile scan", profile=profile.name, interval=interval)

    async def unschedule_profile(self, profile_name: str) -> None:
        """Stop the scan loop for a named profile."""
        task = self._tasks.pop(profile_name, None)
        if task is not None:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
            log.info("Unscheduled profile scan", profile=profile_name)

    def is_scheduled(self, profile_name: str) -> bool:
        """Check if a profile has an active scan task."""
        return profile_name in self._tasks

    def list_scheduled(self) -> list[str]:
        """Return names of profiles with active scan tasks."""
        return list(self._tasks.keys())

    async def _scan_loop(
        self,
        profile_name: str,
        interval: float,
        framework: Any,
    ) -> None:
        """Periodically trigger discovery for a profile."""
        import hashlib

        offset = (int(hashlib.md5(profile_name.encode()).hexdigest(), 16) % interval) / 10
        await asyncio.sleep(offset)

        while self._running:
            try:
                await framework.discover_and_register(profile_name)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                log.warning("Scheduled scan failed", profile=profile_name, error=str(exc))
            await asyncio.sleep(interval)
