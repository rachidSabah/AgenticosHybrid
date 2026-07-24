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
    CLOSED = "closed"
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
class CircuitBreakerConfig:
    """Configurable parameters for a circuit breaker."""

    failure_threshold: int = 5
    minimum_request_count: int = 3
    recovery_timeout_seconds: float = 30.0
    half_open_probe_count: int = 2
    sliding_window_size: int = 10


@dataclass(frozen=True, slots=True)
class ProviderCircuitMetrics:
    """Per-provider failure tracking metrics."""

    success_count: int = 0
    failure_count: int = 0
    consecutive_failures: int = 0
    failure_rate: float = 0.0
    last_failure: datetime | None = None
    last_success: datetime | None = None
    average_latency_ms: float = 0.0
    timeout_count: int = 0
    http_failures: int = 0
    authentication_failures: int = 0
    rate_limit_failures: int = 0
    network_failures: int = 0
    provider_unavailable_count: int = 0


@dataclass(frozen=True, slots=True)
class CircuitBreakerState:
    """Current state of a circuit breaker for a provider."""

    provider: str = ""
    state: FailoverState = FailoverState.IDLE
    failure_count: int = 0
    success_count: int = 0
    consecutive_failures: int = 0
    last_failure: datetime | None = None
    last_success: datetime | None = None
    circuit_open_until: datetime | None = None
    half_open_attempts: int = 0
    half_open_probe_successes: int = 0
    config: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)


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
    organization: str = ""
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


# ── Phase 5.6: Budget Engine domain models ──


class BudgetScope(StrEnum):
    GLOBAL = "global"
    ORGANIZATION = "organization"
    WORKSPACE = "workspace"
    AGENT = "agent"
    USER = "user"
    SESSION = "session"
    REQUEST = "request"
    PROVIDER = "provider"
    MODEL = "model"


@dataclass(frozen=True, slots=True)
class BudgetPolicy:
    """Budget policy definition for a scope."""

    id: str = field(default_factory=_new_id)
    scope: BudgetScope = BudgetScope.GLOBAL
    scope_id: str = ""  # e.g. org-id, workspace-id, user-id, provider-name, model-id
    enabled: bool = True
    priority: int = 0

    # Spend limits
    max_spend_total: float = 0.0  # 0 = unlimited
    max_spend_daily: float = 0.0
    max_spend_monthly: float = 0.0
    max_spend_per_request: float = 0.0
    max_spend_burst: float = 0.0  # max burst within evaluation window

    # Soft/hard limits
    soft_limit: float = 0.0  # warning threshold (fraction of total or absolute)
    hard_limit: float = 0.0  # hard cap (overrides all other limits)
    warning_threshold: float = 0.8  # fraction of limit that triggers warning

    currency: str = "USD"
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)


@dataclass(frozen=True, slots=True)
class BudgetReservation:
    """An atomic budget reservation for a candidate provider+model."""

    id: str = field(default_factory=_new_id)
    policy_id: str = ""
    scope: BudgetScope = BudgetScope.GLOBAL
    scope_id: str = ""
    provider: str = ""
    model: str = ""
    estimated_cost: float = 0.0
    max_cost: float = 0.0
    timestamp: datetime = field(default_factory=_utcnow)
    expires_at: datetime | None = None
    committed: bool = False
    rolled_back: bool = False
    released: bool = False


@dataclass(frozen=True, slots=True)
class BudgetUsage:
    """Current usage against a budget policy."""

    policy_id: str = ""
    scope: BudgetScope = BudgetScope.GLOBAL
    scope_id: str = ""
    total_spent: float = 0.0
    daily_spent: float = 0.0
    monthly_spent: float = 0.0
    request_count: int = 0
    daily_request_count: int = 0
    monthly_request_count: int = 0
    provider_spend: dict[str, float] = field(default_factory=dict)
    model_spend: dict[str, float] = field(default_factory=dict)
    active_reservations: float = 0.0
    last_updated: datetime = field(default_factory=_utcnow)


