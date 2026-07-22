"""Prompt optimization manager — registers, tracks, and optimizes prompt templates."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from agentic_os.domain.learning import ExecutionHistory
from agentic_os.infrastructure.logging import get_logger

log = get_logger("learning.prompt")


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class PromptTemplate:
    """Metadata for a registered prompt template."""

    template_id: str
    name: str
    content: str
    task_types: list[str]
    version: str = "1.0.0"
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "template_id": self.template_id,
            "name": self.name,
            "content": self.content,
            "task_types": list(self.task_types),
            "version": self.version,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass
class PromptPerformance:
    """Performance metrics for a prompt template."""

    template_id: str
    task_type: str
    total_uses: int = 0
    avg_duration_ms: float = 0.0
    avg_cost: float = 0.0
    success_count: int = 0
    failure_count: int = 0
    quality_scores: list[float] = field(default_factory=list)
    avg_quality_score: float = 0.0

    @property
    def success_rate(self) -> float:
        total = self.success_count + self.failure_count
        return self.success_count / total if total > 0 else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "template_id": self.template_id,
            "task_type": self.task_type,
            "total_uses": self.total_uses,
            "avg_duration_ms": self.avg_duration_ms,
            "avg_cost": self.avg_cost,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "avg_quality_score": self.avg_quality_score,
            "success_rate": self.success_rate,
        }


class PromptOptimizationManager:
    """Manages prompt template registration, performance tracking, and optimization.

    Tracks which prompt templates perform best for which task types
    and generates optimization recommendations based on performance data.
    """

    def __init__(self) -> None:
        self._templates: dict[str, PromptTemplate] = {}
        self._performance: dict[str, PromptPerformance] = {}
        self._execution_history: dict[str, ExecutionHistory] = {}

    def record_execution(self, history: ExecutionHistory) -> ExecutionHistory:
        self._execution_history[history.id] = history
        return history

    async def register_prompt_template(
        self,
        template_id: str,
        name: str,
        content: str,
        task_types: Sequence[str],
        version: str = "1.0.0",
    ) -> PromptTemplate:
        template = PromptTemplate(
            template_id=template_id,
            name=name,
            content=content,
            task_types=list(task_types),
            version=version,
        )
        self._templates[template_id] = template

        for tt in task_types:
            perf_key = f"{template_id}:{tt}"
            if perf_key not in self._performance:
                self._performance[perf_key] = PromptPerformance(
                    template_id=template_id,
                    task_type=tt,
                )

        log.info("Registered prompt template", template_id=template_id, name=name)
        return template

    async def track_prompt_performance(
        self,
        template_id: str,
        task_type: str,
        duration_ms: float = 0.0,
        cost: float = 0.0,
        success: bool = True,
        quality_score: float | None = None,
    ) -> None:
        perf_key = f"{template_id}:{task_type}"
        perf = self._performance.get(perf_key)

        if perf is None:
            perf = PromptPerformance(
                template_id=template_id,
                task_type=task_type,
            )
            self._performance[perf_key] = perf

        # Update rolling averages
        old_total = perf.total_uses
        new_total = old_total + 1
        perf.total_uses = new_total
        perf.avg_duration_ms = (
            (perf.avg_duration_ms * old_total + duration_ms) / new_total
            if old_total > 0
            else duration_ms
        )
        perf.avg_cost = (perf.avg_cost * old_total + cost) / new_total if old_total > 0 else cost
        if success:
            perf.success_count += 1
        else:
            perf.failure_count += 1

        if quality_score is not None:
            perf.quality_scores.append(quality_score)
            perf.avg_quality_score = sum(perf.quality_scores) / len(perf.quality_scores)

        log.debug(
            "Tracked prompt performance",
            template_id=template_id,
            task_type=task_type,
            total_uses=new_total,
        )

    async def analyze_prompts(self) -> dict[str, Any]:
        """Analyze all tracked prompt templates and return performance breakdown."""
        if not self._templates:
            return {"templates": {}, "total_templates": 0}

        analysis: dict[str, Any] = {}
        for tid, template in self._templates.items():
            task_performance: dict[str, Any] = {}
            for tt in template.task_types:
                perf_key = f"{tid}:{tt}"
                perf = self._performance.get(perf_key)
                if perf and perf.total_uses > 0:
                    task_performance[tt] = perf.to_dict()

            analysis[tid] = {
                "template": template.to_dict(),
                "performance": task_performance,
            }

        return {
            "templates": analysis,
            "total_templates": len(self._templates),
            "total_tracked_executions": sum(p.total_uses for p in self._performance.values()),
        }

    async def recommend_prompt_optimizations(self) -> Sequence[dict[str, Any]]:
        """Generate prompt optimization recommendations based on performance."""
        recommendations: list[dict[str, Any]] = []

        # Group performance by task type to find best templates
        task_type_performance: dict[str, list[PromptPerformance]] = {}
        for perf in self._performance.values():
            if perf.total_uses > 0:
                task_type_performance.setdefault(perf.task_type, []).append(perf)

        for task_type, perfs in task_type_performance.items():
            if len(perfs) < 2:
                continue

            # Sort by quality score, then success rate, then duration
            sorted_perfs = sorted(
                perfs,
                key=lambda p: (
                    p.avg_quality_score,
                    p.success_rate,
                    -p.avg_duration_ms,
                ),
                reverse=True,
            )

            best = sorted_perfs[0]
            for perf in sorted_perfs[1:]:
                quality_gap = best.avg_quality_score - perf.avg_quality_score
                success_gap = best.success_rate - perf.success_rate
                duration_penalty = perf.avg_duration_ms - best.avg_duration_ms

                threshold = 0
                reasons = []
                if quality_gap > 0.1:
                    threshold += 1
                    reasons.append(f"quality ({quality_gap:.2f} higher)")
                if success_gap > 0.05:
                    threshold += 1
                    reasons.append(f"success rate ({success_gap:.1%} higher)")
                if duration_penalty > 1000:
                    threshold += 1
                    reasons.append(f"latency ({duration_penalty:.0f}ms lower)")

                if threshold > 0:
                    best_template = self._templates.get(best.template_id)
                    current_template = self._templates.get(perf.template_id)
                    rec: dict[str, Any] = {
                        "id": f"prompt-opt-{int(_utcnow().timestamp())}",
                        "task_type": task_type,
                        "type": "prompt_selection",
                        "title": f"Optimize Prompt for {task_type} Tasks",
                        "description": (
                            f"Template '{perf.template_id}' for {task_type} tasks "
                            f"underperforms '{best.template_id}' in "
                            f"{', '.join(reasons)}. Consider switching."
                        ),
                        "current_template": current_template.name
                        if current_template
                        else perf.template_id,
                        "recommended_template": best_template.name
                        if best_template
                        else best.template_id,
                        "confidence": round(0.5 + threshold * 0.15, 2),
                        "estimated_improvement": round(quality_gap * 100 + success_gap * 100, 1),
                        "current_metrics": {
                            "avg_quality": perf.avg_quality_score,
                            "success_rate": perf.success_rate,
                            "avg_duration_ms": perf.avg_duration_ms,
                            "avg_cost": perf.avg_cost,
                        },
                        "target_metrics": {
                            "avg_quality": best.avg_quality_score,
                            "success_rate": best.success_rate,
                            "avg_duration_ms": best.avg_duration_ms,
                            "avg_cost": best.avg_cost,
                        },
                        "status": "active",
                    }
                    recommendations.append(rec)
                    log.info(
                        "Prompt optimization recommended",
                        task_type=task_type,
                        best=best.template_id,
                        current=perf.template_id,
                    )

        return recommendations
