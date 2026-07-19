"""
Terminal MCP Adapter

Exposes terminal command execution as MCP tools with command sandboxing.
Write/script operations require explicit opt-in via config.
"""

import json
import shlex
from typing import Any

from agentic_os.adapters.mcp.base import BaseMCPAdapter
from agentic_os.domain.mcp import MCPTool, MCPToolResult, MCPTransport

# Commands that are blocked by default for safety.
_DEFAULT_BLOCKED_COMMANDS: list[str] = [
    "dd",
    "mkfs",
    "fdisk",
    "parted",
    "shutdown",
    "reboot",
    "halt",
    "poweroff",
    "init",
    "killall",
    "pkill",
    "su",
    "sudo",
    "chmod",
    "chown",
    "passwd",
    "useradd",
    "userdel",
    "usermod",
    "groupadd",
    "groupdel",
    "mount",
    "umount",
    "modprobe",
    "insmod",
    "rmmod",
    "iptables",
    "ufw",
    "systemctl",
    "service",
]


class TerminalAdapter(BaseMCPAdapter):
    """
    MCP adapter for terminal command execution.

    Tools:
    - run_command(command, timeout=30) -> dict
    - run_script(content, interpreter="bash", timeout=60) -> dict

    Security:
      Config ``allowed_commands`` (list[str] | None): if set, only these base
          commands may be run (exact base-command match).
      Config ``blocked_commands`` (list[str]): base commands that are never
          allowed.  Defaults to a set of dangerous system commands.
      Config ``enable_scripts`` (bool): enable the run_script tool (default: False).
    """

    def __init__(
        self,
        name: str = "terminal",
        config: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(name, config)
        cfg = config or {}
        self._allowed_commands: list[str] | None = cfg.get("allowed_commands")
        self._blocked_commands: list[str] = cfg.get(
            "blocked_commands", list(_DEFAULT_BLOCKED_COMMANDS)
        )
        self._enable_scripts: bool = cfg.get("enable_scripts", False)

    # ── Transport ─────────────────────────────────────────────────────────────

    @property
    def transport_type(self) -> MCPTransport:
        return MCPTransport.STDIO

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def initialize(self) -> None:
        self._log.info(
            "Terminal adapter initialized",
            allowed_commands=self._allowed_commands,
            blocked_count=len(self._blocked_commands),
            enable_scripts=self._enable_scripts,
        )

    # ── Command validation ────────────────────────────────────────────────────

    def _extract_base_command(self, command: str) -> str:
        """Extract the base command (first token) from a shell command string."""
        parts = shlex.split(command)
        if not parts:
            msg = "Empty command"
            raise ValueError(msg)
        return parts[0]

    def _validate_command(self, command: str) -> None:
        """Check that *command* is allowed by the configured security rules."""
        base = self._extract_base_command(command)

        # Check blocked commands first
        if base in self._blocked_commands:
            raise PermissionError(
                f"Command '{base}' is blocked by the terminal adapter configuration."
            )

        # If allowed_commands is set, the base must be in the allowlist
        if self._allowed_commands is not None:
            if base not in self._allowed_commands:
                raise PermissionError(
                    f"Command '{base}' is not in the allowed commands list: "
                    f"{self._allowed_commands}"
                )

    # ── Tool definitions ──────────────────────────────────────────────────────

    def _build_tools(self) -> dict[str, MCPTool]:
        tools: dict[str, MCPTool] = {
            "run_command": MCPTool(
                name="run_command",
                description="Run a shell command and return its output",
                input_schema={
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "Shell command to execute",
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "Timeout in seconds (default: 30)",
                        },
                    },
                    "required": ["command"],
                },
            ),
        }

        if self._enable_scripts:
            tools["run_script"] = MCPTool(
                name="run_script",
                description="Run a script using the specified interpreter",
                input_schema={
                    "type": "object",
                    "properties": {
                        "content": {
                            "type": "string",
                            "description": "Script content",
                        },
                        "interpreter": {
                            "type": "string",
                            "description": "Interpreter to use (default: 'bash')",
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "Timeout in seconds (default: 60)",
                        },
                    },
                    "required": ["content"],
                },
            )

        return tools

    async def list_tools(self) -> list[MCPTool]:
        return list(self._build_tools().values())

    # ── Tool invocation ───────────────────────────────────────────────────────

    async def invoke_tool(self, tool: str, arguments: dict[str, Any]) -> MCPToolResult:
        tool_map: dict[str, Any] = {
            "run_command": self._run_command,
            "run_script": self._run_script,
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
        except TimeoutError as e:
            self._log.warning("Timeout for tool '%s': %s", tool, e)
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

    async def _run_command(self, args: dict[str, Any]) -> dict[str, Any]:
        import asyncio

        command = args["command"]
        timeout = args.get("timeout", 30)

        self._validate_command(command)

        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except TimeoutError:
            proc.kill()
            await proc.wait()
            raise TimeoutError(
                f"Command timed out after {timeout} seconds: {command[:60]}"
            ) from None

        return {
            "stdout": stdout_bytes.decode("utf-8", errors="replace"),
            "stderr": stderr_bytes.decode("utf-8", errors="replace"),
            "returncode": proc.returncode or 0,
            "timed_out": False,
        }

    async def _run_script(self, args: dict[str, Any]) -> dict[str, Any]:
        import asyncio
        import tempfile

        if not self._enable_scripts:
            raise PermissionError(
                "Script execution is disabled. Set enable_scripts=True in config."
            )

        content = args["content"]
        interpreter = args.get("interpreter", "bash")
        timeout = args.get("timeout", 60)

        # Validate the interpreter as the base command
        self._validate_command(interpreter)

        # Write script content to a temporary file
        suffix = ".sh" if interpreter in ("bash", "sh", "zsh") else ".tmp"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=suffix, delete=False, encoding="utf-8"
        ) as f:
            script_path = f.name
            f.write(content)

        try:
            proc = await asyncio.create_subprocess_exec(
                interpreter,
                script_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
            except TimeoutError:
                proc.kill()
                await proc.wait()
                raise TimeoutError(f"Script timed out after {timeout} seconds") from None

            return {
                "stdout": stdout_bytes.decode("utf-8", errors="replace"),
                "stderr": stderr_bytes.decode("utf-8", errors="replace"),
                "returncode": proc.returncode or 0,
                "timed_out": False,
            }
        finally:
            import os as os_mod

            try:
                os_mod.unlink(script_path)
            except OSError:
                pass
