"""MCP Authentication helpers."""

import base64


class McpAuthHelper:
    """Helper for MCP authentication flows.

    Provides static methods to build common HTTP Authorization headers
    and validate tokens.
    """

    @staticmethod
    def basic_auth_header(username: str, password: str) -> dict[str, str]:
        """Build a Basic Authorization header.

        Parameters
        ----------
        username:
            The username.
        password:
            The password.

        Returns
        -------
        dict[str, str]:
            A single-entry dict ``{"Authorization": "Basic <encoded>"}``.
        """
        raw = f"{username}:{password}"
        encoded = base64.b64encode(raw.encode()).decode()
        return {"Authorization": f"Basic {encoded}"}

    @staticmethod
    def bearer_auth_header(token: str) -> dict[str, str]:
        """Build a Bearer Authorization header.

        Parameters
        ----------
        token:
            The bearer token.

        Returns
        -------
        dict[str, str]:
            A single-entry dict ``{"Authorization": "Bearer <token>"}``.
        """
        return {"Authorization": f"Bearer {token}"}

    @staticmethod
    def api_key_header(api_key: str, key_name: str = "X-API-Key") -> dict[str, str]:
        """Build an API key header.

        Parameters
        ----------
        api_key:
            The API key value.
        key_name:
            The header name (default ``"X-API-Key"``).

        Returns
        -------
        dict[str, str]:
            A single-entry dict mapping *key_name* to the API key value.
        """
        return {key_name: api_key}

    @staticmethod
    async def validate_token(token: str, expected_issuer: str | None = None) -> bool:
        """Validate a JWT-like token.

        .. note::
            This is a placeholder implementation that checks the token is
            non-empty. Real applications should integrate with an OIDC/JWT
            validation library.

        Parameters
        ----------
        token:
            The token string to validate.
        expected_issuer:
            Optional expected issuer (not yet enforced).

        Returns
        -------
        bool:
            ``True`` if the token passes basic validation.
        """
        # Basic checks: non-empty, at least two dot-separated parts
        if not token or not isinstance(token, str):
            return False

        parts = token.split(".")
        return len(parts) >= 2
