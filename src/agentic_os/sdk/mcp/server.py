"""MCP Server SDK - high-level developer-facing entry point for MCP servers."""

from agentic_os.domain.mcp import (
    MCPPrompt,
    MCPResource,
    MCPServerConfig,
    MCPServerDetail,
    MCPServerStatus,
    MCPTool,
    MCPTransport,
)
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.mcp import MCPRegistryPort, MCPServerCreate

logger = get_logger("mcp.sdk.server")


class McpServerSdk:
    """Developer-facing SDK for creating and managing MCP servers.

    Usage::

        sdk = McpServerSdk(
            name="my-server",
            transport="stdio",
            command="node",
            args=["server.js"],
        )
        await sdk.initialize()
        detail = await sdk.register()
        await sdk.start()

    Auto-registers with the runtime and becomes visible in Mission Control.
    """

    def __init__(
        self,
        name: str,
        transport: str = "stdio",
        command: str | None = None,
        args: list[str] | None = None,
        url: str | None = None,
        env: dict[str, str] | None = None,
        description: str = "",
        tags: list[str] | None = None,
        config: MCPServerConfig | None = None,
    ) -> None:
        self._name = name
        self._transport = transport
        self._command = command
        self._args = args or []
        self._url = url
        self._env = env or {}
        self._description = description
        self._tags = tags or []
        self._externally_provided_config = config

        self._registry: MCPRegistryPort | None = None
        self._config: MCPServerConfig | None = None
        self._detail: MCPServerDetail | None = None
        self._tools: list[MCPTool] = []
        self._resources: list[MCPResource] = []
        self._prompts: list[MCPPrompt] = []

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """Validate configuration and prepare the server for registration."""
        logger.info("initializing mcp server", name=self._name)

        if self._externally_provided_config is not None:
            self._config = self._externally_provided_config
        else:
            transport_enum = self._resolve_transport(self._transport)

            match transport_enum:
                case MCPTransport.STDIO:
                    if not self._command:
                        msg = "command is required for stdio transport"
                        raise ValueError(msg)
                    self._config = MCPServerConfig.create_stdio(
                        name=self._name,
                        command=self._command,
                        args=self._args,
                        env=self._env,
                        description=self._description,
                        tags=self._tags,
                    )
                case MCPTransport.SSE:
                    if not self._url:
                        msg = "url is required for sse transport"
                        raise ValueError(msg)
                    self._config = MCPServerConfig.create_sse(
                        name=self._name,
                        url=self._url,
                        description=self._description,
                        tags=self._tags,
                    )
                case MCPTransport.STREAMABLE_HTTP:
                    if not self._url:
                        msg = "url is required for streamable_http transport"
                        raise ValueError(msg)
                    self._config = MCPServerConfig.create_streamable_http(
                        name=self._name,
                        url=self._url,
                        description=self._description,
                        tags=self._tags,
                    )

        self._detail = MCPServerDetail(
            config=self._config,
            status=MCPServerStatus.STOPPED,
        )

        logger.info("mcp server initialized", server_id=self._config.id)

    async def register(self, registry: MCPRegistryPort | None = None) -> MCPServerDetail:
        """Register the server with the registry port.

        Parameters
        ----------
        registry:
            Optional registry to use. If omitted, the server must have been
            registered previously via :meth:`bind_registry`.
        """
        if registry is not None:
            self._registry = registry

        if self._registry is None:
            msg = "no MCPRegistryPort available — call bind_registry() or pass registry"
            raise RuntimeError(msg)

        if self._config is None:
            await self.initialize()

        create = MCPServerCreate(
            name=self._name,
            transport=self._transport,
            command=self._command,
            args=self._args,
            env=self._env,
            url=self._url,
            description=self._description,
            tags=self._tags,
        )

        self._detail = await self._registry.register_server(create)
        # Sync local config with the registry-assigned config (IDs may differ)
        self._config = self._detail.config
        logger.info("mcp server registered", server_id=self._config.id)
        return self._detail

    async def bind_registry(self, registry: MCPRegistryPort) -> None:
        """Bind a registry port without registering yet."""
        self._registry = registry

    async def start(self) -> MCPServerDetail:
        """Start the MCP server process."""
        if self._registry is None:
            msg = "registry not bound — call bind_registry() or register() first"
            raise RuntimeError(msg)

        if self._config is None:
            await self.initialize()

        assert self._config is not None  # initialized above
        self._detail = await self._registry.start_server(self._config.id)
        self._detail = self._detail.with_status(MCPServerStatus.RUNNING)
        logger.info("mcp server started", server_id=self._config.id)
        return self._detail

    async def stop(self) -> MCPServerDetail:
        """Stop the MCP server process."""
        if self._registry is None:
            msg = "registry not bound"
            raise RuntimeError(msg)

        if self._config is None:
            msg = "server not initialized"
            raise RuntimeError(msg)

        self._detail = await self._registry.stop_server(self._config.id)
        self._detail = self._detail.with_status(MCPServerStatus.STOPPED)
        logger.info("mcp server stopped", server_id=self._config.id)
        return self._detail

    async def shutdown(self) -> None:
        """Full shutdown: stop the server and unregister it."""
        try:
            await self.stop()
        except Exception as exc:
            logger.warning("error during server stop on shutdown", error=str(exc))

        if self._registry is not None and self._config is not None:
            try:
                await self._registry.delete_server(self._config.id)
                logger.info("mcp server unregistered on shutdown", server_id=self._config.id)
            except Exception as exc:
                logger.warning("error during unregister on shutdown", error=str(exc))

        self._detail = None
        self._config = None

    # ------------------------------------------------------------------
    # Tool / Resource / Prompt management
    # ------------------------------------------------------------------

    async def add_tool(self, tool: MCPTool) -> None:
        """Add a tool definition to the server metadata."""
        self._tools.append(tool)
        name = tool.name
        logger.debug("tool added to server", tool=name)

    async def add_resource(self, resource: MCPResource) -> None:
        """Add a resource definition to the server metadata."""
        self._resources.append(resource)
        logger.debug("resource added to server", uri=resource.uri)

    async def add_prompt(self, prompt: MCPPrompt) -> None:
        """Add a prompt definition to the server metadata."""
        self._prompts.append(prompt)
        logger.debug("prompt added to server", prompt=prompt.name)

    # ------------------------------------------------------------------
    # Status / detail
    # ------------------------------------------------------------------

    def status(self) -> MCPServerStatus:
        """Return the current lifecycle status."""
        if self._detail is not None:
            return self._detail.status
        return MCPServerStatus.STOPPED

    def detail(self) -> MCPServerDetail | None:
        """Return the full detail object from the registry, or *None*."""
        return self._detail

    def config(self) -> MCPServerConfig | None:
        """Return the resolved server configuration."""
        return self._config

    # ------------------------------------------------------------------
    # Helper classmethods
    # ------------------------------------------------------------------

    @classmethod
    def create_stdio(
        cls,
        name: str,
        command: str,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        description: str = "",
    ) -> McpServerSdk:
        """Create an :class:`McpServerSdk` pre-configured for stdio transport."""
        return cls(
            name=name,
            transport="stdio",
            command=command,
            args=args,
            env=env,
            description=description,
        )

    @classmethod
    def create_sse(
        cls,
        name: str,
        url: str,
        headers: dict[str, str] | None = None,
        description: str = "",
    ) -> McpServerSdk:
        """Create an :class:`McpServerSdk` pre-configured for SSE transport."""
        return cls(
            name=name,
            transport="sse",
            url=url,
            env=headers,
            description=description,
        )

    @classmethod
    def create_streamable_http(
        cls,
        name: str,
        url: str,
        headers: dict[str, str] | None = None,
        description: str = "",
    ) -> McpServerSdk:
        """Create an :class:`McpServerSdk` pre-configured for Streamable HTTP transport."""
        return cls(
            name=name,
            transport="streamable_http",
            url=url,
            env=headers,
            description=description,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_transport(value: str) -> MCPTransport:
        normalized = value.lower().replace("-", "_")
        try:
            return MCPTransport(normalized)
        except ValueError:
            valid = [t.value for t in MCPTransport]
            msg = f"unsupported transport {value!r}, expected one of {valid}"
            raise ValueError(msg) from None
