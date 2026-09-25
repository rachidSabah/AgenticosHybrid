"""Windows launcher regression tests for start-agenticos.bat.

The launcher is the first thing every Windows user runs, and it cannot be
exercised on POSIX CI. These tests pin the structural invariants that
previously broke in the field:

* CRLF purity — cmd.exe goto/label lookups fail on LF-only batch files.
* Control-flow integrity — every ``goto`` target has exactly one label,
  every label is reachable, no duplicates.
* Frontend dependency gate — a missing ``node_modules`` (the normal state
  of a GitHub source ZIP) must offer a real npm install and refuse
  honestly when declined, instead of starting a UI that cannot exist.
* Frontend exit sentinel — the child script writes ``frontend_exit.txt``
  when the UI process exits for ANY reason, and the wait loop checks it,
  so npm dying at second 1 fails fast with the real log instead of 60s of
  misleading "UI loading" messages.
* npm presence — dev mode requires ``npm.cmd`` on PATH and fails with an
  actionable message instead of an opaque child crash.

These are pure text-structure tests: honest and cheap, no mocks, no
Windows needed.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = REPO_ROOT / "start-agenticos.bat"


@pytest.fixture(scope="module")
def launcher_text() -> str:
    raw = LAUNCHER.read_bytes()
    # Decode as latin-1 so every byte round-trips; we only assert structure.
    text = raw.decode("latin-1")
    return text


@pytest.fixture(scope="module")
def lf_text(launcher_text: str) -> str:
    return launcher_text.replace("\r\n", "\n")


def _labels(text: str) -> list[str]:
    return re.findall(r"^:(\w+)\s*$", text, re.M)


def _gotos(text: str) -> list[str]:
    return re.findall(r"\bgoto\s+:?(\w+)", text, re.I)


# ── Batch file integrity ─────────────────────────────────────────────────────


def test_launcher_exists() -> None:
    assert LAUNCHER.is_file()


def test_launcher_is_pure_crlf(launcher_text: str) -> None:
    """cmd.exe is unreliable with LF-only batch files (goto/label lookups
    can fail at 512-byte buffer boundaries). The committed bytes must be
    CRLF everywhere - .gitattributes marks *.bat -text, so what is here is
    what ships in every checkout and every GitHub source ZIP."""
    assert "\r\n" in launcher_text
    lone_lf = launcher_text.replace("\r\n", "").count("\n")
    assert lone_lf == 0, f"{lone_lf} lone LF line ending(s) found"


def test_every_goto_target_has_label(lf_text: str) -> None:
    labels = _labels(lf_text)
    dangling = sorted(set(_gotos(lf_text)) - set(labels))
    assert dangling == [], f"goto targets without labels: {dangling}"


def test_no_duplicate_labels(lf_text: str) -> None:
    labels = _labels(lf_text)
    dups = sorted({name for name in labels if labels.count(name) > 1})
    assert dups == [], f"duplicate labels: {dups}"


def test_no_unreachable_labels(lf_text: str) -> None:
    """Every label must be referenced by at least one goto - a label nothing
    jumps to is dead code that silently rots."""
    labels = _labels(lf_text)
    orphans = sorted(set(labels) - set(_gotos(lf_text)))
    assert orphans == [], f"labels never jumped to: {orphans}"


def test_echo_lines_have_no_unescaped_cmd_metacharacters(lf_text: str) -> None:
    """A bare ``&`` or ``|`` inside an echo message would execute/pipe
    instead of printing (classic launcher self-destruct). Caret-escaped
    forms (^& ^|) are fine."""
    bad: list[str] = []
    for line in lf_text.splitlines():
        stripped = line.strip()
        if not stripped.lower().startswith("echo"):
            continue
        # Remove caret-escaped metacharacters before scanning.
        unescaped = re.sub(r"\^.", "", stripped)
        if re.search(r"[&|]", unescaped):
            bad.append(stripped)
    assert bad == [], f"echo lines with unescaped & or |: {bad}"


# ── Frontend dependency gate ─────────────────────────────────────────────────


def test_missing_node_modules_offers_real_install(lf_text: str) -> None:
    """The gate must mirror the backend: explain the ZIP situation, offer a
    choice, run npm install, and verify node_modules afterwards."""
    assert "apps\\mission-control\\node_modules is missing" in lf_text
    assert 'choice /C YN /M "[AgenticOS] Install frontend dependencies now"' in lf_text
    assert "call npm.cmd install" in lf_text
    gate = lf_text.split(":start_frontend", 1)[1].split(":fe_modules_ok", 1)[0]
    assert "if not exist" in gate and "node_modules" in gate, (
        "gate must verify node_modules exists after npm install"
    )


def test_declined_install_exits_instead_of_doomed_start(lf_text: str) -> None:
    """Answering N must stop the launcher - falling through would start a
    UI that cannot come up and hang on 'UI loading' messages again."""
    block = lf_text.split(":fe_deps_refused", 1)[1].split(":npm_missing", 1)[0]
    assert "exit /b 1" in block


def test_failed_install_exits_instead_of_doomed_start(lf_text: str) -> None:
    block = lf_text.split(":fe_install_failed", 1)[1].split(":fe_modules_ok", 1)[0]
    assert "exit /b 1" in block


def test_npm_missing_gives_actionable_message(lf_text: str) -> None:
    """npm absent must name the fix (Node.js install) - and the message
    must not contain cmd metacharacters that would break the echo."""
    block = lf_text.split(":npm_missing", 1)[1].split(":fe_install_failed", 1)[0]
    assert "nodejs.org" in block
    assert "exit /b 1" in block


def test_dev_mode_fails_fast_without_npm(lf_text: str) -> None:
    """Dev mode with stale node_modules but no Node.js installed used to
    die inside the invisible child; now the launcher checks npm.cmd first."""
    dev_block = lf_text.split(":fe_dev", 1)[1].split(":fe_start", 1)[0]
    assert "where npm.cmd" in dev_block
    assert "goto npm_missing" in dev_block


# ── Frontend exit sentinel (fail fast, honest) ───────────────────────────────


def test_child_writes_exit_sentinel(lf_text: str) -> None:
    """The generated child script must capture the FE command's exit code -
    exactly like the backend child writes backend_exit.txt."""
    assert 'echo echo %%errorlevel%% ^> "%ROOT%\\logs\\frontend_exit.txt"' in lf_text


def test_sentinel_is_written_for_both_frontend_modes(lf_text: str) -> None:
    """The sentinel echo follows the single FE_CMD echo line, so it applies
    to dev mode (npm) AND static mode (node serve) alike."""
    child_block = lf_text.split('set "FCHILD=', 1)[1].split(
        "rem -- Health-check tool availability", 1
    )[0]
    lines = [line for line in child_block.splitlines() if line.strip()]
    fe_cmd_lines = [i for i, line in enumerate(lines) if "%FE_CMD%" in line]
    sentinel_lines = [i for i, line in enumerate(lines) if "frontend_exit.txt" in line]
    assert len(fe_cmd_lines) == 1
    assert len(sentinel_lines) == 1
    assert sentinel_lines[0] == fe_cmd_lines[0] + 1, (
        "exit sentinel must immediately follow the FE command"
    )


def test_dev_mode_child_uses_call_for_npm(lf_text: str) -> None:
    """cmd.exe CHAINS to a .cmd invoked without ``call`` - control never
    returns, so the sentinel line would never execute. This exact bug made
    the sentinel dead code."""
    assert 'set "FE_CMD=call npm.cmd run dev' in lf_text
    # Static mode runs node.exe (a real binary) - no call prefix wanted.
    assert 'set "FE_CMD=node node_modules\\serve\\build\\main.js' in lf_text


def test_wait_loop_checks_sentinel_before_timeout(lf_text: str) -> None:
    """The wait loop must consult frontend_exit.txt every iteration, and the
    check must sit between the probe and the 60s timeout branch."""
    loop = lf_text.split(":wait_frontend", 1)[1].split(":frontend_ready", 1)[0]
    assert "frontend_exit.txt" in loop
    sentinel_idx = loop.index("if exist")
    timeout_idx = loop.index("GEQ 60")
    assert sentinel_idx < timeout_idx


def test_frontend_died_handler_dumps_real_log(lf_text: str) -> None:
    """Failure path must show the actual frontend.log tail (like the
    backend handler) - never a generic message without evidence."""
    block = lf_text.split(":frontend_died", 1)[1].split(":frontend_timeout", 1)[0]
    assert "frontend.log" in block
    assert "Get-Content" in block
    assert "exit /b 1" in block


def test_stale_sentinel_cleared_before_each_start(lf_text: str) -> None:
    """A leftover frontend_exit.txt from a previous run must be deleted
    before starting the UI, or the wait loop would instantly report a
    death that never happened."""
    start_block = lf_text.split(":fe_start", 1)[1].split('start "AgenticOS Frontend"', 1)[0]
    assert "del" in start_block and "frontend_exit.txt" in start_block
