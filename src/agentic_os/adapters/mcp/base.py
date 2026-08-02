"""
Base MCP Adapter

Abstract base class for all MCP adapters.
Provides default implementations for lifecycle, health, discovery, and prompting.
Subclasses must implement transport_type, invoke_tool, read_resource, and get_prompt.
"""

from abc import abstractmethod
from typing import Any

from agentic_os.domain.mcp import (
    MCPHealthStatus,
    MCPPrompt,
    MCPResource,
    MCPTool,
    MCPToolResult,
    MCPTransport,
)
from agentic_os.infrastructure.logging import get_logger


class BaseMCPAdapter:
    """
    Abstract base class for all MCP adapters.

    Subclasses must implement:
    - transport_type (abstract property)
    - invoke_tool()
    - read_resource()
    - get_prompt()

    Other methods have sensible defaults that can be overridden.
    """

    def __init__(self, name: str, config: dict[str, Any] | None = None) -> None:
        self._name = name
        self._config = config or {}
        self._log = get_logger(f"mcp.adapter.{name}")

    # ── Identity ──────────────────────────────────────────────────────────────

    @property
    def name(self) -> str:
        """Return the adapter name."""
        return self._name

    @property
    def config(self) -> dict[str, Any]:
        """Return the adapter configuration."""
        return self._config

    @property
    @abstractmethod
    def transport_type(self) -> MCPTransport:
        """Return the MCP transport type for this adapter."""
        ...

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def initialize(self) -> None:
        """Initialize the adapter. Default is a no-op."""
        self._log.info("Initializing adapter: %s", self._name)

    async def shutdown(self) -> None:
        """Shutdown the adapter. Default is a no-op."""
        self._log.info("Shutting down adapter: %s", self._name)

    # ── Health ────────────────────────────────────────────────────────────────

    async def check_health(self) -> MCPHealthStatus:
        """Check health of this adapter. Default returns HEALTHY."""
        return MCPHealthStatus.HEALTHY

    # ── Tool Operations ───────────────────────────────────────────────────────

    async def list_tools(self) -> list[MCPTool]:
        """List available tools. Default returns empty list."""
        return []

    async def invoke_tool(self, tool: str, arguments: dict[str, Any]) -> MCPToolResult:
        """Invoke a tool. Must be implemented by subclasses."""
        raise NotImplementedError(f"invoke_tool not implemented for adapter '{self._name}'")

    # ── Resource Operations ───────────────────────────────────────────────────

    async def list_resources(self) -> list[MCPResource]:
        """List available resources. Default returns empty list."""
        return []

    async def read_resource(self, uri: str) -> dict[str, Any]:
        """Read a resource by URI. Must be implemented by subclasses."""
        raise NotImplementedError(f"read_resource not implemented for adapter '{self._name}'")

    # ── Prompt Operations ─────────────────────────────────────────────────────

    async def list_prompts(self) -> list[MCPPrompt]:
        """List available prompts. Default returns empty list."""
        return []

    async def get_prompt(
        self, name: str, arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Get a prompt by name. Must be implemented by subclasses."""
        raise NotImplementedError(f"get_prompt not implemented for adapter '{self._name}'")
