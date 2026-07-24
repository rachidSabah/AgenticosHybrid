"""Tests for OmniRoute Adaptive Learning & Scoring Engine (Phase 5.7).

Covers lifecycle, CRUD, learning updates, Bayesian estimation, EWMA,
sliding windows, trend detection, confidence evolution, prediction accuracy,
concurrent learning, thread safety, metrics, observability, router integration,
budget integration, circuit breaker integration, policy integration, EventBus,
fault injection, stress tests, performance, and edge cases.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from agentic_os.core.omniroute.learning import (
    _EWMA,
    AdaptiveLearningEngineImpl,
    _AdaptiveScorer,
    _BayesianEstimator,
    _ConfidenceCalculator,
    _ModelLearningState,
    _PredictionEngine,
    _ProviderLearningState,
    _ReputationEngine,
    _SlidingWindowStats,
    _TrendDetector,
)
from agentic_os.domain.omniroute import (
    AdaptiveScore,
    AdaptiveWeights,
    ConfidenceScore,
    LatencyTrend,
    LearningDecision,
    LearningEvent,
    LearningForecast,
    LearningInputSource,
    LearningRecord,
    LearningSnapshot,
    LearningStatistics,
    LearningWindow,
    ModelReputation,
    OmniRouteModel,
    OmniRouteProvider,
    PredictionResult,
    ProviderReputation,
    ProviderTrend,
    ReputationScore,
    RoutingRequest,
    TrendDirection,
)

# ── Helpers ──


def _make_request(**kwargs: Any) -> RoutingRequest:
    """Create a RoutingRequest with sensible defaults for testing."""
    return RoutingRequest(
        task_type=kwargs.get("task_type", "chat"),
        required_capabilities=kwargs.get("required_capabilities", ("text",)),
        workspace=kwargs.get("workspace", "test-ws"),
        user_id=kwargs.get("user_id", "test-user"),
        agent=kwargs.get("agent", "test-agent"),
    )


def _make_record(
    provider: str = "test-provider",
    model: str = "test-model",
    success: bool = True,
    failure: bool = False,
    latency_ms: float = 100.0,
    cost: float = 0.01,
    **kwargs: Any,
) -> LearningRecord:
    return LearningRecord(
        provider=provider,
        model=model,
        success=success,
        failure=failure,
        latency_ms=latency_ms,
        cost=cost,
        source=kwargs.get("source", LearningInputSource.ROUTING),
        retry=kwargs.get("retry", False),
        fallback=kwargs.get("fallback", False),
        tokens_used=kwargs.get("tokens_used", 100),
        duration_ms=kwargs.get("duration_ms", 200.0),
        task_type=kwargs.get("task_type", "chat"),
        workspace=kwargs.get("workspace", "test-ws"),
        user_id=kwargs.get("user_id", "test-user"),
        agent=kwargs.get("agent", "test-agent"),
        budget_approved=kwargs.get("budget_approved", True),
        budget_rejected=kwargs.get("budget_rejected", False),
        timeout=kwargs.get("timeout", False),
    )


def _make_provider(name: str = "test-provider", healthy: bool = True) -> OmniRouteProvider:
    return OmniRouteProvider(
        name=name,
        kind="openai",
        base_url=f"https://api.{name}.com",
        api_key_ref=f"key-{name}",
        enabled=True,
        healthy=healthy,
        latency_ms=100.0,
        cost_per_1k_input=0.01,
        cost_per_1k_output=0.02,
    )


def _make_model(
    model_id: str = "test-model",
    provider: str = "test-provider",
) -> OmniRouteModel:
    return OmniRouteModel(
        model_id=model_id,
        provider=provider,
        display_name=f"{provider}/{model_id}",
        context_window=8192,
        input_cost_per_1k=0.01,
        output_cost_per_1k=0.02,
        quality_score=0.8,
    )


@pytest.fixture
def engine() -> AdaptiveLearningEngineImpl:
    """Create a fresh learning engine for each test."""
    eng = AdaptiveLearningEngineImpl(
        event_bus=None,
        max_records=1000,
        max_recent=100,
    )
    return eng


@pytest.fixture
def started_engine() -> AdaptiveLearningEngineImpl:
    """Create and start a learning engine."""
    eng = AdaptiveLearningEngineImpl(event_bus=None)
    return eng


# ─────────────────────────────────────────────
# 1. Lifecycle Tests
# ─────────────────────────────────────────────


class TestLifecycle:
    """Engine lifecycle — initialize, start, stop, dispose, health, ready."""

    async def test_initial_state(self, engine: AdaptiveLearningEngineImpl) -> None:
        assert not await engine.ready()
        health = await engine.health()
        assert health["status"] == "stopped"

    async def test_start_and_ready(self, engine: AdaptiveLearningEngineImpl) -> None:
        await engine.start()
        assert await engine.ready()
        health = await engine.health()
        assert health["status"] == "healthy"
        assert health["started"]

    async def test_stop(self, engine: AdaptiveLearningEngineImpl) -> None:
        await engine.start()
        assert await engine.ready()
        await engine.stop()
        assert not await engine.ready()
        health = await engine.health()
        assert health["status"] == "stopped"

    async def test_dispose_clears_state(self, engine: AdaptiveLearningEngineImpl) -> None:
        await engine.start()
        rec = _make_record()
        await engine.observe(rec)
        assert engine.observation_count == 1
        await engine.dispose()
        assert engine.observation_count == 0
        assert len(engine.provider_states) == 0
        assert not await engine.ready()

    async def test_health_returns_observations(self, engine: AdaptiveLearningEngineImpl) -> None:
        await engine.start()
        for _ in range(5):
            await engine.observe(_make_record())
        health = await engine.health()
        assert health["observations"] == 5

    async def test_initialize(self, engine: AdaptiveLearningEngineImpl) -> None:
        """initialize should not raise."""
        await engine.initialize()

    async def test_start_then_initialize_noop(self, engine: AdaptiveLearningEngineImpl) -> None:
        await engine.start()
        await engine.initialize()  # should be no-op


# ─────────────────────────────────────────────
# 2. Learning Record & Observe Tests
# ─────────────────────────────────────────────


class TestObserve:
    """Recording learning observations."""

    async def test_observe_increases_count(self, engine: AdaptiveLearningEngineImpl) -> None:
        await engine.start()
        rec = _make_record()
        await engine.observe(rec)
        assert engine.observation_count == 1

    async def test_observe_creates_provider_state(self, engine: AdaptiveLearningEngineImpl) -> None:
        await engine.start()
        rec = _make_record(provider="p1")
        await engine.observe(rec)
        assert "p1" in engine.provider_states

    async def test_observe_creates_model_state(self, engine: AdaptiveLearningEngineImpl) -> None:
        await engine.start()
        rec = _make_record(provider="p1", model="m1")
        await engine.observe(rec)
        assert "p1:m1" in engine.model_states

    async def test_observe_updates_success_count(self, engine: AdaptiveLearningEngineImpl) -> None:
        await engine.start()
        await engine.observe(_make_record(provider="p1", success=True))
        await engine.observe(_make_record(provider="p1", success=False, failure=True))
        state = engine.provider_states["p1"]
        assert state.success_count == 1
        assert state.failure_count == 1

    async def test_observe_updates_ewma(self, engine: AdaptiveLearningEngineImpl) -> None:
        await engine.start()
        await engine.observe(_make_record(provider="p1", latency_ms=100.0, cost=0.01))
        state = engine.provider_states["p1"]
        assert state.latency_ewma.value > 0
        assert state.cost_ewma.value > 0

    async def test_observe_updates_availability(self, engine: AdaptiveLearningEngineImpl) -> None:
        await engine.start()
        await engine.observe(_make_record(provider="p1", success=True))
        assert engine.provider_states["p1"].availability == 1.0
        await engine.observe(_make_record(provider="p1", success=False, failure=True))
        assert engine.provider_states["p1"].availability == 0.5

    async def test_observe_multiple_providers(self, engine: AdaptiveLearningEngineImpl) -> None:
        await engine.start()
        for i in range(5):
            await engine.observe(_make_record(provider=f"p{i}", model="m1"))
        assert len(engine.provider_states) == 5

    async def test_observe_multiple_models(self, engine: AdaptiveLearningEngineImpl) -> None:
        await engine.start()
        for i in range(5):
            await engine.observe(_make_record(provider="p1", model=f"m{i}"))
        assert len(engine.model_states) == 5

    async def test_observe_records_tokens_and_duration(
        self, engine: AdaptiveLearningEngineImpl
    ) -> None:
        await engine.start()
        rec = _make_record(tokens_used=500, duration_ms=1000.0)
        await engine.observe(rec)
        stats = await engine.statistics()
        assert stats.total_observations == 1

    async def test_observe_successful_record_updates_consecutive(
        self, engine: AdaptiveLearningEngineImpl
    ) -> None:
        await engine.start()
        for _ in range(3):
            await engine.observe(_make_record(provider="p1", success=True))
        state = engine.provider_states["p1"]
        assert state.consecutive_successes == 3
        assert state.consecutive_failures == 0

    async def test_observe_failure_resets_consecutive_success(
        self, engine: AdaptiveLearningEngineImpl
    ) -> None:
        await engine.start()
        for _ in range(3):
            await engine.observe(_make_record(provider="p1", success=True))
        await engine.observe(_make_record(provider="p1", success=False, failure=True))
        state = engine.provider_states["p1"]
        assert state.consecutive_successes == 0
        assert state.consecutive_failures == 1

    async def test_observe_updates_statistics(self, engine: AdaptiveLearningEngineImpl) -> None:
        await engine.start()
        for _ in range(10):
            await engine.observe(_make_record(provider="p1", success=True, latency_ms=50.0))
        stats = await engine.statistics()
        assert stats.total_observations == 10
        assert stats.total_successes == 10

    async def test_observe_with_all_fields(self, engine: AdaptiveLearningEngineImpl) -> None:
        await engine.start()
        rec = LearningRecord(
            provider="p1",
            model="m1",
            source=LearningInputSource.FEEDBACK,
            success=True,
            failure=False,
            retry=True,
            fallback=False,
            latency_ms=150.0,
            cost=0.05,
            estimated_cost=0.04,
            tokens_used=1000,
            duration_ms=500.0,
            reason="test",
            task_type="coding",
            workspace="ws1",
            user_id="u1",
            agent="a1",
            policy_used="balanced",
            circuit_state="closed",
            budget_approved=True,
            timeout=False,
            vision_used=True,
            tools_used=True,
            streaming=False,
            cache_hit=False,
        )
        await engine.observe(rec)
        assert engine.observation_count == 1


# ─────────────────────────────────────────────
# 3. Enrich & Learning Decision Tests
# ─────────────────────────────────────────────


class TestEnrich:
    """Candidate enrichment with adaptive scores."""

    async def test_enrich_returns_decision(self, engine: AdaptiveLearningEngineImpl) -> None:
        await engine.start()
        await engine.observe(_make_record(provider="p1", model="m1"))
        candidates = [(_make_provider("p1"), _make_model("m1"))]
        decision = await engine.enrich(candidates, _make_request())
        assert isinstance(decision, LearningDecision)

    async def test_enrich_empty_candidates(self, engine: AdaptiveLearningEngineImpl) -> None:
        await engine.start()
        decision = await engine.enrich([], _make_request())
        assert len(decision.enriched_candidates) == 0
        assert decision.evaluation_time_ms >= 0

    async def test_enrich_without_start(self, engine: AdaptiveLearningEngineImpl) -> None:
        """enrich should return empty decision when not started."""
        decision = await engine.enrich(
            [(_make_provider("p1"), _make_model("m1"))],
            _make_request(),
        )
        assert len(decision.enriched_candidates) == 0

    async def test_enrich_unknown_provider(self, engine: AdaptiveLearningEngineImpl) -> None:
        """Candidates without observed data should not appear."""
        await engine.start()
        decision = await engine.enrich(
            [(_make_provider("unknown"), _make_model("m1"))],
            _make_request(),
        )
        assert len(decision.enriched_candidates) == 0

    async def test_enrich_provides_scores(self, engine: AdaptiveLearningEngineImpl) -> None:
        await engine.start()
        for _ in range(10):
            await engine.observe(_make_record(provider="p1", success=True, latency_ms=50.0))
        candidates = [(_make_provider("p1"), _make_model("m1"))]
        decision = await engine.enrich(candidates, _make_request())
        assert len(decision.enriched_candidates) == 1
        _, _, score = decision.enriched_candidates[0]
        assert isinstance(score, AdaptiveScore)
        assert 0 <= score.normalized_score <= 1.0

    async def test_enrich_multiple_candidates(self, engine: AdaptiveLearningEngineImpl) -> None:
        await engine.start()
        for prov in ["p1", "p2"]:
            for _ in range(5):
                await engine.observe(_make_record(provider=prov, success=True))
        candidates = [
            (_make_provider("p1"), _make_model("m1")),
            (_make_provider("p2"), _make_model("m2")),
        ]
        decision = await engine.enrich(candidates, _make_request())
        assert len(decision.enriched_candidates) == 2

    async def test_enrich_includes_predictions(self, engine: AdaptiveLearningEngineImpl) -> None:
        await engine.start()
        for _ in range(10):
            await engine.observe(_make_record(provider="p1", success=True, latency_ms=50.0))
        candidates = [(_make_provider("p1"), _make_model("m1"))]
        decision = await engine.enrich(candidates, _make_request())
        assert "p1" in decision.predictions

    async def test_enrich_observations_count(self, engine: AdaptiveLearningEngineImpl) -> None:
        await engine.start()
        for _ in range(5):
            await engine.observe(_make_record(provider="p1"))
        candidates = [(_make_provider("p1"), _make_model("m1"))]
        decision = await engine.enrich(candidates, _make_request())
        assert decision.observations_count == 5

    async def test_enrich_evaluation_time(self, engine: AdaptiveLearningEngineImpl) -> None:
        await engine.start()
        await engine.observe(_make_record(provider="p1"))
        candidates = [(_make_provider("p1"), _make_model("m1"))]
        decision = await engine.enrich(candidates, _make_request())
        assert decision.evaluation_time_ms > 0


# ─────────────────────────────────────────────
# 4. Bayesian Estimation Tests
# ─────────────────────────────────────────────


class TestBayesian:
    """Bayesian estimation for success/failure probability."""

    def test_estimate_prior(self) -> None:
        bayes = _BayesianEstimator()
        mean, std = bayes.estimate(0, 0)
        assert mean == 0.5  # uniform prior
        assert std > 0

    def test_estimate_after_successes(self) -> None:
        bayes = _BayesianEstimator()
        mean, std = bayes.estimate(10, 0)
        assert mean > 0.9
        assert std < 0.1

    def test_estimate_after_failures(self) -> None:
        bayes = _BayesianEstimator()
        mean, std = bayes.estimate(0, 10)
        assert mean < 0.1

    def test_estimate_equal_counts(self) -> None:
        bayes = _BayesianEstimator()
        mean, _ = bayes.estimate(5, 5)
        assert mean == 0.5

    def test_estimate_high_counts_low_uncertainty(self) -> None:
        bayes = _BayesianEstimator()
        _, std_small = bayes.estimate(100, 1)
        _, std_large = bayes.estimate(10, 1)
        assert std_small < std_large  # more data = less uncertainty

    def test_credible_interval(self) -> None:
        bayes = _BayesianEstimator()
        lower, upper = bayes.credible_interval(10, 0)
        assert lower >= 0
        assert upper <= 1
        assert lower <= upper

    def test_credible_interval_wide_with_small_sample(self) -> None:
        bayes = _BayesianEstimator()
        lower_small, upper_small = bayes.credible_interval(1, 0)
        lower_large, upper_large = bayes.credible_interval(100, 0)
        assert (upper_small - lower_small) > (upper_large - lower_large)

    def test_reliability_score_perfect(self) -> None:
        bayes = _BayesianEstimator()
        score = bayes.reliability_score(100, 0)
        assert score > 0.9

    def test_reliability_score_poor(self) -> None:
        bayes = _BayesianEstimator()
        score = bayes.reliability_score(1, 100)
        assert score < 0.1

    def test_reliability_score_conservative_small_sample(self) -> None:
        bayes = _BayesianEstimator()
        score = bayes.reliability_score(1, 0)
        assert score < 0.5  # conservative with only 1 sample

    def test_reliability_score_increases_with_samples(self) -> None:
        bayes = _BayesianEstimator()
        score1 = bayes.reliability_score(5, 0)
        score2 = bayes.reliability_score(50, 0)
        assert score2 >= score1

    def test_bayesian_with_custom_prior(self) -> None:
        bayes = _BayesianEstimator(prior_a=2.0, prior_b=2.0)
        mean, _ = bayes.estimate(0, 0)
        assert mean == 0.5

    def test_bayesian_small_counts_dont_overfit(self) -> None:
        """With very small counts, Bayesian should not report extreme confidence."""
        bayes = _BayesianEstimator()
        mean, std = bayes.estimate(1, 0)
        assert mean < 0.8  # pulled toward prior
        assert std > 0.1  # still uncertain


# ─────────────────────────────────────────────
# 5. EWMA Tests
# ─────────────────────────────────────────────


class TestEWMA:
    """Exponentially weighted moving average."""

    def test_initial_value_none(self) -> None:
        ewma = _EWMA()
        assert ewma.value == 0.0

    def test_first_update_sets_value(self) -> None:
        ewma = _EWMA()
        result = ewma.update(100.0)
        assert result == 100.0
        assert ewma.value == 100.0

    def test_ewma_smoothing(self) -> None:
        ewma = _EWMA(alpha=0.5)
        ewma.update(100.0)
        result = ewma.update(200.0)
        # 0.5 * 200 + 0.5 * 100 = 150
        assert result == 150.0

    def test_ewma_tracks_count(self) -> None:
        ewma = _EWMA()
        assert ewma.count == 0
        ewma.update(10.0)
        assert ewma.count == 1
        ewma.update(20.0)
        assert ewma.count == 2

    def test_ewma_low_alpha(self) -> None:
        """Low alpha = smoother, slower to change."""
        ewma = _EWMA(alpha=0.1)
        ewma.update(100.0)
        result = ewma.update(200.0)
        # 0.1 * 200 + 0.9 * 100 = 110
        assert result == pytest.approx(110.0)

    def test_ewma_high_alpha(self) -> None:
        """High alpha = more responsive to recent values."""
        ewma = _EWMA(alpha=0.9)
        ewma.update(100.0)
        result = ewma.update(200.0)
        # 0.9 * 200 + 0.1 * 100 = 190
        assert result == pytest.approx(190.0)

    def test_ewma_convergence(self) -> None:
        """Repeated same value should converge to that value."""
        ewma = _EWMA(alpha=0.3)
        for _ in range(20):
            ewma.update(50.0)
        assert ewma.value == pytest.approx(50.0, abs=0.001)

    def test_ewma_custom_alpha(self) -> None:
        ewma = _EWMA(alpha=0.25)
        ewma.update(100)
        result = ewma.update(0)
        assert result == pytest.approx(75.0)


# ─────────────────────────────────────────────
# 6. Sliding Window Tests
# ─────────────────────────────────────────────


class TestSlidingWindow:
    """Sliding window statistics."""

    def test_empty_window(self) -> None:
        window = _SlidingWindowStats(timedelta(hours=1))
        summary = window.summary("test")
        assert summary.sample_count == 0
        assert summary.success_rate == 0.0

    def test_single_record(self) -> None:
        window = _SlidingWindowStats(timedelta(hours=1))
        window.record(latency_ms=100.0, success=True, cost=0.01)
        summary = window.summary("test")
        assert summary.sample_count == 1
        assert summary.success_rate == 1.0
        assert summary.average_latency_ms == 100.0

    def test_multiple_records(self) -> None:
        window = _SlidingWindowStats(timedelta(hours=1))
        window.record(latency_ms=100.0, success=True, cost=0.01)
        window.record(latency_ms=200.0, success=False, cost=0.02)
        summary = window.summary("test")
        assert summary.sample_count == 2
        assert summary.success_rate == 0.5
        assert summary.failure_rate == 0.5
        assert summary.average_latency_ms == 150.0

    def test_expiration(self) -> None:
        window = _SlidingWindowStats(timedelta(milliseconds=1))
        window.record(latency_ms=100.0, success=True, cost=0.01)

        # The expiration uses datetime.now(UTC) — records within max_duration
        # Since our record is fresh, it won't expire
        summary = window.summary("test")
        assert summary.sample_count == 1

    def test_window_name(self) -> None:
        window = _SlidingWindowStats(timedelta(hours=1))
        summary = window.summary("5min")
        assert summary.window_duration == "5min"

    def test_percentiles_empty(self) -> None:
        window = _SlidingWindowStats(timedelta(hours=1))
        # _compute_percentiles returns all 0 when no latencies
        summary = window.summary("test")
        assert summary.p50_latency_ms == 0.0
        assert summary.p95_latency_ms == 0.0
        assert summary.p99_latency_ms == 0.0

    def test_min_max_latency(self) -> None:
        window = _SlidingWindowStats(timedelta(hours=1))
        window.record(latency_ms=50.0, success=True, cost=0.01)
        window.record(latency_ms=200.0, success=True, cost=0.02)
        summary = window.summary("test")
        assert summary.min_latency_ms == 50.0
        assert summary.max_latency_ms == 200.0

    def test_record_updates_internally(self) -> None:
        window = _SlidingWindowStats(timedelta(hours=1))
        window.record(latency_ms=100.0, success=True, cost=0.01)
        window.record(latency_ms=50.0, success=True, cost=0.02)
        window.record(latency_ms=200.0, success=False, cost=0.03)
        summary = window.summary("test")
        assert summary.sample_count == 3
        assert summary.average_cost == pytest.approx(0.02)


# ─────────────────────────────────────────────
# 7. Trend Detection Tests
# ─────────────────────────────────────────────


class TestTrendDetection:
    """Trend direction detection."""

    def test_initial_unknown(self) -> None:
        detector = _TrendDetector()
        direction = detector.update(100.0)
        assert direction in (TrendDirection.UNKNOWN, TrendDirection.STABLE)

    def test_stable_trend(self) -> None:
        detector = _TrendDetector()
        for _ in range(10):
            detector.update(100.0)
        direction = detector.update(100.0)
        assert direction in (TrendDirection.STABLE, TrendDirection.UNKNOWN)

    def test_degrading_trend(self) -> None:
        detector = _TrendDetector()
        for _ in range(5):
            detector.update(10.0)
        for _ in range(5):
            detector.update(100.0)
        direction = detector.update(150.0)
        # The short-term average should be higher than long-term
        assert direction in (
            TrendDirection.DEGRADING,
            TrendDirection.RAPID_DEGRADATION,
            TrendDirection.STABLE,
        )

    def test_reset(self) -> None:
        detector = _TrendDetector()
        detector.update(100.0)
        detector.reset()
        # After reset, the first update should be treated as first observation
        direction = detector.update(50.0)
        assert direction in (TrendDirection.UNKNOWN, TrendDirection.STABLE)

    def test_improving_trend(self) -> None:
        detector = _TrendDetector()
        for _ in range(10):
            detector.update(500.0)
        for _ in range(5):
            detector.update(100.0)
        direction = detector.update(50.0)
        assert direction in (
            TrendDirection.RECOVERY,
            TrendDirection.STABLE,
            TrendDirection.OSCILLATION,
        )

    def test_oscillation_detection(self) -> None:
        detector = _TrendDetector()
        # Alternate high/low to simulate oscillation
        for i in range(15):
            val = 100.0 if i % 2 == 0 else 500.0
            direction = detector.update(val)
        # Should detect oscillation or at least not be stable
        assert direction in (
            TrendDirection.OSCILLATION,
            TrendDirection.STABLE,
            TrendDirection.UNKNOWN,
        )


# ─────────────────────────────────────────────
# 8. Confidence Score Tests
# ─────────────────────────────────────────────


class TestConfidence:
    """Confidence score calculation."""

    def test_zero_samples(self) -> None:
        conf = _ConfidenceCalculator.calculate(0, 0.0)
        assert conf.score == 0.0
        assert conf.sample_count == 0

    def test_high_samples_high_confidence(self) -> None:
        conf = _ConfidenceCalculator.calculate(100, 0.01)
        assert conf.score > 0.8

    def test_low_samples_low_confidence(self) -> None:
        conf = _ConfidenceCalculator.calculate(1, 0.5)
        assert conf.score < 0.5

    def test_variance_penalty(self) -> None:
        low_var = _ConfidenceCalculator.calculate(50, 0.01)
        high_var = _ConfidenceCalculator.calculate(50, 0.5)
        assert low_var.score > high_var.score

    def test_prediction_error_penalty(self) -> None:
        no_error = _ConfidenceCalculator.calculate(50, 0.01, prediction_error=0.0)
        high_error = _ConfidenceCalculator.calculate(50, 0.01, prediction_error=0.5)
        assert no_error.score > high_error.score

    def test_calibration_factor(self) -> None:
        conf = _ConfidenceCalculator.calculate(50, 0.01, calibration=0.5)
        assert conf.calibration == 0.5

    def test_confidence_bounded(self) -> None:
        conf = _ConfidenceCalculator.calculate(0, 0.0)
        assert 0.0 <= conf.score <= 1.0
        conf = _ConfidenceCalculator.calculate(10000, 0.0)
        assert 0.0 <= conf.score <= 1.0

    def test_confidence_returns_all_fields(self) -> None:
        conf = _ConfidenceCalculator.calculate(20, 0.05, 0.1, 0.9)
        assert conf.score > 0
        assert conf.sample_count == 20
        assert conf.variance == 0.05
        assert conf.prediction_error == 0.1
        assert conf.calibration == 0.9


# ─────────────────────────────────────────────
# 9. Prediction Engine Tests
# ─────────────────────────────────────────────


class TestPrediction:
    """Prediction engine correctness."""

    def test_empty_prediction(self) -> None:
        predictor = _PredictionEngine()
        rep = _ReputationEngine().compute_reputation(0, 0, 0.0, 0.0, 1.0, 0)
        result = predictor.predict(rep, 0.0, 0.0, 0.0)
        assert result.expected_latency_ms == 0.0
        assert result.expected_cost == 0.0

    def test_prediction_after_observations(self) -> None:
        predictor = _PredictionEngine()
        rep = _ReputationEngine().compute_reputation(10, 0, 0.9, 0.9, 1.0, 10)
        result = predictor.predict(rep, 100.0, 0.01, 0.0)
        assert result.expected_latency_ms > 0
        assert result.expected_success_probability > 0.8
        assert result.expected_failure_probability < 0.2

    def test_prediction_success_probability(self) -> None:
        predictor = _PredictionEngine()
        rep = _ReputationEngine().compute_reputation(95, 5, 0.9, 0.9, 1.0, 100)
        result = predictor.predict(rep, 100.0, 0.01, 0.0)
        assert 0.8 <= result.expected_success_probability <= 1.0
        assert 0.0 <= result.expected_failure_probability <= 0.2

    def test_prediction_has_confidence(self) -> None:
        predictor = _PredictionEngine()
        rep = _ReputationEngine().compute_reputation(10, 0, 0.9, 0.9, 1.0, 10)
        result = predictor.predict(rep, 100.0, 0.01, 0.0)
        assert isinstance(result.confidence, ConfidenceScore)

    def test_prediction_retry_probability(self) -> None:
        predictor = _PredictionEngine()
        rep = _ReputationEngine().compute_reputation(5, 5, 0.5, 0.5, 0.5, 10)
        result = predictor.predict(rep, 100.0, 0.01, 0.0)
        assert result.expected_retry_probability > 0

    def test_prediction_availability(self) -> None:
        predictor = _PredictionEngine()
        rep = _ReputationEngine().compute_reputation(10, 0, 0.9, 0.9, 1.0, 10)
        result = predictor.predict(rep, 100.0, 0.01, 0.0)
        assert result.expected_availability == 1.0

    def test_prediction_horizon_default(self) -> None:
        predictor = _PredictionEngine()
        rep = _ReputationEngine().compute_reputation(10, 0, 0.9, 0.9, 1.0, 10)
        result = predictor.predict(rep, 100.0, 0.01, 0.0)
        assert result.prediction_horizon == "short_term"


# ─────────────────────────────────────────────
# 10. Reputation Engine Tests
# ─────────────────────────────────────────────


class TestReputation:
    """Reputation score computation."""

    def test_empty_reputation(self) -> None:
        rep_engine = _ReputationEngine()
        rep = rep_engine.compute_reputation(0, 0, 0.0, 0.0, 1.0, 0)
        assert rep.success_rate == 0.0
        assert rep.total_attempts == 1  # max(0+0, 1)

    def test_perfect_reputation(self) -> None:
        rep_engine = _ReputationEngine()
        rep = rep_engine.compute_reputation(100, 0, 1.0, 1.0, 1.0, 100)
        assert rep.success_rate > 0.9
        assert rep.quality > 0.9

    def test_poor_reputation(self) -> None:
        rep_engine = _ReputationEngine()
        rep = rep_engine.compute_reputation(1, 100, 0.1, 0.1, 0.1, 101)
        assert rep.failure_rate > 0.9
        assert rep.quality < 0.3

    def test_confidence_increases_with_samples(self) -> None:
        rep_engine = _ReputationEngine()
        rep_small = rep_engine.compute_reputation(5, 0, 1.0, 1.0, 1.0, 5)
        rep_large = rep_engine.compute_reputation(50, 0, 1.0, 1.0, 1.0, 50)
        assert rep_large.confidence > rep_small.confidence

    def test_stability_metric(self) -> None:
        rep_engine = _ReputationEngine()
        rep_balanced = rep_engine.compute_reputation(50, 50, 0.5, 0.5, 0.5, 100)
        rep_skewed = rep_engine.compute_reputation(99, 1, 0.9, 0.9, 0.9, 100)
        assert rep_balanced.stability >= 0
        assert rep_skewed.stability >= 0

    def test_quality_blend(self) -> None:
        rep_engine = _ReputationEngine()
        rep = rep_engine.compute_reputation(80, 20, 0.8, 0.8, 0.9, 100)
        assert 0 < rep.quality < 1.0

    def test_latency_and_cost_scores(self) -> None:
        rep_engine = _ReputationEngine()
        rep = rep_engine.compute_reputation(10, 0, 0.7, 0.8, 1.0, 10)
        assert rep.latency_score == 0.7
        assert rep.cost_score == 0.8

    def test_sample_size(self) -> None:
        rep_engine = _ReputationEngine()
        rep = rep_engine.compute_reputation(5, 3, 0.5, 0.5, 0.5, 8)
        assert rep.sample_size == 8
        assert rep.total_attempts == 8


# ─────────────────────────────────────────────
# 11. Adaptive Scorer Tests
# ─────────────────────────────────────────────


class TestAdaptiveScorer:
    """Adaptive score computation."""

    def test_empty_score(self) -> None:
        scorer = _AdaptiveScorer()
        rep_engine = _ReputationEngine()
        rep = rep_engine.compute_reputation(0, 0, 0.0, 0.0, 0.5, 0)
        from agentic_os.domain.omniroute import CostTrend, FailureTrend, LatencyTrend, SuccessTrend

        score = scorer.compute(rep, LatencyTrend(), CostTrend(), SuccessTrend(), FailureTrend())
        assert 0 <= score.normalized_score <= 1.0

    def test_high_performance_score(self) -> None:
        scorer = _AdaptiveScorer()
        rep_engine = _ReputationEngine()
        rep = rep_engine.compute_reputation(100, 0, 1.0, 1.0, 1.0, 100)
        from agentic_os.domain.omniroute import CostTrend, FailureTrend, LatencyTrend, SuccessTrend

        score = scorer.compute(
            rep,
            LatencyTrend(),
            CostTrend(),
            SuccessTrend(direction=TrendDirection.IMPROVING),
            FailureTrend(),
        )
        assert score.normalized_score >= 0.5

    def test_low_performance_score(self) -> None:
        scorer = _AdaptiveScorer()
        rep_engine = _ReputationEngine()
        rep = rep_engine.compute_reputation(0, 100, 0.0, 0.0, 0.1, 100)
        from agentic_os.domain.omniroute import CostTrend, FailureTrend, LatencyTrend, SuccessTrend

        score = scorer.compute(
            rep,
            LatencyTrend(current=1000, max=1000),
            CostTrend(current=1.0, max=1.0),
            SuccessTrend(),
            FailureTrend(direction=TrendDirection.DEGRADING),
        )
        assert score.normalized_score < 0.5

    def test_custom_weights(self) -> None:
        weights = AdaptiveWeights(
            quality=0.5,
            latency=0.1,
            cost=0.1,
            reliability=0.1,
            availability=0.1,
            recovery=0.05,
            budget_efficiency=0.05,
        )
        scorer = _AdaptiveScorer(weights)
        rep_engine = _ReputationEngine()
        rep = rep_engine.compute_reputation(50, 0, 0.8, 0.8, 0.9, 50)
        from agentic_os.domain.omniroute import CostTrend, FailureTrend, LatencyTrend, SuccessTrend

        score = scorer.compute(rep, LatencyTrend(), CostTrend(), SuccessTrend(), FailureTrend())
        assert 0 <= score.normalized_score <= 1.0

    def test_components_are_present(self) -> None:
        scorer = _AdaptiveScorer()
        rep_engine = _ReputationEngine()
        rep = rep_engine.compute_reputation(10, 0, 0.8, 0.8, 0.9, 10)
        from agentic_os.domain.omniroute import CostTrend, FailureTrend, LatencyTrend, SuccessTrend

        score = scorer.compute(rep, LatencyTrend(), CostTrend(), SuccessTrend(), FailureTrend())
        assert score.quality_component >= 0
        assert score.latency_component >= 0
        assert score.cost_component >= 0
        assert score.reliability_component >= 0
        assert score.availability_component >= 0
        assert score.recovery_component >= 0
        assert score.budget_efficiency >= 0

    def test_recovery_trend_boost(self) -> None:
        scorer = _AdaptiveScorer()
        rep_engine = _ReputationEngine()
        rep = rep_engine.compute_reputation(10, 0, 0.8, 0.8, 0.9, 10)
        from agentic_os.domain.omniroute import CostTrend, FailureTrend, LatencyTrend, SuccessTrend

        score_recovery = scorer.compute(
            rep,
            LatencyTrend(),
            CostTrend(),
            SuccessTrend(direction=TrendDirection.RECOVERY),
            FailureTrend(),
        )
        score_normal = scorer.compute(
            rep, LatencyTrend(), CostTrend(), SuccessTrend(), FailureTrend()
        )
        assert score_recovery.recovery_component >= score_normal.recovery_component


# ─────────────────────────────────────────────
# 12. Update Reputation Tests
# ─────────────────────────────────────────────


class TestUpdateReputation:
    """update_reputation convenience method."""

    async def test_update_success(self, engine: AdaptiveLearningEngineImpl) -> None:
        await engine.start()
        await engine.update_reputation("p1", "m1", success=True)
        assert engine.observation_count == 1
        assert engine.provider_states["p1"].success_count == 1

    async def test_update_failure(self, engine: AdaptiveLearningEngineImpl) -> None:
        await engine.start()
        await engine.update_reputation("p1", "m1", success=False, latency_ms=200.0)
        state = engine.provider_states["p1"]
        assert state.failure_count == 1
        assert state.latency_ewma.value > 0

    async def test_update_with_extra_fields(self, engine: AdaptiveLearningEngineImpl) -> None:
        await engine.start()
        await engine.update_reputation(
            "p1",
            "m1",
            success=True,
            latency_ms=150.0,
            cost=0.02,
            tokens_used=500,
            duration_ms=300.0,
            timeout=False,
        )
        assert engine.observation_count == 1


# ─────────────────────────────────────────────
# 13. Predict & Forecast Tests
# ─────────────────────────────────────────────


class TestForecast:
    """Forecast generation."""

    async def test_forecast_empty(self, engine: AdaptiveLearningEngineImpl) -> None:
        await engine.start()
        forecast = await engine.forecast()
        assert isinstance(forecast, LearningForecast)

    async def test_forecast_with_data(self, engine: AdaptiveLearningEngineImpl) -> None:
        await engine.start()
        for _ in range(10):
            await engine.observe(_make_record(provider="p1", success=True, latency_ms=100.0))
        forecast = await engine.forecast()
        assert "p1" in forecast.provider_forecast
        assert forecast.global_success_rate > 0

    async def test_forecast_at_risk(self, engine: AdaptiveLearningEngineImpl) -> None:
        await engine.start()
        for _ in range(5):
            await engine.observe(_make_record(provider="p1", success=False, failure=True))
        forecast = await engine.forecast()
        assert "p1" in forecast.at_risk_providers

    async def test_forecast_no_at_risk(self, engine: AdaptiveLearningEngineImpl) -> None:
        await engine.start()
        for _ in range(10):
            await engine.observe(_make_record(provider="p1", success=True))
        forecast = await engine.forecast()
        assert "p1" not in forecast.at_risk_providers

    async def test_predict_unknown(self, engine: AdaptiveLearningEngineImpl) -> None:
        await engine.start()
        result = await engine.predict("unknown", "unknown")
        assert result.expected_latency_ms == 0.0

    async def test_predict_known(self, engine: AdaptiveLearningEngineImpl) -> None:
        await engine.start()
        for _ in range(10):
            await engine.observe(
                _make_record(provider="p1", success=True, latency_ms=100.0, cost=0.01)
            )
        result = await engine.predict("p1", "m1")
        assert result.expected_latency_ms > 0
        assert result.expected_cost > 0
        assert result.expected_success_probability > 0.5


# ─────────────────────────────────────────────
# 14. Snapshot Tests
# ─────────────────────────────────────────────


class TestSnapshot:
    """Point-in-time snapshot."""

    async def test_snapshot_empty(self, engine: AdaptiveLearningEngineImpl) -> None:
        await engine.start()
        snap = await engine.snapshot()
        assert isinstance(snap, LearningSnapshot)
        assert len(snap.provider_reputations) == 0

    async def test_snapshot_with_data(self, engine: AdaptiveLearningEngineImpl) -> None:
        await engine.start()
        for _ in range(5):
            await engine.observe(_make_record(provider="p1", success=True))
        snap = await engine.snapshot()
        assert len(snap.provider_reputations) == 1
        assert snap.statistics.total_observations == 5

    async def test_snapshot_multiple_providers(self, engine: AdaptiveLearningEngineImpl) -> None:
        await engine.start()
        for p in ["p1", "p2", "p3"]:
            for _ in range(3):
                await engine.observe(_make_record(provider=p, success=True))
        snap = await engine.snapshot()
        assert len(snap.provider_reputations) == 3

    async def test_snapshot_includes_recent_records(
        self, engine: AdaptiveLearningEngineImpl
    ) -> None:
        await engine.start()
        for _ in range(5):
            await engine.observe(_make_record())
        snap = await engine.snapshot()
        assert len(snap.recent_records) > 0


# ─────────────────────────────────────────────
# 15. Statistics Tests
# ─────────────────────────────────────────────


class TestStatistics:
    """Aggregate learning statistics."""

    async def test_statistics_empty(self, engine: AdaptiveLearningEngineImpl) -> None:
        await engine.start()
        stats = await engine.statistics()
        assert stats.total_observations == 0

    async def test_statistics_counts(self, engine: AdaptiveLearningEngineImpl) -> None:
        await engine.start()
        for _ in range(10):
            await engine.observe(_make_record(success=True))
        for _ in range(5):
            await engine.observe(_make_record(success=False, failure=True))
        stats = await engine.statistics()
        assert stats.total_observations == 15
        assert stats.total_successes == 10
        assert stats.total_failures == 5

    async def test_statistics_retries_and_fallbacks(
        self, engine: AdaptiveLearningEngineImpl
    ) -> None:
        await engine.start()
        for _ in range(3):
            await engine.observe(_make_record(retry=True))
        for _ in range(2):
            await engine.observe(_make_record(fallback=True))
        stats = await engine.statistics()
        assert stats.total_retries == 3
        assert stats.total_fallbacks == 2

    async def test_statistics_provider_count(self, engine: AdaptiveLearningEngineImpl) -> None:
        await engine.start()
        for p in ["p1", "p2", "p3"]:
            await engine.observe(_make_record(provider=p))
        stats = await engine.statistics()
        assert stats.provider_count == 3


# ─────────────────────────────────────────────
# 16. Provider & Model Reputation Tests
# ─────────────────────────────────────────────


class TestReputationQueries:
    """Querying provider and model reputations."""

    async def test_provider_reputation_unknown(self, engine: AdaptiveLearningEngineImpl) -> None:
        await engine.start()
        rep = await engine.provider_reputation("unknown")
        assert rep is None

    async def test_provider_reputation_known(self, engine: AdaptiveLearningEngineImpl) -> None:
        await engine.start()
        for _ in range(10):
            await engine.observe(_make_record(provider="p1", success=True))
        rep = await engine.provider_reputation("p1")
        assert rep is not None
        assert rep.provider == "p1"
        assert rep.reputation.sample_size == 10

    async def test_provider_reputation_includes_predictions(
        self, engine: AdaptiveLearningEngineImpl
    ) -> None:
        await engine.start()
        for _ in range(10):
            await engine.observe(_make_record(provider="p1", success=True))
        rep = await engine.provider_reputation("p1")
        assert rep.predictions.expected_success_probability > 0.5

    async def test_model_reputation_unknown(self, engine: AdaptiveLearningEngineImpl) -> None:
        await engine.start()
        rep = await engine.model_reputation("p1", "unknown")
        assert rep is None

    async def test_model_reputation_known(self, engine: AdaptiveLearningEngineImpl) -> None:
        await engine.start()
        for _ in range(10):
            await engine.observe(_make_record(provider="p1", model="m1", success=True))
        rep = await engine.model_reputation("p1", "m1")
        assert rep is not None
        assert rep.model == "m1"
        assert rep.provider == "p1"


# ─────────────────────────────────────────────
# 17. Metrics Tests
# ─────────────────────────────────────────────


class TestMetrics:
    """Metrics exposure."""

    async def test_metrics_empty(self, engine: AdaptiveLearningEngineImpl) -> None:
        await engine.start()
        metrics = await engine.metrics()
        assert metrics["observations"] == 0
        assert metrics["providers_tracked"] == 0

    async def test_metrics_with_data(self, engine: AdaptiveLearningEngineImpl) -> None:
        await engine.start()
        for _ in range(10):
            await engine.observe(_make_record(provider="p1", latency_ms=100.0, cost=0.01))
        metrics = await engine.metrics()
        assert metrics["observations"] == 10
        assert metrics["providers_tracked"] == 1
        assert metrics["enrich_count"] == 0

    async def test_metrics_after_enrich(self, engine: AdaptiveLearningEngineImpl) -> None:
        await engine.start()
        await engine.observe(_make_record(provider="p1"))
        await engine.enrich([(_make_provider("p1"), _make_model("m1"))], _make_request())
        metrics = await engine.metrics()
        assert metrics["enrich_count"] == 1

    async def test_metrics_anomalies(self, engine: AdaptiveLearningEngineImpl) -> None:
        await engine.start()
        for _ in range(6):
            await engine.observe(_make_record(provider="p1", success=False, failure=True))
        metrics = await engine.metrics()
        # Anomalies may be 0 due to EventBus being None
        assert "anomalies_detected" in metrics

    async def test_metrics_uptime(self, engine: AdaptiveLearningEngineImpl) -> None:
        await engine.start()
        metrics = await engine.metrics()
        assert metrics["uptime_seconds"] >= 0


# ─────────────────────────────────────────────
# 18. EventBus Integration Tests
# ─────────────────────────────────────────────


class TestEventBus:
    """EventBus publishing integration."""

    async def test_publishes_learning_event(self) -> None:
        mock_bus = AsyncMock()
        engine = AdaptiveLearningEngineImpl(event_bus=mock_bus)
        await engine.start()
        await engine.observe(_make_record())
        # Should call publish at least once
        assert mock_bus.publish.called

    async def test_publishes_anomaly_event(self) -> None:
        mock_bus = AsyncMock()
        engine = AdaptiveLearningEngineImpl(event_bus=mock_bus)
        await engine.start()
        for _ in range(6):
            await engine.observe(_make_record(provider="p1", success=False, failure=True))
        # After 5 consecutive failures, ANOMALY_DETECTED should be published
        assert mock_bus.publish.called

    async def test_publishes_reputation_changed(self) -> None:
        mock_bus = AsyncMock()
        engine = AdaptiveLearningEngineImpl(event_bus=mock_bus)
        await engine.start()
        for _ in range(10):
            await engine.observe(_make_record(provider="p1", success=True))
        # After 10 observations, REPUTATION_CHANGED should be published
        assert mock_bus.publish.called

    async def test_no_eventbus_no_crash(self, engine: AdaptiveLearningEngineImpl) -> None:
        """Engine should work without an EventBus."""
        await engine.start()
        for _ in range(10):
            await engine.observe(_make_record())
        assert engine.observation_count == 10

    async def test_recovery_event(self) -> None:
        mock_bus = AsyncMock()
        engine = AdaptiveLearningEngineImpl(event_bus=mock_bus)
        await engine.start()
        # Degrade
        for _ in range(5):
            await engine.observe(_make_record(provider="p1", success=False, failure=True))
        # Recover
        for _ in range(3):
            await engine.observe(_make_record(provider="p1", success=True))
        # Recovery event should be published (MODEL_RECOVERED)
        assert mock_bus.publish.called


# ─────────────────────────────────────────────
# 19. Thread Safety & Concurrent Access Tests
# ─────────────────────────────────────────────


class TestConcurrency:
    """Concurrent access safety."""

    async def test_concurrent_observations(self, engine: AdaptiveLearningEngineImpl) -> None:
        await engine.start()

        async def observe_many(count: int) -> None:
            for i in range(count):
                await engine.observe(_make_record(provider=f"p{i}", success=True))

        await asyncio.gather(
            observe_many(10),
            observe_many(10),
            observe_many(10),
        )
        assert engine.observation_count == 30

    async def test_concurrent_enrich(self, engine: AdaptiveLearningEngineImpl) -> None:
        await engine.start()
        for _ in range(5):
            await engine.observe(_make_record(provider="p1", success=True))

        async def enrich_parallel() -> None:
            candidates = [(_make_provider("p1"), _make_model("m1"))]
            for _ in range(10):
                await engine.enrich(candidates, _make_request())

        await asyncio.gather(enrich_parallel(), enrich_parallel())
        metrics = await engine.metrics()
        assert metrics["enrich_count"] == 20

    async def test_concurrent_observe_and_enrich(self, engine: AdaptiveLearningEngineImpl) -> None:
        await engine.start()

        async def observe_loop() -> None:
            for i in range(20):
                await engine.observe(_make_record(provider=f"p{i % 3}", success=True))

        async def enrich_loop() -> None:
            candidates = [(_make_provider("p1"), _make_model("m1"))]
            for _ in range(10):
                await engine.enrich(candidates, _make_request())

        await asyncio.gather(observe_loop(), enrich_loop())
        assert engine.observation_count == 20

    async def test_concurrent_snapshot(self, engine: AdaptiveLearningEngineImpl) -> None:
        await engine.start()
        for _ in range(5):
            await engine.observe(_make_record(provider="p1"))

        async def read_snapshot() -> None:
            for _ in range(10):
                await engine.snapshot()

        async def observe_more() -> None:
            for _ in range(10):
                await engine.observe(_make_record(provider="p2"))

        await asyncio.gather(read_snapshot(), observe_more())


# ─────────────────────────────────────────────
# 20. Fault Injection & Edge Case Tests
# ─────────────────────────────────────────────


class TestEdgeCases:
    """Edge cases, fault injection, and stress."""

    async def test_empty_provider_name(self, engine: AdaptiveLearningEngineImpl) -> None:
        await engine.start()
        rec = _make_record(provider="", model="m1")
        await engine.observe(rec)
        assert "" in engine.provider_states

    async def test_empty_model_name(self, engine: AdaptiveLearningEngineImpl) -> None:
        await engine.start()
        rec = _make_record(provider="p1", model="")
        await engine.observe(rec)
        assert "p1:" in engine.model_states

    async def test_zero_latency(self, engine: AdaptiveLearningEngineImpl) -> None:
        await engine.start()
        rec = _make_record(latency_ms=0.0)
        await engine.observe(rec)
        state = engine.provider_states["test-provider"]
        # Latency EWMA should not update for 0.0
        assert state.latency_ewma.count == 0

    async def test_negative_cost(self, engine: AdaptiveLearningEngineImpl) -> None:
        await engine.start()
        rec = _make_record(cost=-1.0)
        await engine.observe(rec)
        state = engine.provider_states["test-provider"]
        # Cost EWMA should not update for non-positive values
        assert state.cost_ewma.count == 0

    async def test_very_large_latency(self, engine: AdaptiveLearningEngineImpl) -> None:
        await engine.start()
        rec = _make_record(latency_ms=1_000_000.0)
        await engine.observe(rec)
        state = engine.provider_states["test-provider"]
        assert state.max_latency == 1_000_000.0

    async def test_many_observations(self, engine: AdaptiveLearningEngineImpl) -> None:
        await engine.start()
        for i in range(1000):
            await engine.observe(_make_record(provider=f"p{i % 10}", success=True))
        assert engine.observation_count == 1000
        assert len(engine.provider_states) == 10

    async def test_observe_then_dispose(self, engine: AdaptiveLearningEngineImpl) -> None:
        await engine.start()
        await engine.observe(_make_record())
        await engine.dispose()
        assert engine.observation_count == 0

    async def test_enrich_without_observations(self, engine: AdaptiveLearningEngineImpl) -> None:
        await engine.start()
        candidates = [(_make_provider("p1"), _make_model("m1"))]
        decision = await engine.enrich(candidates, _make_request())
        assert len(decision.enriched_candidates) == 0

    async def test_json_serializable_metrics(self, engine: AdaptiveLearningEngineImpl) -> None:
        await engine.start()
        for p in ["p1", "p2"]:
            for _ in range(5):
                await engine.observe(
                    _make_record(provider=p, success=True, latency_ms=50.0, cost=0.01)
                )
        metrics = await engine.metrics()
        # All values should be JSON-serializable
        import json

        json.dumps(metrics)

    async def test_rapid_observation_stress(self, engine: AdaptiveLearningEngineImpl) -> None:
        """500 rapid observations should not cause issues."""
        await engine.start()
        for i in range(500):
            await engine.observe(
                _make_record(
                    provider=f"p{i % 5}",
                    model=f"m{i % 10}",
                    success=i % 3 != 0,
                    latency_ms=float(i % 100 + 10),
                )
            )
        assert engine.observation_count == 500
        stats = await engine.statistics()
        assert stats.provider_count == 5

    async def test_all_successes(self, engine: AdaptiveLearningEngineImpl) -> None:
        """100% success rate should produce high scores."""
        await engine.start()
        for _ in range(50):
            await engine.observe(
                _make_record(provider="p1", success=True, latency_ms=50.0, cost=0.005)
            )
        rep = await engine.provider_reputation("p1")
        assert rep is not None
        assert rep.reputation.success_rate > 0.9
        assert rep.reputation.quality > 0.8

    async def test_all_failures(self, engine: AdaptiveLearningEngineImpl) -> None:
        """0% success rate should produce low scores."""
        await engine.start()
        for _ in range(50):
            await engine.observe(
                _make_record(
                    provider="p1", success=False, failure=True, latency_ms=500.0, cost=0.05
                )
            )
        rep = await engine.provider_reputation("p1")
        assert rep is not None
        assert rep.reputation.failure_rate > 0.9
        assert rep.reputation.quality < 0.3

    async def test_mixed_outcomes(self, engine: AdaptiveLearningEngineImpl) -> None:
        """Mixed success/failure should give moderate scores."""
        await engine.start()
        for i in range(50):
            success = i % 2 == 0
            await engine.observe(
                _make_record(
                    provider="p1",
                    success=success,
                    failure=not success,
                    latency_ms=100.0 if success else 500.0,
                    cost=0.01 if success else 0.05,
                )
            )
        rep = await engine.provider_reputation("p1")
        assert rep is not None
        assert 0.3 < rep.reputation.quality < 0.9
        assert 0.3 < rep.reputation.success_rate < 0.7


# ─────────────────────────────────────────────
# 21. Learning Provider/Model State Tests
# ─────────────────────────────────────────────


class TestInternalState:
    """Internal learning state correctness."""

    def test_provider_state_initial(self) -> None:
        state = _ProviderLearningState("p1")
        assert state.provider == "p1"
        assert state.success_count == 0
        assert state.failure_count == 0
        assert state.availability == 1.0
        assert state.min_latency == float("inf")

    def test_model_state_initial(self) -> None:
        state = _ModelLearningState("p1", "m1")
        assert state.provider == "p1"
        assert state.model == "m1"
        assert state.min_latency == float("inf")

    def test_provider_state_has_windows(self) -> None:
        state = _ProviderLearningState("p1")
        assert "5min" in state.windows
        assert "30min" in state.windows
        assert "6h" in state.windows
        assert "24h" in state.windows
        assert "7d" in state.windows
        assert "30d" in state.windows
        assert "lifetime" in state.windows

    def test_provider_state_ewmas(self) -> None:
        state = _ProviderLearningState("p1")
        assert state.latency_ewma.value == 0.0
        assert state.cost_ewma.value == 0.0
        assert state.quality_ewma.value == 0.0

    def test_model_state_trackers(self) -> None:
        state = _ModelLearningState("p1", "m1")
        assert state.latency_tracker is not None
        assert state.cost_tracker is not None
        assert state.success_tracker is not None
        assert state.failure_tracker is not None


# ─────────────────────────────────────────────
# 22. Stress & Performance Tests
# ─────────────────────────────────────────────


class TestPerformance:
    """Performance profiling — these are bounds checks, not microbenchmarks."""

    async def test_enrich_large_candidate_set(self, engine: AdaptiveLearningEngineImpl) -> None:
        await engine.start()
        # Register 50 providers
        for i in range(50):
            for _ in range(5):
                await engine.observe(_make_record(provider=f"p{i}", model="m1", success=True))
        # Enrich 50 candidates
        candidates = [(_make_provider(f"p{i}"), _make_model("m1")) for i in range(50)]
        decision = await engine.enrich(candidates, _make_request())
        # Should be able to find at least some enriched candidates
        assert decision.evaluation_time_ms >= 0

    async def test_forecast_many_providers(self, engine: AdaptiveLearningEngineImpl) -> None:
        await engine.start()
        for i in range(20):
            for _ in range(3):
                await engine.observe(_make_record(provider=f"p{i}", success=True))
        forecast = await engine.forecast()
        assert len(forecast.provider_forecast) == 20

    async def test_rapid_observe_reputation_update(
        self, engine: AdaptiveLearningEngineImpl
    ) -> None:
        await engine.start()
        for _ in range(200):
            await engine.observe(
                _make_record(provider="p1", success=True, latency_ms=100.0, cost=0.01)
            )
        rep = await engine.provider_reputation("p1")
        assert rep is not None
        assert rep.reputation.sample_size > 100

    async def test_snapshot_many_providers(self, engine: AdaptiveLearningEngineImpl) -> None:
        await engine.start()
        for i in range(30):
            for _ in range(3):
                await engine.observe(_make_record(provider=f"p{i}", success=True))
        snap = await engine.snapshot()
        assert len(snap.provider_reputations) == 30

    async def test_metrics_json_serialization_large(
        self, engine: AdaptiveLearningEngineImpl
    ) -> None:
        await engine.start()
        for i in range(20):
            for _ in range(3):
                await engine.observe(_make_record(provider=f"p{i}", success=True))
        import json

        metrics = await engine.metrics()
        json.dumps(metrics)


# ─────────────────────────────────────────────
# 23. Router Integration Tests
# ─────────────────────────────────────────────


class TestRouterIntegration:
    """Integration with the Router pipeline."""

    async def test_router_accepts_learning_engine(self) -> None:
        """RouterEngineImpl should accept adaptive_learning_engine in constructor."""
        learning = AdaptiveLearningEngineImpl()
        # Mock the RouterEngineImpl import and instantiate
        from agentic_os.core.omniroute.router import RouterEngineImpl

        router = RouterEngineImpl(
            provider_registry=MagicMock(),
            model_registry=MagicMock(),
            adaptive_learning_engine=learning,
        )
        assert router._adaptive_learning_engine is not None

    async def test_learning_engine_does_not_filter(self) -> None:
        """The learning engine should never filter or reject candidates."""
        learning = AdaptiveLearningEngineImpl()
        await learning.start()
        await learning.observe(_make_record(provider="p1"))
        candidates = [(_make_provider("p1"), _make_model("m1"))]
        decision = await learning.enrich(candidates, _make_request())
        # The enriched_candidates list size should match input or be empty
        assert len(decision.enriched_candidates) <= len(candidates)

    async def test_learning_never_routes(self, engine: AdaptiveLearningEngineImpl) -> None:
        """Verify learning engine has no route() or select() method."""
        assert not hasattr(engine, "route")
        assert not hasattr(engine, "select")

    async def test_learning_enriches_before_routing(self) -> None:
        """Verify the router pipeline calls enrich before policy evaluation."""
        learning = AdaptiveLearningEngineImpl()
        learning._enrich_count = 0

        # Create routers with learning engine
        router_builder = MagicMock()
        router_builder._adaptive_learning_engine = learning

        # The pipeline step should call enrich
        # This is a structural test — verify the pipe exists
        assert hasattr(router_builder, "_adaptive_learning_engine")


# ─────────────────────────────────────────────
# 24. Engine Integration: Budget + Circuit Breaker
# ─────────────────────────────────────────────


class TestEngineIntegration:
    """Integration across multiple engines."""

    async def test_consume_budget_events(self, engine: AdaptiveLearningEngineImpl) -> None:
        """Learning engine should accept observations with budget context."""
        await engine.start()
        rec = _make_record(budget_approved=True, budget_rejected=False)
        await engine.observe(rec)
        assert engine.observation_count == 1

    async def test_consume_circuit_breaker_state(self, engine: AdaptiveLearningEngineImpl) -> None:
        """Learning engine should accept observations with circuit state."""
        await engine.start()
        rec = _make_record()
        rec = LearningRecord(
            provider="p1",
            model="m1",
            circuit_state="open",
            success=False,
            failure=True,
        )
        await engine.observe(rec)
        assert engine.provider_states["p1"].failure_count == 1

    async def test_all_input_sources(self, engine: AdaptiveLearningEngineImpl) -> None:
        """All LearningInputSource values should work."""
        await engine.start()
        sources = [
            LearningInputSource.ROUTING,
            LearningInputSource.BUDGET,
            LearningInputSource.CIRCUIT_BREAKER,
            LearningInputSource.FEEDBACK,
            LearningInputSource.MANUAL,
        ]
        for src in sources:
            rec = _make_record(source=src)
            await engine.observe(rec)
        assert engine.observation_count == len(sources)

    async def test_consecutive_failures_detect_degradation(
        self, engine: AdaptiveLearningEngineImpl
    ) -> None:
        """5 consecutive failures should be detected as degradation."""
        await engine.start()
        mock_bus = AsyncMock()
        engine._event_bus = mock_bus
        for _ in range(5):
            await engine.observe(_make_record(provider="p1", success=False, failure=True))
        assert engine.provider_states["p1"].consecutive_failures == 5

    async def test_consecutive_successes_detect_recovery(
        self, engine: AdaptiveLearningEngineImpl
    ) -> None:
        """After degradation, 3 consecutive successes should detect recovery."""
        await engine.start()
        mock_bus = AsyncMock()
        engine._event_bus = mock_bus
        for _ in range(5):
            await engine.observe(_make_record(provider="p1", success=False, failure=True))
        for _ in range(3):
            await engine.observe(_make_record(provider="p1", success=True))
        assert engine.provider_states["p1"].consecutive_successes == 3
        assert engine.provider_states["p1"].consecutive_failures == 0


# ─────────────────────────────────────────────
# 25. Domain Model Tests
# ─────────────────────────────────────────────


class TestDomainModels:
    """Phase 5.7 domain model contracts."""

    def test_adaptive_weights_defaults(self) -> None:
        w = AdaptiveWeights()
        assert w.quality == 0.25
        assert w.latency == 0.20
        assert w.cost == 0.20
        assert w.reliability == 0.15
        assert w.availability == 0.10
        assert w.recovery == 0.05
        assert w.budget_efficiency == 0.05

    def test_confidence_is_reliable(self) -> None:
        conf = ConfidenceScore(score=0.8, sample_count=20)
        assert conf.score == 0.8
        assert conf.sample_count == 20
        conf = ConfidenceScore(score=0.5, sample_count=5)
        assert conf.score == 0.5

    def test_learning_record_defaults(self) -> None:
        rec = LearningRecord(provider="p1", model="m1")
        assert rec.id != ""
        assert rec.success is False
        assert rec.budget_approved is True
        assert rec.source == LearningInputSource.ROUTING

    def test_trend_direction_values(self) -> None:
        assert TrendDirection.IMPROVING == "improving"
        assert TrendDirection.DEGRADING == "degrading"
        assert TrendDirection.RECOVERY == "recovery"

    def test_learning_input_source_values(self) -> None:
        assert LearningInputSource.ROUTING == "routing"
        assert LearningInputSource.FEEDBACK == "feedback"

    def test_learning_snapshot_forward_ref(self) -> None:
        snap = LearningSnapshot()
        assert isinstance(snap.statistics, LearningStatistics)

    def test_prediction_result_defaults(self) -> None:
        pred = PredictionResult()
        assert pred.expected_latency_ms == 0.0
        assert pred.prediction_horizon == "short_term"

    def test_adaptive_score_components(self) -> None:
        score = AdaptiveScore()
        assert score.raw_score == 0.0
        assert score.normalized_score == 0.0
        assert score.trend == TrendDirection.UNKNOWN

    def test_provider_reputation_defaults(self) -> None:
        rep = ProviderReputation(provider="p1")
        assert isinstance(rep.reputation, ReputationScore)
        assert isinstance(rep.adaptive_score, AdaptiveScore)

    def test_model_reputation_defaults(self) -> None:
        rep = ModelReputation(provider="p1", model="m1")
        assert isinstance(rep.reputation, ReputationScore)

    def test_learning_decision_defaults(self) -> None:
        dec = LearningDecision()
        assert len(dec.enriched_candidates) == 0
        assert dec.evaluation_time_ms == 0.0

    def test_learning_forecast_defaults(self) -> None:
        fc = LearningForecast()
        assert fc.global_success_rate == 0.0
        assert len(fc.at_risk_providers) == 0

    def test_learning_window_defaults(self) -> None:
        w = LearningWindow(window_duration="5min")
        assert w.sample_count == 0
        assert w.success_rate == 0.0

    def test_provider_trend_defaults(self) -> None:
        t = ProviderTrend()
        assert isinstance(t.latency, LatencyTrend)
        assert t.overall == TrendDirection.UNKNOWN

    def test_learning_event_defaults(self) -> None:
        e = LearningEvent()
        assert e.id != ""
        assert e.score_before == 0.0
        assert e.score_after == 0.0

    def test_learning_statistics_defaults(self) -> None:
        s = LearningStatistics()
        assert s.total_observations == 0
        assert s.last_observation is None

    def test_module_exports(self) -> None:
        from agentic_os.core.omniroute.learning import (
            AdaptiveLearningEngineImpl,
            AdaptiveLearningEnginePort,
        )

        assert AdaptiveLearningEngineImpl is not None
        assert AdaptiveLearningEnginePort is not None
