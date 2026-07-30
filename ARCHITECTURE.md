# Architecture

AgenticOS is a **local-first, event-bus-driven AI Agent Operating System**
built on a strict **hexagonal (clean) architecture**. Business logic depends on
*interfaces* (ports); concrete infrastructure lives behind those ports as
adapters. The composition root (`kernel.py`) is the only place that knows about
concrete classes.

## Layers

```
User / UI / CLI
      │  ports (interfaces)
      ▼
┌────────────────────────────────────────────────────────────┐
│  API (FastAPI) — REST + WebSocket live dashboard            │
└───────────────┬────────────────────────────────────────────┘
                │
   ┌────────────┼─────────────────────────────────────────┐
   │  CORE       │  orchestrator, registry, scheduler,      │
   │            │  health, recovery, providers/, capability/│
   │            │  memory/, security/                       │
   ├────────────┼─────────────────────────────────────────┤
   │  DOMAIN    │  Agent, Task, ProviderConfig, ModelInfo,  │
   │            │  AgentSpec, MemoryItem, Security entities  │
   ├────────────┼─────────────────────────────────────────┤
   │  PORTS     │  EventBus, ProviderAdapter, Plugin, and   │
   │            │  the four Phase-2 subsystem ports          │
   ├────────────┼─────────────────────────────────────────┤
   │  ADAPTERS  │  bus (local/redis/nats), providers,        │
   │            │  capability, memory, security              │
   └────────────┴─────────────────────────────────────────┘
```

| Layer | Path | Responsibility |
|-------|------|----------------|
| `domain/` | entities + value objects (Pydantic v2) | state, no behavior beyond validation |
| `ports/` | interfaces (`Protocol`) | contracts; no implementation |
| `core/` | orchestration + subsystem logic | depends only on ports |
| `adapters/` | concrete infrastructure | bus, providers, capability, memory, security |
| `api/` | FastAPI app | REST + WebSocket (an adapter over the core ports) |
| `kernel.py` | composition root | wires ports → concrete impls → `Platform` |

## Event Bus (frozen abstraction)

One `EventBus` port, three interchangeable adapters selected by `BUS_TYPE`:

| Adapter | Use | Default in |
|---------|-----|-----------|
| `LocalBus` | in-process asyncio | dev / CI |
| `RedisStreamsBus` | Redis Streams (persistent, replayable) | **production** |
| `NatsJetStreamBus` | NATS JetStream (alt prod) | prod (opt-in) |

Every bus message is wrapped in an `EventEnvelope` (id, type, source,
timestamp, topic, payload). Topics are centralized in `domain/events.py`.

## Phase 3B Subsystems (v0.4.0)

| Subsystem | Ports | Core Impl | Status |
|-----------|-------|-----------|--------|
| Workflow Engine | `WorkflowEnginePort` | `WorkflowEngineImpl` — DAG execution, topological sort, versioning, replay, approval gates | ✅ Verified |
| Pipeline Engine | `PipelineEnginePort` | `PipelineEngineImpl` — stage execution, scheduling, retry, rollback, parallel stages | ✅ Verified |
| Observability Framework | `TracingPort`, `MetricsPort`, `LoggingPort` | `InMemoryTracing`, `InMemoryMetrics`, `InMemoryStructuredLogging` (Prometheus/OTel bridges available) | ✅ Verified |
| MCP Framework | `MCPRegistryPort` | domain models + ports + full runtime (registry, client, manager, security, SDK) | ✅ Verified |
| Plugin Framework | `PluginRegistryPort` | `PluginSDK`, `PluginValidator`, `PluginRegistryClient`, `generate_plugin_template` | ✅ Domain/Ports/SDK |

All core engines achieve >90% test coverage with comprehensive unit, integration, and stress tests.

## Phase 4, Milestone 3: MCP Runtime Foundation (v0.7.0)

The MCP Runtime Foundation completes the MCP Framework from Phase 3B into a
production-ready runtime with registry, client, manager, security, and SDK layers.

### Architecture Layers

