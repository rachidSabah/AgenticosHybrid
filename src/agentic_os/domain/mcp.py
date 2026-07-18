"""
MCP (Model Context Protocol) Domain Models

Domain layer for MCP framework - pure Python, no external dependencies.
Follows hexagonal architecture: domain depends on nothing.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4


def _utcnow() -> datetime:
    return datetime.now(UTC)


class MCPTransport(StrEnum):
    """MCP transport types."""

    STDIO = "stdio"
    SSE = "sse"
    STREAMABLE_HTTP = "streamable_http"


class MCPServerStatus(StrEnum):
    """Lifecycle status of an MCP server."""

    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    FAILED = "failed"


class MCPHealthStatus(StrEnum):
    """Health status of an MCP server."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class MCPSessionStatus(StrEnum):
    """Session status for MCP connections."""

    ACTIVE = "active"
    IDLE = "idle"
    EXPIRED = "expired"
    CLOSED = "closed"


@dataclass(frozen=True, slots=True)
class MCPTool:
    """An MCP tool exposed by a server."""

    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
            "outputSchema": self.output_schema,
        }

    @classmethod
    def from_mcp(cls, tool: dict[str, Any]) -> MCPTool:
        """Create MCPTool from MCP protocol tool definition."""
        return cls(
            name=tool.get("name", ""),
            description=tool.get("description", ""),
            input_schema=tool.get("inputSchema", {}),
            output_schema=tool.get("outputSchema"),
        )


@dataclass(frozen=True, slots=True)
class MCPToolResult:
    """Result of an MCP tool invocation."""

    content: list[dict[str, Any]]
    is_error: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "isError": self.is_error,
        }


@dataclass(frozen=True, slots=True)
class MCPResource:
    """An MCP resource exposed by a server."""

    uri: str
    name: str
    description: str = ""
    mime_type: str | None = None
    size: int | None = None
    annotations: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "uri": self.uri,
            "name": self.name,
            "description": self.description,
            "mimeType": self.mime_type,
            "size": self.size,
            "annotations": self.annotations,
        }

    @classmethod
    def from_mcp(cls, resource: dict[str, Any]) -> MCPResource:
        """Create MCPResource from MCP protocol resource definition."""
        return cls(
            uri=resource.get("uri", ""),
            name=resource.get("name", ""),
            description=resource.get("description", ""),
            mime_type=resource.get("mimeType"),
            size=resource.get("size"),
            annotations=resource.get("annotations", {}),
        )


@dataclass(frozen=True, slots=True)
class MCPResourceTemplate:
    """A resource template for parameterized resource URIs."""

    uri_template: str
    name: str
    description: str = ""
    mime_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "uriTemplate": self.uri_template,
            "name": self.name,
            "description": self.description,
            "mimeType": self.mime_type,
        }


@dataclass(frozen=True, slots=True)
class MCPPrompt:
    """An MCP prompt template exposed by a server."""

    name: str
    description: str = ""
    arguments: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "arguments": list(self.arguments),
        }

    @classmethod
    def from_mcp(cls, prompt: dict[str, Any]) -> MCPPrompt:
        """Create MCPPrompt from MCP protocol prompt definition."""
        return cls(
            name=prompt.get("name", ""),
            description=prompt.get("description", ""),
            arguments=tuple(prompt.get("arguments", [])),
        )


@dataclass(frozen=True, slots=True)
class MCPRoot:
    """A root directory exposed by the client to the server."""

    uri: str
    name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "uri": self.uri,
            "name": self.name,
        }


@dataclass(frozen=True, slots=True)
class MCPPermissionMapping:
    """Maps an MCP tool to a capability for permission control."""

    tool_name: str
    capability: str
    description: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "capability": self.capability,
            "description": self.description,
        }


