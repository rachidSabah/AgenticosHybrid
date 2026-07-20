"""Historical analyzer — analyzes historical execution data."""

import math
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from agentic_os.domain.learning import ExecutionHistory, ExecutionStatistics, FailureAnalysis
from agentic_os.infrastructure.logging import get_logger

log = get_logger("learning.history")


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _percentile(sorted_values: Sequence[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    k = (pct / 100.0) * (len(sorted_values) - 1)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_values[int(k)]
    return sorted_values[f] * (c - k) + sorted_values[c] * (k - f)


class HistoricalAnalyzer:
    """Analyzes historical execution data to produce statistics and trends.

    Stores ``ExecutionHistory`` records in-memory and provides statistical
    computations including averages, percentiles, failure analysis, and
    execution distributions.
    """

    def __init__(self) -> None:
        self._records: dict[str, ExecutionHistory] = {}

    # ── Record Management ──

    def record_execution(self, record: ExecutionHistory) -> None:
        """Store an execution record for analysis."""
        self._records[record.id] = record
        log.debug("Execution recorded for analysis", execution_id=record.id)

    def get_record(self, record_id: str) -> ExecutionHistory | None:
        return self._records.get(record_id)

    def list_records(
        self,
        engine_type: str | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[ExecutionHistory]:
        results = sorted(self._records.values(), key=lambda r: r.executed_at, reverse=True)
        if engine_type is not None:
            results = [r for r in results if r.engine_type == engine_type]
        if status is not None:
            results = [r for r in results if r.status == status]
        return results[offset : offset + limit]

    # ── Analysis ──

    async def analyze_executions(
        self,
        history_ids: tuple[str, ...],
    ) -> ExecutionStatistics:
        """Compute execution statistics for the given history record ids."""
        records = [self._records[hid] for hid in history_ids if hid in self._records]
        if not records:
            return ExecutionStatistics(
                period_start=_utcnow(),
                period_end=_utcnow(),
            )

        durations = [r.duration_ms for r in records]
        durations_sorted = sorted(durations)

        success_count = sum(1 for r in records if r.status == "success")
        failure_count = sum(1 for r in records if r.status == "failure")
        total_retries = sum(r.retry_count for r in records)

        by_engine: dict[str, int] = {}
        by_status: dict[str, int] = {}
        by_error_type: dict[str, int] = {}
        for r in records:
            by_engine[r.engine_type] = by_engine.get(r.engine_type, 0) + 1
            by_status[r.status] = by_status.get(r.status, 0) + 1
            if r.error_type:
                by_error_type[r.error_type] = by_error_type.get(r.error_type, 0) + 1

        timestamps = [r.executed_at for r in records if r.executed_at]

        return ExecutionStatistics(
            total_count=len(records),
            success_count=success_count,
            failure_count=failure_count,
            avg_duration_ms=_mean(durations),
            min_duration_ms=durations_sorted[0] if durations_sorted else 0.0,
            max_duration_ms=durations_sorted[-1] if durations_sorted else 0.0,
            total_retries=total_retries,
            by_engine=by_engine,
            by_status=by_status,
            by_error_type=by_error_type,
            period_start=min(timestamps) if timestamps else None,
            period_end=max(timestamps) if timestamps else None,
        )

    async def compute_failure_analysis(
        self,
        history_ids: tuple[str, ...],
    ) -> FailureAnalysis:
        """Analyze failures from the given history record ids."""
        records = [self._records[hid] for hid in history_ids if hid in self._records]
        failures = [r for r in records if r.status == "failure"]

        if not records:
            return FailureAnalysis(period_start=_utcnow(), period_end=_utcnow())

        total_failures = len(failures)
        failure_rate = total_failures / len(records) if records else 0.0

        top_error_types: dict[str, int] = {}
        top_failing_engines: dict[str, int] = {}
        for f in failures:
            if f.error_type:
                top_error_types[f.error_type] = top_error_types.get(f.error_type, 0) + 1
            top_failing_engines[f.engine_type] = top_failing_engines.get(f.engine_type, 0) + 1

        # Sort and keep top 10
        top_error_types = dict(
            sorted(top_error_types.items(), key=lambda x: x[1], reverse=True)[:10]
        )
        top_failing_engines = dict(
            sorted(top_failing_engines.items(), key=lambda x: x[1], reverse=True)[:10]
        )

        recovery_success_rate = 0.0
        common_patterns: list[str] = []
        if top_error_types:
            common_patterns = [f"error_type:{k}" for k in top_error_types]

        timestamps = [r.executed_at for r in records if r.executed_at]

        return FailureAnalysis(
            total_failures=total_failures,
            failure_rate=failure_rate,
            top_error_types=top_error_types,
            top_failing_engines=top_failing_engines,
            recovery_success_rate=recovery_success_rate,
            common_patterns=tuple(common_patterns),
            recommendations=tuple(self._generate_failure_recommendations(top_error_types)),
            period_start=min(timestamps) if timestamps else None,
            period_end=max(timestamps) if timestamps else None,
        )

    async def compute_trends(
        self,
        engine_type: str | None = None,
        metric: str = "duration_ms",
        window_hours: int = 24,
    ) -> dict[str, Any]:
        """Compute performance trends for the given metric.

        Returns current average, previous average, change percentage,
        and direction.
        """
        records = list(self._records.values())
        if engine_type:
            records = [r for r in records if r.engine_type == engine_type]

        if not records:
            return {
                "metric": metric,
                "current_avg": 0.0,
                "previous_avg": 0.0,
                "change_pct": 0.0,
                "direction": "stable",
                "samples_analyzed": 0,
            }

        now = _utcnow()
        cutoff = now.timestamp() - window_hours * 3600

        recent = [r for r in records if r.executed_at.timestamp() >= cutoff]
        older = [r for r in records if r.executed_at.timestamp() < cutoff]

        def _metric_values(recs: list[ExecutionHistory]) -> list[float]:
            if metric == "duration_ms":
                return [r.duration_ms for r in recs]
            if metric == "cost":
                return [r.cost for r in recs]
            if metric == "retry_count":
                return [float(r.retry_count) for r in recs]
            return []

        recent_vals = _metric_values(recent)
        older_vals = _metric_values(older)

        current_avg = _mean(recent_vals) if recent_vals else 0.0
        previous_avg = _mean(older_vals) if older_vals else current_avg

        change_pct = (
            ((current_avg - previous_avg) / max(abs(previous_avg), 0.001)) * 100
            if previous_avg != 0
            else 0.0
        )

        if abs(change_pct) < 5.0:
            direction = "stable"
        elif change_pct > 0:
            direction = "increasing"
        else:
            direction = "decreasing"

        return {
            "metric": metric,
            "current_avg": current_avg,
            "previous_avg": previous_avg,
            "change_pct": change_pct,
            "direction": direction,
            "samples_analyzed": len(recent_vals),
        }

    async def get_execution_distribution(
        self,
        history_ids: tuple[str, ...],
        bins: int = 10,
    ) -> dict[str, Any]:
        """Compute the distribution of execution durations."""
        records = [self._records[hid] for hid in history_ids if hid in self._records]
        if not records:
            return {"bins": [], "counts": [], "bin_edges": []}

        durations = sorted([r.duration_ms for r in records])
        min_val = durations[0]
        max_val = durations[-1]
        bin_width = max((max_val - min_val) / bins, 1.0)

        bin_edges = [min_val + i * bin_width for i in range(bins + 1)]
        counts = [0] * bins

        for d in durations:
            idx = min(int((d - min_val) / bin_width), bins - 1)
            counts[idx] += 1

        return {
            "bins": [f"{bin_edges[i]:.1f}-{bin_edges[i + 1]:.1f}" for i in range(bins)],
            "counts": counts,
            "bin_edges": bin_edges,
            "total_samples": len(durations),
            "mean": _mean(durations),
            "p50": _percentile(durations, 50),
            "p95": _percentile(durations, 95),
            "p99": _percentile(durations, 99),
        }

    # ── Internals ──

    @staticmethod
    def _generate_failure_recommendations(
        top_error_types: dict[str, int],
    ) -> list[str]:
        recs: list[str] = []
        for error_type, count in top_error_types.items():
            if count >= 5:
                recs.append(
                    f"High frequency of '{error_type}' errors ({count} occurrences) "
                    "- investigate root cause and implement retry with backoff"
                )
            elif count >= 2:
                recs.append(
                    f"Recurring '{error_type}' errors ({count} occurrences) - review error handling"
                )
        if not recs:
            recs.append("No significant failure patterns detected")
        return recs
