"""MCP server discovery — detects MCP servers on the local system.

Discovers MCP (Model Context Protocol) servers from:
- Standard install directories
- MCP-specific config files (``mcp.json``, ``mcp.config.json``, ``.mcprc``)
- Known MCP server registries
- Executable scanning with MCP-specific patterns

Integrates with the existing MCP infrastructure and returns standardized
discovery results compatible with the Runtime Discovery framework.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.logging import get_logger

from services.runtime_discovery.scanner import Scanner

_log = get_logger(__name__)

__all__ = [
    "MCPDiscovery",
    "DiscoveredMCPServer",
    "MCPTransportType",
]

from enum import StrEnum


class MCPTransportType(StrEnum):
    """Supported MCP transport types."""

    STDIO = "stdio"
    SSE = "sse"
    STREAMABLE_HTTP = "streamable_http"


@dataclass
class DiscoveredMCPServer:
    """A discovered MCP server on the local system."""

    name: str
    binary_path: str | None = None
    transport: MCPTransportType = MCPTransportType.STDIO
    version: str | None = None
    config_path: str | None = None
    description: str = ""
    capabilities: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    discovered_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "binary_path": self.binary_path,
            "transport": self.transport.value,
            "version": self.version,
            "config_path": self.config_path,
            "description": self.description,
            "capabilities": list(self.capabilities),
            "tools": list(self.tools),
            "metadata": dict(self.metadata),
            "discovered_at": self.discovered_at.isoformat(),
        }


# MCP config file patterns to search for
_MCP_CONFIG_PATTERNS = ["mcp.json", "mcp.config.json", ".mcprc", "mcp-server.json"]

# MCP executable name patterns
_MCP_EXECUTABLE_NAMES = [
    "mcp-server",
    "mcp-server-*",
    "mcp_*",
    "server-*",
]

# Well-known MCP server names to discover
_KNOWN_MCP_SERVERS: dict[str, str] = {
    "mcp-server-filesystem": "MCP Filesystem Server",
    "mcp-server-github": "MCP GitHub Server",
    "mcp-server-postgres": "MCP PostgreSQL Server",
    "mcp-server-sqlite": "MCP SQLite Server",
    "mcp-server-puppeteer": "MCP Puppeteer Server",
    "mcp-server-brave-search": "MCP Brave Search Server",
    "mcp-server-fetch": "MCP Fetch Server",
    "mcp-server-memory": "MCP Memory Server",
    "mcp-server-everart": "MCP EverArt Server",
    "mcp-server-exa": "MCP Exa Server",
    "mcp-server-firecrawl": "MCP Firecrawl Server",
    "mcp-server-spotify": "MCP Spotify Server",
    "mcp-server-weather": "MCP Weather Server",
    "mcp-server-time": "MCP Time Server",
    "mcp-server-sentry": "MCP Sentry Server",
    "mcp-server-slack": "MCP Slack Server",
}


class MCPDiscovery:
    """Discovers MCP servers installed on the local system.

    Scans standard paths for MCP executables and config files,
    detecting transport type, version, and capabilities.
    """

    def __init__(self) -> None:
        self._scanner = Scanner()
        self._discovered: dict[str, DiscoveredMCPServer] = {}

    async def discover_all(self) -> list[DiscoveredMCPServer]:
        """Discover all MCP servers on the system."""
        servers: list[DiscoveredMCPServer] = []

        # 1. Scan for MCP executables on PATH
        servers.extend(await self._discover_from_path())

        # 2. Scan for MCP config files in standard locations
        servers.extend(await self._discover_from_configs())

        # 3. Scan known MCP server names
        servers.extend(await self._discover_known_servers())

        # Deduplicate by name (keep the one with more info)
        merged = self._deduplicate(servers)

        for server in merged:
            self._discovered[server.name] = server

        _log.info("MCP discovery found %d servers", len(merged))
        return merged

    async def discover_by_name(self, name: str) -> DiscoveredMCPServer | None:
        """Discover a single MCP server by name."""
        # Check if it's a known server
        if name in _KNOWN_MCP_SERVERS:
            binary_path = self._scanner.which(name)
            if binary_path:
                version = self._scanner.detect_version(binary_path)
                transport = await self._detect_transport(binary_path)
                server = DiscoveredMCPServer(
                    name=name,
                    binary_path=binary_path,
                    transport=transport,
                    version=version,
                    description=_KNOWN_MCP_SERVERS[name],
                    metadata={"source": "known_server"},
                )
                self._discovered[name] = server
                return server

        # Generic scan
        binary_path = self._scanner.which(name)
        if binary_path:
            version = self._scanner.detect_version(binary_path)
            transport = await self._detect_transport(binary_path)
            server = DiscoveredMCPServer(
                name=name,
                binary_path=binary_path,
                transport=transport,
                version=version,
                metadata={"source": "path_scan"},
            )
            self._discovered[name] = server
            return server

        return None

    def get_discovered(self, name: str) -> DiscoveredMCPServer | None:
        """Get a previously discovered MCP server by name."""
        return self._discovered.get(name)

    def get_all_discovered(self) -> list[DiscoveredMCPServer]:
        """Return all previously discovered MCP servers."""
        return list(self._discovered.values())

    # ── Path scanning ──

    async def _discover_from_path(self) -> list[DiscoveredMCPServer]:
        """Discover MCP servers from PATH."""
        servers: list[DiscoveredMCPServer] = []
        # Scan for patterns like "mcp-server-*", "mcp_*"
        for name in _KNOWN_MCP_SERVERS:
            binary_path = self._scanner.which(name)
            if binary_path:
                version = self._scanner.detect_version(binary_path)
                transport = await self._detect_transport(binary_path)
                servers.append(
                    DiscoveredMCPServer(
                        name=name,
                        binary_path=binary_path,
                        transport=transport,
                        version=version,
                        description=_KNOWN_MCP_SERVERS[name],
                        metadata={"source": "path"},
                    )
                )

        # Generic MCP executable scan by name pattern
        mcp_exec_names = [name for name in _MCP_EXECUTABLE_NAMES if "*" not in name]
        for name in mcp_exec_names:
            binary_path = self._scanner.which(name)
            if binary_path and not any(s.binary_path == binary_path for s in servers):
                servers.append(
                    DiscoveredMCPServer(
                        name=name,
                        binary_path=binary_path,
                        transport=await self._detect_transport(binary_path),
                        metadata={"source": "path"},
                    )
                )

        return servers

    # ── Config file scanning ──

    async def _discover_from_configs(self) -> list[DiscoveredMCPServer]:
        """Discover MCP servers from config files."""
        servers: list[DiscoveredMCPServer] = []
        config_dirs = self._get_config_search_dirs()

        for config_dir in config_dirs:
            if not config_dir.is_dir():
                continue
            try:
                for pattern in _MCP_CONFIG_PATTERNS:
                    for config_path in config_dir.glob(pattern):
                        server = await self._parse_config(config_path)
                        if server:
                            servers.append(server)
            except PermissionError:
                continue

        return servers

    async def _parse_config(self, config_path: Path) -> DiscoveredMCPServer | None:
        """Parse an MCP config file and return a discovered server."""
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

        name = data.get("name") or config_path.stem
        # Resolve the command/binary from config
        binary_path = None
        cmd = data.get("command") or data.get("binary") or data.get("executable")
        if cmd:
            if os.path.isabs(cmd) and os.path.isfile(cmd):
                binary_path = cmd
            else:
                resolved = self._scanner.which(cmd)
                if resolved:
                    binary_path = resolved

        transport_str = data.get("transport", "stdio")
        try:
            transport = MCPTransportType(transport_str)
        except ValueError:
            transport = MCPTransportType.STDIO

        return DiscoveredMCPServer(
            name=name,
            binary_path=binary_path,
            transport=transport,
            version=data.get("version"),
            config_path=str(config_path),
            description=data.get("description", ""),
            capabilities=data.get("capabilities", []),
            tools=data.get("tools", []),
            metadata={"source": "config_file", "config_path": str(config_path)},
        )

    # ── Known servers ──

    async def _discover_known_servers(self) -> list[DiscoveredMCPServer]:
        """Discover known MCP servers from standard directories."""
        servers: list[DiscoveredMCPServer] = []
        standard_dirs = self._get_config_search_dirs()

        for name, description in _KNOWN_MCP_SERVERS.items():
            # Already found via PATH scan, skip
            if name in self._discovered:
                continue

            for directory in standard_dirs:
                candidate = directory / name
                if candidate.is_file() and os.access(candidate, os.X_OK):
                    version = self._scanner.detect_version(str(candidate))
                    transport = await self._detect_transport(str(candidate))
                    servers.append(
                        DiscoveredMCPServer(
                            name=name,
                            binary_path=str(candidate),
                            transport=transport,
                            version=version,
                            description=description,
                            metadata={"source": "known_dir"},
                        )
                    )
                    break

        return servers

    # ── Transport detection ──

    @staticmethod
    async def _detect_transport(binary_path: str) -> MCPTransportType:
        """Detect the MCP transport type from a binary's --help output."""
        import asyncio

        try:
            proc = await asyncio.create_subprocess_exec(
                binary_path,
                "--help",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=5.0)
            output = (stdout.decode() + stderr.decode()).lower()

            if "sse" in output or "http" in output:
                return MCPTransportType.SSE
            if "streamable" in output:
                return MCPTransportType.STREAMABLE_HTTP
        except Exception:
            pass

        return MCPTransportType.STDIO

    # ── Helpers ──

    @staticmethod
    def _get_config_search_dirs() -> list[Path]:
        """Return directories to search for MCP config files."""
        home = Path.home()
        dirs = [
            home / ".mcp" / "servers",
            home / ".config" / "mcp",
            home / ".local" / "bin",
            Path("/usr/local/bin"),
            Path("/usr/bin"),
            Path(".").resolve(),
        ]

        # Add user PATH directories
        path_env = os.environ.get("PATH", "")
        for p in path_env.split(os.pathsep):
            if p:
                dirs.append(Path(p))

        return dirs

    @staticmethod
    def _deduplicate(servers: list[DiscoveredMCPServer]) -> list[DiscoveredMCPServer]:
        """Deduplicate servers by name, keeping the one with more information."""
        best: dict[str, DiscoveredMCPServer] = {}
        for server in servers:
            existing = best.get(server.name)
            if existing is None:
                best[server.name] = server
            else:
                # Merge: prefer the one with a binary_path
                if server.binary_path and not existing.binary_path:
                    best[server.name] = server
                elif server.version and not existing.version:
                    existing.version = server.version
                if server.capabilities:
                    existing.capabilities = list(set(existing.capabilities + server.capabilities))
        return list(best.values())

    @staticmethod
    def get_known_servers() -> dict[str, str]:
        """Return the mapping of known MCP server names to descriptions."""
        return dict(_KNOWN_MCP_SERVERS)
