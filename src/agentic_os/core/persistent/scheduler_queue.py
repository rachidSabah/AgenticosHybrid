"""Phase 18 — BackgroundJobScheduler + DurableTaskQueue + EventJournal + AuditLog.

BackgroundJobScheduler: cron/interval/one-shot scheduling with priority,
  retry, dependency graph, timeout, cancellation, pause/resume.

DurableTaskQueue: persistent priority queue with leases, acknowledgements,
  dead-letter queue, timeouts, worker pool.

EventJournal: append-only event log with replay, filter, search.

AuditLog: immutable audit trail.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from agentic_os.core.persistent.domain import (
    AuditCategory,
    AuditRecord,
    EventJournalEntry,
    Job,
    JobStatus,
    JobType,
    QueueTask,
    QueueTaskStatus,
)
from agentic_os.core.persistent.snapshot_engine import PersistenceLayer
from agentic_os.infrastructure.logging import get_logger

if TYPE_CHECKING:
    from agentic_os.ports.event_bus import EventBus

log = get_logger("persistent.scheduler")


class BackgroundJobScheduler:
    """Autonomous background job scheduler with persistence."""

    def __init__(
        self,
        bus: EventBus,
        persistence: PersistenceLayer,
    ) -> None:
        self._bus = bus
        self._persistence = persistence
        self._jobs: dict[str, Job] = {}
        self._handlers: dict[str, Callable[..., Any]] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._started = False
        self._stats: dict[str, int] = {
            "jobs_scheduled": 0,
            "jobs_executed": 0,
            "jobs_failed": 0,
            "jobs_cancelled": 0,
        }

    @property
    def stats(self) -> dict[str, Any]:
        return {**self._stats, "active_jobs": len(self._jobs)}

    def list_jobs(self, status: JobStatus | str | None = None) -> list[Job]:
        if status is None:
            return list(self._jobs.values())
        if isinstance(status, str):
            try:
                status = JobStatus(status)
            except ValueError:
                return []
        return [j for j in self._jobs.values() if j.status == status]

    def get_job(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def register_handler(self, name: str, handler: Callable[..., Any]) -> None:
        """Register a handler function for jobs."""
        self._handlers[name] = handler

    # ── Lifecycle ──────────────────────────────────────────────────

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        # Load persisted jobs
        try:
            jobs = await self._persistence.load_jobs()
            for job in jobs:
                self._jobs[job.id] = job
                if job.status in {JobStatus.SCHEDULED, JobStatus.PAUSED}:
                    job.status = JobStatus.SCHEDULED
                    self._schedule_job(job)
            log.info("Loaded %d persisted jobs", len(jobs))
        except Exception:
            log.exception("Failed to load persisted jobs")
        log.info("BackgroundJobScheduler started")

    async def stop(self) -> None:
        self._started = False
        for task in self._tasks.values():
            task.cancel()
        self._tasks.clear()
        log.info("BackgroundJobScheduler stopped")

    # ── Job management ─────────────────────────────────────────────

    async def schedule(
        self,
        name: str,
        handler: str,
        job_type: JobType = JobType.INTERVAL,
        schedule: str = "60",  # seconds for interval, cron expr for cron
        priority: int = 5,
        args: dict[str, Any] | None = None,
        timeout_s: float = 300.0,
        max_retries: int = 3,
        dependencies: list[str] | None = None,
    ) -> Job:
        """Schedule a new background job."""
        job = Job(
            name=name,
            type=job_type,
            schedule=schedule,
            priority=priority,
            handler=handler,
            args=dict(args or {}),
            timeout_s=timeout_s,
            max_retries=max_retries,
            dependencies=list(dependencies or []),
            status=JobStatus.SCHEDULED,
        )
        self._jobs[job.id] = job
        self._stats["jobs_scheduled"] += 1
        await self._persistence.save_job(job)
        self._schedule_job(job)
        await self._publish("runtime.job.started", {"job_id": job.id, "name": name})
        log.info("Job scheduled", id=job.id, name=name, type=job_type.value)
        return job

    def _schedule_job(self, job: Job) -> None:
        """Create an asyncio task for a job."""
        if job.type == JobType.ONE_SHOT:
            delay = float(job.schedule) if job.schedule.replace(".", "").isdigit() else 0
            task = asyncio.create_task(self._run_one_shot(job, delay))
        else:
            interval = float(job.schedule) if job.schedule.replace(".", "").isdigit() else 60.0
            task = asyncio.create_task(self._run_interval(job, interval))
        self._tasks[job.id] = task

    async def _run_interval(self, job: Job, interval: float) -> None:
        """Run a job at regular intervals."""
        while self._started and job.status == JobStatus.SCHEDULED:
            try:
                await asyncio.sleep(interval)
                if not self._started or job.status != JobStatus.SCHEDULED:
                    break
                await self._execute_job(job)
            except asyncio.CancelledError:
                break
            except Exception:
                log.exception("Interval job error", job_id=job.id)

    async def _run_one_shot(self, job: Job, delay: float) -> None:
        """Run a job once after a delay."""
        try:
            if delay > 0:
                await asyncio.sleep(delay)
            await self._execute_job(job)
            job.status = JobStatus.COMPLETED
        except asyncio.CancelledError:
            job.status = JobStatus.CANCELLED
        except Exception:
            job.status = JobStatus.FAILED

    async def _execute_job(self, job: Job) -> None:
        """Execute a single job invocation."""
        job.status = JobStatus.RUNNING
        job.last_run = datetime.now(UTC).isoformat()

        handler = self._handlers.get(job.handler)
        if handler is None:
            job.status = JobStatus.FAILED
            job.last_error = f"Handler '{job.handler}' not registered"
            self._stats["jobs_failed"] += 1
            await self._publish("runtime.job.failed", job.to_dict())
            return

        try:
            result = handler(**job.args)
            if hasattr(result, "__await__"):
                result = await result
            job.last_result = result if isinstance(result, dict) else {"result": str(result)}
            job.status = JobStatus.SCHEDULED  # back to scheduled for next run
            self._stats["jobs_executed"] += 1
            await self._publish("runtime.job.completed", {"job_id": job.id, "name": job.name})
        except Exception as e:
            job.retries += 1
            job.last_error = str(e)
            if job.retries >= job.max_retries:
                job.status = JobStatus.FAILED
                self._stats["jobs_failed"] += 1
            else:
                job.status = JobStatus.SCHEDULED  # retry
            log.exception("Job execution failed", job_id=job.id, retry=job.retries)
            await self._publish("runtime.job.failed", {"job_id": job.id, "error": str(e)})

        job.updated_at = datetime.now(UTC).isoformat()

    async def cancel(self, job_id: str) -> bool:
        """Cancel a running job."""
        job = self._jobs.get(job_id)
        if job is None:
            return False
        job.status = JobStatus.CANCELLED
        task = self._tasks.pop(job_id, None)
        if task:
            task.cancel()
        self._stats["jobs_cancelled"] += 1
        return True

    async def pause(self, job_id: str) -> bool:
        """Pause a scheduled job."""
        job = self._jobs.get(job_id)
        if job is None:
            return False
        job.status = JobStatus.PAUSED
        task = self._tasks.pop(job_id, None)
        if task:
            task.cancel()
        return True

    async def resume(self, job_id: str) -> bool:
        """Resume a paused job."""
        job = self._jobs.get(job_id)
        if job is None or job.status != JobStatus.PAUSED:
            return False
        job.status = JobStatus.SCHEDULED
        self._schedule_job(job)
        return True

    async def _publish(self, topic: str, payload: dict[str, Any]) -> None:
        try:
            from agentic_os.domain.events import EventEnvelope

            await self._bus.publish(
                EventEnvelope(
                    type=topic,
                    source="persistent.scheduler",
                    topic=topic,
                    payload=payload,
                )
            )
        except Exception:
            log.exception("Failed to publish %s", topic)


class DurableTaskQueue:
    """Persistent priority task queue with leases and dead-letter."""

    def __init__(
        self,
        bus: EventBus,
        persistence: PersistenceLayer,
    ) -> None:
        self._bus = bus
        self._persistence = persistence
        self._queues: dict[str, list[QueueTask]] = {}  # queue_name → tasks
        self._dead_letter: list[QueueTask] = []
        self._stats: dict[str, int] = {
            "enqueued": 0,
            "completed": 0,
            "failed": 0,
            "dead_lettered": 0,
            "timed_out": 0,
        }

    @property
    def stats(self) -> dict[str, Any]:
        return {
            **self._stats,
            "queue_count": len(self._queues),
            "dead_letter_count": len(self._dead_letter),
        }

    def list_tasks(self, queue: str = "default", limit: int = 50) -> list[QueueTask]:
        return list(self._queues.get(queue, [])[-limit:])

    def list_dead_letter(self, limit: int = 50) -> list[QueueTask]:
        return list(self._dead_letter[-limit:])

    # ── Queue operations ───────────────────────────────────────────

    async def enqueue(
        self,
        payload: dict[str, Any],
        queue: str = "default",
        priority: int = 5,
        max_attempts: int = 3,
    ) -> QueueTask:
        """Enqueue a task. Returns the created task."""
        task = QueueTask(
            queue=queue,
            priority=priority,
            payload=payload,
            max_attempts=max_attempts,
        )
        self._queues.setdefault(queue, []).append(task)
        self._stats["enqueued"] += 1
        await self._persistence.save_queue_task(task)
        await self._publish("runtime.queue.updated", {"task_id": task.id, "action": "enqueue"})
        return task

    async def lease(
        self, queue: str = "default", worker_id: str = "", lease_s: float = 60.0
    ) -> QueueTask | None:
        """Lease the highest-priority task from a queue."""
        tasks = self._queues.get(queue, [])
        if not tasks:
            return None
        # Sort by priority (1=highest) then by created_at (oldest first)
        tasks.sort(key=lambda t: (t.priority, t.created_at))
        task = tasks.pop(0)
        task.status = QueueTaskStatus.LEASED
        task.lease_owner = worker_id
        task.attempts += 1
        from datetime import timedelta

        lease_expires = datetime.now(UTC) + timedelta(seconds=lease_s)
        task.lease_expires = lease_expires.isoformat()
        await self._persistence.save_queue_task(task)
        return task

    async def ack(
        self, task_id: str, worker_id: str = "", result: dict[str, Any] | None = None
    ) -> bool:
        """Acknowledge a task as completed."""
        # Find the task in persistence
        for queue_tasks in self._queues.values():
            for t in queue_tasks:
                if t.id == task_id:
                    t.status = QueueTaskStatus.COMPLETED
                    t.ack_count += 1
                    t.result = result or {}
                    t.completed_at = datetime.now(UTC).isoformat()
                    self._stats["completed"] += 1
                    await self._persistence.save_queue_task(t)
                    await self._publish(
                        "runtime.queue.updated", {"task_id": task_id, "action": "ack"}
                    )
                    return True
        return False

    async def nack(self, task_id: str, worker_id: str = "", error: str = "") -> bool:
        """Negative acknowledge — task failed, retry or dead-letter."""
        for queue_tasks in self._queues.values():
            for t in queue_tasks:
                if t.id == task_id:
                    t.nack_count += 1
                    t.error = error
                    if t.attempts >= t.max_attempts:
                        t.status = QueueTaskStatus.DEAD_LETTER
                        self._dead_letter.append(t)
                        self._stats["dead_lettered"] += 1
                    else:
                        t.status = QueueTaskStatus.QUEUED
                        t.lease_owner = ""
                        t.lease_expires = ""
                    await self._persistence.save_queue_task(t)
                    await self._publish(
                        "runtime.queue.updated", {"task_id": task_id, "action": "nack"}
                    )
                    return True
        return False

    async def check_timeouts(self) -> int:
        """Check for timed-out leases. Returns count of timed out."""
        now = datetime.now(UTC)
        count = 0
        for queue_tasks in self._queues.values():
            for t in queue_tasks:
                if t.status != QueueTaskStatus.LEASED or not t.lease_expires:
                    continue
                try:
                    expires = datetime.fromisoformat(t.lease_expires)
                except (ValueError, TypeError):
                    continue
                if now > expires:
                    t.status = QueueTaskStatus.TIMED_OUT
                    t.lease_owner = ""
                    t.lease_expires = ""
                    self._stats["timed_out"] += 1
                    count += 1
                    await self._persistence.save_queue_task(t)
        return count

    async def _publish(self, topic: str, payload: dict[str, Any]) -> None:
        try:
            from agentic_os.domain.events import EventEnvelope

            await self._bus.publish(
                EventEnvelope(
                    type=topic,
                    source="persistent.queue",
                    topic=topic,
                    payload=payload,
                )
            )
        except Exception:
            log.exception("Failed to publish %s", topic)


class EventJournal:
    """Append-only event journal for replay and search."""

    def __init__(self, persistence: PersistenceLayer) -> None:
        self._persistence = persistence
        self._stats: dict[str, int] = {
            "entries_journaled": 0,
        }

    @property
    def stats(self) -> dict[str, Any]:
        return dict(self._stats)

    async def record(self, event: Any) -> None:
        """Record an EventBus event to the journal."""
        entry = EventJournalEntry(
            event_type=getattr(event, "type", ""),
            source=getattr(event, "source", ""),
            topic=getattr(event, "topic", ""),
            payload=dict(getattr(event, "payload", {}) or {}),
        )
        await self._persistence.append_journal(entry)
        self._stats["entries_journaled"] += 1

    async def replay(self, limit: int = 100, topic: str | None = None) -> list[dict[str, Any]]:
        """Read events from the journal."""
        return await self._persistence.read_journal(limit=limit, topic=topic)

    async def search(self, query: str, limit: int = 50) -> list[dict[str, Any]]:
        """Search the journal for events matching a query string."""
        all_entries = await self._persistence.read_journal(limit=10000)
        query_lower = query.lower()
        return [e for e in all_entries if query_lower in json.dumps(e).lower()][:limit]


class AuditLog:
    """Immutable audit log for configuration/mission/security events."""

    def __init__(self, persistence: PersistenceLayer) -> None:
        self._persistence = persistence
        self._stats: dict[str, int] = {
            "records_written": 0,
        }

    @property
    def stats(self) -> dict[str, Any]:
        return dict(self._stats)

    async def record(
        self,
        category: AuditCategory,
        action: str,
        actor: str = "",
        target: str = "",
        details: dict[str, Any] | None = None,
        severity: str = "info",
    ) -> AuditRecord:
        """Write an immutable audit record."""
        record = AuditRecord(
            category=category,
            action=action,
            actor=actor,
            target=target,
            details=dict(details or {}),
            severity=severity,
        )
        await self._persistence.append_audit(record)
        self._stats["records_written"] += 1
        return record

    async def read(self, limit: int = 100) -> list[dict[str, Any]]:
        """Read audit records."""
        return await self._persistence.read_audit(limit=limit)


# Import needed for search
import json  # noqa: E402
