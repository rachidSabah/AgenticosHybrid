"""Regression tests for WorktreeManager git execution on Windows.

The manager previously ran git via ``asyncio.create_subprocess_exec``, which
raises ``NotImplementedError`` under the Windows SelectorEventLoop (the same
bug class fixed across discovery/installer). ``_run_git`` now runs git via
``asyncio.to_thread`` + synchronous ``subprocess.run`` (loop-agnostic), and the
worktree diff/merge endpoints reuse the same approach.
"""

from __future__ import annotations

import os
import subprocess
from unittest.mock import patch

import pytest

from agentic_os.core.worktree_manager import WorktreeManager


class _FakeResult:
    def __init__(
        self,
        stdout: str = "",
        stderr: str = "",
        returncode: int = 0,
    ) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


@pytest.mark.asyncio
async def test_run_git_uses_subprocess_run_off_event_loop(tmp_path) -> None:
    mgr = WorktreeManager(str(tmp_path))
    fake = _FakeResult(
        stdout="worktree /repo\nbranch refs/heads/main\n\n",
        stderr="",
        returncode=0,
    )
    with patch("agentic_os.core.worktree_manager.subprocess.run", return_value=fake) as mock_run:
        stdout, stderr, rc = await mgr._run_git(["worktree", "list", "--porcelain"])

    assert rc == 0
    assert stdout.startswith("worktree /repo")
    assert stderr == ""
    mock_run.assert_called_once()
    args, kwargs = mock_run.call_args
    assert args[0] == ["git", "worktree", "list", "--porcelain"]
    assert kwargs["cwd"] == str(tmp_path)
    assert kwargs["capture_output"] is True


@pytest.mark.asyncio
async def test_run_git_surfaces_error_returncode(tmp_path) -> None:
    mgr = WorktreeManager(str(tmp_path))
    fake = _FakeResult(stdout="", stderr="fatal: not a git repository", returncode=128)
    with patch("agentic_os.core.worktree_manager.subprocess.run", return_value=fake):
        _stdout, stderr, rc = await mgr._run_git(["status"])

    assert rc == 128
    assert "not a git repository" in stderr


@pytest.mark.asyncio
async def test_run_git_maps_subprocess_timeout_to_124(tmp_path) -> None:
    mgr = WorktreeManager(str(tmp_path))

    def _boom(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=30)

    with patch("agentic_os.core.worktree_manager.subprocess.run", side_effect=_boom):
        _stdout, stderr, rc = await mgr._run_git(["status"])

    assert rc == 124
    assert "timed out" in stderr


@pytest.mark.asyncio
async def test_create_worktree_runs_git_add(tmp_path) -> None:
    mgr = WorktreeManager(str(tmp_path))

    def _fake_git(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert args[0] == "git"
        assert args[1] == "worktree"
        assert args[2] == "add"
        return _FakeResult(stdout="", stderr="", returncode=0)  # type: ignore[return-value]

    with patch(
        "agentic_os.core.worktree_manager.subprocess.run",
        side_effect=_fake_git,
    ):
        wt = await mgr.create_worktree("feat/test")

    assert wt.branch == "feat/test"
    assert os.path.normpath(wt.path) == os.path.normpath(
        str(tmp_path / ".worktrees" / "feat" / "test")
    )
