# ADR-0005: Recovery bounded by task attempts

- Status: Accepted
- Date: 2026-07-17

## Context

Agents fail. We must auto-recover, but unbounded retries cause storms (observed
during development: each re-dispatch spawned a fresh agent with `attempts=0`,
looping forever).

## Decision

The attempt counter lives on the **Task** (the durable unit of work), not on the
transient Agent. `Orchestrator.dispatch_task` increments `task.attempts`. The
`RecoveryManager` caps retries at `settings.max_attempts`; beyond that it marks
the task `FAILED` and stops. Health degradation is treated as failure after the
heartbeat window.

## Consequences

- Recovery is guaranteed to terminate.
- Attempt accounting is correct across re-dispatches.
- Future strategies (exponential backoff, Temporal) slot in behind the same port.
