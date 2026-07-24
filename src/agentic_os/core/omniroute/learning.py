"""OmniRoute Adaptive Learning & Scoring Engine — continuous provider/model
intelligence from routing outcomes.

The learning engine never routes requests directly. It enriches candidates
with adaptive intelligence before the Routing Policy Engine executes.

Pipeline position: after Circuit Breaker, before Capability Filters.

Components
----------
• Bayesian estimation for success/failure/reliability
• Exponentially weighted moving averages (EWMA) for latency/cost/quality
• Sliding windows (5 min, 30 min, 6 h, 24 h, 7 d, 30 d, lifetime)
• Trend detection (improving, stable, degrading, rapid degradation, recovery, oscillation)
• Confidence scoring (sample count, variance, prediction error)
• Prediction engine (expected latency, cost, success, failure, retry, availability)
• Reputation engine (provider, model, workspace, agent, user, global)
• Adaptive scoring (quality, latency, cost, reliability, availability, recovery, budget)
• EventBus integration (publish learning events)
• Observability (metrics, statistics, forecast, snapshot)
"""

from __future__ import annotations

import asyncio
import math
import time
from collections import deque
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol, runtime_checkable

from agentic_os.domain.events import EventEnvelope, Topic
from agentic_os.domain.omniroute import (
    AdaptiveScore,
    AdaptiveWeights,
    ConfidenceScore,
    CostTrend,
    FailureTrend,
    LatencyTrend,
    LearningDecision,
    LearningForecast,
    LearningInputSource,
    LearningRecord,
    LearningSnapshot,
    LearningStatistics,
    LearningWindow,
    ModelReputation,
    PredictionResult,
    ProviderReputation,
    ProviderTrend,
    ReputationScore,
    RoutingRequest,
    SuccessTrend,
    TrendDirection,
)
from agentic_os.infrastructure.logging import get_logger

log = get_logger("omniroute.learning")

# ── Constants ──

_EWMA_DEFAULT_ALPHA = 0.3
_SLIDING_WINDOWS: tuple[str, ...] = ("5min", "30min", "6h", "24h", "7d", "30d", "lifetime")
_WINDOW_DURATIONS: dict[str, timedelta] = {
    "5min": timedelta(minutes=5),
    "30min": timedelta(minutes=30),
    "6h": timedelta(hours=6),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
    "lifetime": timedelta(days=365 * 10),
}
_MAX_RECORDS = 10000
_MAX_RECENT = 1000

# ── Port Protocol ──


@runtime_checkable
class AdaptiveLearningEnginePort(Protocol):
    """OmniRoute adaptive learning engine — enriches candidates with intelligence."""

    async def enrich(
        self,
        candidates: list[tuple[Any, Any]],
        request: RoutingRequest,
    ) -> LearningDecision:
        """Enrich candidates with adaptive scores. Never filters, only enriches."""
        ...

    async def observe(self, record: LearningRecord) -> None:
        """Record a learning observation from a routing outcome."""
        ...

    async def update_reputation(
        self, provider: str, model: str, success: bool, **kwargs: Any
    ) -> None:
        """Update provider and model reputation from an outcome."""
        ...

    async def predict(self, provider: str, model: str) -> PredictionResult:
        """Predict outcomes for a provider+model combination."""
        ...

    async def forecast(self) -> LearningForecast:
        """Generate a full learning forecast."""
        ...

    async def snapshot(self) -> LearningSnapshot:
        """Return point-in-time snapshot of all learning state."""
        ...

    async def statistics(self) -> LearningStatistics:
        """Return aggregate learning statistics."""
        ...

    async def provider_reputation(self, provider: str) -> ProviderReputation | None:
        """Get reputation for a specific provider."""
        ...

    async def model_reputation(self, provider: str, model: str) -> ModelReputation | None:
        """Get reputation for a specific provider+model."""
        ...

    async def metrics(self) -> dict[str, Any]:
        """Return learning engine metrics for observability."""
        ...

    # ── Lifecycle ──

    async def initialize(self) -> None: ...

    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def dispose(self) -> None: ...

    async def health(self) -> dict[str, Any]: ...

    async def ready(self) -> bool: ...


# ── Internal: Bayesian Estimator ──


class _BayesianEstimator:
    """Bayesian estimation for success/failure probability.

    Uses a Beta(a, b) posterior where a = success_count, b = failure_count.
    Prior is Beta(1, 1) — uniform. Avoids overconfidence on small samples
    because the posterior mean is pulled toward the prior when counts are low.
    """

    def __init__(self, prior_a: float = 1.0, prior_b: float = 1.0) -> None:
        self._prior_a = prior_a
        self._prior_b = prior_b

    def estimate(
        self,
        success_count: int,
        failure_count: int,
    ) -> tuple[float, float]:
        """Return (posterior_mean, posterior_std) for success probability."""
        a = self._prior_a + success_count
        b = self._prior_b + failure_count
        n = a + b
        if n <= 0:
            return 0.5, 0.5
        mean = a / n
        # Variance of Beta(a, b) = a*b / ((a+b)^2 * (a+b+1))
        variance = (a * b) / (n * n * (n + 1)) if n > 0 else 0.25
        return mean, math.sqrt(variance)

    def credible_interval(
        self,
        success_count: int,
        failure_count: int,
        percentile: float = 0.95,
    ) -> tuple[float, float]:
        """Approximate credible interval using normal approximation.

        For small counts this is conservative (over-estimates uncertainty).
        """
        mean, std = self.estimate(success_count, failure_count)
        z = 1.96 if percentile >= 0.95 else 1.645
        lower = max(0.0, mean - z * std)
        upper = min(1.0, mean + z * std)
        return lower, upper

    def reliability_score(self, success_count: int, failure_count: int) -> float:
        """Compute a reliability score that penalizes uncertainty.

        Returns a value in [0, 1] where 1 = highly reliable.
        Uses the lower bound of the 95% credible interval so small samples
        with high success rate still get conservative scores.
        """
        lower, _ = self.credible_interval(success_count, failure_count)
        n = success_count + failure_count
        if n < 5:
            # Scale by sample size: fewer samples = less reliability
            return lower * (n / 5.0)
        return lower


