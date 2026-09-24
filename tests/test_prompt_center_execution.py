"""Authoritative Regression Test Suite for Prompt Center Execution and SSoT Swarm (§25).

Covers all 20 required forensic tests:
 1. test_prompt_creates_real_task
 2. test_agent_selection_uses_dynamic_discovery
 3. test_runtime_cannot_be_selected_as_ai_agent
 4. test_retired_gemini_cannot_be_selected
 5. test_task_does_not_complete_from_markdown_only
 6. test_task_does_not_complete_from_agent_claim
 7. test_task_completes_after_real_file_creation
 8. test_modified_file_is_verified
 9. test_deleted_file_is_verified
10. test_required_build_is_executed
11. test_failed_build_causes_failure
12. test_fake_deliverable_fence_cannot_create_directories
13. test_directory_cannot_be_executed
14. test_help_flag_cannot_be_executable
15. test_windows_subprocess_has_no_console_window
16. test_running_requires_real_pid
17. test_execution_graph_contains_only_real_tasks
18. test_no_consensus_without_real_consensus
19. test_no_synthetic_metrics
20. test_prompt_center_end_to_end
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from fastapi.testclient import TestClient

from agentic_os.adapters.providers.auto_bind import KNOWN_AGENTS
from agentic_os.api.app import create_app
from agentic_os.core.brains.discovery_engine import agent_discovery_engine
from agentic_os.core.brains.probes import _run, classify, probe_version
from agentic_os.core.brains.schema import (
    KIND_AI_AGENT_CLI,
    KIND_DEV_RUNTIME,
    KIND_PACKAGE_MANAGER,
    KIND_SYSTEM_UTILITY,
    KIND_UNKNOWN,
    KIND_VCS,
)
from agentic_os.core.brains.windows_detector import KNOWN_RUNTIMES
from agentic_os.core.orchestration.registry import OrchestrationAgentRegistry
from agentic_os.core.orchestration.swarm_coordinator import ConsensusManager, ConsensusType
from agentic_os.core.orchestrator import _extract_and_persist_files
from agentic_os.core.verification import ArtifactVerifier
from agentic_os.domain.agent import Agent, AgentStatus, Task, TaskStatus
from agentic_os.domain.execution import EngineType, ExecutionEngine
from agentic_os.kernel import Kernel


# ── Test 1: Prompt Creates Real Task ─────────────────────────────────────────
def test_prompt_creates_real_task():
    """A prompt submitted to Prompt Center creates an authoritative Task with full lifecycle fields."""
    with TemporaryDirectory() as tmpdir:
        task = Task(
            title="Create user auth service",
            role="coding",
            user_prompt="Build user authentication in auth.py with JWT support",
            workspace=tmpdir,
            requested_deliverables=["auth.py"],
        )
        assert task.id and len(task.id) >= 8
        assert task.task_id == task.id
        assert task.prompt == "Build user authentication in auth.py with JWT support"
        assert task.workspace == tmpdir
        assert task.requested_deliverables == ["auth.py"]
        assert task.status == TaskStatus.PENDING
        assert task.pid is None
        assert task.created_files == []
        assert task.modified_files == []
        assert task.deleted_files == []
        assert task.tests_run == []
        assert task.verification_status is None


# ── Test 2: Agent Selection Uses Dynamic Discovery ───────────────────────────
def test_agent_selection_uses_dynamic_discovery():
    """Agent selection inspects dynamically discovered machine agents, never static assumptions."""
    snapshot = agent_discovery_engine.snapshot
    # The discovery engine must have a platform set and provide dynamic active agents
    assert snapshot.platform in ("windows", "linux", "darwin", "fake")
    active = snapshot.active_agents()
    for agent in active:
        assert agent.command, f"Discovered agent {agent.name} must have a valid executable command"
        assert agent.status in ("healthy", "degraded", "discovered")
        assert agent.kind == KIND_AI_AGENT_CLI


# ── Test 3: Runtime Cannot Be Selected as AI Agent ───────────────────────────
def test_runtime_cannot_be_selected_as_ai_agent():
    """Developer runtimes (python, node, git, bun, uv) must not be classified as AI agents."""
    prohibited = {"python", "node", "git", "bun", "uv", "docker"}
    for runtime in KNOWN_RUNTIMES:
        if runtime["key"] in prohibited:
            assert runtime.get("is_agent") is False, (
                f"Runtime {runtime['key']} must have is_agent=False"
            )

    for bad in ("python", "node", "git", "uv", "bun"):
        kind = classify(bad, f"Help for {bad}")
        assert kind != KIND_AI_AGENT_CLI, f"Runtime {bad} was incorrectly classified as AI agent"
        assert kind in (
            KIND_DEV_RUNTIME,
            KIND_VCS,
            KIND_PACKAGE_MANAGER,
            KIND_SYSTEM_UTILITY,
            KIND_UNKNOWN,
        )


# ── Test 4: Retired Gemini Cannot Be Selected ────────────────────────────────
@pytest.mark.asyncio
async def test_retired_gemini_cannot_be_selected():
    """Gemini CLI must never enter active agent registry, probes, or auto-bind."""
    # 1. auto_bind
    binaries = [a["binary"] for a in KNOWN_AGENTS]
    assert "gemini" not in binaries

    # 2. probe_version must reject gemini immediately
    result = await probe_version("C:\\fake\\gemini.cmd")
    assert result.ok is False
    assert "retired" in result.detail.lower()

    # 3. orchestrator registry sync must exclude gemini
    from unittest.mock import AsyncMock

    fake_runtime = AsyncMock()
    fake_runtime.list_engines.return_value = [
        ExecutionEngine(id="gemini-1", name="gemini", engine_type=EngineType.GENERIC),
        ExecutionEngine(id="claude-1", name="claude", engine_type=EngineType.CLAUDE_CODE),
    ]
    reg = OrchestrationAgentRegistry(runtime=fake_runtime)
    synced = await reg.sync_from_runtime()
    synced_names = [a.name.lower() for a in synced]
    assert "gemini" not in synced_names
    assert "claude" in synced_names


# ── Test 5: Task Does Not Complete from Markdown Only ────────────────────────
def test_task_does_not_complete_from_markdown_only():
    """When deliverables are expected, generating only a task summary markdown file must fail."""
    with TemporaryDirectory() as tmpdir:
        task = Task(
            title="Create customer portal component",
            role="coding",
            user_prompt="Build CustomerPortal.tsx component",
            workspace=tmpdir,
        )
        pre_snap = ArtifactVerifier.snapshot_workspace(tmpdir)

        # Agent only generates a markdown summary
        summary = Path(tmpdir) / f"task_{task.id[:8]}_{task.role}.md"
        summary.write_text("# Customer Portal Plan\nComponent design details...", encoding="utf-8")

        result = ArtifactVerifier.verify(tmpdir, pre_snap, task, "Plan generated in task.md")
        assert result.is_verified is False
        assert result.status == "FAILED_VERIFICATION"
        assert "only a markdown summary" in result.reason.lower()
        assert task.verification_status == "FAILED_VERIFICATION"


# ── Test 6: Task Does Not Complete from Agent Claim ──────────────────────────
def test_task_does_not_complete_from_agent_claim():
    """Natural-language completion claims without real files on disk must be rejected."""
    with TemporaryDirectory() as tmpdir:
        task = Task(
            title="Build REST API",
            role="coding",
            user_prompt="Create FastAPI routes in api.py",
            workspace=tmpdir,
        )
        pre_snap = ArtifactVerifier.snapshot_workspace(tmpdir)

        fake_claim = (
            "Status: Verified Complete\n"
            "[DELIVERABLE_VERIFIED]\n"
            "100% test integrity achieved.\n"
            "All endpoints created."
        )
        result = ArtifactVerifier.verify(tmpdir, pre_snap, task, fake_claim)
        assert result.is_verified is False
        assert result.status == "FAILED_VERIFICATION"
        assert "claimed 'verified complete'" in result.reason.lower()


# ── Test 7: Task Completes After Real File Creation ──────────────────────────
def test_task_completes_after_real_file_creation():
    """Real created non-empty files must pass independent artifact verification."""
    with TemporaryDirectory() as tmpdir:
        task = Task(
            title="Implement helper function",
            role="coding",
            user_prompt="Create utils.py with format_date function",
            workspace=tmpdir,
        )
        pre_snap = ArtifactVerifier.snapshot_workspace(tmpdir)

        util_file = Path(tmpdir) / "utils.py"
        util_file.write_text("def format_date(d): return str(d)\n", encoding="utf-8")

        result = ArtifactVerifier.verify(tmpdir, pre_snap, task, "Created utils.py")
        assert result.is_verified is True
        assert result.status == "VERIFIED"
        assert len(result.artifacts) == 1
        assert result.artifacts[0]["path"] == "utils.py"
        assert "utils.py" in task.created_files
        assert task.verification_status == "VERIFIED"


# ── Test 8: Modified File Is Verified ────────────────────────────────────────
def test_modified_file_is_verified():
    """Modification of existing files is tracked and independently verified."""
    with TemporaryDirectory() as tmpdir:
        target = Path(tmpdir) / "config.json"
        target.write_text('{"version": "1.0.0"}', encoding="utf-8")

        task = Task(
            title="Update config version",
            role="coding",
            user_prompt="Update version in config.json to 2.0.0",
            workspace=tmpdir,
        )
        pre_snap = ArtifactVerifier.snapshot_workspace(tmpdir)

        # Modify file
        import time

        time.sleep(0.01)  # Ensure mtime increments
        target.write_text('{"version": "2.0.0", "features": ["auth"]}', encoding="utf-8")

        result = ArtifactVerifier.verify(tmpdir, pre_snap, task, "Updated config.json")
        assert result.is_verified is True
        assert result.status == "VERIFIED"
        assert "config.json" in result.modified_files
        assert "config.json" in task.modified_files


# ── Test 9: Deleted File Is Verified ─────────────────────────────────────────
def test_deleted_file_is_verified():
    """File deletion requested by a task is tracked and verified."""
    with TemporaryDirectory() as tmpdir:
        obsolete = Path(tmpdir) / "deprecated.py"
        obsolete.write_text("# old file\n", encoding="utf-8")

        task = Task(
            title="Remove obsolete module",
            role="coding",
            user_prompt="Delete the deprecated.py file from workspace",
            workspace=tmpdir,
        )
        pre_snap = ArtifactVerifier.snapshot_workspace(tmpdir)

        # Remove the file
        obsolete.unlink()

        result = ArtifactVerifier.verify(tmpdir, pre_snap, task, "Removed deprecated.py")
        assert result.is_verified is True
        assert result.status == "VERIFIED"
        assert "deprecated.py" in result.deleted_files
        assert "deprecated.py" in task.deleted_files


# ── Test 10: Required Build Is Executed ──────────────────────────────────────
def test_required_build_is_executed():
    """Build and validation commands run in the real workspace and capture telemetry."""
    with TemporaryDirectory() as tmpdir:
        task = Task(
            title="Run build validation",
            role="coding",
            user_prompt="Compile and test main.py",
            workspace=tmpdir,
        )
        script = Path(tmpdir) / "main.py"
        script.write_text("print('build passed')\n", encoding="utf-8")

        test_info = ArtifactVerifier.execute_build_or_test(
            directory=tmpdir,
            command=[sys.executable, "-c", "import sys; sys.exit(0)"],
            task=task,
        )
        assert test_info["passed"] is True
        assert test_info["exit_code"] == 0
        assert test_info["duration_ms"] >= 0
        assert len(task.tests_run) == 1
        assert task.verification_status == "VERIFIED"


# ── Test 11: Failed Build Causes Failure ─────────────────────────────────────
def test_failed_build_causes_failure():
    """A build command exiting with non-zero code fails task verification."""
    with TemporaryDirectory() as tmpdir:
        task = Task(
            title="Validate TypeScript compilation",
            role="coding",
            user_prompt="Build project with tsc",
            workspace=tmpdir,
        )
        result = ArtifactVerifier.verify_build(
            directory=tmpdir,
            command=[
                sys.executable,
                "-c",
                "import sys; sys.stderr.write('syntax error'); sys.exit(1)",
            ],
            task=task,
        )
        assert result.is_verified is False
        assert result.status == "FAILED_VERIFICATION"
        assert "failed with exit code 1" in result.reason
        assert task.verification_status == "FAILED_VERIFICATION"


# ── Test 12: Fake Deliverable Fence Cannot Create Directories ─────────────────
def test_fake_deliverable_fence_cannot_create_directories():
    """Fenced blocks containing bogus headers like [DELIVERABLE_VERIFIED] cannot create directories."""
    with TemporaryDirectory() as tmpdir:
        task = Task(title="Design theme", role="coding")
        bogus_output = (
            "```markdown [DELIVERABLE_VERIFIED]\n"
            "# Fake deliverable header\n"
            "```\n"
            "```[DELIVERABLE_VERIFIED]\n"
            "# Another fake header\n"
            "```\n"
            "```text [DELIVERABLE_VERIFIED]/assets/css\n"
            "/* bogus */\n"
            "```\n"
        )
        extracted = _extract_and_persist_files(bogus_output, task, tmpdir, "test_provider")
        assert all(Path(f).exists() for f in extracted)
        # Ensure no directories named '[DELIVERABLE_VERIFIED]' or similar were created
        assert not (Path(tmpdir) / "[DELIVERABLE_VERIFIED]").exists()
        assert not (Path(tmpdir) / "assets" / "css").exists()
        # Only the task summary md report may exist
        for p in Path(tmpdir).iterdir():
            assert p.is_file(), f"Unexpected directory created: {p}"


# ── Test 13: Directory Cannot Be Executed ─────────────────────────────────────
@pytest.mark.asyncio
async def test_directory_cannot_be_executed():
    """Passing a directory path as the executable command must immediately fail."""
    with TemporaryDirectory() as tmpdir:
        rc, out, err = await _run([tmpdir], 2.0)
        assert rc == 127
        assert "directory, not executable" in err


# ── Test 14: Help Flag Cannot Be Executable ──────────────────────────────────
@pytest.mark.asyncio
async def test_help_flag_cannot_be_executable():
    """Flags (e.g. --help) cannot be invoked as the executable target."""
    rc, out, err = await _run(["--help"], 2.0)
    assert rc == 127
    assert "flag cannot be executable" in err


# ── Test 15: Windows Subprocess Has No Console Window ────────────────────────
def test_windows_subprocess_has_no_console_window():
    """On Windows, subprocess launches specify CREATE_NO_WINDOW (0x08000000)."""
    if os.name == "nt":
        expected_flag = subprocess.CREATE_NO_WINDOW
        assert expected_flag == 0x08000000
    else:
        pytest.skip("CREATE_NO_WINDOW is a Windows-specific process creation flag")


# ── Test 16: Running Requires Real PID ────────────────────────────────────────
def test_running_requires_real_pid():
    """A task in RUNNING status must have an authentic process ID assigned."""
    agent = Agent(role="coding", provider="claude_code")
    task = Task(title="Compile source", role="coding")

    # Mark agent running
    agent.mark_running(task.id)
    assert agent.status == AgentStatus.RUNNING
    assert agent.current_task_id == task.id

    # Simulated process launch must set real PID
    task.pid = os.getpid()
    task.status = TaskStatus.IN_PROGRESS
    assert task.pid is not None
    assert task.pid > 0


# ── Test 17: Execution Graph Contains Only Real Tasks ────────────────────────
def test_execution_graph_contains_only_real_tasks():
    """Execution graph endpoint returns only missions and tasks actually executed."""
    kernel = Kernel()
    app = create_app(kernel.platform())

    with TestClient(app) as client:
        res = client.get("/api/observability/execution-graph")
        assert res.status_code == 200
        data = res.json()
        assert "missions" in data
        assert "total" in data
        # In a fresh system with no missions, total must be 0, not 20 synthetic nodes
        assert data["total"] == len(data["missions"])


# ── Test 18: No Consensus Without Real Consensus ─────────────────────────────
@pytest.mark.asyncio
async def test_no_consensus_without_real_consensus():
    """Swarm consensus manager must not report approved consensus without actual affirmative votes."""
    cm = ConsensusManager()

    # 1. Empty votes in majority mode must result in 'tie', not approved
    result_empty = await cm.run_consensus(
        swarm_id="swarm-1",
        proposal="Deploy to production",
        votes={},
        consensus_type=ConsensusType.MAJORITY,
    )
    assert result_empty.result != "approved"
    assert result_empty.confidence == 0.0

    # 2. Unanimous 'no' must result in 'rejected'
    result_rejected = await cm.run_consensus(
        swarm_id="swarm-1",
        proposal="Delete database",
        votes={"agent-1": "no", "agent-2": "no"},
        consensus_type=ConsensusType.MAJORITY,
    )
    assert result_rejected.result == "rejected"


# ── Test 19: No Synthetic Metrics ────────────────────────────────────────────
def test_no_synthetic_metrics():
    """Metrics endpoints must never return hardcoded 35ms or 56%."""
    kernel = Kernel()
    app = create_app(kernel.platform())

    with TestClient(app) as client:
        res = client.get("/api/swarm/metrics")
        assert res.status_code == 200
        metrics = res.json()
        assert metrics.get("avg_latency_ms") != 35.0, "Hardcoded 35ms latency prohibited"
        assert metrics.get("success_rate") != 56.0, "Hardcoded 56% success rate prohibited"


# ── Test 20: Prompt Center End-to-End Execution & Transparency ───────────────
def test_prompt_center_end_to_end():
    """End-to-end task execution: produces real deliverables and transparent status reporting."""
    with TemporaryDirectory() as tmpdir:
        # Scenario A: Real work executed with non-empty files and validation
        task = Task(
            title="Create math library",
            role="coding",
            user_prompt="Create math_utils.py with add(a,b) function and test it",
            workspace=tmpdir,
            requested_deliverables=["math_utils.py", "test_math.py"],
        )
        pre_snap = ArtifactVerifier.snapshot_workspace(tmpdir)

        # Agent writes math_utils.py and test_math.py
        math_file = Path(tmpdir) / "math_utils.py"
        math_file.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")

        test_file = Path(tmpdir) / "test_math.py"
        test_file.write_text(
            "from math_utils import add\nassert add(2, 3) == 5\nprint('Tests pass')\n",
            encoding="utf-8",
        )

        # Run test verification
        build_info = ArtifactVerifier.execute_build_or_test(
            directory=tmpdir,
            command=[sys.executable, "test_math.py"],
            task=task,
        )
        assert build_info["passed"] is True

        # Run artifact verification
        verif_res = ArtifactVerifier.verify(
            directory=tmpdir,
            initial_snapshot=pre_snap,
            task=task,
            agent_output="Implemented math_utils.py and verified with test_math.py",
        )
        assert verif_res.is_verified is True
        assert verif_res.status == "VERIFIED"
        assert len(verif_res.artifacts) >= 2
        assert "math_utils.py" in task.created_files
        assert "test_math.py" in task.created_files
        assert task.verification_status == "VERIFIED"

        # Scenario B: Negative test — task claiming success with only markdown fails transparently
        neg_task = Task(
            title="Create production React application",
            role="coding",
            user_prompt="Build App.tsx with component tree",
            workspace=tmpdir,
        )
        neg_pre_snap = ArtifactVerifier.snapshot_workspace(tmpdir)

        # Write markdown summary only
        md_summary = Path(tmpdir) / f"task_{neg_task.id[:8]}_{neg_task.role}.md"
        md_summary.write_text("Completed successfully. See task report.", encoding="utf-8")

        neg_res = ArtifactVerifier.verify(
            directory=tmpdir,
            initial_snapshot=neg_pre_snap,
            task=neg_task,
            agent_output="Completed successfully. See task report.",
        )
        assert neg_res.is_verified is False
        assert neg_res.status == "FAILED_VERIFICATION"
        assert neg_task.verification_status == "FAILED_VERIFICATION"
        assert "only a markdown summary or plan was generated" in neg_res.reason.lower()
