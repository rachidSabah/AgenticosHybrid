"""
Plugin SDK

TypeScript/Python interfaces for external plugin developers.
Provides a stable API for building plugins for the Agentic OS platform.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import field
from datetime import UTC, datetime
from typing import Any

from agentic_os.domain.plugin import (
    PluginCapability,
    PluginCategory,
    PluginDependency,
    PluginDependencyType,
    PluginManifest,
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


# =============================================================================
# Python Plugin SDK
# =============================================================================


class PluginBase:
    """
    Base class for all plugins.

    Plugins should inherit from this class and implement the required methods.
    """

    # Plugin metadata (override in subclass)
    name: str = ""
    version: str = "1.0.0"
    description: str = ""
    category: PluginCategory = PluginCategory.UTILITY
    author: str = ""
    license: str = "MIT"
    homepage: str | None = None
    repository: str | None = None
    dependencies: list[PluginDependency] = field(default_factory=list)
    capabilities: list[PluginCapability] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    config_schema: dict[str, Any] = field(default_factory=dict)

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self._capabilities: dict[str, Callable] = {}
        self._initialized = False

    async def ainit(self) -> None:
        """Async initialization - override for async setup."""
        pass

    def start(self) -> None:
        """Called when plugin starts."""
        pass

    def stop(self) -> None:
        """Called when plugin stops."""
        pass

    def cleanup(self) -> None:
        """Called when plugin is unloaded."""
        pass

    def get_manifest(self) -> PluginManifest:
        """Generate manifest from class attributes."""
        return PluginManifest(
            name=self.name or self.__class__.__name__,
            version=self.version,
            description=self.description,
            category=self.category,
            author=self.author,
            license=self.license,
            homepage=self.homepage,
            repository=self.repository,
            dependencies=tuple(self.dependencies),
            capabilities=tuple(self.capabilities),
            entry_point=f"{self.__class__.__module__}.{self.__class__.__name__}",
            config_schema=self.config_schema,
            permissions=tuple(self.permissions),
        )

    def register_capability(self, name: str, func: Callable, **schemas: Any) -> None:
        """Register a capability."""
        self._capabilities[name] = func

    async def call_capability(self, name: str, **arguments: Any) -> Any:
        """Call a registered capability."""
        if name not in self._capabilities:
            raise AttributeError(f"Capability {name} not found")
        func = self._capabilities[name]
        if asyncio.iscoroutinefunction(func):
            return await func(**arguments)
        return func(**arguments)


class AgentPlugin(PluginBase):
    """Base class for agent plugins."""

    category = PluginCategory.AGENT

    async def execute(self, task: str, context: dict[str, Any] | None = None) -> Any:
        """Execute the agent with a task."""
        raise NotImplementedError


class ToolPlugin(PluginBase):
    """Base class for tool plugins."""

    category = PluginCategory.TOOL

    async def execute(self, **arguments: Any) -> Any:
        """Execute the tool."""
        raise NotImplementedError


class ProviderPlugin(PluginBase):
    """Base class for provider plugins."""

    category = PluginCategory.PROVIDER

    async def complete(self, prompt: str, **options: Any) -> Any:
        """Complete a prompt."""
        raise NotImplementedError

    async def stream_complete(self, prompt: str, **options: Any):
        """Stream completion."""
        raise NotImplementedError


class MCPServerPlugin(PluginBase):
    """Base class for MCP server plugins."""

    category = PluginCategory.MCP_SERVER

    async def list_tools(self) -> list[dict[str, Any]]:
        """List available tools."""
        raise NotImplementedError

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """Call a tool."""
        raise NotImplementedError


class WorkflowNodePlugin(PluginBase):
    """Base class for workflow node plugins."""

    category = PluginCategory.WORKFLOW_NODE

    async def execute(
        self, inputs: dict[str, Any], context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Execute the workflow node."""
        raise NotImplementedError


