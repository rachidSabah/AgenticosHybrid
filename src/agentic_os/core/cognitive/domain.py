"""Cognitive Intelligence Layer — domain types.

Defines LongTermObjective, Prediction, ExperienceRecord, EvaluationScore,
ImprovementProposal, WorldModelSnapshot, and KnowledgeGraphNode/Edge.
All additive — no existing types replaced.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4


def _new_id() -> str:
    return uuid4().hex[:12]


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


# ── Enums ────────────────────────────────────────────────────────────────


class ObjectiveStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ARCHIVED = "archived"


class ObjectivePriority(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"
    BACKGROUND = "background"


# ── Long-Term Objective ─────────────────────────────────────────────────


class LongTermObjective:
    __slots__ = (
        "id",
        "title",
        "description",
        "priority",
        "status",
        "owner",
        "success_metrics",
        "dependencies",
        "deadline",
        "estimated_value",
        "estimated_cost",
        "risk",
        "created_at",
        "updated_at",
        "linked_goals",
        "linked_missions",
        "reflection_history",
    )

    def __init__(
        self,
        title: str = "",
        description: str = "",
        priority: ObjectivePriority = ObjectivePriority.NORMAL,
        objective_id: str = "",
        owner: str = "",
        success_metrics: list[str] | None = None,
        dependencies: list[str] | None = None,
        deadline: str = "",
        estimated_value: float = 0.0,
        estimated_cost: float = 0.0,
        risk: float = 0.0,
        linked_goals: list[str] | None = None,
        linked_missions: list[str] | None = None,
    ) -> None:
        self.id: str = objective_id or _new_id()
        self.title: str = title
        self.description: str = description
        self.priority: ObjectivePriority = priority
        self.status: ObjectiveStatus = ObjectiveStatus.DRAFT
        self.owner: str = owner
        self.success_metrics: list[str] = success_metrics or []
        self.dependencies: list[str] = dependencies or []
        self.deadline: str = deadline
        self.estimated_value: float = estimated_value
        self.estimated_cost: float = estimated_cost
        self.risk: float = risk
        self.created_at: str = _now_iso()
        self.updated_at: str = self.created_at
        self.linked_goals: list[str] = linked_goals or []
        self.linked_missions: list[str] = linked_missions or []
        self.reflection_history: list[str] = []

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "priority": self.priority.value,
            "status": self.status.value,
            "owner": self.owner,
            "success_metrics": list(self.success_metrics),
            "dependencies": list(self.dependencies),
            "deadline": self.deadline,
            "estimated_value": self.estimated_value,
            "estimated_cost": self.estimated_cost,
            "risk": self.risk,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "linked_goals": list(self.linked_goals),
            "linked_missions": list(self.linked_missions),
            "reflection_history": list(self.reflection_history),
        }


# ── Prediction ──────────────────────────────────────────────────────────


class Prediction:
    __slots__ = (
        "id",
        "goal_id",
        "probability_of_success",
        "expected_runtime_seconds",
        "expected_cost",
        "expected_failures",
        "expected_retries",
        "confidence",
        "factors",
        "created_at",
    )

    def __init__(
        self,
        goal_id: str = "",
        probability_of_success: float = 0.0,
        expected_runtime_seconds: float = 0.0,
        expected_cost: float = 0.0,
        expected_failures: int = 0,
        expected_retries: int = 0,
        confidence: float = 0.0,
        factors: dict[str, Any] | None = None,
        prediction_id: str = "",
    ) -> None:
        self.id: str = prediction_id or _new_id()
        self.goal_id: str = goal_id
        self.probability_of_success: float = probability_of_success
        self.expected_runtime_seconds: float = expected_runtime_seconds
        self.expected_cost: float = expected_cost
        self.expected_failures: int = expected_failures
        self.expected_retries: int = expected_retries
        self.confidence: float = confidence
        self.factors: dict[str, Any] = factors or {}
        self.created_at: str = _now_iso()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "goal_id": self.goal_id,
            "probability_of_success": round(self.probability_of_success, 3),
            "expected_runtime_seconds": self.expected_runtime_seconds,
            "expected_cost": self.expected_cost,
            "expected_failures": self.expected_failures,
            "expected_retries": self.expected_retries,
            "confidence": round(self.confidence, 3),
            "factors": dict(self.factors),
            "created_at": self.created_at,
        }


# ── Experience Record ──────────────────────────────────────────────────


class ExperienceRecord:
    __slots__ = (
        "id",
        "mission_id",
        "goal_id",
        "patterns",
        "common_failures",
        "optimization_opportunities",
        "routing_improvements",
        "capability_bottlenecks",
        "summary",
        "created_at",
    )

    def __init__(
        self,
        mission_id: str = "",
        goal_id: str = "",
        patterns: list[str] | None = None,
        common_failures: list[str] | None = None,
        optimization_opportunities: list[str] | None = None,
        routing_improvements: list[str] | None = None,
        capability_bottlenecks: list[str] | None = None,
        summary: str = "",
        record_id: str = "",
    ) -> None:
        self.id: str = record_id or _new_id()
        self.mission_id: str = mission_id
        self.goal_id: str = goal_id
        self.patterns: list[str] = patterns or []
        self.common_failures: list[str] = common_failures or []
        self.optimization_opportunities: list[str] = optimization_opportunities or []
        self.routing_improvements: list[str] = routing_improvements or []
        self.capability_bottlenecks: list[str] = capability_bottlenecks or []
        self.summary: str = summary
        self.created_at: str = _now_iso()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "mission_id": self.mission_id,
            "goal_id": self.goal_id,
            "patterns": list(self.patterns),
            "common_failures": list(self.common_failures),
            "optimization_opportunities": list(self.optimization_opportunities),
            "routing_improvements": list(self.routing_improvements),
            "capability_bottlenecks": list(self.capability_bottlenecks),
            "summary": self.summary,
            "created_at": self.created_at,
        }


# ── Evaluation Score ───────────────────────────────────────────────────


class EvaluationScore:
    __slots__ = (
        "id",
        "decision_quality",
        "goal_quality",
        "reflection_quality",
        "routing_quality",
        "runtime_utilization",
        "mission_efficiency",
        "memory_quality",
        "overall_executive_score",
        "overall_system_score",
        "factors",
        "created_at",
    )

    def __init__(
        self,
        decision_quality: float = 0.0,
        goal_quality: float = 0.0,
        reflection_quality: float = 0.0,
        routing_quality: float = 0.0,
        runtime_utilization: float = 0.0,
        mission_efficiency: float = 0.0,
        memory_quality: float = 0.0,
        overall_executive_score: float = 0.0,
        overall_system_score: float = 0.0,
        factors: dict[str, Any] | None = None,
        eval_id: str = "",
    ) -> None:
        self.id: str = eval_id or _new_id()
        self.decision_quality: float = decision_quality
        self.goal_quality: float = goal_quality
        self.reflection_quality: float = reflection_quality
        self.routing_quality: float = routing_quality
        self.runtime_utilization: float = runtime_utilization
        self.mission_efficiency: float = mission_efficiency
        self.memory_quality: float = memory_quality
        self.overall_executive_score: float = overall_executive_score
        self.overall_system_score: float = overall_system_score
        self.factors: dict[str, Any] = factors or {}
        self.created_at: str = _now_iso()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "decision_quality": round(self.decision_quality, 3),
            "goal_quality": round(self.goal_quality, 3),
            "reflection_quality": round(self.reflection_quality, 3),
            "routing_quality": round(self.routing_quality, 3),
            "runtime_utilization": round(self.runtime_utilization, 3),
            "mission_efficiency": round(self.mission_efficiency, 3),
            "memory_quality": round(self.memory_quality, 3),
            "overall_executive_score": round(self.overall_executive_score, 3),
            "overall_system_score": round(self.overall_system_score, 3),
            "factors": dict(self.factors),
            "created_at": self.created_at,
        }


# ── Improvement Proposal ──────────────────────────────────────────────


class ImprovementProposal:
    __slots__ = (
        "id",
        "title",
        "description",
        "proposal_type",
        "priority",
        "estimated_impact",
        "estimated_effort",
        "rationale",
        "linked_goal_id",
        "status",
        "created_at",
    )

    def __init__(
        self,
        title: str = "",
        description: str = "",
        proposal_type: str = "",
        priority: str = "normal",
        estimated_impact: float = 0.0,
        estimated_effort: float = 0.0,
        rationale: str = "",
        linked_goal_id: str = "",
        proposal_id: str = "",
    ) -> None:
        self.id: str = proposal_id or _new_id()
        self.title: str = title
        self.description: str = description
        self.proposal_type: str = proposal_type
        self.priority: str = priority
        self.estimated_impact: float = estimated_impact
        self.estimated_effort: float = estimated_effort
        self.rationale: str = rationale
        self.linked_goal_id: str = linked_goal_id
        self.status: str = "proposed"
        self.created_at: str = _now_iso()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "proposal_type": self.proposal_type,
            "priority": self.priority,
            "estimated_impact": self.estimated_impact,
            "estimated_effort": self.estimated_effort,
            "rationale": self.rationale,
            "linked_goal_id": self.linked_goal_id,
            "status": self.status,
            "created_at": self.created_at,
        }