# ── Internal: Moving Average (EWMA) ──


class _EWMA:
    """Exponentially weighted moving average with configurable alpha."""

    def __init__(self, alpha: float = _EWMA_DEFAULT_ALPHA) -> None:
        self._alpha = alpha
        self._value: float | None = None
        self._count: int = 0

    def update(self, value: float) -> float:
        """Update the EWMA with a new observation, return the new value."""
        if self._value is None:
            self._value = value
        else:
            self._value = self._alpha * value + (1 - self._alpha) * self._value
        self._count += 1
        return self._value

    @property
    def value(self) -> float:
        return self._value or 0.0

    @property
    def count(self) -> int:
        return self._count


# ── Internal: Sliding Window ──


class _SlidingWindowStats:
    """Sliding window statistics with O(1) updates via deque.

    Tracks: sample count, success rate, failure rate, average latency,
    average cost, latency percentiles (p50/p95/p99), min/max.
    """

    def __init__(self, max_duration: timedelta) -> None:
        self._max_duration = max_duration
        self._samples: deque[tuple[datetime, float, bool, float]] = deque()
        self._latencies: deque[float] = deque(maxlen=10000)

    def record(self, latency_ms: float, success: bool, cost: float) -> None:
        now = datetime.now(UTC)
        self._samples.append((now, latency_ms, success, cost))
        if success:
            self._latencies.append(latency_ms)

    def expire(self) -> None:
        now = datetime.now(UTC)
        cutoff = now - self._max_duration
        while self._samples and self._samples[0][0] < cutoff:
            self._samples.popleft()

    def _compute_percentiles(self) -> tuple[float, float, float]:
        """Compute p50, p95, p99 from recent latencies."""
        if not self._latencies:
            return 0.0, 0.0, 0.0
        sorted_l = sorted(self._latencies)
        n = len(sorted_l)
        p50 = sorted_l[max(0, int(n * 0.5))] if n > 0 else 0.0
        p95 = sorted_l[max(0, int(n * 0.95))] if n > 0 else 0.0
        p99 = sorted_l[max(0, int(n * 0.99))] if n > 0 else 0.0
        return p50, p95, p99

    def summary(self, window_name: str) -> LearningWindow:
        self.expire()
        count = len(self._samples)
        if count == 0:
            return LearningWindow(window_duration=window_name)
        successes = sum(1 for _, _, s, _ in self._samples if s)
        failures = count - successes
        total_latency = sum(lat for _, lat, _, _ in self._samples)
        total_cost = sum(c for _, _, _, c in self._samples)
        latencies = [lat for _, lat, _, _ in self._samples]
        p50, p95, p99 = self._compute_percentiles()
        return LearningWindow(
            window_duration=window_name,
            sample_count=count,
            success_rate=successes / count if count > 0 else 0.0,
            failure_rate=failures / count if count > 0 else 0.0,
            average_latency_ms=total_latency / count if count > 0 else 0.0,
            average_cost=total_cost / count if count > 0 else 0.0,
            p50_latency_ms=p50,
            p95_latency_ms=p95,
            p99_latency_ms=p99,
            min_latency_ms=min(latencies) if latencies else 0.0,
            max_latency_ms=max(latencies) if latencies else 0.0,
        )


# ── Internal: Trend Detector ──


class _TrendDetector:
    """Detects performance trends from EWMA values.

    Compares the short-term EWMA against a longer-term EWMA to classify
    the direction of change.
    """

    def __init__(self, short_alpha: float = 0.5, long_alpha: float = 0.1) -> None:
        self._short = _EWMA(short_alpha)
        self._long = _EWMA(long_alpha)
        self._last_direction: TrendDirection = TrendDirection.UNKNOWN

    def update(self, value: float) -> TrendDirection:
        short_val = self._short.update(value)
        long_val = self._long.update(value)

        if self._short.count < 3:
            return TrendDirection.UNKNOWN

        ratio = short_val / long_val if long_val > 0 else 1.0
        delta = short_val - long_val

        if delta > 0:
            if ratio > 1.5:
                direction = TrendDirection.RAPID_DEGRADATION
            elif ratio > 1.15:
                direction = TrendDirection.DEGRADING
            elif ratio > 1.02:
                direction = TrendDirection.STABLE
            else:
                direction = TrendDirection.STABLE
        else:
            if ratio < 0.6:
                direction = TrendDirection.RAPID_DEGRADATION
            elif ratio < 0.85:
                direction = TrendDirection.DEGRADING
            elif ratio < 0.98:
                direction = TrendDirection.STABLE
            else:
                direction = TrendDirection.STABLE

        # Recovery detection: was degrading, now improving
        if (
            self._last_direction in (TrendDirection.DEGRADING, TrendDirection.RAPID_DEGRADATION)
            and direction == TrendDirection.STABLE
            and delta < 0
        ):
            direction = TrendDirection.RECOVERY

        # If short has sign opposite to long, check for oscillation
        if self._short.count >= 10:
            prev = self._last_direction
            if prev != direction and prev != TrendDirection.UNKNOWN:
                direction = TrendDirection.OSCILLATION

        self._last_direction = direction
        return direction

    def reset(self) -> None:
        self._short = _EWMA(self._short._alpha)
        self._long = _EWMA(self._long._alpha)
        self._last_direction = TrendDirection.UNKNOWN


