"""Orchestration Framework — main M3/M4 composition root.

Wires together all orchestration subsystems:
- AgentRegistry (engine → agent wrapping)
- SwarmManager (team lifecycle)
- CoordinationEngine (pattern execution)
- SwarmIntelligenceEngine (consensus, voting, leader election)
- CommunicationBus (inter-agent messaging)
- TaskOrchestrator (goal decomposition + execution)
- OrchestrationEventPublisher (lifecycle events)
- OrchestrationTelemetry (history + stats)
- SwarmPlanner (goal analysis + plan creation)              [M4]
- SwarmScheduler (task scheduling + dispatch)               [M4]
- SwarmSupervisor (monitoring + failure detection)          [M4]
- ResultMerger (output merging)                             [M4]
- ValidationEngine (plan + output validation)               [M4]
- RetryManager (retry with backoff)                         [M4]
- FailureRecovery (recovery + rollback)                     [M4]
- CheckpointManager (execution checkpointing)               [M4]
- AgentSelector (capability-based agent selection)          [M4]
- MetricsEngine (execution metrics)                         [M4]
- CostTracker (cost tracking)                               [M4]
- PerformanceAnalyzer (analysis + reporting)                [M4]

The framework is the entry point for the API layer and kernel integration.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any

from agentic_os.core.orchestration.agent_selector import AgentSelector
from agentic_os.core.orchestration.checkpoint import CheckpointManager
from agentic_os.core.orchestration.communication import CommunicationBus
from agentic_os.core.orchestration.config import OrchestrationConfiguration
from agentic_os.core.orchestration.coordination import CoordinationEngine
from agentic_os.core.orchestration.intelligence import SwarmIntelligenceEngine
from agentic_os.core.orchestration.metrics import (
    CostTracker,
    MetricsEngine,
    PerformanceAnalyzer,
)
from agentic_os.core.orchestration.planner import SwarmPlanner
from agentic_os.core.orchestration.publisher import OrchestrationEventPublisher
from agentic_os.core.orchestration.recovery import FailureRecovery
from agentic_os.core.orchestration.registry import OrchestrationAgentRegistry
from agentic_os.core.orchestration.result_merger import ResultMerger
from agentic_os.core.orchestration.retry import RetryManager
from agentic_os.core.orchestration.scheduler import SwarmScheduler
from agentic_os.core.orchestration.supervisor import SwarmSupervisor
from agentic_os.core.orchestration.swarm import SwarmManager
from agentic_os.core.orchestration.task_orchestrator import TaskOrchestrator
from agentic_os.core.orchestration.telemetry import OrchestrationTelemetry
from agentic_os.core.orchestration.validation import ValidationEngine
from agentic_os.core.runtime.manager import RuntimeManager
from agentic_os.domain.execution import EngineCapability
from agentic_os.domain.orchestration import (
    AgentDescriptor,
    AgentTask,
    Checkpoint,
    ConsensusResult,
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
    ValidationResult,
)
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.event_bus import EventBus

log = get_logger("orchestration.framework")


@dataclass
class OrchestrationFramework:
    """Main M3/M4 orchestrator. Composes all orchestration subsystems.

    Usage::

        framework = OrchestrationFramework(
            bus=event_bus,
            runtime=runtime_manager,
            config=OrchestrationConfiguration(...),
        )
        await framework.start()
        agents = await framework.discover_agents()
        ...
        await framework.stop()
    """

    bus: EventBus
    runtime: RuntimeManager
    config: OrchestrationConfiguration = field(default_factory=OrchestrationConfiguration)

    # Core subsystems (injected or built by ``start()``)
    agent_registry: OrchestrationAgentRegistry | None = None
    swarm_manager: SwarmManager | None = None
    coordination_engine: CoordinationEngine | None = None
    intelligence_engine: SwarmIntelligenceEngine | None = None
    communication_bus: CommunicationBus | None = None
    task_orchestrator: TaskOrchestrator | None = None
    publisher: OrchestrationEventPublisher | None = None
    telemetry: OrchestrationTelemetry | None = None

    # M4 Swarm Engine subsystems
    planner: SwarmPlanner | None = None
    scheduler: SwarmScheduler | None = None
    supervisor: SwarmSupervisor | None = None
    result_merger: ResultMerger | None = None
    validation_engine: ValidationEngine | None = None
    retry_manager: RetryManager | None = None
    failure_recovery: FailureRecovery | None = None
    checkpoint_manager: CheckpointManager | None = None
    agent_selector: AgentSelector | None = None
    metrics_engine: MetricsEngine | None = None
    cost_tracker: CostTracker | None = None
    performance_analyzer: PerformanceAnalyzer | None = None

    # Internal state
    _running: bool = field(default=False, repr=False)
    _agent_sync_task: asyncio.Task | None = field(default=None, repr=False)

    # ── Lifecycle ──

    async def start(self) -> None:
        """Start the orchestration framework.

        Builds all subsystems if not already injected, syncs agents from
        the runtime, and starts background agent synchronisation.
        """
        if self._running:
            log.warning("OrchestrationFramework already running")
            return

        self._build_subsystems()

        # Initial sync from runtime
        if self.agent_registry is None:
            raise RuntimeError("agent_registry cannot be None")
        await self.agent_registry.sync_from_runtime()
        agent_count = await self.agent_registry.count_agents()
        log.info("Orchestration framework started", agents=agent_count)

        self._running = True

        # Start background agent sync if enabled
        if self.config.enabled and self.config.agent_sync_interval_seconds > 0:
            self._agent_sync_task = asyncio.create_task(
                self._sync_agents_loop(),
                name="orchestration-agent-sync",
            )

    async def stop(self) -> None:
        """Stop the orchestration framework and cancel background tasks."""
        self._running = False

        if self._agent_sync_task is not None:
            self._agent_sync_task.cancel()
            try:
                await self._agent_sync_task
            except asyncio.CancelledError:
                pass
            self._agent_sync_task = None

        log.info("Orchestration framework stopped")

    # ── Agent Discovery ──

    async def discover_agents(
        self,
        capability: str | None = None,
        status: str | None = None,
    ) -> list[AgentDescriptor]:
        """Discover agents from the runtime, optionally filtered."""
        if self.agent_registry is None:
            raise RuntimeError("agent_registry cannot be None")
        engine_cap = EngineCapability(capability) if capability else None
        return await self.agent_registry.list_agents(
            capability=engine_cap,
            status=status,
        )

    async def get_agent(self, agent_id: str) -> AgentDescriptor | None:
        """Get a single agent descriptor."""
        if self.agent_registry is None:
            raise RuntimeError("agent_registry cannot be None")
        return await self.agent_registry.get_agent(agent_id)

    async def list_agents(self) -> list[AgentDescriptor]:
        """List all available agents."""
        if self.agent_registry is None:
            raise RuntimeError("agent_registry cannot be None")
        return await self.agent_registry.list_agents()

    async def find_agents_by_capability(
        self,
        capability: str,
        min_confidence: float = 0.0,
    ) -> list[AgentDescriptor]:
        """Find agents matching a capability."""
        if self.agent_registry is None:
            raise RuntimeError("agent_registry cannot be None")
        return await self.agent_registry.find_agents_by_capability(
            EngineCapability(capability),
            min_confidence,
        )

    # ── Swarm Management ──

    async def create_swarm(
        self,
        name: str,
        description: str = "",
        topology: str = "mesh",
        agent_ids: tuple[str, ...] = (),
        tags: tuple[str, ...] = (),
        metadata: dict[str, Any] | None = None,
    ) -> SwarmSpec:
        """Create a new swarm."""
        if self.swarm_manager is None:
            raise RuntimeError("swarm_manager cannot be None")
        from agentic_os.domain.orchestration import SwarmTopology

        try:
            topo = SwarmTopology(topology)
        except ValueError:
            topo = SwarmTopology.MESH

        spec = SwarmSpec(
            name=name,
            description=description,
            topology=topo,
            agent_ids=agent_ids,
            tags=tags,
            metadata=metadata or {},
        )
        return await self.swarm_manager.create_swarm(spec)

    async def get_swarm(self, swarm_id: str) -> SwarmSpec | None:
        if self.swarm_manager is None:
            raise RuntimeError("swarm_manager cannot be None")
        return await self.swarm_manager.get_swarm(swarm_id)

    async def list_swarms(self) -> list[SwarmSpec]:
        if self.swarm_manager is None:
            raise RuntimeError("swarm_manager cannot be None")
        return await self.swarm_manager.list_swarms()

    async def delete_swarm(self, swarm_id: str) -> bool:
        if self.swarm_manager is None:
            raise RuntimeError("swarm_manager cannot be None")
        return await self.swarm_manager.delete_swarm(swarm_id)

    async def add_agent_to_swarm(self, swarm_id: str, agent_id: str) -> SwarmSpec | None:
        if self.swarm_manager is None:
            raise RuntimeError("swarm_manager cannot be None")
        try:
            return await self.swarm_manager.add_agent_to_swarm(swarm_id, agent_id)
        except ValueError:
            return None

    async def remove_agent_from_swarm(self, swarm_id: str, agent_id: str) -> SwarmSpec | None:
        if self.swarm_manager is None:
            raise RuntimeError("swarm_manager cannot be None")
        return await self.swarm_manager.remove_agent_from_swarm(swarm_id, agent_id)

    async def get_swarm_state(self, swarm_id: str) -> Any:
        if self.swarm_manager is None:
            raise RuntimeError("swarm_manager cannot be None")
        return await self.swarm_manager.get_swarm_state(swarm_id)

    async def elect_leader(self, swarm_id: str) -> LeaderElectionResult | None:
        if self.swarm_manager is None:
            raise RuntimeError("swarm_manager cannot be None")
        return await self.swarm_manager.elect_leader(swarm_id)

    async def get_swarm_leader(self, swarm_id: str) -> AgentDescriptor | None:
        if self.swarm_manager is None:
            raise RuntimeError("swarm_manager cannot be None")
        return await self.swarm_manager.get_leader(swarm_id)

    # ── Task Orchestration ──

    async def orchestrate(
        self,
        goal: OrchestrationGoal,
        swarm_id: str,
    ) -> OrchestrationPlan | None:
        """Full pipeline: create goal → assign to swarm → execute plan."""
        if self.task_orchestrator is None:
            raise RuntimeError("task_orchestrator cannot be None")
        await self.task_orchestrator.create_goal(goal)
        plan = await self.task_orchestrator.assign_to_swarm(goal.id, swarm_id)
        if plan is None:
            return None
        return await self.task_orchestrator.execute_plan(plan.id)

    async def create_goal(
        self,
        title: str,
        description: str = "",
        context: dict[str, Any] | None = None,
        swarm_id: str | None = None,
    ) -> OrchestrationGoal:
        if self.task_orchestrator is None:
            raise RuntimeError("task_orchestrator cannot be None")
        goal = OrchestrationGoal(
            title=title,
            description=description,
            context=context or {},
            swarm_id=swarm_id,
        )
        return await self.task_orchestrator.create_goal(goal)

    async def get_goal(self, goal_id: str) -> OrchestrationGoal | None:
        if self.task_orchestrator is None:
            raise RuntimeError("task_orchestrator cannot be None")
        return await self.task_orchestrator.get_goal(goal_id)

    async def list_goals(self, status: str | None = None) -> list[OrchestrationGoal]:
        if self.task_orchestrator is None:
            raise RuntimeError("task_orchestrator cannot be None")
        return await self.task_orchestrator.list_goals(status)

    async def cancel_goal(self, goal_id: str) -> OrchestrationGoal | None:
        if self.task_orchestrator is None:
            raise RuntimeError("task_orchestrator cannot be None")
        return await self.task_orchestrator.cancel_goal(goal_id)

    async def get_plan(self, plan_id: str) -> OrchestrationPlan | None:
        if self.task_orchestrator is None:
            raise RuntimeError("task_orchestrator cannot be None")
        return await self.task_orchestrator.get_plan(plan_id)

    async def get_task(self, task_id: str) -> AgentTask | None:
        if self.task_orchestrator is None:
            raise RuntimeError("task_orchestrator cannot be None")
        return await self.task_orchestrator.get_task(task_id)

    async def list_tasks(
        self,
        goal_id: str | None = None,
        status: str | None = None,
    ) -> list[AgentTask]:
        if self.task_orchestrator is None:
            raise RuntimeError("task_orchestrator cannot be None")
        return await self.task_orchestrator.list_tasks(goal_id, status)

    # ── Swarm Intelligence ──

    async def reach_consensus(
        self,
        swarm_id: str,
        topic: str,
        proposals: list[dict[str, Any]] | None = None,
    ) -> ConsensusResult | None:
        """Conduct a consensus round among all agents in a swarm."""
        if self.swarm_manager is None:
            raise RuntimeError("swarm_manager cannot be None")
        if self.intelligence_engine is None:
            raise RuntimeError("intelligence_engine cannot be None")
        agents = await self.swarm_manager.get_agents_in_swarm(swarm_id)
        if not agents:
            return None
        return await self.intelligence_engine.start_consensus(
            swarm_id=swarm_id,
            topic=topic,
            proposals=proposals or [],
            agents=agents,
            quorum=self.config.default_quorum,
        )

    async def cast_vote(
        self,
        consensus_id: str,
        voter_id: str,
        value: str,
        rationale: str = "",
        weight: float = 1.0,
    ) -> ConsensusResult | None:
        if self.intelligence_engine is None:
            raise RuntimeError("intelligence_engine cannot be None")
        from agentic_os.domain.orchestration import VoteValue

        try:
            vote_val = VoteValue(value)
        except ValueError:
            return None
        return await self.intelligence_engine.cast_vote(
            consensus_id=consensus_id,
            voter_id=voter_id,
            value=vote_val,
            rationale=rationale,
            weight=weight,
        )

    # ── Communication ──

    async def send_message(
        self,
        source_agent_id: str,
        target_agent_id: str | None,
        swarm_id: str,
        payload: dict[str, Any],
        message_type: str = "direct",
    ) -> Any:
        if self.communication_bus is None:
            raise RuntimeError("communication_bus cannot be None")
        from agentic_os.domain.orchestration import AgentMessage

        msg = AgentMessage(
            source_agent_id=source_agent_id,
            target_agent_id=target_agent_id,
            swarm_id=swarm_id,
            message_type=message_type,
            payload=payload,
        )
        return await self.communication_bus.send_message(msg)

    async def broadcast_message(
        self,
        source_agent_id: str,
        swarm_id: str,
        payload: dict[str, Any],
    ) -> Any:
        if self.communication_bus is None:
            raise RuntimeError("communication_bus cannot be None")
        return await self.communication_bus.broadcast(
            source_agent_id=source_agent_id,
            swarm_id=swarm_id,
            payload=payload,
        )

    async def get_message_history(
        self,
        limit: int = 50,
        swarm_id: str | None = None,
        agent_id: str | None = None,
    ) -> list[Any]:
        if self.communication_bus is None:
            raise RuntimeError("communication_bus cannot be None")
        return await self.communication_bus.get_history(
            limit=limit,
            swarm_id=swarm_id,
            agent_id=agent_id,
        )

    # ── Telemetry ──

    def get_stats(self) -> dict[str, Any]:
        """Get aggregated orchestration statistics."""
        if self.telemetry is None:
            raise RuntimeError("telemetry cannot be None")
        return self.telemetry.get_stats()

    def get_telemetry_entries(
        self,
        limit: int = 50,
        event_type: str | None = None,
        swarm_id: str | None = None,
    ) -> list[Any]:
        if self.telemetry is None:
            raise RuntimeError("telemetry cannot be None")
        return self.telemetry.get_entries(
            limit=limit,
            event_type=event_type,
            swarm_id=swarm_id,
        )

    # ═══════════════════════════════════════════════════════════════
    #  M4 Swarm Engine Methods
    # ═══════════════════════════════════════════════════════════════

    # ── Planner ──

    async def analyze_goal(self, goal: OrchestrationGoal) -> dict[str, Any]:
        """Analyze a goal for complexity, required capabilities, and topology suggestion."""
        if self.planner is None:
            raise RuntimeError("planner cannot be None")
        return await self.planner.analyze_goal(goal)

    async def create_plan(
        self,
        goal: OrchestrationGoal,
        swarm: SwarmSpec | None = None,
        profile: SwarmProfile | None = None,
    ) -> OrchestrationPlan:
        """Create a full execution plan from a goal."""
        if self.planner is None:
            raise RuntimeError("planner cannot be None")
        return await self.planner.create_plan(goal, swarm, profile)

    async def resolve_dependencies(self, plan: OrchestrationPlan) -> OrchestrationPlan:
        """Resolve and validate all task dependencies in a plan."""
        if self.planner is None:
            raise RuntimeError("planner cannot be None")
        return await self.planner.resolve_dependencies(plan)

    async def parallelize_plan(
        self, plan: OrchestrationPlan, max_parallel: int = 5
    ) -> OrchestrationPlan:
        """Identify tasks that can be parallelized and annotate them."""
        if self.planner is None:
            raise RuntimeError("planner cannot be None")
        return await self.planner.parallelize_plan(plan, max_parallel)

    # ── Scheduler ──

    async def schedule_tasks(
        self,
        plan: OrchestrationPlan,
        agents: list[AgentDescriptor],
        policy: RetryPolicy | None = None,
    ) -> OrchestrationPlan:
        """Schedule all tasks in a plan, topologically sorted and agent-assigned."""
        if self.scheduler is None:
            raise RuntimeError("scheduler cannot be None")
        return await self.scheduler.schedule_tasks(plan, agents, policy)

    async def dispatch_task(self, task: AgentTask, agent: AgentDescriptor) -> AgentTask:
        """Dispatch a single task to an agent for execution."""
        if self.scheduler is None:
            raise RuntimeError("scheduler cannot be None")
        return await self.scheduler.dispatch_task(task, agent)

    async def get_schedule(self, plan_id: str) -> list[AgentTask]:
        """Get the current ordered schedule for a plan."""
        if self.scheduler is None:
            raise RuntimeError("scheduler cannot be None")
        return await self.scheduler.get_schedule(plan_id)

    # ── Supervisor ──

    async def monitor_execution(self, plan: OrchestrationPlan) -> OrchestrationPlan:
        """Monitor ongoing execution and detect failures/deadlocks."""
        if self.supervisor is None:
            raise RuntimeError("supervisor cannot be None")
        return await self.supervisor.monitor_execution(plan)

    async def detect_failures(self, plan: OrchestrationPlan) -> list[AgentTask]:
        """Detect failed or hung tasks in a plan."""
        if self.supervisor is None:
            raise RuntimeError("supervisor cannot be None")
        return await self.supervisor.detect_failures(plan)

    async def detect_deadlocks(self, plan: OrchestrationPlan) -> list[str]:
        """Detect deadlocked dependency chains."""
        if self.supervisor is None:
            raise RuntimeError("supervisor cannot be None")
        return await self.supervisor.detect_deadlocks(plan)

    async def restart_task(
        self, task: AgentTask, agent: AgentDescriptor | None = None
    ) -> AgentTask:
        """Restart a failed task, optionally on a different agent."""
        if self.supervisor is None:
            raise RuntimeError("supervisor cannot be None")
        return await self.supervisor.restart_task(task, agent)

    async def reassign_task(self, task: AgentTask, new_agent_id: str) -> AgentTask:
        """Reassign a task to a different agent."""
        if self.supervisor is None:
            raise RuntimeError("supervisor cannot be None")
        return await self.supervisor.reassign_task(task, new_agent_id)

    # ── Result Merger ──

    async def merge_results(
        self,
        tasks: list[AgentTask],
        strategy: MergeStrategy = MergeStrategy.CONSENSUS,
    ) -> MergedResult:
        """Merge results from multiple completed tasks."""
        if self.result_merger is None:
            raise RuntimeError("result_merger cannot be None")
        return await self.result_merger.merge(tasks, strategy)

    async def resolve_merge_conflicts(self, merged_result: MergedResult) -> MergedResult:
        """Resolve conflicts in a merged result."""
        if self.result_merger is None:
            raise RuntimeError("result_merger cannot be None")
        return await self.result_merger.resolve_conflicts(merged_result)

    async def score_confidence(self, merged_result: MergedResult) -> float:
        """Score the confidence of a merged result."""
        if self.result_merger is None:
            raise RuntimeError("result_merger cannot be None")
        return await self.result_merger.score_confidence(merged_result)

    # ── Validation ──

    async def validate_output(
        self,
        task: AgentTask,
        schema: dict[str, Any] | None = None,
    ) -> ValidationResult:
        """Validate a task's output."""
        if self.validation_engine is None:
            raise RuntimeError("validation_engine cannot be None")
        return await self.validation_engine.validate_output(task, schema)

    async def validate_plan(self, plan: OrchestrationPlan) -> ValidationResult:
        """Validate a plan's structure and dependencies."""
        if self.validation_engine is None:
            raise RuntimeError("validation_engine cannot be None")
        return await self.validation_engine.validate_plan(plan)

    async def validate_security(self, task: AgentTask, agent: AgentDescriptor) -> ValidationResult:
        """Validate security constraints for a task-agent assignment."""
        if self.validation_engine is None:
            raise RuntimeError("validation_engine cannot be None")
        return await self.validation_engine.validate_security(task, agent)

    async def validate_policy(self, task: AgentTask, policies: dict[str, Any]) -> ValidationResult:
        """Validate a task against execution policies."""
        if self.validation_engine is None:
            raise RuntimeError("validation_engine cannot be None")
        return await self.validation_engine.validate_policy(task, policies)

    # ── Checkpoints ──

    async def save_checkpoint(
        self,
        plan: OrchestrationPlan,
        stage: ExecutionStage | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Checkpoint:
        """Save a checkpoint of the current execution state."""
        if self.checkpoint_manager is None:
            raise RuntimeError("checkpoint_manager cannot be None")
        return await self.checkpoint_manager.save_checkpoint(plan, stage, metadata)

    async def restore_checkpoint(self, checkpoint_id: str) -> OrchestrationPlan | None:
        """Restore execution state from a checkpoint."""
        if self.checkpoint_manager is None:
            raise RuntimeError("checkpoint_manager cannot be None")
        return await self.checkpoint_manager.restore_checkpoint(checkpoint_id)

    async def list_checkpoints(self, plan_id: str) -> list[Checkpoint]:
        """List all checkpoints for a plan."""
        if self.checkpoint_manager is None:
            raise RuntimeError("checkpoint_manager cannot be None")
        return await self.checkpoint_manager.list_checkpoints(plan_id)

    async def delete_checkpoint(self, checkpoint_id: str) -> bool:
        """Delete a checkpoint."""
        if self.checkpoint_manager is None:
            raise RuntimeError("checkpoint_manager cannot be None")
        return await self.checkpoint_manager.delete_checkpoint(checkpoint_id)

    # ── Agent Selection ──

    async def select_agent(
        self,
        task: AgentTask,
        available_agents: list[AgentDescriptor] | None = None,
    ) -> AgentDescriptor | None:
        """Select the best agent for a task."""
        if self.agent_selector is None:
            raise RuntimeError("agent_selector cannot be None")
        return await self.agent_selector.select_agent(task, available_agents)

    async def match_capabilities(
        self,
        goal: OrchestrationGoal,
        required_capabilities: list[str],
    ) -> list[AgentDescriptor]:
        """Find agents matching required capabilities."""
        if self.agent_selector is None:
            raise RuntimeError("agent_selector cannot be None")
        return await self.agent_selector.match_capabilities(goal, required_capabilities)

    # ── Metrics & Cost ──

    async def collect_metrics(self, plan: OrchestrationPlan) -> ExecutionMetrics:
        """Collect execution metrics for a plan."""
        if self.metrics_engine is None:
            raise RuntimeError("metrics_engine cannot be None")
        return await self.metrics_engine.collect_metrics(plan)

    async def record_timeline(self, entry: ExecutionTimeline) -> None:
        """Record a timeline entry."""
        if self.metrics_engine is None:
            raise RuntimeError("metrics_engine cannot be None")
        await self.metrics_engine.record_timeline(entry)

    async def get_timeline(self, plan_id: str, limit: int = 100) -> list[ExecutionTimeline]:
        """Get the execution timeline for a plan."""
        if self.metrics_engine is None:
            raise RuntimeError("metrics_engine cannot be None")
        return await self.metrics_engine.get_timeline(plan_id, limit)

    async def estimate_cost(self, plan: OrchestrationPlan) -> ExecutionCost:
        """Estimate the cost of executing a plan."""
        if self.cost_tracker is None:
            raise RuntimeError("cost_tracker cannot be None")
        return await self.cost_tracker.estimate_cost(plan)

    async def track_cost(
        self, plan_id: str, agent_id: str, cost: float, stage_id: str | None = None
    ) -> ExecutionCost:
        """Track actual cost incurred."""
        if self.cost_tracker is None:
            raise RuntimeError("cost_tracker cannot be None")
        return await self.cost_tracker.track_cost(plan_id, agent_id, cost, stage_id)

    async def get_costs(self, plan_id: str) -> ExecutionCost | None:
        """Get accumulated costs for a plan."""
        if self.cost_tracker is None:
            raise RuntimeError("cost_tracker cannot be None")
        return await self.cost_tracker.get_costs(plan_id)

    async def analyze_performance(self, plan_id: str) -> dict[str, Any]:
        """Generate a performance analysis report."""
        if self.performance_analyzer is None:
            raise RuntimeError("performance_analyzer cannot be None")
        return await self.performance_analyzer.analyze_plan(plan_id)

    # ── Recovery ──

    async def recover_task(
        self,
        task: AgentTask,
        available_agents: list[AgentDescriptor],
    ) -> AgentTask:
        """Recover a failed task by retrying on a suitable agent."""
        if self.failure_recovery is None:
            raise RuntimeError("failure_recovery cannot be None")
        return await self.failure_recovery.recover_task(task, available_agents)

    async def recover_plan(
        self,
        plan: OrchestrationPlan,
        checkpoint: Checkpoint | None = None,
    ) -> OrchestrationPlan:
        """Recover a plan from checkpoint or from scratch."""
        if self.failure_recovery is None:
            raise RuntimeError("failure_recovery cannot be None")
        return await self.failure_recovery.recover_plan(plan, checkpoint)

    async def rollback_plan(
        self, plan: OrchestrationPlan, checkpoint: Checkpoint
    ) -> OrchestrationPlan:
        """Rollback a plan to a specific checkpoint."""
        if self.failure_recovery is None:
            raise RuntimeError("failure_recovery cannot be None")
        return await self.failure_recovery.rollback_plan(plan, checkpoint)

    # ── Retry ──

    async def should_retry(self, task: AgentTask, policy: RetryPolicy | None = None) -> bool:
        """Determine if a task should be retried."""
        if self.retry_manager is None:
            raise RuntimeError("retry_manager cannot be None")
        return await self.retry_manager.should_retry(task, policy)

    async def reset_retry_count(self, task_id: str) -> None:
        """Reset retry count for a task."""
        if self.retry_manager is None:
            raise RuntimeError("retry_manager cannot be None")
        self.retry_manager.reset_retry_count(task_id)

    # ── Internal ──

    def _build_subsystems(self) -> None:
        """Build all orchestration subsystems if not already injected.

        Order matters: foundational subsystems (publisher, registry) are
        built first, then those that depend on them, then the M4 engine
        subsystems on top.
        """
        # ── M3 Core ──
        if self.publisher is None:
            self.publisher = OrchestrationEventPublisher(bus=self.bus)

        if self.agent_registry is None:
            self.agent_registry = OrchestrationAgentRegistry(
                runtime=self.runtime,
            )

        if self.intelligence_engine is None:
            self.intelligence_engine = SwarmIntelligenceEngine(
                bus=self.bus,
                default_quorum=self.config.default_quorum,
            )

        if self.swarm_manager is None:
            self.swarm_manager = SwarmManager(
                bus=self.bus,
                agent_registry=self.agent_registry,
                intelligence=self.intelligence_engine,
            )

        if self.coordination_engine is None:
            self.coordination_engine = CoordinationEngine()

        if self.task_orchestrator is None:
            self.task_orchestrator = TaskOrchestrator(
                bus=self.bus,
                agent_registry=self.agent_registry,
                swarm_manager=self.swarm_manager,
                coordination=self.coordination_engine,
            )

        if self.communication_bus is None:
            self.communication_bus = CommunicationBus(
                bus=self.bus,
                history_max=self.config.communication_history_max,
            )

        if self.telemetry is None:
            self.telemetry = OrchestrationTelemetry(
                max_entries=self.config.telemetry_max_entries,
            )

        # ── M4 Swarm Engine Subsystems ──

        # Agent selector depends on agent_registry
        if self.agent_selector is None:
            self.agent_selector = AgentSelector(
                bus=self.bus,
                agent_registry=self.agent_registry,
            )

        # Planner: goal analysis + plan generation
        if self.planner is None:
            self.planner = SwarmPlanner(
                bus=self.bus,
                agent_registry=self.agent_registry,
                default_strategy=None,
            )

        # Scheduler: topological sort + dispatch
        if self.scheduler is None:
            self.scheduler = SwarmScheduler(
                bus=self.bus,
                agent_registry=self.agent_registry,
                runtime=self.runtime,
                default_policy=RetryPolicy(
                    max_retries=self.config.supervisor_max_retries,
                    base_delay_seconds=self.config.retry_default_policy.get(
                        "base_delay_seconds", 1.0
                    ),
                    backoff_multiplier=self.config.retry_default_policy.get(
                        "backoff_multiplier", 2.0
                    ),
                    max_delay_seconds=self.config.retry_default_policy.get(
                        "max_delay_seconds", 60.0
                    ),
                    jitter=self.config.retry_default_policy.get("jitter", True),
                    retry_on_error=self.config.retry_default_policy.get("retry_on_error", True),
                    retry_on_timeout=self.config.retry_default_policy.get("retry_on_timeout", True),
                ),
            )

        # Supervisor: monitoring + failure detection
        if self.supervisor is None:
            self.supervisor = SwarmSupervisor(
                bus=self.bus,
                agent_registry=self.agent_registry,
                runtime=self.runtime,
                max_retries=self.config.supervisor_max_retries,
                monitor_interval_seconds=self.config.supervisor_monitor_interval_seconds,
            )

        # Result merger
        if self.result_merger is None:
            self.result_merger = ResultMerger(bus=self.bus)

        # Validation engine
        if self.validation_engine is None:
            self.validation_engine = ValidationEngine(bus=self.bus)

        # Retry manager
        if self.retry_manager is None:
            policy = RetryPolicy(
                max_retries=self.config.retry_default_policy.get("max_retries", 3),
                base_delay_seconds=self.config.retry_default_policy.get("base_delay_seconds", 1.0),
                backoff_multiplier=self.config.retry_default_policy.get("backoff_multiplier", 2.0),
                max_delay_seconds=self.config.retry_default_policy.get("max_delay_seconds", 60.0),
                jitter=self.config.retry_default_policy.get("jitter", True),
                retry_on_error=self.config.retry_default_policy.get("retry_on_error", True),
                retry_on_timeout=self.config.retry_default_policy.get("retry_on_timeout", True),
            )
            self.retry_manager = RetryManager(bus=self.bus, default_policy=policy)

        # Failure recovery
        if self.failure_recovery is None:
            self.failure_recovery = FailureRecovery(bus=self.bus)

        # Checkpoint manager
        if self.checkpoint_manager is None:
            self.checkpoint_manager = CheckpointManager(bus=self.bus)

        # Metrics & cost
        if self.metrics_engine is None:
            self.metrics_engine = MetricsEngine(
                bus=self.bus,
                max_timeline_entries=self.config.metrics_max_timeline_entries,
            )

        if self.cost_tracker is None:
            self.cost_tracker = CostTracker(bus=self.bus)

        if self.performance_analyzer is None:
            self.performance_analyzer = PerformanceAnalyzer(
                metrics_engine=self.metrics_engine,
                cost_tracker=self.cost_tracker,
            )

        log.info(
            "Orchestration subsystems built",
            planner=self.planner is not None,
            scheduler=self.scheduler is not None,
            supervisor=self.supervisor is not None,
            result_merger=self.result_merger is not None,
            validation=self.validation_engine is not None,
            retry=self.retry_manager is not None,
            recovery=self.failure_recovery is not None,
            checkpoint=self.checkpoint_manager is not None,
            agent_selector=self.agent_selector is not None,
            metrics=self.metrics_engine is not None,
            cost=self.cost_tracker is not None,
        )

    async def _sync_agents_loop(self) -> None:
        """Background loop to periodically sync agents from the runtime."""
        while self._running:
            try:
                await asyncio.sleep(self.config.agent_sync_interval_seconds)
                if self._running:
                    if self.agent_registry is None:
                        raise RuntimeError("agent_registry cannot be None")
                    await self.agent_registry.sync_from_runtime()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                log.warning("Agent sync error", error=str(exc))
