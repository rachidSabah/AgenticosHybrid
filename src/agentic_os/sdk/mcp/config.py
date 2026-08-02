"""MCP Configuration helpers."""

from typing import Any
from uuid import uuid4

from agentic_os.domain.mcp import MCPServerConfig, MCPTransport
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.mcp import ValidationResult

logger = get_logger("mcp.sdk.config")


class McpConfigHelper:
    """Helpers for building and validating MCP server configurations."""

    @staticmethod
    def from_dict(data: dict[str, Any]) -> MCPServerConfig:
        """Build an :class:`MCPServerConfig` from a dictionary.

        Parameters
        ----------
        data:
            Dictionary with keys matching :class:`MCPServerConfig` fields.
            The ``transport`` key accepts a string or :class:`MCPTransport` enum.
            If ``id`` is omitted a UUID is auto-generated.

        Returns
        -------
        MCPServerConfig:
            A new server config instance.
        """
        transport_raw = data.get("transport", "stdio")
        if isinstance(transport_raw, str):
            transport = MCPTransport(transport_raw.lower().replace("-", "_"))
        else:
            transport = transport_raw

        config_id = data.get("id", str(uuid4()))

        return MCPServerConfig(
            id=config_id,
            name=data.get("name", ""),
            transport=transport,
            command=data.get("command"),
            args=tuple(data.get("args", [])),
            env=data.get("env", {}),
            url=data.get("url"),
            headers=data.get("headers", {}),
            sandbox=data.get("sandbox", True),
            sandbox_config=data.get("sandbox_config", {}),
            enabled=data.get("enabled", True),
            health_check_interval_seconds=data.get("health_check_interval_seconds", 30),
            health_check_timeout_seconds=data.get("health_check_timeout_seconds", 10),
            description=data.get("description", ""),
            tags=tuple(data.get("tags", [])),
        )

    @staticmethod
    def merge_configs(base: MCPServerConfig, overrides: dict[str, Any]) -> MCPServerConfig:
        """Merge *overrides* into a base config, returning a new config.

        Parameters
        ----------
        base:
            The base configuration.
        overrides:
            A dictionary of fields to override.

        Returns
        -------
        MCPServerConfig:
            A new config with overridden values.
        """
        merged_data = base.to_dict()
        merged_data.update(overrides)
        return McpConfigHelper.from_dict(merged_data)

    @staticmethod
    def validate_config(config: MCPServerConfig) -> ValidationResult:
        """Validate a server configuration.

        Checks:
        - Server name is non-empty.
        - Transport is valid.
        - Required fields for the transport type are present.

        Parameters
        ----------
        config:
            The configuration to validate.

        Returns
        -------
        ValidationResult:
            Result with errors and warnings.
        """
        errors: list[str] = []
        warnings: list[str] = []

        if not config.name or not config.name.strip():
            errors.append("server name must not be empty")

        match config.transport:
            case MCPTransport.STDIO:
                if not config.command:
                    errors.append("command is required for stdio transport")
            case MCPTransport.SSE:
                if not config.url:
                    errors.append("url is required for sse transport")
            case MCPTransport.STREAMABLE_HTTP:
                if not config.url:
                    errors.append("url is required for streamable_http transport")
            case _:
                errors.append(f"unsupported transport: {config.transport}")

        return ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)

    @staticmethod
    def default_stdio_config(name: str) -> MCPServerConfig:
        """Create a default stdio server configuration.

        Parameters
        ----------
        name:
            The server name.

        Returns
        -------
        MCPServerConfig:
            A minimal stdio config — command is left as *None* for the caller
            to fill in.
        """
        return MCPServerConfig(
            id=str(uuid4()),
            name=name,
            transport=MCPTransport.STDIO,
        )

    @staticmethod
    def default_sse_config(name: str, url: str) -> MCPServerConfig:
        """Create a default SSE server configuration.

        Parameters
        ----------
        name:
            The server name.
        url:
            The SSE endpoint URL.

        Returns
        -------
        MCPServerConfig:
            An SSE configuration with the given name and URL.
        """
        return MCPServerConfig(
            id=str(uuid4()),
            name=name,
            transport=MCPTransport.SSE,
            url=url,
        )
