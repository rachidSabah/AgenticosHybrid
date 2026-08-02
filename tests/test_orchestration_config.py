"""Tests for orchestration configuration (Phase 4, M3)."""

from agentic_os.core.orchestration.config import OrchestrationConfiguration
from agentic_os.domain.orchestration import OrchestrationProfile, SwarmTopology


class TestOrchestrationConfiguration:
    def test_default_construction(self) -> None:
        config = OrchestrationConfiguration()
        assert config.enabled
        assert config.default_profile == "default"
        assert config.agent_sync_interval_seconds == 30.0
        assert config.communication_history_max == 1000
        assert config.telemetry_max_entries == 500
        assert config.default_quorum == 0.51
        assert config.default_topology == "mesh"

    def test_custom_construction(self) -> None:
        config = OrchestrationConfiguration(
            enabled=False,
            default_profile="fast",
            agent_sync_interval_seconds=10.0,
            communication_history_max=500,
            telemetry_max_entries=200,
            default_quorum=0.75,
            default_topology="star",
        )
        assert not config.enabled
        assert config.default_profile == "fast"
        assert config.agent_sync_interval_seconds == 10.0
        assert config.default_quorum == 0.75
        assert config.default_topology == "star"

    def test_add_and_get_profile(self) -> None:
        config = OrchestrationConfiguration()
        profile = OrchestrationProfile(
            name="fast",
            default_topology=SwarmTopology.STAR,
            max_agents_per_swarm=5,
        )
        config.add_profile(profile)
        retrieved = config.get_profile("fast")
        assert retrieved is not None
        assert retrieved.name == "fast"
        assert retrieved.max_agents_per_swarm == 5

    def test_get_default_profile(self) -> None:
        config = OrchestrationConfiguration()
        profile = config.get_profile()
        assert profile is not None
        assert profile.name == "default"

    def test_get_nonexistent_profile_returns_default(self) -> None:
        config = OrchestrationConfiguration()
        profile = config.get_profile("nonexistent")
        assert profile is not None
        assert profile.name == "default"

    def test_remove_profile(self) -> None:
        config = OrchestrationConfiguration()
        config.add_profile(OrchestrationProfile(name="fast"))
        assert config.remove_profile("fast")

    def test_remove_profile_not_found(self) -> None:
        config = OrchestrationConfiguration()
        assert not config.remove_profile("nonexistent")

    def test_remove_default_profile_not_allowed(self) -> None:
        config = OrchestrationConfiguration()
        assert not config.remove_profile("default")

    def test_get_profile_with_none_returns_default(self) -> None:
        config = OrchestrationConfiguration()
        profile = config.get_profile(None)
        assert profile.name == "default"

    def test_default_profile_values(self) -> None:
        config = OrchestrationConfiguration()
        profile = config.get_profile()
        assert profile.default_topology == SwarmTopology.MESH
        assert profile.max_agents_per_swarm == 10
        assert profile.auto_discover_agents
        assert profile.subtask_timeout_seconds == 60.0

    def test_multiple_profiles(self) -> None:
        config = OrchestrationConfiguration()
        config.add_profile(OrchestrationProfile(name="fast", max_agents_per_swarm=3))
        config.add_profile(OrchestrationProfile(name="slow", max_agents_per_swarm=20))
        fast = config.get_profile("fast")
        slow = config.get_profile("slow")
        assert fast.max_agents_per_swarm == 3
        assert slow.max_agents_per_swarm == 20
