"""Tests for Phase 13 — Autonomous Executive Decision & Mission Orchestration."""

from __future__ import annotations

import pytest

from agentic_os.adapters.bus.local import LocalBus
from agentic_os.core.executive.orchestrator import ExecutiveOrchestrator
from agentic_os.core.executive.phase13_domain import (
    ExecutiveDecision,
    ExecutivePolicy,
    ExecutivePolicyType,
    ExecutiveWorldState,
    MissionSupervisionRecord,
    ResourceAllocation,
)

# ── Fixtures ───────────────────────────────────────────────────────────


@pytest.fixture
async def bus():
    b = LocalBus()
    await b.start()
    yield b
    await b.stop()


@pytest.fixture
async def orchestrator(bus):
    o = ExecutiveOrchestrator(bus=bus)
    await o.start()
    yield o
    await o.stop()


# ── Domain Types ──────────────────────────────────────────────────────


class TestPhase13Domain:
    def test_executive_policy_creation(self):
        p = ExecutivePolicy(ExecutivePolicyType.THROUGHPUT)
        d = p.to_dict()
        assert d["type"] == "throughput"
        assert "params" in d
        assert "updated_at" in d

    def test_executive_policy_types(self):
        types = {t.value for t in ExecutivePolicyType}
        required = {"throughput", "quality", "latency", "cost", "resilience", "balanced", "custom"}
        assert required.issubset(types)

    def test_executive_decision_creation(self):
        d = ExecutiveDecision(
            decision_type="allocation",
            reason="Allocated brain to mission",
            confidence=0.85,
            predicted_impact="Faster execution",
        )
        dd = d.to_dict()
        assert dd["decision_type"] == "allocation"
        assert dd["confidence"] == 0.85
        assert "evidence" in dd
        assert "actual_outcome" in dd
        assert dd["actual_outcome"] == ""

    def test_resource_allocation_creation(self):
        a = ResourceAllocation(
            mission_id="m1",
            brain_ids=["b1", "b2"],
            provider_ids=["p1"],
            memory_mb=512,
            priority="high",
        )
        d = a.to_dict()
        assert d["mission_id"] == "m1"
        assert d["brain_ids"] == ["b1", "b2"]
        assert d["memory_mb"] == 512
        assert d["released_at"] == ""

    def test_mission_supervision_record(self):
        r = MissionSupervisionRecord(
            mission_id="m1",
            is_stalled=True,
            issues=["No tasks dispatched"],
        )
        d = r.to_dict()
        assert d["is_stalled"] is True
        assert "No tasks dispatched" in d["issues"]

    def test_executive_world_state(self):
        ws = ExecutiveWorldState()
        d = ws.to_dict()
        assert "runtimes" in d
        assert "active_brains" in d
        assert "missions" in d
        assert "execution_queue_size" in d
        assert "resource_utilization" in d
        assert "last_updated" in d


# ── Orchestrator ──────────────────────────────────────────────────────


class TestOrchestrator:
    @pytest.mark.asyncio
    async def test_start_stop(self, bus):
        o = ExecutiveOrchestrator(bus=bus)
        await o.start()
        assert o._started is True
        assert len(o._subs) > 0
        await o.stop()
        assert o._started is False

    @pytest.mark.asyncio
    async def test_compose_mission_no_registry(self, orchestrator):
        result = await orchestrator.compose_mission(
            goal_id="g1",
            title="Test Mission",
            required_capabilities=["coding"],
        )
        assert result["goal_id"] == "g1"
        assert result["complexity"] > 0
        assert "probability_of_success" in result
        assert "matching_runtimes" in result

    @pytest.mark.asyncio
    async def test_allocate_resources_no_registry(self, orchestrator):
        alloc = await orchestrator.allocate_resources(
            mission_id="m1",
            required_capabilities=["coding"],
        )
        assert alloc.mission_id == "m1"
        assert isinstance(alloc.brain_ids, list)

    @pytest.mark.asyncio
    async def test_release_resources(self, orchestrator):
        await orchestrator.allocate_resources(mission_id="m1")
        result = await orchestrator.release_resources("m1")
        assert result["mission_id"] == "m1"
        assert len(result["released"]) > 0

    @pytest.mark.asyncio
    async def test_supervise_missions(self, orchestrator):
        records = await orchestrator.supervise_missions()
        assert isinstance(records, list)

    @pytest.mark.asyncio
    async def test_reprioritize(self, orchestrator):
        result = await orchestrator.reprioritize()
        assert "reprioritized" in result

    @pytest.mark.asyncio
    async def test_set_policy(self, orchestrator):
        p = orchestrator.set_policy(ExecutivePolicyType.THROUGHPUT)
        assert p.type == ExecutivePolicyType.THROUGHPUT
        history = orchestrator.get_policy_history()
        assert len(history) > 0

    @pytest.mark.asyncio
    async def test_get_policy(self, orchestrator):
        p = orchestrator.get_policy()
        assert p.type == ExecutivePolicyType.BALANCED

    @pytest.mark.asyncio
    async def test_trigger_recovery(self, orchestrator):
        result = await orchestrator.trigger_recovery("m1", "stalled")
        assert result["mission_id"] == "m1"
        assert result["recovery"] == "initiated"

    @pytest.mark.asyncio
    async def test_optimize(self, orchestrator):
        result = await orchestrator.optimize()
        assert "reprioritized" in result
        assert "supervision" in result
        assert "policy" in result

    @pytest.mark.asyncio
    async def test_get_world_state(self, orchestrator):
        ws = await orchestrator.get_world_state()
        assert "runtimes" in ws
        assert "active_brains" in ws
        assert "last_updated" in ws

    @pytest.mark.asyncio
    async def test_dashboard(self, orchestrator):
        d = await orchestrator.dashboard()
        assert "status" in d
        assert "world" in d
        assert "policy" in d
        assert "decisions_count" in d
        assert "allocations_count" in d

    @pytest.mark.asyncio
    async def test_decisions_recorded(self, orchestrator):
        await orchestrator.compose_mission(
            goal_id="g1", title="Test", required_capabilities=["coding"]
        )
        decisions = orchestrator.get_decisions()
        assert len(decisions) > 0
        assert decisions[-1]["decision_type"] == "mission_composition"

    @pytest.mark.asyncio
    async def test_event_handling(self, bus, orchestrator):
        from agentic_os.domain.events import EventEnvelope

        await bus.publish(
            EventEnvelope(
                type="mission.started",
                source="test",
                topic="mission.started",
                payload={"id": "m1", "title": "Test Mission"},
            )
        )
        import asyncio

        await asyncio.sleep(0.1)
        ws = await orchestrator.get_world_state()
        assert "m1" in orchestrator._world.missions