@dataclass(frozen=True, slots=True)
class BudgetResult:
    """Result of a budget evaluation for a candidate."""

    approved: bool = False
    rejected: bool = False
    reason: str = ""
    estimated_cost: float = 0.0
    max_cost: float = 0.0
    remaining_budget: float = 0.0
    reservation_id: str = ""
    effective_policy_id: str = ""
    effective_scope: BudgetScope = BudgetScope.GLOBAL
    warnings: tuple[str, ...] = field(default_factory=tuple)
    overrides_applied: tuple[str, ...] = field(default_factory=tuple)
    evaluation_time_ms: float = 0.0


@dataclass(frozen=True, slots=True)
class BudgetStatistics:
    """Aggregate budget engine statistics."""

    total_evaluations: int = 0
    approvals: int = 0
    rejections: int = 0
    reservation_count: int = 0
    active_reservations: int = 0
    commits: int = 0
    rollbacks: int = 0
    average_evaluation_time_ms: float = 0.0
    cost_saved: float = 0.0
    provider_spend: dict[str, float] = field(default_factory=dict)
    model_spend: dict[str, float] = field(default_factory=dict)
    workspace_spend: dict[str, float] = field(default_factory=dict)
    user_spend: dict[str, float] = field(default_factory=dict)
    organization_spend: dict[str, float] = field(default_factory=dict)
    limit_hits: dict[str, int] = field(default_factory=dict)  # scope -> count
    warnings_issued: int = 0


@dataclass(frozen=True, slots=True)
class BudgetAuditRecord:
    """An audit trail entry for budget operations."""

    id: str = field(default_factory=_new_id)
    action: str = ""  # approved, rejected, reserved, committed, rolled_back, released
    policy_id: str = ""
    scope: BudgetScope = BudgetScope.GLOBAL
    scope_id: str = ""
    provider: str = ""
    model: str = ""
    amount: float = 0.0
    reservation_id: str = ""
    reason: str = ""
    timestamp: datetime = field(default_factory=_utcnow)


@dataclass(frozen=True, slots=True)
class BudgetOverride:
    """A temporary override that adjusts a budget policy's limits."""

    id: str = field(default_factory=_new_id)
    policy_id: str = ""
    reason: str = ""
    overridden_limits: dict[str, float] = field(default_factory=dict)
    expires_at: datetime | None = None
    applied_by: str = ""
    timestamp: datetime = field(default_factory=_utcnow)


@dataclass(frozen=True, slots=True)
class BudgetSnapshot:
    """Point-in-time snapshot of all budget engine state."""

    timestamp: datetime = field(default_factory=_utcnow)
    policies: tuple[BudgetPolicy, ...] = field(default_factory=tuple)
    usage: tuple[BudgetUsage, ...] = field(default_factory=tuple)
    active_reservations: tuple[BudgetReservation, ...] = field(default_factory=tuple)
    statistics: BudgetStatistics = field(default_factory=BudgetStatistics)
    emergency_mode: bool = False


@dataclass(frozen=True, slots=True)
class BudgetForecast:
    """Projected budget usage and remaining runway."""

    projected_daily_spend: float = 0.0
    projected_monthly_spend: float = 0.0
    remaining_daily_budget: float = 0.0
    remaining_monthly_budget: float = 0.0
    estimated_days_remaining: float = 0.0
    estimated_runway_days: float = 0.0
    provider_forecast: dict[str, float] = field(default_factory=dict)
    model_forecast: dict[str, float] = field(default_factory=dict)
    at_risk: bool = False
    warnings: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class BudgetDecision:
    """Combined decision from budget engine across all candidates."""

    approved: bool = False
    rejected: bool = False
    reason: str = ""
    filtered_candidates: tuple[str, ...] = field(default_factory=tuple)
    results: tuple[BudgetResult, ...] = field(default_factory=tuple)
    reservations: tuple[str, ...] = field(default_factory=tuple)
    evaluation_time_ms: float = 0.0
    emergency_mode: bool = False


# ── Phase 5.7: Adaptive Learning Engine domain models ──


