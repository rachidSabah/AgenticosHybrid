"""Tests for orchestration strategies (Phase 4, M3)."""

import pytest

from agentic_os.core.orchestration.strategies.consensus import (
    SimpleMajorityConsensus,
    WeightedConsensus,
)
from agentic_os.core.orchestration.strategies.decomposition import (
    LLMDecomposition,
    RuleBasedDecomposition,
    TemplateBasedDecomposition,
)
from agentic_os.domain.orchestration import (
    AgentDescriptor,
    ConsensusResult,
    ConsensusStatus,
    OrchestrationGoal,
    VoteValue,
)


class _MockBus:
    async def publish(self, envelope):
        pass


@pytest.fixture
def bus():
    return _MockBus()


class TestRuleBasedDecomposition:
    @pytest.fixture
    def strategy(self):
        return RuleBasedDecomposition()

    async def test_code_goal(self, strategy) -> None:
        goal = OrchestrationGoal(
            title="Implement authentication middleware", context={"lang": "python"}
        )
        tasks = await strategy.decompose(goal)
        assert len(tasks) == 4
        titles = [t.title for t in tasks]
        assert "Implement changes" in titles

    async def test_research_goal(self, strategy) -> None:
        goal = OrchestrationGoal(title="Research vector databases")
        tasks = await strategy.decompose(goal)
        assert len(tasks) == 4
        titles = [t.title for t in tasks]
        # "research" keyword matches → research template produces "Define research scope"
        assert "Define research scope" in titles

    async def test_deploy_goal(self, strategy) -> None:
        goal = OrchestrationGoal(title="Deploy to production")
        tasks = await strategy.decompose(goal)
        assert len(tasks) == 4

    async def test_test_goal(self, strategy) -> None:
        goal = OrchestrationGoal(title="Write unit tests")
        tasks = await strategy.decompose(goal)
        assert len(tasks) == 4

    async def test_analyze_goal(self, strategy) -> None:
        goal = OrchestrationGoal(title="Analyze performance metrics")
        tasks = await strategy.decompose(goal)
        assert len(tasks) == 4

    async def test_unknown_goal(self, strategy) -> None:
        goal = OrchestrationGoal(title="Do something random")
        tasks = await strategy.decompose(goal)
        # Falls back to "analyze" template which has 4 tasks
        assert len(tasks) == 4

    async def test_code_tasks_have_deps(self, strategy) -> None:
        goal = OrchestrationGoal(title="Implement feature")
        tasks = await strategy.decompose(goal)
        if len(tasks) > 1:
            assert tasks[1].depends_on  # subsequent tasks depend on previous

    async def test_strategy_name(self, strategy) -> None:
        assert strategy.name == "rule-based"


class TestTemplateBasedDecomposition:
    @pytest.fixture
    def strategy(self):
        return TemplateBasedDecomposition()

    async def test_default_template(self, strategy) -> None:
        goal = OrchestrationGoal(title="test", context={})
        tasks = await strategy.decompose(goal)
        # Falls back to rule-based → "test" keyword matches test template (4 tasks)
        assert len(tasks) == 4

    async def test_named_template(self, strategy) -> None:
        goal = OrchestrationGoal(
            title="test",
            context={"template": "code"},
        )
        tasks = await strategy.decompose(goal)
        assert len(tasks) > 0
        assert any("Write" in t.title or "Define" in t.title or "Test" in t.title for t in tasks)

    async def test_strategy_name(self, strategy) -> None:
        assert strategy.name == "template-based"


class TestLLMDecomposition:
    @pytest.fixture
    def strategy(self):
        return LLMDecomposition()

    async def test_returns_single_composite(self, strategy) -> None:
        goal = OrchestrationGoal(title="Complex task")
        tasks = await strategy.decompose(goal)
        assert len(tasks) == 1
        assert tasks[0].title == "Complex task"

    async def test_strategy_name(self, strategy) -> None:
        assert strategy.name == "llm"

    async def test_output_includes_all(self, strategy) -> None:
        goal = OrchestrationGoal(title="Full stack feature", context={"req": "build everything"})
        tasks = await strategy.decompose(goal)
        assert tasks[0].description == "Execute: Full stack feature"


