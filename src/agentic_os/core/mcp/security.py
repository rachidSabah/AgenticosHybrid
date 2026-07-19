"""
MCP Security Integration

Wraps the SecurityFramework to provide fine-grained authorization for every
MCP operation. Each public method maps an MCP action to a permission string
and runs the full authorization pipeline (RBAC -> approval gate -> audit).

Every MCP action must pass through this module. No direct bypasses.
"""

from dataclasses import dataclass
from typing import Any

from agentic_os.domain.security import Decision, Principal, Role, ToolRequest
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.event_bus import EventBus

log = get_logger("mcp.security")


@dataclass
class MCPSecurity:
    """
    Authorization gate for MCP operations.

    Wraps the SecurityFramework's authorize() pipeline with MCP-specific
    capability strings. Automatically records audit entries through the
    framework's built-in audit mechanism.

    When no framework is provided (None), all operations are allowed — this
    matches the local-development default where MCP runs without mandatory
    auth.
    """

    framework: Any = None  # SecurityFramework | None — Any avoids circular import typing
    bus: EventBus | None = None

    # ── Server Lifecycle ──────────────────────────────────────────────────

    async def authorize_server_create(self, principal: Principal, server_name: str) -> Decision:
        """Authorize creating a new MCP server."""
        return await self._check(principal, "mcp.server.create", f"Create server: {server_name}")

    async def authorize_server_read(self, principal: Principal, server_id: str) -> Decision:
        """Authorize reading MCP server details."""
        return await self._check(principal, "mcp.server.read", f"Read server: {server_id}")

    async def authorize_server_update(self, principal: Principal, server_id: str) -> Decision:
        """Authorize updating an MCP server configuration."""
        return await self._check(principal, "mcp.server.update", f"Update server: {server_id}")

    async def authorize_server_delete(self, principal: Principal, server_id: str) -> Decision:
        """Authorize deleting an MCP server."""
        return await self._check(principal, "mcp.server.delete", f"Delete server: {server_id}")

    async def authorize_server_start(self, principal: Principal, server_id: str) -> Decision:
        """Authorize starting an MCP server."""
        return await self._check(principal, "mcp.server.start", f"Start server: {server_id}")

    async def authorize_server_stop(self, principal: Principal, server_id: str) -> Decision:
        """Authorize stopping an MCP server."""
        return await self._check(principal, "mcp.server.stop", f"Stop server: {server_id}")

    async def authorize_server_restart(self, principal: Principal, server_id: str) -> Decision:
        """Authorize restarting an MCP server."""
        return await self._check(principal, "mcp.server.restart", f"Restart server: {server_id}")

    async def authorize_server_reload(self, principal: Principal, server_id: str) -> Decision:
        """Authorize reloading an MCP server."""
        return await self._check(principal, "mcp.server.reload", f"Reload server: {server_id}")

    # ── Tool Operations ───────────────────────────────────────────────────

    async def authorize_tool_invoke(
        self, principal: Principal, server_id: str, tool_name: str
    ) -> Decision:
        """Authorize invoking a tool on an MCP server."""
        return await self._check(
            principal,
            "mcp.tool.invoke",
            f"Invoke tool {tool_name} on {server_id}",
            requires_approval=True,
        )

    async def authorize_tool_discover(self, principal: Principal, server_id: str) -> Decision:
        """Authorize discovering tools on an MCP server."""
        return await self._check(
            principal,
            "mcp.tool.discover",
            f"Discover tools on {server_id}",
        )

    async def authorize_tool_read(self, principal: Principal, server_id: str) -> Decision:
        """Authorize reading tools from an MCP server."""
        return await self._check(principal, "mcp.tool.read", f"Read tools on {server_id}")

    # ── Resource Operations ───────────────────────────────────────────────

    async def authorize_resource_read(
        self,
        principal: Principal,
        server_id: str,
        uri: str,
    ) -> Decision:
        """Authorize reading a resource from an MCP server."""
        return await self._check(
            principal,
            "mcp.resource.read",
            f"Read resource {uri} on {server_id}",
        )

    async def authorize_resource_subscribe(
        self, principal: Principal, server_id: str, uri: str
    ) -> Decision:
        """Authorize subscribing to resource changes."""
        return await self._check(
            principal,
            "mcp.resource.subscribe",
            f"Subscribe to {uri} on {server_id}",
        )

    # ── Prompt Operations ─────────────────────────────────────────────────

    async def authorize_prompt_get(
        self, principal: Principal, server_id: str, prompt_name: str
    ) -> Decision:
        """Authorize getting a prompt from an MCP server."""
        return await self._check(
            principal,
            "mcp.prompt.get",
            f"Get prompt {prompt_name} on {server_id}",
        )

    async def authorize_prompt_list(self, principal: Principal, server_id: str) -> Decision:
        """Authorize listing prompts on an MCP server."""
        return await self._check(
            principal,
            "mcp.prompt.list",
            f"List prompts on {server_id}",
        )

    # ── Session Operations ────────────────────────────────────────────────

    async def authorize_session_manage(
        self, principal: Principal, server_id: str, action: str
    ) -> Decision:
        """Authorize managing sessions on an MCP server."""
        return await self._check(
            principal,
            "mcp.session.manage",
            f"{action} session on {server_id}",
        )

    async def authorize_session_read(self, principal: Principal, server_id: str) -> Decision:
        """Authorize reading session information."""
        return await self._check(
            principal,
            "mcp.session.read",
            f"Read session on {server_id}",
        )

    # ── Permission / Config / Health Operations ───────────────────────────

    async def authorize_permissions_manage(self, principal: Principal, server_id: str) -> Decision:
        """Authorize managing permissions for an MCP server."""
        return await self._check(
            principal,
            "mcp.permissions.manage",
            f"Manage permissions on {server_id}",
        )

    async def authorize_permissions_read(self, principal: Principal, server_id: str) -> Decision:
        """Authorize reading permissions for an MCP server."""
        return await self._check(
            principal,
            "mcp.permissions.read",
            f"Read permissions on {server_id}",
        )

    async def authorize_health_read(self, principal: Principal, server_id: str) -> Decision:
        """Authorize reading MCP server health."""
        return await self._check(
            principal,
            "mcp.health.read",
            f"Read health on {server_id}",
        )

    async def authorize_config_read(self, principal: Principal, server_id: str) -> Decision:
        """Authorize reading MCP server configuration."""
        return await self._check(
            principal,
            "mcp.config.read",
            f"Read config on {server_id}",
        )

    async def authorize_config_update(self, principal: Principal, server_id: str) -> Decision:
        """Authorize updating MCP server configuration."""
        return await self._check(
            principal,
            "mcp.config.update",
            f"Update config on {server_id}",
        )

    async def authorize_telemetry_read(self, principal: Principal) -> Decision:
        """Authorize reading MCP telemetry data."""
        return await self._check(principal, "mcp.telemetry.read", "Read telemetry")

    async def authorize_audit_read(self, principal: Principal) -> Decision:
        """Authorize reading MCP audit log."""
        return await self._check(principal, "mcp.audit.read", "Read audit log")

    # ── Internal ──────────────────────────────────────────────────────────

    _DEFAULT_PRINCIPAL: Principal = Principal(id="mcp-system", roles=[Role.ADMIN])

    def system_principal(self) -> Principal:
        """Return the system-level principal used for internal operations."""
        return self._DEFAULT_PRINCIPAL

    async def _check(
        self,
        principal: Principal,
        capability: str,
        detail: str,
        requires_approval: bool = False,
    ) -> Decision:
        """Run the authorization pipeline for an MCP capability."""
        if self.framework is None:
            return Decision(allowed=True, reason="No security framework configured")

        request = ToolRequest(
            principal=principal,
            capability=capability,
            detail=detail,
            requires_approval=requires_approval,
        )
        return await self.framework.authorize(principal, request)
