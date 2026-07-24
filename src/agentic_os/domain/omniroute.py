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
    BACKGROUND = "background"


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
    total_dispatched: int = 0
    total_expired: int = 0
    total_canceled: int = 0
    total_retries: int = 0
    dispatch_rate: float = 0.0
    backpressure_events: int = 0
    starvation_count: int = 0
    worker_utilization: float = 0.0


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


# ═══════════════════════════════════════════════════════════════
# Phase 5.9 — Intelligent Request Scheduler & Queue Manager
# ═══════════════════════════════════════════════════════════════


class SchedulingReason(StrEnum):
    QUEUED = "queued"
    QUEUE_FULL = "queue_full"
    QUEUE_PAUSED = "queue_paused"
    SCHEDULER_NOT_RUNNING = "scheduler_not_running"
    DEADLINE_MISSED = "deadline_missed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    RETRY = "retry"
    BACKPRESSURE = "backpressure"
    STARVATION = "starvation"
    OVERFLOW = "overflow"
    DISPATCHED = "dispatched"


class QueueOverflowStrategy(StrEnum):
    REJECT = "reject"
    DROP_OLDEST = "drop_oldest"
    DROP_NEWEST = "drop_newest"
    DELAY = "delay"
    SPILLOVER = "spillover"
    PRIORITY_EVICTION = "priority_eviction"
    ADAPTIVE_EVICTION = "adaptive_eviction"


@dataclass(frozen=True, slots=True)
class SchedulingPolicy:
    algorithm: str = "adaptive_hybrid"
    max_queue_depth: int = 500
    worker_pool_size: int = 32
    enable_fairness: bool = True
    enable_starvation_detection: bool = True
    enable_backpressure: bool = True
    enable_deadlines: bool = True
    default_priority: PriorityLevel = PriorityLevel.NORMAL
    overflow_strategy: QueueOverflowStrategy = QueueOverflowStrategy.REJECT
    aging_threshold_ms: float = 30000.0
    fair_share_weight: float = 1.0
    edf_enabled: bool = True


@dataclass(frozen=True, slots=True)
class QueueItem:
    id: str = ""
    provider: str = ""
    model: str = ""
    priority: PriorityLevel = PriorityLevel.NORMAL
    created_at: datetime = field(default_factory=_utcnow)
    deadline: datetime | None = None
    cost: float = 0.0
    estimated_latency_ms: float = 0.0
    queue_affinity: str = ""


@dataclass(frozen=True, slots=True)
class DeadlinePolicy:
    soft_deadline_s: float | None = None
    hard_deadline_s: float | None = None
    expire_on_soft: bool = False
    expire_on_hard: bool = True
    cancel_on_expire: bool = True
    notify_on_miss: bool = True


@dataclass(frozen=True, slots=True)
class RetrySchedule:
    should_retry: bool = False
    retry_count: int = 0
    delay_ms: float = 0.0
    reason: str = ""


@dataclass(frozen=True, slots=True)
class FairnessWindow:
    window_duration_s: float = 60.0
    max_per_window: int = 0
    current_count: int = 0
    window_start: datetime = field(default_factory=_utcnow)


@dataclass(frozen=True, slots=True)
class WorkerLease:
    worker_id: str = ""
    item_id: str = ""
    provider: str = ""
    acquired_at: datetime = field(default_factory=_utcnow)
    expires_at: datetime | None = None
    released: bool = False


@dataclass(frozen=True, slots=True)
class BackPressureState:
    active: bool = False
    high_water_mark: int = 100
    low_water_mark: int = 30
    current_depth: int = 0
    triggered_at: datetime | None = None
    events: int = 0


@dataclass(frozen=True, slots=True)
class DispatchReservation:
    item_id: str = ""
    provider: str = ""
    model: str = ""
    reserved_at: float = 0.0
    expires_at: float = 0.0


@dataclass(frozen=True, slots=True)
class DispatchPlan:
    item: QueueItem = field(default_factory=QueueItem)
    priority: PriorityLevel = PriorityLevel.NORMAL
    wait_time_ms: float = 0.0
    retry: RetrySchedule = field(default_factory=RetrySchedule)
    deadline_ms: float | None = None
    reservation: DispatchReservation | None = None
    algorithm: str = ""


