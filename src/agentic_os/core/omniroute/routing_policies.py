"""OmniRoute Routing Policy Engine — the decision layer that controls RouterEngine.

Replaces hardcoded routing logic with configurable policies. Each policy
implements a :class:`PolicyStrategy` that evaluates candidates and returns
ranked results. The :class:`RoutingPolicyEngineImpl` manages the lifecycle
of policies (CRUD, scoping) and provides evaluation + resolution.

Every future subsystem (BudgetEngine, CircuitBreaker, Learning Engine,
AI Brain, Swarm Orchestrator) consumes decisions through this engine.
"""

from __future__ import annotations

import asyncio
import math
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from agentic_os.domain.events import EventEnvelope, Topic
from agentic_os.domain.omniroute import (
    OmniRouteModel,
    OmniRouteProvider,
    PolicyResult,
    RoutingPolicy,
    RoutingRequest,
)
from agentic_os.infrastructure.logging import get_logger

log = get_logger("omniroute.routing_policies")


# ── Port Protocol ──


@runtime_checkable
class RoutingPolicyPort(Protocol):
    """Port for the Routing Policy Engine."""

    async def create_policy(self, policy: RoutingPolicy) -> str:
        """Register a new routing policy. Returns its id."""
        ...

    async def update_policy(self, policy: RoutingPolicy) -> str:
        """Update an existing policy. Returns its id."""
        ...

    async def delete_policy(self, policy_id: str) -> bool:
        """Delete a policy by id. Returns True if found."""
        ...

    async def enable_policy(self, policy_id: str) -> bool:
        """Enable a policy. Returns True if found and changed."""
        ...

    async def disable_policy(self, policy_id: str) -> bool:
        """Disable a policy. Returns True if found and changed."""
        ...

    async def get_policy(self, policy_id: str) -> RoutingPolicy | None:
        """Get a policy by id."""
        ...

    async def list_policies(self, *, enabled_only: bool = False) -> list[RoutingPolicy]:
        """List all registered policies."""
        ...

    async def default_policy(self) -> RoutingPolicy | None:
        """Return the default policy (if any)."""
        ...

    async def set_default(self, policy_id: str) -> bool:
        """Set a policy as the default. Returns True if found."""
        ...

    async def evaluate(
        self,
        candidates: list[Any],
        request: RoutingRequest,
        policy: RoutingPolicy | None = None,
    ) -> PolicyResult:
        """Evaluate candidates against a policy.

        If *policy* is None, the engine :meth:`resolve_policy` for the request.
        Returns a :class:`PolicyResult` with the ranked candidates.
        """
        ...

    async def resolve_policy(self, request: RoutingRequest) -> RoutingPolicy:
        """Resolve which policy applies to a request (scoping + priority)."""
        ...

    async def applicable_policies(self, request: RoutingRequest) -> list[RoutingPolicy]:
        """Return policies that match the request's workspace/agent/user scope."""
        ...

    async def rank_policies(self, request: RoutingRequest) -> list[RoutingPolicy]:
        """Return applicable policies sorted by priority descending."""
        ...

    # ── Lifecycle ──

    async def initialize(self) -> None: ...
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def dispose(self) -> None: ...
    async def health(self) -> dict[str, Any]: ...
    async def ready(self) -> bool: ...
    async def metadata(self) -> dict[str, Any]: ...
    async def dependencies(self) -> list[str]: ...
    async def capabilities(self) -> list[dict[str, Any]]: ...


# ── Internal candidate wrapper ──


@dataclass
class _ScoredCandidate:
    """Scored provider+model pair during policy evaluation."""

    provider: OmniRouteProvider
    model: OmniRouteModel
    score: float = 0.0
    rank: int = 0
    reason: str = ""


# ── Policy Strategy Interface ──


class PolicyStrategy(ABC):
    """Base class for a routing policy strategy."""

    name: str = "base"

    @abstractmethod
    async def evaluate(
        self,
        candidates: list[_ScoredCandidate],
        request: RoutingRequest,
        policy: RoutingPolicy,
    ) -> list[_ScoredCandidate]:
        """Score and sort candidates according to the strategy.

        Returns the same list, mutated in-place with scores and reasons.
        """
        ...


# ── Scoring Helpers ──


def _compute_cost_score(provider: OmniRouteProvider, model: OmniRouteModel) -> float:
    """Cost score — cheaper = better. Inverted log-normalised."""
    total = provider.cost_per_1k_input + provider.cost_per_1k_output
    total += model.input_cost_per_1k + model.output_cost_per_1k
    if total <= 0:
        return 1.0
    max_cost = 10.0
    raw = math.log1p(total) / math.log1p(max_cost)
    return round(max(0.0, 1.0 - raw), 4)


def _compute_latency_score(
    provider: OmniRouteProvider, model: OmniRouteModel, max_latency: float = 0.0
) -> float:
    """Latency score — lower = better."""
    combined = max(provider.latency_ms, model.latency_ms)
    if combined <= 0:
        return 1.0
    bound = max_latency if max_latency > 0 else 5000.0
    raw = combined / bound
    return round(max(0.0, min(1.0, 1.0 - raw)), 4)


