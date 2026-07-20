"""Tests for services.runtime_discovery services: validation, profiling, health."""

from __future__ import annotations

import sys
from pathlib import Path

_services_path = str(Path(__file__).resolve().parent.parent / "services")
if _services_path not in sys.path:
    sys.path.insert(0, _services_path)

from unittest.mock import MagicMock, patch

import pytest
from services.runtime_discovery.health_monitor import RuntimeHealthMonitor
from services.runtime_discovery.models import (
    Runtime,
    RuntimeHealth,
    RuntimeProfile,
    RuntimeType,
    ValidationStatus,
)
from services.runtime_discovery.profiling import ProfilingEngine
from services.runtime_discovery.validation import (
    CapabilityMatchValidator,
    ExecutableExistsValidator,
    HealthProbeValidator,
    IntegrityValidator,
    PermissionValidator,
    ValidationPipeline,
    VersionDetectValidator,
)


class TestExecutableExistsValidator:
    @patch("os.path.isfile", return_value=True)
    @patch("os.access", return_value=True)
    async def test_exists_with_binary_path(self, mock_access, mock_isfile) -> None:
        runtime = Runtime(name="python3", binary_path="/usr/bin/python3")
        result = await ExecutableExistsValidator.validate(runtime)
        assert result is True

    @patch("os.path.isfile", return_value=False)
    async def test_not_exists(self, mock_isfile) -> None:
        runtime = Runtime(name="python3", binary_path="/usr/bin/python3")
        result = await ExecutableExistsValidator.validate(runtime)
        assert result is False

    @patch("shutil.which", return_value="/usr/bin/python3")
    async def test_found_via_which(self, mock_which) -> None:
        runtime = Runtime(name="python3")
        result = await ExecutableExistsValidator.validate(runtime)
        assert result is True
        assert runtime.binary_path == "/usr/bin/python3"

    @patch("shutil.which", return_value=None)
    async def test_not_found_via_which(self, mock_which) -> None:
        runtime = Runtime(name="nonexistent_tool")
        result = await ExecutableExistsValidator.validate(runtime)
        assert result is False


class TestVersionDetectValidator:
    async def test_no_binary(self) -> None:
        runtime = Runtime(name="")
        result = await VersionDetectValidator.validate(runtime)
        assert result["passed"] is False

    @patch("subprocess.run")
    async def test_version_detected(self, mock_run) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="Python 3.14.0\n", stderr="")
        runtime = Runtime(
            name="python3", runtime_type=RuntimeType.PYTHON, binary_path="/usr/bin/python3"
        )
        result = await VersionDetectValidator.validate(runtime)
        assert result["passed"] is True
        assert runtime.version is not None

    @patch("subprocess.run", side_effect=FileNotFoundError)
    async def test_binary_not_found(self, mock_run) -> None:
        runtime = Runtime(
            name="python3", runtime_type=RuntimeType.PYTHON, binary_path="/usr/bin/python3"
        )
        result = await VersionDetectValidator.validate(runtime)
        assert result["passed"] is False


class TestCapabilityMatchValidator:
    async def test_known_type_populates_capabilities(self) -> None:
        runtime = Runtime(
            name="git",
            runtime_type=RuntimeType.GIT,
            capabilities=[],
        )
        result = await CapabilityMatchValidator.validate(runtime)
        assert result["passed"] is True
        assert len(runtime.capabilities) > 0

    async def test_unknown_type_returns_warning(self) -> None:
        runtime = Runtime(
            name="custom_tool",
            runtime_type=RuntimeType.CUSTOM,
            capabilities=[],
        )
        result = await CapabilityMatchValidator.validate(runtime)
        assert result["passed"] is True
        assert "warning" in result

    async def test_existing_capabilities_preserved(self) -> None:
        from services.runtime_discovery.models import RuntimeCapability

        runtime = Runtime(
            name="git",
            runtime_type=RuntimeType.GIT,
            capabilities=[RuntimeCapability(namespace="git.clone")],
        )
        result = await CapabilityMatchValidator.validate(runtime)
        assert result["passed"] is True


class TestPermissionValidator:
    async def test_no_binary(self) -> None:
        runtime = Runtime(name="test")
        result = await PermissionValidator.validate(runtime)
        assert result["passed"] is False

    @patch("os.path.exists", return_value=True)
    @patch("os.access", side_effect=[True, True])
    async def test_permissions_ok(self, mock_access, mock_exists) -> None:
        runtime = Runtime(name="test", binary_path="/usr/bin/test")
        result = await PermissionValidator.validate(runtime)
        assert result["passed"] is True

    @patch("os.path.exists", return_value=True)
    @patch("os.access", side_effect=[False, True])
    async def test_not_readable(self, mock_access, mock_exists) -> None:
        runtime = Runtime(name="test", binary_path="/usr/bin/test")
        result = await PermissionValidator.validate(runtime)
        assert result["passed"] is False

    @patch("os.path.exists", return_value=False)
    async def test_binary_not_exist(self, mock_exists) -> None:
        runtime = Runtime(name="test", binary_path="/usr/bin/test")
        result = await PermissionValidator.validate(runtime)
        assert result["passed"] is False


