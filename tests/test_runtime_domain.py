"""Tests for execution engine domain models."""

from agentic_os.domain.execution import (
    EngineCapability,
    EngineHealthStatus,
    EngineRegistry,
    EngineStatus,
    EngineType,
    ExecutionBenchmark,
    ExecutionCapability,
    ExecutionConfiguration,
    ExecutionEngine,
    ExecutionEvent,
    ExecutionEventType,
    ExecutionHealth,
    ExecutionMetrics,
    ExecutionProfile,
    ExecutionResult,
    ExecutionSession,
    ExecutionStatus,
    ExecutionTelemetry,
    ExecutionWorkspace,
)

# ── Enums ──


class TestEngineTypeEnum:
    def test_values(self) -> None:
        assert EngineType.GENERIC == "generic"
        assert EngineType.MCP == "mcp"
        assert EngineType.DOCKER == "docker"
        assert EngineType.WSL == "wsl"
        assert EngineType.CLAUDE_CODE == "claude_code"
        assert EngineType.CUSTOM == "custom"

    def test_all_members(self) -> None:
        expected = {
            "generic",
            "mcp",
            "docker",
            "wsl",
            "claude_code",
            "hermes",
            "opencode",
            "codex",
            "gemini_cli",
            "openhands",
            "continue",
            "aider",
            "goose",
            "cursor",
            "qwen",
            "deepseek",
            "glm",
            "open_interpreter",
            "cline",
            "roo_code",
            "ollama",
            "agy_cli",
            "custom",
        }
        assert {m.value for m in EngineType} == expected


class TestEngineStatusEnum:
    def test_values(self) -> None:
        assert EngineStatus.CREATED == "created"
        assert EngineStatus.RUNNING == "running"
        assert EngineStatus.FAILED == "failed"
        assert EngineStatus.STOPPED == "stopped"

    def test_all_members(self) -> None:
        expected = {
            "created",
            "initializing",
            "running",
            "busy",
            "idle",
            "paused",
            "stopped",
            "failed",
            "recovering",
            "unknown",
        }
        assert {m.value for m in EngineStatus} == expected


class TestEngineCapabilityEnum:
    def test_values(self) -> None:
        assert EngineCapability.CODING == "coding"
        assert EngineCapability.REASONING == "reasoning"
        assert EngineCapability.DOCKER == "docker"

    def test_all_members(self) -> None:
        expected = {
            "planning",
            "coding",
            "reasoning",
            "research",
            "terminal",
            "git",
            "docker",
            "filesystem",
            "vision",
            "multimodal",
            "mcp",
            "streaming",
            "large_context",
            "offline",
            "cloud",
        }
        assert {m.value for m in EngineCapability} == expected


class TestEngineHealthStatusEnum:
    def test_values(self) -> None:
        assert EngineHealthStatus.HEALTHY == "healthy"
        assert EngineHealthStatus.UNHEALTHY == "unhealthy"
        assert EngineHealthStatus.UNKNOWN == "unknown"

    def test_all_members(self) -> None:
        expected = {"healthy", "degraded", "unhealthy", "unknown"}
        assert {m.value for m in EngineHealthStatus} == expected


class TestExecutionStatusEnum:
    def test_values(self) -> None:
        assert ExecutionStatus.COMPLETED == "completed"
        assert ExecutionStatus.FAILED == "failed"
        assert ExecutionStatus.CANCELLED == "cancelled"

    def test_all_members(self) -> None:
        expected = {"pending", "running", "completed", "failed", "cancelled", "paused", "timeout"}
        assert {m.value for m in ExecutionStatus} == expected


class TestExecutionEventTypeEnum:
    def test_values(self) -> None:
        assert ExecutionEventType.ENGINE_REGISTERED == "engine.registered"
        assert ExecutionEventType.ENGINE_SHUTDOWN == "engine.shutdown"

    def test_all_members(self) -> None:
        expected = {
            "engine.registered",
            "engine.initialized",
            "engine.shutdown",
            "engine.health_changed",
            "engine.capabilities_changed",
            "engine.error",
            "execution.started",
            "execution.completed",
            "execution.failed",
            "execution.cancelled",
            "benchmark.started",
            "benchmark.completed",
        }
        assert {m.value for m in ExecutionEventType} == expected


# ── Domain Models ──


