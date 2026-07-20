"""Tests for MCP Health Monitor."""

import pytest
from unittest.mock import AsyncMock

from agentic_os.core.mcp.health import MCPHealthMonitor
from agentic_os.domain.mcp import MCPHealthStatus


@pytest.fixture
async def health_monitor(bus):
    monitor = MCPHealthMonitor(bus=bus)
    yield monitor


class TestMCPHealthMonitorRegistration:
    async def test_register_server(self, health_monitor) -> None:
        callback = AsyncMock(return_value={"status": "healthy"})
        health_monitor.register_server(
            server_id="test-server",
            server_name="Test Server",
            health_check_callback=callback,
        )
        assert "test-server" in health_monitor._health_history

    async def test_unregister_server(self, health_monitor) -> None:
        callback = AsyncMock(return_value={"status": "healthy"})
        health_monitor.register_server(
            server_id="test-server",
            server_name="Test Server",
            health_check_callback=callback,
        )
        health_monitor.unregister_server("test-server")
        assert "test-server" not in health_monitor._health_history


class TestMCPHealthMonitorChecking:
    async def test_check_server_healthy(self, health_monitor) -> None:
        callback = AsyncMock(return_value={"status": "healthy", "latency_ms": 10})
        health_monitor.register_server(
            server_id="test-server",
            server_name="Test Server",
            health_check_callback=callback,
        )

        result = await health_monitor.check_server("test-server")
        assert result.status == MCPHealthStatus.HEALTHY
        assert result.latency_ms is not None

    async def test_check_server_unhealthy(self, health_monitor) -> None:
        callback = AsyncMock(side_effect=Exception("Connection refused"))
        health_monitor.register_server(
            server_id="test-server",
            server_name="Test Server",
            health_check_callback=callback,
        )

        result = await health_monitor.check_server("test-server")
        assert result.status == MCPHealthStatus.UNHEALTHY
        assert result.error is not None

    async def test_check_server_missing_callback(self, health_monitor) -> None:
        result = await health_monitor.check_server("nonexistent")
        assert result.status == MCPHealthStatus.UNKNOWN


class TestMCPHealthMonitorState:
    async def test_get_health(self, health_monitor) -> None:
        callback = AsyncMock(return_value={"status": "healthy"})
        health_monitor.register_server(
            server_id="test-server",
            server_name="Test Server",
            health_check_callback=callback,
        )
        await health_monitor.check_server("test-server")

        status = health_monitor.get_health("test-server")
        assert status == MCPHealthStatus.HEALTHY

    async def test_get_health_missing(self, health_monitor) -> None:
        status = health_monitor.get_health("nonexistent")
        assert status is None

    async def test_get_all_health(self, health_monitor) -> None:
        callback = AsyncMock(return_value={"status": "healthy"})
        health_monitor.register_server(
            server_id="server1",
            server_name="Server 1",
            health_check_callback=callback,
        )
        health_monitor.register_server(
            server_id="server2",
            server_name="Server 2",
            health_check_callback=callback,
        )

        await health_monitor.check_server("server1")
        await health_monitor.check_server("server2")

        all_health = health_monitor.get_all_health()
        assert len(all_health) == 2


class TestMCPHealthMonitorDegraded:
    async def test_is_server_degraded(self, health_monitor) -> None:
        callback = AsyncMock(return_value={"status": "degraded"})
        health_monitor.register_server(
            server_id="test-server",
            server_name="Test Server",
            health_check_callback=callback,
        )
        await health_monitor.check_server("test-server")

        assert health_monitor.is_server_degraded("test-server") is True

    async def test_get_degraded_servers(self, health_monitor) -> None:
        callback = AsyncMock(return_value={"status": "healthy"})
        degraded_callback = AsyncMock(return_value={"status": "degraded"})

        health_monitor.register_server(
            server_id="healthy-server",
            server_name="Healthy Server",
            health_check_callback=callback,
        )
        health_monitor.register_server(
            server_id="degraded-server",
            server_name="Degraded Server",
            health_check_callback=degraded_callback,
        )

        await health_monitor.check_server("healthy-server")
        await health_monitor.check_server("degraded-server")

        degraded = health_monitor.get_degraded_servers()
        assert "degraded-server" in degraded
        assert "healthy-server" not in degraded


class TestMCPHealthMonitorUnhealthy:
    async def test_is_server_unhealthy(self, health_monitor) -> None:
        callback = AsyncMock(side_effect=Exception("Connection refused"))
        health_monitor.register_server(
            server_id="test-server",
            server_name="Test Server",
            health_check_callback=callback,
        )

        # Multiple failures to cross threshold
        for _ in range(5):
            await health_monitor.check_server("test-server")

        assert health_monitor.is_server_unhealthy("test-server") is True

    async def test_get_unhealthy_servers(self, health_monitor) -> None:
        healthy_callback = AsyncMock(return_value={"status": "healthy"})
        unhealthy_callback = AsyncMock(side_effect=Exception("Error"))

        health_monitor.register_server(
            server_id="healthy-server",
            server_name="Healthy Server",
            health_check_callback=healthy_callback,
        )
        health_monitor.register_server(
            server_id="unhealthy-server",
            server_name="Unhealthy Server",
            health_check_callback=unhealthy_callback,
        )

        # Cross failure threshold
        for _ in range(5):
            await health_monitor.check_server("unhealthy-server")

        unhealthy = health_monitor.get_unhealthy_servers()
        assert "unhealthy-server" in unhealthy


class TestMCPHealthMonitorSummary:
    async def test_get_summary(self, health_monitor) -> None:
        callback = AsyncMock(return_value={"status": "healthy"})
        health_monitor.register_server(
            server_id="server1",
            server_name="Server 1",
            health_check_callback=callback,
        )
        health_monitor.register_server(
            server_id="server2",
            server_name="Server 2",
            health_check_callback=callback,
        )

        await health_monitor.check_server("server1")
        await health_monitor.check_server("server2")

        summary = health_monitor.get_summary()
        assert summary.total_servers == 2
        assert summary.healthy_count == 2
