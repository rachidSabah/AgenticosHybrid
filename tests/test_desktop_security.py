"""Security and adversarial tests for desktop hardening, signatures, and recovery."""

from __future__ import annotations

import hashlib
from unittest.mock import patch

import pytest

from agentic_os.core.desktop import DesktopHardeningManager, SignatureVerification
from agentic_os.domain.desktop import IntegrityStatus


class TestHardeningSecurity:
    @pytest.mark.asyncio
    async def test_corrupted_integrity(self) -> None:
        mgr = DesktopHardeningManager()
        with patch("importlib.import_module", side_effect=ImportError("corrupted")):
            result = await mgr.check_integrity()
            assert result.status == IntegrityStatus.FAILED
            assert len(result.errors) > 0

    @pytest.mark.asyncio
    async def test_recovery_from_corrupted_workspace(self, tmp_path, monkeypatch) -> None:
        mgr = DesktopHardeningManager()
        monkeypatch.setenv("AGENTIC_OS_WORKSPACE_DIR", str(tmp_path / "missing"))
        result = await mgr.repair(["workspace", "config", "cache"])
        assert result.success is True

    @pytest.mark.asyncio
    async def test_recovery_mode_isolation(self) -> None:
        mgr = DesktopHardeningManager()
        assert await mgr.enter_recovery_mode() is True
        assert await mgr.enter_recovery_mode() is False

    @pytest.mark.asyncio
    async def test_memory_leak_detection_sensitivity(self) -> None:
        mgr = DesktopHardeningManager()
        config = await mgr.get_config()
        config.memory_leak_threshold_mb = 5
        await mgr.update_config(config)
        r1 = await mgr.check_memory_leaks()
        assert r1.detected is False
        r2 = await mgr.check_memory_leaks()
        assert r2.detected is False

    @pytest.mark.asyncio
    async def test_shutdown_plan_completeness(self) -> None:
        mgr = DesktopHardeningManager()
        plan = await mgr.plan_shutdown()
        assert len(plan.steps) == 6

    @pytest.mark.asyncio
    async def test_force_shutdown_no_save(self) -> None:
        mgr = DesktopHardeningManager()
        plan = await mgr.plan_shutdown(force=True)
        assert plan.force is True

    @pytest.mark.asyncio
    async def test_self_diagnostics_services(self) -> None:
        mgr = DesktopHardeningManager()
        report = await mgr.run_self_diagnostics()
        assert len(report.services) >= 5

    @pytest.mark.asyncio
    async def test_repair_rejects_unknown_target(self) -> None:
        mgr = DesktopHardeningManager()
        result = await mgr.repair(["nonexistent"])
        assert result.actions[0].status == "skipped"


class TestSignatureSecurity:
    @pytest.mark.asyncio
    async def test_verify_sha256_valid(self, tmp_path) -> None:
        sig = SignatureVerification()
        f = tmp_path / "test.bin"
        f.write_text("hello world")
        expected = hashlib.sha256(b"hello world").hexdigest()
        assert await sig.verify_sha256(str(f), expected) is True

    @pytest.mark.asyncio
    async def test_verify_sha256_invalid(self, tmp_path) -> None:
        sig = SignatureVerification()
        f = tmp_path / "test.bin"
        f.write_text("hello world")
        assert await sig.verify_sha256(str(f), "00000000") is False

    @pytest.mark.asyncio
    async def test_verify_sha256_missing_file(self) -> None:
        sig = SignatureVerification()
        result = await sig.verify_sha256("/nonexistent/path", "abc")
        assert result is False

    @pytest.mark.asyncio
    async def test_checksum_algorithm(self, tmp_path) -> None:
        sig = SignatureVerification()
        f = tmp_path / "test.bin"
        f.write_text("data")
        result = await sig.get_checksum(str(f), "sha256")
        assert result["algorithm"] == "sha256"
        assert "hash" in result
        assert "file" in result

    @pytest.mark.asyncio
    async def test_verify_signed_data(self) -> None:
        sig = SignatureVerification()
        assert await sig.verify_signature(b"data", "sig") is True

    @pytest.mark.asyncio
    async def test_certificate_chain_system_trust(self) -> None:
        sig = SignatureVerification()
        result = await sig.verify_certificate_chain("fake_cert", None)
        assert "valid" in result
        assert "chain" in result

    @pytest.mark.asyncio
    async def test_certificate_chain_with_roots(self) -> None:
        sig = SignatureVerification()
        result = await sig.verify_certificate_chain("fake_cert", ["root1", "root2"])
        assert "valid" in result
        assert "chain" in result

    @pytest.mark.asyncio
    async def test_certificate_revocation_no_url(self) -> None:
        sig = SignatureVerification()
        result = await sig.check_certificate_revocation("fake_cert")
        assert result["revoked"] is False

    @pytest.mark.asyncio
    async def test_certificate_revocation_with_url(self) -> None:
        sig = SignatureVerification()
        result = await sig.check_certificate_revocation("fake_cert", "http://crl.example.com")
        assert result["revoked"] is False
        assert result.get("crl_checked") is True

    @pytest.mark.asyncio
    async def test_code_signing_missing_file(self, tmp_path) -> None:
        sig = SignatureVerification()
        result = await sig.verify_code_signing(str(tmp_path / "nonexistent.exe"))
        assert result["valid"] is False
        assert "File not found" in result["errors"]

    @pytest.mark.asyncio
    async def test_code_signing_valid_file(self, tmp_path) -> None:
        sig = SignatureVerification()
        f = tmp_path / "signed.exe"
        f.write_text("fake executable content")
        result = await sig.verify_code_signing(str(f))
        assert "valid" in result
        assert "errors" in result
