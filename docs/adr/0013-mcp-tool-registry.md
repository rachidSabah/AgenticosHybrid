# ADR 0013: MCP Tool Registry

**Status:** Accepted (2026-07-19)

## Context

MCP servers expose tools that AI agents can invoke. The runtime must discover,
cache, and resolve tools across multiple connected servers. Tool metadata must be
available without an active connection.

## Decision

Implement tool registry as a tuple of `MCPTool` instances on `MCPServerDetail`.
Tools are discovered when a server starts (via `client.list_tools()`) and cached
in the server detail until the next start/reload cycle.

### Tool Lifecycle

```
Server Start → client.connect() → client.list_tools() → cache on MCPServerDetail
Server Reload → client.list_tools() → update cache
Server Stop → cache retained (stale) until next start
```

### Tool Access Patterns

- `get_tools(server_id)` — returns cached tools (no connection needed).
- `discover_tools(server_id)` — forces re-discovery by reconnecting to the server.
- `invoke_tool(data)` — routes the invocation to the connected client for the server.

### Permission Model

Each tool can be mapped to a capability string via `MCPPermissionMapping`. The
`set_permissions`/`get_permissions` methods on the registry allow the SecurityFramework
to gate tool invocation by checking the caller's principal against the required
capability.

## Consequences

- (+) Tools are available for listing even when the server is stopped.
- (+) Permission mappings enable fine-grained access control per tool.
- (-) Cached tools may become stale if the server updates its tool list without
  restarting (mitigated by explicit `discover_tools` endpoint).
