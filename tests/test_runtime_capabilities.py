"""Tests for capability negotiator."""

import pytest

from agentic_os.core.runtime.capabilities import CapabilityNegotiator
from agentic_os.domain.execution import (
    EngineCapability,
    EngineStatus,
    ExecutionCapability,
    ExecutionEngine,
)


class TestCapabilityNegotiator:
    @pytest.fixture
    def negotiator(self) -> CapabilityNegotiator:
        return CapabilityNegotiator()

    @pytest.fixture
    def coding_engine(self) -> ExecutionEngine:
        caps = (ExecutionCapability(type=EngineCapability.CODING, confidence=1.0),)
        return ExecutionEngine(name="coder", capabilities=caps, status=EngineStatus.RUNNING)

    @pytest.fixture
    def full_engine(self) -> ExecutionEngine:
        caps = (
            ExecutionCapability(type=EngineCapability.CODING, confidence=0.9),
            ExecutionCapability(type=EngineCapability.REASONING, confidence=0.8),
            ExecutionCapability(type=EngineCapability.PLANNING, confidence=0.7),
        )
        return ExecutionEngine(name="full", capabilities=caps, status=EngineStatus.RUNNING)

    @pytest.mark.asyncio
    async def test_register_capabilities(self, negotiator: CapabilityNegotiator) -> None:
        caps = [ExecutionCapability(type=EngineCapability.CODING)]
        await negotiator.register_capabilities("eng-1", caps)
        cached = await negotiator.get_capabilities("eng-1")
        assert cached is not None
        assert len(cached) == 1
        assert cached[0].type == EngineCapability.CODING

    @pytest.mark.asyncio
    async def test_unregister_capabilities(self, negotiator: CapabilityNegotiator) -> None:
        await negotiator.register_capabilities(
            "eng-1", [ExecutionCapability(type=EngineCapability.CODING)]
        )
        await negotiator.unregister_capabilities("eng-1")
        assert await negotiator.get_capabilities("eng-1") is None

    @pytest.mark.asyncio
    async def test_get_capabilities_nonexistent(self, negotiator: CapabilityNegotiator) -> None:
        assert await negotiator.get_capabilities("nonexistent") is None

    @pytest.mark.asyncio
    async def test_find_best_match_exact(
        self, negotiator: CapabilityNegotiator, coding_engine: ExecutionEngine
    ) -> None:
        best = await negotiator.find_best_match([EngineCapability.CODING], [coding_engine])
        assert best is not None
        assert best.name == "coder"

    @pytest.mark.asyncio
    async def test_find_best_match_returns_best_scoring(
        self,
        negotiator: CapabilityNegotiator,
        coding_engine: ExecutionEngine,
        full_engine: ExecutionEngine,
    ) -> None:
        # full_engine has coding (0.9) + reasoning, coding_engine has coding (1.0)
        # For just CODING, coding_engine scores 10*1.0=10, full_engine scores 10*0.9=9
        best = await negotiator.find_best_match(
            [EngineCapability.CODING], [coding_engine, full_engine]
        )
        assert best is not None
        assert best.name == "coder"

    @pytest.mark.asyncio
    async def test_find_best_match_multiple_required(
        self,
        negotiator: CapabilityNegotiator,
        coding_engine: ExecutionEngine,
        full_engine: ExecutionEngine,
    ) -> None:
        # Full engine has reasoning, coding_engine doesn't
        best = await negotiator.find_best_match(
            [EngineCapability.CODING, EngineCapability.REASONING],
            [coding_engine, full_engine],
        )
        assert best is not None
        assert best.name == "full"

    @pytest.mark.asyncio
    async def test_find_best_match_no_match(
        self, negotiator: CapabilityNegotiator, coding_engine: ExecutionEngine
    ) -> None:
        best = await negotiator.find_best_match([EngineCapability.DOCKER], [coding_engine])
        assert best is None

    @pytest.mark.asyncio
    async def test_find_best_match_offline_engine(self, negotiator: CapabilityNegotiator) -> None:
        offline = ExecutionEngine(
            name="offline",
            capabilities=(ExecutionCapability(type=EngineCapability.CODING),),
            status=EngineStatus.STOPPED,
        )
        best = await negotiator.find_best_match([EngineCapability.CODING], [offline])
        assert best is None

    @pytest.mark.asyncio
    async def test_find_best_match_empty_inputs(self, negotiator: CapabilityNegotiator) -> None:
        assert await negotiator.find_best_match([], []) is None
        assert await negotiator.find_best_match([EngineCapability.CODING], []) is None
        assert await negotiator.find_best_match([], [ExecutionEngine()]) is None

    @pytest.mark.asyncio
    async def test_find_all_matches(
        self,
        negotiator: CapabilityNegotiator,
        coding_engine: ExecutionEngine,
        full_engine: ExecutionEngine,
    ) -> None:
        matches = await negotiator.find_all_matches(
            [EngineCapability.CODING], [coding_engine, full_engine]
        )
        assert len(matches) == 2
        # Sorted by score descending: coder (10) > full (9)
        assert matches[0][0].name == "coder"

    @pytest.mark.asyncio
    async def test_find_all_matches_min_score_filter(
        self, negotiator: CapabilityNegotiator, coding_engine: ExecutionEngine
    ) -> None:
        matches = await negotiator.find_all_matches(
            [EngineCapability.CODING], [coding_engine], min_score=15.0
        )
        assert len(matches) == 0

    @pytest.mark.asyncio
    async def test_refresh_all(self, negotiator: CapabilityNegotiator) -> None:
        await negotiator.register_capabilities(
            "eng-1", [ExecutionCapability(type=EngineCapability.CODING)]
        )
        # No expired entries initially — TTL is 60s
        expired = await negotiator.refresh_all()
        assert expired == 0

    @pytest.mark.asyncio
    async def test_clear(self, negotiator: CapabilityNegotiator) -> None:
        await negotiator.register_capabilities(
            "eng-1", [ExecutionCapability(type=EngineCapability.CODING)]
        )
        await negotiator.clear()
        assert await negotiator.get_capabilities("eng-1") is None

    @pytest.mark.asyncio
    async def test_min_confidence_filter(self, negotiator: CapabilityNegotiator) -> None:
        low_conf = ExecutionEngine(
            name="low",
            capabilities=(ExecutionCapability(type=EngineCapability.CODING, confidence=0.3),),
            status=EngineStatus.RUNNING,
        )
        best = await negotiator.find_best_match(
            [EngineCapability.CODING], [low_conf], min_confidence=0.5
        )
        assert best is None

        best = await negotiator.find_best_match(
            [EngineCapability.CODING], [low_conf], min_confidence=0.0
        )
        assert best is not None

    def test_cache_entry_expiry(self) -> None:
        from agentic_os.core.runtime.capabilities import CapabilityCacheEntry

        entry = CapabilityCacheEntry(engine_id="e1", capabilities=(), ttl_seconds=-1.0)
        assert entry.is_expired()
        # Refresh preserves the TTL, so a negative-TTL entry stays expired
        refreshed = entry.refresh()
        assert refreshed.is_expired()

    @pytest.mark.asyncio
    async def test_register_with_custom_ttl(self, negotiator: CapabilityNegotiator) -> None:
        await negotiator.register_capabilities(
            "eng-1",
            [ExecutionCapability(type=EngineCapability.CODING)],
            ttl_seconds=999.0,
        )
        cached = await negotiator.get_capabilities("eng-1")
        assert cached is not None
