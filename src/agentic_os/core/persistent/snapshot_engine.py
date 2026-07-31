"""Phase 18 — SnapshotEngine + RecoveryEngine + PersistenceLayer.

SnapshotEngine: creates full/incremental system-wide snapshots of all
  platform state. Stores them as JSON files on disk with checksums.

RecoveryEngine: restores platform state from a snapshot after restart.

PersistenceLayer: file-based JSON persistence for snapshots, jobs, queue
  tasks, event journal, and audit log. All I/O is async via to_thread.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agentic_os.core.persistent.domain import (
    AuditRecord,
    EventJournalEntry,
    Job,
    QueueTask,
    RecoveryPlan,
    RecoveryStatus,
    RuntimeStatistics,
    SnapshotType,
    SystemSnapshot,
)
from agentic_os.infrastructure.logging import get_logger

if TYPE_CHECKING:
    from agentic_os.ports.event_bus import EventBus

log = get_logger("persistent.snapshot")


class PersistenceLayer:
    """File-based JSON persistence for all Phase 18 data.

    Directory layout:
      {data_dir}/
        snapshots/     — system snapshots (.json)
        jobs/          — background job definitions (.json)
        queue/         — durable task queue (.json)
        journal/       — event journal (.jsonl, append-only)
        audit/         — audit log (.jsonl, append-only)
        backups/       — backup archives (.tar.gz)
        recovery/      — recovery plans (.json)
    """

    def __init__(self, data_dir: str = "") -> None:
        self._data_dir = Path(data_dir or os.path.expanduser("~/.agentic_os/persistent"))
        self._snapshots_dir = self._data_dir / "snapshots"
        self._jobs_dir = self._data_dir / "jobs"
        self._queue_dir = self._data_dir / "queue"
        self._journal_dir = self._data_dir / "journal"
        self._audit_dir = self._data_dir / "audit"
        self._backups_dir = self._data_dir / "backups"
        self._recovery_dir = self._data_dir / "recovery"

    def _ensure_dirs(self) -> None:
        for d in [
            self._snapshots_dir,
            self._jobs_dir,
            self._queue_dir,
            self._journal_dir,
            self._audit_dir,
            self._backups_dir,
            self._recovery_dir,
        ]:
            d.mkdir(parents=True, exist_ok=True)

    @property
    def data_dir(self) -> str:
        return str(self._data_dir)

    # ── Snapshots ──────────────────────────────────────────────────

    async def save_snapshot(self, snapshot: SystemSnapshot) -> str:
        """Save a snapshot to disk. Returns the file path."""
        self._ensure_dirs()
        path = self._snapshots_dir / f"{snapshot.id}.json"
        data = json.dumps(snapshot.to_dict(), default=str)
        snapshot.checksum = hashlib.sha256(data.encode()).hexdigest()
        snapshot.size_bytes = len(data.encode())
        # Re-serialize with checksum
        data = json.dumps(snapshot.to_dict(), default=str)
        await asyncio.to_thread(self._write_file, str(path), data)
        return str(path)

    async def load_snapshot(self, snapshot_id: str) -> SystemSnapshot | None:
        path = self._snapshots_dir / f"{snapshot_id}.json"
        if not path.exists():
            return None
        data = await asyncio.to_thread(self._read_file, str(path))
        if not data:
            return None
        try:
            d = json.loads(data)
            snap = SystemSnapshot(
                id=d.get("id", snapshot_id),
                type=SnapshotType(d.get("type", "automatic")),
                version=d.get("version", ""),
                created_at=d.get("created_at", ""),
                size_bytes=d.get("size_bytes", 0),
                compressed=d.get("compressed", True),
                checksum=d.get("checksum", ""),
            )
            sections = d.get("sections", {})
            for attr in [
                "brain_registry",
                "executive",
                "cognitive",
                "swarm",
                "ecosystem",
                "cluster",
                "distributed",
                "evolution",
                "missions",
                "providers",
                "security",
                "settings",
            ]:
                setattr(snap, attr, sections.get(attr, {}))
            snap.metadata = d.get("metadata", {})
            return snap
        except Exception:
            log.exception("Failed to load snapshot %s", snapshot_id)
            return None

    async def list_snapshots(self, limit: int = 50) -> list[dict[str, Any]]:
        self._ensure_dirs()
        files = sorted(self._snapshots_dir.glob("*.json"), key=os.path.getmtime, reverse=True)
        results: list[dict[str, Any]] = []
        for f in files[:limit]:
            data = await asyncio.to_thread(self._read_file, str(f))
            if data:
                try:
                    d = json.loads(data)
                    results.append(
                        {
                            "id": d.get("id", ""),
                            "type": d.get("type", ""),
                            "created_at": d.get("created_at", ""),
                            "size_bytes": d.get("size_bytes", 0),
                            "checksum": d.get("checksum", "")[:16],
                        }
                    )
                except Exception:
                    pass
        return results

    async def delete_snapshot(self, snapshot_id: str) -> bool:
        path = self._snapshots_dir / f"{snapshot_id}.json"
        if not path.exists():
            return False
        await asyncio.to_thread(path.unlink)
        return True

    # ── Jobs ───────────────────────────────────────────────────────

    async def save_job(self, job: Job) -> None:
        self._ensure_dirs()
        path = self._jobs_dir / f"{job.id}.json"
        await asyncio.to_thread(self._write_file, str(path), json.dumps(job.to_dict(), default=str))

    async def load_jobs(self) -> list[Job]:
        self._ensure_dirs()
        jobs: list[Job] = []
        for f in self._jobs_dir.glob("*.json"):
            data = await asyncio.to_thread(self._read_file, str(f))
            if data:
                try:
                    d = json.loads(data)
                    jobs.append(
                        Job(
                            id=d.get("id", ""),
                            name=d.get("name", ""),
                            schedule=d.get("schedule", ""),
                            priority=d.get("priority", 5),
                            handler=d.get("handler", ""),
                            args=d.get("args", {}),
                        )
                    )
                except Exception:
                    pass
        return jobs

    # ── Queue ──────────────────────────────────────────────────────

    async def save_queue_task(self, task: QueueTask) -> None:
        self._ensure_dirs()
        path = self._queue_dir / f"{task.id}.json"
        await asyncio.to_thread(
            self._write_file, str(path), json.dumps(task.to_dict(), default=str)
        )

    async def delete_queue_task(self, task_id: str) -> bool:
        path = self._queue_dir / f"{task_id}.json"
        if not path.exists():
            return False
        await asyncio.to_thread(path.unlink)
        return True

    # ── Journal ────────────────────────────────────────────────────

    async def append_journal(self, entry: EventJournalEntry) -> None:
        self._ensure_dirs()
        # Use date-based file for journal
        date_str = datetime.now(UTC).strftime("%Y-%m-%d")
        path = self._journal_dir / f"{date_str}.jsonl"
        line = json.dumps(entry.to_dict(), default=str) + "\n"
        await asyncio.to_thread(self._append_file, str(path), line)

    async def read_journal(
        self, limit: int = 100, topic: str | None = None
    ) -> list[dict[str, Any]]:
        self._ensure_dirs()
        files = sorted(self._journal_dir.glob("*.jsonl"), reverse=True)
        results: list[dict[str, Any]] = []
        for f in files:
            data = await asyncio.to_thread(self._read_file, str(f))
            if not data:
                continue
            for line in data.strip().split("\n"):
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    if topic and not d.get("topic", "").startswith(topic):
                        continue
                    results.append(d)
                    if len(results) >= limit:
                        return results
                except Exception:
                    pass
        return results

    # ── Audit ──────────────────────────────────────────────────────

    async def append_audit(self, record: AuditRecord) -> None:
        self._ensure_dirs()
        date_str = datetime.now(UTC).strftime("%Y-%m-%d")
        path = self._audit_dir / f"{date_str}.jsonl"
        line = json.dumps(record.to_dict(), default=str) + "\n"
        await asyncio.to_thread(self._append_file, str(path), line)

    async def read_audit(self, limit: int = 100) -> list[dict[str, Any]]:
        self._ensure_dirs()
        files = sorted(self._audit_dir.glob("*.jsonl"), reverse=True)
        results: list[dict[str, Any]] = []
        for f in files:
            data = await asyncio.to_thread(self._read_file, str(f))
            if not data:
                continue
            for line in data.strip().split("\n"):
                if not line:
                    continue
                try:
                    results.append(json.loads(line))
                    if len(results) >= limit:
                        return results
                except Exception:
                    pass
        return results

    # ── File helpers ───────────────────────────────────────────────

    @staticmethod
    def _write_file(path: str, data: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            f.write(data)

    @staticmethod
    def _read_file(path: str) -> str:
        try:
            with open(path, encoding="utf-8") as f:
                return f.read()
        except Exception:
            return ""

    @staticmethod
    def _append_file(path: str, data: str) -> None:
        with open(path, "a", encoding="utf-8") as f:
            f.write(data)


class SnapshotEngine:
    """Creates and manages system-wide snapshots."""

    def __init__(
        self,
        bus: EventBus,
        persistence: PersistenceLayer,
    ) -> None:
        self._bus = bus
        self._persistence = persistence
        self._stats = RuntimeStatistics()
        self._auto_snapshot_interval = 300.0  # 5 minutes
        self._snapshot_task: asyncio.Task | None = None
        self._started = False

    @property
    def stats(self) -> RuntimeStatistics:
        return self._stats

    def list_snapshots(self, limit: int = 50) -> Any:
        return self._persistence.list_snapshots(limit=limit)

    # ── Lifecycle ──────────────────────────────────────────────────

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        log.info("SnapshotEngine started")

    async def stop(self) -> None:
        self._started = False
        log.info("SnapshotEngine stopped")

    # ── Snapshot creation ──────────────────────────────────────────

    async def create_snapshot(
        self,
        snapshot_type: SnapshotType = SnapshotType.AUTOMATIC,
        state_provider: Any = None,
    ) -> SystemSnapshot | None:
        """Create a system-wide snapshot.

        ``state_provider`` is a callable that returns a dict of section → state.
        If None, an empty snapshot is created.
        """
        snapshot = SystemSnapshot(type=snapshot_type)

        if state_provider is not None:
            try:
                state = state_provider()
                if hasattr(state, "__await__"):
                    state = await state
                for section in [
                    "brain_registry",
                    "executive",
                    "cognitive",
                    "swarm",
                    "ecosystem",
                    "cluster",
                    "distributed",
                    "evolution",
                    "missions",
                    "providers",
                    "security",
                    "settings",
                ]:
                    setattr(snapshot, section, state.get(section, {}))
            except Exception:
                log.exception("Failed to capture state for snapshot")

        await self._persistence.save_snapshot(snapshot)
        self._stats.snapshots_created += 1
        self._stats.last_snapshot = snapshot.created_at

        await self._publish(
            "runtime.snapshot.created",
            {
                "id": snapshot.id,
                "type": snapshot.type.value,
                "size_bytes": snapshot.size_bytes,
            },
        )

        log.info("Snapshot created", id=snapshot.id, type=snapshot.type.value)
        return snapshot

    async def restore_snapshot(self, snapshot_id: str) -> SystemSnapshot | None:
        """Load a snapshot from disk for restoration."""
        snapshot = await self._persistence.load_snapshot(snapshot_id)
        if snapshot is None:
            log.warning("Snapshot not found: %s", snapshot_id)
            return None
        self._stats.snapshots_restored += 1
        await self._publish("runtime.snapshot.restored", {"id": snapshot_id})
        log.info("Snapshot restored: %s", snapshot_id)
        return snapshot

    async def delete_snapshot(self, snapshot_id: str) -> bool:
        deleted = await self._persistence.delete_snapshot(snapshot_id)
        if deleted:
            log.info("Snapshot deleted: %s", snapshot_id)
        return deleted

    # ── Internal ───────────────────────────────────────────────────

    async def _publish(self, topic: str, payload: dict[str, Any]) -> None:
        try:
            from agentic_os.domain.events import EventEnvelope

            await self._bus.publish(
                EventEnvelope(
                    type=topic,
                    source="persistent.snapshot",
                    topic=topic,
                    payload=payload,
                )
            )
        except Exception:
            log.exception("Failed to publish %s", topic)


class RecoveryEngine:
    """Restores platform state from snapshots after restart."""

    def __init__(
        self,
        bus: EventBus,
        persistence: PersistenceLayer,
        snapshot_engine: SnapshotEngine,
    ) -> None:
        self._bus = bus
        self._persistence = persistence
        self._snapshot_engine = snapshot_engine
        self._history: list[RecoveryPlan] = []
        self._stats: dict[str, int] = {
            "recoveries_started": 0,
            "recoveries_completed": 0,
            "recoveries_failed": 0,
        }

    @property
    def stats(self) -> dict[str, Any]:
        return dict(self._stats)

    def list_history(self, limit: int = 50) -> list[RecoveryPlan]:
        return list(self._history[-limit:])

    async def recover_from_snapshot(
        self,
        snapshot_id: str,
        sections: list[str] | None = None,
        state_applier: Any = None,
    ) -> RecoveryPlan:
        """Recover platform state from a snapshot.

        ``state_applier`` is a callable that takes (section_name, section_state)
        and applies it to the live system. If None, the snapshot is loaded but
        not applied.
        """
        self._stats["recoveries_started"] += 1
        plan = RecoveryPlan(
            snapshot_id=snapshot_id,
            sections_to_recover=sections
            or [
                "brain_registry",
                "executive",
                "cognitive",
                "swarm",
                "ecosystem",
                "cluster",
                "distributed",
                "evolution",
                "missions",
                "providers",
                "security",
                "settings",
            ],
            status=RecoveryStatus.IN_PROGRESS,
            started_at=datetime.now(UTC).isoformat(),
        )

        snapshot = await self._snapshot_engine.restore_snapshot(snapshot_id)
        if snapshot is None:
            plan.status = RecoveryStatus.FAILED
            plan.errors.append(f"Snapshot {snapshot_id} not found")
            self._stats["recoveries_failed"] += 1
            self._history.append(plan)
            await self._publish("runtime.recovery.failed", plan.to_dict())
            return plan

        for section in plan.sections_to_recover:
            try:
                section_state = getattr(snapshot, section, {})
                if state_applier is not None:
                    result = state_applier(section, section_state)
                    if hasattr(result, "__await__"):
                        await result
                plan.sections_recovered.append(section)
            except Exception as e:
                plan.sections_failed.append(section)
                plan.errors.append(f"{section}: {e}")
                log.exception("Failed to recover section %s", section)

        if plan.sections_failed:
            plan.status = (
                RecoveryStatus.PARTIAL if plan.sections_recovered else RecoveryStatus.FAILED
            )
        else:
            plan.status = RecoveryStatus.COMPLETED

        plan.completed_at = datetime.now(UTC).isoformat()
        self._stats["recoveries_completed"] += 1
        self._history.append(plan)

        await self._publish("runtime.recovered", plan.to_dict())
        log.info(
            "Recovery completed",
            snapshot=snapshot_id,
            status=plan.status.value,
            recovered=len(plan.sections_recovered),
            failed=len(plan.sections_failed),
        )
        return plan

    async def _publish(self, topic: str, payload: dict[str, Any]) -> None:
        try:
            from agentic_os.domain.events import EventEnvelope

            await self._bus.publish(
                EventEnvelope(
                    type=topic,
                    source="persistent.recovery",
                    topic=topic,
                    payload=payload,
                )
            )
        except Exception:
            log.exception("Failed to publish %s", topic)
