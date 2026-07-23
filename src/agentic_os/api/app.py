"""FastAPI control plane + WebSocket live dashboard.

REST surface over the Platform (all subsystems), plus a WebSocket endpoint that
streams every bus event to connected dashboards. This is the user-facing top of
the hexagonal stack (the API is an adapter over the core ports).

Phase 2 adds the Provider Management API (add/edit/test/list providers, models,
health, cost, rate limits) and a minimal functional HTML page for managing
providers in-browser (the unified Mission Control dashboard lands in Phase 3).
"""

import dataclasses
import time
from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response

from agentic_os.config import settings
from agentic_os.core.mcp.manager import MCPManager
from agentic_os.domain.agent import Role, Task
from agentic_os.domain.events import EventEnvelope, Topic
from agentic_os.domain.execution import EngineCapability, EngineType
from agentic_os.domain.mcp import MCPServerStatus
from agentic_os.domain.mission import (
    Attachment,
    ExecutionMode,
    Mission,
    MissionPriority,
    MissionStatus,
)
from agentic_os.domain.orchestration import (
    AgentDescriptor,
    AgentTask,
    AgentTaskStatus,
    Checkpoint,
    CoordinationPattern,
    ExecutionStage,
    ExecutionStageStatus,
    ExecutionTimeline,
    MergedResult,
    MergeStrategy,
    OrchestrationGoal,
    OrchestrationPlan,
    RetryPolicy,
)
from agentic_os.domain.pipeline import (
    PipelineEdge,
    PipelineExecutionStatus,
    PipelineStage,
    PipelineStatus,
)
from agentic_os.domain.provider_mgmt import ProviderConfig, ProviderHealthStatus
from agentic_os.domain.workflow import (
    WorkflowEdge,
    WorkflowExecutionStatus,
    WorkflowNode,
    WorkflowStatus,
)
from agentic_os.infrastructure.logging import get_logger
from agentic_os.infrastructure.metrics import metrics_payload, observe
from agentic_os.kernel import Platform
from agentic_os.ports.execution import EngineRegistration, ExecutionRequest

log = get_logger("api")


# ── Swarm API helpers ──


def _parse_task(data: dict) -> AgentTask:
    """Parse an AgentTask from a JSON dict."""
    status_str = data.get("status", "pending")
    try:
        status = AgentTaskStatus(status_str)
    except ValueError:
        status = AgentTaskStatus.PENDING

    pattern_str = data.get("coordination_pattern")
    pattern = CoordinationPattern(pattern_str) if pattern_str else None

    return AgentTask(
        id=data.get("id", ""),
        goal_id=data.get("goal_id", ""),
        title=data.get("title", ""),
        description=data.get("description", ""),
        status=status,
        assigned_agent_id=data.get("assigned_agent_id"),
        depends_on=tuple(data.get("depends_on", [])),
        coordination_pattern=pattern,
        input_data=data.get("input_data", {}),
        output_data=data.get("output_data", {}),
        error=data.get("error"),
        priority=data.get("priority", 0),
        timeout_seconds=data.get("timeout_seconds", 300.0),
    )


def _parse_agent(data: dict) -> AgentDescriptor:
    """Parse an AgentDescriptor from a JSON dict."""
    return AgentDescriptor(
        agent_id=data.get("agent_id", ""),
        name=data.get("name", ""),
        engine_type=data.get("engine_type", "generic"),
        capabilities=tuple(data.get("capabilities", [])),
        status=data.get("status", "unknown"),
        health_status=data.get("health_status", "unknown"),
        latency_ms=data.get("latency_ms", 0.0),
        is_leader=data.get("is_leader", False),
        swarm_id=data.get("swarm_id"),
        metadata=data.get("metadata", {}),
    )


def _parse_plan(data: dict) -> OrchestrationPlan:
    """Parse an OrchestrationPlan from a JSON dict."""
    return OrchestrationPlan(
        id=data.get("id", ""),
        goal_id=data.get("goal_id", ""),
        subtasks=tuple(_parse_task(t) for t in data.get("subtasks", [])),
        status=data.get("status", "pending"),
        metadata=data.get("metadata", {}),
    )


def _parse_stage(data: dict) -> ExecutionStage:
    """Parse an ExecutionStage from a JSON dict."""
    status_str = data.get("status", "pending")
    try:
        status = ExecutionStageStatus(status_str)
    except ValueError:
        status = ExecutionStageStatus.PENDING

    pattern_str = data.get("coordination_pattern", "sequential")
    try:
        pattern = CoordinationPattern(pattern_str)
    except ValueError:
        pattern = CoordinationPattern.SEQUENTIAL

    return ExecutionStage(
        id=data.get("id", ""),
        plan_id=data.get("plan_id", ""),
        name=data.get("name", ""),
        description=data.get("description", ""),
        status=status,
        task_ids=tuple(data.get("task_ids", [])),
        depends_on=tuple(data.get("depends_on", [])),
        coordination_pattern=pattern,
        timeout_seconds=data.get("timeout_seconds", 300.0),
    )


def _parse_checkpoint(data: dict) -> Checkpoint:
    """Parse a Checkpoint from a JSON dict."""
    return Checkpoint(
        id=data.get("id", ""),
        plan_id=data.get("plan_id", ""),
        stage_id=data.get("stage_id", ""),
        task_states=data.get("task_states", {}),
        completed_task_ids=tuple(data.get("completed_task_ids", [])),
        failed_task_ids=tuple(data.get("failed_task_ids", [])),
        partial_outputs=data.get("partial_outputs", {}),
        metadata=data.get("metadata", {}),
    )


def _parse_retry_policy(data: dict) -> RetryPolicy:
    """Parse a RetryPolicy from a JSON dict."""
    return RetryPolicy(
        max_retries=data.get("max_retries", 3),
        base_delay_seconds=data.get("base_delay_seconds", 1.0),
        max_delay_seconds=data.get("max_delay_seconds", 60.0),
        backoff_multiplier=data.get("backoff_multiplier", 2.0),
        retry_on_timeout=data.get("retry_on_timeout", True),
        retry_on_error=data.get("retry_on_error", True),
        retry_on_rejection=data.get("retry_on_rejection", False),
        jitter=data.get("jitter", True),
    )


