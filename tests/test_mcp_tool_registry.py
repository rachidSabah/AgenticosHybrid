"""Tests for MCP Tool Registry."""

import pytest

from agentic_os.core.mcp.tool_registry import TOOL_CATEGORIES, MCPToolRegistry, ToolDefinition


@pytest.fixture
def tool_registry():
    return MCPToolRegistry()


@pytest.fixture
def sample_tool():
    return ToolDefinition(
        name="read-file",
        server_id="srv1",
        description="Read a file from the filesystem",
        input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
        categories=["file_system", "utility"],
        tags=["file", "read", "fs"],
    )


class TestMCPToolRegistryRegistration:
    def test_register_tool(self, tool_registry, sample_tool) -> None:
        tool_registry.register(sample_tool)
        assert len(tool_registry.list_tools()) == 1

    def test_register_duplicate(self, tool_registry, sample_tool) -> None:
        tool_registry.register(sample_tool)
        tool_registry.register(sample_tool)
        assert len(tool_registry.list_tools()) == 1

    def test_unregister_tool(self, tool_registry, sample_tool) -> None:
        tool_registry.register(sample_tool)
        assert tool_registry.unregister("srv1", "read-file")
        assert len(tool_registry.list_tools()) == 0

    def test_unregister_nonexistent(self, tool_registry) -> None:
        assert not tool_registry.unregister("srv1", "nonexistent")

    def test_get_tool(self, tool_registry, sample_tool) -> None:
        tool_registry.register(sample_tool)
        tool = tool_registry.get_tool("srv1", "read-file")
        assert tool is not None
        assert tool.name == "read-file"

    def test_get_tool_not_found(self, tool_registry) -> None:
        assert tool_registry.get_tool("srv1", "nonexistent") is None

    def test_get_server_tools(self, tool_registry, sample_tool) -> None:
        tool_registry.register(sample_tool)
        tool2 = ToolDefinition(name="write-file", server_id="srv1", description="Write a file")
        tool_registry.register(tool2)
        tools = tool_registry.get_server_tools("srv1")
        assert len(tools) == 2

    def test_clear_server(self, tool_registry, sample_tool) -> None:
        tool_registry.register(sample_tool)
        tool_registry.clear_server("srv1")
        assert len(tool_registry.list_tools()) == 0

    def test_clear(self, tool_registry, sample_tool) -> None:
        tool_registry.register(sample_tool)
        tool_registry.clear()
        assert len(tool_registry.list_tools()) == 0


class TestMCPToolRegistrySearch:
    def test_find_by_category(self, tool_registry, sample_tool) -> None:
        tool_registry.register(sample_tool)
        results = tool_registry.find_tools_by_category("file_system")
        assert len(results) == 1
        assert results[0].name == "read-file"

    def test_find_by_category_empty(self, tool_registry) -> None:
        results = tool_registry.find_tools_by_category("database")
        assert len(results) == 0

    def test_find_by_tag(self, tool_registry, sample_tool) -> None:
        tool_registry.register(sample_tool)
        results = tool_registry.find_tools_by_tag("read")
        assert len(results) == 1

    def test_search_tools(self, tool_registry, sample_tool) -> None:
        tool_registry.register(sample_tool)
        results = tool_registry.search_tools("file")
        assert len(results) == 1

    def test_search_tools_no_match(self, tool_registry, sample_tool) -> None:
        tool_registry.register(sample_tool)
        results = tool_registry.search_tools("zzznonexistent")
        assert len(results) == 0


class TestMCPToolRegistryLifecycle:
    def test_enable_tool(self, tool_registry, sample_tool) -> None:
        tool_registry.register(sample_tool)
        assert tool_registry.disable_tool("srv1", "read-file")
        assert not tool_registry.get_tool("srv1", "read-file").enabled
        assert tool_registry.enable_tool("srv1", "read-file")
        assert tool_registry.get_tool("srv1", "read-file").enabled

    def test_enable_nonexistent(self, tool_registry) -> None:
        assert not tool_registry.enable_tool("srv1", "nonexistent")

    def test_get_enabled_tools(self, tool_registry, sample_tool) -> None:
        tool_registry.register(sample_tool)
        tool2 = ToolDefinition(
            name="disabled-tool", server_id="srv1", description="Disabled", enabled=False
        )
        tool_registry.register(tool2)
        enabled = tool_registry.get_enabled_tools("srv1")
        assert len(enabled) == 1
        assert enabled[0].name == "read-file"

    def test_get_stats(self, tool_registry, sample_tool) -> None:
        tool_registry.register(sample_tool)
        stats = tool_registry.get_stats()
        assert stats["total_tools"] == 1
        assert stats["total_servers"] == 1
        assert "srv1" in stats["tools_per_server"]


class TestMCPToolRegistryConstants:
    def test_tool_categories_defined(self) -> None:
        assert "file_system" in TOOL_CATEGORIES
        assert "database" in TOOL_CATEGORIES
        assert "api" in TOOL_CATEGORIES
        assert "utility" in TOOL_CATEGORIES
