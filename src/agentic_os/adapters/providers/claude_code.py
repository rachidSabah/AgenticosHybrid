"""Claude Code provider adapter.

Drives the real ``claude`` CLI as a subprocess, piping the task prompt
via **stdin** (not argv) to avoid the Windows ``cmd.exe`` 8191-char
command line limit.

Side-effect-isolated: it only shells out, parses output, and raises on
non-zero exit so the Supervisor/Recovery layer can react.
"""

from __future__ import annotations

import os
import shutil

from agentic_os.adapters.providers.run_cli import run_cli
from agentic_os.domain.agent import Agent, ProviderInfo, Task
from agentic_os.infrastructure.logging import get_logger

log = get_logger("provider.claude_code")


class ClaudeCodeProvider:
    def __init__(
        self,
        bin_path: str = "claude",
        api_key: str = "",
        name: str = "claude_code",
        timeout: float = 300.0,
    ) -> None:
        self._bin = bin_path
        self._api_key = api_key
        self._timeout = timeout
        self.info = ProviderInfo(
            name=name, kind="claude_code", supports_streaming=True, supports_tools=True
        )

    async def execute(
        self, agent: Agent, task: Task, on_output=None, cwd: str | None = None
    ) -> str:
        if not shutil.which(self._bin):
            raise RuntimeError(f"claude CLI not found at '{self._bin}'")

        from agentic_os.adapters.providers.strategies import ClaudeExecutionStrategy

        strategy = ClaudeExecutionStrategy()
        prompt = strategy.build_prompt(task)
        # Build env — inject API key only if configured, never log it
        env = dict(os.environ)
        if self._api_key:
            env["ANTHROPIC_API_KEY"] = self._api_key

        log.info("claude_code.execute", agent=agent.id, task=task.id, has_stdin=True)

        # claude -p --output-format text --dangerously-skip-permissions  (prompt goes via stdin)
        rc, stdout_str, stderr_str = await run_cli(
            [self._bin, "-p", "--output-format", "text", "--dangerously-skip-permissions"],
            input_data=prompt.encode("utf-8"),
            env=env,
            cwd=cwd,
            timeout=self._timeout,
            on_output=on_output,
        )

        if rc == -999:
            raise RuntimeError(f"{self._bin} timed out after {self._timeout}s") from None
        if rc != 0:
            raise RuntimeError(f"claude exited {rc}: {stderr_str.strip()}")

        return stdout_str.strip() or f"[claude_code] completed '{task.title}'"

    async def healthcheck(self) -> bool:
        if not shutil.which(self._bin):
            return False
        # If user configured a custom proxy in ~/.claude/settings.json, verify it is reachable
        try:
            import json
            import pathlib
            import socket
            import urllib.parse

            settings_file = pathlib.Path.home() / ".claude" / "settings.json"
            if settings_file.is_file():
                data = json.loads(settings_file.read_text(encoding="utf-8"))
                base_url = data.get("apiBaseUrl") or (data.get("env", {}).get("ANTHROPIC_BASE_URL"))
                if base_url:
                    parsed = urllib.parse.urlparse(base_url)
                    host = parsed.hostname or "127.0.0.1"
                    port = parsed.port or (443 if parsed.scheme == "https" else 80)
                    with socket.create_connection((host, port), timeout=0.5):
                        pass
        except Exception:
            return False
        return True
