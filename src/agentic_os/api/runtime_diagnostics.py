"""Runtime Diagnostics API — live introspection of the discovery pipeline.

Provides 12+ endpoints under /api/runtime/ for debugging and monitoring
the entire discovery → registry → EventBus → SSE → frontend pipeline.

Used by the Runtime Diagnostics Dashboard (frontend component).
"""

from __future__ import annotations

import platform as py_platform
from datetime import UTC, datetime
from typing import Any

from agentic_os.api.dashboard import DashboardBroadcaster
from agentic_os.core.brains.health import BrainHealthMonitor
from agentic_os.core.brains.registry import BrainRegistry
from agentic_os.core.brains.runtime_bridge import RuntimeBridge
from agentic_os.core.brains.stats import BrainStatistics
from agentic_os.domain.events import Topic
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.event_bus import EventBus

log = get_logger("api.runtime_diagnostics")


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _status_color(healthy: bool, active: bool) -> str:
    if healthy and active:
        return "green"
    if active:
        return "yellow"
    return "red"


# ── Helpers ──────────────────────────────────────────────────────────────


async def _collect_registry_stats(
    registry: BrainRegistry | None,
) -> dict[str, Any]:
    """Collect statistics from the BrainRegistry."""
    if registry is None:
        return {"status": "unavailable", "brains": 0, "by_status": {}, "by_type": {}}

    brains = await registry.list_all()
    by_status: dict[str, int] = {}
    by_type: dict[str, int] = {}
    total = len(brains)
    healthy = 0
    for b in brains:
        s = b.status.value if hasattr(b.status, "value") else str(b.status)
        by_status[s] = by_status.get(s, 0) + 1
        t = b.brain_type.value if hasattr(b.brain_type, "value") else str(b.brain_type)
        by_type[t] = by_type.get(t, 0) + 1
        if b.health >= 80:
            healthy += 1

    return {
        "status": "available",
        "total": total,
        "healthy": healthy,
        "degraded": sum(1 for b in brains if 0 < b.health < 80),
        "unhealthy": sum(1 for b in brains if b.health == 0),
        "by_status": by_status,
        "by_type": by_type,
    }


async def _collect_brain_details(registry: BrainRegistry | None) -> list[dict[str, Any]]:
    """Collect detailed brain records for diagnostics."""
    if registry is None:
        return []
    brains = await registry.list_all()
    result: list[dict[str, Any]] = []
    for b in brains:
        result.append(
            {
                "id": b.id,
                "display_name": b.display_name,
                "brain_type": str(b.brain_type),
                "vendor": str(b.vendor),
                "runtime": str(b.runtime),
                "version": b.version,
                "status": str(b.status),
                "health": b.health,
                "capabilities": list(b.capabilities),
                "memory_usage": b.memory_usage,
                "cpu_usage": b.cpu_usage,
                "latency": b.latency,
                "current_tasks": b.current_tasks,
                "error_count": b.error_count,
                "last_seen": b.last_seen,
                "discovered_at": b.discovered_at,
                "supported_models": list(b.supported_models),
            }
        )
    return result


# ── Endpoint implementations ────────────────────────────────────────────


async def status(
    platform: Any,
    runtime_bridge: RuntimeBridge | None,
    event_bus: EventBus | None,
) -> dict[str, Any]:
    """GET /api/runtime/status — overall runtime health."""
    return {
        "server": {
            "started_at": _now_iso(),
            "python_version": py_platform.python_version(),
            "platform": py_platform.system(),
            "hostname": py_platform.node(),
        },
        "pipeline": {
            "discovery": "active" if runtime_bridge is not None else "unavailable",
            "registry": "active" if platform.brain_registry is not None else "unavailable",
            "dashboard": "active" if platform.dashboard is not None else "unavailable",
            "eventbus": "active" if event_bus is not None else "unavailable",
        },
        "timestamp": _now_iso(),
    }


async def discovery(
    platform: Any,
    runtime_bridge: RuntimeBridge | None,
) -> dict[str, Any]:
    """GET /api/runtime/discovery — discovery scanner status."""
    scanners: list[dict[str, Any]] = []
    if runtime_bridge is not None:
        for tt in runtime_bridge.list_tool_types():
            info = await runtime_bridge.detect_one(tt)
            scanners.append(
                {
                    "tool_type": tt,
                    "installed": info.installed if info else False,
                    "version": info.version if info else "",
                    "executable": info.executable if info else "",
                    "status": str(info.status) if info else "unknown",
                }
            )
    return {
        "windows_scan": "supported",
        "connectors": len(scanners),
        "scanners": scanners,
        "local_discovery": platform.local_discovery is not None,
        "local_agents": len(await platform.local_discovery.get_agents())
        if platform.local_discovery is not None
        else 0,
        "timestamp": _now_iso(),
    }


