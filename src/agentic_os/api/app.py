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

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response

from agentic_os.config import settings
from agentic_os.core.mcp.manager import MCPManager
from agentic_os.domain.agent import Task
from agentic_os.domain.execution import EngineCapability, EngineType
from agentic_os.domain.mcp import MCPServerStatus
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
    app = FastAPI(title="Agentic OS", version="0.2.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "tauri://localhost",
            "https://tauri.localhost",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    orch = platform.orchestrator
    swarm = platform.orchestration
    if swarm is None:
        raise RuntimeError(
            "OrchestrationFramework is required but was not initialised on the Platform"
        )
    pm = platform.provider_mgr
    vault = platform.vault
    phealth = platform.provider_health
    cost = platform.cost
    rate = platform.rate
    router = platform.router
    capability = platform.capability
    if capability is None:
        raise RuntimeError("CapabilityEngine is required but was not initialised on the Platform")
    memory = platform.memory
    if memory is None:
        raise RuntimeError("MemoryManager is required but was not initialised on the Platform")
    security = platform.security
    if security is None:
        raise RuntimeError("SecurityFramework is required but was not initialised on the Platform")

    workflow_engine = platform.workflow
    pipeline_engine = platform.pipeline

    if workflow_engine is None:
        raise RuntimeError("WorkflowEngine is required but was not initialised on the Platform")
    if pipeline_engine is None:
        raise RuntimeError("PipelineEngine is required but was not initialised on the Platform")

    learning = platform.learning
    if learning is None:
        raise RuntimeError("LearningManager is required but was not initialised on the Platform")

    @app.middleware("http")
    async def _metrics(request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        observe(request.method, request.url.path, response.status_code, time.perf_counter() - start)
        return response

    @app.get("/healthz")
    async def healthz() -> dict:
        return {"status": "ok", "bus": settings.bus_type}

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
            for c in capability.registry.all()
        ]

    @app.post("/api/agents/compose")
    async def compose_agent(body: dict) -> dict:
        spec = capability.composer.compose(
            name=body.get("name", "composed-agent"),
            capabilities=body.get("capabilities", []),
            provider=body.get("provider", ""),
            model=body.get("model", ""),
        )
        return spec.model_dump(mode="json")

    @app.post("/api/agents/compose-for-task")
    async def compose_for_task(task: Task) -> dict:
        spec = await capability.compose_and_emit(task)
        return spec.model_dump(mode="json")

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
        stored = await memory.write(item)
        return stored.model_dump(mode="json")

    @app.get("/api/memory/{scope}")
    async def read_memory_scope(scope: str, agent_id: str = "") -> list[dict]:
        from agentic_os.domain.memory import MemoryScope

        return [
            i.model_dump(mode="json")
            for i in await memory.store.list_scope(MemoryScope(scope), agent_id)
        ]

    @app.get("/api/memory/{scope}/recall")
    async def recall_memory(
        scope: str, query: str = "", limit: int = 10, agent_id: str = ""
    ) -> list[dict]:
        from agentic_os.domain.memory import MemoryScope

        return [
            i.model_dump(mode="json")
            for i in await memory.recall(MemoryScope(scope), query, limit, agent_id)
        ]

    @app.delete("/api/memory/{item_id}")
    async def forget_memory(item_id: str) -> dict:
        ok = await memory.forget(item_id)
        return {"forgotten": ok}

    @app.post("/api/memory/retention")
    async def enforce_retention() -> dict:
        evicted = await memory.enforce_retention()
        return {"evicted": evicted}

    # ── Security Framework API (Phase 2, Subsystem 4) ──
    @app.post("/api/security/assign")
    async def assign_role(body: dict) -> dict:
        from agentic_os.domain.security import Principal, Role

        principal = Principal(id=body["principal"], roles=[Role(r) for r in body.get("roles", [])])
        security.ac.assign(principal, Role(body["role"]))
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
        decision = await security.authorize(principal, request)
        return decision.model_dump(mode="json")

    @app.post("/api/security/approval/{request_id}/decide")
    async def decide_approval(request_id: str, body: dict) -> dict:
        await security.gate.decide(request_id, bool(body.get("approved")), body.get("by", ""))
        return {"decided": request_id}

    @app.get("/api/security/approval/{request_id}")
    async def approval_status(request_id: str) -> dict:
        decision = security.gate.status(request_id)
        return decision.model_dump(mode="json") if decision else {"status": "unknown"}

    @app.get("/api/security/audit")
    async def audit_log(principal: str | None = None) -> list[dict]:
        entries = await security.audit.query(principal)
        return [e.model_dump(mode="json") for e in entries]

    @app.get("/api/security/workspace/{agent_id}")
    async def workspace_for(agent_id: str) -> dict:
        return {"agent_id": agent_id, "workspace": security.workspace_for(agent_id)}

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
        profiles = swarm.config.profiles
        return [p.to_dict() for p in profiles.values()]

    @app.get("/api/swarm/profiles/{name}")
    async def get_swarm_profile(name: str) -> dict:
        """Get a swarm profile by name."""
        profile = swarm.config.get_profile(name)
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
        swarm.config.add_profile(profile)
        return profile.to_dict()

    @app.delete("/api/swarm/profiles/{name}")
    async def delete_swarm_profile(name: str) -> dict:
        """Delete a swarm profile."""
        removed = swarm.config.remove_profile(name)
        if not removed:
            raise HTTPException(status_code=404, detail="Profile not found")
        return {"removed": name}

    # ── Swarm CRUD (existing M3 endpoints extended) ──

    @app.get("/api/swarm/swarms")
    async def list_swarms() -> list[dict]:
        """List all swarms."""
        swarms = await swarm.list_swarms()
        return [s.to_dict() for s in swarms]

    @app.get("/api/swarm/swarms/{swarm_id}")
    async def get_swarm(swarm_id: str) -> dict:
        """Get a swarm by ID."""
        result = await swarm.get_swarm(swarm_id)
        if result is None:
            raise HTTPException(status_code=404, detail="Swarm not found")
        return result.to_dict()

    @app.post("/api/swarm/swarms")
    async def create_swarm(body: dict) -> dict:
        """Create a new swarm."""
        result = await swarm.create_swarm(
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
        ok = await swarm.delete_swarm(swarm_id)
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
        return await swarm.analyze_goal(goal)

    @app.post("/api/swarm/planner/plan")
    async def create_plan(body: dict) -> dict:
        """Create a full execution plan from a goal."""
        goal = OrchestrationGoal(
            title=body["title"],
            description=body.get("description", ""),
            context=body.get("context", {}),
            swarm_id=body.get("swarm_id"),
        )
        plan = await swarm.create_plan(goal)
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
        resolved = await swarm.resolve_dependencies(plan)
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
        parallelized = await swarm.parallelize_plan(plan, max_parallel)
        return parallelized.to_dict()

    # ── Scheduler ──

    @app.post("/api/swarm/scheduler/schedule")
    async def schedule_plan_tasks(body: dict) -> dict:
        """Schedule all tasks in a plan using topological sort."""
        plan = _parse_plan(body["plan"])
        agents = [_parse_agent(a) for a in body.get("agents", [])]
        scheduled = await swarm.schedule_tasks(plan, agents)
        return scheduled.to_dict()

    @app.post("/api/swarm/scheduler/dispatch")
    async def dispatch_scheduled_task(body: dict) -> dict:
        """Dispatch a scheduled task to an agent."""
        task = _parse_task(body["task"])
        agent = _parse_agent(body["agent"])
        dispatched = await swarm.dispatch_task(task, agent)
        return dispatched.to_dict()

    @app.get("/api/swarm/scheduler/schedule/{plan_id}")
    async def get_plan_schedule(plan_id: str) -> list[dict]:
        """Get the ordered schedule for a plan."""
        schedule = await swarm.get_schedule(plan_id)
        return [t.to_dict() for t in schedule]

    # ── Supervisor ──

    @app.post("/api/swarm/supervisor/monitor")
    async def monitor_plan_execution(body: dict) -> dict:
        """Monitor a plan's execution for failures/deadlocks."""
        plan = _parse_plan(body)
        monitored = await swarm.monitor_execution(plan)
        return monitored.to_dict()

    @app.post("/api/swarm/supervisor/detect-failures")
    async def detect_plan_failures(body: dict) -> list[dict]:
        """Detect failed or hung tasks in a plan."""
        plan = _parse_plan(body)
        failed = await swarm.detect_failures(plan)
        return [t.to_dict() for t in failed]

    @app.post("/api/swarm/supervisor/detect-deadlocks")
    async def detect_plan_deadlocks(body: dict) -> list[str]:
        """Detect deadlocked dependency chains."""
        plan = _parse_plan(body)
        return await swarm.detect_deadlocks(plan)

    @app.post("/api/swarm/supervisor/restart")
    async def restart_failed_task(body: dict) -> dict:
        """Restart a failed task."""
        task = _parse_task(body["task"])
        agent = _parse_agent(body["agent"]) if body.get("agent") else None
        restarted = await swarm.restart_task(task, agent)
        return restarted.to_dict()

    @app.post("/api/swarm/supervisor/reassign")
    async def reassign_task_agent(body: dict) -> dict:
        """Reassign a task to a different agent."""
        task = _parse_task(body["task"])
        reassigned = await swarm.reassign_task(task, body["new_agent_id"])
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
        merged = await swarm.merge_results(tasks, strategy)
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
        resolved = await swarm.resolve_merge_conflicts(merged)
        return resolved.to_dict()

    # ── Validation ──

    @app.post("/api/swarm/validate/output")
    async def validate_task_output(body: dict) -> dict:
        """Validate a task's output against an optional schema."""
        task = _parse_task(body["task"])
        schema = body.get("schema")
        result = await swarm.validate_output(task, schema)
        return result.to_dict()

    @app.post("/api/swarm/validate/plan")
    async def validate_plan_structure(body: dict) -> dict:
        """Validate a plan's structure and dependencies."""
        plan = _parse_plan(body)
        result = await swarm.validate_plan(plan)
        return result.to_dict()

    @app.post("/api/swarm/validate/security")
    async def validate_task_security(body: dict) -> dict:
        """Validate security constraints for a task-agent assignment."""
        task = _parse_task(body["task"])
        agent = _parse_agent(body["agent"])
        result = await swarm.validate_security(task, agent)
        return result.to_dict()

    @app.post("/api/swarm/validate/policy")
    async def validate_task_policy(body: dict) -> dict:
        """Validate a task against execution policies."""
        task = _parse_task(body["task"])
        policies = body.get("policies", {})
        result = await swarm.validate_policy(task, policies)
        return result.to_dict()

    # ── Checkpoint ──

    @app.post("/api/swarm/checkpoints")
    async def save_execution_checkpoint(body: dict) -> dict:
        """Save a checkpoint of the current execution state."""
        plan = _parse_plan(body["plan"])
        stage_data = body.get("stage")
        stage = _parse_stage(stage_data) if stage_data else None
        checkpoint = await swarm.save_checkpoint(plan, stage, body.get("metadata"))
        return checkpoint.to_dict()

    @app.get("/api/swarm/checkpoints/{checkpoint_id}")
    async def restore_execution_checkpoint(checkpoint_id: str) -> dict:
        """Restore execution state from a checkpoint."""
        plan = await swarm.restore_checkpoint(checkpoint_id)
        if plan is None:
            raise HTTPException(status_code=404, detail="Checkpoint not found")
        return plan.to_dict()

    @app.get("/api/swarm/checkpoints")
    async def list_plan_checkpoints(plan_id: str) -> list[dict]:
        """List all checkpoints for a plan."""
        checkpoints = await swarm.list_checkpoints(plan_id)
        return [c.to_dict() for c in checkpoints]

    @app.delete("/api/swarm/checkpoints/{checkpoint_id}")
    async def delete_execution_checkpoint(checkpoint_id: str) -> dict:
        """Delete a checkpoint."""
        ok = await swarm.delete_checkpoint(checkpoint_id)
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
        agent = await swarm.select_agent(task, agents)
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
        agents = await swarm.match_capabilities(goal, body.get("capabilities", []))
        return [a.to_dict() for a in agents]

    # ── Metrics & Cost ──

    @app.post("/api/swarm/metrics/collect")
    async def collect_execution_metrics(body: dict) -> dict:
        """Collect execution metrics for a plan."""
        plan = _parse_plan(body)
        metrics = await swarm.collect_metrics(plan)
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
        await swarm.record_timeline(entry)
        return {"recorded": True}

    @app.get("/api/swarm/metrics/timeline/{plan_id}")
    async def get_execution_timeline(plan_id: str, limit: int = 100) -> list[dict]:
        """Get the execution timeline for a plan."""
        entries = await swarm.get_timeline(plan_id, limit)
        return [e.to_dict() for e in entries]

    @app.post("/api/swarm/cost/estimate")
    async def estimate_plan_cost(body: dict) -> dict:
        """Estimate the cost of executing a plan."""
        plan = _parse_plan(body)
        cost = await swarm.estimate_cost(plan)
        return cost.to_dict()

    @app.post("/api/swarm/cost/track")
    async def track_execution_cost(body: dict) -> dict:
        """Track actual cost incurred."""
        cost = await swarm.track_cost(
            plan_id=body["plan_id"],
            agent_id=body["agent_id"],
            cost=body["cost"],
            stage_id=body.get("stage_id"),
        )
        return cost.to_dict()

    @app.get("/api/swarm/cost/{plan_id}")
    async def get_plan_costs(plan_id: str) -> dict:
        """Get accumulated costs for a plan."""
        costs = await swarm.get_costs(plan_id)
        if costs is None:
            return {"plan_id": plan_id, "total_cost": 0.0, "cost_by_agent": {}}
        return costs.to_dict()

    @app.get("/api/swarm/performance/{plan_id}")
    async def analyze_plan_performance(plan_id: str) -> dict:
        """Generate a performance analysis report for a plan."""
        return await swarm.analyze_performance(plan_id)

    # ── Recovery ──

    @app.post("/api/swarm/recovery/task")
    async def recover_failed_task(body: dict) -> dict:
        """Recover a failed task on a suitable agent."""
        task = _parse_task(body["task"])
        agents = [_parse_agent(a) for a in body.get("available_agents", [])]
        recovered = await swarm.recover_task(task, agents)
        return recovered.to_dict()

    @app.post("/api/swarm/recovery/plan")
    async def recover_execution_plan(body: dict) -> dict:
        """Recover a plan from checkpoint or from scratch."""
        plan = _parse_plan(body["plan"])
        checkpoint_data = body.get("checkpoint")
        checkpoint = _parse_checkpoint(checkpoint_data) if checkpoint_data else None
        recovered = await swarm.recover_plan(plan, checkpoint)
        return recovered.to_dict()

    @app.post("/api/swarm/recovery/rollback")
    async def rollback_execution_plan(body: dict) -> dict:
        """Rollback a plan to a specific checkpoint."""
        plan = _parse_plan(body["plan"])
        checkpoint = _parse_checkpoint(body["checkpoint"])
        rolled_back = await swarm.rollback_plan(plan, checkpoint)
        return rolled_back.to_dict()

    # ── Retry ──

    @app.post("/api/swarm/retry/should")
    async def should_retry_task(body: dict) -> dict:
        """Check if a task should be retried."""
        task = _parse_task(body["task"])
        policy_data = body.get("policy")
        policy = _parse_retry_policy(policy_data) if policy_data else None
        should = await swarm.should_retry(task, policy)
        return {"task_id": task.id, "should_retry": should}

    @app.post("/api/swarm/retry/reset")
    async def reset_task_retry(body: dict) -> dict:
        """Reset retry count for a task."""
        await swarm.reset_retry_count(body["task_id"])
        return {"reset": body["task_id"]}

    # ── Goals & Tasks (extended M3) ──

    @app.get("/api/swarm/goals")
    async def list_orchestration_goals(status: str | None = None) -> list[dict]:
        """List orchestration goals."""
        goals = await swarm.list_goals(status)
        return [g.to_dict() for g in goals]

    @app.get("/api/swarm/goals/{goal_id}")
    async def get_orchestration_goal(goal_id: str) -> dict:
        """Get an orchestration goal."""
        goal = await swarm.get_goal(goal_id)
        if goal is None:
            raise HTTPException(status_code=404, detail="Goal not found")
        return goal.to_dict()

    @app.post("/api/swarm/goals")
    async def create_orchestration_goal(body: dict) -> dict:
        """Create an orchestration goal."""
        goal = await swarm.create_goal(
            title=body["title"],
            description=body.get("description", ""),
            context=body.get("context"),
            swarm_id=body.get("swarm_id"),
        )
        return goal.to_dict()

    @app.delete("/api/swarm/goals/{goal_id}")
    async def cancel_orchestration_goal(goal_id: str) -> dict:
        """Cancel a goal."""
        goal = await swarm.cancel_goal(goal_id)
        if goal is None:
            raise HTTPException(status_code=404, detail="Goal not found")
        return goal.to_dict()

    @app.get("/api/swarm/plans/{plan_id}")
    async def get_orchestration_plan(plan_id: str) -> dict:
        """Get an orchestration plan."""
        plan = await swarm.get_plan(plan_id)
        if plan is None:
            raise HTTPException(status_code=404, detail="Plan not found")
        return plan.to_dict()

    @app.get("/api/swarm/tasks")
    async def list_orchestration_tasks(
        goal_id: str | None = None,
        status: str | None = None,
    ) -> list[dict]:
        """List orchestration tasks."""
        tasks = await swarm.list_tasks(goal_id, status)
        return [t.to_dict() for t in tasks]

    @app.get("/api/swarm/tasks/{task_id}")
    async def get_orchestration_task(task_id: str) -> dict:
        """Get a task by ID."""
        task = await swarm.get_task(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        return task.to_dict()

    # ─────────────────────────────────────────────────────────────────────────
    # Learning & Optimization Engine API (Phase 5 / v0.9.0)
    # ─────────────────────────────────────────────────────────────────────────

    # -- Executions --

    @app.get("/api/learning/executions")
    async def list_learning_executions(
        target_id: str | None = None,
        target_type: str | None = None,
        outcome: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """List execution records with optional filters."""
        results = await learning.list_executions(target_id, target_type, outcome, limit, offset)
        return [r.to_dict() for r in results]

    @app.get("/api/learning/executions/{execution_id}")
    async def get_learning_execution(execution_id: str) -> dict:
        """Get an execution record by ID."""
        result = await learning.get_execution(execution_id)
        if result is None:
            raise HTTPException(status_code=404, detail="Execution not found")
        return result.to_dict()

    @app.post("/api/learning/executions")
    async def record_learning_execution(body: dict) -> dict:
        """Record an execution in the learning history."""
        from agentic_os.domain.learning import ExecutionHistory, ExecutionOutcome

        outcome_str = body.get("outcome", "success")
        try:
            outcome = ExecutionOutcome(outcome_str)
        except ValueError:
            outcome = ExecutionOutcome.SUCCESS

        execution = ExecutionHistory(
            id=body.get("id", f"exec-{int(time.time())}"),
            target_id=body["target_id"],
            target_type=body.get("target_type", "engine"),
            outcome=outcome,
            duration_ms=body.get("duration_ms", 0.0),
            cpu_percent=body.get("cpu_percent", 0.0),
            memory_mb=body.get("memory_mb", 0.0),
            token_count=body.get("token_count", 0),
            cost=body.get("cost", 0.0),
            error=body.get("error"),
            metadata=body.get("metadata", {}),
        )
        recorded = await learning.record_execution(execution)
        return recorded.to_dict()

    @app.get("/api/learning/executions/profile/{target_id}")
    async def get_execution_profile(
        target_id: str,
        target_type: str = "engine",
        window_hours: int = 24,
    ) -> dict:
        """Get an execution profile for a target."""
        profile = await learning.get_execution_profile(target_id, target_type, window_hours)
        return profile.to_dict()

    # -- Failure Patterns --

    @app.get("/api/learning/patterns/failure")
    async def list_failure_patterns(
        target_type: str | None = None,
        pattern_type: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """List failure patterns."""
        patterns = await learning.list_failure_patterns(target_type, pattern_type, limit)
        return [p.to_dict() for p in patterns]

    @app.get("/api/learning/patterns/failure/{pattern_id}")
    async def get_failure_pattern(pattern_id: str) -> dict:
        """Get a failure pattern by ID."""
        pattern = await learning.get_failure_pattern(pattern_id)
        if pattern is None:
            raise HTTPException(status_code=404, detail="Failure pattern not found")
        return pattern.to_dict()

    # -- Recovery Patterns --

    @app.get("/api/learning/patterns/recovery")
    async def list_recovery_patterns(
        strategy: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """List recovery patterns."""
        patterns = await learning.list_recovery_patterns(strategy, limit)
        return [p.to_dict() for p in patterns]

    @app.get("/api/learning/patterns/recovery/{pattern_id}")
    async def get_recovery_pattern(pattern_id: str) -> dict:
        """Get a recovery pattern by ID."""
        pattern = await learning.get_recovery_pattern(pattern_id)
        if pattern is None:
            raise HTTPException(status_code=404, detail="Recovery pattern not found")
        return pattern.to_dict()

    # -- Knowledge --

    @app.get("/api/learning/knowledge")
    async def list_knowledge_patterns(
        pattern_type: str | None = None,
        min_confidence: float = 0.0,
        limit: int = 50,
    ) -> list[dict]:
        """List knowledge patterns."""
        patterns = await learning.list_knowledge_patterns(pattern_type, min_confidence, limit)
        return [p.to_dict() for p in patterns]

    @app.get("/api/learning/knowledge/{pattern_id}")
    async def get_knowledge_pattern(pattern_id: str) -> dict:
        """Get a knowledge pattern by ID."""
        pattern = await learning.get_knowledge_pattern(pattern_id)
        if pattern is None:
            raise HTTPException(status_code=404, detail="Knowledge pattern not found")
        return pattern.to_dict()

    # -- Predictions --

    @app.post("/api/learning/predict/execution")
    async def predict_execution(body: dict) -> dict:
        """Predict execution characteristics."""
        pred = await learning.predict_execution(
            body["target_id"],
            body.get("target_type", "engine"),
            body.get("features"),
        )
        return pred.to_dict()

    @app.post("/api/learning/predict/duration")
    async def predict_duration(body: dict) -> dict:
        """Predict execution duration."""
        pred = await learning.predict_duration(
            body["target_id"],
            body.get("target_type", "engine"),
            body.get("features"),
        )
        return pred.to_dict()

    @app.post("/api/learning/predict/cost")
    async def predict_cost(body: dict) -> dict:
        """Predict execution cost."""
        pred = await learning.predict_cost(
            body["target_id"],
            body.get("target_type", "engine"),
            body.get("features"),
        )
        return pred.to_dict()

    @app.post("/api/learning/predict/success")
    async def predict_success_probability(body: dict) -> dict:
        """Predict success probability."""
        pred = await learning.predict_success_probability(
            body["target_id"],
            body.get("target_type", "engine"),
            body.get("features"),
        )
        return pred.to_dict()

    @app.get("/api/learning/predictions")
    async def list_predictions(
        target_id: str | None = None,
        prediction_type: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """List predictions."""
        preds = await learning.list_predictions(target_id, prediction_type, limit)
        return [p.to_dict() for p in preds]

    @app.get("/api/learning/predictions/{prediction_id}")
    async def get_prediction(prediction_id: str) -> dict:
        """Get a prediction by ID."""
        pred = await learning.get_prediction(prediction_id)
        if pred is None:
            raise HTTPException(status_code=404, detail="Prediction not found")
        return pred.to_dict()

    # -- Recommendations --

    @app.get("/api/learning/recommendations")
    async def list_recommendations(
        target_id: str | None = None,
        recommendation_type: str | None = None,
        priority: str | None = None,
        applied: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """List recommendations with optional filters."""
        recs = await learning.list_recommendations(
            target_id=target_id,
            recommendation_type=recommendation_type,
            priority=priority,
            applied=applied,
            limit=limit,
            offset=offset,
        )
        return [r.to_dict() for r in recs]

    @app.get("/api/learning/recommendations/{recommendation_id}")
    async def get_recommendation(recommendation_id: str) -> dict:
        """Get a recommendation by ID."""
        rec = await learning.get_recommendation(recommendation_id)
        if rec is None:
            raise HTTPException(status_code=404, detail="Recommendation not found")
        return rec.to_dict()

    @app.post("/api/learning/recommendations/{recommendation_id}/apply")
    async def apply_recommendation(recommendation_id: str) -> dict:
        """Apply a recommendation."""
        rec = await learning.apply_recommendation(recommendation_id)
        return rec.to_dict()

    @app.post("/api/learning/recommendations/{recommendation_id}/dismiss")
    async def dismiss_recommendation(recommendation_id: str) -> dict:
        """Dismiss a recommendation."""
        rec = await learning.dismiss_recommendation(recommendation_id)
        return rec.to_dict()

    @app.post("/api/learning/recommendations/generate")
    async def generate_recommendations(body: dict) -> list[dict]:
        """Generate recommendations for a target."""
        recs = await learning.generate_recommendations(
            body["target_id"],
            body.get("target_type", "engine"),
            body.get("limit", 10),
        )
        return [r.to_dict() for r in recs]

    # -- Routing --

    @app.post("/api/learning/routing/optimize")
    async def optimize_routing(body: dict) -> dict:
        """Optimize routing for a task."""

        decision = await learning.optimize_routing(
            task_id=body["task_id"],
            required_capabilities=body.get("required_capabilities", []),
            available_engines=body.get("available_engines", []),
        )
        return decision.to_dict()

    @app.get("/api/learning/routing/history")
    async def get_routing_history(
        task_id: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Get routing decision history."""
        decisions = await learning.get_routing_history(task_id, limit)
        return [d.to_dict() for d in decisions]

    # -- Benchmarks --

    @app.post("/api/learning/benchmarks")
    async def run_benchmark(body: dict) -> dict:
        """Run a benchmark against a target."""
        record = await learning.run_benchmark(
            target_id=body["target_id"],
            target_type=body.get("target_type", "engine"),
            benchmark_name=body["benchmark_name"],
        )
        return record.to_dict()

    @app.get("/api/learning/benchmarks")
    async def list_benchmarks(
        target_id: str | None = None,
        benchmark_name: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """List benchmark records."""
        records = await learning.list_benchmarks(target_id, benchmark_name, limit, offset)
        return [r.to_dict() for r in records]

    @app.get("/api/learning/benchmarks/{benchmark_id}")
    async def get_benchmark(benchmark_id: str) -> dict:
        """Get a benchmark record by ID."""
        record = await learning.get_benchmark(benchmark_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Benchmark not found")
        return record.to_dict()

    @app.post("/api/learning/benchmarks/compare")
    async def compare_engines(body: dict) -> dict:
        """Compare multiple engines on a benchmark."""
        result = await learning.compare_engines(
            engine_ids=body["engine_ids"],
            benchmark_name=body["benchmark_name"],
        )
        return {k: v.to_dict() for k, v in result.items()}

    @app.get("/api/learning/benchmarks/top/{benchmark_name}")
    async def get_top_scores(benchmark_name: str, limit: int = 10) -> list[dict]:
        """Get top scores for a benchmark."""
        records = await learning.get_top_scores(benchmark_name, limit)
        return [r.to_dict() for r in records]

    # -- Performance / Analytics --

    @app.get("/api/learning/performance/engines")
    async def list_engine_performance(
        engine_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """List engine performance records."""
        results = await learning.list_engine_performance(engine_type, limit, offset)
        return [r.to_dict() for r in results]

    @app.get("/api/learning/performance/engines/{engine_id}")
    async def get_engine_performance(engine_id: str) -> dict:
        """Get performance for a specific engine."""
        perf = await learning.get_engine_performance(engine_id)
        if perf is None:
            raise HTTPException(status_code=404, detail="Engine performance not found")
        return perf.to_dict()

    @app.get("/api/learning/performance/workflows")
    async def list_workflow_performance(
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """List workflow performance records."""
        results = await learning.list_workflow_performance(limit, offset)
        return [r.to_dict() for r in results]

    @app.get("/api/learning/performance/workflows/{workflow_type}")
    async def get_workflow_performance(workflow_type: str) -> dict:
        """Get performance for a specific workflow type."""
        perf = await learning.get_workflow_performance(workflow_type)
        if perf is None:
            raise HTTPException(status_code=404, detail="Workflow performance not found")
        return perf.to_dict()

    @app.get("/api/learning/performance/swarms")
    async def list_swarm_performance(
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """List swarm performance records."""
        results = await learning.list_swarm_performance(limit, offset)
        return [r.to_dict() for r in results]

    @app.get("/api/learning/performance/swarms/{swarm_id}")
    async def get_swarm_performance(swarm_id: str) -> dict:
        """Get performance for a specific swarm."""
        perf = await learning.get_swarm_performance(swarm_id)
        if perf is None:
            raise HTTPException(status_code=404, detail="Swarm performance not found")
        return perf.to_dict()

    @app.get("/api/learning/performance/trends/{target_id}")
    async def get_performance_trends(
        target_id: str,
        window_hours: int = 24,
    ) -> list[dict]:
        """Get performance trends for a target."""
        trends = await learning.list_performance_trends(target_id, window_hours)
        return [t.to_dict() for t in trends]

    @app.get("/api/learning/performance/capabilities/{engine_id}")
    async def get_capability_scores(engine_id: str) -> list[dict]:
        """Get capability scores for an engine."""
        scores = await learning.get_capability_scores(engine_id)
        return [s.to_dict() for s in scores]

    @app.get("/api/learning/performance/top-engines")
    async def get_top_engines(
        capability: str,
        min_confidence: float = 0.0,
        limit: int = 10,
    ) -> list[dict]:
        """Get top-performing engines for a capability."""
        engines = await learning.get_top_engines(capability, min_confidence, limit)
        return [e.to_dict() for e in engines]

    # -- Policies --

    @app.get("/api/learning/policies")
    async def list_optimization_policies(limit: int = 50) -> list[dict]:
        """List all optimization policies."""
        policies = await learning.list_optimization_policies(limit)
        return [p.to_dict() for p in policies]

    @app.post("/api/learning/policies")
    async def create_optimization_policy(body: dict) -> dict:
        """Create a new optimization policy."""
        from agentic_os.domain.learning import OptimizationGoal, OptimizationPolicy

        goal_str = body.get("goal", "balanced")
        try:
            goal = OptimizationGoal(goal_str)
        except ValueError:
            goal = OptimizationGoal.BALANCED

        policy = OptimizationPolicy(
            id=body.get("id", f"policy-{int(time.time())}"),
            name=body["name"],
            goal=goal,
            enabled=body.get("enabled", True),
            max_execution_cost=body.get("max_execution_cost", 0.0),
            max_execution_latency_ms=body.get("max_execution_latency_ms", 0.0),
            min_reliability=body.get("min_reliability", 0.0),
            prefer_low_cost=body.get("prefer_low_cost", False),
            prefer_low_latency=body.get("prefer_low_latency", False),
            auto_apply_recommendations=body.get("auto_apply_recommendations", False),
            learning_rate=body.get("learning_rate", 0.1),
            exploration_rate=body.get("exploration_rate", 0.1),
            metadata=body.get("metadata", {}),
        )
        created = await learning.create_optimization_policy(policy)
        return created.to_dict()

    @app.get("/api/learning/policies/{policy_id}")
    async def get_optimization_policy(policy_id: str) -> dict:
        """Get an optimization policy by ID."""
        policy = await learning.get_optimization_policy(policy_id)
        if policy is None:
            raise HTTPException(status_code=404, detail="Policy not found")
        return policy.to_dict()

    @app.put("/api/learning/policies/{policy_id}")
    async def update_optimization_policy(policy_id: str, body: dict) -> dict:
        """Update an optimization policy."""
        from agentic_os.domain.learning import OptimizationGoal, OptimizationPolicy

        existing = await learning.get_optimization_policy(policy_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Policy not found")

        goal_str = body.get("goal", existing.goal.value)
        try:
            goal = OptimizationGoal(goal_str)
        except ValueError:
            goal = existing.goal

        updated = OptimizationPolicy(
            id=policy_id,
            name=body.get("name", existing.name),
            goal=goal,
            enabled=body.get("enabled", existing.enabled),
            max_execution_cost=body.get("max_execution_cost", existing.max_execution_cost),
            max_execution_latency_ms=body.get(
                "max_execution_latency_ms", existing.max_execution_latency_ms
            ),
            min_reliability=body.get("min_reliability", existing.min_reliability),
            prefer_low_cost=body.get("prefer_low_cost", existing.prefer_low_cost),
            prefer_low_latency=body.get("prefer_low_latency", existing.prefer_low_latency),
            auto_apply_recommendations=body.get(
                "auto_apply_recommendations", existing.auto_apply_recommendations
            ),
            learning_rate=body.get("learning_rate", existing.learning_rate),
            exploration_rate=body.get("exploration_rate", existing.exploration_rate),
            metadata=body.get("metadata", existing.metadata),
        )
        result = await learning.update_optimization_policy(policy_id, updated)
        return result.to_dict()

    @app.delete("/api/learning/policies/{policy_id}")
    async def delete_optimization_policy(policy_id: str) -> dict:
        """Delete an optimization policy."""
        deleted = await learning.delete_optimization_policy(policy_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Policy not found")
        return {"deleted": policy_id}

    # -- Statistics / Snapshots --

    @app.get("/api/learning/statistics")
    async def get_learning_statistics() -> dict:
        """Get aggregate learning statistics."""
        stats = await learning.compute_statistics()
        return stats.to_dict()

    @app.post("/api/learning/snapshots")
    async def take_learning_snapshot() -> dict:
        """Take a point-in-time snapshot of learning state."""
        snapshot = await learning.take_snapshot()
        return snapshot.to_dict()

    # -- Analyze Performance --

    @app.post("/api/learning/analyze")
    async def analyze_performance(body: dict) -> list[dict]:
        """Analyze performance and generate optimization recommendations."""
        recs = await learning.analyze_performance(
            body["target_id"],
            body.get("target_type", "engine"),
        )
        return [r.to_dict() for r in recs]

    # ── Minimal provider management UI page (Phase 3 builds Mission Control) ──
    @app.get("/providers", response_class=HTMLResponse)
    async def providers_page() -> str:
        return _PROVIDER_PAGE

    @app.websocket("/ws/dashboard")
    async def dashboard_ws(websocket: WebSocket) -> None:
        await websocket.accept()
        recv, send = platform.dashboard.add_client()
        log.info("dashboard.connected")
        try:
            async with recv:
                async for snapshot in recv:
                    await websocket.send_json(snapshot)
        except WebSocketDisconnect:
            pass
        finally:
            platform.dashboard.remove_client(send)
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
