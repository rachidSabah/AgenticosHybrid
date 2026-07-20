"""
MCP Discovery Framework

Automatic discovery of MCP servers with:
- File-based discovery
- Directory scanning
- Version detection
- Capability detection
- Automatic registration
"""

import asyncio
import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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
    MCP Server Discovery Framework.

    Features:
    - Automatic server discovery from filesystem
    - Version detection
    - Capability detection
    - Configuration file parsing
    - Automatic registration
    - Incremental updates
    """

    def __init__(
        self,
        bus: EventBus,
        config: DiscoveryConfig | None = None,
    ) -> None:
        self._bus = bus
        self._config = config or DiscoveryConfig()

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

    # ── Configuration ──────────────────────────────────────────────────

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

    # ── Discovery ──────────────────────────────────────────────────────

    async def discover_all(self) -> DiscoveryResult:
        """Perform a full discovery scan."""
        result = DiscoveryResult(
            timestamp=_utcnow(),
            servers_found=0,
            servers_registered=0,
        )

        expanded_paths = [str(Path(p).expanduser().resolve()) for p in self._config.scan_paths]

        for scan_path in expanded_paths:
            if not os.path.exists(scan_path):
                log.debug(f"Skipping non-existent scan path: {scan_path}")
                continue

            try:
                discoveries = await self._scan_path(scan_path)
                result.discoveries.extend(discoveries)
                result.servers_found += len(discoveries)

                for server in discoveries:
                    await self._discover_server_details(server)
                    self._discovered_servers[server.name] = server

                    if self._config.auto_register and self._register_callback:
                        await self._auto_register(server)
                        result.servers_registered += 1

            except Exception as e:
                result.errors.append(f"Error scanning {scan_path}: {e}")
                log.error(f"Discovery error scanning {scan_path}: {e}")

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
        """Discover a single server at the given path."""
        if not os.path.exists(path):
            log.warning(f"Server path does not exist: {path}")
            return None

        if os.path.isfile(path):
            return await self._discover_from_executable(path)
        elif os.path.isdir(path):
            return await self._discover_from_directory(path)

        return None

    async def _scan_path(self, path: str) -> list[DiscoveredServer]:
        """Scan a directory for MCP servers."""
        discoveries: list[DiscoveredServer] = []

        try:
            entries = os.listdir(path)
        except PermissionError:
            log.warning(f"Permission denied accessing: {path}")
            return discoveries

        for entry in entries:
            entry_path = os.path.join(path, entry)

            # Check if it's an executable file
            if os.path.isfile(entry_path) and os.access(entry_path, os.X_OK):
                if self._matches_pattern(entry):
                    server = await self._discover_from_executable(entry_path)
                    if server:
                        discoveries.append(server)

            # Check if it's a directory with a config file
            elif os.path.isdir(entry_path):
                for config_pattern in self._config.config_patterns:
                    config_path = os.path.join(entry_path, config_pattern)
                    if os.path.exists(config_path):
                        server = await self._discover_from_directory(entry_path)
                        if server:
                            discoveries.append(server)
                        break

        return discoveries

    async def _discover_from_executable(self, path: str) -> DiscoveredServer | None:
        """Discover server from an executable file."""
        name = os.path.basename(path)

        # Try to get version
        version = await self._detect_version(path)

        # Detect transport type
        transport = await self._detect_transport(path)

        # Try to parse config if present
        config = await self._find_config_for_executable(path)

        server = DiscoveredServer(
            name=name,
            path=path,
            transport=transport,
            version=version,
            config_file=config,
            last_modified=datetime.fromtimestamp(os.path.getmtime(path), tz=UTC)
            if os.path.exists(path)
            else None,
        )

        if config:
            await self._parse_config(config, server)

        return server

    async def _discover_from_directory(self, path: str) -> DiscoveredServer | None:
        """Discover server from a directory."""
        name = os.path.basename(path)

        # Look for config file
        config = await self._find_config_for_directory(path)

        # Look for executable
        executable = await self._find_executable_in_directory(path)

        if not executable and not config:
            return None

        transport = MCPTransport.STDIO
        version = None

        if executable:
            version = await self._detect_version(executable)
            transport = await self._detect_transport(executable)

        server = DiscoveredServer(
            name=name,
            path=executable or path,
            transport=transport,
            version=version,
            config_file=config,
            last_modified=datetime.fromtimestamp(os.path.getmtime(path), tz=UTC),
        )

        if config:
            await self._parse_config(config, server)

        return server

    async def _detect_version(self, path: str) -> str | None:
        """Detect server version by running with --version."""
        try:
            proc = await asyncio.create_subprocess_exec(
                path,
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=5.0)

            output = stdout.decode() or stderr.decode()
            # Try to extract version
            for line in output.split("\n"):
                if "version" in line.lower():
                    parts = line.split()
                    for part in parts:
                        if part[0].isdigit() or part.startswith("v"):
                            return part.strip("v")
            return None

        except Exception:
            return None

    async def _detect_transport(self, path: str) -> MCPTransport:
        """Detect transport type for a server."""
        try:
            proc = await asyncio.create_subprocess_exec(
                path,
                "--help",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=5.0)

            output = (stdout.decode() + stderr.decode()).lower()

            if "stdio" in output:
                return MCPTransport.STDIO
            elif "http" in output or "sse" in output:
                return MCPTransport.SSE
            elif "streamable" in output:
                return MCPTransport.STREAMABLE_HTTP

        except Exception:
            pass

        return MCPTransport.STDIO  # Default to stdio

    async def _find_config_for_executable(self, path: str) -> str | None:
        """Find config file for an executable."""
        dir_path = os.path.dirname(path)
        name = os.path.basename(path)

        for pattern in self._config.config_patterns:
            config_path = os.path.join(dir_path, pattern)
            if os.path.exists(config_path):
                return config_path

        # Also check ~/.config/{name}/
        home_config = Path("~/.config").expanduser() / name
        if home_config.exists():
            for pattern in self._config.config_patterns:
                config_path = str(home_config / pattern)
                if os.path.exists(config_path):
                    return config_path

        return None

    async def _find_config_for_directory(self, path: str) -> str | None:
        """Find config file in a server directory."""
        for pattern in self._config.config_patterns:
            config_path = os.path.join(path, pattern)
            if os.path.exists(config_path):
                return config_path
        return None

    async def _find_executable_in_directory(self, path: str) -> str | None:
        """Find executable in a server directory."""
        for name in ["server", "run", "start", "main"]:
            for ext in ["", ".sh", ".js", ".py"]:
                executable = os.path.join(path, f"{name}{ext}")
                if os.path.exists(executable) and os.access(executable, os.X_OK):
                    return executable
        return None

    async def _parse_config(self, config_path: str, server: DiscoveredServer) -> None:
        """Parse a config file and update server info."""
        try:
            with open(config_path) as f:
                content = f.read()

            # Try JSON format
            if config_path.endswith(".json"):
                try:
                    config = json.loads(content)
                    server.name = config.get("name", server.name)
                    server.description = config.get("description", "")
                    server.author = config.get("author", "")
                    server.homepage = config.get("homepage")
                    server.capabilities = config.get("capabilities", [])
                    server.metadata = config.get("metadata", {})
                    return
                except json.JSONDecodeError:
                    pass

            # Try simple key=value format
            for line in content.split("\n"):
                if "=" in line and not line.startswith("#"):
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")

                    if key == "name":
                        server.name = value
                    elif key == "description":
                        server.description = value
                    elif key == "author":
                        server.author = value

        except Exception as e:
            log.warning(f"Error parsing config {config_path}: {e}")

    async def _discover_server_details(self, server: DiscoveredServer) -> None:
        """Discover detailed capabilities for a server."""
        if not self._config.detect_capabilities or not os.path.exists(server.path):
            return

        try:
            # Try to get capabilities via MCP protocol
            proc = await asyncio.create_subprocess_exec(
                server.path,
                "--capabilities",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10.0)

            try:
                caps = json.loads(stdout.decode())
                server.capabilities = caps.get("capabilities", [])
                server.tools = caps.get("tools", [])
            except json.JSONDecodeError:
                pass

        except Exception:
            pass

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
            log.info(f"Auto-registered discovered server: {server.name}")

        except Exception as e:
            log.error(f"Failed to auto-register {server.name}: {e}")

    # ── State Access ────────────────────────────────────────────────────

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

    def _matches_pattern(self, name: str) -> bool:
        """Check if a name matches any discovery pattern."""
        import fnmatch

        for pattern in self._config.file_patterns:
            if fnmatch.fnmatch(name, pattern):
                return True
        return False

    # ── Continuous Discovery ────────────────────────────────────────────

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
                log.error(f"Continuous discovery error: {e}")

    async def stop_continuous_discovery(self) -> None:
        """Stop continuous discovery."""
        self._running = False
        for task in self._scan_tasks.values():
            task.cancel()
        self._scan_tasks.clear()
        log.info("Stopped continuous MCP discovery")


__all__ = ["MCPServerDiscovery", "DiscoveredServer", "DiscoveryConfig", "DiscoveryResult"]