def _compute_health_score(provider: OmniRouteProvider, model: OmniRouteModel) -> float:
    if provider.healthy and model.healthy:
        return 1.0
    if provider.healthy or model.healthy:
        return 0.5
    return 0.0


def _compute_reliability_score(provider: OmniRouteProvider) -> float:
    if not provider.enabled:
        return 0.0
    return 1.0 if provider.healthy else 0.3


def _compute_context_score(model: OmniRouteModel) -> float:
    if model.context_window <= 0:
        return 0.0
    raw = math.log1p(model.context_window) / math.log1p(1_000_000)
    return round(min(1.0, raw), 4)


# ── Strategy Implementations ──


class BalancedStrategy(PolicyStrategy):
    """Equal weights across quality, cost, latency, health."""

    name = "balanced"

    async def evaluate(
        self, candidates: list[_ScoredCandidate], request: RoutingRequest, policy: RoutingPolicy
    ) -> list[_ScoredCandidate]:
        weights = _resolve_weights(policy, q=1.0, c=1.0, latency=1.0, h=1.0, r=0.5, ctx=0.3, p=0.5)
        for c in candidates:
            c.score = _weighted_total(c.provider, c.model, request, weights)
            c.reason = "balanced"
        candidates.sort(key=lambda x: x.score, reverse=True)
        return candidates


class LowestCostStrategy(PolicyStrategy):
    """Heavily favours cheap providers/models."""

    name = "lowest_cost"

    async def evaluate(
        self, candidates: list[_ScoredCandidate], request: RoutingRequest, policy: RoutingPolicy
    ) -> list[_ScoredCandidate]:
        for c in candidates:
            cost = _compute_cost_score(c.provider, c.model)
            health = _compute_health_score(c.provider, c.model)
            c.score = cost * 5 + health * 0.5
            c.reason = f"cost_score={cost:.3f}"
        candidates.sort(key=lambda x: x.score, reverse=True)
        return candidates


class HighestQualityStrategy(PolicyStrategy):
    """Favours models with highest quality_score."""

    name = "highest_quality"

    async def evaluate(
        self, candidates: list[_ScoredCandidate], request: RoutingRequest, policy: RoutingPolicy
    ) -> list[_ScoredCandidate]:
        for c in candidates:
            q = min(max(c.model.quality_score, 0.0), 1.0)
            h = _compute_health_score(c.provider, c.model)
            c.score = q * 5 + h * 0.5
            c.reason = f"quality_score={q:.3f}"
        candidates.sort(key=lambda x: x.score, reverse=True)
        return candidates


class LowestLatencyStrategy(PolicyStrategy):
    """Favours lowest-latency providers/models."""

    name = "lowest_latency"

    async def evaluate(
        self, candidates: list[_ScoredCandidate], request: RoutingRequest, policy: RoutingPolicy
    ) -> list[_ScoredCandidate]:
        for c in candidates:
            lat = _compute_latency_score(c.provider, c.model, request.max_latency_ms)
            h = _compute_health_score(c.provider, c.model)
            c.score = lat * 5 + h * 0.5
            c.reason = f"latency_score={lat:.3f}"
        candidates.sort(key=lambda x: x.score, reverse=True)
        return candidates


class HighestReliabilityStrategy(PolicyStrategy):
    """Favours most reliable providers."""

    name = "highest_reliability"

    async def evaluate(
        self, candidates: list[_ScoredCandidate], request: RoutingRequest, policy: RoutingPolicy
    ) -> list[_ScoredCandidate]:
        for c in candidates:
            rel = _compute_reliability_score(c.provider)
            q = min(max(c.model.quality_score, 0.0), 1.0)
            c.score = rel * 5 + q * 1
            c.reason = f"reliability_score={rel:.3f}"
        candidates.sort(key=lambda x: x.score, reverse=True)
        return candidates


class LocalFirstStrategy(PolicyStrategy):
    """Prefer local/Ollama/LM-Studio providers; fall back to cloud."""

    name = "local_first"

    async def evaluate(
        self, candidates: list[_ScoredCandidate], request: RoutingRequest, policy: RoutingPolicy
    ) -> list[_ScoredCandidate]:
        for c in candidates:
            kind = c.provider.kind.lower() if c.provider.kind else ""
            name = c.provider.name.lower() if c.provider.name else ""
            is_local = any(
                t in kind or t in name for t in ("local", "ollama", "lm-studio", "lmstudio")
            )
            bonus = 5.0 if is_local else 0.0
            q = min(max(c.model.quality_score, 0.0), 1.0)
            c.score = q + bonus
            c.reason = f"local={is_local}, quality={q:.3f}"
        candidates.sort(key=lambda x: x.score, reverse=True)
        return candidates


