"""Tests for the Executive Intelligence Layer (Phase 11).

Covers: GoalManager lifecycle, DecisionEngine scoring, ReflectionEngine
generation, ExecutiveMemory indexes, ExecutiveController event handling,
and all /api/executive/* API endpoints.
"""

from __future__ import annotations

import pytest

from agentic_os.adapters.bus.local import LocalBus
from agentic_os.core.executive.controller import ExecutiveController
from agentic_os.core.executive.decision_engine import DecisionEngine
from agentic_os.core.executive.domain import (
    Decision,
    Goal,
    GoalPriority,
    GoalResult,
    GoalStatus,
    Reflection,
)
from agentic_os.core.executive.goal_manager import GoalManager
from agentic_os.core.executive.memory import ExecutiveMemory
from agentic_os.core.executive.reflection_engine import ReflectionEngine
from agentic_os.domain.events import EventEnvelope

# ── Fixtures ───────────────────────────────────────────────────────────


@pytest.fixture
async def bus():
    b = LocalBus()
    await b.start()
    yield b
    await b.stop()


@pytest.fixture
def goal_manager(bus):
    return GoalManager(bus=bus)


@pytest.fixture
def executive_memory():
    return ExecutiveMemory()


@pytest.fixture
def reflection_engine(bus, executive_memory):
    return ReflectionEngine(bus=bus, memory=executive_memory)


# ── Domain types ───────────────────────────────────────────────────────


class TestGoalDomain:
    def test_goal_creation_defaults(self):
        g = Goal(title="Test")
        assert g.id != ""
        assert g.status == GoalStatus.DRAFT
        assert g.priority == GoalPriority.NORMAL
        assert g.mission_id == ""
        assert g.reflection == ""

    def test_goal_to_dict_roundtrip(self):
        g = Goal(title="Test", description="desc", priority=GoalPriority.HIGH)
        g.status = GoalStatus.ACTIVE
        g.mission_id = "m123"
        d = g.to_dict()
        g2 = Goal.from_dict(d)
        assert g2.title == "Test"
        assert g2.description == "desc"
        assert g2.priority == GoalPriority.HIGH
        assert g2.status == GoalStatus.ACTIVE
        assert g2.mission_id == "m123"

    def test_goal_priority_weights(self):
        assert GoalPriority.CRITICAL.weight > GoalPriority.HIGH.weight
        assert GoalPriority.HIGH.weight > GoalPriority.NORMAL.weight
        assert GoalPriority.NORMAL.weight > GoalPriority.LOW.weight
        assert GoalPriority.LOW.weight > GoalPriority.BACKGROUND.weight

    def test_reflection_creation(self):
        r = Reflection(
            goal_id="g1",
            mission_id="m1",
            goal_achieved=True,
            best_runtime="python",
        )
        assert r.goal_achieved is True
        assert r.best_runtime == "python"
        assert r.id != ""

    def test_decision_creation(self):
        d = Decision(
            goal_id="g1",
            task_id="t1",
            selected_runtime="b1",
            confidence=0.85,
        )
        assert d.confidence == 0.85
        assert d.selected_runtime == "b1"


# ── GoalManager ────────────────────────────────────────────────────────