```
┌─────────────────────────────────────────────┐
│              MCP SDK                         │
│  McpServerSdk · ToolSdk · ResourceSdk ·    │
│  PromptSdk · Auth · Testing · Validation     │
├─────────────────────────────────────────────┤
│              MCP Core Runtime                │
│  MCPRegistryImpl · MCPClient · MCPManager   │
│  MCPSecurity · EventBus integration          │
├─────────────────────────────────────────────┤
│              MCP Ports                       │
│  MCPRegistryPort · MCPTransportPort          │
├─────────────────────────────────────────────┤
│              MCP Domain                      │
│  MCPServerDetail · MCPTool · MCPResource    │
│  MCSServerConfig · MCPServerCreate/Update    │
│  MCPPermissionMapping · MCPSession           │
└─────────────────────────────────────────────┘
```

### Components

| Component | Path | Responsibility |
|-----------|------|----------------|
| Domain Models | `domain/mcp.py` | Frozen dataclasses for server, tool, resource, prompt, session, permission entities |
| Port Interfaces | `ports/mcp.py` | MCPRegistryPort, MCPTransportPort runtime-checkable protocols |
| Registry | `core/mcp/registry.py` | In-memory async server CRUD, lifecycle, tool/resource/prompt management, EventBus integration |
| Client | `core/mcp/client.py` | stdio/subprocess, SSE, Streamable HTTP transport client with auto-reconnect |
| Manager | `core/mcp/manager.py` | Lifecycle orchestration, health monitoring, session tracking |
| Security | `core/mcp/security.py` | 20 authorization methods wrapping SecurityFramework |
| SDK Server | `sdk/mcp/server.py` | McpServerSdk — fluent server lifecycle |
| SDK Tool | `sdk/mcp/tool.py` | ToolBuilder, ToolSdk — tool construction and invocation |
| SDK Resource | `sdk/mcp/resource.py` | ResourceSdk — resource reading and subscription |
| SDK Prompt | `sdk/mcp/prompt.py` | PromptSdk — prompt listing and retrieval |
| SDK Auth | `sdk/mcp/auth.py` | McpAuthHelper — MCP authorization helpers |
| SDK Config | `sdk/mcp/config.py` | McpConfigHelper — server configuration building |
| SDK Registration | `sdk/mcp/registration.py` | RegistrationHelper — server registration/unregistration |
| SDK Validation | `sdk/mcp/validation.py` | McpValidator — MCP protocol validation |
| SDK Testing | `sdk/mcp/testing.py` | McpTestHelper, FakeMCPRegistry, FakeMCPManager |

### Key Design Decisions

- **Immutable domain models** — All dataclasses are frozen; state transitions use
  `with_*` builder methods returning new instances.
- **Registry as event source** — Every lifecycle transition emits an EventBus event.
- **Lazy transport binding** — MCPClient doesn't connect until `connect()` is called.
- **Per-server async locks** — Thread-safe lifecycle transitions via `asyncio.Lock`.
- **Security as a gate** — MCPSecurity wraps every MCP operation with authorization.

### Performance

All MCP operations are sub-millisecond:
- Domain model instantiation: <4 µs
- State transition (`with_status`): <1 µs
- Registry register/get/unregister: <57 µs
- Serialization to dict/JSON: <7 µs

See ADRs `0011`–`0015` for detailed design rationale.

## Phase 4 Subsystem (v0.5.0, M1)

| Subsystem | Ports | Core Impl | Status |
|-----------|-------|-----------|--------|
| Universal Execution Engine Framework | `ExecutionEnginePort`, `RuntimeManagerPort`, `DiscoveryProvider` | `RuntimeManager` + `RuntimeRegistryImpl` + `CapabilityNegotiator` + `DiscoveryEngine` + `CompositeEngine` | ✅ Verified |

The Universal Execution Engine Framework is a hexagonal abstraction layer where
ANY execution engine (MCP, Docker, WSL, Claude Code, subprocess, cloud API)
implements a single `ExecutionEnginePort` interface (~22 methods). The kernel
discovers, binds, orchestrates, supervises, and optimizes engines through this
shared contract. Adding a new engine = one new adapter file = zero kernel changes.

**Key components:**
- **`ExecutionEnginePort`** (ports) — universal interface: lifecycle, execution,
  health, benchmark, telemetry, compatibility, workspace, recovery.
- **`RuntimeManager`** (core) — high-level subsystem wiring registry + discovery +
  negotiator + adapters. Single integration point in the kernel.
- **`RuntimeRegistryImpl`** (core) — in-memory engine CRUD, capability search,
  health caching, session tracking, EventBus emissions.
- **`CapabilityNegotiator`** (core) — scored matching (required 10x weighting,
  confidence-based filtering, TTL cache).
