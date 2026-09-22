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
_AGENT_HINTS = (
    "agent",
    "ai",
    "assistant",
    "llm",
    "copilot",
    "claude",
    "codex",
    "gemini",
    "agy",
    "antigravity",
    "opencode",
    "aider",
    "continue",
    "cline",
    "cursor",
    "windsurf",
    "roo",
    "kilo",
    "qwen",
    "hermes",
    "goose",
    "openhands",
    "glm",
    "deepseek",
)

# File-name noise: OS/CLI plumbing that merely contains a hint word.
_NOISE_SUBSTRINGS = (
    "ssh-agent",
    "gpg-agent",
    "gpg-connect",
    "medicagent",
    "agentpolicy",
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
)

# Known non-agent tooling we deliberately surface as Runtimes (§4).
_KNOWN_TOOLING = ("git", "node", "python", "python3", "npm", "pnpm", "uv", "bun", "deno")


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
        """Directories to scan: PATH, PATHEXT-aware, user-local, npm-global."""
        dirs: list[str] = []

        # 1. Everything on PATH.
        dirs.extend(p for p in os.environ.get("PATH", "").split(os.pathsep) if p)

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
        dirs.extend(p for p in extra if p)

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