@dataclass(frozen=True, slots=True)
class MCPServerConfig:
    """
    Configuration for an MCP server.

    Immutable after creation - use replace() pattern for modifications.
    """

    id: str
    name: str
    transport: MCPTransport
    # For stdio transport
    command: str | None = None
    args: tuple[str, ...] = field(default_factory=tuple)
    env: dict[str, str] = field(default_factory=dict)
    # For SSE transport
    url: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    # Sandboxing
    sandbox: bool = True
    sandbox_config: dict[str, Any] = field(default_factory=dict)
    # Enabled state
    enabled: bool = True
    # Health check
    health_check_interval_seconds: int = 30
    health_check_timeout_seconds: int = 10
    # Metadata
    description: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)
    created_by: str = "system"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "transport": self.transport.value,
            "command": self.command,
            "args": list(self.args),
            "env": self.env,
            "url": self.url,
            "headers": self.headers,
            "sandbox": self.sandbox,
            "sandbox_config": self.sandbox_config,
            "enabled": self.enabled,
            "description": self.description,
            "tags": list(self.tags),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "created_by": self.created_by,
        }

    @classmethod
    def create_stdio(
        cls,
        name: str,
        command: str,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        sandbox: bool = True,
        sandbox_config: dict[str, Any] | None = None,
        description: str = "",
        tags: list[str] | None = None,
        created_by: str = "system",
    ) -> MCPServerConfig:
        """Create a stdio transport MCP server config."""
        return cls(
            id=str(uuid4()),
            name=name,
            transport=MCPTransport.STDIO,
            command=command,
            args=tuple(args) if args else (),
            env=env or {},
            sandbox=sandbox,
            sandbox_config=sandbox_config or {},
            description=description,
            tags=tuple(tags) if tags else (),
            created_by=created_by,
        )

    @classmethod
    def create_sse(
        cls,
        name: str,
        url: str,
        headers: dict[str, str] | None = None,
        sandbox: bool = True,
        sandbox_config: dict[str, Any] | None = None,
        description: str = "",
        tags: list[str] | None = None,
        created_by: str = "system",
    ) -> MCPServerConfig:
        """Create an SSE transport MCP server config."""
        return cls(
            id=str(uuid4()),
            name=name,
            transport=MCPTransport.SSE,
            url=url,
            headers=headers or {},
            sandbox=sandbox,
            sandbox_config=sandbox_config or {},
            description=description,
            tags=tuple(tags) if tags else (),
            created_by=created_by,
        )

    @classmethod
    def create_streamable_http(
        cls,
        name: str,
        url: str,
        headers: dict[str, str] | None = None,
        sandbox: bool = True,
        sandbox_config: dict[str, Any] | None = None,
        description: str = "",
        tags: list[str] | None = None,
        created_by: str = "system",
    ) -> MCPServerConfig:
        """Create a Streamable HTTP transport MCP server config."""
        return cls(
            id=str(uuid4()),
            name=name,
            transport=MCPTransport.STREAMABLE_HTTP,
            url=url,
            headers=headers or {},
            sandbox=sandbox,
            sandbox_config=sandbox_config or {},
            description=description,
            tags=tuple(tags) if tags else (),
            created_by=created_by,
        )

    def with_enabled(self, enabled: bool) -> MCPServerConfig:
        return MCPServerConfig(
            id=self.id,
            name=self.name,
            transport=self.transport,
            command=self.command,
            args=self.args,
            env=self.env,
            url=self.url,
            headers=self.headers,
            sandbox=self.sandbox,
            sandbox_config=self.sandbox_config,
            enabled=enabled,
            description=self.description,
            tags=self.tags,
            created_at=self.created_at,
            updated_at=_utcnow(),
            created_by=self.created_by,
        )

    def with_sandbox(self, sandbox: bool, config: dict[str, Any] | None = None) -> MCPServerConfig:
        return MCPServerConfig(
            id=self.id,
            name=self.name,
            transport=self.transport,
            command=self.command,
            args=self.args,
            env=self.env,
            url=self.url,
            headers=self.headers,
            sandbox=sandbox,
            sandbox_config=config or self.sandbox_config,
            enabled=self.enabled,
            description=self.description,
            tags=self.tags,
            created_at=self.created_at,
            updated_at=_utcnow(),
            created_by=self.created_by,
        )


@dataclass(frozen=True, slots=True)
class MCPServerDetail:
    """
    Runtime detail for an MCP server including status, tools, and health.
    """

    config: MCPServerConfig
    status: MCPServerStatus
    tools: tuple[MCPTool, ...] = field(default_factory=tuple)
    health: MCPHealthStatus = MCPHealthStatus.UNKNOWN
    health_details: dict[str, Any] = field(default_factory=dict)
    last_health_check: datetime | None = None
    error: str | None = None
    process_id: int | None = None
    started_at: datetime | None = None
    stopped_at: datetime | None = None
    restart_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "config": self.config.to_dict(),
            "status": self.status.value,
            "tools": [t.to_dict() for t in self.tools],
            "health": self.health.value,
            "health_details": self.health_details,
            "last_health_check": self.last_health_check.isoformat()
            if self.last_health_check
            else None,
            "error": self.error,
            "process_id": self.process_id,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "stopped_at": self.stopped_at.isoformat() if self.stopped_at else None,
            "restart_count": self.restart_count,
        }

    def with_status(
        self, status: MCPServerStatus, error: str | None = None, process_id: int | None = None
    ) -> MCPServerDetail:
        now = _utcnow()
        return MCPServerDetail(
            config=self.config,
            status=status,
            tools=self.tools,
            health=self.health,
            health_details=self.health_details,
            last_health_check=self.last_health_check,
            error=error if error is not None else self.error,
            process_id=process_id if process_id is not None else self.process_id,
            started_at=self.started_at if status != MCPServerStatus.STARTING else now,
            stopped_at=now
            if status in (MCPServerStatus.STOPPED, MCPServerStatus.FAILED)
            else self.stopped_at,
            restart_count=self.restart_count + (1 if status == MCPServerStatus.FAILED else 0),
        )

    def with_tools(self, tools: list[MCPTool]) -> MCPServerDetail:
        return MCPServerDetail(
            config=self.config,
            status=self.status,
            tools=tuple(tools),
            health=self.health,
            health_details=self.health_details,
            last_health_check=self.last_health_check,
            error=self.error,
            process_id=self.process_id,
            started_at=self.started_at,
            stopped_at=self.stopped_at,
            restart_count=self.restart_count,
        )

    def with_health(
        self, health: MCPHealthStatus, details: dict[str, Any] | None = None
    ) -> MCPServerDetail:
        return MCPServerDetail(
            config=self.config,
            status=self.status,
            tools=self.tools,
            health=health,
            health_details=details or self.health_details,
            last_health_check=_utcnow(),
            error=self.error,
            process_id=self.process_id,
            started_at=self.started_at,
            stopped_at=self.stopped_at,
            restart_count=self.restart_count,
        )


