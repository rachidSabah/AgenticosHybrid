"""OmniRoute domain entities — provider/model registry, routing policies,
token compression, budget tracking, failover, and telemetry.

Pure data (Pydantic v2). No behavior, no I/O. Shared vocabulary between
OmniRoute ports, the core engine, and the API layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _new_id() -> str:
    return uuid4().hex[:12]


# ── Enums ──


class OmniRouteStatus(StrEnum):
    INITIALIZING = "initializing"
    ACTIVE = "active"
    DEGRADED = "degraded"
    FAILED = "failed"
    STOPPED = "stopped"


class ProviderDiscoveryStatus(StrEnum):
    DISCOVERED = "discovered"
    REGISTERED = "registered"
    CONNECTED = "connected"
    FAILED = "failed"
    REMOVED = "removed"


class TokenCompressionStrategy(StrEnum):
    NONE = "none"
    PROMPT_TRUNCATION = "prompt_truncation"
    HISTORY_SUMMARIZATION = "history_summarization"
    SEMANTIC_COMPRESSION = "semantic_compression"
    CACHE_AWARE = "cache_aware"
    ADAPTIVE = "adaptive"


class RoutingPolicyType(StrEnum):
    FASTEST = "fastest"
    CHEAPEST = "cheapest"
    BALANCED = "balanced"
    QUALITY = "quality"
    REASONING = "reasoning"
    VISION = "vision"
    CODING = "coding"
    LONG_CONTEXT = "long_context"
    WEIGHTED = "weighted"
    ROUND_ROBIN = "round_robin"
    RANDOM = "random"
    STICKY_SESSIONS = "sticky_sessions"
    PRIORITY = "priority"
    CAPABILITY = "capability"
    BUDGET = "budget"
    LATENCY = "latency"
    HEALTH = "health"
    CUSTOM = "custom"


class FailoverState(StrEnum):
    IDLE = "idle"
    RETRYING = "retrying"
    FAILING_OVER = "failing_over"
    CIRCUIT_OPEN = "circuit_open"
    CIRCUIT_HALF_OPEN = "circuit_half_open"
    RECOVERED = "recovered"


# ── Domain types ──


@dataclass(frozen=True, slots=True)
class OmniRouteProvider:
    """A provider registered in the OmniRoute provider registry."""

    id: str = field(default_factory=_new_id)
    name: str = ""
    kind: str = ""
    base_url: str = ""
    api_key_ref: str = ""
    enabled: bool = True
    capabilities: tuple[str, ...] = field(default_factory=tuple)
    models: tuple[str, ...] = field(default_factory=tuple)
    latency_ms: float = 0.0
    cost_per_1k_input: float = 0.0
    cost_per_1k_output: float = 0.0
    context_window: int = 0
    supports_streaming: bool = True
    supports_reasoning: bool = False
    supports_vision: bool = False
    supports_tools: bool = False
    status: ProviderDiscoveryStatus = ProviderDiscoveryStatus.DISCOVERED
    priority: int = 0
    fallback_order: int = 0
    rate_limit: int = 0
    version: str = ""
    healthy: bool = False
    last_health_check: datetime | None = None
    error_message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)


@dataclass(frozen=True, slots=True)
class OmniRouteModel:
    """A model discovered from a provider."""

    id: str = field(default_factory=_new_id)
    model_id: str = ""
    provider: str = ""
    provider_id: str = ""
    display_name: str = ""
    model_family: str = ""
    context_window: int = 0
    max_output_tokens: int = 4096
    input_cost_per_1k: float = 0.0
    output_cost_per_1k: float = 0.0
    capabilities: tuple[str, ...] = field(default_factory=tuple)
    supports_streaming: bool = True
    supports_reasoning: bool = False
    supports_vision: bool = False
    supports_tools: bool = False
    is_default: bool = False
    latency_ms: float = 0.0
    quality_score: float = 0.5
    throughput: float = 0.0
    tokenizer: str = ""
    healthy: bool = False
    enabled: bool = True
    tags: tuple[str, ...] = field(default_factory=tuple)
    version: str = ""
    aliases: tuple[str, ...] = field(default_factory=tuple)
    input_modalities: tuple[str, ...] = field(default_factory=tuple)
    output_modalities: tuple[str, ...] = field(default_factory=tuple)
    discovered_at: datetime = field(default_factory=_utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RoutingPolicy:
    """A configurable routing policy that controls RouterEngine behavior.

    Scoped to workspace, agent, or user for fine-grained control.
    weight_overrides and filter settings override defaults when non-empty.
    """

    id: str = field(default_factory=_new_id)
    name: str = ""
    description: str = ""
    enabled: bool = True
    priority: int = 0
    strategy: str = "balanced"
    # Provider / model / capability filters
    provider_filter: tuple[str, ...] = field(default_factory=tuple)
    model_filter: tuple[str, ...] = field(default_factory=tuple)
    capability_filter: tuple[str, ...] = field(default_factory=tuple)
    # Weight overrides (used by custom-weighted and balanced strategies)
    weight_overrides: dict[str, float] = field(default_factory=dict)
    # Threshold overrides
    budget_override: float = 0.0
    latency_override_ms: float = 0.0
    context_override: int = 0
    # Scope — empty means global
    workspace_scope: str = ""
    agent_scope: str = ""
    user_scope: str = ""
    # Metadata
    metadata: dict[str, Any] = field(default_factory=dict)
    version: str = "1.0.0"
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)


@dataclass(frozen=True, slots=True)
class PolicyResult:
    """Result of evaluating one or more policies against candidates."""

    policy_name: str = ""
    policy_id: str = ""
    strategy: str = "balanced"
    selected_provider: str = ""
    selected_provider_id: str = ""
    selected_model: str = ""
    selected_model_id: str = ""
    selected_cost: float = 0.0
    selected_latency_ms: float = 0.0
    scored_candidates: tuple[tuple[str, str, str, float], ...] = field(default_factory=tuple)
    reason: str = ""
    evaluation_time_ms: float = 0.0
    policy_applied: bool = False
    overrides_used: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TokenCompressionResult:
    """Result of a token compression operation."""

    original_tokens: int = 0
    compressed_tokens: int = 0
    compression_ratio: float = 0.0
    savings_pct: float = 0.0
    compressed_text: str = ""
    strategy: TokenCompressionStrategy = TokenCompressionStrategy.NONE
    duration_ms: float = 0.0


@dataclass(frozen=True, slots=True)
class CompressionStats:
    """Aggregate compression statistics."""

    total_original_tokens: int = 0
    total_compressed_tokens: int = 0
    total_savings_pct: float = 0.0
    total_tokens_saved: int = 0
    total_requests_compressed: int = 0
    total_duration_ms: float = 0.0
    by_strategy: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class BudgetRecord:
    """A single budget tracking record."""

    id: str = field(default_factory=_new_id)
    provider: str = ""
    model: str = ""
    mission_id: str = ""
    user_id: str = ""
    workflow_id: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost: float = 0.0
    request_type: str = "chat"
    timestamp: datetime = field(default_factory=_utcnow)


@dataclass(frozen=True, slots=True)
class BudgetSummary:
    """Aggregate budget summary."""

    today_cost: float = 0.0
    today_tokens: int = 0
    today_requests: int = 0
    monthly_cost: float = 0.0
    monthly_tokens: int = 0
    monthly_requests: int = 0
    saved_cost: float = 0.0
    local_ratio: float = 0.0
    per_provider: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class FailoverEvent:
    """An event recording a failover from one provider to another."""

    id: str = field(default_factory=_new_id)
    timestamp: datetime = field(default_factory=_utcnow)
    from_provider: str = ""
    from_model: str = ""
    to_provider: str = ""
    to_model: str = ""
    reason: str = ""
    status: str = "success"
    attempt: int = 1
    latency_ms: float = 0.0
    recovered: bool = True


@dataclass(frozen=True, slots=True)
class CircuitBreakerState:
    """State of a circuit breaker for a provider."""

    provider: str = ""
    state: FailoverState = FailoverState.IDLE
    failure_count: int = 0
    last_failure: datetime | None = None
    last_success: datetime | None = None
    circuit_open_until: datetime | None = None
    half_open_attempts: int = 0


@dataclass(frozen=True, slots=True)
class ProviderAuthConfig:
    """Authentication configuration for a provider."""

    id: str = field(default_factory=_new_id)
    provider: str = ""
    auth_type: str = "api_key"
    api_key: str = ""
    oauth_token: str = ""
    oauth_refresh_token: str = ""
    bearer_token: str = ""
    oauth_client_id: str = ""
    oauth_client_secret: str = ""
    oauth_scopes: str = ""
    token_url: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    validated: bool = False
    last_validated: datetime | None = None
    expires_at: datetime | None = None
    created_at: datetime = field(default_factory=_utcnow)


@dataclass(frozen=True, slots=True)
class OmniRouteTelemetry:
    """Live telemetry snapshot of the OmniRoute engine."""

    status: OmniRouteStatus = OmniRouteStatus.INITIALIZING
    uptime_seconds: float = 0.0
    requests_processed: int = 0
    active_routes: int = 0
    avg_latency_ms: float = 0.0
    compression_savings_pct: float = 0.0
    total_tokens_saved: int = 0
    today_cost_saved: float = 0.0
    local_execution_ratio: float = 0.0
    providers_online: int = 0
    providers_total: int = 0
    models_discovered: int = 0
    failovers_today: int = 0
    circuit_breakers_open: int = 0
    policies_active: int = 0
    memory_usage_mb: float = 0.0
    eventbus_events_per_min: float = 0.0


@dataclass(frozen=True, slots=True)
class OmniRouteHealth:
    """Health check results for the OmniRoute subsystem."""

    routing_engine: bool = False
    provider_registry: bool = False
    model_registry: bool = False
    token_compression: bool = False
    budget_engine: bool = False
    failover_engine: bool = False
    auth_manager: bool = False
    health_monitor: bool = False
    policy_engine: bool = False
    sqlite_storage: bool = False
    websocket_server: bool = False
    api_gateway: bool = False
    mcp_server: bool = False
    a2a_server: bool = False
    all_healthy: bool = False
    errors: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RouteDecision:
    """Result of a routing decision for a prompt/request."""

    id: str = field(default_factory=_new_id)
    prompt_preview: str = ""
    policy_used: str = ""
    target_provider: str = ""
    target_model: str = ""
    fallback_provider: str = ""
    fallback_model: str = ""
    estimated_cost: float = 0.0
    estimated_latency_ms: float = 0.0
    compression_savings_pct: float = 0.0
    provider_healthy: bool = False
    fallback_healthy: bool = False
    status: str = "routed"
    reasoning: str = ""
    timestamp: datetime = field(default_factory=_utcnow)


# ── Phase 5.3: Router Engine domain models ──


@dataclass(frozen=True, slots=True)
class RoutingRequest:
    """A request to the RouterEngine for provider/model selection.

    All fields have sensible defaults — only required_capabilities is
    typically needed for a basic route() call.
    """

    task_type: str = "chat"
    required_capabilities: tuple[str, ...] = field(default_factory=tuple)
    preferred_provider: str = ""
    preferred_model: str = ""
    budget_limit: float = 0.0
    max_latency_ms: float = 0.0
    quality_weight: float = 1.0
    cost_weight: float = 1.0
    latency_weight: float = 1.0
    streaming_required: bool = False
    vision_required: bool = False
    reasoning_required: bool = False
    tools_required: bool = False
    minimum_context: int = 0
    workspace: str = ""
    agent: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)
    priority: int = 0
    source: str = "unknown"
    request_id: str = field(default_factory=_new_id)
    user_id: str = ""
    mission_id: str = ""
    workflow_id: str = ""


@dataclass(frozen=True, slots=True)
class RoutingScore:
    """Detailed scoring breakdown for a provider+model candidate."""

    quality_score: float = 0.0
    cost_score: float = 0.0
    latency_score: float = 0.0
    health_score: float = 0.0
    reliability_score: float = 0.0
    context_score: float = 0.0
    preference_score: float = 0.0
    weighted_total: float = 0.0
    candidate_count: int = 0
    rank: int = 0


@dataclass(frozen=True, slots=True)
class RoutingDecision:
    """Complete routing decision returned by the RouterEngine.

    Includes the selected route, a full fallback chain, and detailed scoring.
    """

    id: str = field(default_factory=_new_id)
    request_id: str = ""
    provider: str = ""
    provider_id: str = ""
    model: str = ""
    model_id: str = ""
    score: RoutingScore = field(default_factory=RoutingScore)
    reason: str = ""
    fallback_chain: tuple[tuple[str, str, str], ...] = field(default_factory=tuple)
    estimated_cost: float = 0.0
    estimated_latency_ms: float = 0.0
    confidence: float = 0.0
    policy_used: str = "weighted"
    status: str = "routed"
    timestamp: datetime = field(default_factory=_utcnow)
    alternatives_rejected: int = 0
