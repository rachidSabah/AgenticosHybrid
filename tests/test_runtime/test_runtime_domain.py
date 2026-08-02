"""Tests for runtime domain model — enums, dataclasses, serialization."""

from datetime import UTC, datetime

from agentic_os.core.runtime.runtime import (
    RestartPolicy,
    Runtime,
    RuntimeCapability,
    RuntimeHealth,
    RuntimeLog,
    RuntimeMetrics,
    RuntimeSession,
    RuntimeStatus,
    RuntimeType,
)

# ── Enum tests ──────────────────────────────────────────────────────────────────


class TestRuntimeType:
    def test_values(self) -> None:
        assert RuntimeType.CUSTOM == "custom"
        assert RuntimeType.CLAUDE_CODE == "claude_code"
        assert RuntimeType.HERMES == "hermes"
        assert RuntimeType.PYTHON == "python"
        assert RuntimeType.NODE == "node"
        assert RuntimeType.DOCKER == "docker"

    def test_all_types_have_unique_values(self) -> None:
        values = [e.value for e in RuntimeType]
        assert len(values) == len(set(values))

    def test_str_conversion(self) -> None:
        assert str(RuntimeType.PYTHON) == "python"


class TestRuntimeStatus:
    def test_values(self) -> None:
        assert RuntimeStatus.DISCOVERED == "discovered"
        assert RuntimeStatus.READY == "ready"
        assert RuntimeStatus.STOPPED == "stopped"
        assert RuntimeStatus.CRASHED == "crashed"
        assert RuntimeStatus.FAILED == "failed"

    def test_terminal_states(self) -> None:
        terminal = {RuntimeStatus.STOPPED, RuntimeStatus.CRASHED, RuntimeStatus.FAILED}
        assert len(terminal) == 3

    def test_from_string(self) -> None:
        assert RuntimeStatus("ready") == RuntimeStatus.READY
        assert RuntimeStatus("crashed") == RuntimeStatus.CRASHED


class TestRuntimeHealth:
    def test_values(self) -> None:
        assert RuntimeHealth.HEALTHY == "healthy"
        assert RuntimeHealth.UNHEALTHY == "unhealthy"
        assert RuntimeHealth.DEGRADED == "degraded"

    def test_from_string(self) -> None:
        assert RuntimeHealth("healthy") == RuntimeHealth.HEALTHY


class TestRestartPolicy:
    def test_values(self) -> None:
        assert RestartPolicy.NEVER == "never"
        assert RestartPolicy.ALWAYS == "always"
        assert RestartPolicy.ON_FAILURE == "on_failure"
        assert RestartPolicy.ON_CRASH == "on_crash"
        assert RestartPolicy.BACKOFF == "backoff"

    def test_all_policies_covered(self) -> None:
        assert len(list(RestartPolicy)) == 5


# ── RuntimeCapability ────────────────────────────────────────────────────────────


class TestRuntimeCapability:
    def test_default_construction(self) -> None:
        cap = RuntimeCapability(name="coding")
        assert cap.name == "coding"
        assert cap.version is None
        assert cap.enabled is True
        assert cap.metadata == {}

    def test_full_construction(self) -> None:
        cap = RuntimeCapability(
            name="docker", version="1.0", enabled=False, metadata={"key": "val"}
        )
        assert cap.name == "docker"
        assert cap.version == "1.0"
        assert cap.enabled is False
        assert cap.metadata["key"] == "val"


# ── RuntimeMetrics ───────────────────────────────────────────────────────────────


