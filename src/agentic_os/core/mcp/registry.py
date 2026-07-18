"""
MCP Registry Implementation

In-memory implementation of MCPRegistryPort with server lifecycle management,
tool registry, and hot reload support.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from agentic_os.domain.events import EventEnvelope, Topic
from agentic_os.domain.mcp import (
    MCPHealthStatus,
    MCPPermissionMapping,
    MCPRegistry,
    MCPServerConfig,
    MCPServerDetail,
    MCPServerStatus,
    MCPTool,
)
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.event_bus import EventBus
from agentic_os.ports.mcp import (
    MCPRegistryPort,
    MCPServerCreate,
    MCPServerUpdate,
    MCPToolInvoke,
    MCPToolResult,
    ValidationResult,
)

log = get_logger("mcp.registry")


@dataclass
class MCPRegistryImpl(MCPRegistryPort):
    """
    In-memory MCP Registry Implementation.

    Features:
    - Server lifecycle management (register, start, stop, hot reload)
    - Tool registry with caching
    - Health monitoring integration
    - Permission mapping for tool-to-capability
    - Event emission for all lifecycle transitions
    """

    bus: EventBus
    _registry: MCPRegistry = field(default_factory=MCPRegistry)
    _permissions: dict[str, list[MCPPermissionMapping]] = field(default_factory=dict)
    _health_cache: dict[str, tuple[MCPHealthStatus, dict[str, Any]]] = field(default_factory=dict)
    _clients: dict[str, Any] = field(default_factory=dict)  # MCPClient instances
    _locks: dict[str, asyncio.Lock] = field(default_factory=dict)

    def _get_lock(self, server_id: str) -> asyncio.Lock:
        if server_id not in self._locks:
            self._locks[server_id] = asyncio.Lock()
        return self._locks[server_id]

    async def _emit(self, topic: Topic, payload: dict[str, Any]) -> None:
        """Emit an event to the event bus."""
        await self.bus.publish(
            EventEnvelope(
                type="event",
                source="mcp-registry",
                topic=topic.value,
                payload=payload,
            )
        )

    def _validate_create(self, data: MCPServerCreate) -> ValidationResult:
        """Validate server creation input."""
        errors = []
        warnings = []

        if not data.name or not data.name.strip():
            errors.append("name is required")

        if data.transport == "stdio":
            if not data.command:
                errors.append("command is required for stdio transport")
        elif data.transport == "sse":
            if not data.url:
                errors.append("url is required for SSE transport")
        else:
            errors.append(f"unknown transport: {data.transport}")

        return ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)

    async def register_server(self, data: MCPServerCreate) -> MCPServerDetail:
        """Register a new MCP server."""
        validation = self._validate_create(data)
        if not validation.valid:
            raise ValueError(f"Invalid server config: {', '.join(validation.errors)}")

        # Create server config
        if data.transport == "stdio":
            if not data.command:
                raise ValueError("command is required for stdio transport")
            config = MCPServerConfig.create_stdio(
                name=data.name,
                command=data.command,
                args=data.args,
                env=data.env,
                sandbox=data.sandbox,
                sandbox_config=data.sandbox_config,
                description=data.description,
                tags=data.tags,
                created_by=data.created_by,
            )
        else:
            if not data.url:
                raise ValueError("url is required for SSE transport")
            config = MCPServerConfig.create_sse(
                name=data.name,
                url=data.url,
                headers=data.headers,
                sandbox=data.sandbox,
                sandbox_config=data.sandbox_config,
                description=data.description,
                tags=data.tags,
                created_by=data.created_by,
            )

        # Create server detail with stopped status
        detail = MCPServerDetail(
            config=config,
            status=MCPServerStatus.STOPPED,
            health=MCPHealthStatus.UNKNOWN,
        )

        # Update registry
        self._registry = self._registry.with_server(detail)

        # Emit event
        await self._emit(
            Topic.MCP_SERVER_REGISTERED,
            {"server_id": config.id, "name": config.name, "transport": config.transport.value},
        )

        log.info(f"Registered MCP server: {config.name} ({config.id})")
        return detail

    async def get_server(self, server_id: str) -> MCPServerDetail | None:
        """Get server by ID."""
        return self._registry.get_server(server_id)

    async def get_server_by_name(self, name: str) -> MCPServerDetail | None:
        """Get server by name."""
        return self._registry.get_server_by_name(name)

    async def list_servers(
        self,
        status: MCPServerStatus | None = None,
        enabled_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[MCPServerDetail]:
        """List servers with optional filtering."""
        servers = self._registry.servers

        if enabled_only:
            servers = tuple(s for s in servers if s.config.enabled)

        if status is not None:
            servers = tuple(s for s in servers if s.status == status)

        return list(servers[offset : offset + limit])

    async def update_server(self, server_id: str, data: MCPServerUpdate) -> MCPServerDetail:
        """Update server configuration."""
        detail = self._registry.get_server(server_id)
        if not detail:
            raise KeyError(f"Server not found: {server_id}")

        # Build updated config
        config = detail.config
        updated = False

        new_name: str | None = None
        new_description: str | None = None
        new_enabled: bool | None = None
        new_tags: tuple[str, ...] | None = None
        new_sandbox: bool | None = None
        new_sandbox_config: dict[str, Any] | None = None

        if data.name is not None and data.name != config.name:
            new_name = data.name
            updated = True
        if data.description is not None and data.description != config.description:
            new_description = data.description
            updated = True
        if data.enabled is not None and data.enabled != config.enabled:
            new_enabled = data.enabled
            updated = True
        if data.tags is not None and tuple(data.tags) != config.tags:
            new_tags = tuple(data.tags)
            updated = True
        if data.sandbox is not None and data.sandbox != config.sandbox:
            new_sandbox = data.sandbox
            new_sandbox_config = data.sandbox_config or config.sandbox_config
            updated = True

        if not updated:
            return detail

        # Create new config with updated fields
        new_config = MCPServerConfig(
            id=config.id,
            name=new_name if new_name is not None else config.name,
            transport=config.transport,
            command=config.command,
            args=config.args,
            env=config.env,
            url=config.url,
            headers=config.headers,
            sandbox=new_sandbox if new_sandbox is not None else config.sandbox,
            sandbox_config=new_sandbox_config
            if new_sandbox_config is not None
            else config.sandbox_config,
            enabled=new_enabled if new_enabled is not None else config.enabled,
            description=new_description if new_description is not None else config.description,
            tags=new_tags if new_tags is not None else config.tags,
            created_at=config.created_at,
            updated_at=_utcnow(),
            created_by=config.created_by,
        )

        # Update detail
        new_detail = MCPServerDetail(
            config=new_config,
            status=detail.status,
            tools=detail.tools,
            health=detail.health,
            health_details=detail.health_details,
            last_health_check=detail.last_health_check,
            error=detail.error,
            process_id=detail.process_id,
            started_at=detail.started_at,
            stopped_at=detail.stopped_at,
            restart_count=detail.restart_count,
        )

        self._registry = self._registry.with_server(new_detail)

        await self._emit(
            Topic.MCP_SERVER_UPDATED,
            {
                "server_id": server_id,
                "changes": {
                    "name": new_name,
                    "description": new_description,
                    "enabled": new_enabled,
                    "tags": new_tags,
                    "sandbox": new_sandbox,
                    "sandbox_config": new_sandbox_config,
                },
            },
        )

        log.info(f"Updated MCP server: {server_id}")
        return new_detail

    async def delete_server(self, server_id: str) -> bool:
        """Delete a server configuration."""
        detail = self._registry.get_server(server_id)
        if not detail:
            return False

        # Stop if running
        if detail.status in (MCPServerStatus.RUNNING, MCPServerStatus.STARTING):
            await self.stop_server(server_id)

        self._registry = self._registry.without_server(server_id)
        self._permissions.pop(server_id, None)
        self._health_cache.pop(server_id, None)

        if server_id in self._clients:
            await self._clients[server_id].disconnect()
            del self._clients[server_id]

        await self._emit(
            Topic.MCP_SERVER_UNREGISTERED,
            {"server_id": server_id, "name": detail.config.name},
        )

        log.info(f"Deleted MCP server: {server_id}")
        return True

    async def start_server(self, server_id: str) -> MCPServerDetail:
        """Start an MCP server."""
        detail = self._registry.get_server(server_id)
        if not detail:
            raise KeyError(f"Server not found: {server_id}")

        if detail.status in (MCPServerStatus.RUNNING, MCPServerStatus.STARTING):
            return detail

        if not detail.config.enabled:
            raise ValueError(f"Server {server_id} is disabled")

        async with self._get_lock(server_id):
            # Double-check after acquiring lock
            detail = self._registry.get_server(server_id)
            if not detail:
                raise KeyError(f"Server not found: {server_id}")

            if detail.status in (MCPServerStatus.RUNNING, MCPServerStatus.STARTING):
                return detail

            # Update status to starting
            starting_detail = detail.with_status(MCPServerStatus.STARTING)
            self._registry = self._registry.with_server(starting_detail)

            try:
                # Import MCP client here to avoid circular imports
                from agentic_os.core.mcp.client import MCPClient

                client = MCPClient(detail.config)
                await client.connect()
                tools = await client.list_tools()

                # Create running detail
                running_detail = (
                    detail.with_status(
                        MCPServerStatus.RUNNING,
                        error=None,
                        process_id=client.process_id if hasattr(client, "process_id") else None,
                    )
                    .with_tools(tools)
                    .with_health(MCPHealthStatus.HEALTHY, {"tools": len(tools)})
                )

                self._registry = self._registry.with_server(running_detail)
                self._clients[server_id] = client

                # Emit events
                await self._emit(
                    Topic.MCP_SERVER_STARTED,
                    {"server_id": server_id, "name": detail.config.name, "tools": len(tools)},
                )
                await self._emit(
                    Topic.MCP_HEALTH_CHANGED,
                    {
                        "server_id": server_id,
                        "health": MCPHealthStatus.HEALTHY.value,
                        "details": {"tools": len(tools)},
                    },
                )

                log.info(f"Started MCP server: {server_id} with {len(tools)} tools")
                return running_detail

            except Exception as e:
                error_detail = detail.with_status(MCPServerStatus.FAILED, error=str(e))
                self._registry = self._registry.with_server(error_detail)

                await self._emit(
                    Topic.MCP_SERVER_FAILED,
                    {"server_id": server_id, "error": str(e)},
                )

                log.error(f"Failed to start MCP server {server_id}: {e}")
                raise

    async def stop_server(self, server_id: str) -> MCPServerDetail:
        """Stop an MCP server."""
        detail = self._registry.get_server(server_id)
        if not detail:
            raise KeyError(f"Server not found: {server_id}")

        if detail.status in (MCPServerStatus.STOPPED, MCPServerStatus.STOPPING):
            return detail

        async with self._get_lock(server_id):
            detail = self._registry.get_server(server_id)
            if not detail:
                raise KeyError(f"Server not found: {server_id}")

            if detail.status in (MCPServerStatus.STOPPED, MCPServerStatus.STOPPING):
                return detail

            # Update to stopping
            stopping_detail = detail.with_status(MCPServerStatus.STOPPING)
            self._registry = self._registry.with_server(stopping_detail)

            try:
                client = self._clients.get(server_id)
                if client:
                    await client.disconnect()
                    del self._clients[server_id]

                # Update to stopped
                stopped_detail = detail.with_status(MCPServerStatus.STOPPED)
                self._registry = self._registry.with_server(stopped_detail)

                await self._emit(
                    Topic.MCP_SERVER_STOPPED,
                    {"server_id": server_id, "name": detail.config.name},
                )

                log.info(f"Stopped MCP server: {server_id}")
                return stopped_detail

            except Exception as e:
                error_detail = detail.with_status(MCPServerStatus.FAILED, error=str(e))
                self._registry = self._registry.with_server(error_detail)
                log.error(f"Error stopping MCP server {server_id}: {e}")
                raise

    async def reload_server(self, server_id: str) -> MCPServerDetail:
        """Hot reload an MCP server (restart and refresh tools)."""
        detail = self._registry.get_server(server_id)
        if not detail:
            raise KeyError(f"Server not found: {server_id}")

        if detail.status == MCPServerStatus.RUNNING:
            await self.stop_server(server_id)
            return await self.start_server(server_id)
        else:
            return await self.start_server(server_id)

    async def list_tools(self, server_id: str) -> list[MCPTool]:
        """Get cached tools for a server."""
        detail = self._registry.get_server(server_id)
        if not detail:
            raise KeyError(f"Server not found: {server_id}")
        return list(detail.tools)

    async def invoke_tool(self, data: MCPToolInvoke) -> MCPToolResult:
        """Invoke an MCP tool on a server."""
        detail = self._registry.get_server(data.server_id)
        if not detail:
            raise KeyError(f"Server not found: {data.server_id}")

        if detail.status != MCPServerStatus.RUNNING:
            raise ValueError(
                f"Server {data.server_id} is not running (status: {detail.status.value})"
            )

        client = self._clients.get(data.server_id)
        if not client:
            raise RuntimeError(f"Client not found for server {data.server_id}")

        # Check permission if mapped
        permissions = self._permissions.get(data.server_id, [])
        tool_perm = next((p for p in permissions if p.tool_name == data.tool), None)
        if tool_perm:
            # Permission check would go through AccessControl port
            pass

        try:
            result = await client.call_tool(data.tool, data.args)

            await self._emit(
                Topic.MCP_TOOL_INVOKED,
                {
                    "server_id": data.server_id,
                    "tool": data.tool,
                    "args": data.args,
                    "success": not result.is_error,
                },
            )

            return result

        except Exception as e:
            await self._emit(
                Topic.MCP_TOOL_INVOKED,
                {
                    "server_id": data.server_id,
                    "tool": data.tool,
                    "args": data.args,
                    "success": False,
                    "error": str(e),
                },
            )
            raise

    async def check_health(self, server_id: str) -> MCPHealthStatus:
        """Check health of an MCP server."""
        detail = self._registry.get_server(server_id)
        if not detail:
            raise KeyError(f"Server not found: {server_id}")

        client = self._clients.get(server_id)
        if not client or detail.status != MCPServerStatus.RUNNING:
            health = MCPHealthStatus.UNHEALTHY
            details = {"error": "Server not running"}
        else:
            try:
                health = await client.health_check()
                details = (
                    {"latency_ms": health.get("latency_ms", 0)} if isinstance(health, dict) else {}
                )
            except Exception as e:
                health = MCPHealthStatus.UNHEALTHY
                details = {"error": str(e)}

        # Update cached health
        new_detail = detail.with_health(health, details)
        self._registry = self._registry.with_server(new_detail)
        self._health_cache[server_id] = (health, details)

        await self._emit(
            Topic.MCP_HEALTH_CHANGED,
            {
                "server_id": server_id,
                "health": health.value,
                "details": details,
            },
        )

        return health

    async def get_health(self, server_id: str) -> MCPHealthStatus | None:
        """Get cached health status."""
        cached = self._health_cache.get(server_id)
        return cached[0] if cached else None

    async def set_permissions(self, server_id: str, mappings: list[MCPPermissionMapping]) -> int:
        """Set tool-to-capability permission mappings."""
        detail = self._registry.get_server(server_id)
        if not detail:
            raise KeyError(f"Server not found: {server_id}")

        self._permissions[server_id] = mappings

        await self._emit(
            Topic.MCP_PERMISSIONS_CHANGED,
            {"server_id": server_id, "mappings": [m.to_dict() for m in mappings]},
        )

        log.info(f"Updated permissions for MCP server {server_id}: {len(mappings)} mappings")
        return len(mappings)

    async def get_permissions(self, server_id: str) -> list[MCPPermissionMapping]:
        """Get tool-to-capability permission mappings."""
        return self._permissions.get(server_id, [])

    async def get_registry(self) -> MCPRegistry:
        """Get full registry snapshot."""
        return self._registry


def _utcnow() -> datetime:
    from datetime import datetime

    return datetime.now(UTC)
