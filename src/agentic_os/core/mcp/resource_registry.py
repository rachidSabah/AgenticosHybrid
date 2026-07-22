"""
MCP Resource Registry

Standalone registry for managing MCP resource definitions across all servers.
Supports resource URI templates, content type tracking, and resource discovery.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from agentic_os.infrastructure.logging import get_logger

log = get_logger("mcp.resource_registry")


RESOURCE_CONTENT_TYPES: list[str] = [
    "text/plain",
    "text/markdown",
    "application/json",
    "application/octet-stream",
    "image/png",
    "image/jpeg",
    "audio/wav",
    "application/zip",
]


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class ResourceDefinition:
    """A registered resource definition."""

    uri: str
    server_id: str
    name: str
    description: str
    mime_type: str = "text/plain"
    uri_template: str | None = None
    annotations: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    enabled: bool = True
    content_size: int | None = None
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)


class MCPResourceRegistry:
    """Registry for MCP resource definitions."""

    def __init__(self) -> None:
        self._resources: dict[str, ResourceDefinition] = {}
        self._server_resources: dict[str, list[str]] = {}

    def register(self, resource: ResourceDefinition) -> None:
        key = f"{resource.server_id}:{resource.uri}"
        self._resources[key] = resource
        if resource.server_id not in self._server_resources:
            self._server_resources[resource.server_id] = []
        if resource.uri not in self._server_resources[resource.server_id]:
            self._server_resources[resource.server_id].append(resource.uri)
        log.info(f"Registered resource '{resource.uri}' for server {resource.server_id}")

    def unregister(self, server_id: str, uri: str) -> bool:
        key = f"{server_id}:{uri}"
        if key in self._resources:
            del self._resources[key]
            server_res = self._server_resources.get(server_id, [])
            if uri in server_res:
                server_res.remove(uri)
            log.info(f"Unregistered resource '{uri}' for server {server_id}")
            return True
        return False

    def get_resource(self, server_id: str, uri: str) -> ResourceDefinition | None:
        return self._resources.get(f"{server_id}:{uri}")

    def get_server_resources(self, server_id: str) -> list[ResourceDefinition]:
        return [
            self._resources[f"{server_id}:{uri}"]
            for uri in self._server_resources.get(server_id, [])
            if f"{server_id}:{uri}" in self._resources
        ]

    def list_resources(self) -> list[ResourceDefinition]:
        return list(self._resources.values())

    def find_by_mime_type(self, mime_type: str) -> list[ResourceDefinition]:
        return [r for r in self._resources.values() if r.mime_type == mime_type]

    def find_by_tag(self, tag: str) -> list[ResourceDefinition]:
        return [r for r in self._resources.values() if tag in r.tags]

    def search_resources(self, query: str) -> list[ResourceDefinition]:
        q = query.lower()
        return [
            r
            for r in self._resources.values()
            if q in r.name.lower() or q in r.description.lower() or q in r.uri.lower()
        ]

    def enable_resource(self, server_id: str, uri: str) -> bool:
        resource = self.get_resource(server_id, uri)
        if resource:
            resource.enabled = True
            resource.updated_at = _utcnow()
            return True
        return False

    def disable_resource(self, server_id: str, uri: str) -> bool:
        resource = self.get_resource(server_id, uri)
        if resource:
            resource.enabled = False
            resource.updated_at = _utcnow()
            return True
        return False

    def get_enabled_resources(self, server_id: str) -> list[ResourceDefinition]:
        return [r for r in self.get_server_resources(server_id) if r.enabled]

    def get_stats(self) -> dict[str, Any]:
        return {
            "total_resources": len(self._resources),
            "total_servers": len(self._server_resources),
            "resources_per_server": {sid: len(res) for sid, res in self._server_resources.items()},
        }

    def clear_server(self, server_id: str) -> None:
        uris = self._server_resources.pop(server_id, [])
        for uri in uris:
            self._resources.pop(f"{server_id}:{uri}", None)

    def clear(self) -> None:
        self._resources.clear()
        self._server_resources.clear()


__all__ = [
    "MCPResourceRegistry",
    "ResourceDefinition",
    "RESOURCE_CONTENT_TYPES",
]
