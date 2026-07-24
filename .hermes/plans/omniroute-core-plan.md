# OmniRoute Core — Implementation Plan

## Module Structure

```
src/agentic_os/
├── core/omniroute/
│   ├── __init__.py              # Module exports + factory orchestrator
│   ├── provider_registry.py     # ProviderRegistryPort impl
│   ├── model_registry.py        # ModelRegistryPort impl
│   ├── router.py                # RouterEnginePort impl (routing logic)
│   ├── routing_policies.py      # RoutingPolicyPort impl (policy CRUD + eval)
│   ├── failover.py              # CircuitBreakerPort impl
│   ├── budget.py                # BudgetEnginePort impl
│   ├── compression.py           # CompressionEnginePort impl
│   ├── gateway.py               # GatewayPort impl (multi-provider HTTP client)
│   ├── telemetry.py             # TelemetryPort impl
│   ├── health.py                # HealthPort impl
│   ├── metrics.py               # MetricsPort impl
│   ├── streaming.py             # StreamingPort impl
│   ├── authentication.py        # CredentialVaultPort impl
│   ├── discovery_bridge.py      # DiscoveryBridgePort impl
│   ├── websocket.py             # WebSocket server for real-time UI
│   ├── rest_api.py              # FastAPI router for OmniRoute REST endpoints
│   └── sqlite_storage.py        # SQLite persistence (shared by multiple ports)
```

## Dependency Graph

```
                     ┌─────────────────────┐
                     │   DiscoveryBridge   │
                     │  (syncs prod/models) │
                     └────────┬────────────┘
                              │ feeds
                              ▼
┌──────────────┐    ┌──────────────────────┐
│ CircuitBreaker│───▶│  ProviderRegistry   │
│ (tracks flrs) │    │  (prod CRUD+health) │
└──────────────┘    └───────────┬──────────┘
                               │ owns
                               ▼
┌──────────────┐    ┌──────────────────────┐
│  BudgetEngine │    │   ModelRegistry      │
│ (cost tracking)│    │  (model CRUD+search) │
└──────────────┘    └───────────┬──────────┘
                               │ queries
                               ▼
┌──────────────┐    ┌──────────────────────┐
│ RoutingPolicy │───▶│  RouterEngine        │
│ (pol CRUD+eval)│   │  (route decisions)   │
└──────────────┘    └───────────┬──────────┘
                               │ selects
                               ▼
┌──────────────┐    ┌──────────────────────┐
│ Compression  │───▶│     Gateway          │
│ (token save) │    │  (HTTP to LLM APIs)  │
└──────────────┘    └───────────┬──────────┘
                               │ exposes
                               ▼
┌──────────────┐    ┌──────────────────────┐
│  Telemetry   │    │    Streaming         │
│ (snapshots)  │    │ (SSE/WebSocket)      │
└──────────────┘    └───────────┬──────────┘
                               │
                               ▼
┌──────────────┐    ┌──────────────────────┐
│  Metrics     │    │   WebSocket          │
│ (counters)   │    │ (real-time UI relay) │
└──────────────┘    └──────────────────────┘

┌──────────────┐    ┌──────────────────────┐
│   Health     │    │    REST API          │
│ (subsys chk) │    │ (FastAPI routers)    │
└──────────────┘    └──────────────────────┘

┌──────────────┐
│  Auth/Creds  │
│ (vault impl) │
└──────────────┘

┌───────────────────┐
│  SQLite Storage   │
│ (shared backend)  │
└───────────────────┘
```

## Implementation Order

### Phase 4-A: SQLite Storage (foundation)

| Module | Depends On | Effort | Key Deliverable |
|--------|-----------|--------|-----------------|
| `sqlite_storage.py` | Nothing (pure persistence) | 1 day | Async SQLite via aiosqlite; tables for providers, models, policies, budget, circuit_breaker, telemetry; CRUD helpers; migrations |

