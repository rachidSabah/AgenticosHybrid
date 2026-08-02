"""
Filesystem MCP Adapter

Exposes filesystem operations as MCP tools with path sandboxing.
All paths are validated against a configured set of allowed directories.
"""

import json
from pathlib import Path
from typing import Any

from agentic_os.adapters.mcp.base import BaseMCPAdapter
from agentic_os.domain.mcp import MCPTool, MCPToolResult, MCPTransport


class FilesystemAdapter(BaseMCPAdapter):
    """
    MCP adapter for filesystem operations.

    Tools:
    - read_file(path) -> str
    - write_file(path, content) -> str
    - list_directory(path) -> list[dict]
    - file_info(path) -> dict
    - search_files(pattern, path=".") -> list[str]

    Config:
      allowed_directories (list[str]): paths accessible via this adapter
          (default: [cwd]).  All paths are resolved and validated against
          this allowlist to prevent directory-traversal attacks.
    """

    def __init__(
        self,
        name: str = "filesystem",
        config: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(name, config)
        cfg = config or {}
        self._allowed_directories: list[str] = cfg.get("allowed_directories", [str(Path.cwd())])

    # ── Transport ─────────────────────────────────────────────────────────────

    @property
    def transport_type(self) -> MCPTransport:
        return MCPTransport.STDIO

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def initialize(self) -> None:
        """Resolve all allowed directories to absolute paths."""
        resolved: list[str] = []
        for d in self._allowed_directories:
            resolved.append(str(Path(d).resolve()))
        self._allowed_directories = resolved
        self._log.info(
            "Filesystem adapter initialized",
            allowed_directories=self._allowed_directories,
        )

    # ── Path sandboxing ───────────────────────────────────────────────────────

    def _resolve_path(self, path: str) -> Path:
        """Resolve *path* and verify it sits inside an allowed directory.

        Raises PermissionError when the resolved path is outside every
        allowed directory.
        """
        resolved = Path(path).resolve()
        for allowed_dir in self._allowed_directories:
            allowed = Path(allowed_dir).resolve()
            try:
                resolved.relative_to(allowed)
                return resolved
            except ValueError:
                continue
        raise PermissionError(
            f"Path '{path}' resolves to '{resolved}' which is outside allowed "
            f"directories: {self._allowed_directories}"
        )

    # ── Tool definitions ──────────────────────────────────────────────────────

    def _build_tools(self) -> dict[str, MCPTool]:
        return {
            "read_file": MCPTool(
                name="read_file",
                description="Read the contents of a file as text",
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Absolute or relative path to the file",
                        },
                    },
                    "required": ["path"],
                },
            ),
            "write_file": MCPTool(
                name="write_file",
                description="Write text content to a file (overwrites existing)",
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Absolute or relative path to the file",
                        },
                        "content": {
                            "type": "string",
                            "description": "Text content to write",
                        },
                    },
                    "required": ["path", "content"],
                },
            ),
            "list_directory": MCPTool(
                name="list_directory",
                description="List entries in a directory",
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path to the directory",
                        },
                    },
                    "required": ["path"],
                },
            ),
            "file_info": MCPTool(
                name="file_info",
                description="Get metadata about a file or directory",
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path to the file or directory",
                        },
                    },
                    "required": ["path"],
                },
            ),
            "search_files": MCPTool(
                name="search_files",
                description="Recursively search for files matching a glob pattern",
                input_schema={
                    "type": "object",
                    "properties": {
                        "pattern": {
                            "type": "string",
                            "description": "Glob pattern (e.g. '*.py', '**/*.md')",
                        },
                        "path": {
                            "type": "string",
                            "description": "Root path to start the search (default: '.')",
                        },
                    },
                    "required": ["pattern"],
                },
            ),
        }

    async def list_tools(self) -> list[MCPTool]:
        return list(self._build_tools().values())

    # ── Tool invocation ───────────────────────────────────────────────────────

    async def invoke_tool(self, tool: str, arguments: dict[str, Any]) -> MCPToolResult:
        tool_map: dict[str, Any] = {
            "read_file": self._read_file,
            "write_file": self._write_file,
            "list_directory": self._list_directory,
            "file_info": self._file_info,
            "search_files": self._search_files,
        }

        method = tool_map.get(tool)
        if method is None:
            return MCPToolResult(
                content=[{"type": "text", "text": f"Unknown tool: {tool}"}],
                is_error=True,
            )

        try:
            result = await method(arguments)
            if isinstance(result, str):
                text = result
            else:
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
        except FileNotFoundError as e:
            self._log.warning("File not found for tool '%s': %s", tool, e)
            return MCPToolResult(
                content=[{"type": "text", "text": str(e)}],
                is_error=True,
            )
        except Exception as e:
            self._log.error("Tool '%s' failed: %s", tool, e)
            return MCPToolResult(
                content=[{"type": "text", "text": f"Error: {e}"}],
                is_error=True,
            )

    # ── Tool implementations ──────────────────────────────────────────────────

    async def _read_file(self, args: dict[str, Any]) -> str:
        path = self._resolve_path(args["path"])
        return path.read_text(encoding="utf-8")

    async def _write_file(self, args: dict[str, Any]) -> str:
        path = self._resolve_path(args["path"])
        path.write_text(args["content"], encoding="utf-8")
        return f"Written {len(args['content'])} bytes to {path}"

    async def _list_directory(self, args: dict[str, Any]) -> list[dict[str, Any]]:
        path = self._resolve_path(args["path"])
        if not path.is_dir():
            raise NotADirectoryError(str(path))
        entries: list[dict[str, Any]] = []
        for entry in sorted(path.iterdir()):
            try:
                stat = entry.stat()
                entries.append(
                    {
                        "name": entry.name,
                        "is_dir": entry.is_dir(),
                        "is_file": entry.is_file(),
                        "size": stat.st_size,
                        "modified": stat.st_mtime,
                    }
                )
            except OSError:
                entries.append(
                    {
                        "name": entry.name,
                        "is_dir": entry.is_dir(),
                        "is_file": entry.is_file(),
                        "size": 0,
                        "modified": 0,
                    }
                )
        return entries

    async def _file_info(self, args: dict[str, Any]) -> dict[str, Any]:
        path = self._resolve_path(args["path"])
        stat = path.stat()
        return {
            "name": path.name,
            "path": str(path),
            "is_dir": path.is_dir(),
            "is_file": path.is_file(),
            "is_symlink": path.is_symlink(),
            "size": stat.st_size,
            "modified": stat.st_mtime,
            "created": stat.st_ctime,
            "mode": stat.st_mode,
        }

    async def _search_files(self, args: dict[str, Any]) -> list[str]:
        root = self._resolve_path(args.get("path", "."))
        pattern = args["pattern"]
        results: list[str] = []
        for entry in root.rglob(pattern):
            if entry.is_file():
                try:
                    results.append(str(entry.relative_to(root)))
                except ValueError:
                    results.append(str(entry))
        return sorted(results)
