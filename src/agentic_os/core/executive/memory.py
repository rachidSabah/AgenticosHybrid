"""ExecutiveMemory — semantic indexes over the existing MemoryManager.

Does NOT replace MemoryManager. Only extends it with executive-specific
indexes:
  - Mission history
  - Goal history
  - Runtime history
  - Failure history
  - Reflection history
  - Capability history

The indexes are in-memory dicts keyed by entity ID. They point into
the existing MemoryManager by scope+key, so the canonical storage is
still the MemoryManager. This is a read-optimization layer only.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from agentic_os.core.executive.domain import Reflection
from agentic_os.infrastructure.logging import get_logger

if TYPE_CHECKING:
    from agentic_os.core.memory.manager import MemoryManagerImpl

log = get_logger("executive.memory")


class ExecutiveMemory:
    """Semantic indexes over the existing MemoryManager.

    Stores executive entities (goals, reflections, decisions) in
    in-memory indexes for fast retrieval. The canonical storage is
    still the MemoryManager — this layer only adds an index.
    """

    def __init__(self, memory: MemoryManagerImpl | None = None) -> None:
        self._memory: MemoryManagerImpl | None = memory
        self._lock = asyncio.Lock()
        # Indexes: entity_id → dict
        self._goals: dict[str, dict[str, Any]] = {}
        self._reflections: dict[str, dict[str, Any]] = {}
        self._decisions: dict[str, dict[str, Any]] = {}
        self._failures: dict[str, dict[str, Any]] = {}
        self._goal_results: dict[str, dict[str, Any]] = {}  # goal_id → GoalResult dict

    def set_memory(self, memory: MemoryManagerImpl) -> None:
        """Inject the existing MemoryManager."""
        self._memory = memory

    # ── Goal history ──────────────────────────────────────────────────

    async def store_goal(self, goal_dict: dict[str, Any]) -> None:
        async with self._lock:
            self._goals[goal_dict["id"]] = goal_dict

    async def get_goal(self, goal_id: str) -> dict[str, Any] | None:
        async with self._lock:
            return self._goals.get(goal_id)

    async def list_goals(self, limit: int = 50) -> list[dict[str, Any]]:
        async with self._lock:
            return list(self._goals.values())[-limit:]

    # ── Reflection history ────────────────────────────────────────────

    async def store_reflection(self, r: Reflection) -> None:
        async with self._lock:
            self._reflections[r.id] = r.to_dict()

    async def get_reflection(self, reflection_id: str) -> dict[str, Any] | None:
        async with self._lock:
            return self._reflections.get(reflection_id)

    async def list_reflections(self, limit: int = 50) -> list[dict[str, Any]]:
        async with self._lock:
            return list(self._reflections.values())[-limit:]

    # ── Decision history ─────────────────────────────────────────────

    async def store_decision(self, decision_dict: dict[str, Any]) -> None:
        async with self._lock:
            self._decisions[decision_dict["id"]] = decision_dict

    async def list_decisions(self, limit: int = 50) -> list[dict[str, Any]]:
        async with self._lock:
            return list(self._decisions.values())[-limit:]

    # ── Failure history ──────────────────────────────────────────────

    async def store_failure(self, failure_dict: dict[str, Any]) -> None:
        async with self._lock:
            self._failures[failure_dict.get("id", "")] = failure_dict

    async def list_failures(self, limit: int = 50) -> list[dict[str, Any]]:
        async with self._lock:
            return list(self._failures.values())[-limit:]

    # ── Runtime history (derived from BrainRegistry events) ──────────

    async def store_runtime_event(self, runtime_dict: dict[str, Any]) -> None:
        """Record a runtime lifecycle event (discovery/removal/health)."""
        # Store in the goals index under a special key for runtime history
        async with self._lock:
            self._goals[f"runtime:{runtime_dict.get('id', '')}"] = runtime_dict

    async def list_runtime_history(self, limit: int = 50) -> list[dict[str, Any]]:
        async with self._lock:
            return [v for k, v in self._goals.items() if k.startswith("runtime:")][-limit:]

    # ── GoalResult index ──────────────────────────────────────────────────

    async def store_goal_result(self, goal_id: str, result_dict: dict[str, Any]) -> None:
        """Index a GoalResult by goal_id."""
        async with self._lock:
            self._goal_results[goal_id] = result_dict

    async def get_goal_result(self, goal_id: str) -> dict[str, Any] | None:
        async with self._lock:
            return self._goal_results.get(goal_id)

    async def list_goal_results(self, limit: int = 50) -> list[dict[str, Any]]:
        async with self._lock:
            return list(self._goal_results.values())[-limit:]

    # ── MemoryManager bridge ─────────────────────────────────────────

    async def write_to_memory(self, scope: str, key: str, value: str) -> None:
        """Write to the existing MemoryManager if available."""
        if self._memory is None:
            return
        try:
            from agentic_os.domain.memory import MemoryItem, MemoryScope

            item = MemoryItem(
                scope=MemoryScope(scope),
                key=key,
                value=value,
            )
            await self._memory.write(item)
        except Exception:
            log.exception("Failed to write to MemoryManager")

    async def read_from_memory(self, scope: str, key: str) -> str | None:
        """Read from the existing MemoryManager if available."""
        if self._memory is None:
            return None
        try:
            from agentic_os.domain.memory import MemoryScope

            item = await self._memory.read(MemoryScope(scope), key)
            return item.value if item else None
        except Exception:
            return None

    # ── Metrics ───────────────────────────────────────────────────────

    async def metrics(self) -> dict[str, int]:
        async with self._lock:
            return {
                "goals_indexed": len([k for k in self._goals if not k.startswith("runtime:")]),
                "reflections_indexed": len(self._reflections),
                "decisions_indexed": len(self._decisions),
                "failures_indexed": len(self._failures),
                "runtime_events_indexed": len([k for k in self._goals if k.startswith("runtime:")]),
                "goal_results_indexed": len(self._goal_results),
            }
