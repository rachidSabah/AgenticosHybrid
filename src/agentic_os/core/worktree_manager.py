"""Git Worktree Manager — isolated workspaces for parallel AI agents.

Each agent gets its own git worktree so multiple agents can work on
different parts of the codebase simultaneously without conflicts.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from agentic_os.infrastructure.logging import get_logger

log = get_logger("core.worktree_manager")


@dataclass
class Worktree:
    branch: str
    path: str
    agent_id: str = ""
    task_id: str = ""
    status: str = "active"  # active | dirty | merged | removed
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    base_branch: str = "main"


class WorktreeManager:
    """Manages git worktrees for isolated agent execution.

    Worktrees are created at {workspace_root}/.worktrees/{branch_name}.
    Each worktree is a full checkout on its own branch, so agents can
    modify files independently.
    """

    def __init__(self, workspace_root: str = "") -> None:
        self._workspace_root = workspace_root or os.getcwd()
        self._worktrees: dict[str, Worktree] = {}
        self._worktrees_dir = os.path.join(self._workspace_root, ".worktrees")
        self._ensure_worktrees_dir()

    def set_workspace_root(self, root: str) -> None:
        self._workspace_root = root
        self._worktrees_dir = os.path.join(root, ".worktrees")
        self._ensure_worktrees_dir()

    def _ensure_worktrees_dir(self) -> None:
        os.makedirs(self._worktrees_dir, exist_ok=True)
        # Add .worktrees to .gitignore if not already there
        gitignore = os.path.join(self._workspace_root, ".gitignore")
        if os.path.isfile(gitignore):
            try:
                content = Path(gitignore).read_text(encoding="utf-8", errors="replace")
                if ".worktrees/" not in content:
                    Path(gitignore).write_text(
                        content.rstrip() + "\n.worktrees/\n", encoding="utf-8"
                    )
            except Exception:
                pass

    async def _run_git(self, args: list[str], cwd: str | None = None) -> tuple[str, str, int]:
        """Run a git command off the event loop.

        On Windows the SelectorEventLoop cannot do ``asyncio.create_subprocess_exec``
        (raises ``NotImplementedError``), so git is run synchronously in a worker
        thread via ``asyncio.to_thread`` (loop-agnostic).
        """

        def _capture() -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                ["git", *args],
                capture_output=True,
                text=True,
                cwd=cwd or self._workspace_root,
                timeout=30,
            )

        try:
            result = await asyncio.wait_for(asyncio.to_thread(_capture), timeout=35)
        except (TimeoutError, subprocess.TimeoutExpired):
            return "", "git command timed out", 124
        except Exception as exc:  # noqa: BLE001 - surface any subprocess error
            return "", f"git command failed: {exc}", 1
        return (
            (result.stdout or "").strip(),
            (result.stderr or "").strip(),
            result.returncode or 0,
        )

    async def create_worktree(
        self,
        branch_name: str,
        base_branch: str = "main",
        agent_id: str = "",
        task_id: str = "",
    ) -> Worktree:
        """Create a git worktree at .worktrees/{branch_name} with a new branch.

        Args:
            branch_name: The git branch name for the worktree.
            base_branch: The base branch to create from (default: main).
            agent_id: The agent this worktree is assigned to.
            task_id: The task this worktree was created for.

        Returns:
            Worktree object with the branch, path, and assignment info.
        """
        wt_path = os.path.join(self._worktrees_dir, branch_name)

        # Check if worktree already exists
        if os.path.isdir(wt_path):
            log.info("worktree.exists", branch=branch_name, path=wt_path)
            wt = Worktree(
                branch=branch_name,
                path=wt_path,
                agent_id=agent_id,
                task_id=task_id,
                base_branch=base_branch,
            )
            self._worktrees[branch_name] = wt
            return wt

        # Check if the workspace root is a git repo before creating worktrees.
        # Fresh folders like E:\Mission are not git repos, so git worktree add
        # fails with "fatal: invalid reference: <branch>". If not a repo,
        # either git init + initial commit (so branches can exist) or skip
        # worktree creation gracefully and let agents run in the workspace root.
        _, _, is_repo_rc = await self._run_git(["rev-parse", "--is-inside-work-tree"])
        if is_repo_rc != 0:
            # Not a git repo — try git init + initial commit
            log.info("worktree.not_git_repo", workspace=self._workspace_root, action="git_init")
            _, _, init_rc = await self._run_git(["init"])
            if init_rc == 0:
                # Create an initial commit so branches can be created
                await self._run_git(["add", "-A"])
                await self._run_git(["commit", "-m", "Initial commit (auto-created by AgenticOS)"])
                log.info("worktree.git_initialized", workspace=self._workspace_root)
            else:
                # git init failed — skip worktree creation gracefully
                log.info(
                    "worktree.skip_not_repo",
                    branch=branch_name,
                    workspace=self._workspace_root,
                    message=(
                        "Not a git repo and git init failed — agents will run in workspace root"
                    ),
                )
                wt = Worktree(
                    branch=branch_name,
                    path=self._workspace_root,
                    agent_id=agent_id,
                    task_id=task_id,
                    base_branch=base_branch,
                )
                self._worktrees[branch_name] = wt
                return wt

        # Create the worktree: git worktree add -b {branch} {path} {base}
        stdout, stderr, rc = await self._run_git(
            [
                "worktree",
                "add",
                "-b",
                branch_name,
                wt_path,
                base_branch,
            ]
        )

        if rc != 0:
            # Try without base_branch (create from HEAD)
            stdout, stderr, rc = await self._run_git(
                [
                    "worktree",
                    "add",
                    "-b",
                    branch_name,
                    wt_path,
                ]
            )
            if rc != 0:
                # Try without -b (branch may already exist)
                stdout, stderr, rc = await self._run_git(
                    [
                        "worktree",
                        "add",
                        wt_path,
                        branch_name,
                    ]
                )
                if rc != 0:
                    log.warning(
                        "worktree.create_failed_fallback_workspace",
                        branch=branch_name,
                        error=stderr,
                    )
                    wt = Worktree(
                        branch=branch_name,
                        path=self._workspace_root,
                        agent_id=agent_id,
                        task_id=task_id,
                        base_branch=base_branch,
                    )
                    self._worktrees[branch_name] = wt
                    return wt

        wt = Worktree(
            branch=branch_name,
            path=wt_path,
            agent_id=agent_id,
            task_id=task_id,
            base_branch=base_branch,
        )
        self._worktrees[branch_name] = wt
        log.info("worktree.created", branch=branch_name, path=wt_path, agent=agent_id)
        return wt

    async def list_worktrees(self) -> list[dict]:
        """List all active worktrees."""
        # Refresh from git
        stdout, _, _ = await self._run_git(["worktree", "list", "--porcelain"])
        git_worktrees: list[dict] = []
        current_entry: dict = {}
        for line in stdout.split("\n"):
            if line.startswith("worktree "):
                if current_entry:
                    git_worktrees.append(current_entry)
                current_entry = {"path": line[9:]}
            elif line.startswith("branch "):
                current_entry["branch"] = line[7:].replace("refs/heads/", "")
            elif line.startswith("HEAD "):
                current_entry["head"] = line[5:]
            elif line == "" and current_entry:
                git_worktrees.append(current_entry)
                current_entry = {}
        if current_entry:
            git_worktrees.append(current_entry)

        # Merge with our tracking (agent_id, task_id, status)
        result: list[dict] = []
        for gw in git_worktrees:
            wt_path = gw.get("path", "")
            branch = gw.get("branch", "")
            # Skip the main workspace worktree
            if os.path.realpath(wt_path) == os.path.realpath(self._workspace_root):
                continue
            tracked = self._worktrees.get(branch)
            result.append(
                {
                    "branch": branch,
                    "path": wt_path,
                    "agent_id": tracked.agent_id if tracked else "",
                    "task_id": tracked.task_id if tracked else "",
                    "status": tracked.status if tracked else "active",
                    "base_branch": tracked.base_branch if tracked else "main",
                    "created_at": tracked.created_at.isoformat() if tracked else None,
                }
            )
        return result

    async def remove_worktree(self, branch_name: str) -> bool:
        """Remove a worktree and its branch.

        Returns True if removed, False if not found.
        """
        wt_path = os.path.join(self._worktrees_dir, branch_name)
        if not os.path.isdir(wt_path):
            return False

        # Remove worktree
        _, _, rc = await self._run_git(
            [
                "worktree",
                "remove",
                "--force",
                wt_path,
            ]
        )
        if rc != 0:
            # Force remove directory
            import shutil

            shutil.rmtree(wt_path, ignore_errors=True)

        # Delete branch
        await self._run_git(["branch", "-D", branch_name])

        if branch_name in self._worktrees:
            self._worktrees[branch_name].status = "removed"
            del self._worktrees[branch_name]

        log.info("worktree.removed", branch=branch_name)
        return True

    def get_worktree_path(self, agent_id: str) -> str | None:
        """Get the worktree path for a given agent."""
        for wt in self._worktrees.values():
            if wt.agent_id == agent_id:
                return wt.path
        return None

    def get_worktree_by_branch(self, branch_name: str) -> Worktree | None:
        """Get a worktree by branch name."""
        return self._worktrees.get(branch_name)

    def mark_dirty(self, agent_id: str) -> None:
        """Mark a worktree as dirty (task failed)."""
        for wt in self._worktrees.values():
            if wt.agent_id == agent_id:
                wt.status = "dirty"
                log.info("worktree.marked_dirty", branch=wt.branch, agent=agent_id)
                return

    def auto_branch_name(self, agent_id: str, task_id: str = "") -> str:
        """Generate an auto branch name from agent/task IDs."""
        short_id = agent_id[:8] if agent_id else (task_id[:8] if task_id else "agent")
        return f"agent-{short_id}"


__all__ = ["WorktreeManager", "Worktree"]
