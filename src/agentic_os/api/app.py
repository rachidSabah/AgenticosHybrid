"""FastAPI control plane + WebSocket live dashboard.

REST surface over the Platform (all subsystems), plus a WebSocket endpoint that
streams every bus event to connected dashboards. This is the user-facing top of
the hexagonal stack (the API is an adapter over the core ports).

Phase 2 adds the Provider Management API (add/edit/test/list providers, models,
health, cost, rate limits) and a minimal functional HTML page for managing
providers in-browser (the unified Mission Control dashboard lands in Phase 3).
"""

from __future__ import annotations

import time

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, Response

from agentic_os.config import settings
from agentic_os.domain.agent import Task
from agentic_os.domain.provider_mgmt import ProviderConfig, ProviderHealthStatus
from agentic_os.infrastructure.logging import get_logger
from agentic_os.infrastructure.metrics import metrics_payload, observe
from agentic_os.kernel import Platform

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