# ── Internal: Confidence Calculator ──


class _ConfidenceCalculator:
    """Calculates confidence in adaptive scores and predictions.

    Confidence increases with sample count and decreases with variance.
    Uses a sigmoid-like mapping to keep confidence in [0, 1].
    """

    @staticmethod
    def calculate(
        sample_count: int,
        variance: float,
        prediction_error: float = 0.0,
        calibration: float = 1.0,
    ) -> ConfidenceScore:
        if sample_count == 0:
            return ConfidenceScore(score=0.0, sample_count=0, variance=variance)

        # Base confidence from sample count (sigmoid-like)
        sample_confidence = 1.0 - math.exp(-sample_count / 20.0)

        # Variance penalty (high variance = lower confidence)
        var_penalty = 1.0 - min(variance * 5.0, 0.5)

        # Prediction error penalty
        error_penalty = 1.0 - min(prediction_error, 0.5)

        # Combined score
        score = sample_confidence * var_penalty * error_penalty * calibration
        score = max(0.0, min(1.0, score))

        return ConfidenceScore(
            score=round(score, 4),
            sample_count=sample_count,
            variance=round(variance, 6),
            prediction_error=round(prediction_error, 4),
            calibration=calibration,
        )


# ── Internal: Prediction Engine ──


class _PredictionEngine:
    """Makes predictions for provider+model combinations.

    Uses EWMA for trending values and Bayesian estimates for probabilities.
    """

    def __init__(self) -> None:
        self._bayesian = _BayesianEstimator()

    def predict(
        self,
        reputation: ReputationScore,
        latency_ewma: float,
        cost_ewma: float,
        latency_variance: float,
    ) -> PredictionResult:
        success_prob, _ = self._bayesian.estimate(
            reputation.success_count, reputation.failure_count
        )
        failure_prob = 1.0 - success_prob
        conf = _ConfidenceCalculator.calculate(
            sample_count=reputation.sample_size,
            variance=latency_variance,
            prediction_error=0.0,
        )
        return PredictionResult(
            expected_latency_ms=round(latency_ewma, 2),
            expected_cost=round(cost_ewma, 6),
            expected_success_probability=round(success_prob, 4),
            expected_failure_probability=round(failure_prob, 4),
            expected_retry_probability=round(failure_prob * 0.3, 4),
            expected_availability=round(reputation.availability, 4),
            confidence=conf,
            prediction_horizon="short_term",
        )


# ── Internal: Reputation Engine ──


class _ReputationEngine:
    """Maintains reputation for providers, models, and scopes."""

    def __init__(self) -> None:
        self._bayesian = _BayesianEstimator()

    def compute_reputation(
        self,
        success_count: int,
        failure_count: int,
        latency_score: float,
        cost_score: float,
        availability: float,
        sample_size: int,
    ) -> ReputationScore:
        total = max(success_count + failure_count, 1)
        success_rate = success_count / total
        failure_rate = failure_count / total

        reliability = self._bayesian.reliability_score(success_count, failure_count)
        confidence = min(
            1.0,
            sample_size / 20.0,
        )
        # Quality is a blend of success rate, reliability, and availability
        quality = 0.4 * success_rate + 0.3 * reliability + 0.3 * availability
        stability = 1.0 - abs(0.5 - success_rate) * 2  # 1.0 when success_rate = 0.5

        return ReputationScore(
            success_count=success_count,
            failure_count=failure_count,
            total_attempts=total,
            success_rate=round(success_rate, 4),
            failure_rate=round(failure_rate, 4),
            latency_score=round(latency_score, 4),
            cost_score=round(cost_score, 4),
            availability=round(availability, 4),
            stability=round(stability, 4),
            confidence=round(confidence, 4),
            quality=round(quality, 4),
            sample_size=sample_size,
        )


# ── Internal: Adaptive Score Calculator ──


