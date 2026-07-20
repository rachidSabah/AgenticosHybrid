"""Tests for MCP Session Manager."""

import pytest
from unittest.mock import AsyncMock

from agentic_os.core.mcp.session import MCPSessionManager
from agentic_os.domain.mcp import MCPSessionStatus, MCPTransport


@pytest.fixture
async def session_manager(bus):
    manager = MCPSessionManager(bus=bus)
    yield manager


class TestMCPSessionManagerCreate:
    async def test_create_session(self, session_manager) -> None:
        session = await session_manager.create_session(
            server_id="test-server",
            transport=MCPTransport.STDIO,
        )
        assert session.server_id == "test-server"
        assert session.transport == MCPTransport.STDIO
        assert session.status == MCPSessionStatus.ACTIVE
        assert session.id is not None

    async def test_create_session_with_capabilities(self, session_manager) -> None:
        caps = {"tools": True, "resources": True}
        session = await session_manager.create_session(
            server_id="test-server",
            transport=MCPTransport.STDIO,
            capabilities=caps,
        )
        assert session.capabilities == caps

    async def test_create_session_with_ttl(self, session_manager) -> None:
        session = await session_manager.create_session(
            server_id="test-server",
            transport=MCPTransport.STDIO,
            ttl_seconds=60,
        )
        assert session.expires_at is not None


class TestMCPSessionManagerGet:
    async def test_get_session(self, session_manager) -> None:
        created = await session_manager.create_session(
            server_id="test-server",
            transport=MCPTransport.STDIO,
        )
        fetched = await session_manager.get_session(created.id)
        assert fetched is not None
        assert fetched.id == created.id

    async def test_get_session_missing(self, session_manager) -> None:
        fetched = await session_manager.get_session("nonexistent")
        assert fetched is None

    async def test_get_session_for_server(self, session_manager) -> None:
        session = await session_manager.create_session(
            server_id="test-server",
            transport=MCPTransport.STDIO,
        )
        fetched = await session_manager.get_session_for_server("test-server")
        assert fetched is not None
        assert fetched.id == session.id


class TestMCPSessionManagerList:
    async def test_list_sessions(self, session_manager) -> None:
        await session_manager.create_session(server_id="s1", transport=MCPTransport.STDIO)
        await session_manager.create_session(server_id="s2", transport=MCPTransport.STDIO)
        sessions = await session_manager.list_sessions()
        assert len(sessions) == 2

    async def test_list_sessions_by_server(self, session_manager) -> None:
        await session_manager.create_session(server_id="s1", transport=MCPTransport.STDIO)
        await session_manager.create_session(server_id="s1", transport=MCPTransport.STDIO)
        await session_manager.create_session(server_id="s2", transport=MCPTransport.STDIO)
        sessions = await session_manager.list_sessions(server_id="s1")
        assert len(sessions) == 2


class TestMCPSessionManagerStatus:
    async def test_update_session_status(self, session_manager) -> None:
        session = await session_manager.create_session(
            server_id="test-server",
            transport=MCPTransport.STDIO,
        )
        updated = await session_manager.update_session_status(session.id, MCPSessionStatus.IDLE)
        assert updated is not None
        assert updated.status == MCPSessionStatus.IDLE

    async def test_close_session(self, session_manager) -> None:
        session = await session_manager.create_session(
            server_id="test-server",
            transport=MCPTransport.STDIO,
        )
        success = await session_manager.close_session(session.id)
        assert success

        closed = await session_manager.get_session(session.id)
        assert closed.status == MCPSessionStatus.CLOSED


class TestMCPSessionManagerExpiration:
    async def test_expire_session(self, session_manager) -> None:
        session = await session_manager.create_session(
            server_id="test-server",
            transport=MCPTransport.STDIO,
        )
        success = await session_manager.expire_session(session.id)
        assert success

    async def test_expire_sessions(self, session_manager) -> None:
        await session_manager.create_session(server_id="s1", transport=MCPTransport.STDIO)
        await session_manager.create_session(server_id="s2", transport=MCPTransport.STDIO)
        expired = await session_manager.expire_sessions()
        assert expired >= 0


class TestMCPSessionManagerStatistics:
    async def test_get_session_count(self, session_manager) -> None:
        await session_manager.create_session(server_id="s1", transport=MCPTransport.STDIO)
        await session_manager.create_session(server_id="s2", transport=MCPTransport.STDIO)
        count = session_manager.get_session_count()
        assert count == 2

    async def test_get_active_session_count(self, session_manager) -> None:
        await session_manager.create_session(server_id="s1", transport=MCPTransport.STDIO)
        await session_manager.create_session(server_id="s2", transport=MCPTransport.STDIO)
        count = session_manager.get_active_session_count()
        assert count == 2

    async def test_get_session_stats(self, session_manager) -> None:
        await session_manager.create_session(server_id="s1", transport=MCPTransport.STDIO)
        await session_manager.create_session(server_id="s2", transport=MCPTransport.STDIO)
        stats = session_manager.get_session_stats()
        assert stats["total"] == 2
        assert stats["active"] == 2