class TrendDirection(StrEnum):
    IMPROVING = "improving"
    STABLE = "stable"
    DEGRADING = "degrading"
    RAPID_DEGRADATION = "rapid_degradation"
    RECOVERY = "recovery"
    OSCILLATION = "oscillation"
    UNKNOWN = "unknown"


class LearningInputSource(StrEnum):
    ROUTING = "routing"
    BUDGET = "budget"
    CIRCUIT_BREAKER = "circuit_breaker"
    FEEDBACK = "feedback"
    MANUAL = "manual"


@dataclass(frozen=True, slots=True)
class AdaptiveWeights:
    quality: float = 0.25
    latency: float = 0.20
    cost: float = 0.20
    reliability: float = 0.15
    availability: float = 0.10
    recovery: float = 0.05
    budget_efficiency: float = 0.05


@dataclass(frozen=True, slots=True)
class LatencyTrend:
    current: float = 0.0
    ewma: float = 0.0
    min: float = 0.0
    max: float = 0.0
    variance: float = 0.0
    sample_count: int = 0
    direction: TrendDirection = TrendDirection.UNKNOWN
    last_update: datetime = field(default_factory=_utcnow)


@dataclass(frozen=True, slots=True)
class CostTrend:
    current: float = 0.0
    ewma: float = 0.0
    min: float = 0.0
    max: float = 0.0
    variance: float = 0.0
    sample_count: int = 0
    direction: TrendDirection = TrendDirection.UNKNOWN
    last_update: datetime = field(default_factory=_utcnow)


@dataclass(frozen=True, slots=True)
class SuccessTrend:
    current: float = 0.0
    ewma: float = 0.0
    direction: TrendDirection = TrendDirection.UNKNOWN
    last_update: datetime = field(default_factory=_utcnow)


@dataclass(frozen=True, slots=True)
class FailureTrend:
    current: float = 0.0
    ewma: float = 0.0
    direction: TrendDirection = TrendDirection.UNKNOWN
    last_update: datetime = field(default_factory=_utcnow)


@dataclass(frozen=True, slots=True)
class ProviderTrend:
    latency: LatencyTrend = field(default_factory=LatencyTrend)
    cost: CostTrend = field(default_factory=CostTrend)
    success: SuccessTrend = field(default_factory=SuccessTrend)
    failure: FailureTrend = field(default_factory=FailureTrend)
    overall: TrendDirection = TrendDirection.UNKNOWN


@dataclass(frozen=True, slots=True)
class ConfidenceScore:
    score: float = 0.0
    sample_count: int = 0
    variance: float = 0.0
    prediction_error: float = 0.0
    calibration: float = 1.0


@dataclass(frozen=True, slots=True)
class PredictionResult:
    expected_latency_ms: float = 0.0
    expected_cost: float = 0.0
    expected_success_probability: float = 0.0
    expected_failure_probability: float = 0.0
    expected_retry_probability: float = 0.0
    expected_availability: float = 0.0
    confidence: ConfidenceScore = field(default_factory=ConfidenceScore)
    prediction_horizon: str = "short_term"


@dataclass(frozen=True, slots=True)
class AdaptiveScore:
    raw_score: float = 0.0
    normalized_score: float = 0.0
    quality_component: float = 0.0
    latency_component: float = 0.0
    cost_component: float = 0.0
    reliability_component: float = 0.0
    availability_component: float = 0.0
    recovery_component: float = 0.0
    budget_efficiency: float = 0.0
    confidence: ConfidenceScore = field(default_factory=ConfidenceScore)
    trend: TrendDirection = TrendDirection.UNKNOWN
    updated_at: datetime = field(default_factory=_utcnow)


@dataclass(frozen=True, slots=True)
class ReputationScore:
    success_count: int = 0
    failure_count: int = 0
    total_attempts: int = 0
    success_rate: float = 0.0
    failure_rate: float = 0.0
    latency_score: float = 0.0
    cost_score: float = 0.0
    availability: float = 0.0
    stability: float = 0.0
    confidence: float = 0.0
    quality: float = 0.0
    trend: TrendDirection = TrendDirection.UNKNOWN
    sample_size: int = 0
    last_updated: datetime = field(default_factory=_utcnow)


