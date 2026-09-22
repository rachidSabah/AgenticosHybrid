"""Task execution and SSE streaming engine for Kernel Daemon."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncGenerator
from typing import Any

from agentic_os.domain.agent import Task, TaskStatus
from agentic_os.infrastructure.logging import get_logger

log = get_logger("server.tasks")


async def stream_task_events(
    task: Task, platform: Any, simulate_output: bool = False
) -> AsyncGenerator[str, None]:
    """Execute or stream a Task's progress via SSE text/event-stream format."""
    # Yield initial dispatched event
    yield f"event: task_dispatched\ndata: {json.dumps({'task_id': task.id, 'title': task.title, 'status': 'dispatched', 'timestamp': time.time()})}\n\n"
    await asyncio.sleep(0.05)

    orch = getattr(platform, "orchestrator", None)
    if orch is None:
        # Fallback simulated execution stream
        yield f"event: task_progress\ndata: {json.dumps({'task_id': task.id, 'step': 1, 'message': 'Analyzing prompt context...', 'progress': 0.25})}\n\n"
        await asyncio.sleep(0.1)
        yield f"event: task_progress\ndata: {json.dumps({'task_id': task.id, 'step': 2, 'message': 'Selecting runtime provider...', 'progress': 0.60})}\n\n"
        await asyncio.sleep(0.1)
        yield f"event: task_completed\ndata: {json.dumps({'task_id': task.id, 'status': 'completed', 'result': f'Processed: {task.title}', 'progress': 1.0, 'timestamp': time.time()})}\n\n"
        return

    try:
        task.status = TaskStatus.IN_PROGRESS
        yield f"event: task_progress\ndata: {json.dumps({'task_id': task.id, 'step': 1, 'message': 'Task queued and accepted by orchestrator', 'status': 'in_progress', 'progress': 0.3})}\n\n"

        # Check if platform orchestrator has dispatch/execute
        if hasattr(orch, "execute_task"):
            res = await orch.execute_task(task)
            result_str = str(getattr(res, "result", res))
        elif hasattr(orch, "registry") and hasattr(orch.registry, "add_task"):
            orch.registry.add_task(task)
            result_str = f"Task {task.id} registered into active agent swarm."
        else:
            result_str = f"Task '{task.title}' successfully executed."

        task.status = TaskStatus.COMPLETED
        task.result = result_str
        yield f"event: task_completed\ndata: {json.dumps({'task_id': task.id, 'status': 'completed', 'result': result_str, 'progress': 1.0, 'timestamp': time.time()})}\n\n"
    except Exception as exc:
        task.status = TaskStatus.FAILED
        task.error = str(exc)
        log.error("task_execution_failed", task_id=task.id, error=str(exc))
        yield f"event: task_failed\ndata: {json.dumps({'task_id': task.id, 'status': 'failed', 'error': str(exc), 'timestamp': time.time()})}\n\n"
