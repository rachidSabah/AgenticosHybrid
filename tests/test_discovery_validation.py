"""Tests for the M2 discovery validation pipeline."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from agentic_os.core.discovery.validation import (
    CapabilityMatchValidator,
    ExecutableExistsValidator,
    HealthCheckValidator,
    IntegrityValidator,
    PermissionValidator,
    ValidationPipeline,
    VersionDetectValidator,
)
from agentic_os.domain.execution import EngineCapability, EngineStatus, EngineType
from agentic_os.ports.execution import EngineRegistration


def _make_reg(
    name: str = "test-engine",
    endpoint: str | None = "local:python",
    engine_type: EngineType = EngineType.GENERIC,
    capabilities: list | None = None,
    version: str = "1.0.0",
    metadata: dict | None = None,
) -> EngineRegistration:
    return EngineRegistration(
        name=name,
        engine_type=engine_type,
        endpoint=endpoint,
        capabilities=capabilities or [],
        version=version,
        metadata=metadata or {},
    )


# ── ExecutableExistsValidator ──


class TestExecutableExistsValidator:
    @pytest.mark.asyncio
    async def test_local_endpoint_found(self) -> None:
        reg = _make_reg(endpoint="local:python")
        with patch("shutil.which", return_value="/usr/bin/python"):
            result = await ExecutableExistsValidator().validate(reg)
            assert result.valid
            assert result.executable_exists

    @pytest.mark.asyncio
    async def test_local_endpoint_not_found(self) -> None:
        reg = _make_reg(endpoint="local:missing-binary")
        with patch("shutil.which", return_value=None):
            result = await ExecutableExistsValidator().validate(reg)
            assert not result.valid
            assert not result.executable_exists
            assert "Binary not found on PATH" in result.errors[0]

    @pytest.mark.asyncio
    async def test_direct_executable_path_found(self) -> None:
        reg = _make_reg(endpoint=None)
        with (
            patch("os.path.isfile", return_value=True),
            patch("os.access", return_value=True),
        ):
            result = await ExecutableExistsValidator().validate(
                reg, executable_path="/custom/path/binary"
            )
            assert result.valid
            assert result.executable_exists

    @pytest.mark.asyncio
    async def test_direct_executable_path_missing(self) -> None:
        reg = _make_reg(endpoint=None)
        with (
            patch("os.path.isfile", return_value=False),
            patch("os.access", return_value=False),
        ):
            result = await ExecutableExistsValidator().validate(
                reg, executable_path="/nonexistent/path"
            )
            assert not result.valid
            assert not result.executable_exists
            assert "Executable not found" in result.errors[0]

    @pytest.mark.asyncio
    async def test_remote_endpoint_passes_automatically(self) -> None:
        reg = _make_reg(endpoint="http://remote:8080")
        result = await ExecutableExistsValidator().validate(reg)
        assert result.valid
        assert result.executable_exists
        assert any("Remote endpoint" in w for w in result.warnings)

    @pytest.mark.asyncio
    async def test_get_validator_name(self) -> None:
        assert ExecutableExistsValidator.get_validator_name() == "executable-exists"


# ── VersionDetectValidator ──


class TestVersionDetectValidator:
    @pytest.mark.asyncio
    async def test_successful_version_detection(self) -> None:
        reg = _make_reg(endpoint="local:python")
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Python 3.12.0\nsome other output\n"
        mock_result.stderr = ""

        with patch("shutil.which", return_value="/usr/bin/python"):
            with patch("subprocess.run", return_value=mock_result):
                result = await VersionDetectValidator().validate(reg)
                assert result.valid
                assert result.version_detected == "Python 3.12.0"

    @pytest.mark.asyncio
    async def test_version_detection_via_executable_path(self) -> None:
        reg = _make_reg(endpoint=None)
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "v2.1.0\n"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            result = await VersionDetectValidator().validate(
                reg, executable_path="/custom/bin/tool"
            )
            assert result.valid
            assert result.version_detected == "v2.1.0"

    @pytest.mark.asyncio
    async def test_file_not_found_error(self) -> None:
        reg = _make_reg(endpoint="local:missing")
        with patch("shutil.which", return_value="/usr/bin/missing"):
            with patch("subprocess.run", side_effect=FileNotFoundError):
                result = await VersionDetectValidator().validate(reg)
                assert not result.valid
                assert "Binary not found" in result.errors[0]

    @pytest.mark.asyncio
    async def test_timeout_expired(self) -> None:
        reg = _make_reg(endpoint="local:slow-binary")
        with patch("shutil.which", return_value="/usr/bin/slow"):
            with patch(
                "subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="slow", timeout=5.0)
            ):
                result = await VersionDetectValidator().validate(reg)
                assert not result.valid
                assert "timed out" in result.errors[0]

    @pytest.mark.asyncio
    async def test_os_error(self) -> None:
        reg = _make_reg(endpoint="local:broken")
        with patch("shutil.which", return_value="/usr/bin/broken"):
            with patch("subprocess.run", side_effect=OSError("Permission denied")):
                result = await VersionDetectValidator().validate(reg)
                assert not result.valid
                assert "OS error" in result.errors[0]

    @pytest.mark.asyncio
    async def test_non_zero_exit_code(self) -> None:
        reg = _make_reg(endpoint="local:python")
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "Unknown flag --version"

        with patch("shutil.which", return_value="/usr/bin/python"):
            with patch("subprocess.run", return_value=mock_result):
                result = await VersionDetectValidator().validate(reg)
                assert not result.valid
                assert "Version command failed" in result.errors[0]

    @pytest.mark.asyncio
    async def test_remote_endpoint_uses_registration_version(self) -> None:
        reg = _make_reg(endpoint="http://remote:8080", version="2.0.0-rc1")
        result = await VersionDetectValidator().validate(reg)
        assert result.valid
        assert result.version_detected == "2.0.0-rc1"
        assert any("Remote endpoint" in w for w in result.warnings)

    @pytest.mark.asyncio
    async def test_binary_not_on_path(self) -> None:
        reg = _make_reg(endpoint="local:missing-binary")
        with patch("shutil.which", return_value=None):
            result = await VersionDetectValidator().validate(reg)
            assert not result.valid
            assert "binary not found" in result.errors[0]

    @pytest.mark.asyncio
    async def test_get_validator_name(self) -> None:
        assert VersionDetectValidator.get_validator_name() == "version-detect"


# ── HealthCheckValidator ──


class TestHealthCheckValidator:
    @pytest.mark.asyncio
    async def test_running_status_passes(self) -> None:
        reg = _make_reg()
        engine = MagicMock()
        engine.status = EngineStatus.RUNNING
        engine.id = "eng-1"

        result = await HealthCheckValidator().validate(reg, engine=engine)
        assert result.valid
        assert result.health_check_passed

    @pytest.mark.asyncio
    async def test_idle_status_passes(self) -> None:
        reg = _make_reg()
        engine = MagicMock()
        engine.status = EngineStatus.IDLE
        engine.id = "eng-1"

        result = await HealthCheckValidator().validate(reg, engine=engine)
        assert result.valid
        assert result.health_check_passed

    @pytest.mark.asyncio
    async def test_unknown_status_fails(self) -> None:
        reg = _make_reg()
        engine = MagicMock()
        engine.status = EngineStatus.UNKNOWN
        engine.id = "eng-1"
        engine.name = reg.name

        result = await HealthCheckValidator().validate(reg, engine=engine)
        assert not result.valid
        assert not result.health_check_passed
        assert "not healthy" in result.errors[0]

    @pytest.mark.asyncio
    async def test_failed_status_fails(self) -> None:
        reg = _make_reg()
        engine = MagicMock()
        engine.status = EngineStatus.FAILED
        engine.id = "eng-1"
        engine.name = reg.name

        result = await HealthCheckValidator().validate(reg, engine=engine)
        assert not result.valid
        assert not result.health_check_passed

    @pytest.mark.asyncio
    async def test_no_engine_skips_with_warning(self) -> None:
        reg = _make_reg()
        result = await HealthCheckValidator().validate(reg, engine=None)
        assert result.valid
        assert result.health_check_passed
        assert any("No engine instance" in w for w in result.warnings)

    @pytest.mark.asyncio
    async def test_get_validator_name(self) -> None:
        assert HealthCheckValidator.get_validator_name() == "health-check"


# ── CapabilityMatchValidator ──


class TestCapabilityMatchValidator:
    @pytest.mark.asyncio
    async def test_valid_capabilities_pass(self) -> None:
        reg = _make_reg(capabilities=[EngineCapability.CODING, EngineCapability.TERMINAL])
        result = await CapabilityMatchValidator().validate(reg)
        assert result.valid
        assert result.capability_match

    @pytest.mark.asyncio
    async def test_empty_capabilities_passes_with_warning(self) -> None:
        reg = _make_reg(capabilities=[])
        result = await CapabilityMatchValidator().validate(reg)
        assert result.valid
        assert result.capability_match
        assert any("No capabilities" in w for w in result.warnings)

    @pytest.mark.asyncio
    async def test_invalid_capability_fails(self) -> None:
        reg = _make_reg(capabilities=["invalid_cap_xyz"])
        result = await CapabilityMatchValidator().validate(reg)
        assert not result.valid
        assert not result.capability_match

    @pytest.mark.asyncio
    async def test_mixed_valid_and_invalid(self) -> None:
        reg = _make_reg(capabilities=[EngineCapability.CODING, "bogus_capability"])
        result = await CapabilityMatchValidator().validate(reg)
        assert not result.valid
        assert not result.capability_match

    @pytest.mark.asyncio
    async def test_get_validator_name(self) -> None:
        assert CapabilityMatchValidator.get_validator_name() == "capability-match"


# ── PermissionValidator ──


class TestPermissionValidator:
    @pytest.mark.asyncio
    async def test_path_exists_and_readable(self) -> None:
        reg = _make_reg(endpoint="local:python")
        with (
            patch("shutil.which", return_value="/usr/bin/python"),
            patch("os.path.exists", return_value=True),
            patch("os.access", return_value=True),
        ):
            result = await PermissionValidator().validate(reg)
            assert result.valid
            assert result.permission_ok

    @pytest.mark.asyncio
    async def test_path_does_not_exist(self) -> None:
        reg = _make_reg(endpoint="local:python")
        with (
            patch("shutil.which", return_value="/usr/bin/python"),
            patch("os.path.exists", return_value=False),
        ):
            result = await PermissionValidator().validate(reg)
            assert not result.valid
            assert not result.permission_ok
            assert "Path does not exist" in result.errors[0]

    @pytest.mark.asyncio
    async def test_path_not_readable(self) -> None:
        reg = _make_reg(endpoint="local:python")
        with (
            patch("shutil.which", return_value="/usr/bin/python"),
            patch("os.path.exists", return_value=True),
            patch("os.access", return_value=False),
        ):
            result = await PermissionValidator().validate(reg)
            assert not result.valid
            assert not result.permission_ok
            assert "not readable" in result.errors[0]

    @pytest.mark.asyncio
    async def test_remote_endpoint_skips_check(self) -> None:
        reg = _make_reg(endpoint="http://remote:8080")
        result = await PermissionValidator().validate(reg)
        assert result.valid
        assert result.permission_ok
        assert any("Remote endpoint" in w for w in result.warnings)

    @pytest.mark.asyncio
    async def test_direct_executable_path_checked(self) -> None:
        reg = _make_reg(endpoint=None)
        with (
            patch("os.path.exists", return_value=True),
            patch("os.access", return_value=True),
        ):
            result = await PermissionValidator().validate(reg, executable_path="/custom/bin")
            assert result.valid
            assert result.permission_ok

    @pytest.mark.asyncio
    async def test_get_validator_name(self) -> None:
        assert PermissionValidator.get_validator_name() == "permission"


# ── IntegrityValidator ──


class TestIntegrityValidator:
    @pytest.mark.asyncio
    async def test_no_known_hash_skips_with_warning(self) -> None:
        reg = _make_reg(metadata={})
        result = await IntegrityValidator().validate(reg)
        assert result.valid
        assert result.integrity_ok
        assert any("No known hash" in w for w in result.warnings)

    @pytest.mark.asyncio
    async def test_sha256_match(self) -> None:
        test_hash = "abcdef1234567890" * 4  # 64-char hex string
        reg = _make_reg(metadata={"sha256": test_hash}, endpoint="local:python")

        with (
            patch("shutil.which", return_value="/usr/bin/python"),
            patch("os.path.isfile", return_value=True),
            patch("builtins.open") as mock_open,
            patch("hashlib.new") as mock_new,
        ):
            mock_file = MagicMock()
            mock_file.read.return_value = b""
            mock_open.return_value.__enter__.return_value = mock_file

            mock_hasher = MagicMock()
            mock_hasher.hexdigest.return_value = test_hash
            mock_new.return_value = mock_hasher

            result = await IntegrityValidator().validate(reg)
            assert result.valid
            assert result.integrity_ok

    @pytest.mark.asyncio
    async def test_sha256_mismatch(self) -> None:
        reg = _make_reg(
            metadata={"sha256": "expected_hash_value_1234567890123456789012345678901"},
            endpoint="local:python",
        )

        with (
            patch("shutil.which", return_value="/usr/bin/python"),
            patch("os.path.isfile", return_value=True),
            patch("builtins.open") as mock_open,
            patch("hashlib.new") as mock_new,
        ):
            mock_file = MagicMock()
            mock_file.read.return_value = b""
            mock_open.return_value.__enter__.return_value = mock_file

            mock_hasher = MagicMock()
            mock_hasher.hexdigest.return_value = "different_hash_value"
            mock_new.return_value = mock_hasher

            result = await IntegrityValidator().validate(reg)
            assert not result.valid
            assert not result.integrity_ok
            assert "mismatch" in result.errors[0]

    @pytest.mark.asyncio
    async def test_md5_hash_works(self) -> None:
        test_hash = "abc123def456"
        reg = _make_reg(metadata={"md5": test_hash}, endpoint="local:python")

        with (
            patch("shutil.which", return_value="/usr/bin/python"),
            patch("os.path.isfile", return_value=True),
            patch("builtins.open") as mock_open,
            patch("hashlib.new") as mock_new,
        ):
            mock_file = MagicMock()
            mock_file.read.return_value = b""
            mock_open.return_value.__enter__.return_value = mock_file

            mock_hasher = MagicMock()
            mock_hasher.hexdigest.return_value = test_hash
            mock_new.return_value = mock_hasher

            result = await IntegrityValidator().validate(reg)
            assert result.valid
            assert result.integrity_ok
            # Should have used md5
            mock_new.assert_called_with("md5")

    @pytest.mark.asyncio
    async def test_file_not_found_for_integrity_check(self) -> None:
        reg = _make_reg(metadata={"sha256": "somehash"}, endpoint="local:python")
        with (
            patch("shutil.which", return_value=None),
            patch("os.path.isfile", return_value=False),
        ):
            result = await IntegrityValidator().validate(reg)
            assert not result.valid
            assert not result.integrity_ok

    @pytest.mark.asyncio
    async def test_exception_during_hashing(self) -> None:
        reg = _make_reg(metadata={"sha256": "somehash"}, endpoint="local:python")
        with (
            patch("shutil.which", return_value="/usr/bin/python"),
            patch("os.path.isfile", return_value=True),
            patch("builtins.open"),
            patch("hashlib.new", side_effect=RuntimeError("OOM")),
        ):
            result = await IntegrityValidator().validate(reg)
            assert not result.valid
            assert not result.integrity_ok
            assert "Integrity check error" in result.errors[0]

    @pytest.mark.asyncio
    async def test_get_validator_name(self) -> None:
        assert IntegrityValidator.get_validator_name() == "integrity"


# ── ValidationPipeline ──


class TestValidationPipeline:
    @pytest.fixture
    def pipeline(self) -> ValidationPipeline:
        return ValidationPipeline()

    @pytest.mark.asyncio
    async def test_add_validator(self, pipeline: ValidationPipeline) -> None:
        pipeline.add_validator(ExecutableExistsValidator())
        assert len(pipeline.list_validators()) == 1
        assert pipeline.list_validators() == ["executable-exists"]

    @pytest.mark.asyncio
    async def test_remove_validator(self, pipeline: ValidationPipeline) -> None:
        pipeline.add_validator(ExecutableExistsValidator())
        pipeline.add_validator(VersionDetectValidator())
        assert len(pipeline.list_validators()) == 2

        removed = pipeline.remove_validator("executable-exists")
        assert removed
        assert pipeline.list_validators() == ["version-detect"]

    @pytest.mark.asyncio
    async def test_remove_nonexistent_validator(self, pipeline: ValidationPipeline) -> None:
        removed = pipeline.remove_validator("nonexistent")
        assert not removed

    @pytest.mark.asyncio
    async def test_list_validators_empty(self, pipeline: ValidationPipeline) -> None:
        assert pipeline.list_validators() == []

    @pytest.mark.asyncio
    async def test_clear_validators(self, pipeline: ValidationPipeline) -> None:
        pipeline.add_validator(ExecutableExistsValidator())
        pipeline.add_validator(VersionDetectValidator())
        pipeline.clear_validators()
        assert pipeline.list_validators() == []

    @pytest.mark.asyncio
    async def test_validate_runs_all_validators(self, pipeline: ValidationPipeline) -> None:
        pipeline.add_validator(ExecutableExistsValidator())
        pipeline.add_validator(CapabilityMatchValidator())

        reg = _make_reg(endpoint="http://remote:8080", capabilities=[EngineCapability.CODING])
        with patch("shutil.which", return_value=None):
            results = await pipeline.validate(reg)

        assert len(results) == 2
        assert all(r.valid for r in results)

    @pytest.mark.asyncio
    async def test_validate_and_report_all_pass(self, pipeline: ValidationPipeline) -> None:
        pipeline.add_validator(ExecutableExistsValidator())
        pipeline.add_validator(CapabilityMatchValidator())

        reg = _make_reg(endpoint="http://remote:8080", capabilities=[EngineCapability.CODING])
        all_pass, results = await pipeline.validate_and_report(reg)

        assert all_pass
        assert len(results) == 2
        assert all(r.valid for r in results)

    @pytest.mark.asyncio
    async def test_validate_and_report_some_fail(self, pipeline: ValidationPipeline) -> None:
        pipeline.add_validator(ExecutableExistsValidator())
        pipeline.add_validator(CapabilityMatchValidator())

        reg = _make_reg(endpoint="local:nonexistent", capabilities=["bad_cap"])
        with patch("shutil.which", return_value=None):
            all_pass, results = await pipeline.validate_and_report(reg)

        assert not all_pass
        assert len(results) == 2
        assert not any(r.valid for r in results)

    @pytest.mark.asyncio
    async def test_validate_handles_validator_exception(self, pipeline: ValidationPipeline) -> None:
        class BrokenValidator:
            async def validate(self, registration, executable_path=None, engine=None) -> None:
                raise RuntimeError("Kaboom!")

            @staticmethod
            def get_validator_name() -> str:
                return "broken"

        pipeline.add_validator(BrokenValidator())
        reg = _make_reg()

        results = await pipeline.validate(reg)
        assert len(results) == 1
        assert not results[0].valid
        assert "Validator error" in results[0].errors[0]