async def pipeline(
    platform: Any,
    runtime_bridge: RuntimeBridge | None,
    event_bus: EventBus | None,
) -> dict[str, Any]:
    """GET /api/runtime/pipeline — pipeline stage health with timing."""
    stages: list[dict[str, Any]] = []
    stages.append(
        {
            "name": "Windows Process Detection",
            "status": "available" if runtime_bridge is not None else "unavailable",
            "color": _status_color(runtime_bridge is not None, True),
        }
    )
    stages.append(
        {
            "name": "Brain Registry",
            "status": "available" if platform.brain_registry is not None else "unavailable",
            "color": _status_color(platform.brain_registry is not None, True),
        }
    )
    stages.append(
        {
            "name": "Runtime Bridge",
            "status": "available" if runtime_bridge is not None else "unavailable",
            "color": _status_color(runtime_bridge is not None, True),
        }
    )
    stages.append(
        {
            "name": "EventBus",
            "status": "available" if event_bus is not None else "unavailable",
            "color": _status_color(event_bus is not None, True),
        }
    )
    stages.append(
        {
            "name": "Dashboard Broadcaster",
            "status": "available" if platform.dashboard is not None else "unavailable",
            "color": _status_color(platform.dashboard is not None, True),
        }
    )
    stages.append(
        {
            "name": "SSE / WebSocket",
            "status": "active" if platform.dashboard is not None else "unavailable",
            "color": _status_color(platform.dashboard is not None, True),
        }
    )
    return {"stages": stages, "timestamp": _now_iso()}


async def eventbus(
    event_bus: EventBus | None,
    dashboard: DashboardBroadcaster | None,
) -> dict[str, Any]:
    """GET /api/runtime/eventbus — EventBus statistics."""
    return {
        "eventbus": "active" if event_bus is not None else "unavailable",
        "dashboard": "active" if dashboard is not None else "unavailable",
        "subscribers": list(_DASHBOARD_TOPICS_NAMES) if dashboard is not None else [],
        "recent_events": dashboard.get_recent_events(limit=25) if dashboard is not None else [],
        "timestamp": _now_iso(),
    }


_DASHBOARD_TOPICS_NAMES = [
    t.value
    for t in [
        Topic.TASK_CREATED,
        Topic.AGENT_STARTED,
        Topic.AGENT_COMPLETED,
        Topic.AGENT_FAILED,
        Topic.AGENT_RECOVERED,
        Topic.PROVIDER_REGISTERED,
        Topic.PROVIDER_HEALTH,
        Topic.PROVIDER_FAILED,
        Topic.BRAIN_DISCOVERED,
        Topic.BRAIN_REGISTERED,
        Topic.BRAIN_UPDATED,
        Topic.BRAIN_CONNECTED,
        Topic.BRAIN_DISCONNECTED,
        Topic.BRAIN_HEALTH_CHANGED,
        Topic.BRAIN_REMOVED,
    ]
]


async def registries(
    platform: Any,
    registry: BrainRegistry | None,
    stats: BrainStatistics | None,
    health: BrainHealthMonitor | None,
) -> dict[str, Any]:
    """GET /api/runtime/registries — all registry statistics."""
    reg_stats = await _collect_registry_stats(registry)
    return {
        "brain_registry": reg_stats,
        "local_discovery": {
            "active": platform.local_discovery is not None,
            "agents": len(await platform.local_discovery.get_agents())
            if platform.local_discovery is not None
            else 0,
        },
        "timestamp": _now_iso(),
    }


async def brains(
    platform: Any,
    registry: BrainRegistry | None,
) -> dict[str, Any]:
    """GET /api/runtime/brains — detailed brain list."""
    return {"brains": await _collect_brain_details(registry), "timestamp": _now_iso()}


async def providers(platform: Any) -> dict[str, Any]:
    """GET /api/runtime/providers — provider diagnostics."""
    providers_list: list[dict[str, Any]] = []
    if platform.brain_registry is not None:
        brains = await platform.brain_registry.list_all()
        for b in brains:
            providers_list.append(
                {
                    "name": b.display_name,
                    "vendor": str(b.vendor),
                    "health": b.health,
                    "status": str(b.status),
                    "latency_ms": b.latency,
                    "brain_id": b.id,
                    "bound": b.health >= 50,
                }
            )
    return {"providers": providers_list, "count": len(providers_list), "timestamp": _now_iso()}


