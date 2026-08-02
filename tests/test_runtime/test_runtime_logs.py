"""Tests for LogManager — ring-buffer append, filtering, search, export."""

import pytest

from agentic_os.core.runtime.runtime import RuntimeLog
from agentic_os.core.runtime.runtime_logs import LogManager


@pytest.fixture
async def log_mgr() -> LogManager:
    return LogManager()


@pytest.mark.asyncio
class TestLogManager:
    async def test_append_and_count(self, log_mgr: LogManager) -> None:
        await log_mgr.append("rt-1", RuntimeLog(text="hello", level="info"))
        count = await log_mgr.count("rt-1")
        assert count == 1

    async def test_append_text_convenience(self, log_mgr: LogManager) -> None:
        await log_mgr.append_text("rt-1", "convenient log", stream="stdout", level="info")
        count = await log_mgr.count("rt-1")
        assert count == 1

    async def test_get_logs_all(self, log_mgr: LogManager) -> None:
        await log_mgr.append_text("rt-1", "first")
        await log_mgr.append_text("rt-1", "second")
        logs = await log_mgr.get_logs("rt-1")
        assert len(logs) == 2

    async def test_get_logs_empty(self, log_mgr: LogManager) -> None:
        logs = await log_mgr.get_logs("nonexistent")
        assert logs == []

    async def test_get_logs_limit(self, log_mgr: LogManager) -> None:
        for i in range(10):
            await log_mgr.append_text("rt-1", f"log-{i}")
        logs = await log_mgr.get_logs("rt-1", limit=3)
        assert len(logs) == 3

    async def test_get_logs_offset(self, log_mgr: LogManager) -> None:
        for i in range(10):
            await log_mgr.append_text("rt-1", f"log-{i}")
        logs = await log_mgr.get_logs("rt-1", limit=5, offset=5)
        assert len(logs) == 5

    async def test_filter_by_stream(self, log_mgr: LogManager) -> None:
        await log_mgr.append_text("rt-1", "stdout msg", stream="stdout")
        await log_mgr.append_text("rt-1", "stderr msg", stream="stderr")
        stdout = await log_mgr.get_logs("rt-1", stream="stdout")
        assert len(stdout) == 1
        assert stdout[0].stream == "stdout"

    async def test_filter_by_level(self, log_mgr: LogManager) -> None:
        await log_mgr.append_text("rt-1", "info msg", level="info")
        await log_mgr.append_text("rt-1", "error msg", level="error")
        errors = await log_mgr.get_logs("rt-1", level="error")
        assert len(errors) == 1
        assert errors[0].level == "error"

    async def test_filter_by_search(self, log_mgr: LogManager) -> None:
        await log_mgr.append_text("rt-1", "this is important")
        await log_mgr.append_text("rt-1", "this is trivial")
        found = await log_mgr.get_logs("rt-1", search="important")
        assert len(found) == 1
        assert "important" in found[0].text

    async def test_search_convenience(self, log_mgr: LogManager) -> None:
        await log_mgr.append_text("rt-1", "find me")
        await log_mgr.append_text("rt-1", "ignore me")
        results = await log_mgr.search("rt-1", "find me")
        assert len(results) == 1

    async def test_search_regex(self, log_mgr: LogManager) -> None:
        await log_mgr.append_text("rt-1", "error: something broke")
        await log_mgr.append_text("rt-1", "info: all good")
        results = await log_mgr.search_regex("rt-1", r"error.*broke")
        assert len(results) == 1

    async def test_search_regex_empty(self, log_mgr: LogManager) -> None:
        results = await log_mgr.search_regex("nonexistent", r".*")
        assert results == []

    async def test_clear(self, log_mgr: LogManager) -> None:
        await log_mgr.append_text("rt-1", "to be cleared")
        cleared = await log_mgr.clear("rt-1")
        assert cleared == 1
        assert await log_mgr.count("rt-1") == 0

    async def test_clear_empty(self, log_mgr: LogManager) -> None:
        cleared = await log_mgr.clear("nonexistent")
        assert cleared == 0

    async def test_list_runtimes(self, log_mgr: LogManager) -> None:
        await log_mgr.append_text("rt-1", "a")
        await log_mgr.append_text("rt-2", "b")
        runtimes = await log_mgr.list_runtimes()
        assert set(runtimes) == {"rt-1", "rt-2"}

    async def test_total_entries(self, log_mgr: LogManager) -> None:
        await log_mgr.append_text("rt-1", "a")
        await log_mgr.append_text("rt-2", "b")
        await log_mgr.append_text("rt-2", "c")
        assert await log_mgr.total_entries() == 3

    async def test_export_text(self, log_mgr: LogManager) -> None:
        await log_mgr.append_text("rt-1", "export test")
        text = await log_mgr.export("rt-1", fmt="text")
        assert "export test" in text

    async def test_export_json(self, log_mgr: LogManager) -> None:
        await log_mgr.append_text("rt-1", "json test")
        json_out = await log_mgr.export("rt-1", fmt="json")
        assert "json test" in json_out

    async def test_export_empty(self, log_mgr: LogManager) -> None:
        text = await log_mgr.export("nonexistent")
        assert text == ""

    async def test_rotation_callback(self, log_mgr: LogManager) -> None:
        fired = []

        def callback(rid: str, evicted: list[RuntimeLog]) -> None:
            fired.append((rid, len(evicted)))

        log_mgr.set_rotation_callback("rt-1", callback)
        # Not rotating yet, just verify callback was set
        await log_mgr.append_text("rt-1", "test")
        assert len(fired) == 0  # no rotation yet

    async def test_set_rotation_callback_none_clears(self, log_mgr: LogManager) -> None:
        log_mgr.set_rotation_callback("rt-1", lambda rid, evicted: None)
        log_mgr.set_rotation_callback("rt-1", None)
        # Should not crash
        await log_mgr.append_text("rt-1", "test")

    async def test_multiple_runtimes_independent(self, log_mgr: LogManager) -> None:
        await log_mgr.append_text("rt-a", "a msg")
        await log_mgr.append_text("rt-b", "b msg")
        assert await log_mgr.count("rt-a") == 1
        assert await log_mgr.count("rt-b") == 1
