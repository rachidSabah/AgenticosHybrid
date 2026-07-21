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

from agentic_os.adapters.providers.claude_code import ClaudeCodeProvider
from agentic_os.adapters.providers.hermes import HermesProvider
from agentic_os.adapters.providers.mock import MockProvider
from agentic_os.core.registry import ProviderRegistry
from agentic_os.domain.agent import ProviderInfo
from agentic_os.infrastructure.logging import get_logger

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
]


def _common_install_dirs() -> list[Path]:
    """Yield well-known install directories for AI agent binaries.

    Combines PATH entries with common platform-specific locations so we
    catch agents that were installed but aren't on the current user's PATH.
    """
    dirs: list[Path] = []

    # ── PATH entries ──
    path_env = os.environ.get("PATH", "")
    sep = ";" if _platform.system() == "Windows" else ":"
    for p in path_env.split(sep):
        p_stripped = p.strip()
        if p_stripped:
            dirs.append(Path(p_stripped))

    # ── Common install roots (platform-aware) ──
    home = Path.home()
    if _platform.system() == "Windows":
        local = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
        roaming = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
        prog_data = Path(os.environ.get("ProgramData", "C:\\ProgramData"))
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
            Path(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")) / "Common Files" / "Oracle" / "Java",
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
        result = subprocess.run(
            [str(bin_path), "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        output = (result.stdout + result.stderr).lower()
        # Check for AI-agent-like keywords
        ai_keywords = ["ai", "agent", "code", "assistant", "copilot", "llm", "gpt", "claude"]
        if any(kw in output for kw in ai_keywords):
            return {"version": result.stdout.strip()[:100], "type": "unknown"}
    except (subprocess.TimeoutExpired, OSError):
        pass
    return None


def _detect_unknown_agents(
    install_dirs: list[Path],
    existing_names: set[str],
) -> list[dict]:
    """Scan install directories for CLI binaries that look like AI agents but
    aren't in KNOWN_AGENTS or already registered.

    This provides future-proofing: when a new AI CLI agent is released,
    AgenticOS will detect and bind it automatically even without a code update.
    """
    found: list[dict] = []
    scanned: set[str] = set()

    for d in install_dirs:
        if not d.is_dir():
            continue
        try:
            for entry in d.iterdir():
                if not entry.is_file() and not entry.is_symlink():
                    continue
                name = entry.name.lower()
                # Skip non-executable / non-binary files
                if name.endswith((".py", ".js", ".txt", ".md", ".json", ".yaml", ".yml", ".toml", ".cfg", ".conf")):
                    continue
                # Skip shell built-in names and common utilities
                if name in (
                    "python", "python3", "node", "npm", "npx", "java", "git",
                    "bash", "sh", "zsh", "fish", "powershell", "cmd", "pwsh",
                    "ls", "cat", "grep", "sed", "awk", "find", "sort",
                    "curl", "wget", "make", "cmake", "gcc", "g++", "clang",
                    "vim", "nvim", "emacs", "nano", "code", "code-insiders",
                    "docker", "docker-compose", "kubectl", "helm",
                    "rustc", "cargo", "go", "deno", "bun",
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

                # Probe the binary
                probe = _probe_binary(entry)
                if probe:
                    scanned.add(stem)
                    found.append({
                        "binary": stem,
                        "kind": "auto_detected",
                        "display_name": stem.capitalize(),
                        "capabilities": ["coding", "reasoning"],
                        "description": f"Auto-detected AI agent: {stem}",
                        "path": str(entry),
                    })
                    log.info("auto_bind.unknown_detected", name=stem, path=str(entry))
        except PermissionError:
            continue
        except OSError:
            continue

    return found


def auto_discover_and_bind(provider_registry: ProviderRegistry) -> list[ProviderInfo]:
    """Scan PATH and common install directories for known and unknown agents.

    Returns the list of newly bound provider infos (empty if none found).
    Safe to call repeatedly — skips already-registered providers.
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

    # ── Phase 1: Scan PATH + common install dirs ──
    install_dirs = _common_install_dirs()
    resolved_dirs: set[Path] = set()
    for d in install_dirs:
        try:
            resolved_dirs.add(d.resolve())
        except OSError:
            resolved_dirs.add(d)

    # Build a set of all binaries found across all directories
    all_binaries: dict[str, Path] = {}
    for d in resolved_dirs:
        if not d.is_dir():
            continue
        try:
            for entry in d.iterdir():
                if entry.is_file() or entry.is_symlink():
                    name = entry.name
                    stem = Path(name).stem if _platform.system() == "Windows" else name
                    if stem not in all_binaries:
                        all_binaries[stem] = entry
        except (PermissionError, OSError):
            continue

    # ── Phase 2: Bind known agents ──
    for entry in KNOWN_AGENTS:
        binary = entry["binary"]
        kind = entry["kind"]

        if binary in existing_names:
            log.debug("auto_bind.skipping", binary=binary, reason="already registered")
            continue

        # Check PATH first, then fall back to scanned directories
        bin_path = shutil.which(binary)
        if bin_path is None and binary in all_binaries:
            bin_path = str(all_binaries[binary])

        if bin_path is None:
            log.debug("auto_bind.skipping", binary=binary, reason="not found on PATH or disk")
            continue

        try:
            name = f"auto:{binary}"
            adapter: object
            if kind == "claude_code":
                adapter = ClaudeCodeProvider(bin_path=binary, api_key="", name=name)
            elif kind == "hermes":
                adapter = HermesProvider(bin_path=binary, api_key="", name=name)
            else:
                # Generic CLI adapter for any other agent type
                adapter = ClaudeCodeProvider(bin_path=binary, api_key="", name=name)

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
    unknown = _detect_unknown_agents(install_dirs, existing_names)
    for agent in unknown:
        binary = agent["binary"]
        bin_path = agent.get("path", binary)
        try:
            name = f"auto:{binary}"
            adapter = ClaudeCodeProvider(bin_path=binary, api_key="", name=name)
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
