"""AgentScanner — coordinates all local agent detection strategies.

Runs every individual scanner in parallel where possible and combines
results into a unified list of discovered tool metadata.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from agentic_os.core.discovery.local.env_detector import EnvironmentDetector
from agentic_os.core.discovery.local.filesystem_scanner import FilesystemScanner
from agentic_os.core.discovery.local.path_scanner import PathScanner
from agentic_os.core.discovery.local.process_scanner import ProcessScanner
from agentic_os.core.discovery.local.registry_scanner import RegistryScanner
from agentic_os.core.discovery.local.version_detector import VersionDetector

log = logging.getLogger("agentic_os.local_discovery.scanner")


# ── Known-tool registry used across all scanners ───────────────────
# (tool_type, display_name) for every tool the system can detect.
KNOWN_TOOL_TYPES: tuple[str, ...] = (
    "hermes",
    "claude-code",
    "codex",
    "gemini-cli",
    "opencode",
    "aider",
    "continue",
    "openhands",
    "ollama",
    "lm-studio",
    "vllm",
    "docker",
    "git",
    "python",
    "node",
    "vscode-cli",
)


class AgentScanner:
    """Master coordinator for all local agent detection strategies.

    Wires together :class:`PathScanner`, :class:`FilesystemScanner`,
    :class:`RegistryScanner`, :class:`ProcessScanner`,
    :class:`EnvironmentDetector`, and :class:`VersionDetector` into a
    single ``scan()`` entry point.

    Thread-safety: create per-call or reuse with care — the underlying
    :class:`VersionDetector` caches results for the lifetime of this
    object.
    """

    def __init__(
        self,
        path_scanner: PathScanner | None = None,
        filesystem_scanner: FilesystemScanner | None = None,
        registry_scanner: RegistryScanner | None = None,
        process_scanner: ProcessScanner | None = None,
        env_detector: EnvironmentDetector | None = None,
        version_detector: VersionDetector | None = None,
    ) -> None:
        self._path_scanner = path_scanner or PathScanner()
        self._fs_scanner = filesystem_scanner or FilesystemScanner()
        self._reg_scanner = registry_scanner or RegistryScanner()
        self._proc_scanner = process_scanner or ProcessScanner()
        self._env_detector = env_detector or EnvironmentDetector()
        self._version_detector = version_detector or VersionDetector()

    # ── Main scan ───────────────────────────────────────────────────────────

    async def scan(
        self,
        enabled_tools: tuple[str, ...] | None = None,
    ) -> list[tuple[str, str, str]]:
        """Run all detection strategies and return unified results.

        Returns:
            A list of ``(tool_type, executable_path, version)`` tuples.
            Each tool type appears at most once (first-found wins).

        Complexity: O(*S*) where *S* is the sum of each sub-scanner's
        complexity.  Sub-scanners run concurrently where possible.
        """
        enabled = set(enabled_tools or KNOWN_TOOL_TYPES)

        # ── Run independent scanners concurrently ──
        path_task = asyncio.to_thread(self._path_scanner.scan_all)  # [(tool_type, path)]
        fs_task = asyncio.create_task(  # [{tool_type, install_path, version}]
            self._fs_scanner.scan()
        )
        reg_task = asyncio.create_task(self._reg_scanner.scan())  # [{tool_type, ...}]
        proc_task = asyncio.create_task(self._proc_scanner.scan())  # [{tool_type, pid, ...}]
        env_task = asyncio.create_task(self._env_detector.scan())  # {env_vars, ...}

        path_results: list[tuple[str, str]] = await path_task
        fs_results: list[dict[str, Any]] = await fs_task
        reg_results: list[dict[str, Any]] = await reg_task
        proc_results: list[dict[str, Any]] = await proc_task
        await env_task  # Environment info fetched but not used for tool-path resolution

        # ── Build a unified map ──
        # Priority: PATH > filesystem > registry
        # (PATH entries are most likely the actual invocation path)
        seen: dict[str, str] = {}  # tool_type → executable_path
        version_lookup: dict[str, str] = {}  # tool_type → version (from registry/filesystem)

        # Helper: add path if tool is enabled and not already seen.
        def _add(tool_type: str, exe_path: str) -> None:
            if tool_type not in enabled:
                return
            if tool_type not in seen:
                seen[tool_type] = exe_path

        # 1. PATH results (highest priority)
        for tool_type, exe_path in path_results:
            _add(tool_type, exe_path)

        # 2. Filesystem results
        for item in fs_results:
            tt = item["tool_type"]
            install_path = item["install_path"]
            ver = item.get("version", "")
            if tt not in seen:
                _add(tt, install_path)
            if ver and tt not in version_lookup:
                version_lookup[tt] = ver

        # 3. Registry results
        for item in reg_results:
            tt = item["tool_type"]
            install_path = item.get("install_path", "")
            ver = item.get("version", "")
            if install_path and tt not in seen:
                _add(tt, install_path)
            if ver and tt not in version_lookup:
                version_lookup[tt] = ver

        # 4. Process results — add PID info for matching
        process_tools: dict[str, dict[str, Any]] = {}
        for item in proc_results:
            tt = item["tool_type"]
            if tt in enabled and tt not in process_tools:
                process_tools[tt] = item

        # Also check for tools seen only in process list (no PATH entry yet)
        for tt in enabled:
            if tt not in seen and tt in process_tools:
                # We know it's running — try to find its executable path
                exe_path = process_tools[tt].get("name", "")
                if exe_path:
                    seen[tt] = exe_path

        # ── Resolve versions ──
        # Build version-detection batch for tools we found
        version_batch: list[tuple[str, str]] = [
            (tt, path) for tt, path in seen.items() if tt not in version_lookup
        ]
        if version_batch:
            version_results = await self._version_detector.get_versions_batch(version_batch)
            for tt, _, ver in version_results:
                if ver:
                    version_lookup[tt] = ver

        # ── Assemble final result ──
        results: list[tuple[str, str, str]] = []
        for tool_type in sorted(seen.keys()):
            results.append(
                (
                    tool_type,
                    seen[tool_type],
                    version_lookup.get(tool_type, ""),
                )
            )

        return results

    # ── Accessors ───────────────────────────────────────────────────────────

    @property
    def version_detector(self) -> VersionDetector:
        """Access the underlying :class:`VersionDetector` (useful for cache control)."""
        return self._version_detector