class CloudFirstStrategy(PolicyStrategy):
    """Prefer cloud providers (non-local)."""

    name = "cloud_first"

    async def evaluate(
        self, candidates: list[_ScoredCandidate], request: RoutingRequest, policy: RoutingPolicy
    ) -> list[_ScoredCandidate]:
        for c in candidates:
            kind = c.provider.kind.lower() if c.provider.kind else ""
            name = c.provider.name.lower() if c.provider.name else ""
            is_local = any(
                t in kind or t in name for t in ("local", "ollama", "lm-studio", "lmstudio")
            )
            bonus = 3.0 if not is_local else 0.0
            q = min(max(c.model.quality_score, 0.0), 1.0)
            c.score = q + bonus
            c.reason = f"cloud={not is_local}, quality={q:.3f}"
        candidates.sort(key=lambda x: x.score, reverse=True)
        return candidates


class ReasoningOptimizedStrategy(PolicyStrategy):
    """Requires reasoning capability, prefers high quality."""

    name = "reasoning_optimized"

    async def evaluate(
        self, candidates: list[_ScoredCandidate], request: RoutingRequest, policy: RoutingPolicy
    ) -> list[_ScoredCandidate]:
        for c in candidates:
            q = min(max(c.model.quality_score, 0.0), 1.0)
            reasoning_bonus = 3.0 if c.model.supports_reasoning else 0.0
            c.score = q * 2 + reasoning_bonus
            c.reason = f"reasoning={bool(c.model.supports_reasoning)}, quality={q:.3f}"
        candidates.sort(key=lambda x: x.score, reverse=True)
        return candidates


class VisionOptimizedStrategy(PolicyStrategy):
    """Requires vision capability, prefers high quality + vision models."""

    name = "vision_optimized"

    async def evaluate(
        self, candidates: list[_ScoredCandidate], request: RoutingRequest, policy: RoutingPolicy
    ) -> list[_ScoredCandidate]:
        for c in candidates:
            q = min(max(c.model.quality_score, 0.0), 1.0)
            vision_bonus = 3.0 if c.model.supports_vision else 0.0
            c.score = q * 2 + vision_bonus
            c.reason = f"vision={bool(c.model.supports_vision)}, quality={q:.3f}"
        candidates.sort(key=lambda x: x.score, reverse=True)
        return candidates


class StreamingOptimizedStrategy(PolicyStrategy):
    """Requires streaming support, prefers low latency."""

    name = "streaming_optimized"

    async def evaluate(
        self, candidates: list[_ScoredCandidate], request: RoutingRequest, policy: RoutingPolicy
    ) -> list[_ScoredCandidate]:
        for c in candidates:
            lat = _compute_latency_score(c.provider, c.model, request.max_latency_ms)
            stream_bonus = 3.0 if c.model.supports_streaming else 0.0
            c.score = lat * 2 + stream_bonus
            c.reason = f"streaming={bool(c.model.supports_streaming)}, latency={lat:.3f}"
        candidates.sort(key=lambda x: x.score, reverse=True)
        return candidates


class ToolCallingOptimizedStrategy(PolicyStrategy):
    """Requires tool calling, prefers high quality."""

    name = "tool_calling_optimized"

    async def evaluate(
        self, candidates: list[_ScoredCandidate], request: RoutingRequest, policy: RoutingPolicy
    ) -> list[_ScoredCandidate]:
        for c in candidates:
            q = min(max(c.model.quality_score, 0.0), 1.0)
            tools_bonus = 3.0 if c.model.supports_tools else 0.0
            c.score = q * 2 + tools_bonus
            c.reason = f"tools={bool(c.model.supports_tools)}, quality={q:.3f}"
        candidates.sort(key=lambda x: x.score, reverse=True)
        return candidates


class CustomWeightedStrategy(PolicyStrategy):
    """Uses weight_overrides from the policy. Falls back to balanced defaults."""

    name = "custom_weighted"

    async def evaluate(
        self, candidates: list[_ScoredCandidate], request: RoutingRequest, policy: RoutingPolicy
    ) -> list[_ScoredCandidate]:
        w = _resolve_weights(
            policy,
            q=policy.weight_overrides.get("quality", 1.0),
            c=policy.weight_overrides.get("cost", 1.0),
            latency=policy.weight_overrides.get("latency", 1.0),
            h=policy.weight_overrides.get("health", 1.0),
            r=policy.weight_overrides.get("reliability", 0.5),
            ctx=policy.weight_overrides.get("context", 0.3),
            p=policy.weight_overrides.get("preference", 0.5),
        )
        for c in candidates:
            c.score = _weighted_total(c.provider, c.model, request, w)
            c.reason = "custom_weighted"
        candidates.sort(key=lambda x: x.score, reverse=True)
        return candidates


class RoundRobinStrategy(PolicyStrategy):
    """Rotates through viable candidates evenly."""

    name = "round_robin"

    def __init__(self) -> None:
        self._counter: int = 0

    async def evaluate(
        self, candidates: list[_ScoredCandidate], request: RoutingRequest, policy: RoutingPolicy
    ) -> list[_ScoredCandidate]:
        if not candidates:
            return candidates
        # Assign scores as 1/distance from current counter
        n = len(candidates)
        for i, c in enumerate(candidates):
            distance = (i - (self._counter % n)) % n
            c.score = 1.0 - (distance / max(n, 1))
            c.reason = f"round_robin_idx={i}"
        self._counter = (self._counter + 1) % n
        candidates.sort(key=lambda x: x.score, reverse=True)
        return candidates


