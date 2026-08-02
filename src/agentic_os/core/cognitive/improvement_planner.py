"""Improvement Planner — generates autonomous improvement proposals.

Automatically generates: improvement proposals, optimization tasks,
maintenance tasks, technical debt tasks, capability upgrades.
Each proposal becomes a Goal automatically via the existing GoalManager.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agentic_os.core.cognitive.domain import ImprovementProposal
from agentic_os.infrastructure.logging import get_logger

if TYPE_CHECKING:
    from agentic_os.core.cognitive.evaluation_engine import EvaluationEngine
    from agentic_os.core.cognitive.experience_replay import ExperienceReplay
    from agentic_os.core.executive.goal_manager import GoalManager

log = get_logger("cognitive.improvement")


class ImprovementPlanner:
    """Generates improvement proposals from evaluation + experience data."""

    def __init__(
        self,
        evaluation_engine: EvaluationEngine | None = None,
        experience_replay: ExperienceReplay | None = None,
        goal_manager: GoalManager | None = None,
    ) -> None:
        self._eval = evaluation_engine
        self._exp = experience_replay
        self._goals = goal_manager
        self._proposals: list[ImprovementProposal] = []

    def set_engines(
        self, eval_eng: EvaluationEngine, exp_replay: ExperienceReplay, goals: GoalManager
    ) -> None:
        self._eval = eval_eng
        self._exp = exp_replay
        self._goals = goals

    async def generate(self) -> list[ImprovementProposal]:
        """Generate improvement proposals from current evaluation + experience."""
        proposals: list[ImprovementProposal] = []

        # Use evaluation scores
        if self._eval is not None:
            latest = self._eval.get_latest()
            if latest is not None:
                # Low decision quality → optimization task
                if latest.get("decision_quality", 1.0) < 0.7:
                    dq = latest["decision_quality"]
                    proposals.append(
                        ImprovementProposal(
                            title="Optimize decision scoring weights",
                            description=(f"Decision quality is {dq:.0%} — below 70% threshold"),
                            proposal_type="optimization",
                            priority="high",
                            estimated_impact=0.2,
                            estimated_effort=0.5,
                            rationale="Low decision quality indicates suboptimal scoring",
                        )
                    )
                # Low routing quality → routing improvement
                if latest.get("routing_quality", 1.0) < 0.7:
                    rq = latest["routing_quality"]
                    proposals.append(
                        ImprovementProposal(
                            title="Improve routing algorithm",
                            description=(f"Routing quality is {rq:.0%} — review routing decisions"),
                            proposal_type="capability_upgrade",
                            priority="high",
                            estimated_impact=0.15,
                            estimated_effort=0.3,
                            rationale=(
                                "Low routing quality suggests better runtime selection needed"
                            ),
                        )
                    )
                # Low runtime utilization → maintenance
                if latest.get("runtime_utilization", 1.0) < 0.3:
                    proposals.append(
                        ImprovementProposal(
                            title="Increase runtime utilization",
                            description=(
                                "Runtime utilization is low — consider discovering more runtimes"
                            ),
                            proposal_type="maintenance",
                            priority="normal",
                            estimated_impact=0.1,
                            estimated_effort=0.2,
                            rationale="Idle runtimes waste capacity",
                        )
                    )

        # Use experience replay findings
        if self._exp is not None:
            for record in self._exp.get_history(limit=10):
                for bottleneck in record.get("capability_bottlenecks", []):
                    proposals.append(
                        ImprovementProposal(
                            title=f"Address capability bottleneck: {bottleneck}",
                            description=f"Experience replay identified bottleneck: {bottleneck}",
                            proposal_type="capability_upgrade",
                            priority="normal",
                            estimated_impact=0.1,
                            estimated_effort=0.4,
                            rationale=f"Replay analysis: {record.get('summary', '')}",
                        )
                    )
                for opt in record.get("optimization_opportunities", []):
                    proposals.append(
                        ImprovementProposal(
                            title=f"Optimization: {opt}",
                            description=f"Experience replay found opportunity: {opt}",
                            proposal_type="optimization",
                            priority="low",
                            estimated_impact=0.05,
                            estimated_effort=0.2,
                            rationale=f"Replay analysis: {record.get('summary', '')}",
                        )
                    )

        # Create goals for each proposal
        for p in proposals:
            self._proposals.append(p)
            if len(self._proposals) > 200:
                self._proposals = self._proposals[-200:]
            if self._goals is not None:
                try:
                    await self._goals.create_goal(
                        title=p.title,
                        description=p.description,
                    )
                except Exception:
                    log.exception("Failed to create goal from proposal %s", p.id)

        return proposals

    def get_history(self, limit: int = 50) -> list[dict[str, Any]]:
        return [p.to_dict() for p in self._proposals[-limit:]]
