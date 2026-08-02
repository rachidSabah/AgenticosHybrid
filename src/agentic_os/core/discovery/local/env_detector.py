"""Environment variable detector for local agent discovery.

Checks well-known environment variables for tool paths / config and
detects Python, Node.js, and Docker availability through subprocess
invocation.
"""

from __future__ import annotations

import asyncio
import logging
import os
import platform
import sys
from typing import Any

log = logging.getLogger("agentic_os.local_discovery.env_detector")

# Environment variables that may point to tool installation paths or config.
_ENV_VAR_CHECKS: dict[str, tuple[str, ...]] = {
    "claude-code": ("CLAUDE_CONFIG", "CLAUDE_HOME"),
    "hermes": ("HERMES_CONFIG", "HERMES_HOME"),
    "ollama": ("OLLAMA_HOST", "OLLAMA_MODELS"),
    "docker": ("DOCKER_HOST", "DOCKER_CONFIG"),
    "python": ("PYTHONPATH", "PYTHON_HOME", "PYTHONHOME"),
    "node": ("NODE_PATH", "NVM_BIN"),
}


class EnvironmentDetector:
    """Detect tools and runtimes via environment variables and subprocess.

    Reads well-known environment variables, detects Python / Node.js
    versions from the running process or subprocess, and checks Docker
    availability.

    Thread-safety: not required — used from a single asyncio task.
    """

    def __init__(self) -> None:
        self._system = platform.system().lower()

    async def scan(self) -> dict[str, Any]:
        """Run all environment-based detection strategies.

        Returns:
            A dict with keys:

            * ``env_vars`` — ``{tool_type: {var: value}}``
            * ``python_version`` — detected Python version string or ``""``
            * ``node_version`` — detected Node.js version string or ``""``
            * ``docker_available`` — ``bool``
            * ``system`` — platform identifier

        Complexity: O(*v* + *s*) where *v* = env var count and
        *s* = subprocess invocations (2–3).
        """
        result: dict[str, Any] = {
            "env_vars": {},
            "python_version": "",
            "node_version": "",
            "docker_available": False,
            "system": self._system,
        }

        # ── Environment variable checks ──
        for tool_type, vars_to_check in _ENV_VAR_CHECKS.items():
            found: dict[str, str] = {}
            for var in vars_to_check:
                val = os.environ.get(var, "")
                if val:
                    found[var] = val
                    log.debug("Detected %s = %s from env var %s", tool_type, val, var)
            if found:
                result["env_vars"][tool_type] = found

        # ── Python version ──
        ver = sys.version_info
        result["python_version"] = f"{ver.major}.{ver.minor}.{ver.micro}"

        # ── Node.js version ──
        node_version = await self._get_node_version()
        if node_version:
            result["node_version"] = node_version

        # ── Docker availability ──
        result["docker_available"] = await self._check_docker()

        return result

    # ── Internals ───────────────────────────────────────────────────────────

    async def _get_node_version(self) -> str:
        """Return ``node --version`` output, or ``""``."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "node",
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
            if proc.returncode == 0:
                ver = stdout.decode("utf-8", errors="replace").strip()
                return ver.lstrip("v") if ver else ""
        except (TimeoutError, FileNotFoundError, OSError):
            pass
        return ""

    async def _check_docker(self) -> bool:
        """Check if ``docker`` is available and responsive."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker",
                "info",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=5.0)
            return proc.returncode == 0
        except (TimeoutError, FileNotFoundError, OSError):
            return False
