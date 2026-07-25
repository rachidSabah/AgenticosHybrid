"""Tests for Phase 6.1 domain models — LocalAgent, AgentStatus, AgentCapability, etc."""

from __future__ import annotations

from datetime import UTC, datetime

from agentic_os.domain.discovery import (
    AgentCapability,
    AgentDiscoveryConfig,
    AgentHealthRecord,
    AgentStatus,
    DiscoveryResult,
    LocalAgent,
)

# ═══════════════════════════════════════════════════════════════════════════════
# LocalAgent
# ═══════════════════════════════════════════════════════════════════════════════


class TestLocalAgentCreation:
    def test_create_with_all_fields(self) -> None:
        agent = LocalAgent(
            id="a1",
            name="Test Agent",
            tool_type="hermes",
            version="1.0.0",
            status=AgentStatus.RUNNING,
            executable_path="/usr/bin/hermes",
            working_directory="/home/user",
            pid=1001,
            capabilities=(AgentCapability.CODE_GENERATION, AgentCapability.CHAT),
            supported_models=("gpt-4",),
            supported_providers=("openai",),
            health_score=0.9,
            memory_mb=128.0,
            cpu_percent=10.0,
            threads=4,
            uptime_seconds=3600.0,
            restart_count=0,
            configuration={"key": "val"},
            tags=("local",),
            error="",
        )
        assert agent.id == "a1"
        assert agent.name == "Test Agent"
        assert agent.tool_type == "hermes"
        assert agent.version == "1.0.0"
        assert agent.status == AgentStatus.RUNNING
        assert agent.executable_path == "/usr/bin/hermes"
        assert agent.working_directory == "/home/user"
        assert agent.pid == 1001
        assert agent.capabilities == (AgentCapability.CODE_GENERATION, AgentCapability.CHAT)
        assert agent.supported_models == ("gpt-4",)
        assert agent.health_score == 0.9
        assert agent.restart_count == 0

    def test_create_with_minimal_fields(self) -> None:
        agent = LocalAgent(id="a2", name="Minimal", tool_type="python", version="3.12")
        assert agent.id == "a2"
        assert agent.status == AgentStatus.UNKNOWN
        assert agent.pid is None
        assert agent.capabilities == ()
        assert agent.health_score == 0.0
        assert agent.error == ""

    def test_default_discovered_at_is_set(self) -> None:
        now = datetime.now(UTC)
        agent = LocalAgent(id="a3", name="Timed", tool_type="test", version="1.0")
        assert agent.discovered_at is not None
        assert agent.last_seen is not None
        assert (agent.discovered_at - now).total_seconds() < 1.0

    def test_id_and_name_roundtrip(self) -> None:
        agent = LocalAgent(id="my-id", name="My Agent", tool_type="test", version="1.0")
        assert agent.id == "my-id"
        assert agent.name == "My Agent"

    def test_restart_count_default(self) -> None:
        agent = LocalAgent(id="r1", name="Restarter", tool_type="test", version="1.0")
        assert agent.restart_count == 0

    def test_error_default(self) -> None:
        agent = LocalAgent(id="e1", name="Err", tool_type="test", version="1.0")
        assert agent.error == ""


class TestLocalAgentRunning:
    def test_running_returns_true_for_running(self) -> None:
        agent = LocalAgent(
            id="r1", name="R", tool_type="t", version="1", status=AgentStatus.RUNNING
        )
        assert agent.running() is True

    def test_running_returns_true_for_idle(self) -> None:
        agent = LocalAgent(id="i1", name="I", tool_type="t", version="1", status=AgentStatus.IDLE)
        assert agent.running() is True

    def test_running_returns_true_for_busy(self) -> None:
        agent = LocalAgent(id="b1", name="B", tool_type="t", version="1", status=AgentStatus.BUSY)
        assert agent.running() is True

    def test_running_returns_false_for_stopped(self) -> None:
        agent = LocalAgent(
            id="s1", name="S", tool_type="t", version="1", status=AgentStatus.STOPPED
        )
        assert agent.running() is False

    def test_running_returns_false_for_crashed(self) -> None:
        agent = LocalAgent(
            id="c1", name="C", tool_type="t", version="1", status=AgentStatus.CRASHED
        )
        assert agent.running() is False

    def test_running_returns_false_for_unknown(self) -> None:
        agent = LocalAgent(
            id="u1", name="U", tool_type="t", version="1", status=AgentStatus.UNKNOWN
        )
        assert agent.running() is False

    def test_running_returns_false_for_updating(self) -> None:
        agent = LocalAgent(
            id="up1", name="Up", tool_type="t", version="1", status=AgentStatus.UPDATING
        )
        assert agent.running() is False

    def test_running_returns_false_for_restarting(self) -> None:
        agent = LocalAgent(
            id="rt1", name="Rt", tool_type="t", version="1", status=AgentStatus.RESTARTING
        )
        assert agent.running() is False


