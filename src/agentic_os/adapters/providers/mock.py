"""Mock provider adapter — offline, deterministic, zero network.

Used for local dev, tests, and CI. Simulates work and can be told to fail via
a task title keyword (``fail``) so the recovery path is exercisable end-to-end.
"""

from __future__ import annotations

import anyio

from agentic_os.domain.agent import Agent, ProviderInfo, Task
from agentic_os.infrastructure.logging import get_logger

log = get_logger("provider.mock")


class MockProvider:
    def __init__(self, name: str = "mock", kind: str = "mock") -> None:
        self.info = ProviderInfo(
            name=name, kind=kind, supports_streaming=False, supports_tools=False
        )

    async def execute(self, agent: Agent, task: Task) -> str:
        log.info("mock.execute", agent=agent.id, task=task.id, title=task.title)
        await anyio.sleep(0.2)  # simulate work
        if "fail" in task.title.lower():
            raise RuntimeError("mock provider forced failure for recovery demo")
        return f"[mock:{agent.role}] completed task '{task.title}'"

    async def healthcheck(self) -> bool:
        return True
