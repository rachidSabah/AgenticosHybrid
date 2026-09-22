"""Zero-agent state must be honest, never filled with placeholders (§6)."""

from __future__ import annotations

import pytest

from agentic_os.core.brains.discovery_engine import AgentDiscoveryEngine
from agentic_os.core.brains.schema import DiscoverySnapshot


class _EmptyAdapter:
    platform_name = "fake"

    async def discover(self):
        return []

    async def _enumerate_candidates(self):
        return []

    async def resolve(self, name: str):
        return None

    async def validate(self, candidate: str):
        from agentic_os.core.brains.schema import (
            STATUS_NOT_FOUND,
            DiscoveredAgent,
        )

        return DiscoveredAgent(id=f"agent:{candidate}", name=candidate, status=STATUS_NOT_FOUND)


@pytest.mark.asyncio
async def test_zero_agents_reports_zero_everywhere():
    """§6: no agents => zeros everywhere, never 16/17/29."""
    engine = AgentDiscoveryEngine()
    engine._adapter = _EmptyAdapter()  # type: ignore[assignment]
    snap = await engine.scan()

    assert len(snap.agents) == 0
    assert len(snap.active_agents()) == 0
    assert len(snap.runtimes()) == 0

    payload = snap.to_dict()
    assert payload["counts"] == {"discovered": 0, "active": 0, "runtimes": 0}
    assert payload["active_agents"] == []
    assert payload["runtimes"] == []


def test_empty_snapshot_has_no_placeholder_counts():
    snap = DiscoverySnapshot()
    assert snap.candidates_seen == 0
    assert snap.to_dict()["counts"]["active"] == 0
    # No decorative node counts. Check the payload's numeric fields only —
    # a substring scan of the whole dict also matches the ISO timestamp
    # (e.g. "13:39:16"), which made this test flaky.
    counts = snap.to_dict()["counts"]
    assert all(v == 0 for v in counts.values()), counts
    assert snap.to_dict()["agents"] == []
    assert snap.to_dict()["active_agents"] == []
    assert snap.to_dict()["runtimes"] == []