class TestRuntimeMetrics:
    def test_defaults(self) -> None:
        m = RuntimeMetrics()
        assert m.cpu_percent == 0.0
        assert m.memory_mb == 0.0
        assert m.threads == 0
        assert m.tokens_used == 0
        assert m.cost == 0.0
        assert m.latency_ms == 0.0
        assert m.queue_depth == 0
        assert m.active_tasks == 0
        assert m.restart_count == 0
        assert m.crash_count == 0
        assert m.uptime_seconds == 0.0

    def test_to_dict_round_trip(self) -> None:
        m = RuntimeMetrics(
            cpu_percent=45.5,
            memory_mb=256.0,
            threads=8,
            tokens_used=1500,
            cost=0.05,
            latency_ms=120.0,
            queue_depth=3,
            active_tasks=2,
            restart_count=1,
            crash_count=0,
            uptime_seconds=3600.0,
        )
        d = m.to_dict()
        assert d["cpu_percent"] == 45.5
        assert d["memory_mb"] == 256.0
        assert d["latency_ms"] == 120.0

        m2 = RuntimeMetrics.from_dict(d)
        assert m2.cpu_percent == 45.5
        assert m2.memory_mb == 256.0
        assert m2.uptime_seconds == 3600.0

    def test_from_dict_filters_unknown_keys(self) -> None:
        d = {"cpu_percent": 50.0, "memory_mb": 128.0, "unknown_field": "ignored"}
        m = RuntimeMetrics.from_dict(d)
        assert m.cpu_percent == 50.0
        assert m.memory_mb == 128.0

    def test_from_dict_empty(self) -> None:
        m = RuntimeMetrics.from_dict({})
        assert m.cpu_percent == 0.0


# ── RuntimeSession ───────────────────────────────────────────────────────────────


class TestRuntimeSession:
    def test_defaults(self) -> None:
        s = RuntimeSession()
        assert s.session_id is not None
        assert len(s.session_id) > 0
        assert s.active is True
        assert s.name == ""
        assert s.command_history == []

    def test_to_dict(self) -> None:
        s = RuntimeSession(name="my-session", working_directory="/tmp")
        d = s.to_dict()
        assert d["name"] == "my-session"
        assert d["working_directory"] == "/tmp"
        assert d["active"] is True
        assert d["closed_at"] is None
        assert "created_at" in d

    def test_close_sets_closed_at(self) -> None:
        s = RuntimeSession(name="temp")
        s.active = False
        s.closed_at = datetime.now(UTC)
        assert s.active is False
        assert s.closed_at is not None


# ── RuntimeLog ────────────────────────────────────────────────────────────────────


class TestRuntimeLog:
    def test_defaults(self) -> None:
        log = RuntimeLog()
        assert log.stream == "stdout"
        assert log.text == ""
        assert log.level == "info"

    def test_to_dict(self) -> None:
        log = RuntimeLog(stream="stderr", text="error message", level="error")
        d = log.to_dict()
        assert d["stream"] == "stderr"
        assert d["text"] == "error message"
        assert d["level"] == "error"


# ── Runtime (main model) ──────────────────────────────────────────────────────────


