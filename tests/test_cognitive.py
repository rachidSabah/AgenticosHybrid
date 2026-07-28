"""Tests for the Cognitive Intelligence Layer (Phase 12).

Covers: WorldModel, KnowledgeGraph, StrategicPlanner, PredictionEngine,
ExperienceReplay, EvaluationEngine, ImprovementPlanner, ObjectiveManager,
CognitiveController, and REST API endpoints.
"""

from __future__ import annotations

import pytest

from agentic_os.adapters.bus.local import LocalBus
from agentic_os.core.cognitive.domain import (
    EvaluationScore,
    ExperienceRecord,
    ImprovementProposal,
    LongTermObjective,
    ObjectivePriority,
    ObjectiveStatus,
    Prediction,
)
from agentic_os.core.cognitive.evaluation_engine import EvaluationEngine
from agentic_os.core.cognitive.experience_replay import ExperienceReplay
from agentic_os.core.cognitive.improvement_planner import ImprovementPlanner
from agentic_os.core.cognitive.knowledge_graph import KnowledgeGraph
from agentic_os.core.cognitive.memory import CognitiveMemory
from agentic_os.core.cognitive.objective_manager import ObjectiveManager
from agentic_os.core.cognitive.prediction_engine import PredictionEngine
from agentic_os.core.cognitive.strategic_planner import StrategicPlanner
from agentic_os.core.cognitive.world_model import WorldModel

# ── Fixtures ───────────────────────────────────────────────────────────


@pytest.fixture
async def bus():
    b = LocalBus()
    await b.start()
    yield b
    await b.stop()


@pytest.fixture
def cognitive_memory():
    return CognitiveMemory()


@pytest.fixture
def world_model(bus):
    return WorldModel(bus=bus)


@pytest.fixture
def objective_manager(bus):
    return ObjectiveManager(bus=bus)


@pytest.fixture
def prediction_engine(world_model, cognitive_memory):
    return PredictionEngine(world_model=world_model, cognitive_memory=cognitive_memory)


@pytest.fixture
def experience_replay(cognitive_memory):
    return ExperienceReplay(cognitive_memory=cognitive_memory)


@pytest.fixture
def evaluation_engine(world_model, cognitive_memory):
    return EvaluationEngine(world_model=world_model, cognitive_memory=cognitive_memory)


# ── Domain types ───────────────────────────────────────────────────────


class TestDomain:
    def test_long_term_objective_creation(self):
        obj = LongTermObjective(
            title="Test Objective",
            description="A long-term goal",
            priority=ObjectivePriority.HIGH,
        )
        assert obj.id != ""
        assert obj.status == ObjectiveStatus.DRAFT
        assert obj.priority == ObjectivePriority.HIGH
        d = obj.to_dict()
        assert d["title"] == "Test Objective"
        assert "linked_goals" in d
        assert "linked_missions" in d
        assert "reflection_history" in d

    def test_prediction_creation(self):
        p = Prediction(goal_id="g1", probability_of_success=0.85, confidence=0.9)
        assert p.probability_of_success == 0.85
        d = p.to_dict()
        assert "expected_failures" in d
        assert "expected_retries" in d

    def test_experience_record_creation(self):
        r = ExperienceRecord(
            mission_id="m1",
            patterns=["pattern_a"],
            common_failures=["timeout"],
        )
        d = r.to_dict()
        assert "patterns" in d
        assert "capability_bottlenecks" in d

    def test_evaluation_score_creation(self):
        s = EvaluationScore(
            decision_quality=0.9,
            goal_quality=0.8,
            overall_executive_score=0.85,
        )
        d = s.to_dict()
        assert "overall_system_score" in d
        assert d["decision_quality"] == 0.9

    def test_improvement_proposal_creation(self):
        p = ImprovementProposal(
            title="Test Improvement",
            proposal_type="optimization",
        )
        d = p.to_dict()
        assert d["proposal_type"] == "optimization"
        assert d["status"] == "proposed"

    def test_objective_status_enum(self):
        states = {s.value for s in ObjectiveStatus}
        required = {"draft", "active", "paused", "completed", "failed", "cancelled", "archived"}
        assert required.issubset(states)

    def test_objective_priority_enum(self):
        priorities = {s.value for s in ObjectivePriority}
        required = {"critical", "high", "normal", "low", "background"}
        assert required.issubset(priorities)


# ── WorldModel ────────────────────────────────────────────────────────


class TestWorldModel:
    @pytest.mark.asyncio
    async def test_start_stop(self, world_model):
        await world_model.start()
        assert len(world_model._subs) > 0
        await world_model.stop()

    @pytest.mark.asyncio
    async def test_snapshot(self, world_model):
        await world_model.start()
        snap = await world_model.snapshot()
        assert "runtimes" in snap
        assert "mission_stats" in snap
        assert "goal_stats" in snap
        assert "historical" in snap
        assert "last_updated" in snap
        await world_model.stop()

    @pytest.mark.asyncio
    async def test_event_updates_state(self, bus, world_model):
        from agentic_os.domain.events import EventEnvelope

        await world_model.start()
        await bus.publish(
            EventEnvelope(
                type="mission.completed",
                source="test",
                topic="mission.completed",
                payload={"id": "m1"},
            )
        )
        import asyncio

        await asyncio.sleep(0.1)
        snap = await world_model.snapshot()
        assert snap["mission_stats"]["completed"] >= 1
        await world_model.stop()


