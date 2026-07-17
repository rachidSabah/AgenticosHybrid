"""Ports: Capability Engine.

Replaces fixed agent roles with composable capabilities. A Capability is a
unit of competence (reasoning, coding, planning, …) that can be independently
implemented, tested, and composed into an Agent at runtime. The engine owns a
registry of capabilities and composes Agent specifications on demand.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from agentic_os.domain.agent import Agent, Task
from agentic_os.domain.capability import AgentSpec


class CapabilityResult:
    """Outcome of exercising a capability on a task."""

    def __init__(self, ok: bool, output: str = "", meta: dict | None = None) -> None:
        self.ok = ok
        self.output = output
        self.meta = meta or {}


@runtime_checkable
class Capability(Protocol):
    """A composable unit of agent competence."""

    name: str
    description: str = ""
    requires_approval: bool = False  # sensitive capabilities need an approval gate

    async def run(self, agent: Agent, task: Task, context: dict) -> CapabilityResult:
        """Execute this capability for ``agent`` against ``task``."""
        ...


@runtime_checkable
class CapabilityRegistry(Protocol):
    """Holds the catalog of available capabilities."""

    def register(self, capability: Capability) -> None: ...

    def get(self, name: str) -> Capability | None: ...

    def all(self) -> list[Capability]: ...

    def names(self) -> list[str]: ...


@runtime_checkable
class AgentComposer(Protocol):
    """Composes agents dynamically from a set of capabilities + provider/model."""

    def compose(
        self, name: str, capabilities: list[str], provider: str, model: str
    ) -> AgentSpec: ...

    def spec_for_task(self, task: Task) -> AgentSpec: ...