class RandomStrategy(PolicyStrategy):
    """Picks randomly from viable candidates."""

    name = "random"

    async def evaluate(
        self, candidates: list[_ScoredCandidate], request: RoutingRequest, policy: RoutingPolicy
    ) -> list[_ScoredCandidate]:
        for c in candidates:
            c.score = random.random()
            c.reason = "random"
        candidates.sort(key=lambda x: x.score, reverse=True)
        return candidates


class StickyProviderStrategy(PolicyStrategy):
    """Prefer the same provider used by this user/workspace previously."""

    name = "sticky_provider"

    def __init__(self) -> None:
        self._last_provider: dict[str, str] = {}

    async def evaluate(
        self, candidates: list[_ScoredCandidate], request: RoutingRequest, policy: RoutingPolicy
    ) -> list[_ScoredCandidate]:
        key = request.user_id or request.workspace or "default"
        last = self._last_provider.get(key, "")
        for c in candidates:
            q = min(max(c.model.quality_score, 0.0), 1.0)
            stickiness = 3.0 if c.provider.id == last or c.provider.name == last else 0.0
            c.score = q + stickiness
            c.reason = f"sticky_provider={'yes' if stickiness else 'no'}"
        candidates.sort(key=lambda x: x.score, reverse=True)
        # Update last provider
        if candidates:
            self._last_provider[key] = candidates[0].provider.name
        return candidates


class WorkspaceDefaultStrategy(PolicyStrategy):
    """Like balanced but scoped to workspace; uses policy weight_overrides."""

    name = "workspace_default"

    async def evaluate(
        self, candidates: list[_ScoredCandidate], request: RoutingRequest, policy: RoutingPolicy
    ) -> list[_ScoredCandidate]:
        w = _resolve_weights(policy, q=1.0, c=1.0, latency=1.0, h=1.0, r=0.5, ctx=0.3, p=0.5)
        for c in candidates:
            c.score = _weighted_total(c.provider, c.model, request, w)
            c.reason = f"workspace={policy.workspace_scope}"
        candidates.sort(key=lambda x: x.score, reverse=True)
        return candidates


class AgentDefaultStrategy(PolicyStrategy):
    """Scoped to a specific agent."""

    name = "agent_default"

    async def evaluate(
        self, candidates: list[_ScoredCandidate], request: RoutingRequest, policy: RoutingPolicy
    ) -> list[_ScoredCandidate]:
        w = _resolve_weights(policy, q=1.0, c=1.0, latency=1.0, h=1.0, r=0.5, ctx=0.3, p=0.5)
        for c in candidates:
            c.score = _weighted_total(c.provider, c.model, request, w)
            c.reason = f"agent={policy.agent_scope}"
        candidates.sort(key=lambda x: x.score, reverse=True)
        return candidates


class UserDefaultStrategy(PolicyStrategy):
    """Scoped to a specific user."""

    name = "user_default"

    async def evaluate(
        self, candidates: list[_ScoredCandidate], request: RoutingRequest, policy: RoutingPolicy
    ) -> list[_ScoredCandidate]:
        w = _resolve_weights(policy, q=1.0, c=1.0, latency=1.0, h=1.0, r=0.5, ctx=0.3, p=0.5)
        for c in candidates:
            c.score = _weighted_total(c.provider, c.model, request, w)
            c.reason = f"user={policy.user_scope}"
        candidates.sort(key=lambda x: x.score, reverse=True)
        return candidates


class EmergencyFailoverStrategy(PolicyStrategy):
    """Last resort: picks anything functional, no scoring sophistication."""

    name = "emergency_failover"

    async def evaluate(
        self, candidates: list[_ScoredCandidate], request: RoutingRequest, policy: RoutingPolicy
    ) -> list[_ScoredCandidate]:
        for c in candidates:
            alive = 1.0 if c.provider.healthy and c.model.healthy else 0.0
            c.score = alive
            c.reason = "emergency_failover"
        candidates.sort(key=lambda x: x.score, reverse=True)
        return candidates


class SafeModeStrategy(PolicyStrategy):
    """Most conservative: only healthy, high-reliability picks."""

    name = "safe_mode"

    async def evaluate(
        self, candidates: list[_ScoredCandidate], request: RoutingRequest, policy: RoutingPolicy
    ) -> list[_ScoredCandidate]:
        for c in candidates:
            q = min(max(c.model.quality_score, 0.0), 1.0)
            rel = _compute_reliability_score(c.provider)
            health = _compute_health_score(c.provider, c.model)
            # Penalise anything not perfectly healthy
            if health < 1.0:
                c.score = 0.0
            else:
                c.score = q * 2 + rel * 3
            c.reason = "safe_mode"
        candidates.sort(key=lambda x: x.score, reverse=True)
        return candidates