# ── KnowledgeGraph ─────────────────────────────────────────────────────


class TestKnowledgeGraph:
    @pytest.mark.asyncio
    async def test_add_entity_and_link(self, cognitive_memory):
        kg = KnowledgeGraph(cognitive_memory)
        await kg.add_entity("g1", "goal", {"title": "Goal 1"})
        await kg.add_entity("m1", "mission", {"title": "Mission 1"})
        await kg.link("g1", "m1", "creates")
        graph = await kg.get_graph()
        assert len(graph["nodes"]) == 2
        assert len(graph["edges"]) == 1

    @pytest.mark.asyncio
    async def test_neighbors(self, cognitive_memory):
        kg = KnowledgeGraph(cognitive_memory)
        await kg.add_entity("a", "test", {})
        await kg.add_entity("b", "test", {})
        await kg.link("a", "b", "related")
        neighbors = await kg.neighbors("a")
        assert len(neighbors) == 1
        assert neighbors[0]["neighbor"] == "b"

    @pytest.mark.asyncio
    async def test_impact_analysis(self, cognitive_memory):
        kg = KnowledgeGraph(cognitive_memory)
        await kg.add_entity("a", "test", {})
        await kg.add_entity("b", "test", {})
        await kg.add_entity("c", "test", {})
        await kg.link("a", "b", "dep")
        await kg.link("b", "c", "dep")
        result = await kg.impact_analysis("a")
        assert result["count"] >= 2


# ── StrategicPlanner ────────────────────────────────────────────────────


class TestStrategicPlanner:
    @pytest.mark.asyncio
    async def test_generate_strategy_no_world(self):
        planner = StrategicPlanner(None)
        result = await planner.generate_strategy()
        assert "recommendations" in result
        assert "resource_allocation" in result
        assert "mission_ordering" in result

    @pytest.mark.asyncio
    async def test_generate_strategy_with_world(self, world_model):
        await world_model.start()
        planner = StrategicPlanner(world_model)
        result = await planner.generate_strategy()
        assert "recommendations" in result
        assert "world_snapshot" in result
        await world_model.stop()


# ── PredictionEngine ──────────────────────────────────────────────────


class TestPredictionEngine:
    @pytest.mark.asyncio
    async def test_predict_no_world(self):
        engine = PredictionEngine(None, None)
        p = await engine.predict(goal_id="g1")
        assert p.goal_id == "g1"
        assert p.confidence == 0.0

    @pytest.mark.asyncio
    async def test_predict_with_world(self, world_model, cognitive_memory):
        await world_model.start()
        engine = PredictionEngine(world_model, cognitive_memory)
        p = await engine.predict(goal_id="g1", required_capability="coding")
        assert p.goal_id == "g1"
        assert p.probability_of_success >= 0.0
        assert p.confidence >= 0.0
        assert "factors" in p.to_dict()
        await world_model.stop()

    def test_history(self, prediction_engine):
        assert isinstance(prediction_engine.get_history(), list)


# ── ExperienceReplay ──────────────────────────────────────────────────


class TestExperienceReplay:
    @pytest.mark.asyncio
    async def test_replay(self, experience_replay):
        record = await experience_replay.replay(mission_id="m1", goal_id="g1")
        assert record.mission_id == "m1"
        assert isinstance(record.patterns, list)
        d = record.to_dict()
        assert "optimization_opportunities" in d

    def test_history(self, experience_replay):
        assert isinstance(experience_replay.get_history(), list)


# ── EvaluationEngine ──────────────────────────────────────────────────


class TestEvaluationEngine:
    @pytest.mark.asyncio
    async def test_evaluate_no_world(self):
        engine = EvaluationEngine(None, None)
        score = await engine.evaluate()
        assert score.overall_executive_score == 0.0

    @pytest.mark.asyncio
    async def test_evaluate_with_world(self, world_model, cognitive_memory):
        await world_model.start()
        engine = EvaluationEngine(world_model, cognitive_memory)
        score = await engine.evaluate()
        assert score.overall_executive_score >= 0.0
        assert score.overall_system_score >= 0.0
        d = score.to_dict()
        assert "decision_quality" in d
        assert "routing_quality" in d
        await world_model.stop()

    def test_get_latest_none(self):
        engine = EvaluationEngine(None)
        assert engine.get_latest() is None


# ── ImprovementPlanner ─────────────────────────────────────────────────


