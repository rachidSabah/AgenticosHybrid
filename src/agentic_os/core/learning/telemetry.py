"""Learning telemetry — ingests platform metrics for learning & optimization."""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from agentic_os.domain.learning import (
    CostMetrics,
    FailureAnalysis,
    LatencyMetrics,
    PerformanceProfile,
    QualityMetrics,
)
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.learning import TelemetryLearningPort

log = get_logger("learning.telemetry")

_MAX_ROLLING_BUFFER = 10_000


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _percentile(sorted_values: Sequence[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    k = (pct / 100.0) * (len(sorted_values) - 1)
    f = int(k)
    c = f + 1 if f < len(sorted_values) - 1 else f
    if f == c:
        return sorted_values[f]
    return sorted_values[f] * (c - k) + sorted_values[c] * (k - f)


class _RollingBuffer:
    """Fixed-size rolling buffer for metric samples."""

    def __init__(self, max_size: int = _MAX_ROLLING_BUFFER) -> None:
        self._data: list[dict[str, Any]] = []
        self._max_size = max_size

    def append(self, item: dict[str, Any]) -> None:
        self._data.append(item)
        if len(self._data) > self._max_size:
            self._data.pop(0)

    def __len__(self) -> int:
        return len(self._data)

    def all(self) -> Sequence[dict[str, Any]]:
        return list(self._data)

    def clear(self) -> None:
        self._data.clear()


class LearningTelemetry(TelemetryLearningPort):
    """Ingests platform metrics and produces aggregated performance views.

    Maintains rolling buffers for each metric type and computes latency,
    cost, quality, and failure analysis on demand.
    """

    def __init__(self) -> None:
        self._execution_metrics = _RollingBuffer()
        self._performance_metrics = _RollingBuffer()
        self._cost_metrics = _RollingBuffer()
        self._failure_metrics = _RollingBuffer()
        self._performance_profiles: dict[str, PerformanceProfile] = {}

    # ── Ingestion ──

    async def ingest_execution_metrics(self, metrics: dict[str, Any]) -> None:
        """Ingest raw execution metrics."""
        self._execution_metrics.append(
            {
                "timestamp": _utcnow().isoformat(),
                **metrics,
            }
        )
        log.debug("Execution metrics ingested", sample_count=len(self._execution_metrics))

    async def ingest_performance_metrics(self, metrics: dict[str, Any]) -> None:
        """Ingest performance profile metrics."""
        self._performance_metrics.append(
            {
                "timestamp": _utcnow().isoformat(),
                **metrics,
            }
        )

        # Build/update performance profile
        target_id = metrics.get("target_id")
        if target_id:
            existing = self._performance_profiles.get(target_id)
            new_sample_count = (existing.sample_count + 1) if existing else 1
            avg_latency = metrics.get("avg_latency_ms", 0.0)
            avg_cost = metrics.get("avg_cost", 0.0)
            success_rate = metrics.get("success_rate", 0.0)

            if existing:
                avg_latency = (
                    (existing.avg_latency_ms * existing.sample_count) + avg_latency
                ) / new_sample_count
                avg_cost = (
                    (existing.avg_cost * existing.sample_count) + avg_cost
                ) / new_sample_count
                success_rate = (
                    (existing.success_rate * existing.sample_count) + success_rate
                ) / new_sample_count

            self._performance_profiles[target_id] = PerformanceProfile(
                target_id=target_id,
                target_type=metrics.get("target_type", ""),
                avg_latency_ms=avg_latency,
                p50_latency_ms=metrics.get("p50_latency_ms", avg_latency),
                p95_latency_ms=metrics.get("p95_latency_ms", avg_latency),
                p99_latency_ms=metrics.get("p99_latency_ms", avg_latency),
                avg_cost=avg_cost,
                success_rate=success_rate,
                throughput=metrics.get("throughput", 0.0),
                sample_count=new_sample_count,
            )

        log.debug("Performance metrics ingested", sample_count=len(self._performance_metrics))

    async def ingest_cost_metrics(self, metrics: dict[str, Any]) -> None:
        """Ingest cost tracking metrics."""
        self._cost_metrics.append(
            {
                "timestamp": _utcnow().isoformat(),
                **metrics,
            }
        )
        log.debug("Cost metrics ingested", sample_count=len(self._cost_metrics))

    async def ingest_failure_metrics(self, metrics: dict[str, Any]) -> None:
        """Ingest failure analysis metrics."""
        self._failure_metrics.append(
            {
                "timestamp": _utcnow().isoformat(),
                **metrics,
            }
        )
        log.debug("Failure metrics ingested", sample_count=len(self._failure_metrics))

    # ── Query Methods ──

    async def get_latency_metrics(
        self,
        period_start: str | None = None,
        period_end: str | None = None,
    ) -> LatencyMetrics:
        """Compute aggregated latency metrics from ingested data."""
        samples = self._filter_by_period(
            self._performance_metrics.all(),
            period_start,
            period_end,
        )

        if not samples:
            return LatencyMetrics()

        latencies = [s.get("avg_latency_ms", 0.0) for s in samples]
        latencies_sorted = sorted(latencies)

        latency_by_engine: dict[str, float] = {}
        latency_by_provider: dict[str, float] = {}
        for s in samples:
            engine = s.get("engine_type", "unknown")
            provider = s.get("provider", "unknown")
            lat = s.get("avg_latency_ms", 0.0)
            latency_by_engine[engine] = lat
            latency_by_provider[provider] = lat

        timestamps = [datetime.fromisoformat(s["timestamp"]) for s in samples if "timestamp" in s]
        return LatencyMetrics(
            avg_latency_ms=_mean(latencies),
            p50_latency_ms=_percentile(latencies_sorted, 50),
            p95_latency_ms=_percentile(latencies_sorted, 95),
            p99_latency_ms=_percentile(latencies_sorted, 99),
            latency_by_engine=latency_by_engine,
            latency_by_provider=latency_by_provider,
            period_start=min(timestamps) if timestamps else None,
            period_end=max(timestamps) if timestamps else None,
        )

    async def get_cost_metrics(
        self,
        period_start: str | None = None,
        period_end: str | None = None,
    ) -> CostMetrics:
        """Compute aggregated cost metrics from ingested data."""
        samples = self._filter_by_period(
            self._cost_metrics.all(),
            period_start,
            period_end,
        )

        if not samples:
            return CostMetrics()

        total_cost = sum(s.get("cost", 0.0) for s in samples)
        avg_cost_per_execution = total_cost / len(samples) if samples else 0.0

        cost_by_engine: dict[str, float] = {}
        cost_by_provider: dict[str, float] = {}
        for s in samples:
            engine = s.get("engine_type", "unknown")
            provider = s.get("provider", "unknown")
            c = s.get("cost", 0.0)
            cost_by_engine[engine] = cost_by_engine.get(engine, 0.0) + c
            cost_by_provider[provider] = cost_by_provider.get(provider, 0.0) + c

        timestamps = [datetime.fromisoformat(s["timestamp"]) for s in samples if "timestamp" in s]
        return CostMetrics(
            total_cost=total_cost,
            avg_cost_per_execution=avg_cost_per_execution,
            cost_by_engine=cost_by_engine,
            cost_by_provider=cost_by_provider,
            period_start=min(timestamps) if timestamps else None,
            period_end=max(timestamps) if timestamps else None,
        )

    async def get_quality_metrics(
        self,
        period_start: str | None = None,
        period_end: str | None = None,
    ) -> QualityMetrics:
        """Compute aggregated quality metrics from ingested data."""
        samples = self._filter_by_period(
            self._execution_metrics.all(),
            period_start,
            period_end,
        )

        if not samples:
            return QualityMetrics()

        quality_scores = [s.get("quality_score", 0.0) for s in samples if "quality_score" in s]
        if not quality_scores:
            # Fall back to using success_rate as a quality proxy
            success_rates = [s.get("success_rate", 0.0) for s in samples]
            quality_scores = success_rates

        if not quality_scores:
            return QualityMetrics()

        quality_by_engine: dict[str, float] = {}
        quality_by_provider: dict[str, float] = {}
        for s in samples:
            engine = s.get("engine_type", "unknown")
            provider = s.get("provider", "unknown")
            q = s.get("quality_score") or s.get("success_rate", 0.0)
            quality_by_engine[engine] = q
            quality_by_provider[provider] = q

        timestamps = [datetime.fromisoformat(s["timestamp"]) for s in samples if "timestamp" in s]
        return QualityMetrics(
            avg_quality_score=_mean(quality_scores),
            min_quality_score=min(quality_scores),
            max_quality_score=max(quality_scores),
            quality_by_engine=quality_by_engine,
            quality_by_provider=quality_by_provider,
            period_start=min(timestamps) if timestamps else None,
            period_end=max(timestamps) if timestamps else None,
        )

    async def get_failure_analysis(
        self,
        period_start: str | None = None,
        period_end: str | None = None,
    ) -> FailureAnalysis:
        """Compute failure analysis from ingested failure metrics."""
        samples = self._filter_by_period(
            self._failure_metrics.all(),
            period_start,
            period_end,
        )

        if not samples:
            return FailureAnalysis()

        total_failures = len(samples)
        total_executions = sum(s.get("total_executions", 0) for s in samples)
        failure_rate = total_failures / total_executions if total_executions > 0 else 0.0

        top_error_types: dict[str, int] = {}
        top_failing_engines: dict[str, int] = {}
        recovery_count = 0
        for s in samples:
            error_type = s.get("error_type", "unknown")
            top_error_types[error_type] = top_error_types.get(error_type, 0) + 1
            engine = s.get("engine_type", "unknown")
            top_failing_engines[engine] = top_failing_engines.get(engine, 0) + 1
            if s.get("recovered", False):
                recovery_count += 1

        recovery_success_rate = recovery_count / total_failures if total_failures > 0 else 0.0

        common_patterns = sorted(top_error_types, key=lambda k: top_error_types[k], reverse=True)[
            :5
        ]
        recommendations: list[str] = []
        for error_type, count in top_error_types.items():
            if count >= 3:
                recommendations.append(
                    f"Frequent '{error_type}' ({count}x) — implement targeted retry logic"
                )

        timestamps = [datetime.fromisoformat(s["timestamp"]) for s in samples if "timestamp" in s]
        return FailureAnalysis(
            total_failures=total_failures,
            failure_rate=failure_rate,
            top_error_types=dict(
                sorted(top_error_types.items(), key=lambda x: x[1], reverse=True)[:10]
            ),
            top_failing_engines=dict(
                sorted(top_failing_engines.items(), key=lambda x: x[1], reverse=True)[:10]
            ),
            recovery_success_rate=recovery_success_rate,
            common_patterns=tuple(common_patterns),
            recommendations=tuple(recommendations),
            period_start=min(timestamps) if timestamps else None,
            period_end=max(timestamps) if timestamps else None,
        )

    # ── Profile Access ──

    def get_performance_profile(self, target_id: str) -> PerformanceProfile | None:
        """Get the current performance profile for a target."""
        return self._performance_profiles.get(target_id)

    def list_performance_profiles(self) -> Sequence[PerformanceProfile]:
        return list(self._performance_profiles.values())

    # ── Helpers ──

    @staticmethod
    def _filter_by_period(
        samples: Sequence[dict[str, Any]],
        period_start: str | None,
        period_end: str | None,
    ) -> list[dict[str, Any]]:
        """Filter samples by optional ISO datetime range."""
        if not period_start and not period_end:
            return list(samples)

        result = list(samples)
        if period_start:
            start_dt = datetime.fromisoformat(period_start)
            result = [
                s
                for s in result
                if s.get("timestamp") and datetime.fromisoformat(s["timestamp"]) >= start_dt
            ]
        if period_end:
            end_dt = datetime.fromisoformat(period_end)
            result = [
                s
                for s in result
                if s.get("timestamp") and datetime.fromisoformat(s["timestamp"]) <= end_dt
            ]
        return result