class TestIntegrityValidator:
    async def test_no_binary(self) -> None:
        runtime = Runtime(name="test")
        result = await IntegrityValidator.validate(runtime)
        assert result["passed"] is False

    @patch("os.path.exists", return_value=True)
    async def test_no_known_hash(self, mock_exists) -> None:
        runtime = Runtime(name="test", binary_path="/usr/bin/test")
        result = await IntegrityValidator.validate(runtime)
        assert result["passed"] is True
        assert "warning" in result

    async def test_empty_binary_path(self) -> None:
        runtime = Runtime(name="test", binary_path="")
        result = await IntegrityValidator.validate(runtime)
        assert result["passed"] is False


class TestHealthProbeValidator:
    async def test_no_binary(self) -> None:
        runtime = Runtime(name="")
        result = await HealthProbeValidator.validate(runtime)
        assert result["passed"] is False

    @patch("subprocess.run")
    async def test_healthy(self, mock_run) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        runtime = Runtime(name="test", binary_path="/usr/bin/test")
        result = await HealthProbeValidator.validate(runtime)
        assert result["passed"] is True

    @patch("subprocess.run", side_effect=FileNotFoundError)
    async def test_binary_not_found(self, mock_run) -> None:
        runtime = Runtime(name="test", binary_path="/usr/bin/test")
        result = await HealthProbeValidator.validate(runtime)
        assert result["passed"] is False


class TestValidationPipeline:
    @pytest.fixture
    def pipeline(self) -> ValidationPipeline:
        return ValidationPipeline()

    async def test_empty_pipeline(self, pipeline: ValidationPipeline) -> None:
        runtime = Runtime(name="test")
        result = await pipeline.validate(runtime)
        assert result.status == ValidationStatus.PASSED

    async def test_with_validators(self, pipeline: ValidationPipeline) -> None:
        pipeline.add_validator("always_pass", lambda r: True)
        pipeline.add_validator("always_fail", lambda r: False, required=True)
        runtime = Runtime(name="test")
        result = await pipeline.validate(runtime)
        assert result.status == ValidationStatus.FAILED

    async def test_optional_validator_failure(self, pipeline: ValidationPipeline) -> None:
        pipeline.add_validator("optional", lambda r: False, required=False)
        runtime = Runtime(name="test")
        result = await pipeline.validate(runtime)
        assert result.status == ValidationStatus.PASSED

    async def test_async_validator(self, pipeline: ValidationPipeline) -> None:
        async def async_check(r: Runtime) -> bool:
            return True

        pipeline.add_validator("async_check", async_check)
        runtime = Runtime(name="test")
        result = await pipeline.validate(runtime)
        assert result.status == ValidationStatus.PASSED

    async def test_validator_with_dict_result(self, pipeline: ValidationPipeline) -> None:
        def dict_validator(r: Runtime) -> dict:
            return {"passed": True, "warning": "check ok"}

        pipeline.add_validator("dict_check", dict_validator)
        runtime = Runtime(name="test")
        result = await pipeline.validate(runtime)
        assert result.status == ValidationStatus.PASSED

    async def test_validator_exception(self, pipeline: ValidationPipeline) -> None:
        def broken(r: Runtime) -> bool:
            raise RuntimeError("broken")

        pipeline.add_validator("broken", broken, required=True)
        runtime = Runtime(name="test")
        result = await pipeline.validate(runtime)
        assert result.status == ValidationStatus.FAILED
        assert any("broken" in e for e in result.errors)

    async def test_list_validators(self, pipeline: ValidationPipeline) -> None:
        pipeline.add_validator("a", lambda r: True)
        pipeline.add_validator("b", lambda r: True)
        names = pipeline.list_validators()
        assert names == ["a", "b"]

    async def test_remove_validator(self, pipeline: ValidationPipeline) -> None:
        pipeline.add_validator("a", lambda r: True)
        pipeline.add_validator("b", lambda r: True)
        pipeline.remove_validator("a")
        assert pipeline.list_validators() == ["b"]

    async def test_validate_all(self, pipeline: ValidationPipeline) -> None:
        pipeline.add_validator("pass", lambda r: True)
        runtimes = [Runtime(name="a"), Runtime(name="b")]
        results = await pipeline.validate_all(runtimes)
        assert len(results) == 2
        assert all(r.status == ValidationStatus.PASSED for r in results)


