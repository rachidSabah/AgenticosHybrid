"""Tests for MCP Telemetry."""

import pytest

from agentic_os.core.mcp.telemetry import MCPTelemetry


@pytest.fixture
async def telemetry(bus):
    tel = MCPTelemetry(bus=bus)
    yield tel


class TestMCPTelemetryRequestTracking:
    async def test_start_request(self, telemetry) -> None:
        request_id = telemetry.start_request(
            server_id="test-server",
            server_name="Test Server",
            method="tools/list",
        )
        assert request_id is not None
        assert len(request_id) > 0

    async def test_complete_request_success(self, telemetry) -> None:
        request_id = telemetry.start_request(
            server_id="test-server",
            server_name="Test Server",
            method="tools/list",
        )
        result = telemetry.complete_request(request_id, success=True)
        assert result is not None
        assert result.success is True

    async def test_complete_request_failure(self, telemetry) -> None:
        request_id = telemetry.start_request(
            server_id="test-server",
            server_name="Test Server",
            method="tools/list",
        )
        result = telemetry.complete_request(request_id, success=False, error="Connection timeout")
        assert result is not None
        assert result.success is False
        assert result.error == "Connection timeout"


class TestMCPTelemetryMetrics:
    async def test_record_counter(self, telemetry) -> None:
        telemetry.increment_counter("test_counter")
        telemetry.increment_counter("test_counter")
        assert "test_counter" in telemetry._metrics
        assert len(telemetry._metrics["test_counter"]) == 2

    async def test_set_gauge(self, telemetry) -> None:
        telemetry.set_gauge("test_gauge", 42.0)
        assert "test_gauge" in telemetry._metrics
        assert telemetry._metrics["test_gauge"][-1].value == 42.0

    async def test_record_histogram(self, telemetry) -> None:
        telemetry.record_histogram("latency", 100.5)
        telemetry.record_histogram("latency", 200.5)
        assert "latency" in telemetry._metrics
        assert len(telemetry._metrics["latency"]) == 2


class TestMCPTelemetryAggregation:
    async def test_get_summary(self, telemetry) -> None:
        # Make some requests
        for idx in range(5):
            rid = telemetry.start_request("server1", "Server 1", "tools/list")
            telemetry.complete_request(rid, success=idx < 4)

        summary = telemetry.get_summary()
        assert summary["total_requests"] == 5
        assert summary["successful_requests"] == 4
        assert summary["failed_requests"] == 1

    async def test_get_latency_distribution(self, telemetry) -> None:
        for _ in range(10):
            rid = telemetry.start_request("server1", "Server 1", "tools/list")
            telemetry.complete_request(rid, success=True)

        dist = telemetry.get_latency_distribution()
        assert "p50" in dist
        assert "p90" in dist
        assert "p99" in dist

    async def test_get_error_rate(self, telemetry) -> None:
        # No requests
        assert telemetry.get_error_rate() == 0.0

        # Some successful
        for _ in range(5):
            rid = telemetry.start_request("server1", "Server 1", "tools/list")
            telemetry.complete_request(rid, success=True)

        # Some failed
        for _ in range(5):
            rid = telemetry.start_request("server2", "Server 2", "tools/list")
            telemetry.complete_request(rid, success=False)

        assert telemetry.get_error_rate() == 0.5


class TestMCPTelemetryServerMetrics:
    async def test_get_server_metrics(self, telemetry) -> None:
        for _ in range(3):
            rid = telemetry.start_request("server1", "Server 1", "tools/list")
            telemetry.complete_request(rid, success=True)

        metrics = telemetry.get_server_metrics("server1")
        assert metrics is not None
        assert metrics.total_requests == 3
        assert metrics.successful_requests == 3

    async def test_get_server_metrics_missing(self, telemetry) -> None:
        metrics = telemetry.get_server_metrics("nonexistent")
        assert metrics is None

    async def test_get_all_server_metrics(self, telemetry) -> None:
        for _ in range(2):
            rid = telemetry.start_request("server1", "Server 1", "tools/list")
            telemetry.complete_request(rid, success=True)
            rid = telemetry.start_request("server2", "Server 2", "prompts/list")
            telemetry.complete_request(rid, success=True)

        all_metrics = telemetry.get_all_server_metrics()
        assert "server1" in all_metrics
        assert "server2" in all_metrics


class TestMCPTelemetrySnapshot:
    async def test_get_snapshot(self, telemetry) -> None:
        for _ in range(3):
            rid = telemetry.start_request("server1", "Server 1", "tools/list")
            telemetry.complete_request(rid, success=True)

        snapshot = telemetry.get_snapshot()
        assert snapshot.total_requests == 3
        assert snapshot.successful_requests == 3
        assert snapshot.failed_requests == 0
        assert snapshot.active_servers == 1
