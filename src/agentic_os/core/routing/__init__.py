"""OmniRoute domain types — mission-level routing decisions.

Extends the per-task RoutingDecision with mission-aware route planning.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4


def _utcnow() -> datetime:
    return datetime.now(UTC)


class RoutingStrategy(StrEnum):
    """Strategy for routing mission tasks to agents."""

    FASTEST = "fastest"
    CHEAPEST = "cheapest"
    BEST_CAPABILITY = "best_capability"
    BALANCED = "balanced"
    RELIABILITY_FIRST = "reliability_first"
    LATENCY_FIRST = "latency_first"
    CUSTOM = "custom"


class RouteDecisionStatus(StrEnum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    FAILED_OVER = "failed_over"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class AgentCapabilityScore:
    """Score of an agent's suitability for a specific capability."""

    agent_id: str
    agent_name: str
    provider: str
    capability: str
    score: float  # 0.0 - 1.0
    estimated_cost: float  # per-1k tokens
    estimated_latency_ms: float
    reliability: float  # 0.0 - 1.0
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TaskRouteAssignment:
    """An assignment of a mission task to a specific agent."""

    task_id: str
    task_title: str
    assigned_agent_id: str
    assigned_agent_name: str
    provider: str
    strategy_used: RoutingStrategy
    composite_score: float  # overall suitability 0.0-1.0
    cost_score: float
    speed_score: float
    capability_score: float
    reliability_score: float
    estimated_cost: float
    estimated_duration_ms: float
    status: RouteDecisionStatus = RouteDecisionStatus.PENDING
    fallback_agent_id: str | None = None
    fallback_provider: str | None = None
    reasoning: str = ""
    created_at: datetime = field(default_factory=_utcnow)


@dataclass(frozen=True, slots=True)
class MissionRoutePlan:
    """Complete route plan for an entire mission."""

    id: str = field(default_factory=lambda: uuid4().hex)
    mission_id: str = ""
    strategy: RoutingStrategy = RoutingStrategy.BALANCED
    assignments: tuple[TaskRouteAssignment, ...] = field(default_factory=tuple)
    total_estimated_cost: float = 0.0
    total_estimated_duration_ms: float = 0.0
    average_composite_score: float = 0.0
    provider_usage: dict[str, int] = field(default_factory=dict)  # provider -> task count
    created_at: datetime = field(default_factory=_utcnow)

    @property
    def task_count(self) -> int:
        return len(self.assignments)

    @property
    def unique_agents(self) -> list[str]:
        return list({a.assigned_agent_id for a in self.assignments})

    @property
    def unique_providers(self) -> list[str]:
        return list({a.provider for a in self.assignments})


@dataclass(frozen=True, slots=True)
class OmniRouteConfig:
    """Configuration for the OmniRoute decision engine."""

    default_strategy: RoutingStrategy = RoutingStrategy.BALANCED
    cost_weight: float = 0.25
    speed_weight: float = 0.25
    capability_weight: float = 0.30
    reliability_weight: float = 0.20
    max_fallback_depth: int = 2
    enable_parallel_routing: bool = True
    min_confidence_for_auto_route: float = 0.6
    cost_tiers: dict[str, float] = field(
        default_factory=lambda: {
            "low": 0.0,
            "medium": 5.0,
            "high": 20.0,
        }
    )
    metadata: dict[str, Any] = field(default_factory=dict)
