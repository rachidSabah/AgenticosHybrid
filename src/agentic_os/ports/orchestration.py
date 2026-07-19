"""
Orchestration Port Interfaces

Defines the protocol contracts for multi-agent orchestration and swarm intelligence.
Domain logic depends on these interfaces, never on implementations.

Six protocols follow the same pattern as ``ports/execution.py``:
- AgentRegistryPort — wraps M1 RuntimeManager as agent source
- SwarmManagerPort — named agent teams with topologies
- TaskOrchestratorPort — goal decomposition, assignment, execution
- CoordinationStrategy — pluggable coordination patterns
- DecompositionStrategy — pluggable goal decomposition
- ConsensusStrategy — pluggable consensus/voting
"""

from collections.abc import Sequence
from typing import Any, Protocol, runtime_checkable

from agentic_os.domain.execution import EngineCapability, ExecutionCapability
from agentic_os.domain.orchestration import (
    AgentDescriptor,
    AgentTask,
    Checkpoint,
    ConsensusResult,
    CoordinationPattern,
    ExecutionCost,
    ExecutionMetrics,
    ExecutionStage,
    ExecutionTimeline,
    LeaderElectionResult,
    MergedResult,
    MergeStrategy,
    OrchestrationGoal,
    OrchestrationPlan,
    RetryPolicy,
    SwarmProfile,
    SwarmSpec,
    SwarmState,
    ValidationResult,
)
from agentic_os.ports.event_bus import EventBus
from agentic_os.ports.execution import RuntimeManagerPort


@runtime_checkable
class AgentRegistryPort(Protocol):
    """Wraps RuntimeManager to present execution engines as agents."""

    async def list_agents(
        self,
        capability: EngineCapability | None = None,
        status: str | None = None,
    ) -> list[AgentDescriptor]:
        """List all available agents (wrapped execution engines)."""
        ...

    async def get_agent(self, agent_id: str) -> AgentDescriptor | None:
        """Get an agent by its engine ID."""
        ...

    async def get_agent_capabilities(self, agent_id: str) -> list[ExecutionCapability]:
        """Get capabilities of a specific agent."""
        ...

    async def count_agents(self) -> int:
        """Total number of available agents."""
        ...

    async def find_agents_by_capability(
        self,
        capability: EngineCapability,
        min_confidence: float = 0.0,
    ) -> list[AgentDescriptor]:
        """Find agents matching a capability."""
        ...


@runtime_checkable
class SwarmManagerPort(Protocol):
    """Manages named agent teams with configurable topologies."""

    async def create_swarm(self, spec: SwarmSpec) -> SwarmSpec:
        """Create a new swarm team."""
        ...

    async def get_swarm(self, swarm_id: str) -> SwarmSpec | None:
        """Get swarm definition by ID."""
        ...

    async def list_swarms(self) -> Sequence[SwarmSpec]:
        """List all swarms."""
        ...

    async def update_swarm(self, swarm_id: str, spec: SwarmSpec) -> SwarmSpec | None:
        """Update a swarm's definition."""
        ...

    async def delete_swarm(self, swarm_id: str) -> bool:
        """Delete a swarm by ID."""
        ...

    async def add_agent_to_swarm(self, swarm_id: str, agent_id: str) -> SwarmSpec | None:
        """Add an agent to a swarm."""
        ...

    async def remove_agent_from_swarm(self, swarm_id: str, agent_id: str) -> SwarmSpec | None:
        """Remove an agent from a swarm."""
        ...

    async def activate_swarm(self, swarm_id: str) -> bool:
        """Activate a swarm for task assignment."""
        ...

    async def deactivate_swarm(self, swarm_id: str) -> bool:
        """Deactivate a swarm."""
        ...

    async def get_swarm_state(self, swarm_id: str) -> SwarmState | None:
        """Get runtime state of a swarm."""
        ...

    async def elect_leader(self, swarm_id: str) -> LeaderElectionResult | None:
        """Elect a leader for the swarm."""
        ...

    async def get_leader(self, swarm_id: str) -> AgentDescriptor | None:
        """Get the current leader of a swarm."""
        ...


