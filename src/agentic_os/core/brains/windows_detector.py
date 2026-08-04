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
    },
    {
        "key": "gemini",
        "name": "Gemini CLI",
        "exe": "gemini",
        "vendor": BrainVendor.GOOGLE,
        "runtime": BrainRuntime.NODE,
    },
    {
        "key": "qwen",
        "name": "Qwen CLI",
        "exe": "qwen",
        "vendor": BrainVendor.CUSTOM,
        "runtime": BrainRuntime.PYTHON,
    },
    {
        "key": "opencode",
        "name": "OpenCode",
        "exe": "opencode",
        "vendor": BrainVendor.CUSTOM,
        "runtime": BrainRuntime.NATIVE,
    },
    {
        "key": "aider",
        "name": "Aider",
        "exe": "aider",
        "vendor": BrainVendor.CUSTOM,
        "runtime": BrainRuntime.PYTHON,
    },
    {
        "key": "continue",
        "name": "Continue",
        "exe": "continue",
        "vendor": BrainVendor.CONTINUE,
        "runtime": BrainRuntime.NODE,
    },
    # ── Local model servers ───────────────────────────────────────────────
    {
        "key": "ollama",
        "name": "Ollama",
        "exe": "ollama",
        "vendor": BrainVendor.CUSTOM,
        "runtime": BrainRuntime.GO,
    },
    {
        "key": "lm-studio",
        "name": "LM Studio",
        "exe": "",
        "vendor": BrainVendor.CUSTOM,
        "runtime": BrainRuntime.NATIVE,
    },
    # ── Docker / MCP ──────────────────────────────────────────────────────
    {
        "key": "docker",
        "name": "Docker",
        "exe": "docker",
        "vendor": BrainVendor.CUSTOM,
        "runtime": BrainRuntime.NATIVE,
    },
    # ── Runtimes that have agent processes ────────────────────────────────
    {
        "key": "uv",
        "name": "uv (Python package)",
        "exe": "uv",
        "vendor": BrainVendor.CUSTOM,
        "runtime": BrainRuntime.PYTHON,
    },
    {
        "key": "node",
        "name": "Node.js",
        "exe": "node",
        "vendor": BrainVendor.CUSTOM,
        "runtime": BrainRuntime.NODE,
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
    try:
        proc = await asyncio.create_subprocess_exec(
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return stdout.decode("utf-16-le", errors="replace").strip() if stdout else ""
    except (TimeoutError, subprocess.TimeoutExpired, FileNotFoundError, OSError, NotImplementedError):
        return ""


async def _where_exe(name: str) -> str:
    """Find an executable via where.exe, returning full path or empty string."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "where.exe",
            name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await proc.communicate()
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
    try:
        proc = await asyncio.create_subprocess_exec(
            exe_path,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        output = (stdout or stderr).decode("utf-8", errors="replace").strip()
        # Extract semantic version (first match)
        m = re.search(r"(\d+\.\d+\.\d+[a-zA-Z0-9._-]*)", output)
        return m.group(1) if m else output[:50]
    except (TimeoutError, FileNotFoundError, OSError, NotImplementedError):
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


async def _detect_python_agent_processes() -> list[DetectedProcess]:
    """Detect Python processes that look like AI agents."""
    all_procs = await _get_running_processes(timeout=5.0)
    agent_keywords = ("agent", "ai", "llm", "model", "brain", "copilot", "codex", "opencode")
    agents = []
    for p in all_procs:
        pname = p.process_name.lower()
        if pname == "python" or pname == "python3" or pname.endswith(".py"):
            agents.append(p)
        elif any(kw in pname for kw in agent_keywords):
            if pname not in ("python.exe", "python3.exe", "node.exe", "conhost.exe", "svchost.exe"):
                agents.append(p)
    return agents


async def _detect_node_agent_processes() -> list[DetectedProcess]:
    """Detect Node.js processes running agent-related scripts."""
    all_procs = await _get_running_processes(timeout=5.0)
    agents = []
    for p in all_procs:
        if p.process_name.lower() == "node" or p.process_name.lower() == "npx":
            agents.append(p)
    return agents


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
        running_proc: DetectedProcess | None = None

        if exe_path:
            version = await _get_version(exe_path)
            running_proc = await _check_process_running(exe_name)

        records.append(
            BrainRecord(
                id=f"{info['key']}-{info['runtime'].value}",
                display_name=info["name"],
                brain_type=BrainType.LOCAL_CLI,
                vendor=info["vendor"],
                runtime=info["runtime"],
                version=version or "",
                status=(
                    BrainStatus.CONNECTED
                    if running_proc
                    else BrainStatus.DISCOVERED
                    if installed
                    else BrainStatus.REMOVED
                ),
                health=100.0 if installed else 0.0,
                memory_usage=running_proc.memory_mb if running_proc else 0.0,
                cpu_usage=running_proc.cpu_percent if running_proc else 0.0,
                latency=5.0 if running_proc else 0.0,
                current_tasks=1 if running_proc else 0,
                error_count=0,
                capabilities=(
                    f"cli:{info['key']}",
                    info["runtime"].value,
                    *(f"v{version}" for _ in [1] if version),
                ),
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
                health=100.0 if lm_running else 50.0,
                memory_usage=lm_running.memory_mb if lm_running else 0.0,
                cpu_usage=lm_running.cpu_percent if lm_running else 0.0,
                latency=5.0 if lm_running else 0.0,
                current_tasks=1 if lm_running else 0,
                error_count=0,
                capabilities=("local_model_server", "native"),
            )
        )

    # 3. MCP servers (running processes)
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
                health=95.0,
                memory_usage=mcp.memory_mb,
                cpu_usage=mcp.cpu_percent,
                latency=10.0,
                current_tasks=1,
                error_count=0,
                capabilities=("mcp", "server"),
            )
        )

    # 4. Python agent processes
    py_agents = await _detect_python_agent_processes()
    for i, agent in enumerate(py_agents):
        records.append(
            BrainRecord(
                id=f"python-agent-{i}",
                display_name=f"Python Agent ({agent.process_name})",
                brain_type=BrainType.ORCHESTRATOR,
                vendor=BrainVendor.CUSTOM,
                runtime=BrainRuntime.PYTHON,
                version="",
                status=BrainStatus.CONNECTED,
                health=95.0,
                memory_usage=agent.memory_mb,
                cpu_usage=agent.cpu_percent,
                latency=15.0,
                current_tasks=1,
                error_count=0,
                capabilities=("python", "agent"),
            )
        )

    # 5. Node agent processes
    node_agents = await _detect_node_agent_processes()
    for i, agent in enumerate(node_agents):
        records.append(
            BrainRecord(
                id=f"node-agent-{i}",
                display_name=f"Node Agent ({agent.process_name})",
                brain_type=BrainType.ORCHESTRATOR,
                vendor=BrainVendor.CUSTOM,
                runtime=BrainRuntime.NODE,
                version="",
                status=BrainStatus.CONNECTED,
                health=95.0,
                memory_usage=agent.memory_mb,
                cpu_usage=agent.cpu_percent,
                latency=15.0,
                current_tasks=1,
                error_count=0,
                capabilities=("node", "agent"),
            )
        )

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
