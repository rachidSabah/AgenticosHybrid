"""Phase 18 — Persistent runtime domain models.

Pure data structures for autonomous runtime persistence:
  - SystemSnapshot (full platform state)
  - RecoveryPlan + RecoveryResult
  - Job + JobSchedule
  - QueueTask + QueueAck
  - EventJournalEntry
  - AuditEntry
  - BackupManifest
  - HealthCheckResult

All additive — does not modify any existing domain model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _new_id(prefix: str = "") -> str:
    return f"{prefix}{uuid4().hex[:12]}" if prefix else uuid4().hex[:12]


# ── System Snapshot ────────────────────────────────────────────────────


class SnapshotType(StrEnum):
    FULL = "full"
    INCREMENTAL = "incremental"
    MANUAL = "manual"
    AUTOMATIC = "automatic"
    PRE_SHUTDOWN = "pre_shutdown"
    PRE_UPDATE = "pre_update"


@dataclass
class SystemSnapshot:
    """A full or incremental snapshot of the entire platform state."""

    id: str = field(default_factory=lambda: _new_id("snap-"))
    type: SnapshotType = SnapshotType.AUTOMATIC
    version: str = "1.0.0-rc9"
    created_at: str = field(default_factory=_now_iso)
    size_bytes: int = 0
    compressed: bool = True
    checksum: str = ""
    # State sections (each is a JSON-serializable dict)
    brain_registry: dict[str, Any] = field(default_factory=dict)
    executive: dict[str, Any] = field(default_factory=dict)
    cognitive: dict[str, Any] = field(default_factory=dict)
    swarm: dict[str, Any] = field(default_factory=dict)
    ecosystem: dict[str, Any] = field(default_factory=dict)
    cluster: dict[str, Any] = field(default_factory=dict)
    distributed: dict[str, Any] = field(default_factory=dict)
    evolution: dict[str, Any] = field(default_factory=dict)
    missions: dict[str, Any] = field(default_factory=dict)
    providers: dict[str, Any] = field(default_factory=dict)
    security: dict[str, Any] = field(default_factory=dict)
    settings: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "version": self.version,
            "created_at": self.created_at,
            "size_bytes": self.size_bytes,
            "compressed": self.compressed,
            "checksum": self.checksum,
            "sections": {
                "brain_registry": self.brain_registry,
                "executive": self.executive,
                "cognitive": self.cognitive,
                "swarm": self.swarm,
                "ecosystem": self.ecosystem,
                "cluster": self.cluster,
                "distributed": self.distributed,
                "evolution": self.evolution,
                "missions": self.missions,
                "providers": self.providers,
                "security": self.security,
                "settings": self.settings,
            },
            "metadata": dict(self.metadata),
        }


# ── Recovery ───────────────────────────────────────────────────────────


class RecoveryStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


@dataclass
class RecoveryPlan:
    """A plan for recovering platform state after a restart."""

    id: str = field(default_factory=lambda: _new_id("rec-"))
    snapshot_id: str = ""
    sections_to_recover: list[str] = field(default_factory=list)
    status: RecoveryStatus = RecoveryStatus.PENDING
    started_at: str = ""
    completed_at: str = ""
    sections_recovered: list[str] = field(default_factory=list)
    sections_failed: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "snapshot_id": self.snapshot_id,
            "sections_to_recover": list(self.sections_to_recover),
            "status": self.status.value,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "sections_recovered": list(self.sections_recovered),
            "sections_failed": list(self.sections_failed),
            "errors": list(self.errors),
            "created_at": self.created_at,
        }


# ── Background Job ─────────────────────────────────────────────────────


class JobType(StrEnum):
    CRON = "cron"
    INTERVAL = "interval"
    ONE_SHOT = "one_shot"


class JobStatus(StrEnum):
    PENDING = "pending"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"


@dataclass
class Job:
    """A scheduled background job."""

    id: str = field(default_factory=lambda: _new_id("job-"))
    name: str = ""
    type: JobType = JobType.INTERVAL
    schedule: str = ""  # cron expr or interval seconds
    priority: int = 5  # 1=highest, 10=lowest
    status: JobStatus = JobStatus.PENDING
    handler: str = ""  # function name to call
    args: dict[str, Any] = field(default_factory=dict)
    dependencies: list[str] = field(default_factory=list)  # job IDs
    timeout_s: float = 300.0
    max_retries: int = 3
    retries: int = 0
    last_run: str = ""
    next_run: str = ""
    last_result: dict[str, Any] = field(default_factory=dict)
    last_error: str = ""
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type.value,
            "schedule": self.schedule,
            "priority": self.priority,
            "status": self.status.value,
            "handler": self.handler,
            "args": dict(self.args),
            "dependencies": list(self.dependencies),
            "timeout_s": self.timeout_s,
            "max_retries": self.max_retries,
            "retries": self.retries,
            "last_run": self.last_run,
            "next_run": self.next_run,
            "last_result": dict(self.last_result),
            "last_error": self.last_error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


# ── Task Queue ─────────────────────────────────────────────────────────


class QueueTaskStatus(StrEnum):
    QUEUED = "queued"
    LEASED = "leased"
    COMPLETED = "completed"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"
    TIMED_OUT = "timed_out"


@dataclass
class QueueTask:
    """A task in the durable priority queue."""

    id: str = field(default_factory=lambda: _new_id("qt-"))
    queue: str = "default"
    priority: int = 5  # 1=highest
    payload: dict[str, Any] = field(default_factory=dict)
    status: QueueTaskStatus = QueueTaskStatus.QUEUED
    lease_owner: str = ""
    lease_expires: str = ""
    ack_count: int = 0
    nack_count: int = 0
    max_attempts: int = 3
    attempts: int = 0
    result: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    created_at: str = field(default_factory=_now_iso)
    completed_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "queue": self.queue,
            "priority": self.priority,
            "payload": dict(self.payload),
            "status": self.status.value,
            "lease_owner": self.lease_owner,
            "lease_expires": self.lease_expires,
            "ack_count": self.ack_count,
            "nack_count": self.nack_count,
            "max_attempts": self.max_attempts,
            "attempts": self.attempts,
            "result": dict(self.result),
            "error": self.error,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }


@dataclass
class QueueAck:
    """Acknowledgement for a queue task."""

    task_id: str
    worker_id: str
    success: bool = True
    result: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    timestamp: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "worker_id": self.worker_id,
            "success": self.success,
            "result": dict(self.result),
            "error": self.error,
            "timestamp": self.timestamp,
        }


# ── Event Journal ──────────────────────────────────────────────────────


@dataclass
class EventJournalEntry:
    """A persisted EventBus entry for replay/search."""

    id: str = field(default_factory=lambda: _new_id("evt-"))
    event_type: str = ""
    source: str = ""
    topic: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    correlation_id: str = ""
    session_id: str = ""
    timestamp: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "event_type": self.event_type,
            "source": self.source,
            "topic": self.topic,
            "payload": dict(self.payload),
            "correlation_id": self.correlation_id,
            "session_id": self.session_id,
            "timestamp": self.timestamp,
        }


# ── Audit Log ──────────────────────────────────────────────────────────


class AuditCategory(StrEnum):
    CONFIGURATION = "configuration"
    MISSION = "mission"
    SECURITY = "security"
    CLUSTER = "cluster"
    DISTRIBUTED = "distributed"
    ECOSYSTEM = "ecosystem"
    SYSTEM = "system"


@dataclass
class AuditRecord:
    """An immutable audit log entry."""

    id: str = field(default_factory=lambda: _new_id("audit-"))
    category: AuditCategory = AuditCategory.SYSTEM
    action: str = ""
    actor: str = ""  # who/what performed the action
    target: str = ""  # what was acted upon
    details: dict[str, Any] = field(default_factory=dict)
    severity: str = "info"  # info | warning | critical
    timestamp: str = field(default_factory=_now_iso)
    # Immutable — no mutation methods, only to_dict

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category.value,
            "action": self.action,
            "actor": self.actor,
            "target": self.target,
            "details": dict(self.details),
            "severity": self.severity,
            "timestamp": self.timestamp,
        }


# ── Backup ─────────────────────────────────────────────────────────────


@dataclass
class BackupManifest:
    """Manifest for a system backup."""

    id: str = field(default_factory=lambda: _new_id("backup-"))
    created_at: str = field(default_factory=_now_iso)
    version: str = "1.0.0-rc9"
    snapshot_id: str = ""
    size_bytes: int = 0
    compressed: bool = True
    encrypted: bool = False
    checksum: str = ""
    path: str = ""
    sections: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "created_at": self.created_at,
            "version": self.version,
            "snapshot_id": self.snapshot_id,
            "size_bytes": self.size_bytes,
            "compressed": self.compressed,
            "encrypted": self.encrypted,
            "checksum": self.checksum,
            "path": self.path,
            "sections": list(self.sections),
        }


# ── Health Check ───────────────────────────────────────────────────────


@dataclass
class HealthCheckResult:
    """Result of a health check on a subsystem."""

    subsystem: str
    healthy: bool = True
    score: float = 1.0
    issues: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "subsystem": self.subsystem,
            "healthy": self.healthy,
            "score": round(self.score, 3),
            "issues": list(self.issues),
            "metrics": dict(self.metrics),
            "timestamp": self.timestamp,
        }


# ── Runtime Statistics ─────────────────────────────────────────────────


@dataclass
class RuntimeStatistics:
    """Aggregate runtime persistence statistics."""

    snapshots_created: int = 0
    snapshots_restored: int = 0
    recoveries_performed: int = 0
    jobs_executed: int = 0
    jobs_failed: int = 0
    tasks_queued: int = 0
    tasks_completed: int = 0
    tasks_failed: int = 0
    tasks_dead_letter: int = 0
    events_journaled: int = 0
    audit_records: int = 0
    backups_created: int = 0
    backups_restored: int = 0
    last_snapshot: str = ""
    last_recovery: str = ""
    last_updated: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshots_created": self.snapshots_created,
            "snapshots_restored": self.snapshots_restored,
            "recoveries_performed": self.recoveries_performed,
            "jobs_executed": self.jobs_executed,
            "jobs_failed": self.jobs_failed,
            "tasks_queued": self.tasks_queued,
            "tasks_completed": self.tasks_completed,
            "tasks_failed": self.tasks_failed,
            "tasks_dead_letter": self.tasks_dead_letter,
            "events_journaled": self.events_journaled,
            "audit_records": self.audit_records,
            "backups_created": self.backups_created,
            "backups_restored": self.backups_restored,
            "last_snapshot": self.last_snapshot,
            "last_recovery": self.last_recovery,
            "last_updated": self.last_updated,
        }