class TestLocalAgentToDict:
    def test_to_dict_returns_all_fields(self) -> None:
        agent = LocalAgent(
            id="d1",
            name="DictTest",
            tool_type="hermes",
            version="2.0.0",
            status=AgentStatus.RUNNING,
            executable_path="/bin/hermes",
            capabilities=(AgentCapability.CODE_GENERATION, AgentCapability.CHAT),
            tags=("dev",),
        )
        d = agent.to_dict()
        assert d["id"] == "d1"
        assert d["name"] == "DictTest"
        assert d["tool_type"] == "hermes"
        assert d["version"] == "2.0.0"
        assert d["status"] == "running"
        assert d["executable_path"] == "/bin/hermes"
        assert d["capabilities"] == ["code_generation", "chat"]
        assert d["tags"] == ["dev"]
        assert d["pid"] is None
        assert "last_seen" in d
        assert "discovered_at" in d

    def test_to_dict_contains_all_keys(self) -> None:
        agent = LocalAgent(id="k1", name="KeysTest", tool_type="t", version="1")
        d = agent.to_dict()
        expected_keys = {
            "id",
            "name",
            "tool_type",
            "version",
            "status",
            "executable_path",
            "working_directory",
            "pid",
            "capabilities",
            "supported_models",
            "supported_providers",
            "health_score",
            "last_seen",
            "discovered_at",
            "latency_ms",
            "memory_mb",
            "cpu_percent",
            "threads",
            "uptime_seconds",
            "restart_count",
            "configuration",
            "tags",
            "error",
        }
        assert set(d.keys()) == expected_keys

    def test_to_dict_roundtrip(self) -> None:
        agent = LocalAgent(
            id="rt1",
            name="Roundtrip",
            tool_type="python",
            version="3.12.0",
            status=AgentStatus.IDLE,
            executable_path="/usr/bin/python3",
            pid=555,
            capabilities=(AgentCapability.CODE_GENERATION, AgentCapability.TESTING),
            health_score=0.8,
        )
        d = agent.to_dict()
        assert d["id"] == "rt1"
        assert d["status"] == "idle"
        assert d["pid"] == 555
        assert d["capabilities"] == ["code_generation", "testing"]


# ═══════════════════════════════════════════════════════════════════════════════
# AgentHealthRecord
# ═══════════════════════════════════════════════════════════════════════════════


class TestAgentHealthRecord:
    def test_create_with_all_fields(self) -> None:
        rec = AgentHealthRecord(
            agent_id="h1",
            status=AgentStatus.RUNNING,
            health_score=1.0,
            latency_ms=5.0,
            memory_mb=64.0,
            cpu_percent=2.0,
            threads=2,
            pid=1001,
        )
        assert rec.agent_id == "h1"
        assert rec.status == AgentStatus.RUNNING
        assert rec.health_score == 1.0
        assert rec.latency_ms == 5.0
        assert rec.memory_mb == 64.0
        assert rec.pid == 1001
        assert rec.error == ""

    def test_checked_at_defaults_to_now(self) -> None:
        now = datetime.now(UTC)
        rec = AgentHealthRecord(
            agent_id="h2",
            status=AgentStatus.UNKNOWN,
            health_score=0.0,
            latency_ms=0.0,
            memory_mb=0.0,
            cpu_percent=0.0,
            threads=0,
            pid=None,
        )
        assert (rec.checked_at - now).total_seconds() < 1.0

    def test_to_dict_keys(self) -> None:
        rec = AgentHealthRecord(
            agent_id="h3",
            status=AgentStatus.BUSY,
            health_score=0.7,
            latency_ms=10.0,
            memory_mb=128.0,
            cpu_percent=5.5,
            threads=4,
            pid=2002,
        )
        d = rec.to_dict()
        assert d["agent_id"] == "h3"
        assert d["status"] == "busy"
        assert d["health_score"] == 0.7
        assert d["pid"] == 2002
        assert "checked_at" in d

    def test_error_field(self) -> None:
        rec = AgentHealthRecord(
            agent_id="h4",
            status=AgentStatus.CRASHED,
            health_score=0.0,
            latency_ms=0.0,
            memory_mb=0.0,
            cpu_percent=0.0,
            threads=0,
            pid=None,
            error="Process died",
        )
        assert rec.error == "Process died"


# ═══════════════════════════════════════════════════════════════════════════════
# AgentDiscoveryConfig
# ═══════════════════════════════════════════════════════════════════════════════


