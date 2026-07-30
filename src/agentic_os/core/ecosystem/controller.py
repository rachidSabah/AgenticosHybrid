"""Phase 15 — EcosystemController.

Long-running controller that owns the EcosystemManager lifecycle and
subscribes it to the EventBus so the ecosystem updates automatically
on every brain.*/mission.*/swarm.* event.

Subscribes to:
  - brain.registered        → manager.on_brain_registered
  - brain.updated           → manager.on_brain_updated
  - brain.removed           → manager.on_brain_removed
  - mission.completed       → manager.on_mission_completed
  - mission.failed          → manager.on_mission_completed (success=False)
  - swarm.execution.completed → manager.on_swarm_completed

On every completed mission, the controller automatically triggers the
continuous self-optimization pipeline:
    Reflection (already done by ExecutiveController)
      → Evaluation (already done by CognitiveController)
      → Prediction update (already done by CognitiveController)
      → Learning (already done by LearningManager)
      → Capability update (done by EcosystemManager.refresh)
      → Evolution recommendation (done by EcosystemManager.optimize)
      → Executive optimization (ExecutiveController listens to ecosystem.evolution.generated)
      → Swarm optimization (SwarmCoordinator listens to ecosystem.evolution.generated)

No manual intervention required.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agentic_os.core.ecosystem.manager import EcosystemManager
from agentic_os.infrastructure.logging import get_logger

if TYPE_CHECKING:
    from agentic_os.core.brains.registry import BrainRegistry
    from agentic_os.core.cognitive.memory import CognitiveMemory
    from agentic_os.core.executive.memory import ExecutiveMemory
    from agentic_os.core.orchestration.swarm_coordinator import SwarmCoordinator
    from agentic_os.ports.event_bus import EventBus

log = get_logger("ecosystem.controller")

# Topics the EcosystemController subscribes to. All are existing topics —
# no new discovery or event pipelines are introduced.
_OBSERVED_TOPICS = [
    "brain.registered",
    "brain.updated",
    "brain.removed",
    "mission.completed",
    "mission.failed",
    "swarm.execution.completed",
]


class EcosystemController:
    """Long-running controller for the EcosystemManager."""

    def __init__(
        self,
        bus: EventBus,
        brain_registry: BrainRegistry | None = None,
        exec_memory: ExecutiveMemory | None = None,
        cognitive_memory: CognitiveMemory | None = None,
        swarm_coordinator: SwarmCoordinator | None = None,
    ) -> None:
        self._bus = bus
        self._started = False
        self._subscriptions: list[str] = []
        self._manager = EcosystemManager(
            bus=bus,
            brain_registry=brain_registry,
            exec_memory=exec_memory,
            cognitive_memory=cognitive_memory,
            swarm_coordinator=swarm_coordinator,
        )
        self._events_processed = 0
        self._optimizations_triggered = 0

    @property
    def manager(self) -> EcosystemManager:
        return self._manager

    @property
    def started(self) -> bool:
        return self._started

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        await self._manager.start()
        for topic in _OBSERVED_TOPICS:
            try:
                sub_id = await self._bus.subscribe(topic, self._on_event)
                self._subscriptions.append(sub_id)
            except Exception:
                log.exception("Failed to subscribe to %s", topic)
        # Announce ecosystem started
        await self._publish(
            "ecosystem.started",
            {
                "runtimes": self._manager.stats.total_runtimes,
                "capabilities": self._manager.stats.unique_capabilities,
            },
        )
        log.info(
            "EcosystemController started (%d subscriptions, %d runtimes)",
            len(self._subscriptions),
            self._manager.stats.total_runtimes,
        )

    async def stop(self) -> None:
        self._started = False
        for sub_id in self._subscriptions:
            try:
                await self._bus.unsubscribe(sub_id)
            except Exception:
                pass
        self._subscriptions.clear()
        await self._manager.stop()
        log.info("EcosystemController stopped")

    async def _on_event(self, event: Any) -> None:
        """Route brain.*/mission.*/swarm.* events to the EcosystemManager."""
        self._events_processed += 1
        topic = event.topic
        payload = event.payload or {}

        try:
            if topic == "brain.registered":
                await self._manager.on_brain_registered(payload)
            elif topic == "brain.updated":
                await self._manager.on_brain_updated(payload)
            elif topic == "brain.removed":
                await self._manager.on_brain_removed(payload)
            elif topic == "mission.completed":
                await self._manager.on_mission_completed({**payload, "success": True})
                # Trigger continuous self-optimization after every mission
                await self._trigger_optimization()
            elif topic == "mission.failed":
                await self._manager.on_mission_completed({**payload, "success": False})
                await self._trigger_optimization()
            elif topic == "swarm.execution.completed":
                await self._manager.on_swarm_completed({**payload, "success": True})
                await self._trigger_optimization()
        except Exception:
            log.exception("EcosystemController failed to handle %s", topic)

    async def _trigger_optimization(self) -> None:
        """Continuous self-optimization: analyze + publish recommendations.

        This is the autonomous feedback loop — no manual intervention.
        The Executive and Cognitive layers listen to
        ``ecosystem.evolution.generated`` and apply the recommendations
        they find relevant.
        """
        try:
            await self._manager.optimize()
            self._optimizations_triggered += 1
        except Exception:
            log.exception("Ecosystem optimization cycle failed")

    def status(self) -> dict[str, Any]:
        return {
            "started": self._started,
            "events_processed": self._events_processed,
            "optimizations_triggered": self._optimizations_triggered,
            "subscriptions": len(self._subscriptions),
            "manager": self._manager.dashboard(),
        }

    async def _publish(self, topic: str, payload: dict[str, Any]) -> None:
        try:
            from agentic_os.domain.events import EventEnvelope

            await self._bus.publish(
                EventEnvelope(
                    type=topic,
                    source="ecosystem.controller",
                    topic=topic,
                    payload=payload,
                )
            )
        except Exception:
            log.exception("Failed to publish %s", topic)
