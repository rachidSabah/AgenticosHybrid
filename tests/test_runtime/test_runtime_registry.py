"""Tests for RuntimeRegistry — thread-safe CRUD, deep copy, dedup."""

import pytest

from agentic_os.core.runtime.runtime import Runtime, RuntimeStatus, RuntimeType
from agentic_os.core.runtime.runtime_registry import RuntimeRegistry


@pytest.fixture
async def registry() -> RuntimeRegistry:
    return RuntimeRegistry()


@pytest.fixture
def sample_runtime() -> Runtime:
    return Runtime(name="test-runtime", type=RuntimeType.PYTHON)


@pytest.mark.asyncio
class TestRuntimeRegistry:
    async def test_register_returns_id(
        self, registry: RuntimeRegistry, sample_runtime: Runtime
    ) -> None:
        rid = await registry.register(sample_runtime)
        assert rid == sample_runtime.id

    async def test_register_and_get(
        self, registry: RuntimeRegistry, sample_runtime: Runtime
    ) -> None:
        rid = await registry.register(sample_runtime)
        fetched = await registry.get(rid)
        assert fetched is not None
        assert fetched.name == "test-runtime"

    async def test_register_duplicate_name_raises(self, registry: RuntimeRegistry) -> None:
        r1 = Runtime(name="dup-name")
        r2 = Runtime(name="dup-name")
        await registry.register(r1)
        with pytest.raises(ValueError, match="already exists"):
            await registry.register(r2)

    async def test_register_same_name_different_allowed_after_remove(
        self, registry: RuntimeRegistry
    ) -> None:
        r1 = Runtime(name="reusable")
        await registry.register(r1)
        await registry.remove(r1.id)
        r2 = Runtime(name="reusable")
        rid = await registry.register(r2)
        assert rid == r2.id

    async def test_get_nonexistent(self, registry: RuntimeRegistry) -> None:
        fetched = await registry.get("nonexistent")
        assert fetched is None

    async def test_get_returns_deep_copy(
        self, registry: RuntimeRegistry, sample_runtime: Runtime
    ) -> None:
        await registry.register(sample_runtime)
        fetched = await registry.get(sample_runtime.id)
        assert fetched is not None
        fetched.name = "mutated"
        # Original should be unmodified
        original = await registry.get(sample_runtime.id)
        assert original is not None
        assert original.name == "test-runtime"

    async def test_update_existing(
        self, registry: RuntimeRegistry, sample_runtime: Runtime
    ) -> None:
        await registry.register(sample_runtime)
        sample_runtime.status = RuntimeStatus.READY
        result = await registry.update(sample_runtime)
        assert result is True
        fetched = await registry.get(sample_runtime.id)
        assert fetched is not None
        assert fetched.status == RuntimeStatus.READY

    async def test_update_nonexistent(self, registry: RuntimeRegistry) -> None:
        r = Runtime(name="ghost")
        result = await registry.update(r)
        assert result is False

    async def test_update_name_change_reindexes(self, registry: RuntimeRegistry) -> None:
        r = Runtime(name="old-name")
        await registry.register(r)
        r.name = "new-name"
        await registry.update(r)
        # Can get by new name
        by_new = await registry.get_by_name("new-name")
        assert by_new is not None
        # Old name should not work
        by_old = await registry.get_by_name("old-name")
        assert by_old is None

    async def test_remove_existing(
        self, registry: RuntimeRegistry, sample_runtime: Runtime
    ) -> None:
        await registry.register(sample_runtime)
        result = await registry.remove(sample_runtime.id)
        assert result is True
        assert await registry.get(sample_runtime.id) is None

    async def test_remove_nonexistent(self, registry: RuntimeRegistry) -> None:
        result = await registry.remove("nonexistent")
        assert result is False

    async def test_get_by_name(self, registry: RuntimeRegistry, sample_runtime: Runtime) -> None:
        await registry.register(sample_runtime)
        fetched = await registry.get_by_name("test-runtime")
        assert fetched is not None
        assert fetched.id == sample_runtime.id

    async def test_get_by_name_not_found(self, registry: RuntimeRegistry) -> None:
        assert await registry.get_by_name("missing") is None

    async def test_get_by_type(self, registry: RuntimeRegistry) -> None:
        py = Runtime(name="py1", type=RuntimeType.PYTHON)
        js = Runtime(name="js1", type=RuntimeType.NODE)
        await registry.register(py)
        await registry.register(js)
        pythons = await registry.get_by_type(RuntimeType.PYTHON)
        assert len(pythons) == 1
        assert pythons[0].name == "py1"

    async def test_get_all(self, registry: RuntimeRegistry) -> None:
        await registry.register(Runtime(name="a"))
        await registry.register(Runtime(name="b"))
        all_runtimes = await registry.get_all()
        assert len(all_runtimes) == 2

    async def test_get_all_empty(self, registry: RuntimeRegistry) -> None:
        assert await registry.get_all() == []

    async def test_get_active_filters_terminal(self, registry: RuntimeRegistry) -> None:
        ready = Runtime(name="ready", status=RuntimeStatus.READY)
        stopped = Runtime(name="stopped", status=RuntimeStatus.STOPPED)
        crashed = Runtime(name="crashed", status=RuntimeStatus.CRASHED)
        failed = Runtime(name="failed", status=RuntimeStatus.FAILED)
        await registry.register(ready)
        await registry.register(stopped)
        await registry.register(crashed)
        await registry.register(failed)
        active = await registry.get_active()
        assert len(active) == 1
        assert active[0].name == "ready"

    async def test_count(self, registry: RuntimeRegistry) -> None:
        assert await registry.count() == 0
        await registry.register(Runtime(name="a"))
        assert await registry.count() == 1

    async def test_get_raw_returns_internal_ref(
        self, registry: RuntimeRegistry, sample_runtime: Runtime
    ) -> None:
        await registry.register(sample_runtime)
        raw = await registry.get_raw(sample_runtime.id)
        assert raw is not None
        # Mutating raw affects internal state (caller must update)
        raw.name = "modified-via-raw"
        fetched = await registry.get(sample_runtime.id)
        assert fetched is not None
        assert fetched.name == "modified-via-raw"

    async def test_concurrent_registrations(self, registry: RuntimeRegistry) -> None:
        import asyncio

        async def register_n(n: int) -> None:
            r = Runtime(name=f"concurrent-{n}")
            await registry.register(r)

        await asyncio.gather(*[register_n(i) for i in range(10)])
        assert await registry.count() == 10

    async def test_concurrent_reads_during_writes(self, registry: RuntimeRegistry) -> None:
        import asyncio

        async def writer() -> None:
            for i in range(20):
                r = Runtime(name=f"w{i}")
                await registry.register(r)
                await asyncio.sleep(0)

        async def reader() -> None:
            for _ in range(20):
                _ = await registry.get_all()
                await asyncio.sleep(0)

        await asyncio.gather(writer(), reader())
        assert await registry.count() == 20
