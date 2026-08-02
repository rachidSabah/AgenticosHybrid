"""
MCP Version Manager

Manages MCP protocol versions and server version compatibility
including version negotiation, compatibility checks,
and version tracking across the MCP runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from agentic_os.infrastructure.logging import get_logger

log = get_logger("mcp.version")


SUPPORTED_PROTOCOL_VERSIONS: list[str] = [
    "2024-11-05",
    "2025-03-26",
]

RECOMMENDED_PROTOCOL_VERSION: str = "2024-11-05"


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class ServerVersionInfo:
    """Version information for an MCP server."""

    server_id: str
    protocol_version: str | None = None
    server_version: str | None = None
    sdk_version: str | None = None
    capabilities_version: str | None = None
    discovered_at: datetime = field(default_factory=_utcnow)
    last_updated: datetime = field(default_factory=_utcnow)


@dataclass
class CompatibilityResult:
    """Result of a version compatibility check."""

    compatible: bool
    protocol_version: str | None = None
    recommended_version: str | None = None
    reason: str | None = None


class MCPVersionManager:
    """Manages MCP protocol and server versioning."""

    def __init__(self) -> None:
        self._server_versions: dict[str, ServerVersionInfo] = {}

    def register_version(self, server_id: str, info: ServerVersionInfo) -> None:
        self._server_versions[server_id] = info
        log.info(f"Registered version for server {server_id}")

    def get_version(self, server_id: str) -> ServerVersionInfo | None:
        return self._server_versions.get(server_id)

    def update_version(self, server_id: str, **kwargs: Any) -> None:
        info = self._server_versions.get(server_id)
        if info:
            for key, value in kwargs.items():
                if hasattr(info, key):
                    setattr(info, key, value)
            info.last_updated = _utcnow()

    def remove_version(self, server_id: str) -> None:
        self._server_versions.pop(server_id, None)

    def check_compatibility(self, server_id: str) -> CompatibilityResult:
        info = self._server_versions.get(server_id)
        if not info:
            return CompatibilityResult(compatible=False, reason="No version info available")

        if not info.protocol_version:
            return CompatibilityResult(compatible=False, reason="No protocol version available")

        if info.protocol_version in SUPPORTED_PROTOCOL_VERSIONS:
            return CompatibilityResult(
                compatible=True,
                protocol_version=info.protocol_version,
                recommended_version=RECOMMENDED_PROTOCOL_VERSION,
            )

        return CompatibilityResult(
            compatible=False,
            protocol_version=info.protocol_version,
            recommended_version=RECOMMENDED_PROTOCOL_VERSION,
            reason=(
                f"Protocol version {info.protocol_version} not supported. "
                f"Supported: {SUPPORTED_PROTOCOL_VERSIONS}"
            ),
        )

    def negotiate_version(self, server_protocol: str) -> str | None:
        for version in SUPPORTED_PROTOCOL_VERSIONS:
            if version <= server_protocol:
                return version
        return None

    def list_versions(self) -> dict[str, ServerVersionInfo]:
        return dict(self._server_versions)

    def get_protocol_compatibility_matrix(self) -> dict[str, Any]:
        return {
            "supported_versions": SUPPORTED_PROTOCOL_VERSIONS,
            "recommended_version": RECOMMENDED_PROTOCOL_VERSION,
            "servers": {
                sid: {
                    "protocol_version": info.protocol_version,
                    "server_version": info.server_version,
                    "compatible": self.check_compatibility(sid).compatible,
                }
                for sid, info in self._server_versions.items()
            },
        }

    def clear(self) -> None:
        self._server_versions.clear()


__all__ = [
    "MCPVersionManager",
    "ServerVersionInfo",
    "CompatibilityResult",
    "SUPPORTED_PROTOCOL_VERSIONS",
    "RECOMMENDED_PROTOCOL_VERSION",
]
