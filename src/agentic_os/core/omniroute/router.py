"""OmniRoute Router Engine — production-grade intelligent routing brain.

Selects the optimal provider + model for each request by executing a
configurable pipeline: request validation → filter unhealthy/disabled →
capability filtering → context/budget/latency filtering → weighted scoring
→ fallback chain generation → final decision.

Port protocol
-------------
:class:`RouterEnginePort` — implement this or depend on it.  All OmniRoute
consumers (Gateway, Swarm, AI Brain, Mission Control) talk through this port.
"""

from __future__ import annotations

import asyncio
import math
import time
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from agentic_os.domain.events import EventEnvelope, Topic
from agentic_os.domain.omniroute import (
    OmniRouteModel,
    OmniRouteProvider,
    RoutingDecision,
    RoutingRequest,
    RoutingScore,
)
from agentic_os.infrastructure.logging import get_logger

log = get_logger("omniroute.router")


# ── Port Protocol ──


@runtime_checkable
class RouterEnginePort(Protocol):
    """OmniRoute router — the intelligent routing brain."""

    async def route(self, request: RoutingRequest) -> RoutingDecision:
        """Execute the full routing pipeline and return a decision."""
        ...

    async def route_many(self, requests: list[RoutingRequest]) -> list[RoutingDecision]:
        """Route multiple requests, returning decisions in the same order."""
        ...

    async def best_model(self, request: RoutingRequest, top_k: int = 1) -> list[RoutingDecision]:
        """Return the top-k best models for a request (skip scoring)."""
        ...

    async def best_provider(self, request: RoutingRequest) -> RoutingDecision | None:
        """Return the single best provider (skip model selection)."""
        ...

    async def rank_models(self, request: RoutingRequest, limit: int = 20) -> list[RoutingDecision]:
        """Return all viable candidates ranked by score."""
        ...

    async def rank_providers(self, request: RoutingRequest) -> list[RoutingDecision]:
        """Return viable providers ranked by aggregate capability score."""
        ...

    async def generate_fallback_chain(
        self, request: RoutingRequest, chain_length: int = 5
    ) -> tuple[tuple[str, str, str], ...]:
        """Build an ordered fallback chain of (provider, provider_id, model) tuples."""
        ...

    async def validate_request(self, request: RoutingRequest) -> list[str]:
        """Validate a RoutingRequest. Returns list of error messages (empty = valid)."""
        ...

    async def estimate_cost(self, request: RoutingRequest) -> float:
        """Estimate the cost of handling a request (max possible)."""
        ...

    async def estimate_latency(self, request: RoutingRequest) -> float:
        """Estimate the latency of handling a request (fastest possible)."""
        ...

    async def score_candidate(
        self,
        provider: OmniRouteProvider,
        model: OmniRouteModel,
        request: RoutingRequest,
    ) -> RoutingScore:
        """Score a single provider+model candidate for a request."""
        ...

    async def supported_capabilities(self) -> list[str]:
        """Return all capabilities the router can handle."""
        ...

    # ── Lifecycle ──

    async def initialize(self) -> None:
        """Initialize the router engine resources."""
        ...

    async def start(self) -> None:
        """Start the router engine."""
        ...

    async def stop(self) -> None:
        """Stop the router engine and release resources."""
        ...

    async def dispose(self) -> None:
        """Final cleanup after stop."""
        ...

    async def health(self) -> dict[str, Any]:
        """Health status of the router itself."""
        ...

    async def ready(self) -> bool:
        """True if the router is started and operational."""
        ...

    async def metadata(self) -> dict[str, Any]:
        """Service metadata for the LifecycleManager."""
        ...

    async def dependencies(self) -> list[str]:
        """Dependency names for the LifecycleManager."""
        ...

    async def capabilities(self) -> list[dict[str, Any]]:
        """Capability list for the ServiceRegistry."""
        ...


# ── Internal Candidate ──


@dataclass
class _Candidate:
    """A scored provider+model pair during routing."""

    provider: OmniRouteProvider
    model: OmniRouteModel
    score: RoutingScore = field(default_factory=RoutingScore)
    weighted_total: float = 0.0
    rank: int = 0


# ── Scoring Engine ──


