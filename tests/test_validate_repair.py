"""Validate All / Repair All must be honest (spec §15, §16).

No result may be generated; failure is reported as failure.
"""

from __future__ import annotations

import asyncio
import contextlib

import pytest

from agentic_os.core.brains.discovery_engine import AgentDiscoveryEngine
from agentic_os.core.brains.schema import (
    KIND_AI_AGENT_CLI,
    STATUS_HEALTHY,
    STATUS_UNAVAILABLE,
    DiscoveredAgent,
    DiscoverySnapshot,
)


class _FakeAdapter:
    platform_name = "fake"

    def __init__(self, results: dict[str, DiscoveredAgent]):
        self._results = results

    async def discover(self):
        return list(self._results)

    async def _enumerate_candidates(self):
        return list(self._results)

    async def resolve(self, name: str):
        return f"/fake/{name}" if name in self._results else None

    async def validate(self, candidate: str) -> DiscoveredAgent:
        return self._results.get(
            candidate,
            DiscoveredAgent(id=f"agent:{candidate}", name=candidate, status=STATUS_UNAVAILABLE),
        )


def _engine_with(results) -> AgentDiscoveryEngine:
    engine = AgentDiscoveryEngine()
    engine._adapter = _FakeAdapter(results)
    engine._snapshot = DiscoverySnapshot(
        platform="fake",
        agents=[
            DiscoveredAgent(
                id=f"agent:{name}",
                name=name,
                command=name,
                kind=KIND_AI_AGENT_CLI,
                status=STATUS_HEALTHY,
            )
            for name in results
        ],
    )
    return engine


@pytest.mark.asyncio
async def test_validate_all_reports_real_pass():
    agent = DiscoveredAgent(
        id="agent:ok", name="ok", command="ok",
        kind=KIND_AI_AGENT_CLI, status=STATUS_HEALTHY, version="1.0.0",
        health_score=100.0,
    )
    engine = _engine_with({"ok": agent})
    res = await engine.validate_all()
    assert res["agent:ok"]["passed"] is True
    assert res["agent:ok"]["status"] == STATUS_HEALTHY


@pytest.mark.asyncio
async def test_validate_all_reports_real_failure():
    """§15: a failing agent is reported failed, never silently passed."""
    agent = DiscoveredAgent(
        id="agent:bad", name="bad", command="bad",
        kind=KIND_AI_AGENT_CLI, status=STATUS_UNAVAILABLE,
        error="broken configuration",
    )
    engine = _engine_with({"bad": agent})
    res = await engine.validate_all()
    assert res["agent:bad"]["passed"] is False
    assert res["agent:bad"]["status"] == STATUS_UNAVAILABLE


@pytest.mark.asyncio
async def test_repair_all_never_reports_success_when_unfixable():
    """§16: unreparable => 'repair_unavailable', not 'repair successful'."""
    agent = DiscoveredAgent(
        id="agent:gone", name="gone", command="gone",
        kind=KIND_AI_AGENT_CLI, status=STATUS_UNAVAILABLE,
    )
    engine = _engine_with({})
    engine._snapshot = DiscoverySnapshot(platform="fake", agents=[agent])
    res = await engine.repair_all()
    assert res["agent:gone"]["repaired"] is False
    assert res["agent:gone"]["outcome"] == "repair_unavailable"


@pytest.mark.asyncio
async def test_repair_all_rebinds_when_executable_found():
    agent = DiscoveredAgent(
        id="agent:fix", name="fix", command="fix",
        kind=KIND_AI_AGENT_CLI, status=STATUS_UNAVAILABLE,
    )
    fixed = DiscoveredAgent(
        id="agent:fix", name="fix", command="fix",
        kind=KIND_AI_AGENT_CLI, status=STATUS_HEALTHY, version="2.0.0",
        health_score=100.0,
    )
    engine = _engine_with({"fix": fixed})
    engine._snapshot = DiscoverySnapshot(platform="fake", agents=[agent])
    res = await engine.repair_all()
    assert res["agent:fix"]["repaired"] is True
    assert res["agent:fix"]["outcome"] == "rebound"


@pytest.mark.asyncio
async def test_start_auto_rescan_is_idempotent():
    """§13: repeated starts must not spawn duplicate loops."""
    engine = _engine_with({})
    engine.start_auto_rescan(interval_seconds=3600)
    first = engine._rescan_task
    engine.start_auto_rescan(interval_seconds=3600)
    assert engine._rescan_task is first
    engine.stop_auto_rescan()
    assert first is not None
    # cancel() is cooperative: the task is 'cancelling' until the loop runs.
    with contextlib.suppress(asyncio.CancelledError):
        await first
    assert first.cancelled() or first.done()
