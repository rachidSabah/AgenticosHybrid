# MCP Runtime Guide

## Overview

The MCP (Model Context Protocol) Runtime is a first-class platform service responsible for discovering, managing, securing, monitoring, and orchestrating every Model Context Protocol server.

## Architecture

The MCP Runtime follows hexagonal architecture principles with clear separation of concerns:

```
┌─────────────────────────────────────────────────────────────┐
│                    Platform Kernel                           │
├─────────────────────────────────────────────────────────────┤
│                     MCP Runtime                              │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐          │
│  │   Manager   │ │   Registry  │ │   Client    │          │
│  └─────────────┘ └─────────────┘ └─────────────┘          │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐          │
│  │   Session   │ │    Pool     │ │  Telemetry  │          │
│  └─────────────┘ └─────────────┘ └─────────────┘          │
│  ┌─────────────┐ ┌─────────────┐                          │
│  │   Health    │ │  Discovery  │                          │
│  └─────────────┘ └─────────────┘                          │
├─────────────────────────────────────────────────────────────┤
│                       Ports                                 │
│  MCPRegistryPort | MCPRuntimePort | MCPSessionPort         │
├─────────────────────────────────────────────────────────────┤
│                      Adapters                                │
│  Filesystem | Git | GitHub | PostgreSQL | Docker           │
└─────────────────────────────────────────────────────────────┘
```

## Core Components

### MCP Manager

The `MCPManager` orchestrates server lifecycle, health monitoring, tool/resource/prompt discovery, session tracking, and error recovery.

```python
from agentic_os.core.mcp.manager import MCPManager
from agentic_os.core.mcp.registry import MCPRegistryImpl

manager = MCPManager(registry=registry, bus=event_bus)
await manager.initialize()
await manager.start()
```

### MCP Registry

The `MCPRegistryImpl` provides server lifecycle management, tool registry, and resource/prompt delegation.

```python
from agentic_os.core.mcp.registry import MCPRegistryImpl

registry = MCPRegistryImpl(bus=event_bus)

# Register a server
server = await registry.register_server(MCPServerCreate(
    name="filesystem",
    transport="stdio",
    command="npx",
    args=["-y", "@modelcontextprotocol/server-filesystem", "/data"],
))

# Start the server
detail = await registry.start_server(server.config.id)
```

### MCP Session Manager

The `MCPSessionManager` handles session lifecycle including creation, tracking, expiration, and cleanup.

```python
from agentic_os.core.mcp.session import MCPSessionManager

session_mgr = MCPSessionManager(bus=event_bus)

# Create a session
session = await session_mgr.create_session(
    server_id="server-id",
    transport=MCPTransport.STDIO,
    capabilities={"tools": True, "resources": True},
)

# List active sessions
sessions = await session_mgr.list_sessions(status=MCPSessionStatus.ACTIVE)
```

### MCP Connection Pool

The `MCPConnectionPool` provides connection pooling and reuse for improved efficiency.

```python
from agentic_os.core.mcp.pool import MCPConnectionPool, MCPPoolConfig

config = MCPPoolConfig(
    min_connections=1,
    max_connections=10,
    max_idle_time_seconds=300,
)
pool = MCPConnectionPool(bus=event_bus, config=config)

# Acquire a connection
connection = await pool.get_connection(server_config)
# ... use connection ...
await pool.release_connection(connection)
```

### MCP Telemetry

The `MCPTelemetry` collector gathers metrics for request/response tracking, latency measurement, and error rates.

```python
from agentic_os.core.mcp.telemetry import MCPTelemetry

telemetry = MCPTelemetry(bus=event_bus)

# Track a request
request_id = telemetry.start_request(
    server_id="server-id",
    server_name="Test Server",
    method="tools/list",
)
# ... perform operation ...
telemetry.complete_request(request_id, success=True)

# Get telemetry summary
summary = telemetry.get_summary()
```

### MCP Health Monitor

The `MCPHealthMonitor` performs periodic health checks with automatic failure detection.

```python
from agentic_os.core.mcp.health import MCPHealthMonitor

monitor = MCPHealthMonitor(bus=event_bus)

# Register a server
monitor.register_server(
    server_id="server-id",
    server_name="Test Server",
    health_check_callback=health_check_function,
)

# Check health
result = await monitor.check_server("server-id")
```