@dataclass(frozen=True, slots=True)
class ProviderReputation:
    provider: str = ""
    reputation: ReputationScore = field(default_factory=ReputationScore)
    adaptive_score: AdaptiveScore = field(default_factory=AdaptiveScore)
    trend: ProviderTrend = field(default_factory=ProviderTrend)
    predictions: PredictionResult = field(default_factory=PredictionResult)


@dataclass(frozen=True, slots=True)
class ModelReputation:
    provider: str = ""
    model: str = ""
    reputation: ReputationScore = field(default_factory=ReputationScore)
    adaptive_score: AdaptiveScore = field(default_factory=AdaptiveScore)
    trend: ProviderTrend = field(default_factory=ProviderTrend)
    predictions: PredictionResult = field(default_factory=PredictionResult)


@dataclass(frozen=True, slots=True)
class LearningRecord:
    id: str = field(default_factory=_new_id)
    provider: str = ""
    model: str = ""
    source: LearningInputSource = LearningInputSource.ROUTING
    success: bool = False
    failure: bool = False
    retry: bool = False
    fallback: bool = False
    latency_ms: float = 0.0
    cost: float = 0.0
    estimated_cost: float = 0.0
    tokens_used: int = 0
    duration_ms: float = 0.0
    reason: str = ""
    task_type: str = ""
    workspace: str = ""
    user_id: str = ""
    agent: str = ""
    policy_used: str = ""
    circuit_state: str = ""
    budget_approved: bool = True
    budget_rejected: bool = False
    timeout: bool = False
    vision_used: bool = False
    tools_used: bool = False
    streaming: bool = False
    cache_hit: bool = False
    timestamp: datetime = field(default_factory=_utcnow)


