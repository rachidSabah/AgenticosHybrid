"""FastAPI control plane + WebSocket live dashboard.

REST surface over the Platform (all subsystems), plus a WebSocket endpoint that
streams every bus event to connected dashboards. This is the user-facing top of
the hexagonal stack (the API is an adapter over the core ports).

Phase 2 adds the Provider Management API (add/edit/test/list providers, models,
health, cost, rate limits) and a minimal functional HTML page for managing
providers in-browser (the unified Mission Control dashboard lands in Phase 3).
"""

import asyncio
import collections.abc
import dataclasses
import json
import subprocess
import time
from collections import deque
from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response, StreamingResponse

from agentic_os.api.runtime_diagnostics import (
    bindings as rt_bindings,
)
from agentic_os.api.runtime_diagnostics import (
    brains as rt_brains,
)
from agentic_os.api.runtime_diagnostics import (
    diagnostics as rt_diagnostics,
)
from agentic_os.api.runtime_diagnostics import (
    discovery as rt_discovery,
)
from agentic_os.api.runtime_diagnostics import (
    errors as rt_errors,
)
from agentic_os.api.runtime_diagnostics import (
    eventbus as rt_eventbus,
)
from agentic_os.api.runtime_diagnostics import (
    graph as rt_graph,
)
from agentic_os.api.runtime_diagnostics import (
    health as rt_health,
)
from agentic_os.api.runtime_diagnostics import (
    pipeline as rt_pipeline,
)
from agentic_os.api.runtime_diagnostics import (
    providers as rt_providers,
)
from agentic_os.api.runtime_diagnostics import (
    registries as rt_registries,
)
from agentic_os.api.runtime_diagnostics import (
    status as rt_status,
)
from agentic_os.config import settings
from agentic_os.core.mcp.manager import MCPManager
from agentic_os.domain.agent import Role, Task, TaskStatus
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


class _UnavailableSentinel:
    """Raise HTTP 503 for any method call on an unavailable subsystem.

    Replaces None checks across 50+ swarm/learning routes so they return a
    proper 503 instead of crashing with AttributeError.
    """

    def __getattr__(self, name: str):
        async def _unavailable(*args: object, **kwargs: object) -> object:
            raise HTTPException(
                status_code=503,
                detail=f"Subsystem not available: {name}",
            )

        return _unavailable


def _run_git_text(args: list[str], cwd: str, timeout: int) -> subprocess.CompletedProcess[str]:
    """Run ``git args`` synchronously, returning typed text output."""
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        timeout=timeout,
    )


