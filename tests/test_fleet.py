"""Cross-CLI Agent Fleet — real adapters, real bidding, real dispatch.

No mocks for execution: dispatch tests spawn REAL subprocesses (temp python
scripts) and assert on measured exit codes, stdout, and durations. Bidding
ranks using only persisted run history.
"""

from __future__ import annotations

import asyncio
import sys
import textwrap
from pathlib import Path

import pytest

from agentic_os.core.brains.schema import DiscoveredAgent
from agentic_os.core.fleet.driver import CLI_ADAPTERS, FleetError, FleetManager


def _script(tmp_path: Path, body: str) -> str:
    """Create a real executable python script; return its path."""
    p = tmp_path / f"agent_{abs(hash(body)) % 10**8}.py"
    p.write_text("#!/usr/bin/env python3\n" + textwrap.dedent(body), encoding="utf-8")
    p.chmod(0o755)
    return str(p)


def _agent(agent_id: str, name: str, exe: str, kind: str = "agentic-cli") -> DiscoveredAgent:
    a = DiscoveredAgent(id=agent_id, name=name)
    a.executable_path = exe
    a.status = "healthy"
    a.kind = kind
    return a


# Runtime entries discovered alongside agent CLIs (vcs kind -> is_agent False).
def _runtime(agent_id: str, name: str, exe: str) -> DiscoveredAgent:
    return _agent(agent_id, name, exe, kind="vcs")


@pytest.fixture
def fleet(tmp_path: Path):
    return FleetManager(data_dir=str(tmp_path / "fleet"))


# ── fleet listing & adapters ─────────────────────────────────────────────────


def test_known_cli_gets_documented_adapter(fleet, tmp_path: Path):
    fake = _script(tmp_path, "print('x')\n")
    fleet._discovery_getter = lambda: [_agent("agent:claude", "claude", fake)]
    rows = fleet.fleet()
    assert len(rows) == 1
    assert rows[0]["adapter"] == "claude"
    assert rows[0]["adapter_note"] == CLI_ADAPTERS["claude"]["note"]


def test_unknown_agent_is_generic_and_probe_only_for_runtime(fleet, tmp_path: Path):
    fake = _script(tmp_path, "print('x')\n")
    fleet._discovery_getter = lambda: [
        _agent("agent:mycli", "mycli", fake),
        _runtime("agent:git", "git", fake),
    ]
    rows = {r["name"]: r for r in fleet.fleet()}
    assert rows["mycli"]["adapter"] == "generic"
    assert "args prefix" in rows["mycli"]["adapter_note"]
    assert rows["git"]["adapter"] == "none"  # git is not an agent (is_agent False)


def test_capabilities_replace_roundtrip(fleet, tmp_path: Path):
    fake = _script(tmp_path, "print('x')\n")
    fleet._discovery_getter = lambda: [_agent("agent:mycli", "mycli", fake)]
    fleet.set_capabilities("agent:mycli", ["coding", " Testing "])
    # set_capabilities REPLACES the operator set (last write wins) so an
    # operator can also remove a capability; discovery-declared caps are
    # merged separately inside fleet().
    fleet.set_capabilities("agent:mycli", ["coding", "review"])
    rows = fleet.fleet()
    assert rows[0]["declared_capabilities"] == ["coding", "review"]


def test_is_active_requires_agent_kind_and_status(fleet, tmp_path: Path):
    fake = _script(tmp_path, "print('x')\n")
    git = _runtime("agent:git", "git", fake)
    fleet._discovery_getter = lambda: [git]
    rows = fleet.fleet()
    assert rows[0]["is_active"] is False  # runtime, not agent


# ── dispatch: real subprocess ────────────────────────────────────────────────


async def test_dispatch_runs_real_process_and_captures_stdout(fleet, tmp_path: Path):
    exe = _script(
        tmp_path,
        """
        import sys
        print("hello-from-real-subprocess")
        sys.exit(0)
        """,
    )
    fleet._discovery_getter = lambda: [_agent("agent:mycli", "mycli", exe)]
    fleet.set_args_prefix("agent:mycli", [])
    res = await fleet.dispatch("agent:mycli", "do a thing")
    assert res["status"] == "completed"
    assert res["exit_code"] == 0
    assert "hello-from-real-subprocess" in res["stdout_preview"]
    assert res["duration_ms"] >= 0
    # Measured history persisted exactly once.
    assert len(fleet.runs(agent_id="agent:mycli")) == 1


async def test_dispatch_prompt_is_final_arg_without_marker(fleet, tmp_path: Path):
    exe = _script(
        tmp_path,
        """
        import sys
        print("ARGS:", sys.argv[1:])
        sys.exit(0)
        """,
    )
    fleet._discovery_getter = lambda: [_agent("agent:mycli", "mycli", exe)]
    fleet.set_args_prefix("agent:mycli", ["--task"])
    res = await fleet.dispatch("agent:mycli", "PROMPT-TEXT")
    assert "PROMPT-TEXT" in res["stdout_preview"]
    assert "--task" in res["stdout_preview"]