class TestRuntime:
    def test_default_construction(self) -> None:
        r = Runtime()
        assert r.id is not None
        assert len(r.id) > 0
        assert r.name == ""
        assert r.type == RuntimeType.CUSTOM
        assert r.status == RuntimeStatus.DISCOVERED
        assert r.health == RuntimeHealth.UNKNOWN
        assert r.command == ""
        assert r.arguments == []
        assert r.capabilities == []
        assert r.discovered is False

    def test_named_construction(self) -> None:
        r = Runtime(name="test-runtime", type=RuntimeType.PYTHON)
        assert r.name == "test-runtime"
        assert r.type == RuntimeType.PYTHON

    def test_to_dict_contains_required_fields(self) -> None:
        r = Runtime(name="demo", type=RuntimeType.CLAUDE_CODE)
        d = r.to_dict()
        assert d["id"] == r.id
        assert d["name"] == "demo"
        assert d["type"] == "claude_code"
        assert d["status"] == "discovered"
        assert d["health"] == "unknown"
        assert d["capabilities"] == []
        assert d["metrics"] is not None
        assert "_snapshot_at" not in d  # to_snapshot adds this

    def test_to_dict_with_sessions(self) -> None:
        sess = RuntimeSession(name="s1")
        r = Runtime(name="multi", sessions=[sess])
        d = r.to_dict()
        assert len(d["sessions"]) == 1
        assert d["sessions"][0]["name"] == "s1"

    def test_to_dict_with_active_session(self) -> None:
        sess = RuntimeSession(name="active-session")
        r = Runtime(name="with-session", active_session=sess)
        d = r.to_dict()
        assert d["active_session"] is not None
        assert d["active_session"]["name"] == "active-session"

    def test_to_dict_with_capabilities(self) -> None:
        caps = [
            RuntimeCapability(name="coding", enabled=True),
            RuntimeCapability(name="docker", enabled=False),
        ]
        r = Runtime(name="capped", capabilities=caps)
        d = r.to_dict()
        assert len(d["capabilities"]) == 2
        assert d["capabilities"][0]["name"] == "coding"

    def test_to_dict_with_metrics(self) -> None:
        m = RuntimeMetrics(cpu_percent=75.0, memory_mb=512.0)
        r = Runtime(name="metric-demo", metrics=m)
        d = r.to_dict()
        assert d["metrics"]["cpu_percent"] == 75.0
        assert d["metrics"]["memory_mb"] == 512.0

    def test_to_snapshot_includes_timestamp(self) -> None:
        r = Runtime(name="snapshot-test")
        snap = r.to_snapshot()
        assert "_snapshot_at" in snap
        assert snap["name"] == "snapshot-test"

    def test_from_dict_round_trip(self) -> None:
        original = Runtime(
            name="roundtrip",
            type=RuntimeType.MCP_SERVER,
            status=RuntimeStatus.READY,
            health=RuntimeHealth.HEALTHY,
            command="node server.js",
            arguments=["--port", "8080"],
            environment={"NODE_ENV": "production"},
            pid=12345,
            version="1.0.0",
            discovered=True,
            source="auto",
            restart_count=2,
            crash_count=1,
        )
        d = original.to_dict()
        restored = Runtime.from_dict(d)
        assert restored.name == "roundtrip"
        assert restored.type == RuntimeType.MCP_SERVER
        assert restored.status == RuntimeStatus.READY
        assert restored.health == RuntimeHealth.HEALTHY
        assert restored.command == "node server.js"
        assert restored.arguments == ["--port", "8080"]
        assert restored.environment == {"NODE_ENV": "production"}
        assert restored.pid == 12345
        assert restored.version == "1.0.0"
        assert restored.discovered is True
        assert restored.source == "auto"
        assert restored.restart_count == 2
        assert restored.crash_count == 1

    def test_from_dict_without_id_generates_new(self) -> None:
        d = {"name": "no-id", "type": "python"}
        r = Runtime.from_dict(d)
        assert r.name == "no-id"
        assert r.id is not None

    def test_from_dict_partial(self) -> None:
        d = {"name": "partial"}
        r = Runtime.from_dict(d)
        assert r.name == "partial"
        assert r.type == RuntimeType.CUSTOM
        assert r.status == RuntimeStatus.DISCOVERED

    def test_immutable_snapshot_isolation(self) -> None:
        r = Runtime(name="original", cpu=50.0)
        snap = r.to_snapshot()
        r.cpu = 90.0
        assert snap["cpu"] == 50.0  # snapshot not affected

    def test_field_defaults_are_independent(self) -> None:
        r1 = Runtime(name="a")
        r2 = Runtime(name="b")
        r1.arguments.append("--verbose")
        assert r2.arguments == []  # not shared

    def test_to_dict_none_values(self) -> None:
        r = Runtime(name="nullable")
        d = r.to_dict()
        assert d["started_at"] is None
        assert d["last_error"] is None
        assert d["last_seen"] is None
        assert d["heartbeat"] is None
        assert d["session_id"] is None
        assert d["active_session"] is None