class _AdaptiveScorer:
    """Computes normalized adaptive scores for providers and models."""

    def __init__(self, weights: AdaptiveWeights | None = None) -> None:
        self._weights = weights or AdaptiveWeights()

    def compute(
        self,
        reputation: ReputationScore,
        latency_trend: LatencyTrend,
        cost_trend: CostTrend,
        success_trend: SuccessTrend,
        failure_trend: FailureTrend,
        budget_efficiency: float = 0.5,
        confidence: ConfidenceScore | None = None,
    ) -> AdaptiveScore:
        # Quality component = reputation quality
        quality_comp = reputation.quality

        # Latency component = inverted normalized latency
        max_latency = max(latency_trend.max, 1.0)
        latency_comp = (
            1.0 - min(latency_trend.current / max_latency, 1.0) if max_latency > 0 else 0.5
        )

        # Cost component = inverted normalized cost
        max_cost = max(cost_trend.max, 0.001)
        cost_comp = 1.0 - min(cost_trend.current / max_cost, 1.0) if max_cost > 0 else 0.5

        # Reliability component = reputation quality
        reliability_comp = reputation.quality

        # Availability component
        availability_comp = reputation.availability

        # Recovery component
        recovery_comp = 0.5
        if success_trend.direction == TrendDirection.RECOVERY:
            recovery_comp = 0.8
        elif failure_trend.direction == TrendDirection.DEGRADING:
            recovery_comp = 0.2

        # Budget efficiency
        budget_eff = min(budget_efficiency, 1.0)

        w = self._weights
        raw = (
            quality_comp * w.quality
            + latency_comp * w.latency
            + cost_comp * w.cost
            + reliability_comp * w.reliability
            + availability_comp * w.availability
            + recovery_comp * w.recovery
            + budget_eff * w.budget_efficiency
        )
        total_w = (
            w.quality
            + w.latency
            + w.cost
            + w.reliability
            + w.availability
            + w.recovery
            + w.budget_efficiency
        )
        normalized = raw / total_w if total_w > 0 else 0.0
        normalized = max(0.0, min(1.0, normalized))

        # Determine overall trend
        trends = [
            latency_trend.direction,
            success_trend.direction,
            failure_trend.direction,
        ]
        if TrendDirection.RAPID_DEGRADATION in trends:
            trend = TrendDirection.RAPID_DEGRADATION
        elif TrendDirection.DEGRADING in trends:
            trend = TrendDirection.DEGRADING
        elif TrendDirection.IMPROVING in trends:
            trend = TrendDirection.IMPROVING
        elif TrendDirection.RECOVERY in trends:
            trend = TrendDirection.RECOVERY
        elif TrendDirection.STABLE in trends:
            trend = TrendDirection.STABLE
        else:
            trend = TrendDirection.UNKNOWN

        if confidence is None:
            confidence = _ConfidenceCalculator.calculate(
                sample_count=reputation.sample_size,
                variance=latency_trend.variance,
            )

        return AdaptiveScore(
            raw_score=round(raw, 4),
            normalized_score=round(normalized, 4),
            quality_component=round(quality_comp, 4),
            latency_component=round(latency_comp, 4),
            cost_component=round(cost_comp, 4),
            reliability_component=round(reliability_comp, 4),
            availability_component=round(availability_comp, 4),
            recovery_component=round(recovery_comp, 4),
            budget_efficiency=round(budget_eff, 4),
            confidence=confidence,
            trend=trend,
        )


# ── Internal Provider Learning State ──


class _ProviderLearningState:
    """Mutable learning state for a single provider."""

    def __init__(self, provider: str) -> None:
        self.provider = provider
        self.success_count: int = 0
        self.failure_count: int = 0
        self.latency_ewma = _EWMA()
        self.cost_ewma = _EWMA()
        self.quality_ewma = _EWMA()
        self.success_ewma = _EWMA()
        self.failure_ewma = _EWMA()
        self.latency_tracker = _TrendDetector()
        self.cost_tracker = _TrendDetector()
        self.success_tracker = _TrendDetector()
        self.failure_tracker = _TrendDetector()
        self.windows: dict[str, _SlidingWindowStats] = {}
        for wname in _SLIDING_WINDOWS:
            self.windows[wname] = _SlidingWindowStats(_WINDOW_DURATIONS[wname])
        self.last_update: datetime = datetime.now(UTC)
        self.min_latency: float = float("inf")
        self.max_latency: float = 0.0
        self.min_cost: float = float("inf")
        self.max_cost: float = 0.0
        self.availability: float = 1.0
        self.consecutive_failures: int = 0
        self.consecutive_successes: int = 0


class _ModelLearningState:
    """Mutable learning state for a single model (within a provider)."""

    def __init__(self, provider: str, model: str) -> None:
        self.provider = provider
        self.model = model
        self.success_count: int = 0
        self.failure_count: int = 0
        self.latency_ewma = _EWMA()
        self.cost_ewma = _EWMA()
        self.quality_ewma = _EWMA()
        self.success_ewma = _EWMA()
        self.failure_ewma = _EWMA()
        self.latency_tracker = _TrendDetector()
        self.cost_tracker = _TrendDetector()
        self.success_tracker = _TrendDetector()
        self.failure_tracker = _TrendDetector()
        self.windows: dict[str, _SlidingWindowStats] = {}
        for wname in _SLIDING_WINDOWS:
            self.windows[wname] = _SlidingWindowStats(_WINDOW_DURATIONS[wname])
        self.last_update: datetime = datetime.now(UTC)
        self.min_latency: float = float("inf")
        self.max_latency: float = 0.0
        self.min_cost: float = float("inf")
        self.max_cost: float = 0.0


# ── Concrete Implementation ──


