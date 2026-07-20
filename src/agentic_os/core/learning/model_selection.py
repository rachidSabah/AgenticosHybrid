"""Model selection engine — selects the best models based on performance data."""

from collections.abc import Sequence
from typing import Any

from agentic_os.domain.learning import PerformanceProfile
from agentic_os.infrastructure.logging import get_logger

log = get_logger("learning.model_selection")

_WEIGHT_LATENCY = 0.3
_WEIGHT_COST = 0.3
_WEIGHT_SUCCESS_RATE = 0.4


class ModelSelectionEngine:
    """Selects the best models based on registered performance profiles.

    Stores ``PerformanceProfile`` records per model and computes scores
    based on a weighted combination of latency, cost, and success rate.
    """

    def __init__(self) -> None:
        self._profiles: dict[str, PerformanceProfile] = {}

    # ── Registration ──

    def register_model_performance(self, profile: PerformanceProfile) -> PerformanceProfile:
        """Register or update a model's performance profile.

        Args:
            profile: The ``PerformanceProfile`` for a model.

        Returns:
            The stored profile.
        """
        self._profiles[profile.target_id] = profile
        log.debug(
            "Model performance registered",
            target_id=profile.target_id,
            sample_count=profile.sample_count,
        )
        return profile

    def get_model_performance(self, model_id: str) -> PerformanceProfile | None:
        """Get the performance profile for a specific model."""
        return self._profiles.get(model_id)

    def list_model_performance(
        self,
        target_type: str | None = None,
        min_samples: int = 1,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[PerformanceProfile]:
        """List performance profiles with optional filtering.

        Args:
            target_type: Optional filter by target type.
            min_samples: Minimum number of samples required.
            limit: Maximum records to return.
            offset: Number of records to skip.

        Returns:
            A sequence of matching ``PerformanceProfile`` records.
        """
        results = list(self._profiles.values())
        if target_type is not None:
            results = [p for p in results if p.target_type == target_type]
        results = [p for p in results if p.sample_count >= min_samples]
        results.sort(key=lambda p: p.sample_count, reverse=True)
        return results[offset : offset + limit]

    # ── Selection ──

    def get_best_model(
        self,
        target_type: str | None = None,
        min_samples: int = 3,
    ) -> PerformanceProfile | None:
        """Get the best-performing model.

        Scores are computed from latency (inverted), cost (inverted),
        and success rate.

        Args:
            target_type: Optional filter by target type.
            min_samples: Minimum number of samples for a model to be eligible.

        Returns:
            The highest-scoring ``PerformanceProfile``, or None.
        """
        candidates = self.list_model_performance(
            target_type=target_type,
            min_samples=min_samples,
        )
        if not candidates:
            return None

        best: PerformanceProfile | None = None
        best_score = -1.0

        for profile in candidates:
            score = self._compute_model_score(profile)
            if score > best_score:
                best_score = score
                best = profile

        return best

    def compare_models(
        self,
        model_ids: Sequence[str],
    ) -> dict[str, dict[str, float]]:
        """Compare multiple models side by side.

        Args:
            model_ids: List of model IDs to compare.

        Returns:
            A dict keyed by model ID, each containing the profile metrics
            and computed score.
        """
        result: dict[str, dict[str, float]] = {}
        for mid in model_ids:
            profile = self._profiles.get(mid)
            if profile is None:
                continue
            result[mid] = {
                "avg_latency_ms": profile.avg_latency_ms,
                "p50_latency_ms": profile.p50_latency_ms,
                "p95_latency_ms": profile.p95_latency_ms,
                "p99_latency_ms": profile.p99_latency_ms,
                "avg_cost": profile.avg_cost,
                "success_rate": profile.success_rate,
                "throughput": profile.throughput,
                "sample_count": float(profile.sample_count),
                "score": self._compute_model_score(profile),
            }
        return result

    def rank_models(
        self,
        target_type: str | None = None,
        min_samples: int = 1,
        limit: int = 10,
    ) -> Sequence[dict[str, Any]]:
        """Rank all models by performance score descending.

        Returns:
            A list of dicts with ``model_id`` and ``score``.
        """
        candidates = self.list_model_performance(
            target_type=target_type,
            min_samples=min_samples,
            limit=1000,
        )
        scored = [
            {
                "model_id": p.target_id,
                "target_type": p.target_type,
                "score": self._compute_model_score(p),
                "avg_latency_ms": p.avg_latency_ms,
                "avg_cost": p.avg_cost,
                "success_rate": p.success_rate,
                "sample_count": p.sample_count,
            }
            for p in candidates
        ]
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:limit]

    # ── Scoring ──

    @staticmethod
    def _compute_model_score(profile: PerformanceProfile) -> float:
        """Compute a normalized composite score (0..1) for a model.

        Uses weighted combination of:
          - Latency score (lower is better, inverted against 5000ms max)
          - Cost score (lower is better, inverted against $0.10 max)
          - Success rate (higher is better, as-is)
        """
        latency_score = max(0.0, 1.0 - (profile.avg_latency_ms / 5000.0))
        cost_score = max(0.0, 1.0 - (profile.avg_cost / 0.10))
        success_score = profile.success_rate

        return (
            _WEIGHT_LATENCY * latency_score
            + _WEIGHT_COST * cost_score
            + _WEIGHT_SUCCESS_RATE * success_score
        )
