"""Benchmark engine — run benchmarks, measure scores, compare engines."""

import random
from collections.abc import Sequence
from datetime import UTC, datetime

from agentic_os.domain.events import EventEnvelope
from agentic_os.domain.learning import BenchmarkRecord
from agentic_os.ports.event_bus import EventBus
from agentic_os.ports.learning import BenchmarkPort


def _utcnow() -> datetime:
    return datetime.now(UTC)


class BenchmarkEngine(BenchmarkPort):
    """In-memory benchmark engine that simulates benchmark measurements.

    In a production deployment this would dispatch actual workloads to the
    target engines and measure real latency, cost, and reliability.  The
    in-memory implementation provides realistic synthetic scores for
    development and testing.
    """

    def __init__(self) -> None:
        self._records: dict[str, BenchmarkRecord] = {}

    # ── CRUD ──

    async def run_benchmark(
        self,
        target_id: str,
        target_type: str,
        benchmark_name: str,
        bus: EventBus | None = None,
    ) -> BenchmarkRecord:
        record = BenchmarkRecord(
            id=f"bench-{int(_utcnow().timestamp())}-{random.randint(1000, 9999)}",
            target_id=target_id,
            target_type=target_type,
            benchmark_name=benchmark_name,
            score=random.uniform(0.5, 1.0),
            latency_ms=random.uniform(50, 2000),
            cost=random.uniform(0.001, 0.1),
            reliability=random.uniform(0.8, 1.0),
            memory_mb=random.uniform(100, 2000),
            cpu_percent=random.uniform(10, 90),
            capability_coverage=random.uniform(0.3, 1.0),
        )
        self._records[record.id] = record

        if bus is not None:
            await bus.publish(
                EventEnvelope(
                    type="event",
                    source="benchmark-engine",
                    topic="learning.benchmark_completed",
                    payload={
                        "benchmark_id": record.id,
                        "target_id": target_id,
                        "benchmark_name": benchmark_name,
                        "score": record.score,
                    },
                )
            )

        return record

    async def get_benchmark(self, benchmark_id: str) -> BenchmarkRecord | None:
        return self._records.get(benchmark_id)

    async def list_benchmarks(
        self,
        target_id: str | None = None,
        benchmark_name: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[BenchmarkRecord]:
        results = sorted(
            self._records.values(),
            key=lambda r: r.created_at,
            reverse=True,
        )
        if target_id is not None:
            results = [r for r in results if r.target_id == target_id]
        if benchmark_name is not None:
            results = [r for r in results if r.benchmark_name == benchmark_name]
        return results[offset : offset + limit]

    # ── Comparison ──

    async def compare_engines(
        self,
        engine_ids: Sequence[str],
        benchmark_name: str,
    ) -> dict[str, BenchmarkRecord]:
        result: dict[str, BenchmarkRecord] = {}
        for eid in engine_ids:
            records = [
                r
                for r in self._records.values()
                if r.target_id == eid and r.benchmark_name == benchmark_name
            ]
            if records:
                # Return the most recent record
                result[eid] = max(records, key=lambda r: r.created_at)
        return result

    # ── History ──

    async def get_benchmark_history(
        self,
        target_id: str,
        benchmark_name: str,
        limit: int = 20,
    ) -> Sequence[BenchmarkRecord]:
        results = [
            r
            for r in self._records.values()
            if r.target_id == target_id and r.benchmark_name == benchmark_name
        ]
        results.sort(key=lambda r: r.created_at, reverse=True)
        return results[:limit]

    async def get_top_scores(
        self,
        benchmark_name: str,
        limit: int = 10,
    ) -> Sequence[BenchmarkRecord]:
        results = [r for r in self._records.values() if r.benchmark_name == benchmark_name]
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:limit]
