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
    ConsensusResult,
    CoordinationPattern,
    LeaderElectionResult,
    OrchestrationGoal,
    OrchestrationPlan,
    SwarmSpec,
    SwarmState,
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