class OfflineModeStrategy(PolicyStrategy):
    """Only local/offline providers."""

    name = "offline_mode"

    async def evaluate(
        self, candidates: list[_ScoredCandidate], request: RoutingRequest, policy: RoutingPolicy
    ) -> list[_ScoredCandidate]:
        for c in candidates:
            kind = c.provider.kind.lower() if c.provider.kind else ""
            name = c.provider.name.lower() if c.provider.name else ""
            is_local = any(
                t in kind or t in name
                for t in ("local", "ollama", "lm-studio", "lmstudio", "offline")
            )
            c.score = 1.0 if is_local else 0.0
            c.reason = "offline_mode"
        candidates.sort(key=lambda x: x.score, reverse=True)
        return candidates


# ── Registry & helpers ──


_strategy_registry: dict[str, type[PolicyStrategy]] = {
    "balanced": BalancedStrategy,
    "lowest_cost": LowestCostStrategy,
    "highest_quality": HighestQualityStrategy,
    "lowest_latency": LowestLatencyStrategy,
    "highest_reliability": HighestReliabilityStrategy,
    "local_first": LocalFirstStrategy,
    "cloud_first": CloudFirstStrategy,
    "reasoning_optimized": ReasoningOptimizedStrategy,
    "vision_optimized": VisionOptimizedStrategy,
    "streaming_optimized": StreamingOptimizedStrategy,
    "tool_calling_optimized": ToolCallingOptimizedStrategy,
    "custom_weighted": CustomWeightedStrategy,
    "round_robin": RoundRobinStrategy,
    "random": RandomStrategy,
    "sticky_provider": StickyProviderStrategy,
    "workspace_default": WorkspaceDefaultStrategy,
    "agent_default": AgentDefaultStrategy,
    "user_default": UserDefaultStrategy,
    "emergency_failover": EmergencyFailoverStrategy,
    "safe_mode": SafeModeStrategy,
    "offline_mode": OfflineModeStrategy,
}


def _resolve_weights(
    policy: RoutingPolicy,
    q: float = 1.0,
    c: float = 1.0,
    latency: float = 1.0,
    h: float = 1.0,
    r: float = 0.5,
    ctx: float = 0.3,
    p: float = 0.5,
) -> dict[str, float]:
    """Build a weights dict, with policy overrides applied."""
    ow = policy.weight_overrides
    return {
        "quality": ow.get("quality", q),
        "cost": ow.get("cost", c),
        "latency": ow.get("latency", latency),
        "health": ow.get("health", h),
        "reliability": ow.get("reliability", r),
        "context": ow.get("context", ctx),
        "preference": ow.get("preference", p),
    }


def _weighted_total(
    provider: OmniRouteProvider,
    model: OmniRouteModel,
    request: RoutingRequest,
    weights: dict[str, float],
) -> float:
    """Compute the weighted score for a provider+model pair."""
    q = min(max(model.quality_score, 0.0), 1.0) * weights.get("quality", 1.0)
    c = _compute_cost_score(provider, model) * weights.get("cost", 1.0)
    lat = _compute_latency_score(provider, model, request.max_latency_ms) * weights.get(
        "latency", 1.0
    )
    h = _compute_health_score(provider, model) * weights.get("health", 1.0)
    r = _compute_reliability_score(provider) * weights.get("reliability", 0.5)
    ctx = _compute_context_score(model) * weights.get("context", 0.3)
    pref = _compute_preference(provider, model, request) * weights.get("preference", 0.5)
    total = q + c + lat + h + r + ctx + pref
    denom = sum(weights.values())
    return round(total / denom if denom > 0 else 0.0, 4)


def _compute_preference(
    provider: OmniRouteProvider, model: OmniRouteModel, request: RoutingRequest
) -> float:
    score = 0.0
    if request.preferred_provider and (
        provider.name == request.preferred_provider or provider.id == request.preferred_provider
    ):
        score += 0.5
    if request.preferred_model and (
        model.model_id == request.preferred_model or model.display_name == request.preferred_model
    ):
        score += 0.5
    return round(min(1.0, score), 4)


# ── Metrics helper ──


class _MetricsTracker:
    """Lightweight metrics collector."""

    def __init__(self) -> None:
        self._policy_usage: dict[str, int] = {}
        self._evaluations = 0
        self._eval_time_total = 0.0
        self._failures = 0
        self._overrides = 0
        self._selection_freq: dict[str, int] = {}

    def record_evaluation(self, policy_name: str, duration_ms: float) -> None:
        self._evaluations += 1
        self._eval_time_total += duration_ms
        self._policy_usage[policy_name] = self._policy_usage.get(policy_name, 0) + 1

    def record_failure(self) -> None:
        self._failures += 1

    def record_override(self) -> None:
        self._overrides += 1

    def record_selection(self, provider: str, model: str) -> None:
        key = f"{provider}/{model}"
        self._selection_freq[key] = self._selection_freq.get(key, 0) + 1

    def snapshot(self) -> dict[str, Any]:
        return {
            "policy_usage": dict(sorted(self._policy_usage.items(), key=lambda x: -x[1])),
            "total_evaluations": self._evaluations,
            "avg_eval_time_ms": round(self._eval_time_total / max(self._evaluations, 1), 2),
            "failures": self._failures,
            "overrides": self._overrides,
            "selection_frequency": dict(sorted(self._selection_freq.items(), key=lambda x: -x[1])),
        }