class TestExecutionCapability:
    def test_construction(self) -> None:
        cap = ExecutionCapability(type=EngineCapability.CODING, confidence=0.9)
        assert cap.type == EngineCapability.CODING
        assert cap.confidence == 0.9

    def test_default_confidence(self) -> None:
        cap = ExecutionCapability(type=EngineCapability.PLANNING)
        assert cap.confidence == 1.0

    def test_from_type_factory(self) -> None:
        cap = ExecutionCapability.from_type(EngineCapability.DOCKER)
        assert cap.type == EngineCapability.DOCKER
        assert cap.description == "docker"

    def test_to_dict(self) -> None:
        cap = ExecutionCapability(
            type=EngineCapability.CODING, confidence=0.8, description="Can code"
        )
        d = cap.to_dict()
        assert d["type"] == "coding"
        assert d["confidence"] == 0.8
        assert d["description"] == "Can code"


class TestExecutionHealth:
    def test_healthy_factory(self) -> None:
        health = ExecutionHealth.healthy(latency_ms=1.5)
        assert health.status == EngineHealthStatus.HEALTHY
        assert health.latency_ms == 1.5
        assert health.error is None

    def test_unhealthy_factory(self) -> None:
        health = ExecutionHealth.unhealthy("Something went wrong")
        assert health.status == EngineHealthStatus.UNHEALTHY
        assert health.error == "Something went wrong"

    def test_with_status(self) -> None:
        health = ExecutionHealth.healthy()
        degraded = health.with_status(EngineHealthStatus.DEGRADED)
        assert degraded.status == EngineHealthStatus.DEGRADED
        assert degraded.latency_ms == health.latency_ms

    def test_to_dict(self) -> None:
        health = ExecutionHealth.healthy(latency_ms=2.0)
        d = health.to_dict()
        assert d["status"] == "healthy"
        assert d["latency_ms"] == 2.0


class TestExecutionMetrics:
    def test_defaults(self) -> None:
        m = ExecutionMetrics()
        assert m.duration_ms == 0.0
        assert m.tokens_in == 0
        assert m.tokens_out == 0

    def test_to_dict(self) -> None:
        m = ExecutionMetrics(duration_ms=100.5, tokens_in=500, tokens_out=200, cost=0.02)
        d = m.to_dict()
        assert d["duration_ms"] == 100.5
        assert d["tokens_in"] == 500
        assert d["cost"] == 0.02

    def test_custom_metrics(self) -> None:
        m = ExecutionMetrics(custom={"accuracy": 0.95})
        assert m.custom["accuracy"] == 0.95


class TestExecutionResult:
    def test_completed(self) -> None:
        r = ExecutionResult(execution_id="e1", status=ExecutionStatus.RUNNING)
        completed = r.with_completed("done")
        assert completed.status == ExecutionStatus.COMPLETED
        assert completed.output == "done"
        assert completed.completed_at is not None

    def test_failed(self) -> None:
        r = ExecutionResult(execution_id="e2", status=ExecutionStatus.RUNNING)
        failed = r.with_failed("boom")
        assert failed.status == ExecutionStatus.FAILED
        assert failed.error == "boom"

    def test_to_dict(self) -> None:
        r = ExecutionResult(execution_id="e1", status=ExecutionStatus.COMPLETED, output="ok")
        d = r.to_dict()
        assert d["execution_id"] == "e1"
        assert d["status"] == "completed"
        assert d["output"] == "ok"


class TestExecutionSession:
    def test_construction(self) -> None:
        session = ExecutionSession(engine_id="eng-1")
        assert session.engine_id == "eng-1"
        assert session.status == ExecutionStatus.PENDING
        assert session.id is not None

    def test_with_status(self) -> None:
        session = ExecutionSession(engine_id="eng-1")
        running = session.with_status(ExecutionStatus.RUNNING)
        assert running.status == ExecutionStatus.RUNNING
        assert running.completed_at is None

    def test_with_status_completed_sets_completed_at(self) -> None:
        session = ExecutionSession(engine_id="eng-1")
        done = session.with_status(ExecutionStatus.COMPLETED)
        assert done.status == ExecutionStatus.COMPLETED
        assert done.completed_at is not None

    def test_with_result(self) -> None:
        session = ExecutionSession(engine_id="eng-1")
        result = ExecutionResult(execution_id="e1", status=ExecutionStatus.COMPLETED)
        with_result = session.with_result(result)
        assert with_result.result is not None
        assert with_result.result.execution_id == "e1"

    def test_to_dict(self) -> None:
        session = ExecutionSession(engine_id="eng-1")
        d = session.to_dict()
        assert d["engine_id"] == "eng-1"
        assert d["status"] == "pending"


class TestExecutionWorkspace:
    def test_defaults(self) -> None:
        ws = ExecutionWorkspace()
        assert ws.path == ""
        assert ws.environment == {}

    def test_to_dict(self) -> None:
        ws = ExecutionWorkspace(path="/home/test", environment={"KEY": "val"})
        d = ws.to_dict()
        assert d["path"] == "/home/test"
        assert d["environment"]["KEY"] == "val"


