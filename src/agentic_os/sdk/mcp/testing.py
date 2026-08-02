"""MCP Testing utilities - mocks, fakes, and test helpers."""

from typing import Any
from uuid import uuid4

from agentic_os.domain.mcp import (
    MCPHealthStatus,
    MCPPermissionMapping,
    MCPPrompt,
    MCPRegistry,
    MCPResource,
    MCPResourceTemplate,
    MCPServerConfig,
    MCPServerDetail,
    MCPServerStatus,
    MCPSession,
    MCPSessionStatus,
    MCPSubscription,
    MCPTool,
    MCPToolResult,
    MCPTransport,
)
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.mcp import (
    MCPServerCreate,
    MCPServerUpdate,
    MCPToolInvoke,
)

logger = get_logger("mcp.sdk.testing")


def _make_config(
    name: str = "test-server",
    transport: str = "stdio",
) -> MCPServerConfig:
    """Create a test server config with a deterministic ID."""
    return MCPServerConfig(
        id=f"test-{name}-{uuid4().hex[:8]}",
        name=name,
        transport=MCPTransport(transport),
        command="echo" if transport == "stdio" else None,
        url="http://localhost:8080" if transport == "sse" else None,
    )


class McpTestHelper:
    """Testing utilities for MCP unit and integration tests.

    Provides factory methods for creating mock domain objects so tests
    do not need to construct them from scratch.
    """

    @staticmethod
    def create_mock_tool(name: str = "test-tool", description: str = "A test tool") -> MCPTool:
        """Create a mock :class:`MCPTool` for testing."""
        return MCPTool(
            name=name,
            description=description,
            input_schema={
                "type": "object",
                "properties": {
                    "param1": {"type": "string", "description": "A test parameter"},
                },
                "required": ["param1"],
            },
        )

    @staticmethod
    def create_mock_resource(
        uri: str = "test://resource",
        name: str = "test-resource",
    ) -> MCPResource:
        """Create a mock :class:`MCPResource` for testing."""
        return MCPResource(
            uri=uri,
            name=name,
            description=f"Mock resource {name}",
            mime_type="text/plain",
        )

    @staticmethod
    def create_mock_prompt(name: str = "test-prompt") -> MCPPrompt:
        """Create a mock :class:`MCPPrompt` for testing."""
        return MCPPrompt(
            name=name,
            description=f"A test prompt named {name}",
            arguments=({"name": "topic", "description": "A topic", "required": True},),
        )

    @staticmethod
    def create_mock_server_config(
        name: str = "test-server",
        transport: str = "stdio",
    ) -> MCPServerConfig:
        """Create a mock :class:`MCPServerConfig` for testing."""
        return _make_config(name, transport)

    @staticmethod
    def create_mock_server_detail(
        config: MCPServerConfig | None = None,
    ) -> MCPServerDetail:
        """Create a mock :class:`MCPServerDetail` for testing.

        Parameters
        ----------
        config:
            Optional config; one is created automatically if omitted.
        """
        cfg = config or _make_config()
        return MCPServerDetail(
            config=cfg,
            status=MCPServerStatus.RUNNING,
            health=MCPHealthStatus.HEALTHY,
            tools=(),
        )


