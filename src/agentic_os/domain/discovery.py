"""
Discovery Domain Models

Domain layer for Phase 4 Milestone 2 — Automatic Runtime Discovery & Binding,
extended in Phase 6.1 with Local Agent Discovery & Auto-Binding.

Pure Python, no external dependencies. These models describe the configuration,
results, telemetry, and local agent registration of discovery operations.

Builds on top of the M1 execution engine domain models in ``domain/execution.py``.
Frozen dataclasses follow the same patterns as the M1 models.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4


def _utcnow() -> datetime:
    return datetime.now(UTC)


# ── Discovery Configuration ──


@dataclass(frozen=True, slots=True)
class DiscoveryProviderConfig:
    """Configuration for a single discovery provider within a profile.

    Controls whether a provider is enabled, how often it runs, its timeout,
    and any confidence override.
    """

    name: str
    provider_type: str
    enabled: bool = True
    interval_seconds: float = 60.0
    timeout_seconds: float = 10.0
    confidence_override: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "provider_type": self.provider_type,
            "enabled": self.enabled,
            "interval_seconds": self.interval_seconds,
            "timeout_seconds": self.timeout_seconds,
            "confidence_override": self.confidence_override,
            "extra": dict(self.extra),
        }

    def with_enabled(self, enabled: bool = True) -> DiscoveryProviderConfig:
        return DiscoveryProviderConfig(
            name=self.name,
            provider_type=self.provider_type,
            enabled=enabled,
            interval_seconds=self.interval_seconds,
            timeout_seconds=self.timeout_seconds,
            confidence_override=self.confidence_override,
            extra=self.extra,
        )

    def with_interval(self, interval_seconds: float) -> DiscoveryProviderConfig:
        return DiscoveryProviderConfig(
            name=self.name,
            provider_type=self.provider_type,
            enabled=self.enabled,
            interval_seconds=interval_seconds,
            timeout_seconds=self.timeout_seconds,
            confidence_override=self.confidence_override,
            extra=self.extra,
        )


@dataclass(frozen=True, slots=True)
class DiscoveryProfile:
    """Named profile selecting which providers to run and with what settings.

    Profiles enable different scanning strategies: "full" runs all providers,
    "quick" runs only PATH + env var, "ide-only" runs VS Code + JetBrains, etc.
    """

    name: str
    description: str = ""
    provider_configs: tuple[DiscoveryProviderConfig, ...] = field(default_factory=tuple)
    schedule_cron: str | None = None
    interval_seconds: float = 60.0
    validate_after_discovery: bool = True
    profile_after_discovery: bool = True
    auto_register: bool = True
    tags: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "provider_configs": [c.to_dict() for c in self.provider_configs],
            "schedule_cron": self.schedule_cron,
            "interval_seconds": self.interval_seconds,
            "validate_after_discovery": self.validate_after_discovery,
            "profile_after_discovery": self.profile_after_discovery,
            "auto_register": self.auto_register,
            "tags": list(self.tags),
        }

    def with_provider(self, config: DiscoveryProviderConfig) -> DiscoveryProfile:
        """Return a new profile with the given provider config added (or replaced)."""
        configs = list(self.provider_configs)
        for i, c in enumerate(configs):
            if c.name == config.name:
                configs[i] = config
                break
        else:
            configs.append(config)
        return DiscoveryProfile(
            name=self.name,
            description=self.description,
            provider_configs=tuple(configs),
            schedule_cron=self.schedule_cron,
            interval_seconds=self.interval_seconds,
            validate_after_discovery=self.validate_after_discovery,
            profile_after_discovery=self.profile_after_discovery,
            auto_register=self.auto_register,
            tags=self.tags,
        )

    def without_provider(self, name: str) -> DiscoveryProfile:
        """Return a new profile with the named provider removed."""
        configs = tuple(c for c in self.provider_configs if c.name != name)
        return DiscoveryProfile(
            name=self.name,
            description=self.description,
            provider_configs=configs,
            schedule_cron=self.schedule_cron,
            interval_seconds=self.interval_seconds,
            validate_after_discovery=self.validate_after_discovery,
            profile_after_discovery=self.profile_after_discovery,
            auto_register=self.auto_register,
            tags=self.tags,
        )

    def with_schedule(
        self, cron: str | None = None, interval: float | None = None
    ) -> DiscoveryProfile:
        """Return a new profile with updated scheduling."""
        return DiscoveryProfile(
            name=self.name,
            description=self.description,
            provider_configs=self.provider_configs,
            schedule_cron=cron if cron is not None else self.schedule_cron,
            interval_seconds=interval if interval is not None else self.interval_seconds,
            validate_after_discovery=self.validate_after_discovery,
            profile_after_discovery=self.profile_after_discovery,
            auto_register=self.auto_register,
            tags=self.tags,
        )


# ── Discovery Rules ──


@dataclass(frozen=True, slots=True)
class DiscoveryRule:
    """Rule for filtering discovered engines by criteria.

    Rules support string comparison on engine registration fields:
    ``name``, ``engine_type``, ``version``, ``capability``, ``platform``.

    Operators: ``eq``, ``ne``, ``gt``, ``gte``, ``lt``, ``lte``, ``in``, ``contains``, ``matches``.

    Action: ``accept`` (keep the engine) or ``reject`` (discard it).
    """

    field: str
    operator: str
    value: Any
    action: str = "accept"

    def matches(self, registration: dict[str, Any]) -> bool:
        """Check if this rule matches a registration dict from a provider."""
        actual = registration.get(self.field)
        if actual is None:
            return False

        op = self.operator
        val = self.value

        if op == "eq":
            return actual == val
        elif op == "ne":
            return actual != val
        elif op == "gt":
            return actual > val
        elif op == "gte":
            return actual >= val
        elif op == "lt":
            return actual < val
        elif op == "lte":
            return actual <= val
        elif op == "in":
            return actual in val if isinstance(val, (list, tuple, set)) else actual == val
        elif op == "contains":
            return val in actual if isinstance(actual, (str, list, tuple)) else False
        elif op == "matches":
            import re

            return bool(re.search(str(val), str(actual)))
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "operator": self.operator,
            "value": self.value,
            "action": self.action,
        }


# ── Caching ──


@dataclass(frozen=True, slots=True)
class DiscoveryCacheEntry:
    """Cached discovery result with TTL tracking.

    The ``key`` is a deterministic hash of (provider_name, engine_name, endpoint)
    so the same engine discovered by the same provider returns the cached entry.
    """

    key: str
    registration_json: str
    confidence: float
    provider_name: str
    discovered_at: datetime
    expires_at: datetime
    hit_count: int = 0
    _version: int = 1

    def is_expired(self) -> bool:
        """Check if this cache entry has expired."""
        return _utcnow() >= self.expires_at

    def with_hit(self) -> DiscoveryCacheEntry:
        """Return a copy with incremented hit count."""
        return DiscoveryCacheEntry(
            key=self.key,
            registration_json=self.registration_json,
            confidence=self.confidence,
            provider_name=self.provider_name,
            discovered_at=self.discovered_at,
            expires_at=self.expires_at,
            hit_count=self.hit_count + 1,
            _version=self._version,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "provider_name": self.provider_name,
            "confidence": self.confidence,
            "discovered_at": self.discovered_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "hit_count": self.hit_count,
            "expired": self.is_expired(),
        }


# ── Telemetry ──


@dataclass(frozen=True, slots=True)
class DiscoveryTelemetryEntry:
    """Record of a single discovery scan operation."""

    id: str = field(default_factory=lambda: uuid4().hex)
    profile_name: str = "default"
    started_at: datetime = field(default_factory=_utcnow)
    completed_at: datetime | None = None
    providers_run: int = 0
    providers_failed: int = 0
    engines_found: int = 0
    engines_new: int = 0
    engines_validated: int = 0
    engines_registered: int = 0
    errors: tuple[str, ...] = field(default_factory=tuple)

    @property
    def duration_ms(self) -> float:
        """Compute duration in milliseconds."""
        if self.completed_at is None:
            return 0.0
        delta = self.completed_at - self.started_at
        return delta.total_seconds() * 1000.0

    def with_completed(self, **updates: Any) -> DiscoveryTelemetryEntry:
        """Return a completed copy of this entry with optional field updates."""
        kwargs: dict[str, Any] = {
            "id": self.id,
            "profile_name": self.profile_name,
            "started_at": self.started_at,
            "completed_at": updates.pop("completed_at", _utcnow()),
            "providers_run": updates.pop("providers_run", self.providers_run),
            "providers_failed": updates.pop("providers_failed", self.providers_failed),
            "engines_found": updates.pop("engines_found", self.engines_found),
            "engines_new": updates.pop("engines_new", self.engines_new),
            "engines_validated": updates.pop("engines_validated", self.engines_validated),
            "engines_registered": updates.pop("engines_registered", self.engines_registered),
            "errors": tuple(updates.pop("errors", self.errors)),
        }
        return DiscoveryTelemetryEntry(**kwargs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "profile_name": self.profile_name,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_ms": self.duration_ms,
            "providers_run": self.providers_run,
            "providers_failed": self.providers_failed,
            "engines_found": self.engines_found,
            "engines_new": self.engines_new,
            "engines_validated": self.engines_validated,
            "engines_registered": self.engines_registered,
            "errors": list(self.errors),
        }


# ── Validation ──


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Result of validating a single discovered engine against one or more criteria."""

    engine_id: str
    engine_name: str
    valid: bool
    executable_exists: bool = False
    version_detected: str | None = None
    health_check_passed: bool = False
    capability_match: bool = False
    permission_ok: bool = True
    integrity_ok: bool = True
    errors: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    validated_at: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "engine_id": self.engine_id,
            "engine_name": self.engine_name,
            "valid": self.valid,
            "executable_exists": self.executable_exists,
            "version_detected": self.version_detected,
            "health_check_passed": self.health_check_passed,
            "capability_match": self.capability_match,
            "permission_ok": self.permission_ok,
            "integrity_ok": self.integrity_ok,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "validated_at": self.validated_at.isoformat(),
        }

    @classmethod
    def passed(cls, engine_id: str, engine_name: str, **extra: Any) -> ValidationResult:
        """Factory for a passing validation result."""
        return cls(
            engine_id=engine_id,
            engine_name=engine_name,
            valid=True,
            **extra,
        )

    @classmethod
    def failed(
        cls, engine_id: str, engine_name: str, *errors: str, **extra: Any
    ) -> ValidationResult:
        """Factory for a failing validation result."""
        return cls(
            engine_id=engine_id,
            engine_name=engine_name,
            valid=False,
            errors=errors,
            **extra,
        )