class TestExecutionTelemetry:
    def test_construction(self) -> None:
        t = ExecutionTelemetry(engine_id="eng-1", metric_name="cpu", value=0.5)
        assert t.engine_id == "eng-1"
        assert t.metric_name == "cpu"
        assert t.value == 0.5

    def test_to_dict(self) -> None:
        t = ExecutionTelemetry(engine_id="eng-1", metric_name="memory", value=256.0, unit="MB")
        d = t.to_dict()
        assert d["metric_name"] == "memory"
        assert d["unit"] == "MB"


class TestExecutionBenchmark:
    def test_construction(self) -> None:
        b = ExecutionBenchmark(engine_id="eng-1", benchmark_type="latency", score=100.0)
        assert b.engine_id == "eng-1"
        assert b.score == 100.0

    def test_to_dict(self) -> None:
        b = ExecutionBenchmark(
            engine_id="eng-1", benchmark_type="throughput", score=50.0, metrics={"ops": 100}
        )
        d = b.to_dict()
        assert d["benchmark_type"] == "throughput"
        assert d["metrics"]["ops"] == 100


class TestExecutionConfiguration:
    def test_construction(self) -> None:
        c = ExecutionConfiguration(engine_id="eng-1", settings={"timeout": 30})
        assert c.engine_id == "eng-1"
        assert c.settings["timeout"] == 30

    def test_with_settings(self) -> None:
        c = ExecutionConfiguration(engine_id="eng-1", settings={"timeout": 30})
        updated = c.with_settings({"timeout": 60})
        assert updated.settings["timeout"] == 60
        assert updated.version == c.version  # unchanged

    def test_to_dict(self) -> None:
        c = ExecutionConfiguration(engine_id="eng-1")
        d = c.to_dict()
        assert d["engine_id"] == "eng-1"


class TestExecutionProfile:
    def test_construction(self) -> None:
        p = ExecutionProfile(name="fast", engine_type=EngineType.GENERIC)
        assert p.name == "fast"
        assert p.engine_type == EngineType.GENERIC

    def test_with_capabilities(self) -> None:
        p = ExecutionProfile(name="full", engine_type=EngineType.GENERIC)
        caps = [ExecutionCapability(type=EngineCapability.CODING)]
        updated = p.with_capabilities(caps)
        assert len(updated.capabilities) == 1
        assert updated.capabilities[0].type == EngineCapability.CODING

    def test_to_dict(self) -> None:
        p = ExecutionProfile(name="test", engine_type=EngineType.GENERIC)
        d = p.to_dict()
        assert d["name"] == "test"
        assert d["engine_type"] == "generic"


class TestExecutionEvent:
    def test_construction(self) -> None:
        event = ExecutionEvent(event_type=ExecutionEventType.ENGINE_REGISTERED, engine_id="eng-1")
        assert event.event_type == ExecutionEventType.ENGINE_REGISTERED
        assert event.engine_id == "eng-1"

    def test_to_dict(self) -> None:
        event = ExecutionEvent(
            event_type=ExecutionEventType.EXECUTION_STARTED,
            engine_id="eng-1",
            data={"action": "test"},
            session_id="sess-1",
        )
        d = event.to_dict()
        assert d["event_type"] == "execution.started"
        assert d["session_id"] == "sess-1"


class TestExecutionEngine:
    def test_default_construction(self) -> None:
        engine = ExecutionEngine()
        assert engine.status == EngineStatus.CREATED
        assert engine.engine_type == EngineType.GENERIC
        assert engine.id is not None

    def test_named_construction(self) -> None:
        engine = ExecutionEngine(name="test-engine", engine_type=EngineType.MCP)
        assert engine.name == "test-engine"
        assert engine.engine_type == EngineType.MCP

    def test_is_online(self) -> None:
        engine = ExecutionEngine(status=EngineStatus.RUNNING)
        assert engine.is_online()
        assert ExecutionEngine(status=EngineStatus.IDLE).is_online()
        assert ExecutionEngine(status=EngineStatus.BUSY).is_online()
        assert not ExecutionEngine(status=EngineStatus.STOPPED).is_online()
        assert not ExecutionEngine(status=EngineStatus.FAILED).is_online()

    def test_supports_capability(self) -> None:
        caps = (ExecutionCapability(type=EngineCapability.CODING),)
        engine = ExecutionEngine(capabilities=caps)
        assert engine.supports_capability(EngineCapability.CODING)
        assert not engine.supports_capability(EngineCapability.DOCKER)

    def test_with_status(self) -> None:
        engine = ExecutionEngine()
        running = engine.with_status(EngineStatus.RUNNING)
        assert running.status == EngineStatus.RUNNING
        assert engine.status == EngineStatus.CREATED  # immutability

    def test_with_capabilities(self) -> None:
        engine = ExecutionEngine()
        caps = [ExecutionCapability(type=EngineCapability.REASONING)]
        updated = engine.with_capabilities(caps)
        assert len(updated.capabilities) == 1

    def test_with_health(self) -> None:
        engine = ExecutionEngine()
        health = ExecutionHealth.healthy()
        updated = engine.with_health(health)
        assert updated.health.status == EngineHealthStatus.HEALTHY

    def test_with_config(self) -> None:
        engine = ExecutionEngine()
        config = ExecutionConfiguration(engine_id=engine.id)
        updated = engine.with_config(config)
        assert updated.config is not None

    def test_with_profile(self) -> None:
        engine = ExecutionEngine()
        profile = ExecutionProfile(name="p1", engine_type=EngineType.GENERIC)
        updated = engine.with_profile(profile)
        assert updated.profile is not None

    def test_to_dict(self) -> None:
        engine = ExecutionEngine(name="test", engine_type=EngineType.CLAUDE_CODE)
        d = engine.to_dict()
        assert d["name"] == "test"
        assert d["engine_type"] == "claude_code"
        assert d["status"] == "created"


