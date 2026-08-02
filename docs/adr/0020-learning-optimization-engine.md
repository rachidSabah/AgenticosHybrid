# ADR-0020: Learning & Optimization Engine

- Status: Accepted
- Date: 2026-07-19

## Context

Phase 4 delivered the Execution Engine Framework, MCP Runtime (Phase 4, M3), and
Swarm Orchestration Engine (Phase 4, M4, v0.8.0). These subsystems produce a rich
stream of execution data — task durations, failure modes, cost profiles, routing
outcomes — that is currently discarded. Without a **Learning & Optimization Engine**,
the system cannot:

- Accumulate experience across executions to improve routing decisions
- Detect performance degradation or anomalous behavior before it impacts users
- Benchmark engines against each other to guide capability-aware selection
- Predict execution outcomes (duration, cost, success probability) from history
- Generate and apply actionable recommendations for configuration improvement
- Extract reusable knowledge patterns from operational experience

The Learning & Optimization Engine (Phase 5, v0.9.0) fills this gap.

## Decision

Adopt a **hexagonal architecture** with 6 core subsystems wired through a
`LearningManager` composition root:

```
 ┌──────────────────────────────────────────────────────────┐
 │                    REST API (FastAPI)                      │
 ├──────────────────────────────────────────────────────────┤
 │                     LearningManager                         │
 │  ┌────────────┐ ┌──────────────┐ ┌──────────────────┐    │
 │  │ KnowledgeBase│ │AnalyticsEngine│ │ BenchmarkEngine  │    │
 │  ├────────────┤ ├──────────────┤ ├──────────────────┤    │
 │  │ Patterns   │ │ Engine Perf  │ │ Run / Compare    │    │
 │  │ Experiences│ │ Trends       │ │ History / Top    │    │
 │  │ Prune      │ │ Capabilities │ │ Scores           │    │
 │  └────────────┘ └──────────────┘ └──────────────────┘    │
 │  ┌────────────┐ ┌──────────────┐ ┌──────────────────┐    │
 │  │Prediction  │ │Optimization  │ │ LearningEvent    │    │
 │  │Engine      │ │Engine        │ │ Publisher        │    │
 │  ├────────────┤ ├──────────────┤ ├──────────────────┤    │
 │  │ Duration   │ │ Analysis     │ │ 13 EventBus      │    │
 │  │ Cost       │ │ Routing      │ │ topics           │    │
 │  │ Success    │ │ Recs/Policies│ │                  │    │
 │  │ Resource   │ │ History      │ │                  │    │
 │  └────────────┘ └──────────────┘ └──────────────────┘    │
 ├──────────────────────────────────────────────────────────┤
 │              18 Domain Models (frozen dataclasses)         │
 ├──────────────────────────────────────────────────────────┤
 │          6 Port Interfaces (runtime-checkable protocols)  │
 └──────────────────────────────────────────────────────────┘
```

### Domain Models

All 18 models are **frozen dataclasses** with `to_dict()` serialization,
identical to the pattern established in ADR-0016:

| Model | Purpose |
|-------|---------|
| `ExecutionHistory` | Single execution record with full metrics |
| `ExecutionProfile` | Aggregated profile over a time window |
| `BenchmarkRecord` | Single benchmark measurement result |
| `OptimizationRecommendation` | Target-specific optimization suggestion |
| `RoutingDecision` | Record of an optimizer routing choice |
| `CapabilityScore` | Engine capability score in a specific area |
| `EnginePerformance` | Aggregated per-engine metrics |
| `WorkflowPerformance` | Aggregated per-workflow metrics |
| `SwarmPerformance` | Aggregated per-swarm metrics |
| `FailurePattern` | Identified execution failure pattern |
| `RecoveryPattern` | Identified successful recovery pattern |
| `LearningSnapshot` | Point-in-time state snapshot |
| `LearningStatistics` | Aggregated learning process stats |
| `OptimizationPolicy` | Configuration guiding optimization behavior |
| `Prediction` | Predicted execution characteristic |
| `Recommendation` | User-facing actionable recommendation |
| `ExperienceRecord` | Single learning experience (RL-style) |
| `KnowledgePattern` | Extracted knowledge from experience analysis |

Enums: `ExecutionOutcome`, `OptimizationGoal`, `RecommendationPriority`,
`PredictionStatus`, `TrendDirection`.

### Port Interfaces (Protocols)

| Port | Methods | Purpose |
|------|---------|---------|
| `AnalyticsPort` | 11 methods | Aggregate performance, trends, capability scores |
| `BenchmarkPort` | 7 methods | Run benchmarks, compare engines, history/scores |
| `PredictorPort` | 7 methods | Predict duration, cost, success, resource usage |
| `OptimizerPort` | 12 methods | Analyze, route, generate/apply/dismiss recommendations, policy CRUD |
| `LearningEnginePort` | 12 methods | Record/get/list executions, detect patterns, knowledge management |
| `KnowledgeBasePort` | 6 methods | Store/get/query patterns and experiences, prune |

### Core Subsystems

#### KnowledgeBase
In-memory store for `KnowledgePattern` and `ExperienceRecord` objects. Supports
querying by field matching, filtering by minimum confidence, and pruning by age
or confidence. `LearningStatistics` computed on-demand. Used as the canonical
store for all execution history (serialized as experience records with their
full observation dict).

#### AnalyticsEngine
Aggregates `ExecutionHistory` records into `EnginePerformance`,
`WorkflowPerformance`, and `SwarmPerformance` views. Computes `PerformanceTrend`
with direction detection (improving/degrading/stable) across configurable time
windows. Provides capability scoring, top-engine ranking, and on-demand
`LearningSnapshot` / `LearningStatistics` generation.

