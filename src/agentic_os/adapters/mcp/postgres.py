"""
PostgreSQL MCP Adapter

Exposes PostgreSQL database operations as MCP tools including:
- Query execution
- Schema inspection
- Table operations
"""

import json
from typing import Any

from agentic_os.adapters.mcp.base import BaseMCPAdapter
from agentic_os.domain.mcp import MCPPrompt, MCPResource, MCPTool, MCPToolResult, MCPTransport


class PostgreSQLAdapter(BaseMCPAdapter):
    """
    MCP adapter for PostgreSQL database operations.

    Tools:
    - execute_query(query) -> list[dict]
    - list_tables() -> list[dict]
    - describe_table(table_name) -> dict
    - list_databases() -> list[str]

    Config:
      host (str): Database host (default: localhost)
      port (int): Database port (default: 5432)
      database (str): Database name
      user (str): Database user
      password (str): Database password
    """

    def __init__(
        self,
        name: str = "postgresql",
        config: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(name, config)
        self._host = config.get("host", "localhost") if config else "localhost"
        self._port = config.get("port", 5432) if config else 5432
        self._database = config.get("database", "") if config else ""
        self._user = config.get("user", "") if config else ""
        self._password = config.get("password", "") if config else ""
        self._connection = None

    @property
    def transport_type(self) -> MCPTransport:
        return MCPTransport.STDIO

    async def initialize(self) -> None:
        """Initialize the database connection."""
        try:
            import asyncpg

            self._connection = await asyncpg.connect(
                host=self._host,
                port=self._port,
                database=self._database,
                user=self._user,
                password=self._password,
            )
            self._log.info(f"Connected to PostgreSQL database: {self._database}")
        except ImportError:
            self._log.warning("asyncpg not installed, using mock implementation")
        except Exception as e:
            self._log.error(f"Failed to connect to PostgreSQL: {e}")

    async def shutdown(self) -> None:
        """Close the database connection."""
        if self._connection:
            await self._connection.close()
            self._log.info("Disconnected from PostgreSQL")

    async def list_tools(self) -> list[MCPTool]:
        return list(self._build_tools().values())

    def _build_tools(self) -> dict[str, MCPTool]:
        return {
            "execute_query": MCPTool(
                name="execute_query",
                description="Execute a SQL query and return results",
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "SQL query to execute"},
                    },
                    "required": ["query"],
                },
            ),
            "list_tables": MCPTool(
                name="list_tables",
                description="List all tables in the current database",
                input_schema={
                    "type": "object",
                    "properties": {
                        "schema": {
                            "type": "string",
                            "description": "Schema name (default: public)",
                        },
                    },
                },
            ),
            "describe_table": MCPTool(
                name="describe_table",
                description="Get detailed information about a table",
                input_schema={
                    "type": "object",
                    "properties": {
                        "table_name": {
                            "type": "string",
                            "description": "Name of the table",
                        },
                        "schema": {
                            "type": "string",
                            "description": "Schema name (default: public)",
                        },
                    },
                    "required": ["table_name"],
                },
            ),
            "list_databases": MCPTool(
                name="list_databases",
                description="List all databases on the server",
                input_schema={"type": "object", "properties": {}},
            ),
        }

    async def invoke_tool(self, tool: str, arguments: dict[str, Any]) -> MCPToolResult:
        tool_map = {
            "execute_query": self._execute_query,
            "list_tables": self._list_tables,
            "describe_table": self._describe_table,
            "list_databases": self._list_databases,
        }

        method = tool_map.get(tool)
        if method is None:
            return MCPToolResult(
                content=[{"type": "text", "text": f"Unknown tool: {tool}"}],
                is_error=True,
            )

        try:
            result = await method(arguments)
            return MCPToolResult(
                content=[{"type": "text", "text": json.dumps(result, default=str)}],
                is_error=False,
            )
        except Exception as e:
            self._log.error(f"PostgreSQL tool '{tool}' failed: {e}")
            return MCPToolResult(
                content=[{"type": "text", "text": f"Error: {e}"}],
                is_error=True,
            )

    async def _execute_query(self, args: dict[str, Any]) -> dict:
        """Execute a SQL query."""
        if not self._connection:
            return {"error": "Not connected to database", "rows": [], "row_count": 0}

        query = args["query"]
        rows = await self._connection.fetch(query)
        return {
            "rows": [dict(row) for row in rows],
            "row_count": len(rows),
        }

    async def _list_tables(self, args: dict[str, Any]) -> dict:
        """List tables in the database."""
        if not self._connection:
            return {"tables": [], "error": "Not connected to database"}

        schema = args.get("schema", "public")
        query = """
            SELECT table_name, table_type, is_insertable_into
            FROM information_schema.tables
            WHERE table_schema = $1
            ORDER BY table_name
        """
        rows = await self._connection.fetch(query, schema)
        return {
            "tables": [
                {
                    "name": row["table_name"],
                    "type": row["table_type"],
                    "insertable": row["is_insertable_into"],
                }
                for row in rows
            ],
        }

    async def _describe_table(self, args: dict[str, Any]) -> dict:
        """Describe a table's structure."""
        if not self._connection:
            return {"columns": [], "error": "Not connected to database"}

        table_name = args["table_name"]
        schema = args.get("schema", "public")

        query = """
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema = $1 AND table_name = $2
            ORDER BY ordinal_position
        """
        rows = await self._connection.fetch(query, schema, table_name)
        return {
            "table_name": table_name,
            "schema": schema,
            "columns": [
                {
                    "name": row["column_name"],
                    "type": row["data_type"],
                    "nullable": row["is_nullable"] == "YES",
                    "default": row["column_default"],
                }
                for row in rows
            ],
        }

    async def _list_databases(self, args: dict[str, Any]) -> dict:
        """List all databases."""
        if not self._connection:
            return {"databases": [], "error": "Not connected to database"}

        query = "SELECT datname FROM pg_database WHERE datistemplate = false ORDER BY datname"
        rows = await self._connection.fetch(query)
        return {
            "databases": [row["datname"] for row in rows],
        }

    async def list_resources(self) -> list[MCPResource]:
        from agentic_os.domain.mcp import MCPResource as MCPResourceModel

        return [
            MCPResourceModel(
                uri=f"postgres://{self._database}/tables",
                name="Database Tables",
                description="List of tables in the database",
                mime_type="application/json",
            ),
        ]

    async def read_resource(self, uri: str) -> dict[str, Any]:
        if "://" in uri and "/tables" in uri:
            return await self._list_tables({"schema": "public"})
        raise ValueError(f"Unknown resource URI: {uri}")

    async def list_prompts(self) -> list[MCPPrompt]:
        from agentic_os.domain.mcp import MCPPrompt as MCPPromptModel

        return [
            MCPPromptModel(
                name="postgres_table_summary",
                description="Generate a summary of a database table",
                arguments=(
                    {"name": "table_name", "description": "Name of the table", "required": True},
                    {"name": "schema", "description": "Schema name", "required": False},
                ),
            ),
        ]

    async def get_prompt(
        self, name: str, arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        args = arguments or {}
        if name == "postgres_table_summary":
            table_name = args.get("table_name")
            schema = args.get("schema", "public")

            info = await self._describe_table({"table_name": table_name, "schema": schema})

            summary = f"# PostgreSQL Table Summary: {schema}.{table_name}\n\n"
            summary += f"Columns ({len(info.get('columns', []))}):\n\n"

            for col in info.get("columns", []):
                nullable = "NULL" if col["nullable"] else "NOT NULL"
                default = f" DEFAULT {col['default']}" if col["default"] else ""
                summary += f"- `{col['name']}` {col['type']} {nullable}{default}\n"

            return {
                "messages": [
                    {"role": "user", "content": summary},
                ],
            }

        raise ValueError(f"Unknown prompt: {name}")
