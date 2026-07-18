"""
Plugin Domain Models

Domain layer for plugin framework - pure Python, no external dependencies.
Follows hexagonal architecture: domain depends on nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


def _utcnow() -> datetime:
    return datetime.now(UTC)


class PluginCategory(StrEnum):
    """Plugin categories for organization and discovery."""

    AGENT = "agent"
    TOOL = "tool"
    PROVIDER = "provider"
    MCP_SERVER = "mcp_server"
    WORKFLOW_NODE = "workflow_node"
    PIPELINE_STAGE = "pipeline_stage"
    UI_COMPONENT = "ui_component"
    INTEGRATION = "integration"
    UTILITY = "utility"


class PluginStatus(StrEnum):
    """Lifecycle status of a plugin."""

    UNINSTALLED = "uninstalled"
    INSTALLING = "installing"
    INSTALLED = "installed"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"
    UPDATING = "updating"
    UNINSTALLING = "uninstalling"


class PluginDependencyType(StrEnum):
    """Types of plugin dependencies."""

    REQUIRED = "required"
    OPTIONAL = "optional"
    PEER = "peer"


@dataclass(frozen=True, slots=True)
class PluginDependency:
    """A dependency on another plugin."""

    name: str
    version: str
    type: PluginDependencyType = PluginDependencyType.REQUIRED
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "type": self.type.value,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PluginDependency:
        return cls(
            name=data["name"],
            version=data["version"],
            type=PluginDependencyType(data.get("type", "required")),
            reason=data.get("reason"),
        )


@dataclass(frozen=True, slots=True)
class PluginCapability:
    """A capability provided by a plugin."""

    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    tags: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
            "outputSchema": self.output_schema,
            "tags": list(self.tags),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PluginCapability:
        return cls(
            name=data["name"],
            description=data["description"],
            input_schema=data.get("inputSchema", {}),
            output_schema=data.get("outputSchema", {}),
            tags=tuple(data.get("tags", [])),
        )


@dataclass(frozen=True, slots=True)
class PluginManifest:
    """
    Plugin manifest - immutable metadata describing a plugin.

    This is the primary contract between plugins and the platform.
    """

    name: str
    version: str
    description: str
    category: PluginCategory
    author: str
    license: str
    homepage: str | None = None
    repository: str | None = None
    # Dependencies on other plugins
    dependencies: tuple[PluginDependency, ...] = field(default_factory=tuple)
    # Capabilities this plugin provides
    capabilities: tuple[PluginCapability, ...] = field(default_factory=tuple)
    # Entry points
    entry_point: str | None = None
    # Configuration schema (JSON Schema)
    config_schema: dict[str, Any] = field(default_factory=dict)
    # Required permissions
    permissions: tuple[str, ...] = field(default_factory=tuple)
    # Minimum platform version
    min_platform_version: str = "0.4.0"
    # Maximum platform version (exclusive)
    max_platform_version: str | None = None
    # Keywords for search
    keywords: tuple[str, ...] = field(default_factory=tuple)
    # Signed by author
    signature: str | None = None
    # Public key used for signing
    public_key: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "category": self.category.value,
            "author": self.author,
            "license": self.license,
            "homepage": self.homepage,
            "repository": self.repository,
            "dependencies": [d.to_dict() for d in self.dependencies],
            "capabilities": [c.to_dict() for c in self.capabilities],
            "entry_point": self.entry_point,
            "config_schema": self.config_schema,
            "permissions": list(self.permissions),
            "min_platform_version": self.min_platform_version,
            "max_platform_version": self.max_platform_version,
            "keywords": list(self.keywords),
            "signature": self.signature,
            "public_key": self.public_key,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PluginManifest:
        return cls(
            name=data["name"],
            version=data["version"],
            description=data["description"],
            category=PluginCategory(data["category"]),
            author=data["author"],
            license=data["license"],
            homepage=data.get("homepage"),
            repository=data.get("repository"),
            dependencies=tuple(PluginDependency.from_dict(d) for d in data.get("dependencies", [])),
            capabilities=tuple(PluginCapability.from_dict(c) for c in data.get("capabilities", [])),
            entry_point=data.get("entry_point"),
            config_schema=data.get("config_schema", {}),
            permissions=tuple(data.get("permissions", [])),
            min_platform_version=data.get("min_platform_version", "0.4.0"),
            max_platform_version=data.get("max_platform_version"),
            keywords=tuple(data.get("keywords", [])),
            signature=data.get("signature"),
            public_key=data.get("public_key"),
        )


@dataclass(frozen=True, slots=True)
class PluginInstance:
    """Runtime instance of an installed plugin."""

    manifest: PluginManifest
    status: PluginStatus
    installed_at: datetime
    path: str
    config: dict[str, Any] = field(default_factory=dict)
    process_id: int | None = None
    started_at: datetime | None = None
    stopped_at: datetime | None = None
    error: str | None = None
    health: str = "unknown"
    health_details: dict[str, Any] = field(default_factory=dict)
    last_health_check: datetime | None = None
    restart_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifest": self.manifest.to_dict(),
            "status": self.status.value,
            "installed_at": self.installed_at.isoformat(),
            "path": self.path,
            "config": self.config,
            "process_id": self.process_id,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "stopped_at": self.stopped_at.isoformat() if self.stopped_at else None,
            "error": self.error,
            "health": self.health,
            "health_details": self.health_details,
            "last_health_check": self.last_health_check.isoformat()
            if self.last_health_check
            else None,
            "restart_count": self.restart_count,
        }

    def with_status(
        self, status: PluginStatus, error: str | None = None, process_id: int | None = None
    ) -> PluginInstance:
        now = _utcnow()
        return PluginInstance(
            manifest=self.manifest,
            status=status,
            installed_at=self.installed_at,
            path=self.path,
            config=self.config,
            process_id=process_id if process_id is not None else self.process_id,
            started_at=self.started_at if status != PluginStatus.STARTING else now,
            stopped_at=now
            if status in (PluginStatus.STOPPED, PluginStatus.FAILED)
            else self.stopped_at,
            error=error if error is not None else self.error,
            health=self.health,
            health_details=self.health_details,
            last_health_check=self.last_health_check,
            restart_count=self.restart_count + (1 if status == PluginStatus.FAILED else 0),
        )

    def with_config(self, config: dict[str, Any]) -> PluginInstance:
        return PluginInstance(
            manifest=self.manifest,
            status=self.status,
            installed_at=self.installed_at,
            path=self.path,
            config=config,
            process_id=self.process_id,
            started_at=self.started_at,
            stopped_at=self.stopped_at,
            error=self.error,
            health=self.health,
            health_details=self.health_details,
            last_health_check=self.last_health_check,
            restart_count=self.restart_count,
        )

    def with_health(self, health: str, details: dict[str, Any] | None = None) -> PluginInstance:
        return PluginInstance(
            manifest=self.manifest,
            status=self.status,
            installed_at=self.installed_at,
            path=self.path,
            config=self.config,
            process_id=self.process_id,
            started_at=self.started_at,
            stopped_at=self.stopped_at,
            error=self.error,
            health=health,
            health_details=details or self.health_details,
            last_health_check=_utcnow(),
            restart_count=self.restart_count,
        )


@dataclass(frozen=True, slots=True)
class PluginConfig:
    """Configuration for a plugin instance."""

    plugin_name: str
    values: dict[str, Any] = field(default_factory=dict)
    schema: dict[str, Any] = field(default_factory=dict)
    updated_at: datetime = field(default_factory=_utcnow)
    updated_by: str = "system"

    def to_dict(self) -> dict[str, Any]:
        return {
            "plugin_name": self.plugin_name,
            "values": self.values,
            "schema": self.schema,
            "updated_at": self.updated_at.isoformat(),
            "updated_by": self.updated_by,
        }


@dataclass(frozen=True, slots=True)
class PluginRegistrySnapshot:
    """Snapshot of the entire plugin registry."""

    plugins: tuple[PluginInstance, ...] = field(default_factory=tuple)
    updated_at: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "plugins": [p.to_dict() for p in self.plugins],
            "updated_at": self.updated_at.isoformat(),
        }

    def get_plugin(self, name: str) -> PluginInstance | None:
        for p in self.plugins:
            if p.manifest.name == name:
                return p
        return None

    def list_by_status(self, status: PluginStatus) -> list[PluginInstance]:
        return [p for p in self.plugins if p.status == status]

    def list_by_category(self, category: PluginCategory) -> list[PluginInstance]:
        return [p for p in self.plugins if p.manifest.category == category]

    def list_running(self) -> list[PluginInstance]:
        return [p for p in self.plugins if p.status == PluginStatus.RUNNING]

    def list_failed(self) -> list[PluginInstance]:
        return [p for p in self.plugins if p.status == PluginStatus.FAILED]


@dataclass(frozen=True, slots=True)
class PluginValidationResult:
    """Result of plugin validation."""

    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    manifest: PluginManifest | None = None
    dependency_status: dict[str, bool] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PluginSearchQuery:
    """Query for searching plugins."""

    query: str = ""
    category: PluginCategory | None = None
    capability: str | None = None
    author: str | None = None
    installed_only: bool = False
    enabled_only: bool = False
    limit: int = 50
    offset: int = 0


@dataclass(frozen=True, slots=True)
class PluginSearchResult:
    """Result of a plugin search."""

    plugins: list[PluginManifest]
    total: int
    query: PluginSearchQuery


__all__ = [
    "PluginCategory",
    "PluginStatus",
    "PluginDependencyType",
    "PluginDependency",
    "PluginCapability",
    "PluginManifest",
    "PluginInstance",
    "PluginConfig",
    "PluginRegistrySnapshot",
    "PluginValidationResult",
    "PluginSearchQuery",
    "PluginSearchResult",
]
