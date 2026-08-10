"""Regression tests: agent worktrees must be rooted at the *active workspace*.

Previously the kernel wired ``WorktreeManager()`` with no workspace root, so it
defaulted to ``os.getcwd()`` (the Agenticos repo) and agents executed inside
``E:\\Agenticos\\.worktrees\\agent-*`` instead of the user-selected workspace
(e.g. ``E:\\Mission``). They analyzed the wrong codebase, and produced echoed /
binary / garbage output while the ``task_*.md`` files were still written to the
real workspace.

``_create_worktree_for_agent`` now syncs the manager to
``get_workspace_root()`` before creating a worktree, and skips worktree
isolation entirely for non-git workspaces so agents run directly in the
workspace root and their produced files land there.
"""

from __future__ import annotations

import os
import subprocess
from unittest.mock import patch

import pytest

from agentic_os.core.worktree_manager import WorktreeManager
from agentic_os.domain.agent import Agent, Task


def _make_agent() -> Agent:
    return Agent(role="coding", provider="mock", name="tester")


def _make_task() -> Task:
    return Task(title="Build the theme", role="coding", user_prompt="Make it responsive")


def _git(repo: str, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


@pytest.fixture
def git_workspace(tmp_path) -> str:
    """A real git repo to serve as the active workspace."""
    repo = str(tmp_path / "Mission")
    os.makedirs(repo)
    _git(repo, "init")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "T")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "init")
    return repo


@pytest.fixture
def plain_workspace(tmp_path) -> str:
    """A fresh non-git folder (like a new E:\\Mission)."""
    repo = str(tmp_path / "MissionPlain")
    os.makedirs(repo)
    return repo


async def test_syncs_root_to_active_workspace_before_worktree(orchestrator, git_workspace) -> None:
    """Worktree must be created inside the active workspace, not os.getcwd()."""
    wm = WorktreeManager()  # unrooted — reproduces the kernel bug
    orchestrator.worktree_manager = wm

    with patch(
        "agentic_os.domain.workspace.get_workspace_root",
        return_value=git_workspace,
    ):
        wt_path = await orchestrator._create_worktree_for_agent(_make_agent(), _make_task())

    assert wt_path is not None
    assert wt_path.startswith(git_workspace)  # rooted at active workspace
    assert not wt_path.startswith(os.getcwd())  # NOT the process cwd


async def test_non_git_workspace_skips_worktree_and_returns_none(
    orchestrator, plain_workspace
) -> None:
    """Non-git workspaces run the agent directly in the workspace root."""
    wm = WorktreeManager()
    orchestrator.worktree_manager = wm

    with patch(
        "agentic_os.domain.workspace.get_workspace_root",
        return_value=plain_workspace,
    ):
        wt_path = await orchestrator._create_worktree_for_agent(_make_agent(), _make_task())

    assert wt_path is None  # isolation skipped → falls back to workspace root
