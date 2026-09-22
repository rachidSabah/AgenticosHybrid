"""Dynamic detection of agentic CLI agents.

Why this exists
---------------
Brain detection previously came from a hardcoded ``KNOWN_RUNTIMES`` list in
``windows_detector``. That produced two visible bugs:

* **Retired tools still appeared.** ``gemini`` is installed on PATH but fails
  to run (invalid settings.json), yet it was listed as a healthy brain in AI
  Agent Binding, AI Brain and Agent Constellation.
* **New tools never appeared.** Antigravity (``agy``) replaced Gemini CLI but
  had no entry in the static list, so it was invisible even though it was
  installed and bound as a provider.

Detection is now dynamic: enumerate PATH, keep agentic-looking binaries, and
PROBE each one. A binary that is present but broken is reported as absent.
Nothing is ever emitted from a static list.

Heuristic note: "agentic" is inferred from a keyword set plus a version probe,
not asserted. An unknown binary that responds to ``--version`` and matches an
agent keyword is reported generically rather than dropped.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import shutil
from pathlib import Path
from typing import Any

from agentic_os.infrastructure.logging import get_logger

log = get_logger("brains.dynamic_detect")

AGENTIC_PROBE_TIMEOUT = 8.0

# Cap on how many unknown PATH binaries get probed. A large PATH (Windows
# often has thousands of entries) would otherwise make detection take minutes.
_MAX_SWEEP_PROBES = 40

# Exact binary names of known agentic CLIs. Checked first (fast path): these
# are real agents, so they are probed directly without substring guessing.
_KNOWN_AGENT_BINARIES = (
    "codex",
    "claude",
    "hermes",
    "gemini",
    "agy",
    "antigravity",
    "opencode",
    "aider",
    "continue",
    "qwen",
    "copilot",
    "cursor",
    "windsurf",
    "cline",
    "roo",
    "kilo",
    "crush",
    "amp",
)# Substrings that mark a binary as a plausible agentic CLI. Used only to
# filter the PATH scan; a positive match still must pass a live probe.
_AGENT_KEYWORDS = (
    "codex",
    "claude",
    "hermes",
    "gemini",
    "agy",
    "antigravity",
    "opencode",
    "aider",
    "continue",
    "copilot",
    "cursor",
    "windsurf",
    "cline",
    "roo",
    "kilo",
    "qwen",
)

# Substrings marking OS/desktop noise that merely contains "agent".
# Without these, ssh-agent / gpg-agent / waasmedicagent pollute results.
_KEYWORD_EXCLUDE_SUBSTRINGS = (
    "ssh-agent",
    "gpg-agent",
    "gpg-connect-agent",
    "medicagent",
    "agentpolicy",
    "agent-skills",
    "agent-mcp",
    "npm",
    "host",
    "runner",
    "policygenerator",
    "chroot",
)

# Binaries that are runtimes/tooling, never agents. Keeps git/node/python out.
_EXCLUDE_EXACT = {
    "git",
    "node",
    "npm",
    "npx",
    "python",
    "python3",
    "pip",
    "uv",
    "bun",
    "deno",
    "docker",
    "ls",
    "cat",
    "code",
    "agenticos-kernel",
}

# Nice display names for tools we know about. Unknown tools fall through to a
# title-cased generic label — they are still reported.
_DISPLAY_NAMES = {
    "codex": "Codex CLI",
    "claude": "Claude Code",
    "hermes": "Hermes Agent",
    "gemini": "Gemini CLI",
    "agy": "Antigravity CLI",
    "antigravity": "Antigravity CLI",
    "opencode": "OpenCode",
    "aider": "Aider",
    "continue": "Continue",
    "qwen": "Qwen CLI",
    "github-copilot": "GitHub Copilot CLI",
    "cursor": "Cursor CLI",
}

_VENDORS = {
    "codex": "codex",
    "claude": "claude_code",
    "hermes": "hermes",
    "gemini": "google",
    "agy": "antigravity",
    "antigravity": "antigravity",
    "opencode": "opencode",
    "aider": "aider",
    "continue": "continue",
    "qwen": "qwen",
}


def is_agentic_candidate(name: str) -> bool:
    """True when the binary name plausibly denotes an agentic CLI."""
    lowered = name.lower()
    if lowered in _EXCLUDE_EXACT:
        return False
    # Known agent binaries are always candidates — no substring guessing.
    if lowered in _KNOWN_AGENT_BINARIES:
        return True
    # Reject OS/desktop noise whose name merely contains "agent".
    if any(bad in lowered for bad in _KEYWORD_EXCLUDE_SUBSTRINGS):
        return False
    return any(kw in lowered for kw in _AGENT_KEYWORDS)


def classify_binary(name: str) -> tuple[str, str]:
    """Return (display_name, vendor) for a binary name."""
    lowered = name.lower()
    display = _DISPLAY_NAMES.get(lowered) or lowered.replace("-", " ").replace("_", " ").title()
    vendor = _VENDORS.get(lowered, "custom")
    return display, vendor


def _iter_path_binaries() -> Any:
    """Yield unique binary basenames found on PATH (Windows-aware)."""
    seen: set[str] = set()
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        if not directory:
            continue
        try:
            entries = os.listdir(directory)
        except OSError:
            continue
        for entry in entries:
            base = Path(entry).stem.lower()
            if not base or base in seen:
                continue
            if os.name == "nt":
                if not entry.lower().endswith((".exe", ".cmd", ".bat", ".ps1")):
                    continue
            seen.add(base)
            yield base


async def _run_probe(cmd: list[str], timeout: float) -> Any:
    """Run a probe command, returning a completed-process-like object."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except (OSError, ValueError):
        return type("R", (), {"returncode": 127, "stdout": b"", "stderr": b"spawn failed"})()
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        with contextlib.suppress(Exception):
            proc.kill()
        return type("R", (), {"returncode": 124, "stdout": b"", "stderr": b"timeout"})()
    return type(
        "R",
        (),
        {
            "returncode": proc.returncode or 0,
            "stdout": out or b"",
            "stderr": err or b"",
        },
    )()