- **`DiscoveryEngine`** (core) — multi-provider orchestration with deduplication
  and confidence scoring.
- **`CompositeEngine`** (core) — combines multiple engines behind one port for
  fallback, load balancing, and fan-out routing.
- **`GenericExecutionEngine`** (adapter) — reference adapter demonstrating the
  port contract with echo/ping/sleep/info/fail actions.
- **`PathDiscovery`** (adapter) — scans system PATH for known AI executables.

**Phase 4 event topics:** 14 new `engine.*` topics on the EventBus.

## Phase 4, Milestone 4: Swarm Orchestration Engine (v0.8.0)

The Swarm Orchestration Engine provides multi-agent coordination with dynamic
goal decomposition, capability-based task assignment, and fault-tolerant
execution. It is built as 12 hexagonal subsystems behind a single
`OrchestrationFramework` facade.

### Architecture

```
OrchestrationFramework (facade)
 ├── SwarmPlanner         — analyze_goal, create_plan, resolve_dependencies, parallelize_plan
 ├── SwarmScheduler       — topological sort (Kahn's algorithm), dispatch, schedule query
 ├── SwarmSupervisor      — monitor_execution, detect_failures/deadlocks, restart/reassign
 ├── ResultMerger         — 7 merge strategies: weighted, priority, consensus, voting, best-of-N, concatenate, semantic
 ├── ValidationEngine     — schema, plan integrity, circular-dep (DFS), security, policy validation
 ├── RetryManager         — exponential backoff with 10% jitter, per-task retry tracking
 ├── FailureRecovery      — recover_task (reassign), recover_plan (with/without checkpoint), rollback
 ├── CheckpointManager    — save/restore/list/delete execution snapshots
 ├── AgentSelector        — weighted scoring: 50% capability, 20% health, 15% latency, 15% status
 ├── MetricsEngine        — collect_metrics, record_timeline, get_timeline
 ├── CostTracker          — estimate_cost, track_cost, get_costs
 └── PerformanceAnalyzer  — success_rate, bottleneck detection, efficiency score
```

### Domain Models

All 14 new models are frozen dataclasses in `domain/orchestration.py`:

| Model | Key Fields |
|-------|-----------|
| `SwarmProfile` | name, description, topology, max_agents, capabilities |
| `AgentDescriptor` | agent_id, name, capabilities, health, role, latency |
| `OrchestrationGoal` | id, description, complexity, required_capabilities |
| `AgentTask` | id, status, assigned_agent, depends_on, output, priority, timeout |
| `OrchestrationPlan` | id, goal_id, subtasks, schedule, execution_config |
| `ExecutionStage` | id, plan_id, tasks, status, started_at, completed_at |
| `MergedResult` | output, confidence, conflicts, strategy_used |
| `ValidationResult` | status, score, errors, warnings |
| `RetryPolicy` | max_retries, base_delay, backoff_multiplier, max_delay, jitter |
| `Checkpoint` | id, plan_id, task_states, partial_outputs, timestamp |
| `ExecutionMetrics` | total/completed/failed tasks, duration, avg_latency |
| `ExecutionCost` | plan_id, agent_id, cost, currency, timestamp |

### Coordination Patterns

The engine supports 6 coordination patterns via the `CoordinationPattern` enum:

| Pattern | Behavior |
|---------|----------|
| `SEQUENTIAL` | Tasks execute one after another, in schedule order |
| `PARALLEL` | All tasks execute concurrently |
| `FAN_OUT` | One task fans out to multiple agents in parallel |
| `FAN_IN` | Multiple agent results merge into one |
| `HIERARCHICAL` | Tasks organized in a tree with parent-child dependencies |
| `VOTING` | Agents vote on a decision; results merged by consensus |

### REST API

The engine is exposed through the FastAPI control plane at `/api/v1/swarm/`:
- `POST /profiles` — Create swarm profile
- `POST /planner/analyze` — Analyze a goal
- `POST /planner/plan` — Create a plan
- `POST /scheduler/schedule` — Schedule tasks
- `POST /supervisor/monitor` — Monitor execution
- `POST /merger/merge` — Merge task results
- `POST /validation/validate` — Validate output/plan/security/policy
- `POST /checkpoints/` — Manage checkpoints
- `POST /selector/select` — Select best agent
- `GET /metrics/` — Query metrics and cost data