class PipelineStagePlugin(PluginBase):
    """Base class for pipeline stage plugins."""

    category = PluginCategory.PIPELINE_STAGE

    async def execute(
        self, inputs: dict[str, Any], context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Execute the pipeline stage."""
        raise NotImplementedError


# Capability decorator
def capability(
    name: str,
    description: str,
    input_schema: dict[str, Any] | None = None,
    output_schema: dict[str, Any] | None = None,
    tags: list[str] | None = None,
):
    """Decorator to mark a method as a plugin capability."""

    def decorator(func):
        func._plugin_capability = {
            "name": name,
            "description": description,
            "input_schema": input_schema or {},
            "output_schema": output_schema or {},
            "tags": tuple(tags or []),
        }
        return func

    return decorator


def plugin_main(cls):
    """Decorator to mark a class as the main plugin class."""
    cls._plugin_main = True
    return cls


def plugin_config(schema: dict[str, Any]):
    """Decorator to define plugin configuration schema."""

    def decorator(cls):
        cls.config_schema = schema
        return cls

    return decorator


# Event system for plugins
class PluginEventBus:
    """Simple event bus for plugin communication."""

    def __init__(self):
        self._subscribers: dict[str, list[Callable]] = {}

    def subscribe(self, event_type: str, callback: Callable) -> None:
        """Subscribe to an event type."""
        self._subscribers.setdefault(event_type, []).append(callback)

    def unsubscribe(self, event_type: str, callback: Callable) -> None:
        """Unsubscribe from an event type."""
        if event_type in self._subscribers:
            self._subscribers[event_type].remove(callback)

    async def emit(self, event_type: str, data: Any) -> None:
        """Emit an event."""
        for callback in self._subscribers.get(event_type, []):
            if asyncio.iscoroutinefunction(callback):
                await callback(data)
            else:
                callback(data)


# Plugin metadata helpers
def create_manifest(
    name: str,
    version: str,
    description: str,
    category: PluginCategory,
    author: str,
    license: str = "MIT",
    **kwargs: Any,
) -> PluginManifest:
    """Helper to create a plugin manifest."""
    return PluginManifest(
        name=name,
        version=version,
        description=description,
        category=category,
        author=author,
        license=license,
        **kwargs,
    )


def create_dependency(
    name: str,
    version: str,
    dep_type: PluginDependencyType | str = PluginDependencyType.REQUIRED,
    reason: str | None = None,
) -> PluginDependency:
    """Helper to create a plugin dependency."""
    dep_type_enum = (
        dep_type if isinstance(dep_type, PluginDependencyType) else PluginDependencyType(dep_type)
    )
    return PluginDependency(
        name=name,
        version=version,
        type=dep_type_enum,
        reason=reason,
    )


def create_capability(
    name: str,
    description: str,
    input_schema: dict[str, Any] | None = None,
    output_schema: dict[str, Any] | None = None,
    tags: list[str] | None = None,
) -> PluginCapability:
    """Helper to create a plugin capability."""
    return PluginCapability(
        name=name,
        description=description,
        input_schema=input_schema or {},
        output_schema=output_schema or {},
        tags=tuple(tags or []),
    )


# =============================================================================
# TypeScript Definitions (as docstrings for reference)
# =============================================================================

TYPESCRIPT_DEFINITIONS = """
// TypeScript definitions for Agentic OS Plugin SDK
// These are provided as reference for TypeScript plugin authors

interface PluginManifest {
  name: string;
  version: string;
  description: string;
  category: PluginCategory;
  author: string;
  license: string;
  homepage?: string;
  repository?: string;
  dependencies: PluginDependency[];
  capabilities: PluginCapability[];
  entry_point?: string;
  config_schema: Record<string, any>;
  permissions: string[];
  min_platform_version: string;
  max_platform_version?: string;
  keywords: string[];
  signature?: string;
  public_key?: string;
}

type PluginCategory =
  | "agent"
  | "tool"
  | "provider"
  | "mcp_server"
  | "workflow_node"
  | "pipeline_stage"
  | "ui_component"
  | "integration"
  | "utility";

type PluginStatus =
  | "uninstalled"
  | "installing"
  | "installed"
  | "starting"
  | "running"
  | "stopping"
  | "stopped"
  | "failed"
  | "updating"
  | "uninstalling";

interface PluginDependency {
  name: string;
  version: string;
  type: "required" | "optional" | "peer";
  reason?: string;
}

interface PluginCapability {
  name: string;
  description: string;
  inputSchema: Record<string, any>;
  outputSchema?: Record<string, any>;
  tags: string[];
}

interface PluginConfig {
  plugin_name: string;
  values: Record<string, any>;
  schema: Record<string, any>;
  updated_at: string;
  updated_by: string;
}

// Base plugin class (Python equivalent)
abstract class PluginBase {
  abstract name: string;
  abstract version: string;
  abstract description: string;
  abstract category: PluginCategory;
  abstract author: string;
  abstract license: string;

  config: Record<string, any>;

  constructor(config?: Record<string, any>);

  async ainit(): Promise<void>;
  start(): void;
  stop(): void;
  cleanup(): void;

  getManifest(): PluginManifest;
  registerCapability(name: string, func: Function, schemas?: {
    input_schema?: Record<string, any>;
    output_schema?: Record<string, any>;
    tags?: string[];
  }): void;
  async callCapability(name: string, ...args: any[]): Promise<any>;
}

// Specialized plugin base classes
abstract class AgentPlugin extends PluginBase {
  abstract execute(task: string, context?: Record<string, any>): Promise<any>;
}

abstract class ToolPlugin extends PluginBase {
  abstract execute(...args: any[]): Promise<any>;
}

abstract class ProviderPlugin extends PluginBase {
  abstract complete(prompt: string, options?: Record<string, any>): Promise<any>;
  abstract streamComplete(prompt: string, options?: Record<string, any>): AsyncGenerator<any>;
}

abstract class MCPServerPlugin extends PluginBase {
  abstract listTools(): Promise<Array<{ name: string; description: string; inputSchema: any }>>;
  abstract callTool(name: string, arguments: Record<string, any>): Promise<any>;
}

abstract class WorkflowNodePlugin extends PluginBase {
  abstract execute(
    inputs: Record<string, any>,
    context?: Record<string, any>
  ): Promise<Record<string, any>>;
}

abstract class PipelineStagePlugin extends PluginBase {
  abstract execute(
    inputs: Record<string, any>,
    context?: Record<string, any>
  ): Promise<Record<string, any>>;
}

// Decorators
function capability(
  name: string,
  description: string,
  inputSchema?: Record<string, any>,
  outputSchema?: Record<string, any>,
  tags?: string[]
): MethodDecorator;

function pluginMain(): ClassDecorator;

function pluginConfig(schema: Record<string, any>): ClassDecorator;

// Event bus
class PluginEventBus {
  subscribe(eventType: string, callback: (data: any) => void | Promise<void>): void;
  unsubscribe(eventType: string, callback: (data: any) => void | Promise<void>): void;
  async emit(eventType: string, data: any): Promise<void>;
}

// Manifest helpers
function createManifest(
  name: string,
  version: string,
  description: string,
  category: PluginCategory,
  author: string,
  license?: string,
  options?: Partial<PluginManifest>
): PluginManifest;

function createDependency(
  name: string,
  version: string,
  type?: "required" | "optional" | "peer",
  reason?: string
): PluginDependency;

function createCapability(
  name: string,
  description: string,
  inputSchema?: Record<string, any>,
  outputSchema?: Record<string, any>,
  tags?: string[]
): PluginCapability;
"""


# =============================================================================
# Plugin Template Generator
# =============================================================================


def generate_plugin_template(
    name: str,
    category: PluginCategory,
    author: str,
    description: str = "",
    version: str = "1.0.0",
) -> str:
    """Generate a plugin template file."""

    category_class_map = {
        PluginCategory.AGENT: "AgentPlugin",
        PluginCategory.TOOL: "ToolPlugin",
        PluginCategory.PROVIDER: "ProviderPlugin",
        PluginCategory.MCP_SERVER: "MCPServerPlugin",
        PluginCategory.WORKFLOW_NODE: "WorkflowNodePlugin",
        PluginCategory.PIPELINE_STAGE: "PipelineStagePlugin",
        PluginCategory.UI_COMPONENT: "PluginBase",
        PluginCategory.INTEGRATION: "PluginBase",
        PluginCategory.UTILITY: "PluginBase",
    }

    base_class = category_class_map.get(category, "PluginBase")

    template = f'''"""
{name} Plugin

{description}
"""

from agentic_os.core.plugin.sdk import (
    {base_class},
    capability,
    plugin_main,
    plugin_config,
    PluginCategory,
    PluginDependency,
    PluginCapability,
)


@plugin_main
@plugin_config({{
    "type": "object",
    "properties": {{
        "setting1": {{"type": "string", "description": "Example setting"}},
    }},
}})
class {name.replace("-", "_").title().replace("_", "")}Plugin({base_class}):
    """{description}"""

    name = "{name}"
    version = "{version}"
    description = "{description}"
    category = PluginCategory.{category.name}
    author = "{author}"
    license = "MIT"

    # Define dependencies if any
    dependencies = [
        # PluginDependency(name="other-plugin", version="1.0.0"),
    ]

    # Define capabilities
    capabilities = [
        # PluginCapability(
        #     name="my_capability",
        #     description="What this capability does",
        #     input_schema={{"type": "object", "properties": {{}}}},
        # ),
    ]

    # Required permissions
    permissions = [
        # "capability:name",
    ]

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config)
        # Initialize your plugin here

    async def ainit(self) -> None:
        """Async initialization."""
        await super().ainit()
        # Async setup here

    def start(self) -> None:
        """Start the plugin."""
        super().start()
        # Start logic here

    def stop(self) -> None:
        """Stop the plugin."""
        super().stop()
        # Stop logic here

    def cleanup(self) -> None:
        """Cleanup on unload."""
        super().cleanup()
        # Cleanup logic here

    # Example capability
    @capability(
        name="hello",
        description="Say hello",
        input_schema={{"type": "object", "properties": {{"name": {{"type": "string"}}}}}},
        output_schema={{"type": "object", "properties": {{"message": {{"type": "string"}}}}}},
    )
    async def hello(self, name: str = "World") -> dict[str, str]:
        return {{"message": f"Hello, {{name}}!"}}
'''

    return template


# =============================================================================
# Plugin Validation
# =============================================================================


class PluginValidator:
    """Validates plugin manifests and implementations."""

    @staticmethod
    def validate_manifest(manifest: PluginManifest) -> tuple[bool, list[str]]:
        """Validate a plugin manifest."""
        errors = []

        if not manifest.name:
            errors.append("Plugin name is required")

        if not manifest.version:
            errors.append("Plugin version is required")

        if not manifest.description:
            errors.append("Plugin description is required")

        if not manifest.author:
            errors.append("Plugin author is required")

        if not manifest.license:
            errors.append("Plugin license is required")

        # Validate version format (semver)
        import re

        if not re.match(r"^\d+\.\d+\.\d+", manifest.version):
            errors.append("Version should follow semantic versioning (e.g., 1.0.0)")

        # Validate dependencies
        for dep in manifest.dependencies:
            if not dep.name:
                errors.append("Dependency name is required")
            if not dep.version:
                errors.append(f"Dependency version required for {dep.name}")

        # Validate capabilities
        for cap in manifest.capabilities:
            if not cap.name:
                errors.append("Capability name is required")
            if not cap.description:
                errors.append(f"Capability description required for {cap.name}")

        return len(errors) == 0, errors

    @staticmethod
    def validate_config(config: dict[str, Any], schema: dict[str, Any]) -> tuple[bool, list[str]]:
        """Validate plugin configuration against schema."""
        # Basic validation - in production use jsonschema
        errors = []

        if schema.get("type") == "object":
            required = schema.get("required", [])
            for field in required:
                if field not in config:
                    errors.append(f"Required config field missing: {field}")

        return len(errors) == 0, errors


# =============================================================================
# Plugin Registry Client (for marketplace integration)
# =============================================================================


class PluginRegistryClient:
    """Client for interacting with the plugin registry."""

    def __init__(self, base_url: str, api_key: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    async def search(self, query: str, **filters: Any) -> list[PluginManifest]:
        """Search for plugins in the registry."""
        # Would make HTTP request to registry
        return []

    async def get_manifest(self, name: str, version: str | None = None) -> PluginManifest | None:
        """Get a plugin manifest from the registry."""
        return None

    async def download(self, name: str, version: str, destination: str) -> None:
        """Download a plugin."""
        pass

    async def publish(self, manifest: PluginManifest, package_path: str) -> str:
        """Publish a plugin to the registry."""
        return ""

    async def get_categories(self) -> list[PluginCategory]:
        """Get available categories."""
        return list(PluginCategory)


__all__ = [
    # Base classes
    "PluginBase",
    "AgentPlugin",
    "ToolPlugin",
    "ProviderPlugin",
    "MCPServerPlugin",
    "WorkflowNodePlugin",
    "PipelineStagePlugin",
    # Decorators
    "capability",
    "plugin_main",
    "plugin_config",
    # Event system
    "PluginEventBus",
    # Helpers
    "create_manifest",
    "create_dependency",
    "create_capability",
    # Validation
    "PluginValidator",
    # Registry client
    "PluginRegistryClient",
    # Template
    "generate_plugin_template",
    # TypeScript definitions (as string)
    "TYPESCRIPT_DEFINITIONS",
]