class _ScoringEngine:
    """Weighted scoring with dimension normalization.

    Each dimension is normalised to [0, 1] where 1 = best.
    The weighted total is sum(score_i * weight_i) / sum(weights).
    """

    def __init__(self, request: RoutingRequest) -> None:
        self._request = request

    def score(self, provider: OmniRouteProvider, model: OmniRouteModel) -> RoutingScore:
        quality = self._score_quality(model)
        cost = self._score_cost(provider, model)
        latency = self._score_latency(provider, model)
        health = self._score_health(provider, model)
        reliability = self._score_reliability(provider)
        context = self._score_context(model)
        preference = self._score_preference(provider, model)

        # Weighted combination
        w_quality = self._request.quality_weight
        w_cost = self._request.cost_weight
        w_latency = self._request.latency_weight
        w_health = 1.0
        w_reliability = 0.5
        w_context = 0.3
        w_preference = 0.5

        total_weight = (
            w_quality + w_cost + w_latency + w_health + w_reliability + w_context + w_preference
        )
        if total_weight <= 0:
            total_weight = 1.0

        weighted_total = (
            quality * w_quality
            + cost * w_cost
            + latency * w_latency
            + health * w_health
            + reliability * w_reliability
            + context * w_context
            + preference * w_preference
        ) / total_weight

        return RoutingScore(
            quality_score=round(quality, 4),
            cost_score=round(cost, 4),
            latency_score=round(latency, 4),
            health_score=round(health, 4),
            reliability_score=round(reliability, 4),
            context_score=round(context, 4),
            preference_score=round(preference, 4),
            weighted_total=round(weighted_total, 4),
            candidate_count=1,
            rank=0,
        )

    def _score_quality(self, model: OmniRouteModel) -> float:
        """Quality score — higher quality_score on model = better."""
        return min(max(model.quality_score, 0.0), 1.0)

    def _score_cost(self, provider: OmniRouteProvider, model: OmniRouteModel) -> float:
        """Cost score — cheaper = better. Inverted sigmoid on combined cost."""
        total_cost = provider.cost_per_1k_input + provider.cost_per_1k_output
        total_cost += model.input_cost_per_1k + model.output_cost_per_1k
        if total_cost <= 0:
            return 1.0
        # Inverted normalised log: cost_score = 1 - log(1+cost) / log(1+max_cost)
        # max realistic cost is ~$10 per 1k
        max_cost = 10.0
        raw = math.log1p(total_cost) / math.log1p(max_cost)
        return round(max(0.0, 1.0 - raw), 4)

    def _score_latency(self, provider: OmniRouteProvider, model: OmniRouteModel) -> float:
        """Latency score — lower latency = better. Uses both provider and model latency."""
        combined = max(provider.latency_ms, model.latency_ms)
        if combined <= 0:
            return 1.0
        max_latency = self._request.max_latency_ms or 5000.0
        raw = combined / max_latency
        return round(max(0.0, min(1.0, 1.0 - raw)), 4)

    def _score_health(self, provider: OmniRouteProvider, model: OmniRouteModel) -> float:
        """Health score — 1.0 if both healthy, 0.5 if only model healthy, 0.0 otherwise."""
        if provider.healthy and model.healthy:
            return 1.0
        if provider.healthy or model.healthy:
            return 0.5
        return 0.0

    def _score_reliability(self, provider: OmniRouteProvider) -> float:
        """Reliability score — providers that are healthy + enabled get a boost."""
        if not provider.enabled:
            return 0.0
        if provider.healthy:
            return 1.0
        return 0.3

    def _score_context(self, model: OmniRouteModel) -> float:
        """Context score — larger context = better, capped at 1M."""
        if model.context_window <= 0:
            return 0.0
        max_ctx = 1_000_000
        raw = math.log1p(model.context_window) / math.log1p(max_ctx)
        return round(min(1.0, raw), 4)

    def _score_preference(self, provider: OmniRouteProvider, model: OmniRouteModel) -> float:
        """Preference score — boost for preferred provider/model in the request."""
        score = 0.0
        req = self._request
        if req.preferred_provider and (
            provider.name == req.preferred_provider or provider.id == req.preferred_provider
        ):
            score += 0.5
        if req.preferred_model and (
            model.model_id == req.preferred_model or model.display_name == req.preferred_model
        ):
            score += 0.5
        return round(min(1.0, score), 4)


# ── Fallback Engine ──


class _FallbackEngine:
    """Generates ordered fallback chains from ranked candidates."""

    @staticmethod
    def generate(
        candidates: list[_Candidate],
        chain_length: int = 5,
    ) -> tuple[tuple[str, str, str], ...]:
        """Build (provider_name, provider_id, model_id) tuples from top candidates.

        Skips candidates that have zero score (incompatible).
        """
        chain: list[tuple[str, str, str]] = []
        for c in candidates:
            if len(chain) >= chain_length:
                break
            if c.weighted_total <= 0.0:
                continue
            chain.append((c.provider.name, c.provider.id, c.model.model_id))
        return tuple(chain)

    @staticmethod
    def generate_by_provider(
        providers: list[OmniRouteProvider],
        chain_length: int = 5,
    ) -> tuple[tuple[str, str, str], ...]:
        """Build fallback chain from providers only (no model selection yet)."""
        chain: list[tuple[str, str, str]] = []
        for p in providers:
            if len(chain) >= chain_length:
                break
            chain.append((p.name, p.id, ""))
        return tuple(chain)


# ── Histogram helpers for P50/P95/P99 ──


class _LatencyHistogram:
    """Bounded histogram for latency percentiles."""

    def __init__(self, max_samples: int = 1000) -> None:
        self._samples: list[float] = []
        self._max = max_samples

    def record(self, value: float) -> None:
        self._samples.append(value)
        if len(self._samples) > self._max:
            self._samples = self._samples[-self._max :]

    def percentile(self, p: float) -> float:
        if not self._samples:
            return 0.0
        sorted_s = sorted(self._samples)
        idx = max(0, min(len(sorted_s) - 1, int(len(sorted_s) * p / 100)))
        return sorted_s[idx]

    @property
    def count(self) -> int:
        return len(self._samples)


# ── Concrete Implementation ──


