# ADR 0015: MCP SDK Architecture

**Status:** Accepted (2026-07-19)

## Context

Developers building applications on AgenticOS need a high-level SDK for working with
MCP servers — registering, configuring, starting, stopping, invoking tools, and
managing resources and prompts. The SDK should provide a fluent, ergonomic API while
remaining compatible with the core port interfaces.

## Decision

Build the SDK as a thin facade layer on top of the port interfaces. The SDK does
not reimplement core logic; it delegates to `MCPRegistryPort` implementations.

### Architecture

```
┌─────────────────────────────────────────────┐
│                  SDK Layer                    │
│  McpServerSdk  ToolSdk  ResourceSdk  PromptSdk│
│  McpAuthHelper  McpConfigHelper  Registration │
│  McpValidator  McpTestHelper                  │
├─────────────────────────────────────────────┤
│              Port Interfaces                  │
│        MCPRegistryPort, MCPTransportPort       │
├─────────────────────────────────────────────┤
│              Core Implementations             │
│        MCPRegistryImpl, MCPClient, etc.        │
└─────────────────────────────────────────────┘
```

### Design Principles

1. **No core reimplementation** — SDK methods map 1:1 to port methods with
   convenience wrappers (e.g., `McpServerSdk.start()` calls `registry.start_server()`).
2. **Fluent builders** — `ToolBuilder`, `ResourceSdk`, `PromptSdk` provide
   builder-pattern interfaces for constructing domain objects.
3. **Developer-friendly errors** — SDK wraps `KeyError`/`ValueError` with descriptive
   messages about what the developer should do (e.g., "call bind_registry() first").
4. **Testability** — `McpTestHelper`, `FakeMCPRegistry`, `FakeMCPManager` provide
   in-memory fakes for testing without real MCP servers.

### Module Structure

| Module | Purpose |
|--------|---------|
| `server.py` | McpServerSdk — high-level server lifecycle |
| `tool.py` | ToolBuilder, ToolSdk — tool construction and invocation |
| `resource.py` | ResourceSdk — resource reading and subscription |
| `prompt.py` | PromptSdk — prompt listing and retrieval |
| `auth.py` | McpAuthHelper — MCP authorization helpers |
| `config.py` | McpConfigHelper — server configuration building |
| `registration.py` | RegistrationHelper — server registration/unregistration |
| `validation.py` | McpValidator — MCP protocol validation |
| `testing.py` | McpTestHelper, FakeMCPRegistry, FakeMCPManager — fakes |

## Consequences

- (+) SDK is testable without real MCP servers (fakes provided).
- (+) SDK stays thin — no duplication of core business logic.
- (-) SDK depends on port interfaces, which may change across releases.
  Version pinning of SDK to core is recommended.