@runtime_checkable
class TaskOrchestratorPort(Protocol):
    """Decomposes goals into subtasks, assigns to agents, monitors execution."""

    async def create_goal(self, goal: OrchestrationGoal) -> OrchestrationGoal:
        """Create a high-level orchestration goal."""
        ...

    async def get_goal(self, goal_id: str) -> OrchestrationGoal | None:
        """Get a goal by ID."""
        ...

    async def list_goals(self, status: str | None = None) -> list[OrchestrationGoal]:
        """List all goals, optionally filtered by status."""
        ...

    async def decompose_goal(self, goal_id: str, strategy: str | None = None) -> OrchestrationPlan:
        """Decompose a goal into subtasks using the named strategy."""
        ...

    async def get_plan(self, plan_id: str) -> OrchestrationPlan | None:
        """Get an orchestration plan by ID."""
        ...

    async def assign_to_swarm(self, goal_id: str, swarm_id: str) -> OrchestrationPlan:
        """Assign a goal to a swarm for execution."""
        ...

    async def assign_subtask(self, task_id: str, agent_id: str) -> AgentTask:
        """Assign a single subtask to a specific agent."""
        ...

    async def execute_plan(self, plan_id: str) -> OrchestrationPlan:
        """Execute an orchestration plan through the swarm."""
        ...

    async def cancel_goal(self, goal_id: str) -> OrchestrationGoal:
        """Cancel a goal and all its subtasks."""
        ...

    async def get_task(self, task_id: str) -> AgentTask | None:
        """Get a subtask by ID."""
        ...

    async def list_tasks(
        self, goal_id: str | None = None, status: str | None = None
    ) -> list[AgentTask]:
        """List subtasks, optionally filtered."""
        ...


@runtime_checkable
class CoordinationStrategy(Protocol):
    """Pluggable coordination pattern strategy for executing subtasks."""

    @property
    def pattern(self) -> CoordinationPattern:
        """The coordination pattern this strategy implements."""
        ...

    async def execute(
        self,
        swarm: SwarmSpec,
        tasks: list[AgentTask],
        agent_registry: AgentRegistryPort,
        runtime_manager: RuntimeManagerPort,
        bus: EventBus,
    ) -> list[AgentTask]:
        """Execute tasks using this coordination pattern.

        Returns updated tasks with results/errors populated.
        """
        ...


@runtime_checkable
class DecompositionStrategy(Protocol):
    """Pluggable strategy for decomposing a goal into subtasks."""

    @property
    def name(self) -> str:
        """Name of this decomposition strategy."""
        ...

    async def decompose(self, goal: OrchestrationGoal) -> list[AgentTask]:
        """Decompose a goal into a list of subtasks."""
        ...


@runtime_checkable
class ConsensusStrategy(Protocol):
    """Pluggable strategy for reaching consensus among agents."""

    async def reach_consensus(
        self,
        swarm_id: str,
        topic: str,
        proposals: list[dict[str, Any]],
        agents: list[AgentDescriptor],
        bus: EventBus,
    ) -> ConsensusResult:
        """Run a consensus round and return the result."""
        ...


# ── Additional Ports ──


@runtime_checkable
class PlannerPort(Protocol):
    """Autonomous goal planner — analysis, decomposition, and plan generation."""

    async def analyze_goal(self, goal: OrchestrationGoal) -> dict[str, Any]:
        """Analyze a goal and return analysis including required capabilities and complexity."""
        ...

    async def create_plan(
        self,
        goal: OrchestrationGoal,
        swarm: SwarmSpec | None = None,
        profile: SwarmProfile | None = None,
    ) -> OrchestrationPlan:
        """Create an execution plan from a goal, decomposing into ordered tasks."""
        ...

    async def resolve_dependencies(self, plan: OrchestrationPlan) -> OrchestrationPlan:
        """Resolve and validate all task dependencies in a plan."""
        ...

    async def parallelize_plan(
        self, plan: OrchestrationPlan, max_parallel: int = 5
    ) -> OrchestrationPlan:
        """Identify tasks that can be parallelized and annotate them."""
        ...


@runtime_checkable
class SchedulerPort(Protocol):
    """Task scheduler — prioritization, sequencing, and dispatching."""

    async def schedule_tasks(
        self,
        plan: OrchestrationPlan,
        agents: list[AgentDescriptor],
        policy: RetryPolicy | None = None,
    ) -> OrchestrationPlan:
        """Schedule all tasks in a plan, assigning agents and priorities."""
        ...

    async def dispatch_task(self, task: AgentTask, agent: AgentDescriptor) -> AgentTask:
        """Dispatch a single task to an agent for execution."""
        ...

    async def get_schedule(self, plan_id: str) -> list[AgentTask]:
        """Get the current schedule (ordered tasks) for a plan."""
        ...


