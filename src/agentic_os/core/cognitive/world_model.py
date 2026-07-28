"""World Model — continuously updated system understanding.

Subscribes to EventBus and maintains a live view of:
  - available runtimes, capabilities, health
  - mission/goal statistics
  - system load, historical failures/successes
  - memory utilization, active collaborations
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from agentic_os.infrastructure.logging import get_logger

if TYPE_CHECKING:
    from agentic_os.core.brains.registry import BrainRegistry
    from agentic_os.core.executive.goal_manager import GoalManager
    from agentic_os.core.executive.memory import ExecutiveMemory
    from agentic_os.ports.event_bus import EventBus

log = get_logger("cognitive.world_model")

_OBSERVED_TOPICS = [
    "brain.registered",
    "brain.removed",
    "brain.health_changed",
    "mission.completed",
    "mission.failed",
    "agent.started",
    "agent.completed",
    "agent.failed",
]


class WorldModel:
    """Continuously updated understanding of the system state."""

    def __init__(
        self,
        bus: EventBus | None = None,
        brain_registry: BrainRegistry | None = None,
        goal_manager: GoalManager | None = None,
        exec_memory: ExecutiveMemory | None = None,
    ) -> None:
        self._bus = bus
        self._registry = brain_registry
        self._goals = goal_manager
        self._exec_mem = exec_memory
        self._subs: list[str] = []
        self._state: dict[str, Any] = self._initial_state()
        self._lock = asyncio.Lock()

    def _initial_state(self) -> dict[str, Any]:
        return {
            "runtimes": {},
            "runtime_count": 0,
            "mission_stats": {"completed": 0, "failed": 0, "active": 0},
            "goal_stats": {"total": 0, "active": 0, "completed": 0, "failed": 0},
            "system_load": {"events_processed": 0, "tasks_running": 0},
            "historical": {"failures": 0, "successes": 0},
            "memory_utilization": 0.0,
            "active_collaborations": 0,
            "last_updated": datetime.now(UTC).isoformat(),
        }

    async def start(self) -> None:
        if self._bus is None:
            return
        for topic in _OBSERVED_TOPICS:
            try:
                sub_id = await self._bus.subscribe(topic, self._on_event)
                self._subs.append(sub_id)
            except Exception:
                log.exception("Failed to subscribe to %s", topic)
        log.info("WorldModel started (%d subscriptions)", len(self._subs))

    async def stop(self) -> None:
        if self._bus is None:
            return
        for sub_id in self._subs:
            try:
                await self._bus.unsubscribe(sub_id)
            except Exception:
                pass
        self._subs.clear()

    async def _on_event(self, event: Any) -> None:
        topic = event.topic
        payload = event.payload or {}
        async with self._lock:
            if topic == "brain.registered":
                self._state["runtimes"][payload.get("id", "")] = payload
                self._state["runtime_count"] = len(self._state["runtimes"])
            elif topic == "brain.removed":
                self._state["runtimes"].pop(payload.get("id", ""), None)
                self._state["runtime_count"] = len(self._state["runtimes"])
            elif topic == "brain.health_changed":
                rid = payload.get("id", "")
                if rid in self._state["runtimes"]:
                    self._state["runtimes"][rid].update(payload)
            elif topic == "mission.completed":
                self._state["mission_stats"]["completed"] += 1
                self._state["historical"]["successes"] += 1
            elif topic == "mission.failed":
                self._state["mission_stats"]["failed"] += 1
                self._state["historical"]["failures"] += 1
            elif topic == "agent.started":
                self._state["system_load"]["tasks_running"] += 1
            elif topic == "agent.completed" or topic == "agent.failed":
                self._state["system_load"]["tasks_running"] = max(
                    0, self._state["system_load"]["tasks_running"] - 1
                )
            self._state["last_updated"] = datetime.now(UTC).isoformat()

    async def snapshot(self) -> dict[str, Any]:
        """Return a snapshot of the current world state."""
        async with self._lock:
            # Refresh runtime count from registry if available
            if self._registry is not None:
                try:
                    brains = await self._registry.list_all()
                    self._state["runtimes"] = {
                        b.id: {
                            "name": b.display_name,
                            "health": b.health,
                            "latency": b.latency,
                            "capabilities": list(b.capabilities),
                        }
                        for b in brains
                    }
                    self._state["runtime_count"] = len(brains)
                except Exception:
                    pass
            # Refresh goal stats if available
            if self._goals is not None:
                try:
                    goals = await self._goals.list_all()
                    self._state["goal_stats"]["total"] = len(goals)
                    self._state["goal_stats"]["active"] = sum(
                        1 for g in goals if g.status.value == "active"
                    )
                    self._state["goal_stats"]["completed"] = sum(
                        1 for g in goals if g.status.value == "completed"
                    )
                    self._state["goal_stats"]["failed"] = sum(
                        1 for g in goals if g.status.value == "failed"
                    )
                except Exception:
                    pass
            return dict(self._state)
