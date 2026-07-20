"""Recommendation engine — generates, manages, and tracks recommendations."""

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from agentic_os.domain.learning import Recommendation, RecommendationStatus
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.learning import RecommendationPort

log = get_logger("learning.recommendation")


def _utcnow() -> datetime:
    return datetime.now(UTC)


_RECOMMENDATION_TEMPLATES: dict[str, dict[str, Any]] = {
    "engine_selection": {
        "title": "Optimize Engine Selection Strategy",
        "description_template": (
            "Current engine selection does not account for task-specific performance "
            "characteristics. Consider using {engine} for {task_type} tasks based on "
            "historical success rates."
        ),
        "confidence_base": 0.75,
        "alternatives": [
            "llm-based selection",
            "round-robin fallback",
            "cost-weighted selection",
        ],
    },
    "routing_strategy": {
        "title": "Adjust Routing Strategy",
        "description_template": (
            "Routing strategy should be updated to {strategy} based on observed latency "
            "patterns. Current approach results in {metric} for {task_type} tasks."
        ),
        "confidence_base": 0.7,
        "alternatives": [
            "latency-based routing",
            "capability-based routing",
            "cost-aware routing",
            "random routing",
        ],
    },
    "swarm_topology": {
        "title": "Optimize Swarm Topology",
        "description_template": (
            "Swarm topology can be improved by switching to {topology} topology. "
            "Current topology shows {metric} in agent coordination overhead."
        ),
        "confidence_base": 0.65,
        "alternatives": ["hierarchical", "mesh", "star", "ring", "tree"],
    },
    "retry_policy": {
        "title": "Refine Retry Policy",
        "description_template": (
            "Retry policy should use {retry_type} with {max_retries} max retries. "
            "Current policy causes {metric} in execution overhead."
        ),
        "confidence_base": 0.8,
        "alternatives": [
            "exponential backoff",
            "immediate retry",
            "circuit breaker",
            "dead letter queue",
        ],
    },
    "execution_mode": {
        "title": "Change Execution Mode",
        "description_template": (
            "Switch execution mode to {mode} for {task_type} tasks. Current mode shows "
            "{metric} in resource utilization."
        ),
        "confidence_base": 0.7,
        "alternatives": ["sequential", "parallel", "fan-out", "pipeline", "batch"],
    },
}


class RecommendationEngine(RecommendationPort):
    """In-memory recommendation engine implementing RecommendationPort.

    Generates concrete, actionable recommendations for various optimization
    categories based on context data. Stores recommendations in memory
    with full CRUD lifecycle management.
    """

    def __init__(self) -> None:
        self._recommendations: dict[str, Recommendation] = {}

    # ── CRUD ──

    async def create_recommendation(self, recommendation: Recommendation) -> Recommendation:
        """Store a pre-built recommendation directly."""
        self._recommendations[recommendation.id] = recommendation
        log.info(
            "Stored recommendation", rec_id=recommendation.id, category=recommendation.category
        )
        return recommendation

    async def get_recommendation(self, recommendation_id: str) -> Recommendation | None:
        return self._recommendations.get(recommendation_id)

    async def update_recommendation(
        self, recommendation_id: str, updates: dict[str, Any]
    ) -> Recommendation:
        rec = self._recommendations.get(recommendation_id)
        if rec is None:
            raise ValueError(f"Recommendation not found: {recommendation_id}")
        filtered = {k: v for k, v in updates.items() if hasattr(rec, k)}
        updated = replace(rec, **filtered)
        self._recommendations[recommendation_id] = updated
        log.info("Updated recommendation", rec_id=recommendation_id, updates=list(filtered))
        return updated

    async def delete_recommendation(self, recommendation_id: str) -> None:
        if recommendation_id not in self._recommendations:
            raise ValueError(f"Recommendation not found: {recommendation_id}")
        del self._recommendations[recommendation_id]
        log.info("Deleted recommendation", rec_id=recommendation_id)

    async def list_recommendations(
        self,
        status: RecommendationStatus | None = None,
        limit: int = 50,
    ) -> Sequence[Recommendation]:
        results = list(self._recommendations.values())
        if status is not None:
            results = [r for r in results if r.status == status]
        results.sort(key=lambda r: r.created_at, reverse=True)
        return results[:limit]

    # ── Generate ──

    async def generate_recommendation(
        self, category: str, context: dict[str, Any]
    ) -> Recommendation:
        template = _RECOMMENDATION_TEMPLATES.get(category)
        if template is None:
            rec = Recommendation(
                category=category,
                title=f"General Optimization for {category}",
                description=(
                    f"Analyze {category} patterns and optimize based on context: {context}"
                ),
                confidence=0.5,
                evidence="No specific template available for this category.",
                alternatives=(),
                source="recommendation_engine",
            )
            self._recommendations[rec.id] = rec
            log.info("Generated generic recommendation", category=category, rec_id=rec.id)
            return rec

        task_type = context.get("task_type", "general")
        engine = context.get("engine", "appropriate engine")
        strategy = context.get("strategy", "adaptive")
        topology = context.get("topology", "flexible")
        retry_type = context.get("retry_type", "adaptive")
        max_retries = context.get("max_retries", 3)
        mode = context.get("mode", "adaptive")
        metric = context.get("metric", "suboptimal performance")

        confidence = template["confidence_base"]
        if len(context) > 3:
            confidence = min(1.0, confidence + 0.1)
        if "evidence" in context:
            confidence = min(1.0, confidence + 0.15)

        description = template["description_template"].format(
            engine=engine,
            task_type=task_type,
            strategy=strategy,
            topology=topology,
            retry_type=retry_type,
            max_retries=max_retries,
            mode=mode,
            metric=metric,
        )

        evidence_parts: list[str] = []
        if "evidence" in context:
            evidence_parts.append(str(context["evidence"]))
        if task_type != "general":
            evidence_parts.append(f"Analysis based on {task_type} task patterns")
        evidence = (
            "; ".join(evidence_parts)
            if evidence_parts
            else f"Generated from {category} template with confidence {confidence:.0%}"
        )

        alternatives = tuple(template["alternatives"][:3])

        rec = Recommendation(
            category=category,
            title=template["title"],
            description=description,
            confidence=confidence,
            evidence=evidence,
            alternatives=alternatives,
            source="recommendation_engine",
        )
        self._recommendations[rec.id] = rec
        log.info(
            "Generated recommendation",
            category=category,
            rec_id=rec.id,
            confidence=confidence,
        )
        return rec

    # ── Lifecycle ──

    async def apply_recommendation(self, recommendation_id: str) -> Recommendation:
        rec = self._recommendations.get(recommendation_id)
        if rec is None:
            raise ValueError(f"Recommendation not found: {recommendation_id}")
        updated = replace(
            rec,
            status=RecommendationStatus.APPLIED,
            applied_at=_utcnow(),
        )
        self._recommendations[recommendation_id] = updated
        log.info("Applied recommendation", rec_id=recommendation_id)
        return updated

    async def dismiss_recommendation(self, recommendation_id: str) -> Recommendation:
        rec = self._recommendations.get(recommendation_id)
        if rec is None:
            raise ValueError(f"Recommendation not found: {recommendation_id}")
        updated = replace(rec, status=RecommendationStatus.DISMISSED)
        self._recommendations[recommendation_id] = updated
        log.info("Dismissed recommendation", rec_id=recommendation_id)
        return updated
