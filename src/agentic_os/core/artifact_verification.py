"""Independent artifact verification for agent task executions.

Spec rules enforced here (see FORENSIC remediation brief §14/§41):

* An agent's natural-language claim of completion ("Verified Complete",
  "done", a Markdown plan) is NEVER accepted as proof of work.
* After a provider returns, the orchestrator must independently verify that
  real, non-empty files were produced in the workspace before a task may be
  reported COMPLETED with verified artifacts.
* If the only thing produced is the orchestrator's own task report (or a
  plan-style Markdown document with no code artifacts), the task must be
  reported PLAN_GENERATED — never COMPLETED (for build-style roles).

The verification is filesystem-based: exists(), is_file(), size > 0, plus a
before/after workspace diff so files the agent wrote directly (without
echoing them on stdout) are counted as real artifacts too.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

# Directories that never count as deliverable locations.
_EXCLUDED_DIR_NAMES = frozenset(
    {".git", ".worktrees", "node_modules", "__pycache__", ".venv", "venv", ".agenticos"}
)

# Files written by the orchestrator itself (execution reports) — they are
# bookkeeping, not mission deliverables.
_REPORT_PREFIXES = ("task_",)

# Roles whose legitimate deliverable IS a written report (prose/document).
# Every other role (coding, devops, ...) must produce real workspace files.
_PROSE_ROLES = frozenset({"research", "documentation", "planner", "reviewer"})


def is_report_file(path: str) -> bool:
    """True when ``path`` is an orchestrator-written task report."""
    base = os.path.basename(path)
    return base.startswith(_REPORT_PREFIXES) and base.endswith(".md")


@dataclass
class WorkspaceSnapshot:
    """Point-in-time map of relative file path -> (size, mtime)."""

    root: str
    files: dict[str, tuple[int, float]] = field(default_factory=dict)

    @classmethod
    def capture(cls, root: str | None) -> "WorkspaceSnapshot":
        snap = cls(root=root or "")
        if not root or not os.path.isdir(root):
            return snap
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in _EXCLUDED_DIR_NAMES]
            for name in filenames:
                full = os.path.join(dirpath, name)
                try:
                    st = os.stat(full)
                except OSError:
                    continue
                if not os.path.isfile(full):
                    continue
                rel = os.path.relpath(full, root)
                snap.files[rel.replace(os.sep, "/")] = (st.st_size, st.st_mtime)
        return snap

    def added_or_changed(self, after: "WorkspaceSnapshot") -> list[str]:
        """Relative paths present/modified in ``after`` but not in ``self``."""
        changed: list[str] = []
        for rel, (size, _mtime) in after.files.items():
            before = self.files.get(rel)
            if before is None or before[0] != size:
                changed.append(rel)
        return changed


@dataclass
class ArtifactVerification:
    """Result of independently verifying produced artifacts."""

    ok: bool
    artifacts: list[dict] = field(default_factory=list)
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "reason": self.reason,
            "artifacts": self.artifacts,
            "artifact_count": len(self.artifacts),
        }


def verify_files(paths: list[str], min_size: int = 1) -> ArtifactVerification:
    """Independently verify that each path exists, is a file and is non-empty.

    Paths may be absolute or relative to the current workspace root; both are
    checked. A path that fails any check is reported in ``artifacts`` with
    ``verified: false`` and makes the whole verification not-ok.
    """
    artifacts: list[dict] = []
    ok = bool(paths)
    for path in paths:
        entry: dict = {"path": path, "exists": False, "is_file": False, "size": 0}
        try:
            if os.path.exists(path):
                entry["exists"] = True
                if os.path.isfile(path):
                    entry["is_file"] = True
                    entry["size"] = os.path.getsize(path)
        except OSError as exc:
            entry["error"] = str(exc)
        entry["verified"] = entry["is_file"] and entry["size"] >= max(1, min_size)
        artifacts.append(entry)
        if not entry["verified"]:
            ok = False
    reason = "" if ok else "one or more declared artifacts failed verification"
    return ArtifactVerification(ok=ok, artifacts=artifacts, reason=reason)


def looks_like_plan_only(result: str | None) -> bool:
    """True when the result is prose/plan-style Markdown with no code blocks.

    A build task that returns only a Markdown plan did NOT produce the
    requested deliverable; the orchestrator must report PLAN_GENERATED, not
    COMPLETED (spec §34/§35).
    """
    if not result or not result.strip():
        return False
    return "```" not in result


def verify_task_execution(
    *,
    role: str,
    result: str | None,
    saved_files: list[str],
    before: WorkspaceSnapshot | None,
    after: WorkspaceSnapshot | None,
    ws_root: str,
) -> ArtifactVerification:
    """Verify what a task actually produced on disk.

    ``saved_files`` are paths returned by the report/extract step (may include
    the orchestrator's own task report). The workspace diff catches files the
    agent wrote directly into its cwd.

    Rules:
    * Prose roles (research/documentation/planner/reviewer): the honest task
      report is a legitimate deliverable — verified if non-empty on disk.
    * Every other role: requires at least one real, non-empty, non-report
      file created or modified in the workspace (extracted code file or a
      file the agent wrote itself).
    """
    candidates: list[str] = []
    for path in saved_files or []:
        if not path or is_report_file(path):
            continue
        candidates.append(path if os.path.isabs(path) else os.path.join(ws_root, path))

    if before is not None and after is not None:
        # Only trust the diff when we actually captured a before-snapshot;
        # otherwise pre-existing files would be miscounted as new artifacts.
        for rel in before.added_or_changed(after):
            if is_report_file(rel):
                continue
            candidates.append(os.path.join(after.root, rel))

    # De-duplicate while preserving order.
    seen: set[str] = set()
    unique: list[str] = []
    for c in candidates:
        norm = os.path.normpath(c)
        if norm not in seen:
            seen.add(norm)
            unique.append(c)

    artifact_check = verify_files(unique)

    # Prose roles: their honest task report IS the deliverable. The report
    # path comes from the extract/persist step (it starts with task_).
    report_paths = [
        p if os.path.isabs(p) else os.path.join(ws_root or ".", p)
        for p in (saved_files or [])
        if p and is_report_file(p)
    ]
    report_ok = False
    if report_paths:
        report_check = verify_files(report_paths)
        report_ok = report_check.ok

    if artifact_check.ok:
        return artifact_check

    if role in _PROSE_ROLES:
        if report_ok:
            return ArtifactVerification(
                ok=True,
                artifacts=artifact_check.artifacts,
                reason="prose deliverable: task report verified on disk",
            )
        return ArtifactVerification(
            ok=False,
            artifacts=artifact_check.artifacts,
            reason="report role produced no readable task report",
        )

    return ArtifactVerification(
        ok=False,
        artifacts=artifact_check.artifacts,
        reason=(
            "no real, non-empty workspace artifact was produced "
            "(natural-language output is not evidence of completion)"
        ),
    )
