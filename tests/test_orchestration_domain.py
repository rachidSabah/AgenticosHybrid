"""Tests for orchestration domain models (Phase 4, M3)."""

from agentic_os.domain.orchestration import (
    AgentDescriptor,
    AgentMessage,
    AgentTask,
    AgentTaskStatus,
    ConsensusResult,
    ConsensusStatus,
    CoordinationPattern,
    LeaderElectionResult,
    OrchestrationGoal,
    OrchestrationPlan,
    OrchestrationProfile,
    OrchestrationTelemetryEntry,
    SwarmSpec,
    SwarmState,
    SwarmTopology,
    Vote,
    VoteValue,
)


class TestSwarmTopology:
    def test_values(self) -> None:
        assert SwarmTopology.MESH == "mesh"
        assert SwarmTopology.STAR == "star"
        assert SwarmTopology.HIERARCHICAL == "hierarchical"
        assert SwarmTopology.RING == "ring"


class TestAgentTaskStatus:
    def test_values(self) -> None:
        assert AgentTaskStatus.PENDING == "pending"
        assert AgentTaskStatus.ASSIGNED == "assigned"
        assert AgentTaskStatus.RUNNING == "running"
        assert AgentTaskStatus.COMPLETED == "completed"
        assert AgentTaskStatus.FAILED == "failed"
        assert AgentTaskStatus.CANCELLED == "cancelled"
        assert AgentTaskStatus.TIMEOUT == "timeout"


class TestCoordinationPattern:
    def test_values(self) -> None:
        assert CoordinationPattern.SEQUENTIAL == "sequential"
        assert CoordinationPattern.PARALLEL == "parallel"
        assert CoordinationPattern.FAN_OUT == "fan_out"
        assert CoordinationPattern.FAN_IN == "fan_in"
        assert CoordinationPattern.HIERARCHICAL == "hierarchical"
        assert CoordinationPattern.VOTING == "voting"


class TestVoteValue:
    def test_values(self) -> None:
        assert VoteValue.YES == "yes"
        assert VoteValue.NO == "no"
        assert VoteValue.ABSTAIN == "abstain"


class TestConsensusStatus:
    def test_values(self) -> None:
        assert ConsensusStatus.PENDING == "pending"
        assert ConsensusStatus.IN_PROGRESS == "in_progress"
        assert ConsensusStatus.REACHED == "reached"
        assert ConsensusStatus.FAILED == "failed"
        assert ConsensusStatus.TIE == "tie"


class TestAgentDescriptor:
    def test_construction(self) -> None:
        desc = AgentDescriptor(
            agent_id="engine-1",
            name="Test Engine",
            engine_type="generic",
            capabilities=("code", "research"),
            status="idle",
            health_status="healthy",
            latency_ms=50.0,
        )
        assert desc.agent_id == "engine-1"
        assert desc.name == "Test Engine"
        assert desc.engine_type == "generic"
        assert desc.capabilities == ("code", "research")
        assert desc.status == "idle"
        assert desc.latency_ms == 50.0

    def test_defaults(self) -> None:
        desc = AgentDescriptor(agent_id="e1", name="E1")
        assert desc.status == "unknown"
        assert desc.health_status == "unknown"
        assert desc.latency_ms == 0.0
        assert not desc.is_leader
        assert desc.swarm_id is None
        assert desc.metadata == {}

    def test_to_dict(self) -> None:
        desc = AgentDescriptor(
            agent_id="e1",
            name="E1",
            engine_type="generic",
            capabilities=("code",),
            status="idle",
        )
        d = desc.to_dict()
        assert d["agent_id"] == "e1"
        assert d["capabilities"] == ["code"]
        assert d["is_leader"] is False

    def test_with_leader(self) -> None:
        desc = AgentDescriptor(agent_id="e1", name="E1", engine_type="generic")
        leader = desc.with_leader(True)
        assert leader.is_leader
        assert not desc.is_leader  # immutable

    def test_with_swarm(self) -> None:
        desc = AgentDescriptor(agent_id="e1", name="E1", engine_type="generic")
        with_swarm = desc.with_swarm("swarm-1")
        assert with_swarm.swarm_id == "swarm-1"
        assert desc.swarm_id is None


