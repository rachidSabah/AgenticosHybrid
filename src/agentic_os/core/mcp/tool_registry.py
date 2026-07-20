"""
MCP Tool Registry

Standalone registry for managing MCP tool definitions across all servers.
Provides tool lookup, categorization, discovery, and lifecycle management.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from agentic_os.infrastructure.logging import get_logger

log = get_logger("mcp.tool_registry")


TOOL_CATEGORIES: list[str] = [
    "file_system",
    "database",
    "api",
    "code",
    "system",
    "ai_ml",
    "communication",
    "utility",
]


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class ToolDefinition:
    """A registered tool definition."""

    name: str
    server_id: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    categories: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    version: str = "1.0.0"
    enabled: bool = True
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)


class MCPToolRegistry:
    """Registry for MCP tool definitions."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}
        self._server_tools: dict[str, list[str]] = {}

    def register(self, tool: ToolDefinition) -> None:
        key = f"{tool.server_id}:{tool.name}"
        self._tools[key] = tool
        if tool.server_id not in self._server_tools:
            self._server_tools[tool.server_id] = []
        if tool.name not in self._server_tools[tool.server_id]:
            self._server_tools[tool.server_id].append(tool.name)
        log.info(f"Registered tool '{tool.name}' for server {tool.server_id}")

    def unregister(self, server_id: str, tool_name: str) -> bool:
        key = f"{server_id}:{tool_name}"
        if key in self._tools:
            del self._tools[key]
            server_tools = self._server_tools.get(server_id, [])
            if tool_name in server_tools:
                server_tools.remove(tool_name)
            log.info(f"Unregistered tool '{tool_name}' for server {server_id}")
            return True
        return False

    def get_tool(self, server_id: str, tool_name: str) -> ToolDefinition | None:
        return self._tools.get(f"{server_id}:{tool_name}")

    def get_server_tools(self, server_id: str) -> list[ToolDefinition]:
        return [
            self._tools[f"{server_id}:{name}"]
            for name in self._server_tools.get(server_id, [])
            if f"{server_id}:{name}" in self._tools
        ]

    def list_tools(self) -> list[ToolDefinition]:
        return list(self._tools.values())

    def find_tools_by_category(self, category: str) -> list[ToolDefinition]:
        return [t for t in self._tools.values() if category in t.categories]

    def find_tools_by_tag(self, tag: str) -> list[ToolDefinition]:
        return [t for t in self._tools.values() if tag in t.tags]

    def search_tools(self, query: str) -> list[ToolDefinition]:
        q = query.lower()
        return [
            t for t in self._tools.values() if q in t.name.lower() or q in t.description.lower()
        ]

    def enable_tool(self, server_id: str, tool_name: str) -> bool:
        tool = self.get_tool(server_id, tool_name)
        if tool:
            tool.enabled = True
            tool.updated_at = _utcnow()
            return True
        return False

    def disable_tool(self, server_id: str, tool_name: str) -> bool:
        tool = self.get_tool(server_id, tool_name)
        if tool:
            tool.enabled = False
            tool.updated_at = _utcnow()
            return True
        return False

    def get_enabled_tools(self, server_id: str) -> list[ToolDefinition]:
        return [t for t in self.get_server_tools(server_id) if t.enabled]

    def get_stats(self) -> dict[str, Any]:
        return {
            "total_tools": len(self._tools),
            "total_servers": len(self._server_tools),
            "tools_per_server": {sid: len(tools) for sid, tools in self._server_tools.items()},
        }

    def clear_server(self, server_id: str) -> None:
        names = self._server_tools.pop(server_id, [])
        for name in names:
            self._tools.pop(f"{server_id}:{name}", None)

    def clear(self) -> None:
        self._tools.clear()
        self._server_tools.clear()


__all__ = [
    "MCPToolRegistry",
    "ToolDefinition",
    "TOOL_CATEGORIES",
]
