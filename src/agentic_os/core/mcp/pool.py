"""
MCP Connection Pool

Provides connection pooling and reuse for MCP servers to improve efficiency
and reduce overhead from creating new connections.
"""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from agentic_os.core.mcp.client import MCPClient
from agentic_os.domain.events import EventEnvelope, Topic
from agentic_os.domain.mcp import (
    MCPServerConfig,
)
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.event_bus import EventBus

log = get_logger("mcp.pool")


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class MCPConnection:
    """Represents a pooled MCP connection."""

    id: str
    server_id: str
    client: MCPClient
    created_at: datetime
    last_used_at: datetime
    in_use: bool = False
    request_count: int = 0
    error_count: int = 0


@dataclass
class MCPPoolConfig:
    """Configuration for the connection pool."""

    min_connections: int = 1
    max_connections: int = 10
    max_idle_time_seconds: int = 300  # 5 minutes
    max_lifetime_seconds: int = 3600  # 1 hour
    acquire_timeout_seconds: int = 30
    health_check_interval_seconds: int = 60


@dataclass
class MCPPoolStats:
    """Statistics for the connection pool."""

    total_connections: int
    active_connections: int
    idle_connections: int
    in_use_connections: int
    total_requests: int
    total_errors: int
    avg_wait_time_ms: float
    server_stats: dict[str, dict[str, Any]]


