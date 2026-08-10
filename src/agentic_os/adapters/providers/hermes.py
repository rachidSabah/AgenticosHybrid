"""Hermes Agent provider adapter.

Drives the real ``hermes`` CLI as a subprocess. Hermes is assumed to be
installed globally (pip install hermes) or available on PATH.

The real hermes CLI contract is ``-z PROMPT`` — it has **no**
``--output-format`` flag; passing one makes it exit 2 with a usage error.
Timeout is 600s — real agent runs with workspace context + tool calls
routinely exceed 120s.
"""

from __future__ import annotations

import os
import shutil

from agentic_os.adapters.providers.run_cli import run_cli
from agentic_os.domain.agent import Agent, ProviderInfo, Task
from agentic_os.infrastructure.logging import get_logger

log = get_logger("provider.hermes")

_DEFAULT_TIMEOUT = 600.0


class HermesProvider:
    """Provider adapter for the Hermes CLI agent.

    Discovers the Hermes binary on PATH at construction time. Falls back
    gracefully when the binary is missing (healthcheck returns False).
    """

    def __init__(
        self,
        bin_path: str = "hermes",
        api_key: str = "",
        name: str = "hermes",
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        self._bin = bin_path
        self._api_key = api_key
        self._timeout = timeout
        self.info = ProviderInfo(
            name=name,
            kind="hermes",
            supports_streaming=True,
            supports_tools=True,
        )

    async def execute(
        self, agent: Agent, task: Task, on_output=None, cwd: str | None = None
    ) -> str:
        if not shutil.which(self._bin):
            raise RuntimeError(
                f"Hermes CLI not found at '{self._bin}'. Install with: pip install hermes-cli"
            )

        from agentic_os.adapters.providers.strategies import HermesExecutionStrategy

        strategy = HermesExecutionStrategy()
        prompt = strategy.build_prompt(task)
        # Build env — inject HERMES_CONFIG only if set, never log it
        env = dict(os.environ)
        if self._api_key:
            env["HERMES_CONFIG"] = self._api_key

        log.info("hermes.execute", agent=agent.id, task=task.id)

        # hermes -z "<prompt>" --yolo  (prompt is the -z argument value —
        # hermes oneshot reads no stdin, so piping it would send "-" instead)
        rc, stdout_str, stderr_str = await run_cli(
            [self._bin, "-z", prompt, "--yolo"],
            input_data=None,
            env=env,
            cwd=cwd,
            timeout=self._timeout,
            on_output=on_output,
        )

        if rc == -999:
            raise RuntimeError(f"{self._bin} timed out after {self._timeout}s") from None
        if rc != 0:
            raise RuntimeError(f"hermes exited {rc}: {stderr_str.strip()}")

        return stdout_str.strip() or f"[hermes] completed '{task.title}'"

    async def healthcheck(self) -> bool:
        return shutil.which(self._bin) is not None
