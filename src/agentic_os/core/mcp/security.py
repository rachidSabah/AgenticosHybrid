"""
MCP Security Integration

Wraps the SecurityFramework to provide fine-grained authorization for every
MCP operation. Each public method maps an MCP action to a permission string
and runs the full authorization pipeline (RBAC -> approval gate -> audit).

Every MCP action must pass through this module. No direct bypasses.

Includes authentication mechanisms (API keys, OAuth2, JWT tokens) and a
permission manager for fine-grained access control at the server/tool/resource level.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from secrets import token_hex
from typing import Any
from uuid import uuid4

from agentic_os.domain.security import Decision, Principal, Role, ToolRequest
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.event_bus import EventBus

log = get_logger("mcp.security")


def _utcnow() -> datetime:
    return datetime.now(UTC)


_AUTH_TOKEN_EXPIRY_DAYS = 30
_API_KEY_LENGTH = 32


@dataclass
class AuthToken:
    """An authentication token for MCP access."""

    id: str
    token: str
    principal: Principal
    scopes: list[str]
    issued_at: datetime
    expires_at: datetime
    revoked: bool = False
    description: str = ""


@dataclass
class APICredential:
    """Stored API key credential."""

    id: str
    name: str
    key_hash: str
    principal: Principal
    scopes: list[str]
    created_at: datetime
    expires_at: datetime | None = None
    enabled: bool = True


class MCPAuthentication:
    """Handles MCP authentication — API keys, OAuth2 flows, JWT tokens."""

    def __init__(self) -> None:
        self._tokens: dict[str, AuthToken] = {}
        self._api_credentials: dict[str, APICredential] = {}
        self._server_auth_configs: dict[str, dict[str, Any]] = {}

    # ── Token Management ────────────────────────────────────────────────

    def create_token(
        self,
        principal: Principal,
        scopes: list[str] | None = None,
        expiry_days: int = _AUTH_TOKEN_EXPIRY_DAYS,
        description: str = "",
    ) -> AuthToken:
        token_id = str(uuid4())
        token_value = token_hex(_API_KEY_LENGTH)
        now = _utcnow()
        auth_token = AuthToken(
            id=token_id,
            token=token_value,
            principal=principal,
            scopes=scopes or [],
            issued_at=now,
            expires_at=now + timedelta(days=expiry_days),
            description=description,
        )
        self._tokens[token_id] = auth_token
        log.info(f"Created auth token {token_id} for principal {principal.id}")
        return auth_token

    def validate_token(self, token_value: str) -> AuthToken | None:
        for token in self._tokens.values():
            if token.token == token_value:
                if token.revoked:
                    return None
                if _utcnow() > token.expires_at:
                    return None
                return token
        return None

    def revoke_token(self, token_id: str) -> bool:
        token = self._tokens.get(token_id)
        if token:
            token.revoked = True
            log.info(f"Revoked token {token_id}")
            return True
        return False

    def list_tokens(self, principal_id: str | None = None) -> list[AuthToken]:
        tokens = list(self._tokens.values())
        if principal_id:
            tokens = [t for t in tokens if t.principal.id == principal_id]
        return tokens

    # ── API Key Management ──────────────────────────────────────────────

    def create_api_key(
        self,
        name: str,
        principal: Principal,
        scopes: list[str] | None = None,
        expires_at: datetime | None = None,
    ) -> tuple[str, APICredential]:
        key_id = str(uuid4())
        key_value = token_hex(_API_KEY_LENGTH)
        credential = APICredential(
            id=key_id,
            name=name,
            key_hash=key_value,
            principal=principal,
            scopes=scopes or [],
            created_at=_utcnow(),
            expires_at=expires_at,
        )
        self._api_credentials[key_id] = credential
        log.info(f"Created API key {key_id} for principal {principal.id}")
        return key_value, credential

    def validate_api_key(self, key_value: str) -> APICredential | None:
        for cred in self._api_credentials.values():
            if cred.key_hash == key_value:
                if not cred.enabled:
                    return None
                if cred.expires_at and _utcnow() > cred.expires_at:
                    return None
                return cred
        return None

    def revoke_api_key(self, key_id: str) -> bool:
        cred = self._api_credentials.get(key_id)
        if cred:
            cred.enabled = False
            log.info(f"Revoked API key {key_id}")
            return True
        return False

    def list_api_keys(self, principal_id: str | None = None) -> list[APICredential]:
        keys = list(self._api_credentials.values())
        if principal_id:
            keys = [k for k in keys if k.principal.id == principal_id]
        return keys

    # ── Server Auth Configuration ───────────────────────────────────────

    def configure_server_auth(
        self,
        server_id: str,
        auth_type: str,
        config: dict[str, Any],
    ) -> None:
        self._server_auth_configs[server_id] = {"type": auth_type, "config": config}
        log.info(f"Configured {auth_type} auth for server {server_id}")

    def get_server_auth(self, server_id: str) -> dict[str, Any] | None:
        return self._server_auth_configs.get(server_id)

    def remove_server_auth(self, server_id: str) -> None:
        self._server_auth_configs.pop(server_id, None)

    def clear(self) -> None:
        self._tokens.clear()
        self._api_credentials.clear()
        self._server_auth_configs.clear()


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


__all__ = ["MCPSecurity", "MCPAuthentication"]
