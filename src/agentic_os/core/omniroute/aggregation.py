# ═══════════════════════════════════════════════════════════════════════════════
# OmniRoute — Aggregation Engine
# Phase 5.11
# ═══════════════════════════════════════════════════════════════════════════════
"""OmniRoute Aggregation Engine — transforms raw execution results from
multiple providers into a synthesised, ranked, consensus-validated final
response.

The aggregation pipeline in order:
  1. Normalize — convert ExecutionResult → NormalizedResponse
  2. Filter — discard invalid/unfinished results
  3. Score quality — attach quality scores to each response
  4. Compute similarity — build pairwise similarity / agreement matrix
  5. Build candidates — compute multi-metric ranking scores
  6. Run consensus — cast votes and apply consensus algorithm
  7. Detect/resolve conflicts — identify contradictory responses
  8. Select content — pick or merge content per strategy
  9. Estimate confidence — aggregate confidence from all signals
  10. Publish events — EventBus topics for observability

Thread-safety: asyncio.Lock guards shared mutable state (_StatisticsCollector,
_AuditRecorder, engine lifecycle flags). Internal components are stateless or
use only local state — no user-facing locks needed.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from collections import Counter
from typing import Any

from agentic_os.domain.events import Topic
from agentic_os.domain.omniroute import (
    AggregationCandidate,
    AggregationConfidence,
    AggregationHealth,
    AggregationMetrics,
    AggregationPolicy,
    AggregationRequest,
    AggregationResult,
    AggregationSnapshot,
    AggregationStatistics,
    AggregationStrategy,
    AgreementMatrix,
    ConflictRecord,
    ConflictResolution,
    ConflictResolutionPolicy,
    ConsensusMode,
    ConsensusResult,
    ExecutionResult,
    ExecutionState,
    MajorityResult,
    MergedContent,
    NormalizedResponse,
    SemanticCluster,
    SimilarityMatrix,
    WeightedVote,
)

log = logging.getLogger("omniroute.aggregation")


# ═══════════════════════════════════════════════════════════════════════════════
# Port Protocol
# ═══════════════════════════════════════════════════════════════════════════════


class AggregationPort:
    """OmniRoute aggregation engine — transforms raw execution results into a
    synthesised, ranked, consensus-validated final response.

    This is the port (interface) that concrete implementations must satisfy.
    All methods are async for non-blocking integration into the routing pipeline.
    """

    async def aggregate(self, request: AggregationRequest) -> AggregationResult:
        """Aggregate multiple execution results into a single final response.

        Args:
            request: Aggregation request containing results to aggregate.

        Returns:
            AggregationResult with synthesised content, confidence, and metadata.

        Raises:
            NotImplementedError: Must be overridden by subclass.
        """
        raise NotImplementedError

    async def start(self) -> None:
        """Start the engine. Must be called before first aggregate().

        Raises:
            NotImplementedError: Must be overridden by subclass.
        """
        raise NotImplementedError

    async def stop(self) -> None:
        """Stop the engine. Safe to call multiple times.

        Raises:
            NotImplementedError: Must be overridden by subclass.
        """
        raise NotImplementedError

    async def ready(self) -> bool:
        """Check engine readiness.

        Returns:
            True if the engine is started and running.
        """
        return False

    async def health(self) -> AggregationHealth:
        """Return current health snapshot.

        Returns:
            AggregationHealth with status, uptime, and aggregate stats.

        Raises:
            NotImplementedError: Must be overridden by subclass.
        """
        raise NotImplementedError

    async def metrics(self) -> AggregationMetrics:
        """Return current operational metrics.

        Returns:
            AggregationMetrics with counts, rates, and distributions.

        Raises:
            NotImplementedError: Must be overridden by subclass.
        """
        raise NotImplementedError

    async def snapshot(self) -> AggregationSnapshot:
        """Return immutable snapshot of current state.

        Returns:
            AggregationSnapshot with status and aggregate totals.

        Raises:
            NotImplementedError: Must be overridden by subclass.
        """
        raise NotImplementedError


# ═══════════════════════════════════════════════════════════════════════════════
# Internal components
# ═══════════════════════════════════════════════════════════════════════════════


class _ContentNormalizer:
    """Normalise responses to a common representation.

    Converts raw ExecutionResult objects into NormalizedResponse with
    consistent field extraction. Handles null content, missing metadata,
    and citation extraction.

    Thread-safety: Stateless — all methods are @staticmethod.
    Complexity: O(n) for n results, O(k) per trim for k content length.
    """

    @staticmethod
    def normalize(result: ExecutionResult) -> NormalizedResponse:
        """Convert an ExecutionResult into a NormalizedResponse.

        Extracts content (from .content or .output), finish_reason, citations,
        latency, cost, confidence, quality, and metadata. Falls back to empty
        strings and 0.5 defaults for missing fields.

        Args:
            result: Raw execution result from a provider.

        Returns:
            NormalizedResponse with standardised fields.

        Complexity: O(1) — field extraction only, no iteration.
        """
        content = result.content or result.output or ""
        finish_reason = result.finish_reason or ""
        citations: list[str] = []
        md = result.metadata or {}
        if "citations" in md:
            raw = md["citations"]
            citations = list(raw) if isinstance(raw, (list, tuple)) else [str(raw)]
        return NormalizedResponse(
            provider=result.provider,
            model=result.model,
            content=content,
            citations=tuple(citations),
            tokens_in=result.tokens_in,
            tokens_out=result.tokens_out,
            finish_reason=finish_reason,
            latency_ms=result.latency_ms,
            cost=result.cost,
            confidence=md.get("confidence", 0.5),
            quality=md.get("quality", 0.5),
            metadata=md,
        )

    @staticmethod
    def trim(content: str, max_len: int = 8000) -> str:
        """Truncate content to max_len characters.

        Args:
            content: Text to trim.
            max_len: Maximum length (default 8000).

        Returns:
            Truncated string if content exceeds max_len, else the original.

        Complexity: O(1) — slice operation.
        """
        return content[:max_len] if len(content) > max_len else content

    @staticmethod
    def extract_json(text: str) -> str:
        """Extract the first JSON object or array from text.

        Scans the text for the first '{' or '[' and returns the balanced
        JSON structure. Handles nested braces and brackets.

        Args:
            text: Text potentially containing JSON.

        Returns:
            Extracted JSON substring, or the original text if no JSON found.

        Complexity: O(n) for n = text length, single pass with depth tracking.
        """
        for opener, closer in [("{", "}"), ("[", "]")]:
            start = text.find(opener)
            if start >= 0:
                depth = 0
                for i in range(start, len(text)):
                    if text[i] == opener:
                        depth += 1
                    elif text[i] == closer:
                        depth -= 1
                    if depth == 0:
                        return text[start : i + 1]
        return text


class _SimilarityComputer:
    """Lightweight semantic similarity — no external APIs.

    Provides multiple similarity measures: Jaccard, cosine approximation,
    token overlap, and normalised edit distance. All operate on raw text
    without embeddings or external model calls.

    Thread-safety: Stateless — all methods are @staticmethod.
    Complexity: O(n²) for matrix methods, O(t) for pairwise (t = token count).
    """

    @staticmethod
    def token_overlap(a: str, b: str) -> float:
        """Compute token overlap similarity.

        Intersection over minimum set size. Treats empty sets as dissimilar.

        Args:
            a: First text.
            b: Second text.

        Returns:
            Similarity in [0.0, 1.0].

        Complexity: O(t_a + t_b) for tokenisation + set ops.
        """
        tokens_a = set(a.lower().split())
        tokens_b = set(b.lower().split())
        if not tokens_a or not tokens_b:
            return 0.0
        intersection = tokens_a & tokens_b
        return len(intersection) / min(len(tokens_a), len(tokens_b))

    @staticmethod
    def jaccard(a: str, b: str) -> float:
        """Compute Jaccard similarity (intersection over union).

        Args:
            a: First text.
            b: Second text.

        Returns:
            Similarity in [0.0, 1.0]. Returns 1.0 if both empty.

        Complexity: O(t_a + t_b) for tokenisation + set ops.
        """
        tokens_a = set(a.lower().split())
        tokens_b = set(b.lower().split())
        if not tokens_a and not tokens_b:
            return 1.0
        union = tokens_a | tokens_b
        if not union:
            return 0.0
        intersection = tokens_a & tokens_b
        return len(intersection) / len(union)

    @staticmethod
    def normalized_edit_distance(a: str, b: str) -> float:
        """Compute similarity based on normalised Levenshtein distance.

        Falls back to token_overlap for strings over 100 chars to avoid
        O(n*m) quadratic cost on long texts.

        Args:
            a: First text.
            b: Second text.

        Returns:
            Similarity in [0.0, 1.0]. Returns 1.0 if both empty.

        Complexity: O(min(n,m)²) for the DP table, capped at 100×100.
        """
        if not a and not b:
            return 1.0
        if not a or not b:
            return 0.0
        n, m = len(a), len(b)
        if n > 100 or m > 100:
            return _SimilarityComputer.token_overlap(a[:200], b[:200])
        dp = list(range(m + 1))
        for i in range(1, n + 1):
            prev = dp[0]
            dp[0] = i
            for j in range(1, m + 1):
                tmp = dp[j]
                cost = 0 if a[i - 1] == b[j - 1] else 1
                dp[j] = min(dp[j] + 1, dp[j - 1] + 1, prev + cost)
                prev = tmp
        max_len = max(n, m)
        return 1.0 - (dp[m] / max_len) if max_len > 0 else 1.0

    @staticmethod
    def cosine_fast(a: str, b: str) -> float:
        """Fast cosine approximation via token frequency.

        Counts token frequencies and computes cosine of the frequency vectors.
        Uses collections.Counter for O(t) frequency calculation.

        Args:
            a: First text.
            b: Second text.

        Returns:
            Similarity in [0.0, 1.0]. Returns 1.0 if both empty.

        Complexity: O(t_a + t_b) for tokenisation + vector ops.
        """
        from collections import Counter as _Counter

        tokens_a = _Counter(a.lower().split())
        tokens_b = _Counter(b.lower().split())
        all_tokens = set(tokens_a) | set(tokens_b)
        if not all_tokens:
            return 1.0
        dot = sum(tokens_a[t] * tokens_b.get(t, 0) for t in all_tokens)
        norm_a = sum(v * v for v in tokens_a.values()) ** 0.5
        norm_b = sum(v * v for v in tokens_b.values()) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    @staticmethod
    def combined(a: str, b: str) -> float:
        """Combined similarity score (weighted average of three measures).

        Weights: 0.3 Jaccard + 0.4 cosine + 0.3 edit distance.

        Args:
            a: First text.
            b: Second text.

        Returns:
            Weighted similarity in [0.0, 1.0].

        Complexity: O(t) — sum of all three component methods.
        """
        j = _SimilarityComputer.jaccard(a, b)
        c = _SimilarityComputer.cosine_fast(a, b)
        e = _SimilarityComputer.normalized_edit_distance(a[:200], b[:200])
        return 0.3 * j + 0.4 * c + 0.3 * e

    @staticmethod
    def build_agreement_matrix(
        responses: list[NormalizedResponse],
    ) -> AgreementMatrix:
        """Build pairwise agreement matrix for all responses.

        Computes combined similarity for every pair (i, j). Diagonal is 1.0.

        Args:
            responses: List of normalised responses.

        Returns:
            AgreementMatrix with providers, pairwise matrix, and average.

        Complexity: O(n² * t) for n responses and t average token count.
        """
        providers = tuple(r.provider for r in responses)
        n = len(responses)
        matrix: list[list[float]] = [[0.0] * n for _ in range(n)]
        total = 0.0
        count = 0
        for i in range(n):
            for j in range(i + 1, n):
                sim = _SimilarityComputer.combined(responses[i].content, responses[j].content)
                matrix[i][j] = sim
                matrix[j][i] = sim
                total += sim
                count += 1
            matrix[i][i] = 1.0
        avg = total / count if count > 0 else 0.0
        return AgreementMatrix(
            providers=providers,
            matrix=tuple(tuple(row) for row in matrix),
            average_agreement=avg,
        )

    @staticmethod
    def build_similarity_matrix(
        responses: list[NormalizedResponse],
    ) -> SimilarityMatrix:
        """Build a similarity matrix with min/max/avg summary.

        Wraps build_agreement_matrix and adds summary statistics
        (min, max, avg similarity across all pairs).

        Args:
            responses: List of normalised responses.

        Returns:
            SimilarityMatrix with full matrix and summary stats.

        Complexity: O(n² * t) — delegates to build_agreement_matrix.
        """
        am = _SimilarityComputer.build_agreement_matrix(responses)
        values = [
            am.matrix[i][j] for i in range(len(responses)) for j in range(i + 1, len(responses))
        ]
        min_s = min(values) if values else 0.0
        max_s = max(values) if values else 0.0
        return SimilarityMatrix(
            providers=am.providers,
            matrix=am.matrix,
            min_similarity=min_s,
            max_similarity=max_s,
            avg_similarity=am.average_agreement,
        )

    @staticmethod
    def cluster(
        responses: list[NormalizedResponse], threshold: float = 0.6
    ) -> list[SemanticCluster]:
        """Cluster responses by semantic similarity.

        Greedy single-linkage clustering: each response joins the first
        cluster whose centroid similarity exceeds threshold.

        Args:
            responses: List of normalised responses.
            threshold: Similarity threshold for clustering (default 0.6).

        Returns:
            List of SemanticCluster with label, members, and average score.

        Complexity: O(n² * t) in worst case (no clustering).
        """
        clusters: list[list[int]] = []
        n = len(responses)
        assigned: set[int] = set()
        for i in range(n):
            if i in assigned:
                continue
            group = [i]
            assigned.add(i)
            for j in range(i + 1, n):
                if j in assigned:
                    continue
                sim = _SimilarityComputer.combined(responses[i].content, responses[j].content)
                if sim >= threshold:
                    group.append(j)
                    assigned.add(j)
            clusters.append(group)
        result: list[SemanticCluster] = []
        for g in clusters:
            members = tuple(responses[idx].provider for idx in g)
            texts = tuple(responses[idx].content[:200] for idx in g)
            label = texts[0][:60] if texts else ""
            scores = [responses[idx].quality for idx in g]
            avg_score = sum(scores) / len(scores) if scores else 0.0
            result.append(
                SemanticCluster(
                    label=label,
                    members=members,
                    provider_responses=texts,
                    average_score=avg_score,
                    size=len(g),
                )
            )
        return result


class _ResponseRanker:
    """Rank candidates by multiple metrics.

    Compute multi-metric scores for each response and sort by final score.
    Weights: quality (0.25), confidence (0.20), latency (0.20), cost (0.15),
    reliability (0.10), learning_score (0.10).

    Thread-safety: Stateless.
    Complexity: O(n) for scoring, O(n log n) for sort.
    """

    @staticmethod
    def compute_candidates(
        responses: list[NormalizedResponse],
    ) -> list[AggregationCandidate]:
        """Score and rank responses into ordered candidates.

        Computes normalised latency and cost scores from raw values, then
        applies weighted sum to produce a final_score per candidate.

        Args:
            responses: Normalised responses to rank.

        Returns:
            Sorted list of AggregationCandidate (highest score first).

        Complexity: O(n + n log n) — O(n) scoring, O(n log n) sort.
        """
        candidates: list[AggregationCandidate] = []
        max_latency = max(r.latency_ms for r in responses) if responses else 1.0
        max_cost = max(r.cost for r in responses) if responses else 1.0

        for r in responses:
            latency_score = 1.0 - (r.latency_ms / max_latency) if max_latency > 0 else 1.0
            cost_score = 1.0 - (r.cost / max_cost) if max_cost > 0 else 1.0
            quality = r.quality
            confidence = r.confidence

            final = (
                0.25 * quality
                + 0.20 * confidence
                + 0.20 * latency_score
                + 0.15 * cost_score
                + 0.10 * r.metadata.get("reliability", 0.5)
                + 0.10 * r.metadata.get("learning_score", 0.5)
            )

            candidates.append(
                AggregationCandidate(
                    provider=r.provider,
                    content=r.content,
                    normalized_content=r.content,
                    quality_score=quality,
                    confidence_score=confidence,
                    latency_score=latency_score,
                    cost_score=cost_score,
                    reliability_score=r.metadata.get("reliability", 0.5),
                    learning_score=r.metadata.get("learning_score", 0.5),
                    final_score=final,
                    metadata=r.metadata,
                )
            )
        return sorted(candidates, key=lambda c: c.final_score, reverse=True)

    @staticmethod
    def pick_best(
        candidates: list[AggregationCandidate],
    ) -> AggregationCandidate:
        """Pick the highest-ranked candidate.

        Args:
            candidates: Sorted list of candidates (highest first).

        Returns:
            The top candidate, or an empty candidate if list is empty.

        Complexity: O(1).
        """
        if not candidates:
            return AggregationCandidate(provider="", content="")
        return candidates[0]


class _ConsensusEngine:
    """Multiple consensus algorithms.

    Provides 10 consensus strategies for determining agreement among
    provider responses. All methods are @staticmethod and operate on
    WeightedVote lists.

    Thread-safety: Stateless — no mutable shared state.
    Complexity: O(v) per algorithm for v votes.
    """

    @staticmethod
    def simple_majority(
        votes: list[WeightedVote],
    ) -> ConsensusResult:
        """Simple majority — >50% of votes.

        Each vote counts equally (weight=1). Winner needs >50% of total votes.

        Args:
            votes: Weighted votes from providers.

        Returns:
            ConsensusResult with reached/confidence/majority details.

        Complexity: O(v) for v votes.
        """
        counter: dict[str, int] = {}
        for v in votes:
            counter[v.value] = counter.get(v.value, 0) + 1
        if not counter:
            return ConsensusResult(reached=False, mode=ConsensusMode.SIMPLE_MAJORITY)
        winner = max(counter, key=lambda k: counter[k])
        total = sum(counter.values())
        votes_for = counter[winner]
        majority_pct = votes_for / total if total > 0 else 0.0
        threshold_met = majority_pct > 0.5
        return ConsensusResult(
            reached=threshold_met,
            value=winner,
            confidence=majority_pct,
            mode=ConsensusMode.SIMPLE_MAJORITY,
            votes=tuple(votes),
            tie=votes_for == total - votes_for,
            majority=MajorityResult(
                winner=winner,
                votes_for=votes_for,
                votes_against=total - votes_for,
                total_votes=total,
                majority_pct=majority_pct,
                threshold_met=threshold_met,
            ),
        )

    @staticmethod
    def absolute_majority(
        votes: list[WeightedVote],
    ) -> ConsensusResult:
        """Absolute majority — >= 50% + 1.

        Stricter than simple majority: requires floor(total/2)+1 votes.

        Args:
            votes: Weighted votes from providers.

        Returns:
            ConsensusResult with reached/confidence/majority details.

        Complexity: O(v) for v votes.
        """
        counter: dict[str, int] = {}
        for v in votes:
            counter[v.value] = counter.get(v.value, 0) + 1
        if not counter:
            return ConsensusResult(reached=False, mode=ConsensusMode.ABSOLUTE_MAJORITY)
        winner = max(counter, key=lambda k: counter[k])
        total = sum(counter.values())
        votes_for = counter[winner]
        abs_threshold = total / 2 + 1 if total > 1 else 1
        threshold_met = votes_for >= abs_threshold
        return ConsensusResult(
            reached=threshold_met,
            value=winner,
            confidence=votes_for / total if total > 0 else 0.0,
            mode=ConsensusMode.ABSOLUTE_MAJORITY,
            votes=tuple(votes),
            majority=MajorityResult(
                winner=winner,
                votes_for=votes_for,
                votes_against=total - votes_for,
                total_votes=total,
                majority_pct=votes_for / total if total > 0 else 0.0,
                threshold_met=threshold_met,
            ),
        )

    @staticmethod
    def super_majority(votes: list[WeightedVote], threshold: float = 0.66) -> ConsensusResult:
        """Super majority — votes >= threshold (default 66%).

        Configurable threshold for near-unanimous decisions.

        Args:
            votes: Weighted votes from providers.
            threshold: Required fraction (default 0.66).

        Returns:
            ConsensusResult with reached/confidence/majority details.

        Complexity: O(v) for v votes.
        """
        counter: dict[str, int] = {}
        for v in votes:
            counter[v.value] = counter.get(v.value, 0) + 1
        if not counter:
            return ConsensusResult(reached=False, mode=ConsensusMode.SUPER_MAJORITY)
        winner = max(counter, key=lambda k: counter[k])
        total = sum(counter.values())
        votes_for = counter[winner]
        pct = votes_for / total if total > 0 else 0.0
        threshold_met = pct >= threshold
        return ConsensusResult(
            reached=threshold_met,
            value=winner,
            confidence=pct,
            mode=ConsensusMode.SUPER_MAJORITY,
            votes=tuple(votes),
            majority=MajorityResult(
                winner=winner,
                votes_for=votes_for,
                votes_against=total - votes_for,
                total_votes=total,
                majority_pct=pct,
                threshold_met=threshold_met,
            ),
        )

    @staticmethod
    def unanimous(
        votes: list[WeightedVote],
    ) -> ConsensusResult:
        """Unanimous — all votes for the same value.

        The strictest consensus mode — requires 100% agreement.

        Args:
            votes: Weighted votes from providers.

        Returns:
            ConsensusResult with reached=True only if all votes agree.

        Complexity: O(v) for v votes.
        """
        counter: dict[str, int] = {}
        for v in votes:
            counter[v.value] = counter.get(v.value, 0) + 1
        if not counter:
            return ConsensusResult(reached=False, mode=ConsensusMode.UNANIMOUS)
        reached = len(counter) == 1
        winner = list(counter.keys())[0] if reached else ""
        return ConsensusResult(
            reached=reached,
            value=winner,
            confidence=1.0 if reached else 0.0,
            mode=ConsensusMode.UNANIMOUS,
            votes=tuple(votes),
        )

    @staticmethod
    def weighted_voting(
        votes: list[WeightedVote],
    ) -> ConsensusResult:
        """Weighted voting — >50% of weighted score.

        Each vote's weight is considered, not just count. Useful when
        providers have different reliability or authority levels.

        Args:
            votes: Weighted votes from providers.

        Returns:
            ConsensusResult with reached/confidence details.

        Complexity: O(v) for v votes.
        """
        scores: dict[str, float] = {}
        for v in votes:
            scores[v.value] = scores.get(v.value, 0.0) + v.weight
        if not scores:
            return ConsensusResult(reached=False, mode=ConsensusMode.WEIGHTED_VOTING)
        winner = max(scores, key=lambda k: scores[k])
        total = sum(scores.values())
        pct = scores[winner] / total if total > 0 else 0.0
        threshold_met = pct > 0.5
        return ConsensusResult(
            reached=threshold_met,
            value=winner,
            confidence=pct,
            mode=ConsensusMode.WEIGHTED_VOTING,
            votes=tuple(votes),
        )

    @staticmethod
    def confidence_weighted(
        votes: list[WeightedVote],
    ) -> ConsensusResult:
        """Confidence-weighted voting — >50% with confidence multipliers.

        Each vote's weight is scaled by the provider's confidence score.
        Higher-confidence votes influence the outcome more.

        Args:
            votes: Weighted votes from providers.

        Returns:
            ConsensusResult with reached/confidence details.

        Complexity: O(v) for v votes.
        """
        scores: dict[str, float] = {}
        total_weight = 0.0
        for v in votes:
            w = v.weight * v.confidence
            scores[v.value] = scores.get(v.value, 0.0) + w
            total_weight += w
        if not scores or total_weight == 0:
            return ConsensusResult(reached=False, mode=ConsensusMode.CONFIDENCE_WEIGHTED)
        winner = max(scores, key=lambda k: scores[k])
        pct = scores[winner] / total_weight
        threshold_met = pct > 0.5
        return ConsensusResult(
            reached=threshold_met,
            value=winner,
            confidence=pct,
            mode=ConsensusMode.CONFIDENCE_WEIGHTED,
            votes=tuple(votes),
        )

    @staticmethod
    def quality_weighted(
        votes: list[WeightedVote],
    ) -> ConsensusResult:
        """Quality-weighted voting — >50% with quality multipliers.

        Each vote's weight is scaled by the provider's quality score.
        Higher-quality responses have more influence.

        Args:
            votes: Weighted votes from providers.

        Returns:
            ConsensusResult with reached/confidence details.

        Complexity: O(v) for v votes.
        """
        scores: dict[str, float] = {}
        total_weight = 0.0
        for v in votes:
            w = v.weight * v.quality
            scores[v.value] = scores.get(v.value, 0.0) + w
            total_weight += w
        if not scores or total_weight == 0:
            return ConsensusResult(reached=False, mode=ConsensusMode.QUALITY_WEIGHTED)
        winner = max(scores, key=lambda k: scores[k])
        pct = scores[winner] / total_weight
        threshold_met = pct > 0.5
        return ConsensusResult(
            reached=threshold_met,
            value=winner,
            confidence=pct,
            mode=ConsensusMode.QUALITY_WEIGHTED,
            votes=tuple(votes),
        )

    @staticmethod
    def bayesian(votes: list[WeightedVote], prior: float = 0.5) -> ConsensusResult:
        """Bayesian consensus — Bayesian posterior-weighted voting.

        Applies a Bayesian update to each vote's confidence using a prior,
        combining prior belief with observed confidence. Useful when some
        providers are unreliable and should be down-weighted.

        Args:
            votes: Weighted votes from providers.
            prior: Bayesian prior (default 0.5, neutral).

        Returns:
            ConsensusResult with reached/confidence details.

        Complexity: O(v) for v votes.
        """
        scores: dict[str, float] = {}
        for v in votes:
            posterior = (prior * v.confidence + (1 - prior)) / (
                1 + (1 - prior) * (1 - v.confidence)
            )
            scores[v.value] = scores.get(v.value, 0.0) + v.weight * posterior
        if not scores:
            return ConsensusResult(reached=False, mode=ConsensusMode.BAYESIAN)
        winner = max(scores, key=lambda k: scores[k])
        total = sum(scores.values())
        pct = scores[winner] / total if total > 0 else 0.0
        threshold_met = pct > 0.5
        return ConsensusResult(
            reached=threshold_met,
            value=winner,
            confidence=pct,
            mode=ConsensusMode.BAYESIAN,
            votes=tuple(votes),
        )

    @staticmethod
    def quorum(
        votes: list[WeightedVote], quorum_size: int = 3, threshold: float = 0.5
    ) -> ConsensusResult:
        """Quorum-based consensus — requires minimum voters before deciding.

        Only considers consensus reached if at least quorum_size votes exist.
        Prevents premature decisions with too few providers.

        Args:
            votes: Weighted votes from providers.
            quorum_size: Minimum voters for a valid decision (default 3).
            threshold: Supermajority ratio (default 0.5).

        Returns:
            ConsensusResult with reached/confidence details.

        Complexity: O(v) for v votes.
        """
        if len(votes) < quorum_size:
            return ConsensusResult(
                reached=False,
                mode=ConsensusMode.QUORUM,
                confidence=0.0,
            )
        counter: dict[str, int] = {}
        for v in votes:
            counter[v.value] = counter.get(v.value, 0) + 1
        if not counter:
            return ConsensusResult(reached=False, mode=ConsensusMode.QUORUM)
        winner = max(counter, key=lambda k: counter[k])
        total = sum(counter.values())
        pct = counter[winner] / total if total > 0 else 0.0
        threshold_met = pct >= threshold
        return ConsensusResult(
            reached=threshold_met,
            value=winner,
            confidence=pct,
            mode=ConsensusMode.QUORUM,
            votes=tuple(votes),
        )

    @staticmethod
    def consensus_threshold(votes: list[WeightedVote], threshold: float = 0.8) -> ConsensusResult:
        """Configurable threshold consensus — winner must exceed threshold.

        The most flexible mode: the winning option must receive votes
        exceeding the configured threshold fraction.

        Args:
            votes: Weighted votes from providers.
            threshold: Required fraction (default 0.8).

        Returns:
            ConsensusResult with reached/confidence details.

        Complexity: O(v) for v votes.
        """
        counter: dict[str, int] = {}
        for v in votes:
            counter[v.value] = counter.get(v.value, 0) + 1
        if not counter:
            return ConsensusResult(reached=False, mode=ConsensusMode.CONSENSUS_THRESHOLD)
        winner = max(counter, key=lambda k: counter[k])
        total = sum(counter.values())
        pct = counter[winner] / total if total > 0 else 0.0
        threshold_met = pct >= threshold
        return ConsensusResult(
            reached=threshold_met,
            value=winner,
            confidence=pct,
            mode=ConsensusMode.CONSENSUS_THRESHOLD,
            votes=tuple(votes),
        )


class _VotingEngine:
    """Vote casting and tallying.

    Converts normalised responses into WeightedVotes and dispatches
    to the appropriate consensus algorithm.

    Thread-safety: Stateless.
    Complexity: O(v) for v responses.
    """

    @staticmethod
    def cast_votes(
        responses: list[NormalizedResponse],
    ) -> list[WeightedVote]:
        """Convert normalised responses into WeightedVote objects.

        Each vote has weight=1.0, with confidence, quality, latency, and
        cost carried through for weighted consensus algorithms.

        Args:
            responses: Normalised responses to convert.

        Returns:
            List of WeightedVote, one per response.

        Complexity: O(n) for n responses.
        """
        return [
            WeightedVote(
                provider=r.provider,
                value=r.content,
                weight=1.0,
                confidence=r.confidence,
                quality=r.quality,
                latency_ms=r.latency_ms,
                cost=r.cost,
            )
            for r in responses
        ]

    @staticmethod
    def run_consensus(
        votes: list[WeightedVote],
        mode: ConsensusMode = ConsensusMode.SIMPLE_MAJORITY,
    ) -> ConsensusResult:
        """Run consensus using the specified mode.

        Dispatches to the appropriate _ConsensusEngine method based on mode.

        Args:
            votes: Weighted votes from providers.
            mode: Consensus algorithm to use (default SIMPLE_MAJORITY).

        Returns:
            ConsensusResult with reached/confidence/majority details.

        Raises:
            No exceptions — all modes have safe fallback values.

        Complexity: O(v) — dispatches to the underlying algorithm.
        """
        if mode == ConsensusMode.SIMPLE_MAJORITY:
            return _ConsensusEngine.simple_majority(votes)
        if mode == ConsensusMode.ABSOLUTE_MAJORITY:
            return _ConsensusEngine.absolute_majority(votes)
        if mode == ConsensusMode.SUPER_MAJORITY:
            return _ConsensusEngine.super_majority(votes)
        if mode == ConsensusMode.UNANIMOUS:
            return _ConsensusEngine.unanimous(votes)
        if mode == ConsensusMode.WEIGHTED_VOTING:
            return _ConsensusEngine.weighted_voting(votes)
        if mode == ConsensusMode.CONFIDENCE_WEIGHTED:
            return _ConsensusEngine.confidence_weighted(votes)
        if mode == ConsensusMode.QUALITY_WEIGHTED:
            return _ConsensusEngine.quality_weighted(votes)
        if mode == ConsensusMode.BAYESIAN:
            return _ConsensusEngine.bayesian(votes)
        if mode == ConsensusMode.QUORUM:
            return _ConsensusEngine.quorum(votes)
        if mode == ConsensusMode.CONSENSUS_THRESHOLD:
            return _ConsensusEngine.consensus_threshold(votes)
        return _ConsensusEngine.simple_majority(votes)


class _WeightedVoting:
    """Weighted scoring for candidates.

    Converts AggregationCandidate objects into WeightedVote with final
    scores as vote weights.

    Thread-safety: Stateless.
    Complexity: O(c) for c candidates.
    """

    @staticmethod
    def score(
        candidates: list[AggregationCandidate],
    ) -> list[WeightedVote]:
        """Score candidates and produce weighted votes.

        Each candidate's final_score becomes the vote weight, enabling
        weighted consensus algorithms to consider overall candidate quality.

        Args:
            candidates: Ranked aggregation candidates.

        Returns:
            List of WeightedVote with weight = final_score.

        Complexity: O(c) for c candidates.
        """
        return [
            WeightedVote(
                provider=c.provider,
                value=c.content[:500],
                weight=c.final_score,
                confidence=c.confidence_score,
                quality=c.quality_score,
                latency_ms=c.metadata.get("latency_ms", 0.0),
                cost=c.metadata.get("cost", 0.0),
            )
            for c in candidates
        ]


class _ResponseMerger:
    """Merge responses from multiple providers.

    Supports text concatenation, JSON merging, citation deduplication,
    metadata aggregation, and streaming chunk assembly.

    Thread-safety: Stateless.
    Complexity: O(n) for n responses.
    """

    @staticmethod
    def merge_text(
        responses: list[NormalizedResponse],
        strategy: AggregationStrategy = AggregationStrategy.MERGE,
    ) -> MergedContent:
        """Merge text responses with deduplication.

        Joins unique responses with double-newline separators. Deduplicates
        by MD5 hash of content to avoid repetitions.

        Args:
            responses: Normalised responses to merge.
            strategy: Unused, reserved for custom merge strategies.

        Returns:
            MergedContent with combined text, sources, and metadata.

        Complexity: O(n) for n responses + O(k) per hash.
        """
        if not responses:
            return MergedContent(content="")
        if len(responses) == 1:
            return MergedContent(
                content=responses[0].content,
                sources=(responses[0].provider,),
                total_source_count=1,
                merge_type="text",
            )
        seen: set[str] = set()
        fragments: list[str] = []
        sources: list[str] = []
        for r in responses:
            text = r.content.strip()
            key = hashlib.md5(text.encode()).hexdigest()
            if key not in seen:
                seen.add(key)
                fragments.append(text)
                sources.append(r.provider)
        merged = "\n\n".join(fragments)
        return MergedContent(
            content=merged,
            sources=tuple(sources),
            fragments=tuple(fragments),
            total_source_count=len(sources),
            merge_type="text",
        )

    @staticmethod
    def merge_json(
        responses: list[NormalizedResponse],
    ) -> MergedContent:
        """Merge JSON responses by deep-updating a shared dict.

        Each response's JSON content is parsed and merged into a single dict
        using dict.update(). Non-dict or parse-failure responses are skipped.

        Args:
            responses: Normalised responses with JSON content.

        Returns:
            MergedContent with the merged JSON string.

        Complexity: O(n) for n responses.
        """
        merged: dict[str, Any] = {}
        sources: list[str] = []
        for r in responses:
            try:
                import json

                data = json.loads(r.content)
                if isinstance(data, dict):
                    merged.update(data)
                    sources.append(r.provider)
            except (json.JSONDecodeError, ValueError):
                continue
        import json

        content = json.dumps(merged, indent=2) if merged else ""
        return MergedContent(
            content=content,
            sources=tuple(sources),
            total_source_count=len(sources),
            merge_type="json",
        )

    @staticmethod
    def merge_citations(
        responses: list[NormalizedResponse],
    ) -> list[str]:
        """Deduplicate citations across multiple responses.

        Uses MD5 hash deduplication to produce a unique list.

        Args:
            responses: Normalised responses with citations.

        Returns:
            List of unique citation strings.

        Complexity: O(c) for c total citations across all responses.
        """
        all_citations: list[str] = []
        seen_cit: set[str] = set()
        for r in responses:
            for c in r.citations:
                key = hashlib.md5(c.encode()).hexdigest()
                if key not in seen_cit:
                    seen_cit.add(key)
                    all_citations.append(c)
        return all_citations

    @staticmethod
    def merge_metadata(
        responses: list[NormalizedResponse],
    ) -> dict[str, Any]:
        """Aggregate metadata across responses.

        Sums tokens (in/out), cost, latency, and tracks unique providers.

        Args:
            responses: Normalised responses to aggregate.

        Returns:
            Dict with total_tokens, total_cost, total_latency_ms,
            provider_count, and providers list.

        Complexity: O(n) for n responses.
        """
        total_tokens = sum(r.tokens_in + r.tokens_out for r in responses)
        total_cost = sum(r.cost for r in responses)
        total_latency = sum(r.latency_ms for r in responses)
        providers = list({r.provider for r in responses})
        return {
            "total_tokens": total_tokens,
            "total_cost": round(total_cost, 6),
            "total_latency_ms": round(total_latency, 2),
            "provider_count": len(providers),
            "providers": providers,
        }

    @staticmethod
    def merge_streaming(
        chunks: list[str],
    ) -> str:
        """Concatenate streaming chunks into a single string.

        Args:
            chunks: Ordered list of text chunks from streaming.

        Returns:
            Concatenated string.

        Complexity: O(k) for k total chars (string concatenation).
        """
        return "".join(chunks)


class _ConflictResolver:
    """Detect and resolve conflicts between responses.

    Detects low-similarity content pairs and resolves them according to
    configurable policy (trust majority, highest confidence, mark conflict).

    Thread-safety: Stateless.
    Complexity: O(n² * t) for detection, O(c) for resolution.
    """

    @staticmethod
    def detect(
        responses: list[NormalizedResponse],
    ) -> ConflictResolution:
        """Detect conflicts between pairs of responses.

        A conflict is flagged when combined similarity < 0.4. Each conflict
        records the conflicting values, providers, and confidences.

        Args:
            responses: Normalised responses to check.

        Returns:
            ConflictResolution with a list of ConflictRecord entries.

        Complexity: O(n² * t) for n responses and t average token count.
        """
        conflicts: list[ConflictRecord] = []
        if len(responses) < 2:
            return ConflictResolution(conflicts=(), total_conflicts=0, resolved_count=0)

        for i in range(len(responses)):
            for j in range(i + 1, len(responses)):
                r1, r2 = responses[i], responses[j]
                sim = _SimilarityComputer.combined(r1.content, r2.content)
                if sim < 0.4:
                    conflicts.append(
                        ConflictRecord(
                            conflict_field="content",
                            values=(r1.content[:500], r2.content[:500]),
                            providers=(r1.provider, r2.provider),
                            confidences=(r1.confidence, r2.confidence),
                            resolved=False,
                            resolution="",
                            resolution_policy="manual",
                        )
                    )
        return ConflictResolution(
            conflicts=tuple(conflicts),
            total_conflicts=len(conflicts),
            resolved_count=0,
            policy=ConflictResolutionPolicy.MARK_CONFLICT,
        )

    @staticmethod
    def resolve(
        conflict: ConflictResolution,
        policy: ConflictResolutionPolicy = ConflictResolutionPolicy.TRUST_MAJORITY,
    ) -> ConflictResolution:
        """Resolve conflicts according to the specified policy.

        Policies:
        - TRUST_HIGHEST_CONFIDENCE: pick the value with higher confidence
        - MARK_CONFLICT: annotate with "CONFLICT:" prefix
        - TRUST_LATEST / default: pick the first value

        Args:
            conflict: Unresolved conflicts from detect().
            policy: Resolution policy to apply.

        Returns:
            ConflictResolution with resolved records.

        Complexity: O(c) for c conflicts.
        """
        resolved_records: list[ConflictRecord] = []
        for c in conflict.conflicts:
            if not c.confidences:
                rec = ConflictRecord(**{k: getattr(c, k) for k in c.__dataclass_fields__})
                resolved_records.append(rec)
                continue
            resolved: bool = True
            result: str = ""
            if policy == ConflictResolutionPolicy.TRUST_HIGHEST_CONFIDENCE:
                idx = max(range(len(c.confidences)), key=lambda k: c.confidences[k])
                result = c.values[idx] if idx < len(c.values) else ""
            elif policy == ConflictResolutionPolicy.MARK_CONFLICT:
                result = f"CONFLICT: {', '.join(c.values)}"
            elif policy == ConflictResolutionPolicy.TRUST_LATEST:
                result = c.values[0] if c.values else ""
            else:
                result = c.values[0] if c.values else ""
            resolved_records.append(
                ConflictRecord(
                    conflict_field=c.conflict_field,
                    values=c.values,
                    providers=c.providers,
                    confidences=c.confidences,
                    resolved=resolved,
                    resolution=result,
                    resolution_policy=policy.value,
                )
            )
        resolved_count = sum(1 for r in resolved_records if r.resolved)
        return ConflictResolution(
            conflicts=tuple(resolved_records),
            total_conflicts=len(resolved_records),
            resolved_count=resolved_count,
            policy=policy,
        )


class _QualityScorer:
    """Score quality of each candidate.

    Computes an overall quality score per response based on content length,
    finish reason validity, latency freshness, and existing quality metadata.

    Thread-safety: Stateless.
    Complexity: O(n) for n responses.
    """

    @staticmethod
    def score(responses: list[NormalizedResponse]) -> list[NormalizedResponse]:
        """Score each response's quality and return copies with updated quality.

        Quality formula: 0.35 * r.quality + 0.25 * length_score +
        0.20 * has_finish + 0.20 * (1.0 - freshness)

        Args:
            responses: Normalised responses to score.

        Returns:
            New list of NormalizedResponse with updated quality field and
            quality_score in metadata.

        Complexity: O(n) for n responses.
        """
        scored: list[NormalizedResponse] = []
        for r in responses:
            content = r.content

            length = len(content)
            length_score = min(1.0, length / 2000.0)

            has_finish = 1.0 if r.finish_reason in ("stop", "end_turn", "complete") else 0.8
            freshness = min(1.0, r.latency_ms / 10000.0)

            overall = (
                0.35 * r.quality
                + 0.25 * length_score
                + 0.20 * has_finish
                + 0.20 * (1.0 - freshness)
            )

            md = dict(r.metadata)
            md["quality_score"] = round(overall, 4)
            scored.append(
                NormalizedResponse(
                    provider=r.provider,
                    model=r.model,
                    content=content,
                    citations=r.citations,
                    tokens_in=r.tokens_in,
                    tokens_out=r.tokens_out,
                    finish_reason=r.finish_reason,
                    latency_ms=r.latency_ms,
                    cost=r.cost,
                    confidence=r.confidence,
                    quality=overall,
                    metadata=md,
                )
            )
        return scored


class _ConfidenceEstimator:
    """Estimate confidence levels for aggregate results.

    Combines provider confidence, citation confidence, and consensus
    confidence into a single overall confidence score with uncertainty
    and risk score.

    Thread-safety: Stateless.
    Complexity: O(n) for n responses.
    """

    @staticmethod
    def estimate(
        responses: list[NormalizedResponse],
        consensus: ConsensusResult | None = None,
    ) -> AggregationConfidence:
        """Estimate aggregate confidence from multiple signals.

        Scores: avg_provider_conf, citation_conf, consensus_conf * 0.5.

        Returns:
            AggregationConfidence with overall, per_section,
            provider_confidence, uncertainty, and risk_score.

        Complexity: O(n) for n responses.
        """
        if not responses:
            return AggregationConfidence(
                overall=0.5,
                uncertainty=0.5,
                risk_score=0.5,
            )

        provider_confidence: dict[str, float] = {r.provider: r.confidence for r in responses}
        avg_provider_conf = (
            sum(r.confidence for r in responses) / len(responses) if responses else 0.5
        )

        per_section: dict[str, float] = {}
        for i, r in enumerate(responses):
            tokens = r.content.split()
            if tokens:
                per_section[f"section_{i}"] = r.confidence

        citation_conf = max(r.confidence for r in responses) if responses else 0.5
        consensus_conf = consensus.confidence if consensus and consensus.reached else 0.0

        scores = [
            avg_provider_conf,
            citation_conf,
            consensus_conf * 0.5 if consensus else 0.0,
        ]
        overall = sum(scores) / len(scores) if scores else 0.5
        uncertainty = 1.0 - overall
        risk_score = 1.0 - (overall * 0.7 + 0.3)

        return AggregationConfidence(
            overall=overall,
            per_section=per_section,
            provider_confidence=provider_confidence,
            citation_confidence=citation_conf,
            consensus_confidence=consensus_conf,
            uncertainty=uncertainty,
            risk_score=risk_score,
        )


class _EnsembleBuilder:
    """Build ensemble responses from multiple candidates.

    Supports top-N ensemble and full stacking with score-based ranking.

    Thread-safety: Stateless.
    Complexity: O(c log c) for stacking sort, O(1) for top-N selection.
    """

    @staticmethod
    def build_ensemble(
        candidates: list[AggregationCandidate],
        max_providers: int = 3,
    ) -> MergedContent:
        """Build top-N ensemble from the highest-ranked candidates.

        Takes the top max_providers candidates and joins their content with
        "---" separators.

        Args:
            candidates: Ranked aggregation candidates.
            max_providers: Maximum number of providers to include (default 3).

        Returns:
            MergedContent with ensemble text and source tracking.

        Complexity: O(max_providers) — selects from pre-sorted list.
        """
        top = candidates[:max_providers]
        fragments: list[str] = []
        sources: list[str] = []
        for c in top:
            fragments.append(c.content)
            sources.append(c.provider)
        content = "\n\n---\n\n".join(fragments)
        return MergedContent(
            content=content,
            sources=tuple(sources),
            fragments=tuple(fragments),
            total_source_count=len(sources),
            merge_type="ensemble",
        )

    @staticmethod
    def build_stacked(
        candidates: list[AggregationCandidate],
    ) -> MergedContent:
        """Build a fully stacked response from ALL candidates.

        Sorts candidates by final_score (highest first) and joins all
        content with "---" separators.

        Args:
            candidates: Aggregation candidates to stack.

        Returns:
            MergedContent with stacked text and source tracking.

        Complexity: O(c log c) for sort by final_score.
        """
        ranked = sorted(candidates, key=lambda c: c.final_score, reverse=True)
        fragments: list[str] = []
        sources: list[str] = []
        for c in ranked:
            fragments.append(c.content)
            sources.append(c.provider)
        content = "\n\n---\n\n".join(fragments)
        return MergedContent(
            content=content,
            sources=tuple(sources),
            fragments=tuple(fragments),
            total_source_count=len(sources),
            merge_type="stacked",
        )


class _StatisticsCollector:
    """Collect aggregation statistics.

    Thread-safe: asyncio.Lock is NOT used internally — callers wrap
    record_aggregation() and snapshot() with the engine's lock.

    Complexity: O(1) per record, O(k) for snapshot/metrics (k = strategy count).
    """

    def __init__(self) -> None:
        """Initialise all counters to zero.

        Tracks: total, consensus, merge, conflicts, similarity sum,
        confidence sum, quality sum, strategy usage, provider distribution,
        and latency list.
        """
        self._total: int = 0
        self._consensus_count: int = 0
        self._merge_count: int = 0
        self._conflicts: int = 0
        self._total_sim: float = 0.0
        self._sim_count: int = 0
        self._total_conf: float = 0.0
        self._total_quality: float = 0.0
        self._count: int = 0
        self._strategy_usage: Counter[str] = Counter()
        self._provider_distribution: Counter[str] = Counter()
        self._latencies: list[float] = []

    def record_aggregation(
        self,
        strategy: AggregationStrategy,
        consensus_reached: bool,
        conflict_count: int,
        selected_provider: str,
        avg_similarity: float = 0.0,
        avg_confidence: float = 0.0,
        avg_quality: float = 0.0,
        latency_ms: float = 0.0,
    ) -> None:
        """Record one aggregation result into the statistics counters.

        Must be called under the engine's asyncio.Lock for thread safety.

        Args:
            strategy: The strategy used.
            consensus_reached: Whether consensus was reached.
            conflict_count: Number of conflicts detected.
            selected_provider: The provider selected.
            avg_similarity: Average similarity (0.0 to skip).
            avg_confidence: Average confidence.
            avg_quality: Average quality.
            latency_ms: Duration in milliseconds.

        Complexity: O(1) — all counter operations.
        """
        self._total += 1
        if consensus_reached:
            self._consensus_count += 1
        if strategy in (
            AggregationStrategy.MERGE,
            AggregationStrategy.ENSEMBLE,
            AggregationStrategy.STACKING,
        ):
            self._merge_count += 1
        self._conflicts += conflict_count
        self._strategy_usage[strategy.value] += 1
        self._provider_distribution[selected_provider] += 1
        if avg_similarity > 0:
            self._total_sim += avg_similarity
            self._sim_count += 1
        self._total_conf += avg_confidence
        self._total_quality += avg_quality
        self._count += 1
        self._latencies.append(latency_ms)

    def snapshot(self) -> AggregationStatistics:
        """Return a point-in-time snapshot of all statistics.

        Returns:
            AggregationStatistics with totals, rates, and averages.

        Complexity: O(k) for k unique strategies used.
        """
        avg_conf = self._total_conf / self._count if self._count > 0 else 0.0
        avg_qual = self._total_quality / self._count if self._count > 0 else 0.0
        avg_lat = sum(self._latencies) / len(self._latencies) if self._latencies else 0.0
        return AggregationStatistics(
            total_aggregations=self._total,
            avg_latency_ms=avg_lat,
            strategy_breakdown=dict(self._strategy_usage),
            consensus_count=self._consensus_count,
            consensus_rate=self._consensus_count / self._total if self._total > 0 else 0.0,
            conflict_count=self._conflicts,
            conflict_rate=self._conflicts / self._total if self._total > 0 else 0.0,
            dedup_count=0,
            avg_quality=avg_qual,
            avg_confidence=avg_conf,
        )

    def metrics(self) -> AggregationMetrics:
        """Return operational metrics for observability.

        Returns:
            AggregationMetrics with counts, rates, distributions.

        Complexity: O(k) for k unique strategies.
        """
        avg_sim = self._total_sim / self._sim_count if self._sim_count > 0 else 0.0
        avg_conf = self._total_conf / self._count if self._count > 0 else 0.0
        avg_qual = self._total_quality / self._count if self._count > 0 else 0.0
        avg_lat = sum(self._latencies) / len(self._latencies) if self._latencies else 0.0
        return AggregationMetrics(
            aggregation_count=self._total,
            consensus_count=self._consensus_count,
            merge_count=self._merge_count,
            average_similarity=avg_sim,
            average_confidence=avg_conf,
            average_quality=avg_qual,
            majority_rate=self._consensus_count / self._total if self._total > 0 else 0.0,
            conflict_rate=self._conflicts / self._total if self._total > 0 else 0.0,
            consensus_latency_ms=avg_lat,
            selected_provider_distribution=dict(self._provider_distribution),
            strategy_usage=dict(self._strategy_usage),
        )


class _ExplanationBuilder:
    """Build human-readable explanations for aggregation decisions.

    Formats request ID, strategy, selected provider, and candidate details
    into a structured text explanation.

    Thread-safety: Stateless.
    Complexity: O(c) for c candidates.
    """

    @staticmethod
    def explain(
        request_id: str,
        strategy: AggregationStrategy,
        candidates: list[AggregationCandidate],
        selected: str,
    ) -> str:
        """Build a human-readable explanation of the aggregation decision.

        Args:
            request_id: The request identifier.
            strategy: The strategy used.
            candidates: Ranked candidates with scores.
            selected: The provider selected.

        Returns:
            Multi-line explanation string.

        Complexity: O(c) for c candidates.
        """
        lines: list[str] = [
            f"Aggregation for request {request_id}",
            f"Strategy: {strategy.value}",
            f"Selected provider: {selected}",
            "Candidates:",
        ]
        for c in candidates:
            lines.append(
                f"  - {c.provider}: final_score={c.final_score:.3f}, "
                f"quality={c.quality_score:.3f}, confidence={c.confidence_score:.3f}"
            )
        return "\n".join(lines)


class _AuditRecorder:
    """Record aggregation audit trails.

    Maintains an in-memory ordered history of all aggregation operations.
    Each record captures request_id, strategy, counts, and outcome.

    Thread-safety: Must be called under engine's asyncio.Lock.
    Complexity: O(1) per record, O(h) for get_history (h = history size).
    """

    def __init__(self) -> None:
        """Initialise empty audit record list."""
        self._records: list[dict[str, Any]] = []

    def record(
        self,
        request_id: str,
        strategy: AggregationStrategy,
        provider_count: int,
        conflict_count: int,
        selected_provider: str,
        consensus_reached: bool,
        duration_ms: float,
        error: str = "",
    ) -> None:
        """Record one aggregation audit entry.

        Must be called under the engine's asyncio.Lock for thread safety.

        Args:
            request_id: Request identifier.
            strategy: Strategy used.
            provider_count: Number of providers.
            conflict_count: Number of conflicts.
            selected_provider: The selected provider.
            consensus_reached: Whether consensus was reached.
            duration_ms: Duration in milliseconds.
            error: Error string if aggregation failed (default empty).

        Complexity: O(1) — list append.
        """
        self._records.append(
            {
                "request_id": request_id,
                "strategy": strategy.value,
                "provider_count": provider_count,
                "conflict_count": conflict_count,
                "selected_provider": selected_provider,
                "consensus_reached": consensus_reached,
                "duration_ms": duration_ms,
                "timestamp": time.time(),
                "error": error,
            }
        )

    def get_history(self) -> tuple[dict[str, Any], ...]:
        """Return immutable copy of the audit history.

        Returns:
            Tuple of audit record dicts in chronological order.

        Complexity: O(h) for h records (tuple copy).
        """
        return tuple(self._records)


# ═══════════════════════════════════════════════════════════════════════════════
# Main Engine
# ═══════════════════════════════════════════════════════════════════════════════


class AggregationEngineImpl(AggregationPort):
    """Production-grade aggregation engine.

    Combines, ranks, scores, and synthesises execution results from multiple
    providers into a single high-quality response. Integrates with EventBus
    for observability and HealthRegistry for lifecycle monitoring.

    Thread-safety:
    - asyncio.Lock protects: _started, _running, _stats, _audit.
    - Internal components (_ContentNormalizer, etc.) are stateless.
    - snapshot()/metrics() also acquire the lock.

    Lifecycle:
        engine = AggregationEngineImpl(event_bus=bus)
        await engine.start()
        result = await engine.aggregate(request)
        await engine.stop()

    Complexity:
    - aggregate(): O(n² * t) worst case for n results with t avg tokens.
      - Normalization: O(n)
      - Similarity matrix: O(n² * t)
      - Quality scoring: O(n)
      - Ranking: O(n log n)
      - Consensus: O(n)
      - Conflict detection: O(n² * t)
      - Merge: O(n)
    - Typical case (2-5 providers): O(1) with small constants.
    """

    def __init__(
        self,
        event_bus: Any = None,
        policy: AggregationPolicy | None = None,
    ) -> None:
        """Initialise engine with optional event bus and policy.

        Args:
            event_bus: EventBus instance for publishing aggregation events.
                       Pass None (default) to disable event publishing.
            policy: AggregationPolicy controlling consensus mode and conflict
                    resolution. Uses defaults if omitted.
        """
        self._event_bus = event_bus
        self._policy = policy or AggregationPolicy()
        self._lock = asyncio.Lock()
        self._stats = _StatisticsCollector()
        self._audit = _AuditRecorder()
        self._started: bool = False
        self._start_time: float = 0.0
        self._running: bool = False

    async def start(self) -> None:
        """Start the engine.

        Sets running flag and records start time. Must be called before
        aggregate(). Safe to call multiple times (idempotent).

        Thread-safety: Acquires self._lock.
        """
        async with self._lock:
            self._started = True
            self._start_time = time.time()
            self._running = True

    async def stop(self) -> None:
        """Stop the engine.

        Clears running flag. In-flight aggregate() calls will complete.
        Safe to call multiple times.

        Thread-safety: Acquires self._lock.
        """
        async with self._lock:
            self._running = False

    async def ready(self) -> bool:
        """Check if the engine is started and running.

        Returns:
            True if start() has been called and stop() has not.
        """
        return self._started and self._running

    async def health(self) -> AggregationHealth:
        """Return a health snapshot for HealthRegistry.

        Returns:
            AggregationHealth with status, uptime, total aggregations,
            average latency, conflict rate, and consensus rate.

        Thread-safety: Acquires self._lock.
        Complexity: O(1).
        """
        uptime = time.time() - self._start_time if self._start_time > 0 else 0.0
        stats = self._stats.snapshot()
        async with self._lock:
            return AggregationHealth(
                status="healthy" if self._running else "stopped",
                uptime_s=uptime,
                total_aggregations=stats.total_aggregations,
                avg_latency_ms=stats.avg_latency_ms,
                active_count=0,
                conflict_rate=stats.conflict_rate,
                consensus_rate=stats.consensus_rate,
            )

    async def metrics(self) -> AggregationMetrics:
        """Return operational metrics.

        Returns:
            AggregationMetrics with counts, rates, distributions.

        Thread-safety: Delegates to _StatisticsCollector.metrics().
        Complexity: O(k) for k unique strategies.
        """
        return self._stats.metrics()

    async def snapshot(self) -> AggregationSnapshot:
        """Return immutable point-in-time state snapshot.

        Returns:
            AggregationSnapshot with status, total, and average latency.

        Thread-safety: Delegates to _StatisticsCollector.metrics().
        Complexity: O(k) for k unique strategies.
        """
        m = self._stats.metrics()
        return AggregationSnapshot(
            status="healthy",
            total_aggregations=m.aggregation_count,
            active_count=0,
            avg_latency_ms=m.consensus_latency_ms,
            strategy="",
        )

    async def aggregate(
        self,
        request: AggregationRequest,
    ) -> AggregationResult:
        """Execute full aggregation pipeline for a single request.

        Pipeline:
          1. Publish AGGREGATION_STARTED event
          2. Execute _aggregate_impl (the main pipeline)
          3. Record statistics and audit trail
          4. Publish completion/consensus events
          5. Return AggregationResult

        Args:
            request: Aggregation request containing execution results.

        Returns:
            AggregationResult with synthesised content, confidence,
            consensus results, conflicts, candidates, and metadata.
            On failure, returns a result with error metadata.

        Raises:
            No exceptions — all errors are captured into AggregationResult.

        Thread-safety:
        - Acquires self._lock for stats and audit recording.
        - _aggregate_impl is entirely local (no shared state).

        Complexity:
        - O(n² * t) worst case (n responses, t avg tokens).
        - n is typically 2--5 in practice.
        """
        start_time = time.time()
        await self._publish(
            Topic.AGGREGATION_STARTED,
            {
                "request_id": request.request_id,
                "strategy": request.strategy.value,
                "result_count": len(request.results),
            },
        )

        try:
            result = await self._aggregate_impl(request)
            duration_ms = (time.time() - start_time) * 1000.0

            candidate = result.candidates[0] if result.candidates else None
            selected = candidate.provider if candidate else ""

            async with self._lock:
                sim = 0.0
                if len(request.results) > 1:
                    normalised = [_ContentNormalizer.normalize(r) for r in request.results]
                    sim_matrix = _SimilarityComputer.build_similarity_matrix(normalised)
                    sim = sim_matrix.avg_similarity

                self._stats.record_aggregation(
                    strategy=result.strategy,
                    consensus_reached=result.consensus is not None and result.consensus.reached,
                    conflict_count=result.conflicts.total_conflicts if result.conflicts else 0,
                    selected_provider=selected,
                    avg_similarity=sim,
                    avg_confidence=result.confidence.overall,
                    avg_quality=result.confidence.overall,
                    latency_ms=duration_ms,
                )

                self._audit.record(
                    request_id=request.request_id,
                    strategy=result.strategy,
                    provider_count=len(request.results),
                    conflict_count=result.conflicts.total_conflicts if result.conflicts else 0,
                    selected_provider=selected,
                    consensus_reached=result.consensus is not None and result.consensus.reached,
                    duration_ms=duration_ms,
                )

            await self._publish(
                Topic.AGGREGATION_COMPLETED,
                {
                    "request_id": request.request_id,
                    "strategy": result.strategy.value,
                    "selected_provider": selected,
                    "duration_ms": duration_ms,
                    "consensus_reached": result.consensus.reached if result.consensus else False,
                    "conflict_count": result.conflicts.total_conflicts if result.conflicts else 0,
                },
            )

            if result.consensus and result.consensus.reached:
                await self._publish(
                    Topic.CONSENSUS_REACHED,
                    {
                        "request_id": request.request_id,
                        "mode": result.consensus.mode.value,
                        "confidence": result.consensus.confidence,
                    },
                )
            else:
                await self._publish(
                    Topic.CONSENSUS_FAILED,
                    {
                        "request_id": request.request_id,
                    },
                )

            return result

        except Exception as exc:
            duration_ms = (time.time() - start_time) * 1000.0
            log.error("aggregation failed for %s: %s", request.request_id, exc)

            async with self._lock:
                self._audit.record(
                    request_id=request.request_id,
                    strategy=request.strategy,
                    provider_count=len(request.results),
                    conflict_count=0,
                    selected_provider="",
                    consensus_reached=False,
                    duration_ms=duration_ms,
                    error=str(exc),
                )

            await self._publish(
                Topic.AGGREGATION_FAILED,
                {
                    "request_id": request.request_id,
                    "error": str(exc),
                },
            )

            return AggregationResult(
                request_id=request.request_id,
                content="",
                strategy=request.strategy,
                confidence=AggregationConfidence(overall=0.0, uncertainty=1.0, risk_score=1.0),
                candidates=(),
                metadata={"error": str(exc)},
            )

    async def _aggregate_impl(
        self,
        request: AggregationRequest,
    ) -> AggregationResult:
        """Core aggregation pipeline (internal).

        Steps:
          1. Extract and validate results
          2. Normalize all results
          3. Score quality
          4. Compute similarity matrix
          5. Build candidates and rank
          6. Cast votes
          7. Determine strategy (resolve AUTO)
          8. Run consensus if applicable
          9. Detect and resolve conflicts
          10. Select content per strategy
          11. Estimate confidence
          12. Build and return AggregationResult

        Args:
            request: Aggregation request.

        Returns:
            AggregationResult with full pipeline output.
        """
        results = list(request.results) if request.results else []
        if not results:
            return AggregationResult(
                request_id=request.request_id,
                content="",
                strategy=request.strategy,
                confidence=AggregationConfidence(overall=0.5),
                candidates=(),
            )

        valid = [
            r
            for r in results
            if r.state
            in (
                ExecutionState.COMPLETED,
                ExecutionState.PARTIAL_SUCCESS,
            )
        ]
        if not valid:
            valid = [results[0]]

        # 1. Normalize
        normalised = [_ContentNormalizer.normalize(r) for r in valid]

        # 2. Score quality
        scored = _QualityScorer.score(normalised)

        # 3. Compute similarity (only for multi-provider)
        if len(scored) > 1:
            sim_matrix = _SimilarityComputer.build_similarity_matrix(scored)
        else:
            sim_matrix = SimilarityMatrix(
                providers=(scored[0].provider,),
                matrix=((1.0,),),
                min_similarity=1.0,
                max_similarity=1.0,
                avg_similarity=1.0,
            )

        # 4. Build candidates & rank
        candidates = _ResponseRanker.compute_candidates(scored)

        # 5. Cast votes for consensus
        votes = _VotingEngine.cast_votes(scored)

        # 6. Determine strategy
        strategy = request.strategy
        if strategy == AggregationStrategy.AUTO:
            if len(candidates) >= 3:
                strategy = AggregationStrategy.CONSENSUS
            elif len(candidates) >= 2:
                strategy = _pick_auto_strategy(candidates)
            else:
                strategy = AggregationStrategy.FIRST_SUCCESS
        await self._publish_events(strategy, votes, scored, candidates)

        # 7. Run consensus
        consensus_reached: ConsensusResult | None = None
        if strategy in (
            AggregationStrategy.CONSENSUS,
            AggregationStrategy.MAJORITY_VOTE,
            AggregationStrategy.WEIGHTED_VOTE,
            AggregationStrategy.WEIGHTED_SCORE,
            AggregationStrategy.SUPER_MAJORITY,
            AggregationStrategy.UNANIMOUS,
            AggregationStrategy.QUORUM,
        ):
            mode = _resolve_consensus_mode(strategy, self._policy.consensus_mode)
            consensus_reached = _VotingEngine.run_consensus(votes, mode)

        # 8. Detect and resolve conflicts
        conflict_resolution = _ConflictResolver.detect(scored)
        if conflict_resolution.total_conflicts > 0:
            conflict_resolution = _ConflictResolver.resolve(
                conflict_resolution, self._policy.conflict_policy
            )
            await self._publish(
                Topic.CONFLICT_DETECTED,
                {
                    "request_id": request.request_id,
                    "count": conflict_resolution.total_conflicts,
                },
            )
            await self._publish(
                Topic.CONFLICT_RESOLVED,
                {
                    "request_id": request.request_id,
                    "resolved": conflict_resolution.resolved_count,
                },
            )

        # 9. Select content based on strategy
        content = _select_content(strategy, candidates, scored, request)

        # 10. Estimate confidence
        confidence = _ConfidenceEstimator.estimate(scored, consensus_reached)

        # 12. Build final result
        return AggregationResult(
            request_id=request.request_id,
            content=content,
            strategy=strategy,
            confidence=confidence,
            consensus=consensus_reached,
            conflicts=conflict_resolution,
            selected_provider=candidates[0].provider if candidates else "",
            candidates=tuple(candidates),
            metadata={
                "provider_count": len(scored),
                "sim_matrix": {
                    "avg_similarity": sim_matrix.avg_similarity,
                    "min_similarity": sim_matrix.min_similarity,
                    "max_similarity": sim_matrix.max_similarity,
                },
            },
        )

    async def _publish(self, topic: Topic, payload: dict[str, Any]) -> None:
        """Publish an event to the EventBus.

        Args:
            topic: EventBus Topic enum value.
            payload: Dictionary payload for the event.

        Notes:
            Failures are logged as warnings — never raised.
            No-op if event_bus is None.

        Complexity: O(1) — single async publish call.
        """
        if not self._event_bus:
            return
        try:
            await self._event_bus.publish(
                topic=topic.value,
                payload=payload,
                source="aggregation_engine",
            )
        except Exception:
            log.warning("failed to publish %s", topic, exc_info=True)

    async def _publish_events(
        self,
        strategy: AggregationStrategy,
        votes: list[WeightedVote],
        scored: list[NormalizedResponse],
        candidates: list[AggregationCandidate],
    ) -> None:
        """Publish pipeline events for observability.

        Always publishes: VOTE_CAST, WEIGHTED_VOTE, QUALITY_SCORE_UPDATED,
        CONFIDENCE_UPDATED.
        Conditionally publishes: RESPONSE_SELECTED (if candidates exist),
        MERGE_COMPLETED (for merge/ensemble strategies),
        ENSEMBLE_COMPLETED (for ensemble strategy).

        Args:
            strategy: The resolved strategy.
            votes: Cast votes.
            scored: Quality-scored responses.
            candidates: Ranked candidates.

        Complexity: O(n) — iterates candidates once.
        """
        await self._publish(
            Topic.VOTE_CAST,
            {
                "vote_count": len(votes),
            },
        )
        await self._publish(
            Topic.WEIGHTED_VOTE,
            {
                "top_vote": max(
                    (v for v in votes),
                    key=lambda v: v.weight,
                    default=None,
                ),
            },
        )
        if candidates:
            await self._publish(
                Topic.RESPONSE_SELECTED,
                {
                    "selected": candidates[0].provider,
                    "score": candidates[0].final_score,
                },
            )
        await self._publish(
            Topic.QUALITY_SCORE_UPDATED,
            {
                "avg_quality": sum(s.quality for s in scored) / len(scored) if scored else 0.0,
            },
        )
        await self._publish(
            Topic.CONFIDENCE_UPDATED,
            {
                "avg_confidence": sum(s.confidence for s in scored) / len(scored)
                if scored
                else 0.0,
            },
        )

        if strategy in (
            AggregationStrategy.MERGE,
            AggregationStrategy.ENSEMBLE,
        ):
            await self._publish(
                Topic.MERGE_COMPLETED,
                {
                    "strategy": strategy.value,
                    "candidate_count": len(candidates),
                },
            )
        if strategy == AggregationStrategy.ENSEMBLE:
            await self._publish(
                Topic.ENSEMBLE_COMPLETED,
                {
                    "candidate_count": len(candidates),
                },
            )


# ── Module-level helper functions ──


def _pick_auto_strategy(
    candidates: list[AggregationCandidate],
) -> AggregationStrategy:
    """Pick the best strategy automatically based on candidate scores.

    Heuristic:
    - confidence > 0.8 → BEST_CONFIDENCE
    - quality > 0.8 → BEST_QUALITY
    - latency > 0.8 → FASTEST
    - default → WEIGHTED_SCORE

    Args:
        candidates: Ranked candidates (highest score first).

    Returns:
        The most appropriate AggregationStrategy.

    Complexity: O(1) — checks first candidate only.
    """
    if not candidates:
        return AggregationStrategy.FIRST_SUCCESS
    top = candidates[0]
    if top.confidence_score > 0.8:
        return AggregationStrategy.BEST_CONFIDENCE
    if top.quality_score > 0.8:
        return AggregationStrategy.BEST_QUALITY
    if top.latency_score > 0.8:
        return AggregationStrategy.FASTEST
    return AggregationStrategy.WEIGHTED_SCORE


def _resolve_consensus_mode(
    strategy: AggregationStrategy,
    default: ConsensusMode,
) -> ConsensusMode:
    """Map an AggregationStrategy to the appropriate ConsensusMode.

    Args:
        strategy: The aggregation strategy.
        default: Fallback mode if no mapping exists.

    Returns:
        Corresponding ConsensusMode for the strategy.

    Complexity: O(1) — dict lookup.
    """
    mapping: dict[AggregationStrategy, ConsensusMode] = {
        AggregationStrategy.CONSENSUS: ConsensusMode.SIMPLE_MAJORITY,
        AggregationStrategy.MAJORITY_VOTE: ConsensusMode.SIMPLE_MAJORITY,
        AggregationStrategy.WEIGHTED_VOTE: ConsensusMode.WEIGHTED_VOTING,
        AggregationStrategy.WEIGHTED_SCORE: ConsensusMode.CONFIDENCE_WEIGHTED,
        AggregationStrategy.SUPER_MAJORITY: ConsensusMode.SUPER_MAJORITY,
        AggregationStrategy.UNANIMOUS: ConsensusMode.UNANIMOUS,
        AggregationStrategy.QUORUM: ConsensusMode.QUORUM,
    }
    return mapping.get(strategy, default)


def _select_content(
    strategy: AggregationStrategy,
    candidates: list[AggregationCandidate],
    scored: list[NormalizedResponse],
    request: AggregationRequest,
) -> str:
    """Select or synthesise content based on the aggregation strategy.

    Dispatches to the appropriate content selection for 21 strategies:
    - Direct selection: FIRST_SUCCESS, BEST_QUALITY, BEST_CONFIDENCE, etc.
    - Consensus-based: CONSENSUS, MAJORITY_VOTE, SUPER_MAJORITY, etc.
    - Merge: MERGE, ENSEMBLE, STACKING
    - Pipeline: concatenates all candidates

    Args:
        strategy: The resolved strategy.
        candidates: Ranked candidates.
        scored: Quality-scored normalised responses.
        request: Original aggregation request (for FIRST_COMPLETED).

    Returns:
        Selected or synthesised content string.

    Complexity: O(n) for merge/ensemble/stacking, O(1) for direct selection.
    """
    if not candidates:
        return ""

    if strategy == AggregationStrategy.FIRST_SUCCESS:
        return candidates[0].content if candidates else ""

    if strategy == AggregationStrategy.FIRST_COMPLETED:
        for r in request.results:
            if r.state == ExecutionState.COMPLETED and (r.content or r.output):
                return r.content or r.output
        return ""

    if strategy == AggregationStrategy.FASTEST:
        return min(candidates, key=lambda c: c.metadata.get("latency_ms", 0.0)).content

    if strategy == AggregationStrategy.LOWEST_COST:
        return min(candidates, key=lambda c: c.metadata.get("cost", 0.0)).content

    if strategy == AggregationStrategy.BEST_QUALITY:
        return max(candidates, key=lambda c: c.quality_score).content

    if strategy == AggregationStrategy.BEST_CONFIDENCE:
        return max(candidates, key=lambda c: c.confidence_score).content

    if strategy == AggregationStrategy.WEIGHTED_SCORE:
        return candidates[0].content if candidates else ""

    if strategy in (
        AggregationStrategy.CONSENSUS,
        AggregationStrategy.MAJORITY_VOTE,
        AggregationStrategy.SUPER_MAJORITY,
    ):
        # Return the top-ranked content
        return candidates[0].content if candidates else ""

    if strategy in (AggregationStrategy.WEIGHTED_VOTE,):
        return candidates[0].content if candidates else ""

    if strategy in (
        AggregationStrategy.MERGE,
        AggregationStrategy.ENSEMBLE,
        AggregationStrategy.STACKING,
    ):
        merged = _ResponseMerger.merge_text(scored, strategy)
        return merged.content

    if strategy == AggregationStrategy.UNANIMOUS:
        if scored:
            return scored[0].content
        return ""

    if strategy == AggregationStrategy.QUORUM:
        return candidates[0].content if candidates else ""

    if strategy in (
        AggregationStrategy.AVERAGE,
        AggregationStrategy.MEDIAN,
    ):
        return candidates[0].content if candidates else ""

    if strategy == AggregationStrategy.PIPELINE:
        return "\n\n".join(c.content for c in candidates)

    if strategy == AggregationStrategy.CUSTOM:
        return candidates[0].content if candidates else ""

    return candidates[0].content if candidates else ""
