"""RuntimeBridge — runtime connectors for local CLI AI brains.

Provides version, capability, status, and workspace queries for known
local CLI brains: Claude Code, Hermes, Gemini CLI, Codex, OpenCode,
Aider, and Continue.

Each connector attempts to find the brain's executable and run brief
subprocess queries to determine version, capabilities, and operational
status.  Results are packaged into :class:`BrainRecord` fragments that
can be used by the registry.
"""

from __future__ import annotations

import asyncio
import os
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from agentic_os.domain.brains import (
    BrainRecord,
    BrainRuntime,
    BrainStatus,
    BrainType,
    BrainVendor,
    WorkspaceInfo,
)
from agentic_os.infrastructure.logging import get_logger

log = get_logger("brains.runtime_bridge")


@dataclass(frozen=True)
class RuntimeInfo:
    """Information about a detected runtime executable."""

    tool_type: str
    display_name: str
    vendor: BrainVendor
    executable: str = ""
    version: str = ""
    installed: bool = False
    status: BrainStatus = BrainStatus.DISCOVERED
    capabilities: tuple[str, ...] = field(default_factory=tuple)


# ── Connector protocol ──────────────────────────────────────────────────────


class BrainConnector:
    """Abstract interface for a CLI brain connector.

    Subclasses override :meth:`detect` to query a specific CLI brain.
    """

    tool_type: str = ""
    display_name: str = ""
    vendor: BrainVendor = BrainVendor.CUSTOM

    async def detect(self) -> RuntimeInfo:
        """Detect the brain on the local system.

        Returns:
            A :class:`RuntimeInfo` with detection results.
        """
        raise NotImplementedError

    async def query_status(self) -> dict[str, Any]:
        """Query current operational status.

        Returns:
            A dict with keys like ``{"status": ..., "pid": ..., "memory_mb": ...}``.
        """
        raise NotImplementedError

    async def query_workspace(self) -> WorkspaceInfo:
        """Query current workspace information.

        Returns:
            A :class:`WorkspaceInfo` describing the brain's workspace.
        """
        raise NotImplementedError

    async def query_sessions(self) -> list[dict[str, Any]]:
        """Query active sessions.

        Returns:
            A list of session dicts.
        """
        raise NotImplementedError

    async def to_brain_record(self, info: RuntimeInfo) -> BrainRecord:
        """Convert a :class:`RuntimeInfo` to a full :class:`BrainRecord`."""
        raise NotImplementedError


# ── Generic CLI connector (fallback) ────────────────────────────────────────


class _GenericCliConnector(BrainConnector):
    """Generic connector for CLI tools that respond to ``--version``."""

    def __init__(
        self,
        tool_type: str,
        display_name: str,
        vendor: BrainVendor,
        exe_name: str,
        version_args: tuple[str, ...] = ("--version",),
        extra_capabilities: tuple[str, ...] = (),
    ) -> None:
        self.tool_type = tool_type
        self.display_name = display_name
        self.vendor = vendor
        self._exe_name = exe_name
        self._version_args = version_args
        self._extra_capabilities = extra_capabilities

    async def detect(self) -> RuntimeInfo:
        try:
            exe_path = str(
                await asyncio.wait_for(
                    asyncio.to_thread(shutil.which, self._exe_name),
                    timeout=3.0,
                )
                or ""
            )
        except TimeoutError:
            exe_path = ""
        except Exception:
            exe_path = ""
        installed = bool(exe_path)
        version = ""

        if installed:
            try:
                proc = await asyncio.create_subprocess_exec(
                    exe_path,
                    *self._version_args,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10.0)
                version = stdout.decode("utf-8", errors="replace").strip()
            except (TimeoutError, FileNotFoundError, OSError):
                version = ""

        caps = [f"cli:{self._exe_name}"]
        if version:
            caps.append(f"version:{version.split()[0] if version else ''}")
        caps.extend(self._extra_capabilities)

        return RuntimeInfo(
            tool_type=self.tool_type,
            display_name=self.display_name,
            vendor=self.vendor,
            executable=exe_path,
            version=version,
            installed=installed,
            status=BrainStatus.DISCOVERED if installed else BrainStatus.REMOVED,
            capabilities=tuple(caps),
        )

    async def query_status(self) -> dict[str, Any]:
        return {"status": "unknown"}

    async def query_workspace(self) -> WorkspaceInfo:
        return WorkspaceInfo(workspace_path=os.getcwd())

    async def query_sessions(self) -> list[dict[str, Any]]:
        return []

    async def to_brain_record(self, info: RuntimeInfo) -> BrainRecord:
        runtime = BrainRuntime.UNKNOWN
        if self._exe_name.endswith(".py") or self._exe_name in ("hermes",):
            runtime = BrainRuntime.PYTHON
        elif self._exe_name in ("node", "npx"):
            runtime = BrainRuntime.NODE
        elif self._exe_name in ("go",):
            runtime = BrainRuntime.GO
        elif self._exe_name in ("codex", "claude", "opencode"):
            runtime = BrainRuntime.NATIVE

        return BrainRecord(
            id=uuid4().hex[:12],
            display_name=info.display_name,
            brain_type=BrainType.LOCAL_CLI,
            vendor=info.vendor,
            runtime=runtime,
            version=info.version,
            status=info.status,
            health=100.0 if info.installed else 0.0,
            capabilities=info.capabilities,
            workspace=info.executable,
            discovered_at=datetime.now(UTC).isoformat(),
            last_seen=datetime.now(UTC).isoformat(),
        )


