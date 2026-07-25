"""Path scanner for local agent discovery.

Provides :class:`ExecutableLocator` (find executables in ``PATH`` or common
directories) and :class:`PathScanner` (batch-scan ``PATH`` for known AI tools).
"""

from __future__ import annotations

import logging
import os
import platform
import shutil

log = logging.getLogger("agentic_os.local_discovery.path_scanner")

# Known tools with their possible executable names (no extension — platform
# detection adds .exe, .cmd, .bat on Windows automatically).
KNOWN_TOOLS: dict[str, list[str]] = {
    "hermes": ["hermes", "hermes-agent"],
    "claude-code": ["claude"],
    "codex": ["codex"],
    "gemini-cli": ["gemini"],
    "opencode": ["opencode"],
    "aider": ["aider"],
    "openhands": ["openhands"],
    "ollama": ["ollama"],
    "lm-studio": [],
    "vllm": ["vllm"],
    "docker": ["docker"],
    "git": ["git"],
    "python": ["python", "python3"],
    "node": ["node"],
    "vscode-cli": ["code"],
}


class ExecutableLocator:
    """Finds executables in ``PATH`` or common install directories.

    *Windows:* appends ``.exe``, ``.cmd``, ``.bat`` automatically.
    *Linux / macOS:* checks the executable bit via ``shutil.which``.
    """

    def __init__(self) -> None:
        self._system = platform.system().lower()
        # Extensions to try on each platform (empty string = bare name).
        self._extensions: tuple[str, ...] = (
            (".exe", ".cmd", ".bat", "") if self._system == "windows" else ("",)
        )

    # ── Public API ──────────────────────────────────────────────────────────

    def find_in_path(self, name: str) -> str | None:
        """Search **PATH** for *name*, returning the first absolute path.

        Complexity: O(*n*) where *n* is the number of PATH directories.
        """
        if self._system == "windows":
            best: str | None = None
            for ext in self._extensions:
                candidate = shutil.which(name + ext) if ext else shutil.which(name)
                if candidate and (best is None or len(candidate) < len(best)):
                    best = os.path.abspath(candidate)
            return best

        candidate = shutil.which(name)
        return os.path.abspath(candidate) if candidate else None

    def find_in_common_dirs(self, name: str) -> list[str]:
        """Search common installation directories for *name*.

        Returns a (possibly empty) list of absolute paths to matching
        executables found in platform-specific install roots.

        Complexity: O(*d* × *f*) where *d* is directory count, *f* is
        listing size per directory.
        """
        results: list[str] = []
        for base in self._get_common_dirs():
            if not os.path.isdir(base):
                continue
            try:
                entries = os.listdir(base)
            except PermissionError:
                log.debug("Permission denied listing %s", base)
                continue

            for entry in entries:
                full = os.path.join(base, entry)
                try:
                    if os.path.isfile(full):
                        stem, _ = os.path.splitext(entry)
                        if stem.lower() == name.lower():
                            results.append(os.path.abspath(full))
                    elif os.path.isdir(full):
                        # Check inside the directory for a matching binary.
                        inner_path = os.path.join(full, name)
                        if os.path.isfile(inner_path) and os.access(inner_path, os.X_OK):
                            results.append(os.path.abspath(inner_path))
                except PermissionError:
                    continue
        return results

    # ── Internals ───────────────────────────────────────────────────────────

    def _get_common_dirs(self) -> list[str]:
        """Return a list of common install roots for the current platform."""
        system = self._system
        dirs: list[str] = []

        if system == "windows":
            prog_files = os.environ.get("PROGRAMFILES", "C:\\Program Files")
            prog_files_x86 = os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)")
            local_appdata = os.environ.get("LOCALAPPDATA", "")
            appdata = os.environ.get("APPDATA", "")
            user_profile = os.environ.get("USERPROFILE", "C:\\Users\\Default")

            dirs.append(prog_files)
            dirs.append(prog_files_x86)
            dirs.extend(d for d in (local_appdata, os.path.join(local_appdata, "Programs")) if d)
            dirs.extend(d for d in (appdata, os.path.join(user_profile, ".local", "bin")) if d)
        else:
            home = os.path.expanduser("~")
            dirs.extend(
                [
                    os.path.join(home, ".local", "bin"),
                    "/usr/local/bin",
                    "/opt",
                    "/Applications",
                    "/usr/bin",
                    "/bin",
                ]
            )

        return dirs


class PathScanner:
    """Batch-scan ``PATH`` for known AI tools.

    Iterates every executable name registered in :data:`KNOWN_TOOLS` and
    returns the first match found in the system ``PATH``.
    """

    def __init__(self, locator: ExecutableLocator | None = None) -> None:
        self._locator = locator or ExecutableLocator()

    def scan_all(self) -> list[tuple[str, str]]:
        """Scan ``PATH`` for all known tools.

        Returns:
            A list of ``(tool_type, executable_path)`` tuples for every
            tool found in the system ``PATH``.

        Complexity: O(*t* × *p*) where *t* = tool count, *p* = PATH dirs.
        """
        results: list[tuple[str, str]] = []
        for tool_type, exec_names in KNOWN_TOOLS.items():
            if not exec_names:
                continue
            for exe_name in exec_names:
                path = self._locator.find_in_path(exe_name)
                if path:
                    results.append((tool_type, path))
                    break
        return results
