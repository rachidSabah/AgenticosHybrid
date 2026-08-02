"""Phase 17 — CapabilityExpansionEngine.

Analyzes capability gaps and proposes new capabilities to discover or
construct. Builds on Phase 15's EvolutionEngine.analyze_capability_gaps
but adds construction planning.
"""

from __future__ import annotations

from typing import Any

from agentic_os.core.evolution.domain import (
    ImprovementPriority,
    ImprovementProposal,
    ImprovementType,
)
from agentic_os.infrastructure.logging import get_logger

log = get_logger("evolution.capability_expansion")


class CapabilityExpansionEngine:
    """Proposes new capabilities based on gap analysis."""

    def __init__(self) -> None:
        self._proposals: list[ImprovementProposal] = []
        self._known_gaps: dict[str, dict[str, Any]] = {}

    async def analyze_gaps(
        self,
        required_caps: list[str],
        available_caps: list[str],
    ) -> list[ImprovementProposal]:
        """Find capability gaps and propose expansions."""
        proposals: list[ImprovementProposal] = []
        available_set = set(available_caps)
        for cap in required_caps:
            if cap not in available_set:
                proposal = ImprovementProposal(
                    type=ImprovementType.CAPABILITY_EXPANSION,
                    title=f"Acquire capability: {cap}",
                    description=(
                        f"Capability '{cap}' is required but not available. "
                        f"Recommend discovering a provider or constructing a new adapter."
                    ),
                    rationale=f"Capability gap: {cap}",
                    priority=ImprovementPriority.HIGH,
                    target_capability=cap,
                    expected_impact=0.5,
                    confidence=0.8,
                    risk_score=0.2,
                    implementation_plan={
                        "action": "discover_or_construct",
                        "capability": cap,
                        "strategy": "discovery_first",
                    },
                )
                proposals.append(proposal)
                self._known_gaps[cap] = {
                    "required": True,
                    "available": False,
                    "proposal_id": proposal.id,
                }
        self._proposals.extend(proposals)
        return proposals

    def list_gaps(self) -> dict[str, dict[str, Any]]:
        return dict(self._known_gaps)

    def list_proposals(self) -> list[ImprovementProposal]:
        return list(self._proposals)