@runtime_checkable
class SupervisorPort(Protocol):
    """Execution supervisor — monitoring, failure detection, and recovery."""

    async def monitor_execution(self, plan: OrchestrationPlan) -> OrchestrationPlan:
        """Monitor ongoing execution and detect failures or deadlocks."""
        ...

    async def detect_failures(self, plan: OrchestrationPlan) -> list[AgentTask]:
        """Detect failed or hung tasks in a plan."""
        ...

    async def detect_deadlocks(self, plan: OrchestrationPlan) -> list[str]:
        """Detect deadlocked task dependency chains."""
        ...

    async def restart_task(
        self, task: AgentTask, agent: AgentDescriptor | None = None
    ) -> AgentTask:
        """Restart a failed task, optionally on a different agent."""
        ...

    async def reassign_task(self, task: AgentTask, new_agent_id: str) -> AgentTask:
        """Reassign a task to a different agent."""
        ...


@runtime_checkable
class ResultMergerPort(Protocol):
    """Result merging — combine outputs from multiple agents."""

    async def merge(
        self,
        tasks: list[AgentTask],
        strategy: MergeStrategy = MergeStrategy.CONSENSUS,
    ) -> MergedResult:
        """Merge results from multiple completed tasks using the specified strategy."""
        ...

    async def resolve_conflicts(self, merged_result: MergedResult) -> MergedResult:
        """Resolve conflicts in a merged result."""
        ...

    async def score_confidence(self, merged_result: MergedResult) -> float:
        """Score the confidence of a merged result."""
        ...


@runtime_checkable
class ValidationPort(Protocol):
    """Validation engine — validate task outputs, plans, and agent results."""

    async def validate_output(
        self, task: AgentTask, schema: dict[str, Any] | None = None
    ) -> ValidationResult:
        """Validate a task's output against optional schema and quality rules."""
        ...

    async def validate_plan(self, plan: OrchestrationPlan) -> ValidationResult:
        """Validate a plan's structure, dependencies, and feasibility."""
        ...

    async def validate_security(
        self,
        task: AgentTask,
        agent: AgentDescriptor,
    ) -> ValidationResult:
        """Validate security constraints for a task-agent assignment."""
        ...

    async def validate_policy(
        self,
        task: AgentTask,
        policies: dict[str, Any],
    ) -> ValidationResult:
        """Validate a task against execution policies."""
        ...


@runtime_checkable
class CheckpointPort(Protocol):
    """Checkpoint management — save and restore execution state."""

    async def save_checkpoint(
        self,
        plan: OrchestrationPlan,
        stage: ExecutionStage | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Checkpoint:
        """Save a checkpoint of the current execution state."""
        ...

    async def restore_checkpoint(self, checkpoint_id: str) -> OrchestrationPlan | None:
        """Restore execution state from a checkpoint."""
        ...

    async def list_checkpoints(self, plan_id: str) -> list[Checkpoint]:
        """List all checkpoints for a plan."""
        ...

    async def delete_checkpoint(self, checkpoint_id: str) -> bool:
        """Delete a checkpoint."""
        ...


@runtime_checkable
class MetricsPort(Protocol):
    """Metrics collection — execution, performance, and cost metrics."""

    async def collect_metrics(self, plan: OrchestrationPlan) -> ExecutionMetrics:
        """Collect execution metrics for a plan."""
        ...

    async def record_timeline(self, entry: ExecutionTimeline) -> None:
        """Record a timeline entry."""
        ...

    async def get_timeline(self, plan_id: str, limit: int = 100) -> list[ExecutionTimeline]:
        """Get the execution timeline for a plan."""
        ...


@runtime_checkable
class CostEstimatorPort(Protocol):
    """Cost estimation and tracking for execution plans."""

    async def estimate_cost(self, plan: OrchestrationPlan) -> ExecutionCost:
        """Estimate the cost of executing a plan."""
        ...

    async def track_cost(
        self,
        plan_id: str,
        agent_id: str,
        cost: float,
        stage_id: str | None = None,
    ) -> ExecutionCost:
        """Track actual cost incurred."""
        ...

    async def get_costs(self, plan_id: str) -> ExecutionCost | None:
        """Get accumulated costs for a plan."""
        ...


@runtime_checkable
class RecoveryPort(Protocol):
    """Failure recovery — recover from failed tasks and agents."""

    async def recover_task(
        self, task: AgentTask, available_agents: list[AgentDescriptor]
    ) -> AgentTask:
        """Recover a failed task by retrying on a suitable agent."""
        ...

    async def recover_plan(
        self,
        plan: OrchestrationPlan,
        checkpoint: Checkpoint | None = None,
    ) -> OrchestrationPlan:
        """Recover a plan from the last checkpoint or from scratch."""
        ...

    async def rollback_plan(
        self,
        plan: OrchestrationPlan,
        checkpoint: Checkpoint,
    ) -> OrchestrationPlan:
        """Rollback a plan to a specific checkpoint."""
        ...