async def test_dispatch_adapter_template_substitution(fleet, tmp_path: Path):
    # A binary named like a known CLI but pointing at our instrumented script:
    # the adapter template args are passed verbatim after the executable.
    exe = _script(
        tmp_path,
        """
        import sys
        print("ARGS:", sys.argv[1:])
        sys.exit(0)
        """,
    )
    fleet._discovery_getter = lambda: [_agent("agent:claude", "claude", exe)]
    res = await fleet.dispatch("agent:claude", "say hi")
    assert res["status"] == "completed"
    # claude template: ["claude", "-p", "{prompt}"] -> exe -p "say hi"
    assert "-p" in res["stdout_preview"]
    assert "say hi" in res["stdout_preview"]


async def test_dispatch_failure_reports_real_stderr_and_exit(fleet, tmp_path: Path):
    exe = _script(
        tmp_path,
        """
        import sys
        print("boom-reason", file=sys.stderr)
        sys.exit(3)
        """,
    )
    fleet._discovery_getter = lambda: [_agent("agent:mycli", "mycli", exe)]
    fleet.set_args_prefix("agent:mycli", [])
    res = await fleet.dispatch("agent:mycli", "x")
    assert res["status"] == "failed"
    assert res["exit_code"] == 3
    assert "boom-reason" in res["stderr_preview"]


async def test_dispatch_timeout_kills_and_reports(fleet, tmp_path: Path):
    exe = _script(
        tmp_path,
        """
        import time
        time.sleep(30)
        """,
    )
    fleet._discovery_getter = lambda: [_agent("agent:mycli", "mycli", exe)]
    fleet.set_args_prefix("agent:mycli", [])
    res = await fleet.dispatch("agent:mycli", "x", timeout_s=1)
    assert res["status"] == "timeout"
    assert "killed" in res["error"]


async def test_dispatch_unknown_agent_404_class(fleet):
    with pytest.raises(FleetError) as exc:
        await fleet.dispatch("agent:ghost", "x")
    assert "not in the current discovery snapshot" in str(exc.value)


async def test_dispatch_generic_without_args_prefix_refused(fleet, tmp_path: Path):
    exe = _script(tmp_path, "print('x')\n")
    fleet._discovery_getter = lambda: [_agent("agent:mycli", "mycli", exe)]
    with pytest.raises(FleetError) as exc:
        await fleet.dispatch("agent:mycli", "x")
    assert "will not guess" in str(exc.value)


async def test_dispatch_runtime_entry_refused(fleet, tmp_path: Path):
    exe = _script(tmp_path, "print('x')\n")
    fleet._discovery_getter = lambda: [_runtime("agent:git", "git", exe)]
    with pytest.raises(FleetError) as exc:
        await fleet.dispatch("agent:git", "x")
    assert "dispatch refused" in str(exc.value)


# ── bidding: measured history only ───────────────────────────────────────────


async def _seed_history(fleet: FleetManager, agent_id: str, outcomes: list[str]) -> None:
    from agentic_os.core.fleet.driver import FleetRunRecord

    for status in outcomes:
        rec = FleetRunRecord(agent_id=agent_id, status=status, duration_ms=100)
        fleet._append_run(rec)


async def test_bid_ranks_by_measured_success_then_speed(fleet, tmp_path: Path):
    slow_ok = _script(tmp_path, "print('a')\n")
    fast_ok = _script(tmp_path, "print('b')\n")
    flaky = _script(tmp_path, "print('c')\n")
    fleet._discovery_getter = lambda: [
        _agent("agent:mycli-a", "mycli-a", slow_ok),
        _agent("agent:mycli-b", "mycli-b", fast_ok),
        _agent("agent:mycli-c", "mycli-c", flaky),
    ]
    for r in ("mycli-a", "mycli-b", "mycli-c"):
        fleet.set_args_prefix(f"agent:{r}", [])
        fleet.set_capabilities(f"agent:{r}", ["coding"])
    # mycli-a: 100% success but slow; mycli-b: 100% success and fast;
    # mycli-c: 50% success.
    await _seed_history(fleet, "agent:mycli-a", ["completed", "completed"])
    await _seed_history(fleet, "agent:mycli-b", ["completed", "completed"])
    await _seed_history(fleet, "agent:mycli-c", ["completed", "failed"])
    # Fix measured durations: b is fastest.
    runs = fleet._runs(limit=1000)
    for r in runs:
        r["duration_ms"] = 500 if r["agent_id"] == "agent:mycli-a" else 50
    fleet._runs_path.write_text(
        "\n".join(__import__("json").dumps(r) for r in runs) + "\n", encoding="utf-8"
    )

    result = fleet.bid("refactor module", ["coding"], top=3)
    assert result["eligible_count"] == 3
    names = [row["name"] for row in result["ranking"]]
    assert names[0] == "mycli-b"  # same success rate, fastest
    assert names[2] == "mycli-c"  # lower success rate ranks last
    row = result["ranking"][0]
    assert row["stats"]["success_rate"] == 1.0
    assert row["stats"]["avg_duration_ms"] == 50