class MCPConnectionPool:
    """
    MCP Connection Pool for efficient connection management.

    Features:
    - Connection creation and caching
    - Connection reuse to reduce overhead
    - Connection health checking
    - Automatic connection cleanup
    - Graceful degradation under load
    - Statistics collection
    """

    def __init__(
        self,
        bus: EventBus,
        config: MCPPoolConfig | None = None,
    ) -> None:
        self._bus = bus
        self._config = config or MCPPoolConfig()
        self._pools: dict[str, list[MCPConnection]] = {}  # server_id -> connections
        self._locks: dict[str, asyncio.Lock] = {}
        self._total_requests: int = 0
        self._total_errors: int = 0
        self._wait_times: list[float] = []
        self._acquire_times: dict[str, datetime] = {}  # connection_id -> start time

    def _get_lock(self, server_id: str) -> asyncio.Lock:
        """Get or create a lock for a server pool."""
        if server_id not in self._locks:
            self._locks[server_id] = asyncio.Lock()
        return self._locks[server_id]

    async def _emit(self, topic: Topic, payload: dict[str, Any]) -> None:
        """Emit an event to the event bus."""
        await self._bus.publish(
            EventEnvelope(
                type="event",
                source="mcp-connection-pool",
                topic=topic.value,
                payload=payload,
            )
        )

    # ── Connection Management ───────────────────────────────────────────

    async def get_connection(self, server_config: MCPServerConfig) -> MCPConnection:
        """
        Get a connection from the pool, creating one if necessary.

        Returns a connection that must be released using release_connection().
        """
        start_time = asyncio.get_running_loop().time()
        server_id = server_config.id

        async with self._get_lock(server_id):
            pool = self._pools.get(server_id, [])

            # Try to find an idle, healthy connection
            idle_conn = None
            for conn in pool:
                if not conn.in_use and self._is_connection_healthy(conn):
                    if self._is_connection_expired(conn):
                        await self._close_connection(conn)
                        continue
                    idle_conn = conn
                    break

            # Create new connection if needed
            if idle_conn is None:
                if len(pool) < self._config.max_connections:
                    idle_conn = await self._create_connection(server_config)
                    pool.append(idle_conn)
                    self._pools[server_id] = pool
                else:
                    # Wait for a connection to become available
                    idle_conn = await self._wait_for_connection(server_config, start_time)

            if idle_conn:
                idle_conn.in_use = True
                self._acquire_times[idle_conn.id] = datetime.now(UTC)

        wait_time_ms = (asyncio.get_running_loop().time() - start_time) * 1000
        self._wait_times.append(wait_time_ms)
        if len(self._wait_times) > 1000:
            self._wait_times = self._wait_times[-1000:]

        self._total_requests += 1

        await self._emit(
            Topic.MCP_CONNECTION_ACQUIRED,
            {
                "server_id": server_id,
                "connection_id": idle_conn.id,
                "wait_time_ms": round(wait_time_ms, 2),
            },
        )

        return idle_conn

    async def release_connection(self, connection: MCPConnection) -> None:
        """Release a connection back to the pool."""
        connection.in_use = False
        connection.last_used_at = _utcnow()

        if connection in self._acquire_times:
            acquire_time = self._acquire_times.pop(connection.id)
            held_time_ms = (datetime.now(UTC) - acquire_time).total_seconds() * 1000
            log.debug(f"Connection {connection.id} held for {held_time_ms:.2f}ms")

        await self._emit(
            Topic.MCP_CONNECTION_RELEASED,
            {
                "server_id": connection.server_id,
                "connection_id": connection.id,
            },
        )

    async def _create_connection(self, server_config: MCPServerConfig) -> MCPConnection:
        """Create a new connection."""
        client = MCPClient(config=server_config)
        await client.connect()

        connection = MCPConnection(
            id=uuid4().hex,
            server_id=server_config.id,
            client=client,
            created_at=_utcnow(),
            last_used_at=_utcnow(),
            in_use=False,
        )

        log.info(f"Created new connection {connection.id} for server {server_config.id}")
        return connection

    async def _close_connection(self, connection: MCPConnection) -> None:
        """Close and remove a connection."""
        try:
            await connection.client.disconnect()
        except Exception as e:
            log.warning(f"Error disconnecting client: {e}")

        pool = self._pools.get(connection.server_id, [])
        if connection in pool:
            pool.remove(connection)
        self._pools[connection.server_id] = pool

        await self._emit(
            Topic.MCP_CONNECTION_CLOSED,
            {
                "server_id": connection.server_id,
                "connection_id": connection.id,
                "reason": "expired",
            },
        )

        log.info(f"Closed expired connection {connection.id}")

    async def _wait_for_connection(
        self, server_config: MCPServerConfig, start_time: float
    ) -> MCPConnection:
        """Wait for an available connection."""
        timeout = self._config.acquire_timeout_seconds
        poll_interval = 0.1
        elapsed = 0.0

        while elapsed < timeout:
            await asyncio.sleep(poll_interval)
            elapsed = asyncio.get_running_loop().time() - start_time

            pool = self._pools.get(server_config.id, [])
            for conn in pool:
                if not conn.in_use and self._is_connection_healthy(conn):
                    return conn

        raise TimeoutError(f"Timeout waiting for connection to {server_config.name}")

    # ── Connection Health ───────────────────────────────────────────────

    def _is_connection_healthy(self, connection: MCPConnection) -> bool:
        """Check if a connection is healthy."""
        if connection.error_count >= 5:
            return False
        return connection.client.is_connected

    def _is_connection_expired(self, connection: MCPConnection) -> bool:
        """Check if a connection has exceeded its max lifetime."""
        age_seconds = (datetime.now(UTC) - connection.created_at).total_seconds()
        return age_seconds >= self._config.max_lifetime_seconds

    def _is_connection_idle_too_long(self, connection: MCPConnection) -> bool:
        """Check if a connection has been idle too long."""
        idle_seconds = (datetime.now(UTC) - connection.last_used_at).total_seconds()
        return idle_seconds >= self._config.max_idle_time_seconds

    # ── Pool Maintenance ───────────────────────────────────────────────

    async def maintain_pool(self) -> dict[str, int]:
        """Perform maintenance on all pools. Returns counts of cleaned connections."""
        stats = {"closed": 0, "reconnected": 0}

        for server_id, pool in list(self._pools.items()):
            async with self._get_lock(server_id):
                to_close = []
                for conn in pool:
                    if conn.in_use:
                        continue

                    if self._is_connection_expired(conn):
                        to_close.append(conn)
                    elif not conn.client.is_connected:
                        to_close.append(conn)
                    elif self._is_connection_idle_too_long(conn):
                        to_close.append(conn)

                for conn in to_close:
                    await self._close_connection(conn)
                    stats["closed"] += 1

                # Ensure minimum connections are maintained
                idle_count = sum(1 for c in self._pools.get(server_id, []) if not c.in_use)
                if idle_count < self._config.min_connections:
                    # This would require server config, so we just log for now
                    log.debug(
                        f"Pool {server_id} below minimum connections: "
                        f"{idle_count}/{self._config.min_connections}"
                    )

        return stats

    async def close_server_connections(self, server_id: str) -> int:
        """Close all connections for a server."""
        async with self._get_lock(server_id):
            pool = self._pools.get(server_id, [])
            closed_count = 0

            for conn in pool:
                await self._close_connection(conn)
                closed_count += 1

            self._pools[server_id] = []
            log.info(f"Closed {closed_count} connections for server {server_id}")

            return closed_count

    async def close_all(self) -> None:
        """Close all connections in all pools."""
        for server_id in list(self._pools.keys()):
            await self.close_server_connections(server_id)

        log.info("Closed all connection pools")

    # ── Statistics ─────────────────────────────────────────────────────

    def get_stats(self) -> MCPPoolStats:
        """Get pool statistics."""
        total_connections = 0
        active_connections = 0
        idle_connections = 0
        in_use_connections = 0
        server_stats: dict[str, dict[str, Any]] = {}

        for server_id, pool in self._pools.items():
            total_connections += len(pool)
            in_use = sum(1 for c in pool if c.in_use)
            connected = sum(1 for c in pool if c.client.is_connected)

            total_connections_for_server = len(pool)
            in_use_connections += in_use
            idle_connections += len(pool) - in_use
            active_connections += connected

            server_stats[server_id] = {
                "total": total_connections_for_server,
                "in_use": in_use,
                "idle": len(pool) - in_use,
                "healthy": connected,
                "total_requests": sum(c.request_count for c in pool),
                "total_errors": sum(c.error_count for c in pool),
            }

        avg_wait = sum(self._wait_times) / len(self._wait_times) if self._wait_times else 0.0

        return MCPPoolStats(
            total_connections=total_connections,
            active_connections=active_connections,
            idle_connections=idle_connections,
            in_use_connections=in_use_connections,
            total_requests=self._total_requests,
            total_errors=self._total_errors,
            avg_wait_time_ms=avg_wait,
            server_stats=server_stats,
        )

    def record_success(self, connection: MCPConnection) -> None:
        """Record a successful request on a connection."""
        connection.request_count += 1

    def record_error(self, connection: MCPConnection) -> None:
        """Record an error on a connection."""
        connection.request_count += 1
        connection.error_count += 1
        self._total_errors += 1


__all__ = ["MCPConnectionPool", "MCPPoolConfig", "MCPPoolStats", "MCPConnection"]
