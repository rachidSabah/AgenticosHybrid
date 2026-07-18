"""
Orchestration Domain Models

Domain layer for Phase 4 Milestone 3 — Multi-Agent Orchestration & Swarm Intelligence.
Pure Python, no external dependencies. These models describe agents, swarms, goals,
tasks, voting, consensus, messaging, and telemetry for multi-agent orchestration.

Agents are lightweight wrappers around the M1 ExecutionEngine domain models.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4


def _utcnow() -> datetime:
    return datetime.now(UTC)


# ── Enums ──


class SwarmTopology(StrEnum):
    """Communication topology within a swarm."""

    MESH = "mesh"
    STAR = "star"
    HIERARCHICAL = "hierarchical"
    RING = "ring"


class AgentTaskStatus(StrEnum):
    """Status of a single subtask within an orchestration plan."""

    PENDING = "pending"
    ASSIGNED = "assigned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


class CoordinationPattern(StrEnum):
    """Coordination pattern for executing subtasks across agents."""

    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    FAN_OUT = "fan_out"
    FAN_IN = "fan_in"
    HIERARCHICAL = "hierarchical"
    VOTING = "voting"


class VoteValue(StrEnum):
    """Possible values for a single vote in consensus rounds."""

    YES = "yes"
    NO = "no"
    ABSTAIN = "abstain"


class ConsensusStatus(StrEnum):
    """Status of a consensus round."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    REACHED = "reached"
    FAILED = "failed"
    TIE = "tie"


# ── Domain Models ──


@dataclass(frozen=True, slots=True)
class AgentDescriptor:
    """Wraps an M1 ExecutionEngine as an agent in the orchestration layer.

    This is a read-only view, not a new entity — the underlying engine
    is managed by the M1 RuntimeManager.
    """

    agent_id: str
    name: str
    engine_type: str = "generic"
    capabilities: tuple[str, ...] = field(default_factory=tuple)
    status: str = "unknown"
    health_status: str = "unknown"
    latency_ms: float = 0.0
    is_leader: bool = False
    swarm_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "engine_type": self.engine_type,
            "capabilities": list(self.capabilities),
            "status": self.status,
            "health_status": self.health_status,
            "latency_ms": self.latency_ms,
            "is_leader": self.is_leader,
            "swarm_id": self.swarm_id,
            "metadata": dict(self.metadata),
        }

    def with_leader(self, is_leader: bool = True) -> AgentDescriptor:
        """Return a copy with updated leader status."""
        return AgentDescriptor(
            agent_id=self.agent_id,
            name=self.name,
            engine_type=self.engine_type,
            capabilities=self.capabilities,
            status=self.status,
            health_status=self.health_status,
            latency_ms=self.latency_ms,
            is_leader=is_leader,
            swarm_id=self.swarm_id,
            metadata=self.metadata,
        )

    def with_swarm(self, swarm_id: str | None) -> AgentDescriptor:
        """Return a copy with updated swarm assignment."""
        return AgentDescriptor(
            agent_id=self.agent_id,
            name=self.name,
            engine_type=self.engine_type,
            capabilities=self.capabilities,
            status=self.status,
            health_status=self.health_status,
            latency_ms=self.latency_ms,
            is_leader=self.is_leader,
            swarm_id=swarm_id,
            metadata=self.metadata,
        )


