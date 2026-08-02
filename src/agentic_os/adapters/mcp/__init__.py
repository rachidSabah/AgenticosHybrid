"""MCP Adapter Framework - built-in adapters for common protocols and services."""

from agentic_os.adapters.mcp.base import BaseMCPAdapter
from agentic_os.adapters.mcp.filesystem import FilesystemAdapter
from agentic_os.adapters.mcp.git import GitAdapter
from agentic_os.adapters.mcp.http import HTTPAdapter
from agentic_os.adapters.mcp.sqlite import SQLiteAdapter
from agentic_os.adapters.mcp.terminal import TerminalAdapter

__all__ = [
    "BaseMCPAdapter",
    "FilesystemAdapter",
    "GitAdapter",
    "HTTPAdapter",
    "SQLiteAdapter",
    "TerminalAdapter",
]