def _decode(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value or "")


# Output that means "this CLI is installed but cannot actually run".
# Observed with Gemini CLI: `--version` exits 0, but any real invocation
# fails on a broken settings.json. Presence is not usability.
_BROKEN_SIGNATURES = (
    "invalid configuration",
    "expected object, received array",
    "error in:",
    "authentication required",
    "not authenticated",
    "no api key",
    "missing api key",
)


async def _is_functional(resolved: str, timeout: float) -> bool:
    """Best-effort check that the CLI can actually run, not just print a version.

    Tries a harmless non-interactive invocation. A CLI that prints a
    configuration/auth error is unusable even though --version succeeded.
    """
    for args in (["--help"], ["-h"], ["help"]):
        try:
            result = await _run_probe([resolved, *args], timeout=timeout)
        except Exception:
            continue
        combined = (_decode(result.stdout) + _decode(result.stderr)).lower()
        if any(sig in combined for sig in _BROKEN_SIGNATURES):
            return False
        if result.returncode == 0:
            return True
    # No probe produced a clean run, but if the version probe succeeded we
    # cannot prove it is broken — accept it rather than guess.
    return True


async def probe_binary(name: str, timeout: float = AGENTIC_PROBE_TIMEOUT) -> tuple[bool, str]:
    """Probe a binary; return (works, version_string).

    A binary that cannot be resolved or errors on ``--version`` is reported as
    not working. Presence on PATH alone is NOT evidence of a healthy agent.
    """
    resolved = shutil.which(name)
    if not resolved:
        return False, ""

    for args in (["--version"], ["-v"], ["version"]):
        try:
            result = await _run_probe([resolved, *args], timeout=timeout)
        except Exception:
            continue
        if result.returncode == 0:
            raw = _decode(result.stdout)
            version = raw.strip().splitlines()[0] if raw.strip() else ""
            # Installed is not the same as usable: confirm the CLI can run.
            if not await _is_functional(resolved, timeout=timeout):
                log.info("dynamic_detect.unusable_cli", binary=name, version=version)
                return False, ""
            return True, version
    return False, ""


async def scan_path_for_agents(timeout: float = AGENTIC_PROBE_TIMEOUT) -> list[dict[str, Any]]:
    """Scan PATH and return every agentic CLI that actually responds.

    Known agent binaries are probed first so results are fast and reliable;
    the broader PATH sweep is capped so a machine with thousands of entries
    cannot stall startup.

    Returns dicts with keys: key, name, exe, vendor, version, path.
    Empty when nothing real is installed — never padded with guesses.
    """
    found: list[dict[str, Any]] = []
    seen: set[str] = set()

    async def _consider(base: str) -> None:
        if base in seen or not is_agentic_candidate(base):
            return
        seen.add(base)
        works, version = await probe_binary(base, timeout=timeout)
        if not works:
            log.debug("dynamic_detect.skip_unusable", binary=base)
            return
        display, vendor = classify_binary(base)
        found.append(
            {
                "key": base,
                "name": display,
                "exe": base,
                "vendor": vendor,
                "version": version,
                "path": shutil.which(base) or "",
            }
        )

    # Fast path: known agent binaries, probed in parallel.
    await asyncio.gather(*(_consider(b) for b in _KNOWN_AGENT_BINARIES))

    # Discovery path: any other agentic-looking binary on PATH, capped so a
    # very large PATH cannot stall the scan.
    swept = 0
    for base in _iter_path_binaries():
        if swept >= _MAX_SWEEP_PROBES:
            break
        if base in seen:
            continue
        seen.add(base)
        swept += 1
        await _consider(base)

    return found