class TestSwarmSpec:
    def test_construction(self) -> None:
        spec = SwarmSpec(
            name="test-swarm",
            description="A test swarm",
            topology=SwarmTopology.STAR,
            agent_ids=("a1", "a2", "a3"),
        )
        assert spec.name == "test-swarm"
        assert spec.topology == SwarmTopology.STAR
        assert spec.agent_ids == ("a1", "a2", "a3")
        assert spec.id is not None

    def test_default_topology(self) -> None:
        spec = SwarmSpec(name="default")
        assert spec.topology == SwarmTopology.MESH

    def test_to_dict(self) -> None:
        spec = SwarmSpec(name="s1", agent_ids=("a1", "a2"))
        d = spec.to_dict()
        assert d["name"] == "s1"
        assert d["agent_ids"] == ["a1", "a2"]
        assert d["topology"] == "mesh"

    def test_with_agent(self) -> None:
        spec = SwarmSpec(name="s1", agent_ids=("a1",))
        updated = spec.with_agent("a2")
        assert updated.agent_ids == ("a1", "a2")
        assert spec.agent_ids == ("a1",)  # immutable

    def test_with_agent_duplicate(self) -> None:
        spec = SwarmSpec(name="s1", agent_ids=("a1",))
        updated = spec.with_agent("a1")
        assert updated.agent_ids == ("a1",)  # no duplicate

    def test_without_agent(self) -> None:
        spec = SwarmSpec(name="s1", agent_ids=("a1", "a2", "a3"))
        updated = spec.without_agent("a2")
        assert updated.agent_ids == ("a1", "a3")

    def test_with_leader(self) -> None:
        spec = SwarmSpec(name="s1")
        updated = spec.with_leader("a1")
        assert updated.leader_id == "a1"

    def test_with_topology(self) -> None:
        spec = SwarmSpec(name="s1")
        updated = spec.with_topology(SwarmTopology.RING)
        assert updated.topology == SwarmTopology.RING


class TestSwarmState:
    def test_construction(self) -> None:
        state = SwarmState(swarm_id="s1", active=True)
        assert state.swarm_id == "s1"
        assert state.active
        assert state.agent_states == {}

    def test_with_active(self) -> None:
        state = SwarmState(swarm_id="s1")
        activated = state.with_active(True)
        assert activated.active
        assert not state.active

    def test_with_task(self) -> None:
        state = SwarmState(swarm_id="s1")
        with_task = state.with_task("task-1")
        assert with_task.current_task_id == "task-1"

    def test_with_agent_state(self) -> None:
        state = SwarmState(swarm_id="s1")
        updated = state.with_agent_state("a1", "running")
        assert updated.agent_states == {"a1": "running"}

    def test_to_dict(self) -> None:
        state = SwarmState(swarm_id="s1", active=True)
        d = state.to_dict()
        assert d["swarm_id"] == "s1"
        assert d["active"] is True


class TestOrchestrationGoal:
    def test_construction(self) -> None:
        goal = OrchestrationGoal(
            title="test-goal",
            description="Do something",
            context={"key": "value"},
        )
        assert goal.title == "test-goal"
        assert goal.status == "pending"

    def test_with_status(self) -> None:
        goal = OrchestrationGoal(title="g1")
        completed = goal.with_status("completed")
        assert completed.status == "completed"
        assert goal.status == "pending"

    def test_with_swarm(self) -> None:
        goal = OrchestrationGoal(title="g1")
        assigned = goal.with_swarm("s1")
        assert assigned.swarm_id == "s1"

    def test_to_dict(self) -> None:
        goal = OrchestrationGoal(title="g1", context={"k": "v"})
        d = goal.to_dict()
        assert d["title"] == "g1"
        assert d["context"] == {"k": "v"}


