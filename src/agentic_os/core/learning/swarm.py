"""Swarm optimizer — analyzes swarm performance and optimizes swarm composition."""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from agentic_os.domain.learning import (
    ExecutionHistory,
    OptimizationTarget,
)
from agentic_os.infrastructure.logging import get_logger

log = get_logger("learning.swarm")


def _utcnow() -> datetime:
    return datetime.now(UTC)


_SWARM_TOPOLOGIES = ["hierarchical", "mesh", "star", "ring", "tree", "fully_connected"]
_CONSENSUS_STRATEGIES = ["majority", "weighted", "unanimous", "median", "ranked_choice"]


class SwarmOptimizer:
    """In-memory swarm optimizer that analyzes and optimizes swarm executions.

    Analyzes swarm execution data to recommend better topologies,
    consensus strategies, and agent selection for optimal performance.
    """

    def __init__(self) -> None:
        self._execution_history: dict[str, ExecutionHistory] = {}
        self._swarm_data: dict[str, dict[str, Any]] = {}
        self._swarm_recommendations: dict[str, dict[str, Any]] = {}

    def record_execution(self, history: ExecutionHistory) -> ExecutionHistory:
        self._execution_history[history.id] = history
        if history.swarm_id:
            self._swarm_data.setdefault(
                history.swarm_id,
                {
                    "executions": [],
                    "agents": set(),
                    "total_duration_ms": 0.0,
                    "total_cost": 0.0,
                    "success_count": 0,
                    "failure_count": 0,
                },
            )
            entry = self._swarm_data[history.swarm_id]
            entry["executions"].append(history)
            if history.engine_name:
                entry["agents"].add(history.engine_name)
            entry["total_duration_ms"] += history.duration_ms
            entry["total_cost"] += history.cost
            if history.status == "completed":
                entry["success_count"] += 1
            elif history.status == "failed":
                entry["failure_count"] += 1
        return history

    async def analyze_swarm_performance(self) -> dict[str, Any]:
        """Analyze all swarm execution data and return performance metrics."""
        if not self._swarm_data:
            return {"swarms_analyzed": 0, "swarms": {}}

        results: dict[str, Any] = {}
        for swarm_id, data in self._swarm_data.items():
            executions = data["executions"]
            total = len(executions)
            if total == 0:
                continue

            avg_duration = data["total_duration_ms"] / total
            avg_cost = data["total_cost"] / total
            success_rate = (
                data["success_count"] / (data["success_count"] + data["failure_count"])
                if (data["success_count"] + data["failure_count"]) > 0
                else 0.0
            )

            # Determine current topology and strategy from metadata
            current_topology = "unknown"
            current_strategy = "unknown"
            task_types: dict[str, int] = {}
            for ex in executions:
                if ex.metadata:
                    ct = ex.metadata.get("swarm_topology", "")
                    if ct:
                        current_topology = str(ct)
                    cs = ex.metadata.get("consensus_strategy", "")
                    if cs:
                        current_strategy = str(cs)
                if ex.task_type:
                    task_types[ex.task_type] = task_types.get(ex.task_type, 0) + 1

            results[swarm_id] = {
                "swarm_id": swarm_id,
                "total_executions": total,
                "agents": sorted(data["agents"]),
                "agent_count": len(data["agents"]),
                "avg_duration_ms": round(avg_duration, 1),
                "avg_cost": round(avg_cost, 4),
                "success_rate": round(success_rate, 3),
                "current_topology": current_topology,
                "current_consensus_strategy": current_strategy,
                "task_types": task_types,
                "top_task_type": max(task_types, key=lambda k: task_types[k])
                if task_types
                else "unknown",
            }

        log.info("Swarm performance analysis complete", swarms=len(results))
        return {
            "swarms_analyzed": len(results),
            "swarms": results,
        }

    async def recommend_swarm_optimizations(self) -> Sequence[dict[str, Any]]:
        """Generate swarm optimization recommendations based on performance data."""
        recommendations: list[dict[str, Any]] = []

        for swarm_id, data in self._swarm_data.items():
            executions = data["executions"]
            total = len(executions)
            if total < 3:
                continue

            success_rate = (
                data["success_count"] / (data["success_count"] + data["failure_count"])
                if (data["success_count"] + data["failure_count"]) > 0
                else 0.0
            )
            avg_duration = data["total_duration_ms"] / total
            agent_count = len(data["agents"])

            # Low success rate -> recommend topology/strategy change
            if success_rate < 0.7:
                rec: dict[str, Any] = {
                    "id": f"swarm-perf-{int(_utcnow().timestamp())}",
                    "target": OptimizationTarget.SWARM_COMPOSITION.value,
                    "swarm_id": swarm_id,
                    "type": "swarm_topology",
                    "title": f"Improve Swarm {swarm_id} Success Rate",
                    "description": (
                        f"Swarm {swarm_id} has {success_rate:.0%} success rate "
                        f"across {total} executions with {agent_count} agents. "
                        f"Consider switching topology or consensus strategy."
                    ),
                    "current_success_rate": round(success_rate, 3),
                    "agent_count": agent_count,
                    "recommended_topology": "mesh",
                    "recommended_strategy": "weighted",
                    "alternatives": _SWARM_TOPOLOGIES[:4],
                    "confidence": 0.7,
                    "estimated_improvement": round((0.9 - success_rate) * 100, 1),
                    "status": "active",
                }
                recommendations.append(rec)
                self._swarm_recommendations[rec["id"]] = rec
                log.info("Swarm optimization recommended", swarm_id=swarm_id)

            # High latency -> recommend agent reduction or task splitting
            if avg_duration > 5000:
                rec = {
                    "id": f"swarm-latency-{int(_utcnow().timestamp())}",
                    "target": OptimizationTarget.SWARM_COMPOSITION.value,
                    "swarm_id": swarm_id,
                    "type": "swarm_latency",
                    "title": f"Reduce Swarm {swarm_id} Latency",
                    "description": (
                        f"Swarm {swarm_id} average execution duration is "
                        f"{avg_duration:.0f}ms with {agent_count} agents. "
                        f"Consider reducing agent count or parallelizing subtasks."
                    ),
                    "avg_duration_ms": round(avg_duration, 1),
                    "agent_count": agent_count,
                    "recommended_topology": "tree",
                    "alternatives": ["hierarchical", "star"],
                    "confidence": 0.65,
                    "estimated_improvement": min(60.0, (avg_duration - 1000.0) / avg_duration * 50),
                    "status": "active",
                }
                recommendations.append(rec)
                self._swarm_recommendations[rec["id"]] = rec
                log.info("Swarm latency optimization recommended", swarm_id=swarm_id)

        return recommendations

    async def optimize_swarm_composition(
        self, swarm_id: str, config: dict[str, Any]
    ) -> dict[str, Any]:
        """Apply a swarm composition optimization based on config."""
        if swarm_id not in self._swarm_data:
            raise ValueError(f"Swarm not found: {swarm_id}")

        topology = config.get("topology", "mesh")
        agents = config.get("agents", [])
        strategy = config.get("consensus_strategy", "weighted")

        result = {
            "swarm_id": swarm_id,
            "previous_agents": sorted(self._swarm_data[swarm_id]["agents"]),
            "recommended_agents": agents,
            "previous_topology": "unknown",
            "recommended_topology": topology,
            "previous_strategy": "unknown",
            "recommended_strategy": strategy,
            "optimized_at": _utcnow().isoformat(),
            "estimated_improvement": config.get("estimated_improvement", 0.0),
        }

        log.info(
            "Swarm composition optimized",
            swarm_id=swarm_id,
            topology=topology,
            agent_count=len(agents),
        )
        return result

    async def optimize_swarm_strategy(self, swarm_id: str, strategy: str) -> dict[str, Any]:
        """Apply a consensus strategy optimization for a swarm."""
        if swarm_id not in self._swarm_data:
            raise ValueError(f"Swarm not found: {swarm_id}")

        if strategy not in _CONSENSUS_STRATEGIES:
            raise ValueError(
                f"Unknown consensus strategy '{strategy}'. Valid options: {_CONSENSUS_STRATEGIES}"
            )

        result = {
            "swarm_id": swarm_id,
            "previous_strategy": "unknown",
            "recommended_strategy": strategy,
            "optimized_at": _utcnow().isoformat(),
        }

        log.info("Swarm strategy optimized", swarm_id=swarm_id, strategy=strategy)
        return result
