"""
MCP Capability Mapper

Negotiates, maps, and tracks MCP server capabilities including tools,
resources, prompts, sampling, roots, streaming, and session management.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from agentic_os.infrastructure.logging import get_logger

log = get_logger("mcp.capability")


SUPPORTED_CAPABILITIES: list[str] = [
    "tools",
    "resources",
    "prompts",
    "sampling",
    "roots",
    "streaming",
    "session_management",
    "capability_negotiation",
    "automatic_discovery",
]


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class ServerCapabilities:
    """Capabilities declared by an MCP server."""

    server_id: str
    tools: list[dict[str, Any]] = field(default_factory=list)
    resources: list[dict[str, Any]] = field(default_factory=list)
    prompts: list[dict[str, Any]] = field(default_factory=list)
    sampling: bool = False
    roots: bool = False
    streaming: bool = False
    session_management: bool = False
    capability_negotiation: bool = False
    automatic_discovery: bool = False
    custom_capabilities: dict[str, Any] = field(default_factory=dict)
    discovered_at: datetime = field(default_factory=_utcnow)
    last_negotiated: datetime = field(default_factory=_utcnow)


@dataclass
class NegotiationResult:
    """Result of a capability negotiation."""

    server_id: str
    agreed_capabilities: list[str]
    rejected_capabilities: list[str]
    negotiated_at: datetime = field(default_factory=_utcnow)


class MCPCapabilityMapper:
    """Maps and negotiates MCP server capabilities."""

    def __init__(self) -> None:
        self._capabilities: dict[str, ServerCapabilities] = {}
        self._negotiation_history: dict[str, list[NegotiationResult]] = {}

    def register_capabilities(self, server_id: str, caps: ServerCapabilities) -> None:
        self._capabilities[server_id] = caps
        log.info(f"Registered capabilities for server {server_id}")

    def get_capabilities(self, server_id: str) -> ServerCapabilities | None:
        return self._capabilities.get(server_id)

    def update_capabilities(self, server_id: str, **kwargs: Any) -> None:
        caps = self._capabilities.get(server_id)
        if caps:
            for key, value in kwargs.items():
                if hasattr(caps, key):
                    setattr(caps, key, value)
            caps.last_negotiated = _utcnow()

    def remove_capabilities(self, server_id: str) -> None:
        self._capabilities.pop(server_id, None)
        self._negotiation_history.pop(server_id, None)

    def negotiate(self, server_id: str, requested: list[str]) -> NegotiationResult:
        caps = self._capabilities.get(server_id)
        if not caps:
            caps = ServerCapabilities(server_id=server_id)
            self._capabilities[server_id] = caps

        agreed: list[str] = []
        rejected: list[str] = []

        for capability in requested:
            if capability in SUPPORTED_CAPABILITIES:
                attr = capability.replace("-", "_")
                if hasattr(caps, attr):
                    setattr(caps, attr, True)
                agreed.append(capability)
            else:
                rejected.append(capability)

        caps.last_negotiated = _utcnow()

        result = NegotiationResult(
            server_id=server_id,
            agreed_capabilities=agreed,
            rejected_capabilities=rejected,
        )

        if server_id not in self._negotiation_history:
            self._negotiation_history[server_id] = []
        self._negotiation_history[server_id].append(result)

        return result

    def has_capability(self, server_id: str, capability: str) -> bool:
        caps = self._capabilities.get(server_id)
        if not caps:
            return False
        attr = capability.replace("-", "_")
        if hasattr(caps, attr):
            return bool(getattr(caps, attr))
        return capability in caps.custom_capabilities

    def get_supported_capabilities(self, server_id: str) -> list[str]:
        caps = self._capabilities.get(server_id)
        if not caps:
            return []
        supported: list[str] = []
        for cap in SUPPORTED_CAPABILITIES:
            if self.has_capability(server_id, cap):
                supported.append(cap)
        supported.extend(caps.custom_capabilities.keys())
        return supported

    def get_negotiation_history(self, server_id: str) -> list[NegotiationResult]:
        return self._negotiation_history.get(server_id, [])

    def list_all_capabilities(self) -> dict[str, list[str]]:
        return {sid: self.get_supported_capabilities(sid) for sid in self._capabilities}

    def clear(self) -> None:
        self._capabilities.clear()
        self._negotiation_history.clear()


__all__ = [
    "MCPCapabilityMapper",
    "ServerCapabilities",
    "NegotiationResult",
    "SUPPORTED_CAPABILITIES",
]
