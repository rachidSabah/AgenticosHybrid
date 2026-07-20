# MCP SDK Guide

## Overview

The MCP SDK allows third parties to build custom MCP servers without modifying the kernel. This guide covers the SDK components, registration process, and best practices.

## SDK Components

```
agentic_os/sdk/mcp/
├── __init__.py
├── server.py      - Server SDK
├── tool.py        - Tool SDK
├── resource.py    - Resource SDK
├── prompt.py      - Prompt SDK
├── auth.py        - Authentication helpers
├── validation.py - Validation helpers
├── testing.py     - Testing helpers
├── registration.py- Registration helpers
└── config.py      - Configuration helpers
```

## Creating an MCP Server

### Basic Server Structure

```python
from agentic_os.sdk.mcp.server import MCPServer
from agentic_os.sdk.mcp.tool import tool
from agentic_os.sdk.mcp.resource import resource
from agentic_os.sdk.mcp.prompt import prompt

class MyServer(MCPServer):
    """Custom MCP server implementation."""

    @tool(name="greet", description="Greet a user")
    async def greet(self, name: str) -> str:
        return f"Hello, {name}!"

    @tool(name="calculate", description="Perform a calculation")
    async def calculate(self, a: float, b: float, operation: str = "add") -> float:
        if operation == "add":
            return a + b
        elif operation == "subtract":
            return a - b
        elif operation == "multiply":
            return a * b
        elif operation == "divide":
            return a / b
        raise ValueError(f"Unknown operation: {operation}")

    @resource(uri="config://settings", name="Settings", mime_type="application/json")
    async def get_settings(self) -> dict:
        return {"theme": "dark", "language": "en"}

    @prompt(name="generate_report", description="Generate a report")
    async def generate_report(self, title: str, data: list[dict]) -> dict:
        return {
            "title": title,
            "content": f"# {title}\n\n" + "\n".join(str(d) for d in data),
            "format": "markdown",
        }
```

### Running the Server

```python
from agentic_os.sdk.mcp.server import run_server

async def main():
    server = MyServer(
        name="my-server",
        version="1.0.0",
        description="My custom MCP server",
    )
    await run_server(server)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

## Tool SDK

### Defining Tools

```python
from agentic_os.sdk.mcp.tool import tool, ToolInput

@tool(
    name="read_file",
    description="Read contents of a file",
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path"},
        },
        "required": ["path"],
    },
)
async def read_file(input_data: ToolInput) -> dict:
    path = input_data.path
    with open(path) as f:
        content = f.read()
    return {"content": content, "size": len(content)}
```

### Tool Result Format

```python
from agentic_os.sdk.mcp.tool import ToolResult

result = ToolResult(
    content=[
        {"type": "text", "text": "Hello, world!"},
    ],
    is_error=False,
)
```

## Resource SDK

### Defining Resources

```python
from agentic_os.sdk.mcp.resource import resource, ResourceContent

@resource(
    uri="file://{path}",
    name="File Resource",
    description="Access files in the workspace",
    mime_type="text/plain",
    template=True,  # Supports URI templating
)
async def get_file(path: str) -> ResourceContent:
    with open(path) as f:
        content = f.read()
    return ResourceContent(
        uri=f"file://{path}",
        mime_type="text/plain",
        content=content,
    )
```

### Resource Subscription

```python
@resource(uri="config://settings", subscribe=True)
async def get_settings() -> dict:
    return {"theme": "dark"}
```

## Prompt SDK

### Defining Prompts

```python
from agentic_os.sdk.mcp.prompt import prompt, PromptArgument

@prompt(
    name="code_review",
    description="Generate a code review summary",
    arguments=[
        PromptArgument(name="language", description="Programming language", required=True),
        PromptArgument(name="code", description="Code to review", required=True),
        PromptArgument(name="style", description="Review style", required=False),
    ],
)
async def code_review(
    language: str,
    code: str,
    style: str = "constructive",
) -> dict:
    return {
        "messages": [
            {
                "role": "user",
                "content": f"Please review this {language} code:\n\n```{language}\n{code}\n```",
            }
        ],
        "meta": {"style": style},
    }
```

## Authentication Helpers

```python
from agentic_os.sdk.mcp.auth import require_auth, AuthContext

@tool(name="secure_operation")
@require_auth(scopes=["read", "write"])
async def secure_operation(self, ctx: AuthContext) -> dict:
    return {
        "user": ctx.user_id,
        "scopes": ctx.scopes,
        "result": "Operation completed",
    }
```

## Validation Helpers

```python
from agentic_os.sdk.mcp.validation import validate_input, ValidationError

@tool(name="process_data")
@validate_input({
    "name": {"type": "string", "min_length": 1, "max_length": 100},
    "age": {"type": "integer", "minimum": 0, "maximum": 150},
    "email": {"type": "string", "format": "email"},
})
async def process_data(self, data: dict) -> dict:
    return {"validated": True, "data": data}
```

## Testing Helpers

```python
from agentic_os.sdk.mcp.testing import MCPServerTest, MockTransport

class TestMyServer(MCPServerTest):
    server_class = MyServer

    async def test_greet(self):
        result = await self.invoke_tool("greet", {"name": "World"})
        assert result.content[0].text == "Hello, World!"

    async def test_calculate(self):
        result = await self.invoke_tool("calculate", {"a": 2, "b": 3, "operation": "add"})
        assert result.content[0].text == "5.0"
```

## Registration Helpers

```python
from agentic_os.sdk.mcp.registration import register_server, ServerConfig

# Register with the platform
config = ServerConfig(
    name="my-server",
    transport="stdio",
    command="python",
    args=["-m", "my_server"],
    enabled=True,
    sandbox=True,
)

await register_server(config)
```

## Configuration

### Server Configuration

```python
from agentic_os.sdk.mcp.config import ServerConfig, TransportConfig

config = ServerConfig(
    name="production-server",
    version="1.0.0",
    transport=TransportConfig(
        type="stdio",
        command="node",
        args=["server.js"],
        env={"NODE_ENV": "production"},
    ),
    health_check=HealthCheckConfig(
        enabled=True,
        interval_seconds=30,
        timeout_seconds=10,
    ),
    sandbox=SandboxConfig(
        enabled=True,
        allowed_paths=["/data"],
        max_memory_mb=512,
    ),
)
```

## Best Practices

1. **Always define input schemas** for tools to enable validation
2. **Use type hints** for better IDE support
3. **Handle errors gracefully** with proper error messages
4. **Log operations** for debugging and monitoring
5. **Subscribe to resources** that change frequently
6. **Version your server** for compatibility tracking
7. **Test thoroughly** using the testing helpers

## Example Servers

See `src/agentic_os/adapters/mcp/` for example implementations:

- `filesystem.py` - File operations
- `git.py` - Git operations
- `github.py` - GitHub API
- `postgres.py` - PostgreSQL queries
- `docker.py` - Docker management

## SDK Reference

For complete API documentation, see the generated API docs or source code in `src/agentic_os/sdk/mcp/`.
