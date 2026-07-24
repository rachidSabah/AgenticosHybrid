"""OmniRoute Budget Engine — financial decision layer for provider/model selection.

The Budget Engine determines whether a provider/model may be selected
according to configurable spending policies. It executes in the routing
pipeline immediately after the Model Registry, BEFORE the Circuit Breaker.

Responsibilities:
  - enforce request/workspace/user/organization budget
  - daily/monthly/per-provider/per-model spending limits
  - cost prediction (input, output, reasoning, vision, tool tokens)
  - budget reservations (reserve → commit → rollback lifecycle)
  - soft/hard limits with warning thresholds
  - emergency mode
  - audit trail
  - metrics and observability
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4

from agentic_os.domain.events import EventEnvelope, Topic
from agentic_os.domain.omniroute import (
    BudgetAuditRecord,
    BudgetDecision,
    BudgetForecast,
    BudgetOverride,
    BudgetPolicy,
    BudgetReservation,
    BudgetResult,
    BudgetScope,
    BudgetSnapshot,
    BudgetStatistics,
    BudgetUsage,
    OmniRouteModel,
    OmniRouteProvider,
    RoutingRequest,
)
from agentic_os.infrastructure.logging import get_logger

log = get_logger("omniroute.budget_engine")


# ── Port Protocol ──


@runtime_checkable
class BudgetEnginePort(Protocol):
    """OmniRoute Budget Engine — financial decision layer."""

    # Lifecycle
    async def initialize(self) -> None: ...
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def dispose(self) -> None: ...

    # Policy CRUD
    async def create_policy(self, policy: BudgetPolicy) -> BudgetPolicy: ...
    async def update_policy(self, policy_id: str, policy: BudgetPolicy) -> BudgetPolicy | None: ...
    async def delete_policy(self, policy_id: str) -> bool: ...
    async def get_policy(self, policy_id: str) -> BudgetPolicy | None: ...
    async def list_policies(
        self, scope: BudgetScope | None = None, scope_id: str | None = None
    ) -> list[BudgetPolicy]: ...

    # Evaluation
    async def evaluate(
        self,
        candidates: list[tuple[OmniRouteProvider, OmniRouteModel]],
        request: RoutingRequest,
    ) -> BudgetDecision: ...

    # Reservation lifecycle
    async def reserve(
        self,
        provider: str,
        model: str,
        estimated_cost: float,
        max_cost: float,
        scope: BudgetScope = BudgetScope.GLOBAL,
        scope_id: str = "",
    ) -> BudgetReservation | None: ...
    async def commit(self, reservation_id: str) -> bool: ...
    async def rollback(self, reservation_id: str) -> bool: ...
    async def release(self, reservation_id: str) -> bool: ...

    # Observability
    async def statistics(self) -> BudgetStatistics: ...
    async def snapshot(self) -> BudgetSnapshot: ...
    async def forecast(self) -> BudgetForecast: ...
    async def metrics(self) -> dict[str, Any]: ...
    async def usage(self, policy_id: str) -> BudgetUsage | None: ...

    # Overrides
    async def apply_override(self, override: BudgetOverride) -> bool: ...
    async def remove_override(self, override_id: str) -> bool: ...

    # Emergency
    async def emergency_mode(self, active: bool) -> None: ...

    # Audit
    async def audit_log(self, limit: int = 100, offset: int = 0) -> list[BudgetAuditRecord]: ...


# ── Cost Prediction ──


@dataclass
class _CostEstimate:
    """Estimated cost for a provider+model handling a request."""

    estimated_cost: float = 0.0
    max_cost: float = 0.0
    expected_cost: float = 0.0
    input_cost: float = 0.0
    output_cost: float = 0.0
    reasoning_cost: float = 0.0
    vision_cost: float = 0.0
    tool_cost: float = 0.0
    cache_savings: float = 0.0
    streaming_discount: float = 0.0


class _CostPredictor:
    """Predicts cost of handling a request with a given provider+model."""

    # Default token estimates when not specified by the request
    DEFAULT_INPUT_TOKENS = 500
    DEFAULT_OUTPUT_TOKENS = 200
    REASONING_MULTIPLIER = 1.5  # reasoning models typically use more output tokens
    VISION_IMAGE_TOKENS = 258  # ~258 tokens per 512x512 image
    TOOL_CALL_OVERHEAD = 100  # extra tokens per tool call
    STREAMING_DISCOUNT_FACTOR = 0.85  # streaming can reduce perceived cost
    CACHE_HIT_RATIO = 0.3  # estimated cache hit ratio
    CACHE_DISCOUNT = 0.5  # cache hits are 50% cheaper

    def estimate(
        self,
        provider: OmniRouteProvider,
        model: OmniRouteModel,
        request: RoutingRequest,
    ) -> _CostEstimate:
        input_tokens = self._estimate_input_tokens(request)
        output_tokens = self._estimate_output_tokens(request)
        reasoning_tokens = self._estimate_reasoning_tokens(request)
        vision_tokens = self._estimate_vision_tokens(request)
        tool_tokens = self._estimate_tool_tokens(request)

        # Base costs
        input_cost = (input_tokens / 1000) * model.input_cost_per_1k
        output_cost = (output_tokens / 1000) * model.output_cost_per_1k
        reasoning_cost = (reasoning_tokens / 1000) * model.output_cost_per_1k
        vision_cost = (vision_tokens / 1000) * model.input_cost_per_1k
        tool_cost = (tool_tokens / 1000) * model.input_cost_per_1k

        # Cache savings
        cache_input = input_tokens * self.CACHE_HIT_RATIO
        cache_savings = (cache_input / 1000) * model.input_cost_per_1k * self.CACHE_DISCOUNT

        # Streaming discount
        streaming_discount = 0.0
        if request.streaming_required and model.supports_streaming:
            streaming_discount = (output_cost + reasoning_cost) * (
                1 - self.STREAMING_DISCOUNT_FACTOR
            )

        total_estimated = input_cost + output_cost + reasoning_cost + vision_cost + tool_cost
        total_estimated -= cache_savings + streaming_discount

        # Max cost (no caching, no streaming discount)
        max_cost = input_cost + output_cost + reasoning_cost + vision_cost + tool_cost

        # Expected cost (middle estimate)
        expected_cost = total_estimated

        return _CostEstimate(
            estimated_cost=max(0.0, total_estimated),
            max_cost=max_cost,
            expected_cost=max(0.0, expected_cost),
            input_cost=input_cost,
            output_cost=output_cost,
            reasoning_cost=reasoning_cost,
            vision_cost=vision_cost,
            tool_cost=tool_cost,
            cache_savings=cache_savings,
            streaming_discount=streaming_discount,
        )

    def _estimate_input_tokens(self, request: RoutingRequest) -> int:
        return max(
            getattr(request, "estimated_input_tokens", 0),
            self.DEFAULT_INPUT_TOKENS,
        )

    def _estimate_output_tokens(self, request: RoutingRequest) -> int:
        return max(
            getattr(request, "estimated_output_tokens", 0),
            self.DEFAULT_OUTPUT_TOKENS,
        )

    def _estimate_reasoning_tokens(self, request: RoutingRequest) -> int:
        if request.reasoning_required:
            output = self._estimate_output_tokens(request)
            return int(output * (self.REASONING_MULTIPLIER - 1))
        return 0

    def _estimate_vision_tokens(self, request: RoutingRequest) -> int:
        if request.vision_required:
            image_count = getattr(request, "estimated_images", 1)
            return max(image_count, 1) * self.VISION_IMAGE_TOKENS
        return 0

    def _estimate_tool_tokens(self, request: RoutingRequest) -> int:
        if request.tools_required:
            tool_count = getattr(request, "estimated_tool_calls", 2)
            return max(tool_count, 1) * self.TOOL_CALL_OVERHEAD
        return 0


# ── Usage Tracker ──


class _UsageTracker:
    """Tracks accumulated spend against budget policies."""

    def __init__(self) -> None:
        self._usage: dict[str, BudgetUsage] = {}
        self._spend_log: list[tuple[str, float, datetime]] = []  # (policy_id, amount, time)

    def get_usage(self, policy_id: str) -> BudgetUsage:
        return self._usage.get(policy_id, BudgetUsage(policy_id=policy_id))

    def record_spend(
        self,
        policy_id: str,
        amount: float,
        provider: str = "",
        model: str = "",
    ) -> BudgetUsage:
        existing = self._usage.get(policy_id)
        today = date.today()

        if existing:
            # Frozen dataclass — rebuild
            daily = existing.daily_spent
            monthly = existing.monthly_spent
            daily_count = existing.daily_request_count
            monthly_count = existing.monthly_request_count

            # Reset daily if not today
            if existing.last_updated.date() < today:
                daily = 0.0
                daily_count = 0
            # Reset monthly if different month
            if (
                existing.last_updated.month != today.month
                or existing.last_updated.year != today.year
            ):
                monthly = 0.0
                monthly_count = 0

            provider_spend = dict(existing.provider_spend)
            model_spend = dict(existing.model_spend)
            if provider:
                provider_spend[provider] = provider_spend.get(provider, 0.0) + amount
            if model:
                model_spend[model] = model_spend.get(model, 0.0) + amount

            updated = BudgetUsage(
                policy_id=existing.policy_id,
                scope=existing.scope,
                scope_id=existing.scope_id,
                total_spent=existing.total_spent + amount,
                daily_spent=daily + amount,
                monthly_spent=monthly + amount,
                request_count=existing.request_count + 1,
                daily_request_count=daily_count + 1,
                monthly_request_count=monthly_count + 1,
                provider_spend=provider_spend,
                model_spend=model_spend,
                active_reservations=existing.active_reservations,
                last_updated=datetime.now(UTC),
            )
        else:
            provider_spend: dict[str, float] = {}
            model_spend: dict[str, float] = {}
            if provider:
                provider_spend[provider] = amount
            if model:
                model_spend[model] = amount

            updated = BudgetUsage(
                policy_id=policy_id,
                total_spent=amount,
                daily_spent=amount,
                monthly_spent=amount,
                request_count=1,
                daily_request_count=1,
                monthly_request_count=1,
                provider_spend=provider_spend,
                model_spend=model_spend,
                last_updated=datetime.now(UTC),
            )

        self._usage[policy_id] = updated
        self._spend_log.append((policy_id, amount, datetime.now(UTC)))
        return updated

    def add_reservation(self, policy_id: str, amount: float) -> None:
        usage = self.get_usage(policy_id)
        self._usage[policy_id] = BudgetUsage(
            policy_id=usage.policy_id,
            scope=usage.scope,
            scope_id=usage.scope_id,
            total_spent=usage.total_spent,
            daily_spent=usage.daily_spent,
            monthly_spent=usage.monthly_spent,
            request_count=usage.request_count,
            daily_request_count=usage.daily_request_count,
            monthly_request_count=usage.monthly_request_count,
            provider_spend=usage.provider_spend,
            model_spend=usage.model_spend,
            active_reservations=usage.active_reservations + amount,
            last_updated=usage.last_updated,
        )

    def remove_reservation(self, policy_id: str, amount: float) -> None:
        usage = self.get_usage(policy_id)
        if usage.active_reservations > 0:
            self._usage[policy_id] = BudgetUsage(
                policy_id=usage.policy_id,
                scope=usage.scope,
                scope_id=usage.scope_id,
                total_spent=usage.total_spent,
                daily_spent=usage.daily_spent,
                monthly_spent=usage.monthly_spent,
                request_count=usage.request_count,
                daily_request_count=usage.daily_request_count,
                monthly_request_count=usage.monthly_request_count,
                provider_spend=usage.provider_spend,
                model_spend=usage.model_spend,
                active_reservations=usage.active_reservations - amount,
                last_updated=usage.last_updated,
            )

    def all_usage(self) -> list[BudgetUsage]:
        return list(self._usage.values())

    def clear(self) -> None:
        self._usage.clear()
        self._spend_log.clear()


# ── Budget Engine Implementation ──


class BudgetEngineImpl:
    """Production Budget Engine — financial decision layer for OmniRoute.

    Evaluates candidate provider+model pairs against configurable budget policies.
    Supports nested scopes (global → org → workspace → user → session → request),
    reservation lifecycle, cost prediction, emergency mode, and audit logging.
    Thread-safe via asyncio.Lock.
    """

    RESERVATION_TTL_SECONDS = 30.0  # reservations expire after 30s if not committed

    def __init__(
        self,
        event_bus: Any | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._lock = asyncio.Lock()
        self._started = False

        # Policies
        self._policies: dict[str, BudgetPolicy] = {}
        self._policies_by_scope: dict[str, list[str]] = defaultdict(list)

        # Reservations
        self._reservations: dict[str, BudgetReservation] = {}
        self._next_reservation_cleanup: float = 0.0

        # Overrides
        self._overrides: dict[str, BudgetOverride] = {}

        # Audit log
        self._audit_log: list[BudgetAuditRecord] = []
        self._max_audit_entries = 10000

        # Usage tracking
        self._usage_tracker = _UsageTracker()

        # Cost prediction
        self._predictor = _CostPredictor()

        # Emergency mode
        self._emergency_mode = False

        # Statistics
        self._stats = BudgetStatistics()

        # Observability
        self._start_time: float = 0.0

    # ── Lifecycle ──

    async def initialize(self) -> None:
        log.info("BudgetEngine initializing")

    async def start(self) -> None:
        self._started = True
        self._start_time = time.monotonic()
        log.info("BudgetEngine started")

    async def stop(self) -> None:
        self._started = False
        log.info("BudgetEngine stopped")

    async def dispose(self) -> None:
        await self.stop()
        async with self._lock:
            self._policies.clear()
            self._policies_by_scope.clear()
            self._reservations.clear()
            self._overrides.clear()
            self._audit_log.clear()
            self._usage_tracker.clear()
            self._stats = BudgetStatistics()
        log.info("BudgetEngine disposed")

    # ── Policy CRUD ──

    async def create_policy(self, policy: BudgetPolicy) -> BudgetPolicy:
        async with self._lock:
            self._policies[policy.id] = policy
            scope_key = f"{policy.scope.value}:{policy.scope_id}"
            self._policies_by_scope[scope_key].append(policy.id)
            # Sort by priority descending
            self._policies_by_scope[scope_key].sort(
                key=lambda pid: self._policies[pid].priority,
                reverse=True,
            )
        await self._publish(Topic.BUDGET_POLICY_CREATED, {"policy_id": policy.id})
        return policy

    async def update_policy(self, policy_id: str, policy: BudgetPolicy) -> BudgetPolicy | None:
        async with self._lock:
            if policy_id not in self._policies:
                return None
            self._policies[policy_id] = policy
        await self._publish(Topic.BUDGET_POLICY_UPDATED, {"policy_id": policy_id})
        return policy

    async def delete_policy(self, policy_id: str) -> bool:
        async with self._lock:
            if policy_id not in self._policies:
                return False
            policy = self._policies.pop(policy_id)
            scope_key = f"{policy.scope.value}:{policy.scope_id}"
            if policy_id in self._policies_by_scope[scope_key]:
                self._policies_by_scope[scope_key].remove(policy_id)
                if not self._policies_by_scope[scope_key]:
                    del self._policies_by_scope[scope_key]
        await self._publish(Topic.BUDGET_POLICY_DELETED, {"policy_id": policy_id})
        return True

    async def get_policy(self, policy_id: str) -> BudgetPolicy | None:
        async with self._lock:
            return self._policies.get(policy_id)

    async def list_policies(
        self, scope: BudgetScope | None = None, scope_id: str | None = None
    ) -> list[BudgetPolicy]:
        async with self._lock:
            if scope is not None:
                scope_key = f"{scope.value}:{scope_id or ''}"
                return [
                    self._policies[pid]
                    for pid in self._policies_by_scope.get(scope_key, [])
                    if pid in self._policies
                ]
            return list(self._policies.values())

    # ── Evaluation ──

    async def evaluate(
        self,
        candidates: list[tuple[OmniRouteProvider, OmniRouteModel]],
        request: RoutingRequest,
    ) -> BudgetDecision:
        """Evaluate all candidates against applicable budget policies.

        Returns a BudgetDecision with:
        - filtered_candidates (those that pass budget checks)
        - reservations for each approved candidate
        - detailed results per candidate
        """
        eval_start = time.monotonic()
        async with self._lock:
            self._cleanup_expired_reservations_locked()

            if self._emergency_mode:
                self._stats = BudgetStatistics(
                    total_evaluations=self._stats.total_evaluations + 1,
                    rejections=self._stats.rejections + 1,
                    approvals=self._stats.approvals,
                    reservation_count=self._stats.reservation_count,
                    active_reservations=len(self._reservations),
                    commits=self._stats.commits,
                    rollbacks=self._stats.rollbacks,
                    average_evaluation_time_ms=self._stats.average_evaluation_time_ms,
                    cost_saved=self._stats.cost_saved,
                    provider_spend=self._stats.provider_spend,
                    model_spend=self._stats.model_spend,
                    workspace_spend=self._stats.workspace_spend,
                    user_spend=self._stats.user_spend,
                    organization_spend=self._stats.organization_spend,
                    limit_hits=self._stats.limit_hits,
                    warnings_issued=self._stats.warnings_issued,
                )
                return BudgetDecision(
                    approved=False,
                    rejected=True,
                    reason="Emergency mode: all spending blocked",
                    evaluation_time_ms=(time.monotonic() - eval_start) * 1000,
                    emergency_mode=True,
                )

            # Gather applicable policies
            applicable_policies = self._resolve_applicable_policies(request)

            results: list[BudgetResult] = []
            reservations: list[str] = []
            filtered: list[str] = []

            for provider, model in candidates:
                result = self._evaluate_candidate(provider, model, request, applicable_policies)
                results.append(result)
                if result.approved:
                    reservations.append(result.reservation_id)
                else:
                    filtered.append(f"{provider.name}/{model.model_id}")

            approved_count = sum(1 for r in results if r.approved)
            rejected_count = sum(1 for r in results if r.rejected)
            eval_time_ms = (time.monotonic() - eval_start) * 1000

            # Update stats
            total_eval = self._stats.total_evaluations + 1
            avg_time = (
                (
                    self._stats.average_evaluation_time_ms * self._stats.total_evaluations
                    + eval_time_ms
                )
                / total_eval
                if total_eval > 0
                else eval_time_ms
            )

            self._stats = BudgetStatistics(
                total_evaluations=total_eval,
                approvals=self._stats.approvals + approved_count,
                rejections=self._stats.rejections + rejected_count,
                reservation_count=self._stats.reservation_count + len(reservations),
                active_reservations=len(self._reservations),
                commits=self._stats.commits,
                rollbacks=self._stats.rollbacks,
                average_evaluation_time_ms=avg_time,
                cost_saved=self._stats.cost_saved,
                provider_spend=self._stats.provider_spend,
                model_spend=self._stats.model_spend,
                workspace_spend=self._stats.workspace_spend,
                user_spend=self._stats.user_spend,
                organization_spend=self._stats.organization_spend,
                limit_hits=self._stats.limit_hits,
                warnings_issued=self._stats.warnings_issued,
            )

            has_approved = any(r.approved for r in results)

            decision = BudgetDecision(
                approved=has_approved,
                rejected=not has_approved,
                reason="" if has_approved else "All candidates exceed budget limits",
                filtered_candidates=tuple(filtered),
                results=tuple(results),
                reservations=tuple(reservations),
                evaluation_time_ms=eval_time_ms,
                emergency_mode=False,
            )

        if has_approved:
            await self._publish(
                Topic.BUDGET_APPROVED,
                {
                    "request_id": request.request_id,
                    "approved_count": approved_count,
                    "total_candidates": len(candidates),
                },
            )
        else:
            await self._publish(
                Topic.BUDGET_REJECTED,
                {
                    "request_id": request.request_id,
                    "reason": "All candidates exceed budget limits",
                },
            )

        self._add_audit("evaluate", "", request_id=request.request_id)
        return decision

    def _resolve_applicable_policies(self, request: RoutingRequest) -> list[BudgetPolicy]:
        """Collect policies from all applicable scopes in order of precedence.

        Lower scopes override higher scopes.
        Order: GLOBAL → ORGANIZATION → WORKSPACE → AGENT → USER → SESSION → REQUEST
        """
        collected: dict[str, BudgetPolicy] = {}
        scope_keys = [
            f"{BudgetScope.GLOBAL.value}:",
            f"{BudgetScope.ORGANIZATION.value}:{request.organization}",
            f"{BudgetScope.WORKSPACE.value}:{request.workspace}",
            f"{BudgetScope.USER.value}:{request.user_id}",
            f"{BudgetScope.AGENT.value}:{request.agent}",
            f"{BudgetScope.SESSION.value}:{request.mission_id}",
        ]

        for key in scope_keys:
            if key in self._policies_by_scope:
                for pid in self._policies_by_scope[key]:
                    policy = self._policies.get(pid)
                    if policy and policy.enabled:
                        collected[pid] = policy

        return list(collected.values())

    def _evaluate_candidate(
        self,
        provider: OmniRouteProvider,
        model: OmniRouteModel,
        request: RoutingRequest,
        policies: list[BudgetPolicy],
    ) -> BudgetResult:
        """Evaluate a single candidate against applicable policies."""
        estimate = self._predictor.estimate(provider, model, request)
        estimated_cost = estimate.estimated_cost
        max_cost = estimate.max_cost

        warnings: list[str] = []
        overrides: list[str] = []

        # Check request-level budget limit first
        if request.budget_limit > 0 and estimated_cost > request.budget_limit:
            return BudgetResult(
                approved=False,
                rejected=True,
                reason=(
                    f"Estimated cost {estimated_cost:.4f} exceeds "
                    f"request budget limit {request.budget_limit:.4f}"
                ),
                estimated_cost=estimated_cost,
                max_cost=max_cost,
            )

        # Check all applicable policies
        effective_policy_id = ""
        effective_scope = BudgetScope.GLOBAL
        remaining = float("inf")

        for policy in policies:
            # Apply overrides
            limit_total = policy.max_spend_total
            limit_daily = policy.max_spend_daily
            limit_monthly = policy.max_spend_monthly
            limit_per_request = policy.max_spend_per_request
            hard_limit = policy.hard_limit
            soft_limit = policy.soft_limit

            override = self._find_active_override(policy.id)
            if override:
                overrides.append(policy.id)
                if "max_spend_total" in override.overridden_limits:
                    limit_total = override.overridden_limits["max_spend_total"]
                if "max_spend_daily" in override.overridden_limits:
                    limit_daily = override.overridden_limits["max_spend_daily"]
                if "hard_limit" in override.overridden_limits:
                    hard_limit = override.overridden_limits["hard_limit"]

            # Check hard limit
            if hard_limit > 0 and estimated_cost > hard_limit:
                return BudgetResult(
                    approved=False,
                    rejected=True,
                    reason=(
                        f"Estimated cost {estimated_cost:.4f} exceeds "
                        f"hard limit {hard_limit:.4f} (policy {policy.id})"
                    ),
                    estimated_cost=estimated_cost,
                    max_cost=max_cost,
                )

            # Check per-request limit
            if limit_per_request > 0 and estimated_cost > limit_per_request:
                return BudgetResult(
                    approved=False,
                    rejected=True,
                    reason=(
                        f"Estimated cost {estimated_cost:.4f} exceeds "
                        f"per-request limit {limit_per_request:.4f}"
                    ),
                    estimated_cost=estimated_cost,
                    max_cost=max_cost,
                )

            # Get current usage for this policy
            usage = self._usage_tracker.get_usage(policy.id)

            # Check total limit
            if limit_total > 0 and usage.total_spent + estimated_cost > limit_total:
                self._stats = BudgetStatistics(
                    total_evaluations=self._stats.total_evaluations,
                    approvals=self._stats.approvals,
                    rejections=self._stats.rejections,
                    reservation_count=self._stats.reservation_count,
                    active_reservations=self._stats.active_reservations,
                    commits=self._stats.commits,
                    rollbacks=self._stats.rollbacks,
                    average_evaluation_time_ms=self._stats.average_evaluation_time_ms,
                    cost_saved=self._stats.cost_saved,
                    provider_spend=self._stats.provider_spend,
                    model_spend=self._stats.model_spend,
                    workspace_spend=self._stats.workspace_spend,
                    user_spend=self._stats.user_spend,
                    organization_spend=self._stats.organization_spend,
                    limit_hits={
                        **self._stats.limit_hits,
                        policy.scope.value: self._stats.limit_hits.get(policy.scope.value, 0) + 1,
                    },
                    warnings_issued=self._stats.warnings_issued,
                )
                self._publish_blocking(
                    Topic.BUDGET_LIMIT_REACHED,
                    {
                        "policy_id": policy.id,
                        "scope": policy.scope.value,
                        "total_spent": usage.total_spent,
                        "limit": limit_total,
                        "estimated_cost": estimated_cost,
                    },
                )
                return BudgetResult(
                    approved=False,
                    rejected=True,
                    reason=(
                        f"Total budget limit {limit_total:.4f} exceeded "
                        f"(spent: {usage.total_spent:.4f}, "
                        f"estimated: {estimated_cost:.4f})"
                    ),
                    estimated_cost=estimated_cost,
                    max_cost=max_cost,
                )

            # Check daily limit
            if limit_daily > 0 and usage.daily_spent + estimated_cost > limit_daily:
                self._record_limit_hit(policy.scope.value)
                self._publish_blocking(
                    Topic.BUDGET_LIMIT_REACHED,
                    {
                        "policy_id": policy.id,
                        "scope": policy.scope.value,
                        "daily_spent": usage.daily_spent,
                        "daily_limit": limit_daily,
                    },
                )
                return BudgetResult(
                    approved=False,
                    rejected=True,
                    reason=(
                        f"Daily budget limit {limit_daily:.4f} exceeded "
                        f"(daily spent: {usage.daily_spent:.4f})"
                    ),
                    estimated_cost=estimated_cost,
                    max_cost=max_cost,
                )

            # Check monthly limit
            if limit_monthly > 0 and usage.monthly_spent + estimated_cost > limit_monthly:
                self._record_limit_hit(policy.scope.value)
                self._publish_blocking(
                    Topic.BUDGET_LIMIT_REACHED,
                    {
                        "policy_id": policy.id,
                        "scope": policy.scope.value,
                        "monthly_spent": usage.monthly_spent,
                        "monthly_limit": limit_monthly,
                    },
                )
                return BudgetResult(
                    approved=False,
                    rejected=True,
                    reason=(
                        f"Monthly budget limit {limit_monthly:.4f} exceeded "
                        f"(monthly spent: {usage.monthly_spent:.4f})"
                    ),
                    estimated_cost=estimated_cost,
                    max_cost=max_cost,
                )

            # Check soft limit — warning only
            if soft_limit > 0:
                effective_limit = hard_limit if hard_limit > 0 else limit_total
                if effective_limit > 0:
                    ratio = (usage.total_spent + estimated_cost) / effective_limit
                    if ratio >= policy.warning_threshold:
                        warnings.append(
                            f"Approaching limit on {policy.scope.value} policy: {ratio:.0%} used"
                        )
                        self._stats = BudgetStatistics(
                            total_evaluations=self._stats.total_evaluations,
                            approvals=self._stats.approvals,
                            rejections=self._stats.rejections,
                            reservation_count=self._stats.reservation_count,
                            active_reservations=self._stats.active_reservations,
                            commits=self._stats.commits,
                            rollbacks=self._stats.rollbacks,
                            average_evaluation_time_ms=self._stats.average_evaluation_time_ms,
                            cost_saved=self._stats.cost_saved,
                            provider_spend=self._stats.provider_spend,
                            model_spend=self._stats.model_spend,
                            workspace_spend=self._stats.workspace_spend,
                            user_spend=self._stats.user_spend,
                            organization_spend=self._stats.organization_spend,
                            limit_hits=self._stats.limit_hits,
                            warnings_issued=self._stats.warnings_issued + 1,
                        )
                        self._publish_blocking(
                            Topic.BUDGET_WARNING,
                            {
                                "policy_id": policy.id,
                                "scope": policy.scope.value,
                                "usage_ratio": ratio,
                                "warning_threshold": policy.warning_threshold,
                            },
                        )

            # Track remaining budget
            if limit_total > 0:
                policy_remaining = limit_total - usage.total_spent - usage.active_reservations
                remaining = min(remaining, policy_remaining)

            effective_policy_id = policy.id
            effective_scope = policy.scope

        # Create reservation
        reservation_id = uuid4().hex[:16]
        reservation = BudgetReservation(
            id=reservation_id,
            policy_id=effective_policy_id,
            scope=effective_scope,
            provider=provider.name,
            model=model.model_id,
            estimated_cost=estimated_cost,
            max_cost=max_cost,
            expires_at=datetime.now(UTC) + timedelta(seconds=self.RESERVATION_TTL_SECONDS),
        )

        self._reservations[reservation_id] = reservation
        if effective_policy_id:
            self._usage_tracker.add_reservation(effective_policy_id, estimated_cost)

        self._publish_blocking(
            Topic.BUDGET_RESERVED,
            {
                "reservation_id": reservation_id,
                "policy_id": effective_policy_id,
                "estimated_cost": estimated_cost,
            },
        )

        return BudgetResult(
            approved=True,
            estimated_cost=estimated_cost,
            max_cost=max_cost,
            remaining_budget=remaining,
            reservation_id=reservation_id,
            effective_policy_id=effective_policy_id,
            effective_scope=effective_scope,
            warnings=tuple(warnings),
            overrides_applied=tuple(set(overrides)),
        )

    def _record_limit_hit(self, scope: str) -> None:
        limit_hits = dict(self._stats.limit_hits)
        limit_hits[scope] = limit_hits.get(scope, 0) + 1
        self._stats = BudgetStatistics(
            total_evaluations=self._stats.total_evaluations,
            approvals=self._stats.approvals,
            rejections=self._stats.rejections,
            reservation_count=self._stats.reservation_count,
            active_reservations=self._stats.active_reservations,
            commits=self._stats.commits,
            rollbacks=self._stats.rollbacks,
            average_evaluation_time_ms=self._stats.average_evaluation_time_ms,
            cost_saved=self._stats.cost_saved,
            provider_spend=self._stats.provider_spend,
            model_spend=self._stats.model_spend,
            workspace_spend=self._stats.workspace_spend,
            user_spend=self._stats.user_spend,
            organization_spend=self._stats.organization_spend,
            limit_hits=limit_hits,
            warnings_issued=self._stats.warnings_issued,
        )

    # ── Reservation Lifecycle ──

    async def reserve(
        self,
        provider: str,
        model: str,
        estimated_cost: float,
        max_cost: float,
        scope: BudgetScope = BudgetScope.GLOBAL,
        scope_id: str = "",
    ) -> BudgetReservation | None:
        """Create an explicit reservation outside of evaluate()."""
        async with self._lock:
            self._cleanup_expired_reservations_locked()
            reservation_id = uuid4().hex[:16]
            reservation = BudgetReservation(
                id=reservation_id,
                provider=provider,
                model=model,
                estimated_cost=estimated_cost,
                max_cost=max_cost,
                scope=scope,
                scope_id=scope_id,
                expires_at=datetime.now(UTC) + timedelta(seconds=self.RESERVATION_TTL_SECONDS),
            )
            self._reservations[reservation_id] = reservation
        await self._publish(
            Topic.BUDGET_RESERVED,
            {
                "reservation_id": reservation_id,
                "provider": provider,
                "estimated_cost": estimated_cost,
            },
        )
        self._add_audit(
            "reserve", reservation_id, provider=provider, model=model, amount=estimated_cost
        )
        return reservation

    async def commit(self, reservation_id: str) -> bool:
        """Commit a reservation — record the spend."""
        async with self._lock:
            reservation = self._reservations.get(reservation_id)
            if (
                not reservation
                or reservation.committed
                or reservation.rolled_back
                or reservation.released
            ):
                return False

            updated = BudgetReservation(
                id=reservation.id,
                policy_id=reservation.policy_id,
                scope=reservation.scope,
                scope_id=reservation.scope_id,
                provider=reservation.provider,
                model=reservation.model,
                estimated_cost=reservation.estimated_cost,
                max_cost=reservation.max_cost,
                timestamp=reservation.timestamp,
                expires_at=reservation.expires_at,
                committed=True,
                rolled_back=False,
                released=False,
            )
            self._reservations[reservation_id] = updated

            # Record spend in usage tracker
            if reservation.policy_id:
                self._usage_tracker.remove_reservation(
                    reservation.policy_id, reservation.estimated_cost
                )
                self._usage_tracker.record_spend(
                    reservation.policy_id,
                    reservation.estimated_cost,
                    provider=reservation.provider,
                    model=reservation.model,
                )

            self._stats = BudgetStatistics(
                total_evaluations=self._stats.total_evaluations,
                approvals=self._stats.approvals,
                rejections=self._stats.rejections,
                reservation_count=self._stats.reservation_count,
                active_reservations=self._stats.active_reservations,
                commits=self._stats.commits + 1,
                rollbacks=self._stats.rollbacks,
                average_evaluation_time_ms=self._stats.average_evaluation_time_ms,
                cost_saved=self._stats.cost_saved,
                provider_spend=self._update_dict(
                    self._stats.provider_spend, reservation.provider, reservation.estimated_cost
                ),
                model_spend=self._update_dict(
                    self._stats.model_spend, reservation.model, reservation.estimated_cost
                ),
                workspace_spend=self._stats.workspace_spend,
                user_spend=self._stats.user_spend,
                organization_spend=self._stats.organization_spend,
                limit_hits=self._stats.limit_hits,
                warnings_issued=self._stats.warnings_issued,
            )

        await self._publish(
            Topic.BUDGET_COMMITTED,
            {
                "reservation_id": reservation_id,
                "policy_id": reservation.policy_id,
                "amount": reservation.estimated_cost,
            },
        )
        self._add_audit("commit", reservation_id, amount=reservation.estimated_cost)
        return True

    async def rollback(self, reservation_id: str) -> bool:
        """Roll back a reservation — release the funds without recording spend."""
        async with self._lock:
            reservation = self._reservations.get(reservation_id)
            if not reservation or reservation.committed or reservation.rolled_back:
                return False

            updated = BudgetReservation(
                id=reservation.id,
                policy_id=reservation.policy_id,
                scope=reservation.scope,
                scope_id=reservation.scope_id,
                provider=reservation.provider,
                model=reservation.model,
                estimated_cost=reservation.estimated_cost,
                max_cost=reservation.max_cost,
                timestamp=reservation.timestamp,
                expires_at=None,
                committed=False,
                rolled_back=True,
                released=False,
            )
            self._reservations[reservation_id] = updated

            if reservation.policy_id:
                self._usage_tracker.remove_reservation(
                    reservation.policy_id, reservation.estimated_cost
                )

            self._stats = BudgetStatistics(
                total_evaluations=self._stats.total_evaluations,
                approvals=self._stats.approvals,
                rejections=self._stats.rejections,
                reservation_count=self._stats.reservation_count,
                active_reservations=self._stats.active_reservations,
                commits=self._stats.commits,
                rollbacks=self._stats.rollbacks + 1,
                average_evaluation_time_ms=self._stats.average_evaluation_time_ms,
                cost_saved=self._stats.cost_saved + reservation.estimated_cost,
                provider_spend=self._stats.provider_spend,
                model_spend=self._stats.model_spend,
                workspace_spend=self._stats.workspace_spend,
                user_spend=self._stats.user_spend,
                organization_spend=self._stats.organization_spend,
                limit_hits=self._stats.limit_hits,
                warnings_issued=self._stats.warnings_issued,
            )

        await self._publish(
            Topic.BUDGET_ROLLBACK,
            {
                "reservation_id": reservation_id,
                "policy_id": reservation.policy_id,
                "amount": reservation.estimated_cost,
            },
        )
        self._add_audit("rollback", reservation_id, amount=reservation.estimated_cost)
        return True

    async def release(self, reservation_id: str) -> bool:
        """Release a reservation without committing or rolling back."""
        async with self._lock:
            reservation = self._reservations.get(reservation_id)
            if not reservation or reservation.released:
                return False

            updated = BudgetReservation(
                id=reservation.id,
                policy_id=reservation.policy_id,
                scope=reservation.scope,
                scope_id=reservation.scope_id,
                provider=reservation.provider,
                model=reservation.model,
                estimated_cost=reservation.estimated_cost,
                max_cost=reservation.max_cost,
                timestamp=reservation.timestamp,
                expires_at=None,
                committed=False,
                rolled_back=False,
                released=True,
            )
            self._reservations[reservation_id] = updated

            if reservation.policy_id:
                self._usage_tracker.remove_reservation(
                    reservation.policy_id, reservation.estimated_cost
                )

        await self._publish(
            Topic.BUDGET_RELEASED,
            {
                "reservation_id": reservation_id,
                "policy_id": reservation.policy_id,
            },
        )
        self._add_audit("release", reservation_id, amount=reservation.estimated_cost)
        return True

    def _cleanup_expired_reservations_locked(self) -> None:
        """Remove expired reservations (called with lock held)."""
        now = datetime.now(UTC)
        expired_ids = [
            rid
            for rid, res in self._reservations.items()
            if not res.committed
            and not res.rolled_back
            and not res.released
            and res.expires_at
            and res.expires_at < now
        ]
        for rid in expired_ids:
            res = self._reservations[rid]
            updated = BudgetReservation(
                id=res.id,
                policy_id=res.policy_id,
                scope=res.scope,
                scope_id=res.scope_id,
                provider=res.provider,
                model=res.model,
                estimated_cost=res.estimated_cost,
                max_cost=res.max_cost,
                timestamp=res.timestamp,
                expires_at=None,
                committed=False,
                rolled_back=False,
                released=True,
            )
            self._reservations[rid] = updated
            if res.policy_id:
                self._usage_tracker.remove_reservation(res.policy_id, res.estimated_cost)

    # ── Overrides ──

    async def apply_override(self, override: BudgetOverride) -> bool:
        async with self._lock:
            self._overrides[override.id] = override
        await self._publish(
            Topic.BUDGET_OVERRIDE,
            {
                "override_id": override.id,
                "policy_id": override.policy_id,
                "reason": override.reason,
            },
        )
        return True

    async def remove_override(self, override_id: str) -> bool:
        async with self._lock:
            if override_id not in self._overrides:
                return False
            del self._overrides[override_id]
        return True

    def _find_active_override(self, policy_id: str) -> BudgetOverride | None:
        """Find an active override for a policy."""
        now = datetime.now(UTC)
        for override in self._overrides.values():
            if override.policy_id == policy_id:
                if override.expires_at and override.expires_at < now:
                    continue
                return override
        return None

    # ── Emergency Mode ──

    async def set_emergency_mode(self, active: bool) -> None:
        async with self._lock:
            self._emergency_mode = active
        log.warning("BudgetEngine emergency mode %s", "ACTIVATED" if active else "DEACTIVATED")

    # ── Observability ──

    async def statistics(self) -> BudgetStatistics:
        async with self._lock:
            return self._stats

    async def snapshot(self) -> BudgetSnapshot:
        async with self._lock:
            self._cleanup_expired_reservations_locked()
            active_reservations = [
                r
                for r in self._reservations.values()
                if not r.committed and not r.rolled_back and not r.released
            ]
            return BudgetSnapshot(
                policies=tuple(self._policies.values()),
                usage=tuple(self._usage_tracker.all_usage()),
                active_reservations=tuple(active_reservations),
                statistics=self._stats,
                emergency_mode=self._emergency_mode,
            )

    async def forecast(self) -> BudgetForecast:
        """Project future budget usage based on current trends."""
        async with self._lock:
            usage_list = self._usage_tracker.all_usage()
            total_daily_spend = sum(u.daily_spent for u in usage_list)

            # Find global policy for remaining budget
            global_policy = None
            for p in self._policies.values():
                if p.scope == BudgetScope.GLOBAL and p.enabled:
                    global_policy = p
                    break

            remaining_daily = 0.0
            remaining_monthly = 0.0
            if global_policy:
                global_usage = self._usage_tracker.get_usage(global_policy.id)
                remaining_daily = (
                    max(0.0, global_policy.max_spend_daily - global_usage.daily_spent)
                    if global_policy.max_spend_daily > 0
                    else float("inf")
                )
                remaining_monthly = (
                    max(0.0, global_policy.max_spend_monthly - global_usage.monthly_spent)
                    if global_policy.max_spend_monthly > 0
                    else float("inf")
                )

            # Project per-provider/model
            provider_forecast: dict[str, float] = {}
            model_forecast: dict[str, float] = {}
            for usage in usage_list:
                for prov, spend in usage.provider_spend.items():
                    provider_forecast[prov] = provider_forecast.get(prov, 0.0) + spend
                for mod, spend in usage.model_spend.items():
                    model_forecast[mod] = model_forecast.get(mod, 0.0) + spend

            # Estimate remaining days in month
            now = datetime.now(UTC)
            days_in_month = (now.replace(day=28) + timedelta(days=4)).replace(day=1).day
            days_elapsed = now.day
            days_remaining = max(1, days_in_month - days_elapsed)
            avg_daily = total_daily_spend / max(1, days_elapsed)

            projected_monthly = avg_daily * days_in_month
            estimated_runway = (
                remaining_monthly / max(0.001, avg_daily) if remaining_monthly > 0 else 0.0
            )
            at_risk = estimated_runway < 7 if remaining_monthly > 0 else False

            warnings_list: list[str] = []
            if at_risk:
                warnings_list.append(
                    f"Budget runway less than 7 days ({estimated_runway:.1f} days remaining)"
                )
            if total_daily_spend > 0 and remaining_daily < total_daily_spend * 0.2:
                warnings_list.append("Less than 20% of daily budget remaining")

            return BudgetForecast(
                projected_daily_spend=avg_daily,
                projected_monthly_spend=projected_monthly,
                remaining_daily_budget=remaining_daily,
                remaining_monthly_budget=remaining_monthly,
                estimated_days_remaining=days_remaining,
                estimated_runway_days=estimated_runway,
                provider_forecast=provider_forecast,
                model_forecast=model_forecast,
                at_risk=at_risk,
                warnings=tuple(warnings_list),
            )

    async def metrics(self) -> dict[str, Any]:
        """Return current metrics snapshot."""
        async with self._lock:
            return {
                "total_evaluations": self._stats.total_evaluations,
                "approvals": self._stats.approvals,
                "rejections": self._stats.rejections,
                "reservation_count": self._stats.reservation_count,
                "active_reservations": self._stats.active_reservations,
                "commits": self._stats.commits,
                "rollbacks": self._stats.rollbacks,
                "average_evaluation_time_ms": self._stats.average_evaluation_time_ms,
                "cost_saved": self._stats.cost_saved,
                "policies_count": len(self._policies),
                "reservations_count": len(self._reservations),
                "overrides_count": len(self._overrides),
                "emergency_mode": self._emergency_mode,
                "uptime_seconds": time.monotonic() - self._start_time
                if self._start_time > 0
                else 0,
            }

    async def usage(self, policy_id: str) -> BudgetUsage | None:
        async with self._lock:
            return self._usage_tracker.get_usage(policy_id)

    async def audit_log(self, limit: int = 100, offset: int = 0) -> list[BudgetAuditRecord]:
        async with self._lock:
            start = min(offset, len(self._audit_log))
            end = min(start + limit, len(self._audit_log))
            return list(reversed(self._audit_log))[start:end]

    def _add_audit(
        self,
        action: str,
        reservation_id: str = "",
        policy_id: str = "",
        provider: str = "",
        model: str = "",
        amount: float = 0.0,
        request_id: str = "",
    ) -> None:
        record = BudgetAuditRecord(
            action=action,
            policy_id=policy_id,
            provider=provider,
            model=model,
            amount=amount,
            reservation_id=reservation_id,
            reason=request_id,
        )
        self._audit_log.append(record)
        # Trim if exceeding max
        if len(self._audit_log) > self._max_audit_entries:
            self._audit_log = self._audit_log[-self._max_audit_entries :]

    # ── Helpers ──

    @staticmethod
    def _update_dict(d: dict[str, float], key: str, amount: float) -> dict[str, float]:
        result = dict(d)
        result[key] = result.get(key, 0.0) + amount
        return result

    async def _publish(self, topic: Topic, payload: dict[str, Any]) -> None:
        if self._event_bus is not None:
            try:
                await self._event_bus.publish(
                    EventEnvelope(
                        type="budget",
                        topic=topic,
                        source="omniroute.budget_engine",
                        payload=payload,
                    )
                )
            except Exception:
                log.warning("Failed to publish %s", topic)

    def _publish_blocking(self, topic: Topic, payload: dict[str, Any]) -> None:
        """Synchronous publish for use inside async with lock."""
        if self._event_bus is not None:
            try:
                # Create and schedule a task — fire-and-forget
                asyncio.ensure_future(self._publish(topic, payload))
            except Exception:
                log.warning("Failed to schedule publish for %s", topic)


# ── __all__ ──

__all__ = [
    "BudgetEngineImpl",
    "BudgetEnginePort",
    "_CostPredictor",
    "_CostEstimate",
    "_UsageTracker",
]
