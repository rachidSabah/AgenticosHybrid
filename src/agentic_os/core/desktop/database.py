"""Local Database Manager — SQLite-based local persistence with migrations."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agentic_os.domain.desktop import (
    DatabaseInfo,
    SessionRecord,
    WorkspaceMetadata,
)
from agentic_os.infrastructure.logging import get_logger

log = get_logger("desktop.database")

MIGRATIONS: list[dict[str, Any]] = [
    {
        "name": "001_initial",
        "sql": """
        CREATE TABLE IF NOT EXISTS workspaces (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            layout_json TEXT DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS workspace_metadata (
            workspace_id TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (workspace_id, key)
        );
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            session_type TEXT NOT NULL DEFAULT 'app',
            started_at TEXT NOT NULL,
            ended_at TEXT,
            duration_seconds REAL DEFAULT 0,
            metadata_json TEXT DEFAULT '{}'
        );
        CREATE TABLE IF NOT EXISTS desktop_config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS migration_log (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL,
            checksum TEXT NOT NULL,
            success INTEGER NOT NULL DEFAULT 1,
            duration_ms REAL DEFAULT 0,
            error TEXT
        );
        """,
    },
]


class LocalDatabaseManager:
    """SQLite-based local persistence with migration support."""

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or self._default_db_path()
        self._conn: sqlite3.Connection | None = None

    @staticmethod
    def _default_db_path() -> str:
        data_dir = Path.home() / ".agentic_os" / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        return str(data_dir / "desktop.db")

    async def initialize(self) -> None:
        self._conn = sqlite3.connect(self._db_path)
        self._conn.row_factory = sqlite3.Row
        await self._run_migrations()
        log.info("Local database initialized", path=self._db_path)

    async def _run_migrations(self) -> None:
        assert self._conn is not None
        cursor = self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='migration_log'"
        )
        if not cursor.fetchone():
            sql = (
                "CREATE TABLE IF NOT EXISTS migration_log ("
                "id TEXT PRIMARY KEY, name TEXT NOT NULL, "
                "applied_at TEXT NOT NULL, checksum TEXT NOT NULL, "
                "success INTEGER NOT NULL DEFAULT 1, duration_ms REAL DEFAULT 0, error TEXT)"
            )
            self._conn.execute(sql)

        for migration in MIGRATIONS:
            checksum = hashlib.sha256(migration["sql"].encode()).hexdigest()
            cursor = self._conn.execute(
                "SELECT id FROM migration_log WHERE name = ? AND success = 1", (migration["name"],)
            )
            if cursor.fetchone():
                continue
            self._conn.executescript(migration["sql"])
            self._conn.execute(
                "INSERT INTO migration_log (id, name, applied_at, checksum, success, duration_ms) "
                "VALUES (?, ?, ?, ?, 1, 0)",
                (
                    hashlib.md5(migration["name"].encode()).hexdigest(),
                    migration["name"],
                    datetime.now(UTC).isoformat(),
                    checksum,
                ),
            )
            self._conn.commit()
            log.info("Migration applied", name=migration["name"])

    async def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    async def get_info(self) -> DatabaseInfo:
        if self._conn is None:
            return DatabaseInfo(status="disconnected")
        cursor = self._conn.execute("SELECT COUNT(*) as count FROM migration_log")
        migration_count = cursor.fetchone()["count"]
        cursor = self._conn.execute(
            "SELECT name FROM migration_log ORDER BY applied_at DESC LIMIT 1"
        )
        row = cursor.fetchone()
        last_migration = row["name"] if row else ""
        cursor = self._conn.execute(
            "SELECT COUNT(*) as count FROM sqlite_master WHERE type='table'"
        )
        table_count = cursor.fetchone()["count"]
        size = (
            Path(self._db_path).stat().st_size / (1024 * 1024)
            if Path(self._db_path).exists()
            else 0.0
        )
        return DatabaseInfo(
            path=self._db_path,
            size_mb=round(size, 2),
            table_count=table_count,
            migration_count=migration_count,
            last_migration=last_migration,
        )

    async def execute(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        if self._conn is None:
            raise RuntimeError("Database not initialized")
        cursor = self._conn.execute(sql, params)
        self._conn.commit()
        return [dict(row) for row in cursor.fetchall()]

    async def save_session(self, session: SessionRecord) -> None:
        sql = (
            "INSERT OR REPLACE INTO sessions "
            "(id, session_type, started_at, ended_at, duration_seconds, metadata_json) "
            "VALUES (?, ?, ?, ?, ?, ?)"
        )
        await self.execute(
            sql,
            (
                session.id,
                session.session_type,
                session.started_at.isoformat(),
                session.ended_at.isoformat() if session.ended_at else None,
                session.duration_seconds,
                json.dumps(session.metadata),
            ),
        )

    async def save_workspace_metadata(self, meta: WorkspaceMetadata) -> None:
        sql = (
            "INSERT OR REPLACE INTO workspace_metadata "
            "(workspace_id, key, value, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)"
        )
        await self.execute(
            sql,
            (
                meta.workspace_id,
                meta.key,
                meta.value,
                meta.created_at.isoformat(),
                meta.updated_at.isoformat(),
            ),
        )