**Depended on by:** provider_registry, model_registry, budget, policies, failover, telemetry

### Phase 4-B: Credential Vault

| Module | Depends On | Effort | Key Deliverable |
|--------|-----------|--------|-----------------|
| `authentication.py` | SQLiteStorage | 0.5 day | AES-256-GCM encryption at rest; api_key/oauth/bearer storage; validate() pings provider for 401 |

### Phase 4-C: Provider & Model Registries

| Module | Depends On | Effort | Key Deliverable |
|--------|-----------|--------|-----------------|
| `provider_registry.py` | SQLiteStorage, EventBus | 1 day | ProviderRegistryPort impl; CRUD; health updates; EventBus events (PROVIDER_REGISTERED, PROVIDER_FAILED, PROVIDER_HEALTH) |
| `model_registry.py` | SQLiteStorage, EventBus | 0.5 day | ModelRegistryPort impl; CRUD; search by capability; set_default() |

### Phase 4-D: Routing Policies

| Module | Depends On | Effort | Key Deliverable |
|--------|-----------|--------|-----------------|
| `routing_policies.py` | SQLiteStorage | 0.5 day | RoutingPolicyPort impl; policy CRUD; evaluate() ranks by cost/speed/capability weights |

### Phase 4-E: Circuit Breaker & Failover

| Module | Depends On | Effort | Key Deliverable |
|--------|-----------|--------|-----------------|
| `failover.py` | SQLiteStorage, EventBus | 0.5 day | CircuitBreakerPort impl; 3-state (CLOSED/HALF/OPEN); automatic half-open probes; EventBus events (FAILOVER recorded) |

### Phase 4-F: Budget Engine

| Module | Depends On | Effort | Key Deliverable |
|--------|-----------|--------|-----------------|
| `budget.py` | SQLiteStorage, EventBus | 0.5 day | BudgetEnginePort impl; record/summary/check_budget; monthly rollup; EventBus events (COST_RECORDED) |

### Phase 4-G: Router Engine

| Module | Depends On | Effort | Key Deliverable |
|--------|-----------|--------|-----------------|
| `router.py` | ProviderRegistry, ModelRegistry, RoutingPolicy, CircuitBreaker, BudgetEngine, EventBus | 1.5 days | RouterEnginePort impl; route() selects optimal provider/model; uses policy evaluation; respects circuit breaker state; checks budget before routing; emits RouteDecision |

### Phase 4-H: Compression Engine

| Module | Depends On | Effort | Key Deliverable |
|--------|-----------|--------|-----------------|
| `compression.py` | Nothing (pure algorithm) | 1 day | CompressionEnginePort impl; prompt truncation, history summarization, semantic compression (tiktoken-based), cache-aware, adaptive strategies |

### Phase 4-I: Gateway (API Client)

| Module | Depends On | Effort | Key Deliverable |
|--------|-----------|--------|-----------------|
| `gateway.py` | RouterEngine, CompressionEngine, CredentialVault, CircuitBreaker, Telemetry | 2 days | GatewayPort impl; HTTP client for OpenAI/Anthropic/OpenRouter/Ollama APIs; streaming support; retry with circuit breaker; compression integration; telemetry recording |

### Phase 4-J: Telemetry & Metrics

| Module | Depends On | Effort | Key Deliverable |
|--------|-----------|--------|-----------------|
| `telemetry.py` | SQLiteStorage | 0.5 day | TelemetryPort impl; snapshot() aggregates from SQLite counters; real-time failover event recording |
| `metrics.py` | Nothing (in-memory counters) | 0.5 day | MetricsPort impl; Counter/Gauge/Timer with OpenMetrics-compatible snapshot |

### Phase 4-K: Health

| Module | Depends On | Effort | Key Deliverable |
|--------|-----------|--------|-----------------|
| `health.py` | All other ports | 0.5 day | HealthPort impl; check() pings every subsystem via their health methods |

