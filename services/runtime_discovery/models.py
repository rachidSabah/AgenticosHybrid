from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any
from uuid import uuid4

__all__ = [
    # Enums
    "RuntimeStatus",
    "RuntimeType",
    "DiscoveryProviderType",
    "BindingStatus",
    "HealthStatus",
    "ValidationStatus",
    # Models
    "Runtime",
    "RuntimeProfile",
    "RuntimeConfiguration",
    "RuntimeCapability",
    "RuntimeHealth",
    "RuntimeValidation",
    "RuntimeValidationResult",
    "RuntimeCache",
    "RuntimeCacheEntry",
    "RuntimeBinding",
    "RuntimeTelemetry",
    "RuntimeEvent",
    "RuntimeMetadata",
    "RuntimeDiscoveryResult",
    "RuntimeBindingConfig",
]


class RuntimeStatus(StrEnum):
    DISCOVERED = "discovered"
    VALIDATING = "validating"
    VALIDATED = "validated"
    PROFILING = "profiling"
    BINDING = "binding"
    BOUND = "bound"
    ACTIVE = "active"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    DISABLED = "disabled"
    UNBOUND = "unbound"
    LOST = "lost"


class RuntimeType(StrEnum):
    CLAUDE_CODE = "claude_code"
    GEMINI_CLI = "gemini_cli"
    CODEX_CLI = "codex_cli"
    HERMES = "hermes"
    OPENHANDS = "openhands"
    AIDER = "aider"
    CONTINUE = "continue"
    CLINE = "cline"
    ROO_CODE = "roo_code"
    OLLAMA = "ollama"
    PYTHON = "python"
    NODEJS = "nodejs"
    DOCKER = "docker"
    GIT = "git"
    GH_CLI = "gh_cli"
    MCP_SERVER = "mcp_server"
    CUSTOM = "custom"


class DiscoveryProviderType(StrEnum):
    PATH = "path"
    FILESYSTEM = "filesystem"
    ENV_VAR = "env_var"
    REGISTRY = "registry"
    WSL = "wsl"
    DOCKER = "docker"
    KNOWN_INSTALL_DIRS = "known_install_dirs"
    CONFIG_FILE = "config_file"
    VSCODE = "vscode"
    JETBRAINS = "jetbrains"
    CUSTOM = "custom"


class BindingStatus(StrEnum):
    PENDING = "pending"
    BINDING = "binding"
    BOUND = "bound"
    FAILED = "failed"
    UNBOUND = "unbound"


class HealthStatus(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class ValidationStatus(StrEnum):
    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class RuntimeCapability:
    namespace: str = ""
    description: str = ""
    version: str = ""
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RuntimeMetadata:
    vendor: str = ""
    homepage: str = ""
    docs_url: str = ""
    license_info: str = ""
    tags: list[str] = field(default_factory=list)
    custom: dict[str, Any] = field(default_factory=dict)


@dataclass
class RuntimeDiscoveryResult:
    runtime_type: RuntimeType = RuntimeType.CUSTOM
    name: str = ""
    display_name: str = ""
    version: str | None = None
    binary_path: str | None = None
    executable: str | None = None
    source: DiscoveryProviderType = DiscoveryProviderType.PATH
    confidence: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    found: bool = False
    error: str | None = None


@dataclass
class Runtime:
    runtime_id: str = field(default_factory=lambda: uuid4().hex[:16])
    runtime_type: RuntimeType = RuntimeType.CUSTOM
    name: str = ""
    display_name: str = ""
    version: str | None = None
    binary_path: str | None = None
    status: RuntimeStatus = RuntimeStatus.DISCOVERED
    capabilities: list[RuntimeCapability] = field(default_factory=list)
    metadata: RuntimeMetadata = field(default_factory=RuntimeMetadata)
    profile: RuntimeProfile | None = None
    configuration: RuntimeConfiguration | None = None
    health: RuntimeHealth | None = None
    binding: RuntimeBinding | None = None
    telemetry: RuntimeTelemetry | None = None
    tags: list[str] = field(default_factory=list)
    discovered_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_seen_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    confidence: float = 0.0
    source: DiscoveryProviderType = DiscoveryProviderType.PATH

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_id": self.runtime_id,
            "runtime_type": self.runtime_type.value,
            "name": self.name,
            "display_name": self.display_name,
            "version": self.version,
            "binary_path": self.binary_path,
            "status": self.status.value,
            "capabilities": [c.namespace for c in self.capabilities],
            "tags": list(self.tags),
            "discovered_at": self.discovered_at.isoformat(),
            "last_seen_at": self.last_seen_at.isoformat(),
            "confidence": self.confidence,
            "source": self.source.value,
        }


@dataclass
class RuntimeProfile:
    runtime_id: str = ""
    runtime_type: RuntimeType = RuntimeType.CUSTOM
    version: str = ""
    executable_path: str = ""
    platform: str = ""
    capabilities: list[str] = field(default_factory=list)
    supports_streaming: bool = False
    supports_mcp: bool = False
    supports_tools: bool = False
    supports_vision: bool = False
    latency_estimate_ms: float = 0.0
    cost_estimate: float = 0.0
    resource_footprint_mb: float = 0.0
    max_concurrency: int = 1
    config_defaults: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_id": self.runtime_id,
            "runtime_type": self.runtime_type.value,
            "version": self.version,
            "executable_path": self.executable_path,
            "platform": self.platform,
            "capabilities": list(self.capabilities),
            "supports_streaming": self.supports_streaming,
            "supports_mcp": self.supports_mcp,
            "latency_estimate_ms": self.latency_estimate_ms,
            "cost_estimate": self.cost_estimate,
            "resource_footprint_mb": self.resource_footprint_mb,
            "max_concurrency": self.max_concurrency,
        }


