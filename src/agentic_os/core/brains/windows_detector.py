"""Real Windows process detection for AI brain runtimes.

Uses PowerShell Get-Process, where.exe, registry queries, and
subprocess version probes to find every installed local AI runtime
on a Windows machine.
"""

from __future__ import annotations

import asyncio
import os
import platform
import re
import subprocess
from dataclasses import dataclass
from typing import Any

from agentic_os.domain.brains import BrainRecord, BrainRuntime, BrainStatus, BrainType, BrainVendor

# ── Known runtimes ────────────────────────────────────────────────────────────

KNOWN_RUNTIMES: list[dict[str, Any]] = [
    # ── CLI agents ────────────────────────────────────────────────────────
    {
        "key": "claude",
        "name": "Claude Code",
        "exe": "claude",
        "vendor": BrainVendor.ANTHROPIC,
        "runtime": BrainRuntime.NATIVE,
    },
    {
        "key": "hermes",
        "name": "Hermes Desktop",
        "exe": "hermes",
        "vendor": BrainVendor.HERMES,
        "runtime": BrainRuntime.PYTHON,
    },
    {
        "key": "codex",
        "name": "OpenAI Codex CLI",
        "exe": "codex",
        "vendor": BrainVendor.CODEX,
        "runtime": BrainRuntime.NATIVE,
        "is_agent": True,
    },
    # "gemini" (Gemini CLI) REMOVED — retired provider. Antigravity (agy) is
    # the canonical Google CLI agent; no alias may resurrect Gemini.
    {
        "key": "qwen",
        "name": "Qwen CLI",
        "exe": "qwen",
        "vendor": BrainVendor.QWEN,
        "runtime": BrainRuntime.PYTHON,
        "is_agent": True,
    },
    {
        "key": "opencode",
        "name": "OpenCode",
        "exe": "opencode",
        "vendor": BrainVendor.OPENCODE,
        "runtime": BrainRuntime.NATIVE,
        "is_agent": True,
    },
    {
        "key": "aider",
        "name": "Aider",
        "exe": "aider",
        "vendor": BrainVendor.AIDER,
        "runtime": BrainRuntime.PYTHON,
        "is_agent": True,
    },
    {
        "key": "continue",
        "name": "Continue",
        "exe": "continue",
        "vendor": BrainVendor.CONTINUE,
        "runtime": BrainRuntime.NODE,
        "is_agent": True,
    },
    # ── Local model servers ───────────────────────────────────────────────
    {
        "key": "ollama",
        "name": "Ollama",
        "exe": "ollama",
        "vendor": BrainVendor.OLLAMA,
        "runtime": BrainRuntime.GO,
        "is_agent": False,
    },
    {
        "key": "lm-studio",
        "name": "LM Studio",
        "exe": "",
        "vendor": BrainVendor.LM_STUDIO,
        "runtime": BrainRuntime.NATIVE,
        "is_agent": False,
    },
    # ── Docker / MCP ──────────────────────────────────────────────────────
    {
        "key": "docker",
        "name": "Docker",
        "exe": "docker",
        "vendor": BrainVendor.CUSTOM,
        "runtime": BrainRuntime.CONTAINER,
        "is_agent": False,
    },
    # ── Developer Tools & Language Runtimes (NOT AI agents; spec §4/§22/§37).
    # Kept for runtime/tooling visibility with is_agent=False — the kernel
    # and every agent endpoint filter them out of the agent registries.
    {
        "key": "python",
        "name": "Python",
        "exe": "python",
        "vendor": BrainVendor.PYTHON,
        "runtime": BrainRuntime.PYTHON,
        "is_agent": False,
    },
    {
        "key": "node",
        "name": "Node.js",
        "exe": "node",
        "vendor": BrainVendor.NODE,
        "runtime": BrainRuntime.NODE,
        "is_agent": False,
    },
    {
        "key": "bun",
        "name": "Bun",
        "exe": "bun",
        "vendor": BrainVendor.BUN,
        "runtime": BrainRuntime.BUN,
        "is_agent": False,
    },
    {
        "key": "git",
        "name": "Git",
        "exe": "git",
        "vendor": BrainVendor.GIT,
        "runtime": BrainRuntime.NATIVE,
        "is_agent": False,
    },
    {
        "key": "uv",
        "name": "uv (Python package)",
        "exe": "uv",
        "vendor": BrainVendor.PYTHON,
        "runtime": BrainRuntime.PYTHON,
        "is_agent": False,
    },
]

