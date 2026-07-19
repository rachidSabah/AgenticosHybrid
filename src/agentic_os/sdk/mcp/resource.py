"""MCP Resource SDK - resource discovery, reading, and subscription."""

from typing import Any

from agentic_os.domain.mcp import MCPResource, MCPResourceTemplate, MCPSubscription
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.mcp import MCPResourceProvider

logger = get_logger("mcp.sdk.resource")


class ResourceSdk:
    """SDK for MCP resource operations.

    Wraps an :class:`MCPResourceProvider` to provide a clean developer API.
    """

    def __init__(self, provider: MCPResourceProvider) -> None:
        self._provider = provider

    async def list_resources(self, server_id: str) -> list[MCPResource]:
        """List all resources from the given MCP server."""
        logger.info("listing resources", server_id=server_id)
        try:
            resources = await self._provider.list_resources(server_id)
            logger.debug("resources listed", server_id=server_id, count=len(resources))
            return resources
        except Exception:
            logger.exception("failed to list resources", server_id=server_id)
            raise

    async def read_resource(self, server_id: str, uri: str) -> dict[str, Any]:
        """Read a specific resource by URI."""
        logger.info("reading resource", server_id=server_id, uri=uri)
        try:
            return await self._provider.read_resource(server_id, uri)
        except Exception:
            logger.exception("failed to read resource", server_id=server_id, uri=uri)
            raise

    async def list_templates(self, server_id: str) -> list[MCPResourceTemplate]:
        """List resource templates from the given MCP server."""
        logger.info("listing resource templates", server_id=server_id)
        try:
            return await self._provider.list_resource_templates(server_id)
        except Exception:
            logger.exception("failed to list resource templates", server_id=server_id)
            raise

    async def subscribe(self, server_id: str, uri: str) -> MCPSubscription:
        """Subscribe to resource change notifications."""
        logger.info("subscribing to resource", server_id=server_id, uri=uri)
        try:
            return await self._provider.subscribe_resource(server_id, uri)
        except Exception:
            logger.exception("failed to subscribe to resource", server_id=server_id, uri=uri)
            raise

    async def unsubscribe(self, server_id: str, uri: str) -> bool:
        """Unsubscribe from resource change notifications."""
        logger.info("unsubscribing from resource", server_id=server_id, uri=uri)
        try:
            return await self._provider.unsubscribe_resource(server_id, uri)
        except Exception:
            logger.exception("failed to unsubscribe from resource", server_id=server_id, uri=uri)
            raise

    async def list_changed(self, server_id: str) -> list[MCPResource]:
        """List all resources that have changed (re-read from server).

        This is a convenience method that re-reads all resources from the
        server — equivalent to :meth:`list_resources`.
        """
        logger.info("listing changed resources", server_id=server_id)
        return await self.list_resources(server_id)
