"""Tests for MCP domain models."""

from uuid import UUID

import pytest

from agentic_os.domain.mcp import (
    MCPCapability,
    MCPHealthStatus,
    MCPPermissionMapping,
    MCPPrompt,
    MCPRegistry,
    MCPResource,
    MCPResourceTemplate,
    MCPRoot,
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


class TestMCPTransport:
    def test_enum_values(self) -> None:
        assert MCPTransport.STDIO.value == "stdio"
        assert MCPTransport.SSE.value == "sse"
        assert MCPTransport.STREAMABLE_HTTP.value == "streamable_http"

    def test_all_transports_defined(self) -> None:
        expected = {"stdio", "sse", "streamable_http", "http"}
        assert {t.value for t in MCPTransport} == expected


class TestMCPServerStatus:
    def test_enum_values(self) -> None:
        assert MCPServerStatus.STOPPED.value == "stopped"
        assert MCPServerStatus.STARTING.value == "starting"
        assert MCPServerStatus.RUNNING.value == "running"
        assert MCPServerStatus.STOPPING.value == "stopping"
        assert MCPServerStatus.FAILED.value == "failed"

    def test_valid_lifecycle_transitions(self) -> None:
        assert MCPServerStatus.STOPPED != MCPServerStatus.RUNNING
        assert MCPServerStatus.STARTING != MCPServerStatus.STOPPED


class TestMCPHealthStatus:
    def test_enum_values(self) -> None:
        assert MCPHealthStatus.HEALTHY.value == "healthy"
        assert MCPHealthStatus.DEGRADED.value == "degraded"
        assert MCPHealthStatus.UNHEALTHY.value == "unhealthy"
        assert MCPHealthStatus.UNKNOWN.value == "unknown"


class TestMCPSessionStatus:
    def test_enum_values(self) -> None:
        assert MCPSessionStatus.ACTIVE.value == "active"
        assert MCPSessionStatus.IDLE.value == "idle"
        assert MCPSessionStatus.EXPIRED.value == "expired"
        assert MCPSessionStatus.CLOSED.value == "closed"


class TestMCPTool:
    def test_create(self) -> None:
        tool = MCPTool(name="read_file", description="Read a file", input_schema={"type": "object"})
        assert tool.name == "read_file"
        assert tool.description == "Read a file"
        assert tool.input_schema == {"type": "object"}
        assert tool.output_schema is None

    def test_create_with_output_schema(self) -> None:
        tool = MCPTool(
            name="write_file",
            description="Write to a file",
            input_schema={"type": "object"},
            output_schema={"type": "string"},
        )
        assert tool.output_schema == {"type": "string"}

    def test_to_dict(self) -> None:
        tool = MCPTool(name="test", description="desc", input_schema={})
        d = tool.to_dict()
        assert d["name"] == "test"
        assert d["description"] == "desc"
        assert d["inputSchema"] == {}

    def test_from_mcp(self) -> None:
        raw = {"name": "tool1", "description": "A tool", "inputSchema": {"type": "object"}}
        tool = MCPTool.from_mcp(raw)
        assert tool.name == "tool1"
        assert tool.description == "A tool"
        assert tool.input_schema == {"type": "object"}

    def test_from_mcp_empty(self) -> None:
        tool = MCPTool.from_mcp({})
        assert tool.name == ""
        assert tool.description == ""
        assert tool.input_schema == {}

    def test_frozen(self) -> None:
        tool = MCPTool(name="n", description="d", input_schema={})
        with pytest.raises(AttributeError):
            tool.name = "other"  # type: ignore[misc]


class TestMCPToolResult:
    def test_create(self) -> None:
        result = MCPToolResult(content=[{"type": "text", "text": "hello"}])
        assert result.content == [{"type": "text", "text": "hello"}]
        assert not result.is_error

    def test_create_error(self) -> None:
        result = MCPToolResult(content=[{"type": "text", "text": "error"}], is_error=True)
        assert result.is_error

    def test_to_dict(self) -> None:
        result = MCPToolResult(content=[{"type": "text", "text": "ok"}])
        d = result.to_dict()
        assert d["content"] == [{"type": "text", "text": "ok"}]
        assert not d["isError"]


class TestMCPResource:
    def test_create(self) -> None:
        r = MCPResource(uri="file:///tmp/data", name="data", description="Some data")
        assert r.uri == "file:///tmp/data"
        assert r.name == "data"
        assert r.description == "Some data"

    def test_create_with_mime_type(self) -> None:
        r = MCPResource(uri="file:///data.csv", name="csv", mime_type="text/csv")
        assert r.mime_type == "text/csv"

    def test_to_dict(self) -> None:
        r = MCPResource(uri="uri", name="n", description="d", mime_type="text/plain")
        d = r.to_dict()
        assert d["uri"] == "uri"
        assert d["name"] == "n"
        assert d["mimeType"] == "text/plain"

    def test_from_mcp(self) -> None:
        raw = {"uri": "file:///x", "name": "x", "description": "desc"}
        r = MCPResource.from_mcp(raw)
        assert r.uri == "file:///x"

    def test_from_mcp_empty(self) -> None:
        r = MCPResource.from_mcp({})
        assert r.uri == ""
        assert r.name == ""


class TestMCPResourceTemplate:
    def test_create(self) -> None:
        t = MCPResourceTemplate(uri_template="file:///{path}", name="file-template")
        assert t.uri_template == "file:///{path}"
        assert t.name == "file-template"

    def test_to_dict(self) -> None:
        t = MCPResourceTemplate(uri_template="tpl", name="n")
        d = t.to_dict()
        assert d["uriTemplate"] == "tpl"


class TestMCPPrompt:
    def test_create(self) -> None:
        p = MCPPrompt(name="greet", description="A greeting prompt")
        assert p.name == "greet"
        assert p.description == "A greeting prompt"

    def test_create_with_arguments(self) -> None:
        p = MCPPrompt(
            name="ask",
            description="Ask a question",
            arguments=({"name": "question", "type": "string"},),
        )
        assert len(p.arguments) == 1

    def test_to_dict(self) -> None:
        p = MCPPrompt(name="p", description="d")
        d = p.to_dict()
        assert d["name"] == "p"

    def test_from_mcp(self) -> None:
        raw = {"name": "p1", "description": "d1", "arguments": []}
        p = MCPPrompt.from_mcp(raw)
        assert p.name == "p1"

    def test_from_mcp_empty(self) -> None:
        p = MCPPrompt.from_mcp({})
        assert p.name == ""


class TestMCPRoot:
    def test_create(self) -> None:
        root = MCPRoot(uri="/home/user/project", name="my-project")
        assert root.uri == "/home/user/project"
        assert root.name == "my-project"

    def test_create_without_name(self) -> None:
        root = MCPRoot(uri="/tmp")
        assert root.name is None

    def test_to_dict(self) -> None:
        root = MCPRoot(uri="/a", name="b")
        d = root.to_dict()
        assert d["uri"] == "/a"
        assert d["name"] == "b"


class TestMCPPermissionMapping:
    def test_create(self) -> None:
        m = MCPPermissionMapping(tool_name="read_file", capability="mcp.tool.invoke")
        assert m.tool_name == "read_file"
        assert m.capability == "mcp.tool.invoke"

    def test_create_with_description(self) -> None:
        m = MCPPermissionMapping(
            tool_name="delete",
            capability="mcp.tool.invoke",
            description="Delete files",
        )
        assert m.description == "Delete files"

    def test_to_dict(self) -> None:
        m = MCPPermissionMapping(tool_name="t", capability="c")
        d = m.to_dict()
        assert d["tool_name"] == "t"
        assert d["capability"] == "c"


class TestMCPServerConfig:
    def test_create_stdio(self) -> None:
        config = MCPServerConfig.create_stdio(
            name="test-server",
            command="node",
            args=["server.js"],
            description="Test MCP server",
        )
        assert config.name == "test-server"
        assert config.transport == MCPTransport.STDIO
        assert config.command == "node"
        assert config.args == ("server.js",)
        assert config.description == "Test MCP server"
        assert config.enabled
        assert config.sandbox

    def test_create_sse(self) -> None:
        config = MCPServerConfig.create_sse(
            name="sse-server",
            url="http://localhost:3000/mcp",
            headers={"Authorization": "Bearer token"},
        )
        assert config.name == "sse-server"
        assert config.transport == MCPTransport.SSE
        assert config.url == "http://localhost:3000/mcp"
        assert config.headers == {"Authorization": "Bearer token"}

    def test_create_streamable_http(self) -> None:
        config = MCPServerConfig.create_streamable_http(
            name="http-server",
            url="http://localhost:8080/mcp",
        )
        assert config.name == "http-server"
        assert config.transport == MCPTransport.STREAMABLE_HTTP
        assert config.url == "http://localhost:8080/mcp"

    def test_to_dict(self) -> None:
        config = MCPServerConfig.create_stdio(name="srv", command="cmd")
        d = config.to_dict()
        assert d["name"] == "srv"
        assert d["transport"] == "stdio"
        assert d["command"] == "cmd"
        assert isinstance(d["created_at"], str)
        assert isinstance(d["id"], str)

    def test_with_enabled(self) -> None:
        config = MCPServerConfig.create_stdio(name="srv", command="cmd")
        disabled = config.with_enabled(False)
        assert not disabled.enabled
        assert config.enabled  # original unchanged

    def test_with_sandbox(self) -> None:
        config = MCPServerConfig.create_stdio(name="srv", command="cmd")
        sandboxed = config.with_sandbox(False)
        assert not sandboxed.sandbox
        assert config.sandbox  # original unchanged

    def test_with_sandbox_config(self) -> None:
        config = MCPServerConfig.create_stdio(name="srv", command="cmd")
        updated = config.with_sandbox(True, {"allowed_dirs": ["/tmp"]})
        assert updated.sandbox_config == {"allowed_dirs": ["/tmp"]}

    def test_generates_unique_ids(self) -> None:
        c1 = MCPServerConfig.create_stdio(name="s1", command="c")
        c2 = MCPServerConfig.create_stdio(name="s2", command="c")
        assert c1.id != c2.id

    def test_valid_uuid(self) -> None:
        config = MCPServerConfig.create_stdio(name="srv", command="cmd")
        UUID(config.id)  # must not raise

    def test_defaults(self) -> None:
        config = MCPServerConfig.create_stdio(name="defaults", command="cmd")
        assert config.health_check_interval_seconds == 30
        assert config.health_check_timeout_seconds == 10
        assert config.tags == ()
        assert config.env == {}


class TestMCPServerDetail:
    def test_create(self) -> None:
        config = MCPServerConfig.create_stdio(name="srv", command="cmd")
        detail = MCPServerDetail(config=config, status=MCPServerStatus.STOPPED)
        assert detail.config.name == "srv"
        assert detail.status == MCPServerStatus.STOPPED
        assert detail.health == MCPHealthStatus.UNKNOWN
        assert detail.restart_count == 0

    def test_to_dict(self) -> None:
        config = MCPServerConfig.create_stdio(name="srv", command="cmd")
        detail = MCPServerDetail(config=config, status=MCPServerStatus.RUNNING)
        d = detail.to_dict()
        assert d["status"] == "running"
        assert isinstance(d["config"], dict)

    def test_with_status_updates_started_at(self) -> None:
        config = MCPServerConfig.create_stdio(name="srv", command="cmd")
        detail = MCPServerDetail(config=config, status=MCPServerStatus.STOPPED)
        started = detail.with_status(MCPServerStatus.STARTING)
        assert started.status == MCPServerStatus.STARTING
        assert started.started_at is not None

    def test_with_status_updates_stopped_at(self) -> None:
        config = MCPServerConfig.create_stdio(name="srv", command="cmd")
        detail = MCPServerDetail(config=config, status=MCPServerStatus.RUNNING)
        stopped = detail.with_status(MCPServerStatus.STOPPED)
        assert stopped.status == MCPServerStatus.STOPPED
        assert stopped.stopped_at is not None

    def test_with_status_increments_restart_on_failed(self) -> None:
        config = MCPServerConfig.create_stdio(name="srv", command="cmd")
        detail = MCPServerDetail(config=config, status=MCPServerStatus.RUNNING)
        failed = detail.with_status(MCPServerStatus.FAILED)
        assert failed.restart_count == 1

    def test_with_tools(self) -> None:
        config = MCPServerConfig.create_stdio(name="srv", command="cmd")
        detail = MCPServerDetail(config=config, status=MCPServerStatus.STOPPED)
        tools = [MCPTool(name="t1", description="d", input_schema={})]
        updated = detail.with_tools(tools)
        assert len(updated.tools) == 1
        assert updated.tools[0].name == "t1"

    def test_with_health(self) -> None:
        config = MCPServerConfig.create_stdio(name="srv", command="cmd")
        detail = MCPServerDetail(config=config, status=MCPServerStatus.RUNNING)
        healthy = detail.with_health(MCPHealthStatus.HEALTHY)
        assert healthy.health == MCPHealthStatus.HEALTHY
        assert healthy.last_health_check is not None

    def test_with_health_details(self) -> None:
        config = MCPServerConfig.create_stdio(name="srv", command="cmd")
        detail = MCPServerDetail(config=config, status=MCPServerStatus.RUNNING)
        updated = detail.with_health(MCPHealthStatus.DEGRADED, {"memory": "high"})
        assert updated.health_details == {"memory": "high"}


class TestMCPRegistry:
    def test_empty_registry(self) -> None:
        reg = MCPRegistry()
        assert len(reg.servers) == 0

    def test_with_server_adds(self) -> None:
        reg = MCPRegistry()
        config = MCPServerConfig.create_stdio(name="srv", command="cmd")
        detail = MCPServerDetail(config=config, status=MCPServerStatus.STOPPED)
        reg2 = reg.with_server(detail)
        assert len(reg2.servers) == 1
        assert len(reg.servers) == 0  # original unchanged

    def test_get_server_by_id(self) -> None:
        config = MCPServerConfig.create_stdio(name="srv", command="cmd")
        detail = MCPServerDetail(config=config, status=MCPServerStatus.STOPPED)
        reg = MCPRegistry(servers=(detail,))
        found = reg.get_server(config.id)
        assert found is not None
        assert found.config.id == config.id

    def test_get_server_by_name(self) -> None:
        config = MCPServerConfig.create_stdio(name="srv", command="cmd")
        detail = MCPServerDetail(config=config, status=MCPServerStatus.STOPPED)
        reg = MCPRegistry(servers=(detail,))
        found = reg.get_server("srv")
        assert found is not None

    def test_get_server_nonexistent(self) -> None:
        reg = MCPRegistry()
        assert reg.get_server("missing") is None

    def test_get_server_by_name_method(self) -> None:
        config = MCPServerConfig.create_stdio(name="my-server", command="cmd")
        detail = MCPServerDetail(config=config, status=MCPServerStatus.STOPPED)
        reg = MCPRegistry(servers=(detail,))
        found = reg.get_server_by_name("my-server")
        assert found is not None
        assert found.config.name == "my-server"

    def test_without_server(self) -> None:
        config = MCPServerConfig.create_stdio(name="srv", command="cmd")
        detail = MCPServerDetail(config=config, status=MCPServerStatus.STOPPED)
        reg = MCPRegistry(servers=(detail,))
        reg2 = reg.without_server(config.id)
        assert len(reg2.servers) == 0

    def test_without_server_nonexistent(self) -> None:
        reg = MCPRegistry()
        reg2 = reg.without_server("missing")
        assert len(reg2.servers) == 0

    def test_list_enabled(self) -> None:
        cfg1 = MCPServerConfig.create_stdio(name="s1", command="c")
        cfg2 = MCPServerConfig.create_stdio(name="s2", command="c").with_enabled(False)
        d1 = MCPServerDetail(config=cfg1, status=MCPServerStatus.STOPPED)
        d2 = MCPServerDetail(config=cfg2, status=MCPServerStatus.STOPPED)
        reg = MCPRegistry(servers=(d1, d2))
        enabled = reg.list_enabled()
        assert len(enabled) == 1
        assert enabled[0].config.name == "s1"

    def test_list_by_status(self) -> None:
        cfg1 = MCPServerConfig.create_stdio(name="s1", command="c")
        cfg2 = MCPServerConfig.create_stdio(name="s2", command="c")
        d1 = MCPServerDetail(config=cfg1, status=MCPServerStatus.RUNNING)
        d2 = MCPServerDetail(config=cfg2, status=MCPServerStatus.STOPPED)
        reg = MCPRegistry(servers=(d1, d2))
        running = reg.list_by_status(MCPServerStatus.RUNNING)
        assert len(running) == 1

    def test_to_dict(self) -> None:
        config = MCPServerConfig.create_stdio(name="srv", command="cmd")
        detail = MCPServerDetail(config=config, status=MCPServerStatus.STOPPED)
        reg = MCPRegistry(servers=(detail,))
        d = reg.to_dict()
        assert "servers" in d
        assert "updated_at" in d
        assert len(d["servers"]) == 1

    def test_update_timestamp(self) -> None:
        reg = MCPRegistry()
        cfg = MCPServerConfig.create_stdio(name="srv", command="cmd")
        d = MCPServerDetail(config=cfg, status=MCPServerStatus.STOPPED)
        reg2 = reg.with_server(d)
        assert reg2.updated_at >= reg.updated_at


class TestMCPSession:
    def test_create(self) -> None:
        session = MCPSession(id="sess-1", server_id="srv-1", transport=MCPTransport.STDIO)
        assert session.id == "sess-1"
        assert session.server_id == "srv-1"
        assert session.status == MCPSessionStatus.ACTIVE

    def test_to_dict(self) -> None:
        session = MCPSession(id="s1", server_id="srv1", transport=MCPTransport.SSE)
        d = session.to_dict()
        assert d["id"] == "s1"
        assert d["status"] == "active"
        assert d["transport"] == "sse"

    def test_with_status(self) -> None:
        session = MCPSession(id="s1", server_id="srv1", transport=MCPTransport.STDIO)
        closed = session.with_status(MCPSessionStatus.CLOSED)
        assert closed.status == MCPSessionStatus.CLOSED
        assert session.status == MCPSessionStatus.ACTIVE  # original unchanged

    def test_with_capabilities(self) -> None:
        session = MCPSession(id="s1", server_id="srv1", transport=MCPTransport.STDIO)
        caps = {"tools": {"listChanged": True}}
        updated = session.with_capabilities(caps)
        assert updated.capabilities == caps


class TestMCPSubscription:
    def test_create(self) -> None:
        sub = MCPSubscription(id="sub-1", server_id="srv-1", resource_uri="file:///data")
        assert sub.id == "sub-1"
        assert sub.server_id == "srv-1"
        assert sub.resource_uri == "file:///data"

    def test_to_dict(self) -> None:
        sub = MCPSubscription(id="s1", server_id="srv1", resource_uri="uri")
        d = sub.to_dict()
        assert d["resource_uri"] == "uri"
        assert d["server_id"] == "srv1"


class TestMCPCapability:
    def test_create(self) -> None:
        cap = MCPCapability(name="tools", version="2024-11-05")
        assert cap.name == "tools"
        assert cap.version == "2024-11-05"
        assert cap.enabled

    def test_to_dict(self) -> None:
        cap = MCPCapability(name="resources", enabled=True)
        d = cap.to_dict()
        assert d["name"] == "resources"
        assert d["enabled"]

    def test_with_config(self) -> None:
        cap = MCPCapability(name="sampling", config={"maxTokens": 1000})
        assert cap.config == {"maxTokens": 1000}
