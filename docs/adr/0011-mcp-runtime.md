# ADR 0011: MCP Runtime Architecture

**Status:** Accepted (2026-07-19)

## Context

The Model Context Protocol (MCP) enables AI agents to interact with external tools,
resources, and prompt templates through a standardized protocol. AgenticOS needs a
first-class MCP Runtime to support server lifecycle management, tool discovery,
resource access, and real-time streaming — all within the existing hexagonal
architecture.

## Decision

Build the MCP Runtime as four layers within the hexagonal architecture:

1. **Domain** (`domain/mcp.py`) — Pure domain models with zero external dependencies.
2. **Ports** (`ports/mcp.py`) — Two runtime-checkable Protocols: MCPRegistryPort and
   MCPTransportPort, defining the contract between core and infrastructure.
3. **Core** (`core/mcp/`) — Registry, Client, Manager, and Security implementations
   that implement the port contracts.
4. **Adapters** (`adapters/mcp/`) — Five built-in adapters (Filesystem, Git, HTTP,
   SQLite, Terminal) that demo the adapter contract and serve as references.

## Key Design Decisions

- **Immutable domain models** — All domain dataclasses are frozen. State transitions
  use `with_*` builder methods returning new instances. This enables safe caching and
  snapshot semantics in the registry.
- **Registry as event source** — Every lifecycle transition emits an EventBus event.
  The WebSocket broadcaster (`MCPBroadcaster`) subscribes to MCP topics and fans
  them to Mission Control clients.
- **Lazy transport binding** — MCPClient doesn't connect until `client.connect()` is
  called. Transport choice (stdio/SSE/HTTP) is resolved at connect time.
- **Per-server async locks** — Registry uses per-server `asyncio.Lock` for thread-safe
  lifecycle transitions (start/stop/restart).
- **Security as a gate** — MCPSecurity wraps every MCP operation with an authorization
  check through the SecurityFramework. No operation bypasses security.

## Consequences

- (+) Clear separation of concerns between protocol (core), infrastructure (adapters),
  and developer experience (SDK).
- (+) All 22 MCP modules import cleanly with zero circular dependencies.
- (+) Domain models are reusable outside the runtime (e.g., in the SDK).
- (-) Immutable models create allocation overhead for every state transition (measured
  at <10 µs per transition — acceptable).
- (-) In-memory registry doesn't persist state across restarts (Phase 5+ concern).

## References

- [ADR 0012: MCP Session Lifecycle](0012-mcp-session-lifecycle.md)
- [ADR 0013: MCP Tool Registry](0013-mcp-tool-registry.md)
- [ADR 0014: MCP Connection Pool](0014-mcp-connection-pool.md)
- [ADR 0015: MCP SDK Architecture](0015-mcp-sdk-architecture.md)