class FakeMCPRegistry:
    """In-memory fake implementation of :class:`MCPRegistryPort` for testing.

    Stores servers, tools, and permissions in plain dicts.  No real processes
    are spawned — all lifecycle transitions are simulated.
    """

    def __init__(self) -> None:
        self._servers: dict[str, MCPServerDetail] = {}
        self._tools: dict[str, list[MCPTool]] = {}
        self._permissions: dict[str, list[MCPPermissionMapping]] = {}

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def register_server(self, data: MCPServerCreate) -> MCPServerDetail:
        config = MCPServerConfig(
            id=str(uuid4()),
            name=data.name,
            transport=MCPTransport(data.transport),
            command=data.command,
            args=tuple(data.args),
            env=data.env,
            url=data.url,
            headers=data.headers,
            sandbox=data.sandbox,
            sandbox_config=data.sandbox_config,
            enabled=data.enabled,
            description=data.description,
            tags=tuple(data.tags),
        )
        detail = MCPServerDetail(
            config=config,
            status=MCPServerStatus.STOPPED,
        )
        self._servers[config.id] = detail
        self._tools[config.id] = []
        self._permissions[config.id] = []
        logger.debug("fake registry: server registered", server_id=config.id, name=config.name)
        return detail

    async def get_server(self, server_id: str) -> MCPServerDetail | None:
        return self._servers.get(server_id)

    async def get_server_by_name(self, name: str) -> MCPServerDetail | None:
        for detail in self._servers.values():
            if detail.config.name == name:
                return detail
        return None

    async def list_servers(
        self,
        status: MCPServerStatus | None = None,
        enabled_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[MCPServerDetail]:
        results = list(self._servers.values())
        if status is not None:
            results = [s for s in results if s.status == status]
        if enabled_only:
            results = [s for s in results if s.config.enabled]
        return results[offset : offset + limit]

    async def update_server(self, server_id: str, data: MCPServerUpdate) -> MCPServerDetail:
        existing = self._servers.get(server_id)
        if existing is None:
            msg = f"server not found: {server_id}"
            raise KeyError(msg)

        updates: dict[str, Any] = {}
        for field in (
            "name",
            "transport",
            "command",
            "description",
            "enabled",
            "sandbox",
        ):
            value = getattr(data, field, None)
            if value is not None:
                updates[field] = value

        updated_config = MCPServerConfig(
            id=existing.config.id,
            name=updates.get("name", existing.config.name),
            transport=MCPTransport(updates.get("transport", existing.config.transport.value)),
            command=updates.get("command", existing.config.command),
            args=existing.config.args,
            env=existing.config.env,
            url=existing.config.url,
            headers=existing.config.headers,
            sandbox=updates.get("sandbox", existing.config.sandbox),
            sandbox_config=existing.config.sandbox_config,
            enabled=updates.get("enabled", existing.config.enabled),
            description=updates.get("description", existing.config.description),
            tags=existing.config.tags,
        )
        updated = MCPServerDetail(
            config=updated_config,
            status=existing.status,
            tools=existing.tools,
            health=existing.health,
        )
        self._servers[server_id] = updated
        return updated

    async def delete_server(self, server_id: str) -> bool:
        if server_id in self._servers:
            del self._servers[server_id]
            self._tools.pop(server_id, None)
            self._permissions.pop(server_id, None)
            return True
        return False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start_server(self, server_id: str) -> MCPServerDetail:
        detail = self._get_or_raise(server_id)
        updated = detail.with_status(MCPServerStatus.RUNNING)
        self._servers[server_id] = updated
        return updated

    async def stop_server(self, server_id: str) -> MCPServerDetail:
        detail = self._get_or_raise(server_id)
        updated = detail.with_status(MCPServerStatus.STOPPED)
        self._servers[server_id] = updated
        return updated

    async def restart_server(self, server_id: str) -> MCPServerDetail:
        detail = self._get_or_raise(server_id)
        stopped = detail.with_status(MCPServerStatus.STOPPED)
        started = stopped.with_status(MCPServerStatus.RUNNING)
        self._servers[server_id] = started
        return started

    # ------------------------------------------------------------------
    # Tools
    # ------------------------------------------------------------------

    async def discover_tools(self, server_id: str) -> list[MCPTool]:
        self._get_or_raise(server_id)
        return self._tools.get(server_id, [])

    async def get_tools(self, server_id: str) -> list[MCPTool]:
        self._get_or_raise(server_id)
        return self._tools.get(server_id, [])

    async def invoke_tool(self, data: MCPToolInvoke) -> MCPToolResult:
        self._get_or_raise(data.server_id)
        return MCPToolResult(
            content=[{"type": "text", "text": f"fake result for {data.tool}"}],
            is_error=False,
        )

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    async def check_health(self, server_id: str) -> MCPHealthStatus:
        self._get_or_raise(server_id)
        return MCPHealthStatus.HEALTHY

    async def get_health(self, server_id: str) -> MCPHealthStatus | None:
        detail = self._servers.get(server_id)
        if detail is None:
            return None
        return detail.health

    # ------------------------------------------------------------------
    # Permissions
    # ------------------------------------------------------------------

    async def set_permissions(self, server_id: str, mappings: list[MCPPermissionMapping]) -> int:
        self._permissions[server_id] = mappings
        return len(mappings)

    async def get_permissions(self, server_id: str) -> list[MCPPermissionMapping]:
        return self._permissions.get(server_id, [])

    # ------------------------------------------------------------------
    # Resources (MCPResourceProvider)
    # ------------------------------------------------------------------

    async def list_resources(self, server_id: str) -> list[MCPResource]:
        self._get_or_raise(server_id)
        return []

    async def read_resource(self, server_id: str, uri: str) -> dict[str, Any]:
        self._get_or_raise(server_id)
        return {"uri": uri, "content": f"fake content for {uri}"}

    async def list_resource_templates(self, server_id: str) -> list[MCPResourceTemplate]:
        self._get_or_raise(server_id)
        return []

    async def subscribe_resource(self, server_id: str, uri: str) -> MCPSubscription:
        self._get_or_raise(server_id)
        return MCPSubscription(
            id=str(uuid4()),
            server_id=server_id,
            resource_uri=uri,
        )

    async def unsubscribe_resource(self, server_id: str, uri: str) -> bool:
        self._get_or_raise(server_id)
        return True

    # ------------------------------------------------------------------
    # Prompts (MCPPromptProvider)
    # ------------------------------------------------------------------

    async def list_prompts(self, server_id: str) -> list[MCPPrompt]:
        self._get_or_raise(server_id)
        return []

    async def get_prompt(
        self, server_id: str, name: str, arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        self._get_or_raise(server_id)
        return {"name": name, "messages": [], "description": f"fake prompt {name}"}

    # ------------------------------------------------------------------
    # Registry
    # ------------------------------------------------------------------

    async def get_registry(self) -> MCPRegistry:
        return MCPRegistry(servers=tuple(self._servers.values()))

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get_or_raise(self, server_id: str) -> MCPServerDetail:
        detail = self._servers.get(server_id)
        if detail is None:
            msg = f"server not found: {server_id}"
            raise KeyError(msg)
        return detail


class FakeMCPManager:
    """Fake MCP manager for integration testing.

    Simulates server lifecycle management without spawning real processes.
    Provides the same interface as the production MCP manager but backed by
    an in-memory :class:`FakeMCPRegistry` and simple session tracking.
    """

    def __init__(self) -> None:
        self.registry = FakeMCPRegistry()
        self._sessions: dict[str, MCPSession] = {}
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the fake manager."""
        self._initialized = True
        logger.debug("fake mcp manager initialized")

    async def start(self) -> None:
        """Start the fake manager (no-op beyond init)."""
        if not self._initialized:
            await self.initialize()

    async def stop(self) -> None:
        """Stop the fake manager."""
        self._initialized = False
        # Close all sessions
        for sid, session in list(self._sessions.items()):
            self._sessions[sid] = session.with_status(MCPSessionStatus.CLOSED)
        logger.debug("fake mcp manager stopped")

    async def create_session(
        self,
        server_id: str,
        transport: MCPTransport = MCPTransport.STDIO,
        capabilities: dict[str, Any] | None = None,
    ) -> MCPSession:
        """Create a simulated session for a server."""
        config = await self.registry.get_server(server_id)
        if config is None:
            # If not found in registry, create a transient session anyway
            pass

        session = MCPSession(
            id=str(uuid4()),
            server_id=server_id,
            transport=transport,
            status=MCPSessionStatus.ACTIVE,
            capabilities=capabilities or {},
        )
        self._sessions[session.id] = session
        logger.debug("fake session created", session_id=session.id, server_id=server_id)
        return session

    async def close_session(self, session_id: str) -> bool:
        """Close a simulated session."""
        session = self._sessions.get(session_id)
        if session is None:
            return False
        self._sessions[session_id] = session.with_status(MCPSessionStatus.CLOSED)
        return True

    async def list_sessions(self, server_id: str | None = None) -> list[MCPSession]:
        """List sessions, optionally filtered by server."""
        sessions = list(self._sessions.values())
        if server_id is not None:
            sessions = [s for s in sessions if s.server_id == server_id]
        return sessions

    @property
    def is_initialized(self) -> bool:
        """Whether the fake manager has been initialized."""
        return self._initialized