@dataclass(frozen=True, slots=True)
class LearningSnapshot:
    timestamp: datetime = field(default_factory=_utcnow)
    provider_reputations: tuple[ProviderReputation, ...] = field(default_factory=tuple)
    model_reputations: tuple[ModelReputation, ...] = field(default_factory=tuple)
    statistics: "LearningStatistics" = field(default_factory=lambda: LearningStatistics())
    recent_records: tuple[LearningRecord, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class LearningStatistics:
    total_observations: int = 0
    total_successes: int = 0
    total_failures: int = 0
    total_retries: int = 0
    total_fallbacks: int = 0
    provider_count: int = 0
    model_count: int = 0
    average_latency_ms: float = 0.0
    average_cost: float = 0.0
    average_confidence: float = 0.0
    prediction_accuracy: float = 0.0
    alerts_triggered: int = 0
    anomalies_detected: int = 0
    last_observation: datetime | None = None


@dataclass(frozen=True, slots=True)
class LearningForecast:
    provider_forecast: dict[str, PredictionResult] = field(default_factory=dict)
    model_forecast: dict[str, PredictionResult] = field(default_factory=dict)
    global_latency_trend: LatencyTrend = field(default_factory=LatencyTrend)
    global_cost_trend: CostTrend = field(default_factory=CostTrend)
    global_success_rate: float = 0.0
    confidence: ConfidenceScore = field(default_factory=ConfidenceScore)
    at_risk_providers: tuple[str, ...] = field(default_factory=tuple)
    at_risk_models: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class LearningWindow:
    window_duration: str = ""
    sample_count: int = 0
    success_rate: float = 0.0
    failure_rate: float = 0.0
    average_latency_ms: float = 0.0
    average_cost: float = 0.0
    p50_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    min_latency_ms: float = 0.0
    max_latency_ms: float = 0.0
    direction: TrendDirection = TrendDirection.UNKNOWN


@dataclass(frozen=True, slots=True)
class LearningEvent:
    id: str = field(default_factory=_new_id)
    topic: str = ""
    provider: str = ""
    model: str = ""
    score_before: float = 0.0
    score_after: float = 0.0
    confidence: float = 0.0
    reason: str = ""
    timestamp: datetime = field(default_factory=_utcnow)


@dataclass(frozen=True, slots=True)
class LearningDecision:
    enriched_candidates: tuple[tuple[str, str, AdaptiveScore], ...] = field(default_factory=tuple)
    predictions: dict[str, PredictionResult] = field(default_factory=dict)
    evaluation_time_ms: float = 0.0
    observations_count: int = 0


# ── Phase 5.8: Rate Limiter & Quota Engine domain models ──


class QuotaScope(StrEnum):
    GLOBAL = "global"
    PROVIDER = "provider"
    MODEL = "model"
    WORKSPACE = "workspace"
    ORGANIZATION = "organization"
    USER = "user"
    AGENT = "agent"


class PriorityLevel(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"
    BULK = "bulk"


@dataclass(frozen=True, slots=True)
class TokenBucket:
    capacity: float = 100.0
    refill_rate: float = 10.0
    refill_interval_ms: float = 1000.0
    burst_allowance: float = 20.0


@dataclass(frozen=True, slots=True)
class LeakyBucket:
    drain_rate: float = 10.0
    drain_interval_ms: float = 1000.0
    max_queue_depth: int = 100
    overflow: bool = False


@dataclass(frozen=True, slots=True)
class SlidingWindowCounter:
    window_duration_s: float = 60.0
    max_requests: int = 100
    current_count: int = 0


@dataclass(frozen=True, slots=True)
class RateLimitPolicy:
    id: str = field(default_factory=_new_id)
    name: str = ""
    description: str = ""
    enabled: bool = True
    order: int = 0
    scope: QuotaScope = QuotaScope.GLOBAL
    scope_id: str = ""
    algorithm: str = "token_bucket"  # token_bucket, leaky_bucket, sliding_window, fixed_window
    token_bucket: TokenBucket = field(default_factory=TokenBucket)
    leaky_bucket: LeakyBucket = field(default_factory=LeakyBucket)
    sliding_window: SlidingWindowCounter = field(default_factory=SlidingWindowCounter)
    max_burst: int = 0
    queue_max_size: int = 0
    priority: PriorityLevel = PriorityLevel.NORMAL
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)


@dataclass(frozen=True, slots=True)
class QuotaUsage:
    policy_id: str = ""
    scope: QuotaScope = QuotaScope.GLOBAL
    scope_id: str = ""
    request_count: int = 0
    approved_count: int = 0
    rejected_count: int = 0
    queued_count: int = 0
    delayed_count: int = 0
    burst_count: int = 0
    token_balance: float = 0.0
    queue_depth: int = 0
    last_request: datetime | None = None
    last_updated: datetime = field(default_factory=_utcnow)


@dataclass(frozen=True, slots=True)
class PermitReservation:
    id: str = field(default_factory=_new_id)
    policy_id: str = ""
    scope: QuotaScope = QuotaScope.GLOBAL
    scope_id: str = ""
    provider: str = ""
    model: str = ""
    count: int = 1
    status: str = "reserved"  # reserved, granted, committed, released, rolled_back, expired
    ttl_seconds: float = 30.0
    created_at: datetime = field(default_factory=_utcnow)
    expires_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    committed_at: datetime | None = None
    released_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PermitGrant:
    id: str = field(default_factory=_new_id)
    reservation_id: str = ""
    policy_id: str = ""
    scope: QuotaScope = QuotaScope.GLOBAL
    scope_id: str = ""
    provider: str = ""
    model: str = ""
    count: int = 1
    granted: bool = False
    delay_ms: float = 0.0
    timestamp: datetime = field(default_factory=_utcnow)


@dataclass(frozen=True, slots=True)
class PermitRelease:
    id: str = field(default_factory=_new_id)
    reservation_id: str = ""
    policy_id: str = ""
    count: int = 1
    released: bool = False
    timestamp: datetime = field(default_factory=_utcnow)


@dataclass(frozen=True, slots=True)
class PermitAuditRecord:
    id: str = field(default_factory=_new_id)
    action: str = ""  # reserved, granted, committed, released, rolled_back, expired
    policy_id: str = ""
    scope: QuotaScope = QuotaScope.GLOBAL
    scope_id: str = ""
    provider: str = ""
    model: str = ""
    count: int = 0
    reason: str = ""
    timestamp: datetime = field(default_factory=_utcnow)


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    approved: bool = False
    rejected: bool = False
    queued: bool = False
    delayed: bool = False
    reason: str = ""
    policy_id: str = ""
    algorithm: str = ""
    retry_after_ms: float = 0.0
    estimated_wait_ms: float = 0.0
    queue_position: int = 0
    tokens_remaining: float = 0.0
    evaluation_time_ms: float = 0.0
    reservation_id: str = ""


@dataclass(frozen=True, slots=True)
class ThrottleDecision:
    throttled: bool = False
    reason: str = ""
    provider: str = ""
    model: str = ""
    retry_after_ms: float = 0.0
    throttle_duration_ms: float = 0.0
    scope: QuotaScope = QuotaScope.GLOBAL


@dataclass(frozen=True, slots=True)
class RetryPrediction:
    retry_after_ms: float = 0.0
    queue_delay_ms: float = 0.0
    expected_permit_availability: float = 0.0
    expected_provider_availability: float = 0.0
    confidence: float = 0.0
    estimated_wait_total_ms: float = 0.0


@dataclass(frozen=True, slots=True)
class QueueStatistics:
    total_queued: int = 0
    active_queues: int = 0
    average_wait_ms: float = 0.0
    max_wait_ms: float = 0.0
    queue_depth: int = 0
    overflow_count: int = 0
    priority_distribution: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PermitSnapshot:
    timestamp: datetime = field(default_factory=_utcnow)
    total_reservations: int = 0
    active_reservations: int = 0
    granted_count: int = 0
    released_count: int = 0
    rolled_back_count: int = 0
    expired_count: int = 0
    pending_count: int = 0


@dataclass(frozen=True, slots=True)
class PermitStatistics:
    total_requests: int = 0
    approved: int = 0
    rejected: int = 0
    queued: int = 0
    delayed: int = 0
    burst_count: int = 0
    reservations_active: int = 0
    reservations_granted: int = 0
    reservations_released: int = 0
    reservations_expired: int = 0
    reservations_rolled_back: int = 0
    average_evaluation_time_ms: float = 0.0
    queue_overflow_count: int = 0
    quota_exceeded_count: int = 0


@dataclass(frozen=True, slots=True)
class QuotaForecast:
    policy_id: str = ""
    projected_usage_next_hour: float = 0.0
    projected_usage_today: float = 0.0
    remaining_capacity_today: float = 0.0
    estimated_exhaustion_time: datetime | None = None
    at_risk: bool = False
    recommendation: str = ""


@dataclass(frozen=True, slots=True)
class RateLimitForecast:
    provider_forecasts: dict[str, QuotaForecast] = field(default_factory=dict)
    model_forecasts: dict[str, QuotaForecast] = field(default_factory=dict)
    workspace_forecasts: dict[str, QuotaForecast] = field(default_factory=dict)
    global_forecast: QuotaForecast = field(default_factory=QuotaForecast)
    at_risk_providers: tuple[str, ...] = field(default_factory=tuple)
    at_risk_models: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class RateLimitMetrics:
    requests_per_second: float = 0.0
    permits_per_second: float = 0.0
    queue_depth: int = 0
    average_wait_ms: float = 0.0
    average_retry_delay_ms: float = 0.0
    burst_count: int = 0
    quota_utilization_pct: float = 0.0
    reservation_count: int = 0
    queue_latency_ms: float = 0.0
    permit_throughput: float = 0.0
    forecast_accuracy_pct: float = 0.0
    adaptive_adjustments: int = 0
    provider_utilization_pct: float = 0.0
    workspace_utilization_pct: float = 0.0
    organization_utilization_pct: float = 0.0
    token_utilization_pct: float = 0.0
