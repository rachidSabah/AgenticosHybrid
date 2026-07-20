"""Tests for services.runtime_discovery domain models, registry, and cache."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from services.runtime_discovery.cache import RuntimeCache as RuntimeCacheService
from services.runtime_discovery.models import (
    BindingStatus,
    DiscoveryProviderType,
    HealthStatus,
    Runtime,
    RuntimeBinding,
    RuntimeBindingConfig,
    RuntimeCacheEntry,
    RuntimeCapability,
    RuntimeConfiguration,
    RuntimeDiscoveryResult,
    RuntimeEvent,
    RuntimeHealth,
    RuntimeMetadata,
    RuntimeProfile,
    RuntimeStatus,
    RuntimeTelemetry,
    RuntimeType,
    RuntimeValidation,
    RuntimeValidationResult,
    ValidationStatus,
)
from services.runtime_discovery.registry import RuntimeRegistry, RuntimeRegistryError


class TestRuntimeType:
    def test_all_runtime_types_present(self) -> None:
        types = {e.value for e in RuntimeType}
        expected = {
            "claude_code",
            "gemini_cli",
            "codex_cli",
            "hermes",
            "openhands",
            "aider",
            "continue",
            "cline",
            "roo_code",
            "ollama",
            "python",
            "nodejs",
            "docker",
            "git",
            "gh_cli",
            "mcp_server",
            "custom",
        }
        assert types == expected


class TestRuntimeStatus:
    def test_all_statuses_present(self) -> None:
        statuses = {e.value for e in RuntimeStatus}
        expected = {
            "discovered",
            "validating",
            "validated",
            "profiling",
            "binding",
            "bound",
            "active",
            "degraded",
            "unhealthy",
            "disabled",
            "unbound",
            "lost",
        }
        assert statuses == expected


class TestDiscoveryProviderType:
    def test_all_providers_present(self) -> None:
        providers = {e.value for e in DiscoveryProviderType}
        expected = {
            "path",
            "filesystem",
            "env_var",
            "registry",
            "wsl",
            "docker",
            "known_install_dirs",
            "config_file",
            "vscode",
            "jetbrains",
            "custom",
        }
        assert providers == expected


class TestRuntimeModel:
    def test_defaults(self) -> None:
        r = Runtime()
        assert r.runtime_type == RuntimeType.CUSTOM
        assert r.status == RuntimeStatus.DISCOVERED
        assert r.name == ""
        assert r.capabilities == []
        assert isinstance(r.metadata, RuntimeMetadata)
        assert r.confidence == 0.0
        assert r.source == DiscoveryProviderType.PATH

    def test_custom_values(self) -> None:
        r = Runtime(
            name="python3",
            runtime_type=RuntimeType.PYTHON,
            version="3.14.0",
            status=RuntimeStatus.BOUND,
        )
        assert r.name == "python3"
        assert r.runtime_type == RuntimeType.PYTHON
        assert r.version == "3.14.0"
        assert r.status == RuntimeStatus.BOUND

    def test_to_dict(self) -> None:
        r = Runtime(
            name="git",
            runtime_type=RuntimeType.GIT,
            version="2.40.0",
        )
        d = r.to_dict()
        assert d["name"] == "git"
        assert d["runtime_type"] == "git"
        assert d["version"] == "2.40.0"
        assert d["status"] == "discovered"
        assert "runtime_id" in d
        assert "discovered_at" in d

    def test_unique_ids(self) -> None:
        r1 = Runtime()
        r2 = Runtime()
        assert r1.runtime_id != r2.runtime_id


class TestRuntimeCapability:
    def test_defaults(self) -> None:
        c = RuntimeCapability()
        assert c.namespace == ""
        assert c.enabled is True

    def test_custom(self) -> None:
        c = RuntimeCapability(namespace="code.read", description="Read code files", version="1.0")
        assert c.namespace == "code.read"
        assert c.description == "Read code files"


class TestRuntimeMetadata:
    def test_defaults(self) -> None:
        m = RuntimeMetadata()
        assert m.vendor == ""
        assert m.tags == []

    def test_custom(self) -> None:
        m = RuntimeMetadata(vendor="Anthropic", tags=["claude", "ai"])
        assert m.vendor == "Anthropic"
        assert m.tags == ["claude", "ai"]


class TestRuntimeDiscoveryResult:
    def test_defaults(self) -> None:
        r = RuntimeDiscoveryResult()
        assert r.found is False
        assert r.confidence == 0.0
        assert r.runtime_type == RuntimeType.CUSTOM
        assert r.source == DiscoveryProviderType.PATH

    def test_found_result(self) -> None:
        r = RuntimeDiscoveryResult(
            name="python",
            runtime_type=RuntimeType.PYTHON,
            version="3.14.0",
            binary_path="/usr/bin/python3",
            found=True,
            confidence=0.9,
        )
        assert r.found is True
        assert r.confidence == 0.9
        assert r.version == "3.14.0"


class TestRuntimeProfile:
    def test_defaults(self) -> None:
        p = RuntimeProfile()
        assert p.supports_streaming is False
        assert p.max_concurrency == 1

    def test_custom(self) -> None:
        p = RuntimeProfile(
            runtime_type=RuntimeType.CLAUDE_CODE,
            version="4.0.0",
            supports_streaming=True,
            max_concurrency=1,
            latency_estimate_ms=15000.0,
        )
        assert p.runtime_type == RuntimeType.CLAUDE_CODE
        assert p.supports_streaming is True
        assert p.latency_estimate_ms == 15000.0

    def test_to_dict(self) -> None:
        p = RuntimeProfile(
            runtime_type=RuntimeType.PYTHON,
            version="3.14.0",
            supports_streaming=False,
        )
        d = p.to_dict()
        assert d["runtime_type"] == "python"
        assert d["version"] == "3.14.0"
        assert d["supports_streaming"] is False


class TestRuntimeConfiguration:
    def test_defaults(self) -> None:
        c = RuntimeConfiguration()
        assert c.enabled is True
        assert c.auto_start is True
        assert c.health_check_interval_s == 60
        assert c.max_retries == 3

    def test_custom(self) -> None:
        c = RuntimeConfiguration(
            runtime_id="test123",
            enabled=False,
            auto_start=False,
            timeout_s=600.0,
        )
        assert c.runtime_id == "test123"
        assert c.enabled is False
        assert c.timeout_s == 600.0

    def test_to_dict(self) -> None:
        c = RuntimeConfiguration(runtime_id="test123")
        d = c.to_dict()
        assert d["runtime_id"] == "test123"
        assert d["enabled"] is True


class TestRuntimeHealth:
    def test_defaults(self) -> None:
        h = RuntimeHealth()
        assert h.healthy is True
        assert h.status == HealthStatus.UNKNOWN
        assert h.consecutive_failures == 0

    def test_record_success(self) -> None:
        h = RuntimeHealth()
        h.record_failure("test error")
        assert h.healthy is False
        h.record_success(response_time_ms=50.0)
        assert h.healthy is True
        assert h.status == HealthStatus.HEALTHY
        assert h.consecutive_failures == 0
        assert h.response_time_ms == 50.0

    def test_record_failure(self) -> None:
        h = RuntimeHealth()
        h.record_failure("err1")
        assert h.healthy is False
        assert h.status == HealthStatus.DEGRADED
        h.record_failure("err2")
        assert h.consecutive_failures == 2
        h.record_failure("err3")
        assert h.status == HealthStatus.UNHEALTHY
        assert h.consecutive_failures == 3


class TestRuntimeValidation:
    def test_defaults(self) -> None:
        v = RuntimeValidation()
        assert v.status == ValidationStatus.PENDING
        assert v.errors == []

    def test_passed_factory(self) -> None:
        v = RuntimeValidation.passed()
        assert v.status == ValidationStatus.PASSED
        assert v.executable_exists is True
        assert v.health_check_passed is True

    def test_failed_factory(self) -> None:
        v = RuntimeValidation.failed("binary not found")
        assert v.status == ValidationStatus.FAILED
        assert v.errors == ["binary not found"]


class TestRuntimeValidationResult:
    def test_defaults(self) -> None:
        r = RuntimeValidationResult()
        assert r.status == ValidationStatus.PENDING
        assert r.errors == []


class TestRuntimeCacheEntry:
    def test_is_expired(self) -> None:
        entry = RuntimeCacheEntry(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        assert entry.is_expired() is True

    def test_not_expired(self) -> None:
        entry = RuntimeCacheEntry(expires_at=datetime.now(UTC) + timedelta(hours=1))
        assert entry.is_expired() is False

    def test_with_hit_increments(self) -> None:
        entry = RuntimeCacheEntry()
        assert entry.hit_count == 0
        entry.with_hit()
        assert entry.hit_count == 1


class TestRuntimeBinding:
    def test_defaults(self) -> None:
        b = RuntimeBinding()
        assert b.status == BindingStatus.PENDING
        assert b.binding_config is None

    def test_custom(self) -> None:
        b = RuntimeBinding(
            runtime_id="test123",
            engine_name="python-engine",
            status=BindingStatus.BOUND,
        )
        assert b.runtime_id == "test123"
        assert b.status == BindingStatus.BOUND


class TestRuntimeBindingConfig:
    def test_defaults(self) -> None:
        c = RuntimeBindingConfig()
        assert c.auto_register is True
        assert c.auto_start is True
        assert c.adapter_params == {}


class TestRuntimeTelemetry:
    def test_defaults(self) -> None:
        t = RuntimeTelemetry()
        assert t.tasks_completed == 0
        assert t.tasks_failed == 0
        assert t.total_duration_s == 0.0

    def test_record_execution_success(self) -> None:
        t = RuntimeTelemetry(runtime_type=RuntimeType.PYTHON, name="python3")
        t.record_execution(duration_s=2.5, success=True)
        assert t.tasks_completed == 1
        assert t.tasks_failed == 0
        assert t.total_duration_s == 2.5
        assert t.avg_duration_s == 2.5

    def test_record_execution_failure(self) -> None:
        t = RuntimeTelemetry(runtime_type=RuntimeType.PYTHON, name="python3")
        t.record_execution(duration_s=1.0, success=False)
        assert t.tasks_completed == 0
        assert t.tasks_failed == 1
        assert t.total_duration_s == 1.0


class TestRuntimeEvent:
    def test_defaults(self) -> None:
        e = RuntimeEvent()
        assert e.event_type == ""
        assert e.payload == {}
        assert e.event_id != ""

    def test_custom(self) -> None:
        e = RuntimeEvent(
            runtime_id="test123",
            event_type="runtime.discovery.scan.started",
            payload={"engines": 5},
        )
        assert e.runtime_id == "test123"
        assert e.payload["engines"] == 5


class TestRuntimeCacheService:
    def test_create_entry(self) -> None:
        cache = RuntimeCacheService()
        entry = cache.create_entry("path", "python", RuntimeType.PYTHON, {"version": "3.14"})
        assert entry.runtime_type == RuntimeType.PYTHON
        assert entry.name == "python"
        assert entry.data["version"] == "3.14"

    def test_get_set(self) -> None:
        cache = RuntimeCacheService()
        entry = cache.create_entry("path", "python", RuntimeType.PYTHON, {})
        cache.set(entry)
        retrieved = cache.get(entry.key)
        assert retrieved is not None
        assert retrieved.name == "python"

    def test_get_nonexistent(self) -> None:
        cache = RuntimeCacheService()
        assert cache.get("nonexistent") is None

    def test_invalidate(self) -> None:
        cache = RuntimeCacheService()
        entry = cache.create_entry("path", "python", RuntimeType.PYTHON, {})
        cache.set(entry)
        assert cache.count() == 1
        cache.invalidate(entry.key)
        assert cache.count() == 0

    def test_invalidate_all(self) -> None:
        cache = RuntimeCacheService()
        cache.set(cache.create_entry("a", "e1", RuntimeType.PYTHON, {}))
        cache.set(cache.create_entry("b", "e2", RuntimeType.GIT, {}))
        assert cache.count() == 2
        cache.invalidate_all()
        assert cache.count() == 0

    def test_eviction(self) -> None:
        cache = RuntimeCacheService(max_entries=2)
        cache.set(cache.create_entry("a", "e1", RuntimeType.PYTHON, {}))
        cache.set(cache.create_entry("b", "e2", RuntimeType.GIT, {}))
        cache.set(cache.create_entry("c", "e3", RuntimeType.DOCKER, {}))
        assert cache.count() <= 2

    def test_get_stats(self) -> None:
        cache = RuntimeCacheService()
        entry = cache.create_entry("path", "python", RuntimeType.PYTHON, {})
        cache.set(entry)
        cache.get(entry.key)
        stats = cache.get_stats()
        assert stats["total_entries"] == 1
        assert stats["total_hits"] >= 1

    def test_clean_expired(self) -> None:
        cache = RuntimeCacheService()
        cache.set(cache.create_entry("path", "python", RuntimeType.PYTHON, {}))
        entry = RuntimeCacheEntry(
            key="expired",
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
        )
        cache.set(entry)
        cleaned = cache.clean_expired()
        assert cleaned >= 1
        assert cache.count() >= 1

    def test_invalidate_by_engine(self) -> None:
        cache = RuntimeCacheService()
        cache.set(cache.create_entry("a", "python", RuntimeType.PYTHON, {}))
        cache.set(cache.create_entry("b", "git", RuntimeType.GIT, {}))
        cache.invalidate_by_engine("python")
        remaining = cache.list_entries()
        assert all(e.name != "python" for e in remaining)

    def test_make_key_consistency(self) -> None:
        cache = RuntimeCacheService()
        key1 = cache.make_key("path", "python")
        key2 = cache.make_key("path", "python")
        assert key1 == key2

    def test_invalidate_by_provider(self) -> None:
        cache = RuntimeCacheService()
        cache.set(cache.create_entry("path", "python", RuntimeType.PYTHON, {}))
        cache.set(cache.create_entry("env", "node", RuntimeType.NODEJS, {}))
        cache.invalidate_by_provider("path")
        remaining = cache.list_entries()
        assert all(e.name != "python" for e in remaining)


class TestRuntimeRegistry:
    @pytest.fixture
    def registry(self) -> RuntimeRegistry:
        return RuntimeRegistry()

    @pytest.fixture
    def sample_runtime(self) -> Runtime:
        return Runtime(
            name="python3",
            runtime_type=RuntimeType.PYTHON,
            version="3.14.0",
        )

    async def test_register_and_get(  # noqa: E501
        self, registry: RuntimeRegistry, sample_runtime: Runtime
    ) -> None:
        await registry.register(sample_runtime)
        retrieved = await registry.get(sample_runtime.runtime_id)
        assert retrieved is not None
        assert retrieved.name == "python3"

    async def test_register_duplicate_updates(self, registry: RuntimeRegistry) -> None:
        r1 = Runtime(name="python3", runtime_type=RuntimeType.PYTHON)
        r2 = Runtime(name="python3", runtime_type=RuntimeType.PYTHON, version="3.14.0")
        await registry.register(r1)
        await registry.register(r2)
        assert (await registry.count()) == 1
        retrieved = await registry.get(r1.runtime_id)
        assert retrieved is not None
        assert retrieved.version == "3.14.0"

    async def test_unregister(self, registry: RuntimeRegistry, sample_runtime: Runtime) -> None:
        await registry.register(sample_runtime)
        result = await registry.unregister(sample_runtime.runtime_id)
        assert result is True
        assert await registry.get(sample_runtime.runtime_id) is None

    async def test_unregister_nonexistent(self, registry: RuntimeRegistry) -> None:
        result = await registry.unregister("nonexistent")
        assert result is False

    async def test_find_by_name(self, registry: RuntimeRegistry, sample_runtime: Runtime) -> None:
        await registry.register(sample_runtime)
        found = await registry.find_by_name("python3")
        assert found is not None
        assert found.runtime_type == RuntimeType.PYTHON

    async def test_find_by_name_nonexistent(self, registry: RuntimeRegistry) -> None:
        assert await registry.find_by_name("nonexistent") is None

    async def test_find_by_type(self, registry: RuntimeRegistry) -> None:
        await registry.register(Runtime(name="python3", runtime_type=RuntimeType.PYTHON))
        await registry.register(Runtime(name="python", runtime_type=RuntimeType.PYTHON))
        await registry.register(Runtime(name="git", runtime_type=RuntimeType.GIT))
        results = await registry.find_by_type(RuntimeType.PYTHON)
        assert len(results) == 2

    async def test_list_all(self, registry: RuntimeRegistry) -> None:
        await registry.register(Runtime(name="a", runtime_type=RuntimeType.PYTHON))
        await registry.register(Runtime(name="b", runtime_type=RuntimeType.GIT))
        all_runtimes = await registry.list()
        assert len(all_runtimes) == 2

    async def test_list_by_status(self, registry: RuntimeRegistry) -> None:
        await registry.register(
            Runtime(name="a", runtime_type=RuntimeType.PYTHON, status=RuntimeStatus.BOUND)
        )
        await registry.register(
            Runtime(name="b", runtime_type=RuntimeType.GIT, status=RuntimeStatus.DISCOVERED)
        )
        bound = await registry.list(status=RuntimeStatus.BOUND.value)
        assert len(bound) == 1

    async def test_update(self, registry: RuntimeRegistry, sample_runtime: Runtime) -> None:
        await registry.register(sample_runtime)
        sample_runtime.version = "3.15.0"
        updated = await registry.update(sample_runtime)
        assert updated.version == "3.15.0"

    async def test_update_nonexistent(self, registry: RuntimeRegistry) -> None:
        with pytest.raises(RuntimeRegistryError):
            await registry.update(Runtime(name="ghost"))

    async def test_update_status(self, registry: RuntimeRegistry, sample_runtime: Runtime) -> None:
        await registry.register(sample_runtime)
        result = await registry.update_status(sample_runtime.runtime_id, RuntimeStatus.BOUND)
        assert result is not None
        assert result.status == RuntimeStatus.BOUND

    async def test_update_status_nonexistent(self, registry: RuntimeRegistry) -> None:
        result = await registry.update_status("ghost", RuntimeStatus.BOUND)
        assert result is None

    async def test_count(self, registry: RuntimeRegistry) -> None:
        await registry.register(Runtime(name="a", runtime_type=RuntimeType.PYTHON))
        await registry.register(Runtime(name="b", runtime_type=RuntimeType.GIT))
        assert await registry.count() == 2

    async def test_count_by_status(self, registry: RuntimeRegistry) -> None:
        await registry.register(
            Runtime(name="a", runtime_type=RuntimeType.PYTHON, status=RuntimeStatus.BOUND)
        )
        await registry.register(
            Runtime(name="b", runtime_type=RuntimeType.GIT, status=RuntimeStatus.DISCOVERED)
        )
        assert await registry.count(status="bound") == 1

    async def test_search(self, registry: RuntimeRegistry) -> None:
        await registry.register(Runtime(name="python3", runtime_type=RuntimeType.PYTHON))
        await registry.register(
            Runtime(name="git", runtime_type=RuntimeType.GIT, display_name="Git SCM")
        )
        results = await registry.search("python")
        assert len(results) == 1
        results = await registry.search("git")
        assert len(results) == 1

    async def test_registry_snapshot(self, registry: RuntimeRegistry) -> None:
        await registry.register(
            Runtime(name="python3", runtime_type=RuntimeType.PYTHON, status=RuntimeStatus.BOUND)
        )
        await registry.register(
            Runtime(name="git", runtime_type=RuntimeType.GIT, status=RuntimeStatus.BOUND)
        )
        await registry.register(
            Runtime(name="node", runtime_type=RuntimeType.NODEJS, status=RuntimeStatus.DISCOVERED)
        )
        snapshot = await registry.get_registry_snapshot()
        assert snapshot["total_runtimes"] == 3
        assert snapshot["by_status"]["bound"] == 2
        assert snapshot["by_status"]["discovered"] == 1
