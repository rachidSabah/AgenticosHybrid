"""BrainStatistics — aggregate metrics across all registered brains.

Computes summary statistics from the current set of :class:`BrainRecord`
instances including totals, averages, status distributions, and
vendor/type breakdowns.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agentic_os.domain.brains import BrainRecord
from agentic_os.infrastructure.logging import get_logger

log = get_logger("brains.stats")


@dataclass(frozen=True)
class BrainStatsSnapshot:
    """Immutable snapshot of aggregate brain statistics."""

    total_brains: int = 0
    total_healthy: int = 0
    total_unhealthy: int = 0
    total_connected: int = 0
    total_disconnected: int = 0
    total_paused: int = 0
    total_failed: int = 0
    total_busy: int = 0
    total_idle: int = 0
    total_executing: int = 0
    total_removed: int = 0
    total_shutdown: int = 0
    total_recovering: int = 0
    total_local_cli: int = 0
    total_cloud_api: int = 0
    total_orchestrator: int = 0
    total_mcp_server: int = 0
    total_custom_type: int = 0
    avg_health: float = 0.0
    avg_memory_usage: float = 0.0
    avg_cpu_usage: float = 0.0
    avg_latency: float = 0.0
    avg_throughput: float = 0.0
    avg_uptime: float = 0.0
    total_tasks_in_flight: int = 0
    total_queue_depth: int = 0
    total_error_count: int = 0
    vendor_breakdown: dict[str, int] = field(default_factory=dict)
    runtime_breakdown: dict[str, int] = field(default_factory=dict)
    capacity_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable dict."""
        return {
            "total_brains": self.total_brains,
            "total_healthy": self.total_healthy,
            "total_unhealthy": self.total_unhealthy,
            "total_connected": self.total_connected,
            "total_disconnected": self.total_disconnected,
            "total_paused": self.total_paused,
            "total_failed": self.total_failed,
            "total_busy": self.total_busy,
            "total_idle": self.total_idle,
            "total_executing": self.total_executing,
            "total_removed": self.total_removed,
            "total_shutdown": self.total_shutdown,
            "total_recovering": self.total_recovering,
            "total_local_cli": self.total_local_cli,
            "total_cloud_api": self.total_cloud_api,
            "total_orchestrator": self.total_orchestrator,
            "total_mcp_server": self.total_mcp_server,
            "total_custom_type": self.total_custom_type,
            "avg_health": round(self.avg_health, 1),
            "avg_memory_usage": round(self.avg_memory_usage, 1),
            "avg_cpu_usage": round(self.avg_cpu_usage, 1),
            "avg_latency": round(self.avg_latency, 2),
            "avg_throughput": round(self.avg_throughput, 2),
            "avg_uptime": round(self.avg_uptime, 1),
            "total_tasks_in_flight": self.total_tasks_in_flight,
            "total_queue_depth": self.total_queue_depth,
            "total_error_count": self.total_error_count,
            "vendor_breakdown": dict(self.vendor_breakdown),
            "runtime_breakdown": dict(self.runtime_breakdown),
            "capacity_score": round(self.capacity_score, 1),
        }


class BrainStatistics:
    """Aggregate metrics across all brains.

    Computes :class:`BrainStatsSnapshot` snapshots from a provided list
    of brain records.  This class is stateless by design — each call to
    :meth:`compute` produces a fresh snapshot.

    Thread-safety
    -------------
    All public methods are idempotent and safe to call concurrently.
    """

    async def compute(self, brains: list[BrainRecord]) -> BrainStatsSnapshot:
        """Compute aggregate statistics from a list of brain records.

        Args:
            brains: The current list of registered brain records.

        Returns:
            A frozen :class:`BrainStatsSnapshot`.
        """
        total = len(brains)
        if total == 0:
            return BrainStatsSnapshot()

        status_counts: dict[str, int] = {}
        type_counts: dict[str, int] = {}
        vendor_counts: dict[str, int] = {}
        runtime_counts: dict[str, int] = {}

        sum_health = 0.0
        sum_memory = 0.0
        sum_cpu = 0.0
        sum_latency = 0.0
        sum_throughput = 0.0
        sum_uptime = 0.0
        sum_tasks = 0
        sum_queue = 0
        sum_errors = 0

        for brain in brains:
            s = brain.status.value
            status_counts[s] = status_counts.get(s, 0) + 1

            t = brain.brain_type.value
            type_counts[t] = type_counts.get(t, 0) + 1

            v = brain.vendor.value
            vendor_counts[v] = vendor_counts.get(v, 0) + 1

            r = brain.runtime.value
            runtime_counts[r] = runtime_counts.get(r, 0) + 1

            sum_health += brain.health
            sum_memory += brain.memory_usage
            sum_cpu += brain.cpu_usage
            sum_latency += brain.latency
            sum_throughput += brain.throughput
            sum_uptime += brain.uptime
            sum_tasks += brain.current_tasks
            sum_queue += brain.queue_depth
            sum_errors += brain.error_count

        # ── Capacity score ──────────────────────────────────────────────────
        # A rough heuristic: 0-100, higher is better.
        healthy_ratio = status_counts.get("healthy", 0) / max(total, 1)
        avg_health_val = sum_health / max(total, 1)
        error_penalty = min(sum_errors * 2.0, 30.0)
        capacity = (healthy_ratio * 50.0) + (avg_health_val * 0.5) - error_penalty
        capacity = max(0.0, min(100.0, capacity))

        return BrainStatsSnapshot(
            total_brains=total,
            total_healthy=status_counts.get("healthy", 0),
            total_unhealthy=status_counts.get("unhealthy", 0),
            total_connected=status_counts.get("connected", 0),
            total_disconnected=status_counts.get("disconnected", 0),
            total_paused=status_counts.get("paused", 0),
            total_failed=status_counts.get("failed", 0),
            total_busy=status_counts.get("busy", 0),
            total_idle=status_counts.get("idle", 0),
            total_executing=status_counts.get("executing", 0),
            total_removed=status_counts.get("removed", 0),
            total_shutdown=status_counts.get("shutdown", 0),
            total_recovering=status_counts.get("recovering", 0),
            total_local_cli=type_counts.get("local_cli", 0),
            total_cloud_api=type_counts.get("cloud_api", 0),
            total_orchestrator=type_counts.get("orchestrator", 0),
            total_mcp_server=type_counts.get("mcp_server", 0),
            total_custom_type=type_counts.get("custom", 0),
            avg_health=sum_health / max(total, 1),
            avg_memory_usage=sum_memory / max(total, 1),
            avg_cpu_usage=sum_cpu / max(total, 1),
            avg_latency=sum_latency / max(total, 1),
            avg_throughput=sum_throughput / max(total, 1),
            avg_uptime=sum_uptime / max(total, 1),
            total_tasks_in_flight=sum_tasks,
            total_queue_depth=sum_queue,
            total_error_count=sum_errors,
            vendor_breakdown=vendor_counts,
            runtime_breakdown=runtime_counts,
            capacity_score=capacity,
        )
