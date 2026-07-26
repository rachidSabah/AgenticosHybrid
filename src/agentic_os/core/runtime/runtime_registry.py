"""In-memory thread-safe CRUD registry for Runtime objects."""

from __future__ import annotations

import asyncio
import copy

from agentic_os.core.runtime.runtime import Runtime, RuntimeStatus, RuntimeType
from agentic_os.infrastructure.logging import get_logger

log = get_logger("runtime.registry")


class RuntimeRegistry:
    """In-memory CRUD registry for Runtime objects.

    Thread-safe via asyncio.Lock. Reads return deep copies so callers
    cannot mutate the canonical record.
    """

    def __init__(self) -> None:
        self._lock: asyncio.Lock = asyncio.Lock()
        self._runtimes: dict[str, Runtime] = {}
        self._names: dict[str, str] = {}  # name -> id

    # ── Write operations ────────────────────────────────────────────────

    async def register(self, runtime: Runtime) -> str:
        """Register a new runtime. Returns its id.

        Raises ValueError if another runtime with the same name exists.
        """
        async with self._lock:
            if runtime.name and runtime.name in self._names:
                existing_id = self._names[runtime.name]
                raise ValueError(
                    f"Runtime with name {runtime.name!r} already exists (id={existing_id})"
                )
            self._runtimes[runtime.id] = runtime
            if runtime.name:
                self._names[runtime.name] = runtime.id
            log.info("Runtime registered", runtime_id=runtime.id, name=runtime.name)
        return runtime.id

    async def update(self, runtime: Runtime) -> bool:
        """Replace the stored runtime with the provided instance.

        Returns True if an existing record was updated, False if not found.
        """
        async with self._lock:
            if runtime.id not in self._runtimes:
                return False
            # Snapshot the OLD name from the index (not from the object, which
            # may have already been mutated in-place by the caller).
            old_name: str | None = None
            for name, rid in self._names.items():
                if rid == runtime.id:
                    old_name = name
                    break
            self._runtimes[runtime.id] = runtime
            # Re-index name map if name changed
            if old_name != runtime.name:
                if old_name and old_name in self._names:
                    del self._names[old_name]
                if runtime.name:
                    self._names[runtime.name] = runtime.id
        return True

    async def remove(self, runtime_id: str) -> bool:
        """Remove a runtime by id. Returns True if removed."""
        async with self._lock:
            runtime = self._runtimes.pop(runtime_id, None)
            if runtime is None:
                return False
            if runtime.name and runtime.name in self._names:
                del self._names[runtime.name]
            log.info("Runtime removed", runtime_id=runtime_id)
        return True

    # ── Read operations (deep copies) ───────────────────────────────────

    async def get(self, runtime_id: str) -> Runtime | None:
        """Return a deep copy of the runtime, or None."""
        async with self._lock:
            runtime = self._runtimes.get(runtime_id)
            if runtime is None:
                return None
            return copy.deepcopy(runtime)

    async def get_by_name(self, name: str) -> Runtime | None:
        """Lookup a runtime by its display name."""
        async with self._lock:
            runtime_id = self._names.get(name)
            if runtime_id is None:
                return None
            runtime = self._runtimes.get(runtime_id)
            if runtime is None:
                return None
            return copy.deepcopy(runtime)

    async def get_by_type(self, rt: RuntimeType) -> list[Runtime]:
        """Return all runtimes of a given type (deep copies)."""
        async with self._lock:
            return [copy.deepcopy(r) for r in self._runtimes.values() if r.type == rt]

    async def get_all(self) -> list[Runtime]:
        """Return all registered runtimes (deep copies)."""
        async with self._lock:
            return [copy.deepcopy(r) for r in self._runtimes.values()]

    async def get_active(self) -> list[Runtime]:
        """Return runtimes whose status is not STOPPED, CRASHED, or FAILED."""
        async with self._lock:
            terminal = {RuntimeStatus.STOPPED, RuntimeStatus.CRASHED, RuntimeStatus.FAILED}
            return [copy.deepcopy(r) for r in self._runtimes.values() if r.status not in terminal]

    async def count(self) -> int:
        """Return the number of registered runtimes."""
        async with self._lock:
            return len(self._runtimes)

    # ── Bulk / internal helpers ─────────────────────────────────────────

    async def get_raw(self, runtime_id: str) -> Runtime | None:
        """Return the internal reference for mutation (controller use only).

        WARNING: Callers that mutate the result MUST call update() or
        otherwise hold the lock. Prefer get() for external reads.
        """
        async with self._lock:
            return self._runtimes.get(runtime_id)

    async def _get_all_raw(self) -> list[Runtime]:
        """Return all internal references (controller/internal use)."""
        async with self._lock:
            return list(self._runtimes.values())


__all__ = [
    "RuntimeRegistry",
]