@dataclass(frozen=True, slots=True)
class SwarmSpec:
    """Defines a named team of agents with a topology and strategy."""

    id: str = field(default_factory=lambda: uuid4().hex)
    name: str = ""
    description: str = ""
    topology: SwarmTopology = SwarmTopology.MESH
    agent_ids: tuple[str, ...] = field(default_factory=tuple)
    leader_id: str | None = None
    tags: tuple[str, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "topology": self.topology.value,
            "agent_ids": list(self.agent_ids),
            "leader_id": self.leader_id,
            "tags": list(self.tags),
            "metadata": dict(self.metadata),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    def with_agent(self, agent_id: str) -> SwarmSpec:
        """Return a copy with an agent added."""
        if agent_id in self.agent_ids:
            return self
        new_ids = list(self.agent_ids) + [agent_id]
        return SwarmSpec(
            id=self.id,
            name=self.name,
            description=self.description,
            topology=self.topology,
            agent_ids=tuple(new_ids),
            leader_id=self.leader_id,
            tags=self.tags,
            metadata=self.metadata,
            created_at=self.created_at,
            updated_at=_utcnow(),
        )

    def without_agent(self, agent_id: str) -> SwarmSpec:
        """Return a copy with an agent removed."""
        new_ids = tuple(a for a in self.agent_ids if a != agent_id)
        return SwarmSpec(
            id=self.id,
            name=self.name,
            description=self.description,
            topology=self.topology,
            agent_ids=new_ids,
            leader_id=self.leader_id if self.leader_id != agent_id else None,
            tags=self.tags,
            metadata=self.metadata,
            created_at=self.created_at,
            updated_at=_utcnow(),
        )

    def with_leader(self, leader_id: str | None) -> SwarmSpec:
        """Return a copy with an updated leader."""
        return SwarmSpec(
            id=self.id,
            name=self.name,
            description=self.description,
            topology=self.topology,
            agent_ids=self.agent_ids,
            leader_id=leader_id,
            tags=self.tags,
            metadata=self.metadata,
            created_at=self.created_at,
            updated_at=_utcnow(),
        )

    def with_topology(self, topology: SwarmTopology) -> SwarmSpec:
        """Return a copy with an updated topology."""
        return SwarmSpec(
            id=self.id,
            name=self.name,
            description=self.description,
            topology=topology,
            agent_ids=self.agent_ids,
            leader_id=self.leader_id,
            tags=self.tags,
            metadata=self.metadata,
            created_at=self.created_at,
            updated_at=_utcnow(),
        )


@dataclass(frozen=True, slots=True)
class SwarmState:
    """Runtime state of a swarm — mutable information that changes during execution."""

    swarm_id: str
    active: bool = False
    current_task_id: str | None = None
    leader_id: str | None = None
    agent_states: dict[str, str] = field(default_factory=dict)
    last_activity: datetime = field(default_factory=_utcnow)
    metrics: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "swarm_id": self.swarm_id,
            "active": self.active,
            "current_task_id": self.current_task_id,
            "leader_id": self.leader_id,
            "agent_states": dict(self.agent_states),
            "last_activity": self.last_activity.isoformat(),
            "metrics": dict(self.metrics),
        }

    def with_active(self, active: bool = True) -> SwarmState:
        return SwarmState(
            swarm_id=self.swarm_id,
            active=active,
            current_task_id=self.current_task_id,
            leader_id=self.leader_id,
            agent_states=self.agent_states,
            last_activity=_utcnow(),
            metrics=self.metrics,
        )

    def with_task(self, task_id: str | None) -> SwarmState:
        return SwarmState(
            swarm_id=self.swarm_id,
            active=self.active,
            current_task_id=task_id,
            leader_id=self.leader_id,
            agent_states=self.agent_states,
            last_activity=_utcnow(),
            metrics=self.metrics,
        )

    def with_agent_state(self, agent_id: str, state: str) -> SwarmState:
        new_states = dict(self.agent_states)
        new_states[agent_id] = state
        return SwarmState(
            swarm_id=self.swarm_id,
            active=self.active,
            current_task_id=self.current_task_id,
            leader_id=self.leader_id,
            agent_states=new_states,
            last_activity=_utcnow(),
            metrics=self.metrics,
        )


@dataclass(frozen=True, slots=True)
class OrchestrationGoal:
    """High-level goal to be decomposed into subtasks and assigned to a swarm."""

    id: str = field(default_factory=lambda: uuid4().hex)
    title: str = ""
    description: str = ""
    context: dict[str, Any] = field(default_factory=dict)
    swarm_id: str | None = None
    status: str = "pending"
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "context": dict(self.context),
            "swarm_id": self.swarm_id,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    def with_status(self, status: str) -> OrchestrationGoal:
        return OrchestrationGoal(
            id=self.id,
            title=self.title,
            description=self.description,
            context=self.context,
            swarm_id=self.swarm_id,
            status=status,
            created_at=self.created_at,
            updated_at=_utcnow(),
        )

    def with_swarm(self, swarm_id: str | None) -> OrchestrationGoal:
        return OrchestrationGoal(
            id=self.id,
            title=self.title,
            description=self.description,
            context=self.context,
            swarm_id=swarm_id,
            status=self.status,
            created_at=self.created_at,
            updated_at=_utcnow(),
        )


