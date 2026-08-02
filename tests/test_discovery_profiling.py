"""Tests for the M2 discovery profiling engine."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from agentic_os.core.discovery.profiling import ProfilingEngine
from agentic_os.domain.discovery import ProfileResult, ValidationResult
from agentic_os.domain.execution import EngineType
from agentic_os.ports.execution import EngineRegistration


def _make_reg(
    name: str = "test-engine",
    engine_type: EngineType = EngineType.GENERIC,
    endpoint: str | None = "local:python",
    capabilities: list | None = None,
    version: str = "1.0.0",
    metadata: dict | None = None,
    transport: str = "local",
) -> EngineRegistration:
    return EngineRegistration(
        name=name,
        engine_type=engine_type,
        endpoint=endpoint,
        capabilities=capabilities or [],
        version=version,
        metadata=metadata or {},
        transport=transport,
    )


class TestProfilingEngine:
    @pytest.fixture
    def engine(self) -> ProfilingEngine:
        return ProfilingEngine()

    @pytest.mark.asyncio
    async def test_profile_generates_basic_fields(self, engine: ProfilingEngine) -> None:
        reg = _make_reg(name="my-engine", version="3.2.1")

        with (
            patch("shutil.which", return_value="/usr/bin/python"),
            patch.object(engine, "_detect_streaming", return_value=False),
            patch.object(engine, "_estimate_latency", return_value=25.0),
            patch("agentic_os.core.discovery.profiling.platform_mod.system", return_value="linux"),
        ):
            result = await engine.profile(reg)

        assert result.engine_id == "my-engine"
        assert result.engine_name == "my-engine"
        assert result.version == "3.2.1"
        assert result.executable_path == "/usr/bin/python"
        assert result.platform == "linux"
        assert result.profiled_at is not None

    @pytest.mark.asyncio
    async def test_profile_includes_capabilities(self, engine: ProfilingEngine) -> None:
        reg = _make_reg(capabilities=["coding", "terminal"])

        with (
            patch("shutil.which", return_value="/usr/bin/python"),
            patch.object(engine, "_detect_streaming", return_value=False),
            patch.object(engine, "_estimate_latency", return_value=25.0),
            patch("agentic_os.core.discovery.profiling.platform_mod.system", return_value="linux"),
        ):
            result = await engine.profile(reg)

        assert "coding" in result.capabilities
        assert "terminal" in result.capabilities
        assert len(result.capabilities) == 2

    @pytest.mark.asyncio
    async def test_profile_with_validation_results_overrides_version(
        self, engine: ProfilingEngine
    ) -> None:
        reg = _make_reg(version="1.0.0")
        vr = ValidationResult.passed(
            engine_id="test-engine",
            engine_name="test-engine",
            version_detected="2.0.0-rc1",
            executable_exists=True,
        )

        with (
            patch("shutil.which", return_value="/usr/bin/python"),
            patch.object(engine, "_detect_streaming", return_value=False),
            patch.object(engine, "_estimate_latency", return_value=25.0),
            patch("agentic_os.core.discovery.profiling.platform_mod.system", return_value="linux"),
        ):
            result = await engine.profile(reg, validation_results=[vr])

        assert result.version == "2.0.0-rc1"

    @pytest.mark.asyncio
    async def test_profile_with_failed_validation_keeps_registration_version(
        self, engine: ProfilingEngine
    ) -> None:
        reg = _make_reg(version="1.0.0")
        vr = ValidationResult.failed(
            "test-engine",
            "test-engine",
            "version detection failed",
            version_detected=None,
        )

        with (
            patch("shutil.which", return_value="/usr/bin/python"),
            patch.object(engine, "_detect_streaming", return_value=False),
            patch.object(engine, "_estimate_latency", return_value=25.0),
            patch("agentic_os.core.discovery.profiling.platform_mod.system", return_value="linux"),
        ):
            result = await engine.profile(reg, validation_results=[vr])

        assert result.version == "1.0.0"

    @pytest.mark.asyncio
    async def test_profile_for_remote_endpoint_no_executable(self, engine: ProfilingEngine) -> None:
        reg = _make_reg(endpoint="https://api.example.com")

        with (
            patch("shutil.which", return_value=None),
            patch.object(engine, "_detect_streaming", return_value=False),
            patch.object(engine, "_estimate_latency", return_value=50.0),
            patch("agentic_os.core.discovery.profiling.platform_mod.system", return_value="linux"),
        ):
            result = await engine.profile(reg)

        assert result.executable_path == "https://api.example.com"
        assert result.version == "1.0.0"

    @pytest.mark.asyncio
    async def test_to_execution_profile_converts_correctly(self, engine: ProfilingEngine) -> None:
        profile_result = ProfileResult(
            engine_id="e1",
            engine_name="my-engine",
            version="2.0.0",
            executable_path="/usr/bin/my-engine",
            platform="linux",
            capabilities=("coding", "terminal"),
            supports_streaming=True,
            latency_estimate_ms=42.0,
            config_defaults={"timeout_seconds": 60, "max_retries": 3},
        )

        exec_profile = await engine.to_execution_profile(profile_result)

        assert exec_profile.name == "my-engine"
        assert exec_profile.capabilities[0].type.value == "coding"
        assert exec_profile.capabilities[1].type.value == "terminal"
        assert exec_profile.config is None
        assert "Auto-profiled" in exec_profile.description
        assert "auto-profiled" in exec_profile.tags
        assert exec_profile.engine_type == EngineType.GENERIC  # filled by caller

    @pytest.mark.asyncio
    async def test_estimate_latency_with_executable(self, engine: ProfilingEngine) -> None:
        reg = _make_reg()
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""

        with (
            patch("time.perf_counter", side_effect=[1.0, 1.15]),
            patch("subprocess.run", return_value=mock_result),
        ):
            latency = await engine._estimate_latency("/usr/bin/python", reg)

        assert latency == pytest.approx(150.0, abs=0.1)

    @pytest.mark.asyncio
    async def test_estimate_latency_non_zero_exit(self, engine: ProfilingEngine) -> None:
        reg = _make_reg()
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "error"

        with (
            patch("time.perf_counter", side_effect=[1.0, 1.1]),
            patch("subprocess.run", return_value=mock_result),
        ):
            latency = await engine._estimate_latency("/usr/bin/python", reg)

        assert latency == pytest.approx(200.0, abs=0.1)

    @pytest.mark.asyncio
    async def test_estimate_latency_no_executable_default(self, engine: ProfilingEngine) -> None:
        reg = _make_reg(endpoint="https://remote")
        latency = await engine._estimate_latency(None, reg)
        assert latency == 50.0

    @pytest.mark.asyncio
    async def test_estimate_latency_on_error_returns_conservative(
        self, engine: ProfilingEngine
    ) -> None:
        reg = _make_reg()
        with patch(
            "subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="test", timeout=5.0)
        ):
            latency = await engine._estimate_latency("/usr/bin/python", reg)

        assert latency == 100.0

    @pytest.mark.asyncio
    async def test_detect_streaming_by_engine_type(self, engine: ProfilingEngine) -> None:
        reg = _make_reg(engine_type=EngineType.CLAUDE_CODE)

        with patch.object(engine, "_detect_streaming", wraps=engine._detect_streaming):
            result = await engine._detect_streaming(reg)
            assert result is True

    @pytest.mark.asyncio
    async def test_detect_streaming_from_metadata(self, engine: ProfilingEngine) -> None:
        reg = _make_reg(metadata={"supports_streaming": True})
        result = await engine._detect_streaming(reg)
        assert result is True

    @pytest.mark.asyncio
    async def test_detect_streaming_default_false(self, engine: ProfilingEngine) -> None:
        reg = _make_reg(engine_type=EngineType.GENERIC)
        result = await engine._detect_streaming(reg)
        assert result is False

    def test_estimate_mcp_support_by_type(self, engine: ProfilingEngine) -> None:
        reg = _make_reg(engine_type=EngineType.MCP)
        assert engine._estimate_mcp_support(reg) is True

    def test_estimate_mcp_support_from_metadata(self, engine: ProfilingEngine) -> None:
        reg = _make_reg(metadata={"supports_mcp": True})
        assert engine._estimate_mcp_support(reg) is True

    def test_estimate_mcp_support_default_false(self, engine: ProfilingEngine) -> None:
        reg = _make_reg(engine_type=EngineType.GENERIC)
        assert engine._estimate_mcp_support(reg) is False

    def test_estimate_resource_footprint_by_type(self, engine: ProfilingEngine) -> None:
        mapping = {
            EngineType.CLAUDE_CODE: 512.0,
            EngineType.DOCKER: 256.0,
            EngineType.WSL: 512.0,
            EngineType.MCP: 128.0,
            EngineType.GENERIC: 64.0,
            EngineType.AIDER: 256.0,
            EngineType.CUSTOM: 128.0,
        }
        for engine_type, expected in mapping.items():
            reg = _make_reg(engine_type=engine_type)
            assert engine._estimate_resource_footprint(reg) == expected

    def test_estimate_resource_footprint_unknown_type(self, engine: ProfilingEngine) -> None:
        reg = _make_reg(engine_type=EngineType.ROO_CODE)
        assert engine._estimate_resource_footprint(reg) == 128.0

    def test_generate_config_defaults_generic(self, engine: ProfilingEngine) -> None:
        reg = _make_reg(engine_type=EngineType.GENERIC)
        config = engine._generate_config_defaults(reg)
        assert config["timeout_seconds"] == 60
        assert config["max_retries"] == 3

    def test_generate_config_defaults_claude_code(self, engine: ProfilingEngine) -> None:
        reg = _make_reg(engine_type=EngineType.CLAUDE_CODE)
        config = engine._generate_config_defaults(reg)
        assert config["model"] == "sonnet"
        assert config["max_tokens"] == 4096
        assert config["timeout_seconds"] == 60

    def test_generate_config_defaults_docker(self, engine: ProfilingEngine) -> None:
        reg = _make_reg(engine_type=EngineType.DOCKER)
        config = engine._generate_config_defaults(reg)
        assert config["network"] == "host"
        assert config["memory_limit"] == "4g"

    def test_resolve_executable_local(self, engine: ProfilingEngine) -> None:
        reg = _make_reg(endpoint="local:python")
        with patch("shutil.which", return_value="/usr/bin/python"):
            result = engine._resolve_executable(reg)
            assert result == "/usr/bin/python"

    def test_resolve_executable_remote(self, engine: ProfilingEngine) -> None:
        reg = _make_reg(endpoint="https://remote.api")
        result = engine._resolve_executable(reg)
        assert result is None

    def test_resolve_executable_no_endpoint(self, engine: ProfilingEngine) -> None:
        reg = _make_reg(endpoint=None)
        result = engine._resolve_executable(reg)
        assert result is None


class TestProfileResultFactory:
    def test_from_registration_minimal(self) -> None:
        result = ProfileResult.from_registration(
            engine_id="e1",
            engine_name="test",
            version="1.0",
            executable_path="/usr/bin/test",
            capabilities=["streaming"],
        )
        assert result.engine_id == "e1"
        assert result.engine_name == "test"
        assert result.version == "1.0"
        assert result.executable_path == "/usr/bin/test"
        assert result.capabilities == ("streaming",)
        assert isinstance(result.platform, str)
        assert len(result.platform) > 0

    def test_from_registration_with_platform_override(self) -> None:
        result = ProfileResult.from_registration(
            engine_id="e1",
            engine_name="test",
            version="1.0",
            executable_path="/usr/bin/test",
            capabilities=[],
            platform_name="darwin",
        )
        assert result.platform == "darwin"

    def test_from_registration_empty_capabilities(self) -> None:
        result = ProfileResult.from_registration(
            engine_id="e1",
            engine_name="test",
            version="1.0",
            executable_path="/usr/bin/test",
            capabilities=[],
            platform_name="linux",
        )
        assert result.capabilities == ()
