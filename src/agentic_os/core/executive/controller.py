"""ExecutiveController — the continuously running executive intelligence.

The ExecutiveController is a long-running asyncio task that:
  1. Observes system state (via EventBus subscriptions)
  2. Manages the goal queue (prioritizes + activates goals)
  3. Makes routing decisions (via DecisionEngine)
  4. Monitors mission completion (via EventBus)
  5. Generates reflections (via ReflectionEngine)
  6. Learns from outcomes (via Learning engine)
  7. Optimizes routing policies

It subscribes to existing EventBus topics — never polls when events
already exist. It uses the existing MissionPlanner, BrainRegistry,
MemoryManager, and LearningManager.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from agentic_os.core.executive.decision_engine import DecisionEngine
from agentic_os.core.executive.goal_manager import GoalManager
from agentic_os.core.executive.memory import ExecutiveMemory
from agentic_os.core.executive.reflection_engine import ReflectionEngine
from agentic_os.infrastructure.logging import get_logger

if TYPE_CHECKING:
    from agentic_os.core.brains.registry import BrainRegistry
    from agentic_os.core.learning.manager import LearningManager
    from agentic_os.core.memory.manager import MemoryManagerImpl
    from agentic_os.core.mission import MissionPlannerImpl
    from agentic_os.domain.events import EventEnvelope
    from agentic_os.ports.event_bus import EventBus

log = get_logger("executive.controller")

# Topics the ExecutiveController subscribes to
_OBSERVED_TOPICS = [
    "mission.completed",
    "mission.failed",
    "mission.cancelled",
    "brain.registered",
    "brain.removed",
    "brain.health_changed",
    "agent.started",
    "agent.completed",
    "agent.failed",
    "agent.recovered",
]


class ExecutiveController:
    """The continuously running executive intelligence.

    Lifecycle
    ---------
    ::

        ctrl = ExecutiveController(bus, brain_registry, ...)
        await ctrl.start()
        # ... runs in background ...
        await ctrl.stop()
    """

    def __init__(
        self,
        bus: EventBus,
        brain_registry: BrainRegistry | None = None,
        mission_planner: MissionPlannerImpl | None = None,
        memory: MemoryManagerImpl | None = None,
        learning: LearningManager | None = None,
    ) -> None:
        self._bus: EventBus = bus
        self._started = False
        self._task: asyncio.Task | None = None
        self._subscriptions: list[str] = []

        # Executive components
        self._memory = ExecutiveMemory(memory)
        self._goals = GoalManager(bus, mission_planner)
        self._decisions = DecisionEngine(brain_registry, learning)
        self._reflection = ReflectionEngine(bus, self._memory, self._goals)

        # Phase 13: Executive Orchestrator (world state, policies, allocation, supervision)
        from agentic_os.core.executive.orchestrator import ExecutiveOrchestrator

        self._orchestrator = ExecutiveOrchestrator(
            bus=bus,
            brain_registry=brain_registry,
            goal_manager=self._goals,
            exec_memory=self._memory,
        )

        # Wire cross-references
        self._decisions.set_registry(brain_registry) if brain_registry else None
        self._decisions.set_learning(learning) if learning else None
        self._reflection.set_memory(self._memory)
        self._reflection.set_goal_manager(self._goals)

        # Stats
        self._events_processed = 0
        self._decisions_made = 0
        self._reflections_generated = 0

    @property
    def goal_manager(self) -> GoalManager:
        return self._goals

    @property
    def decision_engine(self) -> DecisionEngine:
        return self._decisions

    @property
    def reflection_engine(self) -> ReflectionEngine:
        return self._reflection

    @property
    def memory(self) -> ExecutiveMemory:
        return self._memory

    @property
    def orchestrator(self) -> Any:
        """Phase 13 ExecutiveOrchestrator instance."""
        return self._orchestrator

    async def start(self) -> None:
        """Start the controller: subscribe to events + launch background loop."""
        if self._started:
            return
        self._started = True

        await self._goals.start()

        # Subscribe to existing EventBus topics
        for topic in _OBSERVED_TOPICS:
            try:
                sub_id = await self._bus.subscribe(topic, self._on_event)
                self._subscriptions.append(sub_id)
            except Exception:
                log.exception("Failed to subscribe to %s", topic)

        # Start Phase 13 orchestrator
        await self._orchestrator.start()

        # Start background optimization loop (runs every 60s)
        self._task = asyncio.create_task(self._optimization_loop())

        log.info("ExecutiveController started (%d subscriptions)", len(self._subscriptions))

    async def stop(self) -> None:
        """Stop the controller: unsubscribe + cancel background loop."""
        self._started = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        # Stop Phase 13 orchestrator
        await self._orchestrator.stop()
        for sub_id in self._subscriptions:
            try:
                await self._bus.unsubscribe(sub_id)
            except Exception:
                pass
        self._subscriptions.clear()
        await self._goals.stop()
        log.info("ExecutiveController stopped")

    # ── Event handler ──────────────────────────────────────────────────

    async def _on_event(self, event: EventEnvelope) -> None:
        """Handle an observed EventBus event."""
        self._events_processed += 1
        topic = event.topic
        payload = event.payload

        try:
            if topic == "mission.completed":
                await self._on_mission_completed(payload)
            elif topic == "mission.failed":
                await self._on_mission_failed(payload)
            elif topic == "brain.registered":
                await self._memory.store_runtime_event(payload)
            elif topic == "brain.removed":
                await self._memory.store_runtime_event(payload)
            elif topic == "brain.health_changed":
                await self._memory.store_runtime_event(payload)
            elif topic == "agent.failed":
                await self._memory.store_failure(
                    {"id": payload.get("id", ""), "topic": topic, "payload": payload}
                )
        except Exception:
            log.exception("Failed to handle event %s", topic)

    async def _on_mission_completed(self, payload: dict) -> None:
        """Generate a reflection when a mission completes."""
        mission_id = payload.get("id", payload.get("mission_id", ""))
        goal_id = payload.get("goal_id", "")

        # Use the DecisionEngine's history to find the best runtime
        decisions = self._decisions.get_history(limit=100)
        best_runtime = ""
        if decisions:
            # Find the decision with highest confidence for this mission
            mission_decisions = [d for d in decisions if d.get("goal_id") == goal_id]
            if mission_decisions:
                best = max(mission_decisions, key=lambda d: d.get("confidence", 0))
                best_runtime = best.get("factors", {}).get("brain_name", "")

        await self._reflection.reflect(
            goal_id=goal_id,
            mission_id=mission_id,
            goal_achieved=True,
            retries_needed=0,
            best_runtime=best_runtime,
            routing_could_improve=False,
        )
        self._reflections_generated += 1

    async def _on_mission_failed(self, payload: dict) -> None:
        """Generate a reflection + trigger recovery when a mission fails."""
        mission_id = payload.get("id", payload.get("mission_id", ""))
        goal_id = payload.get("goal_id", "")
        error = payload.get("error", "")

        # Record the failure
        await self._memory.store_failure(
            {"id": mission_id, "goal_id": goal_id, "error": error, "payload": payload}
        )

        await self._reflection.reflect(
            goal_id=goal_id,
            mission_id=mission_id,
            goal_achieved=False,
            retries_needed=1,
            best_runtime="",
            failed_runtimes=[],
            routing_could_improve=True,
            summary=f"Mission failed: {error}",
        )
        self._reflections_generated += 1

    # ── Background optimization loop ────────────────────────────────────

    async def _optimization_loop(self) -> None:
        """Background loop: every 60s, optimize the goal queue.

        - Activate pending goals (by priority)
        - Make routing decisions for active goals
        - Publish optimization metrics
        """
        while self._started:
            try:
                await asyncio.sleep(60)
                await self._optimize()
            except asyncio.CancelledError:
                break
            except Exception:
                log.exception("Optimization loop error")

    async def _optimize(self) -> None:
        """Run one optimization cycle."""
        # Get pending goals sorted by priority
        pending = await self._goals.list_pending()
        if not pending:
            return

        # Activate up to 3 goals (configurable)
        for goal in pending[:3]:
            if goal.status.value == "pending":
                await self._goals.activate(goal.id)
                # Make a routing decision for the goal
                decision = await self._decisions.select(
                    required_capability="chat",
                    goal_id=goal.id,
                    task_id=goal.mission_id,
                )
                if decision is not None:
                    await self._memory.store_decision(decision.to_dict())
                    self._decisions_made += 1
                    await self._publish(
                        "executive.decision",
                        decision.to_dict(),
                    )

    async def _publish(self, topic_str: str, payload: dict) -> None:
        from agentic_os.domain.events import EventEnvelope

        try:
            await self._bus.publish(
                EventEnvelope(
                    type=topic_str,
                    source="executive.controller",
                    topic=topic_str,
                    payload=payload,
                )
            )
        except Exception:
            log.exception("Failed to publish %s", topic_str)

    # ── Status / metrics ──────────────────────────────────────────────

    def status(self) -> dict[str, Any]:
        """Return the controller's current status for /api/executive/status."""
        return {
            "started": self._started,
            "subscriptions": len(self._subscriptions),
            "events_processed": self._events_processed,
            "decisions_made": self._decisions_made,
            "reflections_generated": self._reflections_generated,
            "observed_topics": list(_OBSERVED_TOPICS),
        }
