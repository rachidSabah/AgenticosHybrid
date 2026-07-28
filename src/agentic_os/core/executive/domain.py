"""Executive Intelligence Layer — domain types.

Defines the Goal model and its lifecycle states, priorities, and
dependencies. Goals are the highest-level abstraction in the
autonomous OS: a Goal creates a Mission (via the existing
MissionPlanner), which decomposes into Tasks, which are executed
by discovered runtimes.

All types are additive — they do not replace any existing domain
model. Goals reference Missions by ID but do not duplicate them.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

# ── Enums ────────────────────────────────────────────────────────────────


class GoalStatus(StrEnum):
    """Lifecycle states for an executive goal."""

    DRAFT = "draft"
    PENDING = "pending"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    MERGED = "merged"
    SPLIT = "split"
    ARCHIVED = "archived"


class GoalPriority(StrEnum):
    """Priority levels for goal scheduling."""

    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"
    BACKGROUND = "background"

    @property
    def weight(self) -> int:
        """Numeric weight for priority comparison (higher = more urgent)."""
        return {
            GoalPriority.CRITICAL: 100,
            GoalPriority.HIGH: 75,
            GoalPriority.NORMAL: 50,
            GoalPriority.LOW: 25,
            GoalPriority.BACKGROUND: 10,
        }[self]


# ── Data models ─────────────────────────────────────────────────────────


def _new_id() -> str:
    return uuid4().hex[:12]


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class Goal:
    """A high-level executive objective.

    A Goal describes WHAT the system should achieve (natural language).
    The ExecutiveController creates a Mission from the Goal (via the
    existing MissionPlanner), which decomposes it into Tasks.

    Attributes:
        id: Unique identifier (12-char hex).
        title: Short human-readable title.
        description: Full natural-language description of the objective.
        priority: Scheduling priority.
        status: Current lifecycle state.
        mission_id: ID of the Mission created from this Goal (empty until planned).
        dependencies: IDs of other Goals that must complete before this one.
        tags: Free-form labels for categorisation.
        created_at: ISO timestamp of creation.
        updated_at: ISO timestamp of last update.
        completed_at: ISO timestamp of completion (empty if not completed).
        reflection: Post-completion analysis (empty until reflected).
        metadata: Arbitrary key-value pairs.
    """

    __slots__ = (
        "id",
        "title",
        "description",
        "priority",
        "status",
        "mission_id",
        "dependencies",
        "tags",
        "created_at",
        "updated_at",
        "completed_at",
        "reflection",
        "metadata",
    )

    def __init__(
        self,
        title: str = "",
        description: str = "",
        priority: GoalPriority = GoalPriority.NORMAL,
        goal_id: str = "",
        dependencies: list[str] | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.id: str = goal_id or _new_id()
        self.title: str = title
        self.description: str = description
        self.priority: GoalPriority = priority
        self.status: GoalStatus = GoalStatus.DRAFT
        self.mission_id: str = ""
        self.dependencies: list[str] = dependencies or []
        self.tags: list[str] = tags or []
        self.created_at: str = _now_iso()
        self.updated_at: str = self.created_at
        self.completed_at: str = ""
        self.reflection: str = ""
        self.metadata: dict[str, Any] = metadata or {}

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "priority": self.priority.value,
            "status": self.status.value,
            "mission_id": self.mission_id,
            "dependencies": list(self.dependencies),
            "tags": list(self.tags),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
            "reflection": self.reflection,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Goal:
        """Deserialize from a dict."""
        g = cls(
            title=data.get("title", ""),
            description=data.get("description", ""),
            priority=GoalPriority(data.get("priority", "normal")),
            goal_id=data.get("id", ""),
            dependencies=data.get("dependencies", []),
            tags=data.get("tags", []),
            metadata=data.get("metadata", {}),
        )
        g.status = GoalStatus(data.get("status", "draft"))
        g.mission_id = data.get("mission_id", "")
        g.created_at = data.get("created_at", g.created_at)
        g.updated_at = data.get("updated_at", g.updated_at)
        g.completed_at = data.get("completed_at", "")
        g.reflection = data.get("reflection", "")
        return g


class GoalDependency:
    """A dependency relationship between two goals.

    The dependent goal cannot start until the prerequisite goal
    reaches a terminal state (completed, failed, or cancelled).
    """

    __slots__ = ("goal_id", "prerequisite_id", "satisfied")

    def __init__(self, goal_id: str, prerequisite_id: str) -> None:
        self.goal_id: str = goal_id
        self.prerequisite_id: str = prerequisite_id
        self.satisfied: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal_id": self.goal_id,
            "prerequisite_id": self.prerequisite_id,
            "satisfied": self.satisfied,
        }


# ── Reflection model ────────────────────────────────────────────────────


class Reflection:
    """Post-mission analysis produced by the ReflectionEngine.

    Stored in ExecutiveMemory under the ``reflection`` scope so the
    Learning engine can use it for future routing decisions.
    """

    __slots__ = (
        "id",
        "goal_id",
        "mission_id",
        "goal_achieved",
        "retries_needed",
        "best_runtime",
        "failed_runtimes",
        "routing_could_improve",
        "summary",
        "created_at",
        "success_factors",
        "failures",
        "improvements",
        "routing_issues",
        "capability_gaps",
        "recommended_actions",
        "estimated_future_success",
    )

    def __init__(
        self,
        goal_id: str = "",
        mission_id: str = "",
        goal_achieved: bool = False,
        retries_needed: int = 0,
        best_runtime: str = "",
        failed_runtimes: list[str] | None = None,
        routing_could_improve: bool = False,
        summary: str = "",
        reflection_id: str = "",
        success_factors: list[str] | None = None,
        failures: list[str] | None = None,
        improvements: list[str] | None = None,
        routing_issues: list[str] | None = None,
        capability_gaps: list[str] | None = None,
        recommended_actions: list[str] | None = None,
        estimated_future_success: float = 0.0,
    ) -> None:
        self.id: str = reflection_id or _new_id()
        self.goal_id: str = goal_id
        self.mission_id: str = mission_id
        self.goal_achieved: bool = goal_achieved
        self.retries_needed: int = retries_needed
        self.best_runtime: str = best_runtime
        self.failed_runtimes: list[str] = failed_runtimes or []
        self.routing_could_improve: bool = routing_could_improve
        self.summary: str = summary
        self.created_at: str = _now_iso()
        self.success_factors: list[str] = success_factors or []
        self.failures: list[str] = failures or []
        self.improvements: list[str] = improvements or []
        self.routing_issues: list[str] = routing_issues or []
        self.capability_gaps: list[str] = capability_gaps or []
        self.recommended_actions: list[str] = recommended_actions or []
        self.estimated_future_success: float = estimated_future_success

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "goal_id": self.goal_id,
            "mission_id": self.mission_id,
            "goal_achieved": self.goal_achieved,
            "retries_needed": self.retries_needed,
            "best_runtime": self.best_runtime,
            "failed_runtimes": list(self.failed_runtimes),
            "routing_could_improve": self.routing_could_improve,
            "summary": self.summary,
            "created_at": self.created_at,
            "success_factors": list(self.success_factors),
            "failures": list(self.failures),
            "improvements": list(self.improvements),
            "routing_issues": list(self.routing_issues),
            "capability_gaps": list(self.capability_gaps),
            "recommended_actions": list(self.recommended_actions),
            "estimated_future_success": self.estimated_future_success,
        }


# ── Decision record ─────────────────────────────────────────────────────


class Decision:
    """A routing/allocation decision made by the DecisionEngine.

    Stored for auditability and for the Learning engine to improve
    future routing decisions. Includes a risk score (0.0=safe,
    1.0=dangerous) and human-readable reasoning.
    """

    __slots__ = (
        "id",
        "goal_id",
        "task_id",
        "selected_runtime",
        "alternatives",
        "confidence",
        "risk",
        "risk_factors",
        "reasoning",
        "factors",
        "created_at",
    )

    def __init__(
        self,
        goal_id: str = "",
        task_id: str = "",
        selected_runtime: str = "",
        alternatives: list[str] | None = None,
        confidence: float = 0.0,
        risk: float = 0.0,
        risk_factors: dict[str, float] | None = None,
        reasoning: str = "",
        factors: dict[str, Any] | None = None,
        decision_id: str = "",
    ) -> None:
        self.id: str = decision_id or _new_id()
        self.goal_id: str = goal_id
        self.task_id: str = task_id
        self.selected_runtime: str = selected_runtime
        self.alternatives: list[str] = alternatives or []
        self.confidence: float = confidence
        self.risk: float = risk
        self.risk_factors: dict[str, float] = risk_factors or {}
        self.reasoning: str = reasoning
        self.factors: dict[str, Any] = factors or {}
        self.created_at: str = _now_iso()

    @property
    def decision_timestamp(self) -> str:
        """Alias for ``created_at`` — the timestamp the decision was made."""
        return self.created_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "goal_id": self.goal_id,
            "task_id": self.task_id,
            "selected_runtime": self.selected_runtime,
            "alternatives": list(self.alternatives),
            "confidence": self.confidence,
            "risk": self.risk,
            "risk_factors": dict(self.risk_factors),
            "reasoning": self.reasoning,
            "factors": dict(self.factors),
            "decision_timestamp": self.created_at,
            "created_at": self.created_at,
        }


# ── Goal Result ──────────────────────────────────────────────────────


class GoalResult:
    """The outcome of a completed or failed goal.

    Captures whether the goal was achieved, the final state, timing,
    cost, runtimes used, and a reference to the Reflection that
    analyzed it. Supports serialization and deserialization.
    """

    __slots__ = (
        "goal_id",
        "mission_id",
        "achieved",
        "completion_status",
        "start_time",
        "end_time",
        "duration",
        "execution_cost",
        "runtime_used",
        "alternative_runtimes",
        "failure_reason",
        "reflection_summary",
        "metrics",
        "created_at",
    )

    def __init__(
        self,
        goal_id: str = "",
        mission_id: str = "",
        achieved: bool = False,
        completion_status: str = "",
        start_time: str = "",
        end_time: str = "",
        duration: float = 0.0,
        execution_cost: float = 0.0,
        runtime_used: str = "",
        alternative_runtimes: list[str] | None = None,
        failure_reason: str = "",
        reflection_summary: str = "",
        metrics: dict[str, Any] | None = None,
    ) -> None:
        self.goal_id: str = goal_id
        self.mission_id: str = mission_id
        self.achieved: bool = achieved
        self.completion_status: str = completion_status
        self.start_time: str = start_time
        self.end_time: str = end_time
        self.duration: float = duration
        self.execution_cost: float = execution_cost
        self.runtime_used: str = runtime_used
        self.alternative_runtimes: list[str] = alternative_runtimes or []
        self.failure_reason: str = failure_reason
        self.reflection_summary: str = reflection_summary
        self.metrics: dict[str, Any] = metrics or {}
        self.created_at: str = _now_iso()

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal_id": self.goal_id,
            "mission_id": self.mission_id,
            "achieved": self.achieved,
            "completion_status": self.completion_status,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration": self.duration,
            "execution_cost": self.execution_cost,
            "runtime_used": self.runtime_used,
            "alternative_runtimes": list(self.alternative_runtimes),
            "failure_reason": self.failure_reason,
            "reflection_summary": self.reflection_summary,
            "metrics": dict(self.metrics),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GoalResult:
        gr = cls(
            goal_id=data.get("goal_id", ""),
            mission_id=data.get("mission_id", ""),
            achieved=data.get("achieved", False),
            completion_status=data.get("completion_status", ""),
            start_time=data.get("start_time", ""),
            end_time=data.get("end_time", ""),
            duration=data.get("duration", 0.0),
            execution_cost=data.get("execution_cost", 0.0),
            runtime_used=data.get("runtime_used", ""),
            alternative_runtimes=data.get("alternative_runtimes", []),
            failure_reason=data.get("failure_reason", ""),
            reflection_summary=data.get("reflection_summary", ""),
            metrics=data.get("metrics", {}),
        )
        gr.created_at = data.get("created_at", gr.created_at)
        return gr
