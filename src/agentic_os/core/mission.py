"""Mission Planner — analyzes goals, decomposes into tasks, assigns agents.

The planner is the first stage of the Mission Orchestrator pipeline. It takes
a user-defined mission, analyzes goal + scope + complexity + dependencies,
decomposes it into ordered tasks, and assigns each task to the most appropriate
agent role through the Provider Framework role mapping.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from agentic_os.config import Settings
from agentic_os.domain.events import EventEnvelope, Topic
from agentic_os.domain.mission import (
    AgentRole,
    ExecutionMode,
    Mission,
    MissionPlan,
    MissionPriority,
    MissionTask,
    TaskStatus,
)
from agentic_os.infrastructure.logging import get_logger

if TYPE_CHECKING:
    from agentic_os.ports.event_bus import EventBus

log = get_logger("core.mission_planner")

# Role-to-provider mapping (can be overridden at runtime)
DEFAULT_ROLE_MAP: dict[AgentRole, str] = {
    AgentRole.CHIEF_ARCHITECT: "claude_code",
    AgentRole.REPOSITORY_AUDITOR: "hermes",
    AgentRole.BACKEND_ENGINEER: "opencode",
    AgentRole.FRONTEND_ENGINEER: "opencode",
    AgentRole.SECURITY_ENGINEER: "hermes",
    AgentRole.TEST_ENGINEER: "opencode",
    AgentRole.DOCUMENTATION_WRITER: "gemini_cli",
    AgentRole.RELEASE_ENGINEER: "hermes",
    AgentRole.RESEARCHER: "gemini_cli",
    AgentRole.DEBUGGER: "hermes",
    AgentRole.VALIDATOR: "hermes",
}


class MissionPlannerImpl:
    """Analyzes missions, produces execution plans, assigns agents by role."""

    def __init__(self, bus: EventBus, settings: Settings) -> None:
        self._bus = bus
        self._settings = settings
        self._role_map: dict[AgentRole, str] = dict(DEFAULT_ROLE_MAP)

    # ── Public API ──

    async def analyze(self, mission: Mission) -> MissionPlan:
        """Analyze a mission and produce an execution plan.

        This is the core planning pipeline:
        1. Emit ``planning`` event
        2. Analyze goal / scope / complexity / attachments
        3. Decompose into tasks with dependencies
        4. Assign agent roles and providers
        5. Emit ``planned`` event
        """
        await self._bus.publish(
            EventEnvelope(
                type="mission.planning",
                source="planner",
                topic=Topic.MISSION_PLANNING.value,
                payload={"mission_id": mission.id, "title": mission.title},
            )
        )

        complexity = self._estimate_complexity(mission)
        risk = self._estimate_risk(mission, complexity)
        tasks = self._decompose(mission)
        self._assign_roles(tasks)

        total_minutes = sum(t.estimated_minutes for t in tasks)

        plan = MissionPlan(
            mission_id=mission.id,
            summary=f"Plan for {mission.title}: {len(tasks)} tasks, "
            f"{mission.execution_mode.value} execution, "
            f"risk level {risk}",
            complexity=complexity,
            estimated_total_minutes=total_minutes,
            risk_level=risk,
            tasks=tasks,
        )

        await self._bus.publish(
            EventEnvelope(
                type="mission.planned",
                source="planner",
                topic=Topic.MISSION_PLANNED.value,
                payload={"mission_id": mission.id, "task_count": len(tasks), "plan_id": plan.id},
            )
        )

        return plan

    def update_role_map(self, role: AgentRole, provider: str) -> None:
        """Override the default provider for a given role."""
        self._role_map[role] = provider

    # ── Analysis heuristics ──

    def _estimate_complexity(self, mission: Mission) -> str:
        """Rough complexity estimate based on mission inputs."""
        score = 0
        if mission.prompt:
            score += len(mission.prompt) // 200  # longer prompt = more complex
        score += len(mission.objectives) * 2
        score += len(mission.deliverables) * 2
        score += len(mission.constraints) * 1
        score += len(mission.attachments) * 3
        if mission.execution_mode == ExecutionMode.HYBRID:
            score += 2
        if mission.priority == MissionPriority.CRITICAL:
            score += 3
        if score < 3:
            return "low"
        if score < 8:
            return "medium"
        return "high"

    def _estimate_risk(self, mission: Mission, complexity: str) -> str:
        """Simple risk assessment."""
        risk = 0
        if complexity == "high":
            risk += 2
        if mission.priority in (MissionPriority.HIGH, MissionPriority.CRITICAL):
            risk += 1
        if mission.deadline:
            delta = (mission.deadline - datetime.now(UTC)).total_seconds()
            if delta < 86400 * 3:  # 3 days
                risk += 2
        if not mission.prompt:
            risk += 1
        if risk < 2:
            return "low"
        if risk < 4:
            return "medium"
        return "high"

    def _decompose(self, mission: Mission) -> list[MissionTask]:
        """Decompose a mission into dependency-ordered tasks.

        Produces a standard set of tasks that every mission goes through,
        customized by the mission's inputs. This is the default decomposition
        strategy — advanced strategies can be added later.
        """
        tasks: list[MissionTask] = []

        # Task 1: Repository Analysis
        tasks.append(
            MissionTask(
                mission_id=mission.id,
                title="Analyze repository & environment",
                description="Scan the repository structure, technology stack, dependencies, "
                "and environment to understand the codebase context for the mission.",
                dependencies=[],
                estimated_minutes=10,
                assigned_role=AgentRole.REPOSITORY_AUDITOR,
            )
        )

        # Task 2: Architecture Review (depends on 1)
        tasks.append(
            MissionTask(
                mission_id=mission.id,
                title="Review architecture & design",
                description="Analyze existing architecture, design patterns, and identify "
                "impact areas for the mission objectives.",
                dependencies=[tasks[0].id],
                estimated_minutes=15,
                assigned_role=AgentRole.CHIEF_ARCHITECT,
            )
        )

        # Task 3: Design workflow (depends on 2)
        tasks.append(
            MissionTask(
                mission_id=mission.id,
                title="Design implementation workflow",
                description="Design the detailed implementation plan, including component "
                "breakdown, API contracts, and integration points.",
                dependencies=[tasks[1].id],
                estimated_minutes=15,
                assigned_role=AgentRole.CHIEF_ARCHITECT,
            )
        )

        # Task 4: Backend (depends on 2, 3)
        backend_task = MissionTask(
            mission_id=mission.id,
            title="Backend implementation",
            description=(
                "Implement backend components using the designed architecture and API contracts."
            ),
            dependencies=[tasks[1].id, tasks[2].id],
            estimated_minutes=30,
            assigned_role=AgentRole.BACKEND_ENGINEER,
        )
        tasks.append(backend_task)

        # Task 5: Frontend (depends on 3)
        tasks.append(
            MissionTask(
                mission_id=mission.id,
                title="Frontend implementation",
                description=(
                    "Implement frontend components matching the designed workflow and backend APIs."
                ),
                dependencies=[tasks[2].id],
                estimated_minutes=25,
                assigned_role=AgentRole.FRONTEND_ENGINEER,
            )
        )

        # Task 6: Security review (depends on 4)
        tasks.append(
            MissionTask(
                mission_id=mission.id,
                title="Security audit & review",
                description="Review the implementation for security vulnerabilities, "
                "apply secure coding patterns, and verify access controls.",
                dependencies=[backend_task.id],
                estimated_minutes=15,
                assigned_role=AgentRole.SECURITY_ENGINEER,
            )
        )

        # Task 7: Testing (depends on 4, 5)
        tasks.append(
            MissionTask(
                mission_id=mission.id,
                title="Testing & regression validation",
                description="Write and run unit tests, integration tests, and regression "
                "tests to validate the implementation.",
                dependencies=[tasks[3].id, tasks[4].id],
                estimated_minutes=20,
                assigned_role=AgentRole.TEST_ENGINEER,
            )
        )

        # Task 8: Documentation (depends on 4, 5)
        tasks.append(
            MissionTask(
                mission_id=mission.id,
                title="Documentation & usage guides",
                description="Write documentation, API references, usage guides, "
                "and changelog entries for the completed work.",
                dependencies=[tasks[3].id, tasks[4].id],
                estimated_minutes=15,
                assigned_role=AgentRole.DOCUMENTATION_WRITER,
            )
        )

        # Task 9: Final validation (depends on 6, 7, 8)
        tasks.append(
            MissionTask(
                mission_id=mission.id,
                title="Final validation & quality gates",
                description="Run final validation: verify all tasks complete, tests pass, "
                "no regressions, docs up to date, security checks ok.",
                dependencies=[tasks[5].id, tasks[6].id, tasks[7].id],
                estimated_minutes=10,
                assigned_role=AgentRole.VALIDATOR,
            )
        )

        return tasks

    def _assign_roles(self, tasks: list[MissionTask]) -> None:
        """Assign providers to each task based on the role mapping.

        The assigned_provider field is informational — the actual provider
        selection happens in the Orchestrator's _on_task_planned which
        prefers real providers over mock. Setting it to the role-mapped
        provider name (e.g. 'claude_code', 'hermes') helps the planner
        produce a meaningful plan, but the dispatcher may override it.
        """
        for task in tasks:
            if task.assigned_role:
                # Use the role map value (e.g. 'claude_code') or empty string
                # — never 'mock' (the dispatcher handles fallback)
                task.assigned_provider = self._role_map.get(task.assigned_role, "")
            task.status = TaskStatus.PLANNED
