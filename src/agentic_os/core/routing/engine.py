"""OmniRoute Decision Engine — mission-level routing across the agent swarm.

Evaluates every available agent against every mission task across four dimensions:
cost, speed, capability fit, and reliability. Produces optimal mission-level
assignment plans that can be fed directly to the Orchestrator.

Strategies
----------
- FASTEST           — minimises total estimated execution time
- CHEAPEST          — minimises total estimated cost
- BEST_CAPABILITY   — maximises capability match scores
- BALANCED          — weighted sum of all four dimensions (default)
- RELIABILITY_FIRST — maximises reliability scores (prefers proven agents)
- LATENCY_FIRST     — minimises per-call latency
- CUSTOM            — user-provided weights via OmniRouteConfig

Integration
-----------
Call ``route_mission(plan)`` from the Orchestrator's ``_on_task_planned``
handler to produce an optimal assignment before dispatch.
"""

from __future__ import annotations

from typing import Any

from agentic_os.core.routing import (
    AgentCapabilityScore,
    MissionRoutePlan,
    OmniRouteConfig,
    RouteDecisionStatus,
    RoutingStrategy,
    TaskRouteAssignment,
)
from agentic_os.domain.mission import (
    Mission,
    MissionPlan,
    MissionTask,
)
from agentic_os.infrastructure.logging import get_logger

log = get_logger("routing.omni")

# Weight presets for each strategy
STRATEGY_WEIGHTS: dict[RoutingStrategy, dict[str, float]] = {
    RoutingStrategy.FASTEST: {
        "cost": 0.05,
        "speed": 0.70,
        "capability": 0.15,
        "reliability": 0.10,
    },
    RoutingStrategy.CHEAPEST: {
        "cost": 0.70,
        "speed": 0.10,
        "capability": 0.10,
        "reliability": 0.10,
    },
    RoutingStrategy.BEST_CAPABILITY: {
        "cost": 0.10,
        "speed": 0.10,
        "capability": 0.70,
        "reliability": 0.10,
    },
    RoutingStrategy.BALANCED: {
        "cost": 0.25,
        "speed": 0.25,
        "capability": 0.30,
        "reliability": 0.20,
    },
    RoutingStrategy.RELIABILITY_FIRST: {
        "cost": 0.10,
        "speed": 0.10,
        "capability": 0.15,
        "reliability": 0.65,
    },
    RoutingStrategy.LATENCY_FIRST: {
        "cost": 0.10,
        "speed": 0.60,
        "capability": 0.20,
        "reliability": 0.10,
    },
    RoutingStrategy.CUSTOM: {
        "cost": 0.25,
        "speed": 0.25,
        "capability": 0.30,
        "reliability": 0.20,
    },
}


