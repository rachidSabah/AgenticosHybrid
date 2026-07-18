"""Orchestration Framework — main M3 composition root.

Wires together all orchestration subsystems:
- AgentRegistry (engine → agent wrapping)
- SwarmManager (team lifecycle)
- CoordinationEngine (pattern execution)
- SwarmIntelligenceEngine (consensus, voting, leader election)
- CommunicationBus (inter-agent messaging)
- TaskOrchestrator (goal decomposition + execution)
- OrchestrationEventPublisher (lifecycle events)
- OrchestrationTelemetry (history + stats)

The framework is the entry point for the API layer and kernel integration.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any

from agentic_os.core.orchestration.communication import CommunicationBus
from agentic_os.core.orchestration.config import OrchestrationConfiguration
from agentic_os.core.orchestration.coordination import CoordinationEngine
from agentic_os.core.orchestration.intelligence import SwarmIntelligenceEngine
from agentic_os.core.orchestration.publisher import OrchestrationEventPublisher
from agentic_os.core.orchestration.registry import OrchestrationAgentRegistry
from agentic_os.core.orchestration.swarm import SwarmManager
from agentic_os.core.orchestration.task_orchestrator import TaskOrchestrator
from agentic_os.core.orchestration.telemetry import OrchestrationTelemetry
from agentic_os.core.runtime.manager import RuntimeManager
from agentic_os.domain.execution import EngineCapability
from agentic_os.domain.orchestration import (
    AgentDescriptor,
    AgentTask,
    ConsensusResult,
    LeaderElectionResult,
    OrchestrationGoal,
    OrchestrationPlan,
    SwarmSpec,
)
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.event_bus import EventBus

log = get_logger("orchestration.framework")


@dataclass
class OrchestrationFramework:
    """Main M3 orchestrator. Composes all orchestration subsystems.

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

    # Subsystems (built by ``start()`` or injected for testing)
    agent_registry: OrchestrationAgentRegistry | None = None
    swarm_manager: SwarmManager | None = None
    coordination_engine: CoordinationEngine | None = None
    intelligence_engine: SwarmIntelligenceEngine | None = None
    communication_bus: CommunicationBus | None = None
    task_orchestrator: TaskOrchestrator | None = None
    publisher: OrchestrationEventPublisher | None = None
    telemetry: OrchestrationTelemetry | None = None

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
        assert self.agent_registry is not None
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
        assert self.agent_registry is not None
        engine_cap = EngineCapability(capability) if capability else None
        return await self.agent_registry.list_agents(
            capability=engine_cap,
            status=status,
        )

    async def get_agent(self, agent_id: str) -> AgentDescriptor | None:
        """Get a single agent descriptor."""
        assert self.agent_registry is not None
        return await self.agent_registry.get_agent(agent_id)

    async def list_agents(self) -> list[AgentDescriptor]:
        """List all available agents."""
        assert self.agent_registry is not None
        return await self.agent_registry.list_agents()

    async def find_agents_by_capability(
        self,
        capability: str,
        min_confidence: float = 0.0,
    ) -> list[AgentDescriptor]:
        """Find agents matching a capability."""
        assert self.agent_registry is not None
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
        assert self.swarm_manager is not None
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
        assert self.swarm_manager is not None
        return await self.swarm_manager.get_swarm(swarm_id)

    async def list_swarms(self) -> list[SwarmSpec]:
        assert self.swarm_manager is not None
        return await self.swarm_manager.list_swarms()

    async def delete_swarm(self, swarm_id: str) -> bool:
        assert self.swarm_manager is not None
        return await self.swarm_manager.delete_swarm(swarm_id)

    async def add_agent_to_swarm(self, swarm_id: str, agent_id: str) -> SwarmSpec | None:
        assert self.swarm_manager is not None
        try:
            return await self.swarm_manager.add_agent_to_swarm(swarm_id, agent_id)
        except ValueError:
            return None

    async def remove_agent_from_swarm(self, swarm_id: str, agent_id: str) -> SwarmSpec | None:
        assert self.swarm_manager is not None
        return await self.swarm_manager.remove_agent_from_swarm(swarm_id, agent_id)

    async def get_swarm_state(self, swarm_id: str) -> Any:
        assert self.swarm_manager is not None
        return await self.swarm_manager.get_swarm_state(swarm_id)

    async def elect_leader(self, swarm_id: str) -> LeaderElectionResult | None:
        assert self.swarm_manager is not None
        return await self.swarm_manager.elect_leader(swarm_id)

    async def get_swarm_leader(self, swarm_id: str) -> AgentDescriptor | None:
        assert self.swarm_manager is not None
        return await self.swarm_manager.get_leader(swarm_id)

    # ── Task Orchestration ──

    async def orchestrate(
        self,
        goal: OrchestrationGoal,
        swarm_id: str,
    ) -> OrchestrationPlan | None:
        """Full pipeline: create goal → assign to swarm → execute plan."""
        assert self.task_orchestrator is not None
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
        assert self.task_orchestrator is not None
        goal = OrchestrationGoal(
            title=title,
            description=description,
            context=context or {},
            swarm_id=swarm_id,
        )
        return await self.task_orchestrator.create_goal(goal)

    async def get_goal(self, goal_id: str) -> OrchestrationGoal | None:
        assert self.task_orchestrator is not None
        return await self.task_orchestrator.get_goal(goal_id)

    async def list_goals(self, status: str | None = None) -> list[OrchestrationGoal]:
        assert self.task_orchestrator is not None
        return await self.task_orchestrator.list_goals(status)

    async def cancel_goal(self, goal_id: str) -> OrchestrationGoal | None:
        assert self.task_orchestrator is not None
        return await self.task_orchestrator.cancel_goal(goal_id)

    async def get_plan(self, plan_id: str) -> OrchestrationPlan | None:
        assert self.task_orchestrator is not None
        return await self.task_orchestrator.get_plan(plan_id)

    async def get_task(self, task_id: str) -> AgentTask | None:
        assert self.task_orchestrator is not None
        return await self.task_orchestrator.get_task(task_id)

    async def list_tasks(
        self,
        goal_id: str | None = None,
        status: str | None = None,
    ) -> list[AgentTask]:
        assert self.task_orchestrator is not None
        return await self.task_orchestrator.list_tasks(goal_id, status)

    # ── Swarm Intelligence ──

    async def reach_consensus(
        self,
        swarm_id: str,
        topic: str,
        proposals: list[dict[str, Any]] | None = None,
    ) -> ConsensusResult | None:
        """Conduct a consensus round among all agents in a swarm."""
        assert self.swarm_manager is not None
        assert self.intelligence_engine is not None
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
        assert self.intelligence_engine is not None
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
        assert self.communication_bus is not None
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
        assert self.communication_bus is not None
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
        assert self.communication_bus is not None
        return await self.communication_bus.get_history(
            limit=limit,
            swarm_id=swarm_id,
            agent_id=agent_id,
        )

    # ── Telemetry ──

    def get_stats(self) -> dict[str, Any]:
        """Get aggregated orchestration statistics."""
        assert self.telemetry is not None
        return self.telemetry.get_stats()

    def get_telemetry_entries(
        self,
        limit: int = 50,
        event_type: str | None = None,
        swarm_id: str | None = None,
    ) -> list[Any]:
        assert self.telemetry is not None
        return self.telemetry.get_entries(
            limit=limit,
            event_type=event_type,
            swarm_id=swarm_id,
        )

    # ── Internal ──

    def _build_subsystems(self) -> None:
        """Build all orchestration subsystems if not already injected."""
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

    async def _sync_agents_loop(self) -> None:
        """Background loop to periodically sync agents from the runtime."""
        while self._running:
            try:
                await asyncio.sleep(self.config.agent_sync_interval_seconds)
                if self._running:
                    assert self.agent_registry is not None
                    await self.agent_registry.sync_from_runtime()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                log.warning("Agent sync error", error=str(exc))
