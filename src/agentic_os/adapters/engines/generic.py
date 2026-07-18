"""
GenericExecutionEngine — Reference Adapter

Demonstrates the ExecutionEnginePort contract with a simple in-process engine
that executes actions locally. Use as a template for building new adapters.

This engine supports:
- In-process execution of actions
- Health checks (always healthy)
- Basic capability advertising
- Cost/latency estimation stubs
- Workspace info
"""

import asyncio
import os
import platform
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from agentic_os.core.runtime.engine import ExecutionEngineBase
from agentic_os.domain.execution import (
    EngineCapability,
    EngineStatus,
    ExecutionCapability,
    ExecutionConfiguration,
    ExecutionEngine,
    ExecutionHealth,
    ExecutionMetrics,
    ExecutionResult,
    ExecutionSession,
    ExecutionStatus,
    ExecutionWorkspace,
)
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.execution import ExecutionRequest

log = get_logger("engines.generic")


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class GenericExecutionEngine(ExecutionEngineBase):
    """
    Reference adapter for the ExecutionEnginePort.

    This is a simple in-process engine that executes actions locally. It serves
    as a template and reference implementation for building new engine adapters.
    """

    def __post_init__(self) -> None:
        """Initialize with GENERIC engine type and default capabilities."""
        super().__post_init__()
        self._capabilities = (
            ExecutionCapability(type=EngineCapability.PLANNING, confidence=0.5),
            ExecutionCapability(type=EngineCapability.CODING, confidence=0.3),
            ExecutionCapability(type=EngineCapability.FILESYSTEM, confidence=0.8),
            ExecutionCapability(type=EngineCapability.TERMINAL, confidence=0.6),
        )
        self._sessions: dict[str, ExecutionSession] = {}
        self._running_tasks: dict[str, asyncio.Task] = {}
        self._shutdown_flag = False

    async def initialize(self) -> ExecutionEngine:
        """Initialize the generic engine."""
        self._set_status(EngineStatus.INITIALIZING)
        await asyncio.sleep(0.01)  # Simulate init work

        self.descriptor = self.descriptor.with_capabilities(list(self._capabilities))
        self._set_status(EngineStatus.RUNNING)

        log.info("Generic engine initialized", name=self.name)
        return self.descriptor

    async def shutdown(self) -> None:
        """Shutdown the engine and cancel running tasks."""
        self._shutdown_flag = True
        self._set_status(EngineStatus.STOPPED)

        # Cancel running tasks
        for _task_id, task in self._running_tasks.items():
            task.cancel()
        self._running_tasks.clear()
        self._sessions.clear()

        log.info("Generic engine shutdown", name=self.name)

    async def health_check(self) -> ExecutionHealth:
        """Return health status — always healthy."""
        return ExecutionHealth.healthy(latency_ms=0.5)

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """Execute an action. For the generic engine, actions are simple operations.

        Supported actions:
        - "echo" — returns the payload back
        - "ping" — returns {"pong": True}
        - "sleep" — sleeps for payload["seconds"] seconds
        - "info" — returns system info
        - "fail" — simulates a failure (for testing)
        """
        execution_id = f"gen-{_utcnow().timestamp()}"
        session = ExecutionSession(
            engine_id=self.descriptor.id,
            request={"action": request.action, "payload": request.payload},
        )
        self._sessions[session.id] = session

        try:
            result = await self._execute_action(request.action, request.payload)
            completed = ExecutionResult(
                execution_id=execution_id,
                status=ExecutionStatus.COMPLETED,
                output=result,
                metrics=ExecutionMetrics(
                    duration_ms=0.1,
                    cpu_percent=0.0,
                    memory_mb=0.0,
                ),
            )
            self._sessions[session.id] = session.with_result(completed)
            return completed
        except Exception as exc:
            failed = ExecutionResult(
                execution_id=execution_id,
                status=ExecutionStatus.FAILED,
                error=str(exc),
            )
            self._sessions[session.id] = session.with_result(failed)
            return failed

    async def cancel(self, execution_id: str) -> bool:
        """Cancel a running execution."""
        task = self._running_tasks.get(execution_id)
        if task is not None:
            task.cancel()
            self._running_tasks.pop(execution_id, None)
            return True
        return False

    async def _execute_action(self, action: str, payload: dict[str, Any]) -> Any:
        """Execute a specific action."""
        if action == "echo":
            return payload
        elif action == "ping":
            return {"pong": True, "timestamp": _utcnow().isoformat()}
        elif action == "sleep":
            seconds = payload.get("seconds", 1)
            await asyncio.sleep(seconds)
            return {"slept": seconds}
        elif action == "info":
            return {
                "system": platform.system(),
                "hostname": platform.node(),
                "cwd": os.getcwd(),
                "python_version": platform.python_version(),
            }
        elif action == "fail":
            msg = payload.get("message", "Simulated failure")
            raise RuntimeError(msg)
        else:
            raise ValueError(f"Unknown action: {action}")

    async def get_capabilities(self) -> list[ExecutionCapability]:
        """Return advertised capabilities."""
        return list(self._capabilities)

    async def supports(self, capability: EngineCapability) -> bool:
        """Check if this engine supports a given capability."""
        return any(c.type == capability for c in self._capabilities)

    async def get_version(self) -> str:
        return "0.1.0"

    async def get_configuration(self) -> ExecutionConfiguration:
        return ExecutionConfiguration(
            engine_id=self.descriptor.id,
            settings={"supported_actions": ["echo", "ping", "sleep", "info", "fail"]},
        )

    async def get_workspace(self) -> ExecutionWorkspace:
        return ExecutionWorkspace(
            path=os.getcwd(),
            environment={"HOME": os.path.expanduser("~")},
            constraints={"platform": platform.system()},
        )

    async def estimate_cost(self, request: ExecutionRequest) -> float:
        """Estimate cost — generic engine is free."""
        return 0.0

    async def estimate_latency(self, request: ExecutionRequest) -> float:
        """Estimate latency based on action type."""
        if request.action == "sleep":
            return request.payload.get("seconds", 1) * 1000.0
        return 10.0  # 10ms for simple operations
