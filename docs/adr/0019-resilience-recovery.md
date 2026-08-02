# ADR-0019: Resilience & Recovery

- Status: Accepted
- Date: 2026-07-19

## Context

Distributed agent execution is inherently unreliable: engines crash, networks
fail, tasks time out, and agents produce invalid results. The swarm engine must
handle failures gracefully through retry, checkpointing, and recovery mechanisms
without losing progress or requiring manual intervention for transient failures.

Four interrelated subsystems provide resilience:

| Subsystem | Responsibility |
|-----------|---------------|
| `RetryManager` | Track retry attempts, calculate backoff, cap exhaustion |
| `FailureRecovery` | Reassign failed tasks to healthy agents, recover plans |
| `CheckpointManager` | Save/restore execution snapshots at task boundaries |
| `SwarmSupervisor` | Detect failures, hung tasks, and deadlocks at runtime |

## Decision

### RetryManager: Exponential Backoff with Jitter

The `RetryManager` implements **exponential backoff with jitter**:

```python
def _calculate_delay(self, retry_count: int) -> float:
    base = self._policy.get("base_delay_seconds", 1.0)
    multiplier = self._policy.get("backoff_multiplier", 2.0)
    max_delay = self._policy.get("max_delay_seconds", 60.0)
    jitter = self._policy.get("jitter", True)

    delay = min(base * (multiplier ** retry_count), max_delay)
    if jitter:
        delay += random.uniform(0, delay * 0.1)  # 10% jitter
    return delay
```

Key design decisions:
- **`should_retry()`** checks against the configured `max_retries` (default: 3)
  and returns `(should_retry: bool, delay_seconds: float)`.
- **`execute_with_retry()`** wraps an async callable with the retry loop,
  calculating delay before each attempt and calling `retry_scheduled` /
  `retry_executing` / `retry_exhausted` events at appropriate points.
- **Per-task tracking** — Retry counts are stored in `_retry_counts: dict[str, int]`,
  keyed by task ID. `reset_retry_count()` clears the count for a given task.
- **10% jitter** was chosen as a compromise: enough to avoid thundering-herd
  without making delays unpredictably long.

### CheckpointManager: In-Memory Snapshots

The `CheckpointManager` stores execution snapshots in memory:

```python
@dataclass(frozen=True)
class Checkpoint:
    id: str
    plan_id: str
    task_states: dict[str, AgentTaskStatus]
    partial_outputs: dict[str, dict[str, Any]]
    timestamp: datetime
```

- `save_checkpoint(plan)` — Iterates plan subtasks, captures each task's status
  and output data as a `Checkpoint`, publishes `checkpoint_created` event.
- `restore_checkpoint(checkpoint_id)` — Returns the stored `Checkpoint` or None.
- `list_checkpoints(plan_id)` — Filters by plan ID.
- `delete_checkpoint(checkpoint_id)` — Removes from store.

Checkpoints are saved at configurable intervals (every N completed tasks,
configured via `checkpoint_interval_tasks`). This provides a balance between
granularity and overhead — too-frequent checkpoints add memory pressure; too-
infrequent checkpoints risk losing more work on failure.

### FailureRecovery: Three Recovery Paths

The `FailureRecovery` subsystem provides three recovery paths:

1. **`recover_task(task, available_agents)`** — Reassigns a failed task to a
   different agent (prefers agents with matching capabilities). Returns the
   reassigned `AgentTask` with `ASSIGNED` status, or the original task with an
   error if no suitable agent exists.

2. **`recover_plan(plan, checkpoint_id=None)`** — Two modes:
   - **From checkpoint**: Restores task states from the checkpoint, reconstructs
     the plan from the restored task states, publishes `recovery_completed`.
   - **Without checkpoint**: Resets all tasks to `PENDING` status and clears
     their outputs (full replan), publishes `recovery_started`/`recovery_completed`.

3. **`rollback_plan(plan, checkpoint_id)`** — Restores a specific checkpoint
   and reconstructs the plan from those task states. Used when the current
   execution state is unrecoverable and a known-good checkpoint exists.

### SwarmSupervisor: Runtime Monitoring

The `SwarmSupervisor` monitors execution at runtime:
- **`monitor_execution(plan)`** — Records task statuses, detects completed and
  failed tasks, publishes `supervisor_monitoring` event.
- **`detect_failures(plan)`** — Returns list of FAILED tasks.
- **`detect_deadlocks(plan)`** — Runs DFS-based cycle detection on the plan's
  dependency graph; returns the cycle node IDs.
- **`detect_hung_tasks(plan)`** — Compares task `started_at` timestamps against
  the configured `hung_task_timeout_seconds`; returns timed-out tasks.
- **`restart_task(task, agent)`** — Executes the task via runtime on the given
  agent. On success returns COMPLETED; on failure returns FAILED with error.
- **`reassign_task(task, new_agent_id)`** — Returns the task with a new
  `assigned_agent_id` and `ASSIGNED` status.

### Event-Driven Resilience

All resilience actions emit `EventBus` events:
- Retry: `retry_scheduled` → `retry_executing` → `retry_exhausted`
- Recovery: `recovery_started` → `recovery_completed` / `recovery_failed`
- Checkpoint: `checkpoint_created` / `checkpoint_restored`
- Supervisor: `supervisor_failure_detected` / `supervisor_deadlock_detected` /
  `supervisor_restarted` / `supervisor_reassigned`

This allows external consoles (Mission Control, telemetry dashboard) to observe
and react to resilience events without coupling to recovery logic.

## Consequences

- **Positive**: Retry with jitter prevents thundering-herd on transient failures.
- **Positive**: Checkpoint/restore allows resumption from partial progress.
- **Positive**: Three recovery paths cover the main failure scenarios (single
  task, full plan with checkpoint, full plan without checkpoint).
- **Positive**: Event-driven resilience enables external monitoring.
- **Negative**: In-memory checkpoints are lost on process restart — no persistent
  storage (deferred to a future milestone with database-backed checkpoints).
- **Negative**: No circuit-breaker pattern — the retry manager always attempts
  up to `max_retries` regardless of failure rate.
- **Negative**: Recovery does not attempt to reorder tasks that were in-flight
  at checkpoint time; those must be re-executed.

## Related ADRs

- ADR-0016 (Swarm Orchestration Architecture) — Parent architecture
- ADR-0017 (Task Decomposition & Scheduling) — Supervisor monitors scheduled tasks
- ADR-0018 (Result Merging & Validation) — Validation gates recovery decisions