class RouterEngineImpl:
    """Production Router Engine — the intelligent routing brain.

    Integrates with:
      - ProviderRegistry  (validate provider existence, health)
      - ModelRegistry      (model search, filtering)
      - EventBus           (publish lifecycle events)
      - RoutingPolicy      (configurable decision strategies)
      - CircuitBreaker     (provider resilience filtering)
      - BudgetEngine       (financial decision layer)

    The 13-step routing pipeline:
      1. Validate request
      2. Query ProviderRegistry
      3. Query ModelRegistry
      4. Remove unhealthy/disabled
      5. Budget Engine filtering
      6. Circuit breaker filtering
      7. Adaptive Learning enrichment
      8. Capability filtering
      9. Context window filtering
     10. Budget limit check (request-level)
     11. Latency filtering
     12. Weighted scoring / policy evaluation
     13. Return RoutingDecision
    """

    def __init__(
        self,
        provider_registry: Any | None = None,
        model_registry: Any | None = None,
        event_bus: Any | None = None,
        routing_policy_engine: Any | None = None,
        budget_engine: Any | None = None,
        circuit_breaker: Any | None = None,
        adaptive_learning_engine: Any | None = None,
    ) -> None:
        from agentic_os.core.omniroute.model_registry import ModelRegistryPort
        from agentic_os.core.omniroute.provider_registry import ProviderRegistryPort

        self._provider_registry: ProviderRegistryPort | None = provider_registry
        self._model_registry: ModelRegistryPort | None = model_registry
        self._event_bus = event_bus
        self._routing_policy_engine = routing_policy_engine
        self._budget_engine = budget_engine
        self._circuit_breaker = circuit_breaker
        self._adaptive_learning_engine = adaptive_learning_engine

        self._lock = asyncio.Lock()
        self._started = False
        self._start_time: float = 0.0

        # Observability counters
        self._routing_count = 0
        self._routing_failures = 0
        self._routing_duration_total = 0.0
        self._provider_selection: dict[str, int] = {}
        self._model_selection: dict[str, int] = {}
        self._total_candidates = 0
        self._total_scoring_time = 0.0
        self._latency_histogram = _LatencyHistogram()

    # ── Lifecycle ──

    async def initialize(self) -> None:
        log.info("RouterEngine initializing")
        # Future: load persisted state, warm caches

    async def start(self) -> None:
        self._started = True
        self._start_time = time.monotonic()
        log.info("RouterEngine started")

    async def stop(self) -> None:
        self._started = False
        log.info("RouterEngine stopped")

    async def dispose(self) -> None:
        await self.stop()
        self._latency_histogram = _LatencyHistogram()
        self._provider_selection.clear()
        self._model_selection.clear()
        self._routing_count = 0
        self._routing_duration_total = 0.0
        log.info("RouterEngine disposed")

    async def health(self) -> dict[str, Any]:
        uptime = time.monotonic() - self._start_time if self._started else 0.0
        return {
            "status": "healthy" if self._started else "stopped",
            "started": self._started,
            "uptime_seconds": round(uptime, 2),
            "routing_count": self._routing_count,
            "routing_failures": self._routing_failures,
            "provider_registry": self._provider_registry is not None,
            "model_registry": self._model_registry is not None,
        }

    async def ready(self) -> bool:
        return self._started

    async def metadata(self) -> dict[str, Any]:
        return {
            "type": "RouterEngineImpl",
            "version": "1.0.0",
            "started": self._started,
            "provider_registry": self._provider_registry is not None,
            "model_registry": self._model_registry is not None,
            "routing_count": self._routing_count,
        }

    async def dependencies(self) -> list[str]:
        return ["provider_registry", "model_registry"]

    async def capabilities(self) -> list[dict[str, Any]]:
        return [
            {"name": "routing", "description": "Route requests to optimal provider+model"},
            {"name": "ranking", "description": "Rank providers and models by suitability"},
            {"name": "fallback", "description": "Generate ordered fallback chains"},
            {"name": "scoring", "description": "Weighted multi-dimensional scoring"},
            {"name": "estimation", "description": "Estimate cost and latency for requests"},
        ]

    # ── Public API ──

    async def route(self, request: RoutingRequest) -> RoutingDecision:
        """Execute the full 12-step routing pipeline."""
        if not self._started:
            return RoutingDecision(
                request_id=request.request_id,
                status="failed",
                reason="Router engine not started",
            )

        start = time.monotonic()
        async with self._lock:
            self._routing_count += 1

        await self._publish(
            Topic.ROUTE_REQUESTED,
            {
                "request_id": request.request_id,
                "task_type": request.task_type,
                "capabilities": list(request.required_capabilities),
            },
        )

        # Step 1: Validate
        errors = await self.validate_request(request)
        if errors:
            self._routing_failures += 1
            decision = RoutingDecision(
                request_id=request.request_id,
                status="rejected",
                reason="; ".join(errors),
            )
            await self._publish(
                Topic.ROUTE_REJECTED,
                {
                    "request_id": request.request_id,
                    "errors": errors,
                },
            )
            return decision

        # Steps 2-3: Query registries
        providers, models = await self._query_registries(request)
        if not providers or not models:
            self._routing_failures += 1
            decision = RoutingDecision(
                request_id=request.request_id,
                status="failed",
                reason="No providers or models available",
            )
            await self._publish(
                Topic.ROUTE_FAILED,
                {
                    "request_id": request.request_id,
                    "reason": "No providers or models available",
                },
            )
            return decision

        # Step 4: Remove unhealthy/disabled
        candidates = await self._filter_unhealthy_disabled(providers, models)
        if not candidates:
            self._routing_failures += 1
            decision = RoutingDecision(
                request_id=request.request_id,
                status="failed",
                reason="All providers/models unhealthy or disabled",
            )
            await self._publish(
                Topic.ROUTE_FAILED,
                {
                    "request_id": request.request_id,
                    "reason": "All providers/models unhealthy or disabled",
                },
            )
            return decision

        # Step 5: Budget Engine — filter candidates by spending policies
        if self._budget_engine is not None:
            budget_candidates = [(c.provider, c.model) for c in candidates]
            budget_decision = await self._budget_engine.evaluate(budget_candidates, request)
            if not budget_decision.approved:
                self._routing_failures += 1
                decision = RoutingDecision(
                    request_id=request.request_id,
                    status="failed",
                    reason=f"Budget exceeded: {budget_decision.reason}",
                )
                await self._publish(
                    Topic.ROUTE_FAILED,
                    {
                        "request_id": request.request_id,
                        "reason": decision.reason,
                    },
                )
                return decision
            # Remove candidates that were filtered out by budget
            filtered_names = set(budget_decision.filtered_candidates)
            if filtered_names:
                candidates = [
                    c
                    for c in candidates
                    if f"{c.provider.name}/{c.model.model_id}" not in filtered_names
                ]
                if not candidates:
                    self._routing_failures += 1
                    decision = RoutingDecision(
                        request_id=request.request_id,
                        status="failed",
                        reason="All candidates excluded by budget policies",
                    )
                    await self._publish(
                        Topic.ROUTE_FAILED,
                        {
                            "request_id": request.request_id,
                            "reason": decision.reason,
                        },
                    )
                    return decision

        # Step 6: Circuit breaker filtering
        if self._circuit_breaker is not None:
            candidates = await self._filter_circuit_breaker(candidates)
            if not candidates:
                self._routing_failures += 1
                decision = RoutingDecision(
                    request_id=request.request_id,
                    status="failed",
                    reason="All candidates excluded by circuit breaker",
                )
                await self._publish(
                    Topic.ROUTE_FAILED,
                    {
                        "request_id": request.request_id,
                        "reason": "All candidates excluded by circuit breaker",
                    },
                )
                return decision

        # Step 7: Adaptive Learning enrichment (before capability filtering)
        if self._adaptive_learning_engine is not None:
            await self._adaptive_learning_engine.enrich(candidates, request)

        # Step 8: Capability filtering
        candidates = await self._filter_capabilities(candidates, request)
        if not candidates:
            self._routing_failures += 1
            decision = RoutingDecision(
                request_id=request.request_id,
                status="failed",
                reason="No candidates match required capabilities",
            )
            await self._publish(
                Topic.ROUTE_FAILED,
                {
                    "request_id": request.request_id,
                    "reason": "No candidates match required capabilities",
                },
            )
            return decision

        # Step 8: Context window filtering
        candidates = await self._filter_context(candidates, request)

        # Step 9: Request budget limit check (fast path for simple limits)
        if request.budget_limit > 0:
            candidates = await self._filter_budget(candidates, request)

        # Step 10: Latency filtering
        if request.max_latency_ms > 0:
            candidates = await self._filter_latency(candidates, request)

        if not candidates:
            self._routing_failures += 1
            decision = RoutingDecision(
                request_id=request.request_id,
                status="failed",
                reason="No candidates pass budget/latency constraints",
            )
            await self._publish(
                Topic.ROUTE_FAILED,
                {
                    "request_id": request.request_id,
                    "reason": "No candidates pass budget/latency constraints",
                },
            )
            return decision

        # Step 11-12: Evaluate via RoutingPolicyEngine or fall back to weighted scoring
        scoring_start = time.monotonic()
        if self._routing_policy_engine is not None:
            # Delegate to policy engine
            raw_candidates = [(c.provider, c.model) for c in candidates]
            policy_result = await self._routing_policy_engine.evaluate(raw_candidates, request)
            scoring_duration = time.monotonic() - scoring_start
            self._total_scoring_time += scoring_duration

            if not policy_result.selected_model_id:
                self._routing_failures += 1
                decision = RoutingDecision(
                    request_id=request.request_id,
                    status="failed",
                    reason=policy_result.reason or "Policy engine returned no selection",
                )
                await self._publish(
                    Topic.ROUTE_FAILED,
                    {
                        "request_id": request.request_id,
                        "reason": decision.reason,
                    },
                )
                return decision

            # Build scored list from policy result
            scored: list[_Candidate] = []
            for pname, mid, _reason, score_val in policy_result.scored_candidates:
                for c in candidates:
                    if c.provider.name == pname and c.model.model_id == mid:
                        routing_score = RoutingScore(
                            quality_score=score_val,
                            cost_score=score_val,
                            latency_score=score_val,
                            health_score=score_val,
                            reliability_score=score_val,
                            context_score=score_val,
                            preference_score=score_val,
                            weighted_total=score_val,
                            candidate_count=len(policy_result.scored_candidates),
                            rank=0,
                        )
                        scored.append(
                            _Candidate(
                                provider=c.provider,
                                model=c.model,
                                score=routing_score,
                                weighted_total=score_val,
                            )
                        )
                        break

            if not scored:
                self._routing_failures += 1
                decision = RoutingDecision(
                    request_id=request.request_id,
                    status="failed",
                    reason="Policy engine scored zero candidates",
                )
                await self._publish(
                    Topic.ROUTE_FAILED,
                    {
                        "request_id": request.request_id,
                        "reason": decision.reason,
                    },
                )
                return decision

            scored.sort(key=lambda c: c.weighted_total, reverse=True)
            for i, c in enumerate(scored):
                c.rank = i + 1
                c.score = RoutingScore(
                    quality_score=c.score.quality_score,
                    cost_score=c.score.cost_score,
                    latency_score=c.score.latency_score,
                    health_score=c.score.health_score,
                    reliability_score=c.score.reliability_score,
                    context_score=c.score.context_score,
                    preference_score=c.score.preference_score,
                    weighted_total=c.score.weighted_total,
                    candidate_count=len(scored),
                    rank=i + 1,
                )

            async with self._lock:
                self._total_candidates += len(scored)

            best = scored[0]
            fallback_chain = _FallbackEngine.generate(scored, chain_length=5)
            estimated_cost = policy_result.selected_cost or (
                best.model.input_cost_per_1k + best.model.output_cost_per_1k
            )
            estimated_latency = policy_result.selected_latency_ms or max(
                best.provider.latency_ms, best.model.latency_ms
            )
            confidence = best.score.weighted_total

            decision = RoutingDecision(
                request_id=request.request_id,
                provider=best.provider.name,
                provider_id=best.provider.id,
                model=best.model.display_name or best.model.model_id,
                model_id=best.model.model_id,
                score=best.score,
                reason=(
                    policy_result.reason
                    or (
                        f"Selected {best.provider.name}/{best.model.model_id}"
                        f" via {policy_result.strategy}"
                    )
                ),
                fallback_chain=fallback_chain,
                estimated_cost=round(estimated_cost, 6),
                estimated_latency_ms=round(estimated_latency, 2),
                confidence=round(confidence, 4),
                policy_used=policy_result.strategy or "policy_engine",
                status="routed",
                alternatives_rejected=len(scored) - 1,
            )
        else:
            # Fallback: hardcoded weighted scoring (legacy)
            candidates.sort(key=lambda c: c.model.quality_score, reverse=True)
            scorer = _ScoringEngine(request)
            scored = []
            for c in candidates:
                score = scorer.score(c.provider, c.model)
                scored.append(
                    _Candidate(
                        provider=c.provider,
                        model=c.model,
                        score=score,
                        weighted_total=score.weighted_total,
                    )
                )
            scoring_duration = time.monotonic() - scoring_start
            self._total_scoring_time += scoring_duration

            scored.sort(key=lambda c: c.weighted_total, reverse=True)
            for i, c in enumerate(scored):
                c.rank = i + 1
                c.score = RoutingScore(
                    quality_score=c.score.quality_score,
                    cost_score=c.score.cost_score,
                    latency_score=c.score.latency_score,
                    health_score=c.score.health_score,
                    reliability_score=c.score.reliability_score,
                    context_score=c.score.context_score,
                    preference_score=c.score.preference_score,
                    weighted_total=c.score.weighted_total,
                    candidate_count=len(scored),
                    rank=i + 1,
                )

            async with self._lock:
                self._total_candidates += len(scored)

            if not scored:
                self._routing_failures += 1
                decision = RoutingDecision(
                    request_id=request.request_id,
                    status="failed",
                    reason="All candidates scored zero",
                )
                await self._publish(
                    Topic.ROUTE_FAILED,
                    {
                        "request_id": request.request_id,
                        "reason": decision.reason,
                    },
                )
                return decision

            best = scored[0]
            fallback_chain = _FallbackEngine.generate(scored, chain_length=5)
            estimated_cost = best.model.input_cost_per_1k + best.model.output_cost_per_1k
            estimated_latency = max(best.provider.latency_ms, best.model.latency_ms)
            confidence = best.score.weighted_total

            decision = RoutingDecision(
                request_id=request.request_id,
                provider=best.provider.name,
                provider_id=best.provider.id,
                model=best.model.display_name or best.model.model_id,
                model_id=best.model.model_id,
                score=best.score,
                reason=f"Selected {best.provider.name}/{best.model.model_id} "
                f"(score={best.score.weighted_total:.3f})",
                fallback_chain=fallback_chain,
                estimated_cost=round(estimated_cost, 6),
                estimated_latency_ms=round(estimated_latency, 2),
                confidence=round(confidence, 4),
                policy_used="weighted",
                status="routed",
                alternatives_rejected=len(scored) - 1,
            )

        # Track provider/model selection
        async with self._lock:
            pn = best.provider.name
            self._provider_selection[pn] = self._provider_selection.get(pn, 0) + 1
            mn = best.model.model_id
            self._model_selection[mn] = self._model_selection.get(mn, 0) + 1

        duration = time.monotonic() - start
        async with self._lock:
            self._routing_duration_total += duration
            self._latency_histogram.record(duration * 1000)

        await self._publish(
            Topic.ROUTE_SELECTED,
            {
                "request_id": request.request_id,
                "provider": best.provider.name,
                "provider_id": best.provider.id,
                "model": best.model.model_id,
                "score": best.score.weighted_total,
                "estimated_cost": estimated_cost,
                "estimated_latency_ms": estimated_latency,
                "candidates_evaluated": len(scored),
                "fallback_count": len(fallback_chain),
            },
        )

        await self._publish(
            Topic.ROUTE_SCORING,
            {
                "request_id": request.request_id,
                "scoring_duration_ms": round(scoring_duration * 1000, 2),
                "candidates_scored": len(scored),
            },
        )

        return decision

    async def route_many(self, requests: list[RoutingRequest]) -> list[RoutingDecision]:
        """Route multiple requests sequentially and return decisions in order."""
        return [await self.route(r) for r in requests]

    async def best_model(self, request: RoutingRequest, top_k: int = 1) -> list[RoutingDecision]:
        """Return the top-k best models. Accepts streaming=False (no full scoring)."""
        decision = await self.route(request)
        if decision.status != "routed":
            return []
        return [decision]

    async def best_provider(self, request: RoutingRequest) -> RoutingDecision | None:
        """Return the single best provider (aggregates model scores per provider)."""
        providers, models = await self._query_registries(request)
        if not providers or not models:
            return None

        candidates = await self._filter_unhealthy_disabled(providers, models)
        if not candidates:
            return None

        candidates = await self._filter_capabilities(candidates, request)
        if not candidates:
            return None

        # Group by provider, pick highest scoring model per provider
        scorer = _ScoringEngine(request)
        provider_best: dict[str, _Candidate] = {}
        for c in candidates:
            score = scorer.score(c.provider, c.model)
            if (
                c.provider.id not in provider_best
                or score.weighted_total > provider_best[c.provider.id].weighted_total
            ):
                provider_best[c.provider.id] = _Candidate(
                    provider=c.provider,
                    model=c.model,
                    score=score,
                    weighted_total=score.weighted_total,
                )

        if not provider_best:
            return None

        # Pick highest scoring provider
        best = max(provider_best.values(), key=lambda c: c.weighted_total)
        return RoutingDecision(
            request_id=request.request_id,
            provider=best.provider.name,
            provider_id=best.provider.id,
            model=best.model.display_name or best.model.model_id,
            model_id=best.model.model_id,
            score=best.score,
            reason=f"Best provider: {best.provider.name} (score={best.score.weighted_total:.3f})",
            estimated_cost=best.model.input_cost_per_1k + best.model.output_cost_per_1k,
            estimated_latency_ms=max(best.provider.latency_ms, best.model.latency_ms),
            confidence=best.score.weighted_total,
            policy_used="weighted",
            status="routed",
        )

    async def rank_models(self, request: RoutingRequest, limit: int = 20) -> list[RoutingDecision]:
        """Return all viable candidates ranked by score."""
        decision = await self.route(request)
        if decision.status != "routed":
            return []

        # Re-run scoring on all candidates (route() only returns top-1)
        providers, models = await self._query_registries(request)
        candidates = await self._filter_unhealthy_disabled(providers, models)
        candidates = await self._filter_capabilities(candidates, request)
        if request.max_latency_ms > 0:
            candidates = await self._filter_latency(candidates, request)

        scorer = _ScoringEngine(request)
        scored: list[RoutingDecision] = []
        for c in candidates:
            score = scorer.score(c.provider, c.model)
            scored.append(
                RoutingDecision(
                    request_id=request.request_id,
                    provider=c.provider.name,
                    provider_id=c.provider.id,
                    model=c.model.display_name or c.model.model_id,
                    model_id=c.model.model_id,
                    score=score,
                    estimated_cost=c.model.input_cost_per_1k + c.model.output_cost_per_1k,
                    estimated_latency_ms=max(c.provider.latency_ms, c.model.latency_ms),
                    policy_used="weighted",
                    status="routed",
                )
            )

        scored.sort(key=lambda d: d.score.weighted_total, reverse=True)
        for i, d in enumerate(scored):
            d = RoutingDecision(
                request_id=d.request_id,
                provider=d.provider,
                provider_id=d.provider_id,
                model=d.model,
                model_id=d.model_id,
                score=RoutingScore(
                    quality_score=d.score.quality_score,
                    cost_score=d.score.cost_score,
                    latency_score=d.score.latency_score,
                    health_score=d.score.health_score,
                    reliability_score=d.score.reliability_score,
                    context_score=d.score.context_score,
                    preference_score=d.score.preference_score,
                    weighted_total=d.score.weighted_total,
                    candidate_count=len(scored),
                    rank=i + 1,
                ),
                estimated_cost=d.estimated_cost,
                estimated_latency_ms=d.estimated_latency_ms,
                policy_used="weighted",
                status="ranked",
            )
            scored[i] = d

        return scored[:limit]

    async def rank_providers(self, request: RoutingRequest) -> list[RoutingDecision]:
        """Return viable providers ranked by aggregate capability."""
        providers, models = await self._query_registries(request)
        if not providers:
            return []

        candidates = await self._filter_unhealthy_disabled(providers, models)
        if not candidates:
            return []

        candidates = await self._filter_capabilities(candidates, request)

        scorer = _ScoringEngine(request)
        provider_scores: dict[str, float] = {}
        provider_decisions: dict[str, RoutingDecision] = {}

        for c in candidates:
            score = scorer.score(c.provider, c.model)
            if (
                c.provider.id not in provider_scores
                or score.weighted_total > provider_scores[c.provider.id]
            ):
                provider_scores[c.provider.id] = score.weighted_total
                provider_decisions[c.provider.id] = RoutingDecision(
                    request_id=request.request_id,
                    provider=c.provider.name,
                    provider_id=c.provider.id,
                    model=c.model.display_name or c.model.model_id,
                    model_id=c.model.model_id,
                    score=score,
                    estimated_cost=c.model.input_cost_per_1k + c.model.output_cost_per_1k,
                    estimated_latency_ms=max(c.provider.latency_ms, c.model.latency_ms),
                    policy_used="weighted",
                    status="ranked",
                )

        ranked = sorted(
            provider_decisions.values(), key=lambda d: d.score.weighted_total, reverse=True
        )
        return ranked

    async def generate_fallback_chain(
        self, request: RoutingRequest, chain_length: int = 5
    ) -> tuple[tuple[str, str, str], ...]:
        """Generate an ordered fallback chain without needing a full route."""
        providers, models = await self._query_registries(request)
        if not providers or not models:
            return ()

        candidates = await self._filter_unhealthy_disabled(providers, models)
        candidates = await self._filter_capabilities(candidates, request)
        if request.max_latency_ms > 0:
            candidates = await self._filter_latency(candidates, request)

        scorer = _ScoringEngine(request)
        scored: list[_Candidate] = []
        for c in candidates:
            score = scorer.score(c.provider, c.model)
            scored.append(
                _Candidate(
                    provider=c.provider,
                    model=c.model,
                    score=score,
                    weighted_total=score.weighted_total,
                )
            )

        scored.sort(key=lambda c: c.weighted_total, reverse=True)
        return _FallbackEngine.generate(scored, chain_length)

    async def validate_request(self, request: RoutingRequest) -> list[str]:
        """Validate a RoutingRequest. Returns list of error messages (empty = valid)."""
        errors: list[str] = []
        if not request.task_type:
            errors.append("task_type is required")
        if request.cost_weight < 0:
            errors.append("cost_weight must be >= 0")
        if request.quality_weight < 0:
            errors.append("quality_weight must be >= 0")
        if request.latency_weight < 0:
            errors.append("latency_weight must be >= 0")
        if request.budget_limit < 0:
            errors.append("budget_limit must be >= 0")
        if request.max_latency_ms < 0:
            errors.append("max_latency_ms must be >= 0")
        return errors

    async def estimate_cost(self, request: RoutingRequest) -> float:
        """Estimate the max possible cost for this request (most expensive combo)."""
        providers, models = await self._query_registries(request)
        if not providers or not models:
            return 0.0
        max_cost = 0.0
        for p in providers:
            for m in models:
                cost = (
                    p.cost_per_1k_input
                    + p.cost_per_1k_output
                    + m.input_cost_per_1k
                    + m.output_cost_per_1k
                )
                if cost > max_cost:
                    max_cost = cost
        return round(max_cost, 6)

    async def estimate_latency(self, request: RoutingRequest) -> float:
        """Estimate the best possible latency (fastest combo)."""
        providers, models = await self._query_registries(request)
        if not providers or not models:
            return 0.0
        min_latency = float("inf")
        for p in providers:
            for m in models:
                lat = max(p.latency_ms, m.latency_ms)
                if lat < min_latency and lat > 0:
                    min_latency = lat
        return round(min_latency if min_latency < float("inf") else 0.0, 2)

    async def score_candidate(
        self,
        provider: OmniRouteProvider,
        model: OmniRouteModel,
        request: RoutingRequest,
    ) -> RoutingScore:
        """Score a single provider+model candidate."""
        scorer = _ScoringEngine(request)
        return scorer.score(provider, model)

    async def supported_capabilities(self) -> list[str]:
        """Return all capabilities the router can handle."""
        return [
            "chat",
            "completion",
            "vision",
            "reasoning",
            "coding",
            "embedding",
            "moderation",
            "image-generation",
            "audio",
            "function-calling",
            "tools",
            "streaming",
        ]

    # ── Internal Pipeline Steps ──

    async def _query_registries(
        self, request: RoutingRequest
    ) -> tuple[list[OmniRouteProvider], list[OmniRouteModel]]:
        """Query ProviderRegistry and ModelRegistry for available resources."""
        providers: list[OmniRouteProvider] = []
        models: list[OmniRouteModel] = []

        if self._provider_registry is not None:
            provider_list = await self._provider_registry.list_providers(
                kind=request.task_type
                if request.task_type in ("openai", "anthropic", "ollama")
                else None,
            )
            providers.extend(provider_list)

        if self._model_registry is not None:
            model_list = await self._model_registry.list_models(enabled_only=True)
            models.extend(model_list)

        # If preferred provider specified, try to find it
        if request.preferred_provider and self._provider_registry is not None:
            pref = await self._provider_registry.get_by_name(request.preferred_provider)
            if pref is not None and pref not in providers:
                providers.append(pref)

        return providers, models

    async def _filter_unhealthy_disabled(
        self,
        providers: list[OmniRouteProvider],
        models: list[OmniRouteModel],
    ) -> list[_Candidate]:
        """Remove unhealthy providers, disabled providers, and disabled models."""
        valid_providers = [p for p in providers if p.enabled and p.healthy]
        valid_models = [m for m in models if m.enabled]

        candidates: list[_Candidate] = []
        provider_map: dict[str, OmniRouteProvider] = {p.id: p for p in valid_providers}

        for m in valid_models:
            provider = provider_map.get(m.provider_id)
            if provider is None:
                # Try to find by name
                for p in valid_providers:
                    if p.name == m.provider:
                        provider = p
                        break
            if provider is not None:
                candidates.append(_Candidate(provider=provider, model=m))

        return candidates

    async def _filter_circuit_breaker(
        self,
        candidates: list[_Candidate],
    ) -> list[_Candidate]:
        """Remove candidates whose provider has an OPEN circuit breaker.

        Providers in CLOSED state are allowed. Providers in HALF_OPEN are
        allowed only for probe traffic (limited by circuit breaker config).
        Providers in OPEN state are filtered out entirely.
        """
        filtered: list[_Candidate] = []
        cb = self._circuit_breaker
        if cb is None:
            return candidates
        for c in candidates:
            try:
                allowed = await cb.allow_request(c.provider.name)
                if allowed:
                    filtered.append(c)
            except Exception:
                log.warning("Circuit breaker check failed for %s, allowing", c.provider.name)
                filtered.append(c)
        return filtered

    async def _filter_capabilities(
        self,
        candidates: list[_Candidate],
        request: RoutingRequest,
    ) -> list[_Candidate]:
        """Filter candidates by required capabilities and feature flags."""
        result = list(candidates)

        if request.required_capabilities:
            cap_set = {c.lower() for c in request.required_capabilities}
            filtered: list[_Candidate] = []
            for c in candidates:
                model_caps = {cap.lower() for cap in c.model.capabilities}
                if cap_set.intersection(model_caps) or not cap_set:
                    filtered.append(c)
            result = filtered

        if request.streaming_required:
            result = [c for c in result if c.model.supports_streaming]
        if request.vision_required:
            result = [c for c in result if c.model.supports_vision]
        if request.reasoning_required:
            result = [c for c in result if c.model.supports_reasoning]
        if request.tools_required:
            result = [c for c in result if c.model.supports_tools]

        return result

    async def _filter_context(
        self,
        candidates: list[_Candidate],
        request: RoutingRequest,
    ) -> list[_Candidate]:
        """Filter candidates by minimum context window."""
        if request.minimum_context <= 0:
            return candidates
        return [c for c in candidates if c.model.context_window >= request.minimum_context]

    async def _filter_budget(
        self,
        candidates: list[_Candidate],
        request: RoutingRequest,
    ) -> list[_Candidate]:
        """Filter candidates by budget limit (combined provider+model cost per 1k)."""
        if request.budget_limit <= 0:
            return candidates
        return [
            c
            for c in candidates
            if (c.model.input_cost_per_1k + c.model.output_cost_per_1k) <= request.budget_limit
        ]

    async def _filter_latency(
        self,
        candidates: list[_Candidate],
        request: RoutingRequest,
    ) -> list[_Candidate]:
        """Filter candidates by max allowed latency."""
        if request.max_latency_ms <= 0:
            return candidates
        return [
            c
            for c in candidates
            if max(c.provider.latency_ms, c.model.latency_ms) <= request.max_latency_ms
        ]

    # ── Metrics ──

    def metrics(self) -> dict[str, Any]:
        """Return observability metrics snapshot."""
        p50 = self._latency_histogram.percentile(50)
        p95 = self._latency_histogram.percentile(95)
        p99 = self._latency_histogram.percentile(99)
        return {
            "routing_count": self._routing_count,
            "routing_failures": self._routing_failures,
            "failure_rate": round(self._routing_failures / max(self._routing_count, 1), 4),
            "avg_routing_latency_ms": round(
                (self._routing_duration_total / max(self._routing_count, 1)) * 1000, 2
            ),
            "p50_routing_latency_ms": round(p50, 2),
            "p95_routing_latency_ms": round(p95, 2),
            "p99_routing_latency_ms": round(p99, 2),
            "avg_candidate_count": round(self._total_candidates / max(self._routing_count, 1), 1),
            "avg_scoring_time_ms": round(
                (self._total_scoring_time / max(self._routing_count, 1)) * 1000, 2
            ),
            "provider_selection_frequency": dict(
                sorted(self._provider_selection.items(), key=lambda x: -x[1])
            ),
            "model_selection_frequency": dict(
                sorted(self._model_selection.items(), key=lambda x: -x[1])
            ),
        }

    # ── Internal helpers ──

    async def _publish(self, topic: Topic, payload: dict[str, Any]) -> None:
        if self._event_bus is None:
            return
        try:
            envelope = EventEnvelope(
                type=topic.value,
                source="omniroute.router",
                topic=topic.value,
                payload=payload,
            )
            await self._event_bus.publish(envelope)
        except Exception:
            log.warning("Failed to publish event %s", topic.value, exc_info=True)


__all__ = [
    "RouterEnginePort",
    "RouterEngineImpl",
]
