# ADR 0012: MCP Session Lifecycle

**Status:** Accepted (2026-07-19)

## Context

MCP servers maintain sessions with connected clients. Session lifecycle management
— creation, expiration, destruction — must be tracked in the runtime to enable
resource cleanup, health monitoring, and real-time status updates.

## Decision

Model session state as a first-class domain entity (`MCPSession`) with four states:
ACTIVE, IDLE, EXPIRED, CLOSED. Session lifecycle is managed by the MCPManager,
which tracks active session IDs per server.

### Session State Machine

```
CREATED → ACTIVE → IDLE → EXPIRED → CLOSED
                ↘_________↗
```

- **ACTIVE**: Server is connected and processing requests.
- **IDLE**: Server is connected but has not received requests for the idle timeout.
- **EXPIRED**: Server has been idle beyond the TTL; session is eligible for cleanup.
- **CLOSED**: Session has been explicitly closed by `disconnect()` or server shutdown.

### Events

- `MCP_SESSION_CREATED` — emitted when a transport connection is established.
- `MCP_SESSION_DESTROYED` — emitted when a session is explicitly closed.
- `MCP_SESSION_EXPIRED` — emitted when a session TTL elapses.

## Consequences

- (+) Clear lifecycle tracking enables proper resource cleanup.
- (+) Event emission allows Mission Control to display real-time session status.
- (-) Session expiry requires a background task in the Manager (implemented via
  `start_health_monitoring`).
