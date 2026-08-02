# ADR 0014: MCP Connection Pool

**Status:** Accepted (2026-07-19)

## Context

MCP servers that use persistent transports (SSE, Streamable HTTP) maintain long-lived
connections. The runtime must track these connections, provide access for tool
invocation, and clean them up on shutdown.

## Decision

Connections are tracked in a `_clients: dict[str, MCPClient]` on the registry
instance. Each server gets at most one active client instance, created during
`start_server()` and destroyed during `stop_server()`.

### Key Properties

- **One client per server** — Simpler than a connection pool with load balancing.
  MCP servers are single-process; there's no benefit to multiple connections.
- **Client lifecycle tied to server status** — Client exists only when server is
  RUNNING. Starting creates a client; stopping disconnects and removes it.
- **Per-server lock** — Each server has an `asyncio.Lock` preventing concurrent
  lifecycle operations (double-start, stop-while-starting).

### Reconnection

MCPClient implements exponential backoff auto-reconnect for SSE and Streamable HTTP
transports (`_auto_reconnect` method). Stdio transport is ephemeral and does not
reconnect.

## Consequences

- (+) Simple, predictable connection model with one client per server.
- (+) Auto-reconnect for persistent transports improves resilience.
- (-) No load balancing for tools across server instances.