@dataclass(frozen=True, slots=True)
class AgentTask:
    """A single subtask within an orchestration plan, assigned to one agent."""

    id: str = field(default_factory=lambda: uuid4().hex)
    goal_id: str = ""
    title: str = ""
    description: str = ""
    status: AgentTaskStatus = AgentTaskStatus.PENDING
    assigned_agent_id: str | None = None
    depends_on: tuple[str, ...] = field(default_factory=tuple)
    coordination_pattern: CoordinationPattern | None = None
    input_data: dict[str, Any] = field(default_factory=dict)
    output_data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    priority: int = 0
    timeout_seconds: float = 300.0
    created_at: datetime = field(default_factory=_utcnow)
    started_at: datetime | None = None
    completed_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "goal_id": self.goal_id,
            "title": self.title,
            "description": self.description,
            "status": self.status.value,
            "assigned_agent_id": self.assigned_agent_id,
            "depends_on": list(self.depends_on),
            "coordination_pattern": self.coordination_pattern.value
            if self.coordination_pattern
            else None,
            "input_data": dict(self.input_data),
            "output_data": dict(self.output_data),
            "error": self.error,
            "priority": self.priority,
            "timeout_seconds": self.timeout_seconds,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }

    def with_assigned(self, agent_id: str) -> AgentTask:
        return AgentTask(
            id=self.id,
            goal_id=self.goal_id,
            title=self.title,
            description=self.description,
            status=AgentTaskStatus.ASSIGNED,
            assigned_agent_id=agent_id,
            depends_on=self.depends_on,
            coordination_pattern=self.coordination_pattern,
            input_data=self.input_data,
            output_data=self.output_data,
            error=self.error,
            priority=self.priority,
            timeout_seconds=self.timeout_seconds,
            created_at=self.created_at,
            started_at=None,
            completed_at=None,
        )

    def with_status(self, status: AgentTaskStatus) -> AgentTask:
        return AgentTask(
            id=self.id,
            goal_id=self.goal_id,
            title=self.title,
            description=self.description,
            status=status,
            assigned_agent_id=self.assigned_agent_id,
            depends_on=self.depends_on,
            coordination_pattern=self.coordination_pattern,
            input_data=self.input_data,
            output_data=self.output_data,
            error=self.error,
            priority=self.priority,
            timeout_seconds=self.timeout_seconds,
            created_at=self.created_at,
            started_at=self.started_at,
            completed_at=self.completed_at,
        )

    def with_output(self, output: dict[str, Any]) -> AgentTask:
        return AgentTask(
            id=self.id,
            goal_id=self.goal_id,
            title=self.title,
            description=self.description,
            status=AgentTaskStatus.COMPLETED,
            assigned_agent_id=self.assigned_agent_id,
            depends_on=self.depends_on,
            coordination_pattern=self.coordination_pattern,
            input_data=self.input_data,
            output_data=output,
            error=self.error,
            priority=self.priority,
            timeout_seconds=self.timeout_seconds,
            created_at=self.created_at,
            started_at=self.started_at,
            completed_at=_utcnow(),
        )

    def with_error(self, error: str) -> AgentTask:
        return AgentTask(
            id=self.id,
            goal_id=self.goal_id,
            title=self.title,
            description=self.description,
            status=AgentTaskStatus.FAILED,
            assigned_agent_id=self.assigned_agent_id,
            depends_on=self.depends_on,
            coordination_pattern=self.coordination_pattern,
            input_data=self.input_data,
            output_data=self.output_data,
            error=error,
            priority=self.priority,
            timeout_seconds=self.timeout_seconds,
            created_at=self.created_at,
            started_at=self.started_at,
            completed_at=_utcnow(),
        )


