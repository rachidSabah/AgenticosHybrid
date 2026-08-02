"""Ports: supervision and recovery.

Kept as interfaces so the health/recovery strategy is replaceable. The default
implementation lives in ``core/``; an operator can swap in a Temporal-backed or
LLM-driven strategy without touching agents or the bus.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from agentic_os.domain.agent import Agent


@runtime_checkable
class HealthMonitor(Protocol):
    """Periodically checks agent liveness and emits health events."""

    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def register(self, agent: Agent) -> None: ...

    async def check(self, agent: Agent) -> bool:
        """Return True if the agent is considered healthy."""
        ...


@runtime_checkable
class RecoveryManager(Protocol):
    """Decides and performs recovery when an agent degrades or fails."""

    async def handle_failure(self, agent: Agent, reason: str) -> bool:
        """Attempt recovery. Return True if recovered (or recovering)."""
        ...