@dataclass
class RuntimeConfiguration:
    runtime_id: str = ""
    enabled: bool = True
    auto_start: bool = True
    health_check_interval_s: int = 60
    max_retries: int = 3
    timeout_s: float = 300.0
    environment: dict[str, str] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)
    permissions: list[str] = field(default_factory=list)
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_id": self.runtime_id,
            "enabled": self.enabled,
            "auto_start": self.auto_start,
            "health_check_interval_s": self.health_check_interval_s,
            "max_retries": self.max_retries,
            "timeout_s": self.timeout_s,
            "permissions": list(self.permissions),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass
class RuntimeHealth:
    runtime_id: str = ""
    status: HealthStatus = HealthStatus.UNKNOWN
    healthy: bool = True
    last_check: datetime | None = None
    last_error: str | None = None
    consecutive_failures: int = 0
    response_time_ms: float = 0.0
    uptime_s: float = 0.0
    version: str | None = None

    def record_success(self, response_time_ms: float = 0.0) -> None:
        self.healthy = True
        self.status = HealthStatus.HEALTHY
        self.last_check = datetime.now(UTC)
        self.consecutive_failures = 0
        self.response_time_ms = response_time_ms
        self.last_error = None

    def record_failure(self, error: str) -> None:
        self.healthy = False
        self.consecutive_failures += 1
        self.last_check = datetime.now(UTC)
        self.last_error = error
        if self.consecutive_failures >= 3:
            self.status = HealthStatus.UNHEALTHY
        else:
            self.status = HealthStatus.DEGRADED


@dataclass
class RuntimeValidation:
    runtime_id: str = ""
    status: ValidationStatus = ValidationStatus.PENDING
    executable_exists: bool = False
    version_detected: bool = False
    health_check_passed: bool = False
    capability_match: bool = False
    permission_ok: bool = False
    integrity_ok: bool = False
    errors: list[str] = field(default_factory=list)
    validated_at: datetime | None = None

    @staticmethod
    def passed() -> RuntimeValidation:
        return RuntimeValidation(
            status=ValidationStatus.PASSED,
            executable_exists=True,
            version_detected=True,
            health_check_passed=True,
            capability_match=True,
            permission_ok=True,
            integrity_ok=True,
            validated_at=datetime.now(UTC),
        )

    @staticmethod
    def failed(reason: str) -> RuntimeValidation:
        return RuntimeValidation(
            status=ValidationStatus.FAILED,
            errors=[reason],
            validated_at=datetime.now(UTC),
        )


@dataclass
class RuntimeValidationResult:
    runtime_id: str = ""
    runtime_type: RuntimeType = RuntimeType.CUSTOM
    name: str = ""
    status: ValidationStatus = ValidationStatus.PENDING
    checks: dict[str, bool] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    validated_at: datetime | None = None


@dataclass
class RuntimeCacheEntry:
    key: str = ""
    runtime_type: RuntimeType = RuntimeType.CUSTOM
    name: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime = field(default_factory=lambda: datetime.now(UTC) + timedelta(minutes=5))
    hit_count: int = 0

    def is_expired(self) -> bool:
        return datetime.now(UTC) > self.expires_at

    def with_hit(self) -> RuntimeCacheEntry:
        self.hit_count += 1
        return self


@dataclass
class RuntimeCache:
    entries: dict[str, RuntimeCacheEntry] = field(default_factory=dict)
    max_entries: int = 1000
    ttl_seconds: int = 300


@dataclass
class RuntimeBinding:
    runtime_id: str = ""
    engine_name: str = ""
    adapter_key: str = ""
    status: BindingStatus = BindingStatus.PENDING
    binding_config: RuntimeBindingConfig | None = None
    bound_at: datetime | None = None
    error: str | None = None


@dataclass
class RuntimeBindingConfig:
    auto_register: bool = True
    auto_start: bool = True
    adapter_params: dict[str, Any] = field(default_factory=dict)
    permission_overrides: list[str] = field(default_factory=list)
    environment_overrides: dict[str, str] = field(default_factory=dict)


@dataclass
class RuntimeTelemetry:
    runtime_id: str = ""
    runtime_type: RuntimeType = RuntimeType.CUSTOM
    name: str = ""
    tasks_completed: int = 0
    tasks_failed: int = 0
    tasks_cancelled: int = 0
    total_duration_s: float = 0.0
    avg_duration_s: float = 0.0
    total_errors: int = 0
    last_used: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def record_execution(self, duration_s: float, success: bool) -> None:
        if success:
            self.tasks_completed += 1
        else:
            self.tasks_failed += 1
        self.total_duration_s += duration_s
        self.last_used = datetime.now(UTC)
        total = self.tasks_completed + self.tasks_failed + self.tasks_cancelled
        self.avg_duration_s = self.total_duration_s / max(1, total)


@dataclass
class RuntimeEvent:
    event_id: str = field(default_factory=lambda: uuid4().hex[:16])
    runtime_id: str = ""
    event_type: str = ""
    source: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    payload: dict[str, Any] = field(default_factory=dict)