@dataclass(frozen=True, slots=True)
class OrchestrationPlan:
    """A decomposed goal with its DAG of subtasks."""

    id: str = field(default_factory=lambda: uuid4().hex)
    goal_id: str = ""
    subtasks: tuple[AgentTask, ...] = field(default_factory=tuple)
    status: str = "pending"
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utcnow)
    completed_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "goal_id": self.goal_id,
            "subtasks": [t.to_dict() for t in self.subtasks],
            "status": self.status,
            "metadata": dict(self.metadata),
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }

    def with_subtask(self, task: AgentTask) -> OrchestrationPlan:
        new_subtasks = list(self.subtasks) + [task]
        return OrchestrationPlan(
            id=self.id,
            goal_id=self.goal_id,
            subtasks=tuple(new_subtasks),
            status=self.status,
            metadata=self.metadata,
            created_at=self.created_at,
            completed_at=self.completed_at,
        )

    def with_status(self, status: str) -> OrchestrationPlan:
        return OrchestrationPlan(
            id=self.id,
            goal_id=self.goal_id,
            subtasks=self.subtasks,
            status=status,
            metadata=self.metadata,
            created_at=self.created_at,
            completed_at=self.completed_at
            if status in ("completed", "failed", "cancelled")
            else None,
        )

    def with_completed(self) -> OrchestrationPlan:
        return OrchestrationPlan(
            id=self.id,
            goal_id=self.goal_id,
            subtasks=self.subtasks,
            status="completed",
            metadata=self.metadata,
            created_at=self.created_at,
            completed_at=_utcnow(),
        )


@dataclass(frozen=True, slots=True)
class Vote:
    """A single vote in a consensus round."""

    voter_id: str
    value: VoteValue
    rationale: str = ""
    weight: float = 1.0
    timestamp: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "voter_id": self.voter_id,
            "value": self.value.value,
            "rationale": self.rationale,
            "weight": self.weight,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class ConsensusResult:
    """Result of a consensus or voting round among swarm agents."""

    id: str = field(default_factory=lambda: uuid4().hex)
    swarm_id: str = ""
    topic: str = ""
    status: ConsensusStatus = ConsensusStatus.PENDING
    votes: tuple[Vote, ...] = field(default_factory=tuple)
    yea_count: int = 0
    nay_count: int = 0
    abstain_count: int = 0
    total_weight: float = 0.0
    yea_weight: float = 0.0
    threshold: float = 0.51
    outcome: bool = False
    started_at: datetime = field(default_factory=_utcnow)
    completed_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "swarm_id": self.swarm_id,
            "topic": self.topic,
            "status": self.status.value,
            "votes": [v.to_dict() for v in self.votes],
            "yea_count": self.yea_count,
            "nay_count": self.nay_count,
            "abstain_count": self.abstain_count,
            "total_weight": self.total_weight,
            "yea_weight": self.yea_weight,
            "threshold": self.threshold,
            "outcome": self.outcome,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }

    def with_vote(self, vote: Vote) -> ConsensusResult:
        new_votes = list(self.votes) + [vote]
        yea = sum(1 for v in new_votes if v.value == VoteValue.YES)
        nay = sum(1 for v in new_votes if v.value == VoteValue.NO)
        abstain = sum(1 for v in new_votes if v.value == VoteValue.ABSTAIN)
        total_w = sum(v.weight for v in new_votes)
        yea_w = sum(v.weight for v in new_votes if v.value == VoteValue.YES)
        reached = yea_w / total_w >= self.threshold if total_w > 0 else False

        if reached:
            new_status = ConsensusStatus.REACHED
        else:
            new_status = ConsensusStatus.IN_PROGRESS

        return ConsensusResult(
            id=self.id,
            swarm_id=self.swarm_id,
            topic=self.topic,
            status=new_status,
            votes=tuple(new_votes),
            yea_count=yea,
            nay_count=nay,
            abstain_count=abstain,
            total_weight=total_w,
            yea_weight=yea_w,
            threshold=self.threshold,
            outcome=reached,
            started_at=self.started_at,
            completed_at=_utcnow() if reached else None,
        )

    def with_status(self, status: ConsensusStatus) -> ConsensusResult:
        return ConsensusResult(
            id=self.id,
            swarm_id=self.swarm_id,
            topic=self.topic,
            status=status,
            votes=self.votes,
            yea_count=self.yea_count,
            nay_count=self.nay_count,
            abstain_count=self.abstain_count,
            total_weight=self.total_weight,
            yea_weight=self.yea_weight,
            threshold=self.threshold,
            outcome=status == ConsensusStatus.REACHED,
            started_at=self.started_at,
            completed_at=_utcnow()
            if status in (ConsensusStatus.REACHED, ConsensusStatus.FAILED, ConsensusStatus.TIE)
            else None,
        )

    def with_outcome(self, outcome: bool) -> ConsensusResult:
        return ConsensusResult(
            id=self.id,
            swarm_id=self.swarm_id,
            topic=self.topic,
            status=ConsensusStatus.REACHED if outcome else ConsensusStatus.FAILED,
            votes=self.votes,
            yea_count=self.yea_count,
            nay_count=self.nay_count,
            abstain_count=self.abstain_count,
            total_weight=self.total_weight,
            yea_weight=self.yea_weight,
            threshold=self.threshold,
            outcome=outcome,
            started_at=self.started_at,
            completed_at=_utcnow(),
        )


