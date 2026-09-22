"""Linux / macOS discovery adapters (spec §17).

Same interface as the Windows adapter. Not exercised on this Windows host —
architecture only, so the UI stays platform-independent.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from agentic_os.core.brains.discovery_providers import BaseAgentDiscovery

# Hint fragments used only to GENERATE candidates from real files on disk.
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

_NOISE_SUBSTRINGS = (
    "ssh-agent",
    "gpg-agent",
    "gpg-connect",
    "npm",
    "installer",
    "setup",
    "node_modules",
)

_KNOWN_TOOLING = ("git", "node", "python", "python3", "npm", "pnpm", "uv", "bun", "deno", "cargo")


class _UnixBase(BaseAgentDiscovery):
    async def _enumerate_candidates(self) -> list[str]:
        names: set[str] = set()
        for directory in self._scan_dirs():
            try:
                entries = os.listdir(directory)
            except OSError:
                continue
            for entry in entries:
                path = Path(directory) / entry
                if not os.access(path, os.X_OK) or not path.is_file():
                    continue
                lowered = entry.lower()
                if any(noise in lowered for noise in _NOISE_SUBSTRINGS):
                    continue
                if any(hint in lowered for hint in _AGENT_HINTS) or lowered in _KNOWN_TOOLING:
                    names.add(lowered)
        return sorted(names)

    def _scan_dirs(self) -> list[str]:
        home = Path.home()
        return [
            p
            for p in os.environ.get("PATH", "").split(os.pathsep)
            + [
                str(home / ".local" / "bin"),
                str(home / ".cargo" / "bin"),
                str(home / ".bun" / "bin"),
                str(home / ".deno" / "bin"),
                "/usr/local/bin",
                "/opt/homebrew/bin",
            ]
            if p
        ]

    async def _resolve(self, name: str) -> str | None:
        return shutil.which(name)


class LinuxAgentDiscovery(_UnixBase):
    platform_name = "linux"


class MacOSAgentDiscovery(_UnixBase):
    platform_name = "macos"
