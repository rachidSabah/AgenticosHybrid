"""Benchmark manager — runs benchmarks, compares results, determines winners."""

import random
from collections.abc import Sequence
from datetime import UTC, datetime

from agentic_os.domain.learning import Benchmark, BenchmarkStatus, LearningMetric
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.learning import BenchmarkPort

log = get_logger("learning.benchmark")


def _utcnow() -> datetime:
    return datetime.now(UTC)


class BenchmarkManager(BenchmarkPort):
    """In-memory benchmark manager implementing ``BenchmarkPort``.

    Manages the full lifecycle of ``Benchmark`` instances: creation,
    execution (with simulated metric collection), comparison, and
    deletion. Stores results in a dict keyed by benchmark ID.
    """

    def __init__(self) -> None:
        self._benchmarks: dict[str, Benchmark] = {}
        self._results: dict[str, dict[str, dict[str, float]]] = {}

    # ── CRUD ──

    async def create_benchmark(self, benchmark: Benchmark) -> Benchmark:
        if benchmark.id in self._benchmarks:
            raise ValueError(f"Benchmark '{benchmark.id}' already exists")
        self._benchmarks[benchmark.id] = benchmark
        log.info("Benchmark created", benchmark_id=benchmark.id, name=benchmark.name)
        return benchmark

    async def get_benchmark(self, benchmark_id: str) -> Benchmark | None:
        return self._benchmarks.get(benchmark_id)

    async def list_benchmarks(self) -> Sequence[Benchmark]:
        return sorted(
            self._benchmarks.values(),
            key=lambda b: b.created_at,
            reverse=True,
        )

    async def delete_benchmark(self, benchmark_id: str) -> None:
        if benchmark_id not in self._benchmarks:
            raise ValueError(f"Benchmark '{benchmark_id}' not found")
        del self._benchmarks[benchmark_id]
        self._results.pop(benchmark_id, None)
        log.info("Benchmark deleted", benchmark_id=benchmark_id)

    async def update_benchmark(self, benchmark: Benchmark) -> Benchmark:
        if benchmark.id not in self._benchmarks:
            raise ValueError(f"Benchmark '{benchmark.id}' not found")
        self._benchmarks[benchmark.id] = benchmark
        return benchmark

    # ── Execution ──

    async def run_benchmark(self, benchmark_id: str) -> Benchmark:
        """Run a benchmark, collecting simulated metrics for each target.

        For each target and each iteration, a random metric value is
        generated within a realistic range. Results are aggregated per
        target.

        Args:
            benchmark_id: The ID of the benchmark to run.

        Returns:
            The updated ``Benchmark`` with results populated.

        Raises:
            ValueError: If the benchmark is not found.
        """
        benchmark = self._benchmarks.get(benchmark_id)
        if benchmark is None:
            raise ValueError(f"Benchmark '{benchmark_id}' not found")

        updated = Benchmark(
            id=benchmark.id,
            name=benchmark.name,
            description=benchmark.description,
            targets=benchmark.targets,
            metrics=benchmark.metrics,
            iterations=benchmark.iterations,
            status=BenchmarkStatus.RUNNING,
            results=benchmark.results,
            winner=benchmark.winner,
            report=benchmark.report,
            created_at=benchmark.created_at,
            completed_at=benchmark.completed_at,
        )
        self._benchmarks[benchmark_id] = updated

        try:
            results: dict[str, dict[str, float]] = {}
            for target in benchmark.targets:
                target_results: dict[str, float] = {}
                for metric in benchmark.metrics or [m for m in LearningMetric]:
                    values = []
                    for _ in range(benchmark.iterations):
                        values.append(self._simulate_metric(metric))
                    target_results[metric.value] = sum(values) / len(values) if values else 0.0
                results[target] = target_results

            self._results[benchmark_id] = results

            report_lines = ["Benchmark Results:", "-----------------"]
            for target, target_results in results.items():
                report_lines.append(f"\n  Target: {target}")
                for metric_name, avg_val in target_results.items():
                    report_lines.append(f"    {metric_name}: {avg_val:.4f}")

            completed = Benchmark(
                id=benchmark.id,
                name=benchmark.name,
                description=benchmark.description,
                targets=benchmark.targets,
                metrics=benchmark.metrics,
                iterations=benchmark.iterations,
                status=BenchmarkStatus.COMPLETED,
                results=results,
                winner=benchmark.winner,
                report="\n".join(report_lines),
                created_at=benchmark.created_at,
                completed_at=_utcnow(),
            )
            self._benchmarks[benchmark_id] = completed
            log.info(
                "Benchmark completed",
                benchmark_id=benchmark_id,
                targets=len(results),
            )
            return completed

        except Exception as exc:
            failed = Benchmark(
                id=benchmark.id,
                name=benchmark.name,
                description=benchmark.description,
                targets=benchmark.targets,
                metrics=benchmark.metrics,
                iterations=benchmark.iterations,
                status=BenchmarkStatus.FAILED,
                results=benchmark.results,
                winner=benchmark.winner,
                report=f"Error: {exc}",
                created_at=benchmark.created_at,
                completed_at=_utcnow(),
            )
            self._benchmarks[benchmark_id] = failed
            log.error("Benchmark failed", benchmark_id=benchmark_id, error=str(exc))
            return failed

    async def compare(self, benchmark_id: str) -> Benchmark:
        """Compare results for a completed benchmark and determine a winner.

        For each metric, the best value across targets is determined
        (lower is better for latency/cost metrics, higher is better
        for success_rate/quality). The target with the most winning
        metrics is declared the winner.

        Args:
            benchmark_id: The ID of the benchmark to compare.

        Returns:
            The updated ``Benchmark`` with the winner field set.

        Raises:
            ValueError: If the benchmark is not found or not completed.
        """
        benchmark = self._benchmarks.get(benchmark_id)
        if benchmark is None:
            raise ValueError(f"Benchmark '{benchmark_id}' not found")
        if benchmark.status != BenchmarkStatus.COMPLETED:
            raise ValueError(f"Cannot compare benchmark in status '{benchmark.status.value}'")

        results = benchmark.results
        if not results or len(results) < 2:
            updated = Benchmark(
                id=benchmark.id,
                name=benchmark.name,
                description=benchmark.description,
                targets=benchmark.targets,
                metrics=benchmark.metrics,
                iterations=benchmark.iterations,
                status=benchmark.status,
                results=benchmark.results,
                winner=list(results.keys())[0] if results else None,
                report=benchmark.report,
                created_at=benchmark.created_at,
                completed_at=benchmark.completed_at,
            )
            self._benchmarks[benchmark_id] = updated
            return updated

        # Determine which metrics are "lower is better"
        lower_is_better_metrics = {
            "avg_latency_ms",
            "latency_ms",
            "p50_latency_ms",
            "p95_latency_ms",
            "p99_latency_ms",
            "avg_cost",
            "cost",
            "retry_count",
            "execution_latency",
            "cost_per_execution",
        }

        scores: dict[str, int] = {t: 0 for t in results}
        for metric in self._get_all_metric_names(results):
            lower_better = any(m in metric for m in lower_is_better_metrics)
            values = {t: results[t].get(metric, 0.0) for t in results}
            if lower_better:
                best_target = min(values, key=lambda k: values[k])
            else:
                best_target = max(values, key=lambda k: values[k])
            scores[best_target] += 1

        winner = max(scores, key=lambda k: scores[k])

        updated = Benchmark(
            id=benchmark.id,
            name=benchmark.name,
            description=benchmark.description,
            targets=benchmark.targets,
            metrics=benchmark.metrics,
            iterations=benchmark.iterations,
            status=benchmark.status,
            results=benchmark.results,
            winner=winner,
            report=benchmark.report + f"\n\nWinner: {winner}",
            created_at=benchmark.created_at,
            completed_at=benchmark.completed_at,
        )
        self._benchmarks[benchmark_id] = updated
        log.info("Benchmark comparison completed", benchmark_id=benchmark_id, winner=winner)
        return updated

    # ── Results Access ──

    def get_benchmark_results(
        self,
        benchmark_id: str,
    ) -> dict[str, dict[str, float]] | None:
        """Get raw results for a completed benchmark."""
        return self._results.get(benchmark_id)

    def get_target_history(
        self,
        target_id: str,
        limit: int = 20,
    ) -> Sequence[Benchmark]:
        """Get benchmark history for a specific target."""
        results = [
            b
            for b in self._benchmarks.values()
            if target_id in b.targets and b.status == BenchmarkStatus.COMPLETED
        ]
        results.sort(key=lambda b: b.completed_at or _utcnow(), reverse=True)
        return results[:limit]

    # ── Internals ──

    @staticmethod
    def _simulate_metric(metric: LearningMetric) -> float:
        """Generate a simulated metric value within realistic bounds."""
        ranges = {
            LearningMetric.EXECUTION_LATENCY: (50.0, 2000.0),
            LearningMetric.FAILURE_RATE: (0.0, 0.3),
            LearningMetric.RESOURCE_USAGE: (10.0, 90.0),
            LearningMetric.TASK_SUCCESS_RATE: (0.7, 1.0),
            LearningMetric.RETRY_COUNT: (0.0, 5.0),
            LearningMetric.CAPABILITY_UTILIZATION: (0.1, 1.0),
            LearningMetric.COST_PER_EXECUTION: (0.001, 0.1),
            LearningMetric.RESPONSE_QUALITY: (0.3, 1.0),
            LearningMetric.USER_SATISFACTION: (0.5, 1.0),
        }
        lo, hi = ranges.get(metric, (0.0, 1.0))
        return random.uniform(lo, hi)

    @staticmethod
    def _get_all_metric_names(
        results: dict[str, dict[str, float]],
    ) -> set[str]:
        names: set[str] = set()
        for target_results in results.values():
            names.update(target_results.keys())
        return names
