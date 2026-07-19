# ADR-0016: Swarm Orchestration Architecture

- Status: Accepted
- Date: 2026-07-19

## Context

Phase 4, Milestone 4 (v0.8.0) requires a **Swarm Orchestration Engine** capable
of coordinating multiple AI agents to achieve complex goals. Unlike the existing
Phase 3B engines (workflow, pipeline) which operate on predefined DAGs of
abstract tasks, the swarm engine must dynamically decompose goals, assign tasks
to agents based on capabilities, supervise execution with failure recovery, and
merge partial results into a coherent output.

The design must support:
- Dynamic goal decomposition into tasks at runtime
- Capability-based agent selection with health-aware scoring
- Multiple coordination patterns (sequential, parallel, fan-out/fan-in, voting)
- Topological scheduling with dependency resolution
- Result merging via configurable strategies
- Fault tolerance through retry, checkpoint, and recovery mechanisms

## Decision

Adopt a **hexagonal architecture** with 12 specialized core subsystems wired
through an `OrchestrationFramework` composition root:

```
 ┌──────────────────────────────────────────────────────────┐
 │                     REST API (FastAPI)                     │
 ├──────────────────────────────────────────────────────────┤
 │                  OrchestrationFramework                    │
 │  ┌──────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐ │
 │  │Planner│ │Scheduler │ │Supervisor│ │ ResultMerger     │ │
 │  ├──────┤ ├──────────┤ ├──────────┤ ├──────────────────┤ │
 │  │Analyze│ │Topo.Sort │ │Monitor   │ │Weighted/Consensus│ │
 │  │Decomp │ │Dispatch  │ │Detect    │ │Best-of-N/Voting  │ │
 │  │Plan   │ │Schedule  │ │Restart   │ │Concatenate       │ │
 │  └──────┘ └──────────┘ └──────────┘ └──────────────────┘ │
 │  ┌──────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐ │
 │  │Validate│ │RetryMgr │ │Recovery  │ │ CheckpointMgr   │ │
 │  ├──────┤ ├──────────┤ ├──────────┤ ├──────────────────┤ │
 │  │Schema │ │Backoff  │ │Reassign  │ │ Save/Restore     │ │
 │  │Policy │ │Jitter   │ │Rollback  │ │ List/Delete      │ │
 │  │Plan   │ │Exhausted│ │Recover   │ │                  │ │
 │  └──────┘ └──────────┘ └──────────┘ └──────────────────┘ │
 │  ┌─────────┐ ┌──────────┐ ┌──────────────┐              │
 │  │Selector │ │Metrics   │ │CostTracker   │              │
 │  ├─────────┤ ├──────────┤ ├──────────────┤              │
 │  │Scoring  │ │Timeline  │ │Estimate/Track│              │
 │  │Match    │ │Analyze   │ │Per-agent     │              │
 │  └─────────┘ └──────────┘ └──────────────┘              │
 ├──────────────────────────────────────────────────────────┤
 │                  EventBus (publisher)                     │
 ├──────────────────────────────────────────────────────────┤
 │    Domain (frozen dataclasses) ← Ports (protocols)       │
 └──────────────────────────────────────────────────────────┘
```

### Domain Models

All 14 new domain models are **frozen dataclasses** (not Pydantic):

| Model | Purpose |
|-------|---------|
| `SwarmProfile` | Named configuration profile for a swarm |
| `SwarmTopology` | Enum: mesh, star, hierarchical |
| `AgentTaskStatus` | Enum: pending, assigned, running, completed, etc. |
| `CoordinationPattern` | Enum: sequential, parallel, fan_out, fan_in, etc. |
| `AgentDescriptor` | Agent identity, capabilities, health, role |
| `OrchestrationGoal` | Top-level goal with complexity and constraints |
| `AgentTask` | Individual task with dependencies, status, output |
| `OrchestrationPlan` | Ordered collection of tasks with execution config |
| `ExecutionStage` | Stage within a multi-stage execution |
| `MergedResult` | Merged output with confidence and conflict info |
| `ValidationResult` | Validation outcome with score and errors |
| `RetryPolicy` | Retry configuration (max retries, backoff, jitter) |
| `Checkpoint` | Snapshot of task states and partial outputs |
| `ExecutionMetrics`, `ExecutionCost`, `ExecutionTimeline` | Telemetry |

### Port Interfaces

| Port | Purpose |
|------|---------|
| `SwarmPlannerPort` | Goal analysis, plan creation, dependency resolution |
| `SwarmSchedulerPort` | Topological sort, dispatch, schedule management |
| `SwarmSupervisorPort` | Monitor, detect failures/deadlocks, restart/reassign |
| `ResultMergerPort` | Multi-strategy result merging |
| `ValidationPort` | Schema, type, plan, security, policy validation |
| `RetryPort` | Retry tracking, backoff calculation |
| `RecoveryPort` | Task/plan recovery, rollback |
| `CheckpointPort` | Save, restore, list, delete checkpoints |
| `AgentSelectionPort` | Capability matching, scoring, selection |
| `MetricsPort` | Metrics collection, timeline recording |
| `CostEstimatorPort` | Cost estimation and tracking |

### Subsystem Design Principles

1. **Stateless core, stateful infrastructure** — Core subsystems hold no
   persistent state; checkpoints and metrics are managed by dedicated subsystems.
2. **Event emission** — Every state transition publishes an `EventEnvelope`
   through the `OrchestrationEventPublisher` facade.
3. **Immutable state transitions** — Domain models are frozen; state changes
   return new instances via `with_*()` or direct constructor calls.
4. **Injection-friendly** — All subsystems accept their dependencies through
   constructors; `OrchestrationFramework._build_subsystems()` wires defaults but
   allows override per-subsystem for testing.

### Routing Logic

The `OrchestrationFramework` acts as a **facade** — each public method delegates
to the appropriate subsystem. The framework does NOT embed routing logic; it is
a thin composition/coordination layer. Subsystems call each other through the
framework only when cross-subsystem coordination is needed (e.g., scheduler
calls supervisor for task failure handling).

## Consequences

- **Positive**: Clear separation of concerns — each subsystem has a single
  responsibility and is independently testable.
- **Positive**: New coordination patterns or merge strategies can be added by
  extending one subsystem without touching others.
- **Positive**: The facade pattern makes the API surface predictable and
  discoverable.
- **Negative**: 12 subsystems + framework + publisher = 14 classes to wire,
  creating a non-trivial composition graph.
- **Negative**: Event publishing is manual per method rather than AOP-based,
  leading to boilerplate in publisher calls.

## Related ADRs

- ADR-0002 (Hexagonal Architecture) — The parent architectural pattern
- ADR-0017 (Task Decomposition & Scheduling) — Planner and scheduler design
- ADR-0018 (Result Merging & Validation) — Merge strategies and validation
- ADR-0019 (Resilience & Recovery) — Retry, checkpoint, and recovery patterns