# ── Concrete connectors ─────────────────────────────────────────────────────

_CLAUDE_CODE_EXE: str = os.environ.get("CLAUDE_CODE_CLI_PATH", "claude")


class ClaudeCodeConnector(_GenericCliConnector):
    """Connector for Anthropic's Claude Code CLI."""

    def __init__(self) -> None:
        super().__init__(
            tool_type="claude-code",
            display_name="Claude Code",
            vendor=BrainVendor.CLAUDE_CODE,
            exe_name=_CLAUDE_CODE_EXE,
            version_args=("--version",),
            extra_capabilities=(
                "chat",
                "code_generation",
                "file_editing",
                "tool_use",
                "terminal_access",
            ),
        )


class HermesConnector(_GenericCliConnector):
    """Connector for Hermes Agent."""

    def __init__(self) -> None:
        super().__init__(
            tool_type="hermes",
            display_name="Hermes Agent",
            vendor=BrainVendor.HERMES,
            exe_name="hermes",
            version_args=("--version",),
            extra_capabilities=(
                "chat",
                "tool_use",
                "multi_agent",
                "plugin_system",
            ),
        )


class GeminiCliConnector(_GenericCliConnector):
    """Connector for Google Gemini CLI."""

    def __init__(self) -> None:
        super().__init__(
            tool_type="gemini-cli",
            display_name="Gemini CLI",
            vendor=BrainVendor.GEMINI_CLI,
            exe_name="gemini",
            version_args=("--version",),
            extra_capabilities=(
                "chat",
                "vision",
                "code_generation",
            ),
        )


class CodexConnector(_GenericCliConnector):
    """Connector for OpenAI Codex CLI."""

    def __init__(self) -> None:
        super().__init__(
            tool_type="codex",
            display_name="Codex CLI",
            vendor=BrainVendor.CODEX,
            exe_name="codex",
            version_args=("--version",),
            extra_capabilities=(
                "chat",
                "code_generation",
                "file_editing",
            ),
        )


class OpenCodeConnector(_GenericCliConnector):
    """Connector for OpenCode CLI."""

    def __init__(self) -> None:
        super().__init__(
            tool_type="opencode",
            display_name="OpenCode",
            vendor=BrainVendor.OPENCODE,
            exe_name="opencode",
            version_args=("--version",),
            extra_capabilities=(
                "chat",
                "code_generation",
                "file_editing",
                "search",
            ),
        )


class AiderConnector(_GenericCliConnector):
    """Connector for Aider AI pair programming CLI."""

    def __init__(self) -> None:
        super().__init__(
            tool_type="aider",
            display_name="Aider",
            vendor=BrainVendor.AIDER,
            exe_name="aider",
            version_args=("--version",),
            extra_capabilities=(
                "chat",
                "code_generation",
                "file_editing",
                "git_integration",
            ),
        )


