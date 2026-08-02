"""Tests for MCP Registry implementation."""

from unittest.mock import AsyncMock, patch

import pytest

from agentic_os.core.mcp.registry import MCPRegistryImpl
from agentic_os.domain.mcp import (
    MCPPermissionMapping,
    MCPServerStatus,
    MCPTransport,
)
from agentic_os.ports.mcp import MCPServerCreate, MCPServerUpdate


def _make(name: str, **kw: object) -> MCPServerCreate:
    """Create an MCPServerCreate with a default transport."""
    kw.setdefault("transport", "stdio")
    return MCPServerCreate(name=name, **kw)  # type: ignore[arg-type]


@pytest.fixture
async def registry(bus):
    with patch("agentic_os.core.mcp.registry.MCPClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.connect = AsyncMock()
        mock_client.disconnect = AsyncMock()
        mock_client.list_tools = AsyncMock(return_value=[])
        mock_client.process_id = 12345
        mock_client_cls.return_value = mock_client

        reg = MCPRegistryImpl(bus=bus)
        yield reg


class TestMCPRegistryImplRegister:
    async def test_register_server(self, registry) -> None:
        data = MCPServerCreate(
            name="test-server", transport="stdio", command="node", args=["server.js"]
        )
        detail = await registry.register_server(data)
        assert detail.config.name == "test-server"
        assert detail.config.transport == MCPTransport.STDIO
        assert detail.status == MCPServerStatus.STOPPED
        assert detail.config.id is not None

    async def test_register_sse_server(self, registry) -> None:
        data = MCPServerCreate(
            name="sse-server",
            transport="sse",
            url="http://localhost:3000/mcp",
        )
        detail = await registry.register_server(data)
        assert detail.config.transport == MCPTransport.SSE
        assert detail.config.url == "http://localhost:3000/mcp"

    async def test_register_duplicate_name(self, registry) -> None:
        data = MCPServerCreate(name="dup", transport="stdio", command="node")
        await registry.register_server(data)
        with pytest.raises(ValueError, match="already registered"):
            await registry.register_server(data)

    async def test_register_generates_unique_ids(self, registry) -> None:
        d1 = await registry.register_server(
            MCPServerCreate(name="s1", transport="stdio", command="c")
        )
        d2 = await registry.register_server(
            MCPServerCreate(name="s2", transport="stdio", command="c")
        )
        assert d1.config.id != d2.config.id


class TestMCPRegistryImplGet:
    async def test_get_server(self, registry) -> None:
        created = await registry.register_server(_make("srv", command="c"))
        fetched = await registry.get_server(created.config.id)
        assert fetched is not None
        assert fetched.config.id == created.config.id

    async def test_get_server_missing(self, registry) -> None:
        fetched = await registry.get_server("nonexistent")
        assert fetched is None

    async def test_get_server_by_name(self, registry) -> None:
        await registry.register_server(_make("my-server", command="c"))
        fetched = await registry.get_server("my-server")
        assert fetched is not None
        assert fetched.config.name == "my-server"

    async def test_get_server_by_name_missing(self, registry) -> None:
        fetched = await registry.get_server("missing")
        assert fetched is None


class TestMCPRegistryImplList:
    async def test_list_servers_empty(self, registry) -> None:
        servers = await registry.list_servers()
        assert servers == []

    async def test_list_servers(self, registry) -> None:
        await registry.register_server(_make("s1", command="c"))
        await registry.register_server(_make("s2", command="c"))
        servers = await registry.list_servers()
        assert len(servers) == 2

    async def test_list_servers_with_status_filter(self, registry) -> None:
        await registry.register_server(_make("s1", command="c"))
        stopped = await registry.list_servers(status=MCPServerStatus.STOPPED)
        assert len(stopped) == 1

    async def test_list_servers_limit_offset(self, registry) -> None:
        for i in range(5):
            await registry.register_server(_make(name=f"s{i}", command="c"))
        limited = await registry.list_servers(limit=2)
        assert len(limited) == 2
        offset = await registry.list_servers(limit=2, offset=2)
        assert len(offset) == 2


class TestMCPRegistryImplUpdate:
    async def test_update_server(self, registry) -> None:
        created = await registry.register_server(_make("srv", command="c"))
        update = MCPServerUpdate(description="Updated description")
        updated = await registry.update_server(created.config.id, update)
        assert updated.config.description == "Updated description"

    async def test_update_server_missing(self, registry) -> None:
        with pytest.raises(KeyError):
            await registry.update_server("missing", MCPServerUpdate())

    async def test_update_server_enabled(self, registry) -> None:
        created = await registry.register_server(_make("srv", command="c"))
        updated = await registry.update_server(created.config.id, MCPServerUpdate(enabled=False))
        assert not updated.config.enabled


class TestMCPRegistryImplDelete:
    async def test_delete_server(self, registry) -> None:
        created = await registry.register_server(_make("srv", command="c"))
        ok = await registry.delete_server(created.config.id)
        assert ok
        fetched = await registry.get_server(created.config.id)
        assert fetched is None

    async def test_delete_server_missing(self, registry) -> None:
        ok = await registry.delete_server("missing")
        assert not ok


class TestMCPRegistryImplLifecycle:
    async def test_start_server(self, registry) -> None:
        created = await registry.register_server(_make("srv", command="c"))
        started = await registry.start_server(created.config.id)
        assert started.status == MCPServerStatus.RUNNING
        assert started.started_at is not None

    async def test_start_server_missing(self, registry) -> None:
        with pytest.raises(KeyError):
            await registry.start_server("missing")

    async def test_stop_server(self, registry) -> None:
        created = await registry.register_server(_make("srv", command="c"))
        await registry.start_server(created.config.id)
        stopped = await registry.stop_server(created.config.id)
        assert stopped.status == MCPServerStatus.STOPPED

    async def test_restart_server(self, registry) -> None:
        created = await registry.register_server(_make("srv", command="c"))
        restarted = await registry.restart_server(created.config.id)
        assert restarted.status == MCPServerStatus.RUNNING

    async def test_restart_server_from_running(self, registry) -> None:
        created = await registry.register_server(_make("srv", command="c"))
        await registry.start_server(created.config.id)
        restarted = await registry.restart_server(created.config.id)
        assert restarted.status == MCPServerStatus.RUNNING


class TestMCPRegistryImplTools:
    async def test_discover_tools_default(self, registry) -> None:
        created = await registry.register_server(_make("srv", command="c"))
        await registry.start_server(created.config.id)
        tools = await registry.discover_tools(created.config.id)
        assert isinstance(tools, list)

    async def test_discover_tools_on_stopped_server(self, registry) -> None:
        created = await registry.register_server(_make("srv", command="c"))
        with pytest.raises(RuntimeError, match="Client not found"):
            await registry.discover_tools(created.config.id)

    async def test_get_tools(self, registry) -> None:
        created = await registry.register_server(_make("srv", command="c"))
        tools = await registry.get_tools(created.config.id)
        assert isinstance(tools, list)

    async def test_get_tools_missing(self, registry) -> None:
        tools = await registry.get_tools("missing")
        assert tools == []

    async def test_get_registry(self, registry) -> None:
        reg = await registry.get_registry()
        assert reg is not None


class TestMCPRegistryImplHealth:
    async def test_check_health_missing(self, registry) -> None:
        with pytest.raises(KeyError):
            await registry.check_health("missing")

    async def test_get_health(self, registry) -> None:
        health = await registry.get_health("missing")
        assert health is None


class TestMCPRegistryImplPermissions:
    async def test_set_permissions(self, registry) -> None:
        created = await registry.register_server(_make("srv", command="c"))
        mappings = [MCPPermissionMapping(tool_name="read", capability="mcp.tool.invoke")]
        count = await registry.set_permissions(created.config.id, mappings)
        assert count == 1

    async def test_set_permissions_missing(self, registry) -> None:
        with pytest.raises(KeyError):
            await registry.set_permissions("missing", [])

    async def test_get_permissions(self, registry) -> None:
        created = await registry.register_server(_make("srv", command="c"))
        perms = await registry.get_permissions(created.config.id)
        assert isinstance(perms, list)

    async def test_get_permissions_missing(self, registry) -> None:
        perms = await registry.get_permissions("missing")
        assert perms == []


class TestMCPRegistryImplSnapshot:
    async def test_registry_snapshot(self, registry) -> None:
        await registry.register_server(_make("s1", command="c"))
        await registry.register_server(_make("s2", command="c"))
        snapshot = registry.get_registry_snapshot()
        assert len(snapshot.servers) == 2

    async def test_registry_snapshot_immutable(self, registry) -> None:
        snapshot1 = registry.get_registry_snapshot()
        await registry.register_server(_make("s1", command="c"))
        snapshot2 = registry.get_registry_snapshot()
        assert len(snapshot1.servers) == 0
        assert len(snapshot2.servers) == 1
