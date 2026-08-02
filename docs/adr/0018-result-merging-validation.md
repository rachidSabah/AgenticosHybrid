# ADR-0018: Result Merging & Validation

- Status: Accepted
- Date: 2026-07-19

## Context

In a multi-agent swarm, multiple agents may produce outputs for the same task
(e.g., parallel execution, voting on a decision, or redundant processing for
reliability). The system must merge these potentially divergent results into a
single coherent output. Additionally, all outputs, plans, and configurations
must be validated against schemas, policies, and security constraints.

Two subsystems address these concerns:
1. **ResultMerger** — Combines multiple task outputs into one `MergedResult`
2. **ValidationEngine** — Validates outputs, plans, security, and policies

## Decision

### ResultMerger: 7 Merge Strategies

The `ResultMerger` supports 7 strategies selected via the `MergeStrategy` enum:

| Strategy | Algorithm | Use Case |
|----------|-----------|----------|
| `WEIGHTED` | Weighted average of numeric outputs by task priority | Performance metrics, scores |
| `PRIORITY` | Highest-priority task's output wins | Hierarchical decisions |
| `CONSENSUS` | Majority agreement (mode) per field | Factual determinations, voting |
| `VOTING` | Weighted vote with quorum tracking | Democratic decisions |
| `BEST_OF_N` | Highest-confidence output wins | Quality-critical outputs |
| `CONCATENATE` | All outputs concatenated | Brainstorming, list generation |
| `SEMANTIC` | (Future) semantic deduplication merge | Knowledge synthesis (stub) |

**Strategy selection** defaults to `CONSENSUS` but can be overridden per merge
call. The strategy is selected declaratively — there is no auto-detection of the
best strategy.

**Conflict resolution** (`resolve_conflicts()`) identifies fields that differ
across task outputs and returns the conflicts with their frequency counts. The
caller can choose to accept the majority value, the highest-confidence value,
or fall back to a default.

**Confidence scoring** (`score_confidence()`) returns a 0.0–1.0 score based on:
- Agreement ratio across tasks (higher agreement → higher confidence)
- Number of tasks contributing to the merge (more tasks → higher confidence)
- Task priority weights (if available)

### ValidationEngine: Multi-Domain Validation

The `ValidationEngine` validates across four domains:

1. **Output Validation** (`validate_output`):
   - Optional schema validation (checks required fields exist)
   - Type checking of field values
   - Returns `ValidationResult` with `PASSED`/`WARNING`/`FAILED` status
   - Missing fields → `FAILED`; empty output → `WARNING`

2. **Plan Validation** (`validate_plan`):
   - Empty plan detection (no subtasks → `FAILED`)
   - Dependency integrity (all `depends_on` targets exist → `FAILED` if not)
   - Circular dependency detection via DFS-based cycle discovery:
     ```python
     def _has_circular_deps(tasks) -> bool:
         graph = {t.id: list(t.depends_on) for t in tasks}
         visited = set()
         path = set()
         def dfs(node):
             if node in path: return True  # Cycle found
             if node in visited: return False
             visited.add(node); path.add(node)
             for dep in graph.get(node, []):
                 if dfs(dep): return True
             path.remove(node)
             return False
         return any(dfs(n) for n in graph if n not in visited)
     ```

3. **Security Validation** (`validate_security`):
   - Health check (all agents must have `health > 0`)
   - Capability check (each agent must have at least one capability)

4. **Policy Validation** (`validate_policy`):
   - Maximum priority check (against `max_priority` threshold)
   - Timeout range check (within `min_timeout`/`max_timeout` bounds)

### Design Rationale

**Why 7 strategies rather than a single generic algorithm?** Different swarm
coordination patterns require fundamentally different merging approaches:
consensus for voting, weighted for performance aggregation, concatenate for
creative work. A single algorithm would force tradeoffs that don't fit all cases.

**Why DFS for cycle detection instead of Kahn's algorithm?** Kahn's algorithm
finds one valid topological order but doesn't directly label cycles. DFS with a
recursion stack provides clear cycle identification and can report the cycle
path for diagnostics.

## Consequences

- **Positive**: 7 strategies cover the known coordination patterns from the
  swarm domain model.
- **Positive**: Validation is comprehensive across four orthogonal domains.
- **Positive**: DFS cycle detection reports the exact cycle path for debugging.
- **Negative**: SEMANTIC strategy is a stub — true semantic dedup requires an
  LLM or embedding model and is deferred to a future milestone.
- **Negative**: Schema validation is basic field presence checking, not full
  JSON Schema compliance.
- **Negative**: Strategy selection is manual; no auto-recommendation based on
  task type or output shape.

## Related ADRs

- ADR-0016 (Swarm Orchestration Architecture) — Parent architecture
- ADR-0019 (Resilience & Recovery) — Retry/checkpoint integration with validation