@dataclass(frozen=True, slots=True)
class SchedulingDecision:
    queued: bool = False
    item_id: str = ""
    position: int = 0
    reason: SchedulingReason = SchedulingReason.QUEUED
    retry_after_ms: float = 0.0


@dataclass(frozen=True, slots=True)
class SchedulingEvent:
    event_type: str = ""
    item_id: str = ""
    provider: str = ""
    priority: PriorityLevel = PriorityLevel.NORMAL
    wait_ms: float = 0.0
    timestamp: datetime = field(default_factory=_utcnow)


@dataclass(frozen=True, slots=True)
class QueueState:
    name: str = ""
    depth: int = 0
    priority: PriorityLevel = PriorityLevel.NORMAL
    overflow: bool = False


@dataclass(frozen=True, slots=True)
class QueueSnapshot:
    timestamp: datetime = field(default_factory=_utcnow)
    total_queued: int = 0
    depth_by_priority: dict[str, int] = field(default_factory=dict)
    edf_depth: int = 0
    fair_depth: int = 0
    backpressure_active: bool = False
    worker_utilization: float = 0.0
    average_wait_ms: float = 0.0
    max_wait_ms: float = 0.0
    overflow_count: int = 0
    stale_count: int = 0


@dataclass(frozen=True, slots=True)
class QueueMetrics:
    queue_length: int = 0
    average_wait_time: float = 0.0
    dispatch_rate: float = 0.0
    expired_requests: int = 0
    retry_rate: float = 0.0
    queue_utilization: float = 0.0
    starvation_count: int = 0
    deadline_misses: int = 0
    backpressure_events: int = 0
    worker_utilization: float = 0.0
    dispatch_latency: float = 0.0
    fairness_index: float = 1.0
    scheduler_health: str = "healthy"


@dataclass(frozen=True, slots=True)
class SchedulerHealth:
    status: str = "stopped"
    uptime_s: float = 0.0
    total_queued: int = 0
    total_dispatched: int = 0
    total_expired: int = 0
    total_canceled: int = 0
    total_retries: int = 0
    backpressure_active: bool = False
    queue_full_pct: float = 0.0
    worker_utilization: float = 0.0
    error_count: int = 0
    last_error: str = ""


@dataclass(frozen=True, slots=True)
class SchedulerForecast:
    current_depth: int = 0
    predicted_dispatch_rate: float = 0.0
    estimated_wait_s: float = 0.0
    workload_prediction: str = "stable"
    recommendation: str = ""


# ═══════════════════════════════════════════════════════════════════════════════
# Execution Engine (Phase 5.10)
# ═══════════════════════════════════════════════════════════════════════════════


class ExecutionStrategy(StrEnum):
    SINGLE = "single"
    STREAMING = "streaming"
    PARALLEL = "parallel"
    HEDGED = "hedged"
    SPECULATIVE = "speculative"
    SHADOW = "shadow"
    CANARY = "canary"
    MIRROR = "mirror"
    FALLBACK = "fallback"
    QUORUM = "quorum"
    RACE = "race"
    BATCH = "batch"
    PIPELINE = "pipeline"


