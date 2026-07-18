"""
MCP Registry Port

Defines the interface for MCP server registry operations.
Domain logic depends on this interface, not implementations.
"""

from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass, field
from typing import Any, Protocol

from agentic_os.domain.mcp import (
    MCPHealthStatus,
    MCPPermissionMapping,
    MCPRegistry,
    MCPServerDetail,
    MCPServerStatus,
    MCPTool,
    MCPToolResult,
)


@dataclass(frozen=True, slots=True)
class MCPServerCreate:
    """Input for creating a new MCP server registration."""

    name: str
    transport: str  # "stdio", "sse", "streamable_http"
    command: str | None = None
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    url: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    server_type: str = "custom"  # "builtin", "custom", "marketplace"
    description: str = ""
    enabled: bool = True
    sandbox: bool = True
    sandbox_config: dict[str, Any] = field(default_factory=dict)
    health_check_interval_seconds: int = 30
    health_check_timeout_seconds: int = 10
    version: str = "1.0.0"
    author: str = ""
    homepage: str | None = None
    repository: str | None = None
    tags: list[str] = field(default_factory=list)
    created_by: str = "system"


@dataclass(frozen=True, slots=True)
class MCPServerUpdate:
    """Input for updating an MCP server registration."""

    name: str | None = None
    transport: str | None = None
    command: str | None = None
    args: list[str] | None = None
    env: dict[str, str] | None = None
    url: str | None = None
    headers: dict[str, str] | None = None
    server_type: str | None = None
    description: str | None = None
    enabled: bool | None = None
    sandbox: bool | None = None
    sandbox_config: dict[str, Any] | None = None
    health_check_interval_seconds: int | None = None
    health_check_timeout_seconds: int | None = None
    version: str | None = None
    author: str | None = None
    homepage: str | None = None
    repository: str | None = None
    tags: list[str] | None = None
    updated_by: str = "system"


@dataclass(frozen=True, slots=True)
class MCPToolInvoke:
    """Input for invoking an MCP tool."""

    server_id: str
    tool: str
    args: dict[str, Any] = field(default_factory=dict)
    timeout_seconds: int | None = None


class MCPRegistryPort(Protocol):
    """
    Port interface for MCP registry operations.

    All implementations must provide these methods.
    Domain logic depends on this interface, not implementations.
    """

    # CRUD Operations
    @abstractmethod
    async def register_server(self, data: MCPServerCreate) -> MCPServerDetail:
        """Register a new MCP server."""
        ...

    @abstractmethod
    async def get_server(self, server_id: str) -> MCPServerDetail | None:
        """Get server by ID."""
        ...

    @abstractmethod
    async def get_server_by_name(self, name: str) -> MCPServerDetail | None:
        """Get server by name."""
        ...

    @abstractmethod
    async def list_servers(
        self,
        status: MCPServerStatus | None = None,
        enabled_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[MCPServerDetail]:
        """List servers with optional filtering."""
        ...

    @abstractmethod
    async def update_server(self, server_id: str, data: MCPServerUpdate) -> MCPServerDetail:
        """Update server configuration."""
        ...

    @abstractmethod
    async def delete_server(self, server_id: str) -> bool:
        """Delete server registration."""
        ...

    # Server Lifecycle
    @abstractmethod
    async def start_server(self, server_id: str) -> MCPServerDetail:
        """Start an MCP server process."""
        ...

    @abstractmethod
    async def stop_server(self, server_id: str) -> MCPServerDetail:
        """Stop an MCP server process."""
        ...

    @abstractmethod
    async def restart_server(self, server_id: str) -> MCPServerDetail:
        """Restart an MCP server process."""
        ...

    # Tool Discovery
    @abstractmethod
    async def discover_tools(self, server_id: str) -> list[MCPTool]:
        """Discover tools from an MCP server."""
        ...

    @abstractmethod
    async def get_tools(self, server_id: str) -> list[MCPTool]:
        """Get cached tools for a server."""
        ...

    @abstractmethod
    async def invoke_tool(self, data: MCPToolInvoke) -> MCPToolResult:
        """Invoke an MCP tool on a server."""
        ...

    # Health Monitoring
    @abstractmethod
    async def check_health(self, server_id: str) -> MCPHealthStatus:
        """Check health of an MCP server."""
        ...

    @abstractmethod
    async def get_health(self, server_id: str) -> MCPHealthStatus | None:
        """Get cached health status."""
        ...

    # Permissions
    @abstractmethod
    async def set_permissions(self, server_id: str, mappings: list[MCPPermissionMapping]) -> int:
        """Map tools to capabilities for permission control."""
        ...

    @abstractmethod
    async def get_permissions(self, server_id: str) -> list[MCPPermissionMapping]:
        """Get tool-to-capability mappings for a server."""
        ...

    # Registry Snapshot
    @abstractmethod
    async def get_registry(self) -> MCPRegistry:
        """Get full registry snapshot."""
        ...


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Result of server configuration validation."""

    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


__all__ = [
    "MCPServerCreate",
    "MCPServerUpdate",
    "MCPToolInvoke",
    "MCPPermissionMapping",
    "MCPRegistryPort",
    "ValidationResult",
]
