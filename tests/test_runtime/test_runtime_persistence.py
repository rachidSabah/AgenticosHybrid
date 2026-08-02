"""Tests for RuntimePersistence — save/load JSON, state recovery, corrupt data."""

import pytest

from agentic_os.core.runtime.runtime import Runtime, RuntimeHealth, RuntimeStatus, RuntimeType
from agentic_os.core.runtime.runtime_persistence import RuntimePersistence


@pytest.fixture
async def persistence(tmp_path) -> RuntimePersistence:
    return RuntimePersistence(data_dir=str(tmp_path))


@pytest.mark.asyncio
class TestRuntimePersistence:
    async def test_save_returns_path(self, persistence: RuntimePersistence) -> None:
        r = Runtime(name="save-test", type=RuntimeType.PYTHON)
        path = await persistence.save(r)
        assert path.endswith(f"{r.id}.json")

    async def test_save_and_load(self, persistence: RuntimePersistence) -> None:
        r = Runtime(name="roundtrip", type=RuntimeType.CLAUDE_CODE, version="1.0.0")
        await persistence.save(r)
        loaded = await persistence.load(r.id)
        assert loaded is not None
        assert loaded.name == "roundtrip"
        assert loaded.type == RuntimeType.CLAUDE_CODE
        assert loaded.version == "1.0.0"

    async def test_load_nonexistent(self, persistence: RuntimePersistence) -> None:
        loaded = await persistence.load("nonexistent")
        assert loaded is None

    async def test_load_all_empty(self, persistence: RuntimePersistence) -> None:
        runtimes = await persistence.load_all()
        assert runtimes == []

    async def test_load_all_multiple(self, persistence: RuntimePersistence) -> None:
        r1 = Runtime(name="a")
        r2 = Runtime(name="b")
        await persistence.save(r1)
        await persistence.save(r2)
        runtimes = await persistence.load_all()
        assert len(runtimes) == 2

    async def test_delete_existing(self, persistence: RuntimePersistence) -> None:
        r = Runtime(name="delete-me")
        await persistence.save(r)
        result = await persistence.delete(r.id)
        assert result is True
        assert await persistence.load(r.id) is None

    async def test_delete_nonexistent(self, persistence: RuntimePersistence) -> None:
        result = await persistence.delete("nonexistent")
        assert result is False

    async def test_list_saved(self, persistence: RuntimePersistence) -> None:
        r1 = Runtime(name="a")
        r2 = Runtime(name="b")
        await persistence.save(r1)
        await persistence.save(r2)
        saved = await persistence.list_saved()
        assert r1.id in saved
        assert r2.id in saved

    async def test_list_saved_empty(self, persistence: RuntimePersistence) -> None:
        saved = await persistence.list_saved()
        assert saved == []

    async def test_corrupt_json_returns_none(self, persistence: RuntimePersistence) -> None:
        r = Runtime(name="corrupt-me")
        path = await persistence.save(r)
        # Overwrite file with invalid JSON
        with open(path, "w", encoding="utf-8") as f:
            f.write("not valid json")
        loaded = await persistence.load(r.id)
        assert loaded is None

    async def test_missing_file_returns_none(self, persistence: RuntimePersistence) -> None:
        loaded = await persistence.load("missing")
        assert loaded is None

    async def test_data_dir_property(self, persistence: RuntimePersistence) -> None:
        assert persistence.data_dir is not None

    async def test_save_updates_existing(self, persistence: RuntimePersistence) -> None:
        r = Runtime(name="update-test", restart_count=5)
        await persistence.save(r)
        r.restart_count = 10
        await persistence.save(r)
        loaded = await persistence.load(r.id)
        assert loaded is not None
        assert loaded.restart_count == 10

    async def test_full_state_roundtrip(self, persistence: RuntimePersistence) -> None:
        """Verify that all fields survive a save/load cycle."""
        original = Runtime(
            name="full-state",
            type=RuntimeType.MCP_SERVER,
            status=RuntimeStatus.READY,
            health=RuntimeHealth.HEALTHY,
            command="/usr/bin/node",
            arguments=["server.js", "--port", "3000"],
            environment={"NODE_ENV": "production"},
            pid=12345,
            version="2.0.0",
            restart_count=3,
            crash_count=1,
            discovered=True,
            source="auto",
        )
        await persistence.save(original)
        loaded = await persistence.load(original.id)
        assert loaded is not None
        assert loaded.name == original.name
        assert loaded.type == original.type
        assert loaded.status == original.status
        assert loaded.health == original.health
        assert loaded.command == original.command
        assert loaded.arguments == original.arguments
        assert loaded.environment == original.environment
        assert loaded.pid == original.pid
        assert loaded.version == original.version
        assert loaded.restart_count == original.restart_count
        assert loaded.crash_count == original.crash_count
        assert loaded.discovered == original.discovered
        assert loaded.source == original.source
