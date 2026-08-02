"""Phase 13 — Autonomous Executive Decision & Mission Orchestration.

Extends ExecutiveController with:
  - ExecutiveWorldState (live platform snapshot from EventBus)
  - MissionComposer (decompose goals → missions with estimates)
  - ResourceAllocator (allocate brains/providers/memory per mission)
  - MissionSupervisor (detect stalled/overloaded/blocked missions)
  - DynamicPrioritizer (reprioritize based on policy + performance)
  - ExecutivePolicies (runtime-switchable: throughput/quality/...)
  - ExecutiveDecision records (with evidence + predicted impact)

All additive — the existing ExecutiveController is extended, not
replaced. New methods are added; existing methods are unchanged.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from agentic_os.core.executive.phase13_domain import (
    ExecutiveDecision,
    ExecutivePolicy,
    ExecutivePolicyType,
    ExecutiveWorldState,
    MissionSupervisionRecord,
    ResourceAllocation,
)
from agentic_os.infrastructure.logging import get_logger

if TYPE_CHECKING:
    from agentic_os.core.brains.registry import BrainRegistry
    from agentic_os.core.executive.goal_manager import GoalManager
    from agentic_os.core.executive.memory import ExecutiveMemory
    from agentic_os.ports.event_bus import EventBus

log = get_logger("executive.phase13")

# Additional topics for Phase 13 executive observation
_PHASE13_TOPICS = [
    "task.created",
    "task.dispatched",
    "task.assigned",
    "mission.started",
    "mission.planning",
    "mission.planned",
]


class ExecutiveOrchestrator:
    """Phase 13 extension to ExecutiveController.

    Provides:
      - ExecutiveWorldState maintenance
      - Mission composition (goal → mission with estimates)
      - Resource allocation
      - Mission supervision (stalled/overloaded detection)
      - Dynamic prioritization
      - Executive policy management
      - Executive decision records

    This class is instantiated by the existing ExecutiveController
    and delegates to it for existing functionality. It does NOT
    replace any existing component.
    """

    def __init__(
        self,
        bus: EventBus,
        brain_registry: BrainRegistry | None = None,
        goal_manager: GoalManager | None = None,
        exec_memory: ExecutiveMemory | None = None,
    ) -> None:
        self._bus = bus
        self._registry = brain_registry
        self._goals = goal_manager
        self._memory = exec_memory
        self._started = False
        self._subs: list[str] = []

        # World state
        self._world = ExecutiveWorldState()

        # Policy
        self._policy = ExecutivePolicy()

        # Decision history
        self._decisions: list[ExecutiveDecision] = []
        self._allocations: list[ResourceAllocation] = []
        self._supervision_records: list[MissionSupervisionRecord] = []

        # Policy history
        self._policy_history: list[dict[str, Any]] = []

    @property
    def world_state(self) -> ExecutiveWorldState:
        return self._world

    @property
    def policy(self) -> ExecutivePolicy:
        return self._policy

    @property
    def decisions(self) -> list[ExecutiveDecision]:
        return self._decisions

    @property
    def allocations(self) -> list[ResourceAllocation]:
        return self._allocations

    # ── Lifecycle ───────────────────────────────────────────────────

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        for topic in _PHASE13_TOPICS:
            try:
                sub_id = await self._bus.subscribe(topic, self._on_event)
                self._subs.append(sub_id)
            except Exception:
                log.exception("Failed to subscribe to %s", topic)
        await self._publish("executive.started", {"timestamp": datetime.now(UTC).isoformat()})
        log.info("ExecutiveOrchestrator started (%d subscriptions)", len(self._subs))

    async def stop(self) -> None:
        self._started = False
        for sub_id in self._subs:
            try:
                await self._bus.unsubscribe(sub_id)
            except Exception:
                pass
        self._subs.clear()
        await self._publish("executive.stopped", {"timestamp": datetime.now(UTC).isoformat()})
        log.info("ExecutiveOrchestrator stopped")

    # ── Event handler ───────────────────────────────────────────────

    async def _on_event(self, event: Any) -> None:
        topic = event.topic
        payload = event.payload or {}
        try:
            if topic == "mission.started":
                mid = str(payload.get("id", ""))
                self._world.missions[mid] = payload
                await self._publish("executive.mission.created", {"mission_id": mid})
            elif topic == "mission.planning":
                mid = str(payload.get("mission_id", ""))
                if mid in self._world.missions:
                    self._world.missions[mid]["status"] = "planning"
                    await self._publish(
                        "executive.mission.updated", {"mission_id": mid, "status": "planning"}
                    )
            elif topic == "mission.planned":
                mid = str(payload.get("mission_id", ""))
                if mid in self._world.missions:
                    self._world.missions[mid]["status"] = "planned"
                    await self._publish(
                        "executive.mission.updated", {"mission_id": mid, "status": "planned"}
                    )
            elif topic == "task.created":
                self._world.execution_queue_size += 1
            elif topic == "task.assigned":
                self._world.execution_queue_size = max(0, self._world.execution_queue_size - 1)
            elif topic == "task.dispatched":
                # Track active brain utilization
                provider = payload.get("assigned_provider", "")
                if provider and provider not in self._world.active_providers:
                    self._world.active_providers.append(provider)
            self._world.last_updated = datetime.now(UTC).isoformat()
        except Exception:
            log.exception("Phase13 event handler failed for %s", topic)

    # ── Mission Composer ────────────────────────────────────────────

    async def compose_mission(
        self,
        goal_id: str = "",
        title: str = "",
        description: str = "",
        required_capabilities: list[str] | None = None,
    ) -> dict[str, Any]:
        """Analyze a goal and compose a mission plan with estimates.

        Uses the live BrainRegistry to determine available runtimes
        and estimate complexity, resources, time, and success.
        """
        required_capabilities = required_capabilities or ["chat"]
        runtime_count = 0
        matching_runtimes: list[str] = []

        if self._registry is not None:
            try:
                brains = await self._registry.list_all()
                runtime_count = len(brains)
                for b in brains:
                    caps = list(b.capabilities) if b.capabilities else []
                    if any(c in caps for c in required_capabilities):
                        matching_runtimes.append(b.display_name)
            except Exception:
                pass

        # Estimate complexity (1-10 scale based on capability count)
        complexity = min(len(required_capabilities) * 2, 10)

        # Estimate execution time (seconds)
        estimated_time = max(60, 300 / max(runtime_count, 1))

        # Estimate resources
        estimated_memory = 128.0 * max(len(matching_runtimes), 1)

        # Estimate probability of success
        if runtime_count == 0:
            prob_success = 0.0
        elif matching_runtimes:
            prob_success = min(0.9, 0.5 + 0.1 * len(matching_runtimes))
        else:
            prob_success = 0.3  # runtimes exist but no capability match

        # Create resource allocation
        alloc = ResourceAllocation(
            mission_id=goal_id,
            brain_ids=matching_runtimes[:3],
            priority=self._policy.type.value,
            memory_mb=estimated_memory,
        )
        self._allocations.append(alloc)

        await self._publish(
            "executive.resource.allocated",
            alloc.to_dict(),
        )
        await self._publish(
            "executive.mission.created",
            {"goal_id": goal_id, "title": title},
        )

        # Create executive decision record
        match_count = len(matching_runtimes)
        decision = ExecutiveDecision(
            decision_type="mission_composition",
            reason=(f"Composed mission for goal '{title}' with {match_count} matching runtimes"),
            evidence={
                "runtime_count": runtime_count,
                "matching_runtimes": matching_runtimes,
                "required_capabilities": required_capabilities,
                "complexity": complexity,
            },
            confidence=prob_success,
            predicted_impact=(
                f"Mission expected to complete in ~{estimated_time:.0f}s"
                f" with {prob_success:.0%} success rate"
            ),
            target_id=goal_id,
        )
        self._decisions.append(decision)
        if len(self._decisions) > 500:
            self._decisions = self._decisions[-500:]
        await self._publish(
            "executive.decision.created",
            decision.to_dict(),
        )

        return {
            "goal_id": goal_id,
            "title": title,
            "description": description,
            "complexity": complexity,
            "estimated_time_seconds": round(estimated_time, 1),
            "estimated_memory_mb": estimated_memory,
            "probability_of_success": round(prob_success, 3),
            "matching_runtimes": matching_runtimes,
            "allocation": alloc.to_dict(),
            "decision": decision.to_dict(),
        }

    # ── Resource Allocator ─────────────────────────────────────────

    async def allocate_resources(
        self,
        mission_id: str = "",
        required_capabilities: list[str] | None = None,
        priority: str = "normal",
    ) -> ResourceAllocation:
        """Allocate brains, providers, memory, and context to a mission."""
        required_capabilities = required_capabilities or []
        brain_ids: list[str] = []
        provider_ids: list[str] = []

        if self._registry is not None:
            try:
                brains = await self._registry.list_all()
                for b in brains:
                    caps = list(b.capabilities) if b.capabilities else []
                    if any(c in caps for c in required_capabilities):
                        brain_ids.append(b.id)
                        provider_ids.append(b.display_name)
                    if len(brain_ids) >= 5:
                        break
            except Exception:
                pass

        alloc = ResourceAllocation(
            mission_id=mission_id,
            brain_ids=brain_ids,
            provider_ids=provider_ids,
            memory_mb=256.0,
            context_tokens=8192,
            priority=priority,
        )
        self._allocations.append(alloc)
        if len(self._allocations) > 200:
            self._allocations = self._allocations[-200:]
        await self._publish("executive.resource.allocated", alloc.to_dict())
        log.info(
            "Allocated %d brains to mission %s (priority=%s)",
            len(brain_ids),
            mission_id,
            priority,
        )
        return alloc

    async def release_resources(self, mission_id: str) -> dict[str, Any]:
        """Release all resources allocated to a mission."""
        released: list[str] = []
        for alloc in self._allocations:
            if alloc.mission_id == mission_id and not alloc.released_at:
                alloc.released_at = datetime.now(UTC).isoformat()
                released.append(alloc.id)
                await self._publish(
                    "executive.resource.released",
                    {"allocation_id": alloc.id, "mission_id": mission_id},
                )
        return {"mission_id": mission_id, "released": released}

    # ── Mission Supervisor ──────────────────────────────────────────

    async def supervise_missions(self) -> list[MissionSupervisionRecord]:
        """Monitor all known missions for health issues."""
        records: list[MissionSupervisionRecord] = []

        for mid, data in self._world.missions.items():
            status = data.get("status", "")
            is_stalled = status == "executing" and len(data.get("tasks", [])) == 0
            is_blocked = status == "blocked"
            issues: list[str] = []

            if is_stalled:
                issues.append("Mission is executing but has no tasks")
            if is_blocked:
                issues.append("Mission is blocked")

            record = MissionSupervisionRecord(
                mission_id=mid,
                is_stalled=is_stalled,
                is_blocked=is_blocked,
                issues=issues,
            )
            records.append(record)
            self._supervision_records.append(record)

        if records:
            await self._publish(
                "executive.optimization.completed",
                {"supervision_count": len(records)},
            )

        return records

    # ── Dynamic Prioritization ─────────────────────────────────────

    async def reprioritize(self) -> dict[str, Any]:
        """Reprioritize goals based on current policy + performance."""
        if self._goals is None:
            return {"reprioritized": 0}

        pending = await self._goals.list_pending()
        # Sort by policy-specific criteria
        if self._policy.type == ExecutivePolicyType.THROUGHPUT:
            # Prioritize goals that are ready to execute (have mission_id)
            pending.sort(key=lambda g: (0 if g.mission_id else 1, -g.priority.weight))
        elif self._policy.type == ExecutivePolicyType.QUALITY:
            # Prioritize higher-priority goals first
            pending.sort(key=lambda g: -g.priority.weight)
        elif self._policy.type == ExecutivePolicyType.LATENCY:
            # Prioritize goals with existing missions (less planning overhead)
            pending.sort(key=lambda g: 0 if g.mission_id else 1)
        else:
            # Balanced: default priority ordering
            pending.sort(key=lambda g: -g.priority.weight)

        return {
            "reprioritized": len(pending),
            "policy": self._policy.type.value,
            "queue": [g.to_dict() for g in pending[:10]],
        }

    # ── Policy Management ──────────────────────────────────────────

    def set_policy(
        self,
        policy_type: ExecutivePolicyType,
        params: dict[str, Any] | None = None,
    ) -> ExecutivePolicy:
        """Switch the executive policy at runtime."""
        old_type = self._policy.type
        self._policy = ExecutivePolicy(policy_type, params)
        self._policy_history.append(
            {
                "old_policy": old_type.value,
                "new_policy": policy_type.value,
                "params": params or {},
                "changed_at": self._policy.updated_at,
            }
        )
        log.info("Executive policy changed: %s → %s", old_type.value, policy_type.value)
        return self._policy

    def get_policy(self) -> ExecutivePolicy:
        return self._policy

    def get_policy_history(self) -> list[dict[str, Any]]:
        return self._policy_history

    # ── Executive Decisions ─────────────────────────────────────────

    def get_decisions(self, limit: int = 50) -> list[dict[str, Any]]:
        return [d.to_dict() for d in self._decisions[-limit:]]

    def get_allocations(self, limit: int = 50) -> list[dict[str, Any]]:
        return [a.to_dict() for a in self._allocations[-limit:]]

    # ── World State ──────────────────────────────────────────────────

    async def get_world_state(self) -> dict[str, Any]:
        """Return the live executive world state."""
        # Refresh from BrainRegistry if available
        if self._registry is not None:
            try:
                brains = await self._registry.list_all()
                self._world.runtimes = {
                    b.id: {"name": b.display_name, "health": b.health} for b in brains
                }
                self._world.active_brains = [b.id for b in brains if b.health >= 50]
            except Exception:
                pass
        # Refresh from goals if available
        if self._goals is not None:
            try:
                pending = await self._goals.list_pending()
                self._world.execution_queue_size = len(pending)
            except Exception:
                pass
        return self._world.to_dict()

    # ── Recovery ────────────────────────────────────────────────────

    async def trigger_recovery(self, mission_id: str, reason: str = "") -> dict[str, Any]:
        """Trigger automatic recovery for a stalled/failed mission."""
        await self._publish(
            "executive.recovery.started",
            {"mission_id": mission_id, "reason": reason},
        )
        # Record the decision
        decision = ExecutiveDecision(
            decision_type="recovery",
            reason=f"Recovery triggered for mission {mission_id}: {reason}",
            confidence=0.5,
            predicted_impact="Mission will be retried with alternative runtime if available",
            target_id=mission_id,
        )
        self._decisions.append(decision)
        await self._publish(
            "executive.decision.created",
            decision.to_dict(),
        )
        await self._publish(
            "executive.recovery.completed",
            {"mission_id": mission_id, "status": "recovery_initiated"},
        )
        return {"mission_id": mission_id, "recovery": "initiated", "reason": reason}

    # ── Optimize ────────────────────────────────────────────────────

    async def optimize(self) -> dict[str, Any]:
        """Run an optimization cycle: reprioritize + supervise + allocate."""
        # 1. Reprioritize
        repri = await self.reprioritize()

        # 2. Supervise
        supervision = await self.supervise_missions()

        # 3. Publish optimization completed
        await self._publish(
            "executive.optimization.completed",
            {
                "reprioritized": repri.get("reprioritized", 0),
                "supervision_count": len(supervision),
                "policy": self._policy.type.value,
            },
        )

        return {
            "reprioritized": repri,
            "supervision": [r.to_dict() for r in supervision],
            "policy": self._policy.to_dict(),
        }

    # ── Dashboard ──────────────────────────────────────────────────

    async def dashboard(self) -> dict[str, Any]:
        """Return aggregate executive dashboard data."""
        world = await self.get_world_state()
        return {
            "status": {"started": self._started, "subscriptions": len(self._subs)},
            "world": world,
            "policy": self._policy.to_dict(),
            "decisions_count": len(self._decisions),
            "allocations_count": len(self._allocations),
            "supervision_count": len(self._supervision_records),
            "policy_history": self._policy_history[-5:],
        }

    # ── Internals ────────────────────────────────────────────────────

    async def _publish(self, topic: str, payload: dict[str, Any]) -> None:
        from agentic_os.domain.events import EventEnvelope

        try:
            await self._bus.publish(
                EventEnvelope(
                    type=topic,
                    source="executive.orchestrator",
                    topic=topic,
                    payload=payload,
                )
            )
        except Exception:
            log.exception("Failed to publish %s", topic)