# ── Detection helpers ─────────────────────────────────────────────────────────


@dataclass
class DetectedProcess:
    """Information about a detected OS process."""

    pid: int
    name: str
    process_name: str
    command_line: str = ""
    cpu_percent: float = 0.0
    memory_mb: float = 0.0


async def _run_powershell(script: str, timeout: float = 10.0) -> str:
    """Run a PowerShell script and return stdout.

    Handles the Windows PowerShell execution environment.
    """
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        proc = await asyncio.create_subprocess_exec(
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            creationflags=creationflags,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return stdout.decode("utf-16-le", errors="replace").strip() if stdout else ""
        except (TimeoutError, subprocess.TimeoutExpired):
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass
            return ""
    except (
        FileNotFoundError,
        OSError,
        NotImplementedError,
    ):
        return ""


async def _where_exe(name: str) -> str:
    """Find an executable via where.exe, returning full path or empty string."""
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        proc = await asyncio.create_subprocess_exec(
            "where.exe",
            name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            creationflags=creationflags,
        )
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=3.0)
        except TimeoutError:
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass
            return ""
        lines = stdout.decode("utf-8", errors="replace").strip().splitlines()
        for line in lines:
            line = line.strip()
            if line and line.lower().endswith(".exe"):
                return line
        return lines[0].strip() if lines else ""
    except (FileNotFoundError, OSError, NotImplementedError):
        return ""