# ── Profiling ──


@dataclass(frozen=True, slots=True)
class ProfileResult:
    """Auto-generated profile from a discovered engine's metadata and validation."""

    engine_id: str
    engine_name: str
    version: str
    executable_path: str
    platform: str
    capabilities: tuple[str, ...] = field(default_factory=tuple)
    supports_streaming: bool = False
    supports_mcp: bool = False
    latency_estimate_ms: float = 0.0
    cost_estimate: float = 0.0
    resource_footprint_mb: float = 0.0
    config_defaults: dict[str, Any] = field(default_factory=dict)
    profiled_at: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "engine_id": self.engine_id,
            "engine_name": self.engine_name,
            "version": self.version,
            "executable_path": self.executable_path,
            "platform": self.platform,
            "capabilities": list(self.capabilities),
            "supports_streaming": self.supports_streaming,
            "supports_mcp": self.supports_mcp,
            "latency_estimate_ms": self.latency_estimate_ms,
            "cost_estimate": self.cost_estimate,
            "resource_footprint_mb": self.resource_footprint_mb,
            "config_defaults": dict(self.config_defaults),
            "profiled_at": self.profiled_at.isoformat(),
        }

    @classmethod
    def from_registration(
        cls,
        engine_id: str,
        engine_name: str,
        version: str,
        executable_path: str,
        capabilities: list[str],
        platform_name: str | None = None,
    ) -> ProfileResult:
        """Factory from minimal discovery metadata."""
        import platform

        return cls(
            engine_id=engine_id,
            engine_name=engine_name,
            version=version,
            executable_path=executable_path,
            platform=platform_name or platform.system().lower(),
            capabilities=tuple(capabilities),
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 6.1 — Local Agent Discovery & Auto-Binding
# ═══════════════════════════════════════════════════════════════════════════════


class AgentStatus(StrEnum):
    """Operational status of a locally discovered agent."""

    RUNNING = "running"
    STOPPED = "stopped"
    CRASHED = "crashed"
    BUSY = "busy"
    IDLE = "idle"
    UPDATING = "updating"
    RESTARTING = "restarting"
    UNKNOWN = "unknown"


class AgentCapability(StrEnum):
    """Capabilities an agent can advertise."""

    CODE_GENERATION = "code_generation"
    CODE_REVIEW = "code_review"
    TESTING = "testing"
    DEBUGGING = "debugging"
    CHAT = "chat"
    SEARCH = "search"
    FILE_OPS = "file_operations"
    TERMINAL_OPS = "terminal_operations"
    BROWSER_OPS = "browser_operations"
    IMAGE_GENERATION = "image_generation"
    EMBEDDINGS = "embeddings"
    REASONING = "reasoning"
    PLANNING = "planning"
    MEMORY = "memory"
    MCP = "mcp"
    API_GATEWAY = "api_gateway"
    CUSTOM = "custom"


@dataclass(frozen=True, slots=True)
class LocalAgent:
    """A locally discovered AI agent registered with Mission Control.

    Captures every piece of metadata about an installed AI tool on the
    local workstation — binary path, version, capabilities, health, and
    runtime resource consumption.
    """

    id: str
    name: str
    tool_type: str  # "hermes", "claude-code", "codex", "gemini-cli", "ollama", etc.
    version: str
    status: AgentStatus = AgentStatus.UNKNOWN
    executable_path: str = ""
    working_directory: str = ""
    pid: int | None = None
    capabilities: tuple[AgentCapability, ...] = field(default_factory=tuple)
    supported_models: tuple[str, ...] = field(default_factory=tuple)
    supported_providers: tuple[str, ...] = field(default_factory=tuple)
    health_score: float = 0.0
    last_seen: datetime = field(default_factory=_utcnow)
    discovered_at: datetime = field(default_factory=_utcnow)
    latency_ms: float = 0.0
    memory_mb: float = 0.0
    cpu_percent: float = 0.0
    threads: int = 0
    uptime_seconds: float = 0.0
    restart_count: int = 0
    configuration: dict[str, Any] = field(default_factory=dict)
    tags: tuple[str, ...] = field(default_factory=tuple)
    error: str = ""

    def running(self) -> bool:
        """Check if the agent is in a running-like state."""
        return self.status in (
            AgentStatus.RUNNING,
            AgentStatus.IDLE,
            AgentStatus.BUSY,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        return {
            "id": self.id,
            "name": self.name,
            "tool_type": self.tool_type,
            "version": self.version,
            "status": self.status.value,
            "executable_path": self.executable_path,
            "working_directory": self.working_directory,
            "pid": self.pid,
            "capabilities": [c.value for c in self.capabilities],
            "supported_models": list(self.supported_models),
            "supported_providers": list(self.supported_providers),
            "health_score": self.health_score,
            "last_seen": self.last_seen.isoformat(),
            "discovered_at": self.discovered_at.isoformat(),
            "latency_ms": self.latency_ms,
            "memory_mb": self.memory_mb,
            "cpu_percent": self.cpu_percent,
            "threads": self.threads,
            "uptime_seconds": self.uptime_seconds,
            "restart_count": self.restart_count,
            "configuration": dict(self.configuration),
            "tags": list(self.tags),
            "error": self.error,
            "running": self.running(),
        }


@dataclass(frozen=True, slots=True)
class AgentHealthRecord:
    """A single health check record for a local agent."""

    agent_id: str
    status: AgentStatus
    health_score: float
    latency_ms: float
    memory_mb: float
    cpu_percent: float
    threads: int
    pid: int | None
    checked_at: datetime = field(default_factory=_utcnow)
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "status": self.status.value,
            "health_score": self.health_score,
            "latency_ms": self.latency_ms,
            "memory_mb": self.memory_mb,
            "cpu_percent": self.cpu_percent,
            "threads": self.threads,
            "pid": self.pid,
            "checked_at": self.checked_at.isoformat(),
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class AgentDiscoveryConfig:
    """Configuration for local agent discovery.

    Controls which tools to look for, discovery paths, and auto-binding
    behaviour.
    """

    enabled_tools: tuple[str, ...] = field(
        default_factory=lambda: (
            "hermes",
            "claude-code",
            "codex",
            "gemini-cli",
            "opencode",
            "aider",
            "continue",
            "openhands",
            "ollama",
            "lm-studio",
            "vllm",
            "docker",
            "git",
            "python",
            "node",
            "vscode-cli",
        )
    )
    scan_path: bool = True
    scan_registry: bool = True
    scan_processes: bool = True
    scan_common_dirs: bool = True
    scan_env_vars: bool = True
    auto_register: bool = True
    auto_bind: bool = True
    health_check_interval_seconds: float = 15.0
    discovery_interval_seconds: float = 120.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled_tools": list(self.enabled_tools),
            "scan_path": self.scan_path,
            "scan_registry": self.scan_registry,
            "scan_processes": self.scan_processes,
            "scan_common_dirs": self.scan_common_dirs,
            "scan_env_vars": self.scan_env_vars,
            "auto_register": self.auto_register,
            "auto_bind": self.auto_bind,
            "health_check_interval_seconds": self.health_check_interval_seconds,
            "discovery_interval_seconds": self.discovery_interval_seconds,
        }


@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    """Result of a single local agent discovery scan."""

    agents_found: int = 0
    agents_new: int = 0
    agents_updated: int = 0
    agents_registered: int = 0
    errors: tuple[str, ...] = field(default_factory=tuple)
    scanned_at: datetime = field(default_factory=_utcnow)
    duration_ms: float = 0.0
    tools_detected: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agents_found": self.agents_found,
            "agents_new": self.agents_new,
            "agents_updated": self.agents_updated,
            "agents_registered": self.agents_registered,
            "errors": list(self.errors),
            "scanned_at": self.scanned_at.isoformat(),
            "duration_ms": self.duration_ms,
            "tools_detected": list(self.tools_detected),
        }
