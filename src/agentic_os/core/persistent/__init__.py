"""Phase 18 — Autonomous Runtime, Persistent Memory & Self-Healing Platform.

Builds on the existing Phase 1-17 architecture with:
  - System-wide snapshot engine (full/incremental, compressed, checksummed)
  - Automatic recovery engine (restore from snapshot after restart)
  - Background job scheduler (cron/interval/one-shot, priority, retry, deps)
  - Durable task queue (priority, leases, acks, dead-letter, timeouts)
  - Event journal (append-only, replay, filter, search)
  - Audit log (immutable, categorized)
  - Health supervisor (periodic subsystem monitoring)
  - Backup manager (export/import, compressed archives)

All additive — reuses existing EventBus, BrainRegistry, and all Phase 11-17
controllers. Does NOT replace any existing implementation.
"""

from agentic_os.core.persistent.domain import (
    AuditCategory,
    AuditRecord,
    BackupManifest,
    EventJournalEntry,
    HealthCheckResult,
    Job,
    JobStatus,
    JobType,
    QueueAck,
    QueueTask,
    QueueTaskStatus,
    RecoveryPlan,
    RecoveryStatus,
    RuntimeStatistics,
    SnapshotType,
    SystemSnapshot,
)
from agentic_os.core.persistent.persistent_controller import (
    BackupManager,
    HealthSupervisor,
    PersistentController,
)
from agentic_os.core.persistent.scheduler_queue import (
    AuditLog,
    BackgroundJobScheduler,
    DurableTaskQueue,
    EventJournal,
)
from agentic_os.core.persistent.snapshot_engine import (
    PersistenceLayer,
    RecoveryEngine,
    SnapshotEngine,
)

__all__ = [
    "AuditCategory",
    "AuditLog",
    "AuditRecord",
    "BackgroundJobScheduler",
    "BackupManager",
    "BackupManifest",
    "DurableTaskQueue",
    "EventJournal",
    "EventJournalEntry",
    "HealthCheckResult",
    "HealthSupervisor",
    "Job",
    "JobStatus",
    "JobType",
    "PersistentController",
    "PersistenceLayer",
    "QueueAck",
    "QueueTask",
    "QueueTaskStatus",
    "RecoveryEngine",
    "RecoveryPlan",
    "RecoveryStatus",
    "RuntimeStatistics",
    "SnapshotEngine",
    "SnapshotType",
    "SystemSnapshot",
]
