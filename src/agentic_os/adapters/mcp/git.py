"""
Git MCP Adapter

Exposes Git operations as MCP tools with repository sandboxing.
Write operations (commit) require explicit opt-in via config.
"""

import json
from pathlib import Path
from typing import Any

from agentic_os.adapters.mcp.base import BaseMCPAdapter
from agentic_os.domain.mcp import MCPTool, MCPToolResult, MCPTransport


class GitAdapter(BaseMCPAdapter):
    """
    MCP adapter for Git operations.

    Tools:
    - git_status(path=".") -> dict
    - git_log(count=10, path=".") -> list[dict]
    - git_diff(target="HEAD", path=".") -> str
    - git_branches(path=".") -> list[str]
    - git_commit(message, path=".") -> str  (requires allow_write=True)

    Config:
      allowed_repos (list[str]): repository paths accessible via this adapter
          (default: ["."]).
      allow_write (bool): allow write operations such as commit (default: False).
    """

    def __init__(
        self,
        name: str = "git",
        config: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(name, config)
        cfg = config or {}
        self._allowed_repos: list[str] = cfg.get("allowed_repos", ["."])
        self._allow_write: bool = cfg.get("allow_write", False)

    # ── Transport ─────────────────────────────────────────────────────────────

    @property
    def transport_type(self) -> MCPTransport:
        return MCPTransport.STDIO

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def initialize(self) -> None:
        """Resolve all allowed repos to absolute paths."""
        resolved: list[str] = []
        for r in self._allowed_repos:
            resolved.append(str(Path(r).resolve()))
        self._allowed_repos = resolved
        self._log.info(
            "Git adapter initialized",
            allowed_repos=self._allowed_repos,
            allow_write=self._allow_write,
        )

    # ── Path sandboxing ───────────────────────────────────────────────────────

    def _resolve_repo(self, path: str) -> Path:
        """Resolve *path* and verify it sits inside an allowed repo directory."""
        resolved = Path(path).resolve()
        if not resolved.is_dir():
            resolved = resolved.parent
        for allowed in self._allowed_repos:
            allowed_path = Path(allowed).resolve()
            try:
                resolved.relative_to(allowed_path)
                return resolved
            except ValueError:
                continue
        raise PermissionError(
            f"Path '{path}' resolves to '{resolved}' which is outside allowed "
            f"repos: {self._allowed_repos}"
        )

    # ── Subprocess helper ─────────────────────────────────────────────────────

    async def _run_git(self, args: list[str], cwd: str | None = None) -> tuple[str, str, int]:
        """Run a git command and return (stdout, stderr, returncode)."""
        import asyncio

        repo_path = self._resolve_repo(cwd or ".")

        proc = await asyncio.create_subprocess_exec(
            "git",
            *args,
            cwd=str(repo_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout_bytes, stderr_bytes = await proc.communicate()
        return (
            stdout_bytes.decode("utf-8", errors="replace"),
            stderr_bytes.decode("utf-8", errors="replace"),
            proc.returncode or 0,
        )

    # ── Tool definitions ──────────────────────────────────────────────────────

    def _build_tools(self) -> dict[str, MCPTool]:
        tools: dict[str, MCPTool] = {
            "git_status": MCPTool(
                name="git_status",
                description="Show the working tree status",
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Repository path (default: '.')",
                        },
                    },
                },
            ),
            "git_log": MCPTool(
                name="git_log",
                description="Show commit log",
                input_schema={
                    "type": "object",
                    "properties": {
                        "count": {
                            "type": "integer",
                            "description": "Number of commits to show (default: 10)",
                        },
                        "path": {
                            "type": "string",
                            "description": "Repository path (default: '.')",
                        },
                    },
                },
            ),
            "git_diff": MCPTool(
                name="git_diff",
                description="Show changes between commits, branches, or the working tree",
                input_schema={
                    "type": "object",
                    "properties": {
                        "target": {
                            "type": "string",
                            "description": "Target ref (default: 'HEAD')",
                        },
                        "path": {
                            "type": "string",
                            "description": "Repository path (default: '.')",
                        },
                    },
                },
            ),
            "git_branches": MCPTool(
                name="git_branches",
                description="List local branches",
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Repository path (default: '.')",
                        },
                    },
                },
            ),
            "git_commit": MCPTool(
                name="git_commit",
                description="Create a new commit (requires allow_write=True in config)",
                input_schema={
                    "type": "object",
                    "properties": {
                        "message": {
                            "type": "string",
                            "description": "Commit message",
                        },
                        "path": {
                            "type": "string",
                            "description": "Repository path (default: '.')",
                        },
                    },
                    "required": ["message"],
                },
            ),
        }
        return tools

    async def list_tools(self) -> list[MCPTool]:
        return list(self._build_tools().values())

    # ── Tool invocation ───────────────────────────────────────────────────────

    async def invoke_tool(self, tool: str, arguments: dict[str, Any]) -> MCPToolResult:
        tool_map: dict[str, Any] = {
            "git_status": self._git_status,
            "git_log": self._git_log,
            "git_diff": self._git_diff,
            "git_branches": self._git_branches,
            "git_commit": self._git_commit,
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
        except Exception as e:
            self._log.error("Tool '%s' failed: %s", tool, e)
            return MCPToolResult(
                content=[{"type": "text", "text": f"Error: {e}"}],
                is_error=True,
            )

    # ── Tool implementations ──────────────────────────────────────────────────

    async def _git_status(self, args: dict[str, Any]) -> dict[str, Any]:
        path = args.get("path", ".")
        stdout, stderr, rc = await self._run_git(["status", "--porcelain"], cwd=path)

        if rc != 0:
            raise RuntimeError(f"git status failed: {stderr}")

        changed: list[str] = []
        staged: list[str] = []
        untracked: list[str] = []
        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("??"):
                untracked.append(line[2:].strip())
            elif line.startswith(" "):
                staged.append(line[2:].strip())
            else:
                changed.append(line[2:].strip())

        return {
            "changed": changed,
            "staged": staged,
            "untracked": untracked,
        }

    async def _git_log(self, args: dict[str, Any]) -> list[dict[str, Any]]:
        count = args.get("count", 10)
        path = args.get("path", ".")

        fmt = "--format=%H%n%an%n%ae%n%ai%n%s%n%n%b%n-----END-----"
        stdout, stderr, rc = await self._run_git(["log", f"-n {count}", fmt], cwd=path)

        if rc != 0:
            raise RuntimeError(f"git log failed: {stderr}")

        commits: list[dict[str, Any]] = []
        for entry in stdout.split("-----END-----\n"):
            entry = entry.strip()
            if not entry:
                continue
            lines = entry.split("\n", 4)
            if len(lines) < 5:
                continue
            commits.append(
                {
                    "hash": lines[0].strip(),
                    "author": lines[1].strip(),
                    "email": lines[2].strip(),
                    "date": lines[3].strip(),
                    "message": lines[4].strip(),
                }
            )
        return commits

    async def _git_diff(self, args: dict[str, Any]) -> str:
        target = args.get("target", "HEAD")
        path = args.get("path", ".")

        stdout, stderr, rc = await self._run_git(["diff", target], cwd=path)

        if rc != 0:
            raise RuntimeError(f"git diff failed: {stderr}")

        return stdout.strip()

    async def _git_branches(self, args: dict[str, Any]) -> list[str]:
        path = args.get("path", ".")

        stdout, stderr, rc = await self._run_git(
            ["branch", "--list", "--format=%(refname:short)"], cwd=path
        )

        if rc != 0:
            raise RuntimeError(f"git branch failed: {stderr}")

        return [line.strip() for line in stdout.splitlines() if line.strip()]

    async def _git_commit(self, args: dict[str, Any]) -> str:
        if not self._allow_write:
            raise PermissionError("Write operations are disabled. Set allow_write=True in config.")

        message = args["message"]
        path = args.get("path", ".")

        stdout, stderr, rc = await self._run_git(["commit", "-m", message], cwd=path)

        if rc != 0:
            # Allow "nothing to commit" as non-fatal
            if "nothing to commit" in stderr.lower():
                return "Nothing to commit — working tree clean."
            raise RuntimeError(f"git commit failed: {stderr}")

        # Extract the commit hash from the output
        for line in stdout.splitlines():
            if line.startswith("["):
                return line.strip()

        return stdout.strip()
