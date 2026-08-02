"""
Capability Negotiator

Handles capability advertising, matching, and negotiation between execution
engines and tasks that need specific capabilities.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime

from agentic_os.domain.execution import (
    EngineCapability,
    ExecutionCapability,
    ExecutionEngine,
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class CapabilityCacheEntry:
    """A cached capability declaration for an engine."""

    engine_id: str
    capabilities: tuple[ExecutionCapability, ...]
    registered_at: datetime = field(default_factory=_utcnow)
    ttl_seconds: float = 60.0

    def is_expired(self) -> bool:
        elapsed = (_utcnow() - self.registered_at).total_seconds()
        return elapsed > self.ttl_seconds

    def refresh(self) -> CapabilityCacheEntry:
        return CapabilityCacheEntry(
            engine_id=self.engine_id,
            capabilities=self.capabilities,
            registered_at=_utcnow(),
            ttl_seconds=self.ttl_seconds,
        )


@dataclass
class CapabilityNegotiator:
    """
    Matches execution requests to engines based on capability requirements.

    Scoring:
    - Required capabilities are weighted at 10x each
    - Optional capabilities add 1x each (within the same type)
    - Missing required capabilities result in zero score
    - Higher confidence capabilities score higher within same type
    """

    _cache: dict[str, CapabilityCacheEntry] = field(default_factory=dict)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _default_ttl: float = 60.0

    async def register_capabilities(
        self,
        engine_id: str,
        capabilities: list[ExecutionCapability],
        ttl_seconds: float | None = None,
    ) -> None:
        """Register or update capabilities for an engine."""
        async with self._lock:
            self._cache[engine_id] = CapabilityCacheEntry(
                engine_id=engine_id,
                capabilities=tuple(capabilities),
                ttl_seconds=ttl_seconds or self._default_ttl,
            )

    async def unregister_capabilities(self, engine_id: str) -> None:
        """Remove cached capability declarations for an engine."""
        async with self._lock:
            self._cache.pop(engine_id, None)

    async def get_capabilities(self, engine_id: str) -> list[ExecutionCapability] | None:
        """Get cached capabilities for an engine, or None if not cached."""
        async with self._lock:
            entry = self._cache.get(engine_id)
            if entry is None:
                return None
            if entry.is_expired():
                self._cache.pop(engine_id, None)
                return None
            return list(entry.capabilities)

    async def find_best_match(
        self,
        required: list[EngineCapability],
        engines: list[ExecutionEngine],
        min_confidence: float = 0.0,
    ) -> ExecutionEngine | None:
        """
        Find the best engine match for the required capabilities.

        Returns the highest-scoring engine, or None if no engine meets the
        minimum requirements. Only considers online engines.
        """
        if not required or not engines:
            return None

        best: tuple[float, ExecutionEngine | None] = (0.0, None)

        for engine in engines:
            if not engine.is_online():
                continue

            score = await self._score_engine(engine, required, min_confidence)
            if score > best[0]:
                best = (score, engine)

        return best[1]

    async def find_all_matches(
        self,
        required: list[EngineCapability],
        engines: list[ExecutionEngine],
        min_score: float = 0.0,
    ) -> list[tuple[ExecutionEngine, float]]:
        """Find all engines matching the capabilities, sorted by score descending."""
        scored: list[tuple[ExecutionEngine, float]] = []

        for engine in engines:
            if not engine.is_online():
                continue

            score = await self._score_engine(engine, required, 0.0)
            if score >= min_score:
                scored.append((engine, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    async def _score_engine(
        self,
        engine: ExecutionEngine,
        required: list[EngineCapability],
        min_confidence: float,
    ) -> float:
        """
        Score an engine against required capabilities.

        Each matching required capability adds 10.0 * confidence.
        The score is 0.0 if any required capability is missing.
        """
        score = 0.0

        for req in required:
            # Check engine's advertised capabilities
            matched = False
            for cap in engine.capabilities:
                if cap.type == req and cap.confidence >= min_confidence:
                    score += 10.0 * cap.confidence
                    matched = True
                    break

            if not matched:
                return 0.0

        return score

    async def refresh_all(self) -> int:
        """
        Refresh all expired cache entries by removing them.
        Returns the number of expired entries removed.
        """
        async with self._lock:
            expired = [eid for eid, entry in self._cache.items() if entry.is_expired()]
            for eid in expired:
                self._cache.pop(eid, None)
            return len(expired)

    async def clear(self) -> None:
        """Clear all cached capability declarations."""
        async with self._lock:
            self._cache.clear()