#### BenchmarkEngine
Generates synthetic benchmark measurements (score, latency, cost, reliability,
memory, CPU, capability coverage). In production this would dispatch actual
workloads; the in-memory implementation produces realistic random values for
development and testing. Supports comparison across engines, history queries,
and top-score ranking.

#### PredictionEngine
Applies simple statistical models (mean, standard deviation, confidence
intervals) to historical execution data. Four prediction types:

- **duration** — average latency from matching execution records
- **cost** — average cost from cost-bearing records
- **success_probability** — ratio of successes to total attempts
- **resource_usage** — average of memory and CPU percent values

Prediction confidence levels: `HIGH_CONFIDENCE` (10+ samples),
`MEDIUM_CONFIDENCE` (5-9), `LOW_CONFIDENCE` (3-4), `INSUFFICIENT_DATA` (<3).

A production deployment would replace this with a proper ML model.

#### OptimizationEngine
Provides heuristic-based performance analysis and routing optimization:

- **Analysis:** Detects high latency (>1000ms) and low success rate (<80%)
  patterns, generating `OptimizationRecommendation` entries with priority levels.
- **Routing:** Selects the lowest-latency engine from candidates with
  performance data, falling back to the first available engine when no data
  exists.
- **Recommendations:** Full CRUD for `Recommendation` objects with apply/dismiss
  lifecycle tracking.
- **Policies:** Full CRUD for `OptimizationPolicy` — guides optimization behavior
  with goals (latency, cost, balanced, etc.), learning rate, and exploration rate.

### EventBus Integration

13 topics added to the canonical `Topic` enum (domain/events.py):

| Topic | Trigger |
|-------|---------|
| `learning.execution_recorded` | Execution recorded |
| `learning.profile_updated` | Execution profile recomputed |
| `learning.recommendation_generated` | Recommendation created |
| `learning.recommendation_applied` | Recommendation applied |
| `learning.benchmark_completed` | Benchmark measurement done |
| `learning.prediction_made` | Prediction generated |
| `learning.pattern_detected` | Failure/recovery pattern identified |
| `learning.knowledge_extracted` | Knowledge pattern extracted |
| `learning.routing_decision` | Routing decision made |
| `learning.optimization_applied` | Policy optimization triggered |
| `learning.anomaly_detected` | Anomalous metric detected |
| `learning.trend_changed` | Performance trend direction changed |
| `learning.experience_recorded` | Experience stored in knowledge base |

The `LearningEventPublisher` bridges these onto the EventBus as
`EventEnvelope` objects with topic routing. The `DashboardBroadcaster`
subscribes to all learning topics for live Mission Control updates.

### REST API

~35 endpoints under `/api/learning/` covering:
- Execution history CRUD and filtering
- Failure/recovery pattern listing
- Knowledge pattern queries
- Predictions (duration, cost, success, resource, batched)
- Recommendations (CRUD, apply/dismiss, list with filters)
- Routing decisions and history
- Benchmarks (run, get, list, compare, history, top scores)
- Performance analytics (engine, workflow, swarm, trends, capability)
- Policies (CRUD)
- Statistics and snapshots
- Comprehensive `analyze` endpoint

All routes accept and return JSON dicts via `to_dict()` serialization, matching
the existing pattern from Phase 4 endpoints.

### Composition Root

`LearningManager` is the single entry point:
- Composes all 6 sub-engines using `@dataclass` fields with lazy construction
- `start()` builds subsystems if not injected, `stop()` marks as not running
- `_running` bool prevents double-starts
- Property accessors (`.kb`, `.analytics`, `.benchmark`, `.predictor`, `.optimizer`)
  provide type-safe access to subsystems
- Delegates all operations to sub-engines, handling cross-subsystem data flow
  (e.g., feeding analytics results into the optimizer before analysis)

### Kernel Integration

`Kernel._build_learning_framework()` constructs the `LearningManager` with the
shared EventBus and gates on `settings.learning_enabled`. Start/stop lifecycle
calls in `Kernel.start()` / `.stop()` (learning started after MCP, stopped
before MCP shutdown). The `Platform` dataclass carries the manager so the API
layer receives it.

## Consequences

- **Positive**: Execution data that was previously discarded is now accumulated,
  analyzed, and acted upon.
- **Positive**: Routing decisions improve over time as the knowledge base grows.
- **Positive**: Predictive capabilities enable proactive management (e.g., cost
  forecasting, anomaly detection before failures).
- **Positive**: Benchmark-driven comparisons provide objective engine selection
  guidance.
- **Positive**: Recommendations provide a closed feedback loop between analysis
  and action.
- **Positive**: All 6 subsystems are independently testable with simple
  in-memory state.
- **Negative**: Statistical prediction models are primitive — production
  deployments will need ML model integration.
- **Negative**: No persistent storage — all state is in-memory and lost on
  restart (deferred to a future database-backed milestone).
- **Negative**: No automated curation of knowledge patterns — patterns accumulate
  until pruned by age/confidence thresholds.
- **Negative**: `FailurePattern` and `RecoveryPattern` detection are placeholder
  implementations (return empty lists) — real pattern detection is deferred.

## Related ADRs

- ADR-0002 (Hexagonal Architecture) — The parent architectural pattern
- ADR-0001 (Abstract Event Bus) — Event bus integration
- ADR-0010 (Mission Control) — Dashboard visualization of learning events
- ADR-0016 (Swarm Orchestration Architecture) — Consumer of optimization/routing
- ADR-0019 (Resilience & Recovery) — Consumer of failure pattern detection
