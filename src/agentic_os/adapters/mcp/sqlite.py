"""
SQLite MCP Adapter

Exposes SQLite database operations as MCP tools with database path sandboxing.
Write operations (INSERT, UPDATE, DELETE, DDL) require explicit opt-in via config.
"""

import json
import sqlite3
from pathlib import Path
from typing import Any

from agentic_os.adapters.mcp.base import BaseMCPAdapter
from agentic_os.domain.mcp import MCPTool, MCPToolResult, MCPTransport


class SQLiteAdapter(BaseMCPAdapter):
    """
    MCP adapter for SQLite database operations.

    Tools:
    - execute_query(sql, db_path) -> list[dict]
    - execute_statement(sql, db_path) -> dict  (requires allow_write=True)
    - list_tables(db_path) -> list[str]
    - describe_table(table, db_path) -> list[dict]

    Config:
      allowed_databases (list[str]): database file paths accessible via this
          adapter (default: [] — no databases allowed until configured).
      allow_write (bool): allow write statements (INSERT, UPDATE, DELETE, DDL)
          (default: False).
    """

    def __init__(
        self,
        name: str = "sqlite",
        config: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(name, config)
        cfg = config or {}
        self._allowed_databases: list[str] = cfg.get("allowed_databases", [])
        self._allow_write: bool = cfg.get("allow_write", False)

    # ── Transport ─────────────────────────────────────────────────────────────

    @property
    def transport_type(self) -> MCPTransport:
        return MCPTransport.STDIO

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def initialize(self) -> None:
        """Resolve all allowed database paths to absolute paths."""
        resolved: list[str] = []
        for db in self._allowed_databases:
            resolved.append(str(Path(db).resolve()))
        self._allowed_databases = resolved
        self._log.info(
            "SQLite adapter initialized",
            allowed_databases=self._allowed_databases,
            allow_write=self._allow_write,
        )

    # ── Path sandboxing ───────────────────────────────────────────────────────

    def _resolve_db(self, db_path: str) -> str:
        """Resolve the database path and validate it is in the allowed list."""
        resolved = Path(db_path).resolve()
        resolved_str = str(resolved)

        if not self._allowed_databases:
            raise PermissionError("No databases are allowed. Configure 'allowed_databases'.")

        for allowed in self._allowed_databases:
            allowed_path = Path(allowed).resolve()
            try:
                resolved.relative_to(allowed_path)
                return str(resolved)
            except ValueError:
                continue

            # Direct match (not just relative-to)
            if resolved_str == str(allowed_path):
                return resolved_str

        raise PermissionError(
            f"Database '{db_path}' resolves to '{resolved_str}' which is not in "
            f"allowed databases: {self._allowed_databases}"
        )

    @staticmethod
    def _is_write_statement(sql: str) -> bool:
        """Detect if a SQL statement is a write operation."""
        normalised = sql.strip().upper()
        # Strip leading parenthetical expressions and comments
        for prefix in (
            "INSERT",
            "UPDATE",
            "DELETE",
            "DROP",
            "CREATE",
            "ALTER",
            "TRUNCATE",
            "REPLACE",
            "ATTACH",
            "DETACH",
            "VACUUM",
        ):
            if normalised.startswith(prefix):
                return True
        return False

    # ── Tool definitions ──────────────────────────────────────────────────────

    def _build_tools(self) -> dict[str, MCPTool]:
        return {
            "execute_query": MCPTool(
                name="execute_query",
                description="Execute a SELECT query and return results as a list of dicts",
                input_schema={
                    "type": "object",
                    "properties": {
                        "sql": {
                            "type": "string",
                            "description": "SELECT SQL query to execute",
                        },
                        "db_path": {
                            "type": "string",
                            "description": "Path to the SQLite database file",
                        },
                    },
                    "required": ["sql", "db_path"],
                },
            ),
            "execute_statement": MCPTool(
                name="execute_statement",
                description=(
                    "Execute a write statement (INSERT, UPDATE, DELETE, DDL). "
                    "Requires allow_write=True in config."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "sql": {
                            "type": "string",
                            "description": "SQL statement to execute",
                        },
                        "db_path": {
                            "type": "string",
                            "description": "Path to the SQLite database file",
                        },
                    },
                    "required": ["sql", "db_path"],
                },
            ),
            "list_tables": MCPTool(
                name="list_tables",
                description="List all tables in the database",
                input_schema={
                    "type": "object",
                    "properties": {
                        "db_path": {
                            "type": "string",
                            "description": "Path to the SQLite database file",
                        },
                    },
                    "required": ["db_path"],
                },
            ),
            "describe_table": MCPTool(
                name="describe_table",
                description="Show column information for a table",
                input_schema={
                    "type": "object",
                    "properties": {
                        "table": {
                            "type": "string",
                            "description": "Table name",
                        },
                        "db_path": {
                            "type": "string",
                            "description": "Path to the SQLite database file",
                        },
                    },
                    "required": ["table", "db_path"],
                },
            ),
        }

    async def list_tools(self) -> list[MCPTool]:
        return list(self._build_tools().values())

    # ── Tool invocation ───────────────────────────────────────────────────────

    async def invoke_tool(self, tool: str, arguments: dict[str, Any]) -> MCPToolResult:
        tool_map: dict[str, Any] = {
            "execute_query": self._execute_query,
            "execute_statement": self._execute_statement,
            "list_tables": self._list_tables,
            "describe_table": self._describe_table,
        }

        method = tool_map.get(tool)
        if method is None:
            return MCPToolResult(
                content=[{"type": "text", "text": f"Unknown tool: {tool}"}],
                is_error=True,
            )

        try:
            result = await method(arguments)
            text = json.dumps(result, default=str, indent=2)
            return MCPToolResult(
                content=[{"type": "text", "text": text}],
                is_error=False,
            )
        except PermissionError as e:
            self._log.warning("Permission denied for tool '%s': %s", tool, e)
            return MCPToolResult(
                content=[{"type": "text", "text": str(e)}],
                is_error=True,
            )
        except sqlite3.Error as e:
            self._log.error("SQLite error for tool '%s': %s", tool, e)
            return MCPToolResult(
                content=[{"type": "text", "text": f"SQLite error: {e}"}],
                is_error=True,
            )
        except Exception as e:
            self._log.error("Tool '%s' failed: %s", tool, e)
            return MCPToolResult(
                content=[{"type": "text", "text": f"Error: {e}"}],
                is_error=True,
            )

    # ── Tool implementations ──────────────────────────────────────────────────

    async def _execute_query(self, args: dict[str, Any]) -> list[dict[str, Any]]:
        sql = args["sql"]
        db_path = self._resolve_db(args["db_path"])

        if self._is_write_statement(sql):
            raise PermissionError(
                "Write statements are not allowed via execute_query. "
                "Use execute_statement with allow_write=True."
            )

        # Run the query in a thread pool to avoid blocking the event loop
        def _query() -> list[dict[str, Any]]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                cursor = conn.execute(sql)
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
            finally:
                conn.close()

        import asyncio

        return await asyncio.get_running_loop().run_in_executor(None, _query)

    async def _execute_statement(self, args: dict[str, Any]) -> dict[str, Any]:
        if not self._allow_write:
            raise PermissionError("Write operations are disabled. Set allow_write=True in config.")

        sql = args["sql"]
        db_path = self._resolve_db(args["db_path"])

        def _statement() -> dict[str, Any]:
            conn = sqlite3.connect(db_path)
            try:
                cursor = conn.execute(sql)
                conn.commit()
                return {
                    "rowcount": cursor.rowcount,
                    "lastrowid": cursor.lastrowid,
                }
            finally:
                conn.close()

        import asyncio

        return await asyncio.get_running_loop().run_in_executor(None, _statement)

    async def _list_tables(self, args: dict[str, Any]) -> list[str]:
        db_path = self._resolve_db(args["db_path"])

        def _tables() -> list[str]:
            conn = sqlite3.connect(db_path)
            try:
                cursor = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                )
                return [row[0] for row in cursor.fetchall()]
            finally:
                conn.close()

        import asyncio

        return await asyncio.get_running_loop().run_in_executor(None, _tables)

    async def _describe_table(self, args: dict[str, Any]) -> list[dict[str, Any]]:
        table = args["table"]
        db_path = self._resolve_db(args["db_path"])

        def _describe() -> list[dict[str, Any]]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                cursor = conn.execute(f"PRAGMA table_info({table!r})")
                return [dict(row) for row in cursor.fetchall()]
            finally:
                conn.close()

        import asyncio

        return await asyncio.get_running_loop().run_in_executor(None, _describe)