class OmniRouteEngine:
    """Mission-aware routing engine.

    Usage::

        engine = OmniRouteEngine(config)
        route = await engine.route_mission(mission, plan, available_agents)
    """

    def __init__(
        self,
        config: OmniRouteConfig | None = None,
    ) -> None:
        self._config = config or OmniRouteConfig()
        self._capability_scores: dict[str, list[AgentCapabilityScore]] = {}
        self._agent_registry: dict[str, dict[str, Any]] = {}

    # ── Public API ────────────────────────────────────────────────────────

    def register_agent(
        self,
        agent_id: str,
        name: str,
        provider: str,
        capabilities: dict[str, float],
        cost_per_1k: float = 0.0,
        latency_ms: float = 1000.0,
        reliability: float = 0.95,
    ) -> None:
        """Register an agent with its capability profile for routing decisions."""
        self._agent_registry[agent_id] = {
            "id": agent_id,
            "name": name,
            "provider": provider,
            "capabilities": capabilities,
            "cost_per_1k": cost_per_1k,
            "latency_ms": latency_ms,
            "reliability": reliability,
        }
        for cap, score in capabilities.items():
            cs = AgentCapabilityScore(
                agent_id=agent_id,
                agent_name=name,
                provider=provider,
                capability=cap,
                score=score,
                estimated_cost=cost_per_1k,
                estimated_latency_ms=latency_ms,
                reliability=reliability,
            )
            self._capability_scores.setdefault(cap, []).append(cs)
        log.info("agent.registered_for_routing", agent=agent_id, capabilities=len(capabilities))

    def unregister_agent(self, agent_id: str) -> None:
        """Remove an agent from routing consideration."""
        self._agent_registry.pop(agent_id, None)
        for cap in list(self._capability_scores.keys()):
            self._capability_scores[cap] = [
                cs for cs in self._capability_scores[cap] if cs.agent_id != agent_id
            ]

    def get_weights(self, strategy: RoutingStrategy) -> dict[str, float]:
        """Return the weight vector for a given strategy."""
        if strategy == RoutingStrategy.CUSTOM:
            return {
                "cost": self._config.cost_weight,
                "speed": self._config.speed_weight,
                "capability": self._config.capability_weight,
                "reliability": self._config.reliability_weight,
            }
        return dict(STRATEGY_WEIGHTS.get(strategy, STRATEGY_WEIGHTS[RoutingStrategy.BALANCED]))

    async def route_mission(
        self,
        mission: Mission,
        plan: MissionPlan,
        strategy: RoutingStrategy = RoutingStrategy.BALANCED,
    ) -> MissionRoutePlan:
        """Produce an optimal route plan for an entire mission.

        Args:
            mission: The mission being planned.
            plan: The mission plan (with tasks, dependencies).
            strategy: Routing strategy to use.

        Returns:
            A MissionRoutePlan with per-task assignments.
        """
        weights = self.get_weights(strategy)
        assignments: list[TaskRouteAssignment] = []
        total_cost = 0.0
        total_duration = 0.0
        provider_usage: dict[str, int] = {}

        if not self._agent_registry:
            log.warning("route.no_agents_registered", mission=mission.id)
            return MissionRoutePlan(
                mission_id=mission.id,
                strategy=strategy,
                assignments=(),
                total_estimated_cost=0.0,
                total_estimated_duration_ms=0.0,
                provider_usage={},
            )

        for task in plan.tasks:
            assignment = await self._route_task(
                task=task,
                weights=weights,
                strategy=strategy,
                previous_assignments=assignments,
                provider_usage=provider_usage,
            )
            assignments.append(assignment)
            total_cost += assignment.estimated_cost
            total_duration += assignment.estimated_duration_ms
            provider_usage[assignment.provider] = provider_usage.get(assignment.provider, 0) + 1

        avg_score = (
            sum(a.composite_score for a in assignments) / len(assignments) if assignments else 0.0
        )

        route_plan = MissionRoutePlan(
            mission_id=mission.id,
            strategy=strategy,
            assignments=tuple(assignments),
            total_estimated_cost=total_cost,
            total_estimated_duration_ms=total_duration,
            average_composite_score=avg_score,
            provider_usage=dict(provider_usage),
        )
        log.info(
            "route.mission_planned",
            mission=mission.id,
            tasks=len(assignments),
            providers=len(provider_usage),
            strategy=strategy.value,
            avg_score=round(avg_score, 3),
        )
        return route_plan

    async def route_plan(
        self,
        plan: MissionPlan,
        strategy: RoutingStrategy = RoutingStrategy.BALANCED,
    ) -> MissionRoutePlan:
        """Route a plan without requiring a full Mission object."""
        dummy_mission = Mission(
            id=plan.mission_id or "direct-route",
            title=f"Routed: {plan.summary[:60]}" if plan.summary else "Direct Route",
            description=plan.summary,
        )
        return await self.route_mission(dummy_mission, plan, strategy)

    # ── Internal ──────────────────────────────────────────────────────────

    async def _route_task(
        self,
        task: MissionTask,
        weights: dict[str, float],
        strategy: RoutingStrategy,
        previous_assignments: list[TaskRouteAssignment],
        provider_usage: dict[str, int],
    ) -> TaskRouteAssignment:
        """Score every agent for a single task and pick the best."""
        if not self._agent_registry:
            return TaskRouteAssignment(
                task_id=task.id,
                task_title=task.title,
                assigned_agent_id="",
                assigned_agent_name="none",
                provider="none",
                strategy_used=strategy,
                composite_score=0.0,
                cost_score=0.0,
                speed_score=0.0,
                capability_score=0.0,
                reliability_score=0.0,
                estimated_cost=0.0,
                estimated_duration_ms=0.0,
                status=RouteDecisionStatus.BLOCKED,
                reasoning="No agents available for routing",
            )

        best_score = -1.0
        best_agent_id = ""
        best_agent_name = ""
        best_provider = ""
        best_cost = 0.0
        best_duration = 0.0
        best_cap_score = 0.0
        best_speed_score = 0.0
        best_reliability_score = 0.0
        fallback_id = ""
        fallback_provider = ""
        reasoning_parts: list[str] = []

        requirement = (task.required_capability or "chat").lower()

        # Score each agent
        scored: list[tuple[float, str, dict[str, Any]]] = []
        for agent_id, info in self._agent_registry.items():
            # Normalise values to 0-1 range
            max_cost = max(
                (a["cost_per_1k"] for a in self._agent_registry.values()),
                default=1.0,
            )
            cost_norm = 1.0 - (info["cost_per_1k"] / max_cost if max_cost > 0 else 0.0)

            max_latency = max(
                (a["latency_ms"] for a in self._agent_registry.values()),
                default=1000.0,
            )
            speed_norm = 1.0 - (info["latency_ms"] / max_latency if max_latency > 0 else 0.0)

            cap_score = info["capabilities"].get(requirement, 0.0)
            # Broader capability check — look for partial match
            if cap_score == 0.0:
                for cap_name, cap_val in info["capabilities"].items():
                    if requirement in cap_name or cap_name in requirement:
                        cap_score = max(cap_score, cap_val * 0.6)

            reliability_norm = info["reliability"]

            # Weighted composite score
            composite = (
                weights["cost"] * cost_norm
                + weights["speed"] * speed_norm
                + weights["capability"] * cap_score
                + weights["reliability"] * reliability_norm
            )

            scored.append((composite, agent_id, info))
            reasoning_parts.append(
                f"{info['name']}: cost={cost_norm:.2f} speed={speed_norm:.2f} "
                f"cap={cap_score:.2f} rel={reliability_norm:.2f} → {composite:.3f}"
            )

        # Sort by score descending
        scored.sort(key=lambda x: x[0], reverse=True)

        if scored:
            best_score, best_agent_id, best_info = scored[0]
            best_agent_name = best_info["name"]
            best_provider = best_info["provider"]
            max_cost = max(
                (a["cost_per_1k"] for a in self._agent_registry.values()),
                default=1.0,
            )
            best_cost = best_info["cost_per_1k"]
            best_duration = best_info["latency_ms"]
            max_latency = max(
                (a["latency_ms"] for a in self._agent_registry.values()),
                default=1000.0,
            )
            best_cap_score = best_info["capabilities"].get(requirement, 0.0)
            if best_cap_score == 0.0:
                for cap_name, cap_val in best_info["capabilities"].items():
                    if requirement in cap_name or cap_name in requirement:
                        best_cap_score = max(best_cap_score, cap_val * 0.6)
            best_speed_score = 1.0 - (best_duration / max_latency if max_latency > 0 else 0.0)
            best_reliability_score = best_info["reliability"]

            # Pick fallback (second-best)
            if len(scored) > 1:
                fallback_id = scored[1][1]
                fallback_provider = scored[1][2]["provider"]

        reasoning = "; ".join(reasoning_parts[:3])  # top 3 agents
        if best_score < self._config.min_confidence_for_auto_route:
            reasoning += " [LOW CONFIDENCE — manual approval recommended]"

        return TaskRouteAssignment(
            task_id=task.id,
            task_title=task.title,
            assigned_agent_id=best_agent_id,
            assigned_agent_name=best_agent_name,
            provider=best_provider,
            strategy_used=strategy,
            composite_score=round(best_score, 3) if best_score >= 0 else 0.0,
            cost_score=round(1.0 - (best_cost / max(max_cost, 1)), 3),
            speed_score=round(best_speed_score, 3),
            capability_score=round(best_cap_score, 3),
            reliability_score=round(best_reliability_score, 3),
            estimated_cost=round(best_cost, 4),
            estimated_duration_ms=round(best_duration, 1),
            status=RouteDecisionStatus.ASSIGNED,
            fallback_agent_id=fallback_id or None,
            fallback_provider=fallback_provider or None,
            reasoning=reasoning,
        )

    async def compare_strategies(
        self,
        mission: Mission,
        plan: MissionPlan,
    ) -> dict[str, MissionRoutePlan]:
        """Compare all routing strategies for a mission.

        Returns a dict mapping strategy name to its route plan.
        """
        results: dict[str, MissionRoutePlan] = {}
        for strategy in RoutingStrategy:
            if strategy == RoutingStrategy.CUSTOM:
                continue
            route = await self.route_mission(mission, plan, strategy)
            results[strategy.value] = route
        return results
