"""Tests for OrchestrationTelemetry (Phase 4, M3)."""

import pytest

from agentic_os.core.orchestration.telemetry import OrchestrationTelemetry
from agentic_os.domain.orchestration import (
    AgentTask,
    AgentTaskStatus,
    ConsensusResult,
    ConsensusStatus,
    OrchestrationGoal,
)


@pytest.fixture
def telemetry():
    return OrchestrationTelemetry(max_entries=50)


class TestOrchestrationTelemetry:
    def test_record_basic(self, telemetry) -> None:
        entry = telemetry.record(
            event_type="task.completed",
            swarm_id="s1",
            goal_id="g1",
            status="completed",
        )
        assert entry.event_type == "task.completed"
        assert entry.swarm_id == "s1"
        assert telemetry.entry_count == 1

    def test_record_with_details(self, telemetry) -> None:
        entry = telemetry.record(
            event_type="task.failed",
            status="failed",
            details={"error": "timeout", "task": "t1"},
        )
        assert entry.details["error"] == "timeout"

    def test_record_task(self, telemetry) -> None:
        task = AgentTask(
            title="test",
            goal_id="g1",
            status=AgentTaskStatus.COMPLETED,
            assigned_agent_id="a1",
        )
        entry = telemetry.record_task(task)
        assert entry.event_type == "task.completed"
        assert entry.goal_id == "g1"
        assert entry.status == "completed"

    def test_record_task_with_error(self, telemetry) -> None:
        task = AgentTask(
            title="test",
            status=AgentTaskStatus.FAILED,
            error="something broke",
        )
        entry = telemetry.record_task(task)
        assert entry.event_type == "task.failed"
        assert entry.details.get("error") == "something broke"

    def test_record_goal(self, telemetry) -> None:
        goal = OrchestrationGoal(title="test", status="running")
        entry = telemetry.record_goal(goal)
        assert entry.event_type == "goal.running"
        assert entry.status == "running"

    def test_record_consensus(self, telemetry) -> None:
        result = ConsensusResult(
            swarm_id="s1",
            topic="test",
            status=ConsensusStatus.REACHED,
            yea_count=3,
            nay_count=1,
            outcome=True,
        )
        entry = telemetry.record_consensus(result)
        assert entry.event_type == "consensus.reached"
        assert entry.details["yea"] == 3

    def test_get_entries_empty(self, telemetry) -> None:
        entries = telemetry.get_entries()
        assert entries == []

    def test_get_entries_with_limit(self, telemetry) -> None:
        for _i in range(10):
            telemetry.record(event_type="test", status="ok")
        entries = telemetry.get_entries(limit=3)
        assert len(entries) == 3

    def test_get_entries_filter_by_type(self, telemetry) -> None:
        telemetry.record(event_type="task.completed", status="ok")
        telemetry.record(event_type="task.failed", status="error")
        entries = telemetry.get_entries(event_type="task.completed")
        assert len(entries) == 1

    def test_get_entries_filter_by_swarm(self, telemetry) -> None:
        telemetry.record(event_type="test", swarm_id="s1", status="ok")
        telemetry.record(event_type="test", swarm_id="s2", status="ok")
        entries = telemetry.get_entries(swarm_id="s1")
        assert len(entries) == 1

    def test_get_entries_filter_by_goal(self, telemetry) -> None:
        telemetry.record(event_type="test", goal_id="g1", status="ok")
        telemetry.record(event_type="test", goal_id="g2", status="ok")
        entries = telemetry.get_entries(goal_id="g1")
        assert len(entries) == 1

    def test_get_entries_filter_by_agent(self, telemetry) -> None:
        telemetry.record(event_type="test", agent_id="a1", status="ok")
        telemetry.record(event_type="test", agent_id="a2", status="ok")
        entries = telemetry.get_entries(agent_id="a1")
        assert len(entries) == 1

    def test_get_stats_empty(self, telemetry) -> None:
        stats = telemetry.get_stats()
        assert stats["total_entries"] == 0

    def test_get_stats_populated(self, telemetry) -> None:
        telemetry.record(event_type="task.completed", status="ok")
        telemetry.record(event_type="task.failed", status="error")
        stats = telemetry.get_stats()
        assert stats["total_entries"] == 2
        assert stats["by_event_type"]["task.completed"] == 1

    def test_get_stats_unique_counts(self, telemetry) -> None:
        telemetry.record(event_type="test", swarm_id="s1", goal_id="g1", agent_id="a1", status="ok")
        telemetry.record(
            event_type="test2", swarm_id="s1", goal_id="g2", agent_id="a2", status="ok"
        )
        stats = telemetry.get_stats()
        assert stats["unique_swarms"] == 1
        assert stats["unique_goals"] == 2
        assert stats["unique_agents"] == 2

    def test_clear(self, telemetry) -> None:
        telemetry.record(event_type="test", status="ok")
        assert telemetry.entry_count == 1
        telemetry.clear()
        assert telemetry.entry_count == 0

    def test_max_entries_enforced(self) -> None:
        t = OrchestrationTelemetry(max_entries=3)
        for _i in range(10):
            t.record(event_type="test", status="ok")
        assert t.entry_count == 3

    def test_total_duration(self, telemetry) -> None:
        telemetry.record(event_type="test", duration_ms=100.0, status="ok")
        telemetry.record(event_type="test", duration_ms=200.0, status="ok")
        stats = telemetry.get_stats()
        assert stats["total_duration_ms"] == 300.0
