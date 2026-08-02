from __future__ import annotations

from collections import defaultdict
from typing import Any

from core.logging import get_logger
from services.runtime_discovery.models import RuntimeTelemetry

_log = get_logger(__name__)

__all__ = ["RuntimeTelemetryCollector"]


class RuntimeTelemetryCollector:
    def __init__(self, max_history: int = 1000) -> None:
        self._telemetry: dict[str, RuntimeTelemetry] = {}
        self._history: dict[str, list[RuntimeTelemetry]] = defaultdict(list)
        self._max_history = max_history

    async def record(self, runtime_id: str, telemetry: RuntimeTelemetry) -> None:
        self._telemetry[runtime_id] = telemetry
        history = self._history[runtime_id]
        history.append(telemetry)
        if len(history) > self._max_history:
            self._history[runtime_id] = history[-self._max_history :]

    async def get(self, runtime_id: str) -> RuntimeTelemetry | None:
        return self._telemetry.get(runtime_id)

    async def get_all(self) -> list[RuntimeTelemetry]:
        return list(self._telemetry.values())

    async def flush(self) -> None:
        self._telemetry.clear()
        self._history.clear()

    def get_history(self, runtime_id: str, limit: int = 100) -> list[RuntimeTelemetry]:
        history = self._history.get(runtime_id, [])
        return history[-limit:]

    def get_stats(self) -> dict[str, Any]:
        total_completed = sum(t.tasks_completed for t in self._telemetry.values())
        total_failed = sum(t.tasks_failed for t in self._telemetry.values())
        total_duration = sum(t.total_duration_s for t in self._telemetry.values())
        return {
            "total_runtimes": len(self._telemetry),
            "total_tasks_completed": total_completed,
            "total_tasks_failed": total_failed,
            "total_duration_s": round(total_duration, 2),
            "avg_duration_s": round(total_duration / max(1, total_completed + total_failed), 2),
        }
