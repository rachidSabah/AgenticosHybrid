"""Tests for Swarm Execution & Dynamic Agent Discovery Remediation.

Verifies:
1. Gemini CLI never enters the active agent registry or provider mapping.
2. Developer runtimes (python, node, bun, git, uv) are excluded from the AI agent registry.
3. Deliverable verification rejects empty / Markdown-only artifacts when real files were expected.
4. Deliverable verification succeeds when real files on disk exist and are non-empty.
5. Real process identity (PID, exit code) is captured and tracked.
6. No synthetic telemetry (avg_latency_ms is None/calculated, success_rate is completed/finished, not hardcoded 35ms or 56%).
"""

from __future__ import annotations

from datetime import UTC
from pathlib import Path
from tempfile import TemporaryDirectory

from agentic_os.adapters.providers.auto_bind import KNOWN_AGENTS
from agentic_os.core.brains.discovery_engine import agent_discovery_engine
from agentic_os.core.brains.windows_detector import KNOWN_RUNTIMES
from agentic_os.core.mission import DEFAULT_ROLE_MAP
from agentic_os.core.verification import ArtifactVerifier
from agentic_os.domain.agent import Task


def test_retired_gemini_never_enters_agent_registry():
    """Gemini CLI must never enter active agent registry, role map, or auto-bind."""
    # 1. Check auto_bind KNOWN_AGENTS
    binaries = [a["binary"] for a in KNOWN_AGENTS]
    assert "gemini" not in binaries, "gemini must not be in auto_bind KNOWN_AGENTS"

    # 2. Check windows_detector KNOWN_RUNTIMES
    runtime_keys = [r["key"] for r in KNOWN_RUNTIMES]
    assert "gemini" not in runtime_keys, "gemini must not be in windows_detector KNOWN_RUNTIMES"

    # 3. Check DEFAULT_ROLE_MAP in mission planner
    providers = list(DEFAULT_ROLE_MAP.values())
    assert "gemini_cli" not in providers, "gemini_cli must not be in DEFAULT_ROLE_MAP"
    assert "gemini" not in providers, "gemini must not be in DEFAULT_ROLE_MAP"


def test_runtimes_not_in_ai_agent_registry():
    """Developer runtimes (python, node, git, bun, uv) must not be classified as AI agents."""
    non_agent_keys = {"python", "node", "git", "bun", "uv", "docker"}
    for r in KNOWN_RUNTIMES:
        if r["key"] in non_agent_keys:
            assert r.get("is_agent") is False, (
                f"{r['key']} must have is_agent=False in KNOWN_RUNTIMES"
            )

    # Verify discovery engine active agents
    snap = agent_discovery_engine.snapshot
    if snap.agents:
        active_names = {a.name.lower() for a in snap.active_agents()}
        for bad in ("python", "node", "git", "bun", "uv", "docker"):
            assert bad not in active_names, f"{bad} must not appear in active AI agents"


def test_empty_artifact_verification_protection():
    """Tasks requiring code/deliverables must fail verification if only Markdown or empty files exist."""
    with TemporaryDirectory() as tmpdir:
        task = Task(
            title="Create WordPress theme template",
            role="coding",
            user_prompt="Build a full custom WordPress theme",
        )
        pre_snapshot = ArtifactVerifier.snapshot_workspace(tmpdir)

        # Agent returns Markdown claim without writing actual php/css files
        agent_output = (
            "Status: Verified Complete\n"
            "[DELIVERABLE_VERIFIED]\n"
            "I have designed the complete WordPress theme template.\n"
            "# Theme Plan\nHere is how to structure it..."
        )

        # Write an execution log summary file (like task_<id>_coding.md)
        summary_file = Path(tmpdir) / f"task_{task.id[:8]}_{task.role}.md"
        summary_file.write_text(agent_output, encoding="utf-8")

        result = ArtifactVerifier.verify(tmpdir, pre_snapshot, task, agent_output)
        assert result.is_verified is False, "Claiming complete without code files must fail"
        assert result.status == "FAILED_VERIFICATION"
        assert (
            "no files were created" in result.reason.lower()
            or "only a markdown summary" in result.reason.lower()
        )


def test_real_artifact_verification():
    """Tasks with real created files on disk must pass verification."""
    with TemporaryDirectory() as tmpdir:
        task = Task(
            title="Implement REST API endpoint",
            role="coding",
            user_prompt="Write the user authentication endpoint in main.py",
        )
        pre_snapshot = ArtifactVerifier.snapshot_workspace(tmpdir)

        # Create real file with content
        code_file = Path(tmpdir) / "main.py"
        code_file.write_text("def authenticate(): return True\n", encoding="utf-8")

        agent_output = "I have implemented the authentication endpoint in main.py."
        result = ArtifactVerifier.verify(tmpdir, pre_snapshot, task, agent_output)

        assert result.is_verified is True, "Valid non-empty file must pass verification"
        assert result.status == "VERIFIED"
        assert len(result.artifacts) == 1
        assert result.artifacts[0]["path"] == "main.py"
        assert result.artifacts[0]["size"] > 0


def test_real_process_identity():
    """Task model tracks real process identity (pid, exit_code, timestamps)."""
    task = Task(
        title="Compile binary",
        role="coding",
    )
    assert task.pid is None
    assert task.exit_code is None
    assert task.started_at is None
    assert task.completed_at is None

    # Simulate process launch
    task.pid = 45678
    task.exit_code = 0
    from datetime import datetime

    task.started_at = datetime.now(UTC)
    task.completed_at = datetime.now(UTC)

    dumped = task.model_dump()
    assert dumped["pid"] == 45678
    assert dumped["exit_code"] == 0
    assert dumped["started_at"] is not None
    assert dumped["completed_at"] is not None


def test_no_synthetic_telemetry_and_clean_swarm_agents():
    """Endpoints must never return hardcoded 35ms, 56%, plan-real-1, or fake active agents."""
    from fastapi.testclient import TestClient

    from agentic_os.api.app import create_app
    from agentic_os.kernel import Kernel

    kernel = Kernel()
    app = create_app(kernel.platform())

    with TestClient(app) as client:
        # 1. Swarm metrics: no fake 35ms or 56%
        metrics_res = client.get("/api/swarm/metrics")
        assert metrics_res.status_code == 200
        metrics = metrics_res.json()
        assert metrics.get("avg_latency_ms") != 35.0, "avg_latency_ms must not be hardcoded to 35.0"
        assert metrics.get("success_rate") != 56.0, "success_rate must not be hardcoded to 56%"

        # 2. Swarm plans: no hardcoded plan-real-1
        plans_res = client.get("/api/swarm/plans")
        assert plans_res.status_code == 200
        plans = plans_res.json()
        plan_ids = [p.get("id") for p in plans]
        assert "plan-real-1" not in plan_ids, "plan-real-1 must not be hardcoded in plans"

        # 3. Swarm agents: no python, node, git, gemini
        agents_res = client.get("/api/swarm/agents")
        assert agents_res.status_code == 200
        agents = agents_res.json()
        agent_names = [a.get("name", "").lower() for a in agents]
        for prohibited in ("python", "node", "git", "gemini", "gemini_cli"):
            assert prohibited not in agent_names, f"{prohibited} must never appear as a swarm agent"
        for a in agents:
            assert a.get("status") in ("ready", "idle", "running"), (
                f"Agent status {a.get('status')} invalid"
            )
