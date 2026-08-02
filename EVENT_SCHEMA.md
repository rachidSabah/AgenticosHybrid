# Event Schema

Canonical event contract for the AgenticOS Event Bus. Every message on the bus
is wrapped in an `EventEnvelope`:

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` (hex) | Unique event id (uuid4). |
| `type` | `str` | Logical event type, e.g. `agent.composed`, `memory.written`. |
| `source` | `str` | Producer component, e.g. `capability-engine`, `memory-manager`. |
| `topic` | `str` | Routing topic (see `Topic` in `domain/events.py`). |
| `timestamp` | `datetime` (UTC) | Emission time. |
| `payload` | `dict` | Type-specific body (model_dump of the domain entity). |

## Topics (Phase 1 + 2)

| Topic constant | Value | Emitted by |
|----------------|-------|-----------|
| `TASK_CREATED` | `task.created` | Orchestrator |
| `TASK_PLANNED` | `task.planned` | Planner |
| `TASK_DISPATCHED` | `task.dispatched` | Dispatcher |
| `TASK_ASSIGNED` | `task.assigned` | Orchestrator |
| `AGENT_STARTED` / `AGENT_COMPLETED` / `AGENT_FAILED` / `AGENT_RECOVERED` | `agent.*` | Orchestrator / Recovery |
| `HEALTH_CHECK` / `HEALTH_DEGRADED` | `health.check` / `health.degraded` | Health Monitor |
| `RECOVERY_TRIGGERED` | `recovery.triggered` | Recovery Manager |
| `DASHBOARD` | `dashboard.event` | Dashboard broadcaster |
| `PROVIDER_HEALTH` / `PROVIDER_REGISTERED` / `PROVIDER_FAILED` / `PROVIDER_FAILOVER` | `provider.*` | Provider Management |
| `COST_RECORDED` | `cost.recorded` | Cost Tracker |
| `MEMORY_WRITTEN` / `MEMORY_EVICTED` | `memory.written` / `memory.evicted` | Memory Manager |
| `AGENT_COMPOSED` | `agent.composed` | Capability Engine |
| `APPROVAL_REQUESTED` / `APPROVAL_DECIDED` | `approval.requested` / `approval.decided` | Approval Gate |
| `AUDIT` | `audit.event` | Security Framework |
| `TOOL_DENIED` | `tool.denied` | Security Framework |

> This document is the authoritative schema reference. SDK specs
> (`PROVIDER_SDK.md`, `CAPABILITY_SDK.md`, `PLUGIN_SDK.md`) and the
> `MISSION_CONTROL_SPEC.md` are published when their subsystems ship (Phase 3+).