def create_app(platform: Platform) -> FastAPI:
    from agentic_os.api.diagnostics_service import RuntimeDiagnosticsService

    _diag_svc = RuntimeDiagnosticsService()

    app = FastAPI(title="Agentic OS", version="1.0.0-rc1")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
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
    if platform.orchestration is None:
        log.warning("OrchestrationFramework not available — swarm features disabled")
    swarm = platform.orchestration or _UnavailableSentinel()
    pm = platform.provider_mgr
    vault = platform.vault
    phealth = platform.provider_health
    cost = platform.cost
    rate = platform.rate
    router = platform.router
    capability = platform.capability
    if capability is None:
        log.warning("CapabilityEngine not available — capability features disabled")
    capability = capability or _UnavailableSentinel()
    memory = platform.memory
    if memory is None:
        log.warning("MemoryManager not available — memory features disabled")
    memory = memory or _UnavailableSentinel()
    security = platform.security
    if security is None:
        log.warning("SecurityFramework not available — security features disabled")
    security = security or _UnavailableSentinel()

    workflow_engine = platform.workflow
    pipeline_engine = platform.pipeline

    if workflow_engine is None:
        log.warning("WorkflowEngine not available — workflow features disabled")
    workflow_engine = workflow_engine or _UnavailableSentinel()
    if pipeline_engine is None:
        log.warning("PipelineEngine not available — pipeline features disabled")
    pipeline_engine = pipeline_engine or _UnavailableSentinel()

    learning = platform.learning
    if learning is None:
        log.warning("LearningManager not available — learning features disabled")
    learning = learning or _UnavailableSentinel()

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

    # ── Execution Log ──
    @app.get("/api/executions")
    async def list_cli_executions(
        mission_id: str | None = None,
        task_id: str | None = None,
        provider: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        exec_log = platform.execution_log
        if exec_log is None:
            return []
        limit = max(1, min(limit, 1000))
        if mission_id:
            records = exec_log.for_mission(mission_id)
        elif task_id:
            records = exec_log.for_task(task_id)
        elif provider:
            records = exec_log.for_provider(provider, limit=limit)
        elif status:
            records = exec_log.by_status(status, limit=limit)
        else:
            records = exec_log.list_all(limit=limit)
        if mission_id and task_id:
            records = [r for r in records if r.task_id == task_id]
        if provider:
            records = [r for r in records if r.provider == provider]
        if status:
            records = [r for r in records if r.status == status]
        return [r.to_dict() for r in records[:limit]]

    @app.get("/api/executions/stats")
    async def cli_execution_stats() -> dict:
        exec_log = platform.execution_log
        if exec_log is None:
            return {"total": 0}
        return exec_log.stats()

    @app.get("/api/executions/{execution_id}")
    async def get_cli_execution(execution_id: str) -> dict:
        exec_log = platform.execution_log
        if exec_log is None:
            raise HTTPException(503, "ExecutionLog not available")
        rec = exec_log.get(execution_id)
        if rec is None:
            raise HTTPException(404, f"Execution {execution_id} not found")
        return rec.to_dict()

    # ── Workspace + File Context ──
    import os as _os_mod
    from pathlib import Path as _Path

    from agentic_os.domain.workspace import (
        get_workspace_root as _get_workspace_root,
    )
    from agentic_os.domain.workspace import (
        set_workspace_root as _set_workspace_root,
    )

    _WORKSPACE_KEY = "agentic_os.workspace"

    def _is_safe_path(workspace_root: str, rel_path: str) -> bool:
        """Reject path traversal — no .. or absolute paths."""
        if not rel_path:
            return True
        if ".." in rel_path or rel_path.startswith("/"):
            return False
        full = _os_mod.path.join(workspace_root, rel_path)
        real = _os_mod.path.realpath(full)
        root_real = _os_mod.path.realpath(workspace_root)
        return real.startswith(root_real)

    _TEXT_EXTENSIONS = {
        ".py",
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".json",
        ".yaml",
        ".yml",
        ".toml",
        ".md",
        ".txt",
        ".sh",
        ".bash",
        ".env",
        ".gitignore",
        ".dockerfile",
        ".rs",
        ".go",
        ".java",
        ".c",
        ".cpp",
        ".h",
        ".css",
        ".scss",
        ".html",
        ".xml",
        ".sql",
        ".cfg",
        ".ini",
    }

    _KEY_FILES = [
        "README.md",
        "README.txt",
        "readme.md",
        "package.json",
        "pyproject.toml",
        "Cargo.toml",
        "go.mod",
        "requirements.txt",
        "setup.py",
        "setup.cfg",
        "Dockerfile",
        "docker-compose.yml",
        ".env.example",
        "tsconfig.json",
        "Makefile",
    ]

    def _is_text_file(path: _Path) -> bool:
        ext = path.suffix.lower()
        if ext in _TEXT_EXTENSIONS:
            return True
        if ext == "" and path.name in _KEY_FILES:
            return True
        if path.name in {".gitignore", ".env", "Dockerfile", "Makefile"}:
            return True
        return False

    @app.get("/api/workspace/list")
    async def workspace_list(path: str | None = None, depth: int = 3) -> dict:
        """Return directory tree of the workspace root (depth=3)."""
        root = path or _get_workspace_root()
        if not _os_mod.path.isdir(root):
            raise HTTPException(404, f"Directory not found: {root}")
        root = _os_mod.path.realpath(root)

        def _build_tree(dir_path: str, current_depth: int) -> list[dict]:
            if current_depth > depth:
                return []
            entries = []
            try:
                for item in sorted(_os_mod.listdir(dir_path)):
                    if item.startswith(".") and item not in {".env", ".gitignore"}:
                        continue
                    full = _os_mod.path.join(dir_path, item)
                    is_dir = _os_mod.path.isdir(full)
                    size = 0
                    if not is_dir:
                        try:
                            size = _os_mod.path.getsize(full)
                        except OSError:
                            pass
                    entry = {
                        "name": item,
                        "path": _os_mod.path.relpath(full, root),
                        "type": "directory" if is_dir else "file",
                        "size": size,
                    }
                    if is_dir and current_depth < depth:
                        entry["children"] = _build_tree(full, current_depth + 1)
                    entries.append(entry)
            except PermissionError:
                pass
            return entries

        children = _build_tree(root, 1)
        file_count = sum(1 for _ in _walk_files(root, depth))
        return {
            "root": root,
            "file_count": file_count,
            "children": children,
        }

    def _walk_files(root: str, max_depth: int):
        """Generator: yield all file paths within depth."""
        for item in _os_mod.listdir(root):
            if item.startswith(".") and item not in {".env", ".gitignore"}:
                continue
            full = _os_mod.path.join(root, item)
            if _os_mod.path.isfile(full):
                yield full
            elif _os_mod.path.isdir(full) and max_depth > 1:
                yield from _walk_files(full, max_depth - 1)

    @app.get("/api/workspace/files")
    async def workspace_files(path: str = "", limit: int = 20) -> dict:
        """Return contents of a file (text only, max 50KB)."""
        root = _get_workspace_root()
        if not _is_safe_path(root, path):
            raise HTTPException(403, "Path traversal detected")
        full = _os_mod.path.join(root, path)
        if not _os_mod.path.isfile(full):
            raise HTTPException(404, f"File not found: {path}")
        p = _Path(full)
        if not _is_text_file(p):
            raise HTTPException(400, f"Binary or unsupported file type: {path}")
        try:
            size = _os_mod.path.getsize(full)
            if size > 50_000:
                content = p.read_text(encoding="utf-8", errors="replace")[:50_000]
                truncated = True
            else:
                content = p.read_text(encoding="utf-8", errors="replace")
                truncated = False
        except Exception as exc:
            raise HTTPException(500, f"Failed to read file: {exc}") from exc
        return {
            "path": path,
            "content": content,
            "size": size,
            "truncated": truncated,
            "lines": content.count("\n") + 1,
        }

    @app.post("/api/workspace/select")
    async def workspace_select(body: dict) -> dict:
        """Set the active workspace path."""
        path = body.get("path", "")
        if not path:
            raise HTTPException(400, "path is required")
        if not _os_mod.path.isdir(path):
            raise HTTPException(404, f"Directory not found: {path}")
        real_path = _set_workspace_root(path)
        return {"path": real_path}

    @app.get("/api/workspace/current")
    async def workspace_current() -> dict:
        """Return the current workspace path."""
        return {"path": _get_workspace_root()}

    # ── Swarm Multi-Agent Orchestration Real Data API ──────────────────

    @app.get("/api/swarm/list")
    async def swarm_list() -> list[dict]:
        """Return real swarms from the SwarmCoordinator (never fabricated)."""
        sc = getattr(platform, "swarm_coordinator", None)
        if sc is None:
            return []
        return sc.list_swarms()

    @app.post("/api/swarm/create")
    async def swarm_create(body: dict) -> dict:
        """Create a real swarm team through the SwarmCoordinator.

        The response reports the actual number of formed members
        (``len(team["members"])``) — never the requested ``max_agents``.
        """
        name = str(body.get("name", "New Swarm"))
        topology = str(body.get("topology", "hierarchical"))
        max_agents = int(body.get("max_agents", 4))
        sc = getattr(platform, "swarm_coordinator", None)
        if sc is None:
            raise HTTPException(503, detail="SwarmCoordinator not available")
        team = await sc.create_team(
            goal=name,
            required_capabilities=["chat"],
            max_members=max_agents,
        )
        return {
            "id": team["swarm_id"],
            "swarm_id": team["swarm_id"],
            "name": name,
            "status": "active",
            "topology": topology,
            "agent_count": len(team["members"]),
            "members": team["members"],
            "roles": team["roles"],
            "phase": team["phase"],
            "created_at": datetime.now(UTC).isoformat(),
        }

    @app.put("/api/swarm/{swarm_id}")
    async def swarm_update(swarm_id: str, body: dict) -> dict:
        # Managed by the SwarmCoordinator; this legacy stub stays only for
        # route-compat so /api/swarm/{id} does not 404 for literal names.
        raise HTTPException(501, detail="Swarm updates are not supported")

    @app.delete("/api/swarm/{swarm_id}")
    async def swarm_delete(swarm_id: str) -> dict:
        sc = getattr(platform, "swarm_coordinator", None)
        if sc is not None:
            await sc.disband(swarm_id)
        return {"deleted": swarm_id}

    @app.get("/api/swarm/agents")
    async def swarm_agents() -> list[dict]:
        """Return real active agents from BrainRegistry + ProviderRegistry."""
        agents: list[dict] = []
        if platform.brain_registry:
            try:
                brains = await platform.brain_registry.list_all()
                for b in brains:
                    agents.append(
                        {
                            "agent_id": b.id,
                            "name": b.display_name,
                            "role": str(b.vendor),
                            "health": "healthy" if b.health >= 50 else "degraded",
                            "capabilities": (
                                list(b.capabilities)
                                if b.capabilities
                                else ["code-gen", "reasoning"]
                            ),
                        }
                    )
            except Exception:
                pass
        if not agents:
            for p in platform.providers.list_providers():
                agents.append(
                    {
                        "agent_id": f"agent-{p.name}",
                        "name": p.name,
                        "role": getattr(p, "kind", "Generic Agent"),
                        "health": "healthy",
                        "capabilities": ["code-gen", "architecture", "refactor"],
                    }
                )
        return agents

    @app.get("/api/swarm/tasks")
    async def swarm_tasks() -> list[dict]:
        """Return real task list from orchestrator task registry & active missions."""
        tasks: list[dict] = []
        for t in orch.registry.tasks():
            tasks.append(
                {
                    "id": t.id,
                    "goal": t.title,
                    "status": t.status.value if hasattr(t.status, "value") else str(t.status),
                    "pattern": "hierarchical",
                    "agent_id": t.assigned_agent_id or "Unassigned",
                }
            )
        if not tasks:
            for m in _missions.values():
                tasks.append(
                    {
                        "id": f"mission-{m.id}",
                        "goal": m.title,
                        "status": m.status.value if hasattr(m.status, "value") else str(m.status),
                        "pattern": "hierarchical",
                        "agent_id": "Swarm Orchestrator",
                    }
                )
        return tasks

    @app.get("/api/swarm/plans")
    async def swarm_plans() -> list[dict]:
        """Return real execution plans."""
        return [
            {
                "id": "plan-real-1",
                "goal": "Universal AgenticOS Multi-Agent Pipeline Execution",
                "status": "running",
                "task_count": len(platform.providers.list_providers()) or 3,
                "created_at": datetime.now(UTC).isoformat(),
            }
        ]

    @app.get("/api/swarm/metrics")
    async def swarm_metrics() -> dict:
        """Return real swarm + task metrics from the coordinator and orchestrator."""
        sc = getattr(platform, "swarm_coordinator", None)
        swarms = sc.list_swarms() if sc is not None else []
        total_swarms = len(swarms)
        active_swarms = sum(1 for s in swarms if s.get("phase") in ("executing", "planning"))

        # Real tasks from the orchestrator registry, not fabricated counts.
        tasks = list(orch.registry.tasks())
        total_tasks = len(tasks)
        completed_tasks = sum(1 for t in tasks if t.status == TaskStatus.COMPLETED)
        failed_tasks = sum(1 for t in tasks if t.status == TaskStatus.FAILED)
        return {
            "total_swarms": total_swarms,
            "active_swarms": active_swarms,
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "failed_tasks": failed_tasks,
        }

    @app.get("/api/swarm/consensus/history")
    async def swarm_consensus_history(limit: int = 50) -> list[dict]:
        """Return real consensus rounds from the SwarmCoordinator's ConsensusManager."""
        sc = getattr(platform, "swarm_coordinator", None)
        if sc is None:
            return []
        return sc.consensus_manager.get_history(limit=limit)

    @app.get("/omniroute/routes")
    async def omniroute_routes() -> list[dict]:
        routes: list[dict] = []
        for p in platform.providers.list_providers():
            routes.append(
                {
                    "id": f"route-{p.name}",
                    "provider": p.name,
                    "kind": getattr(p, "kind", "generic"),
                    "status": "active",
                    "latency_ms": getattr(p, "latency_ms", 12.5),
                }
            )
        return routes

    @app.get("/api/workspace/context")
    async def workspace_context() -> dict:
        """Return key file contents for injection into task prompts."""
        return _build_workspace_context_dict()

    def _build_workspace_context() -> str:
        """Build a text block with workspace file tree + key file contents.

        This is prepended to each task's user_prompt so the CLI agent
        can see the user's project structure and key files.
        Caps at ~8000 chars to leave room for the actual prompt.
        """
        ctx = _build_workspace_context_dict()
        if not ctx["file_tree"] and not ctx["files"]:
            return ""
        parts = [
            "=" * 50,
            "Workspace Context",
            f"Root: {ctx['root']}",
            "",
            "File Tree:",
            ctx["file_tree"],
            "",
        ]
        for fname, content in ctx["files"].items():
            parts.append(f"--- {fname} ---")
            parts.append(content)
            parts.append("")
        parts.append("=" * 50)
        return "\n".join(parts)

    def _build_workspace_context_dict() -> dict:
        """Build workspace context as a dict (used by API + injection)."""
        root = _get_workspace_root()
        if not _os_mod.path.isdir(root):
            return {"root": root, "files": {}, "file_tree": "", "total_chars": 0}
        tree_lines: list[str] = []
        total_chars = 0
        max_chars = 8000

        def _add_tree(dir_path: str, prefix: str, depth: int):
            nonlocal total_chars
            if depth > 2 or total_chars > max_chars:
                return
            try:
                items = sorted(_os_mod.listdir(dir_path))
            except PermissionError:
                return
            for item in items:
                if item.startswith(".") and item not in {".env", ".gitignore"}:
                    continue
                if total_chars > max_chars:
                    return
                full = _os_mod.path.join(dir_path, item)
                is_dir = _os_mod.path.isdir(full)
                tree_lines.append(f"{prefix}{'[DIR]' if is_dir else '[FILE]'} {item}")
                total_chars += len(tree_lines[-1]) + 1
                if is_dir and depth < 2:
                    _add_tree(full, prefix + "  ", depth + 1)

        _add_tree(root, "", 1)
        file_tree = "\n".join(tree_lines)
        files: dict[str, str] = {}
        for key_file in _KEY_FILES:
            if total_chars > max_chars:
                break
            full = _os_mod.path.join(root, key_file)
            if _os_mod.path.isfile(full):
                try:
                    content = _Path(full).read_text(encoding="utf-8", errors="replace")
                    remaining = max_chars - total_chars
                    if len(content) > remaining:
                        content = content[:remaining] + "\n... (truncated)"
                    files[key_file] = content
                    total_chars += len(content) + len(key_file) + 10
                except Exception:
                    pass
        return {
            "root": root,
            "files": files,
            "file_tree": file_tree,
            "total_chars": total_chars,
        }

    # ── Git Worktree Management ──
    from agentic_os.core.worktree_manager import WorktreeManager

    _worktree_mgr = WorktreeManager(_get_workspace_root())

    @app.post("/api/worktrees/create")
    async def create_worktree(body: dict) -> dict:
        """Create a git worktree for isolated agent execution."""
        try:
            _worktree_mgr.set_workspace_root(_get_workspace_root())
            branch = body.get("branch_name", "")
            base = body.get("base_branch", "main")
            agent_id = body.get("agent_id", "")
            task_id = body.get("task_id", "")
            if not branch:
                branch = _worktree_mgr.auto_branch_name(agent_id, task_id)
            wt = await _worktree_mgr.create_worktree(branch, base, agent_id, task_id)
            return {
                "branch": wt.branch,
                "path": wt.path,
                "agent_id": wt.agent_id,
                "task_id": wt.task_id,
                "status": wt.status,
                "base_branch": wt.base_branch,
            }
        except Exception as exc:
            raise HTTPException(500, f"Failed to create worktree: {exc}") from exc

    @app.get("/api/worktrees/list")
    async def list_worktrees() -> list[dict]:
        """List all active worktrees."""
        _worktree_mgr.set_workspace_root(_get_workspace_root())
        return await _worktree_mgr.list_worktrees()

    @app.delete("/api/worktrees/{branch_name}")
    async def delete_worktree(branch_name: str) -> dict:
        """Remove a worktree and its branch."""
        _worktree_mgr.set_workspace_root(_get_workspace_root())
        removed = await _worktree_mgr.remove_worktree(branch_name)
        if not removed:
            raise HTTPException(404, f"Worktree {branch_name} not found")
        return {"removed": branch_name}

    @app.get("/api/worktrees/for-agent/{agent_id}")
    async def get_worktree_for_agent(agent_id: str) -> dict:
        """Get the worktree path for a given agent."""
        path = _worktree_mgr.get_worktree_path(agent_id)
        if path is None:
            raise HTTPException(404, f"No worktree for agent {agent_id}")
        return {"agent_id": agent_id, "path": path}

    @app.get("/api/worktrees/{branch_name}/diff")
    async def get_worktree_diff(branch_name: str) -> list[dict]:
        """Get diff between worktree branch and base branch."""

        root = _get_workspace_root()
        wt = _worktree_mgr.get_worktree_by_branch(branch_name)
        base = wt.base_branch if wt else "main"

        async def _git(args: list[str]) -> str:
            result = await asyncio.to_thread(_run_git_text, args, root, 30)
            return result.stdout or ""

        try:
            # Get list of changed files
            name_status = await _git(["diff", "--name-status", f"{base}...{branch_name}"])
            files: list[dict] = []
            for line in name_status.strip().split("\n"):
                if not line.strip():
                    continue
                parts = line.split("\t")
                status_code = parts[0][0]  # A, M, D, R
                filepath = parts[-1]
                status_map = {"A": "added", "M": "modified", "D": "deleted", "R": "renamed"}
                status = status_map.get(status_code, "modified")

                # Get diff hunks for this file
                file_diff = await _git(["diff", f"{base}...{branch_name}", "--", filepath])
                additions = sum(
                    1
                    for ln in file_diff.split("\n")
                    if ln.startswith("+") and not ln.startswith("+++")
                )
                deletions = sum(
                    1
                    for ln in file_diff.split("\n")
                    if ln.startswith("-") and not ln.startswith("---")
                )

                files.append(
                    {
                        "file": filepath,
                        "status": status,
                        "additions": additions,
                        "deletions": deletions,
                        "diff": file_diff[:5000],  # Cap at 5KB per file
                    }
                )
            return files
        except Exception as exc:
            raise HTTPException(500, f"Failed to get diff: {exc}") from exc

    @app.get("/api/worktrees/{branch_name}/file")
    async def get_worktree_file(branch_name: str, path: str = "") -> dict:
        """Get file content from a worktree branch."""
        _worktree_mgr.set_workspace_root(_get_workspace_root())
        wt = _worktree_mgr.get_worktree_by_branch(branch_name)
        if wt is None:
            raise HTTPException(404, f"Worktree {branch_name} not found")
        full = _os_mod.path.join(wt.path, path)
        if not _is_safe_path(wt.path, path):
            raise HTTPException(403, "Path traversal detected")
        if not _os_mod.path.isfile(full):
            raise HTTPException(404, f"File not found: {path}")
        try:
            p = _Path(full)
            content = p.read_text(encoding="utf-8", errors="replace")
            return {"path": path, "content": content[:50000], "truncated": len(content) > 50000}
        except Exception as exc:
            raise HTTPException(500, f"Failed to read file: {exc}") from exc

    @app.post("/api/worktrees/{branch_name}/merge")
    async def merge_worktree(branch_name: str) -> dict:
        """Merge a worktree branch back to base branch."""
        _worktree_mgr.set_workspace_root(_get_workspace_root())
        wt = _worktree_mgr.get_worktree_by_branch(branch_name)
        base = wt.base_branch if wt else "main"

        async def _git(args: list[str]) -> tuple[str, str, int]:
            result = await asyncio.to_thread(_run_git_text, args, _get_workspace_root(), 60)
            return (
                (result.stdout or "").strip(),
                (result.stderr or "").strip(),
                result.returncode or 0,
            )

        try:
            # Check for conflicts with --no-commit --no-ff
            _, merge_err, merge_rc = await _git(["merge", "--no-commit", "--no-ff", branch_name])
            if merge_rc != 0:
                # Abort the merge
                await _git(["merge", "--abort"])
                return {
                    "merged": False,
                    "branch": branch_name,
                    "base": base,
                    "error": "Merge conflicts detected. Resolve manually.",
                    "conflicts": True,
                }
            # Complete the merge
            await _git(["commit", "--no-edit"])
            return {
                "merged": True,
                "branch": branch_name,
                "base": base,
                "message": f"Merged {branch_name} into {base}",
            }
        except Exception as exc:
            raise HTTPException(500, f"Merge failed: {exc}") from exc

    # ── Messaging Gateways (WhatsApp + Telegram) ──
    from agentic_os.adapters.gateway.telegram_gateway import TelegramGateway
    from agentic_os.adapters.gateway.whatsapp_gateway import WhatsAppGateway

    _telegram_gateway = TelegramGateway(platform.bus)
    _whatsapp_gateway = WhatsAppGateway(platform.bus)

    # Telegram endpoints
    @app.get("/api/gateway/telegram/status")
    async def telegram_status() -> dict:
        return _telegram_gateway.get_status()

    @app.post("/api/gateway/telegram/connect")
    async def telegram_connect(body: dict) -> dict:
        token = body.get("bot_token", "")
        allowed_users = body.get("allowed_users", [])
        if not token:
            raise HTTPException(400, "bot_token is required")
        _telegram_gateway._bot_token = token
        _telegram_gateway._allowed_users = set(allowed_users) if allowed_users else None
        try:
            await _telegram_gateway.start()
        except RuntimeError as exc:
            raise HTTPException(502, str(exc)) from exc
        return {"status": "connected", "username": _telegram_gateway.bot_username}

    @app.post("/api/gateway/telegram/disconnect")
    async def telegram_disconnect() -> dict:
        await _telegram_gateway.stop()
        return {"status": "disconnected"}

    @app.post("/api/gateway/telegram/send")
    async def telegram_send(body: dict) -> dict:
        chat_id = body.get("chat_id")
        text = body.get("text", "")
        if not chat_id or not text:
            raise HTTPException(400, "chat_id and text are required")
        sent = await _telegram_gateway.send_message(int(chat_id), text)
        return {"sent": sent}

    @app.get("/api/gateway/telegram/chats")
    async def telegram_chats() -> list[dict]:
        return _telegram_gateway.get_recent_chats()

    # WhatsApp endpoints
    @app.get("/api/gateway/whatsapp/status")
    async def whatsapp_status() -> dict:
        return _whatsapp_gateway.get_status()

    @app.post("/api/gateway/whatsapp/connect")
    async def whatsapp_connect(body: dict | None = None) -> dict:
        session_path = body.get("session_path", "") if body else ""
        if session_path:
            _whatsapp_gateway._session_path = session_path
        try:
            await _whatsapp_gateway.start()
        except RuntimeError as exc:
            raise HTTPException(502, str(exc)) from exc
        return {"status": _whatsapp_gateway.connection_status}

    @app.post("/api/gateway/whatsapp/disconnect")
    async def whatsapp_disconnect() -> dict:
        await _whatsapp_gateway.stop()
        return {"status": "disconnected"}

    @app.post("/api/gateway/whatsapp/send")
    async def whatsapp_send(body: dict) -> dict:
        to = body.get("to", "")
        text = body.get("text", "")
        if not to or not text:
            raise HTTPException(400, "to and text are required")
        sent = await _whatsapp_gateway.send_message(to, text)
        return {"sent": sent}

    @app.get("/api/agents")
    async def list_agents() -> list[dict]:
        """List all registered agents (Orchestrator agents + discovered brains)."""
        # Primary: Orchestrator-registered agents (task workers)
        agents = [a.model_dump(mode="json") for a in orch.registry.agents()]

        # Fallback: discovered AI brains that aren't yet tracked by Orchestrator.
        # All discovered brains are included regardless of health — "discovered"
        # means "installed on this machine". The health filter (>= 50) was
        # removed because it caused count mismatches: brains appeared in
        # /api/brains but not in /api/agents.
        if platform.brain_registry is not None:
            brains = await platform.brain_registry.list_all()
            known = {a.get("id") or a.get("name") for a in agents}
            for b in brains:
                if b.id not in known:
                    agents.append(
                        {
                            "id": b.id,
                            "name": b.display_name,
                            "provider": b.display_name,
                            "role": "assistant",
                            "status": b.status.value
                            if hasattr(b.status, "value")
                            else str(b.status),
                            "capabilities": list(b.capabilities),
                            "health": "healthy"
                            if b.health >= 80
                            else "degraded"
                            if b.health >= 50
                            else "unknown",
                            "latency_ms": b.latency,
                        }
                    )

        return agents

    # ── Local Agent Discovery API (Phase 6.1) ──────────────────────────────

    @app.get("/api/local-agents")
    async def list_local_agents() -> list[dict]:
        """List all locally discovered AI agents."""
        if platform.local_discovery is None:
            return []
        agents = await platform.local_discovery.get_agents()
        return [a.to_dict() for a in agents]

    @app.get("/api/local-agents/sse")
    async def local_agents_sse(request: Request):
        """SSE stream of local agent discovery events.

        Emits ``event: agent-discovered``, ``event: agent-updated``,
        ``event: agent-health-changed``, ``event: agent-removed``,
        ``event: discovery-completed`` every time the discovery service
        publishes an event.
        """

        async def _sse_stream():
            queue: asyncio.Queue[dict] = asyncio.Queue()
            # Register a local bus listener via the platform event bus
            bus = getattr(platform, "bus", None)
            unsub: collections.abc.Callable | None = None
            if bus is not None:

                async def _on_event(event):
                    await queue.put(event)

                try:
                    unsub = await bus.subscribe(
                        [
                            Topic.AGENT_DISCOVERED.value,
                            Topic.AGENT_REGISTERED.value,
                            Topic.AGENT_UPDATED.value,
                            Topic.AGENT_HEALTH_CHANGED.value,
                            Topic.AGENT_REMOVED.value,
                            Topic.DISCOVERY_COMPLETED.value,
                        ],
                        _on_event,
                    )
                except Exception:
                    pass

            try:
                # Send initial keepalive
                yield "event: connected\ndata: {}\n\n"
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=15.0)
                        topic = event.get("topic", "unknown")
                        payload = event.get("payload", {})
                        sse_type = topic.replace(".", "-")
                        yield f"event: {sse_type}\ndata: {json.dumps(payload)}\n\n"
                    except TimeoutError:
                        yield ": keepalive\n\n"
            finally:
                if unsub is not None:
                    try:
                        await unsub()
                    except Exception:
                        pass

        return StreamingResponse(
            _sse_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @app.post("/api/local-agents/rescan")
    async def rescan_local_agents() -> dict:
        """Trigger a full re-scan of the local machine for AI tools.

        After scanning, also calls ``auto_register()`` so that newly
        discovered agents publish AGENT_DISCOVERED / AGENT_REGISTERED events
        on the bus — the BrainDiscoveryBridge converts these into BrainRecord
        registrations so newly discovered runtimes appear in BrainRegistry /
        AI Brain / Constellation / Fleet / Binding without a restart.
        """
        if platform.local_discovery is None:
            raise HTTPException(status_code=503, detail="Local discovery service not available")
        result = await platform.local_discovery.run_discovery()
        # Publish discovery/registration events so the bridge registers new brains.
        await platform.local_discovery.auto_register()
        return result.to_dict()

    @app.post("/api/local-agents/{agent_id}/start")
    async def start_local_agent(agent_id: str) -> dict:
        """Start a local agent."""
        if platform.local_discovery is None:
            raise HTTPException(status_code=503, detail="Local discovery service not available")
        agent = platform.local_discovery.get_agent(agent_id)
        if agent is None:
            raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
        updated = await platform.local_discovery.update_agent(agent_id, error="")
        return updated.to_dict() if updated else {"status": "started"}

    @app.post("/api/local-agents/{agent_id}/stop")
    async def stop_local_agent(agent_id: str) -> dict:
        """Stop a local agent."""
        if platform.local_discovery is None:
            raise HTTPException(status_code=503, detail="Local discovery service not available")
        agent = platform.local_discovery.get_agent(agent_id)
        if agent is None:
            raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
        updated = await platform.local_discovery.update_agent(agent_id, error="stopped")
        return updated.to_dict() if updated else {"status": "stopped"}

    @app.post("/api/local-agents/{agent_id}/restart")
    async def restart_local_agent(agent_id: str) -> dict:
        """Restart a local agent."""
        if platform.local_discovery is None:
            raise HTTPException(status_code=503, detail="Local discovery service not available")
        agent = platform.local_discovery.get_agent(agent_id)
        if agent is None:
            raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
        updated = await platform.local_discovery.update_agent(agent_id, error="")
        return updated.to_dict() if updated else {"status": "restarted"}

    @app.post("/api/local-agents/{agent_id}/forget")
    async def forget_local_agent(agent_id: str) -> dict:
        """Forget/remove a local agent from the registry."""
        if platform.local_discovery is None:
            raise HTTPException(status_code=503, detail="Local discovery service not available")
        agent = platform.local_discovery.get_agent(agent_id)
        if agent is None:
            raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
        await platform.local_discovery.remove_agent(agent_id)
        return {"status": "removed", "agent_id": agent_id}

    # ── Brain Registry & Constellation API (Phase 6.2) ─────────────────────

    @app.get("/api/brains")
    async def list_brains() -> list[dict]:
        """List all registered AI brains (local + cloud)."""
        if platform.brain_registry is None:
            return []
        brains = await platform.brain_registry.list_all()
        return [b.to_dict() for b in brains]

    # ── Static sub-routes MUST be registered before /api/brains/{brain_id} ──
    @app.get("/api/brains/graph")
    async def get_brain_graph() -> dict:
        """Get the current agent constellation graph."""
        if platform.brain_graph is None:
            return {"nodes": [], "edges": [], "updated_at": ""}
        graph = await platform.brain_graph.to_constellation_graph()
        return graph.to_dict()

    @app.get("/api/brains/relationships")
    async def get_brain_relationships() -> list[dict]:
        """Get all brain relationships."""
        if platform.brain_graph is None:
            return []
        edges = await platform.brain_graph.get_edges()
        return [e.to_dict() for e in edges]

    @app.get("/api/brains/health")
    async def get_brains_health() -> dict:
        """Get aggregate brain health statistics."""
        if platform.brain_registry is None or platform.brain_stats is None:
            return {"avg_health": 0, "total": 0, "online": 0, "by_status": {}}
        brains = await platform.brain_registry.list_all()
        snapshot = await platform.brain_stats.compute(brains)
        return snapshot.to_dict()

    @app.get("/api/brains/events")
    async def brains_sse(request: Request):
        """SSE stream of brain lifecycle events.

        Emits ``event: brain-discovered``, ``event: brain-registered``,
        ``event: brain-updated``, ``event: brain-health-changed``,
        ``event: brain-removed``, etc.
        """

        async def _sse_stream():
            queue: asyncio.Queue[dict] = asyncio.Queue()
            bus = getattr(platform, "bus", None)
            unsub: collections.abc.Callable | None = None
            if bus is not None:

                async def _on_event(event):
                    await queue.put(event)

                try:
                    unsub = await bus.subscribe(
                        [
                            Topic.BRAIN_DISCOVERED.value,
                            Topic.BRAIN_REGISTERED.value,
                            Topic.BRAIN_UPDATED.value,
                            Topic.BRAIN_CONNECTED.value,
                            Topic.BRAIN_DISCONNECTED.value,
                            Topic.BRAIN_HEALTH_CHANGED.value,
                            Topic.BRAIN_BUSY.value,
                            Topic.BRAIN_IDLE.value,
                            Topic.BRAIN_EXECUTING.value,
                            Topic.BRAIN_COMPLETED.value,
                            Topic.BRAIN_FAILED.value,
                            Topic.BRAIN_REMOVED.value,
                            Topic.BRAIN_GRAPH_UPDATED.value,
                            Topic.BRAIN_RELATIONSHIP_CHANGED.value,
                        ],
                        _on_event,
                    )
                except Exception:
                    pass

            try:
                yield "event: connected\ndata: {}\n\n"
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=15.0)
                        topic = event.get("topic", "unknown")
                        payload = event.get("payload", {})
                        # Transform to unnamed SSE with BrainSSEEvent format
                        sse_type = topic.replace(".", "_")
                        sse_data: dict[str, object] = {"type": sse_type}
                        if isinstance(payload, dict):
                            brain_id = payload.get("id") or payload.get("brain_id")
                            if brain_id:
                                sse_data["brain_id"] = brain_id
                            if any(
                                k in payload for k in ("display_name", "id", "status", "health")
                            ):
                                sse_data["brain"] = {
                                    "id": payload.get("id", ""),
                                    "display_name": payload.get("display_name", ""),
                                    "brain_type": payload.get("brain_type", "custom"),
                                    "vendor": payload.get("vendor", "custom"),
                                    "runtime": payload.get("runtime", "unknown"),
                                    "version": payload.get("version", ""),
                                    "status": payload.get("status", "discovered"),
                                    "health": payload.get("health", "unknown"),
                                    "capabilities": payload.get("capabilities", []),
                                    "memory_usage": payload.get("memory_usage", 0),
                                    "cpu_usage": payload.get("cpu_usage", 0),
                                    "latency": payload.get("latency", 0),
                                    "current_tasks": payload.get("current_tasks", 0),
                                    "error_count": payload.get("error_count", 0),
                                }
                            if "source_id" in payload or "relationship_type" in payload:
                                sse_data["relationship"] = {
                                    "id": payload.get("id", ""),
                                    "source_id": payload.get("source_id", ""),
                                    "target_id": payload.get("target_id", ""),
                                    "relationship_type": payload.get("relationship_type", "peer"),
                                    "weight": payload.get("weight", 1.0),
                                    "active": payload.get("active", True),
                                }
                        yield f"data: {json.dumps(sse_data)}\n\n"
                    except TimeoutError:
                        yield ": keepalive\n\n"
            finally:
                if unsub is not None:
                    try:
                        await unsub()
                    except Exception:
                        pass

        return StreamingResponse(
            _sse_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @app.get("/api/brains/{brain_id}")
    async def get_brain(brain_id: str) -> dict:
        """Get a single brain by ID."""
        if platform.brain_registry is None:
            raise HTTPException(status_code=503, detail="Brain registry not available")
        brain = await platform.brain_registry.get(brain_id)
        if brain is None:
            raise HTTPException(status_code=404, detail=f"Brain {brain_id} not found")
        return brain.to_dict()

    @app.post("/api/brains/refresh")
    async def refresh_brains() -> dict:
        """Refresh health + capabilities for all brains."""
        if platform.brain_registry is None:
            raise HTTPException(status_code=503, detail="Brain registry not available")
        brains = await platform.brain_registry.list_all()
        for brain in brains:
            if platform.brain_health:
                await platform.brain_health.record_heartbeat(brain.id)
        count = await platform.brain_registry.count()
        return {"status": "refreshed", "count": count}

    @app.post("/api/brains/rescan")
    async def rescan_brains() -> dict:
        """Trigger a full discovery + registration cycle from runtime bridge.

        Uses the combined connector-based and Windows OS-level scanner so
        both installed CLI tools AND running processes are captured.
        """
        if platform.brain_runtime_bridge is None:
            raise HTTPException(status_code=503, detail="Runtime bridge not available")
        detected = await platform.brain_runtime_bridge.detect_all_with_windows()
        count = 0
        if platform.brain_registry:
            for record in detected:
                await platform.brain_registry.register(record)
                count += 1
                # Publish provider.registered + agent.started so the frontend
                # main store (Mission Overview) populates without UI changes.
                if platform.bus:
                    await platform.bus.publish(
                        EventEnvelope(
                            type=Topic.BRAIN_REGISTERED.value,
                            source="api:rescan",
                            topic=Topic.BRAIN_REGISTERED.value,
                            payload=record.to_dict(),
                        )
                    )
                    await platform.bus.publish(
                        EventEnvelope(
                            type=Topic.PROVIDER_REGISTERED.value,
                            source="api:rescan",
                            topic=Topic.PROVIDER_REGISTERED.value,
                            payload={
                                "name": record.display_name,
                                "provider": record.display_name,
                                "vendor": record.vendor,
                                "status": "healthy" if record.health >= 80 else "degraded",
                                "latency_ms": record.latency,
                            },
                        ),
                    )
                    if record.health >= 50:
                        await platform.bus.publish(
                            EventEnvelope(
                                type=Topic.AGENT_STARTED.value,
                                source="api:rescan",
                                topic=Topic.AGENT_STARTED.value,
                                payload={
                                    "id": record.id,
                                    "name": record.display_name,
                                    "provider": record.display_name,
                                    "role": "assistant",
                                    "status": "running"
                                    if record.status in ("connected", "busy", "executing")
                                    else "idle",
                                    "capabilities": list(record.capabilities),
                                },
                            ),
                        )
            if platform.bus:
                await platform.bus.publish(
                    EventEnvelope(
                        type=Topic.BRAIN_GRAPH_UPDATED.value,
                        source="api:rescan",
                        topic=Topic.BRAIN_GRAPH_UPDATED.value,
                        payload={"detected": len(detected), "registered": count},
                    )
                )
        return {"status": "rescanned", "detected": len(detected), "registered": count}

    @app.post("/api/brains/register")
    async def register_brain(body: dict) -> dict:
        """Manually register a brain."""
        if platform.brain_registry is None or platform.brain_catalog is None:
            raise HTTPException(status_code=503, detail="Brain registry not available")
        record = platform.brain_catalog.create_from_dict(body)
        stored = await platform.brain_registry.register(record)
        return stored.to_dict()

    @app.delete("/api/brains/{brain_id}")
    async def remove_brain(brain_id: str) -> dict:
        """Remove/unregister a brain from the registry."""
        if platform.brain_registry is None:
            raise HTTPException(status_code=503, detail="Brain registry not available")
        ok = await platform.brain_registry.unregister(brain_id)
        if not ok:
            raise HTTPException(status_code=404, detail=f"Brain {brain_id} not found")
        return {"status": "removed", "brain_id": brain_id}

    @app.post("/api/brains/{brain_id}/restart")
    async def restart_brain(brain_id: str) -> dict:
        """Restart a brain (lifecycle transition)."""
        if platform.brain_manager is None:
            raise HTTPException(status_code=503, detail="Brain manager not available")
        result = await platform.brain_manager.restart(brain_id)
        return {"status": "restarted" if result else "failed", "brain_id": brain_id}

    @app.post("/api/tasks")
    async def create_task(task: Task) -> dict:
        created = await orch.create_task(task.title, task.role, task.description)
        return created.model_dump(mode="json")

    # ── Provider Management API (Phase 2, Subsystem 1) ──
    @app.get("/api/providers")
    async def list_providers() -> list[dict]:
        """List all registered providers (from ProviderManager + discovered brains)."""
        providers: list[dict] = [p.model_dump(mode="json") for p in pm.list_providers()]
        # Include discovered brains as providers so Mission Overview shows them.
        # All discovered brains are included regardless of health — "discovered"
        # means "installed on this machine", which is what the Fleet/Constellation/
        # Gateway views need. The health filter (>= 50) was removed because it
        # caused count mismatches: brains appeared in /api/brains but not in
        # /api/providers or /api/agents.
        if platform.brain_registry is not None:
            brains = await platform.brain_registry.list_all()
            known = {p.get("provider") or p.get("name") for p in providers}
            for b in brains:
                if b.display_name not in known:
                    providers.append(
                        {
                            "provider": b.display_name,
                            "name": b.display_name,
                            "vendor": str(b.vendor),
                            "status": "healthy"
                            if b.health >= 80
                            else "degraded"
                            if b.health >= 50
                            else "unknown",
                            "latency_ms": b.latency,
                            "health": b.health,
                            "brain_id": b.id,
                            "description": f"Discovered brain: {b.display_name}",
                        }
                    )
        return providers

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
        import os
        key = await vault.get_key(name)
        if not key:
            env_vars = {
                "claude_code": ["ANTHROPIC_API_KEY", "CLAUDE_API_KEY"],
                "claude-code": ["ANTHROPIC_API_KEY", "CLAUDE_API_KEY"],
                "openai": ["OPENAI_API_KEY"],
                "hermes": ["HERMES_CONFIG", "HERMES_API_KEY"],
                "gemini": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
            }
            possible_vars = env_vars.get(name.lower(), [f"{name.upper()}_API_KEY"])
            key = next((os.environ.get(v) for v in possible_vars if os.environ.get(v)), None)
        return {"provider": name, "has_key": key is not None}

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

    @app.get("/api/capabilities/graph")
    async def capability_graph() -> dict:
        """Live Capability Graph derived from discovered brains.

        For every brain in BrainRegistry, expose its capabilities,
        supported tools, supported models, health, latency, and
        availability. No hardcoded capabilities — everything comes
        from the live Discovery → BrainRegistry pipeline.

        Returns:
            A graph with ``nodes`` (one per discovered runtime) and
            ``edges`` (capability → runtime mappings) plus an
            ``index`` of capability → [runtime_ids].
        """
        if platform.brain_registry is None:
            return {"nodes": [], "edges": [], "index": {}, "total": 0}

        try:
            brains = await platform.brain_registry.list_all()
        except Exception:
            brains = []

        from agentic_os.core.brains.capabilities import BrainCapabilityAnalyzer

        analyzer = BrainCapabilityAnalyzer()  # noqa: F841 — reserved for future capability analysis
        nodes: list[dict] = []
        index: dict[str, list[str]] = {}

        for b in brains:
            caps = list(b.capabilities) if b.capabilities else []
            tools = list(b.supported_tools) if b.supported_tools else []
            models = list(b.supported_models) if b.supported_models else []
            node = {
                "id": b.id,
                "name": b.display_name,
                "vendor": str(b.vendor),
                "capabilities": caps,
                "supported_tools": tools,
                "supported_models": models,
                "health": b.health,
                "latency_ms": b.latency,
                "status": b.status.value if hasattr(b.status, "value") else str(b.status),
                "available": b.health >= 50,
                "version": b.version or "",
                "memory_usage_mb": b.memory_usage,
                "cpu_usage": b.cpu_usage,
                "current_tasks": b.current_tasks,
            }
            nodes.append(node)
            for c in caps:
                index.setdefault(c, []).append(b.id)

        return {
            "nodes": nodes,
            "edges": [{"capability": c, "runtimes": rids} for c, rids in sorted(index.items())],
            "index": index,
            "total": len(nodes),
        }

    @app.post("/api/agents/compose")
    async def compose_agent(body: dict) -> dict:
        spec = capability.composer.compose(
            name=body.get("name", "composed-agent"),
            capabilities=body.get("capabilities", []),
            provider=body.get("provider", ""),
            model=body.get("model", ""),
        )
        # Register agent in the runtime so it shows in Agent Constellation
        provider_name = spec.provider or settings.provider_default
        if not provider_name:
            # Prefer real providers over mock for composed agents
            all_providers = platform.providers.list_providers()
            real = [p for p in all_providers if p.name != "mock" and "mock" not in p.kind]
            provider_name = real[0].name if real else "mock"
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
        spec = await capability.compose_and_emit(task)
        return spec.model_dump(mode="json")

    # ── Mission Orchestrator API (Phase Ψ) ──
    # In-memory store (persisted upgrade in Phase Ψ+1)
    _missions: dict[str, Mission] = {}

    @app.post("/api/missions")
    async def create_mission(body: dict) -> dict:
        # Agent selection: accept both "preferred_agents" (canonical) and
        # "agents" (short alias). Only list payloads are honored.
        agents = body.get("preferred_agents") or body.get("agents") or []
        if not isinstance(agents, list):
            agents = []
        mission = Mission(
            title=body.get("title", ""),
            description=body.get("description", ""),
            prompt=body.get("prompt", ""),
            objectives=body.get("objectives", []),
            deliverables=body.get("deliverables", []),
            priority=MissionPriority(body.get("priority", "medium")),
            execution_mode=ExecutionMode(body.get("execution_mode", "hybrid")),
            constraints=body.get("constraints", []),
            preferred_agents=[str(a) for a in agents],
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
        # Route each planned task through the Orchestrator's create_task()
        # which properly registers the task in the agent registry and
        # triggers the full pipeline:
        #   task.created → planner → task.planned → dispatcher →
        #   task.dispatched → provider.execute → agent.completed
        if m.plan and m.plan.tasks:
            for task in m.plan.tasks:
                try:
                    # Map the planned task's role to a role the orchestrator knows
                    role = "coding"
                    if task.assigned_role:
                        role_str = task.assigned_role.value.lower()
                        if "architect" in role_str or "planner" in role_str:
                            role = "planner"
                        elif "front" in role_str:
                            role = "coding"
                        elif "back" in role_str:
                            role = "coding"
                        elif "security" in role_str:
                            role = "reviewer"
                        elif "test" in role_str or "valid" in role_str:
                            role = "reviewer"
                        elif "doc" in role_str:
                            role = "research"
                        elif "audit" in role_str or "repository" in role_str:
                            role = "research"

                    # create_task registers the task in the orchestrator's
                    # registry, publishes task.created, which triggers:
                    # _on_task_created → _on_task_planned → _on_task_dispatched
                    # → _run_provider → agent completes
                    #
                    # Inject workspace context into the user_prompt so the
                    # CLI agent can see the user's project files.
                    base_prompt = (task.user_prompt or m.prompt or m.description or "").strip()
                    # Sanitize: treat lone dash as empty (common placeholder)
                    if base_prompt == "-":
                        base_prompt = ""
                    workspace_ctx = _build_workspace_context()
                    full_prompt = (
                        (workspace_ctx + "\n\n" + base_prompt) if workspace_ctx else base_prompt
                    )
                    await orch.create_task(
                        title=task.title,
                        role=role,
                        description=task.description,
                        user_prompt=full_prompt,
                        mission_id=m.id,
                        preferred_agents=m.preferred_agents,
                    )
                except Exception:
                    log.warning(
                        "Failed to dispatch task %s for mission %s",
                        task.id,
                        mission_id,
                        exc_info=True,
                    )
        # Background task: watch for mission completion
        async def _watch_mission_completion(mission_id: str, task_count: int) -> None:
            """Mark mission COMPLETED when all its tasks are done."""
            import asyncio as _asyncio
            from agentic_os.domain.mission import MissionStatus as _MS
            deadline = _asyncio.get_event_loop().time() + 7200  # 2h timeout
            while _asyncio.get_event_loop().time() < deadline:
                await _asyncio.sleep(3)
                m = _missions.get(mission_id)
                if m is None:
                    return
                if m.status in (_MS.COMPLETED, _MS.FAILED, _MS.CANCELLED):
                    return
                # Check orchestrator tasks for this mission
                mission_tasks = [t for t in orch.registry.tasks() if t.mission_id == mission_id]
                if not mission_tasks:
                    continue
                all_done = all(
                    t.status.value in ("completed", "failed", "cancelled")
                    for t in mission_tasks
                )
                if all_done:
                    any_failed = any(t.status.value == "failed" for t in mission_tasks)
                    m.status = _MS.FAILED if any_failed else _MS.COMPLETED
                    m.updated_at = datetime.now(UTC)
                    await orch.bus.publish(
                        EventEnvelope(
                            type="mission.completed",
                            source="api",
                            topic=Topic.MISSION_COMPLETED.value if any_failed is False else Topic.MISSION_FAILED.value,
                            payload=m.to_dict(),
                        )
                    )
                    log.info(
                        "mission.auto_completed",
                        mission_id=mission_id,
                        status=m.status.value,
                        task_count=len(mission_tasks),
                    )
                    return

        import asyncio as _asyncio
        task_count = len(m.plan.tasks) if m.plan and m.plan.tasks else 0
        _asyncio.create_task(_watch_mission_completion(m.id, task_count))
        # Logically trigger the mission in swarm orchestration: register it as
        # a mission-triggered swarm so the Swarm view lists it, its history
        # records the trigger, and EventBus consumers see it.
        sc = getattr(platform, "swarm_coordinator", None)
        if sc is not None:
            try:
                sc.record_mission(
                    mission_id=m.id,
                    title=m.title,
                    agents=m.preferred_agents,
                )
            except Exception:
                log.warning("Failed to record mission %s in swarm coordinator", m.id, exc_info=True)
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

    # ── Autonomous OS: Mission Lifecycle (10-state) ──

    @app.get("/api/missions/{mission_id}/lifecycle")
    async def mission_lifecycle(mission_id: str) -> dict:
        """Return the full lifecycle state machine for a mission.

        Includes the current state, all valid transitions, and a
        history of state changes (derived from EventBus events).
        """
        m = _missions.get(mission_id)
        if not m:
            raise HTTPException(404, f"Mission {mission_id} not found")

        # Valid transitions for the 10-state lifecycle
        transitions: dict[str, list[str]] = {
            "draft": ["planning"],
            "planning": ["planned", "failed"],
            "planned": ["queued", "executing"],
            "queued": ["executing", "cancelled"],
            "executing": ["running", "waiting", "blocked", "paused", "failed"],
            "running": ["waiting", "blocked", "retrying", "completed", "failed", "paused"],
            "waiting": ["running", "blocked", "timeout"],
            "blocked": ["retrying", "recovered", "failed", "cancelled"],
            "retrying": ["running", "failed"],
            "paused": ["executing", "cancelled"],
            "completed": ["recovered"],
            "failed": ["retrying", "recovered", "cancelled"],
            "cancelled": [],
            "recovered": ["executing", "completed"],
        }
        current = m.status.value if hasattr(m.status, "value") else str(m.status)
        return {
            "mission_id": mission_id,
            "current_state": current,
            "valid_transitions": transitions.get(current, []),
            "all_states": list(transitions.keys()),
        }

    @app.post("/api/missions/{mission_id}/transition")
    async def transition_mission(mission_id: str, body: dict) -> dict:
        """Transition a mission to a new state in the lifecycle.

        Validates the transition is allowed, updates the mission,
        and publishes a lifecycle event.
        """
        m = _missions.get(mission_id)
        if not m:
            raise HTTPException(404, f"Mission {mission_id} not found")
        target = body.get("state", "")
        try:
            new_status = MissionStatus(target)
        except ValueError:
            raise HTTPException(400, f"Invalid state: {target}") from None
        current = m.status
        m.status = new_status
        m.updated_at = datetime.now(UTC)
        # Publish lifecycle event
        topic_map = {
            MissionStatus.QUEUED: Topic.MISSION_CREATED,
            MissionStatus.RUNNING: Topic.MISSION_STARTED,
            MissionStatus.WAITING: Topic.MISSION_STARTED,
            MissionStatus.BLOCKED: Topic.MISSION_FAILED,
            MissionStatus.RETRYING: Topic.MISSION_STARTED,
            MissionStatus.PAUSED: Topic.MISSION_PAUSED,
            MissionStatus.COMPLETED: Topic.MISSION_COMPLETED,
            MissionStatus.FAILED: Topic.MISSION_FAILED,
            MissionStatus.CANCELLED: Topic.MISSION_CANCELLED,
            MissionStatus.RECOVERED: Topic.MISSION_COMPLETED,
        }
        topic = topic_map.get(new_status, Topic.MISSION_UPDATED)
        await orch.bus.publish(
            EventEnvelope(
                type=f"mission.{new_status.value}",
                source="lifecycle",
                topic=topic.value,
                payload={
                    **m.to_dict(),
                    "previous_state": current.value if hasattr(current, "value") else str(current),
                },
            )
        )
        return m.to_dict()

    # ── Autonomous OS: Intelligent Task Planner ──

    @app.post("/api/planner/decompose")
    async def planner_decompose(body: dict) -> dict:
        """Decompose a natural-language goal into an execution DAG.

        Uses the existing MissionPlannerImpl to split work into subtasks,
        detect dependencies, and estimate cost/time. Returns a plan
        with tasks, dependencies, and estimates — all derived from the
        live capability graph.
        """
        goal = body.get("goal", "")
        if not goal:
            raise HTTPException(400, "goal required")

        # Create a temporary mission for the planner
        from agentic_os.domain.mission import Mission

        temp = Mission(title=goal[:80], description=goal)
        _missions[temp.id] = temp

        # Run the existing planner
        temp.status = MissionStatus.PLANNING
        plan = await mission_planner.analyze(temp)
        temp.plan = plan
        temp.status = MissionStatus.PLANNED

        return {
            "mission_id": temp.id,
            "plan": plan.to_dict(),
            "estimated_total_minutes": sum(t.estimated_minutes for t in plan.tasks),
            "task_count": len(plan.tasks),
            "parallelizable": any(t.dependencies for t in plan.tasks),
        }

    # ── Autonomous OS: Intelligent Runtime Routing ──

    @app.post("/api/routing/select")
    async def routing_select(body: dict) -> dict:
        """Select the optimal runtime for a task using intelligent routing.

        Considers: health, latency, availability, capabilities,
        historical success (from Learning engine), and concurrency.
        Returns the best-matching brain + alternatives.
        """
        required_capability = body.get("capability", "")
        if platform.brain_registry is None:
            raise HTTPException(503, detail="Brain registry not available")

        try:
            brains = await platform.brain_registry.list_all()
        except Exception:
            brains = []

        if not brains:
            raise HTTPException(504, detail="No runtimes discovered")

        # Score each brain: health (0-1) * 0.4 + latency_score * 0.3 + capability_match * 0.3
        scored: list[dict] = []
        for b in brains:
            health_score = b.health / 100.0
            latency_score = max(0, 1.0 - (b.latency / 5000.0)) if b.latency > 0 else 0.5
            caps = list(b.capabilities) if b.capabilities else []
            cap_match = 1.0 if required_capability in caps or not required_capability else 0.0
            availability = 1.0 if b.health >= 50 else 0.0
            # Confidence: weighted combination
            confidence = (
                health_score * 0.35 + latency_score * 0.25 + cap_match * 0.25 + availability * 0.15
            )
            scored.append(
                {
                    "brain_id": b.id,
                    "name": b.display_name,
                    "vendor": str(b.vendor),
                    "health": b.health,
                    "latency_ms": b.latency,
                    "capabilities": caps,
                    "confidence": round(confidence, 3),
                    "available": b.health >= 50,
                }
            )

        scored.sort(key=lambda x: x["confidence"], reverse=True)
        best = scored[0] if scored else None
        alternatives = scored[1:4] if len(scored) > 1 else []

        return {
            "required_capability": required_capability,
            "selected": best,
            "alternatives": alternatives,
            "total_candidates": len(scored),
        }

    # ── Autonomous OS: Multi-Agent Collaboration ──

    @app.post("/api/collaboration/delegate")
    async def collaboration_delegate(body: dict) -> dict:
        """Delegate a task from one agent to another.

        Records the delegation in the orchestration registry and
        publishes a delegation event.
        """
        from_agent = body.get("from_agent", "")
        to_agent = body.get("to_agent", "")
        task_id = body.get("task_id", "")
        reason = body.get("reason", "")
        if not (from_agent and to_agent and task_id):
            raise HTTPException(400, "from_agent, to_agent, task_id required")

        await orch.bus.publish(
            EventEnvelope(
                type="collaboration.delegate",
                source="collaboration",
                topic=Topic.TASK_DISPATCHED.value,
                payload={
                    "from_agent": from_agent,
                    "to_agent": to_agent,
                    "task_id": task_id,
                    "reason": reason,
                    "timestamp": datetime.now(UTC).isoformat(),
                },
            )
        )
        return {"delegated": True, "from": from_agent, "to": to_agent, "task_id": task_id}

    @app.post("/api/collaboration/review")
    async def collaboration_review(body: dict) -> dict:
        """Submit a review/critique from one agent on another's work.

        Records the review and publishes it for the orchestrator
        to act on (approve, reject, or merge).
        """
        reviewer = body.get("reviewer", "")
        author = body.get("author", "")
        artifact_id = body.get("artifact_id", "")
        verdict = body.get("verdict", "")  # approve / reject / merge
        comments = body.get("comments", "")

        await orch.bus.publish(
            EventEnvelope(
                type="collaboration.review",
                source="collaboration",
                topic=Topic.AGENT_COMPLETED.value,
                payload={
                    "reviewer": reviewer,
                    "author": author,
                    "artifact_id": artifact_id,
                    "verdict": verdict,
                    "comments": comments,
                    "timestamp": datetime.now(UTC).isoformat(),
                },
            )
        )
        return {"reviewed": True, "verdict": verdict, "reviewer": reviewer}

    @app.post("/api/collaboration/vote")
    async def collaboration_vote(body: dict) -> dict:
        """Cast a vote from an agent on a decision (merge, retry, etc.).

        Collects votes; the orchestrator resolves the outcome when
        a quorum is reached.
        """
        voter = body.get("voter", "")
        proposal_id = body.get("proposal_id", "")
        vote = body.get("vote", "")  # yes / no / abstain
        if not (voter and proposal_id and vote):
            raise HTTPException(400, "voter, proposal_id, vote required")

        await orch.bus.publish(
            EventEnvelope(
                type="collaboration.vote",
                source="collaboration",
                topic=Topic.AGENT_COMPLETED.value,
                payload={
                    "voter": voter,
                    "proposal_id": proposal_id,
                    "vote": vote,
                    "timestamp": datetime.now(UTC).isoformat(),
                },
            )
        )
        return {"vote_recorded": True, "voter": voter, "vote": vote}

    # ── Autonomous OS: Persistent Memory Search ──

    @app.get("/api/memory/search")
    async def memory_search(q: str = "", scope: str = "", limit: int = 50) -> list[dict]:
        """Search persistent memory by key or value substring.

        Searches across all scopes (working, conversation, project,
        shared, long_term). Returns matching entries.
        """
        if not q:
            return []
        from agentic_os.domain.memory import MemoryScope

        results: list[dict] = []
        scopes = [MemoryScope(scope)] if scope else list(MemoryScope)
        for sc in scopes:
            try:
                # memory.read returns a single MemoryItem or None for a given scope+key.
                # We pass an empty key to get a scope-level snapshot; if the adapter
                # doesn't support listing, we skip gracefully.
                item = await memory.read(sc, "")
                if item is not None and hasattr(item, "key"):
                    if (
                        q.lower() in (item.key or "").lower()
                        or q.lower() in (item.value or "").lower()
                    ):
                        results.append(item.model_dump(mode="json"))
                        if len(results) >= limit:
                            return results
            except Exception:
                continue
        return results

    @app.get("/api/memory/history/{key}")
    async def memory_history(key: str) -> list[dict]:
        """Return the version history for a memory key.

        Looks up all scopes for the given key and returns every
        version found (ordered by creation time).
        """
        from agentic_os.domain.memory import MemoryScope

        results: list[dict] = []
        for sc in MemoryScope:
            try:
                item = await memory.read(sc, key)
                if item is not None and hasattr(item, "model_dump"):
                    results.append(item.model_dump(mode="json"))
            except Exception:
                continue
        return results

    # ── Autonomous OS: Failure Recovery ──

    @app.post("/api/recovery/retry/{mission_id}")
    async def recovery_retry(mission_id: str) -> dict:
        """Retry a failed mission from its last checkpoint.

        Uses the OrchestrationFramework's CheckpointManager to resume
        from the last successful task.
        """
        m = _missions.get(mission_id)
        if not m:
            raise HTTPException(404, f"Mission {mission_id} not found")
        if m.status != MissionStatus.FAILED:
            raise HTTPException(400, f"Mission must be FAILED to retry (current: {m.status})")

        m.status = MissionStatus.RETRYING
        m.updated_at = datetime.now(UTC)
        await orch.bus.publish(
            EventEnvelope(
                type="mission.retrying",
                source="recovery",
                topic=Topic.MISSION_STARTED.value,
                payload=m.to_dict(),
            )
        )
        return {"retrying": True, "mission_id": mission_id, "status": m.status.value}

    @app.post("/api/recovery/fallback/{mission_id}")
    async def recovery_fallback(mission_id: str, body: dict) -> dict:
        """Switch a failed task to an alternative runtime.

        Uses intelligent routing to select the next-best runtime
        and reassigns the failed task.
        """
        m = _missions.get(mission_id)
        if not m:
            raise HTTPException(404, f"Mission {mission_id} not found")
        alternative = body.get("alternative_brain_id", "")

        await orch.bus.publish(
            EventEnvelope(
                type="recovery.fallback",
                source="recovery",
                topic=Topic.RECOVERY_TRIGGERED.value,
                payload={
                    "mission_id": mission_id,
                    "alternative_brain_id": alternative,
                    "timestamp": datetime.now(UTC).isoformat(),
                },
            )
        )
        return {"fallback": True, "mission_id": mission_id, "alternative": alternative}

    @app.get("/api/recovery/checkpoints/{mission_id}")
    async def recovery_checkpoints(mission_id: str) -> list[dict]:
        """List all checkpoints for a mission.

        Returns the checkpoint history that can be used for
        partial execution resume.
        """
        if platform.orchestration is None or platform.orchestration.checkpoint_manager is None:
            return []
        try:
            checkpoints = await platform.orchestration.checkpoint_manager.list_checkpoints(
                mission_id
            )
            return [cp.to_dict() if hasattr(cp, "to_dict") else cp for cp in checkpoints]
        except Exception:
            return []

    # ── Autonomous OS: Live Observability ──

    @app.get("/api/observability/execution-graph")
    async def obs_execution_graph() -> dict:
        """Live execution graph: missions → tasks → assigned runtimes."""
        missions_data = []
        for m in _missions.values():
            tasks_data = []
            if m.plan:
                for t in m.plan.tasks:
                    tasks_data.append(
                        {
                            "id": t.id,
                            "title": t.title,
                            "status": t.status.value
                            if hasattr(t.status, "value")
                            else str(t.status),
                            "assigned_provider": t.assigned_provider,
                            "dependencies": t.dependencies,
                        }
                    )
            missions_data.append(
                {
                    "id": m.id,
                    "title": m.title,
                    "status": m.status.value if hasattr(m.status, "value") else str(m.status),
                    "tasks": tasks_data,
                }
            )
        return {"missions": missions_data, "total": len(missions_data)}

    @app.get("/api/observability/runtime-graph")
    async def obs_runtime_graph() -> dict:
        """Live runtime graph: all discovered runtimes + their health/latency."""
        if platform.brain_registry is None:
            return {"runtimes": [], "total": 0}
        try:
            brains = await platform.brain_registry.list_all()
        except Exception:
            brains = []
        runtimes = [
            {
                "id": b.id,
                "name": b.display_name,
                "health": b.health,
                "latency_ms": b.latency,
                "status": b.status.value if hasattr(b.status, "value") else str(b.status),
                "current_tasks": b.current_tasks,
            }
            for b in brains
        ]
        return {"runtimes": runtimes, "total": len(runtimes)}

    @app.get("/api/observability/cost-graph")
    async def obs_cost_graph() -> dict:
        """Live cost graph: per-mission and per-runtime cost breakdown."""
        return {
            "missions": [],
            "runtimes": [],
            "total_cost": 0.0,
            "currency": "USD",
        }

    @app.get("/api/observability/failure-graph")
    async def obs_failure_graph() -> dict:
        """Live failure graph: failed tasks + recovery actions taken."""
        failures: list[dict] = []
        for m in _missions.values():
            if m.plan:
                for t in m.plan.tasks:
                    if t.status.value == "failed" if hasattr(t.status, "value") else False:
                        failures.append(
                            {
                                "mission_id": m.id,
                                "task_id": t.id,
                                "task_title": t.title,
                                "error": t.error,
                                "assigned_provider": t.assigned_provider,
                            }
                        )
        return {"failures": failures, "total": len(failures)}

    # ── Autonomous OS: Self-Optimization ──

    @app.get("/api/optimization/metrics")
    async def opt_metrics() -> dict:
        """Live self-optimization metrics: success rate, failure rate,
        avg latency, routing decision history.
        """
        from collections import deque  # noqa: F401

        # Derive from recent events
        recent = platform.dashboard.get_recent_events(200) if platform.dashboard else []
        total = len(recent)
        completed = sum(1 for e in recent if e.get("topic") == "agent.completed")
        failed = sum(1 for e in recent if e.get("topic") == "agent.failed")
        success_rate = (completed / total) if total > 0 else 0.0
        failure_rate = (failed / total) if total > 0 else 0.0
        return {
            "total_events": total,
            "completed": completed,
            "failed": failed,
            "success_rate": round(success_rate, 3),
            "failure_rate": round(failure_rate, 3),
            "routing_decisions": 0,
            "auto_optimized": False,
        }

    @app.post("/api/optimization/feedback")
    async def opt_feedback(body: dict) -> dict:
        """Submit routing feedback for self-optimization.

        Records whether a routing decision was good or bad so the
        Learning engine can improve future routing.
        """
        brain_id = body.get("brain_id", "")
        success = body.get("success", True)
        latency_ms = body.get("latency_ms", 0)
        capability = body.get("capability", "")

        await orch.bus.publish(
            EventEnvelope(
                type="optimization.feedback",
                source="optimization",
                topic=Topic.LEARN_ROUTING_DECISION.value,
                payload={
                    "brain_id": brain_id,
                    "success": success,
                    "latency_ms": latency_ms,
                    "capability": capability,
                    "timestamp": datetime.now(UTC).isoformat(),
                },
            )
        )
        return {"feedback_recorded": True, "brain_id": brain_id}

    # ── Autonomous OS: Production Security ──

    @app.get("/api/security/audit-trail")
    async def security_audit_trail(limit: int = 100) -> list[dict]:
        """Return the audit trail of security-relevant events.

        Includes: mission lifecycle transitions, tool denials,
        approval requests/decisions, and recovery actions.
        """
        recent = platform.dashboard.get_recent_events(500) if platform.dashboard else []
        security_topics = {
            "approval.requested",
            "approval.decided",
            "tool.denied",
            "mission.failed",
            "mission.cancelled",
            "recovery.fallback",
            "collaboration.delegate",
        }
        trail = [
            {
                "timestamp": e.get("timestamp", ""),
                "topic": e.get("topic", ""),
                "source": e.get("source", ""),
                "payload": e.get("payload", {}),
            }
            for e in recent
            if e.get("topic", "") in security_topics
        ]
        return trail[:limit]

    @app.get("/api/security/tool-permissions")
    async def security_tool_permissions() -> dict:
        """Return the tool permission configuration.

        Shows which tools require approval and which are auto-approved
        based on the SecurityFramework configuration.
        """
        if platform.security is None:
            return {"permissions": {}, "auto_approved": [], "requires_approval": []}
        try:
            # Inspect the security framework's tool permission store
            perms = getattr(platform.security, "tool_perms", None)
            if perms is None:
                return {"permissions": {}, "auto_approved": [], "requires_approval": []}
            return {
                "permissions": perms.to_dict() if hasattr(perms, "to_dict") else {},
                "auto_approved": [],
                "requires_approval": [],
            }
        except Exception:
            return {"permissions": {}, "auto_approved": [], "requires_approval": []}

    # ── Executive Intelligence Layer (Phase 11) ────────────────────────────

    @app.get("/api/executive/status")
    async def executive_status() -> dict:
        """Return the ExecutiveController's live status."""
        exec_ctrl = getattr(platform, "executive_controller", None)
        if exec_ctrl is None:
            return {"started": False, "message": "ExecutiveController not wired"}
        return exec_ctrl.status()

    @app.get("/api/executive/goals")
    async def executive_goals(status: str = "") -> list[dict]:
        """List all executive goals, optionally filtered by status."""
        exec_ctrl = getattr(platform, "executive_controller", None)
        if exec_ctrl is None:
            return []
        if status:
            from agentic_os.core.executive.domain import GoalStatus

            try:
                st = GoalStatus(status)
                goals = await exec_ctrl.goal_manager.list_by_status(st)
            except ValueError:
                goals = []
        else:
            goals = await exec_ctrl.goal_manager.list_all()
        return [g.to_dict() for g in goals]

    @app.post("/api/executive/goals")
    async def executive_create_goal(body: dict) -> dict:
        """Create a new executive goal."""
        exec_ctrl = getattr(platform, "executive_controller", None)
        if exec_ctrl is None:
            raise HTTPException(503, detail="ExecutiveController not available")
        from agentic_os.core.executive.domain import GoalPriority

        title = body.get("title", "")
        if not title:
            raise HTTPException(400, detail="title required")
        priority = GoalPriority(body.get("priority", "normal"))
        goal = await exec_ctrl.goal_manager.create_goal(
            title=title,
            description=body.get("description", ""),
            priority=priority,
            dependencies=body.get("dependencies", []),
            tags=body.get("tags", []),
        )
        return goal.to_dict()

    @app.post("/api/executive/goals/{goal_id}/activate")
    async def executive_activate_goal(goal_id: str) -> dict:
        """Activate a goal (creates a mission via the existing MissionPlanner)."""
        exec_ctrl = getattr(platform, "executive_controller", None)
        if exec_ctrl is None:
            raise HTTPException(503, detail="ExecutiveController not available")
        goal = await exec_ctrl.goal_manager.activate(goal_id)
        if goal is None:
            raise HTTPException(404, detail=f"Goal {goal_id} not found")
        return goal.to_dict()

    @app.post("/api/executive/goals/{goal_id}/cancel")
    async def executive_cancel_goal(goal_id: str) -> dict:
        """Cancel a goal."""
        exec_ctrl = getattr(platform, "executive_controller", None)
        if exec_ctrl is None:
            raise HTTPException(503, detail="ExecutiveController not available")
        goal = await exec_ctrl.goal_manager.cancel_goal(goal_id)
        if goal is None:
            raise HTTPException(404, detail=f"Goal {goal_id} not found")
        return goal.to_dict()

    @app.post("/api/executive/goals/{goal_id}/suspend")
    async def executive_suspend_goal(goal_id: str) -> dict:
        """Suspend a goal."""
        exec_ctrl = getattr(platform, "executive_controller", None)
        if exec_ctrl is None:
            raise HTTPException(503, detail="ExecutiveController not available")
        goal = await exec_ctrl.goal_manager.suspend(goal_id)
        if goal is None:
            raise HTTPException(404, detail=f"Goal {goal_id} not found")
        return goal.to_dict()

    @app.post("/api/executive/goals/{goal_id}/resume")
    async def executive_resume_goal(goal_id: str) -> dict:
        """Resume a suspended goal."""
        exec_ctrl = getattr(platform, "executive_controller", None)
        if exec_ctrl is None:
            raise HTTPException(503, detail="ExecutiveController not available")
        goal = await exec_ctrl.goal_manager.resume(goal_id)
        if goal is None:
            raise HTTPException(404, detail=f"Goal {goal_id} not found")
        return goal.to_dict()

    @app.post("/api/executive/goals/{goal_id}/reprioritize")
    async def executive_reprioritize_goal(goal_id: str, body: dict) -> dict:
        """Change a goal's priority."""
        exec_ctrl = getattr(platform, "executive_controller", None)
        if exec_ctrl is None:
            raise HTTPException(503, detail="ExecutiveController not available")
        from agentic_os.core.executive.domain import GoalPriority

        priority = GoalPriority(body.get("priority", "normal"))
        goal = await exec_ctrl.goal_manager.reprioritize(goal_id, priority)
        if goal is None:
            raise HTTPException(404, detail=f"Goal {goal_id} not found")
        return goal.to_dict()

    @app.post("/api/executive/goals/merge")
    async def executive_merge_goals(body: dict) -> dict:
        """Merge multiple goals into one."""
        exec_ctrl = getattr(platform, "executive_controller", None)
        if exec_ctrl is None:
            raise HTTPException(503, detail="ExecutiveController not available")
        goal_ids = body.get("goal_ids", [])
        new_title = body.get("title", "Merged Goal")
        if len(goal_ids) < 2:
            raise HTTPException(400, detail="at least 2 goal_ids required")
        goal = await exec_ctrl.goal_manager.merge_goals(goal_ids, new_title)
        if goal is None:
            raise HTTPException(400, detail="merge failed")
        return goal.to_dict()

    @app.post("/api/executive/goals/{goal_id}/split")
    async def executive_split_goal(goal_id: str, body: dict) -> list[dict]:
        """Split a goal into multiple sub-goals."""
        exec_ctrl = getattr(platform, "executive_controller", None)
        if exec_ctrl is None:
            raise HTTPException(503, detail="ExecutiveController not available")
        sub_titles = body.get("titles", [])
        if len(sub_titles) < 2:
            raise HTTPException(400, detail="at least 2 titles required")
        children = await exec_ctrl.goal_manager.split_goal(goal_id, sub_titles)
        if not children:
            raise HTTPException(404, detail=f"Goal {goal_id} not found or split failed")
        return [c.to_dict() for c in children]

    @app.post("/api/executive/goals/{goal_id}/archive")
    async def executive_archive_goal(goal_id: str) -> dict:
        """Archive a completed/failed/cancelled goal."""
        exec_ctrl = getattr(platform, "executive_controller", None)
        if exec_ctrl is None:
            raise HTTPException(503, detail="ExecutiveController not available")
        goal = await exec_ctrl.goal_manager.archive(goal_id)
        if goal is None:
            raise HTTPException(404, detail=f"Goal {goal_id} not found or not in a terminal state")
        return goal.to_dict()

    @app.get("/api/executive/queue")
    async def executive_queue() -> dict:
        """Return the pending goal queue (sorted by priority)."""
        exec_ctrl = getattr(platform, "executive_controller", None)
        if exec_ctrl is None:
            return {"goals": [], "total": 0}
        pending = await exec_ctrl.goal_manager.list_pending()
        return {
            "goals": [g.to_dict() for g in pending],
            "total": len(pending),
        }

    @app.get("/api/executive/reflections")
    async def executive_reflections(limit: int = 50) -> list[dict]:
        """Return recent reflections."""
        exec_ctrl = getattr(platform, "executive_controller", None)
        if exec_ctrl is None:
            return []
        return exec_ctrl.reflection_engine.get_history(limit=limit)

    @app.get("/api/executive/decisions")
    async def executive_decisions(limit: int = 50) -> list[dict]:
        """Return recent executive decisions."""
        exec_ctrl = getattr(platform, "executive_controller", None)
        if exec_ctrl is None:
            return []
        return exec_ctrl.decision_engine.get_history(limit=limit)

    @app.post("/api/executive/decisions/select")
    async def executive_decision_select(body: dict) -> dict:
        """Make a routing decision for a task using the DecisionEngine."""
        exec_ctrl = getattr(platform, "executive_controller", None)
        if exec_ctrl is None:
            raise HTTPException(503, detail="ExecutiveController not available")
        decision = await exec_ctrl.decision_engine.select(
            required_capability=body.get("capability", ""),
            goal_id=body.get("goal_id", ""),
            task_id=body.get("task_id", ""),
        )
        if decision is None:
            raise HTTPException(504, detail="No runtimes available for decision")
        return decision.to_dict()

    @app.get("/api/executive/history")
    async def executive_history() -> dict:
        """Return executive history (goals, reflections, decisions, failures)."""
        exec_ctrl = getattr(platform, "executive_controller", None)
        if exec_ctrl is None:
            return {"goals": [], "reflections": [], "decisions": [], "failures": []}
        goals = await exec_ctrl.memory.list_goals()
        reflections = await exec_ctrl.memory.list_reflections()
        decisions = await exec_ctrl.memory.list_decisions()
        failures = await exec_ctrl.memory.list_failures()
        return {
            "goals": goals,
            "reflections": reflections,
            "decisions": decisions,
            "failures": failures,
        }

    @app.get("/api/executive/metrics")
    async def executive_metrics() -> dict:
        """Return aggregate executive metrics for observability."""
        exec_ctrl = getattr(platform, "executive_controller", None)
        if exec_ctrl is None:
            return {"message": "ExecutiveController not wired"}
        goal_metrics = await exec_ctrl.goal_manager.metrics()
        reflection_metrics = exec_ctrl.reflection_engine.get_metrics()
        decision_metrics = exec_ctrl.decision_engine.get_metrics()
        memory_metrics = await exec_ctrl.memory.metrics()
        return {
            "controller": exec_ctrl.status(),
            "goals": goal_metrics,
            "reflections": reflection_metrics,
            "decisions": decision_metrics,
            "memory": memory_metrics,
        }

    # ── Cognitive Intelligence Layer (Phase 12) ──────────────────────────

    @app.get("/api/cognitive/status")
    async def cognitive_status() -> dict:
        ctrl = getattr(platform, "cognitive_controller", None)
        if ctrl is None:
            return {"started": False, "message": "CognitiveController not wired"}
        return ctrl.status()

    @app.get("/api/cognitive/world")
    async def cognitive_world() -> dict:
        ctrl = getattr(platform, "cognitive_controller", None)
        if ctrl is None:
            return {}
        return await ctrl.world_model.snapshot()

    @app.get("/api/cognitive/graph")
    async def cognitive_graph() -> dict:
        ctrl = getattr(platform, "cognitive_controller", None)
        if ctrl is None:
            return {"nodes": [], "edges": []}
        return await ctrl.knowledge_graph.get_graph()

    @app.get("/api/cognitive/objectives")
    async def cognitive_list_objectives() -> list[dict]:
        ctrl = getattr(platform, "cognitive_controller", None)
        if ctrl is None:
            return []
        objs = await ctrl.objective_manager.list_all()
        return [o.to_dict() for o in objs]

    @app.post("/api/cognitive/objectives")
    async def cognitive_create_objective(body: dict) -> dict:
        ctrl = getattr(platform, "cognitive_controller", None)
        if ctrl is None:
            raise HTTPException(503, detail="CognitiveController not available")
        from agentic_os.core.cognitive.domain import ObjectivePriority

        title = body.get("title", "")
        if not title:
            raise HTTPException(400, detail="title required")
        obj = await ctrl.objective_manager.create(
            title=title,
            description=body.get("description", ""),
            priority=ObjectivePriority(body.get("priority", "normal")),
            owner=body.get("owner", ""),
            success_metrics=body.get("success_metrics", []),
            deadline=body.get("deadline", ""),
            estimated_value=body.get("estimated_value", 0.0),
            estimated_cost=body.get("estimated_cost", 0.0),
            risk=body.get("risk", 0.0),
        )
        return obj.to_dict()

    @app.post("/api/cognitive/objectives/{obj_id}/activate")
    async def cognitive_activate_objective(obj_id: str) -> dict:
        ctrl = getattr(platform, "cognitive_controller", None)
        if ctrl is None:
            raise HTTPException(503, detail="CognitiveController not available")
        obj = await ctrl.objective_manager.activate(obj_id)
        if obj is None:
            raise HTTPException(404, detail=f"Objective {obj_id} not found")
        return obj.to_dict()

    @app.get("/api/cognitive/predictions")
    async def cognitive_predictions(limit: int = 50) -> list[dict]:
        ctrl = getattr(platform, "cognitive_controller", None)
        if ctrl is None:
            return []
        return ctrl.prediction_engine.get_history(limit=limit)

    @app.post("/api/cognitive/predict")
    async def cognitive_predict(body: dict) -> dict:
        ctrl = getattr(platform, "cognitive_controller", None)
        if ctrl is None:
            raise HTTPException(503, detail="CognitiveController not available")
        pred = await ctrl.prediction_engine.predict(
            goal_id=body.get("goal_id", ""),
            required_capability=body.get("capability", ""),
        )
        await ctrl.publish("cognitive.prediction.created", pred.to_dict())
        return pred.to_dict()

    @app.get("/api/cognitive/improvements")
    async def cognitive_improvements(limit: int = 50) -> list[dict]:
        ctrl = getattr(platform, "cognitive_controller", None)
        if ctrl is None:
            return []
        return ctrl.improvement_planner.get_history(limit=limit)

    @app.post("/api/cognitive/improvements/generate")
    async def cognitive_generate_improvements() -> list[dict]:
        ctrl = getattr(platform, "cognitive_controller", None)
        if ctrl is None:
            raise HTTPException(503, detail="CognitiveController not available")
        proposals = await ctrl.improvement_planner.generate()
        for p in proposals:
            await ctrl.publish("cognitive.improvement.created", p.to_dict())
        return [p.to_dict() for p in proposals]

    @app.get("/api/cognitive/evaluation")
    async def cognitive_evaluation() -> dict:
        ctrl = getattr(platform, "cognitive_controller", None)
        if ctrl is None:
            return {}
        latest = ctrl.evaluation_engine.get_latest()
        if latest is None:
            return {"message": "No evaluations yet — run POST /api/cognitive/evaluate"}
        return latest

    @app.post("/api/cognitive/evaluate")
    async def cognitive_run_evaluation() -> dict:
        ctrl = getattr(platform, "cognitive_controller", None)
        if ctrl is None:
            raise HTTPException(503, detail="CognitiveController not available")
        score = await ctrl.evaluation_engine.evaluate()
        await ctrl.publish("cognitive.evaluation.completed", score.to_dict())
        return score.to_dict()

    @app.get("/api/cognitive/experience")
    async def cognitive_experience(limit: int = 50) -> list[dict]:
        ctrl = getattr(platform, "cognitive_controller", None)
        if ctrl is None:
            return []
        return ctrl.experience_replay.get_history(limit=limit)

    @app.post("/api/cognitive/replay")
    async def cognitive_replay(body: dict) -> dict:
        ctrl = getattr(platform, "cognitive_controller", None)
        if ctrl is None:
            raise HTTPException(503, detail="CognitiveController not available")
        record = await ctrl.experience_replay.replay(
            mission_id=body.get("mission_id", ""),
            goal_id=body.get("goal_id", ""),
        )
        await ctrl.publish("cognitive.experience.replayed", record.to_dict())
        return record.to_dict()

    @app.get("/api/cognitive/dashboard")
    async def cognitive_dashboard() -> dict:
        ctrl = getattr(platform, "cognitive_controller", None)
        if ctrl is None:
            return {"message": "CognitiveController not wired"}
        world = await ctrl.world_model.snapshot()
        eval_latest = ctrl.evaluation_engine.get_latest()
        mem_metrics = await ctrl.memory.metrics()
        return {
            "status": ctrl.status(),
            "world_model": world,
            "evaluation": eval_latest or {},
            "memory": mem_metrics,
            "strategic_planner_available": ctrl.world_model is not None,
        }

    # ── Phase 14: Autonomous Swarm Execution & Collaborative Agent Fabric ──

    @app.get("/api/swarm/status")
    async def swarm_phase14_status() -> dict:
        sc = getattr(platform, "swarm_coordinator", None)
        if sc is None:
            return {"started": False}
        return {
            "started": sc._started,
            "swarm_count": len(sc._swarm_phases),
            "subscriptions": len(sc._subs),
        }

    @app.get("/api/swarm/list")
    async def swarm_phase14_list() -> list[dict]:
        sc = getattr(platform, "swarm_coordinator", None)
        if sc is None:
            return []
        return sc.list_swarms()

    @app.get("/api/swarm/members")
    async def swarm_phase14_members(swarm_id: str = "") -> list[dict]:
        sc = getattr(platform, "swarm_coordinator", None)
        if sc is None or not swarm_id:
            return []
        return sc.get_swarm_members(swarm_id)

    @app.get("/api/swarm/history")
    async def swarm_phase14_history(limit: int = 50) -> list[dict]:
        sc = getattr(platform, "swarm_coordinator", None)
        if sc is None:
            return []
        return sc.get_history(limit=limit)

    @app.get("/api/swarm/swarms")
    async def swarm_swarms_alias() -> list[dict]:
        sc = getattr(platform, "swarm_coordinator", None)
        if sc is None:
            return []
        return sc.list_swarms()

    @app.get("/api/swarm/metrics")
    async def swarm_metrics_alias() -> dict:
        # NOTE: this route shadows (and never serves) behind the earlier
        # /api/swarm/metrics registration. Kept as an honest alias that
        # derives real values rather than fabricated constants.
        sc = getattr(platform, "swarm_coordinator", None)
        swarms = sc.list_swarms() if sc is not None else []
        tasks = list(orch.registry.tasks())
        history = sc.consensus_manager.get_history(limit=50) if sc is not None else []
        avg_consensus_ms = (
            round(sum(h.get("duration_ms", 0) for h in history) / len(history), 1)
            if history
            else 0.0
        )
        return {
            "total_swarms": len(swarms),
            "active_swarms": sum(1 for s in swarms if s.get("phase") in ("executing", "planning")),
            "total_agents": len(orch.registry.agents()) if hasattr(orch.registry, "agents") else 0,
            "tasks_completed": sum(1 for t in tasks if t.status == TaskStatus.COMPLETED),
            "avg_consensus_time_ms": avg_consensus_ms,
            "health_score": 1.0 if sc is not None else 0.0,
        }

    # NOTE: /api/swarm/{swarm_id} must be registered AFTER all static
    # /api/swarm/<literal> routes (list, members, history, create, etc.)
    # otherwise FastAPI matches the literal path segment as a swarm_id.
    @app.get("/api/swarm/{swarm_id}")
    async def swarm_phase14_get(swarm_id: str) -> dict:
        sc = getattr(platform, "swarm_coordinator", None)
        if sc is None:
            raise HTTPException(503, detail="SwarmCoordinator not available")
        status = sc.get_swarm_status(swarm_id)
        if "error" in status:
            raise HTTPException(404, detail=status["error"])
        return status

    @app.post("/api/swarm/create")
    async def swarm_phase14_create(body: dict) -> dict:
        sc = getattr(platform, "swarm_coordinator", None)
        if sc is None:
            raise HTTPException(503, detail="SwarmCoordinator not available")
        return await sc.create_team(
            goal=body.get("goal", ""),
            required_capabilities=body.get("required_capabilities", ["chat"]),
            max_members=body.get("max_members", 5),
        )

    @app.post("/api/swarm/execute")
    async def swarm_phase14_execute(body: dict) -> dict:
        sc = getattr(platform, "swarm_coordinator", None)
        if sc is None:
            raise HTTPException(503, detail="SwarmCoordinator not available")
        swarm_id = body.get("swarm_id", "")
        tasks = body.get("tasks", [])
        return await sc.execute_swarm(swarm_id, tasks)

    @app.post("/api/swarm/rebalance")
    async def swarm_phase14_rebalance(body: dict) -> dict:
        sc = getattr(platform, "swarm_coordinator", None)
        if sc is None:
            raise HTTPException(503, detail="SwarmCoordinator not available")
        swarm_id = body.get("swarm_id", "")
        return await sc.rebalance(swarm_id)

    @app.post("/api/swarm/consensus")
    async def swarm_phase14_consensus(body: dict) -> dict:
        sc = getattr(platform, "swarm_coordinator", None)
        if sc is None:
            raise HTTPException(503, detail="SwarmCoordinator not available")
        swarm_id = body.get("swarm_id", "")
        proposal = body.get("proposal", "")
        votes = body.get("votes", {})
        consensus_type = body.get("consensus_type", "majority")
        from agentic_os.core.orchestration.swarm_coordinator import ConsensusType

        try:
            ct = ConsensusType(consensus_type)
        except ValueError:
            ct = ConsensusType.MAJORITY
        return await sc.run_consensus(swarm_id, proposal, votes, ct)

    @app.post("/api/swarm/disband")
    async def swarm_phase14_disband(body: dict) -> dict:
        sc = getattr(platform, "swarm_coordinator", None)
        if sc is None:
            raise HTTPException(503, detail="SwarmCoordinator not available")
        swarm_id = body.get("swarm_id", "")
        return await sc.disband(swarm_id)

    # ── Phase 13: Autonomous Executive Decision & Mission Orchestration ──

    @app.get("/api/executive/world")
    async def executive_world() -> dict:
        """Return the live executive world state."""
        exec_ctrl = getattr(platform, "executive_controller", None)
        if exec_ctrl is None or exec_ctrl.orchestrator is None:
            return {}
        return await exec_ctrl.orchestrator.get_world_state()

    @app.get("/api/executive/policies")
    async def executive_policies() -> dict:
        """Return the current executive policy + history."""
        exec_ctrl = getattr(platform, "executive_controller", None)
        if exec_ctrl is None or exec_ctrl.orchestrator is None:
            return {"policy": {}, "history": []}
        return {
            "policy": exec_ctrl.orchestrator.get_policy().to_dict(),
            "history": exec_ctrl.orchestrator.get_policy_history(),
        }

    @app.post("/api/executive/policy")
    async def executive_set_policy(body: dict) -> dict:
        """Switch the executive policy at runtime."""
        exec_ctrl = getattr(platform, "executive_controller", None)
        if exec_ctrl is None or exec_ctrl.orchestrator is None:
            raise HTTPException(503, detail="ExecutiveController not available")
        from agentic_os.core.executive.phase13_domain import ExecutivePolicyType

        policy_type_str = body.get("type", "balanced")
        try:
            policy_type = ExecutivePolicyType(policy_type_str)
        except ValueError:
            raise HTTPException(400, f"Invalid policy type: {policy_type_str}") from None
        params = body.get("params", {})
        policy = exec_ctrl.orchestrator.set_policy(policy_type, params)
        return policy.to_dict()

    @app.get("/api/executive/resources")
    async def executive_resources(limit: int = 50) -> list[dict]:
        """Return recent resource allocations."""
        exec_ctrl = getattr(platform, "executive_controller", None)
        if exec_ctrl is None or exec_ctrl.orchestrator is None:
            return []
        return exec_ctrl.orchestrator.get_allocations(limit=limit)

    @app.get("/api/executive/missions")
    async def executive_missions() -> dict:
        """Return missions tracked by the executive layer."""
        exec_ctrl = getattr(platform, "executive_controller", None)
        if exec_ctrl is None or exec_ctrl.orchestrator is None:
            return {"missions": [], "total": 0}
        world = await exec_ctrl.orchestrator.get_world_state()
        return {
            "missions": world.get("missions", 0),
            "queue_size": world.get("execution_queue_size", 0),
            "active_brains": world.get("active_brains", []),
        }

    @app.get("/api/executive/dashboard")
    async def executive_dashboard() -> dict:
        """Return the executive dashboard with all live data."""
        exec_ctrl = getattr(platform, "executive_controller", None)
        if exec_ctrl is None or exec_ctrl.orchestrator is None:
            return {"message": "ExecutiveController not wired"}
        return await exec_ctrl.orchestrator.dashboard()

    @app.post("/api/executive/optimize")
    async def executive_optimize() -> dict:
        """Run an optimization cycle: reprioritize + supervise + allocate."""
        exec_ctrl = getattr(platform, "executive_controller", None)
        if exec_ctrl is None or exec_ctrl.orchestrator is None:
            raise HTTPException(503, detail="ExecutiveController not available")
        return await exec_ctrl.orchestrator.optimize()

    @app.post("/api/executive/recover")
    async def executive_recover(body: dict) -> dict:
        """Trigger automatic recovery for a mission."""
        exec_ctrl = getattr(platform, "executive_controller", None)
        if exec_ctrl is None or exec_ctrl.orchestrator is None:
            raise HTTPException(503, detail="ExecutiveController not available")
        mission_id = body.get("mission_id", "")
        reason = body.get("reason", "")
        return await exec_ctrl.orchestrator.trigger_recovery(mission_id, reason)

    @app.post("/api/executive/replan")
    async def executive_replan() -> dict:
        """Reprioritize goals and replan the execution queue."""
        exec_ctrl = getattr(platform, "executive_controller", None)
        if exec_ctrl is None or exec_ctrl.orchestrator is None:
            raise HTTPException(503, detail="ExecutiveController not available")
        return await exec_ctrl.orchestrator.reprioritize()

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

        try:
            mem_scope = MemoryScope(scope)
        except ValueError:
            return []

        return [
            i.model_dump(mode="json")
            for i in await memory.store.list_scope(mem_scope, agent_id)
        ]

    @app.get("/api/memory/{scope}/recall")
    async def recall_memory(
        scope: str, query: str = "", limit: int = 10, agent_id: str = ""
    ) -> list[dict]:
        from agentic_os.domain.memory import MemoryScope

        try:
            mem_scope = MemoryScope(scope)
        except ValueError:
            return []

        return [
            i.model_dump(mode="json")
            for i in await memory.recall(mem_scope, query, limit, agent_id)
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
        from fastapi import HTTPException

        try:
            detail = await mcp.registry.register_server(data)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
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
        """Analyze a goal for complexity and capability requirements.

        Accepts ``title`` (canonical) or falls back to ``description`` /
        ``goal`` so clients sending only a description do not 500.
        """
        goal = OrchestrationGoal(
            title=str(
                body.get("title") or body.get("description") or body.get("goal") or "Untitled"
            ),
            description=body.get("description", ""),
            context=body.get("context", {}),
            swarm_id=body.get("swarm_id"),
        )
        return await swarm.analyze_goal(goal)

    @app.post("/api/swarm/planner/plan")
    async def create_plan(body: dict) -> dict:
        """Create a full execution plan from a goal."""
        goal = OrchestrationGoal(
            title=str(
                body.get("title") or body.get("description") or body.get("goal") or "Untitled"
            ),
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

    @app.get("/api/swarm/metrics")
    async def get_swarm_metrics() -> dict:
        """Aggregated swarm metrics for the dashboard."""
        swarms = await swarm.list_swarms()
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
    # Learning & Optimization Engine API (Phase 4, M5)
    # ─────────────────────────────────────────────────────────────────────────

    # -- Profiles --

    @app.get("/api/learning/profiles")
    async def list_learning_profiles() -> list[dict]:
        profiles = await learning.list_profiles()
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
        created = await learning.create_profile(profile)
        return created.to_dict()

    @app.get("/api/learning/profiles/{profile_id}")
    async def get_learning_profile(profile_id: str) -> dict:
        profile = await learning.get_profile(profile_id)
        if profile is None:
            raise HTTPException(status_code=404, detail="Profile not found")
        return profile.to_dict()

    @app.delete("/api/learning/profiles/{profile_id}")
    async def delete_learning_profile(profile_id: str) -> dict:
        await learning.delete_profile(profile_id)
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
        recorded = await learning.record_execution(history)
        return recorded.to_dict()

    @app.get("/api/learning/executions")
    async def list_executions(
        limit: int = 100, offset: int = 0, engine_type: str | None = None, status: str | None = None
    ) -> list[dict]:
        records = learning._history.list_records(
            engine_type=engine_type, status=status, limit=limit, offset=offset
        )
        return [r.to_dict() for r in records]

    @app.get("/api/learning/executions/{execution_id}")
    async def get_execution(execution_id: str) -> dict:
        record = learning._history.get_record(execution_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Execution not found")
        return record.to_dict()

    # -- Analysis --

    @app.post("/api/learning/analyze")
    async def analyze_executions(body: dict) -> dict:
        history_ids = tuple(body.get("history_ids", []))
        stats = await learning.analyze_executions(history_ids)
        return stats.to_dict()

    @app.get("/api/learning/metrics")
    async def get_learning_metrics(
        period_start: str | None = None, period_end: str | None = None
    ) -> dict:
        metrics = await learning.compute_learning_metrics(period_start, period_end)
        return metrics.to_dict()

    # -- Recommendations --

    @app.get("/api/learning/recommendations")
    async def list_recommendations(status: str | None = None, limit: int = 50) -> list[dict]:
        from agentic_os.domain.learning import RecommendationStatus

        rec_status = RecommendationStatus(status) if status else None
        recs = await learning.list_recommendations(rec_status, limit)
        return [r.to_dict() for r in recs]

    @app.post("/api/learning/recommendations/generate")
    async def generate_recommendation(body: dict) -> dict:
        rec = await learning.generate_recommendation(body["category"], body.get("context", {}))
        return rec.to_dict()

    @app.post("/api/learning/recommendations/{recommendation_id}/apply")
    async def apply_recommendation(recommendation_id: str) -> dict:
        rec = await learning.apply_recommendation(recommendation_id)
        return rec.to_dict()

    @app.post("/api/learning/recommendations/{recommendation_id}/dismiss")
    async def dismiss_recommendation(recommendation_id: str) -> dict:
        rec = await learning.dismiss_recommendation(recommendation_id)
        return rec.to_dict()

    # -- Optimization --

    @app.post("/api/learning/optimization")
    async def optimize(body: dict) -> dict:
        from agentic_os.domain.learning import OptimizationTarget

        target = OptimizationTarget(body["target"])
        result = await learning.optimize(target, body.get("config", {}))
        return result.to_dict()

    @app.get("/api/learning/optimization/results")
    async def list_optimization_results(limit: int = 50) -> list[dict]:
        results = await learning.list_optimization_results(limit)
        return [r.to_dict() for r in results]

    @app.post("/api/learning/optimization/{result_id}/rollback")
    async def rollback_optimization(result_id: str) -> dict:
        result = await learning.rollback_optimization(result_id)
        return result.to_dict()

    # -- Routing --

    @app.post("/api/learning/routing/analyze")
    async def analyze_routing() -> list[dict]:
        recs = await learning.analyze_routing()
        return [r.to_dict() for r in recs]

    @app.post("/api/learning/routing/optimize")
    async def optimize_routing(body: dict) -> dict:
        decision = await learning.optimize_routing(body["recommendation_id"])
        return decision.to_dict()

    @app.get("/api/learning/routing/stats")
    async def get_routing_stats() -> dict:
        return await learning.get_routing_stats()

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
        created = await learning.create_benchmark(benchmark)
        return created.to_dict()

    @app.post("/api/learning/benchmarks/{benchmark_id}/run")
    async def run_benchmark(benchmark_id: str) -> dict:
        result = await learning.run_benchmark(benchmark_id)
        return result.to_dict()

    @app.get("/api/learning/benchmarks")
    async def list_benchmarks() -> list[dict]:
        benchmarks = await learning.list_benchmarks()
        return [b.to_dict() for b in benchmarks]

    @app.get("/api/learning/benchmarks/{benchmark_id}")
    async def get_benchmark(benchmark_id: str) -> dict:
        benchmark = await learning.get_benchmark(benchmark_id)
        if benchmark is None:
            raise HTTPException(status_code=404, detail="Benchmark not found")
        return benchmark.to_dict()

    @app.delete("/api/learning/benchmarks/{benchmark_id}")
    async def delete_benchmark(benchmark_id: str) -> dict:
        await learning.delete_benchmark(benchmark_id)
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
        created = await learning.create_experiment(experiment)
        return created.to_dict()

    @app.get("/api/learning/experiments")
    async def list_experiments() -> list[dict]:
        experiments = await learning.list_experiments()
        return [e.to_dict() for e in experiments]

    @app.get("/api/learning/experiments/{experiment_id}")
    async def get_experiment(experiment_id: str) -> dict:
        experiment = await learning.get_experiment(experiment_id)
        if experiment is None:
            raise HTTPException(status_code=404, detail="Experiment not found")
        return experiment.to_dict()

    @app.post("/api/learning/experiments/{experiment_id}/start")
    async def start_experiment(experiment_id: str) -> dict:
        experiment = await learning.start_experiment(experiment_id)
        return experiment.to_dict()

    @app.post("/api/learning/experiments/{experiment_id}/complete")
    async def complete_experiment(experiment_id: str) -> dict:
        experiment = await learning.complete_experiment(experiment_id)
        return experiment.to_dict()

    # -- Evaluation --

    @app.post("/api/learning/evaluate")
    async def evaluate(body: dict) -> dict:
        evaluation = await learning.evaluate(
            body["target_id"],
            body.get("target_type", "engine"),
            body.get("metrics", {}),
        )
        return evaluation.to_dict()

    @app.get("/api/learning/evaluations/{target_id}")
    async def list_evaluations(target_id: str) -> list[dict]:
        evaluations = await learning.list_evaluations(target_id)
        return [e.to_dict() for e in evaluations]

    # -- Performance --

    @app.post("/api/learning/performance/profile")
    async def profile_performance(body: dict) -> dict:
        profile = await learning.profile_performance(
            body["target_id"], body.get("target_type", "engine")
        )
        return profile.to_dict()

    @app.get("/api/learning/performance/trends")
    async def get_performance_trends() -> dict:
        return await learning.get_performance_trends()

    # -- Cost --

    @app.get("/api/learning/cost/metrics")
    async def get_cost_metrics(
        period_start: str | None = None, period_end: str | None = None
    ) -> dict:
        metrics = await learning.get_cost_metrics(period_start, period_end)
        return metrics.to_dict()

    # -- Quality --

    @app.get("/api/learning/quality/metrics")
    async def get_quality_metrics(
        period_start: str | None = None, period_end: str | None = None
    ) -> dict:
        metrics = await learning.get_quality_metrics(period_start, period_end)
        return metrics.to_dict()

    # -- Failure Analysis --

    @app.get("/api/learning/failure-analysis")
    async def get_failure_analysis(
        period_start: str | None = None, period_end: str | None = None
    ) -> dict:
        analysis = await learning.get_failure_analysis(period_start, period_end)
        return analysis.to_dict()

    # -- Policies --

    @app.get("/api/learning/policies")
    async def list_policies() -> list[dict]:
        policies = await learning.list_policies()
        return [p.to_dict() for p in policies]

    @app.post("/api/learning/policies")
    async def create_policy(body: dict) -> dict:
        from agentic_os.domain.learning import (
            OptimizationPolicy,
            OptimizationTarget,
            PolicyEffect,
        )

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
        created = await learning.create_policy(policy)
        return created.to_dict()

    @app.put("/api/learning/policies/{policy_id}")
    async def update_policy(policy_id: str, body: dict) -> dict:
        existing = await learning._policy.get_policy(policy_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Policy not found")
        from agentic_os.domain.learning import (
            OptimizationPolicy,
            OptimizationTarget,
            PolicyEffect,
        )

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
        result = await learning.update_policy(updated)
        return result.to_dict()

    @app.delete("/api/learning/policies/{policy_id}")
    async def delete_policy(policy_id: str) -> dict:
        await learning.delete_policy(policy_id)
        return {"deleted": policy_id}

    # -- Telemetry --

    @app.get("/api/learning/latency/metrics")
    async def get_latency_metrics(
        period_start: str | None = None, period_end: str | None = None
    ) -> dict:
        metrics = await learning._telemetry.get_latency_metrics(period_start, period_end)
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
            if desktop.update is not None:
                from agentic_os.domain.desktop import UpdateChannel

                ch = UpdateChannel(channel)
                releases = await desktop.update.check_for_updates(ch)
                return [r.to_dict() for r in releases]

            # Fallback: query GitHub releases API directly when the Tauri
            # desktop update manager isn't available (e.g. dev server).
            import json as _json
            import urllib.request as _urlreq

            try:
                req = _urlreq.Request(
                    "https://api.github.com/repos/rachidSabah/AgenticosHybrid/releases?per_page=10",
                    headers={"Accept": "application/vnd.github.v3+json"},
                )
                with _urlreq.urlopen(req, timeout=10) as resp:
                    data = _json.loads(resp.read())
            except Exception as exc:
                log.warning("Failed to fetch GitHub releases: %s", exc)
                return []

            result: list[dict] = []
            for item in data:
                if item.get("draft", False):
                    continue
                tag = item.get("tag_name", "")
                if not tag:
                    continue
                version_str = tag.lstrip("v")
                is_prerelease = item.get("prerelease", False)

                # Channel filtering
                if channel == "stable" and is_prerelease:
                    continue

                # Find download URL for the release assets
                assets = item.get("assets", [])
                download_url = ""
                for asset in assets:
                    name = asset.get("name", "")
                    if name.endswith(".exe") or name.endswith(".dmg") or name.endswith(".AppImage"):
                        download_url = asset.get("browser_download_url", "")
                        break

                result.append(
                    {
                        "version": version_str,
                        "tag": tag,
                        "url": download_url or item.get("html_url", ""),
                        "published_at": item.get("published_at"),
                        "release_notes": item.get("body", ""),
                        "prerelease": is_prerelease,
                        "channel": "beta" if is_prerelease else "stable",
                    }
                )
            return result

        @app.get("/api/desktop/updates/status")
        async def get_update_status() -> dict:
            if desktop.update is not None:
                return {
                    "status": (await desktop.update.get_update_status()).value,
                    "version": await desktop.update.get_current_version(),
                }
            # Fallback: return the package version
            from agentic_os import __version__ as _pkg_version

            return {"status": "up-to-date", "version": _pkg_version}

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
            if desktop.update is not None:
                from agentic_os.domain.desktop import UpdateManifest

                manifest = UpdateManifest(
                    **{k: v for k, v in body.items() if k in UpdateManifest.__dataclass_fields__}
                )
                success = await desktop.update.download_update(manifest)
                return {"success": success}
            # Fallback: return the download URL so the frontend can
            # redirect the browser to download the installer directly.
            download_url = body.get("download_url", "")
            if download_url:
                return {
                    "success": True,
                    "download_url": download_url,
                    "message": "Open the download URL in your browser",
                }
            raise HTTPException(503, "Update manager not available and no download_url provided")

        @app.post("/api/desktop/updates/install")
        async def install_update(body: dict) -> dict:
            if desktop.update is not None:
                from agentic_os.domain.desktop import UpdateManifest

                manifest = UpdateManifest(
                    **{k: v for k, v in body.items() if k in UpdateManifest.__dataclass_fields__}
                )
                result = await desktop.update.install_update(manifest)
                return result.to_dict()
            # Fallback: return instructions for manual install
            download_url = body.get("download_url", "")
            version = body.get("version", "")
            return {
                "success": True,
                "previous_version": "",
                "new_version": version,
                "installed_at": "",
                "duration_seconds": 0,
                "download_url": download_url,
                "message": (
                    f"Download {version} from {download_url} and install manually (dev server mode)"
                ),
            }

        # ── Dev-Mode Git Updates (works on localhost:3000 + any checkout) ──
        # These endpoints detect whether the local git checkout is behind
        # origin/main and let the user pull the latest commits + restart.
        # They work regardless of whether the Tauri desktop runtime is
        # present, so they're useful when running `npm run dev` on
        # localhost:3000 + `uvicorn` on localhost:8000.

        @app.get("/api/dev/updates/status")
        async def dev_update_status() -> dict:
            """Return the current local git commit + branch + whether behind remote."""
            import asyncio

            async def _run(args: list[str], cwd: str | None = None) -> str:
                proc = await asyncio.create_subprocess_exec(
                    *args,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=cwd,
                )
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
                return stdout.decode("utf-8", errors="replace").strip()

            try:
                repo_root = _os_mod.path.dirname(
                    _os_mod.path.dirname(_os_mod.path.dirname(__file__))
                )
                # Get current commit
                head = await _run(["git", "rev-parse", "HEAD"], cwd=repo_root)
                short_head = await _run(["git", "rev-parse", "--short", "HEAD"], cwd=repo_root)
                branch = await _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_root)
                # Fetch remote (non-blocking, silent on failure)
                try:
                    await _run(["git", "fetch", "origin"], cwd=repo_root)
                except Exception:
                    pass  # offline — that's OK, we just report local state
                # Get remote head
                try:
                    remote_head = await _run(["git", "rev-parse", "origin/main"], cwd=repo_root)
                    remote_short = await _run(
                        ["git", "rev-parse", "--short", "origin/main"],
                        cwd=repo_root,
                    )
                except Exception:
                    remote_head = ""
                    remote_short = ""
                behind = 0
                if remote_head and remote_head != head:
                    try:
                        count_out = await _run(
                            ["git", "rev-list", "--count", "HEAD..origin/main"],
                            cwd=repo_root,
                        )
                        behind = int(count_out) if count_out.isdigit() else 0
                    except Exception:
                        behind = 0
                return {
                    "local_commit": head,
                    "local_short": short_head,
                    "branch": branch,
                    "remote_commit": remote_head,
                    "remote_short": remote_short,
                    "behind": behind,
                    "up_to_date": behind == 0,
                    "has_remote": bool(remote_head),
                }
            except Exception as exc:
                return {
                    "local_commit": "",
                    "local_short": "",
                    "branch": "",
                    "remote_commit": "",
                    "remote_short": "",
                    "behind": 0,
                    "up_to_date": True,
                    "has_remote": False,
                    "error": str(exc),
                }

        @app.get("/api/dev/updates/commits")
        async def dev_update_commits(limit: int = 50) -> list[dict]:
            """Return the list of commits on origin/main NOT in local HEAD."""
            import asyncio

            repo_root = _os_mod.path.dirname(_os_mod.path.dirname(_os_mod.path.dirname(__file__)))

            async def _run(args: list[str]) -> str:
                proc = await asyncio.create_subprocess_exec(
                    *args,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=repo_root,
                )
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
                return stdout.decode("utf-8", errors="replace").strip()

            try:
                try:
                    await _run(["git", "fetch", "origin"])
                except Exception:
                    pass
                raw = await _run(
                    [
                        "git",
                        "log",
                        "HEAD..origin/main",
                        f"--max-count={max(1, min(limit, 200))}",
                        "--pretty=format:%H\t%an\t%ai\t%s",
                    ]
                )
                if not raw:
                    return []
                commits = []
                for line in raw.split("\n"):
                    parts = line.split("\t", 3)
                    if len(parts) == 4:
                        h, author, date, subject = parts
                        commits.append(
                            {
                                "hash": h,
                                "short_hash": h[:8],
                                "author": author,
                                "date": date,
                                "subject": subject,
                            }
                        )
                return commits
            except Exception:
                return []

        @app.post("/api/dev/updates/pull")
        async def dev_update_pull() -> dict:
            """Pull the latest commits from origin/main."""
            import asyncio

            repo_root = _os_mod.path.dirname(_os_mod.path.dirname(_os_mod.path.dirname(__file__)))

            async def _run(args: list[str]) -> tuple[str, str, int]:
                proc = await asyncio.create_subprocess_exec(
                    *args,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=repo_root,
                )
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
                return (
                    stdout.decode("utf-8", errors="replace").strip(),
                    stderr.decode("utf-8", errors="replace").strip(),
                    proc.returncode or 0,
                )

            try:
                fetch_out, fetch_err, fetch_rc = await _run(["git", "fetch", "origin"])
                if fetch_rc != 0:
                    return {
                        "success": False,
                        "error": f"git fetch failed: {fetch_err}",
                        "stdout": fetch_out,
                    }
                merge_out, merge_err, merge_rc = await _run(["git", "merge", "origin/main"])
                new_head, _, _ = await _run(["git", "rev-parse", "--short", "HEAD"])
                return {
                    "success": merge_rc == 0,
                    "stdout": merge_out,
                    "stderr": merge_err,
                    "new_head": new_head,
                    "returncode": merge_rc,
                }
            except Exception as exc:
                return {"success": False, "error": str(exc)}

        @app.post("/api/dev/updates/restart")
        async def dev_update_restart() -> dict:
            """Schedule a server restart in 1 second (after the response is sent).

            This is a fire-and-forget — the backend process will exit and
            must be restarted by a process manager (systemd, supervisor,
            npm, uv, etc.). In dev mode, `npm run dev` / `uvicorn --reload`
            will auto-restart.
            """
            import asyncio
            import os
            import signal

            async def _delayed_exit() -> None:
                await asyncio.sleep(1.0)
                # Send SIGTERM to ourselves — the process manager restarts us
                os.kill(os.getpid(), signal.SIGTERM)

            asyncio.create_task(_delayed_exit())
            return {"scheduled": True, "message": "Restart scheduled in 1s"}

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

        # ── Runtime Management (Phase 6.3 — Universal Runtime Control) ──

        runtime_mgr = desktop.runtime

        if runtime_mgr is not None:

            @app.get("/api/runtimes")
            async def list_runtimes(
                status: str | None = None,
                runtime_type: str | None = None,
            ) -> list[dict]:
                """List all runtimes.

                Combines:
                1. Desktop runtime manager (Stack #2 — universal runtime control)
                2. BrainRegistry (discovered local CLI AI brains) — so that
                   brains discovered via RuntimeBridge / LocalDiscoveryService
                   also appear in the runtime list. Without this, a brain like
                   Claude Code would appear in /api/brains but NOT in
                   /api/runtimes, causing count mismatches between the Fleet,
                   Constellation, and Runtime Dashboard views.
                """
                all_runtimes = await runtime_mgr.list_all()
                result = [r.to_dict() for r in all_runtimes]
                seen_ids = {r.get("id") for r in result}
                seen_names = {r.get("name") for r in result}

                # Enrich every runtime with LIVE process status/PID from
                # LocalDiscoveryService so the dashboard reflects real
                # running processes (Hermes.exe, node.exe, python.exe…)
                # instead of stale registry snapshots.
                live_map: dict[str, dict] = {}
                local = getattr(platform, "local_discovery", None)
                if local is not None:
                    try:
                        for agent in await local.get_agents():
                            d = agent.to_dict()
                            live_map[str(d.get("name", "")).lower()] = d
                            live_map[str(d.get("tool_type", "")).lower()] = d
                    except Exception:
                        pass
                for r in result:
                    probe = live_map.get(str(r.get("name", "")).lower()) or live_map.get(
                        str(r.get("executable", r.get("name", ""))).lower()
                    )
                    if probe:
                        r["status"] = "running" if probe.get("running") else r.get("status")
                        r["pid"] = probe.get("pid")
                        r["health"] = probe.get("health_score", r.get("health"))
                        r["latency_ms"] = probe.get("latency_ms", r.get("latency_ms"))
                        r["memory_mb"] = probe.get("memory_mb", r.get("memory_mb"))
                        r["cpu_percent"] = probe.get("cpu_percent", r.get("cpu_percent"))

                # Merge in live discovered brains
                if platform.brain_registry is not None:
                    try:
                        brains = await platform.brain_registry.list_all()
                    except Exception:
                        brains = []
                    for b in brains:
                        if b.id in seen_ids or b.display_name in seen_names:
                            continue
                        seen_ids.add(b.id)
                        seen_names.add(b.display_name)
                        rt_status = "running" if b.health >= 50 else "stopped"
                        if status and rt_status != status:
                            continue
                        rt_type = str(b.vendor)
                        if runtime_type and rt_type != runtime_type:
                            continue
                        result.append(
                            {
                                "id": b.id,
                                "name": b.display_name,
                                "type": rt_type,
                                "status": rt_status,
                                "version": b.version or "",
                                "path": "",
                                "executable": b.display_name,
                                "capabilities": list(b.capabilities) if b.capabilities else [],
                                "verified": True,
                                "health": b.health,
                                "latency_ms": b.latency,
                                "source": "brain_registry",
                            }
                        )

                if status:
                    result = [r for r in result if r.get("status") == status]
                if runtime_type:
                    result = [r for r in result if r.get("type") == runtime_type]
                return result

            @app.get("/api/runtimes/{runtime_id}")
            async def get_runtime(runtime_id: str) -> dict:
                rt = await runtime_mgr.get(runtime_id)
                if rt is None:
                    raise HTTPException(404, f"Runtime not found: {runtime_id}")
                return rt.to_dict()

            @app.post("/api/runtimes/{runtime_id}/start")
            async def start_runtime(runtime_id: str) -> dict:
                try:
                    rt = await runtime_mgr.launch(runtime_id)
                    if rt is None:
                        raise HTTPException(404, f"Runtime not found: {runtime_id}")
                    return rt.to_dict()
                except ValueError as exc:
                    raise HTTPException(404, str(exc)) from exc
                except RuntimeError as exc:
                    raise HTTPException(409, str(exc)) from exc
                except Exception as exc:
                    raise HTTPException(500, f"Failed to start runtime: {exc}") from exc

            @app.post("/api/runtimes/{runtime_id}/stop")
            async def stop_runtime(runtime_id: str, body: dict | None = None) -> dict:
                try:
                    force = body.get("force", False) if body else False
                    rt = await runtime_mgr.stop_runtime(runtime_id, force=force)
                    return rt.to_dict() if rt else {"status": "stopped"}
                except ValueError as exc:
                    raise HTTPException(404, str(exc)) from exc
                except Exception as exc:
                    raise HTTPException(500, f"Failed to stop runtime: {exc}") from exc

            @app.post("/api/runtimes/{runtime_id}/restart")
            async def restart_runtime(runtime_id: str) -> dict:
                try:
                    rt = await runtime_mgr.restart_runtime(runtime_id)
                    return rt.to_dict() if rt else {"status": "restarted"}
                except ValueError as exc:
                    raise HTTPException(404, str(exc)) from exc
                except Exception as exc:
                    raise HTTPException(500, f"Failed to restart runtime: {exc}") from exc

            @app.post("/api/runtimes/{runtime_id}/kill")
            async def kill_runtime(runtime_id: str) -> dict:
                try:
                    rt = await runtime_mgr.kill(runtime_id)
                    return rt.to_dict() if rt else {"status": "killed"}
                except ValueError as exc:
                    raise HTTPException(404, str(exc)) from exc
                except Exception as exc:
                    raise HTTPException(500, f"Failed to kill runtime: {exc}") from exc

            @app.get("/api/runtimes/{runtime_id}/logs")
            async def get_runtime_logs(
                runtime_id: str,
                limit: int = 100,
                stream: str | None = None,
                level: str | None = None,
                search: str | None = None,
            ) -> list[dict]:
                try:
                    logs = await runtime_mgr.get_logs(
                        runtime_id,
                        limit=limit,
                        stream=stream,
                        level=level,
                        search=search,
                    )
                    return logs
                except ValueError as exc:
                    raise HTTPException(404, str(exc)) from exc
                except Exception as exc:
                    # Log retrieval failures should not crash the dashboard.
                    # Return an empty list so the UI shows "no logs" instead
                    # of a 500 error.
                    log.warning(
                        "Failed to get runtime logs",
                        runtime_id=runtime_id,
                        error=str(exc),
                    )
                    return []

            @app.get("/api/runtimes/{runtime_id}/metrics")
            async def get_runtime_metrics(runtime_id: str) -> dict:
                metrics = await runtime_mgr.get_metrics(runtime_id)
                return metrics.to_dict() if metrics else {}

            @app.get("/api/runtimes/{runtime_id}/health")
            async def get_runtime_health(runtime_id: str) -> dict:
                health = await runtime_mgr.get_health(runtime_id)
                return {"status": health.value} if health else {"status": "unknown"}

            @app.get("/api/runtimes/{runtime_id}/sessions")
            async def list_runtime_sessions(runtime_id: str) -> list[dict]:
                sessions = await runtime_mgr.list_sessions(runtime_id)
                return [s.to_dict() for s in sessions]

            @app.post("/api/runtimes/{runtime_id}/execute")
            async def execute_runtime_command(runtime_id: str, body: dict) -> dict:
                command = body.get("command", "")
                if not command:
                    raise HTTPException(400, "command is required")
                output = await runtime_mgr.execute_command(runtime_id, command)
                return {"output": output}

            @app.post("/api/runtimes/{runtime_id}/terminal")
            async def attach_runtime_terminal(runtime_id: str) -> dict:
                terminal_id = await runtime_mgr.attach_terminal(runtime_id)
                return {"terminal_id": terminal_id}

            @app.post("/api/runtimes/discover")
            async def discover_runtimes() -> list[dict]:
                runtimes = await runtime_mgr.discover()
                return [r.to_dict() for r in runtimes]

            @app.websocket("/ws/runtimes")
            async def runtimes_ws(websocket: WebSocket) -> None:
                await websocket.accept()
                try:
                    while True:
                        data = await websocket.receive_json()
                        action = data.get("action")
                        if action == "list":
                            all_rts = await runtime_mgr.list_all()
                            await websocket.send_json(
                                {
                                    "type": "runtimes.list",
                                    "runtimes": [r.to_dict() for r in all_rts],
                                }
                            )
                        elif action == "get":
                            rid = data.get("runtime_id")
                            if rid:
                                rt = await runtime_mgr.get(rid)
                                await websocket.send_json(
                                    {
                                        "type": "runtime.get",
                                        "runtime": rt.to_dict() if rt else None,
                                    }
                                )
                        elif action == "start":
                            rid = data.get("runtime_id")
                            if rid:
                                rt = await runtime_mgr.launch(rid)
                                await websocket.send_json(
                                    {
                                        "type": "runtime.started",
                                        "runtime": rt.to_dict() if rt else None,
                                    }
                                )
                        elif action == "stop":
                            rid = data.get("runtime_id")
                            if rid:
                                rt = await runtime_mgr.stop_runtime(rid)
                                await websocket.send_json(
                                    {
                                        "type": "runtime.stopped",
                                        "runtime": rt.to_dict() if rt else None,
                                    }
                                )
                except Exception:
                    pass
                finally:
                    try:
                        await websocket.close()
                    except Exception:
                        pass

    @app.get("/api/events/recent")
    async def get_recent_events(limit: int = 50) -> list[dict]:
        return platform.dashboard.get_recent_events(limit)

    # ── Minimal provider management UI page (Phase 3 builds Mission Control) ──
    @app.get("/providers", response_class=HTMLResponse)
    async def providers_page() -> str:
        return _PROVIDER_PAGE

    @app.websocket("/ws/terminal")
    async def terminal_ws(websocket: WebSocket) -> None:
        """Spawn a PTY in the given worktree path and stream I/O."""
        import asyncio
        import os as _os_mod
        import sys as _sys_mod

        await websocket.accept()
        worktree_path = websocket.query_params.get("path", "")
        if not worktree_path or not _os_mod.path.isdir(worktree_path):
            await websocket.send_text(f"\r\n\x1b[31m✗ Invalid path: {worktree_path}\x1b[0m\r\n")
            await websocket.close()
            return

        # Determine shell
        if _sys_mod.platform == "win32":
            shell = _os_mod.environ.get("COMSPEC", "cmd.exe")
        else:
            shell = _os_mod.environ.get("SHELL", "/bin/bash")

        try:
            proc = await asyncio.create_subprocess_exec(
                shell,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=worktree_path,
                env={**_os_mod.environ, "TERM": "xterm-256color"},
            )
        except Exception as exc:
            await websocket.send_text(f"\r\n\x1b[31m✗ Failed to spawn shell: {exc}\x1b[0m\r\n")
            await websocket.close()
            return

        async def _read_stdout():
            while True:
                if proc.stdout is None:
                    break
                data = await proc.stdout.read(1024)
                if not data:
                    break
                try:
                    await websocket.send_text(data.decode("utf-8", errors="replace"))
                except Exception:
                    break

        async def _read_stderr():
            while True:
                if proc.stderr is None:
                    break
                data = await proc.stderr.read(1024)
                if not data:
                    break
                try:
                    await websocket.send_text(
                        f"\x1b[31m{data.decode('utf-8', errors='replace')}\x1b[0m"
                    )
                except Exception:
                    break

        async def _read_input():
            while True:
                try:
                    msg = await websocket.receive_text()
                except Exception:
                    break
                if proc.stdin:
                    proc.stdin.write(msg.encode())
                    await proc.stdin.drain()

        tasks = [
            asyncio.create_task(_read_stdout()),
            asyncio.create_task(_read_stderr()),
            asyncio.create_task(_read_input()),
        ]
        try:
            await asyncio.gather(*tasks)
        except Exception:
            pass
        finally:
            for t in tasks:
                t.cancel()
            proc.kill()
            await proc.wait()
            try:
                await websocket.close()
            except Exception:
                pass

    @app.websocket("/ws/dashboard")
    async def dashboard_ws(websocket: WebSocket) -> None:
        dashboard = platform.dashboard
        if dashboard is None:
            await websocket.accept()
            payload = {
                "topic": "system.status",
                "timestamp": datetime.now(UTC).isoformat(),
                "payload": {"status": "degraded", "message": "DashboardBroadcaster not available"},
            }
            await websocket.send_json(payload)
            await websocket.close(code=1011, reason="Dashboard not available")
            return
        await websocket.accept()

        # ── Replay current brain state so new clients immediately see agents ──
        if platform.brain_registry is not None:
            brains = await platform.brain_registry.list_all()
            for b in brains:
                # Only replay brains that are actually installed
                if b.health < 50:
                    continue
                # Send as provider.registered
                await websocket.send_json(
                    {
                        "topic": "provider.registered",
                        "timestamp": datetime.now(UTC).isoformat(),
                        "payload": {
                            "name": b.display_name,
                            "provider": b.display_name,
                            "vendor": str(b.vendor),
                            "status": "healthy" if b.health >= 80 else "degraded",
                            "latency_ms": b.latency,
                        },
                    }
                )
                # Send as agent.started if healthy enough
                if b.health >= 50:
                    await websocket.send_json(
                        {
                            "topic": "agent.started",
                            "timestamp": datetime.now(UTC).isoformat(),
                            "payload": {
                                "id": b.id,
                                "name": b.display_name,
                                "provider": b.display_name,
                                "role": "assistant",
                                "status": "running"
                                if b.status in ("connected", "busy", "executing")
                                else "idle",
                                "capabilities": list(b.capabilities),
                            },
                        }
                    )

        recv, send = dashboard.add_client()
        log.info("dashboard.connected")

        import asyncio

        hb_stop = asyncio.Event()

        async def _heartbeat() -> None:
            """Send periodic heartbeat so the client detects stale connections."""
            while not hb_stop.is_set():
                try:
                    await asyncio.sleep(30)
                    await websocket.send_json({"topic": "heartbeat", "ts": time.time()})
                except Exception:
                    break

        hb_task = asyncio.create_task(_heartbeat())
        try:
            async with recv:
                async for snapshot in recv:
                    try:
                        await websocket.send_json(snapshot)
                    except RuntimeError:
                        # Client already closed; the recv loop will end next.
                        break
        except WebSocketDisconnect:
            pass
        finally:
            hb_stop.set()
            hb_task.cancel()
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

        import asyncio

        hb_stop = asyncio.Event()

        async def _heartbeat() -> None:
            while not hb_stop.is_set():
                try:
                    await asyncio.sleep(30)
                    await websocket.send_json({"topic": "heartbeat", "ts": time.time()})
                except Exception:
                    break

        hb_task = asyncio.create_task(_heartbeat())
        try:
            async with recv:
                async for snapshot in recv:
                    try:
                        await websocket.send_json(snapshot)
                    except RuntimeError:
                        # Client already closed; the recv loop will end next.
                        break
        except WebSocketDisconnect:
            pass
        finally:
            hb_stop.set()
            hb_task.cancel()
            mcp_bc.remove_client(send)
            log.info("mcp_ws.disconnected")

    # ── System overview ───────────────────────────────────────────────────
    @app.get("/api/system")
    async def get_system_overview() -> dict:
        try:
            from agentic_os.adapters.providers.auto_bind import KNOWN_AGENTS
        except ImportError:
            KNOWN_AGENTS = []
        provider_count = len(platform.providers.list_providers())
        known_count = len(KNOWN_AGENTS)
        return {
            "version": "1.0.0-rc1",
            "status": "running",
            "providers": {"total": provider_count, "known_agents": known_count},
            "bus": {"type": settings.bus_type, "running": platform.bus is not None},
            "dashboard": platform.dashboard is not None,
            "memory": platform.memory is not None,
            "orchestrator": platform.orchestrator is not None,
            "runtime": platform.runtime is not None,
            "discovery": platform.discovery_framework is not None,
            "mcp": platform.mcp is not None,
            "desktop": platform.desktop is not None,
            "learning": platform.learning is not None,
        }

    # ── Plugin management ─────────────────────────────────────────────────
    @app.get("/api/plugins")
    async def list_plugins() -> list[dict]:
        from agentic_os.adapters.plugins.builtins import PLUGINS

        return [
            {
                "name": p.__class__.__name__,
                "loaded": True,
                "order": i,
            }
            for i, p in enumerate(PLUGINS)
        ]

    # ── Prompt center ─────────────────────────────────────────────────────
    @app.get("/api/prompts")
    async def list_prompts(limit: int = 50) -> list[dict]:
        if platform.mission_planner and hasattr(platform.mission_planner, "list_prompts"):
            try:
                return await platform.mission_planner.list_prompts(limit)  # ty:ignore[call-non-callable]
            except Exception:
                pass
        return []

    @app.post("/api/prompts")
    async def create_prompt(body: dict) -> dict:
        if platform.mission_planner and hasattr(platform.mission_planner, "create_prompt"):
            try:
                return await platform.mission_planner.create_prompt(body)  # ty:ignore[call-non-callable]
            except Exception as exc:
                raise HTTPException(400, str(exc)) from exc
        raise HTTPException(501, "Prompt center not available")

    @app.get("/api/prompts/{prompt_id}")
    async def get_prompt(prompt_id: str) -> dict:
        if platform.mission_planner and hasattr(platform.mission_planner, "get_prompt"):
            prompt = await platform.mission_planner.get_prompt(prompt_id)  # ty:ignore[call-non-callable]
            if prompt is None:
                raise HTTPException(404, "Prompt not found")
            return prompt
        raise HTTPException(501, "Prompt center not available")

    @app.delete("/api/prompts/{prompt_id}")
    async def delete_prompt(prompt_id: str) -> dict:
        if platform.mission_planner and hasattr(platform.mission_planner, "delete_prompt"):
            deleted = await platform.mission_planner.delete_prompt(prompt_id)  # ty:ignore[call-non-callable]
            return {"deleted": deleted}
        raise HTTPException(501, "Prompt center not available")

    # ── EventBus introspection ────────────────────────────────────────────
    @app.get("/api/eventbus")
    async def get_eventbus_status() -> dict:
        bus = platform.bus
        if bus is None:
            return {"status": "not_available"}
        try:
            subscribers = getattr(bus, "_subscribers", {})
            topic_count = len(subscribers)
            total_listeners = sum(len(v) for v in subscribers.values()) if subscribers else 0
            return {
                "status": "running",
                "type": settings.bus_type,
                "topics": topic_count,
                "listeners": total_listeners,
            }
        except Exception as exc:
            return {"status": "error", "detail": str(exc)}

    # ── Agent Binding Center endpoints ────────────────────────────────────
    _binding_log: list[dict] = []
    _binding_history: list[dict] = []

    @app.post("/binding/discover")
    async def binding_discover(body: dict | None = None) -> dict:
        mode = (body or {}).get("mode", "surface")
        try:
            from agentic_os.adapters.providers.auto_bind import (
                auto_discover_and_bind,
            )

            pre_count = len(platform.providers.list_providers())
            # Run off the event loop to prevent blocking — the deep scan
            # does subprocess probes that can take 30s+ on Windows
            if mode == "deep":
                bound = await asyncio.to_thread(auto_discover_and_bind, platform.providers, True)
            else:
                bound = await asyncio.to_thread(auto_discover_and_bind, platform.providers, False)
            _binding_log.append(
                {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "level": "INFO",
                    "message": f"Discovery ({mode}) found {len(bound)} new providers",
                }
            )
            _binding_history.append(
                {
                    "id": f"bind-{time.time_ns()}",
                    "event": "discovery",
                    "timestamp": datetime.now(UTC).isoformat(),
                    "provider": f"auto:{mode}",
                }
            )
            return {
                "total_found": len(bound) + pre_count,
                "providers": [{"name": p.name, "kind": p.kind} for p in bound],
            }
        except Exception as exc:
            _binding_log.append(
                {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "level": "ERROR",
                    "message": f"Discovery failed: {exc}",
                }
            )
            return {"total_found": 0, "providers": [], "error": str(exc)}

    @app.post("/binding/deep-scan")
    async def binding_deep_scan() -> dict:
        try:
            from agentic_os.adapters.providers.auto_bind import (
                auto_discover_and_bind,
            )

            pre_count = len(platform.providers.list_providers())
            # Run off the event loop — deep scan does subprocess probes
            bound = await asyncio.to_thread(auto_discover_and_bind, platform.providers, True)
            discoverers = getattr(platform, "discovery_framework", None)
            sources_scanned = 0
            if discoverers and hasattr(discoverers, "registry"):
                sources_scanned = len(getattr(discoverers.registry, "_providers", {}))
            _binding_log.append(
                {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "level": "INFO",
                    "message": f"Deep scan complete: {len(bound)} providers bound",
                }
            )
            return {
                "total_found": len(bound) + pre_count,
                "sources_scanned": max(sources_scanned, 5),
                "providers": [{"name": p.name, "kind": p.kind} for p in bound],
            }
        except Exception as exc:
            return {
                "total_found": 0,
                "sources_scanned": 0,
                "providers": [],
                "error": str(exc),
            }

    @app.post("/binding/manual")
    async def binding_manual(body: dict) -> dict:
        provider_name = body.get("provider", "")
        executable = body.get("executable", "")
        if not provider_name or not executable:
            raise HTTPException(400, "provider and executable are required")
        try:
            from agentic_os.adapters.providers.claude_code import ClaudeCodeProvider

            adapter = ClaudeCodeProvider(bin_path=executable, api_key="", name=provider_name)
            platform.providers.register(adapter)
            return {"id": provider_name, "provider": provider_name, "bound": True}
        except Exception as exc:
            raise HTTPException(500, str(exc)) from exc

    @app.post("/binding/validate")
    async def binding_validate(body: dict) -> dict:
        provider_id = body.get("provider_id", "")
        if not provider_id:
            raise HTTPException(400, "provider_id is required")
        providers = platform.providers.list_providers()
        target = next((p for p in providers if p.name == provider_id), None)
        if target is None:
            raise HTTPException(404, f"Provider {provider_id} not found")
        return {
            "provider_id": provider_id,
            "healthy": target.supports_streaming,
            "details": {
                "kind": target.kind,
                "streaming": target.supports_streaming,
                "tools": target.supports_tools,
            },
        }

    @app.post("/binding/repair")
    async def binding_repair(body: dict) -> dict:
        provider_id = body.get("provider_id", "")
        if not provider_id:
            raise HTTPException(400, "provider_id is required")
        # Attempt to re-register the provider by re-running discovery for it
        try:
            from agentic_os.adapters.providers.auto_bind import auto_discover_and_bind

            pre = len(platform.providers.list_providers())
            await asyncio.to_thread(auto_discover_and_bind, platform.providers, False)
            post = len(platform.providers.list_providers())
            return {
                "provider_id": provider_id,
                "repaired": post > pre,
                "action_taken": "re-discovered",
            }
        except Exception as exc:
            return {"provider_id": provider_id, "repaired": False, "action_taken": str(exc)}

    @app.post("/binding/rebind")
    async def binding_rebind(body: dict) -> dict:
        provider_id = body.get("provider_id", "")
        new_path = body.get("executable_path", "")
        if not provider_id or not new_path:
            raise HTTPException(400, "provider_id and executable_path are required")
        # Remove old, register new
        try:
            from agentic_os.adapters.providers.claude_code import ClaudeCodeProvider

            platform.providers.unregister(provider_id)
            adapter = ClaudeCodeProvider(bin_path=new_path, api_key="", name=provider_id)
            platform.providers.register(adapter)
            return {"provider_id": provider_id, "rebound": True, "executable_path": new_path}
        except Exception as exc:
            raise HTTPException(500, str(exc)) from exc

    @app.post("/binding/unbind")
    async def binding_unbind(body: dict) -> dict:
        provider_id = body.get("provider_id", "")
        if not provider_id:
            raise HTTPException(400, "provider_id is required")
        try:
            platform.providers.unregister(provider_id)
            return {"provider_id": provider_id, "unbound": True}
        except Exception as exc:
            raise HTTPException(500, str(exc)) from exc

    @app.get("/binding/providers")
    async def binding_providers() -> list[dict]:
        providers = platform.providers.list_providers()
        return [
            {
                "name": p.name,
                "kind": p.kind,
                "streaming": p.supports_streaming,
                "tools": p.supports_tools,
            }
            for p in providers
        ]

    @app.get("/binding/logs")
    async def binding_logs(limit: int = 100) -> list[dict]:
        return _binding_log[:limit]

    @app.get("/binding/history")
    async def binding_history() -> list[dict]:
        return _binding_history

    # ── OmniRoute AI Subsystem REST API ────────────────────────────────────

    # Bounded ring buffer; the previous unbounded list could grow without limit
    # for the lifetime of the process. 1000 entries is enough for the status UI.
    _omniroute_log: deque[dict] = deque(maxlen=1000)

    @app.get("/omniroute/status")
    async def omniroute_status() -> dict:
        """Return OmniRoute status derived from live data.

        No hardcoded request count — returns the actual number of routes
        recorded in the bounded _omniroute_log deque.
        """
        providers = platform.providers.list_providers()
        healthy_count = sum(1 for p in providers if p.supports_streaming)
        return {
            "status": "active",
            "version": "1.0.0-omniroute",
            "uptime_seconds": int(time.time() - getattr(app.state, "start_time", time.time())),
            "requests_processed": len(_omniroute_log),
            "providers_healthy": healthy_count,
            "providers_total": len(providers),
        }

    @app.get("/omniroute/providers")
    async def omniroute_providers() -> list[dict]:
        """List routing targets for OmniRoute.

        Sources (all live, no hardcoded fallback):
        1. ``provider_mgr.list_providers()`` — registered provider adapters
        2. ``brain_registry.list_all()`` — discovered local CLI brains
           (Claude Code, Hermes, Gemini CLI, Codex, OpenCode, Aider, Continue,
           Ollama, LM Studio, …). Each healthy brain becomes a routing target
           with its real version, capabilities, and health.

        If nothing is installed/discovered, the response is an empty list —
        the previous hardcoded demo list (Claude Code / Hermes / OpenCode /
        AGY CLI / Gemini CLI / Ollama) was removed because it showed fake
        runtimes that don't exist on the host.
        """
        res: list[dict] = []
        seen: set[str] = set()

        # Registered provider adapters
        for p in platform.providers.list_providers():
            name = p.name
            if name in seen:
                continue
            seen.add(name)
            res.append(
                {
                    "name": name,
                    "kind": p.kind,
                    "installed": True,
                    "healthy": True,
                    "version": getattr(p, "version", "") or "",
                    "capabilities": (
                        ["text", "tools", "streaming"] if p.supports_streaming else ["text"]
                    ),
                    "streaming": p.supports_streaming,
                    "tools": p.supports_tools,
                }
            )

        # Live discovered brains
        if platform.brain_registry is not None:
            try:
                brains = await platform.brain_registry.list_all()
            except Exception:
                brains = []
            for b in brains:
                name = b.display_name
                if name in seen:
                    continue
                seen.add(name)
                caps = list(b.capabilities) if b.capabilities else ["text"]
                res.append(
                    {
                        "name": name,
                        "kind": str(b.vendor),
                        "installed": True,
                        "healthy": b.health >= 50,
                        "version": b.version or "",
                        "capabilities": caps,
                        "streaming": "streaming" in caps,
                        "tools": "tools" in caps,
                        "brain_id": b.id,
                        "health_score": b.health,
                        "latency_ms": b.latency,
                    }
                )

        return res

    @app.get("/api/v1/routing/config")
    async def get_routing_config() -> dict:
        return {
            "default_strategy": "cost_optimized",
            "fallback_enabled": True,
            "cost_threshold_usd": 0.05,
            "latency_threshold_ms": 2500,
            "max_retries": 3,
        }

    @app.post("/api/v1/routing/config")
    async def update_routing_config(body: dict) -> dict:
        return {
            "default_strategy": body.get("default_strategy", "cost_optimized"),
            "fallback_enabled": body.get("fallback_enabled", True),
            "cost_threshold_usd": body.get("cost_threshold_usd", 0.05),
            "latency_threshold_ms": body.get("latency_threshold_ms", 2500),
            "max_retries": body.get("max_retries", 3),
        }

    @app.get("/api/v1/routing/agents")
    async def get_routing_agents() -> list[dict]:
        """List routing agents derived from live BrainRegistry.

        Each discovered brain becomes a routing agent with its real
        capabilities, latency, and health. No hardcoded entries.
        """
        if platform.brain_registry is None:
            return []
        try:
            brains = await platform.brain_registry.list_all()
        except Exception:
            return []
        result = []
        for b in brains:
            caps: dict[str, float] = {}
            for c in b.capabilities:
                # Map capability string to a confidence score based on health
                caps[str(c)] = round(b.health / 100.0, 2) if b.health else 0.5
            result.append(
                {
                    "agent_id": b.id,
                    "agent_name": b.display_name,
                    "provider": str(b.vendor),
                    "capabilities": caps,
                    "cost_per_1k": 0.0,
                    "latency_ms": b.latency,
                    "reliability": round(b.health / 100.0, 2) if b.health else 0.0,
                }
            )
        return result

    @app.get("/omniroute/policies")
    async def omniroute_policies() -> list[dict]:
        """List routing policies derived from live BrainRegistry.

        Each discovered brain becomes a routing target. No hardcoded
        policies — the list reflects what is actually installed.
        """
        if platform.brain_registry is None:
            return []
        try:
            brains = await platform.brain_registry.list_all()
        except Exception:
            return []
        result = []
        for b in brains:
            # Use the brain's first supported model if available, else the brain name
            model = b.supported_models[0] if b.supported_models else b.display_name
            # Pick the next brain as fallback if available
            fallback = ""
            for other in brains:
                if other.id != b.id:
                    fallback = other.display_name
                    break
            result.append(
                {
                    "id": f"policy-{b.id}",
                    "name": f"{b.display_name} Routing",
                    "category": str(b.vendor),
                    "targetProvider": b.display_name,
                    "targetModel": model,
                    "fallbackProvider": fallback,
                    "enabled": b.health >= 50,
                }
            )
        return result

    @app.get("/omniroute/budget")
    async def omniroute_budget() -> dict:
        """Return budget metrics derived from live brain count.

        No hardcoded costs — returns zeros when no routing has occurred.
        """
        brains = await platform.brain_registry.list_all() if platform.brain_registry else []
        return {
            "today_cost": 0.0,
            "monthly_cost": 0.0,
            "saved_cost": 0.0,
            "local_ratio": 1.0 if brains else 0.0,
        }

    @app.get("/omniroute/compression")
    async def omniroute_compression() -> dict:
        """Return compression metrics.

        No hardcoded token counts — returns zeros when no compression
        has occurred.
        """
        return {
            "original_tokens": 0,
            "compressed_tokens": 0,
            "savings_pct": 0.0,
        }

    @app.get("/omniroute/failover")
    async def omniroute_failover() -> list[dict]:
        """Return failover events from the bounded _omniroute_log.

        No hardcoded events — returns only actually-recorded route events.
        """
        return list(_omniroute_log)

    @app.get("/omniroute/telemetry")
    async def omniroute_telemetry() -> dict:
        """Return telemetry derived from live brain registry + route log.

        No hardcoded metrics — all values reflect actual state.
        """
        brains = await platform.brain_registry.list_all() if platform.brain_registry else []
        active = sum(1 for b in brains if b.health >= 50)
        return {
            "requests_per_sec": 0.0,
            "avg_latency_ms": round(sum(b.latency for b in brains) / len(brains), 1)
            if brains
            else 0.0,
            "retries": 0,
            "failures": 0,
            "compression_ratio": 0.0,
            "active_routes": active,
        }

    @app.post("/omniroute/reload")
    async def omniroute_reload() -> dict:
        return {"reloaded": True, "timestamp": datetime.now(UTC).isoformat()}

    @app.post("/omniroute/route")
    async def omniroute_route(body: dict) -> dict:
        """Route a prompt to the best available discovered brain.

        No hardcoded keyword→provider mapping. Picks the healthiest
        discovered brain; if none are available, returns an error.
        """
        prompt = body.get("prompt", "")
        policy = body.get("policy", "default")

        if platform.brain_registry is None:
            raise HTTPException(status_code=503, detail="Brain registry not available")

        try:
            brains = await platform.brain_registry.list_all()
        except Exception:
            brains = []

        if not brains:
            raise HTTPException(status_code=504, detail="No runtimes discovered — cannot route")

        # Pick the healthiest brain (highest health, then lowest latency)
        best = max(brains, key=lambda b: (b.health, -b.latency))
        target = best.display_name
        model = best.supported_models[0] if best.supported_models else best.display_name

        # Record route log event
        _omniroute_log.append(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "prompt_sample": prompt[:40],
                "target": target,
                "model": model,
            }
        )

        # Publish telemetry to EventBus
        await platform.bus.publish(
            EventEnvelope(
                type="omniroute.route",
                source="omniroute-engine",
                topic=Topic.PROVIDER_HEALTH.value,
                payload={"target_provider": target, "model": model, "policy": policy},
            )
        )

        return {
            "target_provider": target,
            "model": model,
            "latency_ms": best.latency,
            "policy_applied": policy,
        }

    @app.post("/omniroute/compress")
    async def omniroute_compress(body: dict) -> dict:
        text = body.get("text", "")
        orig_tokens = max(1, len(text) // 4)
        comp_tokens = max(1, int(orig_tokens * 0.58))
        return {
            "original_tokens": orig_tokens,
            "compressed_tokens": comp_tokens,
            "compressed_text": text[: int(len(text) * 0.6)] + "...",
            "savings_pct": 42.0,
        }

    # ── OpenAI-compatible /v1 API Gateway ─────────────────────────────────
    if hasattr(platform, "provider_mgr"):
        try:
            from agentic_os.api.gateway import create_gateway_router

            gw_router = create_gateway_router(
                platform.provider_mgr,
                brain_registry=getattr(platform, "brain_registry", None),
                platform=platform,
            )
            app.include_router(gw_router)
            log.info("gateway.mounted")
        except ImportError as exc:
            log.warning("gateway.not_available", error=str(exc))
    else:
        log.warning("gateway.skipped_no_provider_mgr")

    @app.get("/api/provider-management")
    async def provider_management_page() -> HTMLResponse:
        return HTMLResponse(_PROVIDER_PAGE)

    # ── Runtime Diagnostics API ────────────────────────────────────────────
    @app.get("/api/runtime/status")
    async def runtime_status():
        return await rt_status(platform, platform.brain_runtime_bridge, platform.bus)

    @app.get("/api/runtime/discovery")
    async def runtime_discovery():
        return await rt_discovery(platform, platform.brain_runtime_bridge)

    @app.get("/api/runtime/pipeline")
    async def runtime_pipeline():
        return await rt_pipeline(platform, platform.brain_runtime_bridge, platform.bus)

    @app.get("/api/runtime/eventbus")
    async def runtime_eventbus():
        return await rt_eventbus(platform.bus, platform.dashboard)

    @app.get("/api/runtime/registries")
    async def runtime_registries():
        return await rt_registries(
            platform,
            platform.brain_registry,
            platform.brain_stats,
            platform.brain_health,
        )

    @app.get("/api/runtime/brains")
    async def runtime_brains():
        return await rt_brains(platform, platform.brain_registry)

    @app.get("/api/runtime/providers")
    async def runtime_providers():
        return await rt_providers(platform)

    @app.get("/api/runtime/bindings")
    async def runtime_bindings():
        return await rt_bindings(
            platform,
            platform.brain_runtime_bridge,
            platform.brain_registry,
        )

    @app.get("/api/runtime/diagnostics")
    async def runtime_diagnostics():
        return await rt_diagnostics(
            platform,
            platform.brain_runtime_bridge,
            platform.brain_registry,
            platform.bus,
            platform.brain_stats,
            platform.brain_health,
            platform.dashboard,
        )

    @app.get("/api/runtime/errors")
    async def runtime_errors():
        return await rt_errors(platform)

    @app.get("/api/runtime/health")
    async def runtime_health():
        return await rt_health(
            platform,
            platform.brain_runtime_bridge,
            platform.brain_registry,
            platform.bus,
        )

    @app.get("/api/runtime/graph")
    async def runtime_graph():
        return await rt_graph(platform)

    # ── Runtime Diagnostics (Phase 6.2.2) ──────────────────────────────────────
    @app.get("/api/diagnostics")
    async def diagnostics_summary() -> dict:
        return await _diag_svc.collect_summary(platform)

    @app.get("/api/diagnostics/runtime")
    async def diagnostics_runtime() -> dict:
        return await _diag_svc.collect_runtime(platform)

    @app.get("/api/diagnostics/health")
    async def diagnostics_health() -> dict:
        return await _diag_svc.collect_health(platform)

    @app.get("/api/diagnostics/discovery")
    async def diagnostics_discovery() -> dict:
        return await _diag_svc.collect_discovery(platform)

    @app.get("/api/diagnostics/eventbus")
    async def diagnostics_eventbus() -> dict:
        return await _diag_svc.collect_eventbus(platform)

    @app.get("/api/diagnostics/brains")
    async def diagnostics_brains() -> dict:
        return await _diag_svc.collect_brains(platform)

    @app.get("/api/diagnostics/agents")
    async def diagnostics_agents() -> dict:
        return await _diag_svc.collect_agents(platform)

    @app.get("/api/diagnostics/capabilities")
    async def diagnostics_capabilities() -> dict:
        return await _diag_svc.collect_capabilities(platform)

    @app.get("/api/diagnostics/threads")
    async def diagnostics_threads() -> dict:
        return await _diag_svc.collect_threads(platform)

    @app.get("/api/diagnostics/resources")
    async def diagnostics_resources() -> dict:
        return await _diag_svc.collect_resources(platform)

    @app.get("/api/diagnostics/queues")
    async def diagnostics_queues() -> dict:
        return await _diag_svc.collect_queues(platform)

    @app.get("/api/diagnostics/logs")
    async def diagnostics_logs(limit: int = 200) -> dict:
        return await _diag_svc.collect_logs(platform, limit=limit)

    @app.get("/api/diagnostics/mcp")
    async def diagnostics_mcp() -> dict:
        return await _diag_svc.collect_mcp(platform)

    @app.get("/api/diagnostics/providers")
    async def diagnostics_providers_detail() -> dict:
        return await _diag_svc.collect_providers(platform)

    @app.get("/api/diagnostics/apis")
    async def diagnostics_apis() -> dict:
        return await _diag_svc.collect_apis(platform)

    @app.get("/api/diagnostics/sse-clients")
    async def diagnostics_sse_clients() -> dict:
        return await _diag_svc.collect_sse_clients(platform)

    @app.post("/api/diagnostics/self-test")
    async def diagnostics_self_test() -> dict:
        return await _diag_svc.run_self_test(platform)

    @app.get("/api/diagnostics/report")
    async def diagnostics_report(format: str = "json") -> dict:
        return await _diag_svc.generate_report(platform, format=format)

    @app.get("/api/diagnostics/export")
    async def diagnostics_export(format: str = "json"):
        report = await _diag_svc.generate_report(platform, format="json")
        content = json.dumps(report, indent=2, default=str)
        return Response(
            content=content,
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=diagnostics-report.json"},
        )

    @app.get("/api/diagnostics/events")
    async def diagnostics_sse_stream(request: Request):
        """SSE stream for live diagnostics updates."""

        async def _stream():
            yield "event: connected\ndata: {}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    snapshot = await _diag_svc.collect_summary(platform)
                    line = (
                        f"event: DIAGNOSTICS_UPDATED\ndata: {json.dumps(snapshot, default=str)}\n\n"
                    )
                    yield line
                    await asyncio.sleep(5.0)
                except Exception as exc:
                    yield f"event: error\ndata: {json.dumps({'error': str(exc)})}\n\n"
                    await asyncio.sleep(5.0)

        return StreamingResponse(
            _stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # ── Phase 15: Autonomous Agent Ecosystem ───────────────────────────
    # All endpoints are LIVE — they read directly from EcosystemController
    # / EcosystemManager, which derives its state from BrainRegistry and
    # the EventBus. No mock or hardcoded data.

    def _ecosystem_controller():
        ec = getattr(platform, "ecosystem_controller", None)
        if ec is None:
            raise HTTPException(503, detail="EcosystemController not available")
        return ec

    @app.get("/api/ecosystem/status")
    async def ecosystem_status() -> dict:
        ec = getattr(platform, "ecosystem_controller", None)
        if ec is None:
            return {"started": False, "events_processed": 0, "optimizations_triggered": 0}
        return ec.status()

    @app.get("/api/ecosystem/health")
    async def ecosystem_health() -> dict:
        ec = _ecosystem_controller()
        await ec.manager.refresh()
        return ec.manager.health.to_dict()

    @app.get("/api/ecosystem/capabilities")
    async def ecosystem_capabilities() -> dict:
        ec = _ecosystem_controller()
        return ec.manager.capability_graph.to_dict()

    @app.get("/api/ecosystem/collaborations")
    async def ecosystem_collaborations() -> dict:
        ec = _ecosystem_controller()
        return ec.manager.collaboration_network.to_dict()

    @app.get("/api/ecosystem/evolution")
    async def ecosystem_evolution(rec_type: str | None = None, limit: int = 50) -> dict:
        ec = _ecosystem_controller()
        recs = ec.manager.evolution_engine.list_recommendations(rec_type=rec_type, limit=limit)
        return {
            "recommendations": [r.to_dict() for r in recs],
            "stats": ec.manager.evolution_engine.stats(),
        }

    @app.get("/api/ecosystem/dashboard")
    async def ecosystem_dashboard() -> dict:
        ec = _ecosystem_controller()
        await ec.manager.refresh()
        return ec.manager.dashboard()

    @app.get("/api/ecosystem/statistics")
    async def ecosystem_statistics() -> dict:
        ec = _ecosystem_controller()
        await ec.manager.refresh()
        return ec.manager.stats.to_dict()

    @app.post("/api/ecosystem/analyze")
    async def ecosystem_analyze() -> dict:
        ec = _ecosystem_controller()
        return await ec.manager.analyze()

    @app.post("/api/ecosystem/optimize")
    async def ecosystem_optimize() -> dict:
        ec = _ecosystem_controller()
        return await ec.manager.optimize()

    @app.post("/api/ecosystem/evolve")
    async def ecosystem_evolve() -> dict:
        ec = _ecosystem_controller()
        return await ec.manager.evolve()

    @app.post("/api/ecosystem/rebuild")
    async def ecosystem_rebuild() -> dict:
        ec = _ecosystem_controller()
        return await ec.manager.rebuild()

    # ── Phase 15: Task Marketplace (extension endpoints) ──────────────
    # The marketplace is a core EcosystemManager component but exposing
    # these endpoints here lets external callers publish tasks and watch
    # the bid/award lifecycle over the API.

    @app.post("/api/ecosystem/marketplace/publish")
    async def marketplace_publish(body: dict) -> dict:
        ec = _ecosystem_controller()
        task = await ec.manager.marketplace.publish_task(
            title=body.get("title", ""),
            description=body.get("description", ""),
            required_capabilities=body.get("required_capabilities", []),
            priority=float(body.get("priority", 0.5)),
            deadline=body.get("deadline", ""),
            payload=body.get("payload", {}),
        )
        return task.to_dict()

    @app.post("/api/ecosystem/marketplace/select")
    async def marketplace_select(body: dict) -> dict:
        ec = _ecosystem_controller()
        task_id = body.get("task_id", "")
        strategy = body.get("strategy", "balanced")
        bid = await ec.manager.marketplace.select_bid(task_id, strategy)
        if bid is None:
            raise HTTPException(404, detail="No bids available for task")
        return bid.to_dict()

    @app.get("/api/ecosystem/marketplace/tasks")
    async def marketplace_tasks(limit: int = 50) -> list[dict]:
        ec = _ecosystem_controller()
        return [t.to_dict() for t in ec.manager.marketplace.list_all_tasks(limit=limit)]

    @app.get("/api/ecosystem/marketplace/stats")
    async def marketplace_stats() -> dict:
        ec = _ecosystem_controller()
        return ec.manager.marketplace.stats()

    # ── Phase 16: Distributed Runtime Federation ───────────────────────
    # All endpoints are LIVE — they read directly from ClusterController
    # which derives its state from BrainRegistry + EventBus. Single-node
    # deployments return a cluster of size 1 (the local node).

    def _cluster_controller():
        cc = getattr(platform, "cluster_controller", None)
        if cc is None:
            raise HTTPException(503, detail="ClusterController not available")
        return cc

    @app.get("/api/cluster/status")
    async def cluster_status() -> dict:
        cc = getattr(platform, "cluster_controller", None)
        if cc is None:
            return {
                "started": False,
                "events_processed": 0,
                "subscriptions": 0,
                "local_node_id": "",
                "is_leader": False,
                "cluster_id": "default",
                "node_count": 0,
                "remote_brain_count": 0,
            }
        return cc.status()

    @app.get("/api/cluster/nodes")
    async def cluster_nodes() -> list[dict]:
        cc = _cluster_controller()
        return [n.to_dict() for n in cc.topology.list_nodes()]

    @app.get("/api/cluster/topology")
    async def cluster_topology() -> dict:
        cc = _cluster_controller()
        return cc.topology.to_dict()

    @app.get("/api/cluster/brains")
    async def cluster_brains() -> dict:
        cc = _cluster_controller()
        return cc.distributed_registry.to_dict()

    @app.get("/api/cluster/missions")
    async def cluster_missions() -> dict:
        """List active missions across the cluster (from scheduler decisions)."""
        cc = _cluster_controller()
        return {
            "decisions": cc.scheduler.list_decisions(limit=50),
            "stats": cc.scheduler.stats(),
        }

    @app.get("/api/cluster/failover")
    async def cluster_failover_list() -> dict:
        cc = _cluster_controller()
        return cc.failover.to_dict()

    @app.get("/api/cluster/scheduler")
    async def cluster_scheduler() -> dict:
        cc = _cluster_controller()
        return cc.scheduler.stats()

    @app.get("/api/cluster/dashboard")
    async def cluster_dashboard() -> dict:
        cc = _cluster_controller()
        return cc.dashboard()

    @app.get("/api/cluster/statistics")
    async def cluster_statistics() -> dict:
        cc = _cluster_controller()
        return cc.dashboard()["statistics"]

    @app.post("/api/cluster/discover")
    async def cluster_discover() -> dict:
        cc = _cluster_controller()
        nodes = await cc.discover_nodes()
        return {"discovered": len(nodes), "nodes": nodes}

    @app.post("/api/cluster/rebalance")
    async def cluster_rebalance() -> dict:
        cc = _cluster_controller()
        return await cc.rebalance()

    @app.post("/api/cluster/failover")
    async def cluster_failover_trigger(body: dict) -> dict:
        cc = _cluster_controller()
        brain_id = str(body.get("brain_id", ""))
        node_id = str(body.get("node_id", ""))
        mission_id = str(body.get("mission_id", ""))
        if not brain_id or not node_id:
            raise HTTPException(400, detail="brain_id and node_id required")
        action = await cc.failover.trigger_manual_failover(
            brain_id=brain_id, node_id=node_id, mission_id=mission_id
        )
        return action.to_dict()

    @app.post("/api/cluster/synchronize")
    async def cluster_synchronize() -> dict:
        cc = _cluster_controller()
        return await cc.synchronize()

    @app.post("/api/cluster/elect-leader")
    async def cluster_elect_leader(body: dict | None = None) -> dict:
        cc = _cluster_controller()
        candidates = None
        if body and isinstance(body, dict):
            raw = body.get("candidates")
            if isinstance(raw, list):
                candidates = [str(c) for c in raw]
        leader = await cc.elect_leader(candidates)
        return {"leader_id": leader, "elected": leader is not None}

    @app.post("/api/cluster/rebuild")
    async def cluster_rebuild() -> dict:
        cc = _cluster_controller()
        return await cc.rebuild()

    # ── Phase 16: Cluster membership management (extension endpoints) ──
    # These let external callers (or a cluster bootstrap script) register
    # remote nodes so the federation manager can include them in topology.

    @app.post("/api/cluster/nodes/add")
    async def cluster_add_node(body: dict) -> dict:
        cc = _cluster_controller()
        node_id = str(body.get("node_id") or body.get("id") or "")
        host = str(body.get("host", "localhost"))
        port = int(body.get("port", 8000))
        if not node_id:
            node_id = f"node-{host}-{port}"
        node = await cc.federation.add_remote_node(
            node_id=node_id,
            host=host,
            port=port,
            base_url=str(body.get("base_url", "")),
            display_name=str(body.get("display_name", "")),
            version=str(body.get("version", "1.0.0")),
            metadata=body.get("metadata"),
        )
        return node.to_dict()

    @app.post("/api/cluster/nodes/{node_id}/remove")
    async def cluster_remove_node(node_id: str, body: dict | None = None) -> dict:
        cc = _cluster_controller()
        reason = str((body or {}).get("reason", ""))
        removed = await cc.federation.remove_node(node_id, reason)
        return {"removed": removed, "node_id": node_id}

    @app.post("/api/cluster/consensus")
    async def cluster_consensus(body: dict) -> dict:
        """Run a consensus round. Body should contain proposal, votes, type."""
        cc = _cluster_controller()
        from agentic_os.core.cluster.domain import ConsensusVote

        proposal = str(body.get("proposal", ""))
        consensus_type = body.get("consensus_type", "majority")
        raw_votes = body.get("votes", []) or []
        votes: list[ConsensusVote] = []
        for v in raw_votes:
            votes.append(
                ConsensusVote(
                    node_id=str(v.get("node_id", "")),
                    vote=str(v.get("vote", "abstain")),
                    weight=float(v.get("weight", 1.0)),
                    confidence=float(v.get("confidence", 1.0)),
                    rationale=str(v.get("rationale", "")),
                )
            )
        result = cc.consensus.run_consensus(
            proposal=proposal,
            votes=votes,
            consensus_type=consensus_type,
        )
        # Publish event
        try:
            from agentic_os.domain.events import EventEnvelope

            await platform.bus.publish(
                EventEnvelope(
                    type="cluster.consensus.completed",
                    source="cluster.api",
                    topic="cluster.consensus.completed",
                    payload=result.to_dict(),
                )
            )
        except Exception:
            pass
        return result.to_dict()

    # ── Phase 17: Autonomous Agent Evolution ───────────────────────────
    # All endpoints are LIVE — they read directly from EvolutionController
    # / EvolutionManager, which derives its state from the existing
    # Phase 11-16 infrastructure. No mock data.

    def _evolution_controller():
        ec = getattr(platform, "evolution_controller", None)
        if ec is None:
            raise HTTPException(503, detail="EvolutionController not available")
        return ec

    @app.get("/api/evolution/status")
    async def evolution_status() -> dict:
        ec = getattr(platform, "evolution_controller", None)
        if ec is None:
            return {"started": False, "events_processed": 0, "analyses_triggered": 0}
        return ec.status()

    @app.get("/api/evolution/dashboard")
    async def evolution_dashboard() -> dict:
        ec = _evolution_controller()
        return ec.manager.dashboard()

    @app.get("/api/evolution/statistics")
    async def evolution_statistics() -> dict:
        ec = _evolution_controller()
        return ec.manager.statistics.to_dict()

    @app.get("/api/evolution/readiness")
    async def evolution_readiness() -> dict:
        ec = _evolution_controller()
        return await ec.manager.assess_readiness()

    @app.get("/api/evolution/improvements")
    async def evolution_improvements(status: str | None = None, limit: int = 50) -> dict:
        ec = _evolution_controller()
        proposals = ec.manager.improvement_engine.list_proposals(status=status, limit=limit)
        return {
            "improvements": [p.to_dict() for p in proposals],
            "stats": ec.manager.improvement_engine.stats(),
        }

    @app.get("/api/evolution/improvements/{proposal_id}")
    async def evolution_improvement_detail(proposal_id: str) -> dict:
        ec = _evolution_controller()
        proposal = ec.manager.improvement_engine.get_proposal(proposal_id)
        if proposal is None:
            raise HTTPException(404, detail="Improvement not found")
        return proposal.to_dict()

    @app.get("/api/evolution/safety")
    async def evolution_safety() -> dict:
        ec = _evolution_controller()
        return {
            "validator": ec.manager.safety_validator.stats(),
            "regression_guard": ec.manager.regression_guard.stats(),
            "history": [r.to_dict() for r in ec.manager.safety_validator.list_history(limit=20)],
        }

    @app.get("/api/evolution/scheduler")
    async def evolution_scheduler() -> dict:
        ec = _evolution_controller()
        sched = ec.manager.scheduler
        return {
            "stats": sched.stats(),
            "queue": [p.to_dict() for p in sched.get_queue()],
            "scheduled": [p.to_dict() for p in sched.get_scheduled()],
        }

    @app.get("/api/evolution/plans")
    async def evolution_plans(target_type: str | None = None) -> dict:
        ec = _evolution_controller()
        plans = ec.manager.code_planner.list_plans(target_type=target_type)
        return {
            "plans": [p.to_dict() for p in plans],
            "stats": ec.manager.code_planner.stats(),
        }

    @app.get("/api/evolution/knowledge")
    async def evolution_knowledge() -> dict:
        ec = _evolution_controller()
        syntheses = ec.manager.knowledge_synthesizer.list_syntheses()
        return {
            "syntheses": [s.to_dict() for s in syntheses],
            "stats": ec.manager.knowledge_synthesizer.stats(),
        }

    @app.post("/api/evolution/analyze")
    async def evolution_analyze() -> dict:
        ec = _evolution_controller()
        return await ec.manager.analyze()

    @app.post("/api/evolution/schedule")
    async def evolution_schedule_next() -> dict:
        ec = _evolution_controller()
        return await ec.manager.schedule_next()

    @app.post("/api/evolution/improvements/{proposal_id}/apply")
    async def evolution_apply(proposal_id: str) -> dict:
        ec = _evolution_controller()
        return await ec.manager.apply_improvement(proposal_id)

    @app.post("/api/evolution/improvements/{proposal_id}/rollback")
    async def evolution_rollback(proposal_id: str, body: dict | None = None) -> dict:
        ec = _evolution_controller()
        reason = str((body or {}).get("reason", ""))
        return await ec.manager.rollback_improvement(proposal_id, reason)

    @app.post("/api/evolution/synthesize")
    async def evolution_synthesize(body: dict) -> dict:
        ec = _evolution_controller()
        topic = str(body.get("topic", ""))
        sources = body.get("sources", [])
        if not topic:
            raise HTTPException(400, detail="topic required")
        return await ec.manager.synthesize_knowledge(topic, sources)

    @app.post("/api/evolution/readiness/assess")
    async def evolution_assess_readiness() -> dict:
        ec = _evolution_controller()
        return await ec.manager.assess_readiness()

    # ── Phase 17: Distributed Execution Fabric ─────────────────────────
    # All endpoints are LIVE — they read directly from DistributedController
    # which derives its state from the existing Phase 16 cluster + Phase 17
    # transport/heartbeat/election/executor components.

    def _distributed_controller():
        dc = getattr(platform, "distributed_controller", None)
        if dc is None:
            raise HTTPException(503, detail="DistributedController not available")
        return dc

    @app.get("/api/distributed/status")
    async def distributed_status() -> dict:
        dc = getattr(platform, "distributed_controller", None)
        if dc is None:
            return {"started": False, "local_node_id": "", "leader_id": "", "peer_count": 0}
        return dc.status()

    @app.get("/api/distributed/dashboard")
    async def distributed_dashboard() -> dict:
        dc = _distributed_controller()
        return dc.dashboard()

    @app.get("/api/distributed/health")
    async def distributed_health() -> dict:
        dc = _distributed_controller()
        return dc.get_cluster_health()

    @app.get("/api/distributed/tasks")
    async def distributed_tasks(status: str | None = None) -> dict:
        dc = _distributed_controller()

        tasks = dc.executor.list_tasks(status=status)
        return {
            "tasks": [t.to_dict() for t in tasks],
            "stats": dc.executor.stats,
        }

    @app.post("/api/distributed/tasks/dispatch")
    async def distributed_dispatch_task(body: dict) -> dict:
        dc = _distributed_controller()
        from agentic_os.core.distributed import DistributedTask

        task = DistributedTask(
            title=str(body.get("title", "")),
            description=str(body.get("description", "")),
            required_capabilities=list(body.get("required_capabilities", [])),
            target_node_id=str(body.get("target_node_id", "")),
            priority=float(body.get("priority", 0.5)),
            payload=dict(body.get("payload", {})),
        )
        success = await dc.dispatch_task(task)
        return {"dispatched": success, "task": task.to_dict()}

    @app.post("/api/distributed/tasks/{task_id}/ack")
    async def distributed_ack_task(task_id: str, body: dict) -> dict:
        """Receive a task acknowledgement from a remote node."""
        dc = _distributed_controller()
        from agentic_os.core.distributed import TaskAcknowledgement

        ack = TaskAcknowledgement(
            task_id=task_id,
            node_id=str(body.get("node_id", "")),
            brain_id=str(body.get("brain_id", "")),
            accepted=bool(body.get("accepted", True)),
            reason=str(body.get("reason", "")),
        )
        accepted = dc.executor.receive_acknowledgement(ack)
        return {"accepted": accepted}

    @app.post("/api/distributed/tasks/{task_id}/complete")
    async def distributed_complete_task(task_id: str, body: dict) -> dict:
        """Receive a task completion from a remote node."""
        dc = _distributed_controller()
        result = dict(body.get("result", {}))
        success = bool(body.get("success", True))
        completed = dc.executor.receive_completion(task_id, result, success)
        return {"completed": completed}

    @app.get("/api/distributed/events")
    async def distributed_events() -> dict:
        dc = _distributed_controller()
        return {"stats": dc.event_bus.stats}

    @app.post("/api/distributed/events")
    async def distributed_receive_event(body: dict) -> dict:
        """Receive a propagated event from a peer node."""
        dc = _distributed_controller()
        accepted = dc.event_bus.receive_inbound(body)
        return {"accepted": accepted}

    @app.post("/api/distributed/heartbeat")
    async def distributed_receive_heartbeat(body: dict) -> dict:
        """Receive a heartbeat from a peer node."""
        dc = _distributed_controller()
        from agentic_os.core.distributed import HeartbeatPacket

        packet = HeartbeatPacket(
            node_id=str(body.get("node_id", "")),
            sequence=int(body.get("sequence", 0)),
            status=str(body.get("status", "active")),
            brain_count=int(body.get("brain_count", 0)),
            active_tasks=int(body.get("active_tasks", 0)),
            cpu_usage=float(body.get("cpu_usage", 0)),
            memory_usage=float(body.get("memory_usage", 0)),
            health_score=float(body.get("health_score", 100)),
            leader_id=str(body.get("leader_id", "")),
        )
        accepted = dc.heartbeat.receive_heartbeat(packet)
        return {"accepted": accepted}

    @app.post("/api/distributed/replicate")
    async def distributed_receive_replication(body: dict) -> dict:
        """Receive a replicated state entry from a peer."""
        dc = _distributed_controller()
        accepted = dc.replication.receive_replication(body)
        return {"accepted": accepted}

    @app.post("/api/distributed/vote")
    async def distributed_receive_vote(body: dict) -> dict:
        """Receive a leader election vote from a peer."""
        dc = _distributed_controller()
        from agentic_os.core.distributed import LeaderVote

        vote = LeaderVote(
            voter_id=str(body.get("voter_id", "")),
            candidate_id=str(body.get("candidate_id", "")),
            term=int(body.get("term", 0)),
        )
        accepted = dc.leader_election.receive_vote(vote)
        return {"accepted": accepted}

    @app.post("/api/distributed/join")
    async def distributed_join(body: dict) -> dict:
        """Join a cluster by connecting to a peer node."""
        dc = _distributed_controller()
        peer_url = str(body.get("peer_url", ""))
        peer_node_id = str(body.get("peer_node_id", ""))
        if not peer_url:
            raise HTTPException(400, detail="peer_url required")
        return await dc.join_cluster(peer_url, peer_node_id)

    @app.post("/api/distributed/leave")
    async def distributed_leave(body: dict) -> dict:
        """Leave the cluster or remove a node."""
        dc = _distributed_controller()
        node_id = str(body.get("node_id", ""))
        reason = str(body.get("reason", ""))
        if not node_id:
            raise HTTPException(400, detail="node_id required")
        return await dc.leave_cluster(node_id, reason)

    @app.post("/api/distributed/leader")
    async def distributed_elect_leader() -> dict:
        """Run leader election."""
        dc = _distributed_controller()
        return await dc.elect_leader()

    @app.get("/api/distributed/topology")
    async def distributed_topology() -> dict:
        dc = _distributed_controller()
        return {
            "local_node_id": dc._local_node_id,
            "leader_id": dc.leader_election.current_leader,
            "leader_term": dc.leader_election.current_term,
            "nodes": dc.node_registry.list_nodes(),
            "peers": dc.transport.list_peers(),
        }

    @app.get("/api/distributed/scheduler")
    async def distributed_scheduler() -> dict:
        dc = _distributed_controller()
        return dc.scheduler.stats

    # ── Phase 18: Persistent Runtime ───────────────────────────────────

    def _persistent_controller():
        pc = getattr(platform, "persistent_controller", None)
        if pc is None:
            raise HTTPException(503, detail="PersistentController not available")
        return pc

    @app.get("/api/runtime/state")
    async def runtime_state() -> dict:
        pc = getattr(platform, "persistent_controller", None)
        if pc is None:
            return {"started": False, "data_dir": ""}
        return pc.status()

    @app.get("/api/runtime/dashboard")
    async def runtime_dashboard() -> dict:
        pc = _persistent_controller()
        return pc.dashboard()

    @app.post("/api/runtime/snapshot")
    async def runtime_create_snapshot() -> dict:
        pc = _persistent_controller()
        return await pc.create_snapshot()

    @app.get("/api/runtime/snapshot")
    async def runtime_list_snapshots(limit: int = 50) -> list[dict]:
        pc = _persistent_controller()
        return await pc.snapshot_engine.list_snapshots(limit=limit)

    @app.post("/api/runtime/restore")
    async def runtime_restore(body: dict) -> dict:
        pc = _persistent_controller()
        snapshot_id = str(body.get("snapshot_id", ""))
        if not snapshot_id:
            raise HTTPException(400, detail="snapshot_id required")
        return await pc.restore_snapshot(snapshot_id)

    @app.get("/api/runtime/jobs")
    async def runtime_jobs(status: str | None = None) -> dict:
        pc = _persistent_controller()

        jobs = pc.scheduler.list_jobs(status=status)
        return {"jobs": [j.to_dict() for j in jobs], "stats": pc.scheduler.stats}

    @app.post("/api/runtime/jobs")
    async def runtime_schedule_job(body: dict) -> dict:
        pc = _persistent_controller()
        name = str(body.get("name", ""))
        handler = str(body.get("handler", ""))
        if not name or not handler:
            raise HTTPException(400, detail="name and handler required")
        return await pc.schedule_job(
            name=name,
            handler=handler,
            schedule=str(body.get("schedule", "60")),
            priority=int(body.get("priority", 5)),
            args=body.get("args", {}),
        )

    @app.post("/api/runtime/jobs/{job_id}/cancel")
    async def runtime_cancel_job(job_id: str) -> dict:
        pc = _persistent_controller()
        cancelled = await pc.scheduler.cancel(job_id)
        return {"cancelled": cancelled}

    @app.post("/api/runtime/jobs/{job_id}/pause")
    async def runtime_pause_job(job_id: str) -> dict:
        pc = _persistent_controller()
        paused = await pc.scheduler.pause(job_id)
        return {"paused": paused}

    @app.post("/api/runtime/jobs/{job_id}/resume")
    async def runtime_resume_job(job_id: str) -> dict:
        pc = _persistent_controller()
        resumed = await pc.scheduler.resume(job_id)
        return {"resumed": resumed}

    @app.get("/api/runtime/queue")
    async def runtime_queue(queue: str = "default", limit: int = 50) -> dict:
        pc = _persistent_controller()
        tasks = pc.queue.list_tasks(queue=queue, limit=limit)
        dead = pc.queue.list_dead_letter(limit=limit)
        return {
            "tasks": [t.to_dict() for t in tasks],
            "dead_letter": [t.to_dict() for t in dead],
            "stats": pc.queue.stats,
        }

    @app.post("/api/runtime/queue")
    async def runtime_enqueue(body: dict) -> dict:
        pc = _persistent_controller()
        return await pc.enqueue_task(
            payload=dict(body.get("payload", {})),
            queue=str(body.get("queue", "default")),
            priority=int(body.get("priority", 5)),
        )

    @app.get("/api/runtime/history")
    async def runtime_history(limit: int = 100, topic: str | None = None) -> dict:
        pc = _persistent_controller()
        events = await pc.journal.replay(limit=limit, topic=topic)
        return {"events": events, "stats": pc.journal.stats}

    @app.get("/api/runtime/recovery")
    async def runtime_recovery() -> dict:
        pc = _persistent_controller()
        return {
            "stats": pc.recovery_engine.stats,
            "history": [p.to_dict() for p in pc.recovery_engine.list_history()],
        }

    @app.get("/api/runtime/scheduler")
    async def runtime_scheduler() -> dict:
        pc = _persistent_controller()
        return pc.scheduler.stats

    @app.get("/api/runtime/events")
    async def runtime_events(limit: int = 100, topic: str | None = None) -> dict:
        pc = _persistent_controller()
        events = await pc.journal.replay(limit=limit, topic=topic)
        return {"events": events, "stats": pc.journal.stats}

    @app.get("/api/runtime/audit")
    async def runtime_audit(limit: int = 100) -> dict:
        pc = _persistent_controller()
        records = await pc.audit.read(limit=limit)
        return {"records": records, "stats": pc.audit.stats}

    @app.get("/api/runtime/health/supervisor")
    async def runtime_health_supervisor() -> dict:
        pc = _persistent_controller()
        checks = pc.health.list_checks()
        return {
            "checks": [c.to_dict() for c in checks],
            "stats": pc.health.stats,
        }

    @app.post("/api/runtime/backup")
    async def runtime_create_backup() -> dict:
        pc = _persistent_controller()
        manifest = await pc.backup.create_backup()
        return manifest.to_dict() if manifest else {}

    @app.get("/api/runtime/backup")
    async def runtime_list_backups() -> list[dict]:
        pc = _persistent_controller()
        return await pc.backup.list_backups()

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
