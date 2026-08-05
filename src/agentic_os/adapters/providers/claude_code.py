"""Claude Code provider adapter.

Drives the real ``claude`` CLI as a subprocess, piping the task as a prompt.
This is the first-class integration called out in the product brief. The adapter
is side-effect-isolated: it only shells out, parses output, and raises on
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
        prompt = f"{task.title}\n\n{task.description}".strip()
        env = dict(os.environ)
        if self._api_key:
            env["ANTHROPIC_API_KEY"] = self._api_key
        log.info("claude_code.execute", agent=agent.id, task=task.id)
        try:
            returncode, stdout, stderr = await run_cli(
                [self._bin, "-p", prompt, "--output-format", "text"],
                env=env,
                timeout=self._timeout,
                on_output=on_output,
            )
        except TimeoutError:
            raise TimeoutError(f"{self._bin} timed out after {self._timeout}s") from None
        if returncode != 0:
            raise RuntimeError(f"claude exited {returncode}: {stderr.decode().strip()}")
        return stdout.decode().strip() or f"[claude_code] completed '{task.title}'"

    async def healthcheck(self) -> bool:
        return shutil.which(self._bin) is not None
