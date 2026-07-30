"""Phase 17 — RefactoringAdvisor + PerformanceOptimizer.

Two specialized analyzers that produce refactoring and performance
improvement proposals. Both are pure consumers of existing metrics.
"""

from __future__ import annotations

from typing import Any

from agentic_os.core.evolution.domain import (
    ImprovementPriority,
    ImprovementProposal,
    ImprovementType,
)
from agentic_os.infrastructure.logging import get_logger

log = get_logger("evolution.advisors")


class RefactoringAdvisor:
    """Proposes refactoring improvements based on code health signals."""

    def __init__(self) -> None:
        self._proposals: list[ImprovementProposal] = []
        self._stats: dict[str, int] = {"total_proposals": 0}

    async def analyze(self, code_health: dict[str, Any]) -> list[ImprovementProposal]:
        """Analyze code health metrics and propose refactors."""
        proposals: list[ImprovementProposal] = []

        # Check for high-complexity modules
        for module, metrics in code_health.items():
            complexity = float(metrics.get("complexity", 0))
            if complexity > 15:
                proposal = ImprovementProposal(
                    type=ImprovementType.REFACTORING,
                    title=f"Refactor high-complexity module: {module}",
                    description=(
                        f"Module '{module}' has complexity {complexity:.0f} "
                        f"(threshold: 15). Recommend splitting into smaller units."
                    ),
                    rationale=f"Complexity reduction for {module}",
                    priority=ImprovementPriority.MEDIUM,
                    target_module=module,
                    expected_impact=0.3,
                    confidence=0.7,
                    risk_score=0.3,
                    implementation_plan={
                        "action": "split_module",
                        "module": module,
                        "current_complexity": complexity,
                        "target_complexity": 10,
                    },
                )
                proposals.append(proposal)
                self._stats["total_proposals"] += 1

        self._proposals.extend(proposals)
        return proposals

    def list_proposals(self) -> list[ImprovementProposal]:
        return list(self._proposals)

    def stats(self) -> dict[str, Any]:
        return dict(self._stats)


class PerformanceOptimizer:
    """Proposes performance optimizations based on metrics."""

    def __init__(self) -> None:
        self._proposals: list[ImprovementProposal] = []
        self._stats: dict[str, int] = {"total_proposals": 0}

    async def analyze(self, perf_metrics: dict[str, Any]) -> list[ImprovementProposal]:
        """Analyze performance metrics and propose optimizations."""
        proposals: list[ImprovementProposal] = []

        # Check for slow endpoints
        api_latencies: dict[str, float] = perf_metrics.get("api_latencies", {})
        for endpoint, latency in api_latencies.items():
            if latency > 1000:  # >1s
                proposal = ImprovementProposal(
                    type=ImprovementType.PERFORMANCE_OPTIMIZATION,
                    title=f"Optimize slow endpoint: {endpoint}",
                    description=(
                        f"Endpoint '{endpoint}' has {latency:.0f}ms latency "
                        f"(target: <1000ms). Recommend caching or query optimization."
                    ),
                    rationale=f"Latency reduction for {endpoint}",
                    priority=ImprovementPriority.HIGH,
                    target_module=endpoint,
                    expected_impact=0.6,
                    confidence=0.8,
                    risk_score=0.15,
                    implementation_plan={
                        "action": "optimize_endpoint",
                        "endpoint": endpoint,
                        "current_latency_ms": latency,
                        "target_latency_ms": 500,
                        "strategies": ["cache", "query_optimization", "index"],
                    },
                )
                proposals.append(proposal)
                self._stats["total_proposals"] += 1

        # Check for high memory usage
        memory_usage = perf_metrics.get("memory_usage_mb", 0)
        if memory_usage > 500:
            proposal = ImprovementProposal(
                type=ImprovementType.PERFORMANCE_OPTIMIZATION,
                title="Reduce memory footprint",
                description=(
                    f"Memory usage is {memory_usage:.0f}MB (threshold: 500MB). "
                    "Recommend memory profiling + cache eviction tuning."
                ),
                rationale="Memory optimization",
                priority=ImprovementPriority.MEDIUM,
                expected_impact=0.4,
                confidence=0.6,
                risk_score=0.2,
                implementation_plan={
                    "action": "reduce_memory",
                    "current_mb": memory_usage,
                    "target_mb": 400,
                    "strategies": ["cache_eviction", "object_pooling", "lazy_loading"],
                },
            )
            proposals.append(proposal)
            self._stats["total_proposals"] += 1

        self._proposals.extend(proposals)
        return proposals

    def list_proposals(self) -> list[ImprovementProposal]:
        return list(self._proposals)

    def stats(self) -> dict[str, Any]:
        return dict(self._stats)
