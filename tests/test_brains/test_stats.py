"""Tests for BrainStatistics — aggregate metrics across all registered brains."""

from __future__ import annotations

import pytest

from agentic_os.core.brains.stats import BrainStatistics, BrainStatsSnapshot
from agentic_os.domain.brains import BrainRecord, BrainRuntime, BrainStatus, BrainType, BrainVendor

# ── Fixtures ─────────────────────────────────────────────────────────────────


def make_brain(
    brain_id: str,
    status: BrainStatus = BrainStatus.CONNECTED,
    brain_type: BrainType = BrainType.LOCAL_CLI,
    vendor: BrainVendor = BrainVendor.HERMES,
    runtime: BrainRuntime = BrainRuntime.PYTHON,
    health: float = 100.0,
    memory_usage: float = 64.0,
    cpu_usage: float = 5.0,
    latency: float = 10.0,
    throughput: float = 100.0,
    uptime: float = 3600.0,
    current_tasks: int = 1,
    queue_depth: int = 0,
    error_count: int = 0,
) -> BrainRecord:
    return BrainRecord(
        id=brain_id,
        display_name=f"Brain {brain_id}",
        brain_type=brain_type,
        vendor=vendor,
        runtime=runtime,
        version="1.0",
        status=status,
        health=health,
        capabilities=(),
        memory_usage=memory_usage,
        cpu_usage=cpu_usage,
        latency=latency,
        throughput=throughput,
        uptime=uptime,
        current_tasks=current_tasks,
        queue_depth=queue_depth,
        error_count=error_count,
    )


@pytest.fixture
def stats() -> BrainStatistics:
    return BrainStatistics()


@pytest.fixture
def healthy_brains() -> list[BrainRecord]:
    return [
        make_brain(
            "b1",
            status=BrainStatus.CONNECTED,
            vendor=BrainVendor.HERMES,
            runtime=BrainRuntime.PYTHON,
        ),
        make_brain(
            "b2",
            status=BrainStatus.IDLE,
            vendor=BrainVendor.CLAUDE_CODE,
            runtime=BrainRuntime.NATIVE,
        ),
        make_brain(
            "b3", status=BrainStatus.BUSY, vendor=BrainVendor.OPENCODE, runtime=BrainRuntime.NODE
        ),
    ]


# ═══════════════════════════════════════════════════════════════════════════════
# BrainStatsSnapshot
# ═══════════════════════════════════════════════════════════════════════════════


class TestBrainStatsSnapshot:
    def test_default_values(self) -> None:
        snap = BrainStatsSnapshot()
        assert snap.total_brains == 0
        assert snap.total_healthy == 0
        assert snap.avg_health == 0.0
        assert snap.capacity_score == 0.0
        assert snap.vendor_breakdown == {}
        assert snap.runtime_breakdown == {}

    def test_to_dict_contains_all_keys(self) -> None:
        snap = BrainStatsSnapshot(
            total_brains=3,
            total_healthy=2,
            total_connected=2,
            avg_health=85.5,
            vendor_breakdown={"hermes": 2, "claude_code": 1},
            runtime_breakdown={"python": 2, "native": 1},
            capacity_score=75.3,
        )
        d = snap.to_dict()
        assert d["total_brains"] == 3
        assert d["total_healthy"] == 2
        assert d["avg_health"] == 85.5
        assert d["vendor_breakdown"] == {"hermes": 2, "claude_code": 1}
        assert d["runtime_breakdown"] == {"python": 2, "native": 1}
        assert d["capacity_score"] == 75.3
        assert "total_unhealthy" in d
        assert "total_busy" in d
        assert "total_local_cli" in d

    def test_to_dict_rounds_floats(self) -> None:
        snap = BrainStatsSnapshot(
            avg_health=85.555,
            avg_memory_usage=128.456,
            avg_cpu_usage=12.345,
            avg_latency=10.555,
            avg_throughput=99.999,
            avg_uptime=3600.789,
            capacity_score=66.666,
        )
        d = snap.to_dict()
        assert d["avg_health"] == 85.6
        assert d["avg_memory_usage"] == 128.5
        assert d["avg_cpu_usage"] == 12.3
        assert round(d["avg_latency"], 1) == 10.6
        assert d["avg_throughput"] == 100.0
        assert d["avg_uptime"] == 3600.8
        assert d["capacity_score"] == 66.7

    def test_frozen_dataclass(self) -> None:
        snap = BrainStatsSnapshot(total_brains=5)
        with pytest.raises(AttributeError):
            snap.total_brains = 10  # type: ignore[misc]


# ═══════════════════════════════════════════════════════════════════════════════
# BrainStatistics.compute
# ═══════════════════════════════════════════════════════════════════════════════