### Event Topics

40+ new orchestration topics on the EventBus across all subsystems (see
`domain/events.py` for the full list).

### Test Coverage

82 tests covering all 12 subsystems + domain models + event publishing, with
mock runtimes and registries for deterministic async testing.

### Key Design Decisions

- **Frozen dataclasses** (not Pydantic): state transitions return new instances
  via `with_*()` methods.
- **Rule-based planning**: deterministic, no LLM call overhead during
  decomposition.
- **Kahn's algorithm**: O(V+E) topological sort with ready-set semantics.
- **DFS cycle detection**: reports exact cycle path for diagnostics.
- **7 merge strategies**: declaratively selected per merge call.
- **Exponential backoff + 10% jitter**: prevents thundering-herd on transient
  failures.
- **Weighted agent scoring**: 50% capability + 20% health + 15% latency + 15%
  status.
- **In-memory checkpoints**: process-local; persistent storage deferred.
- **Event-driven resilience**: all recovery actions publish bus events for
  external monitoring.

See ADRs `0016`–`0019` for detailed design rationale.

## Phase 2 Subsystems (frozen interfaces)

| Subsystem | Ports | Default impl |
|-----------|-------|-------------|
| Provider Management | `ProviderManager`, `ModelManager`, `SecretStore`, `ApiKeyVault`, `ProviderHealthMonitor`, `RoutingPolicy`, `CostTracker`, `RateLimitMonitor`, `FailoverPolicy` | encrypted Fernet vault, OpenAI-compatible adapter |
| Memory System | `MemoryStore`, `VectorStore`, `KnowledgeGraph`, `MemoryManager` | in-memory store + cosine vector + adjacency graph |
| Capability Engine | `Capability`, `CapabilityRegistry`, `AgentComposer` | 11 built-ins + intent composer |
| Security Framework | `SecretsManager`, `AccessControl`, `WorkspaceIsolation`, `ToolPermissions`, `ApprovalGate`, `AuditLog` | RBAC + workspace isolation + approval gate + audit |

See `docs/adr/0001`–`0019` for the full set of Architecture Decision Records.

## Phase 3B Engine Control Flow

### Workflow Execution
`WorkflowCreate → WorkflowEngineImpl.create_workflow() → ACTIVATE → execute_workflow() → topological_sort() → [execute_node() for each ready node] → EventBus emissions (workflow.*)`

### Pipeline Execution
`PipelineCreate → PipelineEngineImpl.create_pipeline() → ACTIVATE → execute_pipeline() → [execute_stage() for each ready stage, respecting depends_on] → retry policy evaluation → EventBus emissions (pipeline.*)`

### Observability (cross-cutting)
All engines emit structured events through the EventBus. The `InMemoryTracing`, `InMemoryMetrics`, and `InMemoryStructuredLogging` implementations are wired via the observability ports for development and testing; production deployments can substitute OpenTelemetry and Prometheus adapters.

## Control Flow

### Task execution (Phase 1)
`Planner → Task Dispatcher → Provider Adapter → Event Bus → Supervisor ↔
Health Monitor → Recovery Manager → WebSocket Dashboard`.

### Agent composition (Phase 2)
`Task → CapabilityEngine.spec_for_task(intent) → AgentSpec` (capabilities +
provider/model). Sensitive capabilities are gated by the Security Framework's
`authorize()` pipeline (RBAC → approval gate → audit) before execution.

### Memory lifecycle
`write() → retention (TTL/max-size) → MEMORY_WRITTEN` and eviction →
`MEMORY_EVICTED`, both observable on the bus.

## Configuration

All knobs are environment-driven via `pydantic-settings` (`config.py`). Sensible
defaults boot the system on the in-process bus with the mock provider — zero
infrastructure. See `.env.example`.

## Technology Stack

Python 3.13+, FastAPI, asyncio/AnyIO, Pydantic v2, pydantic-settings,
structlog, Prometheus client, httpx, `cryptography` (Fernet), uv, Docker/WSL2.

## Diagrams

C4 diagrams (mermaid) live in [`docs/c4/diagrams.md`](docs/c4/diagrams.md).

## Autonomous Intelligence Layers (Phases 11–16)

On top of the core hexagonal architecture, AgenticOS ships five
event-driven intelligence layers. Each is a self-contained package
under `src/agentic_os/core/` that subscribes to existing EventBus
topics and publishes new ones. No layer duplicates the discovery
pipeline, BrainRegistry, or EventBus — they are pure consumers.