class AdaptiveLearningEngineImpl:
    """Production Adaptive Learning & Scoring Engine.

    Continuously learns from routing outcomes and improves provider/model
    scoring over time. Never routes directly — enriches candidates with
    adaptive intelligence.
    """

    def __init__(
        self,
        event_bus: Any | None = None,
        weights: AdaptiveWeights | None = None,
        max_records: int = _MAX_RECORDS,
        max_recent: int = _MAX_RECENT,
    ) -> None:
        self._event_bus = event_bus
        self._weights = weights or AdaptiveWeights()
        self._max_records = max_records
        self._max_recent = max_recent

        # Component engines
        self._bayesian = _BayesianEstimator()
        self._prediction_engine = _PredictionEngine()
        self._reputation_engine = _ReputationEngine()
        self._adaptive_scorer = _AdaptiveScorer(self._weights)

        # Mutable state (protected by lock)
        self._lock = asyncio.Lock()
        self._providers: dict[str, _ProviderLearningState] = {}
        self._models: dict[str, _ModelLearningState] = {}  # key = "provider:model"
        self._records: deque[LearningRecord] = deque(maxlen=max_records)
        self._recent_records: deque[LearningRecord] = deque(maxlen=max_recent)

        # Cached immutable snapshots
        self._cached_stats: LearningStatistics = LearningStatistics()
        self._cached_forecast: LearningForecast = LearningForecast()

        # Observability counters
        self._observation_count = 0
        self._enrich_count = 0
        self._anomaly_count = 0
        self._alert_count = 0
        self._total_latency = 0.0
        self._total_cost = 0.0
        self._prediction_error_sum = 0.0
        self._prediction_count = 0

        # Lifecycle
        self._started = False
        self._start_time: float = 0.0

    # ── Lifecycle ──

    async def initialize(self) -> None:
        log.info("AdaptiveLearningEngine initializing")

    async def start(self) -> None:
        self._started = True
        self._start_time = time.monotonic()
        log.info("AdaptiveLearningEngine started")

    async def stop(self) -> None:
        self._started = False
        log.info("AdaptiveLearningEngine stopped")

    async def dispose(self) -> None:
        await self.stop()
        self._providers.clear()
        self._models.clear()
        self._records.clear()
        self._recent_records.clear()
        self._observation_count = 0
        self._enrich_count = 0
        self._anomaly_count = 0
        self._alert_count = 0
        self._total_latency = 0.0
        self._total_cost = 0.0
        self._prediction_error_sum = 0.0
        self._prediction_count = 0
        log.info("AdaptiveLearningEngine disposed")

    async def health(self) -> dict[str, Any]:
        return {
            "status": "healthy" if self._started else "stopped",
            "started": self._started,
            "uptime_seconds": round(time.monotonic() - self._start_time, 2),
            "observations": self._observation_count,
            "providers": len(self._providers),
            "models": len(self._models),
            "anomalies": self._anomaly_count,
        }

    async def ready(self) -> bool:
        return self._started

    # ── Core API ──

    async def enrich(
        self,
        candidates: list[tuple[Any, Any]],
        request: RoutingRequest,
    ) -> LearningDecision:
        """Enrich candidates with adaptive scores. Never filters, only enriches."""
        if not self._started or not candidates:
            return LearningDecision()

        start = time.monotonic()
        enriched: list[tuple[str, str, AdaptiveScore]] = []

        async with self._lock:
            self._enrich_count += 1

            for provider_inst, model_inst in candidates:
                pname = provider_inst.name if hasattr(provider_inst, "name") else str(provider_inst)
                mname = model_inst.model_id if hasattr(model_inst, "model_id") else str(model_inst)

                provider_state = self._providers.get(pname)
                if provider_state is None:
                    continue

                score = self._build_adaptive_score(pname, mname)

                enriched.append((pname, mname, score))

            # Build predictions for all known provider+model combos
            predictions: dict[str, PredictionResult] = {}
            for pname, pstate in self._providers.items():
                pred = self._prediction_engine.predict(
                    self._build_reputation_from_state(pstate),
                    pstate.latency_ewma.value,
                    pstate.cost_ewma.value,
                    pstate.latency_ewma.value * 0.1 if pstate.latency_ewma.count > 0 else 0.0,
                )
                predictions[pname] = pred

        duration = (time.monotonic() - start) * 1000
        return LearningDecision(
            enriched_candidates=tuple(enriched),
            predictions=predictions,
            evaluation_time_ms=round(duration, 2),
            observations_count=self._observation_count,
        )

    async def observe(self, record: LearningRecord) -> None:
        """Record a learning observation from a routing outcome."""
        async with self._lock:
            self._records.append(record)
            self._recent_records.append(record)
            self._observation_count += 1

            # Update provider state
            provider_state = self._providers.setdefault(
                record.provider,
                _ProviderLearningState(record.provider),
            )

            # Update model state
            model_key = f"{record.provider}:{record.model}"
            model_state = self._models.setdefault(
                model_key,
                _ModelLearningState(record.provider, record.model),
            )

            # Update counts
            if record.success:
                provider_state.success_count += 1
                model_state.success_count += 1
                provider_state.consecutive_successes += 1
                provider_state.consecutive_failures = 0
            if record.failure:
                provider_state.failure_count += 1
                model_state.failure_count += 1
                provider_state.consecutive_failures += 1
                provider_state.consecutive_successes = 0

            # Update EWMA metrics
            if record.latency_ms > 0:
                provider_state.latency_ewma.update(record.latency_ms)
                model_state.latency_ewma.update(record.latency_ms)
                provider_state.min_latency = min(provider_state.min_latency, record.latency_ms)
                provider_state.max_latency = max(provider_state.max_latency, record.latency_ms)
                model_state.min_latency = min(model_state.min_latency, record.latency_ms)
                model_state.max_latency = max(model_state.max_latency, record.latency_ms)

            if record.cost > 0:
                provider_state.cost_ewma.update(record.cost)
                model_state.cost_ewma.update(record.cost)
                provider_state.min_cost = min(provider_state.min_cost, record.cost)
                provider_state.max_cost = max(provider_state.max_cost, record.cost)
                model_state.min_cost = min(model_state.min_cost, record.cost)
                model_state.max_cost = max(model_state.max_cost, record.cost)

            provider_state.quality_ewma.update(1.0 if record.success else 0.0)
            provider_state.success_ewma.update(1.0 if record.success else 0.0)
            provider_state.failure_ewma.update(1.0 if record.failure else 0.0)
            model_state.quality_ewma.update(1.0 if record.success else 0.0)
            model_state.success_ewma.update(1.0 if record.success else 0.0)
            model_state.failure_ewma.update(1.0 if record.failure else 0.0)

            # Update availability
            total = provider_state.success_count + provider_state.failure_count
            provider_state.availability = provider_state.success_count / total if total > 0 else 1.0

            # Update trend detectors
            provider_state.latency_tracker.update(record.latency_ms)
            provider_state.cost_tracker.update(record.cost)
            provider_state.success_tracker.update(1.0 if record.success else 0.0)
            provider_state.failure_tracker.update(1.0 if record.failure else 0.0)
            model_state.latency_tracker.update(record.latency_ms)
            model_state.cost_tracker.update(record.cost)
            model_state.success_tracker.update(1.0 if record.success else 0.0)
            model_state.failure_tracker.update(1.0 if record.failure else 0.0)

            # Update sliding windows
            for _wname, wstats in provider_state.windows.items():
                wstats.record(record.latency_ms, record.success, record.cost)
            for _wname, wstats in model_state.windows.items():
                wstats.record(record.latency_ms, record.success, record.cost)

            provider_state.last_update = datetime.now(UTC)
            model_state.last_update = datetime.now(UTC)

            # Update aggregate statistics
            total = self._observation_count
            self._total_latency += record.latency_ms
            self._total_cost += record.cost

            self._cached_stats = LearningStatistics(
                total_observations=self._observation_count,
                total_successes=sum(1 for r in self._records if r.success),
                total_failures=sum(1 for r in self._records if r.failure),
                total_retries=sum(1 for r in self._records if r.retry),
                total_fallbacks=sum(1 for r in self._records if r.fallback),
                provider_count=len(self._providers),
                model_count=len(self._models),
                average_latency_ms=self._total_latency / total if total > 0 else 0.0,
                average_cost=self._total_cost / total if total > 0 else 0.0,
                average_confidence=0.0,
                prediction_accuracy=0.0,
                alerts_triggered=self._alert_count,
                anomalies_detected=self._anomaly_count,
                last_observation=record.timestamp,
            )

        # Publish learning event (outside lock)
        if self._event_bus is not None:
            self._publish_event(
                Topic.LEARNING_UPDATED,
                {
                    "provider": record.provider,
                    "model": record.model,
                    "success": record.success,
                    "total_observations": self._observation_count,
                },
            )

        # Check for anomalies/degradation
        await self._check_anomalies(record.provider, record.model)

    async def update_reputation(
        self,
        provider: str,
        model: str,
        success: bool,
        **kwargs: Any,
    ) -> None:
        """Update provider and model reputation from an outcome."""
        record = LearningRecord(
            provider=provider,
            model=model,
            source=LearningInputSource.FEEDBACK,
            success=success,
            failure=not success,
            latency_ms=kwargs.get("latency_ms", 0.0),
            cost=kwargs.get("cost", 0.0),
            estimated_cost=kwargs.get("estimated_cost", 0.0),
            tokens_used=kwargs.get("tokens_used", 0),
            duration_ms=kwargs.get("duration_ms", 0.0),
            reason=kwargs.get("reason", ""),
            task_type=kwargs.get("task_type", ""),
            workspace=kwargs.get("workspace", ""),
            user_id=kwargs.get("user_id", ""),
            agent=kwargs.get("agent", ""),
            timeout=kwargs.get("timeout", False),
            retry=kwargs.get("retry", False),
            fallback=kwargs.get("fallback", False),
        )
        await self.observe(record)

    async def predict(self, provider: str, model: str) -> PredictionResult:
        """Predict outcomes for a provider+model combination."""
        async with self._lock:
            provider_state = self._providers.get(provider)
            if provider_state is None:
                return PredictionResult()

            rep = self._build_reputation_from_state(provider_state)
            return self._prediction_engine.predict(
                rep,
                provider_state.latency_ewma.value,
                provider_state.cost_ewma.value,
                provider_state.latency_ewma.value * 0.1
                if provider_state.latency_ewma.count > 0
                else 0.0,
            )

    async def forecast(self) -> LearningForecast:
        """Generate a full learning forecast."""
        async with self._lock:
            provider_forecast: dict[str, PredictionResult] = {}
            at_risk_providers: list[str] = []

            global_latency_values = [
                s.latency_ewma.value for s in self._providers.values() if s.latency_ewma.count > 0
            ]
            global_cost_values = [
                s.cost_ewma.value for s in self._providers.values() if s.cost_ewma.count > 0
            ]
            global_successes = sum(s.success_count for s in self._providers.values())
            global_failures = sum(s.failure_count for s in self._providers.values())
            global_total = global_successes + global_failures

            for pname, pstate in self._providers.items():
                rep = self._build_reputation_from_state(pstate)
                pred = self._prediction_engine.predict(
                    rep,
                    pstate.latency_ewma.value,
                    pstate.cost_ewma.value,
                    pstate.latency_ewma.value * 0.1 if pstate.latency_ewma.count > 0 else 0.0,
                )
                provider_forecast[pname] = pred

                # Identify at-risk providers
                if rep.quality < 0.3 or pstate.consecutive_failures >= 3:
                    at_risk_providers.append(pname)

            avg_latency = (
                sum(global_latency_values) / len(global_latency_values)
                if global_latency_values
                else 0.0
            )
            avg_cost = (
                sum(global_cost_values) / len(global_cost_values) if global_cost_values else 0.0
            )
            global_success_rate = global_successes / global_total if global_total > 0 else 0.0

            # Build window summaries
            latency_trend = LatencyTrend(
                current=avg_latency,
                ewma=avg_latency,
                sample_count=len(global_latency_values),
            )
            cost_trend = CostTrend(
                current=avg_cost,
                ewma=avg_cost,
                sample_count=len(global_cost_values),
            )

            conf = _ConfidenceCalculator.calculate(
                sample_count=global_total,
                variance=0.0,
            )

            self._cached_forecast = LearningForecast(
                provider_forecast=provider_forecast,
                global_latency_trend=latency_trend,
                global_cost_trend=cost_trend,
                global_success_rate=round(global_success_rate, 4),
                confidence=conf,
                at_risk_providers=tuple(at_risk_providers),
            )

            return self._cached_forecast

    async def snapshot(self) -> LearningSnapshot:
        """Return point-in-time snapshot of all learning state."""
        async with self._lock:
            provider_reps: list[ProviderReputation] = []
            model_reps: list[ModelReputation] = []

            for pname, pstate in self._providers.items():
                rep = self._build_reputation_from_state(pstate)
                score = self._build_adaptive_score(pname, "")
                trend = self._build_provider_trend(pstate)
                pred = self._prediction_engine.predict(
                    rep,
                    pstate.latency_ewma.value,
                    pstate.cost_ewma.value,
                    pstate.latency_ewma.value * 0.1 if pstate.latency_ewma.count > 0 else 0.0,
                )
                provider_reps.append(
                    ProviderReputation(
                        provider=pname,
                        reputation=rep,
                        adaptive_score=score,
                        trend=trend,
                        predictions=pred,
                    )
                )

            for mkey, mstate in self._models.items():
                prov, model = mkey.split(":", 1)
                rep = ReputationScore(
                    success_count=mstate.success_count,
                    failure_count=mstate.failure_count,
                    total_attempts=mstate.success_count + mstate.failure_count,
                    success_rate=mstate.success_count
                    / max(mstate.success_count + mstate.failure_count, 1),
                    latency_score=0.0,
                    cost_score=0.0,
                    sample_size=mstate.success_count + mstate.failure_count,
                )
                model_reps.append(
                    ModelReputation(
                        provider=prov,
                        model=model,
                        reputation=rep,
                    )
                )

            return LearningSnapshot(
                provider_reputations=tuple(provider_reps),
                model_reputations=tuple(model_reps),
                statistics=self._cached_stats,
                recent_records=tuple(self._recent_records),
            )

    async def statistics(self) -> LearningStatistics:
        return self._cached_stats

    async def provider_reputation(self, provider: str) -> ProviderReputation | None:
        async with self._lock:
            pstate = self._providers.get(provider)
            if pstate is None:
                return None
            rep = self._build_reputation_from_state(pstate)
            score = self._build_adaptive_score(provider, "")
            trend = self._build_provider_trend(pstate)
            pred = self._prediction_engine.predict(
                rep,
                pstate.latency_ewma.value,
                pstate.cost_ewma.value,
                pstate.latency_ewma.value * 0.1 if pstate.latency_ewma.count > 0 else 0.0,
            )
            return ProviderReputation(
                provider=provider,
                reputation=rep,
                adaptive_score=score,
                trend=trend,
                predictions=pred,
            )

    async def model_reputation(self, provider: str, model: str) -> ModelReputation | None:
        async with self._lock:
            mkey = f"{provider}:{model}"
            mstate = self._models.get(mkey)
            if mstate is None:
                return None
            rep = ReputationScore(
                success_count=mstate.success_count,
                failure_count=mstate.failure_count,
                total_attempts=mstate.success_count + mstate.failure_count,
                success_rate=mstate.success_count
                / max(mstate.success_count + mstate.failure_count, 1),
                latency_score=0.0,
                cost_score=0.0,
                sample_size=mstate.success_count + mstate.failure_count,
            )
            return ModelReputation(
                provider=provider,
                model=model,
                reputation=rep,
            )

    async def metrics(self) -> dict[str, Any]:
        async with self._lock:
            windows_summary: dict[str, dict[str, float]] = {}
            for wname in _SLIDING_WINDOWS:
                windows_summary[wname] = {"active_windows": 0}

            return {
                "status": "started" if self._started else "stopped",
                "uptime_seconds": round(time.monotonic() - self._start_time, 2),
                "observations": self._observation_count,
                "enrich_count": self._enrich_count,
                "providers_tracked": len(self._providers),
                "models_tracked": len(self._models),
                "anomalies_detected": self._anomaly_count,
                "alerts_triggered": self._alert_count,
                "average_latency_ms": round(
                    self._total_latency / max(self._observation_count, 1), 2
                ),
                "average_cost": round(self._total_cost / max(self._observation_count, 1), 6),
                "records_stored": len(self._records),
                "windows": windows_summary,
            }

    # ── Private Helpers ──

    def _build_reputation_from_state(self, state: _ProviderLearningState) -> ReputationScore:
        return self._reputation_engine.compute_reputation(
            success_count=state.success_count,
            failure_count=state.failure_count,
            latency_score=1.0 - min(state.latency_ewma.value / max(state.max_latency, 1.0), 1.0)
            if state.max_latency > 0
            else 0.5,
            cost_score=1.0 - min(state.cost_ewma.value / max(state.max_cost, 0.001), 1.0)
            if state.max_cost > 0
            else 0.5,
            availability=state.availability,
            sample_size=state.success_count + state.failure_count,
        )

    def _build_adaptive_score(self, provider: str, model: str) -> AdaptiveScore:
        pstate = self._providers.get(provider)
        if pstate is None:
            return AdaptiveScore()
        rep = self._build_reputation_from_state(pstate)
        latency_trend = self._latency_trend_from_state(pstate)
        cost_trend = self._cost_trend_from_state(pstate)
        success_trend = SuccessTrend(
            current=pstate.success_ewma.value,
            ewma=pstate.success_ewma.value,
            direction=pstate.success_tracker.update(1.0 if pstate.success_count > 0 else 0.0),
        )
        failure_trend = FailureTrend(
            current=pstate.failure_ewma.value,
            ewma=pstate.failure_ewma.value,
            direction=pstate.failure_tracker.update(1.0 if pstate.failure_count > 0 else 0.0),
        )
        return self._adaptive_scorer.compute(
            reputation=rep,
            latency_trend=latency_trend,
            cost_trend=cost_trend,
            success_trend=success_trend,
            failure_trend=failure_trend,
            budget_efficiency=0.5,
        )

    def _latency_trend_from_state(self, state: _ProviderLearningState) -> LatencyTrend:
        min_l = state.min_latency if state.min_latency != float("inf") else 0.0
        return LatencyTrend(
            current=state.latency_ewma.value,
            ewma=state.latency_ewma.value,
            min=min_l,
            max=state.max_latency,
            variance=0.0,
            sample_count=state.latency_ewma.count,
            direction=state.latency_tracker.update(state.latency_ewma.value),
        )

    def _cost_trend_from_state(self, state: _ProviderLearningState) -> CostTrend:
        min_c = state.min_cost if state.min_cost != float("inf") else 0.0
        return CostTrend(
            current=state.cost_ewma.value,
            ewma=state.cost_ewma.value,
            min=min_c,
            max=state.max_cost,
            variance=0.0,
            sample_count=state.cost_ewma.count,
            direction=state.cost_tracker.update(state.cost_ewma.value),
        )

    def _build_provider_trend(self, state: _ProviderLearningState) -> ProviderTrend:
        return ProviderTrend(
            latency=self._latency_trend_from_state(state),
            cost=self._cost_trend_from_state(state),
            success=SuccessTrend(
                current=state.success_ewma.value,
                ewma=state.success_ewma.value,
                direction=state.success_tracker.update(1.0 if state.success_count > 0 else 0.0),
            ),
            failure=FailureTrend(
                current=state.failure_ewma.value,
                ewma=state.failure_ewma.value,
                direction=state.failure_tracker.update(1.0 if state.failure_count > 0 else 0.0),
            ),
        )

    async def _check_anomalies(self, provider: str, model: str) -> None:
        """Check for anomalies (degradation, recovery) and publish events."""
        async with self._lock:
            pstate = self._providers.get(provider)
            if pstate is None:
                return

            # Degradation detection: consecutive failures
            if pstate.consecutive_failures >= 5:
                self._anomaly_count += 1
                if self._event_bus is not None:
                    self._publish_event(
                        Topic.ANOMALY_DETECTED,
                        {
                            "provider": provider,
                            "model": model,
                            "type": "degradation",
                            "consecutive_failures": pstate.consecutive_failures,
                        },
                    )
                    self._publish_event(
                        Topic.MODEL_DEGRADED,
                        {
                            "provider": provider,
                            "model": model,
                            "consecutive_failures": pstate.consecutive_failures,
                        },
                    )
                    self._alert_count += 1

            # Recovery detection: after degradation, consecutive successes
            if pstate.consecutive_successes >= 3 and pstate.consecutive_failures == 0:
                if self._event_bus is not None:
                    self._publish_event(
                        Topic.MODEL_RECOVERED,
                        {
                            "provider": provider,
                            "model": model,
                            "consecutive_successes": pstate.consecutive_successes,
                        },
                    )

            # Score change detection (every 10 observations)
            total = pstate.success_count + pstate.failure_count
            if total > 0 and total % 10 == 0 and self._event_bus is not None:
                rep = self._build_reputation_from_state(pstate)
                self._publish_event(
                    Topic.REPUTATION_CHANGED,
                    {
                        "provider": provider,
                        "quality": rep.quality,
                        "confidence": rep.confidence,
                        "sample_size": rep.sample_size,
                    },
                )

    def _publish_event(self, topic: Topic, payload: dict[str, Any]) -> None:
        """Fire-and-forget async event publish."""
        if self._event_bus is None:
            return
        try:
            envelope = EventEnvelope(
                type="learning",
                source="adaptive_learning_engine",
                topic=topic.value,
                payload=payload,
            )
            asyncio.ensure_future(self._event_bus.publish(envelope))
        except Exception as exc:
            log.warning("Failed to publish learning event %s: %s", topic.value, exc)

    # ── Inspectable state for testing ──

    @property
    def provider_states(self) -> dict[str, _ProviderLearningState]:
        return dict(self._providers)

    @property
    def model_states(self) -> dict[str, _ModelLearningState]:
        return dict(self._models)

    @property
    def observation_count(self) -> int:
        return self._observation_count

    @property
    def anomaly_count(self) -> int:
        return self._anomaly_count


__all__ = [
    "AdaptiveLearningEngineImpl",
    "AdaptiveLearningEnginePort",
]
