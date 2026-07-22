"""Evaluation engine — scores and assesses engines, strategies, and optimizations."""

from collections.abc import Sequence
from datetime import UTC, datetime

from agentic_os.domain.learning import Evaluation
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.learning import EvaluationPort

log = get_logger("learning.evaluation")

# Weights for the composite score computation
_WEIGHT_LATENCY = 0.3
_WEIGHT_COST = 0.2
_WEIGHT_SUCCESS_RATE = 0.3
_WEIGHT_QUALITY = 0.2


def _utcnow() -> datetime:
    return datetime.now(UTC)


class EvaluationEngine(EvaluationPort):
    """In-memory evaluation engine implementing ``EvaluationPort``.

    Computes composite scores from raw metrics and stores evaluation
    results for later retrieval.
    """

    def __init__(self) -> None:
        self._evaluations: dict[str, Evaluation] = {}

    async def evaluate(
        self,
        target_id: str,
        target_type: str,
        metrics: dict[str, float],
    ) -> Evaluation:
        """Evaluate a target and produce a score.

        The composite score is computed from:
          - latency (lower is better, inverted)
          - cost (lower is better, inverted)
          - success_rate (higher is better)
          - quality_score (higher is better)

        Args:
            target_id: The identifier of the target being evaluated.
            target_type: The type of target (e.g. "engine", "strategy").
            metrics: A dict of metric names to values.

        Returns:
            An ``Evaluation`` with the computed score and pass/fail status.
        """
        score = self._compute_composite_score(metrics)
        passed = score >= 0.5

        evaluation = Evaluation(
            target_id=target_id,
            target_type=target_type,
            score=round(score, 4),
            metrics=metrics,
            passed=passed,
            details=self._build_details(metrics, score, passed),
        )

        self._evaluations[evaluation.id] = evaluation
        log.info(
            "Evaluation completed",
            target_id=target_id,
            target_type=target_type,
            score=score,
            passed=passed,
        )
        return evaluation

    async def get_evaluation(self, evaluation_id: str) -> Evaluation | None:
        return self._evaluations.get(evaluation_id)

    async def list_evaluations(self, target_id: str) -> Sequence[Evaluation]:
        results = [e for e in self._evaluations.values() if e.target_id == target_id]
        results.sort(key=lambda e: e.evaluated_at, reverse=True)
        return results

    async def list_all_evaluations(
        self,
        target_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[Evaluation]:
        results = list(self._evaluations.values())
        if target_type is not None:
            results = [e for e in results if e.target_type == target_type]
        results.sort(key=lambda e: e.evaluated_at, reverse=True)
        return results[offset : offset + limit]

    # ── Internals ──

    @staticmethod
    def _compute_composite_score(metrics: dict[str, float]) -> float:
        """Compute a normalized composite score (0..1) from raw metrics."""
        if not metrics:
            return 0.5

        latency = metrics.get("latency_ms") or metrics.get("avg_latency_ms", 500)
        cost = metrics.get("cost") or metrics.get("avg_cost", 0.01)
        success_rate = metrics.get("success_rate", 0.5)
        quality = metrics.get("quality_score") or metrics.get("avg_quality_score", 0.5)

        # Invert latency and cost so higher is better (max reference: 5000ms, $0.10)
        latency_score = max(0.0, 1.0 - (latency / 5000.0))
        cost_score = max(0.0, 1.0 - (cost / 0.10))

        score = (
            _WEIGHT_LATENCY * latency_score
            + _WEIGHT_COST * cost_score
            + _WEIGHT_SUCCESS_RATE * success_rate
            + _WEIGHT_QUALITY * quality
        )
        return max(0.0, min(1.0, score))

    @staticmethod
    def _build_details(
        metrics: dict[str, float],
        score: float,
        passed: bool,
    ) -> str:
        parts: list[str] = []
        for key, val in sorted(metrics.items()):
            parts.append(f"{key}={val:.4f}")
        status = "PASS" if passed else "FAIL"
        return f"Score={score:.4f} Status={status} Metrics=[{', '.join(parts)}]"
