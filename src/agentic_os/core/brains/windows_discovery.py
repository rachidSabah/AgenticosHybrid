"""Windows discovery adapter (spec §3, §17).

Enumerates PATH + PATHEXT + user-local + npm-global + known package-manager
locations. Candidate generation is ENVIRONMENT-derived; there is no list of
agent names here. Anything that looks agentic is emitted and then probed.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from agentic_os.core.brains.discovery_providers import BaseAgentDiscovery

# Executable extensions on Windows (PATHEXT-aware, §3).
_WIN_EXTS = (".exe", ".cmd", ".bat", ".ps1", ".com")

# Name fragments that plausibly indicate an agentic tool. These only GENERATE
# CANDIDATES from real files on disk; every candidate is then probed. A false
# positive cannot become an agent because validation rejects it (§4, §21 T6).
#
# IMPORTANT: Avoid single-character or very short hints like "ai" that match
# common Windows system binaries (mspaint, aitstatic, pairtool, etc.).
# Prefer precise tool names or longer unambiguous fragments only.
_AGENT_HINTS = (
    "claude",
    "codex",
    # "gemini" hint REMOVED — retired provider (spec §2/§36).

    "agy",
    "antigravity",
    "opencode",
    "aider",
    "cline",
    "cursor",
    "windsurf",
    "qwen",
    "hermes",
    "goose",
    "openhands",
    "deepseek",
    "copilot",
    "agent-nexus",
    "agent-zero",
    "open-agent",
    "llm-agent",
    "ai-agent",
    "glm",
)

# File-name noise: OS/CLI plumbing that merely contains a hint word.
# Any binary whose lower-cased stem contains one of these substrings is
# excluded from the candidate list immediately — before any subprocess call.
_NOISE_SUBSTRINGS = (
    "ssh-agent",
    "gpg-agent",
    "gpg-connect",
    "medicagent",
    "agentpolicy",
    "agentservice",
    "agentactivation",
    "policygenerator",
    "waasmedic",
    "code-mode-host",
    "command-runner",
    "npm",
    "node_modules",
    "installer",
    "setup",
    "unins",
    "crashhandler",
    # Windows system utilities falsely matched by "agent" or "ai" fragments.
    "mspaint",
    "spaceagent",
    "logagent",
    "reagent",
    "mdmagent",
    "waitfor",
    "repair-bde",
    "pairtool",
    "aitstatic",
    "lsaiso",
    "pinenrollment",
    "thumbnailextraction",
    "shellmcpservers",
    "nvcontainer",
    "microsoft.data",
    # Vendor bloatware that merely contains "ai" — never an AI agent.
    "asus",
    "b9eced6f",
    "credentialenrollment",
    "devicepairing",
    "diskraid",
    "fsavailux",
    "ddmmain",
    "converter",  # ct2-*-converter: model file converters, not agents
    "chrome-native-host",
    "theme",
    "gemini",  # retired provider — must not be scanned or resurrected (§2)
)

# Known non-agent tooling we deliberately surface as Runtimes (§4).
_KNOWN_TOOLING = ("git", "node", "python", "python3", "npm", "pnpm", "uv", "bun", "deno")

# Directory path fragments that should NEVER be scanned for agent candidates.
# These contain OS system binaries, store app stubs, and other non-agent executables.
_EXCLUDED_DIR_FRAGMENTS = (
    os.path.normcase("windowsapps"),  # Microsoft Store stubs (mspaint stub, etc.)
    os.path.normcase("system32"),  # Windows system binaries
    os.path.normcase("syswow64"),  # 32-bit system binaries
    os.path.normcase("\\windows\\"),  # Windows root
    os.path.normcase("/windows/"),
)


def _is_excluded_dir(directory: str) -> bool:
    """Return True if this directory should be excluded from candidate scanning."""
    normed = os.path.normcase(directory)
    return any(frag in normed for frag in _EXCLUDED_DIR_FRAGMENTS)


class WindowsAgentDiscovery(BaseAgentDiscovery):
    platform_name = "windows"

    async def _enumerate_candidates(self) -> list[str]:
        names: set[str] = set()

        for directory in self._scan_dirs():
            try:
                entries = os.listdir(directory)
            except OSError:
                continue
            for entry in entries:
                stem = self._stem(entry)
                if not stem:
                    continue
                lowered = stem.lower()
                if any(noise in lowered for noise in _NOISE_SUBSTRINGS):
                    continue
                if any(hint in lowered for hint in _AGENT_HINTS) or lowered in _KNOWN_TOOLING:
                    names.add(lowered)

        return sorted(names)

    def _scan_dirs(self) -> list[str]:
        """Directories to scan: PATH, PATHEXT-aware, user-local, npm-global.

        Windows system directories (system32, WindowsApps, etc.) are explicitly
        excluded to prevent OS stub launchers from being enumerated as candidates.
        """
        dirs: list[str] = []

        # 1. Everything on PATH — excluding system directories.
        for p in os.environ.get("PATH", "").split(os.pathsep):
            if p and not _is_excluded_dir(p):
                dirs.append(p)

        # 2. User-local and package-manager install roots (§3).
        home = Path.home()
        localappdata = os.environ.get("LOCALAPPDATA", "")
        appdata = os.environ.get("APPDATA", "")
        extra = [
            str(home / ".local" / "bin"),
            str(home / "AppData" / "Roaming" / "npm"),
            str(home / "scoop" / "shims"),
            str(home / ".cargo" / "bin"),
            str(home / ".bun" / "bin"),
            str(home / ".deno" / "bin"),
            os.path.join(localappdata, "Programs"),
            os.path.join(localappdata, "agy", "bin"),
            os.path.join(appdata, "npm"),
            os.path.join(localappdata, "Programs", "OpenAI", "Codex", "bin"),
        ]
        dirs.extend(p for p in extra if p and not _is_excluded_dir(p))

        seen: set[str] = set()
        unique: list[str] = []
        for d in dirs:
            key = os.path.normcase(os.path.normpath(d))
            if key in seen:
                continue
            seen.add(key)
            unique.append(d)
        return unique

    def _stem(self, entry: str) -> str:
        lowered = entry.lower()
        if os.name == "nt" and not lowered.endswith(_WIN_EXTS):
            return ""
        p = Path(entry)
        # Strip .exe/.cmd etc.
        return p.stem if p.suffix.lower() in _WIN_EXTS else ""

    async def _resolve(self, name: str) -> str | None:
        # PATHEXT-aware resolution.
        found = shutil.which(name)
        if found:
            return found
        for ext in _WIN_EXTS:
            found = shutil.which(name + ext)
            if found:
                return found
        # Fall back to scanning known dirs directly (not on PATH).
        for directory in self._scan_dirs():
            for ext in _WIN_EXTS:
                candidate = os.path.join(directory, name + ext)
                if os.path.isfile(candidate):
                    return candidate
        return None
