"""
MCP Manager

High-level manager for MCP server lifecycle, process supervision, and sandboxing.
Coordinates between registry, client, and infrastructure.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from agentic_os.core.mcp.registry import MCPRegistryImpl
from agentic_os.domain.mcp import (
    MCPHealthStatus,
    MCPServerDetail,
    MCPServerStatus,
    MCPTool,
    MCPToolResult,
)
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.event_bus import EventBus

log = get_logger("mcp.manager")


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class MCPManager:
    """
    MCP Manager - orchestrates server lifecycle, health monitoring, and tool invocation.

    Responsibilities:
    - Server process supervision (start/stop/restart/health)
    - Health monitoring with periodic checks
    - Tool discovery and caching
    - Sandbox enforcement
    - Event emission for all lifecycle changes
    """

    registry: MCPRegistryImpl
    bus: EventBus
    _health_check_tasks: dict[str, asyncio.Task] = field(
        default_factory=dict, init=False, repr=False
    )
    _shutdown: bool = field(default=False, init=False, repr=False)

    async def start_all_enabled(self) -> list[MCPServerDetail]:
        """Start all enabled servers."""
        enabled = self.registry._registry.list_enabled()
        started = []

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
        running = self.registry._registry.list_by_status(MCPServerStatus.RUNNING)
        stopped = []

        for detail in running:
            try:
                stopped_detail = await self.registry.stop_server(detail.config.id)
                stopped.append(stopped_detail)
            except Exception as e:
                log.error(f"Failed to stop server {detail.config.id}: {e}")

        return stopped

    async def restart_server(self, server_id: str) -> MCPServerDetail:
        """Restart a server (stop then start)."""
        detail = self.registry._registry.get_server(server_id)
        if not detail:
            raise KeyError(f"Server not found: {server_id}")

        # Stop if running
        if detail.status in (MCPServerStatus.RUNNING, MCPServerStatus.STARTING):
            await self.registry.stop_server(server_id)

        # Start again
        return await self.registry.start_server(server_id)

    async def reload_server(self, server_id: str) -> MCPServerDetail:
        """Hot reload server configuration and tools."""
        return await self.registry.reload_server(server_id)

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

                    detail = self.registry._registry.get_server(server_id)
                    if not detail or detail.status != MCPServerStatus.RUNNING:
                        continue

                    await self.registry.check_health(server_id)

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    log.error(f"Health check error for {server_id}: {e}")

        # Start tasks for all currently running servers
        running = self.registry._registry.list_by_status(MCPServerStatus.RUNNING)
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

        # Wait for tasks to complete
        if self._health_check_tasks:
            await asyncio.gather(*self._health_check_tasks.values(), return_exceptions=True)

        self._health_check_tasks.clear()
        log.info("Stopped health monitoring")

    async def add_server_to_monitoring(self, server_id: str) -> None:
        """Add a newly started server to health monitoring."""
        if self._shutdown:
            return

        detail = self.registry._registry.get_server(server_id)
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

                    detail = self.registry._registry.get_server(server_id)
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

    async def invoke_tool(
        self,
        server_id: str,
        tool: str,
        arguments: dict[str, Any],
        timeout: int | None = None,
    ) -> MCPToolResult:
        """Invoke a tool on an MCP server."""
        from agentic_os.core.mcp.registry import MCPToolInvoke

        return await self.registry.invoke_tool(
            MCPToolInvoke(server_id=server_id, tool=tool, args=arguments, timeout_seconds=timeout)
        )

    async def get_server_detail(self, server_id: str) -> MCPServerDetail | None:
        """Get full server detail including tools and health."""
        return self.registry._registry.get_server(server_id)

    async def list_servers(
        self, status: MCPServerStatus | None = None, enabled_only: bool = False
    ) -> list[MCPServerDetail]:
        """List all servers with optional filtering."""
        return await self.registry.list_servers(status=status, enabled_only=enabled_only)

    async def shutdown(self) -> None:
        """Shutdown manager - stop all servers and monitoring."""
        log.info("Shutting down MCP Manager...")
        await self.stop_health_monitoring()
        await self.stop_all()
        log.info("MCP Manager shutdown complete")

    def get_server_tools(self, server_id: str) -> list[MCPTool]:
        """Get cached tools for a server."""
        detail = self.registry._registry.get_server(server_id)
        if not detail:
            return []
        return list(detail.tools)

    def get_server_health(self, server_id: str) -> MCPHealthStatus | None:
        """Get cached health status for a server."""
        health = self.registry._health_cache.get(server_id)
        return health[0] if health else None

    async def discover_all_tools(self) -> dict[str, list[MCPTool]]:
        """Discover tools from all running servers."""
        tools = {}
        running = self.registry._registry.list_by_status(MCPServerStatus.RUNNING)

        for detail in running:
            client = self.registry._clients.get(detail.config.id)
            if client:
                try:
                    tools = await client.list_tools()
                    tools[detail.config.id] = tools
                except Exception as e:
                    log.error(f"Failed to discover tools for {detail.config.id}: {e}")
                    tools[detail.config.id] = []

        return tools
