"""Tests for dynamic agentic CLI detection.

Contract: an agent is reported ONLY if a binary exists on PATH AND it
responds to a probe. Nothing is invented from a static list.
"""

from __future__ import annotations

import pytest

from agentic_os.core.brains.dynamic_detect import (
    AGENTIC_PROBE_TIMEOUT,
    classify_binary,
    is_agentic_candidate,
    probe_binary,
    scan_path_for_agents,
)


def test_known_agent_keywords_recognised():
    assert is_agentic_candidate("codex")
    assert is_agentic_candidate("claude")
    assert is_agentic_candidate("agy")
    assert is_agentic_candidate("opencode")
    assert is_agentic_candidate("hermes")


def test_non_agent_binaries_rejected():
    """git/node/python are runtimes, not agentic CLIs."""
    assert not is_agentic_candidate("git")
    assert not is_agentic_candidate("node")
    assert not is_agentic_candidate("python")
    assert not is_agentic_candidate("ls")


def test_classify_maps_known_tools():
    assert classify_binary("codex")[0] == "Codex CLI"
    assert classify_binary("agy")[0] == "Antigravity CLI"
    assert classify_binary("opencode")[0] == "OpenCode"


def test_classify_unknown_tool_still_usable():
    """An unrecognised agentic binary is reported generically, not dropped."""
    name, vendor = classify_binary("some-new-agent")
    assert name  # non-empty display name
    assert vendor  # non-empty vendor


@pytest.mark.asyncio
async def test_probe_binary_false_on_broken_cli(monkeypatch):
    """A CLI that errors on --version must be reported as not working.

    This is the gemini case: installed on PATH but non-functional.
    """

    async def fake_run(*args, **kwargs):
        class R:
            returncode = 1
            stdout = ""
            stderr = "Invalid configuration"

        return R()

    monkeypatch.setattr(
        "agentic_os.core.brains.dynamic_detect._run_probe",
        fake_run,
    )
    ok, version = await probe_binary("gemini")
    assert ok is False


@pytest.mark.asyncio
async def test_probe_binary_true_when_works(monkeypatch):
    async def fake_run(*args, **kwargs):
        class R:
            returncode = 0
            stdout = "codex-cli 0.153.2"
            stderr = ""

        return R()

    monkeypatch.setattr(
        "agentic_os.core.brains.dynamic_detect._run_probe",
        fake_run,
    )
    ok, version = await probe_binary("codex")
    assert ok is True
    assert "0.153.2" in version


@pytest.mark.asyncio
async def test_probe_binary_false_when_missing():
    ok, version = await probe_binary("definitely-not-a-real-binary-xyz")
    assert ok is False
    assert version == ""


@pytest.mark.asyncio
async def test_probe_rejects_installed_but_broken_cli(monkeypatch):
    """gemini case: --version exits 0 but any real run fails on bad config."""

    async def fake_run(cmd, timeout):
        args = cmd[1:] if len(cmd) > 1 else []

        class R:
            returncode = 0
            stdout = b"0.58.0"
            stderr = b""

        if args and args[0] in ("--help", "-h", "help"):
            R.stderr = b"Invalid configuration in settings.json"
        return R()

    monkeypatch.setattr("agentic_os.core.brains.dynamic_detect._run_probe", fake_run)
    ok, version = await probe_binary("gemini")
    assert ok is False
    assert version == ""


@pytest.mark.asyncio
async def test_probe_accepts_healthy_cli(monkeypatch):
    async def fake_run(cmd, timeout):
        class R:
            returncode = 0
            stdout = b"agy 1.2.8"
            stderr = b""

        return R()

    monkeypatch.setattr("agentic_os.core.brains.dynamic_detect._run_probe", fake_run)
    ok, version = await probe_binary("agy")
    assert ok is True
    assert "1.2.8" in version


@pytest.mark.asyncio
async def test_scan_returns_only_probed_agents(monkeypatch):
    """End contract: scan yields agents that actually responded."""

    async def fake_probe(name: str, timeout: float = AGENTIC_PROBE_TIMEOUT):
        return (name == "codex"), ("1.0" if name == "codex" else "")

    monkeypatch.setattr(
        "agentic_os.core.brains.dynamic_detect.probe_binary",
        fake_probe,
    )
    monkeypatch.setattr(
        "agentic_os.core.brains.dynamic_detect._iter_path_binaries",
        lambda: iter(["codex", "gemini", "git"]),
    )
    found = await scan_path_for_agents()
    names = [f["key"] for f in found]
    assert "codex" in names
    assert "gemini" not in names  # present but broken -> excluded
    assert "git" not in names  # not agentic
