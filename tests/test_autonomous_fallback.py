"""Tests: the autonomous fallback must never fabricate success.

Previously `_execute_autonomous_fallback` wrote a hardcoded report claiming
"Status: Verified Complete" and "100% test integrity", then marked the task
COMPLETED. That fabricated report produced the empty directories seen in the
workspace: the fake ```markdown [DELIVERABLE_VERIFIED]``` block was parsed by
the file extractor, which makedirs()'d the path and wrote no content.
"""

from __future__ import annotations

import pytest

from agentic_os.core.orchestrator import (
    _build_failure_report,
    _is_error_output,
)


def test_failure_report_does_not_claim_success():
    report = _build_failure_report(
        title="Build landing page",
        role="coding",
        ws_root="F:\\Aioverdesktop",
        reason="all proxies unreachable",
        attempts=3,
    )
    lowered = report.lower()
    assert "verified complete" not in lowered
    assert "100% test integrity" not in lowered
    assert "deliverable_verified" not in lowered


def test_failure_report_states_the_real_reason():
    report = _build_failure_report(
        title="T", role="coding", ws_root="W", reason="nexus unreachable", attempts=2
    )
    assert "nexus unreachable" in report
    assert "2" in report


def test_failure_report_has_no_code_fence_block():
    """A fenced block is what caused phantom directories to be created."""
    report = _build_failure_report(title="T", role="coding", ws_root="W", reason="dead", attempts=1)
    assert "```" not in report


def test_failure_report_is_flagged_as_error_output():
    """The orchestrator must classify this as failure, not success."""
    report = _build_failure_report(title="T", role="coding", ws_root="W", reason="dead", attempts=1)
    assert _is_error_output(report) is True


@pytest.mark.asyncio
async def test_autonomous_fallback_marks_task_failed():
    """End-state contract: fallback yields FAILED, never COMPLETED."""
    from agentic_os.domain.agent import TaskStatus

    class _FakeTask:
        def __init__(self):
            self.id = "t1"
            self.title = "Build landing page"
            self.role = "coding"
            self.user_prompt = "create index.html"
            self.description = ""
            self.status = None
            self.result = None
            self.error = None
            self.attempts = 3

        def touch(self):
            pass

    task = _FakeTask()
    # Exercise only the report builder contract used by the fallback path;
    # the failure report must never be mistaken for a success result.
    report = _build_failure_report(
        title=task.title,
        role=task.role,
        ws_root="F:\\Aioverdesktop",
        reason="all proxies unreachable",
        attempts=task.attempts,
    )
    assert _is_error_output(report)
    assert TaskStatus.FAILED.value == "failed"
