"""MCP Validation utilities."""

import re

from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.mcp import ValidationResult

logger = get_logger("mcp.sdk.validation")

_SERVER_NAME_RE = re.compile(r"^[a-zA-Z0-9_][a-zA-Z0-9_. -]{0,63}$")
_URL_RE = re.compile(r"^https?://[^\s/$.?#].[^\s]*$", re.IGNORECASE)
_TOOL_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_-]{0,63}$")
_RESOURCE_URI_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://.+")


class McpValidator:
    """Validation utilities for MCP configurations and inputs.

    Each static method returns a :class:`ValidationResult` indicating
    whether the value is valid and listing any errors or warnings.
    """

    @staticmethod
    def validate_server_name(name: str) -> ValidationResult:
        """Validate an MCP server name.

        Rules:
        - Between 1 and 64 characters.
        - Starts with a letter, digit, or underscore.
        - Contains only letters, digits, underscores, dots, spaces, hyphens.
        """
        errors: list[str] = []
        warnings: list[str] = []

        if not name or not name.strip():
            errors.append("server name must not be empty")
        elif not _SERVER_NAME_RE.match(name):
            errors.append(
                "server name must be 1-64 characters, start with a letter/digit/underscore, "
                "and contain only letters, digits, underscores, dots, spaces, or hyphens"
            )

        result = ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)
        if not result.valid:
            logger.warning("server name validation failed", name=name, errors=errors)
        return result

    @staticmethod
    def validate_url(url: str) -> ValidationResult:
        """Validate a URL for MCP transport.

        Rules:
        - Must be an HTTP or HTTPS URL.
        - Must be non-empty.
        """
        errors: list[str] = []
        warnings: list[str] = []

        if not url:
            errors.append("url must not be empty")
        elif not _URL_RE.match(url):
            errors.append("url must be a valid HTTP or HTTPS URL")

        result = ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)
        if not result.valid:
            logger.warning("url validation failed", url=url, errors=errors)
        return result

    @staticmethod
    def validate_command(command: str) -> ValidationResult:
        """Validate a shell command path.

        Rules:
        - Must be non-empty.
        - Should not contain shell injection characters.
        """
        errors: list[str] = []
        warnings: list[str] = []

        if not command or not command.strip():
            errors.append("command must not be empty")

        for char in (";", "|", "&", "$", "`", ">", "<"):
            if char in command:
                warnings.append(f"command contains potentially unsafe character: {char!r}")

        result = ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)
        if not result.valid:
            logger.warning("command validation failed", command=command, errors=errors)
        return result

    @staticmethod
    def validate_tool_name(name: str) -> ValidationResult:
        """Validate an MCP tool name.

        Rules:
        - Between 1 and 64 characters.
        - Starts with a letter or underscore.
        - Contains only letters, digits, underscores, hyphens.
        """
        errors: list[str] = []

        if not name:
            errors.append("tool name must not be empty")
        elif not _TOOL_NAME_RE.match(name):
            errors.append(
                "tool name must be 1-64 characters, start with a letter or underscore, "
                "and contain only letters, digits, underscores, or hyphens"
            )

        result = ValidationResult(valid=len(errors) == 0, errors=errors)
        if not result.valid:
            logger.warning("tool name validation failed", name=name, errors=errors)
        return result

    @staticmethod
    def validate_resource_uri(uri: str) -> ValidationResult:
        """Validate a resource URI.

        Rules:
        - Must be non-empty.
        - Must match the URI scheme ``<scheme>://...``.
        """
        errors: list[str] = []

        if not uri:
            errors.append("resource URI must not be empty")
        elif not _RESOURCE_URI_RE.match(uri):
            errors.append("resource URI must follow the scheme://authority/path format")

        result = ValidationResult(valid=len(errors) == 0, errors=errors)
        if not result.valid:
            logger.warning("resource URI validation failed", uri=uri, errors=errors)
        return result

    @staticmethod
    def validate_port(port: int) -> ValidationResult:
        """Validate a network port number.

        Rules:
        - Must be between 1 and 65535.
        """
        errors: list[str] = []

        if not isinstance(port, int):
            errors.append("port must be an integer")
        elif port < 1 or port > 65535:
            errors.append(f"port must be between 1 and 65535, got {port}")

        result = ValidationResult(valid=len(errors) == 0, errors=errors)
        if not result.valid:
            logger.warning("port validation failed", port=port, errors=errors)
        return result
