"""MCP Tool SDK - tool builder, discovery, and invocation."""

from typing import Any

from agentic_os.domain.mcp import MCPTool, MCPToolResult
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.mcp import MCPRegistryPort, MCPToolInvoke

logger = get_logger("mcp.sdk.tool")


class ToolBuilder:
    """Fluent builder for constructing :class:`MCPTool` instances.

    Usage::

        tool = (
            ToolBuilder.create("get_weather")
            .description("Get current weather for a location")
            .string_param("location", "City name", required=True)
            .string_param("units", "metric or imperial", required=False)
            .build()
        )
    """
    def __init__(self, name: str) -> None:
        self._name = name
        self._description = ""
        self._input_schema: dict[str, Any] = {"type": "object", "properties": {}, "required": []}
        self._output_schema: dict[str, Any] | None = None

    @classmethod
    def create(cls, name: str) -> ToolBuilder:
        """Start building a tool with the given *name*."""
        return cls(name)

    def description(self, desc: str) -> ToolBuilder:
        """Set the tool description."""
        self._description = desc
        return self

    def input_schema(self, schema: dict[str, Any]) -> ToolBuilder:
        """Set the input schema directly."""
        self._input_schema = schema
        return self

    def output_schema(self, schema: dict[str, Any] | None) -> ToolBuilder:
        """Set the output schema (optional)."""
        self._output_schema = schema
        return self

    def string_param(self, name: str, description: str = "", required: bool = True) -> ToolBuilder:
        """Add a string parameter to the input schema."""
        self._input_schema["properties"][name] = {"type": "string", "description": description}
        if required and name not in self._input_schema["required"]:
            self._input_schema["required"].append(name)
        return self

    def integer_param(self, name: str, description: str = "", required: bool = True) -> ToolBuilder:
        """Add an integer parameter to the input schema."""
        self._input_schema["properties"][name] = {"type": "integer", "description": description}
        if required and name not in self._input_schema["required"]:
            self._input_schema["required"].append(name)
        return self

    def boolean_param(self, name: str, description: str = "", required: bool = True) -> ToolBuilder:
        """Add a boolean parameter to the input schema."""
        self._input_schema["properties"][name] = {"type": "boolean", "description": description}
        if required and name not in self._input_schema["required"]:
            self._input_schema["required"].append(name)
        return self

    def build(self) -> MCPTool:
        """Construct the :class:`MCPTool` instance."""
        return MCPTool(
            name=self._name,
            description=self._description,
            input_schema=self._input_schema,
            output_schema=self._output_schema,
        )


class ToolSdk:
    """SDK for tool discovery and invocation.

    Wraps an :class:`MCPRegistryPort` to provide a clean developer API.
    """

    def __init__(self, registry: MCPRegistryPort) -> None:
        self._registry = registry

    async def discover(self, server_id: str) -> list[MCPTool]:
        """Discover tools from the given server (performs live discovery)."""
        logger.info("discovering tools", server_id=server_id)
        try:
            tools = await self._registry.discover_tools(server_id)
            logger.info("tools discovered", server_id=server_id, count=len(tools))
            return tools
        except Exception:
            logger.exception("failed to discover tools", server_id=server_id)
            raise

    async def invoke(self, server_id: str, tool: str, args: dict[str, Any]) -> MCPToolResult:
        """Invoke a tool on the given server."""
        logger.info("invoking tool", server_id=server_id, tool=tool)
        try:
            invoke_data = MCPToolInvoke(server_id=server_id, tool=tool, args=args)
            result = await self._registry.invoke_tool(invoke_data)
            return result
        except Exception:
            logger.exception("failed to invoke tool", server_id=server_id, tool=tool)
            raise

    async def get_cached(self, server_id: str) -> list[MCPTool]:
        """Get previously cached tools for a server (no live discovery)."""
        logger.debug("getting cached tools", server_id=server_id)
        try:
            return await self._registry.get_tools(server_id)
        except Exception:
            logger.exception("failed to get cached tools", server_id=server_id)
            raise
