"""MCP Prompt SDK - prompt discovery and retrieval."""

from typing import Any

from agentic_os.domain.mcp import MCPPrompt
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.mcp import MCPPromptProvider

logger = get_logger("mcp.sdk.prompt")


class PromptSdk:
    """SDK for MCP prompt operations.

    Wraps an :class:`MCPPromptProvider` to provide a clean developer API.
    """

    def __init__(self, provider: MCPPromptProvider) -> None:
        self._provider = provider

    async def list_prompts(self, server_id: str) -> list[MCPPrompt]:
        """List all prompts from the given MCP server."""
        logger.info("listing prompts", server_id=server_id)
        try:
            prompts = await self._provider.list_prompts(server_id)
            logger.debug("prompts listed", server_id=server_id, count=len(prompts))
            return prompts
        except Exception:
            logger.exception("failed to list prompts", server_id=server_id)
            raise

    async def get_prompt(
        self,
        server_id: str,
        name: str,
        args: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Get a specific prompt by name, with optional arguments."""
        logger.info("getting prompt", server_id=server_id, name=name)
        try:
            return await self._provider.get_prompt(server_id, name, args)
        except Exception:
            logger.exception("failed to get prompt", server_id=server_id, name=name)
            raise
