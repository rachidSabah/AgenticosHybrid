"""Domain models for the AI Brain Registry & Agent Constellation (Phase 6.2).

Every detected or registered AI capability — local CLI, cloud API, MCP server,
internal orchestrator — is modelled as a :class:`BrainRecord` with its runtime
identity, health, capabilities, and relationship graph. The constellation is
the union of all known brains at any moment.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class BrainType(StrEnum):
    """Classification of a brain's runtime origin."""

    LOCAL_CLI = "local_cli"
    CLOUD_API = "cloud_api"
    ORCHESTRATOR = "orchestrator"
    MCP_SERVER = "mcp_server"
    CUSTOM = "custom"


class BrainStatus(StrEnum):
    """Current lifecycle state of a brain."""

    DISCOVERED = "discovered"
    REGISTERED = "registered"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    BUSY = "busy"
    IDLE = "idle"
    EXECUTING = "executing"
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DEGRADED = "degraded"
    FAILED = "failed"
    REMOVED = "removed"
    PAUSED = "paused"
    RESUMED = "resumed"
    RESTARTING = "restarting"
    SHUTDOWN = "shutdown"
    RECOVERING = "recovering"


class BrainVendor(StrEnum):
    """Known AI brain vendors / providers."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    MISTRAL = "mistral"
    GROQ = "groq"
    AZURE = "azure"
    AWS = "aws"
    VERTEX = "vertex"
    OPENROUTER = "openrouter"
    COHERE = "cohere"
    DEEPSEEK = "deepseek"
    QWEN = "qwen"
    MOONSHOT = "moonshot"
    TOGETHER = "together"
    FIREWORKS = "fireworks"
    REPLICATE = "replicate"
    OLLAMA = "ollama"
    LM_STUDIO = "lm_studio"
    VLLM = "vllm"
    HERMES = "hermes"
    CLAUDE_CODE = "claude_code"
    GEMINI_CLI = "gemini_cli"
    CODEX = "codex"
    OPENCODE = "opencode"
    AIDER = "aider"
    CONTINUE = "continue"
    GITHUB_COPILOT = "github_copilot"
    CURSOR = "cursor"
    CUSTOM = "custom"


class BrainRuntime(StrEnum):
    """Underlying runtime environment for a brain."""

    PYTHON = "python"
    NODE = "node"
    GO = "go"
    RUST = "rust"
    CONTAINER = "container"
    NATIVE = "native"
    CLOUD = "cloud"
    UNKNOWN = "unknown"
    BUN = "bun"
    DENO = "deno"


class RelationshipType(StrEnum):
    """Semantic relationship between two brains in the constellation."""

    PARENT = "parent"
    CHILD = "child"
    PEER = "peer"
    EXECUTOR = "executor"
    PLANNER = "planner"
    REVIEWER = "reviewer"
    OBSERVER = "observer"
    FALLBACK = "fallback"
    SHADOW = "shadow"
    MIRROR = "mirror"
    CONSENSUS = "consensus"
    DELEGATION = "delegation"
    COMMUNICATION = "communication"
    ROUTING = "routing"
    TOOL_USAGE = "tool_usage"
    SHARED_CONTEXT = "shared_context"
    EXECUTION_CHAIN = "execution_chain"
    MCP_CONNECTION = "mcp_connection"


@dataclass(frozen=True)
class BrainRecord:
    """Canonical record for one AI brain in the registry.

    Every brain — local CLI, cloud API, MCP server, or orchestrator — is
    represented by one frozen instance.  Fields are additive; use
    ``replace()`` to produce updated copies.
    """

    id: str
    display_name: str
    brain_type: BrainType
    vendor: BrainVendor
    runtime: BrainRuntime
    version: str
    status: BrainStatus
    health: float = 100.0
    capabilities: tuple[str, ...] = field(default_factory=tuple)
    supported_models: tuple[str, ...] = field(default_factory=tuple)
    supported_tools: tuple[str, ...] = field(default_factory=tuple)
    memory_usage: float = 0.0
    cpu_usage: float = 0.0
    latency: float = 0.0
    throughput: float = 0.0
    workspace: str = ""
    current_tasks: int = 0
    queue_depth: int = 0
    active_models: int = 0
    available_context: int = 0
    connection_state: str = "disconnected"
    uptime: float = 0.0
    heartbeat: float = 0.0
    tags: tuple[str, ...] = field(default_factory=tuple)
    priority: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    discovered_at: str = ""
    last_seen: str = ""
    session_count: int = 0
    error_count: int = 0
    last_error: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable dict (str enums, not enum values)."""
        return {
            "id": self.id,
            "display_name": self.display_name,
            "brain_type": self.brain_type.value,
            "vendor": self.vendor.value,
            "runtime": self.runtime.value,
            "version": self.version,
            "status": self.status.value,
            "health": self.health,
            "capabilities": list(self.capabilities),
            "supported_models": list(self.supported_models),
            "supported_tools": list(self.supported_tools),
            "memory_usage": self.memory_usage,
            "cpu_usage": self.cpu_usage,
            "latency": self.latency,
            "throughput": self.throughput,
            "workspace": self.workspace,
            "current_tasks": self.current_tasks,
            "queue_depth": self.queue_depth,
            "active_models": self.active_models,
            "available_context": self.available_context,
            "connection_state": self.connection_state,
            "uptime": self.uptime,
            "heartbeat": self.heartbeat,
            "tags": list(self.tags),
            "priority": self.priority,
            "metadata": dict(self.metadata),
            "discovered_at": self.discovered_at,
            "last_seen": self.last_seen,
            "session_count": self.session_count,
            "error_count": self.error_count,
            "last_error": self.last_error,
        }

    def running(self) -> bool:
        """Return True when the brain is in an active, healthy state."""
        return self.status in (
            BrainStatus.CONNECTED,
            BrainStatus.IDLE,
            BrainStatus.EXECUTING,
            BrainStatus.BUSY,
        )


@dataclass(frozen=True)
class BrainRelationship:
    """A directed edge between two brains in the constellation."""

    source_id: str
    target_id: str
    relationship_type: RelationshipType
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    weight: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relationship_type": self.relationship_type.value,
            "metadata": dict(self.metadata),
            "created_at": self.created_at,
            "weight": self.weight,
        }


@dataclass(frozen=True)
class ConstellationGraph:
    """Snapshot of the full agent constellation at a point in time."""

    nodes: tuple[str, ...] = field(default_factory=tuple)
    edges: tuple[BrainRelationship, ...] = field(default_factory=tuple)
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": list(self.nodes),
            "edges": [e.to_dict() for e in self.edges],
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class WorkspaceInfo:
    """Workspace awareness — what a brain knows about its environment."""

    current_repository: str = ""
    git_branch: str = ""
    active_files: tuple[str, ...] = field(default_factory=tuple)
    terminal_sessions: int = 0
    workspace_path: str = ""
    mcp_servers: tuple[str, ...] = field(default_factory=tuple)
    loaded_tools: tuple[str, ...] = field(default_factory=tuple)
    open_editors: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "current_repository": self.current_repository,
            "git_branch": self.git_branch,
            "active_files": list(self.active_files),
            "terminal_sessions": self.terminal_sessions,
            "workspace_path": self.workspace_path,
            "mcp_servers": list(self.mcp_servers),
            "loaded_tools": list(self.loaded_tools),
            "open_editors": list(self.open_editors),
        }