class ContinueConnector(_GenericCliConnector):
    """Connector for Continue (open-source AI code assistant)."""

    def __init__(self) -> None:
        super().__init__(
            tool_type="continue",
            display_name="Continue",
            vendor=BrainVendor.CONTINUE,
            exe_name="continue",
            version_args=("--version",),
            extra_capabilities=(
                "chat",
                "code_generation",
                "completion",
                "tool_use",
                "context_provider",
            ),
        )


# ── Runtime Bridge ──────────────────────────────────────────────────────────


class RuntimeBridge:
    """Runtime connector that detects and queries local CLI AI brains.

    Maintains a registry of all known connectors and provides methods
    to detect all brains, query individual status, and produce
    :class:`BrainRecord` objects suitable for the brain registry.

    Thread-safety
    -------------
    Internal state is guarded by an ``asyncio.Lock``.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._connectors: dict[str, BrainConnector] = {}
        self._cache: dict[str, RuntimeInfo] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Register all the built-in connectors."""
        connectors: list[BrainConnector] = [
            ClaudeCodeConnector(),
            HermesConnector(),
            GeminiCliConnector(),
            CodexConnector(),
            OpenCodeConnector(),
            AiderConnector(),
            ContinueConnector(),
        ]
        for c in connectors:
            self._connectors[c.tool_type] = c

    # ── Connector management ────────────────────────────────────────────────

    def register_connector(self, connector: BrainConnector) -> None:
        """Register a custom connector.

        Args:
            connector: A :class:`BrainConnector` instance.
        """
        self._connectors[connector.tool_type] = connector
        log.debug("Registered connector: %s", connector.tool_type)

    def get_connector(self, tool_type: str) -> BrainConnector | None:
        """Get a registered connector by tool type."""
        return self._connectors.get(tool_type)

    def list_connectors(self) -> list[BrainConnector]:
        """Return all registered connectors."""
        return list(self._connectors.values())

    def list_tool_types(self) -> list[str]:
        """Return the tool types of all registered connectors."""
        return list(self._connectors.keys())

    # ── Detection ───────────────────────────────────────────────────────────

    async def detect_all(self, use_cache: bool = True) -> list[RuntimeInfo]:
        """Run detection on all registered connectors.

        Args:
            use_cache: When ``True`` (default), return cached results
                if available instead of re-running detection.

        Returns:
            A list of :class:`RuntimeInfo` objects.
        """
        results: list[RuntimeInfo] = []
        tasks: list[asyncio.Task[RuntimeInfo]] = []
        for tool_type, connector in self._connectors.items():
            if use_cache:
                async with self._lock:
                    cached = self._cache.get(tool_type)
                    if cached is not None:
                        results.append(cached)
                        continue

            async def _detect_one(tt: str, conn: BrainConnector) -> RuntimeInfo:
                try:
                    return await asyncio.wait_for(conn.detect(), timeout=10.0)
                except TimeoutError:
                    log.warning("Detection timed out for %s", tt)
                    return RuntimeInfo(
                        tool_type=tt,
                        display_name=conn.display_name,
                        vendor=conn.vendor,
                        installed=False,
                        status=BrainStatus.REMOVED,
                    )
                except Exception as exc:
                    log.warning("Detection failed for %s: %s", tt, exc)
                    return RuntimeInfo(
                        tool_type=tt,
                        display_name=conn.display_name,
                        vendor=conn.vendor,
                        installed=False,
                        status=BrainStatus.REMOVED,
                    )

            tasks.append(asyncio.create_task(_detect_one(tool_type, connector)))

        if tasks:
            for task in asyncio.as_completed(tasks):
                info = await task
                async with self._lock:
                    self._cache[info.tool_type] = info
                results.append(info)

        return results

    async def detect_one(self, tool_type: str) -> RuntimeInfo | None:
        """Run detection on a single connector.

        Args:
            tool_type: The tool type to detect (e.g. ``"claude-code"``).

        Returns:
            A :class:`RuntimeInfo`, or ``None`` if the connector is
            not registered.
        """
        connector = self._connectors.get(tool_type)
        if connector is None:
            return None
        try:
            info = await connector.detect()
            async with self._lock:
                self._cache[tool_type] = info
            return info
        except Exception as exc:
            log.warning("Detection failed for %s: %s", tool_type, exc)
            return None

    async def clear_cache(self) -> None:
        """Clear the cached detection results."""
        async with self._lock:
            self._cache.clear()

    # ── Status & workspace queries ──────────────────────────────────────────

    async def query_status(self, tool_type: str) -> dict[str, Any]:
        """Query the current operational status of a brain.

        Args:
            tool_type: The tool type to query.

        Returns:
            A status dict, or ``{"status": "unknown"}`` if the connector
            is not registered.
        """
        connector = self._connectors.get(tool_type)
        if connector is None:
            return {"status": "unknown", "error": f"No connector for {tool_type}"}
        try:
            return await connector.query_status()
        except Exception as exc:
            log.warning("Status query failed for %s: %s", tool_type, exc)
            return {"status": "error", "error": str(exc)}

    async def query_workspace(self, tool_type: str) -> WorkspaceInfo:
        """Query the workspace information for a brain.

        Args:
            tool_type: The tool type to query.

        Returns:
            A :class:`WorkspaceInfo`, or a default empty one.
        """
        connector = self._connectors.get(tool_type)
        if connector is None:
            return WorkspaceInfo()
        try:
            return await connector.query_workspace()
        except Exception:
            return WorkspaceInfo()

    async def query_sessions(self, tool_type: str) -> list[dict[str, Any]]:
        """Query active sessions for a brain.

        Args:
            tool_type: The tool type to query.

        Returns:
            A list of session dicts, or an empty list.
        """
        connector = self._connectors.get(tool_type)
        if connector is None:
            return []
        try:
            return await connector.query_sessions()
        except Exception:
            return []

    # ── BrainRecord conversion ──────────────────────────────────────────────

    async def to_brain_record(self, tool_type: str) -> BrainRecord | None:
        """Produce a :class:`BrainRecord` for a detected brain.

        Runs detection first if no cached result is available, then
        delegates to the connector's ``to_brain_record``.

        Args:
            tool_type: The tool type to convert.

        Returns:
            A :class:`BrainRecord`, or ``None`` if the connector is
            not registered.
        """
        connector = self._connectors.get(tool_type)
        if connector is None:
            return None

        async with self._lock:
            info = self._cache.get(tool_type)
        if info is None:
            info = await self.detect_one(tool_type)
            if info is None:
                return None

        try:
            return await connector.to_brain_record(info)
        except Exception as exc:
            log.warning("Conversion failed for %s: %s", tool_type, exc)
            return None

    async def to_brain_records(self) -> list[BrainRecord]:
        """Produce :class:`BrainRecord` objects for all registered brains.

        Runs detection on all connectors and converts the results.
        """
        infos = await self.detect_all()
        records: list[BrainRecord] = []
        for info in infos:
            connector = self._connectors.get(info.tool_type)
            if connector is None:
                continue
            try:
                record = await connector.to_brain_record(info)
                records.append(record)
            except Exception as exc:
                log.warning("Conversion failed for %s: %s", info.tool_type, exc)
        return records

    async def detect_all_with_windows(self) -> list[BrainRecord]:
        """Run connector-based detection + Windows OS-level process scan.

        Returns a merged list of :class:`BrainRecord` objects from both
        the existing CLI-brain connectors and the real Windows process
        scanner (which detects running processes, MCP servers, Docker,
        LM Studio, Python/Node agent processes, and cloud API keys).
        """
        records: list[BrainRecord] = []

        # 1) Connector-based detection for known CLI brains
        try:
            records.extend(await self.to_brain_records())
        except Exception as exc:
            log.warning("Connector-based detection failed: %s", exc)

        # 2) Windows OS-level process scan
        try:
            from agentic_os.core.brains.windows_detector import (
                detect_local_windows,
                detect_remote_brains,
            )

            win_records = await asyncio.wait_for(
                detect_local_windows(),
                timeout=8.0,
            )
            records.extend(win_records)
            cloud_records = await asyncio.wait_for(
                detect_remote_brains(),
                timeout=8.0,
            )
            records.extend(cloud_records)
        except TimeoutError:
            log.warning("Windows process detection timed out")
        except Exception as exc:
            log.warning("Windows process detection failed: %s", exc)

        # Deduplicate by id or display_name
        seen: set[str] = set()
        deduped: list[BrainRecord] = []
        for r in records:
            key = r.id if r.id else r.display_name.lower()
            name_key = r.display_name.lower()
            if key not in seen and name_key not in seen:
                seen.add(key)
                seen.add(name_key)
                deduped.append(r)
        return deduped