class TestBrainStatisticsCompute:
    async def test_compute_empty_list(self, stats: BrainStatistics) -> None:
        snap = await stats.compute([])
        assert snap.total_brains == 0
        assert snap.capacity_score == 0.0

    async def test_compute_with_single_brain(self, stats: BrainStatistics) -> None:
        brains = [make_brain("b1", status=BrainStatus.CONNECTED, health=80.0)]
        snap = await stats.compute(brains)
        assert snap.total_brains == 1
        assert snap.total_connected == 1
        assert snap.avg_health == 80.0
        assert snap.avg_memory_usage == 64.0
        assert snap.avg_cpu_usage == 5.0

    async def test_compute_averages(
        self, stats: BrainStatistics, healthy_brains: list[BrainRecord]
    ) -> None:
        snap = await stats.compute(healthy_brains)
        assert snap.total_brains == 3
        assert snap.avg_health == 100.0
        assert snap.avg_memory_usage == 64.0
        assert snap.avg_cpu_usage == 5.0
        assert snap.avg_latency == 10.0
        assert snap.avg_throughput == 100.0
        assert snap.avg_uptime == 3600.0

    async def test_compute_counts_statuses(self, stats: BrainStatistics) -> None:
        brains = [
            make_brain("b1", status=BrainStatus.CONNECTED),
            make_brain("b2", status=BrainStatus.IDLE),
            make_brain("b3", status=BrainStatus.BUSY),
            make_brain("b4", status=BrainStatus.UNHEALTHY),
            make_brain("b5", status=BrainStatus.DISCONNECTED),
            make_brain("b6", status=BrainStatus.PAUSED),
            make_brain("b7", status=BrainStatus.FAILED),
            make_brain("b8", status=BrainStatus.EXECUTING),
            make_brain("b9", status=BrainStatus.REMOVED),
            make_brain("b10", status=BrainStatus.SHUTDOWN),
            make_brain("b11", status=BrainStatus.RECOVERING),
        ]
        snap = await stats.compute(brains)
        assert snap.total_brains == 11
        assert snap.total_healthy == 0  # no explicit "healthy" status
        assert snap.total_connected == 1
        assert snap.total_idle == 1
        assert snap.total_busy == 1
        assert snap.total_unhealthy == 1
        assert snap.total_disconnected == 1
        assert snap.total_paused == 1
        assert snap.total_failed == 1
        assert snap.total_executing == 1
        assert snap.total_removed == 1
        assert snap.total_shutdown == 1
        assert snap.total_recovering == 1

    async def test_compute_counts_brain_types(self, stats: BrainStatistics) -> None:
        brains = [
            make_brain("b1", brain_type=BrainType.LOCAL_CLI),
            make_brain("b2", brain_type=BrainType.CLOUD_API),
            make_brain("b3", brain_type=BrainType.ORCHESTRATOR),
            make_brain("b4", brain_type=BrainType.MCP_SERVER),
            make_brain("b5", brain_type=BrainType.CUSTOM),
        ]
        snap = await stats.compute(brains)
        assert snap.total_local_cli == 1
        assert snap.total_cloud_api == 1
        assert snap.total_orchestrator == 1
        assert snap.total_mcp_server == 1
        assert snap.total_custom_type == 1

    async def test_compute_vendor_breakdown(self, stats: BrainStatistics) -> None:
        brains = [
            make_brain("b1", vendor=BrainVendor.HERMES),
            make_brain("b2", vendor=BrainVendor.HERMES),
            make_brain("b3", vendor=BrainVendor.CLAUDE_CODE),
        ]
        snap = await stats.compute(brains)
        assert snap.vendor_breakdown == {"hermes": 2, "claude_code": 1}

    async def test_compute_runtime_breakdown(self, stats: BrainStatistics) -> None:
        brains = [
            make_brain("b1", runtime=BrainRuntime.PYTHON),
            make_brain("b2", runtime=BrainRuntime.PYTHON),
            make_brain("b3", runtime=BrainRuntime.NATIVE),
            make_brain("b4", runtime=BrainRuntime.NODE),
        ]
        snap = await stats.compute(brains)
        assert snap.runtime_breakdown == {"python": 2, "native": 1, "node": 1}

    async def test_compute_capacity_score_healthy(self, stats: BrainStatistics) -> None:
        brains = [
            make_brain("b1", status=BrainStatus.CONNECTED, health=100.0, error_count=0),
            make_brain("b2", status=BrainStatus.CONNECTED, health=100.0, error_count=0),
        ]
        snap = await stats.compute(brains)
        # healthy_ratio=0 (CONNECTED != HEALTHY), avg_health=100, error_penalty=0
        # capacity = (0 * 50) + (100 * 0.5) - 0 = 50
        assert snap.capacity_score == 50.0

    async def test_compute_capacity_score_with_errors(self, stats: BrainStatistics) -> None:
        brains = [
            make_brain("b1", status=BrainStatus.CONNECTED, health=80.0, error_count=10),
            make_brain("b2", status=BrainStatus.FAILED, health=20.0, error_count=5),
        ]
        snap = await stats.compute(brains)
        # healthy_ratio=0 (CONNECTED/FAILED != HEALTHY), avg_health=50, error_penalty=30
        # capacity = (0 * 50) + (50 * 0.5) - 30 = 25 - 30 = -5, clamped to 0
        assert snap.capacity_score == 0.0

    async def test_compute_capacity_score_clamped(self, stats: BrainStatistics) -> None:
        brains = [
            make_brain("b1", status=BrainStatus.FAILED, health=0.0, error_count=100),
        ]
        snap = await stats.compute(brains)
        # healthy_ratio=0, avg_health=0, error_penalty=min(200, 30)=30
        # capacity = 0 + 0 - 30 = -30 -> clamped to 0
        assert snap.capacity_score == 0.0

    async def test_compute_sums_tasks_queue_errors(self, stats: BrainStatistics) -> None:
        brains = [
            make_brain("b1", current_tasks=2, queue_depth=3, error_count=1),
            make_brain("b2", current_tasks=5, queue_depth=1, error_count=4),
        ]
        snap = await stats.compute(brains)
        assert snap.total_tasks_in_flight == 7
        assert snap.total_queue_depth == 4
        assert snap.total_error_count == 5
