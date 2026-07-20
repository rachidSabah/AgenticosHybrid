"""
MCP REST API

Complete REST API for MCP server lifecycle, tools, resources, prompts,
sessions, health, and telemetry management.
"""

from fastapi import APIRouter, HTTPException

from agentic_os.core.mcp.health import MCPHealthMonitor
from agentic_os.core.mcp.manager import MCPManager
from agentic_os.core.mcp.registry import MCPRegistryImpl
from agentic_os.core.mcp.session import MCPSessionManager
from agentic_os.core.mcp.telemetry import MCPTelemetry
from agentic_os.domain.mcp import MCPServerStatus, MCPSessionStatus
from agentic_os.ports.mcp import MCPServerCreate, MCPServerUpdate, MCPToolInvoke

mcp_router = APIRouter(prefix="/api/mcp", tags=["MCP"])


def create_mcp_router(
    registry: MCPRegistryImpl,
    manager: MCPManager,
    session_manager: MCPSessionManager,
    health_monitor: MCPHealthMonitor,
    telemetry: MCPTelemetry,
) -> APIRouter:
    """Create the MCP REST API router with all endpoints."""

    # ── Server Lifecycle ────────────────────────────────────────────────

    @mcp_router.post("/servers", status_code=201)
    async def register_server(data: MCPServerCreate):
        """Register a new MCP server."""
        return await registry.register_server(data)

    @mcp_router.get("/servers")
    async def list_servers(
        status: str | None = None,
        enabled_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ):
        """List all MCP servers."""
        status_filter = None
        if status:
            try:
                status_filter = MCPServerStatus(status)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid status: {status}") from None

        return await registry.list_servers(
            status=status_filter,
            enabled_only=enabled_only,
            limit=limit,
            offset=offset,
        )

    @mcp_router.get("/servers/{server_id}")
    async def get_server(server_id: str):
        """Get a specific MCP server."""
        detail = await registry.get_server(server_id)
        if not detail:
            raise HTTPException(status_code=404, detail="Server not found") from None
        return detail

    @mcp_router.put("/servers/{server_id}")
    async def update_server(server_id: str, data: MCPServerUpdate):
        """Update an MCP server configuration."""
        try:
            return await registry.update_server(server_id, data)
        except KeyError:
            raise HTTPException(status_code=404, detail="Server not found") from None

    @mcp_router.delete("/servers/{server_id}")
    async def delete_server(server_id: str):
        """Delete an MCP server registration."""
        deleted = await registry.delete_server(server_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Server not found") from None
        return {"deleted": server_id}

    @mcp_router.post("/servers/{server_id}/start")
    async def start_server(server_id: str):
        """Start an MCP server."""
        try:
            return await registry.start_server(server_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Server not found") from None

    @mcp_router.post("/servers/{server_id}/stop")
    async def stop_server(server_id: str):
        """Stop an MCP server."""
        try:
            return await registry.stop_server(server_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Server not found") from None

    @mcp_router.post("/servers/{server_id}/restart")
    async def restart_server(server_id: str):
        """Restart an MCP server."""
        try:
            return await registry.restart_server(server_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Server not found") from None
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from None

    @mcp_router.post("/servers/{server_id}/reload")
    async def reload_server(server_id: str):
        """Hot reload an MCP server."""
        try:
            return await registry.reload_server(server_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Server not found") from None

    # ── Tool Operations ───────────────────────────────────────────────

    @mcp_router.get("/servers/{server_id}/tools")
    async def list_tools(server_id: str):
        """List available tools for a server."""
        detail = await registry.get_server(server_id)
        if not detail:
            raise HTTPException(status_code=404, detail="Server not found") from None
        return detail.tools

    @mcp_router.post("/servers/{server_id}/tools/discover")
    async def discover_tools(server_id: str):
        """Discover tools from an MCP server."""
        detail = await registry.get_server(server_id)
        if not detail:
            raise HTTPException(status_code=404, detail="Server not found") from None

        tools = await registry.discover_tools(server_id)
        return tools

    @mcp_router.post("/servers/{server_id}/tools/invoke")
    async def invoke_tool(server_id: str, data: dict):
        """Invoke a tool on an MCP server."""
        tool_invoke = MCPToolInvoke(
            server_id=server_id,
            tool=data.get("tool"),
            args=data.get("args", {}),
            timeout_seconds=data.get("timeout_seconds"),
        )

        try:
            return await registry.invoke_tool(tool_invoke)
        except KeyError:
            raise HTTPException(status_code=404, detail="Server not found") from None
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from None
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from None

    # ── Resource Operations ───────────────────────────────────────────

    @mcp_router.get("/servers/{server_id}/resources")
    async def list_resources(server_id: str):
        """List available resources for a server."""
        try:
            resources = await registry.list_server_resources(server_id)
            return resources
        except KeyError:
            raise HTTPException(status_code=404, detail="Server not found") from None
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from None

    @mcp_router.get("/servers/{server_id}/resources/{uri:path}")
    async def read_resource(server_id: str, uri: str):
        """Read a specific resource."""
        try:
            return await registry.read_server_resource(server_id, uri)
        except KeyError:
            raise HTTPException(status_code=404, detail="Server not found") from None
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from None

    @mcp_router.post("/servers/{server_id}/resources/{uri:path}/subscribe")
    async def subscribe_resource(server_id: str, uri: str):
        """Subscribe to resource changes."""
        try:
            success = await registry.subscribe_server_resource(server_id, uri)
            return {"success": success, "uri": uri}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from None

    @mcp_router.delete("/servers/{server_id}/resources/{uri:path}/subscribe")
    async def unsubscribe_resource(server_id: str, uri: str):
        """Unsubscribe from resource changes."""
        try:
            success = await registry.unsubscribe_server_resource(server_id, uri)
            return {"success": success, "uri": uri}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from None

    # ── Prompt Operations ─────────────────────────────────────────────

    @mcp_router.get("/servers/{server_id}/prompts")
    async def list_prompts(server_id: str):
        """List available prompts for a server."""
        try:
            prompts = await registry.list_server_prompts(server_id)
            return prompts
        except KeyError:
            raise HTTPException(status_code=404, detail="Server not found") from None
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from None

    @mcp_router.post("/servers/{server_id}/prompts/{name}")
    async def get_prompt(server_id: str, name: str, arguments: dict | None = None):
        """Get a prompt with arguments."""
        try:
            result = await registry.get_server_prompt(server_id, name, arguments)
            return result
        except KeyError:
            raise HTTPException(status_code=404, detail="Server not found") from None
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from None

    # ── Session Operations ─────────────────────────────────────────────

    @mcp_router.get("/sessions")
    async def list_sessions(server_id: str | None = None, status: str | None = None):
        """List MCP sessions."""
        status_filter = None
        if status:
            try:
                status_filter = MCPSessionStatus(status)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid status: {status}") from None

        return await session_manager.list_sessions(server_id=server_id, status=status_filter)

    @mcp_router.get("/sessions/{session_id}")
    async def get_session(session_id: str):
        """Get a specific session."""
        session = await session_manager.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        return session

    @mcp_router.delete("/sessions/{session_id}")
    async def close_session(session_id: str):
        """Close a session."""
        success = await session_manager.close_session(session_id)
        if not success:
            raise HTTPException(status_code=404, detail="Session not found")
        return {"closed": session_id}

    @mcp_router.post("/sessions/cleanup")
    async def cleanup_sessions():
        """Clean up expired and closed sessions."""
        expired_count = await session_manager.expire_sessions()
        closed_count = await session_manager.cleanup_closed_sessions()
        return {
            "expired": expired_count,
            "closed_cleaned": closed_count,
        }

    @mcp_router.get("/sessions/stats")
    async def session_stats():
        """Get session statistics."""
        return session_manager.get_session_stats()

    # ── Health Operations ─────────────────────────────────────────────

    @mcp_router.get("/health")
    async def get_health_summary():
        """Get health summary for all servers."""
        return health_monitor.get_summary()

    @mcp_router.get("/health/{server_id}")
    async def get_server_health(server_id: str):
        """Get health status for a specific server."""
        status = health_monitor.get_health(server_id)
        if status is None:
            raise HTTPException(status_code=404, detail="Server not found") from None
        return {
            "server_id": server_id,
            "status": status.value,
            "details": health_monitor.get_health_details(server_id),
        }

    @mcp_router.post("/health/{server_id}/check")
    async def check_server_health(server_id: str):
        """Perform a health check on a server."""
        try:
            result = await health_monitor.check_server(server_id)
            return {
                "server_id": server_id,
                "status": result.status.value,
                "latency_ms": result.latency_ms,
                "details": result.details,
                "error": result.error,
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from None

    @mcp_router.get("/health/degraded")
    async def get_degraded_servers():
        """Get list of servers in degraded state."""
        return {"servers": health_monitor.get_degraded_servers()}

    @mcp_router.get("/health/unhealthy")
    async def get_unhealthy_servers():
        """Get list of servers past failure threshold."""
        return {"servers": health_monitor.get_unhealthy_servers()}

    # ── Telemetry Operations ───────────────────────────────────────────

    @mcp_router.get("/telemetry/summary")
    async def get_telemetry_summary():
        """Get telemetry summary."""
        return telemetry.get_summary()

    @mcp_router.get("/telemetry/snapshot")
    async def get_telemetry_snapshot():
        """Get full telemetry snapshot."""
        return telemetry.get_snapshot()

    @mcp_router.get("/telemetry/latency")
    async def get_latency_distribution():
        """Get latency distribution percentiles."""
        return telemetry.get_latency_distribution()

    @mcp_router.get("/telemetry/errors")
    async def get_recent_errors(limit: int = 20):
        """Get recent errors."""
        return {"errors": telemetry.get_recent_errors(limit=limit)}

    @mcp_router.get("/telemetry/servers/{server_id}")
    async def get_server_telemetry(server_id: str):
        """Get telemetry for a specific server."""
        metrics = telemetry.get_server_metrics(server_id)
        if not metrics:
            raise HTTPException(status_code=404, detail="Server not found") from None
        return metrics

    # ── Registry Operations ───────────────────────────────────────────

    @mcp_router.get("/registry")
    async def get_registry():
        """Get the full MCP registry."""
        return await registry.get_registry()

    @mcp_router.get("/registry/stats")
    async def get_registry_stats():
        """Get registry statistics."""
        registry_data = await registry.get_registry()
        running = len(registry_data.list_by_status(MCPServerStatus.RUNNING))
        stopped = len(registry_data.list_by_status(MCPServerStatus.STOPPED))
        failed = len(registry_data.list_by_status(MCPServerStatus.FAILED))

        return {
            "total_servers": len(registry_data.servers),
            "running": running,
            "stopped": stopped,
            "failed": failed,
            "enabled": len(registry_data.list_enabled()),
        }

    # ── Permissions ──────────────────────────────────────────────────

    @mcp_router.get("/servers/{server_id}/permissions")
    async def get_permissions(server_id: str):
        """Get permission mappings for a server."""
        detail = await registry.get_server(server_id)
        if not detail:
            raise HTTPException(status_code=404, detail="Server not found") from None
        return await registry.get_permissions(server_id)

    @mcp_router.post("/servers/{server_id}/permissions")
    async def set_permissions(server_id: str, mappings: list[dict]):
        """Set permission mappings for a server."""
        from agentic_os.domain.mcp import MCPPermissionMapping

        try:
            mapping_objects = [MCPPermissionMapping(**m) for m in mappings]
            count = await registry.set_permissions(server_id, mapping_objects)
            return {"set": count, "mappings": mappings}
        except KeyError:
            raise HTTPException(status_code=404, detail="Server not found") from None
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e)) from None

    return mcp_router


__all__ = ["create_mcp_router"]
