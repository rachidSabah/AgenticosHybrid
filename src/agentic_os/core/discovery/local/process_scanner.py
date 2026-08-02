"""Process scanner for local agent discovery.

Scans running processes for known AI tool executables via
``tasklist`` (Windows) or ``ps aux`` (Linux/macOS).
"""

from __future__ import annotations

import asyncio
import logging
import os
import platform
from typing import Any

log = logging.getLogger("agentic_os.local_discovery.process_scanner")

# Tool type → list of process-name fragments (case-insensitive match).
_TOOL_PROCESS_NAMES: dict[str, list[str]] = {
    "hermes": ["hermes", "hermes-agent"],
    "claude-code": ["claude"],
    "codex": ["codex"],
    "gemini-cli": ["gemini"],
    "opencode": ["opencode"],
    "aider": ["aider"],
    "ollama": ["ollama"],
    "docker": ["docker"],
    "vllm": ["vllm"],
    "python": ["python"],
    "node": ["node"],
    "lm-studio": ["lm-studio", "lmstudio"],
}


class ProcessScanner:
    """Scan running processes for known AI tool names.

    Platform-aware: uses ``tasklist /FO CSV`` on Windows and
    ``ps aux`` on Linux/macOS.

    Thread-safety: not required — used from a single asyncio task.
    """

    def __init__(self) -> None:
        self._system = platform.system().lower()

    async def scan(self) -> list[dict[str, Any]]:
        """List running processes and return matches.

        Returns:
            A list of dicts with keys ``tool_type``, ``pid``,
            ``memory_mb``, ``cpu_percent``, ``name``.

        Complexity: O(*n* × *t*) where *n* = process count and
        *t* = tool count.
        """
        if self._system == "windows":
            return await self._scan_windows()
        return await self._scan_posix()

    async def _scan_windows(self) -> list[dict[str, Any]]:
        """Parse ``tasklist /FO CSV`` output."""
        results: list[dict[str, Any]] = []
        try:
            proc = await asyncio.create_subprocess_exec(
                "tasklist",
                "/FO",
                "CSV",
                "/NH",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10.0)
        except (TimeoutError, FileNotFoundError) as exc:
            log.warning("tasklist failed: %s", exc)
            return []

        text = stdout.decode("utf-8", errors="replace")
        for line in text.splitlines():
            line = line.strip().strip('"')
            if not line:
                continue
            parts = line.split('","')
            if len(parts) < 5:
                continue
            proc_name = parts[0].strip('"').lower()
            pid_str = parts[1].strip('"')
            mem_str = parts[4].strip('"') if len(parts) > 4 else "0"

            match = self._match_process_name(proc_name)
            if match is None:
                continue

            pid = int(pid_str) if pid_str.isdigit() else 0
            # tasklist memory format: "12,345 K" or "12,345"
            mem_kb = 0.0
            mem_clean = mem_str.replace(",", "").replace(" ", "").upper()
            if mem_clean.endswith("K"):
                mem_kb = float(mem_clean[:-1])
            elif mem_clean.endswith("M"):
                mem_kb = float(mem_clean[:-1]) * 1024
            elif mem_clean:
                try:
                    mem_kb = float(mem_clean)
                except ValueError:
                    mem_kb = 0.0

            results.append(
                {
                    "tool_type": match,
                    "pid": pid,
                    "memory_mb": round(mem_kb / 1024, 1),
                    "cpu_percent": 0.0,
                    "name": parts[0].strip('"'),
                }
            )

        return results

    async def _scan_posix(self) -> list[dict[str, Any]]:
        """Parse ``ps aux`` output."""
        results: list[dict[str, Any]] = []
        try:
            proc = await asyncio.create_subprocess_exec(
                "ps",
                "aux",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10.0)
        except (TimeoutError, FileNotFoundError) as exc:
            log.warning("ps aux failed: %s", exc)
            return []

        text = stdout.decode("utf-8", errors="replace")
        lines = text.splitlines()
        if not lines:
            return []
        # Skip header line
        header = lines[0].lower()
        # Determine column indices from header
        cols = header.split()
        try:
            pid_idx = cols.index("pid")
            cpu_idx = cols.index("%cpu")
            mem_idx = cols.index("%mem")
            cmd_idx = self._find_cmd_idx(cols)
        except ValueError:
            cmd_idx = len(cols) - 1  # Assume last column is command
            pid_idx = 1
            cpu_idx = 2
            mem_idx = 3

        for line in lines[1:]:
            parts = line.split(None, cmd_idx)
            if len(parts) < cmd_idx + 1:
                continue
            cmd = parts[cmd_idx] if cmd_idx < len(parts) else ""
            proc_name = os.path.basename(cmd).lower()

            match = self._match_process_name(proc_name)
            if match is None:
                continue

            pid = int(parts[pid_idx]) if pid_idx < len(parts) else 0
            cpu = float(parts[cpu_idx]) if cpu_idx < len(parts) else 0.0
            mem_pct = float(parts[mem_idx]) if mem_idx < len(parts) else 0.0

            results.append(
                {
                    "tool_type": match,
                    "pid": pid,
                    "memory_mb": mem_pct,  # %MEM on ps aux (approximation)
                    "cpu_percent": cpu,
                    "name": os.path.basename(cmd),
                }
            )

        return results

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _match_process_name(self, proc_name: str) -> str | None:
        """Return the *tool_type* whose process name fragments match *proc_name*.

        Case-insensitive substring match against each fragment list.
        """
        proc_lower = proc_name.lower()
        for tool_type, fragments in _TOOL_PROCESS_NAMES.items():
            for frag in fragments:
                if frag.lower() in proc_lower:
                    return tool_type
        return None

    @staticmethod
    def _find_cmd_idx(cols: list[str]) -> int:
        """Find the index of the command column in ``ps`` output.

        The command column is usually the last variable-width column;
        we scan for known metadata column names and pick the first
        one that isn't recognised.
        """
        known = {"pid", "%cpu", "%mem", "rss", "vsz", "tt", "stat", "started", "time", "user"}
        for i, col in enumerate(cols):
            if col not in known:
                return i
        return len(cols) - 1
