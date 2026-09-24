"""Real Artifact Verification Engine (Sections 14, 15, 34, 35, 41).

Guarantees:
- Natural-language claims ("Verified Complete", "[DELIVERABLE_VERIFIED]") are
  NEVER accepted as proof of task completion.
- When deliverables are expected, real files on disk must exist, be non-empty,
  and be independently verified.
- Tasks producing only Markdown when files were expected fail verification.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agentic_os.domain.agent import Task
from agentic_os.infrastructure.logging import get_logger

log = get_logger("verification.artifacts")

_IGNORED_DIRS = frozenset(
    {
        ".git",
        ".venv",
        "__pycache__",
        ".pytest_cache",
        ".cache",
        "logs",
        ".tmp",
        ".ruff_cache",
        "node_modules",
        ".next",
    }
)

_DELIVERABLE_ROLES = frozenset(
    {
        "coding",
        "code",
        "backend",
        "frontend",
        "architecture",
        "chief_architect",
        "backend_engineer",
        "frontend_engineer",
        "security_engineer",
        "test_engineer",
        "release_engineer",
        "engineer",
    }
)

_DELIVERABLE_KEYWORDS = (
    "build",
    "create",
    "write",
    "theme",
    "website",
    "template",
    "component",
    "implement",
    "wordpress",
    "app",
    "application",
    "script",
    "endpoint",
    "code",
    "file",
    "test suite",
    "dockerfile",
)


@dataclass
class ArtifactVerificationResult:
    """Outcome of artifact verification."""

    is_verified: bool
    status: str  # "VERIFIED" | "FAILED_VERIFICATION" | "NO_ARTIFACTS_REQUIRED"
    reason: str
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    created_files: list[str] = field(default_factory=list)
    modified_files: list[str] = field(default_factory=list)
    deleted_files: list[str] = field(default_factory=list)
    tests_run: list[str] = field(default_factory=list)
    test_results: dict[str, Any] = field(default_factory=dict)


class ArtifactVerifier:
    """Independently verifies workspace deliverables created by agent executions."""

    @staticmethod
    def snapshot_workspace(directory: str) -> dict[str, float]:
        """Capture relative paths and modification timestamps of files in workspace."""
        snapshot: dict[str, float] = {}
        if not directory or not os.path.isdir(directory):
            return snapshot

        dir_path = Path(directory)
        try:
            for root, dirs, files in os.walk(directory):
                # Prune ignored directories in-place
                dirs[:] = [d for d in dirs if d not in _IGNORED_DIRS]
                for f in files:
                    try:
                        p = Path(root) / f
                        rel = str(p.relative_to(dir_path)).replace("\\", "/")
                        snapshot[rel] = p.stat().st_mtime
                    except (OSError, ValueError):
                        continue
        except OSError:
            pass
        return snapshot

    @classmethod
    def execute_build_or_test(
        cls,
        directory: str,
        command: list[str] | str,
        task: Task | None = None,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        """Execute a build or test command in the workspace and record telemetry."""
        import subprocess
        import time

        if isinstance(command, str):
            cmd_list = command.split()
        else:
            cmd_list = list(command)

        cmd_str = " ".join(cmd_list)
        start_t = time.perf_counter()
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        try:
            proc = subprocess.run(
                cmd_list,
                cwd=directory,
                capture_output=True,
                text=True,
                timeout=timeout,
                creationflags=creationflags,
            )
            duration_ms = (time.perf_counter() - start_t) * 1000.0
            test_info = {
                "command": cmd_str,
                "cwd": directory,
                "exit_code": proc.returncode,
                "duration_ms": round(duration_ms, 2),
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "passed": proc.returncode == 0,
            }
        except subprocess.TimeoutExpired as te:
            duration_ms = (time.perf_counter() - start_t) * 1000.0
            test_info = {
                "command": cmd_str,
                "cwd": directory,
                "exit_code": 124,
                "duration_ms": round(duration_ms, 2),
                "stdout": (te.stdout or b"").decode("utf-8", errors="replace"),
                "stderr": (te.stderr or b"").decode("utf-8", errors="replace"),
                "passed": False,
            }
        except Exception as exc:
            duration_ms = (time.perf_counter() - start_t) * 1000.0
            test_info = {
                "command": cmd_str,
                "cwd": directory,
                "exit_code": 1,
                "duration_ms": round(duration_ms, 2),
                "stdout": "",
                "stderr": str(exc),
                "passed": False,
            }

        if task is not None:
            task.tests_run.append(cmd_str)
            task.test_results[cmd_str] = test_info
            if not test_info["passed"]:
                task.verification_status = "FAILED_VERIFICATION"
                task.failure_reason = (
                    f"Build/test command '{cmd_str}' failed with exit code {test_info['exit_code']}"
                )
            else:
                task.verification_status = "VERIFIED"

        return test_info

    @classmethod
    def verify_build(
        cls,
        directory: str,
        command: list[str] | str,
        task: Task | None = None,
        timeout: float = 30.0,
    ) -> ArtifactVerificationResult:
        test_info = cls.execute_build_or_test(directory, command, task=task, timeout=timeout)
        if not test_info["passed"]:
            return ArtifactVerificationResult(
                is_verified=False,
                status="FAILED_VERIFICATION",
                reason=f"Build/test command '{test_info['command']}' failed with exit code {test_info['exit_code']}",
                tests_run=[test_info["command"]],
                test_results={test_info["command"]: test_info},
            )
        return ArtifactVerificationResult(
            is_verified=True,
            status="VERIFIED",
            reason=f"Build/test command '{test_info['command']}' completed successfully (exit code 0).",
            tests_run=[test_info["command"]],
            test_results={test_info["command"]: test_info},
        )

    @classmethod
    def verify(
        cls,
        directory: str,
        initial_snapshot: dict[str, float],
        task: Task,
        agent_output: str,
    ) -> ArtifactVerificationResult:
        """Independently inspect directory and verify created artifacts."""
        if not directory or not os.path.isdir(directory):
            res = ArtifactVerificationResult(
                is_verified=False,
                status="FAILED_VERIFICATION",
                reason=f"Workspace directory '{directory}' does not exist or is not a directory.",
            )
            task.verification_status = res.status
            task.verification_reason = res.reason
            return res

        dir_path = Path(directory)
        current_snapshot = cls.snapshot_workspace(directory)

        # Detect files that are new, modified, or deleted
        created_or_modified: list[dict[str, Any]] = []
        created_files: list[str] = []
        modified_files: list[str] = []
        deleted_files: list[str] = [rel for rel in initial_snapshot if rel not in current_snapshot]

        for rel_path, mtime in current_snapshot.items():
            prev_mtime = initial_snapshot.get(rel_path)
            full_path = dir_path / rel_path
            try:
                if full_path.is_file():
                    size = full_path.stat().st_size
                    if prev_mtime is None and size > 0:
                        created_files.append(rel_path)
                        created_or_modified.append(
                            {
                                "path": rel_path,
                                "type": "file",
                                "exists": True,
                                "size": size,
                                "change": "created",
                            }
                        )
                    elif prev_mtime is not None and mtime > prev_mtime:
                        modified_files.append(rel_path)
                        created_or_modified.append(
                            {
                                "path": rel_path,
                                "type": "file",
                                "exists": True,
                                "size": size,
                                "change": "modified",
                            }
                        )
            except OSError:
                continue

        # Sync detected changes to task model
        task.created_files = list(created_files)
        task.modified_files = list(modified_files)
        task.deleted_files = list(deleted_files)
        task.changed_files = list(created_files + modified_files + deleted_files)

        text_to_check = (
            f"{task.title or ''} {task.description or ''} {task.user_prompt or ''}".lower()
        )
        is_deletion_task = any(
            kw in text_to_check for kw in ("delete", "remove", "clean", "drop", "unlink")
        )
        if is_deletion_task and deleted_files:
            task.verification_status = "VERIFIED"
            task.verification_reason = (
                f"Successfully verified deletion of {len(deleted_files)} file(s)."
            )
            return ArtifactVerificationResult(
                is_verified=True,
                status="VERIFIED",
                reason=task.verification_reason,
                artifacts=[
                    {"path": p, "type": "file", "exists": False, "change": "deleted"}
                    for p in deleted_files
                ],
                created_files=created_files,
                modified_files=modified_files,
                deleted_files=deleted_files,
            )

        # Check if the task expected file deliverables
        requires_deliverables = cls._task_requires_deliverables(task)

        output_lower = (agent_output or "").lower()
        claims_verified = (
            "verified complete" in output_lower
            or "deliverable_verified" in output_lower
            or "100% test integrity" in output_lower
            or "mission complete" in output_lower
        )

        if requires_deliverables:
            real_deliverables = [
                art
                for art in created_or_modified
                if not (Path(art["path"]).name.startswith("task_") and art["path"].endswith(".md"))
            ]
            if not real_deliverables:
                if claims_verified:
                    log.warning(
                        "verification.fabricated_claim_rejected",
                        task_id=task.id,
                        title=task.title,
                    )
                    res = ArtifactVerificationResult(
                        is_verified=False,
                        status="FAILED_VERIFICATION",
                        reason=(
                            "Agent claimed 'Verified Complete' or completion, but no files "
                            "were created or modified on disk in the workspace."
                        ),
                        created_files=created_files,
                        modified_files=modified_files,
                        deleted_files=deleted_files,
                    )
                    task.verification_status = res.status
                    task.verification_reason = res.reason
                    return res

                # Pure markdown plan generated when files were expected
                log.warning(
                    "verification.empty_artifacts_rejected",
                    task_id=task.id,
                    title=task.title,
                )
                res = ArtifactVerificationResult(
                    is_verified=False,
                    status="FAILED_VERIFICATION",
                    reason=(
                        "Task required workspace deliverables, but only a Markdown summary or "
                        "plan was generated without actual files created on disk."
                    ),
                    created_files=created_files,
                    modified_files=modified_files,
                    deleted_files=deleted_files,
                )
                task.verification_status = res.status
                task.verification_reason = res.reason
                return res

            # Files exist: verify each artifact independently
            valid_artifacts = []
            for art in real_deliverables:
                art_full = dir_path / art["path"]
                if art_full.exists() and art_full.is_file() and art_full.stat().st_size > 0:
                    valid_artifacts.append(art)

            if not valid_artifacts:
                res = ArtifactVerificationResult(
                    is_verified=False,
                    status="FAILED_VERIFICATION",
                    reason="Created workspace files are empty (0 bytes).",
                    created_files=created_files,
                    modified_files=modified_files,
                    deleted_files=deleted_files,
                )
                task.verification_status = res.status
                task.verification_reason = res.reason
                return res

            log.info(
                "verification.artifacts_verified",
                task_id=task.id,
                count=len(valid_artifacts),
            )
            res = ArtifactVerificationResult(
                is_verified=True,
                status="VERIFIED",
                reason=f"Successfully verified {len(valid_artifacts)} deliverable artifact(s).",
                artifacts=valid_artifacts,
                created_files=created_files,
                modified_files=modified_files,
                deleted_files=deleted_files,
            )
            task.verification_status = res.status
            task.verification_reason = res.reason
            task.artifacts = valid_artifacts
            return res

        # For non-deliverable tasks (pure research/advisory):
        # If files happened to be created, record them, otherwise mark as no artifacts required.
        res = ArtifactVerificationResult(
            is_verified=True,
            status="VERIFIED" if created_or_modified else "NO_ARTIFACTS_REQUIRED",
            reason=(
                f"Verified {len(created_or_modified)} artifact(s)."
                if created_or_modified
                else "Task is advisory/research; no workspace file deliverables required."
            ),
            artifacts=created_or_modified,
            created_files=created_files,
            modified_files=modified_files,
            deleted_files=deleted_files,
        )
        task.verification_status = res.status
        task.verification_reason = res.reason
        task.artifacts = created_or_modified
        return res

    @classmethod
    def _task_requires_deliverables(cls, task: Task) -> bool:
        """Return True if the task's role, title, or prompt indicates deliverables are expected."""
        role_lower = (task.role or "").lower()
        if any(r in role_lower for r in _DELIVERABLE_ROLES):
            return True

        text_to_check = (
            f"{task.title or ''} {task.description or ''} {task.user_prompt or ''}".lower()
        )
        if any(kw in text_to_check for kw in _DELIVERABLE_KEYWORDS):
            # Check if prompt explicitly asks for "plan only" or "markdown only"
            if (
                "plan only" in text_to_check
                or "markdown only" in text_to_check
                or "just a plan" in text_to_check
            ):
                return False
            return True

        return False
