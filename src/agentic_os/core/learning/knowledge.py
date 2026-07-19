"""Knowledge base — store and query learned patterns and experiences."""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from agentic_os.domain.learning import (
    ExperienceRecord,
    KnowledgePattern,
    LearningStatistics,
)
from agentic_os.ports.learning import KnowledgeBasePort


def _utcnow() -> datetime:
    return datetime.now(UTC)


class KnowledgeBase(KnowledgeBasePort):
    """In-memory knowledge base storing learned patterns and raw experiences.

    Follows the same pattern as other in-memory stores in the codebase
    (e.g. ``DiscoveryTelemetry``), keeping state in dicts keyed by IDs.
    """

    def __init__(self) -> None:
        self._patterns: dict[str, KnowledgePattern] = {}
        self._experiences: dict[str, ExperienceRecord] = {}
        self._created_at: datetime = _utcnow()

    # ── Patterns ──

    async def store_pattern(self, pattern: KnowledgePattern) -> KnowledgePattern:
        self._patterns[pattern.id] = pattern
        return pattern

    async def get_pattern(self, pattern_id: str) -> KnowledgePattern | None:
        return self._patterns.get(pattern_id)

    async def query_patterns(
        self,
        query: dict[str, Any],
        min_confidence: float = 0.0,
        limit: int = 20,
    ) -> Sequence[KnowledgePattern]:
        results: list[KnowledgePattern] = []
        for pattern in self._patterns.values():
            if pattern.confidence < min_confidence:
                continue
            if not self._matches_query(pattern, query):
                continue
            results.append(pattern)
            if len(results) >= limit:
                break
        return results

    # ── Experiences ──

    async def store_experience(self, experience: ExperienceRecord) -> ExperienceRecord:
        self._experiences[experience.id] = experience
        return experience

    async def query_experiences(
        self,
        query: dict[str, Any],
        limit: int = 50,
    ) -> Sequence[ExperienceRecord]:
        results: list[ExperienceRecord] = []
        for exp in self._experiences.values():
            if not self._matches_query(exp, query):
                continue
            results.append(exp)
            if len(results) >= limit:
                break
        return results

    # ── Statistics ──

    async def get_statistics(self) -> LearningStatistics:
        total_patterns = len(self._patterns)
        total_experiences = len(self._experiences)
        high_conf = sum(1 for p in self._patterns.values() if p.confidence >= 0.8)
        return LearningStatistics(
            total_experiences=total_experiences,
            total_patterns_detected=total_patterns,
            knowledge_base_size=total_patterns + total_experiences,
            learning_accuracy=(high_conf / total_patterns if total_patterns > 0 else 0.0),
        )

    async def prune(
        self,
        older_than_days: int = 90,
        min_confidence: float = 0.1,
    ) -> int:
        """Remove old or low-confidence patterns."""
        now = _utcnow()
        removed = 0
        to_delete: list[str] = []
        for pid, pattern in self._patterns.items():
            age_hours = (now - pattern.created_at).total_seconds() / 3600
            if age_hours > older_than_days * 24 or pattern.confidence < min_confidence:
                to_delete.append(pid)
        for pid in to_delete:
            del self._patterns[pid]
            removed += 1
        return removed

    # ── Internals ──

    @staticmethod
    def _matches_query(obj: Any, query: dict[str, Any]) -> bool:
        """Check if an object matches all non-None fields in the query dict."""
        for key, value in query.items():
            if value is not None and getattr(obj, key, None) != value:
                return False
        return True
