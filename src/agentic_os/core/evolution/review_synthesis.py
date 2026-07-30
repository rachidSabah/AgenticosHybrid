"""Phase 17 — AutonomousReviewer + KnowledgeSynthesizer.

AutonomousReviewer: reviews improvement proposals for quality + completeness.
KnowledgeSynthesizer: extracts patterns + insights from historical data.
"""

from __future__ import annotations

from typing import Any

from agentic_os.core.evolution.domain import (
    ImprovementProposal,
    KnowledgeSynthesis,
)
from agentic_os.infrastructure.logging import get_logger

log = get_logger("evolution.review_synthesis")


class AutonomousReviewer:
    """Reviews improvement proposals for quality + completeness."""

    def __init__(self) -> None:
        self._reviews: list[dict[str, Any]] = []
        self._stats: dict[str, int] = {
            "total_reviews": 0,
            "approved": 0,
            "needs_revision": 0,
            "rejected": 0,
        }

    async def review(self, proposal: ImprovementProposal) -> dict[str, Any]:
        """Review a proposal for quality + completeness."""
        self._stats["total_reviews"] += 1

        issues: list[str] = []
        strengths: list[str] = []
        score = 0.0

        # Check completeness
        if not proposal.title:
            issues.append("Missing title")
        else:
            score += 0.1
            strengths.append("Clear title")

        if not proposal.description:
            issues.append("Missing description")
        else:
            score += 0.1
            strengths.append("Has description")

        if not proposal.rationale:
            issues.append("Missing rationale")
        else:
            score += 0.15
            strengths.append("Has rationale")

        if not proposal.implementation_plan:
            issues.append("Missing implementation plan")
        else:
            score += 0.2
            strengths.append("Has implementation plan")

        if not proposal.rollback_plan and proposal.implementation_plan:
            issues.append("Missing rollback plan")
        else:
            score += 0.15
            strengths.append("Has rollback plan")

        # Check risk vs impact
        if proposal.risk_score > 0.7:
            issues.append(f"High risk score: {proposal.risk_score:.2f}")
            score -= 0.1
        elif proposal.risk_score < 0.3:
            score += 0.1
            strengths.append("Low risk")

        if proposal.expected_impact > 0.5:
            score += 0.1
            strengths.append("High expected impact")
        elif proposal.expected_impact < 0.2:
            issues.append("Low expected impact")

        if proposal.confidence > 0.7:
            score += 0.1
            strengths.append("High confidence")

        # Clamp score
        score = max(0.0, min(1.0, score))

        # Decision
        if score >= 0.7 and len(issues) <= 1:
            decision = "approved"
            self._stats["approved"] += 1
        elif score >= 0.4:
            decision = "needs_revision"
            self._stats["needs_revision"] += 1
        else:
            decision = "rejected"
            self._stats["rejected"] += 1

        review = {
            "proposal_id": proposal.id,
            "score": round(score, 3),
            "decision": decision,
            "issues": issues,
            "strengths": strengths,
            "reviewed_at": __import__("datetime")
            .datetime.now(__import__("datetime").UTC)
            .isoformat(),
        }
        self._reviews.append(review)
        if len(self._reviews) > 200:
            self._reviews = self._reviews[-200:]

        log.info(
            "Proposal reviewed",
            proposal_id=proposal.id,
            decision=decision,
            score=score,
        )
        return review

    def list_reviews(self, limit: int = 50) -> list[dict[str, Any]]:
        return list(self._reviews[-limit:])

    def stats(self) -> dict[str, Any]:
        return dict(self._stats)


class KnowledgeSynthesizer:
    """Extracts patterns + insights from historical analysis data."""

    def __init__(self) -> None:
        self._syntheses: list[KnowledgeSynthesis] = []
        self._stats: dict[str, int] = {"total_syntheses": 0}

    async def synthesize(
        self,
        topic: str,
        sources: list[dict[str, Any]],
    ) -> KnowledgeSynthesis:
        """Synthesize knowledge from multiple sources."""
        self._stats["total_syntheses"] += 1

        # Extract key insights
        insights: list[str] = []
        patterns: list[dict[str, Any]] = []
        recommendations: list[str] = []
        all_text = ""

        for source in sources:
            source_type = source.get("type", "unknown")
            data = source.get("data", {})
            text = str(data)
            all_text += " " + text

            # Extract common patterns
            if source_type == "reflection":
                for gap in data.get("capability_gaps", []) or []:
                    if gap not in insights:
                        insights.append(f"Capability gap: {gap}")
                for imp in data.get("improvements", []) or []:
                    if imp not in recommendations:
                        recommendations.append(imp)
            elif source_type == "decision":
                selected = data.get("selected_runtime", "")
                if selected:
                    patterns.append(
                        {
                            "type": "preferred_runtime",
                            "runtime": selected,
                            "confidence": data.get("confidence", 0),
                        }
                    )
            elif source_type == "evaluation":
                score = float(data.get("score", 1.0))
                if score < 0.5:
                    insights.append(f"Low evaluation score detected: {score:.2f}")

        # Deduplicate
        insights = list(dict.fromkeys(insights))[:10]
        recommendations = list(dict.fromkeys(recommendations))[:10]

        # Confidence based on source count + diversity
        source_count = len(sources)
        confidence = min(1.0, source_count / 10.0)

        synthesis = KnowledgeSynthesis(
            topic=topic,
            summary=f"Synthesized from {source_count} sources on '{topic}'",
            key_insights=insights,
            patterns=patterns,
            recommendations=recommendations,
            confidence=confidence,
            sources=[s.get("type", "unknown") for s in sources],
        )

        self._syntheses.append(synthesis)
        if len(self._syntheses) > 100:
            self._syntheses = self._syntheses[-100:]

        log.info(
            "Knowledge synthesized",
            topic=topic,
            insights=len(insights),
            patterns=len(patterns),
            confidence=confidence,
        )
        return synthesis

    def list_syntheses(self, limit: int = 50) -> list[KnowledgeSynthesis]:
        return list(self._syntheses[-limit:])

    def stats(self) -> dict[str, Any]:
        return dict(self._stats)
