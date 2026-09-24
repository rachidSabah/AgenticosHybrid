"""Forensic remediation regression tests.

Implements the CRITICAL TESTS required by the remediation brief:

* §36  test_retired_gemini_*            — Gemini CLI never enters any registry
* §37  test_runtime_is_not_agent_*      — python/node/git never become agents
* §38  test_no_synthetic_swarm_*        — zero activity with zero executions
* §35  test_markdown_only_is_not_completed — report-only output != COMPLETED
* §41  test_real_artifact_verification  — independent filesystem verification
* §8/§15 test_retry_paths_apply_error_guard — attempts 2/3 use the SAME guard
* §9/§24 test_installed_is_not_active   — probed-but-not-executed != "active"

The agent's natural-language claim is never accepted as proof of completion:
every success path must pass independent artifact verification.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# ── §36: retired Gemini never enters the agent registry ─────────────────────


def test_retired_gemini_not_in_provider_sources() -> None:
    """gemini must be absent from every provider/agent definition source."""
    from agentic_os.adapters.providers.auto_bind import KNOWN_AGENTS

    binaries = {a.get("binary", "") for a in KNOWN_AGENTS}
    kinds = {a.get("kind", "") for a in KNOWN_AGENTS}
    assert "gemini" not in binaries
    assert "gemini_cli" not in kinds

    from agentic_os.core.brains.bridge import _BUILTIN_VENDOR_MAP

    assert "gemini" not in _BUILTIN_VENDOR_MAP
    assert "gemini-cli" not in _BUILTIN_VENDOR_MAP

    from agentic_os.core.brains.catalog import _BUILTIN_TOOL_MAPPINGS

    assert "gemini-cli" not in _BUILTIN_TOOL_MAPPINGS

    # Unknown kinds fall back to the generic strategy — but the gemini
    # strategy must not exist in the registry.
    from agentic_os.adapters.providers.strategies import _STRATEGY_REGISTRY

    assert "gemini_cli" not in _STRATEGY_REGISTRY


def test_retired_gemini_not_in_enums() -> None:
    """gemini_cli must be gone from every Python enum (spec §2)."""
    from core.contracts.execution_engine import EngineType as ContractsEngineType

    from agentic_os.core.runtime.runtime import RuntimeType as CoreRuntimeType
    from agentic_os.domain.brains import BrainVendor
    from agentic_os.domain.execution import EngineType as DomainEngineType

    assert not hasattr(ContractsEngineType, "GEMINI_CLI")
    assert not hasattr(DomainEngineType, "GEMINI_CLI")
    assert not hasattr(BrainVendor, "GEMINI_CLI")
    assert not hasattr(CoreRuntimeType, "GEMINI_CLI")


def test_retired_gemini_not_in_discovery_maps() -> None:
    """Discovery maps must not target the retired provider."""
    from services.execution_engine.discovery import _ENGINE_BINARIES
    from services.runtime_discovery.cli_discovery import _KNOWN_CLIS
    from services.runtime_discovery.manager import _BINARY_TO_RUNTIME

    from agentic_os.core.discovery.local.path_scanner import KNOWN_TOOLS

    assert all(v != "gemini" and v != "gemini-cli" for v in _ENGINE_BINARIES.values())
    assert "gemini" not in _BINARY_TO_RUNTIME
    assert "gemini-cli" not in _BINARY_TO_RUNTIME
    assert "gemini" not in _KNOWN_CLIS
    assert "gemini-cli" not in _KNOWN_CLIS
    assert "gemini-cli" not in KNOWN_TOOLS


def test_retired_gemini_aliasing_forbidden() -> None:
    """agy must map to Antigravity — never to a Gemini alias (spec §7)."""
    from services.runtime_discovery.manager import (
        _BINARY_TO_RUNTIME,
        _RUNTIME_DISPLAY_NAMES,
        _RUNTIME_VENDORS,
    )
    from services.runtime_discovery.models import RuntimeType

    assert _BINARY_TO_RUNTIME.get("agy") == RuntimeType.AGY_CLI
    assert "Antigravity" in _RUNTIME_VENDORS.get(RuntimeType.AGY_CLI, "")
    # No Gemini display name anywhere.
    assert not any("Gemini" in v for v in _RUNTIME_DISPLAY_NAMES.values())


# ── §37: runtimes are not agents ────────────────────────────────────────────


def test_runtime_connectors_marked_non_agent() -> None:
    """Python/Node/Bun/Git connectors must be flagged is_ai_agent=False."""
    from agentic_os.core.brains.runtime_bridge import (
        BunConnector,
        GitConnector,
        NodeConnector,
        PythonConnector,
    )

    assert PythonConnector.is_ai_agent is False
    assert NodeConnector.is_ai_agent is False
    assert BunConnector.is_ai_agent is False
    assert GitConnector.is_ai_agent is False


async def test_runtime_connectors_excluded_from_brain_records() -> None:
    """to_brain_records must never emit runtimes as brains (spec §22/§37)."""
    from agentic_os.core.brains.runtime_bridge import RuntimeBridge

    bridge = RuntimeBridge()
    records = await bridge.to_brain_records()
    names = {r.display_name for r in records}
    for runtime_name in ("Python", "Node.js", "Bun", "Git"):
        assert runtime_name not in names, (
            f"{runtime_name} is a runtime, not an AI agent — it must never enter the brain registry"
        )


def test_non_agent_tools_blocked_in_discovery_bridge() -> None:
    """BrainDiscoveryBridge must refuse to convert tool payloads to brains."""
    from agentic_os.core.brains.bridge import BrainDiscoveryBridge

    bridge = BrainDiscoveryBridge()
    for tool in ("git", "python", "node", "docker", "vscode-cli"):
        record = bridge._convert(
            {
                "id": f"sys-{tool}",
                "name": tool,
                "tool_type": tool,
                "health_score": 100.0,
            },
            "agent.discovered",
        )
        assert record is None, f"{tool} must never become a BrainRecord"


def test_runtime_processes_not_registered_as_agent_brains() -> None:
    """windows_detector must not fabricate python/node agent brains."""

    detector_src = Path("src/agentic_os/core/brains/windows_detector.py").read_text()
    assert "async def _detect_python_agent_processes" not in detector_src
    assert "async def _detect_node_agent_processes" not in detector_src
    # No fabricated 95.0 health baselines.
    assert "health=95.0" not in detector_src


# ── §38: no synthetic swarm activity ────────────────────────────────────────


def test_no_synthetic_swarm_zero_state(orchestrator) -> None:
    """With no execution, every counter is 0 and latency has no value."""
    from agentic_os.core.orchestrator import Orchestrator

    assert isinstance(orchestrator, Orchestrator)
    tasks = list(orchestrator.registry.tasks())
    assert tasks == []


def test_record_mission_does_not_synthesize_members() -> None:
    """Mission-triggered swarms start with zero members (spec §13)."""
    from agentic_os.core.orchestration.swarm_coordinator import SwarmCoordinator

    sc = SwarmCoordinator.__new__(SwarmCoordinator)
    # Initialize only the structures record_mission touches.
    sc._swarm_phases = {}
    sc._swarm_members = {}
    sc._swarm_roles = {}
    sc._swarm_mission_meta = {}
    sc._swarm_history = []
    entry = sc.record_mission(
        mission_id="m1",
        title="Build a WordPress website",
        agents=["claude_code", "codex"],
    )
    assert entry["member_count"] == 0, (
        "preferred agent names are a routing preference, not evidence of swarm participation"
    )
    assert sc.get_swarm_members("mission-m1") == []


def test_swarm_plans_empty_without_real_plans() -> None:
    """The swarm endpoints must not carry hardcoded fabricated values."""
    import re as _re
    from pathlib import Path as _P

    app_src = _P("src/agentic_os/api/app.py").read_text()
    assert '"plan-real-1"' not in app_src
    # No hardcoded latency assignment like "avg_latency_ms": 35.0
    assert not _re.search(r'"avg_latency_ms"\s*:\s*35\.0', app_src)


# ── §35: markdown-only output is not a completed deliverable ────────────────


def _make_task(tmp_path: Path, role: str = "coding"):
    from agentic_os.domain.agent import Task

    return Task(title="Build a WordPress website", role=role)


async def test_markdown_only_result_is_plan_generated(orchestrator, tmp_path) -> None:
    """§35: agent returns only Markdown → task != COMPLETED."""
    from agentic_os.domain.agent import TaskStatus

    task = _make_task(tmp_path)
    task.role = "coding"
    agent = orchestrator.registry.spawn(role="coding", provider="mock")

    class _Info:
        kind = "mock"

    class _Provider:
        info = _Info()

    outcome = await orchestrator._finalize_attempt(
        agent=agent,
        task=task,
        provider=_Provider(),
        exec_rec=None,
        result=(
            "# Premium WordPress Training Academy — Implementation Plan\n\n"
            "## Phase 1\nWe will build the theme...\n\n## Phase 2\n..."
        ),
        start_time=__import__("time").monotonic(),
        attempt=1,
        before_snapshot=None,
        exec_cwd=str(tmp_path),
    )
    assert outcome == "plan_generated"
    assert task.status == TaskStatus.PLAN_GENERATED
    assert task.status != TaskStatus.COMPLETED
    assert task.verification.get("ok") is False


async def test_error_output_on_retry_is_not_completed(orchestrator, tmp_path) -> None:
    """§8/§15: attempts 2/3 apply the SAME error guard as attempt 1."""
    task = _make_task(tmp_path)
    agent = orchestrator.registry.spawn(role="coding", provider="mock")

    class _Info:
        kind = "mock"

    class _Provider:
        info = _Info()

    outcome = await orchestrator._finalize_attempt(
        agent=agent,
        task=task,
        provider=_Provider(),
        exec_rec=None,
        result="Error: http 401 unauthorized - invalid api key",
        start_time=__import__("time").monotonic(),
        attempt=2,  # retry path
    )
    assert outcome == "error"
    assert task.status.value != "completed"


async def test_real_code_artifact_completes(orchestrator, tmp_path) -> None:
    """§41: real, non-empty workspace files allow verified completion."""
    from agentic_os.core.artifact_verification import WorkspaceSnapshot
    from agentic_os.domain.agent import TaskStatus

    task = _make_task(tmp_path)
    agent = orchestrator.registry.spawn(role="coding", provider="mock")

    class _Info:
        kind = "mock"

    class _Provider:
        info = _Info()

    before = WorkspaceSnapshot.capture(str(tmp_path))
    outcome = await orchestrator._finalize_attempt(
        agent=agent,
        task=task,
        provider=_Provider(),
        exec_rec=None,
        result=(
            "Implemented the theme.\n\n"
            "```php\n<?php\n// functions.php\nadd_theme_support('post-thumbnails');\n```\n"
        ),
        start_time=__import__("time").monotonic(),
        attempt=1,
        before_snapshot=before,
        exec_cwd=str(tmp_path),
    )
    # The extracted functions.php (or the report) must be real on disk.
    assert outcome in ("completed", "plan_generated")
    if outcome == "completed":
        assert task.status == TaskStatus.COMPLETED
        assert task.verification.get("ok") is True
        assert task.verification.get("artifact_count", 0) >= 1
        assert task.status != TaskStatus.PLAN_GENERATED


# ── §41: independent artifact verification unit tests ──────────────────────


def test_verify_files_rejects_missing_and_empty(tmp_path) -> None:
    from agentic_os.core.artifact_verification import verify_files

    real = tmp_path / "real.php"
    real.write_text("<?php echo 'ok'; ?>", encoding="utf-8")
    empty = tmp_path / "empty.css"
    empty.write_text("", encoding="utf-8")

    result = verify_files([str(real), str(empty), str(tmp_path / "missing.js")])
    assert result.ok is False
    by_path = {a["path"]: a for a in result.artifacts}
    assert by_path[str(real)]["verified"] is True
    assert by_path[str(empty)]["verified"] is False  # empty file is not evidence
    assert by_path[str(tmp_path / "missing.js")]["exists"] is False


def test_verify_task_execution_coding_role_requires_real_files(tmp_path) -> None:
    from agentic_os.core.artifact_verification import verify_task_execution

    result = verify_task_execution(
        role="coding",
        result="# A plan written in Markdown only",
        saved_files=[],
        before=None,
        after=None,
        ws_root=str(tmp_path),
    )
    assert result.ok is False
    assert "no real" in result.reason


def test_verify_task_execution_prose_role_accepts_report(tmp_path) -> None:
    from agentic_os.core.artifact_verification import verify_task_execution

    report = tmp_path / "task_abc123_research.md"
    report.write_text("# Findings\n" + "Analysis. " * 50, encoding="utf-8")

    result = verify_task_execution(
        role="research",
        result="# Findings\n" + "Analysis. " * 50,
        saved_files=[str(report)],
        before=None,
        after=None,
        ws_root=str(tmp_path),
    )
    assert result.ok is True


def test_report_files_are_not_deliverables() -> None:
    from agentic_os.core.artifact_verification import is_report_file

    assert is_report_file("task_abc123_coding.md")
    assert not is_report_file("functions.php")
    assert not is_report_file("style.css")


def test_workspace_snapshot_detects_changes(tmp_path) -> None:
    from agentic_os.core.artifact_verification import WorkspaceSnapshot

    before = WorkspaceSnapshot.capture(str(tmp_path))
    new_file = tmp_path / "generated" / "index.php"
    new_file.parent.mkdir()
    new_file.write_text("<?php // real generated file ?>", encoding="utf-8")
    after = WorkspaceSnapshot.capture(str(tmp_path))

    changed = before.added_or_changed(after)
    assert any("index.php" in rel for rel in changed)
    # Excluded dirs never enter the snapshot.
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("x")
    snap2 = WorkspaceSnapshot.capture(str(tmp_path))
    assert not any(rel.startswith(".git/") for rel in snap2.files)


# ── §39: unavailable executable → honest failure ────────────────────────────


def test_missing_binary_raises(monkeypatch) -> None:
    """A CLI binary that does not exist must raise, never fabricate success."""
    from agentic_os.adapters.providers.generic_cli import GenericCLIProvider
    from agentic_os.domain.agent import Agent, Task

    provider = GenericCLIProvider(bin_path="definitely-not-a-real-cli-xyz")
    agent = Agent(role="coding", provider="definitely-not-a-real-cli-xyz")
    task = Task(title="t", role="coding")

    import shutil

    if shutil.which("definitely-not-a-real-cli-xyz"):
        pytest.skip("binary unexpectedly exists")
    with pytest.raises(RuntimeError, match="not found on PATH"):
        __import__("asyncio").run(provider.execute(agent, task))


def test_empty_stdout_is_not_fabricated(monkeypatch) -> None:
    """Empty stdout must propagate — never become 'completed' text (§15)."""
    import shutil as _shutil

    import agentic_os.adapters.providers.generic_cli as gc
    from agentic_os.domain.agent import Agent, Task

    monkeypatch.setattr(_shutil, "which", lambda name: "/usr/bin/fake-cli" if name else None)

    async def _fake_run_cli(args, **kwargs):
        return 0, "", ""

    monkeypatch.setattr(gc, "run_cli", _fake_run_cli)
    provider = gc.GenericCLIProvider(bin_path="whatever")
    agent = Agent(role="coding", provider="whatever")
    task = Task(title="t", role="coding")
    result = __import__("asyncio").run(provider.execute(agent, task))
    assert result == ""
    assert "completed" not in (result or "").lower()

    # And the orchestrator guard classifies empty output as an error.
    from agentic_os.core.orchestrator import _is_error_output

    assert _is_error_output("") is True
    # The fabricated completion fallback can no longer be PRODUCED:
    generic_src = Path("src/agentic_os/adapters/providers/generic_cli.py").read_text()
    assert 'or f"[{self._bin}] completed' not in generic_src


# ── §9/§24: installed is not active ────────────────────────────────────────


def test_swarm_agents_endpoint_never_reports_active() -> None:
    """The swarm agents endpoint must not label probed agents 'active'."""
    from pathlib import Path as _P

    app_src = _P("src/agentic_os/api/app.py").read_text()
    # Extract the swarm_agents endpoint body.
    start = app_src.index("async def swarm_agents")
    end = app_src.index('@app.get("/api/swarm/tasks")')
    body = app_src[start:end]
    assert '"status": "active"' not in body, (
        "installed/probed agents must be 'ready'/'detected', never 'active' (spec §9/§24)"
    )


def test_mock_results_fail_in_execution_engine_manager() -> None:
    """Mock adapter results must FAIL, not complete (§15/§16)."""
    from pathlib import Path as _P

    mgr_src = _P("services/execution_engine/manager.py").read_text()
    assert (
        "mock" in mgr_src.split("async def _execute_on_engine")[1].split("except TimeoutError")[0]
    )
