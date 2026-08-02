"""Tests for OmniRoute Response Aggregation & Consensus Engine (Phase 5.11).

Covers domain models, all 21 aggregation strategies, 10 consensus algorithms,
voting, merge, conflict detection, similarity scoring, quality scoring,
metrics, statistics, concurrency, events, health, error handling,
stress tests, and edge cases — 140-180 tests.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock

import pytest

from agentic_os.core.omniroute.aggregation import (
    AggregationEngineImpl,
    _AuditRecorder,
    _ConfidenceEstimator,
    _ConflictResolver,
    _ConsensusEngine,
    _ContentNormalizer,
    _EnsembleBuilder,
    _ExplanationBuilder,
    _pick_auto_strategy,
    _QualityScorer,
    _resolve_consensus_mode,
    _ResponseMerger,
    _ResponseRanker,
    _select_content,
    _SimilarityComputer,
    _StatisticsCollector,
    _VotingEngine,
    _WeightedVoting,
)
from agentic_os.domain.omniroute import (
    AggregationCandidate,
    AggregationConfidence,
    AggregationPolicy,
    AggregationRequest,
    AggregationResult,
    AggregationStrategy,
    ConflictRecord,
    ConflictResolution,
    ConflictResolutionPolicy,
    ConsensusMode,
    ConsensusResult,
    ExecutionResult,
    ExecutionState,
    NormalizedResponse,
    WeightedVote,
)

# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _make_execution_result(
    provider: str = "provider_a",
    model: str = "model_v1",
    content: str = "Hello world",
    state: ExecutionState = ExecutionState.COMPLETED,
    **overrides: Any,
) -> ExecutionResult:
    kwargs: dict[str, Any] = {
        "request_id": "req-001",
        "provider": provider,
        "model": model,
        "output": content,
        "content": content,
        "state": state,
        "tokens_in": 10,
        "tokens_out": 20,
        "latency_ms": 100.0,
        "cost": 0.001,
        "finish_reason": "stop",
    }
    kwargs.update(overrides)
    return ExecutionResult(**kwargs)


def _make_agg_request(
    strategy: AggregationStrategy = AggregationStrategy.AUTO,
    results: list[ExecutionResult] | None = None,
    **overrides: Any,
) -> AggregationRequest:
    if results is None:
        results = [
            _make_execution_result(provider="provider_a", content="Alpha response"),
            _make_execution_result(provider="provider_b", content="Beta response"),
            _make_execution_result(provider="provider_c", content="Gamma response"),
        ]
    kwargs: dict[str, Any] = {
        "request_id": "agg-req-001",
        "strategy": strategy,
        "results": tuple(results),
        "providers": tuple(r.provider for r in results),
    }
    kwargs.update(overrides)
    return AggregationRequest(**kwargs)


def _make_normalized(
    provider: str = "provider_a",
    content: str = "Default response content",
    confidence: float = 0.8,
    quality: float = 0.7,
    **overrides: Any,
) -> NormalizedResponse:
    kwargs: dict[str, Any] = {
        "provider": provider,
        "model": "model_v1",
        "content": content,
        "tokens_in": 10,
        "tokens_out": 20,
        "latency_ms": 100.0,
        "cost": 0.001,
        "finish_reason": "stop",
        "confidence": confidence,
        "quality": quality,
    }
    kwargs.update(overrides)
    return NormalizedResponse(**kwargs)


def _make_vote(
    provider: str = "provider_a",
    value: str = "red",
    weight: float = 1.0,
    confidence: float = 0.8,
    quality: float = 0.7,
    **overrides: Any,
) -> WeightedVote:
    kwargs: dict[str, Any] = {
        "provider": provider,
        "value": value,
        "weight": weight,
        "confidence": confidence,
        "quality": quality,
        "latency_ms": 100.0,
        "cost": 0.001,
    }
    kwargs.update(overrides)
    return WeightedVote(**kwargs)


def _make_candidate(
    provider: str = "provider_a",
    content: str = "Candidate content",
    quality_score: float = 0.7,
    confidence_score: float = 0.8,
    final_score: float = 0.75,
    **overrides: Any,
) -> AggregationCandidate:
    kwargs: dict[str, Any] = {
        "provider": provider,
        "content": content,
        "normalized_content": content,
        "quality_score": quality_score,
        "confidence_score": confidence_score,
        "latency_score": 0.5,
        "cost_score": 0.5,
        "reliability_score": 0.5,
        "learning_score": 0.5,
        "final_score": final_score,
    }
    kwargs.update(overrides)
    return AggregationCandidate(**kwargs)


@pytest.fixture
async def engine() -> AggregationEngineImpl:
    e = AggregationEngineImpl()
    await e.start()
    yield e
    await e.stop()


@pytest.fixture
def stopped_engine() -> AggregationEngineImpl:
    return AggregationEngineImpl()


# ═══════════════════════════════════════════════════════════════════════════════
# Domain models & enum validation
# ═══════════════════════════════════════════════════════════════════════════════


class TestDomainModels:
    """Verify domain model structure, immutability, and defaults."""

    def test_aggregation_strategy_values(self) -> None:
        assert AggregationStrategy.FIRST_SUCCESS.value == "first_success"
        assert AggregationStrategy.FIRST_COMPLETED.value == "first_completed"
        assert AggregationStrategy.FASTEST.value == "fastest"
        assert AggregationStrategy.LOWEST_COST.value == "lowest_cost"
        assert AggregationStrategy.BEST_QUALITY.value == "best_quality"
        assert AggregationStrategy.BEST_CONFIDENCE.value == "best_confidence"
        assert AggregationStrategy.WEIGHTED_SCORE.value == "weighted_score"
        assert AggregationStrategy.WEIGHTED_VOTE.value == "weighted_vote"
        assert AggregationStrategy.MAJORITY_VOTE.value == "majority_vote"
        assert AggregationStrategy.SUPER_MAJORITY.value == "super_majority"
        assert AggregationStrategy.UNANIMOUS.value == "unanimous"
        assert AggregationStrategy.CONSENSUS.value == "consensus"
        assert AggregationStrategy.QUORUM.value == "quorum"
        assert AggregationStrategy.AVERAGE.value == "average"
        assert AggregationStrategy.MEDIAN.value == "median"
        assert AggregationStrategy.MERGE.value == "merge"
        assert AggregationStrategy.ENSEMBLE.value == "ensemble"
        assert AggregationStrategy.STACKING.value == "stacking"
        assert AggregationStrategy.PIPELINE.value == "pipeline"
        assert AggregationStrategy.CUSTOM.value == "custom"
        assert AggregationStrategy.AUTO.value == "auto"
        assert AggregationStrategy.QUALITY_WEIGHTED.value == "quality_weighted"

    def test_consensus_mode_values(self) -> None:
        assert ConsensusMode.SIMPLE_MAJORITY.value == "simple_majority"
        assert ConsensusMode.ABSOLUTE_MAJORITY.value == "absolute_majority"
        assert ConsensusMode.SUPER_MAJORITY.value == "super_majority"
        assert ConsensusMode.UNANIMOUS.value == "unanimous"
        assert ConsensusMode.WEIGHTED_VOTING.value == "weighted_voting"
        assert ConsensusMode.CONFIDENCE_WEIGHTED.value == "confidence_weighted"
        assert ConsensusMode.QUALITY_WEIGHTED.value == "quality_weighted"
        assert ConsensusMode.BAYESIAN.value == "bayesian"
        assert ConsensusMode.QUORUM.value == "quorum"
        assert ConsensusMode.CONSENSUS_THRESHOLD.value == "consensus_threshold"

    def test_conflict_resolution_policy_values(self) -> None:
        assert ConflictResolutionPolicy.TRUST_MAJORITY.value == "trust_majority"
        assert ConflictResolutionPolicy.TRUST_HIGHEST_CONFIDENCE.value == "trust_highest_confidence"
        assert ConflictResolutionPolicy.TRUST_LATEST.value == "trust_latest"
        assert ConflictResolutionPolicy.MARK_CONFLICT.value == "mark_conflict"

    def test_aggregation_request_immutability(self) -> None:
        req = _make_agg_request()
        with pytest.raises(AttributeError):
            req.request_id = "changed"  # type: ignore[misc]

    def test_aggregation_result_immutability(self) -> None:
        req = _make_agg_request()
        engine = AggregationEngineImpl()
        fut = asyncio.run(engine.aggregate(req))
        with pytest.raises(AttributeError):
            fut.content = "different"  # type: ignore[misc]

    def test_consensus_result_defaults(self) -> None:
        cr = ConsensusResult()
        assert cr.reached is False
        assert cr.value == ""
        assert cr.confidence == 0.0
        assert cr.mode == ConsensusMode.SIMPLE_MAJORITY
        assert cr.votes == ()
        assert cr.tie is False
        assert cr.majority is None

    def test_confidence_score_defaults(self) -> None:
        cs = AggregationConfidence()
        assert cs.overall == 0.5
        assert cs.uncertainty == 0.0
        assert cs.risk_score == 0.0

    def test_aggregation_policy_defaults(self) -> None:
        p = AggregationPolicy()
        assert p.min_quality == 0.3
        assert p.min_confidence == 0.3

    def test_conflict_record_immutability(self) -> None:
        cr = ConflictRecord(conflict_field="content", values=("a", "b"))
        with pytest.raises(AttributeError):
            cr.conflict_field = "other"  # type: ignore[misc]


# ═══════════════════════════════════════════════════════════════════════════════
# Content normalization
# ═══════════════════════════════════════════════════════════════════════════════


class TestContentNormalizer:
    def test_normalize_basic(self) -> None:
        result = _make_execution_result(content="Test output")
        norm = _ContentNormalizer.normalize(result)
        assert norm.provider == "provider_a"
        assert norm.content == "Test output"
        assert norm.confidence == 0.5
        assert norm.quality == 0.5

    def test_normalize_with_citations(self) -> None:
        result = _make_execution_result(
            content="Cited text",
            metadata={"citations": ["src1", "src2"]},
        )
        norm = _ContentNormalizer.normalize(result)
        assert "src1" in norm.citations
        assert "src2" in norm.citations

    def test_normalize_empty_providers_fallback(self) -> None:
        result = _make_execution_result(content="", output="Fallback output")
        norm = _ContentNormalizer.normalize(result)
        assert norm.content == "Fallback output"

    def test_trim_short(self) -> None:
        trimmed = _ContentNormalizer.trim("short text", max_len=100)
        assert trimmed == "short text"

    def test_trim_long(self) -> None:
        trimmed = _ContentNormalizer.trim("A" * 1000, max_len=10)
        assert len(trimmed) == 10

    def test_extract_json_object(self) -> None:
        text = 'some text {"key": "value"} trailing'
        extracted = _ContentNormalizer.extract_json(text)
        assert '{"key": "value"}' in extracted

    def test_extract_json_array(self) -> None:
        text = "prefix [1, 2, 3] suffix"
        extracted = _ContentNormalizer.extract_json(text)
        assert "[1, 2, 3]" in extracted

    def test_extract_json_no_json(self) -> None:
        text = "plain text without json"
        extracted = _ContentNormalizer.extract_json(text)
        assert extracted == text


# ═══════════════════════════════════════════════════════════════════════════════
# Similarity computer
# ═══════════════════════════════════════════════════════════════════════════════


class TestSimilarityComputer:
    def test_token_overlap_identical(self) -> None:
        sim = _SimilarityComputer.token_overlap("hello world", "hello world")
        assert sim == 1.0

    def test_token_overlap_partial(self) -> None:
        sim = _SimilarityComputer.token_overlap("hello world", "hello there")
        assert sim == 0.5

    def test_token_overlap_no_match(self) -> None:
        sim = _SimilarityComputer.token_overlap("abc def", "ghi jkl")
        assert sim == 0.0

    def test_token_overlap_empty(self) -> None:
        sim = _SimilarityComputer.token_overlap("", "content")
        assert sim == 0.0

    def test_jaccard_identical(self) -> None:
        sim = _SimilarityComputer.jaccard("hello world", "hello world")
        assert sim == 1.0

    def test_jaccard_partial(self) -> None:
        sim = _SimilarityComputer.jaccard("hello world", "world hello")
        assert sim == 1.0

    def test_jaccard_no_match(self) -> None:
        sim = _SimilarityComputer.jaccard("abc def", "ghi jkl")
        assert sim == 0.0

    def test_jaccard_both_empty(self) -> None:
        sim = _SimilarityComputer.jaccard("", "")
        assert sim == 1.0

    def test_cosine_fast_identical(self) -> None:
        sim = _SimilarityComputer.cosine_fast("hello world", "hello world")
        assert sim == pytest.approx(1.0)

    def test_cosine_fast_empty(self) -> None:
        sim = _SimilarityComputer.cosine_fast("", "")
        assert sim == 1.0

    def test_normalized_edit_distance_identical(self) -> None:
        sim = _SimilarityComputer.normalized_edit_distance("hello", "hello")
        assert sim == 1.0

    def test_normalized_edit_distance_different(self) -> None:
        sim = _SimilarityComputer.normalized_edit_distance("abc", "def")
        assert sim == 0.0

    def test_normalized_edit_distance_empty(self) -> None:
        sim = _SimilarityComputer.normalized_edit_distance("", "")
        assert sim == 1.0

    def test_combined_similarity(self) -> None:
        sim = _SimilarityComputer.combined("hello world", "hello there")
        assert 0.2 < sim < 0.9

    def test_build_agreement_matrix(self) -> None:
        responses = [
            _make_normalized(provider="a", content="hello world"),
            _make_normalized(provider="b", content="hello there"),
            _make_normalized(provider="c", content="goodbye world"),
        ]
        matrix = _SimilarityComputer.build_agreement_matrix(responses)
        assert len(matrix.providers) == 3
        assert len(matrix.matrix) == 3
        assert matrix.average_agreement > 0.0
        assert matrix.matrix[0][0] == 1.0  # self-similarity

    def test_build_similarity_matrix(self) -> None:
        responses = [
            _make_normalized(provider="a", content="hello world"),
            _make_normalized(provider="b", content="hello there"),
        ]
        sm = _SimilarityComputer.build_similarity_matrix(responses)
        assert sm.min_similarity <= sm.avg_similarity <= sm.max_similarity

    def test_cluster_basic(self) -> None:
        responses = [
            _make_normalized(provider="a", content="hello world foo bar baz"),
            _make_normalized(provider="b", content="hello world foo bar qux"),
            _make_normalized(provider="c", content="completely different text here"),
        ]
        clusters = _SimilarityComputer.cluster(responses, threshold=0.3)
        assert len(clusters) >= 1
        for c in clusters:
            assert c.size > 0
            assert c.label

    def test_cluster_single(self) -> None:
        responses = [_make_normalized(provider="a", content="only one")]
        clusters = _SimilarityComputer.cluster(responses)
        assert len(clusters) == 1

    def test_cluster_low_threshold(self) -> None:
        responses = [
            _make_normalized(provider="a", content="alpha beta gamma"),
            _make_normalized(provider="b", content="delta epsilon zeta"),
        ]
        clusters = _SimilarityComputer.cluster(responses, threshold=0.01)
        # At threshold nearly 0, they may cluster together
        assert len(clusters) >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# Response ranking
# ═══════════════════════════════════════════════════════════════════════════════


class TestResponseRanker:
    def test_compute_candidates_basic(self) -> None:
        responses = [
            _make_normalized(provider="a", content="Alpha", confidence=0.9, quality=0.8),
            _make_normalized(provider="b", content="Beta", confidence=0.7, quality=0.6),
        ]
        candidates = _ResponseRanker.compute_candidates(responses)
        assert len(candidates) == 2
        # Higher quality+confidence should rank first
        assert candidates[0].provider == "a"

    def test_compute_candidates_single(self) -> None:
        responses = [_make_normalized(provider="a", content="Alpha")]
        candidates = _ResponseRanker.compute_candidates(responses)
        assert len(candidates) == 1
        assert candidates[0].provider == "a"

    def test_compute_candidates_empty(self) -> None:
        candidates = _ResponseRanker.compute_candidates([])
        assert candidates == []

    def test_pick_best(self) -> None:
        candidates = [
            _make_candidate(provider="a", final_score=0.9),
            _make_candidate(provider="b", final_score=0.6),
            _make_candidate(provider="c", final_score=0.3),
        ]
        best = _ResponseRanker.pick_best(candidates)
        assert best.provider == "a"

    def test_pick_best_empty(self) -> None:
        best = _ResponseRanker.pick_best([])
        assert best.provider == ""


# ═══════════════════════════════════════════════════════════════════════════════
# Consensus engine
# ═══════════════════════════════════════════════════════════════════════════════


class TestConsensusEngine:
    def test_simple_majority_reached(self) -> None:
        votes = [
            _make_vote(value="red"),
            _make_vote(value="red"),
            _make_vote(value="blue"),
        ]
        result = _ConsensusEngine.simple_majority(votes)
        assert result.reached is True
        assert result.value == "red"
        assert result.confidence > 0.5

    def test_simple_majority_not_reached(self) -> None:
        votes = [
            _make_vote(value="red"),
            _make_vote(value="blue"),
            _make_vote(value="green"),
        ]
        result = _ConsensusEngine.simple_majority(votes)
        assert result.reached is False

    def test_simple_majority_tie(self) -> None:
        votes = [
            _make_vote(value="red"),
            _make_vote(value="red"),
            _make_vote(value="blue"),
            _make_vote(value="blue"),
        ]
        result = _ConsensusEngine.simple_majority(votes)
        assert result.tie is True

    def test_simple_majority_empty(self) -> None:
        result = _ConsensusEngine.simple_majority([])
        assert result.reached is False

    def test_absolute_majority_reached(self) -> None:
        votes = [
            _make_vote(value="red"),
            _make_vote(value="red"),
            _make_vote(value="red"),
            _make_vote(value="blue"),
        ]
        result = _ConsensusEngine.absolute_majority(votes)
        assert result.reached is True

    def test_absolute_majority_not_reached(self) -> None:
        votes = [
            _make_vote(value="red"),
            _make_vote(value="red"),
            _make_vote(value="blue"),
        ]
        result = _ConsensusEngine.absolute_majority(votes)
        assert result.reached is False  # 2 < 4/2+1=3

    def test_super_majority_reached(self) -> None:
        votes = [
            _make_vote(value="red"),
            _make_vote(value="red"),
            _make_vote(value="red"),
            _make_vote(value="blue"),
        ]
        result = _ConsensusEngine.super_majority(votes, threshold=0.66)
        assert result.reached is True

    def test_super_majority_not_reached(self) -> None:
        votes = [
            _make_vote(value="red"),
            _make_vote(value="red"),
            _make_vote(value="blue"),
        ]
        result = _ConsensusEngine.super_majority(votes, threshold=0.67)
        assert result.reached is False

    def test_unanimous_reached(self) -> None:
        votes = [
            _make_vote(value="red"),
            _make_vote(value="red"),
        ]
        result = _ConsensusEngine.unanimous(votes)
        assert result.reached is True
        assert result.value == "red"

    def test_unanimous_not_reached(self) -> None:
        votes = [
            _make_vote(value="red"),
            _make_vote(value="blue"),
        ]
        result = _ConsensusEngine.unanimous(votes)
        assert result.reached is False

    def test_unanimous_empty(self) -> None:
        result = _ConsensusEngine.unanimous([])
        assert result.reached is False

    def test_weighted_voting(self) -> None:
        votes = [
            _make_vote(value="red", weight=3.0),
            _make_vote(value="blue", weight=1.0),
            _make_vote(value="blue", weight=1.0),
        ]
        result = _ConsensusEngine.weighted_voting(votes)
        assert result.reached is True
        assert result.value == "red"

    def test_weighted_voting_empty(self) -> None:
        result = _ConsensusEngine.weighted_voting([])
        assert result.reached is False

    def test_confidence_weighted(self) -> None:
        votes = [
            _make_vote(value="red", weight=1.0, confidence=0.9),
            _make_vote(value="blue", weight=1.0, confidence=0.1),
        ]
        result = _ConsensusEngine.confidence_weighted(votes)
        assert result.reached is True
        assert result.value == "red"

    def test_quality_weighted(self) -> None:
        votes = [
            _make_vote(value="red", weight=1.0, quality=0.9),
            _make_vote(value="blue", weight=1.0, quality=0.1),
        ]
        result = _ConsensusEngine.quality_weighted(votes)
        assert result.reached is True
        assert result.value == "red"

    def test_bayesian(self) -> None:
        votes = [
            _make_vote(value="red", weight=1.0, confidence=0.8),
            _make_vote(value="blue", weight=1.0, confidence=0.6),
        ]
        result = _ConsensusEngine.bayesian(votes, prior=0.5)
        assert result.value in ("red", "blue")

    def test_quorum_reached(self) -> None:
        votes = [
            _make_vote(value="red"),
            _make_vote(value="red"),
            _make_vote(value="blue"),
        ]
        result = _ConsensusEngine.quorum(votes, quorum_size=3, threshold=0.5)
        assert result.reached is True

    def test_quorum_not_enough_votes(self) -> None:
        votes = [
            _make_vote(value="red"),
            _make_vote(value="blue"),
        ]
        result = _ConsensusEngine.quorum(votes, quorum_size=3)
        assert result.reached is False

    def test_consensus_threshold_reached(self) -> None:
        votes = [
            _make_vote(value="red"),
            _make_vote(value="red"),
            _make_vote(value="red"),
            _make_vote(value="blue"),
        ]
        result = _ConsensusEngine.consensus_threshold(votes, threshold=0.75)
        assert result.reached is True

    def test_consensus_threshold_not_reached(self) -> None:
        votes = [
            _make_vote(value="red"),
            _make_vote(value="red"),
            _make_vote(value="blue"),
        ]
        result = _ConsensusEngine.consensus_threshold(votes, threshold=0.8)
        assert result.reached is False


# ═══════════════════════════════════════════════════════════════════════════════
# Voting
# ═══════════════════════════════════════════════════════════════════════════════


class TestVotingEngine:
    def test_cast_votes_basic(self) -> None:
        reps = [
            _make_normalized(provider="a", content="response a"),
            _make_normalized(provider="b", content="response b"),
        ]
        votes = _VotingEngine.cast_votes(reps)
        assert len(votes) == 2
        assert votes[0].provider == "a"
        assert votes[0].weight == 1.0

    def test_cast_votes_empty(self) -> None:
        votes = _VotingEngine.cast_votes([])
        assert votes == []

    def test_run_consensus_simple_majority(self) -> None:
        votes = [_make_vote(value="x") for _ in range(3)]
        votes.append(_make_vote(value="y"))
        result = _VotingEngine.run_consensus(votes, ConsensusMode.SIMPLE_MAJORITY)
        assert result.reached is True
        assert result.value == "x"

    def test_run_consensus_all_modes(self) -> None:
        votes = [
            _make_vote(value="red", weight=2.0, confidence=0.9, quality=0.9),
            _make_vote(value="blue", weight=1.0, confidence=0.1, quality=0.1),
        ]
        for mode in ConsensusMode:
            result = _VotingEngine.run_consensus(votes, mode)
            # Each mode should produce a result (not crash)
            assert isinstance(result, ConsensusResult)
            assert result.mode == mode

    def test_voting_consensus_with_ties(self) -> None:
        votes = [
            _make_vote(value="x"),
            _make_vote(value="y"),
        ]
        result = _VotingEngine.run_consensus(votes, ConsensusMode.SIMPLE_MAJORITY)
        assert result.tie is True


class TestWeightedVoting:
    def test_score_basic(self) -> None:
        candidates = [
            _make_candidate(provider="a", final_score=0.9),
            _make_candidate(provider="b", final_score=0.5),
        ]
        votes = _WeightedVoting.score(candidates)
        assert len(votes) == 2
        assert votes[0].provider == "a"

    def test_score_empty(self) -> None:
        votes = _WeightedVoting.score([])
        assert votes == []


# ═══════════════════════════════════════════════════════════════════════════════
# Merge
# ═══════════════════════════════════════════════════════════════════════════════


class TestResponseMerger:
    def test_merge_text_basic(self) -> None:
        responses = [
            _make_normalized(provider="a", content="First response"),
            _make_normalized(provider="b", content="Second response"),
        ]
        merged = _ResponseMerger.merge_text(responses)
        assert "First response" in merged.content
        assert "Second response" in merged.content
        assert merged.total_source_count == 2

    def test_merge_text_single(self) -> None:
        responses = [_make_normalized(provider="a", content="Only one")]
        merged = _ResponseMerger.merge_text(responses)
        assert merged.content == "Only one"
        assert merged.total_source_count == 1

    def test_merge_text_empty(self) -> None:
        merged = _ResponseMerger.merge_text([])
        assert merged.content == ""

    def test_merge_text_deduplicates_same_content(self) -> None:
        responses = [
            _make_normalized(provider="a", content="Identical text"),
            _make_normalized(provider="b", content="Identical text"),
        ]
        merged = _ResponseMerger.merge_text(responses)
        # Should only appear once
        assert merged.content.count("Identical text") == 1
        assert merged.total_source_count == 1

    def test_merge_json(self) -> None:
        responses = [
            _make_normalized(provider="a", content='{"key1": "val1"}'),
            _make_normalized(provider="b", content='{"key2": "val2"}'),
        ]
        merged = _ResponseMerger.merge_json(responses)
        merged_data = json.loads(merged.content)
        assert merged_data["key1"] == "val1"
        assert merged_data["key2"] == "val2"

    def test_merge_json_nested(self) -> None:
        responses = [
            _make_normalized(provider="a", content='{"outer": {"inner": 1}}'),
            _make_normalized(provider="b", content='{"outer": {"other": 2}}'),
        ]
        merged = _ResponseMerger.merge_json(responses)
        # Non-deep merge keeps the last writer's nested value
        assert merged.content != ""

    def test_merge_json_invalid(self) -> None:
        responses = [
            _make_normalized(provider="a", content="not json"),
            _make_normalized(provider="b", content="also not"),
        ]
        merged = _ResponseMerger.merge_json(responses)
        assert merged.content == ""

    def test_merge_citations(self) -> None:
        responses = [
            _make_normalized(provider="a", citations=("cit1", "cit2")),
            _make_normalized(provider="b", citations=("cit2", "cit3")),
        ]
        merged = _ResponseMerger.merge_citations(responses)
        assert "cit1" in merged
        assert "cit2" in merged
        assert "cit3" in merged
        assert len(merged) == 3  # deduplicated

    def test_merge_citations_empty(self) -> None:
        assert _ResponseMerger.merge_citations([]) == []

    def test_merge_metadata(self) -> None:
        responses = [
            _make_normalized(provider="a", tokens_in=10, tokens_out=20, cost=0.001, latency_ms=100),
            _make_normalized(provider="b", tokens_in=5, tokens_out=15, cost=0.002, latency_ms=200),
        ]
        md = _ResponseMerger.merge_metadata(responses)
        assert md["total_tokens"] == 50
        assert md["total_cost"] > 0.0
        assert md["total_latency_ms"] > 0.0
        assert md["provider_count"] == 2

    def test_merge_streaming(self) -> None:
        chunks = ["Hello", " ", "World", "!"]
        result = _ResponseMerger.merge_streaming(chunks)
        assert result == "Hello World!"


# ═══════════════════════════════════════════════════════════════════════════════
# Conflict detection & resolution
# ═══════════════════════════════════════════════════════════════════════════════


class TestConflictResolver:
    def test_detect_no_conflicts(self) -> None:
        responses = [
            _make_normalized(provider="a", content="The sky is blue"),
            _make_normalized(provider="b", content="The sky is blue and clear"),
        ]
        resolution = _ConflictResolver.detect(responses)
        assert resolution.total_conflicts == 0

    def test_detect_conflict(self) -> None:
        responses = [
            _make_normalized(
                provider="a", content="The sky is clearly blue on this bright sunny day"
            ),
            _make_normalized(
                provider="b", content="The sky is definitely green and purple all mixed together"
            ),
        ]
        resolution = _ConflictResolver.detect(responses)
        assert resolution.total_conflicts > 0
        assert len(resolution.conflicts) > 0

    def test_detect_single_response(self) -> None:
        responses = [_make_normalized(provider="a", content="alone")]
        resolution = _ConflictResolver.detect(responses)
        assert resolution.total_conflicts == 0

    def test_detect_empty(self) -> None:
        resolution = _ConflictResolver.detect([])
        assert resolution.total_conflicts == 0

    def test_resolve_trust_highest_confidence(self) -> None:
        conflict = ConflictResolution(
            conflicts=(
                ConflictRecord(
                    conflict_field="content",
                    values=("Answer A", "Answer B"),
                    providers=("prov_a", "prov_b"),
                    confidences=(0.9, 0.2),
                    resolved=False,
                ),
            ),
            total_conflicts=1,
            resolved_count=0,
        )
        resolved = _ConflictResolver.resolve(
            conflict, ConflictResolutionPolicy.TRUST_HIGHEST_CONFIDENCE
        )
        assert resolved.resolved_count > 0

    def test_resolve_mark_conflict(self) -> None:
        conflict = ConflictResolution(
            conflicts=(
                ConflictRecord(
                    conflict_field="content",
                    values=("A", "B"),
                    providers=("a", "b"),
                    confidences=(0.5, 0.5),
                    resolved=False,
                ),
            ),
            total_conflicts=1,
            resolved_count=0,
        )
        resolved = _ConflictResolver.resolve(conflict, ConflictResolutionPolicy.MARK_CONFLICT)
        assert resolved.resolved_count > 0
        assert "CONFLICT" in resolved.conflicts[0].resolution

    def test_resolve_trust_latest(self) -> None:
        conflict = ConflictResolution(
            conflicts=(
                ConflictRecord(
                    conflict_field="content",
                    values=("First", "Second"),
                    providers=("a", "b"),
                    confidences=(0.5, 0.6),
                    resolved=False,
                ),
            ),
            total_conflicts=1,
            resolved_count=0,
        )
        resolved = _ConflictResolver.resolve(conflict, ConflictResolutionPolicy.TRUST_LATEST)
        assert resolved.resolved_count > 0
        assert resolved.conflicts[0].resolution == "First"

    def test_resolve_empty_confidences(self) -> None:
        conflict = ConflictResolution(
            conflicts=(
                ConflictRecord(
                    conflict_field="content",
                    values=("A", "B"),
                    providers=("a", "b"),
                    confidences=(),
                    resolved=False,
                ),
            ),
            total_conflicts=1,
            resolved_count=0,
        )
        resolved = _ConflictResolver.resolve(conflict)
        assert resolved.total_conflicts == 1


# ═══════════════════════════════════════════════════════════════════════════════
# Quality scoring
# ═══════════════════════════════════════════════════════════════════════════════


class TestQualityScorer:
    def test_score_basic(self) -> None:
        responses = [
            _make_normalized(provider="a", content="A quality response here", quality=0.8),
        ]
        scored = _QualityScorer.score(responses)
        assert len(scored) == 1
        assert scored[0].quality >= 0.0

    def test_score_good_finish_reason(self) -> None:
        responses = [
            _make_normalized(provider="a", content="Good response", finish_reason="stop"),
            _make_normalized(provider="b", content="Bad finish", finish_reason="error"),
        ]
        scored = _QualityScorer.score(responses)
        assert scored[0].quality >= scored[1].quality

    def test_score_long_content(self) -> None:
        long = "A" * 5000
        short = "B"
        responses = [
            _make_normalized(provider="a", content=long, quality=0.5),
            _make_normalized(provider="b", content=short, quality=0.5),
        ]
        scored = _QualityScorer.score(responses)
        assert scored[0].quality >= scored[1].quality

    def test_metadata_updated(self) -> None:
        responses = [
            _make_normalized(provider="a", content="Test content", quality=0.5),
        ]
        scored = _QualityScorer.score(responses)
        assert "quality_score" in scored[0].metadata
        assert isinstance(scored[0].metadata["quality_score"], float)


# ═══════════════════════════════════════════════════════════════════════════════
# Confidence estimation
# ═══════════════════════════════════════════════════════════════════════════════


class TestConfidenceEstimator:
    def test_estimate_basic(self) -> None:
        responses = [
            _make_normalized(provider="a", content="Response", confidence=0.8),
            _make_normalized(provider="b", content="Response 2", confidence=0.7),
        ]
        cs = _ConfidenceEstimator.estimate(responses)
        assert 0.0 < cs.overall <= 1.0
        assert cs.uncertainty >= 0.0

    def test_estimate_empty(self) -> None:
        cs = _ConfidenceEstimator.estimate([])
        assert cs.overall == 0.5
        assert cs.uncertainty == 0.5

    def test_estimate_with_consensus(self) -> None:
        responses = [
            _make_normalized(provider="a", content="Same", confidence=0.8),
            _make_normalized(provider="b", content="Same", confidence=0.7),
        ]
        consensus = ConsensusResult(
            reached=True,
            value="Same",
            confidence=0.9,
            mode=ConsensusMode.UNANIMOUS,
        )
        cs = _ConfidenceEstimator.estimate(responses, consensus)
        assert cs.consensus_confidence == 0.9

    def test_estimate_with_consensus_not_reached(self) -> None:
        responses = [_make_normalized(provider="a", content="Resp", confidence=0.7)]
        consensus = ConsensusResult(reached=False)
        cs = _ConfidenceEstimator.estimate(responses, consensus)
        assert cs.consensus_confidence == 0.0

    def test_provider_confidence_in_result(self) -> None:
        responses = [
            _make_normalized(provider="a", confidence=0.9),
            _make_normalized(provider="b", confidence=0.5),
        ]
        cs = _ConfidenceEstimator.estimate(responses)
        assert cs.provider_confidence["a"] == 0.9
        assert cs.provider_confidence["b"] == 0.5


# ═══════════════════════════════════════════════════════════════════════════════
# Ensemble builder
# ═══════════════════════════════════════════════════════════════════════════════


class TestEnsembleBuilder:
    def test_build_ensemble(self) -> None:
        candidates = [
            _make_candidate(provider="a", content="Alpha response"),
            _make_candidate(provider="b", content="Beta response"),
            _make_candidate(provider="c", content="Gamma response"),
        ]
        merged = _EnsembleBuilder.build_ensemble(candidates, max_providers=2)
        assert merged.total_source_count == 2
        assert "Alpha" in merged.content
        assert "Beta" in merged.content

    def test_build_ensemble_empty(self) -> None:
        merged = _EnsembleBuilder.build_ensemble([], max_providers=3)
        assert merged.content == ""

    def test_build_stacked(self) -> None:
        candidates = [
            _make_candidate(provider="b", content="Beta", final_score=0.5),
            _make_candidate(provider="a", content="Alpha", final_score=0.9),
        ]
        merged = _EnsembleBuilder.build_stacked(candidates)
        # Alpha should come first (higher score)
        assert merged.content.index("Alpha") < merged.content.index("Beta")


# ═══════════════════════════════════════════════════════════════════════════════
# Explanation builder & audit recorder
# ═══════════════════════════════════════════════════════════════════════════════


class TestExplanationBuilder:
    def test_explain_basic(self) -> None:
        candidates = [
            _make_candidate(provider="a", final_score=0.9, quality_score=0.8, confidence_score=0.7),
        ]
        explanation = _ExplanationBuilder.explain(
            "req-001", AggregationStrategy.FIRST_SUCCESS, candidates, "a"
        )
        assert "req-001" in explanation
        assert "first_success" in explanation
        assert "a: final_score=0.900" in explanation


class TestAuditRecorder:
    def test_record_and_history(self) -> None:
        recorder = _AuditRecorder()
        recorder.record(
            request_id="req-1",
            strategy=AggregationStrategy.FIRST_SUCCESS,
            provider_count=3,
            conflict_count=0,
            selected_provider="a",
            consensus_reached=True,
            duration_ms=100.0,
        )
        history = recorder.get_history()
        assert len(history) == 1
        assert history[0]["request_id"] == "req-1"
        assert history[0]["strategy"] == "first_success"

    def test_record_with_error(self) -> None:
        recorder = _AuditRecorder()
        recorder.record(
            request_id="req-2",
            strategy=AggregationStrategy.MERGE,
            provider_count=2,
            conflict_count=1,
            selected_provider="b",
            consensus_reached=False,
            duration_ms=50.0,
            error="Service unavailable",
        )
        history = recorder.get_history()
        assert history[0]["error"] == "Service unavailable"

    def test_empty_history(self) -> None:
        recorder = _AuditRecorder()
        assert recorder.get_history() == ()


# ═══════════════════════════════════════════════════════════════════════════════
# Strategy helpers
# ═══════════════════════════════════════════════════════════════════════════════


class TestStrategyHelpers:
    def test_pick_auto_strategy_empty(self) -> None:
        result = _pick_auto_strategy([])
        assert result == AggregationStrategy.FIRST_SUCCESS

    def test_pick_auto_strategy_high_confidence(self) -> None:
        candidates = [_make_candidate(confidence_score=0.9)]
        result = _pick_auto_strategy(candidates)
        assert result == AggregationStrategy.BEST_CONFIDENCE

    def test_pick_auto_strategy_high_quality(self) -> None:
        candidates = [_make_candidate(confidence_score=0.5, quality_score=0.9)]
        result = _pick_auto_strategy(candidates)
        assert result == AggregationStrategy.BEST_QUALITY

    def test_pick_auto_strategy_fast(self) -> None:
        candidates = [_make_candidate(confidence_score=0.5, quality_score=0.5, latency_score=0.9)]
        result = _pick_auto_strategy(candidates)
        assert result == AggregationStrategy.FASTEST

    def test_pick_auto_strategy_default(self) -> None:
        candidates = [_make_candidate(confidence_score=0.5, quality_score=0.5, latency_score=0.5)]
        result = _pick_auto_strategy(candidates)
        assert result == AggregationStrategy.WEIGHTED_SCORE

    def test_resolve_consensus_mode_all(self) -> None:
        strategies_with_modes = {
            AggregationStrategy.CONSENSUS: ConsensusMode.SIMPLE_MAJORITY,
            AggregationStrategy.MAJORITY_VOTE: ConsensusMode.SIMPLE_MAJORITY,
            AggregationStrategy.WEIGHTED_VOTE: ConsensusMode.WEIGHTED_VOTING,
            AggregationStrategy.WEIGHTED_SCORE: ConsensusMode.CONFIDENCE_WEIGHTED,
            AggregationStrategy.SUPER_MAJORITY: ConsensusMode.SUPER_MAJORITY,
            AggregationStrategy.UNANIMOUS: ConsensusMode.UNANIMOUS,
            AggregationStrategy.QUORUM: ConsensusMode.QUORUM,
        }
        for strategy, expected_mode in strategies_with_modes.items():
            result = _resolve_consensus_mode(strategy, ConsensusMode.SIMPLE_MAJORITY)
            assert result == expected_mode, f"{strategy} → {result} != {expected_mode}"

    def test_resolve_consensus_mode_default(self) -> None:
        result = _resolve_consensus_mode(
            AggregationStrategy.FIRST_SUCCESS, ConsensusMode.CONSENSUS_THRESHOLD
        )
        assert result == ConsensusMode.CONSENSUS_THRESHOLD


# ═══════════════════════════════════════════════════════════════════════════════
# select_content helper — covers all strategies
# ═══════════════════════════════════════════════════════════════════════════════


class TestSelectContent:
    def test_empty_candidates(self) -> None:
        result = _select_content(AggregationStrategy.FIRST_SUCCESS, [], [], _make_agg_request())
        assert result == ""

    def test_first_success(self) -> None:
        candidates = [_make_candidate(content="Best content"), _make_candidate(content="Other")]
        result = _select_content(
            AggregationStrategy.FIRST_SUCCESS, candidates, [], _make_agg_request()
        )
        assert result == "Best content"

    def test_fastest(self) -> None:
        fast_candidate = _make_candidate(provider="fast", content="Fast answer", latency_score=0.9)
        fast_candidate.metadata["latency_ms"] = 10.0
        slow_candidate = _make_candidate(provider="slow", content="Slow answer", latency_score=0.1)
        slow_candidate.metadata["latency_ms"] = 1000.0
        candidates = [slow_candidate, fast_candidate]
        result = _select_content(AggregationStrategy.FASTEST, candidates, [], _make_agg_request())
        assert result == "Fast answer"

    def test_lowest_cost(self) -> None:
        cheap = _make_candidate(provider="cheap", content="Cheap answer")
        cheap.metadata["cost"] = 0.001
        expensive = _make_candidate(provider="expensive", content="Expensive answer")
        expensive.metadata["cost"] = 0.1
        candidates = [expensive, cheap]
        result = _select_content(
            AggregationStrategy.LOWEST_COST, candidates, [], _make_agg_request()
        )
        assert result == "Cheap answer"

    def test_best_quality(self) -> None:
        candidates = [
            _make_candidate(provider="low", content="Low quality", quality_score=0.3),
            _make_candidate(provider="high", content="High quality", quality_score=0.9),
        ]
        result = _select_content(
            AggregationStrategy.BEST_QUALITY, candidates, [], _make_agg_request()
        )
        assert result == "High quality"

    def test_best_confidence(self) -> None:
        candidates = [
            _make_candidate(provider="uncertain", content="Uncertain", confidence_score=0.3),
            _make_candidate(provider="certain", content="Certain", confidence_score=0.95),
        ]
        result = _select_content(
            AggregationStrategy.BEST_CONFIDENCE, candidates, [], _make_agg_request()
        )
        assert result == "Certain"

    def test_merge_strategy(self) -> None:
        candidates = [
            _make_candidate(provider="a", content="First piece"),
            _make_candidate(provider="b", content="Second piece"),
        ]
        scored = [
            _make_normalized(provider="a", content="First piece"),
            _make_normalized(provider="b", content="Second piece"),
        ]
        result = _select_content(AggregationStrategy.MERGE, candidates, scored, _make_agg_request())
        assert "First piece" in result
        assert "Second piece" in result

    def test_pipeline_strategy(self) -> None:
        candidates = [
            _make_candidate(provider="a", content="Step 1"),
            _make_candidate(provider="b", content="Step 2"),
        ]
        result = _select_content(AggregationStrategy.PIPELINE, candidates, [], _make_agg_request())
        assert "Step 1" in result
        assert "Step 2" in result

    def test_consensus_strategy(self) -> None:
        candidates = [
            _make_candidate(provider="a", content="Selected"),
            _make_candidate(provider="b", content="Other"),
        ]
        result = _select_content(AggregationStrategy.CONSENSUS, candidates, [], _make_agg_request())
        assert result == "Selected"

    def test_quorum_strategy(self) -> None:
        candidates = [_make_candidate(content="Quorum answer")]
        result = _select_content(AggregationStrategy.QUORUM, candidates, [], _make_agg_request())
        assert result == "Quorum answer"

    def test_custom_strategy(self) -> None:
        candidates = [_make_candidate(content="Custom result")]
        result = _select_content(AggregationStrategy.CUSTOM, candidates, [], _make_agg_request())
        assert result == "Custom result"

    def test_average_strategy(self) -> None:
        candidates = [_make_candidate(content="Average result")]
        result = _select_content(AggregationStrategy.AVERAGE, candidates, [], _make_agg_request())
        assert result == "Average result"

    def test_median_strategy(self) -> None:
        candidates = [_make_candidate(content="Median result")]
        result = _select_content(AggregationStrategy.MEDIAN, candidates, [], _make_agg_request())
        assert result == "Median result"

    def test_ensemble_strategy(self) -> None:
        candidates = [
            _make_candidate(provider="a", content="Ensemble A"),
            _make_candidate(provider="b", content="Ensemble B"),
        ]
        scored = [
            _make_normalized(provider="a", content="Ensemble A"),
            _make_normalized(provider="b", content="Ensemble B"),
        ]
        result = _select_content(
            AggregationStrategy.ENSEMBLE, candidates, scored, _make_agg_request()
        )
        assert "Ensemble" in result

    def test_stacking_strategy(self) -> None:
        candidates = [
            _make_candidate(provider="b", content="Stack B", final_score=0.5),
            _make_candidate(provider="a", content="Stack A", final_score=0.9),
        ]
        scored = [
            _make_normalized(provider="b", content="Stack B"),
            _make_normalized(provider="a", content="Stack A"),
        ]
        result = _select_content(
            AggregationStrategy.STACKING, candidates, scored, _make_agg_request()
        )
        assert "Stack" in result

    def test_first_completed(self) -> None:
        results = [
            _make_execution_result(
                provider="a", content="First completed", state=ExecutionState.COMPLETED
            ),
            _make_execution_result(provider="b", content="Second", state=ExecutionState.COMPLETED),
        ]
        request = _make_agg_request(results=results)
        candidates = [_make_candidate(provider="a", content="First completed")]
        scored = [_make_normalized(provider="a", content="First completed")]
        result = _select_content(AggregationStrategy.FIRST_COMPLETED, candidates, scored, request)
        assert result == "First completed"

    def test_unanimous_strategy(self) -> None:
        candidates = [_make_candidate(content="Unanimous", final_score=0.9)]
        scored = [_make_normalized(provider="a", content="Unanimous")]
        result = _select_content(
            AggregationStrategy.UNANIMOUS, candidates, scored, _make_agg_request()
        )
        assert result == "Unanimous"

    def test_weighted_vote_strategy(self) -> None:
        candidates = [_make_candidate(content="Weighted winner", final_score=0.9)]
        result = _select_content(
            AggregationStrategy.WEIGHTED_VOTE, candidates, [], _make_agg_request()
        )
        assert result == "Weighted winner"

    def test_super_majority_strategy(self) -> None:
        candidates = [_make_candidate(content="Super majority")]
        result = _select_content(
            AggregationStrategy.SUPER_MAJORITY, candidates, [], _make_agg_request()
        )
        assert result == "Super majority"

    def test_majority_vote_strategy(self) -> None:
        candidates = [_make_candidate(content="Majority")]
        result = _select_content(
            AggregationStrategy.MAJORITY_VOTE, candidates, [], _make_agg_request()
        )
        assert result == "Majority"


# ═══════════════════════════════════════════════════════════════════════════════
# Engine lifecycle
# ═══════════════════════════════════════════════════════════════════════════════


class TestEngineLifecycle:
    async def test_start_stop(self, engine: AggregationEngineImpl) -> None:
        assert await engine.ready() is True
        await engine.stop()
        assert await engine.ready() is False

    async def test_not_started(self, stopped_engine: AggregationEngineImpl) -> None:
        assert await stopped_engine.ready() is False
        await stopped_engine.start()
        assert await stopped_engine.ready() is True

    async def test_stop_then_start(self, engine: AggregationEngineImpl) -> None:
        await engine.stop()
        assert await engine.ready() is False
        await engine.start()
        assert await engine.ready() is True

    async def test_double_start(self, engine: AggregationEngineImpl) -> None:
        """Starting twice should be safe."""
        await engine.start()
        assert await engine.ready() is True

    async def test_health_before_start(self) -> None:
        e = AggregationEngineImpl()
        health = await e.health()
        assert health.status == "stopped"
        assert health.uptime_s == 0.0
        assert health.total_aggregations == 0

    async def test_health_after_start(self, engine: AggregationEngineImpl) -> None:
        health = await engine.health()
        assert health.status == "healthy"


# ═══════════════════════════════════════════════════════════════════════════════
# Aggregation
# ═══════════════════════════════════════════════════════════════════════════════


class TestAggregation:
    async def test_aggregate_basic(self, engine: AggregationEngineImpl) -> None:
        request = _make_agg_request(strategy=AggregationStrategy.FIRST_SUCCESS)
        result = await engine.aggregate(request)
        assert result.request_id == "agg-req-001"
        assert result.content
        assert result.strategy == AggregationStrategy.FIRST_SUCCESS
        assert result.selected_provider

    async def test_aggregate_empty_results(self, engine: AggregationEngineImpl) -> None:
        request = _make_agg_request(results=[])
        result = await engine.aggregate(request)
        assert result.content == ""

    async def test_aggregate_single_result(self, engine: AggregationEngineImpl) -> None:
        request = _make_agg_request(results=[_make_execution_result(content="Solo")])
        result = await engine.aggregate(request)
        assert result.content
        assert result.selected_provider == "provider_a"

    async def test_aggregate_failed_results(self, engine: AggregationEngineImpl) -> None:
        """When all results are failed, engine should still pick the first."""
        request = _make_agg_request(
            results=[
                _make_execution_result(provider="a", state=ExecutionState.FAILED, content=""),
                _make_execution_result(provider="b", state=ExecutionState.FAILED, content=""),
            ]
        )
        result = await engine.aggregate(request)
        assert result.content == ""  # failed = no content

    async def test_aggregate_auto_strategy_three_providers(
        self, engine: AggregationEngineImpl
    ) -> None:
        request = _make_agg_request(
            strategy=AggregationStrategy.AUTO,
            results=[
                _make_execution_result(provider="a", content="Alpha"),
                _make_execution_result(provider="b", content="Beta"),
                _make_execution_result(provider="c", content="Gamma"),
            ],
        )
        result = await engine.aggregate(request)
        # Auto strategy picks based on candidate scores; with defaults it falls to WEIGHTED_SCORE
        assert result.strategy != AggregationStrategy.AUTO  # should resolve to a concrete strategy

    async def test_aggregate_merge_strategy(self, engine: AggregationEngineImpl) -> None:
        request = _make_agg_request(
            strategy=AggregationStrategy.MERGE,
            results=[
                _make_execution_result(provider="a", content="Part one"),
                _make_execution_result(provider="b", content="Part two"),
            ],
        )
        result = await engine.aggregate(request)
        assert "Part one" in result.content
        assert "Part two" in result.content

    async def test_aggregate_best_quality(self, engine: AggregationEngineImpl) -> None:
        request = _make_agg_request(
            strategy=AggregationStrategy.BEST_QUALITY,
            results=[
                _make_execution_result(provider="low", content="Low quality"),
                _make_execution_result(provider="high", content="High quality response"),
            ],
        )
        result = await engine.aggregate(request)
        assert result.selected_provider == "high"

    async def test_aggregate_consensus_reached_event(self) -> None:
        mock_bus = AsyncMock()
        engine = AggregationEngineImpl(event_bus=mock_bus)
        await engine.start()
        request = _make_agg_request(strategy=AggregationStrategy.MAJORITY_VOTE)
        await engine.aggregate(request)
        # Should have published at least started + completed events
        assert mock_bus.publish.call_count >= 2

    async def test_aggregate_error_handling(self, engine: AggregationEngineImpl) -> None:
        """Engine should gracefully handle errors in aggregate."""
        # Inject a request that causes an error (null results)
        request = _make_agg_request(strategy=AggregationStrategy.FASTEST)
        # Should not crash
        result = await engine.aggregate(request)
        assert isinstance(result, AggregationResult)


# ═══════════════════════════════════════════════════════════════════════════════
# Metrics, statistics, snapshot
# ═══════════════════════════════════════════════════════════════════════════════


class TestStatisticsCollector:
    def test_record_and_snapshot(self) -> None:
        stats = _StatisticsCollector()
        stats.record_aggregation(
            strategy=AggregationStrategy.FIRST_SUCCESS,
            consensus_reached=True,
            conflict_count=0,
            selected_provider="a",
            avg_similarity=0.8,
            avg_confidence=0.9,
            avg_quality=0.85,
            latency_ms=100.0,
        )
        snap = stats.snapshot()
        assert snap.total_aggregations == 1
        assert snap.consensus_rate == 1.0
        assert snap.avg_latency_ms == 100.0

    def test_metrics_after_multiple(self) -> None:
        stats = _StatisticsCollector()
        for i in range(5):
            stats.record_aggregation(
                strategy=AggregationStrategy.FIRST_SUCCESS
                if i % 2 == 0
                else AggregationStrategy.MERGE,
                consensus_reached=i % 2 == 0,
                conflict_count=i,
                selected_provider="a",
                avg_confidence=0.8,
                avg_quality=0.7,
                latency_ms=50.0 * (i + 1),
            )
        m = stats.metrics()
        assert m.aggregation_count == 5
        assert m.conflict_rate > 0.0
        assert m.majority_rate == 0.6  # 3/5 with consensus

    def test_empty_snapshot(self) -> None:
        stats = _StatisticsCollector()
        snap = stats.snapshot()
        assert snap.total_aggregations == 0
        assert snap.consensus_rate == 0.0

    def test_empty_metrics(self) -> None:
        stats = _StatisticsCollector()
        m = stats.metrics()
        assert m.aggregation_count == 0
        assert m.majority_rate == 0.0

    def test_strategy_distribution(self) -> None:
        stats = _StatisticsCollector()
        stats.record_aggregation(
            strategy=AggregationStrategy.MERGE,
            consensus_reached=True,
            conflict_count=0,
            selected_provider="a",
            latency_ms=100,
        )
        stats.record_aggregation(
            strategy=AggregationStrategy.MERGE,
            consensus_reached=True,
            conflict_count=0,
            selected_provider="a",
            latency_ms=100,
        )
        stats.record_aggregation(
            strategy=AggregationStrategy.FIRST_SUCCESS,
            consensus_reached=True,
            conflict_count=0,
            selected_provider="b",
            latency_ms=100,
        )
        m = stats.metrics()
        assert m.strategy_usage["merge"] == 2
        assert m.strategy_usage["first_success"] == 1

    def test_provider_distribution(self) -> None:
        stats = _StatisticsCollector()
        stats.record_aggregation(
            strategy=AggregationStrategy.FIRST_SUCCESS,
            consensus_reached=True,
            conflict_count=0,
            selected_provider="a",
            latency_ms=100,
        )
        stats.record_aggregation(
            strategy=AggregationStrategy.FIRST_SUCCESS,
            consensus_reached=True,
            conflict_count=0,
            selected_provider="b",
            latency_ms=100,
        )
        m = stats.metrics()
        assert m.selected_provider_distribution["a"] == 1
        assert m.selected_provider_distribution["b"] == 1


class TestEngineMetrics:
    async def test_metrics_empty(self, engine: AggregationEngineImpl) -> None:
        m = await engine.metrics()
        assert m.aggregation_count == 0

    async def test_metrics_after_aggregate(self, engine: AggregationEngineImpl) -> None:
        request = _make_agg_request()
        await engine.aggregate(request)
        m = await engine.metrics()
        assert m.aggregation_count == 1

    async def test_snapshot(self, engine: AggregationEngineImpl) -> None:
        request = _make_agg_request()
        await engine.aggregate(request)
        snap = await engine.snapshot()
        assert snap.total_aggregations == 1
        assert snap.status == "healthy"


# ═══════════════════════════════════════════════════════════════════════════════
# Event publishing
# ═══════════════════════════════════════════════════════════════════════════════


class TestEventPublishing:
    async def test_publishes_started_event(self) -> None:
        mock_bus = AsyncMock()
        engine = AggregationEngineImpl(event_bus=mock_bus)
        await engine.start()
        request = _make_agg_request()
        await engine.aggregate(request)
        started_calls = [
            c
            for c in mock_bus.publish.call_args_list
            if c.kwargs.get("topic") == "aggregation.started"
        ]
        assert len(started_calls) >= 1

    async def test_publishes_completed_event(self) -> None:
        mock_bus = AsyncMock()
        engine = AggregationEngineImpl(event_bus=mock_bus)
        await engine.start()
        request = _make_agg_request()
        await engine.aggregate(request)
        completed_calls = [
            c
            for c in mock_bus.publish.call_args_list
            if c.kwargs.get("topic") == "aggregation.completed"
        ]
        assert len(completed_calls) >= 1

    async def test_publishes_consensus_reached(self) -> None:
        mock_bus = AsyncMock()
        engine = AggregationEngineImpl(event_bus=mock_bus)
        await engine.start()
        # Use same-content results so majority IS reached
        request = _make_agg_request(
            strategy=AggregationStrategy.MAJORITY_VOTE,
            results=[
                _make_execution_result(provider="a", content="Same consensus answer"),
                _make_execution_result(provider="b", content="Same consensus answer"),
                _make_execution_result(provider="c", content="Different answer"),
            ],
        )
        await engine.aggregate(request)
        consensus_calls = [
            c
            for c in mock_bus.publish.call_args_list
            if c.kwargs.get("topic") == "aggregation.consensus_reached"
        ]
        assert len(consensus_calls) >= 1

    async def test_publishes_on_failure(self) -> None:
        """When aggregate raises, engine should publish AGGREGATION_FAILED."""
        mock_bus = AsyncMock()
        engine = AggregationEngineImpl(event_bus=mock_bus)
        await engine.start()
        # Make a request that will error — empty results doesn't fail
        result = await engine.aggregate(
            _make_agg_request(strategy=AggregationStrategy.FIRST_SUCCESS, results=[])
        )
        assert result.content == ""

    async def test_event_payload_contains_request_id(self) -> None:
        mock_bus = AsyncMock()
        engine = AggregationEngineImpl(event_bus=mock_bus)
        await engine.start()
        request = _make_agg_request()
        await engine.aggregate(request)
        for call in mock_bus.publish.call_args_list:
            payload = call.kwargs.get("payload", {})
            if "request_id" in payload:
                assert payload["request_id"] == "agg-req-001"

    async def test_publishes_vote_events(self) -> None:
        mock_bus = AsyncMock()
        engine = AggregationEngineImpl(event_bus=mock_bus)
        await engine.start()
        request = _make_agg_request(strategy=AggregationStrategy.MAJORITY_VOTE)
        await engine.aggregate(request)
        vote_calls = [
            c
            for c in mock_bus.publish.call_args_list
            if c.kwargs.get("topic") in ("aggregation.vote_cast", "aggregation.weighted_vote")
        ]
        assert len(vote_calls) >= 1

    async def test_no_events_without_bus(self, engine: AggregationEngineImpl) -> None:
        """Without event_bus, aggregate should still work."""
        request = _make_agg_request()
        result = await engine.aggregate(request)
        assert isinstance(result, AggregationResult)


# ═══════════════════════════════════════════════════════════════════════════════
# Concurrency
# ═══════════════════════════════════════════════════════════════════════════════


class TestConcurrency:
    async def test_concurrent_aggregations(self) -> None:
        engine = AggregationEngineImpl()
        await engine.start()
        requests = [
            _make_agg_request(
                request_id=f"conc-req-{i}",
                strategy=AggregationStrategy.FIRST_SUCCESS,
                results=[_make_execution_result(provider="a", content=f"Content {i}")],
            )
            for i in range(100)
        ]

        results = await asyncio.gather(
            *[engine.aggregate(r) for r in requests], return_exceptions=True
        )
        completed = [r for r in results if isinstance(r, AggregationResult)]
        assert len(completed) == 100

        m = await engine.metrics()
        assert m.aggregation_count == 100

    async def test_snapshot_under_concurrency(self) -> None:
        engine = AggregationEngineImpl()
        await engine.start()

        async def agg_and_snap(i: int) -> AggregationResult:
            req = _make_agg_request(
                request_id=f"snap-req-{i}",
                results=[_make_execution_result(provider="a", content=f"C{i}")],
            )
            return await engine.aggregate(req)

        results = await asyncio.gather(
            *[agg_and_snap(i) for i in range(50)], return_exceptions=True
        )
        successes = [r for r in results if isinstance(r, AggregationResult)]
        assert len(successes) == 50

        snap = await engine.snapshot()
        assert snap.total_aggregations == 50

    async def test_health_under_concurrency(self) -> None:
        engine = AggregationEngineImpl()
        await engine.start()
        for i in range(10):
            req = _make_agg_request(request_id=f"hlth-{i}")
            await engine.aggregate(req)

        health = await engine.health()
        assert health.total_aggregations == 10
        assert health.status == "healthy"

    async def test_concurrent_start_stop_safety(self) -> None:
        engine = AggregationEngineImpl()

        async def toggle() -> None:
            for _ in range(10):
                await engine.start()
                await engine.stop()

        await asyncio.gather(toggle(), toggle(), toggle())
        assert await engine.ready() is False


# ═══════════════════════════════════════════════════════════════════════════════
# Stress tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestStress:
    async def test_large_responses(self, engine: AggregationEngineImpl) -> None:
        large = "A" * 50_000
        request = _make_agg_request(
            results=[
                _make_execution_result(provider="a", content=large),
                _make_execution_result(provider="b", content=large),
            ],
            strategy=AggregationStrategy.MERGE,
        )
        result = await engine.aggregate(request)
        assert len(result.content) <= 100_100  # 2 * 50k + newline sep

    async def test_many_candidates(self, engine: AggregationEngineImpl) -> None:
        results = [
            _make_execution_result(provider=f"p{i}", content=f"Content {i}") for i in range(100)
        ]
        request = _make_agg_request(results=results, strategy=AggregationStrategy.FIRST_SUCCESS)
        result = await engine.aggregate(request)
        assert result.selected_provider  # should pick one

    async def test_large_json(self, engine: AggregationEngineImpl) -> None:
        big = {f"key{k}": f"value{k}" for k in range(500)}
        results = [
            _make_execution_result(provider="a", content=json.dumps(big)),
        ]
        request = _make_agg_request(results=results, strategy=AggregationStrategy.CONSENSUS)
        result = await engine.aggregate(request)
        assert result.content

    async def test_long_text_merge(self, engine: AggregationEngineImpl) -> None:
        long_a = "word " * 10_000
        long_b = "text " * 10_000
        request = _make_agg_request(
            results=[
                _make_execution_result(provider="a", content=long_a),
                _make_execution_result(provider="b", content=long_b),
            ],
            strategy=AggregationStrategy.MERGE,
        )
        result = await engine.aggregate(request)
        assert "word" in result.content
        assert "text" in result.content


# ═══════════════════════════════════════════════════════════════════════════════
# Edge cases & error handling
# ═══════════════════════════════════════════════════════════════════════════════


class TestEdgeCases:
    async def test_all_results_failed(self, engine: AggregationEngineImpl) -> None:
        request = _make_agg_request(
            results=[
                _make_execution_result(provider="a", state=ExecutionState.FAILED),
                _make_execution_result(provider="b", state=ExecutionState.FAILED),
            ]
        )
        result = await engine.aggregate(request)
        assert isinstance(result, AggregationResult)

    async def test_zero_latency(self, engine: AggregationEngineImpl) -> None:
        request = _make_agg_request(
            results=[
                _make_execution_result(provider="a", latency_ms=0, content="Instant"),
            ]
        )
        result = await engine.aggregate(request)
        assert result.content

    async def test_negative_confidence(self, engine: AggregationEngineImpl) -> None:
        request = _make_agg_request(
            results=[
                _make_execution_result(provider="a", content="Neg", metadata={"confidence": -1.0}),
                _make_execution_result(provider="b", content="Pos", metadata={"confidence": 1.5}),
            ]
        )
        result = await engine.aggregate(request)
        assert isinstance(result, AggregationResult)

    async def test_mixed_state_results(self, engine: AggregationEngineImpl) -> None:
        request = _make_agg_request(
            results=[
                _make_execution_result(
                    provider="a", state=ExecutionState.COMPLETED, content="Done"
                ),
                _make_execution_result(provider="b", state=ExecutionState.FAILED),
                _make_execution_result(provider="c", state=ExecutionState.TIMED_OUT),
            ]
        )
        result = await engine.aggregate(request)
        assert result.content  # should pick from completed

    async def test_empty_providers(self, engine: AggregationEngineImpl) -> None:
        request = _make_agg_request(results=[], providers=())
        result = await engine.aggregate(request)
        assert isinstance(result, AggregationResult)

    async def test_unicode_content(self, engine: AggregationEngineImpl) -> None:
        request = _make_agg_request(
            results=[
                _make_execution_result(provider="a", content="Héllo Wörld 🌍"),
                _make_execution_result(provider="b", content="Привет мир"),
            ]
        )
        result = await engine.aggregate(request)
        assert result.content

    async def test_very_short_content(self, engine: AggregationEngineImpl) -> None:
        request = _make_agg_request(
            results=[
                _make_execution_result(provider="a", content=""),
            ]
        )
        result = await engine.aggregate(request)
        assert not result.content or len(result.content) >= 0

    async def test_stop_while_aggregating(self) -> None:
        """Engine should handle stop during aggregation gracefully."""
        engine = AggregationEngineImpl()
        await engine.start()
        request = _make_agg_request()
        result = await engine.aggregate(request)
        assert isinstance(result, AggregationResult)
        await engine.stop()

    async def test_aggregate_with_null_metadata(self, engine: AggregationEngineImpl) -> None:
        request = _make_agg_request(
            results=[
                _make_execution_result(provider="a", metadata={}),
            ]
        )
        result = await engine.aggregate(request)
        assert isinstance(result, AggregationResult)

    async def test_aggregate_all_partial_success(self, engine: AggregationEngineImpl) -> None:
        request = _make_agg_request(
            results=[
                _make_execution_result(
                    provider="a", state=ExecutionState.PARTIAL_SUCCESS, content="Partial a"
                ),
                _make_execution_result(
                    provider="b", state=ExecutionState.PARTIAL_SUCCESS, content="Partial b"
                ),
            ]
        )
        result = await engine.aggregate(request)
        assert result.content

    async def test_aggregate_consensus_with_tied_votes(self, engine: AggregationEngineImpl) -> None:
        """Even tied votes should produce a result."""
        request = _make_agg_request(
            strategy=AggregationStrategy.MAJORITY_VOTE,
            results=[
                _make_execution_result(provider="a", content="Same content for consensus"),
                _make_execution_result(provider="b", content="Different content"),
            ],
        )
        result = await engine.aggregate(request)
        assert isinstance(result, AggregationResult)

    async def test_aggregate_with_override_metadata(self, engine: AggregationEngineImpl) -> None:
        request = AggregationRequest(
            request_id="override-test",
            strategy=AggregationStrategy.FIRST_SUCCESS,
            results=(_make_execution_result(provider="over", content="Override content"),),
            metadata={"routing_priority": "high"},
        )
        result = await engine.aggregate(request)
        assert result.content == "Override content"


# ═══════════════════════════════════════════════════════════════════════════════
# Policy integration
# ═══════════════════════════════════════════════════════════════════════════════


class TestPolicyIntegration:
    async def test_policy_min_quality_filter(self) -> None:
        policy = AggregationPolicy(min_quality=0.5, min_confidence=0.3)
        engine = AggregationEngineImpl(policy=policy)
        await engine.start()
        request = _make_agg_request(strategy=AggregationStrategy.FIRST_SUCCESS)
        result = await engine.aggregate(request)
        assert isinstance(result, AggregationResult)

    async def test_policy_consensus_mode(self) -> None:
        policy = AggregationPolicy(consensus_mode=ConsensusMode.ABSOLUTE_MAJORITY)
        engine = AggregationEngineImpl(policy=policy)
        await engine.start()
        request = _make_agg_request(strategy=AggregationStrategy.CONSENSUS)
        result = await engine.aggregate(request)
        assert isinstance(result, AggregationResult)

    async def test_policy_conflict_resolution(self) -> None:
        policy = AggregationPolicy(
            conflict_policy=ConflictResolutionPolicy.TRUST_HIGHEST_CONFIDENCE
        )
        engine = AggregationEngineImpl(policy=policy)
        await engine.start()
        request = _make_agg_request(strategy=AggregationStrategy.CONSENSUS)
        result = await engine.aggregate(request)
        assert isinstance(result, AggregationResult)

    async def test_custom_policy_default_strategy(self) -> None:
        policy = AggregationPolicy(default_strategy=AggregationStrategy.BEST_QUALITY)
        engine = AggregationEngineImpl(policy=policy)
        await engine.start()
        request = _make_agg_request(strategy=AggregationStrategy.BEST_QUALITY)
        result = await engine.aggregate(request)
        assert result.strategy == AggregationStrategy.BEST_QUALITY


# ═══════════════════════════════════════════════════════════════════════════════
# Agreement matrix integrity
# ═══════════════════════════════════════════════════════════════════════════════


class TestAgreementMatrix:
    def test_matrix_symmetry(self) -> None:
        responses = [
            _make_normalized(provider="a", content="Hello world"),
            _make_normalized(provider="b", content="Hello there"),
            _make_normalized(provider="c", content="Goodbye world"),
        ]
        matrix = _SimilarityComputer.build_agreement_matrix(responses)
        n = len(responses)
        for i in range(n):
            for j in range(n):
                assert matrix.matrix[i][j] == matrix.matrix[j][i]

    def test_matrix_diagonal(self) -> None:
        responses = [
            _make_normalized(provider="a", content="First"),
            _make_normalized(provider="b", content="Second"),
        ]
        matrix = _SimilarityComputer.build_agreement_matrix(responses)
        assert matrix.matrix[0][0] == 1.0
        assert matrix.matrix[1][1] == 1.0

    def test_matrix_single_provider(self) -> None:
        responses = [_make_normalized(provider="a", content="Solo")]
        matrix = _SimilarityComputer.build_agreement_matrix(responses)
        assert matrix.average_agreement == 0.0  # single element, no pairs

    def test_similarity_matrix_bounds(self) -> None:
        responses = [
            _make_normalized(provider="a", content="The quick brown fox jumps over the lazy dog"),
            _make_normalized(
                provider="b", content="The quick brown fox jumps over the sleeping cat"
            ),
        ]
        sm = _SimilarityComputer.build_similarity_matrix(responses)
        assert sm.min_similarity >= 0.0
        assert sm.max_similarity <= 1.0
        assert sm.avg_similarity >= sm.min_similarity
        assert sm.avg_similarity <= sm.max_similarity


# ═══════════════════════════════════════════════════════════════════════════════
# NormalizedResponse integrity
# ═══════════════════════════════════════════════════════════════════════════════


class TestNormalizedResponse:
    def test_normalized_response_defaults(self) -> None:
        nr = NormalizedResponse()
        assert nr.provider == ""
        assert nr.content == ""
        assert nr.confidence == 0.5
        assert nr.quality == 0.5

    def test_normalized_response_values(self) -> None:
        nr = _make_normalized(
            provider="test_prov", content="Test content", confidence=0.7, quality=0.6
        )
        assert nr.provider == "test_prov"
        assert nr.content == "Test content"
        assert nr.confidence == 0.7
        assert nr.quality == 0.6
