"""Version detector for local agent discovery.

Runs ``<executable> --version`` (or ``--help`` as a fallback), parses
output against known patterns, and caches results to avoid re-running
expensive subprocess calls.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import re
import subprocess

log = logging.getLogger("agentic_os.local_discovery.version_detector")

# ── Version command and parsing strategy per tool type ──────────────
# Each entry: (flag, list of regex patterns to try in order)
_VERSION_STRATEGIES: dict[str, tuple[str, list[str]]] = {
    "hermes": (
        "--version",
        [
            r"(?:Hermes|hermes)\s+(?:Agent\s+)?v?(\d[\w.]*)",
            r"v?(\d+\.\d+\.\d+)",
        ],
    ),
    "claude-code": ("--version", [r"Claude(?:\s+Code)?\s+v?(\d[\w.]*)", r"v?(\d+\.\d+\.\d+)"]),
    "codex": ("--version", [r"Codex(?:\s+CLI)?\s+v?(\d[\w.]*)", r"v?(\d+\.\d+\.\d+)"]),
    "gemini-cli": ("--version", [r"gemini(?:\s+CLI)?\s+v?(\d[\w.]*)", r"v?(\d+\.\d+\.\d+)"]),
    "opencode": ("--version", [r"opencode\s+v?(\d[\w.]*)", r"v?(\d+\.\d+\.\d+)"]),
    "aider": ("--version", [r"aider\s+v?(\d[\w.]*)", r"v?(\d+\.\d+\.\d+)"]),
    "ollama": ("--version", [r"ollama\s+(?:version\s+is\s+)?v?(\d[\w.]*)", r"v?(\d+\.\d+\.\d+)"]),
    "docker": ("--version", [r"Docker\s+version\s+v?(\d[\w.]*)", r"v?(\d+\.\d+\.\d+)"]),
    "git": ("--version", [r"git\s+version\s+v?(\d[\w.]*)", r"v?(\d+\.\d+\.\d+)"]),
    "python": ("--version", [r"Python\s+(\d[\w.]*)", r"(\d+\.\d+\.\d+)"]),
    "node": ("--version", [r"v?(\d+\.\d+\.\d+)"]),
    "vscode-cli": ("--version", [r"(\d+\.\d+\.\d+)"]),
    "vllm": ("--version", [r"vllm\s+v?(\d[\w.]*)", r"v?(\d+\.\d+\.\d+)"]),
}


def _run_version_capture(
    executable_path: str, flag: str, timeout: float
) -> subprocess.CompletedProcess[bytes]:
    """Run *executable_path flag*, capturing output (typed for ty)."""
    proc = subprocess.Popen(
        [executable_path, flag],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
    )
    try:
        out, err = proc.communicate(timeout=timeout)
        return subprocess.CompletedProcess(proc.args, proc.returncode, out, err)
    except subprocess.TimeoutExpired:
        if os.name == "nt" and proc.pid:
            with contextlib.suppress(Exception):
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
        else:
            proc.kill()
        with contextlib.suppress(Exception):
            proc.communicate()
        raise


class VersionDetector:
    """Detect tool versions by running ``--version`` subprocess.

    Caches results in an internal ``dict[str, str]`` so the same
    executable is never invoked twice.

    Thread-safety: not required — use from a single asyncio task or
    protect the cache with a lock if shared.
    """

    def __init__(self) -> None:
        self._cache: dict[str, str] = {}
        self._timeout: float = 2.0

    async def get_version(self, executable_path: str, tool_type: str) -> str:
        """Detect version for *tool_type* at *executable_path*.

        Returns the version string (e.g. ``"2.1.0"``) or ``""`` if
        detection fails.

        Complexity: O(1) cache hit; O(1) subprocess + O(*r*) regex
        evaluation on cache miss, where *r* = pattern count (≤ 2).
        """
        # Cache keyed by absolute path so different tools at different
        # locations don't collide.
        cache_key = executable_path
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        strategy = _VERSION_STRATEGIES.get(tool_type)
        if strategy is None:
            self._cache[cache_key] = ""
            return ""

        flag, patterns = strategy
        version = await self._run_version_command(executable_path, flag, patterns)
        self._cache[cache_key] = version
        return version

    async def get_versions_batch(
        self, executables: list[tuple[str, str]]
    ) -> list[tuple[str, str, str]]:
        """Detect versions for a batch of (tool_type, executable_path) pairs.

        Returns:
            List of ``(tool_type, executable_path, version)`` tuples.
            Version is ``""`` when detection fails.
        """
        if not executables:
            return []

        sem = asyncio.Semaphore(6)

        async def _probe(tool_type: str, exe_path: str) -> tuple[str, str, str]:
            async with sem:
                version = await self.get_version(exe_path, tool_type)
                return (tool_type, exe_path, version)

        return list(await asyncio.gather(*(_probe(t, p) for t, p in executables)))

    def clear_cache(self) -> None:
        """Reset the version cache."""
        self._cache.clear()

    def get_cache_size(self) -> int:
        """Return the number of cached version results."""
        return len(self._cache)

    # ── Internals ───────────────────────────────────────────────────────────

    async def _run_version_command(
        self, executable_path: str, flag: str, patterns: list[str]
    ) -> str:
        """Run *executable_path flag* and parse output with *patterns*."""
        try:
            result = await asyncio.to_thread(
                _run_version_capture, executable_path, flag, self._timeout
            )
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
            log.debug("Version detection failed for %s: %s", executable_path, exc)
            return ""

        output = (
            ((result.stdout or b"") + (result.stderr or b""))
            .decode("utf-8", errors="replace")
            .strip()
        )
        return self._parse_version(output, patterns)

    @staticmethod
    def _parse_version(output: str, patterns: list[str]) -> str:
        """Return the first version string matching any *patterns* in *output*."""
        for pat in patterns:
            m = re.search(pat, output)
            if m:
                return m.group(1)
        return ""
