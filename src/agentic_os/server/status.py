"""Kernel status metrics collector — real-time CPU, RAM, coroutines, queue depth."""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Any

from agentic_os.server.daemon import kernel_daemon


def _get_system_memory() -> dict[str, float]:
    """Retrieve memory usage in MB."""
    try:
        import psutil

        mem = psutil.virtual_memory()
        proc = psutil.Process(os.getpid())
        return {
            "process_rss_mb": round(proc.memory_info().rss / (1024 * 1024), 2),
            "total_system_mb": round(mem.total / (1024 * 1024), 2),
            "available_system_mb": round(mem.available / (1024 * 1024), 2),
            "percent_used": mem.percent,
        }
    except ImportError:
        # psutil not installed: NO invented values (was 42.5/16384/50.0).
        return {
            "process_rss_mb": 0.0,
            "total_system_mb": 0.0,
            "available_system_mb": 0.0,
            "percent_used": 0.0,
        }


def _get_cpu_usage() -> float:
    """Retrieve CPU usage percent. 0.0 (not a fake 5%) when unavailable."""
    try:
        import psutil

        return float(psutil.cpu_percent(interval=None))
    except Exception:
        return 0.0


def collect_kernel_status(platform: Any | None = None) -> dict[str, Any]:
    """Return real-time kernel status dictionary."""
    loop = asyncio.get_event_loop()
    all_tasks = [t for t in asyncio.all_tasks(loop) if not t.done()]
    active_coroutines = len(all_tasks)

    queue_depth = 0
    if platform and hasattr(platform, "scheduler"):
        queue = getattr(platform.scheduler, "_queue", None) or getattr(
            platform.scheduler, "queue", None
        )
        if queue and hasattr(queue, "qsize"):
            queue_depth = queue.qsize()
        elif queue and hasattr(queue, "__len__"):
            queue_depth = len(queue)

    mem_stats = _get_system_memory()
    cpu_percent = _get_cpu_usage()

    return {
        "status": "online",
        "uptime_sec": kernel_daemon.uptime_sec,
        "platform": sys.platform,
        "python_version": sys.version.split()[0],
        "active_coroutines": active_coroutines,
        "task_queue_depth": queue_depth,
        "cpu_percent": cpu_percent,
        "memory": mem_stats,
        "child_processes_count": len(kernel_daemon._child_pids),
    }
