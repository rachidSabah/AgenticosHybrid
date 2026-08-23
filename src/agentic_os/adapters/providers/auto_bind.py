"""Auto-binding — discovers local AI agents and automatically registers them as providers.

Runs during boot (via the plugin system) and on-demand. For every known agent
binary found on PATH or in common install directories, a corresponding provider
adapter is registered so Mission Control shows it as a live, selectable provider.

KNOWN_AGENTS defines the mapping: binary name → provider kind. Extend this list
to support new CLI agents without touching the rest of the codebase.

The directory scanner complements PATH scanning by checking well-known install
locations so agents that were installed but aren't on PATH are still found.
"""

from __future__ import annotations

import os
import platform as _platform
import shutil
import subprocess
from pathlib import Path

from agentic_os.adapters.providers.strategies import ProviderFactory
from agentic_os.core.registry import ProviderRegistry
from agentic_os.domain.agent import ProviderInfo
from agentic_os.infrastructure.logging import get_logger

# On Windows, subprocess calls spawn a visible console window unless we pass
# CREATE_NO_WINDOW.  Deep Scan probes thousands of binaries, so without this
# the user sees a storm of popping cmd windows.  This flag is Windows-only.
_SUBPROCESS_WINDOW_FLAGS = (
    getattr(subprocess, "CREATE_NO_WINDOW", 0) if _platform.system() == "Windows" else 0
)

log = get_logger("discovery.auto_bind")

# ── Known AI agents that AgenticOS can auto-detect and bind ───────────────
# Each entry: {binary, kind, display_name, capabilities, description}
KNOWN_AGENTS: list[dict] = [
    {
        "binary": "claude",
        "kind": "claude_code",
        "display_name": "Claude Code",
        "capabilities": ["coding", "reasoning", "terminal"],
        "description": "Anthropic's Claude Code CLI — autonomous coding agent",
    },
    {
        "binary": "hermes",
        "kind": "hermes",
        "display_name": "Hermes Agent",
        "capabilities": ["coding", "reasoning", "research", "planning"],
        "description": "Nous Research's Hermes Agent — general-purpose AI agent",
    },
    {
        "binary": "codex",
        "kind": "codex",
        "display_name": "OpenAI Codex CLI",
        "capabilities": ["coding", "reasoning"],
        "description": "OpenAI Codex CLI — coding agent",
    },
    {
        "binary": "opencode",
        "kind": "opencode",
        "display_name": "OpenCode CLI",
        "capabilities": ["coding", "reasoning", "terminal"],
        "description": "OpenCode CLI — terminal-native coding agent",
    },
    {
        "binary": "aider",
        "kind": "aider",
        "display_name": "Aider",
        "capabilities": ["coding", "planning"],
        "description": "Aider — AI pair programming in the terminal",
    },
    {
        "binary": "ollama",
        "kind": "ollama",
        "display_name": "Ollama",
        "capabilities": ["reasoning", "coding"],
        "description": "Ollama — local LLM runner",
    },
    {
        "binary": "lm-studio",
        "kind": "lm_studio",
        "display_name": "LM Studio",
        "capabilities": ["reasoning"],
        "description": "LM Studio — local model server (OpenAI-compatible)",
    },
    {
        "binary": "open-interpreter",
        "kind": "open_interpreter",
        "display_name": "Open Interpreter",
        "capabilities": ["coding", "terminal", "filesystem"],
        "description": "Open Interpreter — natural-language computer control",
    },
    {
        "binary": "copilot",
        "kind": "github_copilot",
        "display_name": "GitHub Copilot CLI",
        "capabilities": ["coding", "terminal"],
        "description": "GitHub Copilot — AI pair programmer",
    },
    {
        "binary": "agy",
        "kind": "antigravity",
        "display_name": "Antigravity CLI",
        "capabilities": ["coding", "reasoning", "planning"],
        "description": "Google Antigravity CLI — autonomous coding agent",
    },
    {
        "binary": "gpt-engineer",
        "kind": "gpt_engineer",
        "display_name": "GPT Engineer",
        "capabilities": ["coding", "planning"],
        "description": "GPT Engineer — code generation from specifications",
    },
    {
        "binary": "swe-agent",
        "kind": "swe_agent",
        "display_name": "SWE-agent",
        "capabilities": ["coding", "bugfixing"],
        "description": "SWE-agent — autonomous bug-fixing agent",
    },
    {
        "binary": "cursor",
        "kind": "cursor",
        "display_name": "Cursor",
        "capabilities": ["coding", "reasoning", "planning"],
        "description": "Cursor — AI-first code editor (CLI mode)",
    },
    {
        "binary": "windsurf",
        "kind": "windsurf",
        "display_name": "Windsurf",
        "capabilities": ["coding", "reasoning", "planning"],
        "description": "Windsurf — AI code editor (CLI mode)",
    },
    {
        "binary": "agentic",
        "kind": "agentic",
        "display_name": "Agentic",
        "capabilities": ["coding", "reasoning", "research", "planning"],
        "description": "Agentic — general-purpose AI agent CLI",
    },
    {
        "binary": "gemini",
        "kind": "gemini_cli",
        "display_name": "Gemini CLI",
        "capabilities": ["coding", "reasoning", "terminal"],
        "description": "Google Gemini CLI — autonomous coding agent",
    },
    {
        "binary": "nvidia-nim",
        "kind": "nvidia_nim",
        "display_name": "NVIDIA NIM",
        "capabilities": ["coding", "reasoning", "research"],
        "description": "NVIDIA NIM API — free tier LLM agent via OpenAI-compatible API",
    },
]


