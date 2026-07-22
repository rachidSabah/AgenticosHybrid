"""Port: Provider Adapter.

A provider adapter turns a Task + Role into execution against some backend
(Claude Code CLI, OpenAI, Gemini, Ollama, …). Adapters are discovered by the
plugin loader and registered in the ProviderRegistry. They must be replaceable
and side-effect-isolated (ADR-0005).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from agentic_os.domain.agent import Agent, ProviderInfo, Task


@runtime_checkable
class ProviderAdapter(Protocol):
    """Executes a task on behalf of an agent via some external backend."""

    info: ProviderInfo

    async def execute(self, agent: Agent, task: Task) -> str:
        """Run ``task`` as ``agent`` and return a textual result.

        Implementations should raise on failure so the Supervisor/Recovery
        layer can observe and react.
        """
        ...

    async def healthcheck(self) -> bool:
        """Return True if the backend is reachable."""
        ...
