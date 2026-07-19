"""Prediction engine — predict execution outcomes from historical data."""

import random
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from agentic_os.domain.learning import (
    ExecutionHistory,
    Prediction,
    PredictionStatus,
)
from agentic_os.ports.learning import PredictorPort


def _utcnow() -> datetime:
    return datetime.now(UTC)


class PredictionEngine(PredictorPort):
    """In-memory prediction engine using simple statistical models.

    Uses running averages and confidence intervals computed from
    historical execution records.  A production deployment would
    replace this with a proper ML model (linear regression, GBM,
    or a small neural network).
    """

    def __init__(self) -> None:
        self._predictions: dict[str, Prediction] = {}
        self._executions: dict[str, ExecutionHistory] = {}

    def ingest_execution(self, execution: ExecutionHistory) -> None:
        """Feed an execution record into the prediction model."""
        self._executions[execution.id] = execution

    # ── Predictions ──

    async def predict_execution(
        self,
        target_id: str,
        target_type: str,
        features: dict[str, Any] | None = None,
    ) -> Prediction:
        """Combined prediction for all key metrics."""
        return await self.predict_duration(target_id, target_type, features)

    async def predict_duration(
        self,
        target_id: str,
        target_type: str,
        features: dict[str, Any] | None = None,
    ) -> Prediction:
        records = self._get_records(target_id, target_type)
        vals = [e.duration_ms for e in records if e.duration_ms > 0]

        if len(vals) < 3:
            return self._low_confidence_prediction(
                target_id,
                target_type,
                "duration",
                500.0,
            )

        mean_val = sum(vals) / len(vals)
        std_val = (sum((v - mean_val) ** 2 for v in vals) / len(vals)) ** 0.5
        return self._build_prediction(
            target_id=target_id,
            target_type=target_type,
            prediction_type="duration",
            predicted_value=mean_val,
            std=std_val,
            sample_count=len(vals),
            features=features,
        )

    async def predict_cost(
        self,
        target_id: str,
        target_type: str,
        features: dict[str, Any] | None = None,
    ) -> Prediction:
        records = self._get_records(target_id, target_type)
        vals = [e.cost for e in records if e.cost > 0]

        if len(vals) < 3:
            return self._low_confidence_prediction(
                target_id,
                target_type,
                "cost",
                0.01,
            )

        mean_val = sum(vals) / len(vals)
        std_val = (sum((v - mean_val) ** 2 for v in vals) / len(vals)) ** 0.5
        return self._build_prediction(
            target_id=target_id,
            target_type=target_type,
            prediction_type="cost",
            predicted_value=mean_val,
            std=std_val,
            sample_count=len(vals),
            features=features,
        )

    async def predict_success_probability(
        self,
        target_id: str,
        target_type: str,
        features: dict[str, Any] | None = None,
    ) -> Prediction:
        records = self._get_records(target_id, target_type)
        if not records:
            return self._low_confidence_prediction(
                target_id,
                target_type,
                "success_probability",
                0.5,
            )

        successes = sum(1 for e in records if e.outcome.value == "success")
        prob = successes / len(records)
        std_val = (prob * (1 - prob) / len(records)) ** 0.5 if len(records) > 1 else 0.5
        return self._build_prediction(
            target_id=target_id,
            target_type=target_type,
            prediction_type="success_probability",
            predicted_value=prob,
            std=std_val,
            sample_count=len(records),
            features=features,
        )

    async def predict_resource_usage(
        self,
        target_id: str,
        target_type: str,
        features: dict[str, Any] | None = None,
    ) -> Prediction:
        records = self._get_records(target_id, target_type)
        mem_vals = [e.memory_mb for e in records if e.memory_mb > 0]
        cpu_vals = [e.cpu_percent for e in records if e.cpu_percent > 0]

        if not mem_vals and not cpu_vals:
            return self._low_confidence_prediction(
                target_id,
                target_type,
                "resource_usage",
                500.0,
            )

        all_vals = mem_vals + cpu_vals
        mean_val = sum(all_vals) / len(all_vals)
        std_val = (sum((v - mean_val) ** 2 for v in all_vals) / len(all_vals)) ** 0.5
        return self._build_prediction(
            target_id=target_id,
            target_type=target_type,
            prediction_type="resource_usage",
            predicted_value=mean_val,
            std=std_val,
            sample_count=len(records),
            features=features,
        )

    # ── Query ──

    async def get_prediction(self, prediction_id: str) -> Prediction | None:
        return self._predictions.get(prediction_id)

    async def list_predictions(
        self,
        target_id: str | None = None,
        prediction_type: str | None = None,
        limit: int = 50,
    ) -> Sequence[Prediction]:
        results = list(self._predictions.values())
        if target_id is not None:
            results = [p for p in results if p.target_id == target_id]
        if prediction_type is not None:
            results = [p for p in results if p.prediction_type == prediction_type]
        results.sort(key=lambda p: p.created_at, reverse=True)
        return results[:limit]

    async def batched_predict(
        self,
        target_ids: Sequence[str],
        target_type: str,
        prediction_type: str = "duration",
        features: dict[str, Any] | None = None,
    ) -> dict[str, Prediction]:
        result: dict[str, Prediction] = {}
        for tid in target_ids:
            pred = await self.predict_duration(tid, target_type, features)
            result[tid] = pred
        return result

    # ── Internals ──

    def _get_records(self, target_id: str, target_type: str) -> list[ExecutionHistory]:
        return [
            e
            for e in self._executions.values()
            if e.target_id == target_id and e.target_type == target_type
        ]

    def _build_prediction(
        self,
        target_id: str,
        target_type: str,
        prediction_type: str,
        predicted_value: float,
        std: float,
        sample_count: int,
        features: dict[str, Any] | None,
    ) -> Prediction:
        pid = f"pred-{int(_utcnow().timestamp())}-{random.randint(1000, 9999)}"
        confidence = max(0.0, min(1.0, 1.0 - (std / max(predicted_value, 0.001))))
        margin = 1.96 * std  # 95% CI

        if sample_count < 5:
            status = PredictionStatus.LOW_CONFIDENCE
        elif sample_count < 10:
            status = PredictionStatus.MEDIUM_CONFIDENCE
        else:
            status = PredictionStatus.HIGH_CONFIDENCE

        pred = Prediction(
            id=pid,
            target_id=target_id,
            target_type=target_type,
            prediction_type=prediction_type,
            predicted_value=predicted_value,
            confidence=confidence,
            lower_bound=max(0.0, predicted_value - margin),
            upper_bound=predicted_value + margin,
            prediction_status=status,
            features=features or {},
            model_version="v1-simple-stats",
            created_at=_utcnow(),
            valid_until=_utcnow() + timedelta(hours=1),
        )
        self._predictions[pid] = pred
        return pred

    @staticmethod
    def _low_confidence_prediction(
        target_id: str,
        target_type: str,
        prediction_type: str,
        default_value: float,
    ) -> Prediction:
        pid = f"pred-{int(_utcnow().timestamp())}-{random.randint(1000, 9999)}"
        return Prediction(
            id=pid,
            target_id=target_id,
            target_type=target_type,
            prediction_type=prediction_type,
            predicted_value=default_value,
            confidence=0.0,
            lower_bound=0.0,
            upper_bound=default_value * 10,
            prediction_status=PredictionStatus.INSUFFICIENT_DATA,
            model_version="v1-simple-stats",
            created_at=_utcnow(),
            valid_until=_utcnow() + timedelta(hours=1),
        )