def _common_install_dirs() -> list[Path]:
    """Yield well-known install directories for AI agent binaries.

    Combines PATH entries with common platform-specific locations so we
    catch agents that were installed but aren't on the current user's PATH.

    Windows system directories (system32, SysWOW64, WindowsApps, etc.) are
    explicitly EXCLUDED to prevent the event-loop wedge caused by probing
    thousands of OS binaries with subprocess --version calls.
    """
    dirs: list[Path] = []

    # Directories that must NEVER be scanned — they contain thousands of
    # OS binaries that would each get a 5s subprocess probe, blocking the
    # event loop for hours. This is the root cause of "Backend Offline".
    _EXCLUDED_DIRS = {
        "system32",
        "syswow64",
        "systemapps",
        "windowsapps",
        "driverstore",
        "servicing",
        "winsxs",
        "assembly",
        "microsoft.net",
        "windowspowershell",
        "powershell",
        "windows defender",
        "windowssystem",
    }

    def _is_excluded(p: Path) -> bool:
        """Check if a path should be excluded from scanning."""
        name = p.name.lower()
        if name in _EXCLUDED_DIRS:
            return True
        # Exclude any path containing \Windows\ (but NOT \Program Files\nodejs etc.)
        str_path = str(p).lower()
        if "\\windows\\" in str_path or "/windows/" in str_path:
            if "nodejs" not in str_path and "git" not in str_path:
                return True
        # Exclude Git usr/bin (thousands of POSIX utilities)
        if "usr\\bin" in str_path or "usr/bin" in str_path:
            if "git" not in name and "hermes" not in str_path:
                return True
        return False

    # ── PATH entries (filtered) ──
    path_env = os.environ.get("PATH", "")
    sep = ";" if _platform.system() == "Windows" else ":"
    for p in path_env.split(sep):
        p_stripped = p.strip()
        if p_stripped:
            path_obj = Path(p_stripped)
            if not _is_excluded(path_obj):
                dirs.append(path_obj)

    # ── Common install roots (platform-aware) ──
    home = Path.home()
    if _platform.system() == "Windows":
        local = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
        roaming = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
        candidates = [
            local / "Programs" / "Python" / "Scripts",
            local / "npm",
            local / "pnpm",
            local / "yarn" / "bin",
            local / "bin",
            local / "Microsoft" / "WinGet" / "Packages",
            roaming / "npm",
            roaming / "yarn" / "bin",
            roaming / "Local" / "bin",
            Path(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"))
            / "Common Files"
            / "Oracle"
            / "Java",
            Path("C:\\Program Files") / "nodejs",
            Path("C:\\Program Files") / "Git" / "bin",
            Path("C:\\Program Files") / "GitHub CLI",
            Path("C:\\tools"),
            home / ".cargo" / "bin",
            home / ".local" / "bin",
            home / "miniconda3" / "Scripts",
            home / "miniconda3" / "Library" / "bin",
            home / "scoop" / "shims",
            home / "AppData" / "Local" / "Microsoft" / "WinGet" / "Links",
        ]
    else:
        candidates = [
            Path("/usr/local/bin"),
            Path("/usr/bin"),
            Path("/opt/homebrew/bin"),
            Path("/home/linuxbrew/.linuxbrew/bin"),
            home / ".local" / "bin",
            home / ".cargo" / "bin",
            home / "go" / "bin",
            home / ".npm-global" / "bin",
            home / ".yarn" / "bin",
            Path("/snap/bin"),
            Path("/var/lib/snapd/snap/bin"),
        ]

    for c in candidates:
        c_resolved = c.resolve()
        if c_resolved.is_dir():
            dirs.append(c_resolved)

    # Deduplicate while preserving order
    seen: set[Path] = set()
    unique: list[Path] = []
    for d in dirs:
        if d not in seen:
            seen.add(d)
            unique.append(d)
    return unique


def _probe_binary(bin_path: Path) -> dict | None:
    """Probe an unknown binary to determine if it looks like an AI agent.

    Tries to extract version and help text. Returns a dict with probe results
    or None if the binary doesn't appear to be an AI agent.
    """
    try:
        # Try --version first (most common)
        # 3s timeout (reduced from 5s to prevent event-loop blocking on
        # interactive CLIs like gemini-cli that hang waiting for input)
        result = subprocess.run(
            [str(bin_path), "--version"],
            capture_output=True,
            text=False,
            timeout=3,
            creationflags=_SUBPROCESS_WINDOW_FLAGS,
        )
        stdout = result.stdout.decode("utf-8", errors="replace") if result.stdout else ""
        stderr = result.stderr.decode("utf-8", errors="replace") if result.stderr else ""
        output = (stdout + stderr).lower()
        # Check for AI-agent-like keywords
        ai_keywords = ["ai", "agent", "code", "assistant", "copilot", "llm", "gpt", "claude"]
        if any(kw in output for kw in ai_keywords):
            return {"version": stdout.strip()[:100], "type": "unknown"}
    except (subprocess.TimeoutExpired, OSError, NotImplementedError):
        pass

    return None


def _detect_unknown_agents(
    install_dirs: list[Path],
    existing_names: set[str],
    max_probes: int = 200,
    deadline_s: float = 30.0,
) -> list[dict]:
    """Scan install directories for CLI binaries that look like AI agents but
    aren't in KNOWN_AGENTS or already registered.

    This provides future-proofing: when a new AI CLI agent is released,
    AgenticOS will detect and bind it automatically even without a code update.

    Safety constraints (prevent event-loop wedge):
      - max_probes: hard cap on number of subprocess probes (default 200)
      - deadline_s: overall time budget in seconds (default 30s)
      - Each probe has a 3s timeout (reduced from 5s)
      - Progress is logged every 25 probes
    """
    import time

    found: list[dict] = []
    scanned: set[str] = set()
    probes_done = 0
    start_time = time.monotonic()

    for d in install_dirs:
        if not d.is_dir():
            continue
        # Check deadline
        if time.monotonic() - start_time > deadline_s:
            log.info("auto_bind.unknown_scan_deadline_reached", probes=probes_done)
            break
        # Check probe cap
        if probes_done >= max_probes:
            log.info("auto_bind.unknown_scan_cap_reached", cap=max_probes)
            break

        try:
            for entry in d.iterdir():
                if probes_done >= max_probes:
                    break
                if time.monotonic() - start_time > deadline_s:
                    break

                if not entry.is_file() and not entry.is_symlink():
                    continue
                name = entry.name.lower()
                # Skip non-executable / non-binary files
                if name.endswith(
                    (
                        ".py",
                        ".js",
                        ".txt",
                        ".md",
                        ".json",
                        ".yaml",
                        ".yml",
                        ".toml",
                        ".cfg",
                        ".conf",
                        ".dll",
                        ".so",
                        ".dylib",
                        ".a",
                        ".lib",
                        ".pdb",
                        ".dat",
                        ".bin",
                        ".cat",
                        ".inf",
                        ".cpl",
                        ".msc",
                        ".msi",
                        ".msp",
                    )
                ):
                    continue
                # Skip shell built-in names and common utilities
                if name in (
                    "python",
                    "python3",
                    "node",
                    "npm",
                    "npx",
                    "java",
                    "git",
                    "bash",
                    "sh",
                    "zsh",
                    "fish",
                    "powershell",
                    "cmd",
                    "pwsh",
                    "ls",
                    "cat",
                    "grep",
                    "sed",
                    "awk",
                    "find",
                    "sort",
                    "curl",
                    "wget",
                    "make",
                    "cmake",
                    "gcc",
                    "g++",
                    "clang",
                    "vim",
                    "nvim",
                    "emacs",
                    "nano",
                    "code",
                    "code-insiders",
                    "docker",
                    "docker-compose",
                    "kubectl",
                    "helm",
                    "rustc",
                    "cargo",
                    "go",
                    "deno",
                    "bun",
                ):
                    continue
                # Skip .exe, .com, .bat, .cmd on Windows (check without extension)
                stem = entry.stem if _platform.system() == "Windows" else name
                if stem in scanned:
                    continue
                # Skip known agents (already handled above) and existing names
                known_names = {a["binary"] for a in KNOWN_AGENTS}
                if stem in known_names or stem in existing_names:
                    continue

                # Probe the binary (with 3s timeout, not 5s)
                probes_done += 1
                if probes_done % 25 == 0:
                    log.info("auto_bind.unknown_scan_progress", probes=probes_done)

                probe = _probe_binary(entry)
                if probe:
                    scanned.add(stem)
                    found.append(
                        {
                            "binary": stem,
                            "kind": "auto_detected",
                            "display_name": stem.capitalize(),
                            "capabilities": ["coding", "reasoning"],
                            "description": f"Auto-detected AI agent: {stem}",
                            "path": str(entry),
                        }
                    )
                    log.info("auto_bind.unknown_detected", name=stem, path=str(entry))
        except PermissionError:
            continue
        except OSError:
            continue

    return found


def _check_dir_for_binary(directory: Path, binary: str) -> str | None:
    """Check if *binary* exists in *directory* (fast — no directory iteration).

    Only checks the specific binary name rather than listing the entire directory.
    On Windows tries common extensions.
    """
    if not directory.is_dir():
        return None
    if _platform.system() == "Windows":
        for ext in ("", ".exe", ".cmd", ".bat", ".ps1"):
            p = directory / f"{binary}{ext}"
            if p.is_file():
                return str(p)
    else:
        candidate = directory / binary
        if candidate.is_file() or candidate.is_symlink():
            return str(candidate)
    return None


def auto_discover_and_bind(
    provider_registry: ProviderRegistry,
    probe_unknown: bool = False,
) -> list[ProviderInfo]:
    """Scan PATH and common install directories for known and unknown agents.

    Returns the list of newly bound provider infos (empty if none found).
    Safe to call repeatedly — skips already-registered providers.

    When *probe_unknown* is False (default startup mode) the expensive unknown-agent
    probing phase (subprocess --version on every unknown binary) is skipped.
    Set *probe_unknown* to True for explicit on-demand scans or background tasks.
    """
    bound: list[ProviderInfo] = []
    existing_names: set[str] = set()

    # Collect already-registered provider names and kinds
    for p in provider_registry.list_providers():
        existing_names.add(p.name)
        existing_names.add(p.kind)
        for entry in KNOWN_AGENTS:
            if p.kind == entry["kind"] or p.name == entry["binary"]:
                existing_names.add(entry["binary"])

    # ── Phase 1: Resolve install directories (no bulk file scan) ──
    install_dirs = _common_install_dirs()
    resolved_dirs: list[Path] = []
    seen: set[Path] = set()
    for d in install_dirs:
        try:
            resolved = d.resolve()
            if resolved not in seen:
                seen.add(resolved)
                resolved_dirs.append(resolved)
        except OSError:
            if d not in seen:
                seen.add(d)
                resolved_dirs.append(d)

    # ── Phase 2: Bind known agents (targeted lookups, no directory iteration) ──
    for entry in KNOWN_AGENTS:
        binary = entry["binary"]
        kind = entry["kind"]

        if binary in existing_names:
            log.debug("auto_bind.skipping", binary=binary, reason="already registered")
            continue

        # Check PATH first (fast — shutil.which only checks PATH dirs)
        bin_path = shutil.which(binary)

        # Fallback: check extra install directories for the specific binary
        if bin_path is None:
            for d in resolved_dirs:
                result = _check_dir_for_binary(d, binary)
                if result:
                    bin_path = result
                    break

        if bin_path is None:
            log.debug("auto_bind.skipping", binary=binary, reason="not found on PATH or disk")
            continue

        try:
            name = f"auto:{binary}"
            # Use the ProviderFactory to create the correct adapter
            # with the correct execution strategy for this CLI.
            # No more manual if/elif/else — the factory handles it.
            adapter = ProviderFactory.create(
                kind=kind,
                bin_path=binary,
                name=name,
                display_name=entry.get("display_name", binary),
                capabilities=entry.get("capabilities", ["coding", "reasoning"]),
                api_key="",
            )

            provider_registry.register(adapter)  # type: ignore[arg-type]

            info = ProviderInfo(
                name=name,
                kind=kind,
                supports_streaming=True,
                supports_tools=True,
            )
            bound.append(info)
            existing_names.add(binary)
            log.info(
                "auto_bind.bound",
                name=name,
                kind=kind,
                binary=binary,
                path=bin_path,
            )
        except Exception as exc:
            log.error("auto_bind.failed", name=binary, kind=kind, error=str(exc))

    # ── Phase 3: Probe for unknown / unlisted agents ──
    # Skipped during synchronous startup — runs on-demand or via background task.
    unknown: list[dict] = []
    if probe_unknown:
        unknown = _detect_unknown_agents(install_dirs, existing_names)
    for agent in unknown:
        binary = agent["binary"]
        bin_path = agent.get("path", binary)
        try:
            name = f"auto:{binary}"
            # Use factory for unknown agents too — they get GenericExecutionStrategy
            adapter = ProviderFactory.create(
                kind=agent.get("kind", "generic"),
                bin_path=binary,
                name=name,
                display_name=agent.get("display_name", binary),
                capabilities=agent.get("capabilities", ["coding", "reasoning"]),
            )
            provider_registry.register(adapter)  # type: ignore[arg-type]

            info = ProviderInfo(
                name=name,
                kind=agent["kind"],
                supports_streaming=True,
                supports_tools=True,
            )
            bound.append(info)
            existing_names.add(binary)
            log.info("auto_bind.bound_unknown", name=name, binary=binary, path=bin_path)
        except Exception as exc:
            log.error("auto_bind.failed_unknown", name=binary, error=str(exc))

    if bound:
        log.info("auto_bind.complete", count=len(bound))
    else:
        log.info("auto_bind.complete", count=0)

    return bound