class TestAgentTask:
    def test_construction(self) -> None:
        task = AgentTask(
            title="test-task",
            description="Do a thing",
            input_data={"x": 1},
            timeout_seconds=30.0,
        )
        assert task.title == "test-task"
        assert task.status == AgentTaskStatus.PENDING
        assert task.timeout_seconds == 30.0

    def test_with_assigned(self) -> None:
        task = AgentTask(title="t1")
        assigned = task.with_assigned("a1")
        assert assigned.assigned_agent_id == "a1"
        assert assigned.status == AgentTaskStatus.ASSIGNED

    def test_with_output(self) -> None:
        task = AgentTask(title="t1")
        completed = task.with_output({"result": "ok"})
        assert completed.status == AgentTaskStatus.COMPLETED
        assert completed.output_data == {"result": "ok"}
        assert completed.completed_at is not None

    def test_with_error(self) -> None:
        task = AgentTask(title="t1")
        failed = task.with_error("Something broke")
        assert failed.status == AgentTaskStatus.FAILED
        assert failed.error == "Something broke"

    def test_with_status(self) -> None:
        task = AgentTask(title="t1")
        running = task.with_status(AgentTaskStatus.RUNNING)
        assert running.status == AgentTaskStatus.RUNNING

    def test_to_dict(self) -> None:
        task = AgentTask(title="t1", input_data={"a": 1})
        d = task.to_dict()
        assert d["title"] == "t1"
        assert d["input_data"] == {"a": 1}
        assert d["coordination_pattern"] is None


class TestOrchestrationPlan:
    def test_construction(self) -> None:
        plan = OrchestrationPlan(goal_id="g1")
        assert plan.goal_id == "g1"
        assert plan.status == "pending"
        assert plan.subtasks == ()

    def test_with_subtask(self) -> None:
        plan = OrchestrationPlan(goal_id="g1")
        task = AgentTask(title="t1")
        updated = plan.with_subtask(task)
        assert len(updated.subtasks) == 1

    def test_with_status(self) -> None:
        plan = OrchestrationPlan(goal_id="g1")
        completed = plan.with_status("completed")
        assert completed.status == "completed"

    def test_with_completed(self) -> None:
        plan = OrchestrationPlan(goal_id="g1")
        completed = plan.with_completed()
        assert completed.status == "completed"
        assert completed.completed_at is not None

    def test_to_dict(self) -> None:
        task = AgentTask(title="t1")
        plan = OrchestrationPlan(goal_id="g1", subtasks=(task,))
        d = plan.to_dict()
        assert d["goal_id"] == "g1"
        assert len(d["subtasks"]) == 1


class TestVote:
    def test_construction(self) -> None:
        vote = Vote(
            voter_id="a1",
            value=VoteValue.YES,
            rationale="Good idea",
            weight=1.0,
        )
        assert vote.voter_id == "a1"
        assert vote.value == VoteValue.YES
        assert vote.weight == 1.0

    def test_to_dict(self) -> None:
        vote = Vote(voter_id="a1", value=VoteValue.NO)
        d = vote.to_dict()
        assert d["value"] == "no"


