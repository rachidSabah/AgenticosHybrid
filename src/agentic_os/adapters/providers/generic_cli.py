"""Generic CLI provider adapter.

Works with any AI agent CLI that accepts a prompt via stdin or as the
last positional argument. Unlike ClaudeCodeProvider which uses
Claude-specific flags (-p, --output-format text), this adapter uses
a simple subprocess call that works across different CLIs.

For CLIs that read from stdin: pipes the prompt via stdin.
For CLIs that take a prompt argument: passes it as the last arg.
"""

from __future__ import annotations

import os
import shutil

from agentic_os.adapters.providers.run_cli import run_cli
from agentic_os.domain.agent import Agent, ProviderInfo, Task
from agentic_os.infrastructure.logging import get_logger

log = get_logger("provider.generic_cli")

_DEFAULT_TIMEOUT = 120.0


class GenericCLIProvider:
    """Generic CLI adapter that works with any AI agent binary.

    Supports two modes:
      - stdin_mode=True: pipes prompt via stdin (default, most compatible)
      - stdin_mode=False: passes prompt as last positional argument

    The adapter auto-detects which mode to use based on the provider kind.
    """

    def __init__(
        self,
        bin_path: str = "",
        name: str = "",
        kind: str = "generic",
        display_name: str = "",
        capabilities: list[str] | None = None,
        stdin_mode: bool = True,
        extra_args: list[str] | None = None,
    ) -> None:
        self._bin = bin_path
        self._stdin_mode = stdin_mode
        self._extra_args = extra_args or []
        self.info = ProviderInfo(
            name=name or f"auto:{bin_path}",
            kind=kind,
            supports_streaming=True,
            supports_tools=True,
        )
        self._display_name = display_name or bin_path
        self._capabilities = capabilities or ["coding", "reasoning"]

    async def execute(
        self, agent: Agent, task: Task, on_output=None, cwd: str | None = None
    ) -> str:
        """Execute a task by invoking the CLI binary."""
        resolved_bin = shutil.which(self._bin) or self._bin
        if not shutil.which(resolved_bin):
            raise RuntimeError(
                f"CLI binary '{self._bin}' not found on PATH. Resolved: {resolved_bin}"
            )

        from agentic_os.adapters.providers.strategies import GenericExecutionStrategy

        strategy = GenericExecutionStrategy()
        prompt = strategy.build_prompt(task)
        env = dict(os.environ)

        log.info(
            "generic_cli.execute",
            binary=self._bin,
            agent=agent.id,
            task=task.id,
            stdin_mode=self._stdin_mode,
            prompt_len=len(prompt),
        )

        if self._stdin_mode:
            args = [resolved_bin] + self._extra_args
            stdin_data = prompt.encode("utf-8")
        else:
            args = [resolved_bin] + self._extra_args + [prompt]
            stdin_data = None

        rc, stdout_str, stderr_str = await run_cli(
            args,
            input_data=stdin_data,
            env=env,
            cwd=cwd,
            timeout=_DEFAULT_TIMEOUT,
            on_output=on_output,
        )

        if rc == -999:
            raise RuntimeError(f"{self._bin} timed out after {_DEFAULT_TIMEOUT}s")
        if rc != 0:
            raise RuntimeError(f"{self._bin} exited {rc}: {stderr_str[:200]}")

        return stdout_str.strip() or f"[{self._bin}] completed '{task.title}'"

    async def healthcheck(self) -> bool:
        return shutil.which(self._bin) is not None
