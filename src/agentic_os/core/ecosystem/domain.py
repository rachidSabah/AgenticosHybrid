"""Phase 15 — Ecosystem domain models.

Pure data structures for the autonomous agent ecosystem:
  - GraphNode / GraphEdge (capability + collaboration graphs)
  - EcosystemStats (live statistics)
  - EvolutionRecommendation (self-evolution output)
  - TaskBid / TaskAssignment (marketplace)
  - CollaborationLink (trust + confidence)

All additive — does not modify any existing domain model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _new_id(prefix: str = "") -> str:
    return f"{prefix}{uuid4().hex[:12]}" if prefix else uuid4().hex[:12]


# ── Capability Graph ──────────────────────────────────────────────────


class NodeType(StrEnum):
    BRAIN = "brain"
    CAPABILITY = "capability"
    MISSION = "mission"
    GOAL = "goal"
    SWARM = "swarm"


class EdgeType(StrEnum):
    PROVIDES = "provides"
    DEPENDS_ON = "depends_on"
    LEARNED = "learned"
    SHARES = "shares"
    COLLABORATES_WITH = "collaborates_with"
    EXECUTED = "executed"


@dataclass
class GraphNode:
    """A node in the capability / collaboration graph."""

    id: str
    type: NodeType
    label: str = ""
    properties: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "label": self.label or self.id,
            "properties": dict(self.properties),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class GraphEdge:
    """A directed edge in the capability / collaboration graph."""

    source: str
    target: str
    type: EdgeType
    weight: float = 1.0
    properties: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_now_iso)

    @property
    def edge_id(self) -> str:
        return f"{self.source}->{self.target}:{self.type.value}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "type": self.type.value,
            "weight": self.weight,
            "properties": dict(self.properties),
            "created_at": self.created_at,
        }


# ── Ecosystem Statistics ──────────────────────────────────────────────


@dataclass
class EcosystemStats:
    """Live ecosystem statistics — derived entirely from BrainRegistry."""

    total_runtimes: int = 0
    healthy_runtimes: int = 0
    degraded_runtimes: int = 0
    unhealthy_runtimes: int = 0
    total_capabilities: int = 0
    unique_capabilities: int = 0
    active_missions: int = 0
    completed_missions: int = 0
    failed_missions: int = 0
    active_swarms: int = 0
    total_collaborations: int = 0
    successful_collaborations: int = 0
    failed_collaborations: int = 0
    average_health: float = 0.0
    average_latency: float = 0.0
    average_confidence: float = 0.0
    evolution_recommendations: int = 0
    last_updated: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_runtimes": self.total_runtimes,
            "healthy_runtimes": self.healthy_runtimes,
            "degraded_runtimes": self.degraded_runtimes,
            "unhealthy_runtimes": self.unhealthy_runtimes,
            "total_capabilities": self.total_capabilities,
            "unique_capabilities": self.unique_capabilities,
            "active_missions": self.active_missions,
            "completed_missions": self.completed_missions,
            "failed_missions": self.failed_missions,
            "active_swarms": self.active_swarms,
            "total_collaborations": self.total_collaborations,
            "successful_collaborations": self.successful_collaborations,
            "failed_collaborations": self.failed_collaborations,
            "average_health": round(self.average_health, 2),
            "average_latency": round(self.average_latency, 2),
            "average_confidence": round(self.average_confidence, 3),
            "evolution_recommendations": self.evolution_recommendations,
            "last_updated": self.last_updated,
        }


# ── Ecosystem Health ──────────────────────────────────────────────────


class EcosystemHealthLevel(StrEnum):
    OPTIMAL = "optimal"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    OFFLINE = "offline"


@dataclass
class EcosystemHealth:
    """Live health snapshot of the entire ecosystem."""

    level: EcosystemHealthLevel = EcosystemHealthLevel.OFFLINE
    health_score: float = 0.0
    availability_score: float = 0.0
    performance_score: float = 0.0
    collaboration_score: float = 0.0
    evolution_score: float = 0.0
    issues: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    last_updated: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level.value,
            "health_score": round(self.health_score, 3),
            "availability_score": round(self.availability_score, 3),
            "performance_score": round(self.performance_score, 3),
            "collaboration_score": round(self.collaboration_score, 3),
            "evolution_score": round(self.evolution_score, 3),
            "issues": list(self.issues),
            "recommendations": list(self.recommendations),
            "last_updated": self.last_updated,
        }


# ── Evolution Recommendation ──────────────────────────────────────────


class RecommendationType(StrEnum):
    CAPABILITY = "recommended_capability"
    ROUTING = "recommended_routing"
    COLLABORATION = "recommended_collaboration"
    OPTIMIZATION = "recommended_optimization"


@dataclass
class EvolutionRecommendation:
    """A self-evolution recommendation produced by the EvolutionEngine."""

    id: str = field(default_factory=lambda: _new_id("evo-"))
    type: RecommendationType = RecommendationType.OPTIMIZATION
    title: str = ""
    rationale: str = ""
    target_id: str = ""
    target_type: str = ""
    priority: float = 0.5
    confidence: float = 0.5
    expected_impact: float = 0.0
    evidence: dict[str, Any] = field(default_factory=dict)
    action: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "title": self.title,
            "rationale": self.rationale,
            "target_id": self.target_id,
            "target_type": self.target_type,
            "priority": round(self.priority, 3),
            "confidence": round(self.confidence, 3),
            "expected_impact": round(self.expected_impact, 3),
            "evidence": dict(self.evidence),
            "action": dict(self.action),
            "created_at": self.created_at,
        }


# ── Collaboration Link ────────────────────────────────────────────────


@dataclass
class CollaborationLink:
    """A directed trust/confidence link between two runtimes.

    Updated after every mission. Higher trust → selected preferentially
    in future team-formation / task-marketplace decisions.
    """

    source: str
    target: str
    successful: int = 0
    failed: int = 0
    confidence: float = 0.5
    trust_score: float = 0.5
    last_collaboration: str = ""
    last_outcome: str = ""
    history: list[dict[str, Any]] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.successful + self.failed

    @property
    def success_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return self.successful / self.total

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "successful": self.successful,
            "failed": self.failed,
            "total": self.total,
            "success_rate": round(self.success_rate, 3),
            "confidence": round(self.confidence, 3),
            "trust_score": round(self.trust_score, 3),
            "last_collaboration": self.last_collaboration,
            "last_outcome": self.last_outcome,
            "history": list(self.history[-20:]),
        }


# ── Task Marketplace ──────────────────────────────────────────────────


class TaskBidStrategy(StrEnum):
    CAPABILITY_MATCH = "capability_match"
    LATENCY_OPTIMIZED = "latency_optimized"
    HEALTH_OPTIMIZED = "health_optimized"
    TRUST_OPTIMIZED = "trust_optimized"
    BALANCED = "balanced"


@dataclass
class TaskBid:
    """A runtime's bid for a published task."""

    runtime_id: str
    runtime_name: str = ""
    capabilities: list[str] = field(default_factory=list)
    health: float = 0.0
    latency: float = 0.0
    availability: float = 0.0
    historical_success: float = 0.0
    trust_score: float = 0.0
    confidence: float = 0.0
    bid_score: float = 0.0
    submitted_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_id": self.runtime_id,
            "runtime_name": self.runtime_name,
            "capabilities": list(self.capabilities),
            "health": round(self.health, 2),
            "latency": round(self.latency, 2),
            "availability": round(self.availability, 3),
            "historical_success": round(self.historical_success, 3),
            "trust_score": round(self.trust_score, 3),
            "confidence": round(self.confidence, 3),
            "bid_score": round(self.bid_score, 3),
            "submitted_at": self.submitted_at,
        }


@dataclass
class MarketTask:
    """A task published to the global task marketplace."""

    id: str = field(default_factory=lambda: _new_id("task-"))
    title: str = ""
    description: str = ""
    required_capabilities: list[str] = field(default_factory=list)
    priority: float = 0.5
    deadline: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    bids: list[TaskBid] = field(default_factory=list)
    selected_bid: TaskBid | None = None
    status: str = "open"  # open | bidding | awarded | dispatched | completed | failed | cancelled
    published_at: str = field(default_factory=_now_iso)
    awarded_at: str = ""
    completed_at: str = ""
    selection_rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "required_capabilities": list(self.required_capabilities),
            "priority": round(self.priority, 3),
            "deadline": self.deadline,
            "payload": dict(self.payload),
            "bids": [b.to_dict() for b in self.bids],
            "selected_bid": self.selected_bid.to_dict() if self.selected_bid else None,
            "status": self.status,
            "published_at": self.published_at,
            "awarded_at": self.awarded_at,
            "completed_at": self.completed_at,
            "selection_rationale": self.selection_rationale,
        }
