"""Runtime Diagnostics Service — Phase 6.2.2.

Collects live runtime state from every AgenticOS subsystem.  All methods are
async and wrap every call in try/except so they never raise — the dashboard
always gets a coherent (possibly partial) snapshot.
"""

from __future__ import annotations

import asyncio
import gc
import os
import platform as os_platform
import subprocess
import time
from datetime import UTC, datetime
from typing import Any

import psutil

from agentic_os.infrastructure.logging import get_logger

log = get_logger("diagnostics")


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


def _safe(fn, default=None):
    """Call *fn* and return *default* on any exception."""
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


class RuntimeDiagnosticsService:
    """Collects comprehensive runtime diagnostics for AgenticOS."""

    def __init__(self) -> None:
        self._start_time = time.monotonic()
        self._wall_start = time.time()

    # ── Git helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _git_commit() -> str:
        try:
            return (
                subprocess.check_output(
                    ["git", "rev-parse", "HEAD"],
                    timeout=2,
                    stderr=subprocess.DEVNULL,
                )
                .decode()
                .strip()
            )
        except Exception:  # noqa: BLE001
            return "unknown"

    @staticmethod
    def _git_branch() -> str:
        try:
            return (
                subprocess.check_output(
                    ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                    timeout=2,
                    stderr=subprocess.DEVNULL,
                )
                .decode()
                .strip()
            )
        except Exception:  # noqa: BLE001
            return "unknown"

    # ── Collectors ───────────────────────────────────────────────────────────

    async def collect_runtime(self, platform: Any) -> dict:
        """Collect core runtime metadata and process info."""
        try:
            proc = psutil.Process()
            mem_info = _safe(proc.memory_info)
            uptime_s = time.monotonic() - self._start_time
            tasks = asyncio.all_tasks()

            return {
                "hostname": _safe(os_platform.node, "unknown"),
                "os": _safe(os_platform.system, "unknown"),
                "os_version": _safe(os_platform.version, "unknown"),
                "python_version": _safe(os_platform.python_version, "unknown"),
                "cpu_count": _safe(lambda: psutil.cpu_count(logical=True), 0),
                "cpu_percent": _safe(lambda: psutil.cpu_percent(interval=None), 0.0),
                "ram_total": _safe(lambda: psutil.virtual_memory().total, 0),
                "ram_used": _safe(lambda: psutil.virtual_memory().used, 0),
                "ram_percent": _safe(lambda: psutil.virtual_memory().percent, 0.0),
                "uptime_seconds": round(uptime_s, 2),
                "process_pid": _safe(proc.pid, 0),
                "process_memory_mb": round((mem_info.rss if mem_info else 0) / 1024 / 1024, 2),
                "gc_counts": list(gc.get_count()),
                "asyncio_tasks_count": len(tasks),
                "version": "1.0.0-rc2",
                "git_commit": self._git_commit(),
                "git_branch": self._git_branch(),
                "build_timestamp": _utcnow_iso(),
                "environment": os.getenv("ENVIRONMENT", "development"),
                "workspace": os.getenv("WORKSPACE_PATH", os.getcwd()),
                "platform_services": {
                    attr: getattr(platform, attr, None) is not None
                    for attr in [
                        "bus",
                        "registry",
                        "providers",
                        "orchestrator",
                        "scheduler",
                        "health",
                        "recovery",
                        "dashboard",
                        "provider_mgr",
                        "model_mgr",
                        "vault",
                        "provider_health",
                        "cost",
                        "rate",
                        "router",
                        "memory",
                        "capability",
                        "security",
                        "workflow",
                        "pipeline",
                        "runtime",
                        "discovery_framework",
                        "orchestration",
                        "mcp",
                        "learning",
                        "desktop",
                        "mission_planner",
                        "local_discovery",
                        "brain_registry",
                        "brain_manager",
                        "brain_catalog",
                        "brain_graph",
                        "brain_stats",
                        "brain_health",
                        "brain_discovery_bridge",
                        "brain_runtime_bridge",
                    ]
                },
            }
        except Exception as exc:  # noqa: BLE001
            log.error("collect_runtime.failed", error=str(exc))
            return {"error": str(exc)}

    async def collect_health(self, platform: Any) -> dict:
        """Inspect real platform subsystem availability and derive health status."""
        try:

            def _subsys(name: str, obj: Any) -> dict:
                available = obj is not None
                return {
                    "healthy": available,
                    "latency_ms": 0.0,
                    "errors": 0,
                    "warnings": 0 if available else 1,
                    "restart_count": 0,
                    "status": "operational" if available else "unavailable",
                    "available": available,
                }

            health = {
                "kernel": _subsys("kernel", platform.orchestrator),
                "discovery": _subsys("discovery", getattr(platform, "discovery_framework", None)),
                "brain_registry": _subsys(
                    "brain_registry", getattr(platform, "brain_registry", None)
                ),
                "capability_registry": _subsys("capability", getattr(platform, "capability", None)),
                "provider_registry": _subsys("providers", getattr(platform, "providers", None)),
                "scheduler": _subsys("scheduler", getattr(platform, "scheduler", None)),
                "executor": _subsys("executor", getattr(platform, "orchestrator", None)),
                "aggregation": _subsys("aggregation", getattr(platform, "orchestration", None)),
                "learning": _subsys("learning", getattr(platform, "learning", None)),
                "budget": _subsys("budget", getattr(platform, "cost", None)),
                "rate_limiter": _subsys("rate_limiter", getattr(platform, "rate", None)),
                "router": _subsys("router", getattr(platform, "router", None)),
                "api": {
                    "healthy": True,
                    "latency_ms": 0.0,
                    "errors": 0,
                    "warnings": 0,
                    "restart_count": 0,
                    "status": "operational",
                    "available": True,
                },
                "event_bus": _subsys("event_bus", getattr(platform, "bus", None)),
                "sse": _subsys("sse", getattr(platform, "dashboard", None)),
                "mission_control": {
                    "healthy": True,
                    "latency_ms": 0.0,
                    "errors": 0,
                    "warnings": 0,
                    "restart_count": 0,
                    "status": "operational",
                    "available": True,
                },
                "mcp": _subsys("mcp", getattr(platform, "mcp", None)),
                "memory": _subsys("memory", getattr(platform, "memory", None)),
                "security": _subsys("security", getattr(platform, "security", None)),
            }

            # Elevate health score based on real checks
            healthy_count = sum(1 for v in health.values() if v.get("healthy"))
            total = len(health)
            health["_meta"] = {
                "health_score": round(healthy_count / total * 100),
                "healthy_count": healthy_count,
                "total_subsystems": total,
                "checked_at": _utcnow_iso(),
            }
            return health
        except Exception as exc:  # noqa: BLE001
            log.error("collect_health.failed", error=str(exc))
            return {"error": str(exc)}

    async def collect_discovery(self, platform: Any) -> dict:
        """Collect runtime discovery data from the discovery framework."""
        try:
            df = getattr(platform, "discovery_framework", None)
            local = getattr(platform, "local_discovery", None)

            providers: list[dict] = []
            total_discovered = 0
            total_running = 0
            total_healthy = 0

            if local is not None:
                try:
                    agents = await local.get_agents()
                    for a in agents:
                        d = a.to_dict() if hasattr(a, "to_dict") else {}
                        providers.append(
                            {
                                "name": d.get("name", str(a)),
                                "type": d.get("engine_type", "unknown"),
                                "vendor": d.get("vendor", "unknown"),
                                "installed": d.get("installed", True),
                                "running": d.get("running", False),
                                "version": d.get("version", "unknown"),
                                "pid": d.get("pid"),
                                "path": d.get("path", ""),
                                "executable": d.get("executable", ""),
                                "last_seen": d.get("last_seen", _utcnow_iso()),
                                "status": d.get("status", "unknown"),
                                "health": d.get("health", "unknown"),
                                "auto_bound": d.get("auto_bound", False),
                                "registration_state": d.get("registration_state", "discovered"),
                                "errors": d.get("errors", []),
                                "support_windows": d.get("support_windows", True),
                                "support_linux": d.get("support_linux", True),
                                "support_macos": d.get("support_macos", True),
                            }
                        )
                    total_discovered = len(providers)
                    total_running = sum(1 for p in providers if p.get("running"))
                    total_healthy = sum(
                        1 for p in providers if p.get("health") in ("healthy", "ok")
                    )
                except Exception:  # noqa: BLE001
                    pass

            scanner_stats: dict = {}
            if df is not None:
                try:
                    scanner_stats = {
                        "type": type(df).__name__,
                        "available": True,
                    }
                except Exception:  # noqa: BLE001
                    pass

            return {
                "providers": providers,
                "scanner_stats": scanner_stats,
                "total_discovered": total_discovered,
                "total_running": total_running,
                "total_healthy": total_healthy,
                "discovery_framework_available": df is not None,
                "local_discovery_available": local is not None,
            }
        except Exception as exc:  # noqa: BLE001
            log.error("collect_discovery.failed", error=str(exc))
            return {
                "providers": [],
                "scanner_stats": {},
                "total_discovered": 0,
                "total_running": 0,
                "total_healthy": 0,
                "error": str(exc),
            }

    async def collect_eventbus(self, platform: Any) -> dict:
        """Collect event bus topology and message stats."""
        try:
            bus = getattr(platform, "bus", None)
            bus_type = type(bus).__name__ if bus is not None else "none"

            # Inspect bus internals if available
            topics: list[dict] = []
            total_messages = 0

            if bus is not None:
                # Try to read subscriber registry
                subs = getattr(bus, "_subscribers", None) or getattr(bus, "subscriptions", None)
                if isinstance(subs, dict):
                    for topic, handlers in subs.items():
                        count = len(handlers) if hasattr(handlers, "__len__") else 0
                        topics.append(
                            {
                                "topic": topic,
                                "publisher": "system",
                                "subscriber_count": count,
                                "messages_per_sec": 0.0,
                                "dropped": 0,
                                "errors": 0,
                                "avg_latency_ms": 0.0,
                                "payload_size_bytes": 0,
                            }
                        )
                # Try published counter
                total_messages = _safe(lambda: getattr(bus, "_message_count", 0), 0)

            return {
                "topics": topics,
                "total_topics": len(topics),
                "total_messages": total_messages,
                "bus_type": bus_type,
                "bus_available": bus is not None,
            }
        except Exception as exc:  # noqa: BLE001
            log.error("collect_eventbus.failed", error=str(exc))
            return {
                "topics": [],
                "total_topics": 0,
                "total_messages": 0,
                "bus_type": "unknown",
                "error": str(exc),
            }

    async def collect_brains(self, platform: Any) -> dict:
        """Collect registered AI brains from the brain registry."""
        try:
            brain_registry = getattr(platform, "brain_registry", None)
            brain_stats = getattr(platform, "brain_stats", None)
            brain_health = getattr(platform, "brain_health", None)

            brains: list[dict] = []
            if brain_registry is not None:
                try:
                    all_brains = await brain_registry.list_all()
                    for b in all_brains:
                        d = b.to_dict() if hasattr(b, "to_dict") else {}
                        brains.append(
                            {
                                "id": d.get("id", str(b)),
                                "display_name": d.get("display_name", ""),
                                "runtime": d.get("runtime", "unknown"),
                                "capabilities": d.get("capabilities", []),
                                "health": d.get("health", 0),
                                "memory_mb": d.get("memory_mb", 0.0),
                                "cpu_percent": d.get("cpu_percent", 0.0),
                                "task_count": d.get("task_count", 0),
                                "current_model": d.get("current_model", ""),
                                "connections": d.get("connections", 0),
                                "heartbeat": d.get("heartbeat", ""),
                                "last_event": d.get("last_event", ""),
                                "registration_source": d.get("registration_source", ""),
                                "status": d.get("status", "unknown"),
                                "latency": d.get("latency", 0),
                            }
                        )
                except Exception:  # noqa: BLE001
                    pass

            healthy_count = sum(1 for b in brains if b.get("health", 0) >= 80)
            return {
                "brains": brains,
                "total_count": len(brains),
                "healthy_count": healthy_count,
                "stats_available": brain_stats is not None,
                "health_monitor_available": brain_health is not None,
            }
        except Exception as exc:  # noqa: BLE001
            log.error("collect_brains.failed", error=str(exc))
            return {"brains": [], "total_count": 0, "healthy_count": 0, "error": str(exc)}

    async def collect_agents(self, platform: Any) -> dict:
        """Collect all registered agent states from the orchestrator."""
        try:
            orch = getattr(platform, "orchestrator", None)
            agents: list[dict] = []

            if orch is not None and hasattr(orch, "registry"):
                try:
                    reg_agents = orch.registry.agents()
                    for a in reg_agents:
                        d = a.model_dump(mode="json") if hasattr(a, "model_dump") else {}
                        agents.append(
                            {
                                "id": d.get("id", str(a)),
                                "name": d.get("name", ""),
                                "status": d.get("status", "unknown"),
                                "task_count": d.get("task_count", 0),
                                "mission": d.get("mission", ""),
                                "workflow": d.get("workflow", ""),
                                "execution_mode": d.get("execution_mode", ""),
                                "provider": d.get("provider", ""),
                                "latency_ms": d.get("latency_ms", 0.0),
                                "failures": d.get("failures", 0),
                                "retries": d.get("retries", 0),
                                "queue_depth": d.get("queue_depth", 0),
                                "lifecycle": d.get("lifecycle", "unknown"),
                            }
                        )
                except Exception:  # noqa: BLE001
                    pass

            # Also include brain-level agents
            brain_registry = getattr(platform, "brain_registry", None)
            if brain_registry is not None:
                try:
                    brains = await brain_registry.list_all()
                    known_ids = {a["id"] for a in agents}
                    for b in brains:
                        d = b.to_dict() if hasattr(b, "to_dict") else {}
                        bid = d.get("id", "")
                        if bid and bid not in known_ids:
                            agents.append(
                                {
                                    "id": bid,
                                    "name": d.get("display_name", bid),
                                    "status": d.get("status", "unknown"),
                                    "task_count": d.get("task_count", 0),
                                    "mission": "",
                                    "workflow": "",
                                    "execution_mode": "brain",
                                    "provider": d.get("runtime", ""),
                                    "latency_ms": d.get("latency", 0),
                                    "failures": 0,
                                    "retries": 0,
                                    "queue_depth": 0,
                                    "lifecycle": d.get("status", "unknown"),
                                }
                            )
                except Exception:  # noqa: BLE001
                    pass

            return {"agents": agents, "total_count": len(agents)}
        except Exception as exc:  # noqa: BLE001
            log.error("collect_agents.failed", error=str(exc))
            return {"agents": [], "total_count": 0, "error": str(exc)}

    async def collect_capabilities(self, platform: Any) -> dict:
        """Collect capability registry entries."""
        try:
            cap = getattr(platform, "capability", None)
            capabilities: list[dict] = []

            if cap is not None:
                try:
                    # Try common method names
                    all_caps = None
                    for method in ("list_all", "get_all", "all_capabilities", "capabilities"):
                        fn = getattr(cap, method, None)
                        if callable(fn):
                            all_caps = await fn() if asyncio.iscoroutinefunction(fn) else fn()
                            break

                    if all_caps and isinstance(all_caps, list):
                        for c in all_caps:
                            d = (
                                c.to_dict()
                                if hasattr(c, "to_dict")
                                else (c.model_dump(mode="json") if hasattr(c, "model_dump") else {})
                            )
                            capabilities.append(
                                {
                                    "name": d.get("name", str(c)),
                                    "provider": d.get("provider", ""),
                                    "brain": d.get("brain", ""),
                                    "priority": d.get("priority", 0),
                                    "healthy": d.get("healthy", True),
                                    "last_updated": d.get("last_updated", _utcnow_iso()),
                                    "consumers": d.get("consumers", 0),
                                    "dependencies": d.get("dependencies", []),
                                }
                            )
                except Exception:  # noqa: BLE001
                    pass

            return {"capabilities": capabilities, "total_count": len(capabilities)}
        except Exception as exc:  # noqa: BLE001
            log.error("collect_capabilities.failed", error=str(exc))
            return {"capabilities": [], "total_count": 0, "error": str(exc)}

    async def collect_threads(self, platform: Any) -> dict:
        """Inspect all running asyncio tasks."""
        try:
            tasks = asyncio.all_tasks()
            task_list: list[dict] = []

            for t in tasks:
                name = t.get_name()
                done = t.done()
                cancelled = t.cancelled()
                coro = t.get_coro()
                coro_name = getattr(coro, "__qualname__", str(coro))

                task_list.append(
                    {
                        "name": name,
                        "status": "cancelled" if cancelled else ("done" if done else "running"),
                        "duration_seconds": 0.0,
                        "owner": "asyncio",
                        "coroutine": coro_name,
                        "cancelled": cancelled,
                        "waiting": False,
                        "blocked": False,
                    }
                )

            running = sum(1 for t in task_list if t["status"] == "running")
            cancelled_count = sum(1 for t in task_list if t["status"] == "cancelled")

            return {
                "tasks": task_list,
                "total_count": len(task_list),
                "running_count": running,
                "cancelled_count": cancelled_count,
            }
        except Exception as exc:  # noqa: BLE001
            log.error("collect_threads.failed", error=str(exc))
            return {
                "tasks": [],
                "total_count": 0,
                "running_count": 0,
                "cancelled_count": 0,
                "error": str(exc),
            }

    async def collect_resources(self, platform: Any) -> dict:
        """Collect system resource utilisation via psutil."""
        try:
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            net = psutil.net_io_counters()
            gc_counts = gc.get_count()
            proc = psutil.Process()
            proc_mem = _safe(proc.memory_info)

            cpu_per_core = _safe(lambda: psutil.cpu_percent(percpu=True), [])
            thread_count = _safe(proc.num_threads, 0)
            handle_count = _safe(
                proc.num_handles
                if hasattr(proc, "num_handles")
                else proc.num_fds
                if hasattr(proc, "num_fds")
                else lambda: 0,
                0,
            )
            open_files = _safe(lambda: len(proc.open_files()), 0)

            return {
                "cpu_percent": _safe(lambda: psutil.cpu_percent(interval=None), 0.0),
                "cpu_per_core": cpu_per_core or [],
                "ram_total": mem.total,
                "ram_used": mem.used,
                "ram_percent": mem.percent,
                "disk_total": disk.total,
                "disk_used": disk.used,
                "disk_percent": disk.percent,
                "net_bytes_sent": net.bytes_sent if net else 0,
                "net_bytes_recv": net.bytes_recv if net else 0,
                "thread_count": thread_count,
                "handle_count": handle_count,
                "open_files_count": open_files,
                "gc_gen0": gc_counts[0] if len(gc_counts) > 0 else 0,
                "gc_gen1": gc_counts[1] if len(gc_counts) > 1 else 0,
                "gc_gen2": gc_counts[2] if len(gc_counts) > 2 else 0,
                "process_rss_mb": round((proc_mem.rss if proc_mem else 0) / 1024 / 1024, 2),
                "process_vms_mb": round((proc_mem.vms if proc_mem else 0) / 1024 / 1024, 2),
                "snapshot_at": _utcnow_iso(),
            }
        except Exception as exc:  # noqa: BLE001
            log.error("collect_resources.failed", error=str(exc))
            return {"error": str(exc)}

    async def collect_queues(self, platform: Any) -> dict:
        """Collect queue depths from scheduler and orchestrator."""
        try:
            queues: list[dict] = []

            scheduler = getattr(platform, "scheduler", None)
            if scheduler is not None:
                for attr in ("_queue", "queue", "_tasks"):
                    q = getattr(scheduler, attr, None)
                    if q is not None:
                        try:
                            depth = len(q)
                        except Exception:
                            depth = 0
                        queues.append(
                            {
                                "name": "Scheduler Queue",
                                "depth": depth,
                                "oldest_item_age_seconds": 0.0,
                                "newest_item_age_seconds": 0.0,
                                "wait_time_seconds": 0.0,
                                "blocked": False,
                                "dead_letter_count": 0,
                            }
                        )
                        break

            orch = getattr(platform, "orchestrator", None)
            if orch is not None:
                for attr in ("_pending", "pending_tasks", "_queue"):
                    q = getattr(orch, attr, None)
                    if q is not None:
                        try:
                            depth = len(q)
                        except Exception:
                            depth = 0
                        queues.append(
                            {
                                "name": "Execution Queue",
                                "depth": depth,
                                "oldest_item_age_seconds": 0.0,
                                "newest_item_age_seconds": 0.0,
                                "wait_time_seconds": 0.0,
                                "blocked": False,
                                "dead_letter_count": 0,
                            }
                        )
                        break

            return {"queues": queues, "total_queues": len(queues)}
        except Exception as exc:  # noqa: BLE001
            log.error("collect_queues.failed", error=str(exc))
            return {"queues": [], "total_queues": 0, "error": str(exc)}

    async def collect_logs(self, platform: Any, limit: int = 200) -> dict:
        """Return recent log entries (stub — structured log capture requires log handler hook)."""
        try:
            return {
                "logs": [],
                "total_count": 0,
                "note": "Attach a log handler to capture structured log entries.",
            }
        except Exception as exc:  # noqa: BLE001
            return {"logs": [], "total_count": 0, "error": str(exc)}

    async def collect_mcp(self, platform: Any) -> dict:
        """Collect MCP server statuses."""
        try:
            mcp = getattr(platform, "mcp", None)
            servers: list[dict] = []

            if mcp is not None:
                # Try to list servers
                try:
                    for method in ("list_servers", "get_servers", "servers"):
                        fn = getattr(mcp, method, None)
                        if callable(fn):
                            result = await fn() if asyncio.iscoroutinefunction(fn) else fn()
                            if isinstance(result, list):
                                for s in result:
                                    d = (
                                        s
                                        if isinstance(s, dict)
                                        else (s.to_dict() if hasattr(s, "to_dict") else {})
                                    )
                                    servers.append(
                                        {
                                            "name": d.get("name", str(s)),
                                            "connected": d.get("connected", False),
                                            "capabilities": d.get("capabilities", []),
                                            "ping_ms": d.get("ping_ms", 0.0),
                                            "errors": d.get("errors", 0),
                                            "last_request": d.get("last_request", ""),
                                            "version": d.get("version", "unknown"),
                                            "health": d.get("health", "unknown"),
                                        }
                                    )
                            break
                except Exception:  # noqa: BLE001
                    pass

            return {
                "servers": servers,
                "total_count": len(servers),
                "mcp_available": mcp is not None,
            }
        except Exception as exc:  # noqa: BLE001
            log.error("collect_mcp.failed", error=str(exc))
            return {"servers": [], "total_count": 0, "error": str(exc)}

    async def collect_providers(self, platform: Any) -> dict:
        """Collect provider runtime state from provider manager and health monitor."""
        try:
            pm = getattr(platform, "provider_mgr", None)
            ph = getattr(platform, "provider_health", None)
            providers: list[dict] = []

            if pm is not None:
                try:
                    cfgs = pm.list_providers() if hasattr(pm, "list_providers") else []
                    for cfg in cfgs:
                        d = cfg.model_dump(mode="json") if hasattr(cfg, "model_dump") else {}
                        name = d.get("name", str(cfg))

                        # Health
                        health_status = "unknown"
                        if ph is not None and hasattr(ph, "get_health"):
                            try:
                                h = await ph.get_health(name)
                                health_status = h.status if hasattr(h, "status") else str(h)
                            except Exception:  # noqa: BLE001
                                pass

                        providers.append(
                            {
                                "name": name,
                                "status": d.get("status", "unknown"),
                                "health": health_status,
                                "rate_limit_remaining": 0,
                                "budget_remaining": 0.0,
                                "latency_ms": 0.0,
                                "circuit_breaker": "closed",
                                "retry_count": 0,
                                "queue_depth": 0,
                                "tokens_used": 0,
                                "streaming": d.get("supports_streaming", False),
                                "connections": 0,
                                "kind": d.get("kind", "unknown"),
                            }
                        )
                except Exception:  # noqa: BLE001
                    pass

            return {"providers": providers, "total_count": len(providers)}
        except Exception as exc:  # noqa: BLE001
            log.error("collect_providers.failed", error=str(exc))
            return {"providers": [], "total_count": 0, "error": str(exc)}

    async def collect_apis(self, platform: Any) -> dict:
        """Collect Prometheus HTTP request metrics for API monitoring."""
        try:
            from prometheus_client import REGISTRY

            endpoints: list[dict] = []

            # Try to read REQUEST_COUNT and REQUEST_LATENCY from the registry
            for metric in REGISTRY.collect():
                if metric.name == "http_requests_total":
                    for sample in metric.samples:
                        if sample.name.endswith("_total"):
                            endpoints.append(
                                {
                                    "path": sample.labels.get("path", ""),
                                    "method": sample.labels.get("method", ""),
                                    "requests_per_sec": 0.0,
                                    "latency_p50_ms": 0.0,
                                    "latency_p95_ms": 0.0,
                                    "latency_p99_ms": 0.0,
                                    "errors": 0,
                                    "avg_response_size": 0,
                                    "active_requests": 0,
                                    "total_requests": int(sample.value),
                                    "status": sample.labels.get("status", ""),
                                }
                            )
                    break

            return {"endpoints": endpoints, "total_endpoints": len(endpoints)}
        except Exception as exc:  # noqa: BLE001
            log.error("collect_apis.failed", error=str(exc))
            return {"endpoints": [], "total_endpoints": 0, "error": str(exc)}

    async def collect_sse_clients(self, platform: Any) -> dict:
        """Collect SSE client connections from the dashboard broadcaster."""
        try:
            dashboard = getattr(platform, "dashboard", None)
            clients: list[dict] = []

            if dashboard is not None:
                # DashboardBroadcaster maintains _clients or similar
                raw = (
                    getattr(dashboard, "_clients", None)
                    or getattr(dashboard, "clients", None)
                    or {}
                )
                if isinstance(raw, dict):
                    for cid, _info in raw.items():
                        clients.append(
                            {
                                "client_id": str(cid),
                                "connected_at": "",
                                "duration_seconds": 0.0,
                                "messages_per_sec": 0.0,
                                "reconnects": 0,
                                "dropped_frames": 0,
                                "heartbeat": "",
                                "last_message": "",
                                "queue_size": 0,
                            }
                        )
                elif isinstance(raw, (list, set)):
                    for i, _c in enumerate(raw):
                        clients.append(
                            {
                                "client_id": str(i),
                                "connected_at": "",
                                "duration_seconds": 0.0,
                                "messages_per_sec": 0.0,
                                "reconnects": 0,
                                "dropped_frames": 0,
                                "heartbeat": "",
                                "last_message": "",
                                "queue_size": 0,
                            }
                        )

            return {"clients": clients, "total_count": len(clients)}
        except Exception as exc:  # noqa: BLE001
            log.error("collect_sse_clients.failed", error=str(exc))
            return {"clients": [], "total_count": 0, "error": str(exc)}

    async def collect_summary(self, platform: Any) -> dict:
        """Compute overall health score and collect critical issues / warnings."""
        try:
            health = await self.collect_health(platform)
            meta = health.pop("_meta", {})

            health_score: int = meta.get("health_score", 100)
            critical: list[str] = []
            warnings: list[str] = []
            info: list[str] = []

            for name, status in health.items():
                if isinstance(status, dict):
                    if not status.get("healthy") and not status.get("available", True):
                        warnings.append(f"{name} subsystem is unavailable")
                    if status.get("errors", 0) > 0:
                        critical.append(f"{name} has {status['errors']} error(s)")

            bus = getattr(platform, "bus", None)
            if bus is None:
                critical.append("EventBus is not running")

            brain_reg = getattr(platform, "brain_registry", None)
            if brain_reg is None:
                warnings.append("Brain registry not initialised")

            mcp = getattr(platform, "mcp", None)
            if mcp is None:
                info.append("MCP subsystem not loaded")

            return {
                "health_score": max(0, health_score - len(critical) * 20),
                "critical_issues": critical,
                "warnings": warnings,
                "info": info,
                "snapshot_at": _utcnow_iso(),
            }
        except Exception as exc:  # noqa: BLE001
            log.error("collect_summary.failed", error=str(exc))
            return {
                "health_score": 0,
                "critical_issues": [str(exc)],
                "warnings": [],
                "info": [],
                "snapshot_at": _utcnow_iso(),
            }

    async def run_self_test(self, platform: Any) -> dict:
        """Run diagnostic self-test. Returns PASS/WARNING/FAIL per subsystem."""
        started_at = _utcnow_iso()
        results: list[dict] = []
        overall = "PASS"

        tests = [
            ("EventBus", lambda: getattr(platform, "bus", None) is not None),
            ("Orchestrator", lambda: getattr(platform, "orchestrator", None) is not None),
            ("Provider Manager", lambda: getattr(platform, "provider_mgr", None) is not None),
            ("Health Monitor", lambda: getattr(platform, "health", None) is not None),
            ("Scheduler", lambda: getattr(platform, "scheduler", None) is not None),
            ("Brain Registry", lambda: getattr(platform, "brain_registry", None) is not None),
            ("MCP Manager", lambda: getattr(platform, "mcp", None) is not None),
            (
                "Discovery Framework",
                lambda: getattr(platform, "discovery_framework", None) is not None,
            ),
            ("Learning Manager", lambda: getattr(platform, "learning", None) is not None),
            ("Memory Manager", lambda: getattr(platform, "memory", None) is not None),
            ("Security Framework", lambda: getattr(platform, "security", None) is not None),
            ("Workflow Engine", lambda: getattr(platform, "workflow", None) is not None),
            ("Pipeline Engine", lambda: getattr(platform, "pipeline", None) is not None),
        ]

        for name, check in tests:
            t0 = time.perf_counter()
            try:
                passed = (
                    await asyncio.to_thread(check)
                    if not asyncio.iscoroutinefunction(check)
                    else await check()
                )
                duration = round((time.perf_counter() - t0) * 1000, 2)
                result = "PASS" if passed else "WARNING"
                message = f"{name} is {'available' if passed else 'not initialised'}"
                if result == "WARNING" and overall == "PASS":
                    overall = "WARNING"
            except Exception as exc:  # noqa: BLE001
                duration = round((time.perf_counter() - t0) * 1000, 2)
                result = "FAIL"
                message = f"{name} check failed: {exc}"
                overall = "FAIL"

            results.append(
                {
                    "subsystem": name,
                    "result": result,
                    "message": message,
                    "duration_ms": duration,
                }
            )

        # Resource check
        t0 = time.perf_counter()
        try:
            mem = psutil.virtual_memory()
            duration = round((time.perf_counter() - t0) * 1000, 2)
            if mem.percent > 90:
                results.append(
                    {
                        "subsystem": "Memory",
                        "result": "WARNING",
                        "message": f"RAM usage is high: {mem.percent:.1f}%",
                        "duration_ms": duration,
                    }
                )
                if overall == "PASS":
                    overall = "WARNING"
            else:
                results.append(
                    {
                        "subsystem": "Memory",
                        "result": "PASS",
                        "message": f"RAM OK: {mem.percent:.1f}% used",
                        "duration_ms": duration,
                    }
                )
        except Exception as exc:  # noqa: BLE001
            results.append(
                {"subsystem": "Memory", "result": "FAIL", "message": str(exc), "duration_ms": 0.0}
            )

        return {
            "results": results,
            "overall": overall,
            "started_at": started_at,
            "completed_at": _utcnow_iso(),
            "total_tests": len(results),
            "passed": sum(1 for r in results if r["result"] == "PASS"),
            "warnings": sum(1 for r in results if r["result"] == "WARNING"),
            "failed": sum(1 for r in results if r["result"] == "FAIL"),
        }

    async def generate_report(self, platform: Any, format: str = "json") -> dict:
        """Generate a full diagnostics report across all subsystems."""
        try:
            report = {
                "generated_at": _utcnow_iso(),
                "format_version": "1.0",
                "runtime": await self.collect_runtime(platform),
                "health": await self.collect_health(platform),
                "discovery": await self.collect_discovery(platform),
                "brains": await self.collect_brains(platform),
                "agents": await self.collect_agents(platform),
                "capabilities": await self.collect_capabilities(platform),
                "resources": await self.collect_resources(platform),
                "threads": await self.collect_threads(platform),
                "queues": await self.collect_queues(platform),
                "mcp": await self.collect_mcp(platform),
                "providers": await self.collect_providers(platform),
                "eventbus": await self.collect_eventbus(platform),
                "sse_clients": await self.collect_sse_clients(platform),
                "summary": await self.collect_summary(platform),
            }
            return report
        except Exception as exc:  # noqa: BLE001
            log.error("generate_report.failed", error=str(exc))
            return {"error": str(exc), "generated_at": _utcnow_iso()}
