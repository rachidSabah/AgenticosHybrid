"""Windows Registry scanner for local agent discovery.

On Windows, uses the ``reg`` command to query ``HKCU`` / ``HKLM`` uninstall
keys.  On Linux / macOS returns an empty list gracefully.
"""

from __future__ import annotations

import asyncio
import logging
import platform
import re
from typing import Any

log = logging.getLogger("agentic_os.local_discovery.registry_scanner")

# Registry paths known to contain tool entries.
_REGISTRY_PATHS: tuple[str, ...] = (
    "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall",
    "HKLM\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall",
    "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\App Paths",
)

# Substrings to match in registry display names for known tools.
_TOOL_REGISTRY_PATTERNS: tuple[tuple[str, str, str], ...] = (
    # (tool_type, search_fragment, key_suffix_override)
    ("hermes", "Hermes", ""),
    ("claude-code", "Claude", ""),
    ("codex", "Codex CLI", ""),
    ("ollama", "Ollama", ""),
    ("docker", "Docker", ""),
    ("git", "Git", ""),
    ("python", "Python 3", ""),
    ("node", "Node.js", ""),
    ("vscode-cli", "Visual Studio Code", ""),
    ("lm-studio", "LM Studio", ""),
)


class RegistryScanner:
    """Scan the Windows Registry for installed AI tools.

    Uses the ``reg`` command-line tool (available on all Windows versions).
    On non-Windows platforms :meth:`scan` returns an empty list.

    Thread-safety: not required — instances are used from a single
    asyncio task.
    """

    def __init__(self) -> None:
        self._system = platform.system().lower()
        self._on_windows = self._system == "windows"

    async def scan(self) -> list[dict[str, Any]]:
        """Run registry queries for known tool patterns.

        Returns:
            A list of dicts with keys ``tool_type``, ``name``,
            ``version``, ``install_path``.  Empty on non-Windows
            or when ``reg`` is unavailable.

        Complexity: O(*k* × *p*) where *k* = key count and *p* =
        pattern count.  Each ``reg query`` is a subprocess call.
        """
        if not self._on_windows:
            log.debug("RegistryScanner skipped — not on Windows")
            return []

        results: list[dict[str, Any]] = []
        for reg_path in _REGISTRY_PATHS:
            try:
                items = await self._query_reg_path(reg_path)
            except FileNotFoundError:
                log.debug("reg command not found — skipping registry scan")
                return []
            except Exception:
                log.warning("Registry query failed for %s", reg_path, exc_info=True)
                continue

            for item in items:
                display_name = item.get("DisplayName", "")
                install_path = item.get("InstallLocation", "")
                version = item.get("DisplayVersion", "")

                for tool_type, frag, _ in _TOOL_REGISTRY_PATTERNS:
                    if frag.lower() in display_name.lower():
                        results.append(
                            {
                                "tool_type": tool_type,
                                "name": display_name,
                                "version": version,
                                "install_path": install_path,
                            }
                        )
                        break

        return results

    # ── Internals ───────────────────────────────────────────────────────────

    async def _query_reg_path(self, reg_path: str) -> list[dict[str, str]]:
        """Execute ``reg query`` for a single key and parse output.

        Returns a list of sub-key dicts with ``DisplayName``,
        ``DisplayVersion``, ``InstallLocation`` etc.
        """
        proc = await asyncio.create_subprocess_exec(
            "reg",
            "query",
            reg_path,
            "/s",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10.0)
        except TimeoutError:
            proc.kill()
            await proc.wait()
            log.warning("Registry query timed out for %s", reg_path)
            return []

        if proc.returncode != 0:
            return []  # Key may not exist

        return self._parse_reg_output(stdout.decode("utf-8", errors="replace"))

    @staticmethod
    def _parse_reg_output(text: str) -> list[dict[str, str]]:
        """Parse multi-line ``reg query`` output into sub-key dicts."""
        items: list[dict[str, str]] = []
        current: dict[str, str] = {}
        # Standard reg output pattern: lines like "    DisplayName    REG_SZ    Value"
        pattern = re.compile(r"^\s{4}(.+?)\s{4}\w+\s{4}(.+)$")

        for line in text.splitlines():
            if not line.strip():
                if current:
                    items.append(current)
                    current = {}
                continue

            m = pattern.match(line)
            if m:
                key = m.group(1).strip()
                value = m.group(2).strip()
                current[key] = value

        if current:
            items.append(current)

        return items