async def _get_version(
    exe_path: str,
    args: tuple[str, ...] = ("--version",),
    timeout: float = 5.0,
) -> str:
    """Get version string from an executable."""
    if not exe_path or os.path.isdir(exe_path):
        return ""
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        proc = await asyncio.create_subprocess_exec(
            exe_path,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            creationflags=creationflags,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except TimeoutError:
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass
            return ""
        output = (stdout or stderr).decode("utf-8", errors="replace").strip()
        lowered = output.lower()
        if any(
            sig in lowered
            for sig in (
                "invalid configuration",
                "expected object, received array",
                "error in:",
                "broken configuration",
            )
        ):
            return ""
        # Extract semantic version (first match)
        m = re.search(r"(\d+\.\d+\.\d+[a-zA-Z0-9._-]*)", output)
        return m.group(1) if m else output[:50]
    except (FileNotFoundError, OSError, NotImplementedError):
        return ""


async def _get_running_processes(timeout: float = 10.0) -> list[DetectedProcess]:
    """Get list of running processes via PowerShell.

    Returns parsed process info for all running processes so callers
    can match by executable name.
    """
    ps_script = (
        "Get-Process | Select-Object Id, ProcessName, "
        "@{N='CPU';E={$_.CPU}}, "
        "@{N='WorkingSetMB';E={[math]::Round($_.WorkingSet64 / 1MB, 1)}} "
        "| ConvertTo-Csv -NoTypeInformation"
    )
    output = await _run_powershell(ps_script, timeout=timeout)
    processes: list[DetectedProcess] = []
    for line in output.splitlines()[1:]:  # Skip header
        parts = line.strip('"').split('","')
        if len(parts) >= 4:
            try:
                processes.append(
                    DetectedProcess(
                        pid=int(parts[0]),
                        name=parts[1],
                        process_name=parts[1],
                        cpu_percent=float(parts[2]) if parts[2] else 0.0,
                        memory_mb=float(parts[3]) if parts[3] else 0.0,
                    )
                )
            except (ValueError, IndexError):
                continue
    return processes


async def _check_process_running(exe_name: str) -> DetectedProcess | None:
    """Check whether a process with the given name is running."""
    # Use separate strings to avoid nested f-string issues
    select_fields = (
        "Id, ProcessName, "
        "@{N='CPU';E={$_.CPU}}, "
        "@{N='WorkingSetMB';E={[math]::Round($_.WorkingSet64 / 1MB, 1)}}"
    )
    ps_script = (
        f"Get-Process -Name '{exe_name}' -ErrorAction SilentlyContinue "
        f"| Select-Object {select_fields} "
        f"| ConvertTo-Csv -NoTypeInformation"
    )
    output = await _run_powershell(ps_script, timeout=5.0)
    for line in output.splitlines()[1:]:
        parts = line.strip('"').split('","')
        if len(parts) >= 4:
            try:
                return DetectedProcess(
                    pid=int(parts[0]),
                    name=parts[1],
                    process_name=parts[1],
                    cpu_percent=float(parts[2]) if parts[2] else 0.0,
                    memory_mb=float(parts[3]) if parts[3] else 0.0,
                )
            except (ValueError, IndexError):
                continue
    return None


async def _check_registry_installed(registry_path: str) -> bool:
    """Check if a registry key exists (indicating installed software)."""
    script = f"Test-Path '{registry_path}'"
    output = await _run_powershell(script, timeout=5.0)
    return "True" in output


async def _check_lm_studio() -> str:
    """Check LM Studio installation via registry and default path."""
    # Check common install locations
    local_appdata = os.environ.get("LOCALAPPDATA", "")
    if local_appdata:
        lm_path = os.path.join(local_appdata, "LM Studio", "LM Studio.exe")
        if os.path.isfile(lm_path):
            return lm_path
    program_files = os.environ.get("PROGRAMFILES", "C:\\Program Files")
    lm_path = os.path.join(program_files, "LM Studio", "LM Studio.exe")
    if os.path.isfile(lm_path):
        return lm_path
    return ""


async def _detect_hermes_desktop_process() -> DetectedProcess | None:
    """Hermes Desktop runs as hermes.exe or hermes-desktop.exe."""
    for name in ("hermes", "hermes-desktop", "Hermes Desktop"):
        proc = await _check_process_running(name)
        if proc:
            return proc
    return None


async def _detect_mcp_processes() -> list[DetectedProcess]:
    """Detect running MCP server processes (common patterns)."""
    mcp_names = ("mcp", "mcp-server", "mcp-server-")
    all_procs = await _get_running_processes(timeout=5.0)
    return [p for p in all_procs if any(m in p.process_name.lower() for m in mcp_names)]


# _detect_python_agent_processes / _detect_node_agent_processes REMOVED
# (spec §4/§22): every running python/node process was being reported as an
# "AI agent brain" with fabricated health=95. A runtime process is not an
# agent; only validated AI-agent CLIs may enter the brain registry.

# ── Public API ────────────────────────────────────────────────────────────────


async def detect_local_windows(timeout: float = 30.0) -> list[BrainRecord]:
    """Detect every installed local AI brain on Windows.

    Scans PATH (via where.exe), running processes (via PowerShell),
    registry keys, and default install locations. Returns a list of
    :class:`BrainRecord` objects, one per detected runtime.
    """
    if platform.system() != "Windows":
        return []

    records: list[BrainRecord] = []

    # 1. Scan known CLI tools: where.exe + version + running
    for info in KNOWN_RUNTIMES:
        exe_name = info["exe"]
        if not exe_name:
            # Non-CLI runtime (LM Studio) handled separately
            continue

        exe_path = await _where_exe(exe_name)
        installed = bool(exe_path)
        version = ""
        is_broken = False
        if exe_path:
            version = await _get_version(exe_path)
            running_proc = await _check_process_running(exe_name)
            if not version:
                is_broken = True

        records.append(
            BrainRecord(
                id=f"{info['key']}-{info['runtime'].value}",
                display_name=info["name"],
                brain_type=BrainType.LOCAL_CLI,
                vendor=info["vendor"],
                runtime=info["runtime"],
                version=version or "",
                status=(
                    BrainStatus.REMOVED
                    if (not installed or is_broken)
                    else BrainStatus.CONNECTED
                    if running_proc
                    else BrainStatus.DISCOVERED
                ),
                # Health reflects REAL evidence only: a successful version
                # probe (and, additionally, a live process). No invented 60/95
                # baselines (spec §16/§17).
                health=100.0 if (installed and not is_broken) else 0.0,
                memory_usage=running_proc.memory_mb if running_proc else 0.0,
                cpu_usage=running_proc.cpu_percent if running_proc else 0.0,
                latency=0.0,
                current_tasks=0,
                error_count=1 if is_broken else 0,
                capabilities=(
                    f"cli:{info['key']}",
                    info["runtime"].value,
                    *(f"v{version}" for _ in [1] if version),
                ),
                is_agent=info.get("is_agent", True),
            )
        )

    # 2. LM Studio (non-CLI, registry/install-dir detection)
    lm_path = await _check_lm_studio()
    lm_running = await _check_process_running("LM Studio")
    if lm_path or lm_running:
        records.append(
            BrainRecord(
                id="lm-studio-native",
                display_name="LM Studio",
                brain_type=BrainType.LOCAL_CLI,
                vendor=BrainVendor.CUSTOM,
                runtime=BrainRuntime.NATIVE,
                version=await _get_version(lm_path) if lm_path else "",
                status=BrainStatus.CONNECTED if lm_running else BrainStatus.DISCOVERED,
                # Real evidence only: probe succeeded (health 100) or not.
                health=100.0 if (lm_path or lm_running) else 0.0,
                memory_usage=lm_running.memory_mb if lm_running else 0.0,
                cpu_usage=lm_running.cpu_percent if lm_running else 0.0,
                latency=0.0,
                current_tasks=0,
                error_count=0,
                capabilities=("local_model_server", "native"),
            )
        )

    # 3. MCP servers (running processes) — a real running process is real
    # evidence; no invented health/latency/task numbers (spec §16/§17).
    mcp_procs = await _detect_mcp_processes()
    for i, mcp in enumerate(mcp_procs):
        records.append(
            BrainRecord(
                id=f"mcp-server-{i}",
                display_name=f"MCP Server ({mcp.process_name})",
                brain_type=BrainType.MCP_SERVER,
                vendor=BrainVendor.CUSTOM,
                runtime=BrainRuntime.NATIVE,
                version="",
                status=BrainStatus.CONNECTED,
                health=100.0,
                memory_usage=mcp.memory_mb,
                cpu_usage=mcp.cpu_percent,
                latency=0.0,
                current_tasks=0,
                error_count=0,
                capabilities=("mcp", "server"),
            )
        )

    # Sections 4/5 (python/node "agent" process brains) REMOVED — every
    # python/node process was registered as an ORCHESTRATOR brain with
    # fabricated health=95 (spec §4/§22/§37: runtimes are not agents).

    return records


async def detect_remote_brains(timeout: float = 10.0) -> list[BrainRecord]:
    """Detect cloud AI services available via API keys.

    Checks environment variables for API keys and creates cloud brain
    records for services whose keys are configured.
    """
    records: list[BrainRecord] = []

    api_key_vars = {
        "openai": ("OPENAI_API_KEY", BrainVendor.OPENAI, "gpt-4o"),
        "anthropic": ("ANTHROPIC_API_KEY", BrainVendor.ANTHROPIC, "claude-sonnet-4"),
        "google": ("GOOGLE_API_KEY", BrainVendor.GOOGLE, "gemini-2.0-flash"),
        "openrouter": ("OPENROUTER_API_KEY", BrainVendor.OPENROUTER, "auto"),
    }

    for service, (env_var, vendor, default_model) in api_key_vars.items():
        key = os.environ.get(env_var, "")
        if key:
            records.append(
                BrainRecord(
                    id=f"cloud-{service}",
                    display_name=f"{vendor.value.title()} Cloud",
                    brain_type=BrainType.CLOUD_API,
                    vendor=vendor,
                    runtime=BrainRuntime.UNKNOWN,
                    version="",
                    status=BrainStatus.CONNECTED,
                    health=100.0,
                    capabilities=(f"cloud:{service}", default_model),
                )
            )

    return records
