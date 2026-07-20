"""
MCP Manager

High-level manager for MCP server lifecycle, process supervision, health monitoring,
tool/resource/prompt discovery, session tracking, version management, capability
negotiation, and error recovery. Coordinates between all MCP subsystems.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from agentic_os.core.mcp.capability import MCPCapabilityMapper, ServerCapabilities
from agentic_os.core.mcp.prompt_registry import MCPPromptRegistry, PromptDefinition
from agentic_os.core.mcp.registry import MCPRegistryImpl
from agentic_os.core.mcp.resource_registry import MCPResourceRegistry, ResourceDefinition
from agentic_os.core.mcp.security import MCPSecurity
from agentic_os.core.mcp.tool_registry import MCPToolRegistry, ToolDefinition
from agentic_os.core.mcp.version import MCPVersionManager, ServerVersionInfo
from agentic_os.domain.mcp import (
    MCPHealthStatus,
    MCPPrompt,
    MCPResource,
    MCPServerDetail,
    MCPServerStatus,
    MCPTool,
    MCPToolResult,
)
from agentic_os.domain.security import Principal, Role
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.event_bus import EventBus

log = get_logger("mcp.manager")


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class MCPManager:
    """
    MCP Manager - orchestrates server lifecycle, health monitoring, tool/resource/prompt
    discovery, session tracking, and error recovery.

    Responsibilities:
    - Lifecycle management (initialize, start, stop, shutdown)
    - Server process supervision (start/stop/restart/health)
    - Health monitoring with periodic checks and auto-restart
    - Tool discovery and caching
    - Resource and prompt discovery
    - Session tracking
    - Event emission for all lifecycle changes
    """

    registry: MCPRegistryImpl
    bus: EventBus
    security: MCPSecurity | None = None
    version_manager: MCPVersionManager = field(default_factory=MCPVersionManager)
    capability_mapper: MCPCapabilityMapper = field(default_factory=MCPCapabilityMapper)
    tool_registry: MCPToolRegistry = field(default_factory=MCPToolRegistry)
    resource_registry: MCPResourceRegistry = field(default_factory=MCPResourceRegistry)
    prompt_registry: MCPPromptRegistry = field(default_factory=MCPPromptRegistry)
    default_principal: Principal = field(
        default_factory=lambda: Principal(id="mcp-system", roles=[Role.ADMIN]),
        init=False,
        repr=False,
    )
    _health_check_tasks: dict[str, asyncio.Task] = field(
        default_factory=dict, init=False, repr=False
    )
    _shutdown: bool = field(default=False, init=False, repr=False)
    _initialized: bool = field(default=False, init=False, repr=False)
    _auto_restart: bool = field(default=True, init=False, repr=False)

    # ── Lifecycle ───────────────────────────────────────────────────────

    async def initialize(self) -> None:
        """Initialize the MCP manager.

        Prepares the manager for operation. Does not start any servers.
        Idempotent — safe to call multiple times.
        """
        if self._initialized:
            log.debug("MCP Manager already initialized")
            return
        log.info("Initializing MCP Manager...")

        snapshot = self.registry.get_registry_snapshot()
        for detail in snapshot.servers:
            vinfo = ServerVersionInfo(
                server_id=detail.config.id,
                server_version=detail.config.version,
            )
            self.version_manager.register_version(detail.config.id, vinfo)

            caps = ServerCapabilities(server_id=detail.config.id)
            self.capability_mapper.register_capabilities(detail.config.id, caps)

            for tool in detail.tools:
                self.tool_registry.register(
                    ToolDefinition(
                        name=tool.name,
                        server_id=detail.config.id,
                        description=tool.description,
                        input_schema=tool.input_schema,
                    )
                )
            for resource in detail.resources:
                self.resource_registry.register(
                    ResourceDefinition(
                        uri=resource.uri,
                        server_id=detail.config.id,
                        name=resource.name,
                        description=resource.description,
                        mime_type=resource.mime_type,
                    )
                )
            for prompt in detail.prompts:
                self.prompt_registry.register(
                    PromptDefinition(
                        name=prompt.name,
                        server_id=detail.config.id,
                        description=prompt.description,
                        template=prompt.template or "",  # type: ignore[arg-type]
                    )
                )

        self._initialized = True
        log.info(f"MCP Manager initialized with {len(snapshot.servers)} servers")

    async def start(self) -> None:
        """Start the MCP manager — initialize, start all enabled servers,
        negotiate capabilities, and begin health monitoring."""
        log.info("Starting MCP Manager...")
        await self.initialize()
        started = await self.start_all_enabled()
        for detail in started:
            self.version_manager.check_compatibility(detail.config.id)
            self.capability_mapper.negotiate(
                detail.config.id,
                ["tools", "resources", "prompts", "streaming"],
            )
        await self.start_health_monitoring()
        log.info(f"MCP Manager started with {len(started)} servers")

    async def shutdown(self) -> None:
        """Shutdown manager - stop all servers, monitoring, and cleanup."""
        log.info("Shutting down MCP Manager...")
        self._shutdown = True
        self._initialized = False
        await self.stop_health_monitoring()
        await self.stop_all()
        self.version_manager.clear()
        self.capability_mapper.clear()
        self.tool_registry.clear()
        self.resource_registry.clear()
        self.prompt_registry.clear()
        log.info("MCP Manager shutdown complete")

    # ── Server Lifecycle ────────────────────────────────────────────────

    async def start_all_enabled(self) -> list[MCPServerDetail]:
        """Start all enabled servers."""
        snapshot = self.registry.get_registry_snapshot()
        enabled = snapshot.list_enabled()
        started: list[MCPServerDetail] = []

        for detail in enabled:
            if detail.status == MCPServerStatus.STOPPED:
                try:
                    started_detail = await self.registry.start_server(detail.config.id)
                    started.append(started_detail)
                except Exception as e:
                    log.error(f"Failed to start server {detail.config.id}: {e}")

        return started

    async def stop_all(self) -> list[MCPServerDetail]:
        """Stop all running servers."""
        snapshot = self.registry.get_registry_snapshot()
        running = snapshot.list_by_status(MCPServerStatus.RUNNING)
        stopped: list[MCPServerDetail] = []

        for detail in running:
            try:
                stopped_detail = await self.registry.stop_server(detail.config.id)
                stopped.append(stopped_detail)
            except Exception as e:
                log.error(f"Failed to stop server {detail.config.id}: {e}")

        return stopped

    async def restart_server(self, server_id: str) -> MCPServerDetail:
        """Restart a server (stop then start)."""
        if self.security:
            decision = await self.security.authorize_server_restart(
                self.default_principal,
                server_id,
            )
            if not decision.allowed:
                raise PermissionError(f"Server restart denied: {decision.reason}")

        snapshot = self.registry.get_registry_snapshot()
        detail = snapshot.get_server(server_id)
        if not detail:
            raise KeyError(f"Server not found: {server_id}")

        if detail.status in (MCPServerStatus.RUNNING, MCPServerStatus.STARTING):
            await self.registry.stop_server(server_id)

        return await self.registry.start_server(server_id)

    async def reload_server(self, server_id: str) -> MCPServerDetail:
        """Hot reload server configuration and tools."""
        if self.security:
            decision = await self.security.authorize_server_reload(
                self.default_principal,
                server_id,
            )
            if not decision.allowed:
                raise PermissionError(f"Server reload denied: {decision.reason}")

        return await self.registry.reload_server(server_id)

    # ── Health Monitoring ───────────────────────────────────────────────

    async def start_health_monitoring(self, interval_seconds: int = 30) -> None:
        """Start periodic health checks for all running servers."""
        if self._health_check_tasks:
            log.warning("Health monitoring already running")
            return

        self._shutdown = False

        async def health_check_loop(server_id: str, interval: int):
            while not self._shutdown:
                try:
                    await asyncio.sleep(interval)
                    if self._shutdown:
                        break

                    snapshot = self.registry.get_registry_snapshot()
                    detail = snapshot.get_server(server_id)
                    if not detail or detail.status != MCPServerStatus.RUNNING:
                        if (
                            detail
                            and detail.status == MCPServerStatus.FAILED
                            and self._auto_restart
                        ):
                            await self._attempt_restart(server_id)
                        continue

                    await self.registry.check_health(server_id)

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    log.error(f"Health check error for {server_id}: {e}")

        snapshot = self.registry.get_registry_snapshot()
        running = snapshot.list_by_status(MCPServerStatus.RUNNING)
        for detail in running:
            interval = detail.config.health_check_interval_seconds
            task = asyncio.create_task(health_check_loop(detail.config.id, interval))
            self._health_check_tasks[detail.config.id] = task

        log.info(f"Started health monitoring for {len(running)} servers")

    async def stop_health_monitoring(self) -> None:
        """Stop all health check tasks."""
        self._shutdown = True

        for task in self._health_check_tasks.values():
            task.cancel()

        if self._health_check_tasks:
            await asyncio.gather(*self._health_check_tasks.values(), return_exceptions=True)

        self._health_check_tasks.clear()
        log.info("Stopped health monitoring")

    async def add_server_to_monitoring(self, server_id: str) -> None:
        """Add a newly started server to health monitoring."""
        if self._shutdown:
            return

        snapshot = self.registry.get_registry_snapshot()
        detail = snapshot.get_server(server_id)
        if not detail or detail.status != MCPServerStatus.RUNNING:
            return

        if server_id in self._health_check_tasks:
            return

        interval = detail.config.health_check_interval_seconds

        async def health_check_loop():
            while not self._shutdown:
                try:
                    await asyncio.sleep(interval)
                    if self._shutdown:
                        break

                    snapshot = self.registry.get_registry_snapshot()
                    detail = snapshot.get_server(server_id)
                    if not detail or detail.status != MCPServerStatus.RUNNING:
                        break

                    await self.registry.check_health(server_id)

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    log.error(f"Health check error for {server_id}: {e}")

        task = asyncio.create_task(health_check_loop())
        self._health_check_tasks[server_id] = task

    async def remove_server_from_monitoring(self, server_id: str) -> None:
        """Remove a server from health monitoring."""
        task = self._health_check_tasks.pop(server_id, None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    # ── Error Recovery ──────────────────────────────────────────────────

    async def _attempt_restart(self, server_id: str) -> bool:
        """Attempt to restart a failed server with backoff."""
        log.info(f"Attempting auto-restart of server {server_id}")
        try:
            snapshot = self.registry.get_registry_snapshot()
            detail = snapshot.get_server(server_id)
            if not detail:
                return False

            restart_count = detail.restart_count
            if restart_count >= 3:
                log.warning(
                    f"Server {server_id} has been restarted {restart_count} times, "
                    f"skipping auto-restart"
                )
                return False

            await asyncio.sleep(min(restart_count * 5, 30))
            await self.registry.start_server(server_id)
            log.info(f"Auto-restart successful for server {server_id}")
            return True
        except Exception as e:
            log.error(f"Auto-restart failed for server {server_id}: {e}")
            return False

    # ── Tool Operations ─────────────────────────────────────────────────

    async def invoke_tool(
        self,
        server_id: str,
        tool: str,
        arguments: dict[str, Any],
        timeout: int | None = None,
    ) -> MCPToolResult:
        """Invoke a tool on an MCP server with authorization."""
        if self.security:
            decision = await self.security.authorize_tool_invoke(
                self.default_principal,
                server_id,
                tool,
            )
            if not decision.allowed:
                raise PermissionError(f"Tool invocation denied: {decision.reason}")

        from agentic_os.ports.mcp import MCPToolInvoke

        return await self.registry.invoke_tool(
            MCPToolInvoke(server_id=server_id, tool=tool, args=arguments, timeout_seconds=timeout)
        )

    async def get_server_detail(self, server_id: str) -> MCPServerDetail | None:
        """Get full server detail including tools and health."""
        snapshot = self.registry.get_registry_snapshot()
        return snapshot.get_server(server_id)

    async def list_servers(
        self, status: MCPServerStatus | None = None, enabled_only: bool = False
    ) -> list[MCPServerDetail]:
        """List all servers with optional filtering."""
        return await self.registry.list_servers(status=status, enabled_only=enabled_only)

    def get_server_tools(self, server_id: str) -> list[MCPTool]:
        """Get cached tools for a server."""
        snapshot = self.registry.get_registry_snapshot()
        detail = snapshot.get_server(server_id)
        if not detail:
            return []
        return list(detail.tools)

    def get_server_health(self, server_id: str) -> MCPHealthStatus | None:
        """Get cached health status for a server."""
        health_cache = self.registry.get_health_cache()
        cached = health_cache.get(server_id)
        return cached[0] if cached else None

    async def discover_all_tools(self) -> dict[str, list[MCPTool]]:
        """Discover tools from all running servers."""
        all_tools: dict[str, list[MCPTool]] = {}
        snapshot = self.registry.get_registry_snapshot()
        running = snapshot.list_by_status(MCPServerStatus.RUNNING)

        for detail in running:
            client = self.registry.get_client(detail.config.id)
            if client:
                try:
                    server_tools = await client.list_tools()
                    all_tools[detail.config.id] = server_tools
                except Exception as e:
                    log.error(f"Failed to discover tools for {detail.config.id}: {e}")
                    all_tools[detail.config.id] = []

        return all_tools

    # ── Resource Operations ─────────────────────────────────────────────

    async def list_server_resources(self, server_id: str) -> list[MCPResource]:
        """List resources from an MCP server."""
        if self.security:
            decision = await self.security.authorize_resource_read(
                self.default_principal,
                server_id,
                "*",
            )
            if not decision.allowed:
                raise PermissionError(f"Resource list denied: {decision.reason}")
        return await self.registry.list_server_resources(server_id)

    async def read_server_resource(self, server_id: str, uri: str) -> dict[str, Any]:
        """Read a resource from an MCP server."""
        if self.security:
            decision = await self.security.authorize_resource_read(
                self.default_principal,
                server_id,
                uri,
            )
            if not decision.allowed:
                raise PermissionError(f"Resource read denied: {decision.reason}")
        return await self.registry.read_server_resource(server_id, uri)

    async def subscribe_server_resource(self, server_id: str, uri: str) -> bool:
        """Subscribe to resource changes on an MCP server."""
        if self.security:
            decision = await self.security.authorize_resource_subscribe(
                self.default_principal,
                server_id,
                uri,
            )
            if not decision.allowed:
                raise PermissionError(f"Resource subscribe denied: {decision.reason}")
        return await self.registry.subscribe_server_resource(server_id, uri)

    async def unsubscribe_server_resource(self, server_id: str, uri: str) -> bool:
        """Unsubscribe from resource changes on an MCP server."""
        return await self.registry.unsubscribe_server_resource(server_id, uri)

    # ── Prompt Operations ───────────────────────────────────────────────

    async def list_server_prompts(self, server_id: str) -> list[MCPPrompt]:
        """List prompts from an MCP server."""
        if self.security:
            decision = await self.security.authorize_prompt_list(self.default_principal, server_id)
            if not decision.allowed:
                raise PermissionError(f"Prompt list denied: {decision.reason}")
        return await self.registry.list_server_prompts(server_id)

    async def get_server_prompt(
        self, server_id: str, name: str, arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Get a prompt from an MCP server."""
        if self.security:
            decision = await self.security.authorize_prompt_get(
                self.default_principal,
                server_id,
                name,
            )
            if not decision.allowed:
                raise PermissionError(f"Prompt get denied: {decision.reason}")
        return await self.registry.get_server_prompt(server_id, name, arguments)

    # ── Session Tracking ────────────────────────────────────────────────

    def get_active_session_ids(self) -> dict[str, str]:
        """Get map of server_id -> session_id for all connected clients."""
        sessions: dict[str, str] = {}
        clients = self.registry.get_clients()
        for server_id, client in clients.items():
            session_id = getattr(client, "session_id", None)
            if session_id:
                sessions[server_id] = session_id
        return sessions

    async def get_session_id(self, server_id: str) -> str | None:
        """Get the active session ID for a server."""
        client = self.registry.get_client(server_id)
        if not client:
            return None
        return getattr(client, "session_id", None)

    # ── Version Management ──────────────────────────────────────────────

    def get_server_version_info(self, server_id: str) -> ServerVersionInfo | None:
        """Get version info for a server."""
        return self.version_manager.get_version(server_id)

    def check_server_compatibility(self, server_id: str) -> Any:
        """Check if a server's protocol version is compatible."""
        return self.version_manager.check_compatibility(server_id)

    def get_protocol_matrix(self) -> dict[str, Any]:
        """Get the protocol compatibility matrix for all servers."""
        return self.version_manager.get_protocol_compatibility_matrix()

    # ── Capability Management ───────────────────────────────────────────

    def get_server_capabilities(self, server_id: str) -> Any:
        """Get capabilities for a server."""
        return self.capability_mapper.get_capabilities(server_id)

    def has_server_capability(self, server_id: str, capability: str) -> bool:
        """Check if a server has a specific capability."""
        return self.capability_mapper.has_capability(server_id, capability)

    def negotiate_capabilities(self, server_id: str, requested: list[str]) -> Any:
        """Negotiate capabilities with a server."""
        return self.capability_mapper.negotiate(server_id, requested)

    def list_all_capabilities(self) -> dict[str, list[str]]:
        """List all capabilities across all servers."""
        return self.capability_mapper.list_all_capabilities()

    # ── Standalone Registry Proxies ─────────────────────────────────────

    def get_registered_tools(self, server_id: str | None = None) -> list[Any]:
        """Get registered tools, optionally filtered by server."""
        tools = self.tool_registry.list_tools()
        if server_id:
            return self.tool_registry.get_server_tools(server_id)
        return tools

    def get_registered_resources(self, server_id: str | None = None) -> list[Any]:
        """Get registered resources, optionally filtered by server."""
        if server_id:
            return self.resource_registry.get_server_resources(server_id)
        return self.resource_registry.list_resources()

    def get_registered_prompts(self, server_id: str | None = None) -> list[Any]:
        """Get registered prompts, optionally filtered by server."""
        if server_id:
            return self.prompt_registry.get_server_prompts(server_id)
        return self.prompt_registry.list_prompts()

    def search_tools(self, query: str) -> list[Any]:
        """Search registered tools."""
        return self.tool_registry.search_tools(query)

    def search_resources(self, query: str) -> list[Any]:
        """Search registered resources."""
        return self.resource_registry.search_resources(query)

    def search_prompts(self, query: str) -> list[Any]:
        """Search registered prompts."""
        return self.prompt_registry.search_prompts(query)

    # ── Utility ─────────────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        return self._initialized and not self._shutdown

    @property
    def server_count(self) -> int:
        snapshot = self.registry.get_registry_snapshot()
        return len(snapshot.servers)

    @property
    def active_server_count(self) -> int:
        snapshot = self.registry.get_registry_snapshot()
        return len(snapshot.list_by_status(MCPServerStatus.RUNNING))
