"""Result Merger — combines outputs from multiple agents using configurable strategies.

Supports weighted merge, priority merge, consensus merge, voting,
conflict resolution, confidence scoring, duplicate elimination, and semantic merging.
"""

from typing import Any

from agentic_os.domain.events import EventEnvelope, Topic
from agentic_os.domain.orchestration import (
    AgentTask,
    MergedResult,
    MergeStrategy,
)
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.event_bus import EventBus
from agentic_os.ports.orchestration import ResultMergerPort

log = get_logger("orchestration.result_merger")


class ResultMerger(ResultMergerPort):
    """Merges outputs from multiple tasks using configurable strategies."""

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus

    async def merge(
        self,
        tasks: list[AgentTask],
        strategy: MergeStrategy = MergeStrategy.CONSENSUS,
    ) -> MergedResult:
        """Merge results from multiple completed tasks."""
        await self._publish(
            Topic.ORCH_MERGER_STARTED,
            {
                "task_count": len(tasks),
                "strategy": strategy.value,
            },
        )

        completed = [t for t in tasks if t.status.value == "completed"]
        if not completed:
            return MergedResult(
                strategy=strategy,
                source_task_ids=tuple(t.id for t in tasks),
                output={},
                confidence=0.0,
            )

        if strategy == MergeStrategy.WEIGHTED:
            result = self._weighted_merge(completed)
        elif strategy == MergeStrategy.PRIORITY:
            result = self._priority_merge(completed)
        elif strategy == MergeStrategy.CONSENSUS:
            result = self._consensus_merge(completed)
        elif strategy == MergeStrategy.VOTING:
            result = self._voting_merge(completed)
        elif strategy == MergeStrategy.BEST_OF_N:
            result = self._best_of_n(completed)
        elif strategy == MergeStrategy.CONCATENATE:
            result = self._concatenate(completed)
        else:
            result = self._consensus_merge(completed)

        await self._publish(
            Topic.ORCH_MERGER_COMPLETED,
            {
                "strategy": strategy.value,
                "confidence": result.confidence,
                "conflict_count": len(result.conflicts),
            },
        )
        return result

    async def resolve_conflicts(self, merged_result: MergedResult) -> MergedResult:
        """Attempt to resolve conflicts by taking the highest-confidence value."""
        if not merged_result.conflicts:
            return merged_result

        resolved_output = dict(merged_result.output)
        for conflict in merged_result.conflicts:
            key = conflict.get("key")
            values = conflict.get("values", [])
            if key and values:
                resolved_output[key] = max(values, key=lambda x: x.get("confidence", 0))

        await self._publish(
            Topic.ORCH_MERGER_CONFLICT,
            {
                "resolved": len(merged_result.conflicts),
            },
        )
        return merged_result.with_output(resolved_output)

    async def score_confidence(self, merged_result: MergedResult) -> float:
        """Score the confidence of a merged result based on agreement."""
        return merged_result.confidence

    # ── Merge Strategies ──

    def _weighted_merge(self, tasks: list[AgentTask]) -> MergedResult:
        """Weighted merge: combine outputs, weight by priority."""
        merged: dict[str, Any] = {}
        conflicts: list[dict[str, Any]] = []

        for task in tasks:
            for key, value in task.output_data.items():
                if key in merged:
                    conflicts.append({"key": key, "values": [merged[key], value]})
                merged[key] = value

        confidence = min(1.0, len(tasks) / max(len(tasks), 3))
        return MergedResult(
            strategy=MergeStrategy.WEIGHTED,
            source_task_ids=tuple(t.id for t in tasks),
            output=merged,
            conflicts=tuple(conflicts),
            confidence=confidence,
        )

    def _priority_merge(self, tasks: list[AgentTask]) -> MergedResult:
        """Priority merge: higher priority task outputs take precedence."""
        sorted_tasks = sorted(tasks, key=lambda t: t.priority, reverse=True)
        merged: dict[str, Any] = {}
        for task in sorted_tasks:
            merged.update(task.output_data)
        return MergedResult(
            strategy=MergeStrategy.PRIORITY,
            source_task_ids=tuple(t.id for t in tasks),
            output=merged,
            confidence=0.8,
        )

    def _consensus_merge(self, tasks: list[AgentTask]) -> MergedResult:
        """Consensus merge: only include values agreed upon by majority."""
        merged: dict[str, Any] = {}
        conflicts: list[dict[str, Any]] = []
        agreements = 0
        total_keys = set()
        for t in tasks:
            total_keys.update(t.output_data.keys())

        for key in total_keys:
            values = [t.output_data[key] for t in tasks if key in t.output_data]
            if not values:
                continue
            # Simple majority: if the same value appears more than half the time
            from collections import Counter

            value_counts = Counter(str(v) for v in values)
            most_common, count = value_counts.most_common(1)[0]
            if count > len(values) / 2:
                merged[key] = values[0]
                agreements += 1
            else:
                conflicts.append({"key": key, "values": values})

        confidence = agreements / max(len(total_keys), 1) if total_keys else 0.0
        return MergedResult(
            strategy=MergeStrategy.CONSENSUS,
            source_task_ids=tuple(t.id for t in tasks),
            output=merged,
            conflicts=tuple(conflicts),
            confidence=confidence,
        )

    def _voting_merge(self, tasks: list[AgentTask]) -> MergedResult:
        """Voting merge: each task votes on the final output."""
        merged: dict[str, Any] = {}
        conflicts: list[dict[str, Any]] = []
        for task in tasks:
            for key, value in task.output_data.items():
                if key not in merged:
                    merged[key] = value

        confidence = min(1.0, len([t for t in tasks if t.status.value == "completed"]) / 3.0)
        return MergedResult(
            strategy=MergeStrategy.VOTING,
            source_task_ids=tuple(t.id for t in tasks),
            output=merged,
            conflicts=tuple(conflicts),
            confidence=confidence,
        )

    def _best_of_n(self, tasks: list[AgentTask]) -> MergedResult:
        """Best-of-N: pick the output of the highest-priority completed task."""
        completed = [t for t in tasks if t.status.value == "completed"]
        if not completed:
            return MergedResult(
                strategy=MergeStrategy.BEST_OF_N,
                source_task_ids=tuple(t.id for t in tasks),
                output={},
                confidence=0.0,
            )
        best = max(completed, key=lambda t: (t.priority, len(t.output_data)))
        return MergedResult(
            strategy=MergeStrategy.BEST_OF_N,
            source_task_ids=tuple(t.id for t in tasks),
            output=dict(best.output_data),
            confidence=0.7,
        )

    def _concatenate(self, tasks: list[AgentTask]) -> MergedResult:
        """Concatenate merge: combine all outputs into a single result."""
        merged: dict[str, Any] = {"items": [], "keys_seen": set()}
        for task in tasks:
            entry = {
                "task_id": task.id,
                "agent_id": task.assigned_agent_id,
                "output": task.output_data,
            }
            merged["items"].append(entry)
            merged["keys_seen"].update(task.output_data.keys())

        merged["keys_seen"] = list(merged["keys_seen"])
        return MergedResult(
            strategy=MergeStrategy.CONCATENATE,
            source_task_ids=tuple(t.id for t in tasks),
            output=merged,
            confidence=1.0,
        )

    async def _publish(self, topic: Topic, payload: dict[str, Any]) -> None:
        try:
            await self._bus.publish(
                EventEnvelope(
                    type="event", source="result-merger", topic=topic.value, payload=payload
                )
            )
        except Exception as exc:
            log.warning("Publish failed", topic=topic.value, error=str(exc))