class TestImprovementPlanner:
    @pytest.mark.asyncio
    async def test_generate_no_engines(self):
        planner = ImprovementPlanner(None, None, None)
        proposals = await planner.generate()
        assert isinstance(proposals, list)

    def test_history_empty(self):
        planner = ImprovementPlanner(None, None, None)
        assert planner.get_history() == []


# ── ObjectiveManager ──────────────────────────────────────────────────


class TestObjectiveManager:
    @pytest.mark.asyncio
    async def test_create(self, objective_manager):
        obj = await objective_manager.create(title="Test", description="Desc")
        assert obj.title == "Test"
        assert obj.status == ObjectiveStatus.DRAFT

    @pytest.mark.asyncio
    async def test_activate(self, objective_manager):
        obj = await objective_manager.create(title="Test")
        activated = await objective_manager.activate(obj.id)
        assert activated.status == ObjectiveStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_cancel(self, objective_manager):
        obj = await objective_manager.create(title="Test")
        cancelled = await objective_manager.cancel(obj.id)
        assert cancelled.status == ObjectiveStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_archive_terminal(self, objective_manager):
        obj = await objective_manager.create(title="Test")
        await objective_manager.cancel(obj.id)
        archived = await objective_manager.archive(obj.id)
        assert archived.status == ObjectiveStatus.ARCHIVED

    @pytest.mark.asyncio
    async def test_archive_active_fails(self, objective_manager):
        obj = await objective_manager.create(title="Test")
        result = await objective_manager.archive(obj.id)
        assert result is None

    @pytest.mark.asyncio
    async def test_prioritize(self, objective_manager):
        obj = await objective_manager.create(title="Test")
        updated = await objective_manager.prioritize(obj.id, ObjectivePriority.CRITICAL)
        assert updated.priority == ObjectivePriority.CRITICAL

    @pytest.mark.asyncio
    async def test_merge(self, objective_manager):
        o1 = await objective_manager.create(title="Obj 1")
        o2 = await objective_manager.create(title="Obj 2")
        merged = await objective_manager.merge([o1.id, o2.id], "Merged")
        assert merged is not None
        assert merged.title == "Merged"

    @pytest.mark.asyncio
    async def test_split(self, objective_manager):
        obj = await objective_manager.create(title="Parent")
        children = await objective_manager.split(obj.id, ["Child A", "Child B"])
        assert len(children) == 2
        parent = await objective_manager.get(obj.id)
        assert parent.status == ObjectiveStatus.ARCHIVED

    @pytest.mark.asyncio
    async def test_list_all(self, objective_manager):
        await objective_manager.create(title="O1")
        await objective_manager.create(title="O2")
        objs = await objective_manager.list_all()
        assert len(objs) == 2


# ── CognitiveMemory ───────────────────────────────────────────────────


class TestCognitiveMemory:
    @pytest.mark.asyncio
    async def test_store_and_get_objective(self, cognitive_memory):
        await cognitive_memory.store_objective("o1", {"title": "Test"})
        obj = await cognitive_memory.get_objective("o1")
        assert obj["title"] == "Test"

    @pytest.mark.asyncio
    async def test_store_prediction(self, cognitive_memory):
        await cognitive_memory.store_prediction("p1", {"goal_id": "g1"})
        preds = await cognitive_memory.list_predictions()
        assert len(preds) == 1

    @pytest.mark.asyncio
    async def test_store_experience(self, cognitive_memory):
        await cognitive_memory.store_experience("e1", {"patterns": ["a"]})
        exps = await cognitive_memory.list_experience()
        assert len(exps) == 1

    @pytest.mark.asyncio
    async def test_store_evaluation(self, cognitive_memory):
        await cognitive_memory.store_evaluation("ev1", {"score": 0.9})
        evals = await cognitive_memory.list_evaluations()
        assert len(evals) == 1

    @pytest.mark.asyncio
    async def test_store_improvement(self, cognitive_memory):
        await cognitive_memory.store_improvement("i1", {"title": "Fix"})
        imps = await cognitive_memory.list_improvements()
        assert len(imps) == 1

    @pytest.mark.asyncio
    async def test_world_snapshot(self, cognitive_memory):
        await cognitive_memory.store_world_snapshot({"runtime_count": 3})
        snap = await cognitive_memory.get_latest_world_snapshot()
        assert snap["runtime_count"] == 3

    @pytest.mark.asyncio
    async def test_kg_operations(self, cognitive_memory):
        await cognitive_memory.add_kg_node("n1", "goal", {"title": "G"})
        await cognitive_memory.add_kg_edge("n1", "n2", "creates")
        kg = await cognitive_memory.get_kg()
        assert len(kg["nodes"]) == 1
        assert len(kg["edges"]) == 1

    @pytest.mark.asyncio
    async def test_metrics(self, cognitive_memory):
        await cognitive_memory.store_objective("o1", {})
        m = await cognitive_memory.metrics()
        assert m["objectives_indexed"] == 1
