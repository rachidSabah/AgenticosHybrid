"""Session Manager — persistent runtime session tracking.

Manages RuntimeSession lifecycle including creation, lookup, and history
trimming. All operations are thread-safe via asyncio.Lock.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime

from agentic_os.core.runtime.runtime import RuntimeSession
from agentic_os.infrastructure.logging import get_logger

log = get_logger("runtime.session")

__all__ = [
    "SessionManager",
]

_MAX_COMMAND_HISTORY = 500


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class SessionRecord:
    """Internal wrapper around RuntimeSession with extra metadata."""

    session: RuntimeSession
    runtime_id: str
    created_at: datetime = field(default_factory=_utcnow)
    last_used: datetime = field(default_factory=_utcnow)


class SessionManager:
    """Persistent session tracking for runtimes.

    Stores sessions in-memory with thread-safe access. Each session records
    up to 500 commands before trimming oldest entries.
    """

    def __init__(self) -> None:
        self._lock: asyncio.Lock = asyncio.Lock()
        # session_id -> SessionRecord
        self._sessions: dict[str, SessionRecord] = {}
        # runtime_id -> set[session_id]
        self._by_runtime: dict[str, set[str]] = {}

    # ── Create ────────────────────────────────────────────────────────────────

    async def create_session(
        self,
        runtime_id: str,
        name: str,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> RuntimeSession:
        """Create a new RuntimeSession for the given runtime.

        Args:
            runtime_id: The runtime to attach the session to.
            name: Human-readable session name.
            cwd: Optional working directory.
            env: Optional environment variables.

        Returns:
            The newly created RuntimeSession.
        """
        session = RuntimeSession(
            name=name,
            working_directory=cwd,
            environment=env or {},
        )
        record = SessionRecord(session=session, runtime_id=runtime_id)

        async with self._lock:
            self._sessions[session.session_id] = record
            self._by_runtime.setdefault(runtime_id, set()).add(session.session_id)

        log.info(
            "session created",
            session_id=session.session_id,
            runtime_id=runtime_id,
            name=name,
        )
        return session

    # ── Read ──────────────────────────────────────────────────────────────────

    async def get_session(self, session_id: str) -> RuntimeSession | None:
        """Retrieve a session by its ID.

        Returns ``None`` if the session does not exist.
        """
        async with self._lock:
            record = self._sessions.get(session_id)
            if record is None:
                return None
            record.last_used = _utcnow()
            return record.session

    async def list_sessions(self, runtime_id: str) -> list[RuntimeSession]:
        """List all sessions for a given runtime.

        Returns sessions in creation order (oldest first).
        """
        async with self._lock:
            sids = self._by_runtime.get(runtime_id, set())
            records = [self._sessions[sid] for sid in sids if sid in self._sessions]
            # Sort by creation time
            records.sort(key=lambda r: r.created_at)
            return [r.session for r in records]

    async def list_all_sessions(self) -> list[RuntimeSession]:
        """Return all sessions across all runtimes."""
        async with self._lock:
            return [r.session for r in self._sessions.values()]

    # ── Find or Create ────────────────────────────────────────────────────────

    async def find_or_create(
        self,
        runtime_id: str,
        name: str,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> RuntimeSession:
        """Find an active session by name for the given runtime, or create one.

        If an active (``closed_at is None``) session with *name* already
        exists for *runtime_id*, it is returned. Otherwise a new session
        is created.
        """
        async with self._lock:
            sids = self._by_runtime.get(runtime_id, set())
            for sid in sids:
                record = self._sessions.get(sid)
                if record is None:
                    continue
                session = record.session
                if session.name == name and session.active:
                    record.last_used = _utcnow()
                    log.debug(
                        "reusing existing session",
                        session_id=session.session_id,
                        runtime_id=runtime_id,
                        name=name,
                    )
                    return session

        # Not found — create new outside lock to avoid long-held lock
        return await self.create_session(runtime_id, name, cwd, env)

    # ── Close ─────────────────────────────────────────────────────────────────

    async def close_session(self, session_id: str) -> bool:
        """Close (deactivate) a session.

        Sets ``active=False`` and ``closed_at``. Returns ``True`` if the
        session was found, ``False`` otherwise.
        """
        async with self._lock:
            record = self._sessions.get(session_id)
            if record is None:
                log.warning("close called for unknown session", session_id=session_id)
                return False
            session = record.session
            session.active = False
            session.closed_at = _utcnow()
            log.info(
                "session closed",
                session_id=session_id,
                runtime_id=record.runtime_id,
                name=session.name,
            )
        return True

    # ── Command History ───────────────────────────────────────────────────────

    async def record_command(
        self,
        session_id: str,
        command: str,
    ) -> bool:
        """Record a command in the session's history (max 500 entries).

        Returns ``True`` if the session was found, ``False`` otherwise.
        """
        async with self._lock:
            record = self._sessions.get(session_id)
            if record is None:
                return False
            session = record.session
            session.command_history.append(command)
            # Trim to max 500
            if len(session.command_history) > _MAX_COMMAND_HISTORY:
                session.command_history = session.command_history[-_MAX_COMMAND_HISTORY:]
            session.last_active = _utcnow()
            record.last_used = _utcnow()
        return True

    async def get_command_history(
        self,
        session_id: str,
        limit: int = 100,
    ) -> list[str]:
        """Return the most recent commands for a session."""
        async with self._lock:
            record = self._sessions.get(session_id)
            if record is None:
                return []
            history = record.session.command_history
            return history[-limit:] if limit else history[:]

    # ── Cleanup ───────────────────────────────────────────────────────────────

    async def remove_session(self, session_id: str) -> bool:
        """Completely remove a session from tracking."""
        async with self._lock:
            record = self._sessions.pop(session_id, None)
            if record is None:
                return False
            self._by_runtime.get(record.runtime_id, set()).discard(session_id)
        log.info("session removed", session_id=session_id)
        return True

    async def close_all_for_runtime(self, runtime_id: str) -> int:
        """Close all active sessions for a given runtime.

        Returns the number of sessions closed.
        """
        async with self._lock:
            sids = list(self._by_runtime.get(runtime_id, set()))
            count = 0
            for sid in sids:
                record = self._sessions.get(sid)
                if record and record.session.active:
                    record.session.active = False
                    record.session.closed_at = _utcnow()
                    count += 1
        if count:
            log.info("closed all sessions for runtime", runtime_id=runtime_id, count=count)
        return count

    async def count_sessions(self, runtime_id: str) -> int:
        """Return the number of sessions for a runtime."""
        async with self._lock:
            return len(self._by_runtime.get(runtime_id, set()))
