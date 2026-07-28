"""GoalManager — creates, schedules, and manages the lifecycle of Goals.

Goals are the highest-level abstraction in the Executive Intelligence
Layer. A Goal describes WHAT to achieve; the GoalManager creates a
Mission from it (via the existing MissionPlanner), which decomposes
into Tasks executed by discovered runtimes.

The GoalManager does NOT replace the MissionPlanner — it wraps it.
Goals create Missions; Missions create Tasks; Tasks are executed by
runtimes.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from agentic_os.core.executive.domain import Goal, GoalPriority, GoalStatus
from agentic_os.infrastructure.logging import get_logger

if TYPE_CHECKING:
    from agentic_os.core.mission import MissionPlannerImpl
    from agentic_os.ports.event_bus import EventBus

log = get_logger("executive.goals")


class GoalManager:
    """Manages the lifecycle of executive Goals.

    Thread-safety
    -------------
    All public methods that read or mutate ``_goals`` acquire an
    ``asyncio.Lock``.

    Lifecycle
    ---------
    ::

        mgr = GoalManager(bus, mission_planner)
        await mgr.start()
        goal = await mgr.create_goal("Refactor the API")
        await mgr.activate(goal.id)
        # ... system runs ...
        await mgr.stop()
    """

    def __init__(
        self,
        bus: EventBus,
        mission_planner: MissionPlannerImpl | None = None,
    ) -> None:
        self._bus: EventBus = bus
        self._planner: MissionPlannerImpl | None = mission_planner
        self._goals: dict[str, Goal] = {}
        self._lock = asyncio.Lock()
        self._started = False

    @property
    def is_started(self) -> bool:
        return self._started

    async def start(self) -> None:
        self._started = True
        log.info("GoalManager started")

    async def stop(self) -> None:
        self._started = False
        log.info("GoalManager stopped")

    # ── CRUD ───────────────────────────────────────────────────────────

    async def create_goal(
        self,
        title: str,
        description: str = "",
        priority: GoalPriority = GoalPriority.NORMAL,
        dependencies: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> Goal:
        """Create a new Goal and publish ``executive.goal.created``."""
        goal = Goal(
            title=title,
            description=description or title,
            priority=priority,
            dependencies=dependencies or [],
            tags=tags or [],
        )
        async with self._lock:
            self._goals[goal.id] = goal
        await self._publish("executive.goal.created", goal.to_dict())
        log.info("Created goal %s (%s)", goal.id, goal.title)
        return goal

    async def cancel_goal(self, goal_id: str) -> Goal | None:
        """Cancel a goal and publish ``executive.goal.cancelled``."""
        async with self._lock:
            goal = self._goals.get(goal_id)
            if goal is None:
                return None
            goal.status = GoalStatus.CANCELLED
            goal.updated_at = datetime.now(UTC).isoformat()
        await self._publish("executive.goal.cancelled", goal.to_dict())
        log.info("Cancelled goal %s", goal_id)
        return goal

    async def reprioritize(self, goal_id: str, priority: GoalPriority) -> Goal | None:
        """Change a goal's priority."""
        async with self._lock:
            goal = self._goals.get(goal_id)
            if goal is None:
                return None
            goal.priority = priority
            goal.updated_at = datetime.now(UTC).isoformat()
        await self._publish("executive.goal.reprioritized", goal.to_dict())
        return goal

    async def suspend(self, goal_id: str) -> Goal | None:
        """Pause a goal (move to PAUSED state)."""
        async with self._lock:
            goal = self._goals.get(goal_id)
            if goal is None:
                return None
            goal.status = GoalStatus.PAUSED
            goal.updated_at = datetime.now(UTC).isoformat()
        await self._publish("executive.goal.suspended", goal.to_dict())
        return goal

    async def resume(self, goal_id: str) -> Goal | None:
        """Resume a paused goal (move back to PENDING)."""
        async with self._lock:
            goal = self._goals.get(goal_id)
            if goal is None:
                return None
            goal.status = GoalStatus.PENDING
            goal.updated_at = datetime.now(UTC).isoformat()
        await self._publish("executive.goal.resumed", goal.to_dict())
        return goal

    async def merge_goals(self, goal_ids: list[str], new_title: str) -> Goal | None:
        """Merge multiple goals into a new goal. Original goals are marked MERGED."""
        async with self._lock:
            merged_goals: list[Goal] = [
                g for gid in goal_ids if (g := self._goals.get(gid)) is not None
            ]
            if len(merged_goals) < 2:
                return None
            # Mark originals as merged
            for g in merged_goals:
                g.status = GoalStatus.MERGED
                g.updated_at = datetime.now(UTC).isoformat()
            # Create new goal
            new_goal = Goal(
                title=new_title,
                description=" | ".join(g.title for g in merged_goals),
                priority=max(g.priority for g in merged_goals),
                dependencies=list(
                    {d for g in merged_goals for d in g.dependencies if d not in goal_ids}
                ),
            )
            self._goals[new_goal.id] = new_goal
        await self._publish("executive.goal.merged", new_goal.to_dict())
        return new_goal

    async def split_goal(self, goal_id: str, sub_titles: list[str]) -> list[Goal]:
        """Split a goal into multiple sub-goals. Original goal is marked SPLIT."""
        async with self._lock:
            parent = self._goals.get(goal_id)
            if parent is None or len(sub_titles) < 2:
                return []
            parent.status = GoalStatus.SPLIT
            parent.updated_at = datetime.now(UTC).isoformat()
            children: list[Goal] = []
            for title in sub_titles:
                child = Goal(
                    title=title,
                    description=f"Sub-goal of {parent.title}: {title}",
                    priority=parent.priority,
                    dependencies=[goal_id],
                )
                self._goals[child.id] = child
                children.append(child)
        for child in children:
            await self._publish("executive.goal.created", child.to_dict())
        await self._publish("executive.goal.split", parent.to_dict())
        return children

    # ── Activation ─────────────────────────────────────────────────────

    async def activate(self, goal_id: str) -> Goal | None:
        """Activate a goal: create a Mission via the existing MissionPlanner.

        The GoalManager does NOT execute the mission — it delegates to
        the existing MissionPlanner, which decomposes the goal into tasks.
        """
        async with self._lock:
            goal = self._goals.get(goal_id)
            if goal is None:
                return None
            goal.status = GoalStatus.ACTIVE
            goal.updated_at = datetime.now(UTC).isoformat()
        await self._publish("executive.goal.started", goal.to_dict())

        # If a MissionPlanner is available, create a mission from the goal
        if self._planner is not None:
            try:
                from agentic_os.domain.mission import Mission, MissionStatus

                mission = Mission(title=goal.title, description=goal.description)
                mission.status = MissionStatus.PLANNING
                plan = await self._planner.analyze(mission)
                mission.plan = plan
                mission.status = MissionStatus.PLANNED
                async with self._lock:
                    goal.mission_id = mission.id
                    goal.updated_at = datetime.now(UTC).isoformat()
                await self._publish(
                    "executive.goal.planned",
                    {**goal.to_dict(), "mission_id": mission.id, "plan": plan.to_dict()},
                )
                log.info("Goal %s planned as mission %s", goal_id, mission.id)
            except Exception:
                log.exception("Failed to plan goal %s", goal_id)

        return goal

    # ── Query ──────────────────────────────────────────────────────────

    async def get(self, goal_id: str) -> Goal | None:
        async with self._lock:
            return self._goals.get(goal_id)

    async def list_all(self) -> list[Goal]:
        async with self._lock:
            return list(self._goals.values())

    async def list_by_status(self, status: GoalStatus) -> list[Goal]:
        async with self._lock:
            return [g for g in self._goals.values() if g.status == status]

    async def list_pending(self) -> list[Goal]:
        """Return goals that are PENDING or ACTIVE, sorted by priority weight."""
        async with self._lock:
            eligible = [
                g
                for g in self._goals.values()
                if g.status in (GoalStatus.PENDING, GoalStatus.ACTIVE)
            ]
        # Sort by priority weight descending (highest first)
        eligible.sort(key=lambda g: g.priority.weight, reverse=True)
        return eligible

    async def complete(self, goal_id: str, reflection: str = "") -> Goal | None:
        """Mark a goal as completed with an optional reflection summary."""
        async with self._lock:
            goal = self._goals.get(goal_id)
            if goal is None:
                return None
            goal.status = GoalStatus.COMPLETED
            goal.reflection = reflection
            goal.completed_at = datetime.now(UTC).isoformat()
            goal.updated_at = goal.completed_at
        await self._publish("executive.goal.completed", goal.to_dict())
        log.info("Completed goal %s", goal_id)
        return goal

    async def fail(self, goal_id: str, reason: str = "") -> Goal | None:
        """Mark a goal as failed."""
        async with self._lock:
            goal = self._goals.get(goal_id)
            if goal is None:
                return None
            goal.status = GoalStatus.FAILED
            goal.reflection = reason
            goal.updated_at = datetime.now(UTC).isoformat()
        await self._publish("executive.goal.failed", goal.to_dict())
        return goal

    # ── Metrics ────────────────────────────────────────────────────────

    async def metrics(self) -> dict[str, int]:
        """Return aggregate metrics for observability."""
        async with self._lock:
            goals = list(self._goals.values())
        counts: dict[str, int] = {s.value: 0 for s in GoalStatus}
        for g in goals:
            counts[g.status.value] = counts.get(g.status.value, 0) + 1
        counts["total"] = len(goals)
        return counts

    # ── Internals ──────────────────────────────────────────────────────

    async def _publish(self, topic_str: str, payload: dict) -> None:
        """Publish an executive event on the existing EventBus."""
        from agentic_os.domain.events import EventEnvelope

        try:
            await self._bus.publish(
                EventEnvelope(
                    type=topic_str,
                    source="executive.goals",
                    topic=topic_str,
                    payload=payload,
                )
            )
        except Exception:
            log.exception("Failed to publish %s", topic_str)
