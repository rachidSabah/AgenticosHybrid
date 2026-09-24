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
    def verify(
        cls,
        directory: str,
        initial_snapshot: dict[str, float],
        task: Task,
        agent_output: str,
    ) -> ArtifactVerificationResult:
        """Independently inspect directory and verify created artifacts."""
        if not directory or not os.path.isdir(directory):
            return ArtifactVerificationResult(
                is_verified=False,
                status="FAILED_VERIFICATION",
                reason=f"Workspace directory '{directory}' does not exist or is not a directory.",
            )

        dir_path = Path(directory)
        current_snapshot = cls.snapshot_workspace(directory)

        # Detect files that are new or whose mtime has changed and have size > 0
        created_or_modified: list[dict[str, Any]] = []
        for rel_path, mtime in current_snapshot.items():
            prev_mtime = initial_snapshot.get(rel_path)
            full_path = dir_path / rel_path
            try:
                if (prev_mtime is None or mtime > prev_mtime) and full_path.is_file():
                    size = full_path.stat().st_size
                    if size > 0:
                        created_or_modified.append(
                            {
                                "path": rel_path,
                                "type": "file",
                                "exists": True,
                                "size": size,
                            }
                        )
            except OSError:
                continue

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
                    return ArtifactVerificationResult(
                        is_verified=False,
                        status="FAILED_VERIFICATION",
                        reason=(
                            "Agent claimed 'Verified Complete' or completion, but no files "
                            "were created or modified on disk in the workspace."
                        ),
                    )
                # Pure markdown plan generated when files were expected
                log.warning(
                    "verification.empty_artifacts_rejected",
                    task_id=task.id,
                    title=task.title,
                )
                return ArtifactVerificationResult(
                    is_verified=False,
                    status="FAILED_VERIFICATION",
                    reason=(
                        "Task required workspace deliverables, but only a Markdown summary or "
                        "plan was generated without actual files created on disk."
                    ),
                )

            # Files exist: verify each artifact independently
            valid_artifacts = []
            for art in real_deliverables:
                art_full = dir_path / art["path"]
                if art_full.exists() and art_full.is_file() and art_full.stat().st_size > 0:
                    valid_artifacts.append(art)

            if not valid_artifacts:
                return ArtifactVerificationResult(
                    is_verified=False,
                    status="FAILED_VERIFICATION",
                    reason="Created workspace files are empty (0 bytes).",
                )

            log.info(
                "verification.artifacts_verified",
                task_id=task.id,
                count=len(valid_artifacts),
            )
            return ArtifactVerificationResult(
                is_verified=True,
                status="VERIFIED",
                reason=f"Successfully verified {len(valid_artifacts)} deliverable artifact(s).",
                artifacts=valid_artifacts,
            )

        # For non-deliverable tasks (pure research/advisory):
        # If files happened to be created, record them, otherwise mark as no artifacts required.
        return ArtifactVerificationResult(
            is_verified=True,
            status="VERIFIED" if created_or_modified else "NO_ARTIFACTS_REQUIRED",
            reason=(
                f"Verified {len(created_or_modified)} artifact(s)."
                if created_or_modified
                else "Task is advisory/research; no workspace file deliverables required."
            ),
            artifacts=created_or_modified,
        )

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
