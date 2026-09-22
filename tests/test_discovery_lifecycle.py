"""Lifecycle tests: a new CLI appears, a removed CLI disappears (§21 T2/T3).

These prove discovery is genuinely dynamic — no source change needed when
the machine's installed tools change.
"""

from __future__ import annotations

import os
import stat
import sys

import pytest

from agentic_os.core.brains.discovery_engine import AgentDiscoveryEngine
from agentic_os.core.brains.probes import classify
from agentic_os.core.brains.schema import (
    KIND_AI_AGENT_CLI,
    STATUS_HEALTHY,
    STATUS_NOT_FOUND,
)

# Each scan walks the whole PATH (~35s on this machine), so these are opt-in
# via `--run-slow` to keep the default suite fast. They are run explicitly
# whenever discovery behaviour changes.
pytestmark = [
    pytest.mark.skipif(
        sys.platform != "win32",
        reason="lifecycle test drives a real Windows executable on PATH",
    ),
    pytest.mark.slow,
]


def _write_fake_cli(directory: str, name: str, version: str = "9.9.9") -> str:
    """Create a real executable that behaves like an agent CLI."""
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, f"{name}.cmd")
    # A genuine agent CLI: reports a version and describes itself in --help.
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(
            "@echo off\r\n"
            'if "%1"=="--version" echo ' + version + " & exit /b 0\r\n"
            'if "%1"=="--help" echo An AI coding agent. Chat with an LLM to generate code. & exit /b 0\r\n'
            "exit /b 0\r\n"
        )
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
    return path


@pytest.mark.asyncio
async def test_new_agent_appears_after_install(tmp_path, monkeypatch):
    """T2: install an unknown agent CLI -> discovered without code change."""
    bindir = str(tmp_path / "bin")
    _write_fake_cli(bindir, "brandnewagent")

    # Put it on PATH exactly as an installer would.
    monkeypatch.setenv("PATH", bindir + os.pathsep + os.environ.get("PATH", ""))

    engine = AgentDiscoveryEngine()
    snap = await engine.scan()

    names = {a.name for a in snap.agents}
    assert "brandnewagent" in names, f"not discovered; saw {sorted(names)}"

    found = next(a for a in snap.agents if a.name == "brandnewagent")
    assert found.version == "9.9.9"  # real, from the executable
    assert found.status == STATUS_HEALTHY
    assert found.health_score is not None
    # Windows may normalize the extension case (.CMD).
    assert found.executable_path.lower().endswith("brandnewagent.cmd")
    assert found in snap.active_agents()  # appears in AI Brain/Constellation


@pytest.mark.asyncio
async def test_removed_agent_disappears_after_uninstall(tmp_path, monkeypatch):
    """T3: remove the executable -> it vanishes from active agents."""
    bindir = str(tmp_path / "bin")
    path = _write_fake_cli(bindir, "tempagent")
    monkeypatch.setenv("PATH", bindir + os.pathsep + os.environ.get("PATH", ""))

    engine = AgentDiscoveryEngine()
    snap1 = await engine.scan()
    assert "tempagent" in {a.name for a in snap1.agents}

    # Uninstall.
    os.remove(path)
    snap2 = await engine.scan()

    assert "tempagent" not in {a.name for a in snap2.agents}
    assert "tempagent" not in {a.name for a in snap2.active_agents()}


def test_fake_executable_name_alone_is_not_enough():
    """§4: an agent-sounding name with no evidence is not promoted."""
    # No help text and no version => never an AI agent CLI.
    assert classify("totallyfakeagent", "") != KIND_AI_AGENT_CLI


def test_missing_executable_is_not_active():
    from agentic_os.core.brains.schema import DiscoveredAgent

    a = DiscoveredAgent(id="agent:ghost", name="ghost", status=STATUS_NOT_FOUND)
    assert not a.is_active()
