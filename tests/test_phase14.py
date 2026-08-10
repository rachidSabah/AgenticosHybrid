"""Tests for Phase 14 — Autonomous Swarm Execution & Collaborative Agent Fabric."""

from __future__ import annotations

import pytest

from agentic_os.adapters.bus.local import LocalBus
from agentic_os.core.orchestration.swarm_coordinator import (
    ConsensusManager,
    ConsensusResult,
    ConsensusType,
    DynamicRoleAssigner,
    SharedMissionMemory,
    SwarmCoordinator,
    SwarmPhase,
    SwarmRole,
)

# ── Fixtures ───────────────────────────────────────────────────────────


@pytest.fixture
async def bus():
    b = LocalBus()
    await b.start()
    yield b
    await b.stop()


@pytest.fixture
async def coordinator(bus):
    c = SwarmCoordinator(bus=bus)
    await c.start()
    yield c
    await c.stop()


# ── Domain Types ──────────────────────────────────────────────────────


class TestPhase14Domain:
    def test_consensus_types(self):
        types = {t.value for t in ConsensusType}
        required = {"majority", "weighted", "confidence", "leader_override"}
        assert required.issubset(types)

    def test_swarm_roles(self):
        roles = {r.value for r in SwarmRole}
        required = {
            "leader",
            "planner",
            "researcher",
            "coder",
            "reviewer",
            "validator",
            "executor",
            "observer",
        }
        assert required.issubset(roles)

    def test_swarm_phases(self):
        phases = {p.value for p in SwarmPhase}
        required = {"created", "forming", "active", "executing", "completed", "failed", "disbanded"}
        assert required.issubset(phases)

    def test_consensus_result(self):
        cr = ConsensusResult(
            swarm_id="s1",
            consensus_type=ConsensusType.MAJORITY,
            proposal="approve plan",
            votes={"m1": "yes", "m2": "no"},
            result="approved",
            confidence=0.5,
        )
        d = cr.to_dict()
        assert d["swarm_id"] == "s1"
        assert d["result"] == "approved"
        assert d["confidence"] == 0.5


# ── SharedMissionMemory ────────────────────────────────────────────────


class TestSharedMissionMemory:
    @pytest.mark.asyncio
    async def test_context(self):
        mem = SharedMissionMemory(mission_id="m1")
        await mem.set_context("goal", "test")
        assert await mem.get_context("goal") == "test"
        assert await mem.get_context("missing", "default") == "default"

    @pytest.mark.asyncio
    async def test_working_memory(self):
        mem = SharedMissionMemory(mission_id="m1")
        await mem.set_working("task1", {"status": "running"})
        result = await mem.get_working("task1")
        assert result["status"] == "running"

    @pytest.mark.asyncio
    async def test_decision_memory(self):
        mem = SharedMissionMemory(mission_id="m1")
        await mem.record_decision({"type": "routing", "brain": "python"})
        decisions = await mem.get_decisions()
        assert len(decisions) == 1
        assert decisions[0]["brain"] == "python"

    def test_to_dict(self):
        mem = SharedMissionMemory(mission_id="m1")
        d = mem.to_dict()
        assert d["mission_id"] == "m1"
        assert "context_keys" in d
        assert "decision_count" in d


# ── ConsensusManager ──────────────────────────────────────────────────


class TestConsensusManager:
    @pytest.mark.asyncio
    async def test_majority_approved(self):
        cm = ConsensusManager()
        result = await cm.run_consensus(
            swarm_id="s1",
            proposal="approve",
            votes={"m1": "yes", "m2": "yes", "m3": "no"},
            consensus_type=ConsensusType.MAJORITY,
        )
        assert result.result == "approved"
        assert result.confidence > 0.5

    @pytest.mark.asyncio
    async def test_majority_rejected(self):
        cm = ConsensusManager()
        result = await cm.run_consensus(
            swarm_id="s1",
            proposal="approve",
            votes={"m1": "no", "m2": "no", "m3": "yes"},
            consensus_type=ConsensusType.MAJORITY,
        )
        assert result.result == "rejected"

    @pytest.mark.asyncio
    async def test_weighted(self):
        cm = ConsensusManager()
        result = await cm.run_consensus(
            swarm_id="s1",
            proposal="approve",
            votes={"m1": "yes", "m2": "no"},
            consensus_type=ConsensusType.WEIGHTED,
            member_weights={"m1": 0.8, "m2": 0.2},
        )
        assert result.result == "approved"

    @pytest.mark.asyncio
    async def test_confidence(self):
        cm = ConsensusManager()
        result = await cm.run_consensus(
            swarm_id="s1",
            proposal="approve",
            votes={"m1": "yes", "m2": "no"},
            consensus_type=ConsensusType.CONFIDENCE,
            member_confidence={"m1": 0.9, "m2": 0.3},
        )
        assert result.result == "approved"

    @pytest.mark.asyncio
    async def test_leader_override(self):
        cm = ConsensusManager()
        result = await cm.run_consensus(
            swarm_id="s1",
            proposal="approve",
            votes={"m1": "yes", "m2": "no"},
            consensus_type=ConsensusType.LEADER_OVERRIDE,
        )
        assert result.result == "approved"

    def test_history(self):
        cm = ConsensusManager()
        assert isinstance(cm.get_history(), list)


