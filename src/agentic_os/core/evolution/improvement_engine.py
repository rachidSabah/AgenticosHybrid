"""Phase 17 — ImprovementEngine.

Converts Phase 15 EvolutionRecommendation objects (passive analysis)
into Phase 17 ImprovementProposal objects (actionable, with safety
validation, implementation plans, and rollback strategies).

The engine is a pure consumer of:
  - ecosystem.evolution_engine.EvolutionEngine (Phase 15)
  - cognitive.improvement_planner.ImprovementPlanner (Phase 12)
  - executive.memory.ExecutiveMemory (Phase 11)
  - cognitive.memory.CognitiveMemory (Phase 12)

It does NOT replace any of those — it reads their output and wraps
it in a safety-validated improvement lifecycle.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agentic_os.core.evolution.domain import (
    ImprovementPriority,
    ImprovementProposal,
    ImprovementStatus,
    ImprovementType,
)
from agentic_os.infrastructure.logging import get_logger

if TYPE_CHECKING:
    from agentic_os.core.cognitive.improvement_planner import ImprovementPlanner
    from agentic_os.core.cognitive.memory import CognitiveMemory
    from agentic_os.core.ecosystem.evolution_engine import EvolutionEngine
    from agentic_os.core.executive.memory import ExecutiveMemory

log = get_logger("evolution.improvement")


class ImprovementEngine:
    """Generates ImprovementProposal objects from existing analysis engines.

    Pulls recommendations from:
      1. Phase 15 EvolutionEngine (capability gaps, routing, collaboration, performance)
      2. Phase 12 ImprovementPlanner (cognitive improvement proposals)
      3. Phase 11 ExecutiveMemory (decision/reflection history)
    """

    def __init__(
        self,
        evolution_engine: EvolutionEngine | None = None,
        improvement_planner: ImprovementPlanner | None = None,
        exec_memory: ExecutiveMemory | None = None,
        cognitive_memory: CognitiveMemory | None = None,
    ) -> None:
        self._evolution = evolution_engine
        self._planner = improvement_planner
        self._exec_mem = exec_memory
        self._cog_mem = cognitive_memory
        self._proposals: list[ImprovementProposal] = []
        self._stats: dict[str, int] = {
            "total_generated": 0,
            "from_ecosystem": 0,
            "from_cognitive": 0,
            "from_executive": 0,
            "from_performance": 0,
        }

    # ── Dependency injection ───────────────────────────────────────

    def set_evolution_engine(self, engine: EvolutionEngine) -> None:
        self._evolution = engine

    def set_improvement_planner(self, planner: ImprovementPlanner) -> None:
        self._planner = planner

    def set_exec_memory(self, memory: ExecutiveMemory) -> None:
        self._exec_mem = memory

    def set_cognitive_memory(self, memory: CognitiveMemory) -> None:
        self._cog_mem = memory

    # ── Public API ──────────────────────────────────────────────────

    async def generate_all(self) -> list[ImprovementProposal]:
        """Generate improvement proposals from all sources."""
        proposals: list[ImprovementProposal] = []
        proposals.extend(await self._from_ecosystem())
        proposals.extend(await self._from_cognitive())
        proposals.extend(await self._from_executive())
        proposals.extend(await self._from_performance())

        # Store + deduplicate by title
        seen_titles: set[str] = {p.title for p in self._proposals}
        for p in proposals:
            if p.title not in seen_titles:
                self._proposals.append(p)
                seen_titles.add(p.title)
                self._stats["total_generated"] += 1

        # Cap stored proposals
        if len(self._proposals) > 500:
            self._proposals = self._proposals[-500:]

        log.info(
            "Generated improvement proposals",
            total=len(proposals),
            stored=len(self._proposals),
        )
        return proposals

    def list_proposals(
        self,
        status: ImprovementStatus | str | None = None,
        limit: int = 50,
    ) -> list[ImprovementProposal]:
        if status is None:
            return list(self._proposals[-limit:])
        if isinstance(status, str):
            try:
                status = ImprovementStatus(status)
            except ValueError:
                return []
        return [p for p in self._proposals[-limit:] if p.status == status]

    def get_proposal(self, proposal_id: str) -> ImprovementProposal | None:
        for p in self._proposals:
            if p.id == proposal_id:
                return p
        return None

    def update_proposal(self, proposal_id: str, **updates: Any) -> ImprovementProposal | None:
        proposal = self.get_proposal(proposal_id)
        if proposal is None:
            return None
        for key, value in updates.items():
            if hasattr(proposal, key):
                setattr(proposal, key, value)
        from datetime import UTC, datetime

        proposal.updated_at = datetime.now(UTC).isoformat()
        return proposal

    def remove_proposal(self, proposal_id: str) -> bool:
        before = len(self._proposals)
        self._proposals = [p for p in self._proposals if p.id != proposal_id]
        return len(self._proposals) < before

    def stats(self) -> dict[str, Any]:
        by_status: dict[str, int] = {s.value: 0 for s in ImprovementStatus}
        by_type: dict[str, int] = {t.value: 0 for t in ImprovementType}
        for p in self._proposals:
            by_status[p.status.value] = by_status.get(p.status.value, 0) + 1
            by_type[p.type.value] = by_type.get(p.type.value, 0) + 1
        return {
            **self._stats,
            "stored": len(self._proposals),
            "by_status": by_status,
            "by_type": by_type,
        }

    # ── Source: Phase 15 EvolutionEngine ───────────────────────────

    async def _from_ecosystem(self) -> list[ImprovementProposal]:
        """Convert Phase 15 EvolutionRecommendation → Phase 17 ImprovementProposal."""
        if self._evolution is None:
            return []
        proposals: list[ImprovementProposal] = []
        try:
            recs = self._evolution.list_recommendations(limit=50)
            for rec in recs:
                # Map Phase 15 recommendation types to Phase 17 improvement types
                imp_type = self._map_rec_type_to_imp_type(rec.type.value)
                priority = self._map_priority(rec.priority)
                proposal = ImprovementProposal(
                    type=imp_type,
                    title=rec.title,
                    description=rec.rationale,
                    rationale=rec.rationale,
                    priority=priority,
                    status=ImprovementStatus.PROPOSED,
                    source="ecosystem",
                    source_recommendation_id=rec.id,
                    target_capability=rec.target_id,
                    expected_impact=rec.expected_impact,
                    confidence=rec.confidence,
                    risk_score=max(0.0, 1.0 - rec.confidence),
                    implementation_plan={
                        "action": rec.action,
                        "evidence": rec.evidence,
                        "source": "ecosystem.evolution_engine",
                    },
                    evidence=rec.evidence,
                )
                proposals.append(proposal)
                self._stats["from_ecosystem"] += 1
        except Exception:
            log.exception("Failed to generate proposals from ecosystem engine")
        return proposals

    def _map_rec_type_to_imp_type(self, rec_type: str) -> ImprovementType:
        """Map Phase 15 RecommendationType → Phase 17 ImprovementType."""
        mapping = {
            "recommended_capability": ImprovementType.CAPABILITY_EXPANSION,
            "recommended_routing": ImprovementType.ROUTING_OPTIMIZATION,
            "recommended_collaboration": ImprovementType.NEW_AGENT,
            "recommended_optimization": ImprovementType.PERFORMANCE_OPTIMIZATION,
        }
        return mapping.get(rec_type, ImprovementType.PERFORMANCE_OPTIMIZATION)

    def _map_priority(self, score: float) -> ImprovementPriority:
        if score >= 0.8:
            return ImprovementPriority.CRITICAL
        elif score >= 0.6:
            return ImprovementPriority.HIGH
        elif score >= 0.4:
            return ImprovementPriority.MEDIUM
        elif score >= 0.2:
            return ImprovementPriority.LOW
        return ImprovementPriority.BACKGROUND

    # ── Source: Phase 12 ImprovementPlanner ────────────────────────

    async def _from_cognitive(self) -> list[ImprovementProposal]:
        """Convert Phase 12 ImprovementProposal → Phase 17 ImprovementProposal."""
        if self._planner is None:
            return []
        proposals: list[ImprovementProposal] = []
        try:
            cognitive_proposals = self._planner.get_history(limit=50)
            for cp in cognitive_proposals:
                proposal = ImprovementProposal(
                    type=ImprovementType.PERFORMANCE_OPTIMIZATION,
                    title=str(cp.get("title", "Cognitive improvement")),
                    description=str(cp.get("description", "")),
                    rationale=str(cp.get("rationale", "")),
                    priority=ImprovementPriority.MEDIUM,
                    status=ImprovementStatus.PROPOSED,
                    source="cognitive",
                    expected_impact=float(cp.get("expected_impact", 0.5)),
                    confidence=float(cp.get("confidence", 0.5)),
                    implementation_plan=dict(cp),
                )
                proposals.append(proposal)
                self._stats["from_cognitive"] += 1
        except Exception:
            log.exception("Failed to generate proposals from cognitive planner")
        return proposals

    # ── Source: Phase 11 ExecutiveMemory ───────────────────────────

    async def _from_executive(self) -> list[ImprovementProposal]:
        """Generate proposals from executive reflections + decisions."""
        if self._exec_mem is None:
            return []
        proposals: list[ImprovementProposal] = []
        try:
            reflections = await self._safe_await(self._exec_mem.list_reflections(limit=50))
            for ref in reflections:
                # Each reflection's capability_gaps + improvements → proposals
                for gap in ref.get("capability_gaps", []) or []:
                    proposal = ImprovementProposal(
                        type=ImprovementType.CAPABILITY_EXPANSION,
                        title=f"Fill capability gap: {gap}",
                        description=(
                            f"Reflection {ref.get('id', '?')} identified missing capability: {gap}"
                        ),
                        rationale=str(ref.get("summary", "")),
                        priority=ImprovementPriority.HIGH,
                        status=ImprovementStatus.PROPOSED,
                        source="executive",
                        target_capability=str(gap),
                        expected_impact=0.4,
                        confidence=0.6,
                        implementation_plan={
                            "capability": gap,
                            "reflection_id": ref.get("id", ""),
                        },
                    )
                    proposals.append(proposal)
                    self._stats["from_executive"] += 1

                for improvement in ref.get("improvements", []) or []:
                    proposal = ImprovementProposal(
                        type=ImprovementType.PERFORMANCE_OPTIMIZATION,
                        title=f"Apply: {improvement}",
                        description=f"Reflection {ref.get('id', '?')} suggested: {improvement}",
                        rationale=str(ref.get("summary", "")),
                        priority=ImprovementPriority.MEDIUM,
                        status=ImprovementStatus.PROPOSED,
                        source="executive",
                        expected_impact=0.3,
                        confidence=0.5,
                        implementation_plan={
                            "improvement": improvement,
                            "reflection_id": ref.get("id", ""),
                        },
                    )
                    proposals.append(proposal)
                    self._stats["from_executive"] += 1
        except Exception:
            log.exception("Failed to generate proposals from executive memory")
        return proposals

    # ── Source: Performance metrics ────────────────────────────────

    async def _from_performance(self) -> list[ImprovementProposal]:
        """Generate proposals from performance analysis or system baseline."""
        proposals: list[ImprovementProposal] = []
        if self._cog_mem is not None:
            try:
                evaluations = await self._safe_await(self._cog_mem.list_evaluations(limit=20))
                for ev in evaluations:
                    score = float(ev.get("score", 1.0))
                    if score < 0.5:
                        proposal = ImprovementProposal(
                            type=ImprovementType.PERFORMANCE_OPTIMIZATION,
                            title=f"Address low evaluation score: {score:.2f}",
                            description=str(ev.get("summary", "Low evaluation score detected")),
                            rationale=f"Evaluation score {score:.2f} below threshold 0.5",
                            priority=ImprovementPriority.HIGH,
                            status=ImprovementStatus.PROPOSED,
                            source="performance",
                            expected_impact=0.5,
                            confidence=0.7,
                            risk_score=0.2,
                            implementation_plan={
                                "evaluation_id": ev.get("id", ""),
                                "current_score": score,
                                "target_score": 0.8,
                            },
                        )
                        proposals.append(proposal)
                        self._stats["from_performance"] += 1
            except Exception:
                log.exception("Failed to generate proposals from performance metrics")

        # Baseline proposal when system has zero active proposals so
        # Evolution Dashboard is populated
        if not proposals and len(self._proposals) == 0:
            baseline = ImprovementProposal(
                type=ImprovementType.PERFORMANCE_OPTIMIZATION,
                title="System Routing & Latency Optimization",
                description=(
                    "Automated baseline optimization check for provider dispatch "
                    "queues and response latency."
                ),
                rationale="System baseline health inspection initialized.",
                priority=ImprovementPriority.MEDIUM,
                status=ImprovementStatus.PROPOSED,
                source="performance",
                expected_impact=0.6,
                confidence=0.8,
                risk_score=0.1,
                implementation_plan={
                    "action": "optimize_provider_routing",
                    "target_latency_ms": 1500,
                },
            )
            proposals.append(baseline)
            self._stats["from_performance"] += 1

        return proposals

    # ── Helpers ─────────────────────────────────────────────────────

    async def _safe_await(self, coro_or_result: Any) -> Any:
        """Await if it's a coroutine, otherwise return directly."""
        if hasattr(coro_or_result, "__await__"):
            return await coro_or_result
        return coro_or_result
