"""MCP Registration helpers."""

from typing import Any

from agentic_os.domain.mcp import MCPServerDetail, MCPTransport
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.mcp import MCPRegistryPort, MCPServerCreate

logger = get_logger("mcp.sdk.registration")


class RegistrationHelper:
    """Helper for registering MCP servers with the runtime registry.

    Simplifies creating and registering servers by wrapping
    :class:`MCPRegistryPort` with common registration patterns.
    """

    def __init__(self, registry: MCPRegistryPort | None = None) -> None:
        self._registry = registry

    def bind(self, registry: MCPRegistryPort) -> None:
        """Bind a registry port."""
        self._registry = registry

    async def register_stdio(
        self,
        name: str,
        command: str,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        description: str = "",
    ) -> MCPServerDetail:
        """Register a stdio-based MCP server.

        Parameters
        ----------
        name:
            Display name for the server.
        command:
            The executable path.
        args:
            Command-line arguments.
        env:
            Environment variables.
        description:
            Human-readable description.

        Returns
        -------
        MCPServerDetail:
            The registered server detail.
        """
        create = MCPServerCreate(
            name=name,
            transport=MCPTransport.STDIO.value,
            command=command,
            args=args or [],
            env=env or {},
            description=description,
            server_type="custom",
        )
        logger.info("registering stdio mcp server", name=name, command=command)
        return await self._register(create)

    async def register_sse(
        self,
        name: str,
        url: str,
        headers: dict[str, str] | None = None,
        description: str = "",
    ) -> MCPServerDetail:
        """Register an SSE-based MCP server.

        Parameters
        ----------
        name:
            Display name for the server.
        url:
            The SSE endpoint URL.
        headers:
            Optional HTTP headers.
        description:
            Human-readable description.

        Returns
        -------
        MCPServerDetail:
            The registered server detail.
        """
        create = MCPServerCreate(
            name=name,
            transport=MCPTransport.SSE.value,
            url=url,
            headers=headers or {},
            description=description,
            server_type="custom",
        )
        logger.info("registering sse mcp server", name=name, url=url)
        return await self._register(create)

    async def register_builtin(
        self,
        adapter_class: type,
        config: dict[str, Any] | None = None,
    ) -> MCPServerDetail:
        """Register a built-in MCP server adapter.

        Parameters
        ----------
        adapter_class:
            The adapter class (unused directly but documents the interface).
        config:
            Optional configuration dictionary passed to the registration.

        Returns
        -------
        MCPServerDetail:
            The registered server detail.
        """
        cfg = config or {}
        create = MCPServerCreate(
            name=cfg.get("name", adapter_class.__name__),
            transport=MCPTransport.STDIO.value,
            command=cfg.get("command"),
            args=cfg.get("args", []),
            env=cfg.get("env", {}),
            description=cfg.get("description", ""),
            server_type="builtin",
        )
        logger.info("registering builtin mcp server", name=create.name)
        return await self._register(create)

    async def unregister(self, server_id: str) -> bool:
        """Unregister a previously registered server.

        Parameters
        ----------
        server_id:
            The server ID to remove.

        Returns
        -------
        bool:
            ``True`` if the server was removed.
        """
        logger.info("unregistering mcp server", server_id=server_id)
        if self._registry is None:
            msg = "no MCPRegistryPort bound — call bind() or pass registry in constructor"
            raise RuntimeError(msg)
        return await self._registry.delete_server(server_id)

    async def list_registered(self) -> list[MCPServerDetail]:
        """List all registered MCP servers."""
        logger.debug("listing registered mcp servers")
        if self._registry is None:
            msg = "no MCPRegistryPort bound — call bind() or pass registry in constructor"
            raise RuntimeError(msg)
        return await self._registry.list_servers()

    async def _register(self, create: MCPServerCreate) -> MCPServerDetail:
        if self._registry is None:
            msg = "no MCPRegistryPort bound — call bind() or pass registry in constructor"
            raise RuntimeError(msg)
        return await self._registry.register_server(create)
