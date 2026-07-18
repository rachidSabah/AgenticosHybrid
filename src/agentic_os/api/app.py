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
from fastapi.responses import HTMLResponse, Response

from agentic_os.config import settings
from agentic_os.domain.agent import Task
from agentic_os.domain.execution import EngineCapability, EngineType
from agentic_os.domain.mcp import MCPServerStatus
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


def create_app(platform: Platform) -> FastAPI:
    app = FastAPI(title="Agentic OS", version="0.2.0")

    orch = platform.orchestrator
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

    def _require_mcp() -> None:
        """Raise 503 if MCP runtime is not available."""
        if mcp is None:
            raise HTTPException(status_code=503, detail="MCP runtime not available")

    # Server CRUD
    @app.get("/api/mcp/servers")
    async def list_mcp_servers(
        status: str | None = None,
        enabled_only: bool = False,
    ) -> list[dict]:
        _require_mcp()
        status_enum = MCPServerStatus(status) if status else None
        servers = await mcp.list_servers(status=status_enum, enabled_only=enabled_only)
        return [s.to_dict() for s in servers]

    @app.get("/api/mcp/servers/{server_id}")
    async def get_mcp_server(server_id: str) -> dict:
        _require_mcp()
        detail = await mcp.get_server_detail(server_id)
        if not detail:
            raise HTTPException(status_code=404, detail="MCP server not found")
        return detail.to_dict()

    @app.post("/api/mcp/servers")
    async def register_mcp_server(body: dict) -> dict:
        _require_mcp()
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
        _require_mcp()
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
            raise HTTPException(status_code=404, detail="MCP server not found")

    @app.delete("/api/mcp/servers/{server_id}")
    async def delete_mcp_server(server_id: str) -> dict:
        _require_mcp()
        ok = await mcp.registry.delete_server(server_id)
        if not ok:
            raise HTTPException(status_code=404, detail="MCP server not found")
        return {"deleted": server_id}

    # Server Lifecycle
    @app.post("/api/mcp/servers/{server_id}/start")
    async def start_mcp_server(server_id: str) -> dict:
        _require_mcp()
        try:
            detail = await mcp.registry.start_server(server_id)
            return detail.to_dict()
        except KeyError:
            raise HTTPException(status_code=404, detail="MCP server not found")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/api/mcp/servers/{server_id}/stop")
    async def stop_mcp_server(server_id: str) -> dict:
        _require_mcp()
        try:
            detail = await mcp.registry.stop_server(server_id)
            return detail.to_dict()
        except KeyError:
            raise HTTPException(status_code=404, detail="MCP server not found")

    @app.post("/api/mcp/servers/{server_id}/restart")
    async def restart_mcp_server(server_id: str) -> dict:
        _require_mcp()
        try:
            detail = await mcp.restart_server(server_id)
            return detail.to_dict()
        except KeyError:
            raise HTTPException(status_code=404, detail="MCP server not found")

    @app.post("/api/mcp/servers/{server_id}/reload")
    async def reload_mcp_server(server_id: str) -> dict:
        _require_mcp()
        try:
            detail = await mcp.reload_server(server_id)
            return detail.to_dict()
        except KeyError:
            raise HTTPException(status_code=404, detail="MCP server not found")

    # Tool Operations
    @app.get("/api/mcp/servers/{server_id}/tools")
    async def list_mcp_server_tools(server_id: str) -> list[dict]:
        _require_mcp()
        tools = mcp.get_server_tools(server_id)
        return [t.to_dict() for t in tools]

    @app.post("/api/mcp/servers/{server_id}/tools/discover")
    async def discover_mcp_server_tools(server_id: str) -> list[dict]:
        _require_mcp()
        try:
            tools = await mcp.registry.discover_tools(server_id)
            return [t.to_dict() for t in tools]
        except KeyError:
            raise HTTPException(status_code=404, detail="MCP server not found")
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/api/mcp/servers/{server_id}/tools/call")
    async def call_mcp_tool(server_id: str, body: dict) -> dict:
        _require_mcp()
        tool = body.get("tool")
        if not tool:
            raise HTTPException(status_code=400, detail="tool name required")
        arguments = body.get("arguments", {})
        try:
            result = await mcp.invoke_tool(server_id, tool, arguments)
            return result.to_dict()
        except KeyError:
            raise HTTPException(status_code=404, detail="MCP server not found")
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    # Resource Operations
    @app.get("/api/mcp/servers/{server_id}/resources")
    async def list_mcp_server_resources(server_id: str) -> list[dict]:
        _require_mcp()
        try:
            resources = await mcp.list_server_resources(server_id)
            return [r.to_dict() for r in resources]
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.get("/api/mcp/servers/{server_id}/resources/read")
    async def read_mcp_server_resource(server_id: str, uri: str) -> dict:
        _require_mcp()
        try:
            result = await mcp.read_server_resource(server_id, uri)
            return result
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/api/mcp/servers/{server_id}/resources/subscribe")
    async def subscribe_mcp_resource(server_id: str, body: dict) -> dict:
        _require_mcp()
        uri = body.get("uri")
        if not uri:
            raise HTTPException(status_code=400, detail="uri required")
        try:
            ok = await mcp.subscribe_server_resource(server_id, uri)
            return {"subscribed": ok, "uri": uri}
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.delete("/api/mcp/servers/{server_id}/resources/subscribe")
    async def unsubscribe_mcp_resource(server_id: str, uri: str) -> dict:
        _require_mcp()
        try:
            ok = await mcp.unsubscribe_server_resource(server_id, uri)
            return {"unsubscribed": ok, "uri": uri}
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    # Prompt Operations
    @app.get("/api/mcp/servers/{server_id}/prompts")
    async def list_mcp_server_prompts(server_id: str) -> list[dict]:
        _require_mcp()
        try:
            prompts = await mcp.list_server_prompts(server_id)
            return [p.to_dict() for p in prompts]
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.get("/api/mcp/servers/{server_id}/prompts/get")
    async def get_mcp_server_prompt(
        server_id: str, name: str, arguments: str | None = None
    ) -> dict:
        _require_mcp()
        import json

        args = json.loads(arguments) if arguments else None
        try:
            result = await mcp.get_server_prompt(server_id, name, args)
            return result
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    # Health & Monitoring
    @app.get("/api/mcp/servers/{server_id}/health")
    async def check_mcp_server_health(server_id: str) -> dict:
        _require_mcp()
        try:
            health = await mcp.registry.check_health(server_id)
            return {"server_id": server_id, "health": health.value}
        except KeyError:
            raise HTTPException(status_code=404, detail="MCP server not found")

    @app.get("/api/mcp/health")
    async def mcp_health_summary() -> dict:
        """Summary of all MCP servers' health status."""
        _require_mcp()
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
        _require_mcp()
        sessions = mcp.get_active_session_ids()
        return {"sessions": sessions, "total": len(sessions)}

    # Permissions
    @app.post("/api/mcp/servers/{server_id}/permissions")
    async def set_mcp_permissions(server_id: str, body: dict) -> dict:
        _require_mcp()
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
            raise HTTPException(status_code=404, detail="MCP server not found")

    @app.get("/api/mcp/servers/{server_id}/permissions")
    async def get_mcp_permissions(server_id: str) -> list[dict]:
        _require_mcp()
        mappings = await mcp.registry.get_permissions(server_id)
        return [m.to_dict() for m in mappings]

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
