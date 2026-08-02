"""Filesystem scanner for local agent discovery.

Scans common installation directories for known AI tools by looking
for tool-specific folders and binaries.
"""

from __future__ import annotations

import logging
import os
import platform
from typing import Any

log = logging.getLogger("agentic_os.local_discovery.filesystem_scanner")

# Tool type → (list of subdirectory/organisation folder names to look for,
#               list of binary names to check inside).
_TOOL_FS_PATTERNS: dict[str, tuple[list[str], list[str]]] = {
    "ollama": (["Ollama"], ["ollama", "ollama.exe", "ollama-app"]),
    "lm-studio": (["LM Studio", "lm-studio"], ["lm-studio", "LM Studio.exe"]),
    "docker": (["Docker", "Docker Desktop"], ["docker", "docker.exe"]),
    "git": (["Git"], ["git", "git.exe"]),
    "python": (["Python", "Python3"], ["python", "python3", "python.exe", "python3.exe"]),
    "node": (["Node.js", "nodejs"], ["node", "node.exe"]),
    "hermes": (["Hermes", "HermesAgent", "hermes"], ["hermes", "hermes-agent", "hermes.exe"]),
    "claude-code": (["Claude"], ["claude", "claude.exe"]),
    "codex": (["Codex", "Codex CLI"], ["codex", "codex.exe"]),
    "opencode": (["OpenCode", "opencode"], ["opencode", "opencode.exe"]),
    "aider": (["Aider", "aider"], ["aider", "aider.exe"]),
    "continue": (["Continue", ".continue"], ["continue", "continue.exe"]),
    "openhands": (["OpenHands", "openhands"], ["openhands", "openhands.exe"]),
    "vscode-cli": (["Visual Studio Code", "VS Code", "VSCode"], ["code", "code.exe"]),
    "gemini-cli": (["Gemini"], ["gemini", "gemini.exe"]),
    "vllm": (["vLLM", "vllm"], ["vllm", "vllm.exe"]),
}


class FilesystemScanner:
    """Scan common install directories for known AI tool installations.

    Platform-aware: checks ``%LOCALAPPDATA%``, ``%PROGRAMFILES%`` on
    Windows, ``/usr/local/bin``, ``/opt``, ``~/Applications`` on Linux/macOS.

    Thread-safety: not required — used from a single asyncio task.
    """

    def __init__(self) -> None:
        self._system = platform.system().lower()

    async def scan(self) -> list[dict[str, Any]]:
        """Scan common directories for known tool installations.

        Returns:
            A list of dicts with keys ``tool_type``, ``install_path``,
            ``version`` (empty string if undetected).  May be empty.

        Complexity: O(*d* × *p* × *f*) where *d* = directory count,
        *p* = pattern count, *f* = entries per directory.
        """
        results: list[dict[str, Any]] = []
        seen: set[str] = set()

        for base_dir in self._get_search_dirs():
            if not os.path.isdir(base_dir):
                continue
            try:
                entries = os.listdir(base_dir)
            except PermissionError:
                log.debug("Permission denied: %s", base_dir)
                continue

            for entry in entries:
                entry_lower = entry.lower()
                full_path = os.path.join(base_dir, entry)

                for tool_type, (folders, binaries) in _TOOL_FS_PATTERNS.items():
                    # Check folder name match
                    folder_match = any(f.lower() == entry_lower for f in folders)

                    if os.path.isdir(full_path) and folder_match:
                        # Look for known binaries inside the folder.
                        for binary in binaries:
                            bin_path = os.path.join(full_path, binary)
                            if os.path.isfile(bin_path) and bin_path not in seen:
                                seen.add(bin_path)
                                results.append(
                                    {
                                        "tool_type": tool_type,
                                        "install_path": os.path.abspath(bin_path),
                                        "version": "",
                                    }
                                )
                                break

                    # Also check if the entry itself is a known binary
                    elif os.path.isfile(full_path):
                        if entry_lower in binaries and full_path not in seen:
                            seen.add(full_path)
                            results.append(
                                {
                                    "tool_type": tool_type,
                                    "install_path": os.path.abspath(full_path),
                                    "version": "",
                                }
                            )

        return results

    # ── Internals ───────────────────────────────────────────────────────────

    def _get_search_dirs(self) -> list[str]:
        """Return the list of directories to search, in priority order."""
        system = self._system
        dirs: list[str] = []

        if system == "windows":
            local_appdata = os.environ.get("LOCALAPPDATA", "")
            appdata = os.environ.get("APPDATA", "")
            prog_files = os.environ.get("PROGRAMFILES", "C:\\Program Files")
            prog_files_x86 = os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)")
            user_profile = os.environ.get("USERPROFILE", "C:\\Users\\Default")

            dirs.extend(
                d
                for d in (
                    os.path.join(local_appdata, "Programs") if local_appdata else "",
                    local_appdata,
                    appdata,
                    prog_files,
                    prog_files_x86,
                    os.path.join(user_profile, ".local", "bin"),
                    os.path.join(user_profile, ".cargo", "bin"),
                )
                if d
            )
        else:
            home = os.path.expanduser("~")
            dirs.extend(
                [
                    os.path.join(home, ".local", "bin"),
                    os.path.join(home, "Applications"),
                    "/usr/local/bin",
                    "/opt",
                    "/Applications",
                    "/usr/local",
                    "/snap/bin",
                ]
            )

        return dirs
