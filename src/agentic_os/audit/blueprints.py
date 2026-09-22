"""Architectural Blueprints — Before vs. After code comparison diffs."""

from __future__ import annotations

from typing import Any


def get_architectural_blueprints() -> list[dict[str, Any]]:
    """Return Before vs After architectural patterns and code diffs."""
    return [
        {
            "id": "event_dispatch",
            "title": "Event Dispatch Architecture",
            "subsystem": "Event Bus",
            "before": {
                "title": "Legacy: Unbounded asyncio.create_task() Storm",
                "description": "Spawned a new unbounded asyncio task for every single event subscriber, overwhelming the runtime.",
                "code": """# BEFORE: Unbounded task creation on every event
for subscriber in subscribers:
    asyncio.create_task(subscriber(event))
# Result: Task explosions, severe GC churn, memory starvation under load""",
            },
            "after": {
                "title": "Modern: Bounded FIFO Worker Pool with Backpressure",
                "description": "Dedicated pool of async workers consuming from a bounded asyncio.Queue with backpressure.",
                "code": """# AFTER: Bounded queue with dedicated async workers
await self._queue.put(event)

async def _worker():
    while True:
        event = await self._queue.get()
        await self._dispatch(event)
        self._queue.task_done()
# Result: Predictable memory ceiling, strict order, zero task explosions""",
            },
        },
        {
            "id": "dag_engine",
            "title": "DAG Pipeline Coordination",
            "subsystem": "Pipeline / Workflow Engine",
            "before": {
                "title": "Legacy: Busy-Wait Sleep & Re-Queue Loop",
                "description": "Polled ready queue, checked dependencies, slept 100ms, and re-queued unfinished stages.",
                "code": """# BEFORE: Busy-waiting on stage dependencies
while ready_queue:
    stage = ready_queue.pop(0)
    if not stage.deps_met():
        await asyncio.sleep(0.1)  # Busy wait spin!
        ready_queue.append(stage)
        continue
    await stage.run()""",
            },
            "after": {
                "title": "Modern: In-Degree Topological Decrement with TaskGroup",
                "description": "When parent completes, children in-degrees decrement. When in_degree reaches 0, child triggers immediately.",
                "code": """# AFTER: Event-driven in-degree tracking + TaskGroup
async with asyncio.TaskGroup() as tg:
    for child in stage.downstream:
        in_degrees[child] -= 1
        if in_degrees[child] == 0:
            tg.create_task(run_stage(child))
# Result: Zero artificial sleep, immediate dispatch, parallel execution""",
            },
        },
        {
            "id": "omniroute_locking",
            "title": "OmniRoute Lock Boundaries",
            "subsystem": "OmniRoute Engine",
            "before": {
                "title": "Legacy: Giant Lock Boundary with I/O Publishing",
                "description": "Held async with self._lock across external event bus publications, creating severe deadlock hazards.",
                "code": """# BEFORE: Coarse lock encompassing network/bus await
async with self._lock:
    self._update_stats()
    await self._bus.publish(route_event)  # Deadlock hazard!""",
            },
            "after": {
                "title": "Modern: Lockless O(1) Atomic Dictionary Routing",
                "description": "Evaluates policies locklessly from memory dicts and emits lifecycle events fire-and-forget.",
                "code": """# AFTER: Lockless atomic state reads and decoupled event emit
route = self._routing_table[strategy]  # Atomic O(1) read
decision_time_ms = (time.perf_counter() - t0) * 1000
asyncio.create_task(self._bus.publish(route_event))
return route  # Sub-millisecond return!""",
            },
        },
        {
            "id": "sqlite_concurrency",
            "title": "SQLite Concurrency & WAL Mode",
            "subsystem": "Storage / Database",
            "before": {
                "title": "Legacy: Default Journal Mode (Rollback Journal)",
                "description": "Single writer locked the entire database from readers, causing OperationalError: database is locked.",
                "code": """# BEFORE: Default SQLite connection
conn = sqlite3.connect(db_path)
# Result: Table locks block all concurrent readers and writers""",
            },
            "after": {
                "title": "Modern: WAL Mode with Busy Timeout",
                "description": "Enables Write-Ahead Logging for concurrent readers and serialized non-blocking writes.",
                "code": """# AFTER: WAL mode + busy timeout
conn = sqlite3.connect(db_path)
conn.execute("PRAGMA journal_mode = WAL;")
conn.execute("PRAGMA synchronous = NORMAL;")
conn.execute("PRAGMA busy_timeout = 5000;")
# Result: Non-blocking concurrent reads + robust serialized writes""",
            },
        },
        {
            "id": "process_lifecycle",
            "title": "Subprocess Lifecycle & Tree Termination",
            "subsystem": "Kernel Process Manager",
            "before": {
                "title": "Legacy: Unchecked Subprocess Execution",
                "description": "Subprocesses spawned without timeout cleanup or SIGKILL tree propagation, creating zombie processes.",
                "code": """# BEFORE: Unbounded subprocess run
proc = subprocess.run(cmd, capture_output=True)
# Result: Blocks event loop, leaves orphaned processes on crash""",
            },
            "after": {
                "title": "Modern: Non-blocking Async Subprocess with PID Tree Tracking",
                "description": "Non-blocking pipe communication, timeout enforcement with taskkill /F /T, and graceful shutdown cascade.",
                "code": """# AFTER: Async subprocess + process tree termination
proc = await asyncio.create_subprocess_exec(cmd, stdout=asyncio.subprocess.PIPE)
try:
    out, err = await asyncio.wait_for(proc.communicate(), timeout=30)
except TimeoutError:
    await kernel_daemon.kill_pid(proc.pid, force=True)  # taskkill /F /T
# Result: Non-blocking event loop + zero zombie background processes""",
            },
        },
    ]