class TestProfilingEngine:
    @pytest.fixture
    def engine(self) -> ProfilingEngine:
        return ProfilingEngine()

    async def test_profile_basic(self, engine: ProfilingEngine) -> None:
        runtime = Runtime(
            name="python3",
            runtime_type=RuntimeType.PYTHON,
            version="3.14.0",
        )
        profile = await engine.profile(runtime)
        assert profile.runtime_id == runtime.runtime_id
        assert profile.runtime_type == RuntimeType.PYTHON
        assert profile.version == "3.14.0"
        assert profile.latency_estimate_ms > 0

    async def test_profile_claude_code(self, engine: ProfilingEngine) -> None:
        runtime = Runtime(
            name="claude",
            runtime_type=RuntimeType.CLAUDE_CODE,
        )
        profile = await engine.profile(runtime)
        assert profile.supports_streaming is True
        assert profile.supports_mcp is True

    async def test_profile_openhands(self, engine: ProfilingEngine) -> None:
        runtime = Runtime(name="openhands", runtime_type=RuntimeType.OPENHANDS)
        profile = await engine.profile(runtime)
        assert profile.resource_footprint_mb == 768.0
        assert profile.cost_estimate == 0.008

    async def test_to_execution_profile(self, engine: ProfilingEngine) -> None:
        profile = RuntimeProfile(
            runtime_type=RuntimeType.PYTHON,
            version="3.14.0",
            supports_streaming=False,
        )
        ep = await engine.to_execution_profile(profile)
        assert ep["engine_type"] == "python"
        assert ep["version"] == "3.14.0"

    async def test_profile_unknown_type(self, engine: ProfilingEngine) -> None:
        runtime = Runtime(name="custom", runtime_type=RuntimeType.CUSTOM)
        profile = await engine.profile(runtime)
        assert profile.latency_estimate_ms >= 0


class TestRuntimeHealthMonitor:
    @pytest.fixture
    def monitor(self) -> RuntimeHealthMonitor:
        return RuntimeHealthMonitor(check_interval_s=3600)

    def test_init(self, monitor) -> None:
        assert monitor is not None

    async def test_check_no_binary(self, monitor) -> None:
        runtime = Runtime(name="")
        health = await monitor.check(runtime)
        assert health.healthy is False

    @patch("subprocess.run")
    async def test_check_success(self, mock_run, monitor) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="Python 3.14.0\n", stderr="")
        runtime = Runtime(name="python3", binary_path="/usr/bin/python3")
        health = await monitor.check(runtime)
        assert health.healthy is True
        assert health.response_time_ms > 0

    @patch("subprocess.run", side_effect=FileNotFoundError)
    async def test_check_file_not_found(self, mock_run, monitor) -> None:
        runtime = Runtime(name="test", binary_path="/usr/bin/nonexistent")
        health = await monitor.check(runtime)
        assert health.healthy is False

    async def test_check_all(self, monitor) -> None:
        async def fake_check(r: Runtime) -> RuntimeHealth:
            h = RuntimeHealth(runtime_id=r.runtime_id, healthy=True, status="healthy")
            return h

        monitor.check = fake_check
        runtimes = [Runtime(name="a"), Runtime(name="b")]
        results = await monitor.check_all(runtimes)
        assert len(results) == 2

    def test_get_health_nonexistent(self, monitor) -> None:
        assert monitor.get_health("ghost") is None

    def test_get_all_health_empty(self, monitor) -> None:
        assert monitor.get_all_health() == {}

    async def test_get_history(self, monitor) -> None:
        runtime = Runtime(name="test")
        await monitor.check(runtime)
        history = monitor.get_history(runtime.runtime_id)
        assert len(history) >= 1

    async def test_status_change_callback(self, monitor) -> None:
        callback = MagicMock()
        monitor.on_status_change(callback)
        runtime = Runtime(name="test")
        await monitor.check(runtime)
        # Check triggers on status changes
        await monitor.check(runtime)
        assert len(monitor._health) >= 1

    async def test_start_stop_periodic(self, monitor) -> None:
        runtime = Runtime(name="test", binary_path="/usr/bin/python3")
        monitor._running = True
        with patch.object(monitor, "check", return_value=RuntimeHealth(healthy=True)):
            await monitor.start_periodic_check(runtime)
            assert runtime.runtime_id in monitor._tasks
            await monitor.stop_periodic_check(runtime.runtime_id)
            assert runtime.runtime_id not in monitor._tasks

    async def test_start_all_stop_all(self, monitor) -> None:
        runtimes = [Runtime(name="a"), Runtime(name="b")]
        monitor._running = False
        # Just verify no crash
        await monitor.start_all(runtimes)
        await monitor.stop_all()
