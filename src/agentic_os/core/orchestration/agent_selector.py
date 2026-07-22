"""Agent Selector — capability-based agent selection and matching.

Matches tasks to the most suitable agents based on capabilities, availability,
latency, health status, and historical performance.
"""

from typing import Any

from agentic_os.core.orchestration.registry import OrchestrationAgentRegistry
from agentic_os.domain.events import EventEnvelope, Topic
from agentic_os.domain.orchestration import (
    AgentDescriptor,
    AgentTask,
    OrchestrationGoal,
)
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.event_bus import EventBus

log = get_logger("orchestration.agent_selector")


class AgentSelector:
    """Selects the best agent for a task based on capability matching.

    Scores agents by capability overlap, health status, latency, and
    current load to find the optimal assignment.
    """

    def __init__(self, bus: EventBus, agent_registry: OrchestrationAgentRegistry) -> None:
        self._bus = bus
        self._agent_registry = agent_registry

    async def select_agent(
        self,
        task: AgentTask,
        available_agents: list[AgentDescriptor] | None = None,
    ) -> AgentDescriptor | None:
        """Select the best agent for a task."""
        if available_agents is None:
            available_agents = await self._agent_registry.list_agents()

        if not available_agents:
            return None

        # Filter healthy agents
        healthy = [a for a in available_agents if a.health_status == "healthy"]
        if not healthy:
            healthy = available_agents

        # Score each agent
        scored = [(self._score_agent_for_task(a, task), a) for a in healthy]
        scored.sort(key=lambda x: x[0], reverse=True)

        best_agent = scored[0][1]

        await self._publish(
            Topic.ORCH_AGENT_SELECTED,
            {
                "task_id": task.id,
                "agent_id": best_agent.agent_id,
                "score": scored[0][0],
            },
        )

        return best_agent

    async def match_capabilities(
        self,
        goal: OrchestrationGoal,
        required_capabilities: list[str],
    ) -> list[AgentDescriptor]:
        """Find agents matching required capabilities for a goal."""
        agents = await self._agent_registry.list_agents()

        matched: list[AgentDescriptor] = []
        for agent in agents:
            agent_caps = set(agent.capabilities)
            required = set(required_capabilities)
            overlap = agent_caps & required
            if overlap or not required_capabilities:
                matched.append(agent)
                await self._publish(
                    Topic.ORCH_AGENT_CAPABILITY_MATCHED,
                    {
                        "agent_id": agent.agent_id,
                        "agent_name": agent.name,
                        "matched_capabilities": list(overlap),
                        "score": len(overlap) / max(len(required), 1),
                    },
                )

        return matched

    def _score_agent_for_task(self, agent: AgentDescriptor, task: AgentTask) -> float:
        """Score an agent's suitability for a task (higher = better)."""
        score = 0.0

        # Capability match (50% weight)
        task_keywords = set(task.title.lower().split())
        agent_caps = set(c.lower() for c in agent.capabilities)
        matched_caps = agent_caps & task_keywords
        score += len(matched_caps) * 10.0

        # Health bonus (20% weight)
        if agent.health_status == "healthy":
            score += 20.0

        # Latency penalty (15% weight)
        score += max(0, 15.0 - agent.latency_ms / 100.0)

        # Status bonus (15% weight)
        if agent.status in ("idle", "running"):
            score += 10.0

        # Leadership bonus
        if agent.is_leader:
            score += 5.0

        return score

    async def _publish(self, topic: Topic, payload: dict[str, Any]) -> None:
        try:
            await self._bus.publish(
                EventEnvelope(
                    type="event", source="agent-selector", topic=topic.value, payload=payload
                )
            )
        except Exception as exc:
            log.warning("Publish failed", topic=topic.value, error=str(exc))
