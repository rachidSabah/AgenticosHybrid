"""BrainRecord schema and normalization models for Discovery Engine."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


def normalize_health_status(raw: Any) -> Literal["healthy", "degraded", "unhealthy", "unknown"]:
    """Normalize raw health metrics or string statuses into strict enum."""
    if isinstance(raw, (int, float)):
        scale = 100.0 if raw > 1.0 else 1.0
        if raw >= 0.8 * scale:
            return "healthy"
        if raw >= 0.4 * scale:
            return "degraded"
        return "unhealthy"
    if isinstance(raw, str):
        lowered = raw.lower()
        if lowered in ("healthy", "degraded", "unhealthy", "unknown"):
            return lowered  # type: ignore[return-value]
        if lowered in ("ok", "online", "connected", "ready"):
            return "healthy"
        if lowered in ("warning", "slow", "recovering"):
            return "degraded"
        if lowered in ("down", "error", "failed", "unreachable"):
            return "unhealthy"
    return "unknown"


class BrainRecord(BaseModel):
    """Normalized specification contract for discovered host runtimes and cloud models."""

    id: str
    display_name: str
    brain_type: Literal["local_cli", "cloud_api", "orchestrator", "mcp_server", "custom"]
    vendor: str
    runtime: str
    version: str = ""
    status: Literal["connected", "idle", "busy", "disconnected", "executing"] = "idle"
    health: Literal["healthy", "degraded", "unhealthy", "unknown"] = "healthy"
    capabilities: list[str] = Field(default_factory=list)
    supported_models: list[str] = Field(default_factory=list)
    supported_tools: list[str] = Field(default_factory=list)
    memory_usage: float = 0.0
    cpu_usage: float = 0.0
    latency: float = 0.0
    throughput: float = 0.0
    workspace: str = ""
    current_tasks: int = 0
    tags: list[str] = Field(default_factory=list)


class BrainRelationship(BaseModel):
    """Dependency or routing edge between orchestrator and executor brains."""

    id: str
    source_id: str
    target_id: str
    relationship_type: str = "executor"
    weight: float = 1.0
    active: bool = True
