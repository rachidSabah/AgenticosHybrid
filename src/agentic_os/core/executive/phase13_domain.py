"""Executive Decision & Mission Orchestration — Phase 13 domain types.

Extends the existing executive domain with:
  - ExecutivePolicy (throughput, quality, latency, cost, resilience, balanced, custom)
  - ExecutiveDecision (with evidence, predicted impact, actual outcome)
  - ResourceAllocation (brain/provider/runtime/memory/context allocations)
  - ExecutiveWorldState (live snapshot of the entire platform)
  - MissionSupervisionRecord (stalled/overloaded/blocked detection)

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


# ── Executive Policy ───────────────────────────────────────────────────


class ExecutivePolicyType(StrEnum):
    THROUGHPUT = "throughput"
    QUALITY = "quality"
    LATENCY = "latency"
    COST = "cost"
    RESILIENCE = "resilience"
    BALANCED = "balanced"
    CUSTOM = "custom"


class ExecutivePolicy:
    """Runtime-switchable executive policy."""

    __slots__ = ("type", "params", "updated_at")

    def __init__(
        self,
        policy_type: ExecutivePolicyType = ExecutivePolicyType.BALANCED,
        params: dict[str, Any] | None = None,
    ) -> None:
        self.type: ExecutivePolicyType = policy_type
        self.params: dict[str, Any] = params or {}
        self.updated_at: str = _now_iso()

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            "params": dict(self.params),
            "updated_at": self.updated_at,
        }


# ── Executive Decision ────────────────────────────────────────────────


class ExecutiveDecision:
    """A decision made by the ExecutiveController.

    Every decision includes evidence, predicted impact, and is
    tracked for actual outcome (filled in after execution).
    """

    __slots__ = (
        "id",
        "timestamp",
        "decision_type",
        "reason",
        "evidence",
        "confidence",
        "predicted_impact",
        "actual_outcome",
        "target_id",
        "metadata",
    )

    def __init__(
        self,
        decision_type: str = "",
        reason: str = "",
        evidence: dict[str, Any] | None = None,
        confidence: float = 0.0,
        predicted_impact: str = "",
        target_id: str = "",
        metadata: dict[str, Any] | None = None,
        decision_id: str = "",
    ) -> None:
        self.id: str = decision_id or _new_id()
        self.timestamp: str = _now_iso()
        self.decision_type: str = decision_type
        self.reason: str = reason
        self.evidence: dict[str, Any] = evidence or {}
        self.confidence: float = confidence
        self.predicted_impact: str = predicted_impact
        self.actual_outcome: str = ""  # filled after execution
        self.target_id: str = target_id
        self.metadata: dict[str, Any] = metadata or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "decision_type": self.decision_type,
            "reason": self.reason,
            "evidence": dict(self.evidence),
            "confidence": self.confidence,
            "predicted_impact": self.predicted_impact,
            "actual_outcome": self.actual_outcome,
            "target_id": self.target_id,
            "metadata": dict(self.metadata),
        }


# ── Resource Allocation ────────────────────────────────────────────────


class ResourceAllocation:
    """An allocation of resources to a mission/goal."""

    __slots__ = (
        "id",
        "mission_id",
        "brain_ids",
        "provider_ids",
        "memory_mb",
        "context_tokens",
        "priority",
        "allocated_at",
        "released_at",
    )

    def __init__(
        self,
        mission_id: str = "",
        brain_ids: list[str] | None = None,
        provider_ids: list[str] | None = None,
        memory_mb: float = 0.0,
        context_tokens: int = 0,
        priority: str = "normal",
        allocation_id: str = "",
    ) -> None:
        self.id: str = allocation_id or _new_id()
        self.mission_id: str = mission_id
        self.brain_ids: list[str] = brain_ids or []
        self.provider_ids: list[str] = provider_ids or []
        self.memory_mb: float = memory_mb
        self.context_tokens: int = context_tokens
        self.priority: str = priority
        self.allocated_at: str = _now_iso()
        self.released_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "mission_id": self.mission_id,
            "brain_ids": list(self.brain_ids),
            "provider_ids": list(self.provider_ids),
            "memory_mb": self.memory_mb,
            "context_tokens": self.context_tokens,
            "priority": self.priority,
            "allocated_at": self.allocated_at,
            "released_at": self.released_at,
        }


# ── Mission Supervision Record ─────────────────────────────────────────


class MissionSupervisionRecord:
    """Result of monitoring a mission for health issues."""

    __slots__ = (
        "mission_id",
        "is_stalled",
        "is_overloaded",
        "is_blocked",
        "has_cascading_failures",
        "idle_resources",
        "issues",
        "checked_at",
    )

    def __init__(
        self,
        mission_id: str = "",
        is_stalled: bool = False,
        is_overloaded: bool = False,
        is_blocked: bool = False,
        has_cascading_failures: bool = False,
        idle_resources: list[str] | None = None,
        issues: list[str] | None = None,
    ) -> None:
        self.mission_id: str = mission_id
        self.is_stalled: bool = is_stalled
        self.is_overloaded: bool = is_overloaded
        self.is_blocked: bool = is_blocked
        self.has_cascading_failures: bool = has_cascading_failures
        self.idle_resources: list[str] = idle_resources or []
        self.issues: list[str] = issues or []
        self.checked_at: str = _now_iso()

    def to_dict(self) -> dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "is_stalled": self.is_stalled,
            "is_overloaded": self.is_overloaded,
            "is_blocked": self.is_blocked,
            "has_cascading_failures": self.has_cascading_failures,
            "idle_resources": list(self.idle_resources),
            "issues": list(self.issues),
            "checked_at": self.checked_at,
        }


# ── Executive World State ─────────────────────────────────────────────


class ExecutiveWorldState:
    """Live snapshot of the entire platform from the executive perspective.

    Updated from EventBus events — no polling.
    """

    __slots__ = (
        "runtimes",
        "active_brains",
        "active_providers",
        "missions",
        "objectives",
        "swarm_availability",
        "execution_queue_size",
        "resource_utilization",
        "memory_usage_mb",
        "prediction_history_count",
        "evaluation_history_count",
        "last_updated",
    )

    def __init__(self) -> None:
        self.runtimes: dict[str, dict[str, Any]] = {}
        self.active_brains: list[str] = []
        self.active_providers: list[str] = []
        self.missions: dict[str, dict[str, Any]] = {}
        self.objectives: list[str] = []
        self.swarm_availability: float = 0.0
        self.execution_queue_size: int = 0
        self.resource_utilization: float = 0.0
        self.memory_usage_mb: float = 0.0
        self.prediction_history_count: int = 0
        self.evaluation_history_count: int = 0
        self.last_updated: str = _now_iso()

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtimes": len(self.runtimes),
            "active_brains": list(self.active_brains),
            "active_providers": list(self.active_providers),
            "missions": len(self.missions),
            "objectives": list(self.objectives),
            "swarm_availability": self.swarm_availability,
            "execution_queue_size": self.execution_queue_size,
            "resource_utilization": self.resource_utilization,
            "memory_usage_mb": self.memory_usage_mb,
            "prediction_history_count": self.prediction_history_count,
            "evaluation_history_count": self.evaluation_history_count,
            "last_updated": self.last_updated,
        }