class TestEngineRegistry:
    def test_empty_registry(self) -> None:
        reg = EngineRegistry()
        assert len(reg.engines) == 0
        assert reg.get_engine("nonexistent") is None

    def test_with_engine_adds(self) -> None:
        reg = EngineRegistry()
        engine = ExecutionEngine(name="e1")
        reg2 = reg.with_engine(engine)
        assert len(reg2.engines) == 1
        assert reg2.get_engine(engine.id) is not None

    def test_with_engine_replaces(self) -> None:
        engine = ExecutionEngine(name="e1", version="1.0")
        reg = EngineRegistry(engines=(engine,))
        updated = engine.with_status(EngineStatus.RUNNING)
        reg2 = reg.with_engine(updated)
        assert len(reg2.engines) == 1
        assert reg2.get_engine(engine.id).status == EngineStatus.RUNNING

    def test_without_engine(self) -> None:
        e1 = ExecutionEngine(name="e1")
        e2 = ExecutionEngine(name="e2")
        reg = EngineRegistry(engines=(e1, e2))
        reg2 = reg.without_engine(e1.id)
        assert len(reg2.engines) == 1
        assert reg2.get_engine(e2.id) is not None

    def test_get_engine_by_name(self) -> None:
        engine = ExecutionEngine(name="finder")
        reg = EngineRegistry(engines=(engine,))
        assert reg.get_engine_by_name("finder") is engine
        assert reg.get_engine_by_name("missing") is None

    def test_list_by_status(self) -> None:
        r1 = ExecutionEngine(name="r1", status=EngineStatus.RUNNING)
        r2 = ExecutionEngine(name="r2", status=EngineStatus.RUNNING)
        s1 = ExecutionEngine(name="s1", status=EngineStatus.STOPPED)
        reg = EngineRegistry(engines=(r1, r2, s1))
        assert len(reg.list_by_status(EngineStatus.RUNNING)) == 2
        assert len(reg.list_by_status(EngineStatus.STOPPED)) == 1

    def test_list_by_capability(self) -> None:
        caps = (ExecutionCapability(type=EngineCapability.CODING),)
        e1 = ExecutionEngine(name="coder", capabilities=caps)
        e2 = ExecutionEngine(name="nocap")
        reg = EngineRegistry(engines=(e1, e2))
        result = reg.list_by_capability(EngineCapability.CODING)
        assert len(result) == 1
        assert result[0].name == "coder"

    def test_list_by_type(self) -> None:
        e1 = ExecutionEngine(name="g", engine_type=EngineType.GENERIC)
        e2 = ExecutionEngine(name="m", engine_type=EngineType.MCP)
        reg = EngineRegistry(engines=(e1, e2))
        assert len(reg.list_by_type(EngineType.GENERIC)) == 1
        assert len(reg.list_by_type(EngineType.MCP)) == 1

    def test_list_online(self) -> None:
        e1 = ExecutionEngine(name="on", status=EngineStatus.RUNNING)
        e2 = ExecutionEngine(name="off", status=EngineStatus.STOPPED)
        reg = EngineRegistry(engines=(e1, e2))
        assert len(reg.list_online()) == 1

    def test_to_dict(self) -> None:
        engine = ExecutionEngine(name="e1")
        reg = EngineRegistry(engines=(engine,))
        d = reg.to_dict()
        assert d["total"] == 1
        assert d["engines"][0]["name"] == "e1"
