"""Phase 17 — EvolutionManager.

Top-level coordinator for autonomous agent evolution. Owns all Phase 17
sub-components and orchestrates the improvement pipeline:

  1. ImprovementEngine generates proposals (from Phase 15/12/11 sources)
  2. SafetyValidator validates each proposal (6 safety checks)
  3. AutonomousReviewer reviews for quality + completeness
  4. RegressionGuard predicts regression risk
  5. ImprovementScheduler schedules validated proposals
  6. CodeGenerationPlanner creates generation plans
  7. KnowledgeSynthesizer extracts insights from history

The manager is a pure consumer of existing infrastructure — it does
NOT modify production code, NOT replace existing engines, NOT duplicate
Phase 15 EvolutionEngine.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from agentic_os.core.evolution.advisors import (
    PerformanceOptimizer,
    RefactoringAdvisor,
)
from agentic_os.core.evolution.capability_expansion_engine import (
    CapabilityExpansionEngine,
)
from agentic_os.core.evolution.code_generation_planner import CodeGenerationPlanner
from agentic_os.core.evolution.domain import (
    EvolutionStatistics,
    ImprovementStatus,
    SystemReadiness,
    SystemReadinessLevel,
)
from agentic_os.core.evolution.improvement_engine import ImprovementEngine
from agentic_os.core.evolution.regression_guard import RegressionGuard
from agentic_os.core.evolution.review_synthesis import (
    AutonomousReviewer,
    KnowledgeSynthesizer,
)
from agentic_os.core.evolution.safety_validator import SafetyValidator
from agentic_os.core.evolution.scheduler import ImprovementScheduler
from agentic_os.infrastructure.logging import get_logger

if TYPE_CHECKING:
    from agentic_os.core.cognitive.improvement_planner import ImprovementPlanner
    from agentic_os.core.cognitive.memory import CognitiveMemory
    from agentic_os.core.ecosystem.evolution_engine import EvolutionEngine
    from agentic_os.core.executive.memory import ExecutiveMemory
    from agentic_os.ports.event_bus import EventBus

log = get_logger("evolution.manager")


class EvolutionManager:
    """Top-level coordinator for the evolution layer."""

    def __init__(
        self,
        bus: EventBus,
        evolution_engine: EvolutionEngine | None = None,
        improvement_planner: ImprovementPlanner | None = None,
        exec_memory: ExecutiveMemory | None = None,
        cognitive_memory: CognitiveMemory | None = None,
    ) -> None:
        self._bus = bus
        self._started = False

        # Sub-components
        self._regression_guard = RegressionGuard()
        self._safety_validator = SafetyValidator(regression_guard=self._regression_guard)
        self._improvement_engine = ImprovementEngine(
            evolution_engine=evolution_engine,
            improvement_planner=improvement_planner,
            exec_memory=exec_memory,
            cognitive_memory=cognitive_memory,
        )
        self._reviewer = AutonomousReviewer()
        self._scheduler = ImprovementScheduler()
        self._code_planner = CodeGenerationPlanner()
        self._knowledge_synthesizer = KnowledgeSynthesizer()
        self._capability_expansion = CapabilityExpansionEngine()
        self._refactoring_advisor = RefactoringAdvisor()
        self._performance_optimizer = PerformanceOptimizer()

        # State
        self._statistics = EvolutionStatistics()
        self._readiness = SystemReadiness()
        self._analysis_count = 0

    # ── Properties (read-only views) ───────────────────────────────

    @property
    def improvement_engine(self) -> ImprovementEngine:
        return self._improvement_engine

    @property
    def safety_validator(self) -> SafetyValidator:
        return self._safety_validator

    @property
    def regression_guard(self) -> RegressionGuard:
        return self._regression_guard

    @property
    def reviewer(self) -> AutonomousReviewer:
        return self._reviewer

    @property
    def scheduler(self) -> ImprovementScheduler:
        return self._scheduler

    @property
    def code_planner(self) -> CodeGenerationPlanner:
        return self._code_planner

    @property
    def knowledge_synthesizer(self) -> KnowledgeSynthesizer:
        return self._knowledge_synthesizer

    @property
    def capability_expansion(self) -> CapabilityExpansionEngine:
        return self._capability_expansion

    @property
    def refactoring_advisor(self) -> RefactoringAdvisor:
        return self._refactoring_advisor

    @property
    def performance_optimizer(self) -> PerformanceOptimizer:
        return self._performance_optimizer

    @property
    def statistics(self) -> EvolutionStatistics:
        return self._statistics

    @property
    def readiness(self) -> SystemReadiness:
        return self._readiness

    @property
    def started(self) -> bool:
        return self._started

    # ── Lifecycle ──────────────────────────────────────────────────

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        await self._publish("evolution.started", {"timestamp": self._now_iso()})
        log.info("EvolutionManager started")

    async def stop(self) -> None:
        self._started = False
        await self._publish("evolution.stopped", {"timestamp": self._now_iso()})
        log.info("EvolutionManager stopped")

    # ── Public operations ───────────────────────────────────────────

    async def analyze(self) -> dict[str, Any]:
        """Run full analysis: generate proposals + validate + review."""
        self._analysis_count += 1

        # 1. Generate proposals from all sources
        proposals = await self._improvement_engine.generate_all()

        # 2. Validate each new proposal
        validated = 0
        rejected = 0
        for proposal in proposals:
            if proposal.status != ImprovementStatus.PROPOSED:
                continue
            proposal.status = ImprovementStatus.VALIDATING
            report = await self._safety_validator.validate(proposal)
            proposal.safety_validation = report.to_dict()

            if report.approved:
                proposal.status = ImprovementStatus.VALIDATED
                # 3. Review for quality
                review = await self._reviewer.review(proposal)
                if review["decision"] == "approved":
                    proposal.status = ImprovementStatus.APPROVED
                    # 4. Enqueue for scheduling
                    self._scheduler.enqueue(proposal)
                    validated += 1
                else:
                    proposal.status = ImprovementStatus.REJECTED
                    rejected += 1
            else:
                proposal.status = ImprovementStatus.REJECTED
                rejected += 1

        await self._publish(
            "evolution.analysis.completed",
            {
                "proposals_generated": len(proposals),
                "validated": validated,
                "rejected": rejected,
                "analysis_count": self._analysis_count,
            },
        )

        # Update statistics
        await self._update_statistics()

        return {
            "proposals_generated": len(proposals),
            "validated": validated,
            "rejected": rejected,
            "queue_size": len(self._scheduler.get_queue()),
        }

    async def schedule_next(self) -> dict[str, Any]:
        """Pick the next improvement to execute."""
        proposal = self._scheduler.schedule_next()
        if proposal is None:
            return {"scheduled": False, "reason": "queue_empty_or_cooldown"}

        # Generate a code plan if applicable
        plan = await self._code_planner.plan_from_proposal(proposal)
        await self._publish(
            "evolution.improvement.scheduled",
            {
                "proposal_id": proposal.id,
                "title": proposal.title,
                "priority": proposal.priority.value,
                "plan_id": plan.id if plan else None,
            },
        )
        return {
            "scheduled": True,
            "proposal": proposal.to_dict(),
            "plan": plan.to_dict() if plan else None,
        }

    async def apply_improvement(self, proposal_id: str) -> dict[str, Any]:
        """Mark an improvement as applied (execution simulation)."""
        proposal = self._improvement_engine.get_proposal(proposal_id)
        if proposal is None:
            return {"applied": False, "reason": "not_found"}

        self._scheduler.mark_executing(proposal_id)
        # In Phase 17, "applying" means the plan is approved for rollout
        # (we never directly overwrite production code)
        self._scheduler.mark_applied(proposal_id)
        proposal.status = ImprovementStatus.APPLIED
        proposal.applied_at = self._now_iso()

        await self._publish(
            "evolution.improvement.applied",
            {"proposal_id": proposal_id, "title": proposal.title},
        )
        await self._update_statistics()
        return {"applied": True, "proposal": proposal.to_dict()}

    async def rollback_improvement(self, proposal_id: str, reason: str = "") -> dict[str, Any]:
        """Roll back an applied improvement."""
        proposal = self._improvement_engine.get_proposal(proposal_id)
        if proposal is None:
            return {"rolled_back": False, "reason": "not_found"}

        self._scheduler.mark_rolled_back(proposal_id)
        proposal.status = ImprovementStatus.ROLLED_BACK
        proposal.rolled_back_at = self._now_iso()

        await self._publish(
            "evolution.improvement.rolled_back",
            {"proposal_id": proposal_id, "reason": reason, "title": proposal.title},
        )
        await self._update_statistics()
        return {"rolled_back": True, "proposal": proposal.to_dict()}

    async def synthesize_knowledge(
        self, topic: str, sources: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Synthesize knowledge from sources."""
        synthesis = await self._knowledge_synthesizer.synthesize(topic, sources)
        await self._publish(
            "evolution.knowledge.synthesized",
            synthesis.to_dict(),
        )
        return synthesis.to_dict()

    async def assess_readiness(self) -> dict[str, Any]:
        """Assess system readiness for autonomous evolution."""
        safety_stats = self._safety_validator.stats()
        sched_stats = self._scheduler.stats()

        # Compute readiness score
        pass_rate = safety_stats.get("pass_rate", 1.0)
        active = sched_stats.get("active", 0)
        queue = sched_stats.get("queue_size", 0)

        readiness_score = (
            pass_rate * 0.5
            + (1.0 - min(active / 10.0, 1.0)) * 0.3
            + (1.0 - min(queue / 50.0, 1.0)) * 0.2
        )

        if readiness_score < 0.3:
            level = SystemReadinessLevel.BLOCKED
        elif readiness_score < 0.6:
            level = SystemReadinessLevel.CAUTIOUS
        elif active > 0:
            level = SystemReadinessLevel.OPTIMIZING
        else:
            level = SystemReadinessLevel.READY

        self._readiness = SystemReadiness(
            level=level,
            readiness_score=readiness_score,
            active_improvements=active,
            pending_validations=queue,
            regression_risk=1.0 - pass_rate,
            issues=([f"Low safety pass rate: {pass_rate:.0%}"] if pass_rate < 0.7 else []),
            updated_at=self._now_iso(),
        )

        await self._publish("evolution.readiness.updated", self._readiness.to_dict())
        return self._readiness.to_dict()

    # ── Snapshot ────────────────────────────────────────────────────

    def dashboard(self) -> dict[str, Any]:
        """Combined snapshot for /api/evolution/dashboard."""
        return {
            "statistics": self._statistics.to_dict(),
            "readiness": self._readiness.to_dict(),
            "improvement_engine": self._improvement_engine.stats(),
            "safety_validator": self._safety_validator.stats(),
            "regression_guard": self._regression_guard.stats(),
            "reviewer": self._reviewer.stats(),
            "scheduler": self._scheduler.stats(),
            "code_planner": self._code_planner.stats(),
            "knowledge_synthesizer": self._knowledge_synthesizer.stats(),
            "analysis_count": self._analysis_count,
        }

    def status(self) -> dict[str, Any]:
        return {
            "started": self._started,
            "analysis_count": self._analysis_count,
            "queue_size": len(self._scheduler.get_queue()),
            "active_improvements": len(self._scheduler.get_scheduled()),
        }

    # ── Internals ───────────────────────────────────────────────────

    async def _update_statistics(self) -> None:
        stats = EvolutionStatistics()
        proposals = self._improvement_engine.list_proposals(limit=500)
        stats.total_proposals = len(proposals)
        for p in proposals:
            if p.status == ImprovementStatus.PROPOSED:
                stats.pending += 1
            elif p.status == ImprovementStatus.VALIDATED:
                stats.validated += 1
            elif p.status == ImprovementStatus.APPROVED:
                stats.approved += 1
            elif p.status == ImprovementStatus.APPLIED:
                stats.applied += 1
            elif p.status == ImprovementStatus.REJECTED:
                stats.rejected += 1
            elif p.status == ImprovementStatus.ROLLED_BACK:
                stats.rolled_back += 1
        stats.generation_plans = len(self._code_planner.list_plans())
        stats.knowledge_syntheses = self._knowledge_synthesizer.stats()["total_syntheses"]
        safety_stats = self._safety_validator.stats()
        stats.safety_pass_rate = safety_stats.get("pass_rate", 0.0)
        if proposals:
            stats.average_impact = sum(p.expected_impact for p in proposals) / len(proposals)
            stats.average_risk = sum(p.risk_score for p in proposals) / len(proposals)
        stats.last_updated = self._now_iso()
        self._statistics = stats
        await self._publish("evolution.statistics.updated", stats.to_dict())

    async def _publish(self, topic: str, payload: dict[str, Any]) -> None:
        try:
            from agentic_os.domain.events import EventEnvelope

            await self._bus.publish(
                EventEnvelope(
                    type=topic,
                    source="evolution.manager",
                    topic=topic,
                    payload=payload,
                )
            )
        except Exception:
            log.exception("Failed to publish %s", topic)

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(UTC).isoformat()