class TestAgentDiscoveryConfig:
    def test_default_values(self) -> None:
        cfg = AgentDiscoveryConfig()
        assert cfg.scan_path is True
        assert cfg.scan_registry is True
        assert cfg.scan_processes is True
        assert cfg.scan_common_dirs is True
        assert cfg.scan_env_vars is True
        assert cfg.auto_register is True
        assert cfg.auto_bind is True
        assert cfg.health_check_interval_seconds == 15.0
        assert cfg.discovery_interval_seconds == 120.0

    def test_enabled_tools_default_list(self) -> None:
        cfg = AgentDiscoveryConfig()
        assert "hermes" in cfg.enabled_tools
        assert "ollama" in cfg.enabled_tools
        assert "docker" in cfg.enabled_tools
        assert "python" in cfg.enabled_tools
        assert len(cfg.enabled_tools) > 5

    def test_custom_values(self) -> None:
        cfg = AgentDiscoveryConfig(
            enabled_tools=("hermes", "ollama"),
            scan_path=False,
            auto_register=False,
            health_check_interval_seconds=30.0,
        )
        assert cfg.enabled_tools == ("hermes", "ollama")
        assert cfg.scan_path is False
        assert cfg.auto_register is False
        assert cfg.health_check_interval_seconds == 30.0

    def test_to_dict(self) -> None:
        cfg = AgentDiscoveryConfig()
        d = cfg.to_dict()
        assert "enabled_tools" in d
        assert "scan_path" in d
        assert "health_check_interval_seconds" in d
        assert d["auto_register"] is True


# ═══════════════════════════════════════════════════════════════════════════════
# DiscoveryResult
# ═══════════════════════════════════════════════════════════════════════════════


class TestDiscoveryResult:
    def test_default_values(self) -> None:
        r = DiscoveryResult()
        assert r.agents_found == 0
        assert r.agents_new == 0
        assert r.agents_updated == 0
        assert r.agents_registered == 0
        assert r.errors == ()
        assert r.duration_ms == 0.0
        assert r.tools_detected == ()

    def test_with_custom_values(self) -> None:
        r = DiscoveryResult(
            agents_found=5,
            agents_new=3,
            agents_updated=1,
            agents_registered=2,
            duration_ms=150.0,
            tools_detected=("hermes", "ollama"),
        )
        assert r.agents_found == 5
        assert r.agents_new == 3
        assert r.duration_ms == 150.0
        assert r.tools_detected == ("hermes", "ollama")

    def test_to_dict_keys(self) -> None:
        r = DiscoveryResult(agents_found=2, agents_new=1)
        d = r.to_dict()
        assert d["agents_found"] == 2
        assert d["agents_new"] == 1
        assert "scanned_at" in d
        assert "duration_ms" in d
        assert "errors" in d
        assert "tools_detected" in d


# ═══════════════════════════════════════════════════════════════════════════════
# AgentCapability enum
# ═══════════════════════════════════════════════════════════════════════════════


class TestAgentCapability:
    def test_values(self) -> None:
        assert AgentCapability.CODE_GENERATION.value == "code_generation"
        assert AgentCapability.CHAT.value == "chat"
        assert AgentCapability.REASONING.value == "reasoning"
        assert AgentCapability.CUSTOM.value == "custom"
        assert AgentCapability.EMBEDDINGS.value == "embeddings"
        assert AgentCapability.MCP.value == "mcp"
        assert AgentCapability.PLANNING.value == "planning"
        assert AgentCapability.MEMORY.value == "memory"

    def test_str(self) -> None:
        assert str(AgentCapability.CODE_GENERATION) == "code_generation"

    def test_all_members_present(self) -> None:
        expected = {
            "CODE_GENERATION",
            "CODE_REVIEW",
            "TESTING",
            "DEBUGGING",
            "CHAT",
            "SEARCH",
            "FILE_OPS",
            "TERMINAL_OPS",
            "BROWSER_OPS",
            "IMAGE_GENERATION",
            "EMBEDDINGS",
            "REASONING",
            "PLANNING",
            "MEMORY",
            "MCP",
            "API_GATEWAY",
            "CUSTOM",
        }
        assert set(AgentCapability.__members__) == expected


# ═══════════════════════════════════════════════════════════════════════════════
# AgentStatus enum
# ═══════════════════════════════════════════════════════════════════════════════


class TestAgentStatus:
    def test_values(self) -> None:
        assert AgentStatus.RUNNING.value == "running"
        assert AgentStatus.STOPPED.value == "stopped"
        assert AgentStatus.CRASHED.value == "crashed"
        assert AgentStatus.BUSY.value == "busy"
        assert AgentStatus.IDLE.value == "idle"
        assert AgentStatus.UNKNOWN.value == "unknown"

    def test_str(self) -> None:
        assert str(AgentStatus.RUNNING) == "running"

    def test_len(self) -> None:
        assert len(AgentStatus) == 8