class TestSimpleMajorityConsensus:
    @pytest.fixture
    def strategy(self):
        return SimpleMajorityConsensus()

    async def test_no_agents(self, strategy, bus) -> None:
        result = await strategy.reach_consensus(
            swarm_id="s1",
            topic="test",
            proposals=[],
            agents=[],
            bus=bus,
        )
        assert result.status == ConsensusStatus.FAILED
        assert not result.outcome

    async def test_majority_yes(self, strategy, bus) -> None:
        agents = [
            AgentDescriptor(
                agent_id="a1",
                name="A1",
                engine_type="generic",
                capabilities=("code",),
                latency_ms=10.0,
                health_status="healthy",
            ),
            AgentDescriptor(
                agent_id="a2",
                name="A2",
                engine_type="generic",
                capabilities=("code",),
                latency_ms=10.0,
                health_status="healthy",
            ),
            AgentDescriptor(
                agent_id="a3",
                name="A3",
                engine_type="generic",
                capabilities=("code",),
                latency_ms=200.0,
                health_status="healthy",
            ),
        ]
        result = await strategy.reach_consensus(
            swarm_id="s1",
            topic="approve",
            proposals=[],
            agents=agents,
            bus=bus,
        )
        assert isinstance(result, ConsensusResult)
        assert len(result.votes) == 3

    async def test_single_agent(self, strategy, bus) -> None:
        agents = [
            AgentDescriptor(
                agent_id="a1",
                name="A1",
                engine_type="generic",
                capabilities=("code",),
                latency_ms=10.0,
                health_status="healthy",
            ),
        ]
        result = await strategy.reach_consensus(
            swarm_id="s1",
            topic="single",
            proposals=[],
            agents=agents,
            bus=bus,
        )
        assert len(result.votes) == 1

    async def test_all_votes_are_vote_objects(self, strategy, bus) -> None:
        agents = [
            AgentDescriptor(
                agent_id="a1",
                name="A1",
                engine_type="generic",
                capabilities=("code",),
                latency_ms=50.0,
                health_status="healthy",
            ),
            AgentDescriptor(
                agent_id="a2",
                name="A2",
                engine_type="generic",
                capabilities=("research",),
                latency_ms=50.0,
                health_status="healthy",
            ),
        ]
        result = await strategy.reach_consensus(
            swarm_id="s1",
            topic="test",
            proposals=[],
            agents=agents,
            bus=bus,
        )
        for vote in result.votes:
            assert vote.voter_id in ("a1", "a2")
            assert vote.value in (VoteValue.YES, VoteValue.NO)


class TestWeightedConsensus:
    @pytest.fixture
    def strategy(self):
        return WeightedConsensus()

    async def test_no_agents(self, strategy, bus) -> None:
        result = await strategy.reach_consensus(
            swarm_id="s1",
            topic="test",
            proposals=[],
            agents=[],
            bus=bus,
        )
        assert result.status == ConsensusStatus.FAILED

    async def test_weighted_voting(self, strategy, bus) -> None:
        agents = [
            AgentDescriptor(
                agent_id="a1",
                name="A1",
                engine_type="generic",
                capabilities=("code",),
                latency_ms=10.0,
                status="idle",
            ),
            AgentDescriptor(
                agent_id="a2",
                name="A2",
                engine_type="generic",
                capabilities=("research",),
                latency_ms=300.0,
                status="idle",
            ),
        ]
        result = await strategy.reach_consensus(
            swarm_id="s1",
            topic="test",
            proposals=[],
            agents=agents,
            bus=bus,
        )
        assert isinstance(result, ConsensusResult)
        assert result.total_weight > 0
        # a1 has low latency -> higher weight -> greater say
        assert result.yea_weight <= result.total_weight

    async def test_weights_differ_by_latency(self, strategy, bus) -> None:
        agents = [
            AgentDescriptor(
                agent_id="fast",
                name="Fast",
                engine_type="generic",
                capabilities=("code",),
                latency_ms=5.0,
                status="idle",
            ),
            AgentDescriptor(
                agent_id="slow",
                name="Slow",
                engine_type="generic",
                capabilities=("code",),
                latency_ms=500.0,
                status="idle",
            ),
        ]
        result = await strategy.reach_consensus(
            swarm_id="s1",
            topic="test",
            proposals=[],
            agents=agents,
            bus=bus,
        )
        votes = {v.voter_id: v.weight for v in result.votes}
        assert votes.get("fast", 0) > votes.get("slow", 0)