@dataclass(frozen=True, slots=True)
class MCPRegistry:
    """Registry snapshot of all MCP servers."""

    servers: tuple[MCPServerDetail, ...] = field(default_factory=tuple)
    updated_at: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "servers": [s.to_dict() for s in self.servers],
            "updated_at": self.updated_at.isoformat(),
        }

    def get_server(self, server_id: str) -> MCPServerDetail | None:
        for s in self.servers:
            if s.config.id == server_id or s.config.name == server_id:
                return s
        return None

    def get_server_by_name(self, name: str) -> MCPServerDetail | None:
        for s in self.servers:
            if s.config.name == name:
                return s
        return None

    def with_server(self, server: MCPServerDetail) -> MCPRegistry:
        existing = [s for s in self.servers if s.config.id != server.config.id]
        return MCPRegistry(
            servers=tuple(existing) + (server,),
            updated_at=_utcnow(),
        )

    def without_server(self, server_id: str) -> MCPRegistry:
        return MCPRegistry(
            servers=tuple(s for s in self.servers if s.config.id != server_id),
            updated_at=_utcnow(),
        )

    def list_enabled(self) -> list[MCPServerDetail]:
        return [s for s in self.servers if s.config.enabled]

    def list_by_status(self, status: MCPServerStatus) -> list[MCPServerDetail]:
        return [s for s in self.servers if s.status == status]


@dataclass(frozen=True, slots=True)
class MCPSession:
    """A session representing a long-lived MCP connection."""

    id: str
    server_id: str
    transport: MCPTransport
    status: MCPSessionStatus = MCPSessionStatus.ACTIVE
    capabilities: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)
    expires_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "server_id": self.server_id,
            "transport": self.transport.value,
            "status": self.status.value,
            "capabilities": self.capabilities,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "metadata": self.metadata,
        }

    def with_status(self, status: MCPSessionStatus) -> MCPSession:
        return MCPSession(
            id=self.id,
            server_id=self.server_id,
            transport=self.transport,
            status=status,
            capabilities=self.capabilities,
            created_at=self.created_at,
            updated_at=_utcnow(),
            expires_at=self.expires_at,
            metadata=self.metadata,
        )

    def with_capabilities(self, capabilities: dict[str, Any]) -> MCPSession:
        return MCPSession(
            id=self.id,
            server_id=self.server_id,
            transport=self.transport,
            status=self.status,
            capabilities=capabilities,
            created_at=self.created_at,
            updated_at=_utcnow(),
            expires_at=self.expires_at,
            metadata=self.metadata,
        )


@dataclass(frozen=True, slots=True)
class MCPSubscription:
    """A subscription for resource change notifications."""

    id: str
    server_id: str
    resource_uri: str
    created_at: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "server_id": self.server_id,
            "resource_uri": self.resource_uri,
            "created_at": self.created_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class MCPCapability:
    """A capability negotiated during MCP protocol handshake."""

    name: str
    version: str = "2024-11-05"
    enabled: bool = True
    config: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "enabled": self.enabled,
            "config": self.config,
        }


__all__ = [
    "MCPTransport",
    "MCPServerStatus",
    "MCPHealthStatus",
    "MCPSessionStatus",
    "MCPTool",
    "MCPToolResult",
    "MCPResource",
    "MCPResourceTemplate",
    "MCPPrompt",
    "MCPRoot",
    "MCPPermissionMapping",
    "MCPServerConfig",
    "MCPServerDetail",
    "MCPRegistry",
    "MCPSession",
    "MCPSubscription",
    "MCPCapability",
]