### Layer overview

```
┌────────────────────────────────────────────────────────────────┐
│  Phase 16 — Cluster Federation (core/cluster/)                 │
│  ClusterController · FederationManager · DistributedRegistry   │
│  GlobalMissionScheduler · ConsensusManager · FailoverEngine    │
│  ClusterTopology · FederatedKnowledgeGraph                     │
├────────────────────────────────────────────────────────────────┤
│  Phase 15 — Autonomous Ecosystem (core/ecosystem/)             │
│  EcosystemController · EcosystemManager · CapabilityGraph      │
│  CollaborationNetwork · EvolutionEngine · TaskMarketplace      │
├────────────────────────────────────────────────────────────────┤
│  Phase 14 — Swarm Execution (core/orchestration/)              │
│  SwarmCoordinator · ConsensusManager · SharedMissionMemory     │
│  DynamicRoleAssigner (8 roles) · Failure Recovery              │
├────────────────────────────────────────────────────────────────┤
│  Phase 13 — Executive Orchestration (core/executive/)          │
│  ExecutiveOrchestrator · Policy · ResourceAllocation           │
│  MissionSupervision · DynamicPriority                          │
├────────────────────────────────────────────────────────────────┤
│  Phase 12 — Cognitive Intelligence (core/cognitive/)           │
│  CognitiveController · WorldModel · KnowledgeGraph             │
│  StrategicPlanner · PredictionEngine · ExperienceReplay        │
│  EvaluationEngine · ImprovementPlanner · ObjectiveManager      │
├────────────────────────────────────────────────────────────────┤
│  Phase 11 — Executive Intelligence (core/executive/)           │
│  ExecutiveController · GoalManager · DecisionEngine            │
│  ReflectionEngine · ExecutiveMemory                            │
├────────────────────────────────────────────────────────────────┤
│  Phase 6 — Discovery + BrainRegistry (core/discovery/, brains/)│
│  LocalDiscoveryService → EventBus → BrainRegistry              │
├────────────────────────────────────────────────────────────────┤
│  Phases 1–5 — Core Platform                                    │
│  EventBus · Planner · Dispatcher · Supervisor · Health         │
│  Recovery · Providers · Capability · Memory · Security · MCP   │
└────────────────────────────────────────────────────────────────┘
```

### Phase 11 — Executive Intelligence

`core/executive/` — long-running executive intelligence that turns
missions into goals, selects runtimes, and reflects on outcomes.

- `ExecutiveController` — subscribes to 10 EventBus topics, owns the
  executive subsystem lifecycle.
- `GoalManager` — 12 operations (activate/cancel/suspend/reprioritize/
  split/merge/archive), 10 goal states.
- `DecisionEngine` — 7-factor runtime selection (health, latency,
  capability match, availability, historical success, load, confidence)
  with `risk_factors` dict + human-readable `reasoning`.
- `ReflectionEngine` — 12-field post-mission analysis (success_factors,
  failures, improvements, routing_issues, capability_gaps, etc.).
- `ExecutiveMemory` — semantic indexes over the existing MemoryManager.

### Phase 12 — Cognitive Intelligence

`core/cognitive/` — autonomous cognitive feedback loop.

- `CognitiveController` — subscribes to `brain.*` + `mission.*` events.
  On mission completion, auto-populates KnowledgeGraph and triggers
  cognitive feedback.
- `WorldModel` — subscribes to 8 brain.*/mission.* topics, publishes
  `cognitive.world.updated`.
- `KnowledgeGraph` — entities + relations, BFS traversal, impact analysis.
- `StrategicPlanner`, `PredictionEngine`, `ExperienceReplay`,
  `EvaluationEngine`, `ImprovementPlanner`, `ObjectiveManager`,
  `CognitiveScheduler` (120s cycle).

### Phase 13 — Executive Orchestration

`core/executive/orchestrator.py` + `phase13_domain.py` — extends the
executive layer with world state, policies, resource allocation, and
mission supervision. 9 API endpoints, 12 `executive.*` events.

### Phase 14 — Swarm Execution

`core/orchestration/swarm_coordinator.py` — collaborative agent fabric.

- `SwarmCoordinator` — wraps the existing `SwarmManager` with
  BrainRegistry-driven team formation, consensus, shared memory, and
  failure recovery.
