"""MCP Discovery Framework -- delegates to services/runtime_discovery/.

Automatic discovery of MCP servers with file-based discovery, directory
scanning, version detection, capability detection, and automatic registration.

The actual scanning and config-file parsing logic lives in
``services.runtime_discovery.mcp_discovery``. This module wraps it with
EventBus integration, continuous scanning, and registration callbacks for the
kernel-layer ``agentic_os.core`` API.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Re-export the services types so callers can still import from here.
from services.runtime_discovery.mcp_discovery import (  # noqa: E402
    MCPDiscovery as _MCPDiscovery,
)
from services.runtime_discovery.mcp_discovery import (
    MCPTransportType,
)

from agentic_os.domain.events import EventEnvelope, Topic
from agentic_os.domain.mcp import MCPTransport
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.event_bus import EventBus

log = get_logger("mcp.discovery")


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class DiscoveredServer:
    """A discovered MCP server."""

    name: str
    path: str
    transport: MCPTransport
    version: str | None = None
    capabilities: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    description: str = ""
    author: str = ""
    homepage: str | None = None
    config_file: str | None = None
    last_modified: datetime | None = None
    discovered_at: datetime = field(default_factory=_utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DiscoveryConfig:
    """Configuration for MCP server discovery."""

    scan_paths: list[str] = field(
        default_factory=lambda: [
            "/usr/local/bin",
            "/usr/bin",
            "~/.local/bin",
            "~/.mcp/servers",
            "./servers",
        ]
    )
    file_patterns: list[str] = field(
        default_factory=lambda: ["mcp-*", "mcp_*", "*mcp*", "server-*.sh"]
    )
    config_patterns: list[str] = field(
        default_factory=lambda: ["mcp.json", "mcp.config.json", ".mcprc"]
    )
    auto_register: bool = True
    validate_installations: bool = True
    detect_capabilities: bool = True
    scan_interval_seconds: int = 300  # 5 minutes


@dataclass
class DiscoveryResult:
    """Result of a discovery scan."""

    timestamp: datetime
    servers_found: int
    servers_registered: int
    errors: list[str] = field(default_factory=list)
    discoveries: list[DiscoveredServer] = field(default_factory=list)


class MCPServerDiscovery:
    """
    MCP Server Discovery Framework -- delegates scanning to MCPDiscovery.

    Features:
    - Automatic server discovery (delegated to services MCPDiscovery)
    - EventBus integration for lifecycle events
    - Configuration file parsing
    - Automatic registration callbacks
    - Continuous discovery with configurable interval
    """

    def __init__(
        self,
        bus: EventBus,
        config: DiscoveryConfig | None = None,
    ) -> None:
        self._bus = bus
        self._config = config or DiscoveryConfig()
        self._backend = _MCPDiscovery()

        self._discovered_servers: dict[str, DiscoveredServer] = {}
        self._scan_tasks: dict[str, asyncio.Task] = {}
        self._running = False
        self._last_scan: datetime | None = None

        # Registration callback
        self._register_callback: Any | None = None

    async def _emit(self, topic: Topic, payload: dict[str, Any]) -> None:
        """Emit an event to the event bus."""
        await self._bus.publish(
            EventEnvelope(
                type="event",
                source="mcp-discovery",
                topic=topic.value,
                payload=payload,
            )
        )

    # -- Configuration --

    def set_register_callback(self, callback: Any) -> None:
        """Set the callback for automatic server registration."""
        self._register_callback = callback

    def add_scan_path(self, path: str) -> None:
        """Add a path to scan for servers."""
        if path not in self._config.scan_paths:
            self._config.scan_paths.append(path)

    def remove_scan_path(self, path: str) -> None:
        """Remove a path from scan list."""
        if path in self._config.scan_paths:
            self._config.scan_paths.remove(path)

    # -- Discovery --

    async def discover_all(self) -> DiscoveryResult:
        """Perform a full discovery scan (delegates to services MCPDiscovery)."""
        result = DiscoveryResult(
            timestamp=_utcnow(),
            servers_found=0,
            servers_registered=0,
        )

        # Delegate actual scanning to the services-layer MCPDiscovery
        try:
            service_servers = await self._backend.discover_all()
        except Exception as e:
            result.errors.append(f"MCPDiscovery error: {e}")
            log.error("MCPDiscovery.discover_all failed: %s", e)
            return result

        # Convert DiscoveredMCPServer -> DiscoveredServer
        for svc in service_servers:
            server = DiscoveredServer(
                name=svc.name,
                path=svc.binary_path or svc.config_path or "",
                transport=self._convert_transport(svc.transport),
                version=svc.version,
                capabilities=list(svc.capabilities),
                tools=list(svc.tools),
                description=svc.description,
                config_file=svc.config_path,
                metadata=dict(svc.metadata),
            )
            result.discoveries.append(server)
            self._discovered_servers[server.name] = server

        result.servers_found = len(result.discoveries)

        # Also scan locally configured paths (original MCPServerDiscovery behavior)
        expanded_paths = [str(Path(p).expanduser().resolve()) for p in self._config.scan_paths]
        for scan_path in expanded_paths:
            if not os.path.exists(scan_path):
                continue
            try:
                for entry in os.listdir(scan_path):
                    entry_path = os.path.join(scan_path, entry)
                    if os.path.isfile(entry_path) and os.access(entry_path, os.X_OK):
                        if self._matches_pattern(entry):
                            name = os.path.basename(entry_path)
                            if name not in self._discovered_servers:
                                server = DiscoveredServer(
                                    name=name,
                                    path=entry_path,
                                    transport=MCPTransport.STDIO,
                                    metadata={"source": "config_path_scan"},
                                )
                                result.discoveries.append(server)
                                self._discovered_servers[server.name] = server
                                result.servers_found += 1

            except PermissionError:
                result.errors.append(f"Permission denied: {scan_path}")
            except Exception as e:
                result.errors.append(f"Error scanning {scan_path}: {e}")

        # Auto-register if configured
        for server in result.discoveries:
            if self._config.auto_register and self._register_callback:
                await self._auto_register(server)
                result.servers_registered += 1

        self._last_scan = _utcnow()

        await self._emit(
            Topic.MCP_SERVER_DISCOVERED,
            {
                "servers_found": result.servers_found,
                "servers_registered": result.servers_registered,
            },
        )

        return result

    async def discover_server(self, path: str) -> DiscoveredServer | None:
        """Discover a single server at the given path (delegates to MCPDiscovery)."""
        if not os.path.exists(path):
            log.warning("Server path does not exist: %s", path)
            return None

        # Use MCPDiscovery to discover by name if it's a known server
        name = os.path.basename(path)
        svc = await self._backend.discover_by_name(name)
        if svc:
            server = DiscoveredServer(
                name=svc.name,
                path=svc.binary_path or path,
                transport=self._convert_transport(svc.transport),
                version=svc.version,
                config_file=svc.config_path,
                description=svc.description,
                capabilities=list(svc.capabilities),
                tools=list(svc.tools),
                metadata=dict(svc.metadata),
            )
            self._discovered_servers[server.name] = server
            return server

        # Fall back to local file/dir scan
        if os.path.isfile(path):
            server = DiscoveredServer(
                name=name,
                path=path,
                transport=MCPTransport.STDIO,
                metadata={"source": "direct_path"},
            )
        elif os.path.isdir(path):
            server = DiscoveredServer(
                name=name,
                path=path,
                transport=MCPTransport.STDIO,
                metadata={"source": "direct_path"},
            )
        else:
            return None

        self._discovered_servers[server.name] = server
        return server

    # -- Helpers --

    async def _auto_register(self, server: DiscoveredServer) -> None:
        """Automatically register a discovered server."""
        if not self._register_callback:
            return
        try:
            await self._register_callback(server)
            await self._emit(
                Topic.MCP_SERVER_REGISTERED,
                {
                    "name": server.name,
                    "path": server.path,
                    "transport": server.transport.value,
                    "source": "discovery",
                },
            )
            log.info("Auto-registered discovered server: %s", server.name)
        except Exception as e:
            log.error("Failed to auto-register %s: %s", server.name, e)

    @staticmethod
    def _matches_pattern(name: str) -> bool:
        """Check if a name matches any discovery pattern."""
        import fnmatch

        patterns = ["mcp-*", "mcp_*", "*mcp*", "server-*.sh"]
        return any(fnmatch.fnmatch(name, p) for p in patterns)

    @staticmethod
    def _convert_transport(t: MCPTransportType) -> MCPTransport:
        """Convert MCPTransportType to MCPTransport enum."""
        mapping = {
            MCPTransportType.STDIO: MCPTransport.STDIO,
            MCPTransportType.SSE: MCPTransport.SSE,
            MCPTransportType.STREAMABLE_HTTP: MCPTransport.STREAMABLE_HTTP,
        }
        return mapping.get(t, MCPTransport.STDIO)

    # -- State Access --

    def get_discovered_servers(self) -> dict[str, DiscoveredServer]:
        """Get all discovered servers."""
        return self._discovered_servers.copy()

    def get_discovered_server(self, name: str) -> DiscoveredServer | None:
        """Get a discovered server by name."""
        return self._discovered_servers.get(name)

    def get_discovered_count(self) -> int:
        """Get the count of discovered servers."""
        return len(self._discovered_servers)

    def get_last_scan_time(self) -> datetime | None:
        """Get the timestamp of the last scan."""
        return self._last_scan

    # -- Continuous Discovery --

    async def start_continuous_discovery(self) -> None:
        """Start continuous discovery at configured intervals."""
        if self._running:
            return
        self._running = True
        log.info("Starting continuous MCP discovery")

        while self._running:
            try:
                await asyncio.sleep(self._config.scan_interval_seconds)
                if not self._running:
                    break
                await self.discover_all()
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error("Continuous discovery error: %s", e)

    async def stop_continuous_discovery(self) -> None:
        """Stop continuous discovery."""
        self._running = False
        for task in self._scan_tasks.values():
            task.cancel()
        self._scan_tasks.clear()
        log.info("Stopped continuous MCP discovery")


__all__ = ["MCPServerDiscovery", "DiscoveredServer", "DiscoveryConfig", "DiscoveryResult"]
