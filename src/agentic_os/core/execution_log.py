"""Execution Record — persistent, queryable record of every CLI execution."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from agentic_os.domain.events import EventEnvelope
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.event_bus import EventBus

log = get_logger("core.execution_log")


@dataclass
class ExecutionRecord:
    execution_id: str = field(default_factory=lambda: uuid4().hex)
    mission_id: str = ""
    task_id: str = ""
    agent_id: str = ""
    provider: str = ""
    runtime: str = ""
    strategy: str = ""
    status: str = "running"
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None
    duration_ms: int = 0
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    retry_count: int = 0
    error: str = ""
    command: str = ""
    prompt_preview: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "mission_id": self.mission_id,
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "provider": self.provider,
            "runtime": self.runtime,
            "strategy": self.strategy,
            "status": self.status,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "duration_ms": self.duration_ms,
            "stdout": self.stdout[:2000],
            "stderr": self.stderr[:2000],
            "exit_code": self.exit_code,
            "retry_count": self.retry_count,
            "error": self.error,
            "command": self.command,
            "prompt_preview": self.prompt_preview,
        }

    def finish(
        self,
        status: str,
        stdout: str = "",
        stderr: str = "",
        exit_code: int | None = None,
        error: str = "",
    ) -> None:
        self.status = status
        self.finished_at = datetime.now(UTC)
        delta = self.finished_at - self.started_at
        self.duration_ms = int(delta.total_seconds() * 1000)
        self.stdout = stdout
        self.stderr = stderr
        self.exit_code = exit_code
        self.error = error


class ExecutionLog:
    def __init__(self, bus: EventBus | None = None, max_records: int = 1000) -> None:
        self._bus = bus
        self._records: deque[ExecutionRecord] = deque(maxlen=max_records)
        self._by_id: dict[str, ExecutionRecord] = {}
        self._by_task: dict[str, list[str]] = {}
        self._by_mission: dict[str, list[str]] = {}

    def start(
        self,
        task_id: str,
        agent_id: str,
        provider: str,
        runtime: str,
        strategy: str,
        mission_id: str = "",
        command: str = "",
        prompt_preview: str = "",
        retry_count: int = 0,
    ) -> ExecutionRecord:
        rec = ExecutionRecord(
            mission_id=mission_id,
            task_id=task_id,
            agent_id=agent_id,
            provider=provider,
            runtime=runtime,
            strategy=strategy,
            command=command,
            prompt_preview=prompt_preview[:500],
            retry_count=retry_count,
        )
        self._records.append(rec)
        self._by_id[rec.execution_id] = rec
        self._by_task.setdefault(task_id, []).append(rec.execution_id)
        if mission_id:
            self._by_mission.setdefault(mission_id, []).append(rec.execution_id)
        if self._bus is not None:
            try:
                import asyncio

                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.ensure_future(
                        self._bus.publish(
                            EventEnvelope(
                                type="execution.started",
                                source="execution_log",
                                topic="execution.started",
                                payload=rec.to_dict(),
                            )
                        )
                    )
            except Exception:
                pass
        log.info(
            "execution.started",
            execution_id=rec.execution_id,
            task=task_id,
            provider=provider,
            retry_count=retry_count,
        )
        return rec

    def finish(self, execution_id: str, status: str, **kwargs) -> ExecutionRecord | None:
        rec = self._by_id.get(execution_id)
        if rec is None:
            return None
        rec.finish(status, **kwargs)
        if self._bus is not None:
            try:
                import asyncio

                loop = asyncio.get_event_loop()
                if loop.is_running():
                    topic = "execution.completed" if status == "completed" else "execution.failed"
                    asyncio.ensure_future(
                        self._bus.publish(
                            EventEnvelope(
                                type=topic,
                                source="execution_log",
                                topic=topic,
                                payload=rec.to_dict(),
                            )
                        )
                    )
            except Exception:
                pass
        log.info(
            "execution.finished",
            execution_id=rec.execution_id,
            task=rec.task_id,
            status=status,
            duration_ms=rec.duration_ms,
        )
        return rec

    def get(self, execution_id: str) -> ExecutionRecord | None:
        return self._by_id.get(execution_id)

    def list_all(self, limit: int = 100) -> list[ExecutionRecord]:
        return list(reversed(self._records))[:limit]

    def for_task(self, task_id: str) -> list[ExecutionRecord]:
        ids = self._by_task.get(task_id, [])
        return list(reversed([self._by_id[i] for i in ids if i in self._by_id]))

    def for_mission(self, mission_id: str) -> list[ExecutionRecord]:
        ids = self._by_mission.get(mission_id, [])
        return list(reversed([self._by_id[i] for i in ids if i in self._by_id]))

    def for_provider(self, provider: str, limit: int = 50) -> list[ExecutionRecord]:
        return [r for r in reversed(self._records) if r.provider == provider][:limit]

    def by_status(self, status: str, limit: int = 50) -> list[ExecutionRecord]:
        return [r for r in reversed(self._records) if r.status == status][:limit]

    def stats(self) -> dict[str, int]:
        counts: dict[str, int] = {"total": len(self._records)}
        for r in self._records:
            counts[r.status] = counts.get(r.status, 0) + 1
        return counts


__all__ = ["ExecutionRecord", "ExecutionLog"]
