"""Tests for SessionManager — session creation, listing, closure, history."""

import pytest

from agentic_os.core.runtime.runtime_session import SessionManager


@pytest.fixture
async def session_mgr() -> SessionManager:
    return SessionManager()


@pytest.mark.asyncio
class TestSessionManager:
    async def test_create_session(self, session_mgr: SessionManager) -> None:
        session = await session_mgr.create_session(
            runtime_id="rt-1",
            name="test-session",
        )
        assert session.session_id is not None
        assert session.name == "test-session"
        assert session.active is True

    async def test_create_session_with_cwd(self, session_mgr: SessionManager) -> None:
        session = await session_mgr.create_session(
            runtime_id="rt-1", name="cwd-session", cwd="/tmp"
        )
        assert session.working_directory == "/tmp"

    async def test_create_session_with_env(self, session_mgr: SessionManager) -> None:
        session = await session_mgr.create_session(
            runtime_id="rt-1", name="env-session", env={"KEY": "VAL"}
        )
        assert session.environment == {"KEY": "VAL"}

    async def test_get_session(self, session_mgr: SessionManager) -> None:
        created = await session_mgr.create_session(runtime_id="rt-1", name="find-me")
        fetched = await session_mgr.get_session(created.session_id)
        assert fetched is not None
        assert fetched.session_id == created.session_id

    async def test_get_session_not_found(self, session_mgr: SessionManager) -> None:
        assert await session_mgr.get_session("nonexistent") is None

    async def test_list_sessions(self, session_mgr: SessionManager) -> None:
        await session_mgr.create_session(runtime_id="rt-1", name="s1")
        await session_mgr.create_session(runtime_id="rt-1", name="s2")
        sessions = await session_mgr.list_sessions("rt-1")
        assert len(sessions) == 2

    async def test_list_sessions_empty(self, session_mgr: SessionManager) -> None:
        sessions = await session_mgr.list_sessions("rt-1")
        assert sessions == []

    async def test_list_sessions_other_runtime(self, session_mgr: SessionManager) -> None:
        await session_mgr.create_session(runtime_id="rt-1", name="s1")
        sessions = await session_mgr.list_sessions("rt-2")
        assert sessions == []

    async def test_list_all_sessions(self, session_mgr: SessionManager) -> None:
        await session_mgr.create_session(runtime_id="rt-1", name="a")
        await session_mgr.create_session(runtime_id="rt-2", name="b")
        all_sessions = await session_mgr.list_all_sessions()
        assert len(all_sessions) == 2

    async def test_close_session(self, session_mgr: SessionManager) -> None:
        session = await session_mgr.create_session(runtime_id="rt-1", name="close-me")
        result = await session_mgr.close_session(session.session_id)
        assert result is True
        fetched = await session_mgr.get_session(session.session_id)
        assert fetched is not None
        assert fetched.active is False
        assert fetched.closed_at is not None

    async def test_close_session_not_found(self, session_mgr: SessionManager) -> None:
        result = await session_mgr.close_session("nonexistent")
        assert result is False

    async def test_find_or_create_creates_new(self, session_mgr: SessionManager) -> None:
        session = await session_mgr.find_or_create(runtime_id="rt-1", name="new-session")
        assert session.name == "new-session"
        assert session.active is True

    async def test_find_or_create_finds_existing(self, session_mgr: SessionManager) -> None:
        first = await session_mgr.create_session(runtime_id="rt-1", name="reuse")
        second = await session_mgr.find_or_create(runtime_id="rt-1", name="reuse")
        assert second.session_id == first.session_id

    async def test_find_or_create_skips_closed(self, session_mgr: SessionManager) -> None:
        first = await session_mgr.create_session(runtime_id="rt-1", name="was-closed")
        await session_mgr.close_session(first.session_id)
        second = await session_mgr.find_or_create(runtime_id="rt-1", name="was-closed")
        assert second.session_id != first.session_id

    async def test_record_command(self, session_mgr: SessionManager) -> None:
        session = await session_mgr.create_session(runtime_id="rt-1", name="cmd-recorder")
        result = await session_mgr.record_command(session.session_id, "echo hello")
        assert result is True
        history = await session_mgr.get_command_history(session.session_id)
        assert len(history) == 1
        assert history[0] == "echo hello"

    async def test_record_command_not_found(self, session_mgr: SessionManager) -> None:
        result = await session_mgr.record_command("nonexistent", "echo")
        assert result is False

    async def test_get_command_history_not_found(self, session_mgr: SessionManager) -> None:
        history = await session_mgr.get_command_history("nonexistent")
        assert history == []

    async def test_get_command_history_limit(self, session_mgr: SessionManager) -> None:
        session = await session_mgr.create_session(runtime_id="rt-1", name="hist")
        for i in range(10):
            await session_mgr.record_command(session.session_id, f"cmd-{i}")
        history = await session_mgr.get_command_history(session.session_id, limit=3)
        assert len(history) == 3

    async def test_remove_session(self, session_mgr: SessionManager) -> None:
        session = await session_mgr.create_session(runtime_id="rt-1", name="remove-me")
        result = await session_mgr.remove_session(session.session_id)
        assert result is True
        assert await session_mgr.get_session(session.session_id) is None

    async def test_remove_session_not_found(self, session_mgr: SessionManager) -> None:
        assert await session_mgr.remove_session("nonexistent") is False

    async def test_close_all_for_runtime(self, session_mgr: SessionManager) -> None:
        await session_mgr.create_session(runtime_id="rt-1", name="a")
        await session_mgr.create_session(runtime_id="rt-1", name="b")
        count = await session_mgr.close_all_for_runtime("rt-1")
        assert count == 2
        assert await session_mgr.count_sessions("rt-1") == 2  # still tracked but closed

    async def test_count_sessions(self, session_mgr: SessionManager) -> None:
        await session_mgr.create_session(runtime_id="rt-1", name="only")
        count = await session_mgr.count_sessions("rt-1")
        assert count == 1

    async def test_count_sessions_empty(self, session_mgr: SessionManager) -> None:
        assert await session_mgr.count_sessions("rt-missing") == 0