class TestConsensusResult:
    def test_construction(self) -> None:
        result = ConsensusResult(swarm_id="s1", topic="approve-deploy")
        assert result.status == ConsensusStatus.PENDING
        assert result.threshold == 0.51

    def test_with_vote_reached(self) -> None:
        result = ConsensusResult(swarm_id="s1", topic="t1")
        result = result.with_vote(Vote("a1", VoteValue.YES, weight=1.0))
        result = result.with_vote(Vote("a2", VoteValue.YES, weight=1.0))
        assert result.status == ConsensusStatus.REACHED
        assert result.outcome
        assert result.yea_count == 2

    def test_with_vote_failed(self) -> None:
        result = ConsensusResult(swarm_id="s1", topic="t1", threshold=0.75)
        result = result.with_vote(Vote("a1", VoteValue.YES, weight=1.0))
        result = result.with_vote(Vote("a2", VoteValue.NO, weight=1.0))
        assert result.status == ConsensusStatus.IN_PROGRESS
        assert not result.outcome

    def test_with_vote_abstain(self) -> None:
        result = ConsensusResult(swarm_id="s1", topic="t1")
        result = result.with_vote(Vote("a1", VoteValue.YES, weight=1.0))
        result = result.with_vote(Vote("a2", VoteValue.ABSTAIN, weight=1.0))
        assert result.yea_count == 1
        assert result.abstain_count == 1

    def test_with_status(self) -> None:
        result = ConsensusResult(swarm_id="s1", topic="t1")
        failed = result.with_status(ConsensusStatus.FAILED)
        assert failed.status == ConsensusStatus.FAILED
        assert failed.completed_at is not None

    def test_with_outcome(self) -> None:
        result = ConsensusResult(swarm_id="s1", topic="t1")
        result = result.with_outcome(True)
        assert result.outcome
        assert result.status == ConsensusStatus.REACHED

    def test_to_dict(self) -> None:
        result = ConsensusResult(swarm_id="s1", topic="t1")
        d = result.to_dict()
        assert d["swarm_id"] == "s1"


class TestLeaderElectionResult:
    def test_construction(self) -> None:
        result = LeaderElectionResult(
            swarm_id="s1",
            elected_leader_id="a1",
            candidates=("a1", "a2"),
            vote_counts={"a1": 5, "a2": 3},
            total_votes=8,
        )
        assert result.elected_leader_id == "a1"
        assert result.total_votes == 8

    def test_to_dict(self) -> None:
        result = LeaderElectionResult(
            swarm_id="s1",
            elected_leader_id="a1",
        )
        d = result.to_dict()
        assert d["elected_leader_id"] == "a1"


class TestAgentMessage:
    def test_construction(self) -> None:
        msg = AgentMessage(
            source_agent_id="a1",
            target_agent_id="a2",
            swarm_id="s1",
            message_type="direct",
            payload={"text": "hello"},
        )
        assert msg.source_agent_id == "a1"
        assert msg.payload == {"text": "hello"}

    def test_broadcast_default(self) -> None:
        msg = AgentMessage(source_agent_id="a1", swarm_id="s1")
        assert msg.target_agent_id is None
        assert msg.message_type == "broadcast"

    def test_with_response(self) -> None:
        msg = AgentMessage(
            source_agent_id="a1",
            target_agent_id="a2",
            swarm_id="s1",
        )
        response = msg.with_response({"result": "done"})
        assert response.source_agent_id == "a2"
        assert response.target_agent_id == "a1"
        assert response.correlation_id == msg.id
        assert response.message_type == "response"

    def test_to_dict(self) -> None:
        msg = AgentMessage(source_agent_id="a1", swarm_id="s1")
        d = msg.to_dict()
        assert d["source_agent_id"] == "a1"


class TestOrchestrationTelemetryEntry:
    def test_construction(self) -> None:
        entry = OrchestrationTelemetryEntry(
            event_type="task.completed",
            swarm_id="s1",
            status="completed",
        )
        assert entry.event_type == "task.completed"
        assert entry.duration_ms == 0.0

    def test_to_dict(self) -> None:
        entry = OrchestrationTelemetryEntry(event_type="test")
        d = entry.to_dict()
        assert d["event_type"] == "test"


class TestOrchestrationProfile:
    def test_construction(self) -> None:
        profile = OrchestrationProfile(
            name="fast",
            description="Fast execution",
            default_topology=SwarmTopology.STAR,
            max_agents_per_swarm=5,
            subtask_timeout_seconds=30.0,
        )
        assert profile.name == "fast"
        assert profile.max_agents_per_swarm == 5

    def test_defaults(self) -> None:
        profile = OrchestrationProfile(name="default")
        assert profile.default_topology == SwarmTopology.MESH
        assert profile.max_agents_per_swarm == 10
        assert profile.auto_discover_agents

    def test_to_dict(self) -> None:
        profile = OrchestrationProfile(name="p1")
        d = profile.to_dict()
        assert d["name"] == "p1"
