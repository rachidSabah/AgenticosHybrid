"""Tests for MCP Authentication."""

import pytest

from agentic_os.core.mcp.security import MCPAuthentication
from agentic_os.domain.security import Principal, Role


@pytest.fixture
def auth():
    return MCPAuthentication()


@pytest.fixture
def admin_principal():
    return Principal(id="admin-user", roles=[Role.ADMIN])


class TestMCPAuthenticationTokens:
    def test_create_token(self, auth, admin_principal) -> None:
        token = auth.create_token(admin_principal, scopes=["tools:read"])
        assert token.principal.id == "admin-user"
        assert "tools:read" in token.scopes
        assert not token.revoked

    def test_validate_valid_token(self, auth, admin_principal) -> None:
        created = auth.create_token(admin_principal)
        validated = auth.validate_token(created.token)
        assert validated is not None
        assert validated.id == created.id

    def test_validate_invalid_token(self, auth) -> None:
        assert auth.validate_token("invalid-token") is None

    def test_revoke_token(self, auth, admin_principal) -> None:
        token = auth.create_token(admin_principal)
        assert auth.revoke_token(token.id)
        assert auth.validate_token(token.token) is None

    def test_revoke_nonexistent(self, auth) -> None:
        assert not auth.revoke_token("nonexistent")

    def test_list_tokens(self, auth, admin_principal) -> None:
        auth.create_token(admin_principal, description="Token 1")
        auth.create_token(admin_principal, description="Token 2")
        tokens = auth.list_tokens()
        assert len(tokens) == 2

    def test_list_tokens_filtered(self, auth, admin_principal) -> None:
        auth.create_token(admin_principal, description="Token 1")
        other = Principal(id="other-user", roles=[Role.GUEST])
        auth.create_token(other, description="Token 2")
        tokens = auth.list_tokens(principal_id="admin-user")
        assert len(tokens) == 1

    def test_create_token_with_description(self, auth, admin_principal) -> None:
        token = auth.create_token(admin_principal, description="CI/CD token")
        assert token.description == "CI/CD token"


class TestMCPAuthenticationAPIKeys:
    def test_create_api_key(self, auth, admin_principal) -> None:
        key_value, cred = auth.create_api_key("deploy-key", admin_principal)
        assert cred.name == "deploy-key"
        assert cred.principal.id == "admin-user"
        assert len(key_value) > 0

    def test_validate_valid_api_key(self, auth, admin_principal) -> None:
        key_value, cred = auth.create_api_key("test-key", admin_principal)
        validated = auth.validate_api_key(key_value)
        assert validated is not None
        assert validated.id == cred.id

    def test_validate_invalid_api_key(self, auth) -> None:
        assert auth.validate_api_key("invalid-key") is None

    def test_revoke_api_key(self, auth, admin_principal) -> None:
        key_value, cred = auth.create_api_key("revocable", admin_principal)
        assert auth.revoke_api_key(cred.id)
        assert auth.validate_api_key(key_value) is None

    def test_revoke_api_key_nonexistent(self, auth) -> None:
        assert not auth.revoke_api_key("nonexistent")

    def test_list_api_keys(self, auth, admin_principal) -> None:
        auth.create_api_key("key1", admin_principal)
        auth.create_api_key("key2", admin_principal)
        keys = auth.list_api_keys()
        assert len(keys) == 2

    def test_list_api_keys_filtered(self, auth, admin_principal) -> None:
        auth.create_api_key("key1", admin_principal)
        other = Principal(id="other-user", roles=[Role.GUEST])
        auth.create_api_key("key2", other)
        keys = auth.list_api_keys(principal_id="admin-user")
        assert len(keys) == 1


class TestMCAuthenticationServerAuth:
    def test_configure_server_auth(self, auth) -> None:
        auth.configure_server_auth("srv1", "api_key", {"key_header": "X-API-Key"})
        config = auth.get_server_auth("srv1")
        assert config is not None
        assert config["type"] == "api_key"
        assert config["config"]["key_header"] == "X-API-Key"

    def test_get_server_auth_none(self, auth) -> None:
        assert auth.get_server_auth("nonexistent") is None

    def test_remove_server_auth(self, auth) -> None:
        auth.configure_server_auth("srv1", "oauth2", {})
        auth.remove_server_auth("srv1")
        assert auth.get_server_auth("srv1") is None

    def test_clear(self, auth, admin_principal) -> None:
        auth.create_token(admin_principal)
        auth.create_api_key("key", admin_principal)
        auth.configure_server_auth("srv1", "jwt", {})
        auth.clear()
        assert len(auth.list_tokens()) == 0
        assert len(auth.list_api_keys()) == 0
        assert auth.get_server_auth("srv1") is None

    def test_create_token_with_scopes(self, auth, admin_principal) -> None:
        scopes = ["tools:read", "tools:write", "resources:read"]
        token = auth.create_token(admin_principal, scopes=scopes)
        assert set(token.scopes) == set(scopes)

    def test_create_api_key_with_scopes(self, auth, admin_principal) -> None:
        _, cred = auth.create_api_key("scoped-key", admin_principal, scopes=["tools:read"])
        assert "tools:read" in cred.scopes