async def test_bid_filters_missing_capabilities(fleet, tmp_path: Path):
    exe = _script(tmp_path, "print('x')\n")
    fleet._discovery_getter = lambda: [_agent("agent:mycli", "mycli", exe)]
    fleet.set_args_prefix("agent:mycli", [])
    fleet.set_capabilities("agent:mycli", ["coding"])
    result = fleet.bid("translate docs", ["translation"], top=5)
    assert result["eligible_count"] == 0
    assert result["ranking"] == []


async def test_bid_excludes_runtimes_and_adapterless(fleet, tmp_path: Path):
    exe = _script(tmp_path, "print('x')\n")
    fleet._discovery_getter = lambda: [_runtime("agent:git", "git", exe)]
    result = fleet.bid("anything", [], top=5)
    assert result["eligible_count"] == 0


async def test_bid_no_history_ranks_last_but_eligible(fleet, tmp_path: Path):
    exe = _script(tmp_path, "print('x')\n")
    fleet._discovery_getter = lambda: [_agent("agent:mycli", "mycli", exe)]
    fleet.set_args_prefix("agent:mycli", [])
    fleet.set_capabilities("agent:mycli", ["coding"])
    result = fleet.bid("task", ["coding"], top=5)
    assert result["eligible_count"] == 1
    assert result["ranking"][0]["stats"]["success_rate"] is None


# ── store persistence ────────────────────────────────────────────────────────


def test_store_persists_across_instances(tmp_path: Path):
    m1 = FleetManager(data_dir=str(tmp_path / "f"))
    m1.set_capabilities("agent:x", ["coding"])
    m1.set_args_prefix("agent:x", ["--y"])
    m2 = FleetManager(data_dir=str(tmp_path / "f"))
    assert m2.fleet.__self__._load_store()["capabilities"]["agent:x"] == ["coding"]
    assert m2._load_store()["args_prefix"]["agent:x"] == ["--y"]


def test_fleet_event_loop_safe_concurrent_dispatch(tmp_path: Path):
    """Two concurrent dispatches both complete (no shared-state corruption)."""
    exe = _script(
        tmp_path,
        """
        import sys
        print("ok")
        sys.exit(0)
        """,
    )

    async def scenario():
        fleet = FleetManager(data_dir=str(tmp_path / "cc"))
        fleet._discovery_getter = lambda: [_agent("agent:mycli", "mycli", exe)]
        fleet.set_args_prefix("agent:mycli", [])
        results = await asyncio.gather(
            fleet.dispatch("agent:mycli", "one"),
            fleet.dispatch("agent:mycli", "two"),
        )
        return results

    results = asyncio.run(scenario())
    assert all(r["status"] == "completed" for r in results)


# ── Windows shebang honoring ─────────────────────────────────────────────────


def test_windows_shebang_resolution(monkeypatch, tmp_path):
    """On Windows a python script is driven under the running interpreter."""
    import agentic_os.core.fleet.driver as driver

    script = tmp_path / "cli.py"
    script.write_text("#!/usr/bin/env python3\nprint('x')\n", encoding="utf-8")
    monkeypatch.setattr(driver.sys, "platform", "win32")
    argv = driver._argv_with_shebang([str(script), "--flag", "prompt"])
    assert argv[0] == driver.sys.executable
    assert argv[1:] == [str(script), "--flag", "prompt"]


def test_windows_non_script_passthrough(monkeypatch, tmp_path):
    """A native executable passes through unchanged (CreateProcess handles it)."""
    import agentic_os.core.fleet.driver as driver

    exe = tmp_path / "tool.exe"
    exe.write_bytes(b"MZ\x90\x00")
    monkeypatch.setattr(driver.sys, "platform", "win32")
    argv = driver._argv_with_shebang([str(exe), "x"])
    assert argv == [str(exe), "x"]


def test_posix_shebang_untouched(tmp_path):
    """On POSIX the kernel honors shebangs; argv passes through untouched."""
    import agentic_os.core.fleet.driver as driver

    script = tmp_path / "cli.py"
    script.write_text("#!/usr/bin/env python3\nprint('x')\n", encoding="utf-8")
    argv = driver._argv_with_shebang([str(script), "prompt"])
    assert argv == [str(script), "prompt"]
