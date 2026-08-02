# ADR-0017: Task Decomposition & Topological Scheduling

- Status: Accepted
- Date: 2026-07-19

## Context

Swarm orchestration requires dynamic decomposition of high-level goals into
executable tasks, followed by dependency-aware scheduling across available
agents. Two key challenges arise:

1. **Goal decomposition** — A single goal ("Write a blog post") must be broken
   into ordered subtasks ("Research → Outline → Draft → Review → Publish")
   with dependency relationships.
2. **Task scheduling** — Tasks with complex dependency graphs must be ordered
   so that all dependencies are satisfied before execution, and the schedule
   must be computable efficiently.

## Decision

### Planner: Rule-Based Goal Decomposition

The `SwarmPlanner` uses a **rule-based strategy** (not LLM-based) for goal
decomposition:

- `analyze_goal()` — Scores goal complexity on a 1–5 scale based on keyword
  analysis (simple/quick/minor → 1, large/complex/major → 5) and estimates
  required task count.
- `create_plan()` — Produces an `OrchestrationPlan` with zero or more subtasks.
  The default rule-based strategy creates a single-task plan; profile-driven
  decomposition uses the profile's `max_agents_per_swarm` and
  `subtask_timeout_seconds` to shape the plan.
- `resolve_dependencies()` — Walks task `depends_on` references, translating
  task IDs to actual `AgentTask` objects for the scheduler.
- `parallelize_plan()` — Groups independent tasks into parallel buckets for
  the coordination pattern selection.

The rule-based approach was chosen over LLM-based decomposition because:
- Deterministic output — same goal always produces same structure
- No external API call overhead during planning
- Predictable latency (sub-millisecond)
- Sufficient for the initial set of coordination patterns

### Scheduler: Kahn's Algorithm for Topological Sort

The `SwarmScheduler` uses **Kahn's algorithm** (BFS-based topological sort)
for dependency resolution:

```python
# Pseudocode
def _topological_sort(tasks, dependencies):
    in_degree = {t.id: len(dependencies.get(t.id, [])) for t in tasks}
    ready = deque(t for t in tasks if in_degree[t.id] == 0)
    ordered = []
    while ready:
        task = ready.popleft()
        ordered.append(task)
        for dependent_id in reverse_deps.get(task.id, []):
            in_degree[dependent_id] -= 1
            if in_degree[dependent_id] == 0:
                ready.append(dependent_id)
    return ordered
```

Key properties:
- **O(V + E)** time complexity (vertices = tasks, edges = dependencies)
- Produces a valid execution order where every task's dependencies appear before it
- The `ready` deque naturally implements the ready-set semantics needed by
  the supervisor for concurrent execution
- Deadlock detection is delegated to the `ValidationEngine` (DFS-based cycle
  detection) and `SwarmSupervisor` (runtime cycle monitoring)

### Schedule Storage

The scheduler maintains an internal `_schedules: dict[str, list[AgentTask]]`
mapping plan IDs to their computed topological order. `schedule_tasks()` stores
the computed schedule; `get_schedule()` retrieves it. This separates computation
from access and allows the supervisor to query the schedule without re-running
the sort.

### Dispatch

`dispatch_task()` executes a single task through the runtime:
1. Sends an `ExecutionRequest` to the assigned agent via `runtime.execute()`
2. Handles `TimeoutError` (returns PENDING task with timeout error)
3. Handles generic exceptions (returns PENDING task with exception message)
4. On success with `status == "completed"`, returns a COMPLETED task with output
5. On other statuses, returns a FAILED task with the runtime error

## Consequences

- **Positive**: Rule-based decomposition is fast, deterministic, and testable.
- **Positive**: Kahn's algorithm is simple to implement, verify, and debug.
- **Positive**: Separate schedule storage enables query without recomputation.
- **Negative**: Rule-based decomposition cannot handle goals requiring semantic
  understanding; future versions may add an LLM-based planner as an alternative.
- **Negative**: Kahn's algorithm produces one valid order but does not optimize
  for parallel execution width (no critical-path minimization).

## Related ADRs

- ADR-0016 (Swarm Orchestration Architecture) — Parent architecture
- ADR-0019 (Resilience & Recovery) — Supervisor monitors scheduled execution
