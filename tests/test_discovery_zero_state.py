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
    # No decorative node counts leak into the payload.
    assert "16" not in str(snap.to_dict())
    assert "17" not in str(snap.to_dict())
    assert "29" not in str(snap.to_dict())