@dataclass(frozen=True, slots=True)
class LeaderElectionResult:
    """Result of a leader election round within a swarm."""

    id: str = field(default_factory=lambda: uuid4().hex)
    swarm_id: str = ""
    elected_leader_id: str = ""
    candidates: tuple[str, ...] = field(default_factory=tuple)
    vote_counts: dict[str, int] = field(default_factory=dict)
    total_votes: int = 0
    started_at: datetime = field(default_factory=_utcnow)
    completed_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "swarm_id": self.swarm_id,
            "elected_leader_id": self.elected_leader_id,
            "candidates": list(self.candidates),
            "vote_counts": dict(self.vote_counts),
            "total_votes": self.total_votes,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


@dataclass(frozen=True, slots=True)
class AgentMessage:
    """An inter-agent message sent over the EventBus."""

    id: str = field(default_factory=lambda: uuid4().hex)
    source_agent_id: str = ""
    target_agent_id: str | None = None  # None = broadcast
    swarm_id: str = ""
    message_type: str = "broadcast"
    payload: dict[str, Any] = field(default_factory=dict)
    correlation_id: str | None = None
    timestamp: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source_agent_id": self.source_agent_id,
            "target_agent_id": self.target_agent_id,
            "swarm_id": self.swarm_id,
            "message_type": self.message_type,
            "payload": dict(self.payload),
            "correlation_id": self.correlation_id,
            "timestamp": self.timestamp.isoformat(),
        }

    def with_response(self, response_payload: dict[str, Any]) -> AgentMessage:
        """Create a response message correlated to this one."""
        return AgentMessage(
            source_agent_id=self.target_agent_id or "",
            target_agent_id=self.source_agent_id,
            swarm_id=self.swarm_id,
            message_type="response",
            payload=response_payload,
            correlation_id=self.id,
        )


@dataclass(frozen=True, slots=True)
class OrchestrationTelemetryEntry:
    """A telemetry record from the orchestration subsystem."""

    id: str = field(default_factory=lambda: uuid4().hex)
    event_type: str = ""
    swarm_id: str | None = None
    goal_id: str | None = None
    task_id: str | None = None
    agent_id: str | None = None
    duration_ms: float = 0.0
    status: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "event_type": self.event_type,
            "swarm_id": self.swarm_id,
            "goal_id": self.goal_id,
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "details": dict(self.details),
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class OrchestrationProfile:
    """Named configuration for orchestration behavior."""

    name: str
    description: str = ""
    default_topology: SwarmTopology = SwarmTopology.MESH
    max_agents_per_swarm: int = 10
    subtask_timeout_seconds: float = 60.0
    auto_discover_agents: bool = True
    tags: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "default_topology": self.default_topology.value,
            "max_agents_per_swarm": self.max_agents_per_swarm,
            "subtask_timeout_seconds": self.subtask_timeout_seconds,
            "auto_discover_agents": self.auto_discover_agents,
            "tags": list(self.tags),
        }