### MCP Discovery

The `MCPServerDiscovery` framework automatically discovers MCP servers from the filesystem.

```python
from agentic_os.core.mcp.discovery import MCPServerDiscovery, DiscoveryConfig

config = DiscoveryConfig(
    scan_paths=["~/.local/bin", "/usr/local/bin"],
    auto_register=True,
)
discovery = MCPServerDiscovery(bus=event_bus, config=config)

# Discover servers
result = await discovery.discover_all()
```

## Supported Transports

The MCP Runtime supports multiple transport types:

| Transport | Description |
|-----------|-------------|
| STDIO | Subprocess-based communication via stdin/stdout |
| SSE | Server-Sent Events over HTTP |
| Streamable HTTP | HTTP POST with streaming responses |

## Supported MCP Servers

The runtime supports generic MCP servers including:

- **Filesystem**: File operations with path sandboxing
- **Git**: Version control operations
- **GitHub**: Repository and issue management
- **SQLite**: Database queries
- **PostgreSQL**: Database operations
- **Docker**: Container management
- **Terminal**: Shell command execution

## REST API

The MCP Runtime exposes a comprehensive REST API:

### Server Lifecycle

```
POST   /api/mcp/servers           - Register a new server
GET    /api/mcp/servers            - List all servers
GET    /api/mcp/servers/{id}      - Get server details
PUT    /api/mcp/servers/{id}      - Update server config
DELETE /api/mcp/servers/{id}      - Delete a server
POST   /api/mcp/servers/{id}/start  - Start server
POST   /api/mcp/servers/{id}/stop   - Stop server
POST   /api/mcp/servers/{id}/restart - Restart server
```

### Tools

```
GET    /api/mcp/servers/{id}/tools              - List tools
POST   /api/mcp/servers/{id}/tools/discover     - Discover tools
POST   /api/mcp/servers/{id}/tools/invoke      - Invoke tool
```

### Resources

```
GET    /api/mcp/servers/{id}/resources          - List resources
GET    /api/mcp/servers/{id}/resources/{uri}    - Read resource
POST   /api/mcp/servers/{id}/resources/{uri}/subscribe
```

### Sessions

```
GET    /api/mcp/sessions              - List sessions
GET    /api/mcp/sessions/{id}        - Get session
DELETE /api/mcp/sessions/{id}        - Close session
POST   /api/mcp/sessions/cleanup     - Cleanup expired
```

### Health & Telemetry

```
GET    /api/mcp/health               - Health summary
GET    /api/mcp/health/{id}         - Server health
POST   /api/mcp/health/{id}/check   - Check health
GET    /api/mcp/telemetry/summary   - Telemetry summary
GET    /api/mcp/telemetry/latency   - Latency distribution
```

## Mission Control

The Mission Control dashboard provides a comprehensive UI for MCP management:

- **Servers Tab**: Server registration, lifecycle management
- **Tools Tab**: Tool discovery and invocation
- **Resources Tab**: Resource browsing
- **Prompts Tab**: Prompt template management
- **Sessions Tab**: Session tracking
- **Health Tab**: Health monitoring
- **Telemetry Tab**: Metrics and performance
- **Permissions Tab**: Tool-to-capability mapping

## Security

The MCP Runtime integrates with the Security Framework:

- RBAC for tool invocation
- Workspace isolation
- Approval gates
- Secret management
- Permission mapping
- Audit logging
- Sandbox enforcement

## Events

The MCP Runtime publishes events to the EventBus:

```
mcp.server.*         - Server lifecycle events
mcp.session.*       - Session lifecycle events
mcp.tool.*           - Tool discovery and invocation
mcp.resource.*       - Resource operations
mcp.prompt.*         - Prompt operations
mcp.health.*         - Health status changes
mcp.telemetry.*      - Telemetry data
mcp.permission.*      - Permission changes
```

## Version History

- **v0.7.0** - MCP Runtime Foundation with Session Manager, Connection Pool, Telemetry, Health Monitor, Discovery
- **v0.5.0** - Initial MCP Runtime with basic server management