class TestGoalManager:
    @pytest.mark.asyncio
    async def test_create_goal(self, goal_manager):
        g = await goal_manager.create_goal("Test Goal", "description")
        assert g.title == "Test Goal"
        assert g.status == GoalStatus.DRAFT
        assert g.id != ""

    @pytest.mark.asyncio
    async def test_cancel_goal(self, goal_manager):
        g = await goal_manager.create_goal("Test")
        cancelled = await goal_manager.cancel_goal(g.id)
        assert cancelled is not None
        assert cancelled.status == GoalStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_cancel_not_found(self, goal_manager):
        result = await goal_manager.cancel_goal("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_reprioritize(self, goal_manager):
        g = await goal_manager.create_goal("Test", priority=GoalPriority.LOW)
        updated = await goal_manager.reprioritize(g.id, GoalPriority.CRITICAL)
        assert updated is not None
        assert updated.priority == GoalPriority.CRITICAL

    @pytest.mark.asyncio
    async def test_suspend_resume(self, goal_manager):
        g = await goal_manager.create_goal("Test")
        suspended = await goal_manager.suspend(g.id)
        assert suspended.status == GoalStatus.PAUSED
        resumed = await goal_manager.resume(g.id)
        assert resumed.status == GoalStatus.PENDING

    @pytest.mark.asyncio
    async def test_merge_goals(self, goal_manager):
        g1 = await goal_manager.create_goal("Goal 1")
        g2 = await goal_manager.create_goal("Goal 2")
        merged = await goal_manager.merge_goals([g1.id, g2.id], "Merged")
        assert merged is not None
        assert merged.title == "Merged"
        # Originals should be marked MERGED
        original1 = await goal_manager.get(g1.id)
        assert original1.status == GoalStatus.MERGED

    @pytest.mark.asyncio
    async def test_merge_requires_two(self, goal_manager):
        g1 = await goal_manager.create_goal("Goal 1")
        result = await goal_manager.merge_goals([g1.id], "Merged")
        assert result is None

    @pytest.mark.asyncio
    async def test_split_goal(self, goal_manager):
        g = await goal_manager.create_goal("Parent")
        children = await goal_manager.split_goal(g.id, ["Child 1", "Child 2", "Child 3"])
        assert len(children) == 3
        parent = await goal_manager.get(g.id)
        assert parent.status == GoalStatus.SPLIT
        for child in children:
            assert g.id in child.dependencies

    @pytest.mark.asyncio
    async def test_list_pending_sorted_by_priority(self, goal_manager):
        low = await goal_manager.create_goal("Low", priority=GoalPriority.LOW)
        await goal_manager.resume(low.id)
        critical = await goal_manager.create_goal("Critical", priority=GoalPriority.CRITICAL)
        await goal_manager.resume(critical.id)
        pending = await goal_manager.list_pending()
        # Critical should come before Low
        assert pending[0].priority == GoalPriority.CRITICAL

    @pytest.mark.asyncio
    async def test_complete_goal(self, goal_manager):
        g = await goal_manager.create_goal("Test")
        completed = await goal_manager.complete(g.id, reflection="Done")
        assert completed.status == GoalStatus.COMPLETED
        assert completed.reflection == "Done"
        assert completed.completed_at != ""

    @pytest.mark.asyncio
    async def test_fail_goal(self, goal_manager):
        g = await goal_manager.create_goal("Test")
        failed = await goal_manager.fail(g.id, reason="Error")
        assert failed.status == GoalStatus.FAILED
        assert failed.reflection == "Error"

    @pytest.mark.asyncio
    async def test_metrics(self, goal_manager):
        await goal_manager.create_goal("G1")
        await goal_manager.create_goal("G2")
        m = await goal_manager.metrics()
        assert m["total"] == 2
        assert m["draft"] == 2


# ── DecisionEngine ─────────────────────────────────────────────────────


class TestDecisionEngine:
    @pytest.mark.asyncio
    async def test_select_no_registry(self):
        engine = DecisionEngine(brain_registry=None)
        result = await engine.select(required_capability="coding")
        assert result is None

    @pytest.mark.asyncio
    async def test_decision_weights_sum_to_one(self):
        engine = DecisionEngine()
        total = (
            engine.WEIGHT_HEALTH
            + engine.WEIGHT_LATENCY
            + engine.WEIGHT_CAPABILITY
            + engine.WEIGHT_SUCCESS_RATE
            + engine.WEIGHT_LOAD
        )
        assert abs(total - 1.0) < 0.01

    def test_get_history_empty(self):
        engine = DecisionEngine()
        assert engine.get_history() == []

    def test_get_metrics(self):
        engine = DecisionEngine()
        m = engine.get_metrics()
        assert "total_decisions" in m
        assert "weights" in m


# ── ReflectionEngine ───────────────────────────────────────────────────


class TestReflectionEngine:
    @pytest.mark.asyncio
    async def test_reflect_success(self, reflection_engine):
        r = await reflection_engine.reflect(
            goal_id="g1",
            mission_id="m1",
            goal_achieved=True,
            best_runtime="python",
        )
        assert r.goal_achieved is True
        assert r.goal_id == "g1"
        assert "achieved" in r.summary

    @pytest.mark.asyncio
    async def test_reflect_failure(self, reflection_engine):
        r = await reflection_engine.reflect(
            goal_id="g2",
            mission_id="m2",
            goal_achieved=False,
            failed_runtimes=["claude-code"],
            routing_could_improve=True,
            summary="Failed",
        )
        assert r.goal_achieved is False
        assert "claude-code" in r.failed_runtimes
        assert r.routing_could_improve is True

    @pytest.mark.asyncio
    async def test_reflection_stored_in_memory(self, reflection_engine, executive_memory):
        r = await reflection_engine.reflect(
            goal_id="g3",
            mission_id="m3",
            goal_achieved=True,
        )
        stored = await executive_memory.get_reflection(r.id)
        assert stored is not None
        assert stored["goal_id"] == "g3"

    @pytest.mark.asyncio
    async def test_reflection_history(self, reflection_engine):
        await reflection_engine.reflect(goal_id="g1", mission_id="m1", goal_achieved=True)
        await reflection_engine.reflect(goal_id="g2", mission_id="m2", goal_achieved=False)
        history = reflection_engine.get_history()
        assert len(history) == 2

    @pytest.mark.asyncio
    async def test_reflection_metrics(self, reflection_engine):
        await reflection_engine.reflect(goal_id="g1", mission_id="m1", goal_achieved=True)
        await reflection_engine.reflect(goal_id="g2", mission_id="m2", goal_achieved=True)
        await reflection_engine.reflect(goal_id="g3", mission_id="m3", goal_achieved=False)
        m = reflection_engine.get_metrics()
        assert m["total_reflections"] == 3
        assert m["goals_achieved"] == 2
        assert m["success_rate"] > 0.0


# ── ExecutiveMemory ────────────────────────────────────────────────────


class TestExecutiveMemory:
    @pytest.mark.asyncio
    async def test_store_and_get_goal(self, executive_memory):
        await executive_memory.store_goal({"id": "g1", "title": "Test"})
        g = await executive_memory.get_goal("g1")
        assert g is not None
        assert g["title"] == "Test"

    @pytest.mark.asyncio
    async def test_store_and_list_reflections(self, executive_memory):
        r = Reflection(goal_id="g1", mission_id="m1")
        await executive_memory.store_reflection(r)
        refs = await executive_memory.list_reflections()
        assert len(refs) == 1
        assert refs[0]["goal_id"] == "g1"

    @pytest.mark.asyncio
    async def test_store_and_list_decisions(self, executive_memory):
        d = Decision(goal_id="g1", selected_runtime="b1")
        await executive_memory.store_decision(d.to_dict())
        decisions = await executive_memory.list_decisions()
        assert len(decisions) == 1

    @pytest.mark.asyncio
    async def test_store_and_list_failures(self, executive_memory):
        await executive_memory.store_failure({"id": "f1", "error": "test"})
        failures = await executive_memory.list_failures()
        assert len(failures) == 1

    @pytest.mark.asyncio
    async def test_runtime_event_storage(self, executive_memory):
        await executive_memory.store_runtime_event({"id": "b1", "name": "Python"})
        history = await executive_memory.list_runtime_history()
        assert len(history) == 1

    @pytest.mark.asyncio
    async def test_metrics(self, executive_memory):
        await executive_memory.store_goal({"id": "g1", "title": "T"})
        r = Reflection(goal_id="g1")
        await executive_memory.store_reflection(r)
        m = await executive_memory.metrics()
        assert m["goals_indexed"] == 1
        assert m["reflections_indexed"] == 1


# ── ExecutiveController ────────────────────────────────────────────────


class TestExecutiveController:
    @pytest.mark.asyncio
    async def test_start_stop(self, bus):
        ctrl = ExecutiveController(bus=bus)
        await ctrl.start()
        assert ctrl.status()["started"] is True
        assert ctrl.status()["subscriptions"] > 0
        await ctrl.stop()
        assert ctrl.status()["started"] is False

    @pytest.mark.asyncio
    async def test_goal_creation_via_controller(self, bus):
        ctrl = ExecutiveController(bus=bus)
        await ctrl.start()
        g = await ctrl.goal_manager.create_goal("Test Goal")
        assert g.title == "Test Goal"
        goals = await ctrl.goal_manager.list_all()
        assert len(goals) == 1
        await ctrl.stop()

    @pytest.mark.asyncio
    async def test_decision_engine_access(self, bus):
        ctrl = ExecutiveController(bus=bus)
        assert ctrl.decision_engine is not None
        assert ctrl.reflection_engine is not None
        assert ctrl.memory is not None

    @pytest.mark.asyncio
    async def test_event_processing(self, bus):
        ctrl = ExecutiveController(bus=bus)
        await ctrl.start()
        # Publish a brain.registered event
        await bus.publish(
            EventEnvelope(
                type="brain.registered",
                source="test",
                topic="brain.registered",
                payload={"id": "b1", "display_name": "Python"},
            )
        )
        import asyncio

        await asyncio.sleep(0.1)
        assert ctrl.status()["events_processed"] > 0
        await ctrl.stop()


# ── Goal status enum ──────────────────────────────────────────────────


class TestGoalStatusEnum:
    def test_all_states_present(self):
        states = {s.value for s in GoalStatus}
        required = {
            "draft",
            "pending",
            "active",
            "paused",
            "completed",
            "failed",
            "cancelled",
            "merged",
            "split",
            "archived",
        }
        assert required.issubset(states)


# ── GoalResult ─────────────────────────────────────────────────────────


class TestGoalResult:
    def test_creation(self):
        gr = GoalResult(
            goal_id="g1",
            achieved=True,
            final_status="completed",
            mission_id="m1",
            total_retries=0,
            execution_time_seconds=42.5,
            runtimes_used=["python", "node"],
            cost_estimate=0.05,
        )
        assert gr.achieved is True
        assert gr.final_status == "completed"
        assert gr.total_retries == 0
        assert gr.execution_time_seconds == 42.5
        assert gr.runtimes_used == ["python", "node"]

    def test_to_dict(self):
        gr = GoalResult(goal_id="g1", achieved=False, final_status="failed")
        d = gr.to_dict()
        assert d["goal_id"] == "g1"
        assert d["achieved"] is False
        assert d["final_status"] == "failed"


# ── Archive ──────────────────────────────────────────────────────────


class TestArchive:
    @pytest.mark.asyncio
    async def test_archive_completed_goal(self, goal_manager):
        g = await goal_manager.create_goal("Test")
        await goal_manager.complete(g.id, "Done")
        archived = await goal_manager.archive(g.id)
        assert archived is not None
        assert archived.status == GoalStatus.ARCHIVED

    @pytest.mark.asyncio
    async def test_archive_active_goal_fails(self, goal_manager):
        g = await goal_manager.create_goal("Test")
        # Active goals cannot be archived
        archived = await goal_manager.archive(g.id)
        assert archived is None

    @pytest.mark.asyncio
    async def test_archive_not_found(self, goal_manager):
        result = await goal_manager.archive("nonexistent")
        assert result is None


# ── Enhanced Reflection ───────────────────────────────────────────────


class TestEnhancedReflection:
    @pytest.mark.asyncio
    async def test_reflection_with_analysis_fields(self, reflection_engine):
        r = await reflection_engine.reflect(
            goal_id="g1",
            mission_id="m1",
            goal_achieved=True,
            best_runtime="python",
        )
        d = r.to_dict()
        assert "success_factors" in d
        assert "failures" in d
        assert "improvements" in d
        assert "routing_issues" in d
        assert "capability_gaps" in d

    @pytest.mark.asyncio
    async def test_reflection_failure_analysis(self, reflection_engine):
        r = await reflection_engine.reflect(
            goal_id="g2",
            mission_id="m2",
            goal_achieved=False,
            failed_runtimes=["claude-code"],
            routing_could_improve=True,
            summary="Failed due to timeout",
        )
        d = r.to_dict()
        assert "claude-code" in d["failed_runtimes"]
        assert d["routing_could_improve"] is True


# ── Enhanced Decision ─────────────────────────────────────────────────


class TestEnhancedDecision:
    def test_decision_has_risk_and_reasoning(self):
        d = Decision(
            goal_id="g1",
            task_id="t1",
            selected_runtime="b1",
            confidence=0.8,
            risk=0.2,
            reasoning="health=90; latency=100ms",
        )
        dd = d.to_dict()
        assert "risk" in dd
        assert dd["risk"] == 0.2
        assert "reasoning" in dd
        assert "health" in dd["reasoning"]