class ExecutionState(StrEnum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    STREAMING = "streaming"
    RETRYING = "retrying"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    FAILED = "failed"
    ABORTED = "aborted"
    PARTIAL_SUCCESS = "partial_success"


class AggregationStrategy(StrEnum):
    FIRST_SUCCESS = "first_success"
    FIRST_COMPLETED = "first_completed"
    FASTEST = "fastest"
    LOWEST_COST = "lowest_cost"
    BEST_QUALITY = "best_quality"
    BEST_CONFIDENCE = "best_confidence"
    WEIGHTED_SCORE = "weighted_score"
    WEIGHTED_VOTE = "weighted_vote"
    MAJORITY_VOTE = "majority_vote"
    SUPER_MAJORITY = "super_majority"
    UNANIMOUS = "unanimous"
    CONSENSUS = "consensus"
    QUORUM = "quorum"
    AVERAGE = "average"
    MEDIAN = "median"
    MERGE = "merge"
    ENSEMBLE = "ensemble"
    STACKING = "stacking"
    PIPELINE = "pipeline"
    CUSTOM = "custom"
    AUTO = "auto"
    # Legacy alias (Phase 5.10 executor compatibility)
    QUALITY_WEIGHTED = "quality_weighted"


class RetryPolicyType(StrEnum):
    IMMEDIATE_RETRY = "immediate_retry"
    FIXED_DELAY = "fixed_delay"
    EXPONENTIAL_BACKOFF = "exponential_backoff"
    LINEAR_BACKOFF = "linear_backoff"
    JITTERED_BACKOFF = "jittered_backoff"
    DECORRELATED_JITTER = "decorrelated_jitter"
    NO_RETRY = "no_retry"
    # Legacy aliases (Phase 5.10 executor compatibility)
    IMMEDIATE = "immediate_retry"
    LINEAR = "linear_backoff"
    JITTER = "jittered_backoff"
    ADAPTIVE = "adaptive"
    BUDGET_AWARE = "budget_aware"
    PROVIDER_AWARE = "provider_aware"
    CIRCUIT_BREAKER_AWARE = "circuit_breaker_aware"
    DEADLINE_AWARE = "deadline_aware"


@dataclass(frozen=True, slots=True)
class ExecutionRequest:
    request_id: str = ""
    session_id: str = ""
    provider: str = ""
    model: str = ""
    messages: tuple[dict[str, str], ...] = field(default_factory=tuple)
    max_tokens: int = 4096
    temperature: float = 0.7
    strategy: ExecutionStrategy = ExecutionStrategy.SINGLE
    aggregation: AggregationStrategy = AggregationStrategy.FIRST_SUCCESS
    retry_policy: RetryPolicyType = RetryPolicyType.EXPONENTIAL_BACKOFF
    max_retries: int = 3
    soft_timeout_s: float = 30.0
    hard_timeout_s: float = 60.0
    idle_timeout_s: float = 10.0
    streaming_timeout_s: float = 120.0
    parallel_providers: tuple[str, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    request_id: str = ""
    provider: str = ""
    model: str = ""
    state: ExecutionState = ExecutionState.PENDING
    output: str = ""
    content: str = ""
    finish_reason: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    total_tokens: int = 0
    latency_ms: float = 0.0
    ttfb_ms: float = 0.0
    attempts: int = 1
    retries: int = 0
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    cost: float = 0.0


@dataclass(frozen=True, slots=True)
class ExecutionAttempt:
    attempt: int = 1
    provider: str = ""
    model: str = ""
    latency_ms: float = 0.0
    state: ExecutionState = ExecutionState.PENDING
    error: str = ""
    timestamp: float = 0.0


@dataclass(frozen=True, slots=True)
class ExecutionHealth:
    status: str = "healthy"
    uptime_s: float = 0.0
    active_executions: int = 0
    total_executions: int = 0
    success_rate: float = 0.0
    failure_rate: float = 0.0
    avg_latency_ms: float = 0.0
    error_count: int = 0
    last_error: str = ""
    provider_health: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ExecutionMetrics:
    total_executions: int = 0
    successful_executions: int = 0
    failed_executions: int = 0
    cancelled_executions: int = 0
    timed_out_executions: int = 0
    retry_count: int = 0
    total_latency_ms: float = 0.0
    avg_latency_ms: float = 0.0
    p50_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    total_tokens: int = 0
    total_tokens_in: int = 0
    total_tokens_out: int = 0
    throughput_tokens_per_s: float = 0.0
    streaming_count: int = 0
    parallel_count: int = 0
    hedged_count: int = 0
    speculative_count: int = 0
    quorum_count: int = 0
    fallback_count: int = 0
    shadow_count: int = 0
    provider_error_count: int = 0
    timeout_count: int = 0
    ttfb_ms: float = 0.0
    provider_utilization: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ExecutionStatistics:
    total_executions: int = 0
    active_executions: int = 0
    completed_executions: int = 0
    failed_executions: int = 0
    cancelled_executions: int = 0
    timed_out_executions: int = 0
    streaming_executions: int = 0
    parallel_executions: int = 0
    hedged_executions: int = 0
    average_latency_ms: float = 0.0
    average_ttfb_ms: float = 0.0
    average_retries: float = 0.0
    average_tokens_per_request: float = 0.0
    throughput_per_minute: float = 0.0
    error_rate: float = 0.0


@dataclass(frozen=True, slots=True)
class ExecutionTrace:
    request_id: str = ""
    provider: str = ""
    model: str = ""
    started_at: float = 0.0
    completed_at: float = 0.0
    duration_ms: float = 0.0
    steps: tuple[str, ...] = field(default_factory=tuple)
    errors: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class ExecutionTimeline:
    request_id: str = ""
    events: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    total_duration_ms: float = 0.0


@dataclass(frozen=True, slots=True)
class ExecutionReservation:
    request_id: str = ""
    provider: str = ""
    reserved_at: float = 0.0
    expires_at: float = 0.0
    ttl_ms: float = 5000.0


@dataclass(frozen=True, slots=True)
class ExecutionStream:
    request_id: str = ""
    provider: str = ""
    model: str = ""
    chunks: tuple[str, ...] = field(default_factory=tuple)
    total_chunks: int = 0
    total_duration_ms: float = 0.0
    complete: bool = False


@dataclass(frozen=True, slots=True)
class ExecutionChunk:
    request_id: str = ""
    provider: str = ""
    model: str = ""
    index: int = 0
    content: str = ""
    finish_reason: str = "continue"
    timestamp: float = 0.0


@dataclass(frozen=True, slots=True)
class ExecutionRetry:
    request_id: str = ""
    attempt: int = 1
    policy: RetryPolicyType = RetryPolicyType.EXPONENTIAL_BACKOFF
    delay_ms: float = 0.0
    reason: str = ""


@dataclass(frozen=True, slots=True)
class ExecutionFailure:
    request_id: str = ""
    provider: str = ""
    error: str = ""
    attempt: int = 1
    is_final: bool = False


@dataclass(frozen=True, slots=True)
class ExecutionTimeout:
    request_id: str = ""
    provider: str = ""
    timeout_type: str = "hard"
    duration_s: float = 0.0


@dataclass(frozen=True, slots=True)
class ExecutionSession:
    session_id: str = ""
    request_ids: tuple[str, ...] = field(default_factory=tuple)
    started_at: float = 0.0
    completed_at: float = 0.0
    total_cost: float = 0.0
    total_latency_ms: float = 0.0
    provider_count: int = 0


@dataclass(frozen=True, slots=True)
class ExecutionDecision:
    request_id: str = ""
    provider: str = ""
    model: str = ""
    strategy: ExecutionStrategy = ExecutionStrategy.SINGLE
    confidence: float = 1.0
    reason: str = ""


@dataclass(frozen=True, slots=True)
class ExecutionSummary:
    request_id: str = ""
    state: ExecutionState = ExecutionState.PENDING
    provider: str = ""
    model: str = ""
    strategy: str = ""
    duration_ms: float = 0.0


@dataclass(frozen=True, slots=True)
class ExecutionSnapshot:
    timestamp: float = 0.0
    active_count: int = 0
    queued_count: int = 0
    completed_count: int = 0
    failed_count: int = 0
    avg_latency_ms: float = 0.0
    status: str = "healthy"


@dataclass(frozen=True, slots=True)
class ExecutionPolicy:
    strategy: ExecutionStrategy = ExecutionStrategy.SINGLE
    aggregation: AggregationStrategy = AggregationStrategy.FIRST_SUCCESS
    retry_policy: RetryPolicyType = RetryPolicyType.EXPONENTIAL_BACKOFF
    max_retries: int = 3
    soft_timeout_s: float = 30.0
    hard_timeout_s: float = 60.0
    hedged_delay_s: float = 1.0
    quorum_size: int = 3


@dataclass(frozen=True, slots=True)
class ExecutionPrediction:
    request_id: str = ""
    predicted_provider: str = ""
    predicted_latency_ms: float = 0.0
    predicted_tokens: int = 0
    confidence: float = 0.5


@dataclass(frozen=True, slots=True)
class ExecutionTelemetry:
    request_id: str = ""
    provider: str = ""
    model: str = ""
    latency_ms: float = 0.0
    ttfb_ms: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    retry_count: int = 0
    timeout: bool = False
    error: str = ""
    strategy: str = ""
    timestamp: float = 0.0


@dataclass(frozen=True, slots=True)
class ExecutionProgress:
    request_id: str = ""
    provider: str = ""
    progress_pct: float = 0.0
    tokens_so_far: int = 0
    estimated_remaining_s: float = 0.0
    current_attempt: int = 1
    state: ExecutionState = ExecutionState.RUNNING


@dataclass(frozen=True, slots=True)
class ExecutionContext:
    request_id: str = ""
    session_id: str = ""
    provider: str = ""
    model: str = ""
    strategy: ExecutionStrategy = ExecutionStrategy.SINGLE
    state: ExecutionState = ExecutionState.PENDING
    attempts: tuple[ExecutionAttempt, ...] = field(default_factory=tuple)
    created_at: float = 0.0
    updated_at: float = 0.0
    cancellation_token: bool = False


# ═══════════════════════════════════════════════════════════════════════════════
# Aggregation Engine (Phase 5.11)
# ═══════════════════════════════════════════════════════════════════════════════


class ConsensusMode(StrEnum):
    SIMPLE_MAJORITY = "simple_majority"
    ABSOLUTE_MAJORITY = "absolute_majority"
    SUPER_MAJORITY = "super_majority"
    UNANIMOUS = "unanimous"
    WEIGHTED_VOTING = "weighted_voting"
    CONFIDENCE_WEIGHTED = "confidence_weighted"
    QUALITY_WEIGHTED = "quality_weighted"
    BAYESIAN = "bayesian"
    QUORUM = "quorum"
    CONSENSUS_THRESHOLD = "consensus_threshold"


class ConflictResolutionPolicy(StrEnum):
    TRUST_HIGHEST_CONFIDENCE = "trust_highest_confidence"
    TRUST_MAJORITY = "trust_majority"
    TRUST_FASTEST = "trust_fastest"
    TRUST_LOWEST_COST = "trust_lowest_cost"
    TRUST_LATEST = "trust_latest"
    MARK_CONFLICT = "mark_conflict"
    REQUEST_CLARIFICATION = "request_clarification"


class DeduplicationMethod(StrEnum):
    EXACT_HASH = "exact_hash"
    TOKEN_OVERLAP = "token_overlap"
    SEMANTIC_SIMILARITY = "semantic_similarity"
    NORMALIZED_TEXT = "normalized_text"


@dataclass(frozen=True, slots=True)
class WeightedVote:
    provider: str = ""
    value: str = ""
    weight: float = 1.0
    confidence: float = 0.5
    quality: float = 0.5
    latency_ms: float = 0.0
    cost: float = 0.0


@dataclass(frozen=True, slots=True)
class VoteRecord:
    provider: str = ""
    content_hash: str = ""
    content: str = ""
    weight: float = 1.0
    confidence: float = 0.5
    quality: float = 0.5
    timestamp: float = 0.0


@dataclass(frozen=True, slots=True)
class ProviderVote:
    provider: str = ""
    vote: str = ""
    weight: float = 1.0
    evidence: str = ""


@dataclass(frozen=True, slots=True)
class MajorityResult:
    winner: str = ""
    votes_for: int = 0
    votes_against: int = 0
    total_votes: int = 0
    majority_pct: float = 0.0
    threshold_met: bool = False


@dataclass(frozen=True, slots=True)
class ConsensusResult:
    reached: bool = False
    value: str = ""
    confidence: float = 0.0
    mode: ConsensusMode = ConsensusMode.SIMPLE_MAJORITY
    votes: tuple[WeightedVote, ...] = field(default_factory=tuple)
    tie: bool = False
    majority: MajorityResult | None = None


@dataclass(frozen=True, slots=True)
class AgreementMatrix:
    providers: tuple[str, ...] = field(default_factory=tuple)
    matrix: tuple[tuple[float, ...], ...] = field(default_factory=tuple)
    average_agreement: float = 0.0


@dataclass(frozen=True, slots=True)
class SimilarityMatrix:
    providers: tuple[str, ...] = field(default_factory=tuple)
    matrix: tuple[tuple[float, ...], ...] = field(default_factory=tuple)
    min_similarity: float = 0.0
    max_similarity: float = 0.0
    avg_similarity: float = 0.0


@dataclass(frozen=True, slots=True)
class SemanticCluster:
    label: str = ""
    members: tuple[str, ...] = field(default_factory=tuple)
    provider_responses: tuple[str, ...] = field(default_factory=tuple)
    average_score: float = 0.0
    size: int = 0


@dataclass(frozen=True, slots=True)
class ProviderContribution:
    provider: str = ""
    model: str = ""
    latency_ms: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    cost: float = 0.0
    quality_score: float = 0.0
    confidence: float = 0.0
    is_selected: bool = False


@dataclass(frozen=True, slots=True)
class NormalizedResponse:
    provider: str = ""
    model: str = ""
    content: str = ""
    citations: tuple[str, ...] = field(default_factory=tuple)
    tokens_in: int = 0
    tokens_out: int = 0
    finish_reason: str = ""
    latency_ms: float = 0.0
    cost: float = 0.0
    confidence: float = 0.5
    quality: float = 0.5
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AggregationCandidate:
    provider: str = ""
    content: str = ""
    normalized_content: str = ""
    quality_score: float = 0.5
    confidence_score: float = 0.5
    latency_score: float = 0.5
    cost_score: float = 0.5
    reliability_score: float = 0.5
    learning_score: float = 0.5
    final_score: float = 0.5
    is_valid: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MergedContent:
    content: str = ""
    sources: tuple[str, ...] = field(default_factory=tuple)
    fragments: tuple[str, ...] = field(default_factory=tuple)
    total_source_count: int = 0
    merge_type: str = "text"


@dataclass(frozen=True, slots=True)
class AggregatedResponse:
    content: str = ""
    provider_count: int = 0
    citations: tuple[str, ...] = field(default_factory=tuple)
    strategy: AggregationStrategy = AggregationStrategy.AUTO
    is_consensus: bool = False
    selected_provider: str = ""
    quality: float = 0.0
    confidence: float = 0.0


@dataclass(frozen=True, slots=True)
class ConflictRecord:
    conflict_field: str = ""
    values: tuple[str, ...] = field(default_factory=tuple)
    providers: tuple[str, ...] = field(default_factory=tuple)
    confidences: tuple[float, ...] = field(default_factory=tuple)
    resolved: bool = False
    resolution: str = ""
    resolution_policy: str = ""


@dataclass(frozen=True, slots=True)
class ConflictResolution:
    conflicts: tuple[ConflictRecord, ...] = field(default_factory=tuple)
    total_conflicts: int = 0
    resolved_count: int = 0
    policy: ConflictResolutionPolicy = ConflictResolutionPolicy.TRUST_MAJORITY


@dataclass(frozen=True, slots=True)
class AggregationConfidence:
    """Aggregation-level confidence score with per-section, provider, and consensus estimates."""

    overall: float = 0.5
    per_section: dict[str, float] = field(default_factory=dict)
    provider_confidence: dict[str, float] = field(default_factory=dict)
    citation_confidence: float = 0.5
    consensus_confidence: float = 0.5
    uncertainty: float = 0.0
    risk_score: float = 0.0


@dataclass(frozen=True, slots=True)
class AggregationRequest:
    request_id: str = ""
    session_id: str = ""
    strategy: AggregationStrategy = AggregationStrategy.AUTO
    results: tuple[ExecutionResult, ...] = field(default_factory=tuple)
    providers: tuple[str, ...] = field(default_factory=tuple)
    models: tuple[str, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AggregationResult:
    request_id: str = ""
    content: str = ""
    strategy: AggregationStrategy = AggregationStrategy.AUTO
    confidence: AggregationConfidence = field(default_factory=AggregationConfidence)
    consensus: ConsensusResult | None = None
    conflicts: ConflictResolution | None = None
    selected_provider: str = ""
    candidates: tuple[AggregationCandidate, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AggregationDecision:
    strategy: AggregationStrategy = AggregationStrategy.AUTO
    reason: str = ""
    confidence: float = 0.0


@dataclass(frozen=True, slots=True)
class AggregationRule:
    name: str = ""
    condition: str = ""
    action: str = ""
    priority: int = 0
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class AggregationOverride:
    request_id: str = ""
    strategy: AggregationStrategy | None = None
    consensus_mode: ConsensusMode | None = None
    threshold: float | None = None
    reason: str = ""


@dataclass(frozen=True, slots=True)
class AggregationAuditRecord:
    request_id: str = ""
    strategy: AggregationStrategy = AggregationStrategy.AUTO
    provider_count: int = 0
    conflict_count: int = 0
    selected_provider: str = ""
    consensus_reached: bool = False
    duration_ms: float = 0.0
    timestamp: float = 0.0
    error: str = ""


@dataclass(frozen=True, slots=True)
class AggregationExplanation:
    request_id: str = ""
    strategy: AggregationStrategy = AggregationStrategy.AUTO
    reasoning: str = ""
    provider_scores: dict[str, float] = field(default_factory=dict)
    confidence_breakdown: str = ""


@dataclass(frozen=True, slots=True)
class AggregationTrace:
    request_id: str = ""
    steps: tuple[str, ...] = field(default_factory=tuple)
    decisions: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    duration_ms: float = 0.0


@dataclass(frozen=True, slots=True)
class AggregationPrediction:
    request_id: str = ""
    predicted_strategy: AggregationStrategy = AggregationStrategy.AUTO
    predicted_consensus: bool = False
    predicted_quality: float = 0.5
    confidence: float = 0.3


@dataclass(frozen=True, slots=True)
class AggregationWindow:
    request_ids: tuple[str, ...] = field(default_factory=tuple)
    start_time: float = 0.0
    end_time: float = 0.0
    aggregation_count: int = 0


@dataclass(frozen=True, slots=True)
class AggregationHistory:
    records: tuple[AggregationAuditRecord, ...] = field(default_factory=tuple)
    total: int = 0
    span_duration_ms: float = 0.0


@dataclass(frozen=True, slots=True)
class AggregationMetrics:
    aggregation_count: int = 0
    consensus_count: int = 0
    merge_count: int = 0
    average_similarity: float = 0.0
    average_confidence: float = 0.0
    average_quality: float = 0.0
    majority_rate: float = 0.0
    conflict_rate: float = 0.0
    consensus_latency_ms: float = 0.0
    selected_provider_distribution: dict[str, int] = field(default_factory=dict)
    strategy_usage: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AggregationStatistics:
    total_aggregations: int = 0
    avg_latency_ms: float = 0.0
    strategy_breakdown: dict[str, int] = field(default_factory=dict)
    consensus_count: int = 0
    consensus_rate: float = 0.0
    conflict_count: int = 0
    conflict_rate: float = 0.0
    dedup_count: int = 0
    avg_quality: float = 0.0
    avg_confidence: float = 0.0


@dataclass(frozen=True, slots=True)
class AggregationSnapshot:
    status: str = "healthy"
    total_aggregations: int = 0
    active_count: int = 0
    avg_latency_ms: float = 0.0
    strategy: str = ""


@dataclass(frozen=True, slots=True)
class AggregationHealth:
    status: str = "healthy"
    uptime_s: float = 0.0
    total_aggregations: int = 0
    avg_latency_ms: float = 0.0
    active_count: int = 0
    conflict_rate: float = 0.0
    consensus_rate: float = 0.0


@dataclass(frozen=True, slots=True)
class AggregationPolicy:
    default_strategy: AggregationStrategy = AggregationStrategy.AUTO
    consensus_mode: ConsensusMode = ConsensusMode.SIMPLE_MAJORITY
    dedup_method: DeduplicationMethod = DeduplicationMethod.EXACT_HASH
    conflict_policy: ConflictResolutionPolicy = ConflictResolutionPolicy.TRUST_MAJORITY
    min_quality: float = 0.3
    min_confidence: float = 0.3