def create_app(platform: Platform) -> FastAPI:
    app = FastAPI(title="Agentic OS", version="1.0.0-rc1")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            # Browser dev server
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            # Tauri v2 custom-protocol (WebView2 on Windows)
            "tauri://localhost",
            "https://tauri.localhost",
            # Tauri v2 on some WebView2 builds emits http://tauri.localhost
            "http://tauri.localhost",
            # Requests from the embedded backend itself (health checks)
            "http://localhost:8000",
            "http://127.0.0.1:8000",
        ],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
        allow_headers=["Content-Type", "Authorization", "X-API-Key", "Accept"],
    )

    if settings.api_key:

        @app.middleware("http")
        async def verify_api_key(request: Request, call_next):
            if request.url.path in ("/healthz", "/metrics", "/providers"):
                return await call_next(request)
            if request.headers.get("X-API-Key") != settings.api_key:
                return Response("Unauthorized", status_code=401)
            return await call_next(request)

    orch = platform.orchestrator
    swarm = platform.orchestration
    if swarm is None:
        log.warning("OrchestrationFramework not available — swarm features disabled")
    pm = platform.provider_mgr
    vault = platform.vault
    phealth = platform.provider_health
    cost = platform.cost
    rate = platform.rate
    router = platform.router
    capability = platform.capability
    if capability is None:
        log.warning("CapabilityEngine not available — capability features disabled")
    memory = platform.memory
    if memory is None:
        log.warning("MemoryManager not available — memory features disabled")
    security = platform.security
    if security is None:
        log.warning("SecurityFramework not available — security features disabled")

    workflow_engine = platform.workflow
    pipeline_engine = platform.pipeline

    if workflow_engine is None:
        log.warning("WorkflowEngine not available — workflow features disabled")
    if pipeline_engine is None:
        log.warning("PipelineEngine not available — pipeline features disabled")

    learning = platform.learning
    if learning is None:
        log.warning("LearningManager not available — learning features disabled")

    mission_planner = platform.mission_planner
    if mission_planner is None:
        raise RuntimeError("MissionPlanner is required but was not initialised on the Platform")

    @app.middleware("http")
    async def _metrics(request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        observe(request.method, request.url.path, response.status_code, time.perf_counter() - start)
        return response

    @app.get("/healthz")
    async def healthz() -> dict:
        return {
            "status": "ok",
            "bus": settings.bus_type,
            "services": {
                "orchestrator": orch is not None,
                "swarm": swarm is not None,
                "capability": capability is not None,
                "memory": memory is not None,
                "security": security is not None,
                "workflow": workflow_engine is not None,
                "pipeline": pipeline_engine is not None,
                "learning": learning is not None,
                "desktop": platform.desktop is not None,
                "runtime": platform.runtime is not None,
                "discovery": platform.discovery_framework is not None,
                "mcp": platform.mcp is not None,
            },
        }

    @app.get("/metrics")
    async def metrics() -> Response:
        data, ctype = metrics_payload()
        return Response(content=data, media_type=ctype)

    # ── Tasks / Agents (Phase 1) ──
    @app.get("/api/tasks")
    async def list_tasks() -> list[dict]:
        return [t.model_dump(mode="json") for t in orch.registry.tasks()]

    @app.get("/api/agents")
    async def list_agents() -> list[dict]:
        return [a.model_dump(mode="json") for a in orch.registry.agents()]

    @app.post("/api/tasks")
    async def create_task(task: Task) -> dict:
        created = await orch.create_task(task.title, task.role, task.description)
        return created.model_dump(mode="json")

    # ── Provider Management API (Phase 2, Subsystem 1) ──
    @app.get("/api/providers")
    async def list_providers() -> list[dict]:
        return [p.model_dump(mode="json") for p in pm.list_providers()]

    @app.get("/api/provider-configs")
    async def list_provider_configs() -> list[dict]:
        return [c.model_dump(mode="json") for c in pm.list_configs()]

    @app.post("/api/provider-configs")
    async def upsert_provider_config(config: ProviderConfig) -> dict:
        pm.set_config(config)
        # Instantiate a working adapter and register it in the manager + registry
        # so it becomes selectable by the router immediately.
        from agentic_os.adapters.providers.factory import build_adapter

        adapter = await build_adapter(config, vault.get_key)
        pm.register(adapter)
        if orch.providers.get(config.name) is None:
            orch.providers.register(adapter)
        # Apply rate limit if configured.
        if config.rate_limit > 0:
            rate.set_limit(config.name, config.rate_limit)
        return config.model_dump(mode="json")

    @app.delete("/api/provider-configs/{name}")
    async def delete_provider_config(name: str) -> dict:
        cfg = pm.get_config(name)
        if cfg is None:
            raise HTTPException(status_code=404, detail="provider config not found")
        pm._configs.pop(name, None)
        return {"deleted": name}

    @app.post("/api/providers/{name}/api-key")
    async def store_api_key(name: str, body: dict) -> dict:
        key = body.get("api_key")
        if not key:
            raise HTTPException(status_code=400, detail="api_key required")
        await vault.store_key(name, key)
        return {"stored": name}

    @app.get("/api/providers/{name}/api-key/status")
    async def api_key_status(name: str) -> dict:
        exists = await vault.get_key(name) is not None
        return {"provider": name, "has_key": exists}

    @app.post("/api/providers/{name}/test")
    async def test_provider(name: str) -> dict:
        ok = await phealth.check_now(name)
        rec = phealth._status.get(name)
        return {
            "provider": name,
            "healthy": ok,
            "status": rec.status.value if rec else ProviderHealthStatus.UNKNOWN.value,
            "latency_ms": rec.latency_ms if rec else 0.0,
            "error": rec.error if rec else None,
        }

    @app.get("/api/models")
    async def list_models(provider: str | None = None) -> list[dict]:
        return [m.model_dump(mode="json") for m in pm.list_models(provider)]

    @app.post("/api/models")
    async def register_model(model: dict) -> dict:
        from agentic_os.ports.provider_management import ModelInfo

        info = ModelInfo.model_validate(model)
        pm.register_model(info)
        return info.model_dump(mode="json")

    @app.get("/api/provider-health")
    async def provider_health() -> list[dict]:
        return [
            phealth._status[p.name].model_dump(mode="json")
            for p in pm.list_providers()
            if p.name in phealth._status
        ]

    @app.get("/api/cost")
    async def cost_report(provider: str | None = None) -> dict:
        return {
            "total": cost.total_cost(provider),
            "records": [r.model_dump(mode="json") for r in cost.records()],
        }

    @app.get("/api/rate-limits")
    async def rate_limits() -> dict:
        return {p.name: rate.remaining(p.name) for p in pm.list_providers()}

    @app.post("/api/routing/policy")
    async def set_routing_policy(body: dict) -> dict:
        policy = body.get("policy")
        if policy not in ("latency", "cost", "round_robin"):
            raise HTTPException(status_code=400, detail="invalid policy")
        router.set_policy(policy)
        return {"policy": policy}

    @app.post("/api/providers/{name}/benchmark")
    async def benchmark_provider(name: str, body: dict | None = None) -> dict:
        model = (body or {}).get("model", "")
        result = await phealth.benchmark(name, model)
        return result.model_dump(mode="json")

    # ── Capability Engine API (Phase 2, Subsystem 3) ──
    @app.get("/api/capabilities")
    async def list_capabilities() -> list[dict]:
        return [
            {
                "name": c.name,
                "description": getattr(c, "description", ""),
                "requires_approval": getattr(c, "requires_approval", False),
            }
            for c in capability.registry.all()  # ty:ignore[unresolved-attribute]
        ]

    @app.post("/api/agents/compose")
    async def compose_agent(body: dict) -> dict:
        spec = capability.composer.compose(  # ty:ignore[unresolved-attribute]
            name=body.get("name", "composed-agent"),
            capabilities=body.get("capabilities", []),
            provider=body.get("provider", ""),
            model=body.get("model", ""),
        )
        # Register agent in the runtime so it shows in Agent Constellation
        provider_name = spec.provider or settings.provider_default
        if not provider_name:
            provider_name = "mock"
        # Ensure the role exists
        if not orch.registry.get_role(spec.name):
            orch.registry.register_role(
                Role(name=spec.name, description=f"Composed agent: {spec.name}")
            )
        agent = orch.registry.spawn(
            role=spec.name,
            provider=provider_name,
            model=spec.model,
            name=spec.name,
        )
        # Emit agent.composed event → WebSocket → Agent Constellation
        await orch.bus.publish(
            EventEnvelope(
                type="agent.composed",
                source="api",
                topic=Topic.AGENT_COMPOSED.value,
                payload=spec.model_dump(),
            )
        )
        # Emit agent.started event → Zustand store creates agent entry
        await orch.bus.publish(
            EventEnvelope(
                type="agent.started",
                source="api",
                topic=Topic.AGENT_STARTED.value,
                payload={
                    "id": agent.id,
                    "role": agent.role,
                    "provider": agent.provider,
                    "status": "idle",
                    "capabilities": spec.capabilities,
                },
            )
        )
        return spec.model_dump(mode="json")

    @app.post("/api/agents/compose-for-task")
    async def compose_for_task(task: Task) -> dict:
        spec = await capability.compose_and_emit(task)  # ty:ignore[unresolved-attribute]
        return spec.model_dump(mode="json")

    # ── Mission Orchestrator API (Phase Ψ) ──
    # In-memory store (persisted upgrade in Phase Ψ+1)
    _missions: dict[str, Mission] = {}

    @app.post("/api/missions")
    async def create_mission(body: dict) -> dict:
        mission = Mission(
            title=body.get("title", ""),
            description=body.get("description", ""),
            prompt=body.get("prompt", ""),
            objectives=body.get("objectives", []),
            deliverables=body.get("deliverables", []),
            priority=MissionPriority(body.get("priority", "medium")),
            execution_mode=ExecutionMode(body.get("execution_mode", "hybrid")),
            constraints=body.get("constraints", []),
            deadline=datetime.fromisoformat(body["deadline"]) if body.get("deadline") else None,
            tags=body.get("tags", []),
            attachments=[
                Attachment(**a) if isinstance(a, dict) else a for a in body.get("attachments", [])
            ],
        )
        _missions[mission.id] = mission
        await orch.bus.publish(
            EventEnvelope(
                type="mission.created",
                source="api",
                topic=Topic.MISSION_CREATED.value,
                payload=mission.to_dict(),
            )
        )
        return mission.to_dict()

    @app.get("/api/missions")
    async def list_missions() -> list[dict]:
        return [
            m.to_dict()
            for m in sorted(_missions.values(), key=lambda x: x.created_at, reverse=True)
        ]

    @app.get("/api/missions/{mission_id}")
    async def get_mission(mission_id: str) -> dict:
        m = _missions.get(mission_id)
        if not m:
            raise HTTPException(404, f"Mission {mission_id} not found")
        return m.to_dict()

    @app.put("/api/missions/{mission_id}")
    async def update_mission(mission_id: str, body: dict) -> dict:
        m = _missions.get(mission_id)
        if not m:
            raise HTTPException(404, f"Mission {mission_id} not found")
        for key in (
            "title",
            "description",
            "prompt",
            "priority",
            "execution_mode",
            "constraints",
            "tags",
        ):
            if key in body:
                setattr(m, key, body[key])
        if "objectives" in body:
            m.objectives = body["objectives"]
        if "deliverables" in body:
            m.deliverables = body["deliverables"]
        if "deadline" in body and body["deadline"]:
            m.deadline = datetime.fromisoformat(body["deadline"])
        if "attachments" in body:
            m.attachments = [
                Attachment(**a) if isinstance(a, dict) else a for a in body["attachments"]
            ]
        m.updated_at = datetime.now(UTC)
        await orch.bus.publish(
            EventEnvelope(
                type="mission.updated",
                source="api",
                topic=Topic.MISSION_UPDATED.value,
                payload=m.to_dict(),
            )
        )
        return m.to_dict()

    @app.delete("/api/missions/{mission_id}")
    async def delete_mission(mission_id: str) -> dict:
        m = _missions.pop(mission_id, None)
        if not m:
            raise HTTPException(404, f"Mission {mission_id} not found")
        await orch.bus.publish(
            EventEnvelope(
                type="mission.deleted",
                source="api",
                topic=Topic.MISSION_DELETED.value,
                payload={"id": mission_id},
            )
        )
        return {"deleted": mission_id}

    @app.post("/api/missions/{mission_id}/plan")
    async def plan_mission(mission_id: str) -> dict:
        m = _missions.get(mission_id)
        if not m:
            raise HTTPException(404, f"Mission {mission_id} not found")
        m.status = MissionStatus.PLANNING
        plan = await mission_planner.analyze(m)
        m.plan = plan
        m.status = MissionStatus.PLANNED
        return plan.to_dict()

    @app.post("/api/missions/{mission_id}/start")
    async def start_mission(mission_id: str) -> dict:
        m = _missions.get(mission_id)
        if not m:
            raise HTTPException(404, f"Mission {mission_id} not found")
        if not m.plan:
            raise HTTPException(400, "Mission has no plan — call /plan first")
        m.status = MissionStatus.EXECUTING
        m.updated_at = datetime.now(UTC)
        await orch.bus.publish(
            EventEnvelope(
                type="mission.started",
                source="api",
                topic=Topic.MISSION_STARTED.value,
                payload=m.to_dict(),
            )
        )
        return m.to_dict()

    @app.post("/api/missions/{mission_id}/pause")
    async def pause_mission(mission_id: str) -> dict:
        m = _missions.get(mission_id)
        if not m:
            raise HTTPException(404, f"Mission {mission_id} not found")
        m.status = MissionStatus.PAUSED
        m.updated_at = datetime.now(UTC)
        await orch.bus.publish(
            EventEnvelope(
                type="mission.paused",
                source="api",
                topic=Topic.MISSION_PAUSED.value,
                payload=m.to_dict(),
            )
        )
        return m.to_dict()

    @app.post("/api/missions/{mission_id}/cancel")
    async def cancel_mission(mission_id: str) -> dict:
        m = _missions.get(mission_id)
        if not m:
            raise HTTPException(404, f"Mission {mission_id} not found")
        m.status = MissionStatus.CANCELLED
        m.updated_at = datetime.now(UTC)
        await orch.bus.publish(
            EventEnvelope(
                type="mission.cancelled",
                source="api",
                topic=Topic.MISSION_CANCELLED.value,
                payload=m.to_dict(),
            )
        )
        return m.to_dict()

    # ── Memory System API (Phase 2, Subsystem 2) ──
    @app.post("/api/memory")
    async def write_memory(body: dict) -> dict:
        from agentic_os.domain.memory import MemoryItem, MemoryScope

        item = MemoryItem(
            scope=MemoryScope(body.get("scope", "working")),
            key=body.get("key", ""),
            value=body.get("value", ""),
            embedding=body.get("embedding", []),
            agent_id=body.get("agent_id", ""),
            project_id=body.get("project_id", ""),
        )
        stored = await memory.write(item)  # ty:ignore[unresolved-attribute]
        return stored.model_dump(mode="json")

    @app.get("/api/memory/{scope}")
    async def read_memory_scope(scope: str, agent_id: str = "") -> list[dict]:
        from agentic_os.domain.memory import MemoryScope

        return [
            i.model_dump(mode="json")
            for i in await memory.store.list_scope(MemoryScope(scope), agent_id)  # ty:ignore[unresolved-attribute]
        ]

    @app.get("/api/memory/{scope}/recall")
    async def recall_memory(
        scope: str, query: str = "", limit: int = 10, agent_id: str = ""
    ) -> list[dict]:
        from agentic_os.domain.memory import MemoryScope

        return [
            i.model_dump(mode="json")
            for i in await memory.recall(MemoryScope(scope), query, limit, agent_id)  # ty:ignore[unresolved-attribute]
        ]

    @app.delete("/api/memory/{item_id}")
    async def forget_memory(item_id: str) -> dict:
        ok = await memory.forget(item_id)  # ty:ignore[unresolved-attribute]
        return {"forgotten": ok}

    @app.post("/api/memory/retention")
    async def enforce_retention() -> dict:
        evicted = await memory.enforce_retention()  # ty:ignore[unresolved-attribute]
        return {"evicted": evicted}

    # ── Security Framework API (Phase 2, Subsystem 4) ──
    @app.post("/api/security/assign")
    async def assign_role(body: dict) -> dict:
        from agentic_os.domain.security import Principal, Role

        principal = Principal(id=body["principal"], roles=[Role(r) for r in body.get("roles", [])])
        security.ac.assign(principal, Role(body["role"]))  # ty:ignore[unresolved-attribute]
        return {"assigned": body["role"], "to": body["principal"]}

    @app.post("/api/security/authorize")
    async def authorize(body: dict) -> dict:
        from agentic_os.domain.security import Principal, ToolRequest

        principal = Principal(id=body["principal"], roles=body.get("roles", []))
        request = ToolRequest(
            principal=principal,
            capability=body["capability"],
            detail=body.get("detail", ""),
            requires_approval=body.get("requires_approval", False),
        )
        decision = await security.authorize(principal, request)  # ty:ignore[unresolved-attribute]
        return decision.model_dump(mode="json")

    @app.post("/api/security/approval/{request_id}/decide")
    async def decide_approval(request_id: str, body: dict) -> dict:
        await security.gate.decide(request_id, bool(body.get("approved")), body.get("by", ""))  # ty:ignore[unresolved-attribute]
        return {"decided": request_id}

    @app.get("/api/security/approval/{request_id}")
    async def approval_status(request_id: str) -> dict:
        decision = security.gate.status(request_id)  # ty:ignore[unresolved-attribute]
        return decision.model_dump(mode="json") if decision else {"status": "unknown"}

    @app.get("/api/security/audit")
    async def audit_log(principal: str | None = None) -> list[dict]:
        entries = await security.audit.query(principal)  # ty:ignore[unresolved-attribute]
        return [e.model_dump(mode="json") for e in entries]

    @app.get("/api/security/workspace/{agent_id}")
    async def workspace_for(agent_id: str) -> dict:
        return {"agent_id": agent_id, "workspace": security.workspace_for(agent_id)}  # ty:ignore[unresolved-attribute]

    # ── Workflow Engine API (Phase 3B) ──
    workflow_engine = platform.workflow
    pipeline_engine = platform.pipeline

    if workflow_engine is None:
        raise RuntimeError("WorkflowEngine is required but was not initialised on the Platform")
    if pipeline_engine is None:
        raise RuntimeError("PipelineEngine is required but was not initialised on the Platform")

    @app.get("/api/workflows")
    async def list_workflows(
        status: WorkflowStatus | None = None, limit: int = 50, offset: int = 0
    ) -> list[dict]:
        return [
            dataclasses.asdict(w)
            for w in await workflow_engine.list_workflows(status, limit, offset)
        ]

    @app.get("/api/workflows/{workflow_id}")
    async def get_workflow(workflow_id: str) -> dict:
        workflow = await workflow_engine.get_workflow(workflow_id)
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")
        return dataclasses.asdict(workflow)

    @app.post("/api/workflows")
    async def create_workflow(body: dict) -> dict:
        from agentic_os.ports.workflow import WorkflowCreate

        data = WorkflowCreate(
            name=body["name"],
            description=body.get("description", ""),
            nodes=[WorkflowNode(**n) for n in body.get("nodes", [])],
            edges=[WorkflowEdge(**e) for e in body.get("edges", [])],
            template_id=body.get("template_id"),
            created_by=body.get("created_by", "system"),
        )
        workflow = await workflow_engine.create_workflow(data)
        return dataclasses.asdict(workflow)

    @app.put("/api/workflows/{workflow_id}")
    async def update_workflow(workflow_id: str, body: dict) -> dict:
        from agentic_os.ports.workflow import WorkflowUpdate

        data = WorkflowUpdate(
            name=body.get("name"),
            description=body.get("description"),
            nodes=[WorkflowNode(**n) for n in body["nodes"]] if "nodes" in body else None,
            edges=[WorkflowEdge(**e) for e in body["edges"]] if "edges" in body else None,
            updated_by=body.get("updated_by", "system"),
        )
        workflow = await workflow_engine.update_workflow(workflow_id, data)
        return dataclasses.asdict(workflow)

    @app.delete("/api/workflows/{workflow_id}")
    async def delete_workflow(workflow_id: str) -> dict:
        ok = await workflow_engine.delete_workflow(workflow_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Workflow not found")
        return {"deleted": workflow_id}

    @app.get("/api/workflows/{workflow_id}/versions")
    async def get_workflow_versions(workflow_id: str) -> list[dict]:
        return [
            dataclasses.asdict(v) for v in await workflow_engine.get_workflow_versions(workflow_id)
        ]

    @app.get("/api/workflows/{workflow_id}/versions/{version}")
    async def get_workflow_version(workflow_id: str, version: int) -> dict:
        workflow = await workflow_engine.get_workflow_version(workflow_id, version)
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow version not found")
        return dataclasses.asdict(workflow)

    @app.post("/api/workflows/{workflow_id}/execute")
    async def execute_workflow(workflow_id: str, body: dict) -> dict:
        from agentic_os.ports.workflow import WorkflowExecute

        data = WorkflowExecute(inputs=body.get("inputs", {}), version=body.get("version"))
        execution = await workflow_engine.execute_workflow(workflow_id, data)
        return dataclasses.asdict(execution)

    @app.post("/api/workflows/{workflow_id}/replay")
    async def replay_workflow(workflow_id: str, body: dict) -> dict:
        from agentic_os.ports.workflow import WorkflowReplay

        data = WorkflowReplay(
            inputs=body.get("inputs", {}),
            version=body.get("version"),
            from_node=body.get("from_node"),
            parent_execution_id=body.get("parent_execution_id"),
        )
        execution = await workflow_engine.replay_workflow(workflow_id, data)
        return dataclasses.asdict(execution)

    @app.post("/api/workflows/{workflow_id}/approve")
    async def approve_workflow(workflow_id: str, body: dict) -> dict:
        from agentic_os.ports.workflow import WorkflowApproval

        data = WorkflowApproval(
            node_id=body["node_id"],
            approved=body["approved"],
            decided_by=body["decided_by"],
            reason=body.get("reason"),
        )
        execution = await workflow_engine.approve_workflow(workflow_id, data)
        return dataclasses.asdict(execution)

    @app.get("/api/workflows/{workflow_id}/executions")
    async def get_workflow_executions(
        workflow_id: str,
        status: WorkflowExecutionStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        return [
            dataclasses.asdict(e)
            for e in await workflow_engine.get_workflow_executions(
                workflow_id, status, limit, offset
            )
        ]

    @app.get("/api/workflows/executions/running")
    async def get_running_workflow_executions() -> list[dict]:
        return [dataclasses.asdict(e) for e in await workflow_engine.get_running_executions()]

    @app.post("/api/workflows/executions/{execution_id}/cancel")
    async def cancel_workflow_execution(execution_id: str) -> dict:
        execution = await workflow_engine.cancel_execution(execution_id)
        return dataclasses.asdict(execution)

    @app.post("/api/workflows/executions/{execution_id}/pause")
    async def pause_workflow_execution(execution_id: str) -> dict:
        execution = await workflow_engine.pause_execution(execution_id)
        return dataclasses.asdict(execution)

    @app.post("/api/workflows/executions/{execution_id}/resume")
    async def resume_workflow_execution(execution_id: str) -> dict:
        execution = await workflow_engine.resume_execution(execution_id)
        return dataclasses.asdict(execution)

    @app.get("/api/workflows/executions/{execution_id}")
    async def get_workflow_execution(execution_id: str) -> dict:
        execution = await workflow_engine.get_execution(execution_id)
        if not execution:
            raise HTTPException(status_code=404, detail="Execution not found")
        return dataclasses.asdict(execution)

    # ── Pipeline Engine API (Phase 3B) ──
    @app.get("/api/pipelines")
    async def list_pipelines(
        status: PipelineStatus | None = None, limit: int = 50, offset: int = 0
    ) -> list[dict]:
        return [
            dataclasses.asdict(p)
            for p in await pipeline_engine.list_pipelines(status, limit, offset)
        ]

    @app.get("/api/pipelines/{pipeline_id}")
    async def get_pipeline(pipeline_id: str) -> dict:
        pipeline = await pipeline_engine.get_pipeline(pipeline_id)
        if not pipeline:
            raise HTTPException(status_code=404, detail="Pipeline not found")
        return dataclasses.asdict(pipeline)

    @app.post("/api/pipelines")
    async def create_pipeline(body: dict) -> dict:
        from agentic_os.ports.pipeline import PipelineCreate

        data = PipelineCreate(
            name=body["name"],
            description=body.get("description", ""),
            stages=[PipelineStage(**s) for s in body.get("stages", [])],
            edges=[PipelineEdge(**e) for e in body.get("edges", [])],
            schedule_cron=body.get("schedule_cron"),
            schedule_timezone=body.get("schedule_timezone", "UTC"),
            created_by=body.get("created_by", "system"),
        )
        pipeline = await pipeline_engine.create_pipeline(data)
        return dataclasses.asdict(pipeline)

    @app.put("/api/pipelines/{pipeline_id}")
    async def update_pipeline(pipeline_id: str, body: dict) -> dict:
        from agentic_os.ports.pipeline import PipelineUpdate

        data = PipelineUpdate(
            name=body.get("name"),
            description=body.get("description"),
            stages=[PipelineStage(**s) for s in body["stages"]] if "stages" in body else None,
            edges=[PipelineEdge(**e) for e in body["edges"]] if "edges" in body else None,
            schedule_cron=body.get("schedule_cron"),
            schedule_timezone=body.get("schedule_timezone"),
            status=PipelineStatus(body["status"]) if "status" in body else None,
            updated_by=body.get("updated_by", "system"),
        )
        pipeline = await pipeline_engine.update_pipeline(pipeline_id, data)
        return dataclasses.asdict(pipeline)

    @app.delete("/api/pipelines/{pipeline_id}")
    async def delete_pipeline(pipeline_id: str) -> dict:
        ok = await pipeline_engine.delete_pipeline(pipeline_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Pipeline not found")
        return {"deleted": pipeline_id}

    @app.get("/api/pipelines/{pipeline_id}/versions")
    async def get_pipeline_versions(pipeline_id: str) -> list[dict]:
        return [
            dataclasses.asdict(v) for v in await pipeline_engine.get_pipeline_versions(pipeline_id)
        ]

    @app.get("/api/pipelines/{pipeline_id}/versions/{version}")
    async def get_pipeline_version(pipeline_id: str, version: int) -> dict:
        pipeline = await pipeline_engine.get_pipeline_version(pipeline_id, version)
        if not pipeline:
            raise HTTPException(status_code=404, detail="Pipeline version not found")
        return dataclasses.asdict(pipeline)

    @app.post("/api/pipelines/{pipeline_id}/execute")
    async def execute_pipeline(pipeline_id: str, body: dict) -> dict:
        from agentic_os.ports.pipeline import PipelineExecute

        data = PipelineExecute(inputs=body.get("inputs", {}))
        execution = await pipeline_engine.execute_pipeline(pipeline_id, data)
        return dataclasses.asdict(execution)

    @app.post("/api/pipelines/{pipeline_id}/schedule")
    async def schedule_pipeline(pipeline_id: str, body: dict) -> dict:
        from agentic_os.ports.pipeline import PipelineScheduleRequest

        data = PipelineScheduleRequest(cron=body["cron"], timezone=body.get("timezone", "UTC"))
        schedule = await pipeline_engine.schedule_pipeline(pipeline_id, data)
        return dataclasses.asdict(schedule)

    @app.delete("/api/pipelines/{pipeline_id}/schedule")
    async def unschedule_pipeline(pipeline_id: str) -> dict:
        await pipeline_engine.unschedule_pipeline(pipeline_id)
        return {"unscheduled": pipeline_id}

    @app.get("/api/pipelines/{pipeline_id}/schedule")
    async def get_pipeline_schedule(pipeline_id: str) -> dict:
        schedule = await pipeline_engine.get_pipeline_schedule(pipeline_id)
        if not schedule:
            raise HTTPException(status_code=404, detail="No schedule found")
        return dataclasses.asdict(schedule)

    @app.post("/api/pipelines/{pipeline_id}/rollback")
    async def rollback_pipeline(pipeline_id: str, body: dict) -> dict:
        from agentic_os.ports.pipeline import PipelineRollback

        data = PipelineRollback(to_execution_id=body["to_execution_id"])
        execution = await pipeline_engine.rollback_pipeline(pipeline_id, data)
        return dataclasses.asdict(execution)

    @app.get("/api/pipelines/{pipeline_id}/executions")
    async def get_pipeline_executions(
        pipeline_id: str,
        status: PipelineExecutionStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        return [
            dataclasses.asdict(e)
            for e in await pipeline_engine.get_pipeline_executions(
                pipeline_id, status, limit, offset
            )
        ]

    @app.get("/api/pipelines/executions/running")
    async def get_running_pipeline_executions() -> list[dict]:
        return [dataclasses.asdict(e) for e in await pipeline_engine.get_running_executions()]

    @app.get("/api/pipelines/executions/scheduled")
    async def get_scheduled_pipeline_executions() -> list[dict]:
        return [dataclasses.asdict(e) for e in await pipeline_engine.get_scheduled_executions()]

    @app.post("/api/pipelines/executions/{execution_id}/cancel")
    async def cancel_pipeline_execution(execution_id: str) -> dict:
        execution = await pipeline_engine.cancel_execution(execution_id)
        return dataclasses.asdict(execution)

    @app.post("/api/pipelines/executions/{execution_id}/pause")
    async def pause_pipeline_execution(execution_id: str) -> dict:
        execution = await pipeline_engine.pause_execution(execution_id)
        return dataclasses.asdict(execution)

    @app.post("/api/pipelines/executions/{execution_id}/resume")
    async def resume_pipeline_execution(execution_id: str) -> dict:
        execution = await pipeline_engine.resume_execution(execution_id)
        return dataclasses.asdict(execution)

    @app.get("/api/pipelines/executions/{execution_id}")
    async def get_pipeline_execution(execution_id: str) -> dict:
        execution = await pipeline_engine.get_execution(execution_id)
        if not execution:
            raise HTTPException(status_code=404, detail="Execution not found")
        return dataclasses.asdict(execution)

    # ── Runtime: Execution Engine Framework (Phase 4, M1) ──
    runtime = platform.runtime
    if runtime is None:
        raise RuntimeError("RuntimeManager is required but was not initialised on the Platform")

    @app.get("/api/runtime/engines")
    async def list_runtime_engines(
        engine_type: str | None = None,
        capability: str | None = None,
        status: str | None = None,
    ) -> dict:
        type_filter = EngineType(engine_type) if engine_type else None
        cap_filter = EngineCapability(capability) if capability else None
        engines = await runtime.list_engines(type_filter, cap_filter, status)
        return {"engines": [e.to_dict() for e in engines], "total": len(engines)}

    @app.get("/api/runtime/engines/{engine_id}")
    async def get_runtime_engine(engine_id: str) -> dict:
        engine = await runtime.get_engine(engine_id)
        if engine is None:
            raise HTTPException(status_code=404, detail="Engine not found")
        return engine.to_dict()

    @app.post("/api/runtime/engines")
    async def register_runtime_engine(body: dict) -> dict:
        try:
            registration = EngineRegistration(
                name=body["name"],
                engine_type=EngineType(body.get("engine_type", "generic")),
                endpoint=body.get("endpoint"),
                transport=body.get("transport", "local"),
                capabilities=[EngineCapability(c) for c in body.get("capabilities", [])],
                description=body.get("description", ""),
                version=body.get("version", "1.0.0"),
                tags=body.get("tags", []),
                metadata=body.get("metadata", {}),
            )
            engine = await runtime.register_engine(registration)
            return engine.to_dict()
        except (ValueError, KeyError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None

    @app.delete("/api/runtime/engines/{engine_id}")
    async def unregister_runtime_engine(engine_id: str) -> dict:
        removed = await runtime.unregister_engine(engine_id)
        if not removed:
            raise HTTPException(status_code=404, detail="Engine not found")
        return {"removed": True, "engine_id": engine_id}

    @app.post("/api/runtime/engines/{engine_id}/execute")
    async def execute_on_engine(engine_id: str, body: dict) -> dict:
        try:
            request = ExecutionRequest(
                action=body["action"],
                payload=body.get("payload", {}),
                timeout_seconds=body.get("timeout_seconds", 60.0),
                stream=body.get("stream", False),
                metadata=body.get("metadata", {}),
            )
            result = await runtime.execute(engine_id, request)
            return result.to_dict()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None

    @app.post("/api/runtime/execute")
    async def execute_best(body: dict) -> dict:
        try:
            request = ExecutionRequest(
                action=body["action"],
                payload=body.get("payload", {}),
                timeout_seconds=body.get("timeout_seconds", 60.0),
            )
            required = None
            if "required_capability" in body:
                required = EngineCapability(body["required_capability"])
            result = await runtime.execute_on_best(request, required)
            return result.to_dict()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None

    @app.post("/api/runtime/discover")
    async def discover_engines() -> dict:
        engines = await runtime.discover_engines()
        return {"engines": [e.to_dict() for e in engines], "total": len(engines)}

    @app.get("/api/runtime/capabilities")
    async def list_runtime_capabilities() -> dict:
        caps = await runtime.list_capabilities()
        return {
            engine_id: [c.to_dict() for c in caps_list] for engine_id, caps_list in caps.items()
        }

    @app.get("/api/runtime/engines/{engine_id}/health")
    async def engine_health(engine_id: str) -> dict:
        health = await runtime.health_check(engine_id)
        return health.to_dict()

    @app.post("/api/runtime/engines/{engine_id}/benchmark")
    async def benchmark_engine(engine_id: str, body: dict | None = None) -> dict:
        try:
            benchmark = await runtime.benchmark(engine_id, body or {})
            return benchmark.to_dict()
        except NotImplementedError:
            raise HTTPException(
                status_code=501,
                detail="Engine does not support benchmarking",
            ) from None
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None

    @app.get("/api/runtime/engines/{engine_id}/sessions")
    async def list_engine_sessions(
        engine_id: str,
        limit: int = 50,
    ) -> dict:
        sessions = await runtime.list_sessions(engine_id=engine_id, limit=limit)
        return {"sessions": [s.to_dict() for s in sessions], "total": len(sessions)}

    # ── Discovery & Profiling API (Phase 4, M2) ──
    discovery_framework = platform.discovery_framework

    @app.get("/api/discovery/providers")
    async def list_discovery_providers() -> list[dict]:
        """List registered discovery providers with status."""
        if discovery_framework is None:
            raise HTTPException(status_code=503, detail="Discovery framework not available")
        return discovery_framework.list_providers()

    @app.put("/api/discovery/providers/{name}")
    async def configure_discovery_provider(name: str, body: dict) -> dict:
        """Enable/disable or configure a discovery provider."""
        if discovery_framework is None:
            raise HTTPException(status_code=503, detail="Discovery framework not available")
        enabled = body.get("enabled")
        if enabled is True:
            discovery_framework.enable_provider(name)
        elif enabled is False:
            discovery_framework.disable_provider(name)
        return {"name": name, "enabled": enabled}

    @app.post("/api/discovery/scan")
    async def run_discovery_scan(profile: str | None = None) -> dict:
        """Run discovery using optional named profile."""
        if discovery_framework is None:
            raise HTTPException(status_code=503, detail="Discovery framework not available")
        profile_name = profile or discovery_framework.config.default_profile
        engines = await discovery_framework.discover_and_register(profile_name)
        return {
            "profile": profile_name,
            "engines_found": len(engines),
            "engines": [e.to_dict() for e in engines] if engines else [],
        }

    @app.get("/api/discovery/cache")
    async def get_discovery_cache() -> dict:
        """List cached discovery results."""
        if discovery_framework is None:
            raise HTTPException(status_code=503, detail="Discovery framework not available")
        cache_entries = discovery_framework.get_cache_entries()
        return {"entries": cache_entries, "total": len(cache_entries)}

    @app.delete("/api/discovery/cache")
    async def clear_discovery_cache() -> dict:
        """Invalidate all cached discovery results."""
        if discovery_framework is None:
            raise HTTPException(status_code=503, detail="Discovery framework not available")
        count = discovery_framework.cache.invalidate_all()
        return {"invalidated": count}

    @app.get("/api/discovery/history")
    async def get_discovery_history(limit: int = 50) -> list[dict]:
        """Return discovery scan history."""
        if discovery_framework is None:
            raise HTTPException(status_code=503, detail="Discovery framework not available")
        return discovery_framework.telemetry.get_history(limit)

    # ── Installer Intelligence API (Phase 4, M3) ──
    installer = platform.installer_intelligence

    @app.get("/api/installer/report")
    async def get_installer_report() -> dict:
        """Return the most recent installer discovery report."""
        if installer is None:
            raise HTTPException(status_code=503, detail="Installer intelligence not available")
        from services.installer.report import InstallReportGenerator

        gen = InstallReportGenerator()
        report = gen.load()
        if report is None:
            return {"report": None, "message": "No install report found"}
        return {"report": report.to_dict()}

    @app.post("/api/installer/scan")
    async def run_installer_scan(background: bool = True) -> dict:
        """Run a full installer discovery and validation scan."""
        if installer is None:
            raise HTTPException(status_code=503, detail="Installer intelligence not available")
        if background:
            import asyncio

            asyncio.create_task(installer.run_full_install())  # ty:ignore[unresolved-attribute]
            return {"status": "started", "mode": "background"}
        report = await installer.run_full_install()  # ty:ignore[unresolved-attribute]
        return {
            "status": "completed",
            "success": report.success,
            "phases": [
                {"phase": p.phase, "success": p.success, "duration": p.duration_seconds}
                for p in report.phases
            ],
            "bound_providers": report.bound_providers,
        }

    @app.post("/api/installer/heal")
    async def run_installer_heal() -> dict:
        """Run self-healing on all bound providers."""
        if installer is None:
            raise HTTPException(status_code=503, detail="Installer intelligence not available")
        report = await installer.heal_all()  # ty:ignore[unresolved-attribute]
        return {
            "total_issues": report.total_issues,
            "total_repaired": report.total_repaired,
            "total_failed": report.total_failed,
            "actions": [
                {
                    "provider": a.provider_id,
                    "issue": a.issue,
                    "severity": a.severity,
                    "success": a.success,
                }
                for a in report.actions
            ],
        }

    @app.get("/api/installer/providers")
    async def list_installer_providers() -> dict:
        """List all bound providers from installer intelligence."""
        if installer is None:
            raise HTTPException(status_code=503, detail="Installer intelligence not available")
        providers = installer.bound_providers  # ty:ignore[unresolved-attribute]
        return {
            "total": len(providers),
            "providers": [
                {
                    "id": pid,
                    "display_name": b.get("display_name", pid),
                    "executable_path": b.get("executable_path"),
                    "version": b.get("version"),
                    "status": b.get("status", "unknown"),
                    "capabilities": b.get("capabilities", []),
                }
                for pid, b in providers.items()
            ],
        }

    @app.get("/api/discovery/stats")
    async def get_discovery_stats() -> dict:
        """Aggregated discovery statistics."""
        if discovery_framework is None:
            raise HTTPException(status_code=503, detail="Discovery framework not available")
        return discovery_framework.telemetry.get_stats()

    # Profiles
    @app.get("/api/discovery/profiles")
    async def list_discovery_profiles() -> list[dict]:
        """List all discovery profiles."""
        if discovery_framework is None:
            raise HTTPException(status_code=503, detail="Discovery framework not available")
        return discovery_framework.config.list_profiles()

    @app.post("/api/discovery/profiles")
    async def create_discovery_profile(body: dict) -> dict:
        """Create a new discovery profile."""
        if discovery_framework is None:
            raise HTTPException(status_code=503, detail="Discovery framework not available")
        from agentic_os.domain.discovery import DiscoveryProfile

        profile = DiscoveryProfile(
            name=body["name"],
            description=body.get("description", ""),
            interval_seconds=body.get("interval_seconds", 60.0),
            validate_after_discovery=body.get("validate_after_discovery", True),
            profile_after_discovery=body.get("profile_after_discovery", True),
            auto_register=body.get("auto_register", True),
            tags=tuple(body.get("tags", [])),
        )
        discovery_framework.config.add_profile(profile)
        return profile.to_dict()

    @app.get("/api/discovery/profiles/{name}")
    async def get_discovery_profile(name: str) -> dict:
        """Get a discovery profile by name."""
        if discovery_framework is None:
            raise HTTPException(status_code=503, detail="Discovery framework not available")
        profile = discovery_framework.config.get_profile(name)
        if profile is None:
            raise HTTPException(status_code=404, detail="Profile not found")
        return profile.to_dict()

    @app.delete("/api/discovery/profiles/{name}")
    async def delete_discovery_profile(name: str) -> dict:
        """Delete a discovery profile."""
        if discovery_framework is None:
            raise HTTPException(status_code=503, detail="Discovery framework not available")
        removed = discovery_framework.config.remove_profile(name)
        if not removed:
            raise HTTPException(status_code=404, detail="Profile not found")
        return {"removed": name}

    @app.post("/api/discovery/profiles/{name}/activate")
    async def activate_discovery_profile(name: str) -> dict:
        """Activate a discovery profile for scheduled scanning."""
        if discovery_framework is None:
            raise HTTPException(status_code=503, detail="Discovery framework not available")
        profile = discovery_framework.config.get_profile(name)
        if profile is None:
            raise HTTPException(status_code=404, detail="Profile not found")
        discovery_framework.config.default_profile = name
        return {"activated": name}

    # Validation
    @app.post("/api/discovery/engines/{engine_id}/validate")
    async def validate_discovered_engine(engine_id: str) -> dict:
        """Validate a discovered engine by its ID."""
        if discovery_framework is None:
            raise HTTPException(status_code=503, detail="Discovery framework not available")

        # Find the engine in the runtime registry
        engine = await runtime.get_engine(engine_id)
        if engine is None:
            raise HTTPException(status_code=404, detail="Engine not found")

        # Build a fake registration from engine data for validation
        registration = EngineRegistration(
            name=engine.name,
            engine_type=engine.engine_type,
            endpoint=engine.endpoint or f"local:{engine.name}",
            transport=engine.transport,
            capabilities=[c.type for c in engine.capabilities],
            description="",
            version=engine.version or "",
        )
        passed, results = await discovery_framework.validate_engine(registration)
        return {
            "engine_id": engine_id,
            "valid": passed,
            "results": [r.to_dict() for r in results],
        }

    # Profiling
    @app.post("/api/discovery/engines/{engine_id}/profile")
    async def profile_discovered_engine(engine_id: str) -> dict:
        """Profile a discovered engine by its ID."""
        if discovery_framework is None:
            raise HTTPException(status_code=503, detail="Discovery framework not available")
        engine = await runtime.get_engine(engine_id)
        if engine is None:
            raise HTTPException(status_code=404, detail="Engine not found")

        registration = EngineRegistration(
            name=engine.name,
            engine_type=engine.engine_type,
            endpoint=engine.endpoint or f"local:{engine.name}",
            transport=engine.transport,
            capabilities=[c.type for c in engine.capabilities],
            description="",
            version=engine.version or "",
        )
        profile_result = await discovery_framework.profile_engine(registration, engine)
        return profile_result.to_dict()

    # Hot Reload
    @app.post("/api/discovery/hot-reload/start")
    async def start_discovery_hot_reload() -> dict:
        """Start hot-reload for runtime discovery."""
        if discovery_framework is None:
            raise HTTPException(status_code=503, detail="Discovery framework not available")
        await discovery_framework.start_hot_reload()
        return {"status": "started"}

    @app.post("/api/discovery/hot-reload/stop")
    async def stop_discovery_hot_reload() -> dict:
        """Stop hot-reload for runtime discovery."""
        if discovery_framework is None:
            raise HTTPException(status_code=503, detail="Discovery framework not available")
        await discovery_framework.stop_hot_reload()
        return {"status": "stopped"}

    @app.get("/api/discovery/hot-reload/status")
    async def get_discovery_hot_reload_status() -> dict:
        """Get hot-reload status."""
        if discovery_framework is None:
            raise HTTPException(status_code=503, detail="Discovery framework not available")
        return {"running": discovery_framework.hot_reload_running}

    # ── MCP Runtime Foundation API (Phase 4, M3) ──
    mcp = platform.mcp

    def _require_mcp() -> MCPManager:
        """Raise 503 if MCP runtime is not available, then return the manager."""
        if mcp is None:
            raise HTTPException(status_code=503, detail="MCP runtime not available")
        return mcp

    # Server CRUD
    @app.get("/api/mcp/servers")
    async def list_mcp_servers(
        status: str | None = None,
        enabled_only: bool = False,
    ) -> list[dict]:
        mcp = _require_mcp()
        status_enum = MCPServerStatus(status) if status else None
        servers = await mcp.list_servers(status=status_enum, enabled_only=enabled_only)
        return [s.to_dict() for s in servers]

    @app.get("/api/mcp/servers/{server_id}")
    async def get_mcp_server(server_id: str) -> dict:
        mcp = _require_mcp()
        detail = await mcp.get_server_detail(server_id)
        if not detail:
            raise HTTPException(status_code=404, detail="MCP server not found")
        return detail.to_dict()

    @app.post("/api/mcp/servers")
    async def register_mcp_server(body: dict) -> dict:
        mcp = _require_mcp()
        from agentic_os.ports.mcp import MCPServerCreate

        data = MCPServerCreate(
            name=body["name"],
            transport=body.get("transport", "stdio"),
            command=body.get("command"),
            args=body.get("args", []),
            env=body.get("env", {}),
            url=body.get("url"),
            headers=body.get("headers", {}),
            server_type=body.get("server_type", "custom"),
            description=body.get("description", ""),
            enabled=body.get("enabled", True),
            sandbox=body.get("sandbox", True),
            sandbox_config=body.get("sandbox_config", {}),
            health_check_interval_seconds=body.get("health_check_interval_seconds", 30),
            health_check_timeout_seconds=body.get("health_check_timeout_seconds", 10),
            version=body.get("version", "1.0.0"),
            author=body.get("author", ""),
            homepage=body.get("homepage"),
            repository=body.get("repository"),
            tags=body.get("tags", []),
            created_by=body.get("created_by", "system"),
        )
        detail = await mcp.registry.register_server(data)
        return detail.to_dict()

    @app.put("/api/mcp/servers/{server_id}")
    async def update_mcp_server(server_id: str, body: dict) -> dict:
        mcp = _require_mcp()
        from agentic_os.ports.mcp import MCPServerUpdate

        data = MCPServerUpdate(
            name=body.get("name"),
            transport=body.get("transport"),
            command=body.get("command"),
            args=body.get("args"),
            env=body.get("env"),
            url=body.get("url"),
            headers=body.get("headers"),
            server_type=body.get("server_type"),
            description=body.get("description"),
            enabled=body.get("enabled"),
            sandbox=body.get("sandbox"),
            sandbox_config=body.get("sandbox_config"),
            health_check_interval_seconds=body.get("health_check_interval_seconds"),
            health_check_timeout_seconds=body.get("health_check_timeout_seconds"),
            version=body.get("version"),
            author=body.get("author"),
            homepage=body.get("homepage"),
            repository=body.get("repository"),
            tags=body.get("tags"),
            updated_by=body.get("updated_by", "api"),
        )
        try:
            detail = await mcp.registry.update_server(server_id, data)
            return detail.to_dict()
        except KeyError:
            raise HTTPException(status_code=404, detail="MCP server not found") from None

    @app.delete("/api/mcp/servers/{server_id}")
    async def delete_mcp_server(server_id: str) -> dict:
        mcp = _require_mcp()
        ok = await mcp.registry.delete_server(server_id)
        if not ok:
            raise HTTPException(status_code=404, detail="MCP server not found")
        return {"deleted": server_id}

    # Server Lifecycle
    @app.post("/api/mcp/servers/{server_id}/start")
    async def start_mcp_server(server_id: str) -> dict:
        mcp = _require_mcp()
        try:
            detail = await mcp.registry.start_server(server_id)
            return detail.to_dict()
        except KeyError:
            raise HTTPException(status_code=404, detail="MCP server not found") from None
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/mcp/servers/{server_id}/stop")
    async def stop_mcp_server(server_id: str) -> dict:
        mcp = _require_mcp()
        try:
            detail = await mcp.registry.stop_server(server_id)
            return detail.to_dict()
        except KeyError:
            raise HTTPException(status_code=404, detail="MCP server not found") from None

    @app.post("/api/mcp/servers/{server_id}/restart")
    async def restart_mcp_server(server_id: str) -> dict:
        mcp = _require_mcp()
        try:
            detail = await mcp.restart_server(server_id)
            return detail.to_dict()
        except KeyError:
            raise HTTPException(status_code=404, detail="MCP server not found") from None

    @app.post("/api/mcp/servers/{server_id}/reload")
    async def reload_mcp_server(server_id: str) -> dict:
        mcp = _require_mcp()
        try:
            detail = await mcp.reload_server(server_id)
            return detail.to_dict()
        except KeyError:
            raise HTTPException(status_code=404, detail="MCP server not found") from None

    # Tool Operations
    @app.get("/api/mcp/servers/{server_id}/tools")
    async def list_mcp_server_tools(server_id: str) -> list[dict]:
        mcp = _require_mcp()
        tools = mcp.get_server_tools(server_id)
        return [t.to_dict() for t in tools]

    @app.post("/api/mcp/servers/{server_id}/tools/discover")
    async def discover_mcp_server_tools(server_id: str) -> list[dict]:
        mcp = _require_mcp()
        try:
            tools = await mcp.registry.discover_tools(server_id)
            return [t.to_dict() for t in tools]
        except KeyError:
            raise HTTPException(status_code=404, detail="MCP server not found") from None
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/mcp/servers/{server_id}/tools/call")
    async def call_mcp_tool(server_id: str, body: dict) -> dict:
        mcp = _require_mcp()
        tool = body.get("tool")
        if not tool:
            raise HTTPException(status_code=400, detail="tool name required")
        arguments = body.get("arguments", {})
        try:
            result = await mcp.invoke_tool(server_id, tool, arguments)
            return result.to_dict()
        except KeyError:
            raise HTTPException(status_code=404, detail="MCP server not found") from None
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Resource Operations
    @app.get("/api/mcp/servers/{server_id}/resources")
    async def list_mcp_server_resources(server_id: str) -> list[dict]:
        mcp = _require_mcp()
        try:
            resources = await mcp.list_server_resources(server_id)
            return [r.to_dict() for r in resources]
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/mcp/servers/{server_id}/resources/read")
    async def read_mcp_server_resource(server_id: str, uri: str) -> dict:
        mcp = _require_mcp()
        try:
            result = await mcp.read_server_resource(server_id, uri)
            return result
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/mcp/servers/{server_id}/resources/subscribe")
    async def subscribe_mcp_resource(server_id: str, body: dict) -> dict:
        mcp = _require_mcp()
        uri = body.get("uri")
        if not uri:
            raise HTTPException(status_code=400, detail="uri required")
        try:
            ok = await mcp.subscribe_server_resource(server_id, uri)
            return {"subscribed": ok, "uri": uri}
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.delete("/api/mcp/servers/{server_id}/resources/subscribe")
    async def unsubscribe_mcp_resource(server_id: str, uri: str) -> dict:
        mcp = _require_mcp()
        try:
            ok = await mcp.unsubscribe_server_resource(server_id, uri)
            return {"unsubscribed": ok, "uri": uri}
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Prompt Operations
    @app.get("/api/mcp/servers/{server_id}/prompts")
    async def list_mcp_server_prompts(server_id: str) -> list[dict]:
        mcp = _require_mcp()
        try:
            prompts = await mcp.list_server_prompts(server_id)
            return [p.to_dict() for p in prompts]
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/mcp/servers/{server_id}/prompts/get")
    async def get_mcp_server_prompt(
        server_id: str, name: str, arguments: str | None = None
    ) -> dict:
        mcp = _require_mcp()
        import json

        args = json.loads(arguments) if arguments else None
        try:
            result = await mcp.get_server_prompt(server_id, name, args)
            return result
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Health & Monitoring
    @app.get("/api/mcp/servers/{server_id}/health")
    async def check_mcp_server_health(server_id: str) -> dict:
        mcp = _require_mcp()
        try:
            health = await mcp.registry.check_health(server_id)
            return {"server_id": server_id, "health": health.value}
        except KeyError:
            raise HTTPException(status_code=404, detail="MCP server not found") from None

    @app.get("/api/mcp/health")
    async def mcp_health_summary() -> dict:
        """Summary of all MCP servers' health status."""
        mcp = _require_mcp()
        servers = await mcp.list_servers()
        statuses = {}
        for s in servers:
            statuses[s.config.id] = {
                "name": s.config.name,
                "status": s.status.value,
                "health": s.health.value,
                "tools": len(s.tools),
            }
        return {
            "total": len(servers),
            "running": sum(1 for s in servers if s.status == MCPServerStatus.RUNNING),
            "servers": statuses,
        }

    # Sessions
    @app.get("/api/mcp/sessions")
    async def list_mcp_sessions() -> dict:
        mcp = _require_mcp()
        sessions = mcp.get_active_session_ids()
        return {"sessions": sessions, "total": len(sessions)}

    # Permissions
    @app.post("/api/mcp/servers/{server_id}/permissions")
    async def set_mcp_permissions(server_id: str, body: dict) -> dict:
        mcp = _require_mcp()
        from agentic_os.domain.mcp import MCPPermissionMapping

        mappings = [
            MCPPermissionMapping(
                tool_name=m["tool_name"],
                capability=m["capability"],
                description=m.get("description"),
            )
            for m in body.get("mappings", [])
        ]
        try:
            count = await mcp.registry.set_permissions(server_id, mappings)
            return {"server_id": server_id, "mappings_count": count}
        except KeyError:
            raise HTTPException(status_code=404, detail="MCP server not found") from None

    @app.get("/api/mcp/servers/{server_id}/permissions")
    async def get_mcp_permissions(server_id: str) -> list[dict]:
        mcp = _require_mcp()
        mappings = await mcp.registry.get_permissions(server_id)
        return [m.to_dict() for m in mappings]

    # ═══════════════════════════════════════════════════════════════════
    #  Swarm Orchestration Engine API (Phase 4, M4)
    # ═══════════════════════════════════════════════════════════════════

    @app.get("/api/swarm/profiles")
    async def list_swarm_profiles() -> list[dict]:
        """List all swarm profiles."""
        profiles = swarm.config.profiles  # ty:ignore[unresolved-attribute]
        return [p.to_dict() for p in profiles.values()]

    @app.get("/api/swarm/profiles/{name}")
    async def get_swarm_profile(name: str) -> dict:
        """Get a swarm profile by name."""
        profile = swarm.config.get_profile(name)  # ty:ignore[unresolved-attribute]
        if profile is None:
            raise HTTPException(status_code=404, detail="Profile not found")
        return profile.to_dict()

    @app.post("/api/swarm/profiles")
    async def create_swarm_profile(body: dict) -> dict:
        """Create a new swarm profile."""
        from agentic_os.domain.orchestration import OrchestrationProfile

        profile = OrchestrationProfile(
            name=body["name"],
            description=body.get("description", ""),
            default_topology=body.get("default_topology", "mesh"),
            max_agents_per_swarm=body.get("max_agents", 10),
            subtask_timeout_seconds=body.get("default_timeout_seconds", 300.0),
            auto_discover_agents=body.get("auto_discover_agents", True),
            tags=tuple(body.get("tags", [])),
        )
        swarm.config.add_profile(profile)  # ty:ignore[unresolved-attribute]
        return profile.to_dict()

    @app.delete("/api/swarm/profiles/{name}")
    async def delete_swarm_profile(name: str) -> dict:
        """Delete a swarm profile."""
        removed = swarm.config.remove_profile(name)  # ty:ignore[unresolved-attribute]
        if not removed:
            raise HTTPException(status_code=404, detail="Profile not found")
        return {"removed": name}

    # ── Swarm CRUD (existing M3 endpoints extended) ──

    @app.get("/api/swarm/swarms")
    async def list_swarms() -> list[dict]:
        """List all swarms."""
        swarms = await swarm.list_swarms()  # ty:ignore[unresolved-attribute]
        return [s.to_dict() for s in swarms]

    @app.get("/api/swarm/swarms/{swarm_id}")
    async def get_swarm(swarm_id: str) -> dict:
        """Get a swarm by ID."""
        result = await swarm.get_swarm(swarm_id)  # ty:ignore[unresolved-attribute]
        if result is None:
            raise HTTPException(status_code=404, detail="Swarm not found")
        return result.to_dict()

    @app.post("/api/swarm/swarms")
    async def create_swarm(body: dict) -> dict:
        """Create a new swarm."""
        result = await swarm.create_swarm(  # ty:ignore[unresolved-attribute]
            name=body["name"],
            description=body.get("description", ""),
            topology=body.get("topology", "mesh"),
            agent_ids=tuple(body.get("agent_ids", [])),
            tags=tuple(body.get("tags", [])),
            metadata=body.get("metadata"),
        )
        return result.to_dict()

    @app.delete("/api/swarm/swarms/{swarm_id}")
    async def delete_swarm(swarm_id: str) -> dict:
        """Delete a swarm."""
        ok = await swarm.delete_swarm(swarm_id)  # ty:ignore[unresolved-attribute]
        if not ok:
            raise HTTPException(status_code=404, detail="Swarm not found")
        return {"deleted": swarm_id}

    # ── Planner ──

    @app.post("/api/swarm/planner/analyze")
    async def analyze_goal(body: dict) -> dict:
        """Analyze a goal for complexity and capability requirements."""
        goal = OrchestrationGoal(
            title=body["title"],
            description=body.get("description", ""),
            context=body.get("context", {}),
            swarm_id=body.get("swarm_id"),
        )
        return await swarm.analyze_goal(goal)  # ty:ignore[unresolved-attribute]

    @app.post("/api/swarm/planner/plan")
    async def create_plan(body: dict) -> dict:
        """Create a full execution plan from a goal."""
        goal = OrchestrationGoal(
            title=body["title"],
            description=body.get("description", ""),
            context=body.get("context", {}),
            swarm_id=body.get("swarm_id"),
        )
        plan = await swarm.create_plan(goal)  # ty:ignore[unresolved-attribute]
        return plan.to_dict()

    @app.post("/api/swarm/planner/resolve-dependencies")
    async def resolve_plan_dependencies(body: dict) -> dict:
        """Resolve and validate all task dependencies."""
        plan = OrchestrationPlan(
            id=body.get("id", ""),
            goal_id=body.get("goal_id", ""),
            subtasks=tuple(_parse_task(t) for t in body.get("subtasks", [])),
            status=body.get("status", "pending"),
            metadata=body.get("metadata", {}),
        )
        resolved = await swarm.resolve_dependencies(plan)  # ty:ignore[unresolved-attribute]
        return resolved.to_dict()

    @app.post("/api/swarm/planner/parallelize")
    async def parallelize_plan(body: dict) -> dict:
        """Identify parallelizable tasks in a plan."""
        plan = OrchestrationPlan(
            id=body.get("id", ""),
            goal_id=body.get("goal_id", ""),
            subtasks=tuple(_parse_task(t) for t in body.get("subtasks", [])),
            status=body.get("status", "pending"),
            metadata=body.get("metadata", {}),
        )
        max_parallel = body.get("max_parallel", 5)
        parallelized = await swarm.parallelize_plan(plan, max_parallel)  # ty:ignore[unresolved-attribute]
        return parallelized.to_dict()

    # ── Scheduler ──

    @app.post("/api/swarm/scheduler/schedule")
    async def schedule_plan_tasks(body: dict) -> dict:
        """Schedule all tasks in a plan using topological sort."""
        plan = _parse_plan(body["plan"])
        agents = [_parse_agent(a) for a in body.get("agents", [])]
        scheduled = await swarm.schedule_tasks(plan, agents)  # ty:ignore[unresolved-attribute]
        return scheduled.to_dict()

    @app.post("/api/swarm/scheduler/dispatch")
    async def dispatch_scheduled_task(body: dict) -> dict:
        """Dispatch a scheduled task to an agent."""
        task = _parse_task(body["task"])
        agent = _parse_agent(body["agent"])
        dispatched = await swarm.dispatch_task(task, agent)  # ty:ignore[unresolved-attribute]
        return dispatched.to_dict()

    @app.get("/api/swarm/scheduler/schedule/{plan_id}")
    async def get_plan_schedule(plan_id: str) -> list[dict]:
        """Get the ordered schedule for a plan."""
        schedule = await swarm.get_schedule(plan_id)  # ty:ignore[unresolved-attribute]
        return [t.to_dict() for t in schedule]

    # ── Supervisor ──

    @app.post("/api/swarm/supervisor/monitor")
    async def monitor_plan_execution(body: dict) -> dict:
        """Monitor a plan's execution for failures/deadlocks."""
        plan = _parse_plan(body)
        monitored = await swarm.monitor_execution(plan)  # ty:ignore[unresolved-attribute]
        return monitored.to_dict()

    @app.post("/api/swarm/supervisor/detect-failures")
    async def detect_plan_failures(body: dict) -> list[dict]:
        """Detect failed or hung tasks in a plan."""
        plan = _parse_plan(body)
        failed = await swarm.detect_failures(plan)  # ty:ignore[unresolved-attribute]
        return [t.to_dict() for t in failed]

    @app.post("/api/swarm/supervisor/detect-deadlocks")
    async def detect_plan_deadlocks(body: dict) -> list[str]:
        """Detect deadlocked dependency chains."""
        plan = _parse_plan(body)
        return await swarm.detect_deadlocks(plan)  # ty:ignore[unresolved-attribute]

    @app.post("/api/swarm/supervisor/restart")
    async def restart_failed_task(body: dict) -> dict:
        """Restart a failed task."""
        task = _parse_task(body["task"])
        agent = _parse_agent(body["agent"]) if body.get("agent") else None
        restarted = await swarm.restart_task(task, agent)  # ty:ignore[unresolved-attribute]
        return restarted.to_dict()

    @app.post("/api/swarm/supervisor/reassign")
    async def reassign_task_agent(body: dict) -> dict:
        """Reassign a task to a different agent."""
        task = _parse_task(body["task"])
        reassigned = await swarm.reassign_task(task, body["new_agent_id"])  # ty:ignore[unresolved-attribute]
        return reassigned.to_dict()

    # ── Result Merger ──

    @app.post("/api/swarm/merge")
    async def merge_task_results(body: dict) -> dict:
        """Merge results from multiple completed tasks."""
        tasks = [_parse_task(t) for t in body["tasks"]]
        strategy_name = body.get("strategy", "consensus")
        try:
            strategy = MergeStrategy(strategy_name)
        except ValueError:
            strategy = MergeStrategy.CONSENSUS
        merged = await swarm.merge_results(tasks, strategy)  # ty:ignore[unresolved-attribute]
        return merged.to_dict()

    @app.post("/api/swarm/merge/resolve")
    async def resolve_merge_conflicts(body: dict) -> dict:
        """Resolve conflicts in a merged result."""
        merged = MergedResult(
            strategy=MergeStrategy(body.get("strategy", "consensus")),
            source_task_ids=tuple(body.get("source_task_ids", [])),
            output=body.get("output", {}),
            conflicts=tuple(body.get("conflicts", [])),
            confidence=body.get("confidence", 0.0),
        )
        resolved = await swarm.resolve_merge_conflicts(merged)  # ty:ignore[unresolved-attribute]
        return resolved.to_dict()

    # ── Validation ──

    @app.post("/api/swarm/validate/output")
    async def validate_task_output(body: dict) -> dict:
        """Validate a task's output against an optional schema."""
        task = _parse_task(body["task"])
        schema = body.get("schema")
        result = await swarm.validate_output(task, schema)  # ty:ignore[unresolved-attribute]
        return result.to_dict()

    @app.post("/api/swarm/validate/plan")
    async def validate_plan_structure(body: dict) -> dict:
        """Validate a plan's structure and dependencies."""
        plan = _parse_plan(body)
        result = await swarm.validate_plan(plan)  # ty:ignore[unresolved-attribute]
        return result.to_dict()

    @app.post("/api/swarm/validate/security")
    async def validate_task_security(body: dict) -> dict:
        """Validate security constraints for a task-agent assignment."""
        task = _parse_task(body["task"])
        agent = _parse_agent(body["agent"])
        result = await swarm.validate_security(task, agent)  # ty:ignore[unresolved-attribute]
        return result.to_dict()

    @app.post("/api/swarm/validate/policy")
    async def validate_task_policy(body: dict) -> dict:
        """Validate a task against execution policies."""
        task = _parse_task(body["task"])
        policies = body.get("policies", {})
        result = await swarm.validate_policy(task, policies)  # ty:ignore[unresolved-attribute]
        return result.to_dict()

    # ── Checkpoint ──

    @app.post("/api/swarm/checkpoints")
    async def save_execution_checkpoint(body: dict) -> dict:
        """Save a checkpoint of the current execution state."""
        plan = _parse_plan(body["plan"])
        stage_data = body.get("stage")
        stage = _parse_stage(stage_data) if stage_data else None
        checkpoint = await swarm.save_checkpoint(plan, stage, body.get("metadata"))  # ty:ignore[unresolved-attribute]
        return checkpoint.to_dict()

    @app.get("/api/swarm/checkpoints/{checkpoint_id}")
    async def restore_execution_checkpoint(checkpoint_id: str) -> dict:
        """Restore execution state from a checkpoint."""
        plan = await swarm.restore_checkpoint(checkpoint_id)  # ty:ignore[unresolved-attribute]
        if plan is None:
            raise HTTPException(status_code=404, detail="Checkpoint not found")
        return plan.to_dict()

    @app.get("/api/swarm/checkpoints")
    async def list_plan_checkpoints(plan_id: str) -> list[dict]:
        """List all checkpoints for a plan."""
        checkpoints = await swarm.list_checkpoints(plan_id)  # ty:ignore[unresolved-attribute]
        return [c.to_dict() for c in checkpoints]

    @app.delete("/api/swarm/checkpoints/{checkpoint_id}")
    async def delete_execution_checkpoint(checkpoint_id: str) -> dict:
        """Delete a checkpoint."""
        ok = await swarm.delete_checkpoint(checkpoint_id)  # ty:ignore[unresolved-attribute]
        if not ok:
            raise HTTPException(status_code=404, detail="Checkpoint not found")
        return {"deleted": checkpoint_id}

    # ── Agent Selection ──

    @app.post("/api/swarm/agent-select")
    async def select_agent_for_task(body: dict) -> dict:
        """Select the best agent for a task."""
        task = _parse_task(body["task"])
        agents_data = body.get("available_agents")
        agents = [_parse_agent(a) for a in agents_data] if agents_data else None
        agent = await swarm.select_agent(task, agents)  # ty:ignore[unresolved-attribute]
        if agent is None:
            raise HTTPException(status_code=404, detail="No suitable agent found")
        return agent.to_dict()

    @app.post("/api/swarm/capability-match")
    async def match_goal_capabilities(body: dict) -> list[dict]:
        """Find agents matching required capabilities."""
        goal = OrchestrationGoal(
            title=body.get("title", ""),
            description=body.get("description", ""),
            context=body.get("context", {}),
        )
        agents = await swarm.match_capabilities(goal, body.get("capabilities", []))  # ty:ignore[unresolved-attribute]
        return [a.to_dict() for a in agents]

    # ── Metrics & Cost ──

    @app.get("/api/swarm/metrics")
    async def get_swarm_metrics() -> dict:
        """Aggregated swarm metrics for the dashboard."""
        swarms = await swarm.list_swarms()  # ty:ignore[unresolved-attribute]
        total_swarms = len(swarms)
        active_swarms = sum(1 for s in swarms if getattr(s, "status", "") == "active")
        total_tasks = 0
        completed_tasks = 0
        failed_tasks = 0
        agents_online = 0
        # Attempt to collect from the registry
        reg = getattr(swarm, "registry", None) or getattr(orch, "registry", None)
        if reg is not None:
            agents = reg.agents()
            agents_online = sum(
                1
                for a in agents
                if getattr(a, "status", "") == "idle" or getattr(a, "status", "") == "active"
            )
            tasks = reg.tasks()
            total_tasks = len(tasks)
            completed_tasks = sum(1 for t in tasks if getattr(t, "status", "") == "completed")
            failed_tasks = sum(1 for t in tasks if getattr(t, "status", "") == "failed")
        return {
            "total_swarms": total_swarms,
            "active_swarms": active_swarms,
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "failed_tasks": failed_tasks,
            "agents_online": agents_online,
        }

    @app.post("/api/swarm/metrics/collect")
    async def collect_execution_metrics(body: dict) -> dict:
        """Collect execution metrics for a plan."""
        plan = _parse_plan(body)
        metrics = await swarm.collect_metrics(plan)  # ty:ignore[unresolved-attribute]
        return metrics.to_dict()

    @app.post("/api/swarm/metrics/timeline")
    async def record_timeline_entry(body: dict) -> dict:
        """Record a timeline entry."""
        entry = ExecutionTimeline(
            plan_id=body.get("plan_id", ""),
            event_type=body.get("event_type", ""),
            stage_id=body.get("stage_id"),
            task_id=body.get("task_id"),
            agent_id=body.get("agent_id"),
            status=body.get("status", ""),
            duration_ms=body.get("duration_ms", 0.0),
            details=body.get("details", {}),
        )
        await swarm.record_timeline(entry)  # ty:ignore[unresolved-attribute]
        return {"recorded": True}

    @app.get("/api/swarm/metrics/timeline/{plan_id}")
    async def get_execution_timeline(plan_id: str, limit: int = 100) -> list[dict]:
        """Get the execution timeline for a plan."""
        entries = await swarm.get_timeline(plan_id, limit)  # ty:ignore[unresolved-attribute]
        return [e.to_dict() for e in entries]

    @app.post("/api/swarm/cost/estimate")
    async def estimate_plan_cost(body: dict) -> dict:
        """Estimate the cost of executing a plan."""
        plan = _parse_plan(body)
        cost = await swarm.estimate_cost(plan)  # ty:ignore[unresolved-attribute]
        return cost.to_dict()

    @app.post("/api/swarm/cost/track")
    async def track_execution_cost(body: dict) -> dict:
        """Track actual cost incurred."""
        cost = await swarm.track_cost(  # ty:ignore[unresolved-attribute]
            plan_id=body["plan_id"],
            agent_id=body["agent_id"],
            cost=body["cost"],
            stage_id=body.get("stage_id"),
        )
        return cost.to_dict()

    @app.get("/api/swarm/cost/{plan_id}")
    async def get_plan_costs(plan_id: str) -> dict:
        """Get accumulated costs for a plan."""
        costs = await swarm.get_costs(plan_id)  # ty:ignore[unresolved-attribute]
        if costs is None:
            return {"plan_id": plan_id, "total_cost": 0.0, "cost_by_agent": {}}
        return costs.to_dict()

    @app.get("/api/swarm/performance/{plan_id}")
    async def analyze_plan_performance(plan_id: str) -> dict:
        """Generate a performance analysis report for a plan."""
        return await swarm.analyze_performance(plan_id)  # ty:ignore[unresolved-attribute]

    # ── Recovery ──

    @app.post("/api/swarm/recovery/task")
    async def recover_failed_task(body: dict) -> dict:
        """Recover a failed task on a suitable agent."""
        task = _parse_task(body["task"])
        agents = [_parse_agent(a) for a in body.get("available_agents", [])]
        recovered = await swarm.recover_task(task, agents)  # ty:ignore[unresolved-attribute]
        return recovered.to_dict()

    @app.post("/api/swarm/recovery/plan")
    async def recover_execution_plan(body: dict) -> dict:
        """Recover a plan from checkpoint or from scratch."""
        plan = _parse_plan(body["plan"])
        checkpoint_data = body.get("checkpoint")
        checkpoint = _parse_checkpoint(checkpoint_data) if checkpoint_data else None
        recovered = await swarm.recover_plan(plan, checkpoint)  # ty:ignore[unresolved-attribute]
        return recovered.to_dict()

    @app.post("/api/swarm/recovery/rollback")
    async def rollback_execution_plan(body: dict) -> dict:
        """Rollback a plan to a specific checkpoint."""
        plan = _parse_plan(body["plan"])
        checkpoint = _parse_checkpoint(body["checkpoint"])
        rolled_back = await swarm.rollback_plan(plan, checkpoint)  # ty:ignore[unresolved-attribute]
        return rolled_back.to_dict()

    # ── Retry ──

    @app.post("/api/swarm/retry/should")
    async def should_retry_task(body: dict) -> dict:
        """Check if a task should be retried."""
        task = _parse_task(body["task"])
        policy_data = body.get("policy")
        policy = _parse_retry_policy(policy_data) if policy_data else None
        should = await swarm.should_retry(task, policy)  # ty:ignore[unresolved-attribute]
        return {"task_id": task.id, "should_retry": should}

    @app.post("/api/swarm/retry/reset")
    async def reset_task_retry(body: dict) -> dict:
        """Reset retry count for a task."""
        await swarm.reset_retry_count(body["task_id"])  # ty:ignore[unresolved-attribute]
        return {"reset": body["task_id"]}

    # ── Goals & Tasks (extended M3) ──

    @app.get("/api/swarm/goals")
    async def list_orchestration_goals(status: str | None = None) -> list[dict]:
        """List orchestration goals."""
        goals = await swarm.list_goals(status)  # ty:ignore[unresolved-attribute]
        return [g.to_dict() for g in goals]

    @app.get("/api/swarm/goals/{goal_id}")
    async def get_orchestration_goal(goal_id: str) -> dict:
        """Get an orchestration goal."""
        goal = await swarm.get_goal(goal_id)  # ty:ignore[unresolved-attribute]
        if goal is None:
            raise HTTPException(status_code=404, detail="Goal not found")
        return goal.to_dict()

    @app.post("/api/swarm/goals")
    async def create_orchestration_goal(body: dict) -> dict:
        """Create an orchestration goal."""
        goal = await swarm.create_goal(  # ty:ignore[unresolved-attribute]
            title=body["title"],
            description=body.get("description", ""),
            context=body.get("context"),
            swarm_id=body.get("swarm_id"),
        )
        return goal.to_dict()

    @app.delete("/api/swarm/goals/{goal_id}")
    async def cancel_orchestration_goal(goal_id: str) -> dict:
        """Cancel a goal."""
        goal = await swarm.cancel_goal(goal_id)  # ty:ignore[unresolved-attribute]
        if goal is None:
            raise HTTPException(status_code=404, detail="Goal not found")
        return goal.to_dict()

    @app.get("/api/swarm/plans/{plan_id}")
    async def get_orchestration_plan(plan_id: str) -> dict:
        """Get an orchestration plan."""
        plan = await swarm.get_plan(plan_id)  # ty:ignore[unresolved-attribute]
        if plan is None:
            raise HTTPException(status_code=404, detail="Plan not found")
        return plan.to_dict()

    @app.get("/api/swarm/tasks")
    async def list_orchestration_tasks(
        goal_id: str | None = None,
        status: str | None = None,
    ) -> list[dict]:
        """List orchestration tasks."""
        tasks = await swarm.list_tasks(goal_id, status)  # ty:ignore[unresolved-attribute]
        return [t.to_dict() for t in tasks]

    @app.get("/api/swarm/tasks/{task_id}")
    async def get_orchestration_task(task_id: str) -> dict:
        """Get a task by ID."""
        task = await swarm.get_task(task_id)  # ty:ignore[unresolved-attribute]
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        return task.to_dict()

    # ─────────────────────────────────────────────────────────────────────────
    # Learning & Optimization Engine API (Phase 4, M5)
    # ─────────────────────────────────────────────────────────────────────────

    # -- Profiles --

    @app.get("/api/learning/profiles")
    async def list_learning_profiles() -> list[dict]:
        profiles = await learning.list_profiles()  # ty:ignore[unresolved-attribute]
        return [p.to_dict() for p in profiles]

    @app.post("/api/learning/profiles")
    async def create_learning_profile(body: dict) -> dict:
        from agentic_os.domain.learning import (
            LearningMetric,
            LearningProfile,
            OptimizationTarget,
            TelemetryGranularity,
        )

        targets = tuple(OptimizationTarget(t) for t in body.get("targets", []) if t)
        metrics = tuple(LearningMetric(m) for m in body.get("metrics", []) if m)
        gran_str = body.get("telemetry_granularity", "hourly")
        try:
            gran = TelemetryGranularity(gran_str)
        except ValueError:
            gran = TelemetryGranularity.HOURLY
        profile = LearningProfile(
            name=body["name"],
            description=body.get("description", ""),
            targets=targets,
            metrics=metrics,
            enabled=body.get("enabled", True),
            telemetry_granularity=gran,
            max_history_size=body.get("max_history_size", 10000),
            min_confidence=body.get("min_confidence", 0.6),
        )
        created = await learning.create_profile(profile)  # ty:ignore[unresolved-attribute]
        return created.to_dict()

    @app.get("/api/learning/profiles/{profile_id}")
    async def get_learning_profile(profile_id: str) -> dict:
        profile = await learning.get_profile(profile_id)  # ty:ignore[unresolved-attribute]
        if profile is None:
            raise HTTPException(status_code=404, detail="Profile not found")
        return profile.to_dict()

    @app.delete("/api/learning/profiles/{profile_id}")
    async def delete_learning_profile(profile_id: str) -> dict:
        await learning.delete_profile(profile_id)  # ty:ignore[unresolved-attribute]
        return {"deleted": profile_id}

    # -- Executions --

    @app.post("/api/learning/executions")
    async def record_execution(body: dict) -> dict:
        from agentic_os.domain.learning import ExecutionHistory

        history = ExecutionHistory(
            execution_id=body.get("execution_id", f"exec-{int(time.time())}"),
            engine_type=body["engine_type"],
            engine_name=body.get("engine_name", ""),
            task_type=body.get("task_type", ""),
            status=body.get("status", "completed"),
            duration_ms=body.get("duration_ms", 0.0),
            cost=body.get("cost", 0.0),
            retry_count=body.get("retry_count", 0),
            error_type=body.get("error_type"),
            swarm_id=body.get("swarm_id"),
            plan_id=body.get("plan_id"),
            model_used=body.get("model_used"),
            metadata=body.get("metadata", {}),
        )
        recorded = await learning.record_execution(history)  # ty:ignore[unresolved-attribute]
        return recorded.to_dict()

    @app.get("/api/learning/executions")
    async def list_executions(
        limit: int = 100, offset: int = 0, engine_type: str | None = None, status: str | None = None
    ) -> list[dict]:
        records = learning._history.list_records(  # ty:ignore[unresolved-attribute]
            engine_type=engine_type, status=status, limit=limit, offset=offset
        )
        return [r.to_dict() for r in records]

    @app.get("/api/learning/executions/{execution_id}")
    async def get_execution(execution_id: str) -> dict:
        record = learning._history.get_record(execution_id)  # ty:ignore[unresolved-attribute]
        if record is None:
            raise HTTPException(status_code=404, detail="Execution not found")
        return record.to_dict()

    # -- Analysis --

    @app.post("/api/learning/analyze")
    async def analyze_executions(body: dict) -> dict:
        history_ids = tuple(body.get("history_ids", []))
        stats = await learning.analyze_executions(history_ids)  # ty:ignore[unresolved-attribute]
        return stats.to_dict()

    @app.get("/api/learning/metrics")
    async def get_learning_metrics(
        period_start: str | None = None, period_end: str | None = None
    ) -> dict:
        metrics = await learning.compute_learning_metrics(period_start, period_end)  # ty:ignore[unresolved-attribute]
        return metrics.to_dict()

    # -- Recommendations --

    @app.get("/api/learning/recommendations")
    async def list_recommendations(status: str | None = None, limit: int = 50) -> list[dict]:
        from agentic_os.domain.learning import RecommendationStatus

        rec_status = RecommendationStatus(status) if status else None
        recs = await learning.list_recommendations(rec_status, limit)  # ty:ignore[unresolved-attribute]
        return [r.to_dict() for r in recs]

    @app.post("/api/learning/recommendations/generate")
    async def generate_recommendation(body: dict) -> dict:
        rec = await learning.generate_recommendation(body["category"], body.get("context", {}))  # ty:ignore[unresolved-attribute]
        return rec.to_dict()

    @app.post("/api/learning/recommendations/{recommendation_id}/apply")
    async def apply_recommendation(recommendation_id: str) -> dict:
        rec = await learning.apply_recommendation(recommendation_id)  # ty:ignore[unresolved-attribute]
        return rec.to_dict()

    @app.post("/api/learning/recommendations/{recommendation_id}/dismiss")
    async def dismiss_recommendation(recommendation_id: str) -> dict:
        rec = await learning.dismiss_recommendation(recommendation_id)  # ty:ignore[unresolved-attribute]
        return rec.to_dict()

    # -- Optimization --

    @app.post("/api/learning/optimization")
    async def optimize(body: dict) -> dict:
        from agentic_os.domain.learning import OptimizationTarget

        target = OptimizationTarget(body["target"])
        result = await learning.optimize(target, body.get("config", {}))  # ty:ignore[unresolved-attribute]
        return result.to_dict()

    @app.get("/api/learning/optimization/results")
    async def list_optimization_results(limit: int = 50) -> list[dict]:
        results = await learning.list_optimization_results(limit)  # ty:ignore[unresolved-attribute]
        return [r.to_dict() for r in results]

    @app.post("/api/learning/optimization/{result_id}/rollback")
    async def rollback_optimization(result_id: str) -> dict:
        result = await learning.rollback_optimization(result_id)  # ty:ignore[unresolved-attribute]
        return result.to_dict()

    # -- Routing --

    @app.post("/api/learning/routing/analyze")
    async def analyze_routing() -> list[dict]:
        recs = await learning.analyze_routing()  # ty:ignore[unresolved-attribute]
        return [r.to_dict() for r in recs]

    @app.post("/api/learning/routing/optimize")
    async def optimize_routing(body: dict) -> dict:
        decision = await learning.optimize_routing(body["recommendation_id"])  # ty:ignore[unresolved-attribute]
        return decision.to_dict()

    @app.get("/api/learning/routing/stats")
    async def get_routing_stats() -> dict:
        return await learning.get_routing_stats()  # ty:ignore[unresolved-attribute]

    # -- Benchmarks --

    @app.post("/api/learning/benchmarks")
    async def create_benchmark(body: dict) -> dict:
        from agentic_os.domain.learning import Benchmark, LearningMetric

        metrics = tuple(LearningMetric(m) for m in body.get("metrics", []) if m)
        benchmark = Benchmark(
            name=body["name"],
            description=body.get("description", ""),
            targets=tuple(body.get("targets", [])),
            metrics=metrics,
            iterations=body.get("iterations", 10),
        )
        created = await learning.create_benchmark(benchmark)  # ty:ignore[unresolved-attribute]
        return created.to_dict()

    @app.post("/api/learning/benchmarks/{benchmark_id}/run")
    async def run_benchmark(benchmark_id: str) -> dict:
        result = await learning.run_benchmark(benchmark_id)  # ty:ignore[unresolved-attribute]
        return result.to_dict()

    @app.get("/api/learning/benchmarks")
    async def list_benchmarks() -> list[dict]:
        benchmarks = await learning.list_benchmarks()  # ty:ignore[unresolved-attribute]
        return [b.to_dict() for b in benchmarks]

    @app.get("/api/learning/benchmarks/{benchmark_id}")
    async def get_benchmark(benchmark_id: str) -> dict:
        benchmark = await learning.get_benchmark(benchmark_id)  # ty:ignore[unresolved-attribute]
        if benchmark is None:
            raise HTTPException(status_code=404, detail="Benchmark not found")
        return benchmark.to_dict()

    @app.delete("/api/learning/benchmarks/{benchmark_id}")
    async def delete_benchmark(benchmark_id: str) -> dict:
        await learning.delete_benchmark(benchmark_id)  # ty:ignore[unresolved-attribute]
        return {"deleted": benchmark_id}

    # -- Experiments --

    @app.post("/api/learning/experiments")
    async def create_experiment(body: dict) -> dict:
        from agentic_os.domain.learning import Experiment, ExperimentType

        exp_type = ExperimentType(body.get("experiment_type", "a_b_test"))
        experiment = Experiment(
            name=body["name"],
            description=body.get("description", ""),
            experiment_type=exp_type,
            control_config=body.get("control_config", {}),
            treatment_config=body.get("treatment_config", {}),
            rollback_on_regression=body.get("rollback_on_regression", True),
        )
        created = await learning.create_experiment(experiment)  # ty:ignore[unresolved-attribute]
        return created.to_dict()

    @app.get("/api/learning/experiments")
    async def list_experiments() -> list[dict]:
        experiments = await learning.list_experiments()  # ty:ignore[unresolved-attribute]
        return [e.to_dict() for e in experiments]

    @app.get("/api/learning/experiments/{experiment_id}")
    async def get_experiment(experiment_id: str) -> dict:
        experiment = await learning.get_experiment(experiment_id)  # ty:ignore[unresolved-attribute]
        if experiment is None:
            raise HTTPException(status_code=404, detail="Experiment not found")
        return experiment.to_dict()

    @app.post("/api/learning/experiments/{experiment_id}/start")
    async def start_experiment(experiment_id: str) -> dict:
        experiment = await learning.start_experiment(experiment_id)  # ty:ignore[unresolved-attribute]
        return experiment.to_dict()

    @app.post("/api/learning/experiments/{experiment_id}/complete")
    async def complete_experiment(experiment_id: str) -> dict:
        experiment = await learning.complete_experiment(experiment_id)  # ty:ignore[unresolved-attribute]
        return experiment.to_dict()

    # -- Evaluation --

    @app.post("/api/learning/evaluate")
    async def evaluate(body: dict) -> dict:
        evaluation = await learning.evaluate(  # ty:ignore[unresolved-attribute]
            body["target_id"],
            body.get("target_type", "engine"),
            body.get("metrics", {}),
        )
        return evaluation.to_dict()

    @app.get("/api/learning/evaluations/{target_id}")
    async def list_evaluations(target_id: str) -> list[dict]:
        evaluations = await learning.list_evaluations(target_id)  # ty:ignore[unresolved-attribute]
        return [e.to_dict() for e in evaluations]

    # -- Performance --

    @app.post("/api/learning/performance/profile")
    async def profile_performance(body: dict) -> dict:
        profile = await learning.profile_performance(  # ty:ignore[unresolved-attribute]
            body["target_id"], body.get("target_type", "engine")
        )
        return profile.to_dict()

    @app.get("/api/learning/performance/trends")
    async def get_performance_trends() -> dict:
        return await learning.get_performance_trends()  # ty:ignore[unresolved-attribute]

    # -- Cost --

    @app.get("/api/learning/cost/metrics")
    async def get_cost_metrics(
        period_start: str | None = None, period_end: str | None = None
    ) -> dict:
        metrics = await learning.get_cost_metrics(period_start, period_end)  # ty:ignore[unresolved-attribute]
        return metrics.to_dict()

    # -- Quality --

    @app.get("/api/learning/quality/metrics")
    async def get_quality_metrics(
        period_start: str | None = None, period_end: str | None = None
    ) -> dict:
        metrics = await learning.get_quality_metrics(period_start, period_end)  # ty:ignore[unresolved-attribute]
        return metrics.to_dict()

    # -- Failure Analysis --

    @app.get("/api/learning/failure-analysis")
    async def get_failure_analysis(
        period_start: str | None = None, period_end: str | None = None
    ) -> dict:
        analysis = await learning.get_failure_analysis(period_start, period_end)  # ty:ignore[unresolved-attribute]
        return analysis.to_dict()

    # -- Policies --

    @app.get("/api/learning/policies")
    async def list_policies() -> list[dict]:
        policies = await learning.list_policies()  # ty:ignore[unresolved-attribute]
        return [p.to_dict() for p in policies]

    @app.post("/api/learning/policies")
    async def create_policy(body: dict) -> dict:
        from agentic_os.domain.learning import OptimizationPolicy, OptimizationTarget, PolicyEffect

        target_enum = OptimizationTarget(body["target"]) if body.get("target") else None
        effect = PolicyEffect(body.get("effect", "allow"))
        policy = OptimizationPolicy(
            name=body["name"],
            description=body.get("description", ""),
            target=target_enum,
            effect=effect,
            conditions=body.get("conditions", {}),
            priority=body.get("priority", 0),
            enabled=body.get("enabled", True),
        )
        created = await learning.create_policy(policy)  # ty:ignore[unresolved-attribute]
        return created.to_dict()

    @app.put("/api/learning/policies/{policy_id}")
    async def update_policy(policy_id: str, body: dict) -> dict:
        existing = await learning._policy.get_policy(policy_id)  # ty:ignore[unresolved-attribute]
        if existing is None:
            raise HTTPException(status_code=404, detail="Policy not found")
        from agentic_os.domain.learning import OptimizationPolicy, OptimizationTarget, PolicyEffect

        updated = OptimizationPolicy(
            id=policy_id,
            name=body.get("name", existing.name),
            description=body.get("description", existing.description),
            target=OptimizationTarget(body["target"]) if body.get("target") else existing.target,
            effect=PolicyEffect(body.get("effect", existing.effect.value)),
            conditions=body.get("conditions", existing.conditions),
            priority=body.get("priority", existing.priority),
            enabled=body.get("enabled", existing.enabled),
        )
        result = await learning.update_policy(updated)  # ty:ignore[unresolved-attribute]
        return result.to_dict()

    @app.delete("/api/learning/policies/{policy_id}")
    async def delete_policy(policy_id: str) -> dict:
        await learning.delete_policy(policy_id)  # ty:ignore[unresolved-attribute]
        return {"deleted": policy_id}

    # -- Telemetry --

    @app.get("/api/learning/latency/metrics")
    async def get_latency_metrics(
        period_start: str | None = None, period_end: str | None = None
    ) -> dict:
        metrics = await learning._telemetry.get_latency_metrics(period_start, period_end)  # ty:ignore[unresolved-attribute]
        return metrics.to_dict()

    # ── Desktop Runtime API (Phase 4, M6) ──

    desktop = platform.desktop

    if desktop is not None:
        # -- Runtime --

        @app.get("/api/desktop/state")
        async def get_desktop_state() -> dict:
            state = await desktop.get_state()
            return state.to_dict()

        @app.get("/api/desktop/status")
        async def get_desktop_status() -> dict:
            return {"status": await desktop.get_status()}

        @app.post("/api/desktop/restart")
        async def restart_desktop() -> dict:
            await desktop.restart()
            return {"status": "restarted"}

        # -- Windows --

        @app.get("/api/desktop/windows")
        async def list_windows() -> list[dict]:
            return [w.to_dict() for w in await desktop.window.list_windows()]

        @app.get("/api/desktop/windows/{window_id}")
        async def get_window(window_id: str) -> dict:
            win = await desktop.window.get_window(window_id)
            if win is None:
                raise HTTPException(404, "Window not found")
            return win.to_dict()

        @app.post("/api/desktop/windows")
        async def create_window(config: dict) -> dict:
            from agentic_os.domain.desktop import WindowConfig

            wc = WindowConfig(
                **{k: v for k, v in config.items() if k in WindowConfig.__dataclass_fields__}
            )
            win = await desktop.window.create_window(wc)
            await desktop.publisher.publish_window_opened(win.id, win.label)
            return win.to_dict()

        @app.delete("/api/desktop/windows/{window_id}")
        async def close_window(window_id: str) -> dict:
            if not await desktop.window.close_window(window_id):
                raise HTTPException(404, "Window not found")
            await desktop.publisher.publish_window_closed(window_id)
            return {"status": "closed"}

        @app.post("/api/desktop/windows/{window_id}/focus")
        async def focus_window(window_id: str) -> dict:
            return {"focused": await desktop.window.focus_window(window_id)}

        @app.post("/api/desktop/windows/{window_id}/minimize")
        async def minimize_window(window_id: str) -> dict:
            return {"minimized": await desktop.window.minimize_window(window_id)}

        @app.post("/api/desktop/windows/{window_id}/maximize")
        async def maximize_window(window_id: str) -> dict:
            return {"maximized": await desktop.window.maximize_window(window_id)}

        @app.post("/api/desktop/windows/{window_id}/restore")
        async def restore_window(window_id: str) -> dict:
            return {"restored": await desktop.window.restore_window(window_id)}

        @app.post("/api/desktop/windows/{window_id}/fullscreen")
        async def fullscreen_window(window_id: str) -> dict:
            return {"fullscreen": await desktop.window.enter_fullscreen(window_id)}

        # -- Workspaces --

        @app.get("/api/desktop/workspaces")
        async def list_workspaces() -> list[dict]:
            return [w.to_dict() for w in await desktop.workspace.list_workspaces()]

        @app.post("/api/desktop/workspaces")
        async def create_workspace(body: dict) -> dict:
            ws = await desktop.workspace.create_workspace(body.get("name", "New Workspace"))
            await desktop.publisher.publish_workspace_created(ws.id, ws.name)
            return ws.to_dict()

        @app.get("/api/desktop/workspaces/{workspace_id}")
        async def get_workspace(workspace_id: str) -> dict:
            ws = await desktop.workspace.get_workspace(workspace_id)
            if ws is None:
                raise HTTPException(404, "Workspace not found")
            return ws.to_dict()

        @app.put("/api/desktop/workspaces/{workspace_id}")
        async def update_workspace(workspace_id: str, body: dict) -> dict:
            ws = await desktop.workspace.get_workspace(workspace_id)
            if ws is None:
                raise HTTPException(404, "Workspace not found")
            for k, v in body.items():
                if hasattr(ws, k):
                    setattr(ws, k, v)
            updated = await desktop.workspace.update_workspace(ws)
            return updated.to_dict()

        @app.delete("/api/desktop/workspaces/{workspace_id}")
        async def delete_workspace(workspace_id: str) -> dict:
            if not await desktop.workspace.delete_workspace(workspace_id):
                raise HTTPException(404, "Workspace not found")
            return {"status": "deleted"}

        @app.post("/api/desktop/workspaces/{workspace_id}/switch")
        async def switch_workspace(workspace_id: str) -> dict:
            ws = await desktop.workspace.switch_workspace(workspace_id)
            await desktop.publisher.publish_workspace_switched(ws.id)
            return ws.to_dict()

        @app.get("/api/desktop/workspaces/active")
        async def get_active_workspace() -> dict | None:
            ws = await desktop.workspace.get_active_workspace()
            return ws.to_dict() if ws else None

        # -- Workspace Layout --

        @app.get("/api/desktop/workspaces/{workspace_id}/layout")
        async def get_workspace_layout(workspace_id: str) -> dict:
            layout = await desktop.workspace.get_workspace_layout(workspace_id)
            if layout is None:
                raise HTTPException(404, "Workspace not found")
            return layout.to_dict()

        @app.put("/api/desktop/workspaces/{workspace_id}/layout")
        async def update_workspace_layout(workspace_id: str, body: dict) -> dict:
            from agentic_os.domain.desktop import WorkspaceLayout

            layout = WorkspaceLayout(
                **{k: v for k, v in body.items() if k in WorkspaceLayout.__dataclass_fields__}
            )
            updated = await desktop.workspace.update_workspace_layout(workspace_id, layout)
            await desktop.publisher.publish_layout_changed(workspace_id, updated.id)
            return updated.to_dict()

        # -- Workspace Tabs --

        @app.post("/api/desktop/workspaces/{workspace_id}/tabs")
        async def add_tab(workspace_id: str, body: dict) -> dict:
            from agentic_os.domain.desktop import TabInfo

            tab = TabInfo(**{k: v for k, v in body.items() if k in TabInfo.__dataclass_fields__})
            added = await desktop.workspace.add_tab(workspace_id, tab)
            return added.to_dict()

        @app.delete("/api/desktop/workspaces/{workspace_id}/tabs/{tab_id}")
        async def remove_tab(workspace_id: str, tab_id: str) -> dict:
            if not await desktop.workspace.remove_tab(workspace_id, tab_id):
                raise HTTPException(404, "Tab not found")
            return {"status": "removed"}

        @app.post("/api/desktop/workspaces/{workspace_id}/tabs/{tab_id}/activate")
        async def activate_tab(workspace_id: str, tab_id: str) -> dict:
            return {"activated": await desktop.workspace.activate_tab(workspace_id, tab_id)}

        # -- Workspace Panels --

        @app.post("/api/desktop/workspaces/{workspace_id}/panels")
        async def add_panel(workspace_id: str, body: dict) -> dict:
            from agentic_os.domain.desktop import PanelConfig

            panel = PanelConfig(
                **{k: v for k, v in body.items() if k in PanelConfig.__dataclass_fields__}
            )
            added = await desktop.workspace.add_panel(workspace_id, panel)
            return added.to_dict()

        @app.delete("/api/desktop/workspaces/{workspace_id}/panels/{panel_id}")
        async def remove_panel(workspace_id: str, panel_id: str) -> dict:
            if not await desktop.workspace.remove_panel(workspace_id, panel_id):
                raise HTTPException(404, "Panel not found")
            return {"status": "removed"}

        # -- Notifications --

        @app.get("/api/desktop/notifications")
        async def list_notifications() -> list[dict]:
            return [n.to_dict() for n in await desktop.notification.list_notifications()]

        @app.post("/api/desktop/notifications")
        async def send_notification(body: dict) -> dict:
            from agentic_os.domain.desktop import DesktopNotification

            notif = DesktopNotification(
                **{k: v for k, v in body.items() if k in DesktopNotification.__dataclass_fields__}
            )
            sent = await desktop.notification.send_notification(notif)
            await desktop.publisher.publish_notification_created(
                sent.id, sent.title, sent.level.value
            )
            return sent.to_dict()

        @app.delete("/api/desktop/notifications/{notification_id}")
        async def dismiss_notification(notification_id: str) -> dict:
            if not await desktop.notification.dismiss_notification(notification_id):
                raise HTTPException(404, "Notification not found")
            return {"status": "dismissed"}

        @app.post("/api/desktop/notifications/{notification_id}/click")
        async def click_notification(notification_id: str) -> dict:
            if not await desktop.notification.mark_clicked(notification_id):
                raise HTTPException(404, "Notification not found")
            await desktop.publisher.publish_notification_clicked(notification_id)
            return {"status": "clicked"}

        @app.get("/api/desktop/notifications/unread/count")
        async def get_unread_count() -> dict:
            return {"count": await desktop.notification.get_unread_count()}

        # -- Configuration --

        @app.get("/api/desktop/config")
        async def get_desktop_config() -> dict:
            cfg = await desktop.configuration.get_config()
            return cfg.to_dict()

        @app.put("/api/desktop/config")
        async def update_desktop_config(body: dict) -> dict:
            cfg = await desktop.configuration.get_config()
            for k, v in body.items():
                if hasattr(cfg, k):
                    setattr(cfg, k, v)
            updated = await desktop.configuration.update_config(cfg)
            return updated.to_dict()

        @app.get("/api/desktop/config/theme")
        async def get_theme() -> dict:
            return {"theme": (await desktop.configuration.get_theme()).value}

        @app.put("/api/desktop/config/theme")
        async def set_theme(body: dict) -> dict:
            from agentic_os.domain.desktop import ThemeMode

            theme = ThemeMode(body.get("theme", "system"))
            await desktop.configuration.set_theme(theme)
            await desktop.publisher.publish_theme_changed(theme.value)
            return {"theme": theme.value}

        # -- Diagnostics --

        @app.get("/api/desktop/diagnostics")
        async def get_diagnostics() -> dict:
            return (await desktop.diagnostics.get_diagnostics()).to_dict()

        @app.get("/api/desktop/diagnostics/health")
        async def desktop_health() -> dict:
            return await desktop.diagnostics.check_health()

        # -- Performance --

        @app.get("/api/desktop/performance")
        async def get_performance() -> dict:
            return (await desktop.performance.get_metrics()).to_dict()

        @app.get("/api/desktop/performance/history/{metric}")
        async def get_metric_history(metric: str, limit: int = 60) -> dict:
            return {
                "metric": metric,
                "values": list(await desktop.performance.get_metric_history(metric, limit)),
            }

        @app.post("/api/desktop/performance/monitor/start")
        async def start_monitoring() -> dict:
            await desktop.performance.start_monitoring()
            return {"status": "started"}

        @app.post("/api/desktop/performance/monitor/stop")
        async def stop_monitoring() -> dict:
            await desktop.performance.stop_monitoring()
            return {"status": "stopped"}

        # -- Menus --

        @app.get("/api/desktop/menus")
        async def list_menus() -> list[dict]:
            return [m.to_dict() for m in await desktop.menu.list_menus()]

        @app.post("/api/desktop/menus")
        async def create_menu(body: dict) -> dict:
            from agentic_os.domain.desktop import MenuConfig

            menu = MenuConfig(
                **{k: v for k, v in body.items() if k in MenuConfig.__dataclass_fields__}
            )
            created = await desktop.menu.create_menu(menu)
            return created.to_dict()

        @app.get("/api/desktop/menus/default")
        async def get_default_menus() -> list[dict]:
            return [m.to_dict() for m in await desktop.menu.get_default_menus()]

        # -- File Dialogs --

        @app.post("/api/desktop/file/open")
        async def open_file_dialog(body: dict) -> dict:
            from agentic_os.domain.desktop import DialogConfig

            config = DialogConfig(
                **{k: v for k, v in body.items() if k in DialogConfig.__dataclass_fields__}
            )
            result = await desktop.file.open_file_dialog(config)
            return result.to_dict()

        @app.post("/api/desktop/file/save")
        async def save_file_dialog(body: dict) -> dict:
            from agentic_os.domain.desktop import DialogConfig

            config = DialogConfig(
                **{k: v for k, v in body.items() if k in DialogConfig.__dataclass_fields__}
            )
            result = await desktop.file.save_file_dialog(config)
            return result.to_dict()

        # -- Clipboard --

        @app.get("/api/desktop/clipboard")
        async def get_clipboard() -> dict:
            content = await desktop.clipboard.get_content()
            return content.to_dict()

        @app.put("/api/desktop/clipboard")
        async def set_clipboard(body: dict) -> dict:
            from agentic_os.domain.desktop import ClipboardContent

            content = ClipboardContent(
                **{k: v for k, v in body.items() if k in ClipboardContent.__dataclass_fields__}
            )
            await desktop.clipboard.set_content(content)
            return {"status": "updated"}

        # -- Terminal --

        @app.get("/api/desktop/terminals")
        async def list_terminals() -> list[dict]:
            return [t.to_dict() for t in await desktop.terminal.list_terminals()]

        @app.post("/api/desktop/terminals")
        async def open_terminal(body: dict) -> dict:
            from agentic_os.domain.desktop import TerminalConfig

            config = TerminalConfig(
                **{k: v for k, v in body.items() if k in TerminalConfig.__dataclass_fields__}
            )
            info = await desktop.terminal.open_terminal(config)
            return info.to_dict()

        @app.delete("/api/desktop/terminals/{terminal_id}")
        async def close_terminal(terminal_id: str) -> dict:
            if not await desktop.terminal.close_terminal(terminal_id):
                raise HTTPException(404, "Terminal not found")
            return {"status": "closed"}

        # -- Keyboard Shortcuts --

        @app.get("/api/desktop/shortcuts")
        async def list_shortcuts() -> list[dict]:
            return [s.to_dict() for s in await desktop.list_shortcuts()]

        # -- Command Palette --

        @app.get("/api/desktop/command-palette")
        async def get_command_palette() -> list[dict]:
            return list(await desktop.get_command_palette_items())

        # -- Global Search --

        @app.get("/api/desktop/search")
        async def global_search(q: str = "") -> list[dict]:
            return list(await desktop.global_search(q))

        # -- Database --

        @app.get("/api/desktop/database")
        async def get_database_info() -> dict:
            return (await desktop.database.get_info()).to_dict()

        # -- Phase 4 M6 Part 2: Installer, Updates, Discovery, Offline, Backup --

        # -- Runtime Discovery --

        @app.get("/api/desktop/runtimes")
        async def list_runtimes() -> list[dict]:
            if desktop.runtime_discovery is None:
                return []
            return [r.to_dict() for r in await desktop.runtime_discovery.get_discovered_runtimes()]

        @app.post("/api/desktop/runtimes/discover")
        async def discover_runtimes() -> dict:
            if desktop.runtime_discovery is None:
                return {"total_discovered": 0, "runtimes": []}
            result = await desktop.runtime_discovery.discover_runtimes()
            return result.to_dict()

        @app.get("/api/desktop/runtimes/{runtime_type}")
        async def get_runtime(runtime_type: str) -> dict:
            if desktop.runtime_discovery is None:
                raise HTTPException(404, "Runtime discovery not available")
            from agentic_os.domain.desktop import RuntimeType

            try:
                rt = RuntimeType(runtime_type)
            except ValueError:
                raise HTTPException(400, f"Unknown runtime type: {runtime_type}") from None
            info = await desktop.runtime_discovery.get_runtime(rt)
            if info is None:
                raise HTTPException(404, f"Runtime not found: {runtime_type}")
            return info.to_dict()

        @app.post("/api/desktop/runtimes/{runtime_type}/verify")
        async def verify_runtime(runtime_type: str) -> dict:
            if desktop.runtime_discovery is None:
                return {"verified": False}
            from agentic_os.domain.desktop import RuntimeType

            rt = RuntimeType(runtime_type)
            return {"verified": await desktop.runtime_discovery.verify_runtime(rt)}

        # -- Auto Updates --

        @app.get("/api/desktop/updates/check")
        async def check_updates(channel: str = "stable") -> list[dict]:
            if desktop.update is None:
                return []
            from agentic_os.domain.desktop import UpdateChannel

            ch = UpdateChannel(channel)
            releases = await desktop.update.check_for_updates(ch)
            return [r.to_dict() for r in releases]

        @app.get("/api/desktop/updates/status")
        async def get_update_status() -> dict:
            if desktop.update is None:
                return {"status": "idle", "version": "1.0.0-rc1"}
            return {
                "status": (await desktop.update.get_update_status()).value,
                "version": await desktop.update.get_current_version(),
            }

        @app.get("/api/desktop/updates/history")
        async def get_update_history(limit: int = 50) -> list[dict]:
            if desktop.update is None:
                return []
            return [h.to_dict() for h in await desktop.update.get_update_history(limit)]

        @app.get("/api/desktop/updates/pending")
        async def get_pending_update() -> dict | None:
            if desktop.update is None:
                return None
            manifest = await desktop.update.get_pending_update()
            return manifest.to_dict() if manifest else None

        @app.get("/api/desktop/updates/version")
        async def get_current_version() -> dict:
            if desktop.update is None:
                return {"version": "1.0.0-rc1"}
            return {"version": await desktop.update.get_current_version()}

        @app.post("/api/desktop/updates/download")
        async def download_update(body: dict) -> dict:
            if desktop.update is None:
                raise HTTPException(503, "Update manager not available")
            from agentic_os.domain.desktop import UpdateManifest

            manifest = UpdateManifest(
                **{k: v for k, v in body.items() if k in UpdateManifest.__dataclass_fields__}
            )
            success = await desktop.update.download_update(manifest)
            return {"success": success}

        @app.post("/api/desktop/updates/install")
        async def install_update(body: dict) -> dict:
            if desktop.update is None:
                raise HTTPException(503, "Update manager not available")
            from agentic_os.domain.desktop import UpdateManifest

            manifest = UpdateManifest(
                **{k: v for k, v in body.items() if k in UpdateManifest.__dataclass_fields__}
            )
            result = await desktop.update.install_update(manifest)
            return result.to_dict()

        # -- Update Channels --

        @app.get("/api/desktop/channels")
        async def get_channels() -> list[str]:
            if desktop.channel is None:
                return ["stable"]
            return [c.value for c in await desktop.channel.get_channels()]

        @app.get("/api/desktop/channels/current")
        async def get_current_channel() -> dict:
            if desktop.channel is None:
                return {"channel": "stable"}
            return {"channel": (await desktop.channel.get_current_channel()).value}

        @app.put("/api/desktop/channels")
        async def set_channel(body: dict) -> dict:
            if desktop.channel is None:
                raise HTTPException(503, "Channel manager not available")
            from agentic_os.domain.desktop import UpdateChannel

            ch = UpdateChannel(body.get("channel", "stable"))
            await desktop.channel.set_channel(ch)
            return {"channel": ch.value}

        # -- Rollback --

        @app.post("/api/desktop/rollback")
        async def rollback(body: dict | None = None) -> dict:
            if desktop.rollback is None:
                raise HTTPException(503, "Rollback manager not available")
            target = body.get("target_version") if body else None
            result = await desktop.rollback.rollback(target)
            return result.to_dict()

        @app.get("/api/desktop/rollback/available")
        async def get_rollback_versions() -> list[str]:
            if desktop.rollback is None:
                return []
            return list(await desktop.rollback.get_available_versions())

        # -- Installer --

        @app.post("/api/desktop/installer/generate")
        async def generate_installer(body: dict) -> dict:
            if desktop.installer is None:
                raise HTTPException(503, "Installer manager not available")
            from agentic_os.domain.desktop import InstallerConfig

            config = InstallerConfig(
                **{k: v for k, v in body.items() if k in InstallerConfig.__dataclass_fields__}
            )
            result = await desktop.installer.generate_installer(config)
            return result.to_dict()

        @app.post("/api/desktop/installer/generate-all")
        async def generate_all_installers(body: dict) -> list[dict]:
            if desktop.installer is None:
                raise HTTPException(503, "Installer manager not available")
            from agentic_os.domain.desktop import InstallerConfig

            config = InstallerConfig(
                **{k: v for k, v in body.items() if k in InstallerConfig.__dataclass_fields__}
            )
            results = await desktop.installer.generate_all(config)
            return [r.to_dict() for r in results]

        @app.get("/api/desktop/installer/supported-types")
        async def get_supported_installer_types() -> list[str]:
            if desktop.installer is None:
                return []
            return [t.value for t in await desktop.installer.get_supported_types()]

        @app.post("/api/desktop/installer/validate")
        async def validate_installer(body: dict) -> dict:
            if desktop.installer is None:
                raise HTTPException(503, "Installer manager not available")
            return await desktop.installer.validate_installer(body.get("path", ""))

        # -- First Run Wizard --

        @app.get("/api/desktop/first-run")
        async def get_first_run_state() -> dict:
            if desktop.first_run is None:
                return {"completed": True}
            return (await desktop.first_run.get_state()).to_dict()

        @app.post("/api/desktop/first-run/step")
        async def run_first_run_step(body: dict) -> dict:
            if desktop.first_run is None:
                return {"success": False, "error": "First run wizard not available"}
            return await desktop.first_run.run_step(body.get("step", "welcome"))

        @app.post("/api/desktop/first-run/complete")
        async def complete_first_run() -> dict:
            if desktop.first_run is None:
                return {"status": "already_completed"}
            await desktop.first_run.complete()
            return {"status": "completed"}

        # -- Offline Mode --

        @app.get("/api/desktop/offline")
        async def get_offline_state() -> dict:
            if desktop.offline is None:
                return {"state": "online"}
            return {"state": (await desktop.offline.get_offline_state()).value}

        @app.post("/api/desktop/offline/enable")
        async def enable_offline() -> dict:
            if desktop.offline is None:
                raise HTTPException(503, "Offline manager not available")
            await desktop.offline.enable_offline_mode()
            return {"state": "offline"}

        @app.post("/api/desktop/offline/disable")
        async def disable_offline() -> dict:
            if desktop.offline is None:
                return {"state": "online"}
            await desktop.offline.disable_offline_mode()
            return {"state": "online"}

        @app.get("/api/desktop/offline/events")
        async def get_queued_events() -> list[dict]:
            if desktop.offline is None:
                return []
            return list(await desktop.offline.get_queued_events())

        @app.post("/api/desktop/offline/sync")
        async def sync_offline_events() -> dict:
            if desktop.offline is None:
                return {"synced": 0}
            count = await desktop.offline.sync_queued_events()
            return {"synced": count}

        # -- Backup / Restore --

        @app.post("/api/desktop/backup")
        async def create_backup(body: dict) -> dict:
            if desktop.backup is None:
                raise HTTPException(503, "Backup manager not available")
            from agentic_os.domain.desktop import BackupConfig

            config = BackupConfig(
                **{k: v for k, v in body.items() if k in BackupConfig.__dataclass_fields__}
            )
            result = await desktop.backup.create_backup(config)
            return result.to_dict()

        @app.get("/api/desktop/backups")
        async def list_backups() -> list[dict]:
            if desktop.backup is None:
                return []
            return [b.to_dict() for b in await desktop.backup.list_backups()]

        @app.post("/api/desktop/restore")
        async def restore_backup(body: dict) -> dict:
            if desktop.backup is None:
                raise HTTPException(503, "Backup manager not available")
            from agentic_os.domain.desktop import RestoreConfig

            config = RestoreConfig(
                **{k: v for k, v in body.items() if k in RestoreConfig.__dataclass_fields__}
            )
            result = await desktop.backup.restore(config)
            return result.to_dict()

        @app.get("/api/desktop/restore/points")
        async def get_restore_points() -> dict:
            if desktop.backup is None:
                return {"points": []}
            return {"points": list(await desktop.backup.get_available_restore_points())}

        # -- Production Hardening --

        @app.get("/api/desktop/hardening/config")
        async def get_hardening_config() -> dict:
            return (await desktop.hardening.get_config()).to_dict()

        @app.put("/api/desktop/hardening/config")
        async def update_hardening_config(body: dict) -> dict:
            from agentic_os.domain.desktop import HardeningConfig

            config = HardeningConfig(
                **{k: v for k, v in body.items() if k in HardeningConfig.__dataclass_fields__}
            )
            return (await desktop.hardening.update_config(config)).to_dict()

        @app.post("/api/desktop/hardening/validate")
        async def run_startup_validation() -> dict:
            return (await desktop.hardening.validate_startup()).to_dict()

        @app.post("/api/desktop/hardening/integrity")
        async def run_integrity_check() -> dict:
            return (await desktop.hardening.check_integrity()).to_dict()

        @app.post("/api/desktop/hardening/diagnostics")
        async def run_diagnostics() -> dict:
            return (await desktop.hardening.run_self_diagnostics()).to_dict()

        @app.post("/api/desktop/hardening/memory")
        async def check_memory() -> dict:
            return (await desktop.hardening.check_memory_leaks()).to_dict()

        @app.post("/api/desktop/hardening/threads")
        async def check_threads() -> dict:
            return (await desktop.hardening.monitor_threads()).to_dict()

        @app.post("/api/desktop/hardening/cleanup")
        async def cleanup_resources() -> dict:
            return (await desktop.hardening.cleanup_resources()).to_dict()

        @app.post("/api/desktop/hardening/repair")
        async def repair_system(body: dict | None = None) -> dict:
            targets = body.get("targets") if body else None
            return (await desktop.hardening.repair(targets)).to_dict()

        @app.get("/api/desktop/hardening/recovery")
        async def get_recovery_status() -> dict:
            return {"in_recovery": await desktop.hardening.is_in_recovery()}

        @app.post("/api/desktop/hardening/recovery/enter")
        async def enter_recovery() -> dict:
            return {"success": await desktop.hardening.enter_recovery_mode()}

        @app.post("/api/desktop/hardening/recovery/exit")
        async def exit_recovery() -> dict:
            return {"success": await desktop.hardening.exit_recovery_mode()}

        @app.post("/api/desktop/hardening/recover")
        async def recover() -> dict:
            return (await desktop.hardening.recover()).to_dict()

        @app.get("/api/desktop/hardening/resources")
        async def get_resource_usage() -> dict:
            return (await desktop.hardening.get_resource_usage()).to_dict()

        @app.post("/api/desktop/hardening/shutdown")
        async def plan_shutdown(body: dict | None = None) -> dict:
            force = body.get("force", False) if body else False
            return (await desktop.hardening.plan_shutdown(force=force)).to_dict()

        @app.get("/api/desktop/hardening/cleanup-history")
        async def get_cleanup_history() -> dict:
            history = await desktop.hardening.get_cleanup_history()
            return {"history": [r.to_dict() for r in history]}

        @app.get("/api/desktop/hardening/recovery-history")
        async def get_recovery_history() -> dict:
            return {"history": list(await desktop.hardening.get_recovery_history())}

        @app.get("/api/desktop/hardening/repair-history")
        async def get_repair_history() -> dict:
            return {"history": list(await desktop.hardening.get_repair_history())}

        # -- Drag & Drop --

        @app.post("/api/desktop/dragdrop")
        async def handle_drop(body: dict) -> dict:
            from agentic_os.domain.desktop import DragDropPayload

            payload = DragDropPayload(
                **{k: v for k, v in body.items() if k in DragDropPayload.__dataclass_fields__}
            )
            result = await desktop.dragdrop.handle_drop(payload)
            return result

    # ── Event history (REST replay for frontend cold-start) ──
    @app.get("/api/events/recent")
    async def get_recent_events(limit: int = 50) -> list[dict]:
        return platform.dashboard.get_recent_events(limit)

    # ── Minimal provider management UI page (Phase 3 builds Mission Control) ──
    @app.get("/providers", response_class=HTMLResponse)
    async def providers_page() -> str:
        return _PROVIDER_PAGE

    @app.websocket("/ws/dashboard")
    async def dashboard_ws(websocket: WebSocket) -> None:
        dashboard = platform.dashboard
        if dashboard is None:
            await websocket.accept()
            payload = {
                "topic": "system.status",
                "payload": {"status": "degraded", "message": "DashboardBroadcaster not available"},
            }
            await websocket.send_json(payload)
            await websocket.close(code=1011, reason="Dashboard not available")
            return
        await websocket.accept()
        recv, send = dashboard.add_client()
        log.info("dashboard.connected")
        try:
            async with recv:
                async for snapshot in recv:
                    await websocket.send_json(snapshot)
        except WebSocketDisconnect:
            pass
        finally:
            dashboard.remove_client(send)
            log.info("dashboard.disconnected")

    @app.websocket("/ws/mcp")
    async def mcp_ws(websocket: WebSocket) -> None:
        from agentic_os.api.mcp_ws import MCPBroadcaster

        mcp_bc: MCPBroadcaster | None = platform.mcp_ws
        if mcp_bc is None:
            await websocket.accept()
            await websocket.close(code=1011, reason="MCP WebSocket not available")
            return
        await websocket.accept()
        recv, send = mcp_bc.add_client()
        log.info("mcp_ws.connected")
        try:
            async with recv:
                async for snapshot in recv:
                    await websocket.send_json(snapshot)
        except WebSocketDisconnect:
            pass
        finally:
            mcp_bc.remove_client(send)
            log.info("mcp_ws.disconnected")

    # ── OpenAI-compatible /v1 API Gateway ─────────────────────────────────
    if hasattr(platform, "provider_mgr"):
        try:
            from agentic_os.api.gateway import create_gateway_router

            gw_router = create_gateway_router(platform.provider_mgr)
            app.include_router(gw_router)
            log.info("gateway.mounted")
        except ImportError as exc:
            log.warning("gateway.not_available", error=str(exc))
    else:
        log.warning("gateway.skipped_no_provider_mgr")

    return app


_PROVIDER_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Agentic OS — Provider Management</title>
<style>body{font-family:system-ui;margin:2rem;background:#0f1115;color:#e6e6e6}
h1{font-weight:600}
.card{background:#171a21;border:1px solid #2a2f3a;border-radius:10px;padding:1rem;margin:1rem 0}
input,select{background:#0f1115;color:#e6e6e6;border:1px solid #2a2f3a;border-radius:6px}
input,select{padding:.4rem;margin:.2rem}
button{background:#2b6cff;color:#fff;border:0;border-radius:6px}
button{padding:.5rem .8rem}
button{cursor:pointer}
pre{background:#0f1115;padding:.6rem;border-radius:6px;overflow:auto}</style></head>
<body><h1>Agentic OS — Provider Management</h1>
<div class="card"><h3>Add / Edit Provider</h3>
<form id="f"><input id="name" placeholder="name" required>
<input id="kind" placeholder="kind (mock|openai_compatible|claude_code)" required>
<input id="base_url" placeholder="base_url" size="32">
<input id="default_model" placeholder="default_model">
<input id="api_key" placeholder="api_key" size="32">
<button type="submit">Save + Store Key</button></form></div>
<div class="card"><h3>Providers</h3><pre id="providers">loading…</pre></div>
<div class="card"><h3>Health / Test</h3><pre id="health">—</pre></div>
<script>
const api="http://"+location.host;
async function refresh(){const p=await (await fetch(api+"/api/provider-configs")).json();
document.getElementById("providers").textContent=JSON.stringify(p,null,2);
const h=await (await fetch(api+"/api/provider-health")).json();
document.getElementById("health").textContent=JSON.stringify(h,null,2);}
document.getElementById("f").onsubmit=async e=>{e.preventDefault();
const name=document.getElementById("name").value;
const cfg={name,kind:document.getElementById("kind").value,
base_url:document.getElementById("base_url").value,
default_model:document.getElementById("default_model").value};
await fetch(api+"/api/provider-configs",{method:"POST",headers:{"content-type":"application/json"},
body:JSON.stringify(cfg)});
const key=document.getElementById("api_key").value;
if(key) await fetch(api+`/api/providers/${name}/api-key`,{method:"POST",
headers:{"content-type":"application/json"},body:JSON.stringify({api_key:key})});
await fetch(api+`/api/providers/${name}/test`,{method:"POST"});refresh();};
refresh();setInterval(refresh,3000);
</script></body></html>"""
