"""Runtime Coordinator — Central live coordination layer for Agentic OS runtimes.

Coordinates the Brain Registry, Local Discovery, OmniRoute, Scheduler, Budget Engine,
Rate Limiter, Learning Engine, Aggregation Engine, and Provider Execution Engine.
"""

from __future__ import annotations

import asyncio
from typing import Any

from agentic_os.core.runtime.runtime import RuntimeStatus
from agentic_os.core.runtime.runtime_manager import RuntimeManager
from agentic_os.infrastructure.logging import get_logger

log = get_logger("runtime.coordinator")

__all__ = ["RuntimeCoordinator"]


class RuntimeCoordinator:
    """Central live coordination layer over all AI agent runtimes."""

    def __init__(self, manager: RuntimeManager, bus: Any | None = None) -> None:
        self.manager = manager
        self.bus = bus
        self._lock = asyncio.Lock()
        self._started = False

    async def start(self) -> None:
        """Start the runtime coordinator."""
        async with self._lock:
            if self._started:
                return
            await self.manager.start()
            self._started = True
            log.info("RuntimeCoordinator started")

    async def stop(self) -> None:
        """Stop the runtime coordinator."""
        async with self._lock:
            if not self._started:
                return
            await self.manager.stop()
            self._started = False
            log.info("RuntimeCoordinator stopped")

    async def get_system_topology(self) -> dict[str, Any]:
        """Return the complete runtime topology graph."""
        runtimes = await self.manager.list_all()
        nodes = []
        for r in runtimes:
            nodes.append(
                {
                    "id": r.id,
                    "name": r.name,
                    "type": r.type.value,
                    "status": r.status.value,
                    "health": r.health.value,
                    "cpu": r.cpu,
                    "memory": r.memory,
                }
            )
        return {
            "nodes": nodes,
            "count": len(nodes),
            "active": sum(1 for r in runtimes if r.status == RuntimeStatus.READY),
        }
