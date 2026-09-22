"""Acceptance: remove an agent -> rescan -> gone; restore -> back (§5).

Uses a real executable on PATH so nothing about the app is stubbed.
Run with: pytest -m slow -o addopts="" tests/test_discovery_removal.py
"""

from __future__ import annotations

import os
import shutil
import stat
import sys

import pytest

from agentic_os.core.brains.discovery_engine import AgentDiscoveryEngine

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(sys.platform != "win32", reason="real Windows executable"),
]


def _write_cli(directory: str, name: str, version: str) -> str:
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, f"{name}.cmd")
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
async def test_remove_then_restore_agent(tmp_path, monkeypatch):
    """§5: uninstall -> rescan -> absent; reinstall -> rescan -> bound again."""
    bindir = str(tmp_path / "bin")
    path = _write_cli(bindir, "disappearingagent", "3.3.3")
    monkeypatch.setenv("PATH", bindir + os.pathsep + os.environ.get("PATH", ""))

    engine = AgentDiscoveryEngine()

    snap1 = await engine.scan()
    found = next((a for a in snap1.agents if a.name == "disappearingagent"), None)
    assert found is not None, "agent not discovered on install"
    record = {
        "id": found.id,
        "executable_path": found.executable_path,
        "version": found.version,
        "status": found.status,
    }
    assert record["status"] == "healthy"
    assert record["version"] == "3.3.3"

    # Make the executable unavailable (as an uninstall would).
    hidden = path + ".hidden"
    shutil.move(path, hidden)

    snap2 = await engine.scan()
    assert "disappearingagent" not in {a.name for a in snap2.agents}
    assert "disappearingagent" not in {a.name for a in snap2.active_agents()}

    # Restore and rescan — no rebuild, no restart.
    shutil.move(hidden, path)
    snap3 = await engine.scan()

    back = next((a for a in snap3.agents if a.name == "disappearingagent"), None)
    assert back is not None, "agent did not reappear after restore"
    assert back.status == "healthy"
    assert back.version == "3.3.3"