### Phase 4-L: Discovery Bridge

| Module | Depends On | Effort | Key Deliverable |
|--------|-----------|--------|-----------------|
| `discovery_bridge.py` | ProviderRegistry, ModelRegistry, RuntimeDiscovery, EventBus | 1 day | DiscoveryBridgePort impl; sync_providers() reads from RuntimeDiscovery and upserts into ProviderRegistry; watch() subscribes to DISCOVERY_* events |

### Phase 4-M: Streaming

| Module | Depends On | Effort | Key Deliverable |
|--------|-----------|--------|-----------------|
| `streaming.py` | EventBus | 0.5 day | StreamingPort impl; SSE/WebSocket session management; broadcast to topic-filtered clients |

### Phase 4-N: WebSocket Server

| Module | Depends On | Effort | Key Deliverable |
|--------|-----------|--------|-----------------|
| `websocket.py` | Streaming, EventBus | 0.5 day | WebSocket server for real-time OmniRoute dashboard; live route decisions, failover events, latency charts |

### Phase 4-O: REST API

| Module | Depends On | Effort | Key Deliverable |
|--------|-----------|--------|-----------------|
| `rest_api.py` | All ports | 1 day | FastAPI routers for all OmniRoute CRUD; provider management, model management, routing policies, budget views, telemetry, health |

### Phase 4-P: Factory Orchestrator

| Module | Depends On | Effort | Key Deliverable |
|--------|-----------|--------|-----------------|
| `__init__.py` | All modules | 0.5 day | `create_omniroute_engine(container, event_bus, discovery)` — builds all ports, registers in Container, replaces stubs |

## Pipeline Diagram

```
runtime_discovery
  │
  ▼
discovery_bridge ───▶ provider_registry ───▶ model_registry
                           │                      │
                           ▼                      ▼
                     circuit_breaker         routing_policies
                           │                      │
                           ▼                      ▼
                     budget_engine ───▶ router_engine
                                           │
                                           ▼
                                     compression_engine
                                           │
                                           ▼
                                        gateway
                                           │
                                           ▼
                                     ┌──────────┐
                                     │  LLM API  │
                                     │ (provider)│
                                     └──────────┘
                                           │
                                           ▼
                                     telemetry
                                           │
                                           ▼
                                     metrics ───▶ health
```

## Verification Plan

| Step | Command | Expected |
|------|---------|----------|
| Ruff | `uv run ruff check src/agentic_os/core/omniroute/` | All checks passed |
| Format | `uv run ruff format --check src/agentic_os/core/omniroute/` | Already formatted |
| Ty | `uv run ty check src/agentic_os/core/omniroute/` | All checks passed |
| Unit tests | `uv run pytest tests/test_omniroute/ -q` | All passed |
| Integration | `uv run pytest tests/test_omniroute_integration.py -q` | All passed |
| Regression | `uv run pytest tests/ -q --ignore=tests/test_desktop_stress.py` | All passed (≥2150) |
| Container | Verify `container.resolve(ProviderRegistryPort)` works | Returns real impl, not stub |
| Boot | Verify `cli.py serve --omniroute` starts without error | Kernel + OmniRoute healthy |

## Artifact Checklist (Final Acceptance)

- [ ] `core/omniroute/` — 18 modules fully implemented
- [ ] All 14 port protocols have real implementations (not stubs)
- [ ] Container registrations updated to use real implementations
- [ ] Gateway routes prompts to correct providers
- [ ] Router engine respects policies, budgets, circuit breakers
- [ ] EventBus v2 used for all OmniRoute events
- [ ] WebSocket streams route decisions live to Mission Control
- [ ] REST API exposes CRUD for providers, models, policies, budget
- [ ] Ruff clean, Ty clean, Bandit clean
- [ ] No regressions in existing tests (2150+)
- [ ] Mission Control, Desktop, all dashboards unchanged

> **Implementation may begin only after this plan is user-approved.**