# ── Concrete Implementation ──


class RoutingPolicyEngineImpl:
    """Production Routing Policy Engine.

    Manages the full lifecycle of routing policies (CRUD, scoping,
    evaluation) and externalizes all routing logic from the RouterEngine
    into configurable strategies.

    Integration flow::

        RoutingRequest
            ↓
        RoutingPolicyEngine.evaluate()
            ↓
        PolicyResult  (ranked candidates + winner)
            ↓
        RouterEngine  (builds RoutingDecision)
    """

    def __init__(self, event_bus: Any | None = None) -> None:
        self._event_bus = event_bus
        self._lock = asyncio.Lock()
        self._started = False
        self._start_time: float = 0.0

        # Policy storage
        self._policies: dict[str, RoutingPolicy] = {}
        self._default_policy_id: str = ""

        # Strategy instances (one per unique strategy name)
        self._strategies: dict[str, PolicyStrategy] = {
            name: cls() for name, cls in _strategy_registry.items()
        }

        # Metrics
        self._metrics = _MetricsTracker()

    # ── Lifecycle ──

    async def initialize(self) -> None:
        log.info("RoutingPolicyEngine initializing")
        # Seed default policies
        if not any(p.name == "Balanced (Default)" for p in self._policies.values()):
            default = RoutingPolicy(
                name="Balanced (Default)",
                description="Default balanced routing policy",
                strategy="balanced",
                priority=0,
            )
            pid = default.id
            self._policies[pid] = default
            self._default_policy_id = pid

    async def start(self) -> None:
        self._started = True
        self._start_time = time.monotonic()
        log.info("RoutingPolicyEngine started")

    async def stop(self) -> None:
        self._started = False
        log.info("RoutingPolicyEngine stopped")

    async def dispose(self) -> None:
        await self.stop()
        self._policies.clear()
        self._default_policy_id = ""
        log.info("RoutingPolicyEngine disposed")

    async def health(self) -> dict[str, Any]:
        uptime = time.monotonic() - self._start_time if self._started else 0.0
        return {
            "status": "healthy" if self._started else "stopped",
            "started": self._started,
            "uptime_seconds": round(uptime, 2),
            "policy_count": len(self._policies),
            "strategies_available": list(self._strategies.keys()),
        }

    async def ready(self) -> bool:
        return self._started

    async def metadata(self) -> dict[str, Any]:
        return {
            "type": "RoutingPolicyEngineImpl",
            "version": "1.0.0",
            "started": self._started,
            "policy_count": len(self._policies),
            "strategies_available": list(self._strategies.keys()),
        }

    async def dependencies(self) -> list[str]:
        return []

    async def capabilities(self) -> list[dict[str, Any]]:
        return [
            {"name": "policy_crud", "description": "Create, read, update, delete routing policies"},
            {"name": "policy_evaluation", "description": "Evaluate candidates against policies"},
            {"name": "policy_scoping", "description": "Scope policies to workspace/agent/user"},
            {"name": "policy_ranking", "description": "Rank policies by priority"},
            {"name": "strategy_management", "description": "Manage 21 built-in routing strategies"},
        ]

    # ── Public API ──

    async def create_policy(self, policy: RoutingPolicy) -> str:
        async with self._lock:
            pid = policy.id
            if pid in self._policies:
                msg = f"Policy {pid} already exists"
                raise ValueError(msg)
            self._policies[pid] = policy
        await self._publish(Topic.ROUTING_POLICY_CREATED, {"policy_id": pid, "name": policy.name})
        log.info("Policy created: %s (%s)", policy.name, pid)
        return pid

    async def update_policy(self, policy: RoutingPolicy) -> str:
        pid = policy.id
        async with self._lock:
            if pid not in self._policies:
                msg = f"Policy {pid} not found"
                raise ValueError(msg)
            self._policies[pid] = policy
        await self._publish(Topic.ROUTING_POLICY_UPDATED, {"policy_id": pid, "name": policy.name})
        return pid

    async def delete_policy(self, policy_id: str) -> bool:
        async with self._lock:
            if policy_id not in self._policies:
                return False
            del self._policies[policy_id]
            if self._default_policy_id == policy_id:
                self._default_policy_id = ""
        await self._publish(Topic.ROUTING_POLICY_DELETED, {"policy_id": policy_id})
        return True

    async def enable_policy(self, policy_id: str) -> bool:
        async with self._lock:
            p = self._policies.get(policy_id)
            if p is None:
                return False
            if p.enabled:
                return False
            self._policies[policy_id] = RoutingPolicy(
                id=p.id,
                name=p.name,
                description=p.description,
                enabled=True,
                priority=p.priority,
                strategy=p.strategy,
                provider_filter=p.provider_filter,
                model_filter=p.model_filter,
                capability_filter=p.capability_filter,
                weight_overrides=p.weight_overrides,
                budget_override=p.budget_override,
                latency_override_ms=p.latency_override_ms,
                context_override=p.context_override,
                workspace_scope=p.workspace_scope,
                agent_scope=p.agent_scope,
                user_scope=p.user_scope,
                metadata=p.metadata,
                version=p.version,
            )
        await self._publish(Topic.ROUTING_POLICY_ENABLED, {"policy_id": policy_id})
        return True

    async def disable_policy(self, policy_id: str) -> bool:
        async with self._lock:
            p = self._policies.get(policy_id)
            if p is None:
                return False
            if not p.enabled:
                return False
            self._policies[policy_id] = RoutingPolicy(
                id=p.id,
                name=p.name,
                description=p.description,
                enabled=False,
                priority=p.priority,
                strategy=p.strategy,
                provider_filter=p.provider_filter,
                model_filter=p.model_filter,
                capability_filter=p.capability_filter,
                weight_overrides=p.weight_overrides,
                budget_override=p.budget_override,
                latency_override_ms=p.latency_override_ms,
                context_override=p.context_override,
                workspace_scope=p.workspace_scope,
                agent_scope=p.agent_scope,
                user_scope=p.user_scope,
                metadata=p.metadata,
                version=p.version,
            )
        await self._publish(Topic.ROUTING_POLICY_DISABLED, {"policy_id": policy_id})
        return True

    async def get_policy(self, policy_id: str) -> RoutingPolicy | None:
        async with self._lock:
            return self._policies.get(policy_id)

    async def list_policies(self, *, enabled_only: bool = False) -> list[RoutingPolicy]:
        async with self._lock:
            result = list(self._policies.values())
        if enabled_only:
            result = [p for p in result if p.enabled]
        return sorted(result, key=lambda p: (-p.priority, p.name))

    async def default_policy(self) -> RoutingPolicy | None:
        if self._default_policy_id:
            async with self._lock:
                return self._policies.get(self._default_policy_id)
        # Fallback: first policy by priority
        async with self._lock:
            if not self._policies:
                return None
            return max(self._policies.values(), key=lambda p: (p.priority, p.name))

    async def set_default(self, policy_id: str) -> bool:
        async with self._lock:
            if policy_id not in self._policies:
                return False
            self._default_policy_id = policy_id
        return True

    async def evaluate(
        self,
        candidates: list[Any],
        request: RoutingRequest,
        policy: RoutingPolicy | None = None,
    ) -> PolicyResult:
        """Evaluate candidates against the resolved policy.

        *candidates* must be a list of (provider, model) tuples.
        """
        eval_start = time.monotonic()
        resolved = policy or await self.resolve_policy(request)

        # Convert raw candidates to _ScoredCandidate
        scored: list[_ScoredCandidate] = []
        for item in candidates:
            if isinstance(item, tuple):
                provider, model = item
            else:
                provider, model = item.provider, item.model
            scored.append(_ScoredCandidate(provider=provider, model=model))

        if not scored:
            return PolicyResult(
                policy_name=resolved.name,
                policy_id=resolved.id,
                strategy=resolved.strategy,
                reason="No candidates to evaluate",
            )

        # Apply policy filters
        scored = await self._apply_policy_filters(scored, resolved)

        # Get strategy instance and evaluate
        strategy_name = resolved.strategy
        strategy = self._strategies.get(strategy_name)
        if strategy is None:
            log.warning("Unknown strategy %s, falling back to balanced", strategy_name)
            strategy = self._strategies.get("balanced", BalancedStrategy())

        scored = await strategy.evaluate(scored, request, resolved)

        # Build result
        overrides = {}
        if resolved.weight_overrides:
            overrides["weight_overrides"] = dict(resolved.weight_overrides)
        if resolved.budget_override > 0:
            overrides["budget_override"] = resolved.budget_override
        if resolved.latency_override_ms > 0:
            overrides["latency_override_ms"] = resolved.latency_override_ms
        if resolved.context_override > 0:
            overrides["context_override"] = resolved.context_override

        scored_tuples: list[tuple[str, str, str, float]] = []
        for _i, s in enumerate(scored):
            scored_tuples.append((s.provider.name, s.model.model_id, s.reason, s.score))

        selected = scored[0] if scored else None
        duration_ms = round((time.monotonic() - eval_start) * 1000, 2)

        self._metrics.record_evaluation(strategy_name, duration_ms)
        if selected:
            self._metrics.record_selection(selected.provider.name, selected.model.model_id)

        await self._publish(
            Topic.ROUTING_POLICY_SELECTED,
            {
                "policy_id": resolved.id,
                "policy_name": resolved.name,
                "strategy": strategy_name,
                "selected_provider": selected.provider.name if selected else "",
                "selected_model": selected.model.model_id if selected else "",
                "candidates_evaluated": len(scored),
                "evaluation_time_ms": duration_ms,
            },
        )

        return PolicyResult(
            policy_name=resolved.name,
            policy_id=resolved.id,
            strategy=strategy_name,
            selected_provider=selected.provider.name if selected else "",
            selected_provider_id=selected.provider.id if selected else "",
            selected_model=selected.model.display_name or selected.model.model_id
            if selected
            else "",
            selected_model_id=selected.model.model_id if selected else "",
            selected_cost=(selected.model.input_cost_per_1k + selected.model.output_cost_per_1k)
            if selected
            else 0.0,
            selected_latency_ms=max(selected.provider.latency_ms, selected.model.latency_ms)
            if selected
            else 0.0,
            scored_candidates=tuple(scored_tuples),
            reason=selected.reason if selected else "No viable candidates",
            evaluation_time_ms=duration_ms,
            policy_applied=True,
            overrides_used=overrides,
        )

    async def resolve_policy(self, request: RoutingRequest) -> RoutingPolicy:
        """Resolve which policy applies to a request.

        1. Check user-scoped policies
        2. Check agent-scoped policies
        3. Check workspace-scoped policies
        4. Return the default policy
        """
        applicable = await self.applicable_policies(request)
        if applicable:
            return applicable[0]

        default = await self.default_policy()
        if default:
            return default

        # Create a synthetic balanced policy if nothing exists
        return RoutingPolicy(name="Fallback Balanced", strategy="balanced", priority=-1)

    async def applicable_policies(self, request: RoutingRequest) -> list[RoutingPolicy]:
        """Return policies that match the request's scope, sorted by priority."""
        policies = await self.list_policies(enabled_only=True)
        matched: list[RoutingPolicy] = []

        for p in policies:
            # Scope checks: empty scope or matching
            if p.user_scope and p.user_scope != request.user_id:
                continue
            if p.agent_scope and p.agent_scope != request.agent:
                continue
            if p.workspace_scope and p.workspace_scope != request.workspace:
                continue
            # Provider / model / capability pre-filters
            if p.provider_filter and request.preferred_provider:
                if request.preferred_provider not in p.provider_filter:
                    continue
            if p.model_filter and request.preferred_model:
                if request.preferred_model not in p.model_filter:
                    continue
            if p.capability_filter and request.required_capabilities:
                cap_set = {c.lower() for c in request.required_capabilities}
                pol_caps = {c.lower() for c in p.capability_filter}
                if not cap_set.intersection(pol_caps):
                    continue
            matched.append(p)

        return sorted(matched, key=lambda p: (-p.priority, p.name))

    async def rank_policies(self, request: RoutingRequest) -> list[RoutingPolicy]:
        """Return applicable policies sorted by priority descending."""
        return await self.applicable_policies(request)

    # ── Policy Filters ──

    async def _apply_policy_filters(
        self,
        candidates: list[_ScoredCandidate],
        policy: RoutingPolicy,
    ) -> list[_ScoredCandidate]:
        """Apply provider/model/capability filters from the policy."""
        result = list(candidates)

        if policy.provider_filter:
            pf = {p.lower() for p in policy.provider_filter}
            result = [
                c for c in result if c.provider.name.lower() in pf or c.provider.id.lower() in pf
            ]

        if policy.model_filter:
            mf = {m.lower() for m in policy.model_filter}
            result = [
                c
                for c in result
                if c.model.model_id.lower() in mf
                or (c.model.display_name and c.model.display_name.lower() in mf)
            ]

        if policy.capability_filter:
            caps = {cap.lower() for cap in policy.capability_filter}
            result = [
                c
                for c in result
                if caps.intersection({cap.lower() for cap in c.model.capabilities})
            ]

        return result

    # ── Metrics ──

    def metrics(self) -> dict[str, Any]:
        return self._metrics.snapshot()

    # ── Strategy access ──

    def get_strategy_names(self) -> list[str]:
        return list(self._strategies.keys())

    def get_strategy(self, name: str) -> PolicyStrategy | None:
        return self._strategies.get(name)

    # ── Internal ──

    async def _publish(self, topic: Topic, payload: dict[str, Any]) -> None:
        if self._event_bus is None:
            return
        try:
            envelope = EventEnvelope(
                type=topic.value,
                source="omniroute.routing_policies",
                topic=topic.value,
                payload=payload,
            )
            await self._event_bus.publish(envelope)
        except Exception:
            log.warning("Failed to publish event %s", topic.value, exc_info=True)


__all__ = [
    "RoutingPolicyPort",
    "RoutingPolicyEngineImpl",
    "PolicyStrategy",
    "BalancedStrategy",
    "LowestCostStrategy",
    "HighestQualityStrategy",
    "LowestLatencyStrategy",
    "HighestReliabilityStrategy",
    "LocalFirstStrategy",
    "CloudFirstStrategy",
    "ReasoningOptimizedStrategy",
    "VisionOptimizedStrategy",
    "StreamingOptimizedStrategy",
    "ToolCallingOptimizedStrategy",
    "CustomWeightedStrategy",
    "RoundRobinStrategy",
    "RandomStrategy",
    "StickyProviderStrategy",
    "WorkspaceDefaultStrategy",
    "AgentDefaultStrategy",
    "UserDefaultStrategy",
    "EmergencyFailoverStrategy",
    "SafeModeStrategy",
    "OfflineModeStrategy",
    "_ScoredCandidate",
    "_strategy_registry",
]
