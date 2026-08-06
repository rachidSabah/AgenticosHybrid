"""Mock provider adapter — offline, deterministic, zero network.

Used for local dev, tests, and CI. Simulates work and can be told to fail via
a task title keyword (``fail``) so the recovery path is exercisable end-to-end.

**Important**: When used as a fallback (no real providers available), mock
execution **marks the task as failed** with reason ``mock_fallback`` so
fake completion can never be mistaken for real work. This prevents missions
from showing "completed" while zero files are written to the workspace.

For tests that explicitly register MockProvider as the only provider, set
``fallback_mode=False`` (default) to allow normal mock completion.
"""

from __future__ import annotations

import anyio

from agentic_os.domain.agent import Agent, ProviderInfo, Task
from agentic_os.infrastructure.logging import get_logger

log = get_logger("provider.mock")


class MockProvider:
    def __init__(
        self,
        name: str = "mock",
        kind: str = "mock",
        *,
        fallback_mode: bool = False,
    ) -> None:
        self.info = ProviderInfo(
            name=name, kind=kind, supports_streaming=False, supports_tools=False
        )
        self._fallback_mode = fallback_mode

    async def execute(
        self,
        agent: Agent,
        task: Task,
        on_output=None,
        cwd: str | None = None,
    ) -> str:
        if self._fallback_mode:
            log.warning(
                "mock.fallback_execute",
                agent=agent.id,
                task=task.id,
                title=task.title,
                reason="mock_fallback",
                message=(
                    "No real providers available — task will be marked "
                    "failed to prevent false completion"
                ),
            )
            await anyio.sleep(0.2)
            if "fail" in task.title.lower():
                raise RuntimeError("mock provider forced failure for recovery demo")
            raise RuntimeError(
                "mock_fallback: no real providers available — task cannot complete. "
                "Configure at least one real provider (hermes, claude, opencode, etc.) "
                "to execute tasks."
            )

        # Normal mock mode (for tests/dev) — simulates successful completion
        log.info("mock.execute", agent=agent.id, task=task.id, title=task.title)
        await anyio.sleep(0.2)  # simulate work
        if "fail" in task.title.lower():
            raise RuntimeError("mock provider forced failure for recovery demo")
        return f"[mock:{agent.role}] completed task '{task.title}'"

    async def healthcheck(self) -> bool:
        return True
