"""Real probe sequence for agent candidates (spec §5, §6, §7, §19).

Lifecycle: DISCOVERED -> version -> identity -> capability -> health -> BIND.

Rules enforced here:
* No version detected => ``version = None`` (rendered UNKNOWN), never "v1.0.0".
* Capabilities come from help-text evidence or are absent. Never assumed.
* Health is None until a real probe produces a number.
* A binary that is present but errors is UNAVAILABLE/FAILED, never HEALTHY.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import re
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

from agentic_os.core.brains.schema import (
    KIND_AI_AGENT_CLI,
    KIND_AI_RUNTIME,
    KIND_DEV_RUNTIME,
    KIND_PACKAGE_MANAGER,
    KIND_SYSTEM_UTILITY,
    KIND_UNKNOWN,
    KIND_VCS,
    STATUS_DEGRADED,
    STATUS_DISCOVERED,
    STATUS_FAILED,
    STATUS_HEALTHY,
    STATUS_NOT_FOUND,
    STATUS_UNAVAILABLE,
    Capability,
    DiscoveredAgent,
    ProbeResult,
)

PROBE_TIMEOUT = 5.0

# Evidence that a CLI is installed but cannot actually run (§5).
# Observed: `gemini --version` exits 0 while any real run fails on bad config.
_BROKEN_OUTPUT_SIGNATURES = (
    "invalid configuration",
    "expected object, received array",
    "error in:",
    "authentication required",
    "not authenticated",
    "no api key",
    "missing api key",
)

# ── Identity evidence (spec §4) ─────────────────────────────────────────────
# Words that, found in --help output, evidence this is an AI agent.
_AGENT_IDENTITY_EVIDENCE = (
    "agent",
    "assistant",
    "llm",
    "model",
    "prompt",
    "chat",
    "copilot",
    "code generation",
    "autonomous",
    "ai ",
)

# Capability keyword -> canonical capability name (evidence-based, §7).
_CAPABILITY_EVIDENCE = {
    "chat": "chat",
    "conversation": "chat",
    "code generation": "code_generation",
    "generate code": "code_generation",
    "write code": "code_generation",
    "edit file": "file_editing",
    "file editing": "file_editing",
    "read file": "file_operations",
    "file operations": "file_operations",
    "shell": "terminal_operations",
    "terminal": "terminal_operations",
    "command execution": "terminal_operations",
    "tool": "tool_use",
    "mcp": "mcp",
    "model context protocol": "mcp",
    "multi-agent": "multi_agent",
    "swarm": "multi_agent",
    "planning": "planning",
    "reasoning": "reasoning",
    "test": "testing",
    "browser": "browser",
    "computer use": "computer_use",
    "image generation": "image_generation",
}

# Known non-agent tooling. Classified explicitly so git/node/python are never
# presented as AI agents (§4). Used ONLY for classification, never to invent.
_KNOWN_NON_AGENT = {
    "git": KIND_VCS,
    "node": KIND_DEV_RUNTIME,
    "nodejs": KIND_DEV_RUNTIME,
    "python": KIND_DEV_RUNTIME,
    "python3": KIND_DEV_RUNTIME,
    "npm": KIND_PACKAGE_MANAGER,
    "pnpm": KIND_PACKAGE_MANAGER,
    "yarn": KIND_PACKAGE_MANAGER,
    "uv": KIND_PACKAGE_MANAGER,
    "pip": KIND_PACKAGE_MANAGER,
    "cargo": KIND_DEV_RUNTIME,
    "deno": KIND_DEV_RUNTIME,
    "bun": KIND_DEV_RUNTIME,
    "docker": KIND_SYSTEM_UTILITY,
}


async def _run(cmd: list[str], timeout: float) -> tuple[int, str, str]:
    """Run a command; return (returncode, stdout, stderr)."""
    if not cmd or not cmd[0]:
        return 127, "", "empty command"
    exe = cmd[0]
    if os.path.exists(exe) and os.path.isdir(exe):
        return 127, "", "path is a directory, not executable"
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            # Critical: CLIs that read stdin hang forever otherwise, burning
            # the full timeout each (observed as exit 124). DEVNULL makes the
            # probe terminate immediately on such binaries.
            stdin=asyncio.subprocess.DEVNULL,
            creationflags=creationflags,
        )
    except (OSError, ValueError):
        return 127, "", "spawn failed"
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        with contextlib.suppress(Exception):
            if os.name == "nt" and proc.pid:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                proc.kill()
        return 124, "", "timeout"
    decode = lambda b: (b or b"").decode("utf-8", errors="replace")  # noqa: E731
    return proc.returncode or 0, decode(out), decode(err)


async def probe_version(path: str) -> ProbeResult:
    """Real version probe (§6). Unknown => ok=False, never fabricated."""
    for args in (["--version"], ["-v"], ["version"]):
        rc, out, err = await _run([path, *args], PROBE_TIMEOUT)
        text = (out or err).strip()
        if rc == 0 and text:
            return ProbeResult("version", True, text.splitlines()[0].strip(), args[0])
    return ProbeResult("version", False, "no version output", "")


def _looks_broken(text: str) -> bool:
    lowered = text.lower()
    return any(sig in lowered for sig in _BROKEN_OUTPUT_SIGNATURES)


async def probe_identity(path: str) -> tuple[ProbeResult, str]:
    """Identity probe (§4). Evidence from help text, not the filename."""
    for args in (["--help"], ["-h"], ["help"]):
        rc, out, err = await _run([path, *args], PROBE_TIMEOUT)
        text = f"{out}\n{err}"
        if _looks_broken(text):
            return ProbeResult("identity", False, "broken configuration", args[0]), ""
        if rc == 0 and text.strip():
            return ProbeResult("identity", True, "help output", args[0]), text
    return ProbeResult("identity", False, "no help output", ""), ""


def classify(name: str, help_text: str) -> str:
    """Classify by evidence (§4). Never promote runtimes to agents."""
    lowered = name.lower()
    known = _KNOWN_NON_AGENT.get(lowered)
    if known:
        return known
    haystack = (help_text or "").lower()
    hits = sum(1 for e in _AGENT_IDENTITY_EVIDENCE if e in haystack)
    if hits >= 2:
        return KIND_AI_AGENT_CLI
    if hits == 1:
        return KIND_AI_RUNTIME
    return KIND_UNKNOWN


def derive_capabilities(help_text: str) -> list[Capability]:
    """Capabilities from real help-text evidence (§7)."""
    if not help_text:
        return []
    haystack = help_text.lower()
    found: list[Capability] = []
    for needle, cap in _CAPABILITY_EVIDENCE.items():
        if needle in haystack and cap not in [c.capability for c in found]:
            found.append(Capability(capability=cap, source="help_text", confidence="inferred"))
    return found


async def probe_health(path: str) -> ProbeResult:
    """Health probe (§5). A real invocation; failure is reported honestly."""
    rc, out, err = await _run([path, "--help"], PROBE_TIMEOUT)
    text = f"{out}\n{err}"
    if _looks_broken(text):
        return ProbeResult("health", False, "unusable: configuration error", "")
    if rc == 0:
        return ProbeResult("health", True, "responsive", "")
    return ProbeResult("health", False, f"exit {rc}", "")


# ── Loop-agnostic execution ─────────────────────────────────────────────────
# The AgenticOS backend runs on WindowsSelectorEventLoop, where
# asyncio.create_subprocess_exec raises NotImplementedError — subprocesses are
# only supported by ProactorEventLoop. Probing therefore runs in a dedicated
# worker thread owning a Proactor loop, so discovery works under ANY event
# loop policy the host app chooses. This is why 47/48 candidates silently
# failed when called from the API but succeeded standalone.
_PROBE_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="agent-probe")


def _run_probe_loop(coro_fn):
    """Run a probe coroutine on a thread with a subprocess-capable loop.

    The loop is built directly from a policy object rather than by calling
    ``asyncio.set_event_loop_policy``: that call is process-global (it would
    mutate the host application's loop policy as a side effect) and is
    deprecated in Python 3.14.
    """
    loop = _probe_policy().new_event_loop()
    try:
        return loop.run_until_complete(coro_fn())
    finally:
        loop.close()


def _probe_policy():
    if os.name == "nt":
        # Proactor supports subprocesses on Windows.
        return asyncio.WindowsProactorEventLoopPolicy()
    return asyncio.DefaultEventLoopPolicy()


def _in_probe_thread(fn):
    """Execute ``fn`` in the probe thread; returns an awaitable."""
    running = asyncio.get_running_loop()
    return running.run_in_executor(_PROBE_EXECUTOR, lambda: _run_probe_loop(fn))


async def _probe_version_async(path: str) -> ProbeResult:
    return await _in_probe_thread(lambda: probe_version(path))


async def _probe_identity_async(path: str) -> tuple[ProbeResult, str]:
    return await _in_probe_thread(lambda: probe_identity(path))


async def _probe_health_async(path: str) -> ProbeResult:
    return await _in_probe_thread(lambda: probe_health(path))


async def run_probe_sequence(name: str, path: str) -> DiscoveredAgent:
    """Full probe lifecycle for one candidate."""
    agent = DiscoveredAgent(
        id=f"agent:{name}",
        name=name,
        command=name,
        executable_path=path,
        status=STATUS_DISCOVERED,
    )

    if not path:
        agent.status = STATUS_NOT_FOUND
        agent.error = "executable not found"
        return agent

    # Probes are independent — run them concurrently. Sequential probing made
    # a full scan take >80s on a large PATH.
    version_probe, (identity_probe, help_text), health_probe = await asyncio.gather(
        _probe_version_async(path),
        _probe_identity_async(path),
        _probe_health_async(path),
    )

    agent.probes.extend([version_probe, identity_probe, health_probe])
    if version_probe.ok:
        agent.version = version_probe.detail[:64]
        agent.version_source = version_probe.evidence
    agent.kind = classify(name, help_text)
    agent.capabilities = derive_capabilities(help_text)

    # A real agent CLI must prove identity AND report a version (§6).
    # Unknown-version candidates stay non-agents rather than being promoted on
    # a single weak keyword in help text.
    if not version_probe.ok and agent.kind == KIND_AI_AGENT_CLI:
        agent.kind = KIND_AI_RUNTIME

    # Status is derived from evidence only.
    # A binary that exists but cannot run is UNAVAILABLE (§5, §8).
    # `gemini --version` exits 0 yet real invocation fails — identity probe
    # catches it, and we must report it, not silently drop it as unknown.
    if identity_probe.ok is False and "broken configuration" in identity_probe.detail:
        agent.status = STATUS_UNAVAILABLE
        agent.error = identity_probe.detail
        return agent

    if not version_probe.ok and not identity_probe.ok:
        agent.status = STATUS_FAILED
        agent.error = "no version or identity evidence"
        return agent
    if not health_probe.ok:
        agent.status = STATUS_UNAVAILABLE
        agent.error = health_probe.detail
        return agent
    if not version_probe.ok:
        agent.status = STATUS_DEGRADED  # runs, but version unknown
    else:
        agent.status = STATUS_HEALTHY

    # Health score is only set when a probe actually succeeded (§20).
    if health_probe.ok:
        agent.health_score = 100.0 if version_probe.ok else 60.0
        agent.validated_at = datetime.now(UTC).isoformat()

    return agent


def resolve(name: str) -> str | None:
    return shutil.which(name)


_VERSION_RE = re.compile(r"\d+(?:\.\d+)+")
