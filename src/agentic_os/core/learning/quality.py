"""Quality optimizer — analyzes output quality and recommends improvements."""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from agentic_os.domain.learning import (
    ExecutionHistory,
    QualityMetrics,
)
from agentic_os.infrastructure.logging import get_logger

log = get_logger("learning.quality")


def _utcnow() -> datetime:
    return datetime.now(UTC)


class QualityOptimizer:
    """In-memory quality optimizer that analyzes output quality.

    Tracks quality scores per engine and provider, detects quality
    degradation, and generates quality improvement recommendations.
    """

    def __init__(self) -> None:
        self._execution_history: dict[str, ExecutionHistory] = {}
        self._quality_scores: dict[str, list[float]] = {}
        self._quality_metrics_history: list[QualityMetrics] = []
        self._quality_recommendations: dict[str, dict[str, Any]] = {}

    def record_execution(self, history: ExecutionHistory) -> ExecutionHistory:
        self._execution_history[history.id] = history
        return history

    def record_quality_score(self, target_id: str, target_type: str, score: float) -> None:
        key = f"{target_type}:{target_id}"
        self._quality_scores.setdefault(key, []).append(score)
        log.debug("Recorded quality score", target=key, score=score)

    async def track_quality(
        self, execution_id: str, score: float, engine: str, provider: str = ""
    ) -> None:
        engine_key = f"engine:{engine}"
        self._quality_scores.setdefault(engine_key, []).append(score)
        if provider:
            provider_key = f"provider:{provider}"
            self._quality_scores.setdefault(provider_key, []).append(score)
        existing = self._execution_history.get(execution_id)
        if existing is not None:
            meta = dict(existing.metadata) if existing.metadata else {}
            meta["quality_score"] = score
            updated = ExecutionHistory(
                id=existing.id,
                execution_id=existing.execution_id,
                engine_type=existing.engine_type,
                engine_name=existing.engine_name,
                task_type=existing.task_type,
                status=existing.status,
                duration_ms=existing.duration_ms,
                cost=existing.cost,
                retry_count=existing.retry_count,
                resource_usage=existing.resource_usage,
                error_type=existing.error_type,
                swarm_id=existing.swarm_id,
                plan_id=existing.plan_id,
                model_used=existing.model_used,
                prompt_template=existing.prompt_template,
                user_id=existing.user_id,
                workspace_id=existing.workspace_id,
                metadata=meta,
                executed_at=existing.executed_at,
            )
            self._execution_history[execution_id] = updated
        log.debug("Tracked quality", execution_id=execution_id, score=score, engine=engine)

    async def analyze_quality(self) -> QualityMetrics:
        if not self._quality_scores:
            metrics = QualityMetrics(period_start=_utcnow(), period_end=_utcnow())
            self._quality_metrics_history.append(metrics)
            return metrics

        all_scores = [s for scores in self._quality_scores.values() for s in scores]
        if not all_scores:
            metrics = QualityMetrics(period_start=_utcnow(), period_end=_utcnow())
            self._quality_metrics_history.append(metrics)
            return metrics

        avg_score = sum(all_scores) / len(all_scores)
        min_score = min(all_scores)
        max_score = max(all_scores)

        quality_by_engine: dict[str, float] = {}
        quality_by_provider: dict[str, float] = {}
        for key, scores in self._quality_scores.items():
            avg = sum(scores) / len(scores)
            if key.startswith("engine:"):
                quality_by_engine[key[7:]] = round(avg, 3)
            elif key.startswith("provider:"):
                quality_by_provider[key[9:]] = round(avg, 3)

        improvement_pct = 0.0
        if len(all_scores) >= 10:
            recent = all_scores[-5:]
            older = all_scores[:-5]
            recent_avg = sum(recent) / len(recent)
            older_avg = sum(older) / len(older)
            if older_avg > 0:
                improvement_pct = round(((recent_avg - older_avg) / older_avg) * 100, 1)

        metrics = QualityMetrics(
            avg_quality_score=round(avg_score, 3),
            min_quality_score=round(min_score, 3),
            max_quality_score=round(max_score, 3),
            quality_by_engine=quality_by_engine,
            quality_by_provider=quality_by_provider,
            improvement_pct=improvement_pct,
            period_start=_utcnow(),
            period_end=_utcnow(),
        )
        self._quality_metrics_history.append(metrics)
        log.info("Quality analysis complete", avg_score=round(avg_score, 3))
        return metrics

    async def get_quality_metrics(
        self, period_start: str | None = None, period_end: str | None = None
    ) -> QualityMetrics:
        if not self._quality_metrics_history:
            return QualityMetrics(period_start=_utcnow(), period_end=_utcnow())
        return self._quality_metrics_history[-1]

    async def recommend_quality_improvements(self) -> Sequence[dict[str, Any]]:
        recommendations: list[dict[str, Any]] = []

        # Group scores by engine and provider
        engine_scores: dict[str, list[float]] = {}
        provider_scores: dict[str, list[float]] = {}
        for key, scores in self._quality_scores.items():
            if key.startswith("engine:"):
                engine_scores[key[7:]] = scores
            elif key.startswith("provider:"):
                provider_scores[key[9:]] = scores

        if not engine_scores:
            return recommendations

        # Find engines with low quality
        avg_by_engine = {eng: sum(scores) / len(scores) for eng, scores in engine_scores.items()}
        sorted_engines = sorted(avg_by_engine, key=lambda k: avg_by_engine[k], reverse=True)

        if len(sorted_engines) >= 2:
            top_engine = sorted_engines[0]
            top_score = avg_by_engine[top_engine]

            for engine in sorted_engines[1:]:
                score = avg_by_engine[engine]
                if top_score - score > 0.1:
                    gap = ((top_score - score) / top_score) * 100 if top_score > 0 else 0
                    rec: dict[str, Any] = {
                        "id": f"qual-engine-{int(_utcnow().timestamp())}",
                        "type": "engine_quality_gap",
                        "title": f"Address Quality Gap in {engine}",
                        "description": (
                            f"Engine '{engine}' average quality ({score:.2f}) is "
                            f"{gap:.0f}% below top performer '{top_engine}' ({top_score:.2f})."
                        ),
                        "engine": engine,
                        "current_score": round(score, 3),
                        "target_score": round(top_score, 3),
                        "top_engine": top_engine,
                        "confidence": min(0.9, 0.5 + gap / 200),
                        "status": "active",
                    }
                    recommendations.append(rec)
                    self._quality_recommendations[rec["id"]] = rec
                    log.info("Quality gap detected", engine=engine, gap=gap)

        # Check for quality degradation over time
        for engine, scores in engine_scores.items():
            if len(scores) >= 6:
                recent = scores[-3:]
                older = scores[:-3]
                recent_avg = sum(recent) / len(recent)
                older_avg = sum(older) / len(older)
                if older_avg > 0 and recent_avg < older_avg * 0.9:
                    rec = {
                        "id": f"qual-degrade-{int(_utcnow().timestamp())}",
                        "type": "quality_degradation",
                        "title": f"Quality Degradation in {engine}",
                        "description": (
                            f"Quality scores for '{engine}' declined from {older_avg:.2f} "
                            f"to {recent_avg:.2f} over last {len(recent)} measurements."
                        ),
                        "engine": engine,
                        "previous_avg": round(older_avg, 3),
                        "current_avg": round(recent_avg, 3),
                        "confidence": 0.7,
                        "status": "active",
                    }
                    recommendations.append(rec)
                    self._quality_recommendations[rec["id"]] = rec
                    log.info("Quality degradation detected", engine=engine)

        return recommendations
