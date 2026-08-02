"""Tests for Phase 17 — Autonomous Agent Evolution, Self-Construction & Continuous Improvement.

Covers:
  - Domain models (ImprovementProposal, SafetyValidationReport, GenerationPlan, etc.)
  - SafetyValidator (6 safety checks)
  - RegressionGuard (risk prediction)
  - ImprovementEngine (proposal generation from ecosystem/cognitive/executive)
  - CodeGenerationPlanner (blueprint generation)
  - CapabilityExpansionEngine (gap analysis)
  - RefactoringAdvisor + PerformanceOptimizer
  - AutonomousReviewer + KnowledgeSynthesizer
  - ImprovementScheduler (queue + scheduling)
  - EvolutionManager (top-level coordinator)
  - EvolutionController (event subscriptions)
  - REST API endpoints under /api/evolution/*
  - WebSocket propagation via DashboardBroadcaster
  - Rollback workflow
  - Safety validation failure handling
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agentic_os.adapters.bus.local import LocalBus
from agentic_os.core.brains.registry import BrainRegistry
from agentic_os.core.cognitive.memory import CognitiveMemory
from agentic_os.core.ecosystem.collaboration_network import CollaborationNetwork
from agentic_os.core.ecosystem.evolution_engine import EvolutionEngine
from agentic_os.core.evolution import (
    AutonomousReviewer,
    CapabilityExpansionEngine,
    CodeGenerationPlanner,
    EvolutionController,
    EvolutionManager,
    GenerationTargetType,
    ImprovementEngine,
    ImprovementPriority,
    ImprovementProposal,
    ImprovementScheduler,
    ImprovementStatus,
    ImprovementType,
    KnowledgeSynthesizer,
    PerformanceOptimizer,
    RefactoringAdvisor,
    RegressionGuard,
    SafetyValidator,
    SystemReadinessLevel,
    ValidationCheckResult,
    ValidationCheckType,
)
from agentic_os.core.executive.memory import ExecutiveMemory
from agentic_os.domain.brains import (
    BrainRecord,
    BrainRuntime,
    BrainStatus,
    BrainType,
    BrainVendor,
)

# ── Fixtures ───────────────────────────────────────────────────────────


def make_brain(
    brain_id: str = "b1",
    name: str = "TestBrain",
    capabilities: tuple[str, ...] = ("chat",),
    health: float = 90.0,
    latency: float = 100.0,
) -> BrainRecord:
    return BrainRecord(
        id=brain_id,
        display_name=name,
        brain_type=BrainType.LOCAL_CLI,
        vendor=BrainVendor.OLLAMA,
        runtime=BrainRuntime.PYTHON,
        version="1.0.0",
        status=BrainStatus.CONNECTED,
        health=health,
        capabilities=capabilities,
        latency=latency,
    )


@pytest.fixture
async def bus():
    b = LocalBus()
    await b.start()
    yield b
    await b.stop()


@pytest.fixture
async def registry(bus):
    r = BrainRegistry()
    await r.start(event_bus=bus)
    yield r
    await r.stop()


@pytest.fixture
def exec_memory():
    return ExecutiveMemory()


@pytest.fixture
def cog_memory():
    return CognitiveMemory()


@pytest.fixture
def collaboration_network():
    return CollaborationNetwork()


@pytest.fixture
def evolution_engine():
    return EvolutionEngine()


@pytest.fixture
async def controller(bus, evolution_engine, exec_memory, cog_memory):
    ec = EvolutionController(
        bus=bus,
        evolution_engine=evolution_engine,
        exec_memory=exec_memory,
        cognitive_memory=cog_memory,
    )
    await ec.start()
    yield ec
    await ec.stop()


# ── Domain Models ──────────────────────────────────────────────────────


class TestEvolutionDomain:
    def test_improvement_proposal_defaults(self):
        p = ImprovementProposal()
        assert p.id.startswith("imp-")
        assert p.status == ImprovementStatus.PROPOSED
        assert p.priority == ImprovementPriority.MEDIUM
        assert p.type == ImprovementType.PERFORMANCE_OPTIMIZATION

    def test_improvement_proposal_to_dict(self):
        p = ImprovementProposal(title="Test", expected_impact=0.5)
        d = p.to_dict()
        assert d["title"] == "Test"
        assert d["expected_impact"] == 0.5
        assert d["status"] == "proposed"

    def test_improvement_status_transitions(self):
        p = ImprovementProposal()
        assert p.status == ImprovementStatus.PROPOSED
        p.status = ImprovementStatus.VALIDATED
        assert p.status == ImprovementStatus.VALIDATED
        p.status = ImprovementStatus.APPROVED
        p.status = ImprovementStatus.APPLIED
        p.status = ImprovementStatus.ROLLED_BACK

    def test_generation_target_types(self):
        types = {t.value for t in GenerationTargetType}
        required = {
            "capability",
            "agent",
            "workflow",
            "planner",
            "tool",
            "orchestrator",
            "strategy",
            "module",
        }
        assert required.issubset(types)


# ── SafetyValidator ────────────────────────────────────────────────────


class TestSafetyValidator:
    @pytest.mark.asyncio
    async def test_validate_passes_safe_proposal(self):
        validator = SafetyValidator()
        proposal = ImprovementProposal(
            title="Safe improvement",
            implementation_plan={
                "dependencies": ["os"],  # stdlib, always available
                "api_changes": {"added_endpoints": ["/api/test"]},
            },
        )
        report = await validator.validate(proposal)
        assert report.approved is True
        assert report.overall_result in {
            ValidationCheckResult.PASS,
            ValidationCheckResult.WARNING,
        }

    @pytest.mark.asyncio
    async def test_validate_fails_on_missing_dependency(self):
        validator = SafetyValidator()
        proposal = ImprovementProposal(
            title="Bad dependency",
            implementation_plan={
                "dependencies": ["nonexistent_package_xyz"],
            },
        )
        report = await validator.validate(proposal)
        assert report.approved is False
        assert report.overall_result == ValidationCheckResult.FAIL
        assert any("Missing dependencies" in issue for issue in report.blocking_issues)

    @pytest.mark.asyncio
    async def test_validate_fails_on_breaking_api(self):
        validator = SafetyValidator()
        proposal = ImprovementProposal(
            title="Breaking change",
            implementation_plan={"remove_api": True},
        )
        report = await validator.validate(proposal)
        assert report.approved is False
        assert any("breaking" in issue.lower() for issue in report.blocking_issues)

    @pytest.mark.asyncio
    async def test_validate_fails_on_risky_patterns(self):
        validator = SafetyValidator()
        proposal = ImprovementProposal(
            title="Risky code",
            implementation_plan={"code": "os.system('rm -rf /')"},
        )
        report = await validator.validate(proposal)
        assert report.approved is False
        assert any("Risky patterns" in issue for issue in report.blocking_issues)

    @pytest.mark.asyncio
    async def test_validate_runs_all_6_checks(self):
        validator = SafetyValidator()
        proposal = ImprovementProposal(title="Test")
        report = await validator.validate(proposal)
        assert len(report.checks) == 6
        check_types = {c.type for c in report.checks}
        assert check_types == {
            ValidationCheckType.ARCHITECTURE,
            ValidationCheckType.DEPENDENCY,
            ValidationCheckType.API_COMPATIBILITY,
            ValidationCheckType.REGRESSION_PREDICTION,
            ValidationCheckType.SECURITY,
            ValidationCheckType.PERFORMANCE,
        }

    @pytest.mark.asyncio
    async def test_validator_stats(self):
        validator = SafetyValidator()
        await validator.validate(ImprovementProposal(title="Test"))
        stats = validator.stats()
        assert stats["total_validations"] == 1
        assert "pass_rate" in stats


# ── RegressionGuard ────────────────────────────────────────────────────


class TestRegressionGuard:
    @pytest.mark.asyncio
    async def test_predict_low_risk_for_simple_proposal(self):
        guard = RegressionGuard()
        proposal = ImprovementProposal(
            implementation_plan={
                "affected_modules": ["some_module"],
                "complexity": "low",
            }
        )
        result = await guard.predict(proposal)
        assert result["regression_risk"] < 0.3
        assert result["risk_level"] == "low"
        assert result["recommendation"] == "proceed"

    @pytest.mark.asyncio
    async def test_predict_high_risk_for_critical_module(self):
        guard = RegressionGuard()
        proposal = ImprovementProposal(
            implementation_plan={
                "affected_modules": ["kernel", "event_bus", "brain_registry", "api", "security"],
                "api_changes": {
                    "removed_endpoints": ["/api/critical1", "/api/critical2"],
                    "renamed_endpoints": ["/api/old"],
                },
                "dependency_changes": ["remove critical_dep1", "remove critical_dep2"],
                "complexity": "high",
            }
        )
        result = await guard.predict(proposal)
        assert result["regression_risk"] >= 0.7
        assert result["risk_level"] == "high"
        assert result["recommendation"] == "reject"

    @pytest.mark.asyncio
    async def test_predict_moderate_risk(self):
        guard = RegressionGuard()
        proposal = ImprovementProposal(
            implementation_plan={
                "affected_modules": ["some_module"],
                "complexity": "medium",
            }
        )
        result = await guard.predict(proposal)
        assert 0.0 <= result["regression_risk"] <= 1.0

    def test_guard_stats(self):
        guard = RegressionGuard()
        assert guard.stats()["predictions_made"] == 0


# ── ImprovementEngine ──────────────────────────────────────────────────


class TestImprovementEngine:
    @pytest.mark.asyncio
    async def test_generate_from_ecosystem(self, evolution_engine):
        # Add some recommendations to the ecosystem engine
        from agentic_os.core.ecosystem.domain import (
            EvolutionRecommendation,
            RecommendationType,
        )

        evolution_engine._recommendations = [
            EvolutionRecommendation(
                type=RecommendationType.CAPABILITY,
                title="Test recommendation",
                rationale="Test rationale",
                priority=0.8,
                confidence=0.7,
                expected_impact=0.5,
            )
        ]
        engine = ImprovementEngine(evolution_engine=evolution_engine)
        proposals = await engine.generate_all()
        assert len(proposals) > 0
        assert any(p.source == "ecosystem" for p in proposals)

    @pytest.mark.asyncio
    async def test_generate_from_executive(self, exec_memory):
        # Store a reflection with capability gaps
        await exec_memory.store_reflection(
            type(
                "Reflection",
                (),
                {
                    "id": "r1",
                    "to_dict": lambda self: {
                        "id": "r1",
                        "capability_gaps": ["chat", "vision"],
                        "improvements": ["optimize routing"],
                        "summary": "Test reflection",
                    },
                },
            )()
        )
        engine = ImprovementEngine(exec_memory=exec_memory)
        proposals = await engine.generate_all()
        # Should generate proposals for each gap + improvement
        assert len(proposals) >= 2

    @pytest.mark.asyncio
    async def test_list_proposals_by_status(self, evolution_engine):
        from agentic_os.core.ecosystem.domain import (
            EvolutionRecommendation,
            RecommendationType,
        )

        evolution_engine._recommendations = [
            EvolutionRecommendation(type=RecommendationType.OPTIMIZATION, title="Test"),
        ]
        engine = ImprovementEngine(evolution_engine=evolution_engine)
        await engine.generate_all()
        proposed = engine.list_proposals(status=ImprovementStatus.PROPOSED)
        assert len(proposed) > 0

    @pytest.mark.asyncio
    async def test_update_proposal(self, evolution_engine):
        from agentic_os.core.ecosystem.domain import (
            EvolutionRecommendation,
            RecommendationType,
        )

        evolution_engine._recommendations = [
            EvolutionRecommendation(type=RecommendationType.OPTIMIZATION, title="Test"),
        ]
        engine = ImprovementEngine(evolution_engine=evolution_engine)
        proposals = await engine.generate_all()
        proposal_id = proposals[0].id
        updated = engine.update_proposal(proposal_id, status=ImprovementStatus.VALIDATED)
        assert updated is not None
        assert updated.status == ImprovementStatus.VALIDATED

    @pytest.mark.asyncio
    async def test_remove_proposal(self, evolution_engine):
        from agentic_os.core.ecosystem.domain import (
            EvolutionRecommendation,
            RecommendationType,
        )

        evolution_engine._recommendations = [
            EvolutionRecommendation(type=RecommendationType.OPTIMIZATION, title="Test"),
        ]
        engine = ImprovementEngine(evolution_engine=evolution_engine)
        proposals = await engine.generate_all()
        proposal_id = proposals[0].id
        assert engine.remove_proposal(proposal_id) is True
        assert engine.get_proposal(proposal_id) is None

    def test_engine_stats(self):
        engine = ImprovementEngine()
        stats = engine.stats()
        assert "stored" in stats
        assert "by_status" in stats


# ── CodeGenerationPlanner ──────────────────────────────────────────────


class TestCodeGenerationPlanner:
    @pytest.mark.asyncio
    async def test_plan_from_capability_proposal(self):
        planner = CodeGenerationPlanner()
        proposal = ImprovementProposal(
            type=ImprovementType.CAPABILITY_EXPANSION,
            title="New chat capability",
            target_capability="chat",
        )
        plan = await planner.plan_from_proposal(proposal)
        assert plan is not None
        assert plan.target_type == GenerationTargetType.CAPABILITY
        assert plan.name == "New chat capability"
        assert len(plan.dependencies) > 0
        assert len(plan.rollout_steps) > 0
        assert len(plan.rollback_steps) > 0

    @pytest.mark.asyncio
    async def test_plan_from_agent_proposal(self):
        planner = CodeGenerationPlanner()
        proposal = ImprovementProposal(
            type=ImprovementType.NEW_AGENT,
            title="New research agent",
        )
        plan = await planner.plan_from_proposal(proposal)
        assert plan is not None
        assert plan.target_type == GenerationTargetType.AGENT

    @pytest.mark.asyncio
    async def test_plan_returns_none_for_unmappable_type(self):
        planner = CodeGenerationPlanner()
        proposal = ImprovementProposal(
            type=ImprovementType.CONFIGURATION_TUNING,
            title="Config change",
        )
        plan = await planner.plan_from_proposal(proposal)
        assert plan is None

    @pytest.mark.asyncio
    async def test_list_plans_by_type(self):
        planner = CodeGenerationPlanner()
        proposal = ImprovementProposal(
            type=ImprovementType.NEW_TOOL,
            title="New tool",
        )
        await planner.plan_from_proposal(proposal)
        plans = planner.list_plans(target_type=GenerationTargetType.TOOL)
        assert len(plans) >= 1

    @pytest.mark.asyncio
    async def test_update_plan_status(self):
        planner = CodeGenerationPlanner()
        proposal = ImprovementProposal(
            type=ImprovementType.NEW_WORKFLOW,
            title="New workflow",
        )
        plan = await planner.plan_from_proposal(proposal)
        assert planner.update_plan_status(plan.id, "approved") is True
        assert plan.status == "approved"


# ── CapabilityExpansionEngine ──────────────────────────────────────────


class TestCapabilityExpansionEngine:
    @pytest.mark.asyncio
    async def test_analyze_gaps_finds_missing(self):
        engine = CapabilityExpansionEngine()
        proposals = await engine.analyze_gaps(
            required_caps=["chat", "code", "vision"],
            available_caps=["chat"],
        )
        assert len(proposals) == 2  # code + vision missing
        assert all(p.type == ImprovementType.CAPABILITY_EXPANSION for p in proposals)

    @pytest.mark.asyncio
    async def test_analyze_gaps_no_gaps(self):
        engine = CapabilityExpansionEngine()
        proposals = await engine.analyze_gaps(
            required_caps=["chat"],
            available_caps=["chat"],
        )
        assert len(proposals) == 0

    @pytest.mark.asyncio
    async def test_list_gaps(self):
        engine = CapabilityExpansionEngine()
        await engine.analyze_gaps(["chat"], [])
        gaps = engine.list_gaps()
        assert "chat" in gaps


# ── Advisors ───────────────────────────────────────────────────────────


class TestAdvisors:
    @pytest.mark.asyncio
    async def test_refactoring_advisor_detects_high_complexity(self):
        advisor = RefactoringAdvisor()
        proposals = await advisor.analyze(
            {
                "module_a": {"complexity": 20},
                "module_b": {"complexity": 5},
            }
        )
        assert len(proposals) == 1  # only module_a
        assert proposals[0].type == ImprovementType.REFACTORING

    @pytest.mark.asyncio
    async def test_performance_optimizer_detects_slow_endpoint(self):
        optimizer = PerformanceOptimizer()
        proposals = await optimizer.analyze(
            {
                "api_latencies": {"/api/slow": 1500, "/api/fast": 50},
            }
        )
        assert len(proposals) == 1
        assert "slow" in proposals[0].title.lower()

    @pytest.mark.asyncio
    async def test_performance_optimizer_detects_high_memory(self):
        optimizer = PerformanceOptimizer()
        proposals = await optimizer.analyze(
            {
                "memory_usage_mb": 600,
            }
        )
        assert len(proposals) == 1
        assert "memory" in proposals[0].title.lower()


# ── AutonomousReviewer + KnowledgeSynthesizer ─────────────────────────


class TestReviewSynthesis:
    @pytest.mark.asyncio
    async def test_reviewer_approves_complete_proposal(self):
        reviewer = AutonomousReviewer()
        proposal = ImprovementProposal(
            title="Complete proposal",
            description="A full description",
            rationale="Good rationale",
            implementation_plan={"action": "test"},
            rollback_plan={"action": "revert"},
            risk_score=0.2,
            expected_impact=0.7,
            confidence=0.8,
        )
        review = await reviewer.review(proposal)
        assert review["decision"] == "approved"
        assert review["score"] >= 0.7

    @pytest.mark.asyncio
    async def test_reviewer_rejects_incomplete_proposal(self):
        reviewer = AutonomousReviewer()
        proposal = ImprovementProposal(
            title="",  # missing title
            risk_score=0.9,  # high risk
            expected_impact=0.1,  # low impact
        )
        review = await reviewer.review(proposal)
        assert review["decision"] in {"rejected", "needs_revision"}

    @pytest.mark.asyncio
    async def test_knowledge_synthesizer_extracts_insights(self):
        synthesizer = KnowledgeSynthesizer()
        synthesis = await synthesizer.synthesize(
            topic="routing optimization",
            sources=[
                {
                    "type": "reflection",
                    "data": {
                        "capability_gaps": ["chat"],
                        "improvements": ["use cache"],
                        "summary": "Need better routing",
                    },
                },
                {
                    "type": "decision",
                    "data": {"selected_runtime": "b1", "confidence": 0.8},
                },
            ],
        )
        assert synthesis.topic == "routing optimization"
        assert len(synthesis.key_insights) > 0
        assert len(synthesis.patterns) > 0
        assert synthesis.confidence > 0


# ── ImprovementScheduler ───────────────────────────────────────────────


class TestImprovementScheduler:
    def test_enqueue_requires_validated_status(self):
        scheduler = ImprovementScheduler()
        proposal = ImprovementProposal(status=ImprovementStatus.PROPOSED)
        assert scheduler.enqueue(proposal) is False

    def test_enqueue_validated_proposal(self):
        scheduler = ImprovementScheduler()
        proposal = ImprovementProposal(status=ImprovementStatus.VALIDATED)
        assert scheduler.enqueue(proposal) is True

    def test_schedule_next_returns_highest_priority(self):
        scheduler = ImprovementScheduler()
        low = ImprovementProposal(
            status=ImprovementStatus.VALIDATED,
            priority=ImprovementPriority.LOW,
            risk_score=0.1,
        )
        critical = ImprovementProposal(
            status=ImprovementStatus.VALIDATED,
            priority=ImprovementPriority.CRITICAL,
            risk_score=0.5,
        )
        high = ImprovementProposal(
            status=ImprovementStatus.VALIDATED,
            priority=ImprovementPriority.HIGH,
            risk_score=0.2,
        )
        scheduler.enqueue(low)
        scheduler.enqueue(critical)
        scheduler.enqueue(high)
        # Critical should be scheduled first
        next_item = scheduler.schedule_next()
        assert next_item is not None
        assert next_item.priority == ImprovementPriority.CRITICAL

    def test_mark_applied(self):
        scheduler = ImprovementScheduler()
        proposal = ImprovementProposal(status=ImprovementStatus.VALIDATED)
        scheduler.enqueue(proposal)
        scheduled = scheduler.schedule_next()
        scheduler.mark_executing(scheduled.id)
        assert scheduler.mark_applied(scheduled.id) is True

    def test_mark_rolled_back(self):
        scheduler = ImprovementScheduler()
        proposal = ImprovementProposal(status=ImprovementStatus.VALIDATED)
        scheduler.enqueue(proposal)
        scheduled = scheduler.schedule_next()
        assert scheduler.mark_rolled_back(scheduled.id) is True

    def test_clear_queue(self):
        scheduler = ImprovementScheduler()
        scheduler.enqueue(ImprovementProposal(status=ImprovementStatus.VALIDATED))
        scheduler.enqueue(ImprovementProposal(status=ImprovementStatus.VALIDATED))
        count = scheduler.clear_queue()
        assert count == 2

    def test_stats(self):
        scheduler = ImprovementScheduler()
        stats = scheduler.stats()
        assert "queue_size" in stats
        assert "max_concurrent" in stats


# ── EvolutionManager ───────────────────────────────────────────────────


class TestEvolutionManager:
    @pytest.mark.asyncio
    async def test_manager_starts_and_publishes_event(self, bus):
        events: list[Any] = []

        async def capture(e):
            events.append(e)

        sub_id = await bus.subscribe("evolution.started", capture)
        try:
            mgr = EvolutionManager(bus=bus)
            await mgr.start()
            try:
                await asyncio.sleep(0.05)
                assert mgr.started is True
                assert any(e.topic == "evolution.started" for e in events)
            finally:
                await mgr.stop()
        finally:
            await bus.unsubscribe(sub_id)

    @pytest.mark.asyncio
    async def test_assess_readiness(self, bus):
        mgr = EvolutionManager(bus=bus)
        await mgr.start()
        try:
            readiness = await mgr.assess_readiness()
            assert "level" in readiness
            assert "readiness_score" in readiness
            assert readiness["level"] in {r.value for r in SystemReadinessLevel}
        finally:
            await mgr.stop()

    @pytest.mark.asyncio
    async def test_dashboard(self, bus):
        mgr = EvolutionManager(bus=bus)
        await mgr.start()
        try:
            dash = mgr.dashboard()
            assert "statistics" in dash
            assert "readiness" in dash
            assert "improvement_engine" in dash
            assert "safety_validator" in dash
        finally:
            await mgr.stop()

    @pytest.mark.asyncio
    async def test_synthesize_knowledge(self, bus):
        mgr = EvolutionManager(bus=bus)
        await mgr.start()
        try:
            result = await mgr.synthesize_knowledge(
                "test topic",
                [{"type": "reflection", "data": {"capability_gaps": ["chat"]}}],
            )
            assert result["topic"] == "test topic"
        finally:
            await mgr.stop()


# ── EvolutionController ────────────────────────────────────────────────


class TestEvolutionController:
    @pytest.mark.asyncio
    async def test_controller_starts(self, bus, evolution_engine, exec_memory, cog_memory):
        ec = EvolutionController(
            bus=bus,
            evolution_engine=evolution_engine,
            exec_memory=exec_memory,
            cognitive_memory=cog_memory,
        )
        await ec.start()
        try:
            assert ec.started is True
            assert len(ec._subscriptions) == 4
        finally:
            await ec.stop()

    @pytest.mark.asyncio
    async def test_controller_status(self, bus, evolution_engine, exec_memory, cog_memory):
        ec = EvolutionController(
            bus=bus,
            evolution_engine=evolution_engine,
            exec_memory=exec_memory,
            cognitive_memory=cog_memory,
        )
        await ec.start()
        try:
            status = ec.status()
            assert status["started"] is True
            assert "events_processed" in status
        finally:
            await ec.stop()

    @pytest.mark.asyncio
    async def test_controller_reacts_to_ecosystem_event(
        self, bus, evolution_engine, exec_memory, cog_memory
    ):
        from agentic_os.domain.events import EventEnvelope

        ec = EvolutionController(
            bus=bus,
            evolution_engine=evolution_engine,
            exec_memory=exec_memory,
            cognitive_memory=cog_memory,
        )
        await ec.start()
        try:
            initial = ec._events_processed
            await bus.publish(
                EventEnvelope(
                    type="ecosystem.evolution.generated",
                    source="test",
                    topic="ecosystem.evolution.generated",
                    payload={"recommendations": [], "count": 0},
                )
            )
            await asyncio.sleep(0.3)
            assert ec._events_processed > initial
        finally:
            await ec.stop()


# ── REST API ───────────────────────────────────────────────────────────


class TestEvolutionAPI:
    @pytest.fixture
    async def app_with_evolution(self, bus, evolution_engine, exec_memory, cog_memory):
        from agentic_os.api.app import create_app
        from agentic_os.kernel import Kernel

        kernel = Kernel()
        platform = kernel.platform()
        platform.bus = bus

        ec = EvolutionController(
            bus=bus,
            evolution_engine=evolution_engine,
            exec_memory=exec_memory,
            cognitive_memory=cog_memory,
        )
        await ec.start()
        platform.evolution_controller = ec

        app = create_app(platform)
        try:
            yield app
        finally:
            await ec.stop()

    def test_evolution_status(self, app_with_evolution):
        with TestClient(app_with_evolution) as client:
            r = client.get("/api/evolution/status")
            assert r.status_code == 200
            data = r.json()
            assert data["started"] is True

    def test_evolution_dashboard(self, app_with_evolution):
        with TestClient(app_with_evolution) as client:
            r = client.get("/api/evolution/dashboard")
            assert r.status_code == 200
            data = r.json()
            assert "statistics" in data
            assert "readiness" in data

    def test_evolution_statistics(self, app_with_evolution):
        with TestClient(app_with_evolution) as client:
            r = client.get("/api/evolution/statistics")
            assert r.status_code == 200
            data = r.json()
            assert "total_proposals" in data

    def test_evolution_readiness(self, app_with_evolution):
        with TestClient(app_with_evolution) as client:
            r = client.get("/api/evolution/readiness")
            assert r.status_code == 200
            data = r.json()
            assert "level" in data

    def test_evolution_improvements(self, app_with_evolution):
        with TestClient(app_with_evolution) as client:
            r = client.get("/api/evolution/improvements")
            assert r.status_code == 200
            data = r.json()
            assert "improvements" in data

    def test_evolution_safety(self, app_with_evolution):
        with TestClient(app_with_evolution) as client:
            r = client.get("/api/evolution/safety")
            assert r.status_code == 200
            data = r.json()
            assert "validator" in data

    def test_evolution_scheduler(self, app_with_evolution):
        with TestClient(app_with_evolution) as client:
            r = client.get("/api/evolution/scheduler")
            assert r.status_code == 200
            data = r.json()
            assert "queue" in data

    def test_evolution_plans(self, app_with_evolution):
        with TestClient(app_with_evolution) as client:
            r = client.get("/api/evolution/plans")
            assert r.status_code == 200
            data = r.json()
            assert "plans" in data

    def test_evolution_knowledge(self, app_with_evolution):
        with TestClient(app_with_evolution) as client:
            r = client.get("/api/evolution/knowledge")
            assert r.status_code == 200

    def test_evolution_analyze(self, app_with_evolution):
        with TestClient(app_with_evolution) as client:
            r = client.post("/api/evolution/analyze")
            assert r.status_code == 200
            data = r.json()
            assert "proposals_generated" in data

    def test_evolution_assess_readiness(self, app_with_evolution):
        with TestClient(app_with_evolution) as client:
            r = client.post("/api/evolution/readiness/assess")
            assert r.status_code == 200

    def test_evolution_synthesize(self, app_with_evolution):
        with TestClient(app_with_evolution) as client:
            r = client.post(
                "/api/evolution/synthesize",
                json={
                    "topic": "test synthesis",
                    "sources": [{"type": "reflection", "data": {"improvements": ["test"]}}],
                },
            )
            assert r.status_code == 200
            data = r.json()
            assert data["topic"] == "test synthesis"


# ── WebSocket Propagation ─────────────────────────────────────────────


class TestDashboardBroadcasterEvolutionForwarding:
    def test_dashboard_topics_include_evolution_events(self):
        from agentic_os.api.dashboard import _DASHBOARD_TOPIC_STRINGS

        required = {
            "evolution.started",
            "evolution.stopped",
            "evolution.analysis.completed",
            "evolution.improvement.scheduled",
            "evolution.improvement.applied",
            "evolution.improvement.rolled_back",
            "evolution.knowledge.synthesized",
            "evolution.readiness.updated",
            "evolution.statistics.updated",
        }
        missing = required - set(_DASHBOARD_TOPIC_STRINGS)
        assert not missing, f"Missing evolution topics: {missing}"

    @pytest.mark.asyncio
    async def test_broadcaster_forwards_evolution_events(
        self, bus, evolution_engine, exec_memory, cog_memory
    ):

        from agentic_os.api.dashboard import DashboardBroadcaster

        broadcaster = DashboardBroadcaster(bus=bus)
        await broadcaster.start()
        recv, send = broadcaster.add_client()
        received: list[str] = []

        async def reader():
            async for msg in recv:
                received.append(msg.get("topic", ""))
                if len(received) >= 1:
                    break

        try:
            ec = EvolutionController(
                bus=bus,
                evolution_engine=evolution_engine,
                exec_memory=exec_memory,
                cognitive_memory=cog_memory,
            )
            await ec.start()
            try:
                # Trigger readiness assessment which publishes evolution.readiness.updated
                await ec.manager.assess_readiness()
                import anyio

                with anyio.move_on_after(2.0):
                    await reader()
            finally:
                await ec.stop()
            assert any(t.startswith("evolution.") for t in received)
        finally:
            broadcaster.remove_client(send)
            await broadcaster.stop()


# ── Rollback Workflow ──────────────────────────────────────────────────


class TestRollbackWorkflow:
    @pytest.mark.asyncio
    async def test_full_rollback_lifecycle(self, bus):
        """Test: propose → validate → approve → apply → rollback."""
        mgr = EvolutionManager(bus=bus)
        await mgr.start()
        try:
            # Manually add a proposal
            proposal = ImprovementProposal(
                title="Test rollback",
                type=ImprovementType.PERFORMANCE_OPTIMIZATION,
                status=ImprovementStatus.VALIDATED,
                risk_score=0.1,
            )
            mgr.improvement_engine._proposals.append(proposal)

            # Apply
            result = await mgr.apply_improvement(proposal.id)
            assert result["applied"] is True
            assert result["proposal"]["status"] == "applied"

            # Rollback
            rollback = await mgr.rollback_improvement(proposal.id, reason="test")
            assert rollback["rolled_back"] is True
            assert rollback["proposal"]["status"] == "rolled_back"
        finally:
            await mgr.stop()


# ── Safety Failure Handling ────────────────────────────────────────────


class TestSafetyFailureHandling:
    @pytest.mark.asyncio
    async def test_rejected_proposal_not_scheduled(self, bus):
        """A proposal that fails safety validation should NOT be scheduled."""
        mgr = EvolutionManager(bus=bus)
        await mgr.start()
        try:
            # Create a proposal with risky patterns
            proposal = ImprovementProposal(
                title="Risky proposal",
                implementation_plan={"code": "os.system('rm -rf /')"},
                status=ImprovementStatus.PROPOSED,
            )
            # Directly validate it (bypassing generate_all dedup)
            proposal.status = ImprovementStatus.VALIDATING
            report = await mgr.safety_validator.validate(proposal)
            proposal.safety_validation = report.to_dict()

            # Should be rejected due to risky patterns
            assert report.approved is False
            assert report.overall_result == ValidationCheckResult.FAIL
            # Should NOT be in the scheduler queue
            assert len(mgr.scheduler.get_queue()) == 0
        finally:
            await mgr.stop()
