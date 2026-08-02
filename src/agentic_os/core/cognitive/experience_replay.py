"""Experience Replay — analyzes completed missions for patterns.

Replays completed missions and generates:
  - patterns, common failures, optimization opportunities
  - routing improvements, capability bottlenecks
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agentic_os.core.cognitive.domain import ExperienceRecord
from agentic_os.infrastructure.logging import get_logger

if TYPE_CHECKING:
    from agentic_os.core.cognitive.memory import CognitiveMemory

log = get_logger("cognitive.experience")


class ExperienceReplay:
    """Replays completed missions and extracts patterns."""

    def __init__(self, cognitive_memory: CognitiveMemory | None = None) -> None:
        self._mem = cognitive_memory
        self._records: list[ExperienceRecord] = []

    def set_memory(self, mem: CognitiveMemory) -> None:
        self._mem = mem

    async def replay(self, mission_id: str = "", goal_id: str = "") -> ExperienceRecord:
        """Replay a completed mission and generate an experience record."""
        patterns: list[str] = []
        common_failures: list[str] = []
        optimization_opportunities: list[str] = []
        routing_improvements: list[str] = []
        capability_bottlenecks: list[str] = []

        # Analyze reflections if available
        if self._mem is not None:
            try:
                reflections = await self._mem.list_reflections(limit=20)
                for r in reflections:
                    for sf in r.get("success_factors", []):
                        if sf not in patterns:
                            patterns.append(sf)
                    for f in r.get("failures", []):
                        if f not in common_failures:
                            common_failures.append(f)
                    for ri in r.get("routing_issues", []):
                        if ri not in routing_improvements:
                            routing_improvements.append(ri)
                    for cg in r.get("capability_gaps", []):
                        if cg not in capability_bottlenecks:
                            capability_bottlenecks.append(cg)
                    for imp in r.get("improvements", []):
                        if imp not in optimization_opportunities:
                            optimization_opportunities.append(imp)
            except Exception:
                log.exception("Failed to read reflections for replay")

        # Generate summary
        summary_parts = [f"Analyzed {len(patterns)} patterns"]
        if common_failures:
            summary_parts.append(f"{len(common_failures)} common failures")
        if capability_bottlenecks:
            summary_parts.append(f"{len(capability_bottlenecks)} capability bottlenecks")
        summary = "; ".join(summary_parts) + "."

        record = ExperienceRecord(
            mission_id=mission_id,
            goal_id=goal_id,
            patterns=patterns,
            common_failures=common_failures,
            optimization_opportunities=optimization_opportunities,
            routing_improvements=routing_improvements,
            capability_bottlenecks=capability_bottlenecks,
            summary=summary,
        )
        self._records.append(record)
        if len(self._records) > 200:
            self._records = self._records[-200:]
        if self._mem is not None:
            try:
                await self._mem.store_experience(record.id, record.to_dict())
            except Exception:
                log.exception("Failed to store experience record")
        return record

    def get_history(self, limit: int = 50) -> list[dict[str, Any]]:
        return [r.to_dict() for r in self._records[-limit:]]
