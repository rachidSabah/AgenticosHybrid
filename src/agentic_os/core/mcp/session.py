"""
MCP Session Manager

Handles MCP session lifecycle including creation, tracking, expiration,
and cleanup. Manages session state, capabilities, and metadata.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from agentic_os.domain.events import EventEnvelope, Topic
from agentic_os.domain.mcp import (
    MCPSession,
    MCPSessionStatus,
    MCPTransport,
)
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.event_bus import EventBus

log = get_logger("mcp.session")


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class MCPSessionManager:
    """
    MCP Session Manager for lifecycle management.

    Features:
    - Session creation with capability negotiation
    - Session tracking and state management
    - Session expiration with configurable TTL
    - Session cleanup and resource release
    - Session event emission
    """

    bus: EventBus
    _sessions: dict[str, MCPSession] = field(default_factory=dict)
    _server_sessions: dict[str, list[str]] = field(default_factory=dict)  # server_id -> session_ids
    _session_ttl_seconds: int = 3600  # 1 hour default
    _cleanup_interval_seconds: int = 300  # 5 minutes default

    # ── Session Creation ─────────────────────────────────────────────────

    async def create_session(
        self,
        server_id: str,
        transport: MCPTransport,
        capabilities: dict[str, Any] | None = None,
        ttl_seconds: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> MCPSession:
        """Create a new MCP session."""
        session_id = uuid4().hex

        expires_at = None
        if ttl_seconds is None:
            ttl_seconds = self._session_ttl_seconds
        if ttl_seconds > 0:
            expires_at = _utcnow() + timedelta(seconds=ttl_seconds)

        session = MCPSession(
            id=session_id,
            server_id=server_id,
            transport=transport,
            status=MCPSessionStatus.ACTIVE,
            capabilities=capabilities or {},
            expires_at=expires_at,
            metadata=metadata or {},
        )

        self._sessions[session_id] = session

        if server_id not in self._server_sessions:
            self._server_sessions[server_id] = []
        self._server_sessions[server_id].append(session_id)

        await self._emit(
            Topic.MCP_SESSION_CREATED,
            {
                "session_id": session_id,
                "server_id": server_id,
                "transport": transport.value,
                "capabilities": capabilities or {},
                "expires_at": expires_at.isoformat() if expires_at else None,
            },
        )

        log.info(f"Created MCP session: {session_id} for server {server_id}")
        return session

    async def get_session(self, session_id: str) -> MCPSession | None:
        """Get a session by ID."""
        session = self._sessions.get(session_id)
        if session and session.expires_at and session.expires_at < _utcnow():
            await self._expire_session(session_id)
            return None
        return session

    async def get_session_for_server(self, server_id: str) -> MCPSession | None:
        """Get the active session for a server (most recently created)."""
        session_ids = self._server_sessions.get(server_id, [])
        if not session_ids:
            return None

        active_session = None
        for session_id in reversed(session_ids):
            session = self._sessions.get(session_id)
            if session and session.status == MCPSessionStatus.ACTIVE:
                if session.expires_at and session.expires_at < _utcnow():
                    await self._expire_session(session_id)
                    continue
                active_session = session
                break

        return active_session

    async def list_sessions(
        self,
        server_id: str | None = None,
        status: MCPSessionStatus | None = None,
    ) -> list[MCPSession]:
        """List sessions with optional filtering."""
        sessions = list(self._sessions.values())

        if server_id is not None:
            sessions = [s for s in sessions if s.server_id == server_id]

        if status is not None:
            sessions = [s for s in sessions if s.status == status]

        return sessions

    async def list_server_sessions(self, server_id: str) -> list[MCPSession]:
        """List all sessions for a specific server."""
        session_ids = self._server_sessions.get(server_id, [])
        sessions = []
        for session_id in session_ids:
            session = self._sessions.get(session_id)
            if session:
                if session.expires_at and session.expires_at < _utcnow():
                    await self._expire_session(session_id)
                    continue
                sessions.append(session)
        return sessions

    # ── Session State Management ─────────────────────────────────────────

    async def update_session_status(
        self, session_id: str, status: MCPSessionStatus
    ) -> MCPSession | None:
        """Update the status of a session."""
        session = self._sessions.get(session_id)
        if not session:
            log.warning(f"Session not found: {session_id}")
            return None

        old_status = session.status
        updated_session = session.with_status(status)
        self._sessions[session_id] = updated_session

        topic = (
            Topic.MCP_SESSION_DESTROYED
            if status == MCPSessionStatus.CLOSED
            else Topic.MCP_SESSION_CREATED
        )
        await self._emit(
            topic,
            {
                "session_id": session_id,
                "server_id": session.server_id,
                "old_status": old_status.value,
                "new_status": status.value,
            },
        )

        log.info(f"Updated session {session_id} status: {old_status.value} -> {status.value}")
        return updated_session

    async def update_session_capabilities(
        self, session_id: str, capabilities: dict[str, Any]
    ) -> MCPSession | None:
        """Update session capabilities."""
        session = self._sessions.get(session_id)
        if not session:
            log.warning(f"Session not found: {session_id}")
            return None

        updated_session = session.with_capabilities(capabilities)
        self._sessions[session_id] = updated_session

        await self._emit(
            Topic.MCP_CAPABILITY_NEGOTIATED,
            {
                "session_id": session_id,
                "server_id": session.server_id,
                "capabilities": capabilities,
            },
        )

        return updated_session

    async def extend_session(self, session_id: str, additional_seconds: int) -> MCPSession | None:
        """Extend a session's TTL."""
        session = self._sessions.get(session_id)
        if not session:
            return None

        if session.expires_at:
            new_expires_at = session.expires_at + timedelta(seconds=additional_seconds)
        else:
            new_expires_at = _utcnow() + timedelta(seconds=additional_seconds)

        updated_session = MCPSession(
            id=session.id,
            server_id=session.server_id,
            transport=session.transport,
            status=session.status,
            capabilities=session.capabilities,
            created_at=session.created_at,
            updated_at=_utcnow(),
            expires_at=new_expires_at,
            metadata=session.metadata,
        )
        self._sessions[session_id] = updated_session

        log.info(f"Extended session {session_id} by {additional_seconds}s")
        return updated_session

    # ── Session Expiration ───────────────────────────────────────────────

    async def expire_session(self, session_id: str) -> bool:
        """Manually expire a session."""
        return await self._expire_session(session_id)

    async def _expire_session(self, session_id: str) -> bool:
        """Internal method to expire a session."""
        session = self._sessions.get(session_id)
        if not session:
            return False

        if session.status == MCPSessionStatus.EXPIRED:
            return False

        updated_session = session.with_status(MCPSessionStatus.EXPIRED)
        self._sessions[session_id] = updated_session

        await self._emit(
            Topic.MCP_SESSION_EXPIRED,
            {
                "session_id": session_id,
                "server_id": session.server_id,
                "expired_at": _utcnow().isoformat(),
            },
        )

        log.info(f"Expired session: {session_id}")
        return True

    async def expire_sessions(self) -> int:
        """Expire all sessions past their expiry time. Returns count of expired sessions."""
        expired_count = 0
        now = _utcnow()

        for session_id, session in list(self._sessions.items()):
            if (
                session.status == MCPSessionStatus.ACTIVE
                and session.expires_at
                and session.expires_at < now
            ):
                if await self._expire_session(session_id):
                    expired_count += 1

        if expired_count > 0:
            log.info(f"Expired {expired_count} sessions")

        return expired_count

    async def expire_server_sessions(self, server_id: str) -> int:
        """Expire all sessions for a specific server."""
        expired_count = 0
        session_ids = self._server_sessions.get(server_id, [])

        for session_id in list(session_ids):
            if await self._expire_session(session_id):
                expired_count += 1

        return expired_count

    # ── Session Cleanup ─────────────────────────────────────────────────

    async def close_session(self, session_id: str) -> bool:
        """Close a session gracefully."""
        session = self._sessions.get(session_id)
        if not session:
            log.warning(f"Session not found: {session_id}")
            return False

        updated_session = session.with_status(MCPSessionStatus.CLOSED)
        self._sessions[session_id] = updated_session

        await self._emit(
            Topic.MCP_SESSION_DESTROYED,
            {
                "session_id": session_id,
                "server_id": session.server_id,
                "reason": "closed",
            },
        )

        log.info(f"Closed session: {session_id}")
        return True

    async def close_server_sessions(self, server_id: str) -> int:
        """Close all sessions for a specific server."""
        closed_count = 0
        session_ids = self._server_sessions.get(server_id, [])

        for session_id in list(session_ids):
            if await self.close_session(session_id):
                closed_count += 1

        return closed_count

    async def cleanup_closed_sessions(self) -> int:
        """Remove closed sessions from tracking (for cleanup)."""
        to_remove = [
            sid for sid, s in self._sessions.items() if s.status == MCPSessionStatus.CLOSED
        ]
        for session_id in to_remove:
            session = self._sessions.pop(session_id, None)
            if session:
                self._server_sessions.get(session.server_id, []).remove(session_id)

        if to_remove:
            log.info(f"Cleaned up {len(to_remove)} closed sessions")

        return len(to_remove)

    # ── Session Statistics ───────────────────────────────────────────────

    def get_session_count(self, server_id: str | None = None) -> int:
        """Get the count of sessions."""
        if server_id:
            return len(self._server_sessions.get(server_id, []))
        return len(self._sessions)

    def get_active_session_count(self, server_id: str | None = None) -> int:
        """Get the count of active (non-closed, non-expired) sessions."""
        if server_id:
            session_ids = self._server_sessions.get(server_id, [])
            return sum(
                1
                for sid in session_ids
                if sid in self._sessions and self._sessions[sid].status == MCPSessionStatus.ACTIVE
            )
        return sum(1 for s in self._sessions.values() if s.status == MCPSessionStatus.ACTIVE)

    def get_session_stats(self) -> dict[str, Any]:
        """Get session statistics."""
        sessions = list(self._sessions.values())
        now = _utcnow()

        active = sum(1 for s in sessions if s.status == MCPSessionStatus.ACTIVE)
        idle = sum(1 for s in sessions if s.status == MCPSessionStatus.IDLE)
        expired = sum(1 for s in sessions if s.status == MCPSessionStatus.EXPIRED)
        closed = sum(1 for s in sessions if s.status == MCPSessionStatus.CLOSED)

        expiring_soon = sum(
            1
            for s in sessions
            if s.status == MCPSessionStatus.ACTIVE
            and s.expires_at
            and 0 < (s.expires_at - now).total_seconds() < 300  # 5 minutes
        )

        return {
            "total": len(sessions),
            "active": active,
            "idle": idle,
            "expired": expired,
            "closed": closed,
            "expiring_soon": expiring_soon,
            "tracked_servers": len(self._server_sessions),
        }

    # ── Internal Helpers ────────────────────────────────────────────────

    async def _emit(self, topic: Topic, payload: dict[str, Any]) -> None:
        """Emit an event to the event bus."""
        await self.bus.publish(
            EventEnvelope(
                type="event",
                source="mcp-session-manager",
                topic=topic.value,
                payload=payload,
            )
        )


__all__ = ["MCPSessionManager"]