- `ConsensusManager` — majority / weighted / confidence / leader-override.
- `SharedMissionMemory` — shared context + working + decision memory.
- `DynamicRoleAssigner` — 8 roles (leader/planner/researcher/coder/
  reviewer/validator/executor/observer).
- Failure recovery: `brain.removed` → swarm detects → finds replacement
  from BrainRegistry → continues execution.

### Phase 15 — Autonomous Ecosystem

`core/ecosystem/` — turns the platform into a continuously
self-improving operating system.

- `EcosystemManager` — top-level coordinator. Derives all state from
  `BrainRegistry` + `EventBus`. Owns the sub-components below.
- `CapabilityGraph` — 5 node types (Brain/Capability/Mission/Goal/
  Swarm) + 6 edge types (provides/depends_on/learned/shares/
  collaborates_with/executed). Auto-updates from brain.*/mission.*/swarm.*
  events.
- `CollaborationNetwork` — directed trust graph with EMA-weighted
  confidence (α=0.3). Updates after every mission.
- `EvolutionEngine` — 4 analyzers: capability gaps, routing
  optimizations, collaboration opportunities, performance optimizations.
  Produces `EvolutionRecommendation` objects with priority/confidence/
  expected_impact.
- `TaskMarketplace` — global task market with deterministic 6-factor
  bid selection (capability_match/health/latency/availability/
  historical_success/trust). 5 strategies: balanced/capability/
  latency/health/trust.
- Continuous self-optimization: every completed mission auto-triggers
  Reflection → Evaluation → Prediction → Learning → Capability update →
  Evolution recommendation → Executive optimization → Swarm optimization.

### Phase 16 — Distributed Runtime Federation

`core/cluster/` — multi-host cluster coordination.

- `ClusterFederationManager` — remote node discovery, topology,
  heartbeat loop (30s), stale detection (90s), deterministic leader
  election (health desc → brain_count desc → node_id asc).
- `DistributedBrainRegistry` — wraps `BrainRegistry` (canonical for
  local brains) + adds remote brain tracking with idempotent sync.
- `GlobalMissionScheduler` — deterministic 9-factor cluster-wide
  scoring (health + latency + availability + historical_success +
  cluster_load + memory + provider + confidence + capability_match).
  Weights sum to 1.0; ties broken by node_id then brain_id.
- `ClusterConsensusManager` — 5 consensus types: majority, weighted,
  confidence (≥0.6 threshold), leader-decides, quorum.
- `FailoverEngine` — 5 triggers (node_offline/runtime_offline/
  high_latency/mission_failed/network_partition/manual) → 5 actions
  (quarantine_node/replace_runtime/elect_replacement/reassign_mission/
  resume_execution). Auto-finds replacement via GlobalMissionScheduler.
- `ClusterTopology` — live graph of hosts/nodes/connections with
  leader/quorum tracking.
- `FederatedKnowledgeGraph` — extends `CapabilityGraph` with cross-host
  nodes (node_id:brain_id naming), cluster capability index, global
  impact analysis (which nodes at risk if a capability disappears).

Single-node deployments are fully backward compatible: the local node
is auto-registered as ACTIVE + LEADER on startup, quorum_size=1, all
cluster operations work with cluster_size=1.

### Event flow (all layers)

```
LocalDiscoveryService
    │ publishes brain.discovered/registered/updated/removed
    ▼
EventBus (LocalBus)
    │ fan-out to all subscribers via asyncio.create_task
    ▼
┌─────────────────────────────────────────────────────┐
│ BrainRegistry     (canonical runtime source)         │
│ BrainDiscoveryBridge (routes AGENT_REMOVED → unregister)│
│ ExecutiveController (subscribes 10 topics)           │
│ CognitiveController (subscribes 6 topics)            │
│ SwarmCoordinator   (subscribes brain.removed)        │
│ EcosystemController (subscribes 6 topics)            │
│ ClusterController  (subscribes 6 topics)             │
│ DashboardBroadcaster (subscribes 129 topics)         │
└─────────────────────────────────────────────────────┘
    │
    ▼
DashboardBroadcaster
    │ fans out to all WebSocket clients
    ▼
Mission Control Store (Zustand)
    │ ingest(event) → switch(topic) → update slice
    ▼
React UI (live re-render)
```