# ── DynamicRoleAssigner ──────────────────────────────────────────────


class TestDynamicRoleAssigner:
    def test_assign_with_leader(self):
        ra = DynamicRoleAssigner()
        members = [
            {"id": "m1", "capabilities": ["coding", "reasoning"]},
            {"id": "m2", "capabilities": ["testing"]},
            {"id": "m3", "capabilities": ["research"]},
        ]
        roles = ra.assign_roles(members, existing_leader="m1")
        assert roles["m1"] == SwarmRole.LEADER
        assert roles["m2"] == SwarmRole.VALIDATOR
        assert roles["m3"] == SwarmRole.RESEARCHER

    def test_assign_first_as_leader(self):
        ra = DynamicRoleAssigner()
        members = [{"id": "m1", "capabilities": ["coding"]}]
        roles = ra.assign_roles(members)
        assert roles["m1"] == SwarmRole.LEADER

    def test_default_role(self):
        ra = DynamicRoleAssigner()
        members = [{"id": "m1", "capabilities": ["unknown_cap"]}]
        roles = ra.assign_roles(members)
        assert roles["m1"] == SwarmRole.LEADER  # first member becomes leader


# ── SwarmCoordinator ──────────────────────────────────────────────────


class TestSwarmCoordinator:
    @pytest.mark.asyncio
    async def test_start_stop(self, bus):
        c = SwarmCoordinator(bus=bus)
        await c.start()
        assert c._started is True
        await c.stop()
        assert c._started is False

    @pytest.mark.asyncio
    async def test_create_team_no_registry(self, coordinator):
        result = await coordinator.create_team(
            goal="Test Mission",
            required_capabilities=["coding"],
        )
        assert "swarm_id" in result
        assert result["goal"] == "Test Mission"
        assert result["phase"] == "created"
        assert "members" in result
        assert "roles" in result

    @pytest.mark.asyncio
    async def test_execute_swarm(self, coordinator):
        team = await coordinator.create_team(goal="Test", required_capabilities=["chat"])
        swarm_id = team["swarm_id"]
        result = await coordinator.execute_swarm(
            swarm_id,
            [{"id": "t1", "title": "Task 1"}, {"id": "t2", "title": "Task 2"}],
        )
        assert result["phase"] == "completed"
        assert "assignments" in result
        assert "merged_result" in result

    @pytest.mark.asyncio
    async def test_execute_swarm_no_orchestrator_is_honest(self, coordinator):
        """Without an orchestrator, assignments must never be fabricated."""
        team = await coordinator.create_team(goal="Test", required_capabilities=["chat"])
        swarm_id = team["swarm_id"]
        result = await coordinator.execute_swarm(
            swarm_id,
            [{"id": "t1", "title": "Task 1"}],
        )
        assignments = result["assignments"]
        assert len(assignments) == 1
        a = assignments[0]
        # Honest contract: NOT "completed" with a canned output line.
        assert a["status"] == "unexecuted"
        assert "no orchestrator" in (a.get("error") or "").lower()
        assert "output" not in a
        assert result["merged_result"]["completed"] == 0

    @pytest.mark.asyncio
    async def test_execute_swarm_real_dispatch(self, bus):
        """A wired orchestrator is actually invoked per assignment."""
        from agentic_os.domain.agent import TaskStatus

        class _FakeOrchestrator:
            def __init__(self) -> None:
                self.dispatched: list[str] = []

            async def dispatch_task(self, task) -> None:  # noqa: ANN001
                self.dispatched.append(task.title)
                task.status = TaskStatus.COMPLETED
                task.result = f"real result for {task.title}"

        fake = _FakeOrchestrator()
        c = SwarmCoordinator(bus=bus, orchestrator=fake)  # type: ignore[arg-type]
        await c.start()
        try:
            team = await c.create_team(goal="Test", required_capabilities=["chat"])
            swarm_id = team["swarm_id"]
            result = await c.execute_swarm(
                swarm_id,
                [{"id": "t1", "title": "Task A"}, {"id": "t2", "title": "Task B"}],
            )
            assert fake.dispatched == ["Task A", "Task B"]
            assert all(a["status"] == "completed" for a in result["assignments"])
            assert result["assignments"][0]["output"] == "real result for Task A"
            assert result["merged_result"]["completed"] == 2
            assert result["merged_result"]["failed"] == 0
        finally:
            await c.stop()

    @pytest.mark.asyncio
    async def test_execute_swarm_real_failure_reported(self, bus):
        """A failing orchestrator task surfaces as failed, not completed."""
        from agentic_os.domain.agent import TaskStatus

        class _FailingOrchestrator:
            async def dispatch_task(self, task) -> None:  # noqa: ANN001
                task.status = TaskStatus.FAILED
                task.error = "provider auth failed"

        fake = _FailingOrchestrator()
        c = SwarmCoordinator(bus=bus, orchestrator=fake)  # type: ignore[arg-type]
        await c.start()
        try:
            team = await c.create_team(goal="Test", required_capabilities=["chat"])
            swarm_id = team["swarm_id"]
            result = await c.execute_swarm(
                swarm_id,
                [{"id": "t1", "title": "Task A"}],
            )
            assert result["assignments"][0]["status"] == "failed"
            assert result["assignments"][0]["error"] == "provider auth failed"
            assert result["phase"] == "failed"
            assert result["merged_result"]["failed"] == 1
        finally:
            await c.stop()

    @pytest.mark.asyncio
    async def test_execute_swarm_pending_reported_honestly(self, bus):
        """A task left PENDING after dispatch means no provider matched."""
        from agentic_os.domain.agent import TaskStatus

        class _NoopOrchestrator:
            async def dispatch_task(self, task) -> None:  # noqa: ANN001
                # Leaves task.status PENDING → no executable provider
                pass

        fake = _NoopOrchestrator()
        c = SwarmCoordinator(bus=bus, orchestrator=fake)  # type: ignore[arg-type]
        await c.start()
        try:
            team = await c.create_team(goal="Test", required_capabilities=["chat"])
            swarm_id = team["swarm_id"]
            result = await c.execute_swarm(
                swarm_id,
                [{"id": "t1", "title": "Task A"}],
            )
            a = result["assignments"][0]
            assert a["status"] == "pending"
            assert "no executable provider" in (a.get("error") or "").lower()
            assert result["merged_result"]["completed"] == 0
        finally:
            await c.stop()

    @pytest.mark.asyncio
    async def test_execute_not_found(self, coordinator):
        result = await coordinator.execute_swarm("nonexistent")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_rebalance(self, coordinator):
        team = await coordinator.create_team(goal="Test")
        result = await coordinator.rebalance(team["swarm_id"])
        assert "swarm_id" in result

    @pytest.mark.asyncio
    async def test_disband(self, coordinator):
        team = await coordinator.create_team(goal="Test")
        result = await coordinator.disband(team["swarm_id"])
        assert result["status"] == "disbanded"

    @pytest.mark.asyncio
    async def test_consensus(self, coordinator):
        team = await coordinator.create_team(goal="Test")
        result = await coordinator.run_consensus(
            swarm_id=team["swarm_id"],
            proposal="approve plan",
            votes={"m1": "yes", "m2": "yes"},
            consensus_type=ConsensusType.MAJORITY,
        )
        assert result["result"] == "approved"

    @pytest.mark.asyncio
    async def test_get_swarm_status(self, coordinator):
        team = await coordinator.create_team(goal="Test")
        status = coordinator.get_swarm_status(team["swarm_id"])
        assert status["swarm_id"] == team["swarm_id"]
        assert "phase" in status
        assert "member_count" in status

    @pytest.mark.asyncio
    async def test_list_swarms(self, coordinator):
        await coordinator.create_team(goal="Test 1")
        await coordinator.create_team(goal="Test 2")
        swarms = coordinator.list_swarms()
        assert len(swarms) >= 2

    @pytest.mark.asyncio
    async def test_get_members(self, coordinator):
        team = await coordinator.create_team(goal="Test")
        members = coordinator.get_swarm_members(team["swarm_id"])
        assert isinstance(members, list)

    @pytest.mark.asyncio
    async def test_history(self, coordinator):
        await coordinator.create_team(goal="Test")
        history = coordinator.get_history()
        assert len(history) >= 1

    @pytest.mark.asyncio
    async def test_brain_removed_handling(self, bus, coordinator):
        from agentic_os.domain.events import EventEnvelope

        await bus.publish(
            EventEnvelope(
                type="brain.removed",
                source="test",
                topic="brain.removed",
                payload={"id": "test-brain-id", "display_name": "Test Brain"},
            )
        )
        import asyncio

        await asyncio.sleep(0.1)
        # Should not crash — no swarm has this member
        assert coordinator._started is True