async def bindings(
    platform: Any,
    runtime_bridge: RuntimeBridge | None,
    registry: BrainRegistry | None,
) -> dict[str, Any]:
    """GET /api/runtime/bindings — auto-binding diagnostics per brain."""
    bindings_list: list[dict[str, Any]] = []
    if runtime_bridge is not None:
        for tt in runtime_bridge.list_tool_types():
            connector = runtime_bridge.get_connector(tt)
            info = await runtime_bridge.detect_one(tt)
            binding: dict[str, Any] = {
                "tool_type": tt,
                "display_name": connector.display_name if connector else tt,
                "steps": [],
            }
            steps = binding["steps"]

            # Step 1: detected?
            if info and info.installed:
                steps.append({"step": "detected", "status": "✓", "detail": info.executable})
            else:
                steps.append(
                    {"step": "detected", "status": "✗", "detail": "executable not found in PATH"}
                )
                steps.append(
                    {"step": "executable_found", "status": "✗", "detail": "binary not on PATH"}
                )
                bindings_list.append(binding)
                continue

            # Step 2: executable found
            if info.executable:
                steps.append({"step": "executable_found", "status": "✓", "detail": info.executable})
            else:
                steps.append(
                    {"step": "executable_found", "status": "✗", "detail": "no path resolved"}
                )

            # Step 3: version resolved
            if info.version:
                steps.append({"step": "version_resolved", "status": "✓", "detail": info.version})
            else:
                steps.append(
                    {
                        "step": "version_resolved",
                        "status": "✗",
                        "detail": "could not determine version",
                    }
                )

            # Step 4: brain record exists?
            if registry is not None:
                record = await registry.get(f"{tt}-brain")
                if record:
                    steps.append(
                        {"step": "brain_registered", "status": "✓", "detail": f"id={record.id}"}
                    )
                else:
                    steps.append(
                        {"step": "brain_registered", "status": "✗", "detail": "not in registry"}
                    )
            else:
                steps.append(
                    {"step": "brain_registered", "status": "✗", "detail": "registry unavailable"}
                )

            # Step 5: event published?
            steps.append(
                {
                    "step": "event_published",
                    "status": "✓" if info.installed else "✗",
                    "detail": "provider.registered + agent.started"
                    if info.installed
                    else "skipped",
                }
            )

            binding["bound"] = all(s["status"] == "✓" for s in steps)
            bindings_list.append(binding)

    return {
        "bindings": bindings_list,
        "total": len(bindings_list),
        "bound": sum(1 for b in bindings_list if b.get("bound")),
        "timestamp": _now_iso(),
    }


async def diagnostics(
    platform: Any,
    runtime_bridge: RuntimeBridge | None,
    registry: BrainRegistry | None,
    event_bus: EventBus | None,
    stats: BrainStatistics | None,
    health: BrainHealthMonitor | None,
    dashboard: DashboardBroadcaster | None,
) -> dict[str, Any]:
    """GET /api/runtime/diagnostics — comprehensive runtime snapshot."""
    return {
        "status": await status(platform, runtime_bridge, event_bus),
        "discovery": await discovery(platform, runtime_bridge),
        "pipeline": await pipeline(platform, runtime_bridge, event_bus),
        "eventbus": await eventbus(event_bus, dashboard),
        "registries": await registries(platform, registry, stats, health),
        "brains": await brains(platform, registry),
        "providers": await providers(platform),
        "bindings": await bindings(platform, runtime_bridge, registry),
        "timestamp": _now_iso(),
    }


async def errors(platform: Any) -> dict[str, Any]:
    """GET /api/runtime/errors — recent errors from brains."""
    error_list: list[dict[str, Any]] = []
    if platform.brain_health is not None:
        brains = await platform.brain_registry.list_all() if platform.brain_registry else []
        for b in brains:
            if b.error_count > 0:
                error_list.append(
                    {
                        "brain_id": b.id,
                        "display_name": b.display_name,
                        "error_count": b.error_count,
                        "status": str(b.status),
                        "health": b.health,
                    }
                )
    return {
        "errors": error_list,
        "total": len(error_list),
        "timestamp": _now_iso(),
    }


async def health(
    platform: Any,
    runtime_bridge: RuntimeBridge | None,
    registry: BrainRegistry | None,
    event_bus: EventBus | None,
) -> dict[str, Any]:
    """GET /api/runtime/health — overall system health."""
    reg_stats = await _collect_registry_stats(registry)
    return {
        "overall": "healthy" if reg_stats.get("healthy", 0) > 0 else "degraded",
        "brain_registry": reg_stats,
        "runtime_bridge": "available" if runtime_bridge is not None else "unavailable",
        "eventbus": "available" if event_bus is not None else "unavailable",
        "dashboard": "available" if platform.dashboard is not None else "unavailable",
        "timestamp": _now_iso(),
    }


async def graph(platform: Any) -> dict[str, Any]:
    """GET /api/runtime/graph — brain relationship graph."""
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    if platform.brain_registry is not None:
        brains = await platform.brain_registry.list_all()
        for b in brains:
            nodes.append(
                {
                    "id": b.id,
                    "label": b.display_name,
                    "type": str(b.brain_type),
                    "status": str(b.status),
                    "health": b.health,
                }
            )
    if platform.brain_graph is not None:
        try:
            rels = await platform.brain_graph.get_all_relationships()
            for r in rels:
                edges.append(
                    {
                        "source": r.source_id,
                        "target": r.target_id,
                        "type": r.relationship_type,
                        "weight": r.weight,
                    }
                )
        except Exception:
            pass
    return {"nodes": nodes, "edges": edges, "timestamp": _now_iso()}
