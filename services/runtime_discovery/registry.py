from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from core.logging import get_logger
from services.runtime_discovery.models import (
    Runtime,
    RuntimeStatus,
    RuntimeType,
)

_log = get_logger(__name__)

__all__ = ["RuntimeRegistry", "RuntimeRegistryError"]


class RuntimeRegistryError(Exception):
    """Raised on registry operation errors."""


class RuntimeRegistry:
    def __init__(self) -> None:
        self._runtimes: dict[str, Runtime] = {}
        self._name_index: dict[str, str] = {}
        self._lock = asyncio.Lock()

    async def register(self, runtime: Runtime) -> Runtime:
        async with self._lock:
            existing = self._name_index.get(runtime.name)
            if existing:
                old = self._runtimes.get(existing)
                if old:
                    runtime.runtime_id = old.runtime_id
                    runtime.discovered_at = old.discovered_at
                    runtime.last_seen_at = datetime.now(UTC)
                    if old.status in (RuntimeStatus.BOUND, RuntimeStatus.ACTIVE):
                        runtime.status = old.status
            self._runtimes[runtime.runtime_id] = runtime
            self._name_index[runtime.name] = runtime.runtime_id
            _log.info(
                "Runtime registered",
                name=runtime.name,
                type=runtime.runtime_type.value,
                id=runtime.runtime_id[:8],
            )
            return runtime

    async def unregister(self, runtime_id: str) -> bool:
        async with self._lock:
            runtime = self._runtimes.pop(runtime_id, None)
            if runtime:
                self._name_index.pop(runtime.name, None)
                _log.info("Runtime unregistered", name=runtime.name, id=runtime_id[:8])
                return True
            return False

    async def get(self, runtime_id: str) -> Runtime | None:
        async with self._lock:
            return self._runtimes.get(runtime_id)

    async def find_by_name(self, name: str) -> Runtime | None:
        async with self._lock:
            runtime_id = self._name_index.get(name)
            if runtime_id:
                return self._runtimes.get(runtime_id)
            return None

    async def find_by_type(self, runtime_type: RuntimeType) -> list[Runtime]:
        async with self._lock:
            return [r for r in self._runtimes.values() if r.runtime_type == runtime_type]

    async def list(self, status: str | None = None) -> list[Runtime]:
        async with self._lock:
            runtimes = list(self._runtimes.values())
            if status:
                runtimes = [r for r in runtimes if r.status.value == status]
            return sorted(runtimes, key=lambda r: r.last_seen_at, reverse=True)

    async def update(self, runtime: Runtime) -> Runtime:
        async with self._lock:
            existing = self._runtimes.get(runtime.runtime_id)
            if not existing:
                raise RuntimeRegistryError(f"Runtime {runtime.runtime_id} not found")
            runtime.discovered_at = existing.discovered_at
            runtime.last_seen_at = datetime.now(UTC)
            self._runtimes[runtime.runtime_id] = runtime
            self._name_index[runtime.name] = runtime.runtime_id
            return runtime

    async def update_status(self, runtime_id: str, status: RuntimeStatus) -> Runtime | None:
        async with self._lock:
            runtime = self._runtimes.get(runtime_id)
            if runtime:
                runtime.status = status
                runtime.last_seen_at = datetime.now(UTC)
            return runtime

    async def count(self, status: str | None = None) -> int:
        async with self._lock:
            if status:
                return sum(1 for r in self._runtimes.values() if r.status.value == status)
            return len(self._runtimes)

    async def search(self, query: str) -> list[Runtime]:
        async with self._lock:
            q = query.lower()
            return [
                r
                for r in self._runtimes.values()
                if q in r.name.lower()
                or q in r.runtime_type.value.lower()
                or (r.display_name and q in r.display_name.lower())
            ]

    async def get_registry_snapshot(self) -> dict[str, Any]:
        async with self._lock:
            total = len(self._runtimes)
            by_status: dict[str, int] = {}
            by_type: dict[str, int] = {}
            for r in self._runtimes.values():
                by_status[r.status.value] = by_status.get(r.status.value, 0) + 1
                by_type[r.runtime_type.value] = by_type.get(r.runtime_type.value, 0) + 1
            return {
                "total_runtimes": total,
                "by_status": by_status,
                "by_type": by_type,
                "names": list(self._name_index.keys()),
            }
