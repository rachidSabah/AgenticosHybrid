"""Swarm Manager — named agent teams with configurable topologies.

Manages swarm lifecycle: creation, membership, activation, leader election,
and state tracking. All state is in-memory; persistence is a future concern.
"""

from typing import Any

from agentic_os.core.orchestration.intelligence import SwarmIntelligenceEngine
from agentic_os.core.orchestration.registry import OrchestrationAgentRegistry
from agentic_os.domain.events import EventEnvelope, Topic
from agentic_os.domain.orchestration import (
    AgentDescriptor,
    LeaderElectionResult,
    SwarmSpec,
    SwarmState,
    SwarmTopology,
)
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.event_bus import EventBus

log = get_logger("orchestration.swarm")


class SwarmManager:
    """Manages named agent teams (swarms) with configurable topologies.

    Provides full lifecycle: create, read, update, delete, activate/deactivate,
    membership changes, leader election, and state tracking.
    """

    def __init__(
        self,
        bus: EventBus,
        agent_registry: OrchestrationAgentRegistry,
        intelligence: SwarmIntelligenceEngine,
        default_topology: str = "mesh",
        max_agents: int = 10,
    ) -> None:
        self._bus = bus
        self._agent_registry = agent_registry
        self._intelligence = intelligence
        self._default_topology_str = default_topology
        self._max_agents = max_agents
        self._swarms: dict[str, SwarmSpec] = {}
        self._states: dict[str, SwarmState] = {}

    # ── CRUD ──

    async def create_swarm(self, spec: SwarmSpec) -> SwarmSpec:
        """Create a new swarm team. Validates topology and agent references."""
        # Validate agents exist
        if spec.agent_ids:
            for aid in spec.agent_ids:
                agent = await self._agent_registry.get_agent(aid)
                if agent is None:
                    raise ValueError(f"Agent not found: {aid}")

        # Validate topology
        self._validate_topology(spec)

        self._swarms[spec.id] = spec
        self._states[spec.id] = SwarmState(
            swarm_id=spec.id,
            active=False,
            agent_states={aid: "present" for aid in spec.agent_ids},
        )

        await self._publish_event(
            Topic.ORCH_SWARM_CREATED, {"swarm_id": spec.id, "name": spec.name}
        )
        log.info("Swarm created", swarm_id=spec.id, name=spec.name)
        return spec

    async def get_swarm(self, swarm_id: str) -> SwarmSpec | None:
        """Get a swarm definition by ID."""
        return self._swarms.get(swarm_id)

    async def list_swarms(self) -> list[SwarmSpec]:
        """List all swarm definitions."""
        return list(self._swarms.values())

    async def update_swarm(self, swarm_id: str, spec: SwarmSpec) -> SwarmSpec | None:
        """Update a swarm's definition."""
        if swarm_id not in self._swarms:
            return None

        # Validate new topology if changed
        self._validate_topology(spec)

        self._swarms[swarm_id] = spec
        await self._publish_event(
            Topic.ORCH_SWARM_UPDATED, {"swarm_id": swarm_id, "name": spec.name}
        )
        return spec

    async def delete_swarm(self, swarm_id: str) -> bool:
        """Delete a swarm by ID."""
        if swarm_id not in self._swarms:
            return False

        self._swarms.pop(swarm_id)
        self._states.pop(swarm_id, None)
        await self._publish_event(Topic.ORCH_SWARM_DELETED, {"swarm_id": swarm_id})
        log.info("Swarm deleted", swarm_id=swarm_id)
        return True

    # ── Membership ──

    async def add_agent_to_swarm(self, swarm_id: str, agent_id: str) -> SwarmSpec | None:
        """Add an agent to a swarm. Validates the agent exists."""
        spec = self._swarms.get(swarm_id)
        if spec is None:
            return None

        # Check max agents
        if len(spec.agent_ids) >= self._max_agents:
            raise ValueError(f"Swarm {swarm_id} already at max capacity ({self._max_agents})")

        # Check agent exists
        agent = await self._agent_registry.get_agent(agent_id)
        if agent is None:
            raise ValueError(f"Agent not found: {agent_id}")

        new_spec = spec.with_agent(agent_id)
        self._swarms[swarm_id] = new_spec

        # Update state
        state = self._states.get(swarm_id)
        if state:
            self._states[swarm_id] = state.with_agent_state(agent_id, "present")

        await self._publish_event(
            Topic.ORCH_AGENT_JOINED, {"swarm_id": swarm_id, "agent_id": agent_id}
        )
        return new_spec

    async def remove_agent_from_swarm(self, swarm_id: str, agent_id: str) -> SwarmSpec | None:
        """Remove an agent from a swarm."""
        spec = self._swarms.get(swarm_id)
        if spec is None:
            return None

        new_spec = spec.without_agent(agent_id)
        self._swarms[swarm_id] = new_spec

        # Update state
        state = self._states.get(swarm_id)
        if state:
            new_states = dict(state.agent_states)
            new_states.pop(agent_id, None)
            self._states[swarm_id] = SwarmState(
                swarm_id=swarm_id,
                active=state.active,
                current_task_id=state.current_task_id,
                leader_id=None if state.leader_id == agent_id else state.leader_id,
                agent_states=new_states,
            )

        await self._publish_event(
            Topic.ORCH_AGENT_LEFT, {"swarm_id": swarm_id, "agent_id": agent_id}
        )
        return new_spec

    async def get_agents_in_swarm(self, swarm_id: str) -> list[AgentDescriptor]:
        """Get the list of AgentDescriptors for all agents in a swarm."""
        spec = self._swarms.get(swarm_id)
        if spec is None:
            return []

        agents: list[AgentDescriptor] = []
        for aid in spec.agent_ids:
            agent = await self._agent_registry.get_agent(aid)
            if agent is not None:
                agents.append(agent.with_swarm(swarm_id))
        return agents

    # ── Activation ──

    async def activate_swarm(self, swarm_id: str) -> bool:
        """Activate a swarm for task assignment."""
        if swarm_id not in self._swarms:
            return False

        state = self._states.get(swarm_id)
        if state is None:
            self._states[swarm_id] = SwarmState(swarm_id=swarm_id, active=True)
        else:
            self._states[swarm_id] = state.with_active(True)

        await self._publish_event(Topic.ORCH_SWARM_ACTIVATED, {"swarm_id": swarm_id})
        return True

    async def deactivate_swarm(self, swarm_id: str) -> bool:
        """Deactivate a swarm."""
        state = self._states.get(swarm_id)
        if state is None:
            return False

        self._states[swarm_id] = state.with_active(False)
        await self._publish_event(Topic.ORCH_SWARM_DEACTIVATED, {"swarm_id": swarm_id})
        return True

    async def get_swarm_state(self, swarm_id: str) -> SwarmState | None:
        """Get the runtime state of a swarm."""
        return self._states.get(swarm_id)

    # ── Leader Election ──

    async def elect_leader(self, swarm_id: str) -> LeaderElectionResult | None:
        """Elect a leader for the swarm. Delegates to SwarmIntelligenceEngine."""
        spec = self._swarms.get(swarm_id)
        if spec is None:
            return None

        agents = await self.get_agents_in_swarm(swarm_id)
        if not agents:
            return None

        result = await self._intelligence.elect_leader(swarm_id, agents)

        # Update swarm spec with new leader
        if result and result.elected_leader_id:
            new_spec = spec.with_leader(result.elected_leader_id)
            self._swarms[swarm_id] = new_spec

            # Update state
            state = self._states.get(swarm_id)
            if state:
                self._states[swarm_id] = SwarmState(
                    swarm_id=swarm_id,
                    active=state.active,
                    current_task_id=state.current_task_id,
                    leader_id=result.elected_leader_id,
                    agent_states=state.agent_states,
                )

        return result

    async def get_leader(self, swarm_id: str) -> AgentDescriptor | None:
        """Get the current leader of a swarm."""
        spec = self._swarms.get(swarm_id)
        if spec is None or spec.leader_id is None:
            return None

        agent = await self._agent_registry.get_agent(spec.leader_id)
        if agent is not None:
            return agent.with_leader(True).with_swarm(swarm_id)
        return None

    # ── Internal ──

    def _validate_topology(self, spec: SwarmSpec) -> None:
        """Validate topology-specific constraints."""
        if spec.topology == SwarmTopology.STAR and len(spec.agent_ids) < 3:
            raise ValueError(f"Star topology requires at least 3 agents, got {len(spec.agent_ids)}")
        if spec.topology == SwarmTopology.RING and len(spec.agent_ids) < 2:
            raise ValueError(f"Ring topology requires at least 2 agents, got {len(spec.agent_ids)}")

    async def _publish_event(self, topic: Topic, payload: dict[str, Any]) -> None:
        """Publish a swarm lifecycle event."""
        try:
            await self._bus.publish(
                EventEnvelope(
                    type="event",
                    source="swarm-manager",
                    topic=topic.value,
                    payload=payload,
                )
            )
        except Exception as exc:
            log.warning("Failed to publish swarm event", topic=topic.value, error=str(exc))
