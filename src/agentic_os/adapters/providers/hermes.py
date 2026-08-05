"""Hermes Agent provider adapter.

Drives the real ``hermes`` CLI as a subprocess. Hermes is assumed to be
installed globally (pip install hermes) or available on PATH. The adapter
shells out for task execution so the Supervisor/Recovery layer can wrap it.

For API-based usage (Hermes HTTP API), users configure via the openai_compatible
adapter with base_url pointing at the Hermes API endpoint.
"""

from __future__ import annotations

import os
import shutil

from agentic_os.adapters.providers.run_cli import run_cli
from agentic_os.domain.agent import Agent, ProviderInfo, Task
from agentic_os.infrastructure.logging import get_logger

log = get_logger("provider.hermes")


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
        timeout: float = 300.0,
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
        prompt = f"{task.title}\n\n{task.description}".strip()
        env = dict(os.environ)
        if self._api_key:
            env["HERMES_CONFIG"] = self._api_key
        log.info("hermes.execute", agent=agent.id, task=task.id)
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
            raise RuntimeError(f"hermes exited {returncode}: {stderr.decode().strip()}")
        return stdout.decode().strip() or f"[hermes] completed '{task.title}'"

    async def healthcheck(self) -> bool:
        return shutil.which(self._bin) is not None
